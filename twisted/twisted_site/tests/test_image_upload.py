import json
from io import BytesIO
from typing import cast, override
from unittest.mock import patch

from botocore.exceptions import ClientError
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.files.uploadedfile import UploadedFile as DjangoUploadedFile
from django.http import HttpResponse
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse
from PIL import Image

from twisted_site.models import Profile, UploadedFile
from twisted_site.views import image_upload

_MAX_FILE_BYTES = 10 * 1024 * 1024


class ImageUploadTests(TestCase):
    user: User  # pyright: ignore[reportUninitializedInstanceVariable]
    profile: Profile  # pyright: ignore[reportUninitializedInstanceVariable]

    @override
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="uploader")
        self.profile = Profile.objects.create(user=self.user, slack_username="Uploader")
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

    def png_bytes(self) -> bytes:
        output = BytesIO()
        image = Image.new("RGB", (2, 2), color="red")
        _ = image.save(output, format="PNG")
        return output.getvalue()

    def test_anonymous_upload_is_rejected(self) -> None:
        self.client.logout()
        file = SimpleUploadedFile("proof.png", self.png_bytes(), content_type="image/png")

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

    def test_spoofed_image_content_is_rejected(self) -> None:
        file = SimpleUploadedFile(
            "proof.png",
            b"<script>alert(1)</script>",
            content_type="image/png",
        )
        with patch("twisted_site.views.image_upload.file_uploader") as uploader:
            response = self.upload(file)

        body = self.response_json(response)
        self.assertEqual(body["status"], "error")
        self.assertIn("not a valid image", str(body["reason"]))
        uploader.assert_not_called()
        self.assertFalse(UploadedFile.objects.exists())

    def test_image_extension_must_match_detected_format(self) -> None:
        file = SimpleUploadedFile(
            "proof.svg",
            self.png_bytes(),
            content_type="image/png",
        )
        with patch("twisted_site.views.image_upload.file_uploader") as uploader:
            response = self.upload(file)

        body = self.response_json(response)
        self.assertEqual(body["status"], "error")
        self.assertIn("extension", str(body["reason"]))
        uploader.assert_not_called()
        self.assertFalse(UploadedFile.objects.exists())

    def test_successful_upload_is_recorded(self) -> None:
        file = SimpleUploadedFile("proof.png", self.png_bytes(), content_type="image/png")
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
        self.assertEqual(str(uploaded_file), "proof uploaded by Uploader")

    def test_uploader_failure_does_not_create_database_record(self) -> None:
        file = SimpleUploadedFile("proof.png", self.png_bytes(), content_type="image/png")
        with patch(
            "twisted_site.views.image_upload.file_uploader",
            return_value={"status": "error", "error": "R2 unavailable"},
        ):
            response = self.upload(file)

        self.assertEqual(self.response_json(response)["status"], "error")
        self.assertFalse(UploadedFile.objects.exists())


class R2UploaderTests(SimpleTestCase):
    def test_upload_fileobj_uses_safe_generated_key(self) -> None:
        file = SimpleUploadedFile("My Proof.PNG", b"png", content_type="image/png")
        with (
            patch.dict(
                "os.environ",
                {"R2_BUCKET": "test-bucket", "R2_PUBLIC_URL": "https://cdn.example"},
            ),
            patch("twisted_site.views.image_upload.uuid4", return_value="fixed-id"),
            patch("twisted_site.views.image_upload.s3") as s3,
        ):
            result = image_upload.file_uploader(file)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["name"], "My Proof")
        self.assertEqual(result["link"], "https://cdn.example/fixed-id-3/my-proof.png")
        s3.upload_fileobj.assert_called_once_with(
            file,
            "test-bucket",
            "fixed-id-3/my-proof.png",
            ExtraArgs={"ContentType": "image/png"},
        )

    def test_r2_client_error_is_returned_as_upload_error(self) -> None:
        error = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Denied"}},
            "PutObject",
        )
        file = SimpleUploadedFile("proof.png", b"png", content_type="image/png")
        with patch("twisted_site.views.image_upload.s3.upload_fileobj", side_effect=error):
            result = image_upload.file_uploader(file)

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"], "Could not upload file")

    def test_missing_filename_is_rejected(self) -> None:
        file = SimpleUploadedFile("proof.png", b"png", content_type="image/png")
        file.name = None

        result = image_upload.file_uploader(file)

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"], "Uploaded file is missing a filename")
