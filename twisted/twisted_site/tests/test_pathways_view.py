from datetime import timedelta
from typing import cast, override

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from twisted_site.models import Journal, Pathway, PathwayTimeSpent, Profile, Project


class PathwaysViewTests(TestCase):
    user: User  # pyright: ignore[reportUninitializedInstanceVariable]
    profile: Profile  # pyright: ignore[reportUninitializedInstanceVariable]

    @override
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="pathway-viewer")
        self.profile = Profile.objects.create(user=self.user)
        self.client = Client()
        self.client.force_login(self.user)

    def test_anonymous_user_is_redirected_home(self) -> None:
        self.client.logout()

        response = self.client.get(reverse("fr.pathways"))

        self.assertRedirects(response, reverse("homepage"))

    def test_exact_threshold_is_reported_as_unlocked(self) -> None:
        now = timezone.now()
        pathway = Pathway.objects.create(
            name="Current",
            min_mins=60,
            start=now - timedelta(hours=1),
            end=now + timedelta(hours=1),
        )
        _ = PathwayTimeSpent.objects.create(
            pathway=pathway,
            user=self.user,
            unlocked=True,
            minutes=pathway.min_mins,
        )

        response = self.client.get(reverse("fr.pathways"))

        self.assertEqual(response.status_code, 200)
        current_pathways = cast(
            "list[dict[str, object]]",
            response.context["current_pathways"],
        )
        self.assertTrue(current_pathways[0]["unlocked"])

    def test_pathways_are_grouped_by_lifecycle_state(self) -> None:
        now = timezone.now()
        _ = Pathway.objects.create(
            name="Past",
            min_mins=10,
            start=now - timedelta(days=2),
            end=now - timedelta(days=1),
        )
        _ = Pathway.objects.create(
            name="Current",
            min_mins=10,
            start=now - timedelta(hours=1),
            end=now + timedelta(hours=1),
        )
        _ = Pathway.objects.create(
            name="Future",
            min_mins=10,
            start=now + timedelta(days=1),
            end=now + timedelta(days=2),
        )

        response = self.client.get(reverse("fr.pathways"))

        self.assertEqual(len(response.context["past_pathways"]), 1)
        self.assertEqual(len(response.context["current_pathways"]), 1)
        self.assertEqual(len(response.context["future_pathways"]), 1)


class UnlockPathwayTests(TestCase):
    user: User  # pyright: ignore[reportUninitializedInstanceVariable]
    profile: Profile  # pyright: ignore[reportUninitializedInstanceVariable]
    project: Project  # pyright: ignore[reportUninitializedInstanceVariable]
    journal: Journal  # pyright: ignore[reportUninitializedInstanceVariable]
    pathway: Pathway  # pyright: ignore[reportUninitializedInstanceVariable]

    @override
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="pathway-unlocker")
        self.profile = Profile.objects.create(user=self.user)
        self.project = Project.objects.create(
            user=self.user,
            project_name="Unlock project",
            project_description="Description",
            project_type="software",
        )
        self.journal = Journal.objects.create(
            project=self.project,
            type="untracked",
            content="Work",
            minutes_worked=100,
            reduced_minutes=100,
        )
        now = timezone.now()
        self.pathway = Pathway.objects.create(
            name="Unlockable",
            min_mins=60,
            start=now - timedelta(hours=1),
            end=now + timedelta(hours=1),
        )
        self.client = Client()
        self.client.force_login(self.user)

    def unlock_url(self) -> str:
        return reverse(
            "fr.pathways.unlock",
            kwargs={"pathway_id": self.pathway.pk},
        )

    def test_sufficient_time_unlocks_pathway(self) -> None:
        response = self.client.post(self.unlock_url())

        self.assertRedirects(response, reverse("fr.pathways"))
        time_spent = PathwayTimeSpent.objects.get(pathway=self.pathway, user=self.user)
        self.assertTrue(time_spent.unlocked)
        self.assertEqual(time_spent.minutes, self.pathway.min_mins)

    def test_insufficient_time_does_not_create_spending_record(self) -> None:
        self.journal.minutes_worked = 30
        self.journal.reduced_minutes = 30
        self.journal.save()

        response = self.client.post(self.unlock_url())

        self.assertRedirects(response, reverse("fr.pathways"))
        self.assertFalse(
            PathwayTimeSpent.objects.filter(pathway=self.pathway, user=self.user).exists(),
        )

    def test_already_unlocked_pathway_is_not_modified(self) -> None:
        existing = PathwayTimeSpent.objects.create(
            pathway=self.pathway,
            user=self.user,
            unlocked=True,
            minutes=60,
        )

        response = self.client.post(self.unlock_url())

        self.assertRedirects(response, reverse("fr.pathways"))
        existing.refresh_from_db()
        self.assertEqual(existing.minutes, 60)

    def test_inactive_pathway_cannot_be_unlocked(self) -> None:
        now = timezone.now()
        future_pathway = Pathway.objects.create(
            name="Future",
            min_mins=60,
            start=now + timedelta(hours=1),
            end=now + timedelta(hours=2),
        )

        response = self.client.post(
            reverse("fr.pathways.unlock", kwargs={"pathway_id": future_pathway.pk}),
        )

        self.assertRedirects(response, reverse("fr.pathways"))
        self.assertFalse(
            PathwayTimeSpent.objects.filter(pathway=future_pathway, user=self.user).exists(),
        )

    def test_anonymous_user_cannot_unlock_pathway(self) -> None:
        self.client.logout()

        response = self.client.post(self.unlock_url())

        self.assertRedirects(response, reverse("homepage"))
        self.assertFalse(
            PathwayTimeSpent.objects.filter(pathway=self.pathway, user=self.user).exists(),
        )
