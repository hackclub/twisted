from typing import override
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from twisted_site.models import Journal, Profile, Project, ProjectShip


class SubmitProjectTests(TestCase):
    user: User  # pyright: ignore[reportUninitializedInstanceVariable]
    profile: Profile  # pyright: ignore[reportUninitializedInstanceVariable]
    project: Project  # pyright: ignore[reportUninitializedInstanceVariable]
    other_user: User  # pyright: ignore[reportUninitializedInstanceVariable]
    other_profile: Profile  # pyright: ignore[reportUninitializedInstanceVariable]

    @override
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="owner")
        self.profile = Profile.objects.create(user=self.user, ysws_eligible=True)
        self.project = Project.objects.create(
            user=self.user,
            project_name="Submission",
            project_description="Description",
            project_type="software",
            playable_url="https://example.com/play",
            screenshot_url="https://example.com/screenshot.png",
        )
        self.other_user = User.objects.create_user(username="other")
        self.other_profile = Profile.objects.create(user=self.other_user)
        self.client = Client()
        self.client.force_login(self.user)

    def ship_url(self) -> str:
        return reverse("fr.projects.ship", kwargs={"project_id": self.project.pk})

    def detail_url(self) -> str:
        return reverse("fr.projects.detail", kwargs={"project_id": self.project.pk})

    def test_owner_submission_creates_ship_and_notifies_integrations(self) -> None:
        with (
            patch("twisted_site.views.client.project.ari.send_ship") as send_ship,
            patch("twisted_site.views.client.project.log_to_channel") as log_to_channel,
        ):
            response = self.client.post(self.ship_url())

        self.assertRedirects(response, self.detail_url(), fetch_redirect_response=False)
        ship = ProjectShip.objects.get(project=self.project)
        send_ship.assert_called_once_with(ship)
        log_to_channel.assert_called_once()

    def test_failed_ari_delivery_removes_new_ship_and_shows_an_error(self) -> None:
        with (
            self.assertLogs("twisted_site.views.client.project", level="ERROR"),
            patch(
                "twisted_site.views.client.project.ari.send_ship",
                side_effect=RuntimeError("Ari unavailable"),
            ),
            patch("twisted_site.views.client.project.log_to_channel"),
        ):
            response = self.client.post(self.ship_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "temporarily unavailable")
        self.assertFalse(ProjectShip.objects.filter(project=self.project).exists())

    def test_ship_link_is_available_at_exactly_sixty_minutes(self) -> None:
        self.project.repo_url = "https://github.com/example/repo"
        self.project.save(update_fields=("repo_url",))
        _ = Journal.objects.create(
            project=self.project,
            type="untracked",
            content="A sufficiently detailed journal entry for the test project.",
            minutes_worked=60,
            reduced_minutes=60,
        )

        response = self.client.get(self.detail_url())

        self.assertContains(response, "Ship project")

    def test_ship_guidance_uses_the_project_type(self) -> None:
        response = self.client.get(self.ship_url())

        self.assertContains(response, "Make sure your project works before shipping it.")

    def test_non_owner_cannot_submit_another_users_project(self) -> None:
        self.client.force_login(self.other_user)
        with (
            patch("twisted_site.views.client.project.ari.send_ship") as send_ship,
            patch("twisted_site.views.client.project.log_to_channel"),
        ):
            response = self.client.post(self.ship_url())

        self.assertRedirects(response, self.detail_url(), fetch_redirect_response=False)
        self.assertFalse(ProjectShip.objects.filter(project=self.project).exists())
        send_ship.assert_not_called()

    def test_ineligible_user_cannot_submit(self) -> None:
        self.profile.ysws_eligible = False
        self.profile.save(update_fields=("ysws_eligible",))
        with (
            patch("twisted_site.views.client.project.ari.send_ship") as send_ship,
            patch("twisted_site.views.client.project.log_to_channel"),
        ):
            response = self.client.post(self.ship_url())

        self.assertEqual(response.status_code, 200)
        self.assertFalse(ProjectShip.objects.filter(project=self.project).exists())
        send_ship.assert_not_called()

    def test_unconfigured_ari_does_not_create_a_ship(self) -> None:
        with (
            patch("twisted_site.views.client.project.ari.is_configured", return_value=False),
            patch("twisted_site.views.client.project.ari.send_ship") as send_ship,
        ):
            response = self.client.post(self.ship_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "temporarily unavailable")
        self.assertFalse(ProjectShip.objects.filter(project=self.project).exists())
        send_ship.assert_not_called()

    def test_shipped_project_detail_survives_unconfigured_ari(self) -> None:
        _ = ProjectShip.objects.create(project=self.project)

        with patch("twisted_site.views.client.project.ari.is_configured", return_value=False):
            response = self.client.get(self.detail_url())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["first_pass_status"], "unavailable")
        self.assertNotContains(response, "Open project settings")

    def test_shipped_project_cannot_be_submitted_twice(self) -> None:
        _ = ProjectShip.objects.create(project=self.project)
        with (
            patch("twisted_site.views.client.project.ari.send_ship") as send_ship,
            patch("twisted_site.views.client.project.log_to_channel"),
        ):
            response = self.client.post(self.ship_url())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ProjectShip.objects.filter(project=self.project).count(), 1)
        send_ship.assert_not_called()

    def test_submission_requires_playable_and_screenshot_urls(self) -> None:
        invalid_values = (
            ("", "https://example.com/screenshot.png"),
            ("https://example.com/play", ""),
            ("", ""),
        )
        for playable_url, screenshot_url in invalid_values:
            with self.subTest(playable_url=playable_url, screenshot_url=screenshot_url):
                _ = Project.objects.filter(pk=self.project.pk).update(
                    playable_url=playable_url,
                    screenshot_url=screenshot_url,
                )
                with patch("twisted_site.views.client.project.ari.send_ship") as send_ship:
                    response = self.client.post(self.ship_url())

                self.assertRedirects(
                    response,
                    self.detail_url(),
                    fetch_redirect_response=False,
                )
                self.assertFalse(ProjectShip.objects.filter(project=self.project).exists())
                send_ship.assert_not_called()
