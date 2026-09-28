from typing import TYPE_CHECKING, cast, override
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from twisted_site.models import Profile, Project, ShopRegion

if TYPE_CHECKING:
    from django.db.models import QuerySet


class ClientWorkflowTests(TestCase):
    user: User  # pyright: ignore[reportUninitializedInstanceVariable]
    profile: Profile  # pyright: ignore[reportUninitializedInstanceVariable]

    @override
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="client-workflow")
        self.profile = Profile.objects.create(
            user=self.user,
            slack_username="Workflow User",
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_project_creation_persists_and_notifies_slack(self) -> None:
        with patch("twisted_site.views.client.projects.log_to_channel") as log_to_channel:
            response = self.client.post(
                reverse("fr.projects.create"),
                {
                    "name": "Browser Project",
                    "description": "Created by a test",
                    "type": "software",
                },
            )

        project = Project.objects.get(user=self.user)
        self.assertRedirects(
            response,
            reverse("fr.projects.detail", kwargs={"project_id": project.pk}),
            fetch_redirect_response=False,
        )
        self.assertEqual(project.project_name, "Browser Project")
        self.assertEqual(project.project_type, "software")
        log_to_channel.assert_called_once()

    def test_project_creation_requires_all_fields(self) -> None:
        response = self.client.post(reverse("fr.projects.create"), {"name": "Incomplete"})

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Project.objects.exists())

    def test_project_creation_rejects_unknown_type(self) -> None:
        with patch("twisted_site.views.client.projects.log_to_channel"):
            response = self.client.post(
                reverse("fr.projects.create"),
                {
                    "name": "Invalid",
                    "description": "Invalid type",
                    "type": "other",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Project.objects.exists())

    def test_project_list_only_contains_owned_projects(self) -> None:
        owned = Project.objects.create(
            user=self.user,
            project_name="Owned",
            project_description="Description",
            project_type="software",
        )
        other_user = User.objects.create_user(username="other-owner")
        _ = Profile.objects.create(user=other_user)
        _ = Project.objects.create(
            user=other_user,
            project_name="Other",
            project_description="Description",
            project_type="software",
        )

        response = self.client.get(reverse("fr.projects"))

        projects = cast("QuerySet[Project]", response.context["projects"])
        self.assertEqual(list(projects), [owned])

    def test_referral_code_is_generated_once_and_preserved(self) -> None:
        with patch("twisted_site.views.client.referrals.secrets.choice", return_value="a"):
            first_response = self.client.get(reverse("fr.referrals"))
            second_response = self.client.get(reverse("fr.referrals"))

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.my_referral_code, "a" * 12)

    def test_shop_region_can_be_selected(self) -> None:
        region = ShopRegion.objects.create(name="North America")
        url = reverse("fr.shop")

        response = self.client.post(url, {"action": "setRegion", "region": region.pk})

        self.assertRedirects(response, url)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.region, region)

    def test_unknown_shop_region_returns_not_found(self) -> None:
        url = reverse("fr.shop")

        response = self.client.post(url, {"action": "setRegion", "region": 999})

        self.assertEqual(response.status_code, 404)
        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.region)
