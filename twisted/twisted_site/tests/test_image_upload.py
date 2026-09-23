import json
from typing import cast, override
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.files.uploadedfile import UploadedFile as DjangoUploadedFile
from django.http import HttpResponse
from django.test import Client, TestCase
from django.urls import reverse

from twisted_site.models import Profile, UploadedFile

_MAX_FILE_BYTES = 10 * 1024 * 1024


class ImageUploadTests(TestCase):
    user: User  # pyright: ignore[reportUninitializedInstanceVariable]
    profile: Profile  # pyright: ignore[reportUninitializedInstanceVariable]

    @override
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="uploader")
        self.profile = Profile.objects.create(user=self.user)
        self.client = Client()
        self.client.force_login(self.user)

    def upload(self, file: SimpleUploadedFile) -> HttpResponse:
        return cast(
            "HttpResponse",
            cast(
                "object",
                self.client.post(
                    reverse("misc.upload_file"),
                    {"file": file, "ref": "test"},
                ),
            ),
        )

    def response_json(self, response: HttpResponse) -> dict[str, object]:
        return cast("dict[str, object]", json.loads(response.content))

    def test_anonymous_upload_is_rejected(self) -> None:
        self.client.logout()
        file = SimpleUploadedFile("proof.png", b"image", content_type="image/png")

        response = self.upload(file)

        self.assertEqual(response.status_code, 302)
        self.assertFalse(UploadedFile.objects.exists())

    def test_disallowed_content_type_is_rejected_before_upload(self) -> None:
        file = SimpleUploadedFile("payload.html", b"<script>", content_type="text/html")
        with patch("twisted_site.views.image_upload.file_uploader") as uploader:
            response = self.upload(file)

        self.assertEqual(self.response_json(response)["status"], "error")
        uploader.assert_not_called()
        self.assertFalse(UploadedFile.objects.exists())

    def test_file_over_ten_megabytes_is_rejected(self) -> None:
        file = SimpleUploadedFile(
            "large.png",
            b"x" * (_MAX_FILE_BYTES + 1),
            content_type="image/png",
        )
        with patch("twisted_site.views.image_upload.file_uploader") as uploader:
            response = self.upload(file)

        body = self.response_json(response)
        self.assertEqual(body["status"], "error")
        self.assertIn("10MB", str(body["reason"]))
        uploader.assert_not_called()
        self.assertFalse(UploadedFile.objects.exists())

    def test_successful_upload_is_recorded(self) -> None:
        file = SimpleUploadedFile("proof.png", b"image", content_type="image/png")
        uploader_result = {
            "status": "ok",
            "link": "https://uploads.example/proof.png",
            "name": "proof",
            "size": len(file),
        }
        with patch(
            "twisted_site.views.image_upload.file_uploader",
            return_value=uploader_result,
        ) as uploader:
            response = self.upload(file)

        self.assertEqual(self.response_json(response)["status"], "ok")
        uploader.assert_called_once()
        uploaded_argument = cast("DjangoUploadedFile[bytes]", uploader.call_args.args[0])
        self.assertEqual(uploaded_argument.name, "proof.png")
        self.assertEqual(uploaded_argument.content_type, "image/png")
        self.assertEqual(uploaded_argument.size, len(file))
        uploaded_file = UploadedFile.objects.get()
        self.assertEqual(uploaded_file.uploaded_by, self.user)
        self.assertEqual(uploaded_file.link, uploader_result["link"])
        self.assertEqual(uploaded_file.filesize, len(file))
        self.assertEqual(uploaded_file.uploaded_thru, "test")

    def test_uploader_failure_does_not_create_database_record(self) -> None:
        file = SimpleUploadedFile("proof.png", b"image", content_type="image/png")
        with patch(
            "twisted_site.views.image_upload.file_uploader",
            return_value={"status": "error", "error": "R2 unavailable"},
        ):
            response = self.upload(file)

        self.assertEqual(self.response_json(response)["status"], "error")
        self.assertFalse(UploadedFile.objects.exists())
