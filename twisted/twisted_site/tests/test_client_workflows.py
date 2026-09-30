from typing import TYPE_CHECKING, cast, override
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from twisted_site.models import Journal, Profile, Project, ProjectShip, ShopRegion

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

    def test_project_creation_escapes_slack_markup(self) -> None:
        with patch("twisted_site.views.client.projects.log_to_channel") as log_to_channel:
            response = self.client.post(
                reverse("fr.projects.create"),
                {
                    "name": "<!here> <https://evil.example|free twists>",
                    "description": "Fish & chips <yum>",
                    "type": "software",
                },
            )

        self.assertEqual(response.status_code, 302)
        message = cast("str", log_to_channel.call_args.args[0])
        self.assertIn("&lt;!here&gt;", message)
        self.assertIn("&lt;https://evil.example|free twists&gt;", message)
        self.assertIn("Fish &amp; chips &lt;yum&gt;", message)
        self.assertNotIn("<!here>", message)

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

    def test_missing_shop_region_is_rejected(self) -> None:
        response = self.client.post(reverse("fr.shop"), {"action": "setRegion"})

        self.assertEqual(response.status_code, 400)
        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.region)

    def test_shop_ignores_unknown_pathway_parameter(self) -> None:
        response = self.client.get(reverse("fr.shop"), {"pathway": 999})

        self.assertEqual(response.status_code, 200)

    def test_dashboard_ignores_non_numeric_project_parameter(self) -> None:
        response = self.client.get(reverse("dashboard"), {"project": "abc"})

        self.assertEqual(response.status_code, 200)

    def test_dashboard_links_the_discover_window(self) -> None:
        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("fr.discover"))

    def test_homepage_links_the_faqs_page(self) -> None:
        self.client.logout()

        response = self.client.get(reverse("homepage"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("faqs"))

    def test_project_detail_shows_journals_but_hides_review_feedback_from_others(self) -> None:
        other_user = User.objects.create_user(username="detail-other")
        _ = Profile.objects.create(user=other_user, slack_username="Other User")
        project = Project.objects.create(
            user=self.user,
            project_name="Public devlog project",
            project_description="Public description",
            project_type="software",
        )
        _ = Journal.objects.create(
            project=project,
            type="hackatime",
            content="shared devlog content",
            minutes_worked=120,
            reduced_minutes=120,
        )
        ship = ProjectShip.objects.create(project=project, status="rejected")
        ship.note_to_maker = "private reviewer note"
        ship.final_status = "approved"
        ship.final_note_to_maker = "private final note"
        ship.save()

        detail_url = reverse("fr.projects.detail", kwargs={"project_id": project.pk})

        with patch(
            "twisted_site.views.client.project.ari.get_project_status",
            return_value={"phase": "reviewed", "decision": "approved"},
        ) as get_status:
            owner_response = self.client.get(detail_url)
            self.client.force_login(other_user)
            other_response = self.client.get(detail_url)

        # The ARI status lookup only happens for the owner.
        get_status.assert_called_once()

        self.assertContains(owner_response, "shared devlog content")
        self.assertContains(owner_response, "private reviewer note")
        self.assertContains(owner_response, "private final note")
        self.assertContains(owner_response, "permanently rejected")

        self.assertEqual(other_response.status_code, 200)
        self.assertContains(other_response, "shared devlog content")
        self.assertContains(other_response, "Public description")
        self.assertNotContains(other_response, "private reviewer note")
        self.assertNotContains(other_response, "private final note")
        self.assertNotContains(other_response, "permanently rejected")
        self.assertNotContains(other_response, "Project shipped")
        self.assertNotContains(other_response, "+ New journal")

    def test_approved_project_shows_shipped_badge_to_other_users(self) -> None:
        other_user = User.objects.create_user(username="badge-other")
        _ = Profile.objects.create(user=other_user)
        project = Project.objects.create(
            user=self.user,
            project_name="Approved project",
            project_description="Description",
            project_type="software",
        )
        _ = ProjectShip.objects.create(project=project, status="approved")
        detail_url = reverse("fr.projects.detail", kwargs={"project_id": project.pk})

        self.client.force_login(other_user)
        with patch(
            "twisted_site.views.client.project.ari.get_project_status",
        ) as get_status:
            response = self.client.get(detail_url)

        self.assertContains(response, "shipped")
        get_status.assert_not_called()

    def test_new_journal_button_is_only_shown_to_the_owner(self) -> None:
        other_user = User.objects.create_user(username="button-other")
        _ = Profile.objects.create(user=other_user)
        project = Project.objects.create(
            user=self.user,
            project_name="Button project",
            project_description="Description",
            project_type="software",
        )
        detail_url = reverse("fr.projects.detail", kwargs={"project_id": project.pk})

        owner_response = self.client.get(detail_url)
        self.client.force_login(other_user)
        other_response = self.client.get(detail_url)

        self.assertContains(owner_response, "+ New journal")
        self.assertNotContains(other_response, "+ New journal")
