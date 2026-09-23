from datetime import timedelta
from typing import cast, override

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from twisted_site.models import Pathway, PathwayTimeSpent, Profile


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
