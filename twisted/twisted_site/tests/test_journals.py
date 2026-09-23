from datetime import UTC, datetime
from typing import cast, override
from unittest.mock import patch

from django.contrib.auth.models import User
from django.http import HttpResponse
from django.test import Client, TestCase
from django.urls import reverse

from twisted_site.hackatime import HackatimeProject
from twisted_site.models import Journal, Profile, Project, ProjectShip


class JournalContentMixin:
    def content(self, *, words: int, images: int) -> str:
        prose = " ".join(["word"] * words)
        evidence = " ".join(
            f"![Evidence {index}](https://example.com/{index}.png)" for index in range(images)
        )
        return f"{prose}\n{evidence}"


class HackatimeJournalWorkflowTests(JournalContentMixin, TestCase):
    user: User  # pyright: ignore[reportUninitializedInstanceVariable]
    profile: Profile  # pyright: ignore[reportUninitializedInstanceVariable]
    project: Project  # pyright: ignore[reportUninitializedInstanceVariable]
    other_user: User  # pyright: ignore[reportUninitializedInstanceVariable]
    other_profile: Profile  # pyright: ignore[reportUninitializedInstanceVariable]
    hackatime_projects: list[HackatimeProject]  # pyright: ignore[reportUninitializedInstanceVariable]

    @override
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="journal-owner")
        self.profile = Profile.objects.create(user=self.user)
        self.project = Project.objects.create(
            user=self.user,
            project_name="Hackatime Journal",
            project_description="Description",
            project_type="software",
        )
        self.other_user = User.objects.create_user(username="other-user")
        self.other_profile = Profile.objects.create(user=self.other_user)
        self.hackatime_projects = [
            HackatimeProject(
                name="Hackatime Journal",
                total_seconds=181 * 60,
                most_recent_heartbeat=datetime(2026, 1, 1, tzinfo=UTC),
                languages=[],
            ),
        ]
        self.client = Client()
        self.client.force_login(self.user)

    def post_journal(self, content: str) -> HttpResponse:
        with (
            patch.object(
                Project,
                "get_hackatime_projects",
                return_value=self.hackatime_projects,
            ),
            patch("twisted_site.views.client.journal.log_to_channel"),
        ):
            return cast(
                "HttpResponse",
                cast(
                    "object",
                    self.client.post(
                        reverse(
                            "fr.projects.journals.new.hackatime",
                            kwargs={"project_id": self.project.pk},
                        ),
                        {"content": content},
                    ),
                ),
            )

    def test_valid_hackatime_journal_is_saved(self) -> None:
        response = self.post_journal(self.content(words=60, images=2))

        self.assertEqual(response.status_code, 200)
        journal = Journal.objects.get(project=self.project)
        self.assertEqual(journal.type, "hackatime")
        self.assertEqual(journal.minutes_worked, 181)
        self.assertEqual(journal.reduced_minutes, 181)

    def test_hackatime_journal_requires_enough_images(self) -> None:
        response = self.post_journal(self.content(words=60, images=1))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Journal.objects.exists())

    def test_hackatime_journal_requires_enough_prose(self) -> None:
        response = self.post_journal(self.content(words=5, images=2))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Journal.objects.exists())

    def test_non_owner_cannot_create_hackatime_journal(self) -> None:
        self.client.force_login(self.other_user)

        response = self.post_journal(self.content(words=60, images=2))

        self.assertRedirects(response, reverse("dashboard"))
        self.assertFalse(Journal.objects.exists())

    def test_shipped_project_cannot_create_hackatime_journal(self) -> None:
        _ = ProjectShip.objects.create(project=self.project)

        response = self.post_journal(self.content(words=60, images=2))

        self.assertRedirects(
            response,
            reverse("fr.projects.detail", kwargs={"project_id": self.project.pk}),
        )
        self.assertFalse(Journal.objects.exists())


class UntrackedJournalWorkflowTests(JournalContentMixin, TestCase):
    user: User  # pyright: ignore[reportUninitializedInstanceVariable]
    profile: Profile  # pyright: ignore[reportUninitializedInstanceVariable]
    project: Project  # pyright: ignore[reportUninitializedInstanceVariable]

    @override
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="hardware-owner")
        self.profile = Profile.objects.create(user=self.user)
        self.project = Project.objects.create(
            user=self.user,
            project_name="Hardware Journal",
            project_description="Description",
            project_type="hardware",
        )
        self.client = Client()
        self.client.force_login(self.user)

    def post_journal(self, time_logged: int, content: str) -> HttpResponse:
        with patch.object(Project, "get_hackatime_projects", return_value=[]):
            return cast(
                "HttpResponse",
                cast(
                    "object",
                    self.client.post(
                        reverse(
                            "fr.projects.journals.new.untracked",
                            kwargs={"project_id": self.project.pk},
                        ),
                        {
                            "content": content,
                            "time_logged": str(time_logged),
                        },
                    ),
                ),
            )

    def test_valid_untracked_journal_is_saved(self) -> None:
        response = self.post_journal(30, self.content(words=60, images=0))

        self.assertEqual(response.status_code, 200)
        journal = Journal.objects.get(project=self.project)
        self.assertEqual(journal.type, "untracked")
        self.assertEqual(journal.minutes_worked, 30)
        self.assertEqual(journal.reduced_minutes, 30)

    def test_untracked_journal_cannot_exceed_sixty_minutes(self) -> None:
        response = self.post_journal(61, self.content(words=100, images=0))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Journal.objects.exists())

    def test_untracked_journal_cannot_be_negative(self) -> None:
        response = self.post_journal(-1, self.content(words=100, images=0))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Journal.objects.exists())

    def test_software_project_is_redirected_to_hackatime_journal(self) -> None:
        _ = Project.objects.filter(pk=self.project.pk).update(project_type="software")

        response = self.post_journal(30, self.content(words=60, images=0))

        self.assertRedirects(
            response,
            reverse(
                "fr.projects.journals.new.hackatime",
                kwargs={"project_id": self.project.pk},
            ),
        )
        self.assertFalse(Journal.objects.exists())


class JournalMutationTests(JournalContentMixin, TestCase):
    user: User  # pyright: ignore[reportUninitializedInstanceVariable]
    profile: Profile  # pyright: ignore[reportUninitializedInstanceVariable]
    other_user: User  # pyright: ignore[reportUninitializedInstanceVariable]
    other_profile: Profile  # pyright: ignore[reportUninitializedInstanceVariable]
    project: Project  # pyright: ignore[reportUninitializedInstanceVariable]
    journal: Journal  # pyright: ignore[reportUninitializedInstanceVariable]

    @override
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="mutation-owner")
        self.profile = Profile.objects.create(user=self.user)
        self.other_user = User.objects.create_user(username="mutation-other")
        self.other_profile = Profile.objects.create(user=self.other_user)
        self.project = Project.objects.create(
            user=self.user,
            project_name="Mutable Journal",
            project_description="Description",
            project_type="software",
        )
        self.journal = Journal.objects.create(
            project=self.project,
            type="untracked",
            content="Original content",
            minutes_worked=30,
            reduced_minutes=30,
        )
        self.client = Client()
        self.client.force_login(self.user)

    def delete_url(self) -> str:
        return reverse(
            "fr.projects.journals.delete",
            kwargs={"journal_id": self.journal.pk},
        )

    def edit_url(self) -> str:
        return reverse(
            "fr.projects.journals.edit",
            kwargs={"id": self.journal.pk},
        )

    def test_owner_can_delete_untracked_journal(self) -> None:
        response = self.client.post(self.delete_url())

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Journal.objects.filter(pk=self.journal.pk).exists())

    def test_non_owner_cannot_delete_journal(self) -> None:
        self.client.force_login(self.other_user)

        response = self.client.post(self.delete_url())

        self.assertRedirects(response, reverse("dashboard"))
        self.assertTrue(Journal.objects.filter(pk=self.journal.pk).exists())

    def test_shipped_project_journal_cannot_be_deleted(self) -> None:
        _ = ProjectShip.objects.create(project=self.project)

        response = self.client.post(self.delete_url())

        self.assertRedirects(
            response,
            reverse("fr.projects.detail", kwargs={"project_id": self.project.pk}),
        )
        self.assertTrue(Journal.objects.filter(pk=self.journal.pk).exists())

    def test_edit_still_requires_evidence_and_prose(self) -> None:
        with patch("twisted_site.views.client.journal.log_to_channel"):
            response = self.client.post(
                self.edit_url(),
                {"content": "Too short without evidence"},
            )

        self.assertEqual(response.status_code, 200)
        self.journal.refresh_from_db()
        self.assertEqual(self.journal.content, "Original content")

    def test_owner_can_edit_untracked_journal(self) -> None:
        new_content = self.content(words=20, images=1)
        with patch("twisted_site.views.client.journal.log_to_channel") as log_to_channel:
            response = self.client.post(self.edit_url(), {"content": new_content})

        self.assertEqual(response.status_code, 200)
        self.journal.refresh_from_db()
        self.assertEqual(self.journal.content, new_content)
        log_to_channel.assert_called_once()
