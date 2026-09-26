from typing import override
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from requests import HTTPError

from twisted_site.models import Profile, Project, ProjectShip


class ProjectSettingsTests(TestCase):
    user: User  # pyright: ignore[reportUninitializedInstanceVariable]
    profile: Profile  # pyright: ignore[reportUninitializedInstanceVariable]
    other_user: User  # pyright: ignore[reportUninitializedInstanceVariable]
    other_profile: Profile  # pyright: ignore[reportUninitializedInstanceVariable]
    project: Project  # pyright: ignore[reportUninitializedInstanceVariable]

    @override
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="settings-owner")
        self.profile = Profile.objects.create(user=self.user, hackatime_access_token="token")
        self.other_user = User.objects.create_user(username="settings-other")
        self.other_profile = Profile.objects.create(user=self.other_user)
        self.project = Project.objects.create(
            user=self.user,
            project_name="Original",
            project_description="Original description",
            project_type="software",
        )
        self.client = Client()
        self.client.force_login(self.user)

    def settings_url(self) -> str:
        return reverse("fr.projects.settings", kwargs={"project_id": self.project.pk})

    def detail_url(self) -> str:
        return reverse("fr.projects.detail", kwargs={"project_id": self.project.pk})

    def valid_post_data(self) -> dict[str, object]:
        return {
            "name": "Updated",
            "description": "Updated description",
            "type": "hardware",
            "hackatime": ["First", "Second"],
            "repo": "https://github.com/example/repo",
            "playable_url": "https://example.com/play",
            "screenshot_url": "https://example.com/image.png",
        }

    def test_owner_can_update_project_settings(self) -> None:
        with patch("twisted_site.views.client.project.log_to_channel") as log_to_channel:
            response = self.client.post(self.settings_url(), self.valid_post_data())

        self.assertRedirects(response, self.detail_url(), fetch_redirect_response=False)
        self.project.refresh_from_db()
        self.assertEqual(self.project.project_name, "Updated")
        self.assertEqual(self.project.project_type, "hardware")
        self.assertEqual(self.project.hackatime_project_names, ["First", "Second"])
        self.assertEqual(self.project.repo_url, "https://github.com/example/repo")
        log_to_channel.assert_called_once()

    def test_non_owner_cannot_read_or_update_settings(self) -> None:
        self.client.force_login(self.other_user)

        get_response = self.client.get(self.settings_url())
        post_response = self.client.post(self.settings_url(), self.valid_post_data())

        self.assertRedirects(get_response, reverse("dashboard"))
        self.assertRedirects(post_response, reverse("dashboard"))
        self.project.refresh_from_db()
        self.assertEqual(self.project.project_name, "Original")

    def test_shipped_project_settings_redirect_to_detail(self) -> None:
        _ = ProjectShip.objects.create(project=self.project)

        response = self.client.get(self.settings_url())

        self.assertRedirects(response, self.detail_url())

    def test_invalid_project_type_is_rejected_without_changes(self) -> None:
        data = self.valid_post_data()
        data["type"] = "invalid"

        with patch("twisted_site.views.client.project.log_to_channel") as log_to_channel:
            response = self.client.post(self.settings_url(), data)

        self.assertEqual(response.status_code, 200)
        self.project.refresh_from_db()
        self.assertEqual(self.project.project_type, "software")
        log_to_channel.assert_not_called()

    def test_hackatime_failure_renders_settings_with_no_projects(self) -> None:
        with patch(
            "twisted_site.views.client.project.hackatime.projects",
            side_effect=HTTPError("Hackatime unavailable"),
        ):
            response = self.client.get(self.settings_url())

        self.assertEqual(response.status_code, 200)
