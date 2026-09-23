from datetime import UTC, datetime, timedelta
from typing import override
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase

from twisted_site.hackatime import HackatimeProject
from twisted_site.models import (
    Journal,
    Pathway,
    PathwayTimeSpent,
    Profile,
    Project,
    ProjectShip,
)

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


class ProjectTimeAccountingTests(TestCase):
    user: User  # pyright: ignore[reportUninitializedInstanceVariable]
    profile: Profile  # pyright: ignore[reportUninitializedInstanceVariable]
    project: Project  # pyright: ignore[reportUninitializedInstanceVariable]

    @override
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="maker")
        self.profile = Profile.objects.create(user=self.user)
        self.project = Project.objects.create(
            user=self.user,
            project_name="Test Project",
            project_description="Description",
            project_type="hardware",
        )

    def test_sums_reduced_or_full_minutes_by_requested_mode(self) -> None:
        _ = Journal.objects.create(
            project=self.project,
            type="hackatime",
            content="Hackatime work",
            minutes_worked=60,
            reduced_minutes=30,
        )
        _ = Journal.objects.create(
            project=self.project,
            type="untracked",
            content="Untracked work",
            minutes_worked=20,
            reduced_minutes=10,
        )
        _ = Journal.objects.create(
            project=self.project,
            type="lookout",
            content="Lookout work",
            minutes_worked=5,
            reduced_minutes=5,
        )

        self.assertEqual(self.project.time_logged(), 45)
        self.assertEqual(self.project.time_logged(include_all_minutes=True), 85)
        self.assertEqual(self.profile.time_logged(), 45)

    def test_hackatime_totals_only_include_hackatime_journals(self) -> None:
        _ = Journal.objects.create(
            project=self.project,
            type="hackatime",
            content="Hackatime work",
            minutes_worked=60,
            reduced_minutes=30,
        )
        _ = Journal.objects.create(
            project=self.project,
            type="untracked",
            content="Untracked work",
            minutes_worked=20,
            reduced_minutes=10,
        )

        self.assertEqual(self.project.hackatime_logged(), 30)
        self.assertEqual(self.project.hackatime_logged(include_all_minutes=True), 60)

    def test_hackatime_time_unjournaled_uses_full_journal_minutes(self) -> None:
        _ = Journal.objects.create(
            project=self.project,
            type="hackatime",
            content="Hackatime work",
            minutes_worked=2,
            reduced_minutes=1,
        )
        hackatime_projects = [
            HackatimeProject(
                name="Test Project",
                total_seconds=149,
                most_recent_heartbeat=_NOW,
                languages=[],
            ),
        ]

        with patch.object(
            self.project,
            "get_hackatime_projects",
            return_value=hackatime_projects,
        ):
            self.assertEqual(self.project.time_spent(), 2)
            self.assertEqual(self.project.hackatime_time_unjournaled(), 0)

    def test_latest_ship_controls_shipped_and_approved_state(self) -> None:
        cases = (
            ("pending", True, False),
            ("requested_changes", False, False),
            ("rejected", True, False),
            ("approved", True, True),
        )
        for status, is_shipped, is_approved in cases:
            with self.subTest(status=status):
                ship = ProjectShip.objects.create(project=self.project, status=status)

                self.assertEqual(self.project.latest_ship(), ship)
                self.assertEqual(self.project.is_shipped(), is_shipped)
                self.assertEqual(self.project.is_approved(), is_approved)

                _ = ship.delete()


class PathwayAccountingTests(TestCase):
    user: User  # pyright: ignore[reportUninitializedInstanceVariable]
    profile: Profile  # pyright: ignore[reportUninitializedInstanceVariable]
    project: Project  # pyright: ignore[reportUninitializedInstanceVariable]
    pathway: Pathway  # pyright: ignore[reportUninitializedInstanceVariable]

    @override
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="pathway-maker")
        self.profile = Profile.objects.create(user=self.user)
        self.project = Project.objects.create(
            user=self.user,
            project_name="Pathway Project",
            project_description="Description",
            project_type="software",
        )
        _ = Journal.objects.create(
            project=self.project,
            type="untracked",
            content="Work",
            minutes_worked=100,
            reduced_minutes=100,
        )
        self.pathway = Pathway.objects.create(
            name="Test Pathway",
            min_mins=60,
            start=_NOW - timedelta(hours=1),
            end=_NOW + timedelta(hours=1),
        )

    def test_unspent_minutes_subtracts_all_pathway_spending(self) -> None:
        first = PathwayTimeSpent.objects.create(
            pathway=self.pathway,
            user=self.user,
            minutes=25,
        )
        second_pathway = Pathway.objects.create(
            name="Second Pathway",
            min_mins=20,
            start=_NOW - timedelta(hours=1),
            end=_NOW + timedelta(hours=1),
        )
        _ = PathwayTimeSpent.objects.create(
            pathway=second_pathway,
            user=self.user,
            minutes=15,
        )

        self.assertEqual(self.pathway.mins_spent(self.user), 25)
        self.assertEqual(self.pathway.get_unspent_mins(self.user), 60)
        self.assertFalse(first.unlocked)

    def test_exact_threshold_qualifies_participant(self) -> None:
        _ = PathwayTimeSpent.objects.create(
            pathway=self.pathway,
            user=self.user,
            unlocked=True,
            minutes=self.pathway.min_mins,
        )

        self.assertEqual(self.pathway.qualified_participants(), [self.user])

    def test_pathway_lifecycle_uses_fixed_clock_boundaries(self) -> None:
        starting_now = Pathway.objects.create(
            name="Starting now",
            min_mins=10,
            start=_NOW,
            end=_NOW + timedelta(hours=1),
        )
        future = Pathway.objects.create(
            name="Future",
            min_mins=10,
            start=_NOW + timedelta(hours=1),
            end=_NOW + timedelta(hours=2),
        )
        ending_now = Pathway.objects.create(
            name="Ending now",
            min_mins=10,
            start=_NOW - timedelta(hours=1),
            end=_NOW,
        )
        ended = Pathway.objects.create(
            name="Ended",
            min_mins=10,
            start=_NOW - timedelta(hours=1),
            end=_NOW - timedelta(microseconds=1),
        )

        with patch("twisted_site.models.timezone.now", return_value=_NOW):
            self.assertTrue(self.pathway.in_progress())
            self.assertTrue(starting_now.in_progress())
            self.assertTrue(future.didnt_start())
            self.assertFalse(future.in_progress())
            self.assertFalse(ending_now.ended())
            self.assertTrue(ending_now.in_progress())
            self.assertTrue(ended.ended())
            self.assertFalse(ended.in_progress())
