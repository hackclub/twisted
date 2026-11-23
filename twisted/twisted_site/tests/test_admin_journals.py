from typing import override

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from twisted_site.models import (
    AuditLog,
    Journal,
    Profile,
    ProfileStaffPermissions,
    Project,
    ProjectShip,
)


class AdminJournalTests(TestCase):
    permissions: ProfileStaffPermissions  # pyright: ignore[reportUninitializedInstanceVariable]
    project: Project  # pyright: ignore[reportUninitializedInstanceVariable]
    journal: Journal  # pyright: ignore[reportUninitializedInstanceVariable]

    @override
    def setUp(self) -> None:
        staff = User.objects.create_user(username="journal-staff")
        self.permissions = ProfileStaffPermissions.objects.create(
            view_projects=True,
            manage_journals=True,
        )
        _ = Profile.objects.create(user=staff, is_staff=True, staff_permissions=self.permissions)
        owner = User.objects.create_user(username="journal-owner")
        _ = Profile.objects.create(user=owner, slack_username="owner")
        self.project = Project.objects.create(
            user=owner,
            project_name="Robot",
            project_description="A robot",
            project_type="hardware",
        )
        self.journal = Journal.objects.create(
            project=self.project,
            type="untracked",
            content="Soldered the board",
            minutes_worked=90,
            reduced_minutes=60,
        )
        self.client = Client()
        self.client.force_login(staff)

    def project_url(self) -> str:
        return reverse("admin.projects.detail", kwargs={"project_id": self.project.pk})

    def test_project_page_links_to_journal_actions(self) -> None:
        response = self.client.get(self.project_url())

        self.assertContains(response, reverse("admin.journals.create", kwargs={"project_id": self.project.pk}))
        self.assertContains(response, reverse("admin.journals.edit", kwargs={"journal_id": self.journal.pk}))
        self.assertContains(response, reverse("admin.journals.delete", kwargs={"journal_id": self.journal.pk}))

    def test_project_page_hides_journal_actions_without_permission(self) -> None:
        self.permissions.manage_journals = False
        self.permissions.save(update_fields=("manage_journals",))

        response = self.client.get(self.project_url())

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, reverse("admin.journals.edit", kwargs={"journal_id": self.journal.pk}))

    def test_staff_can_create_journal_for_any_project(self) -> None:
        create_url = reverse("admin.journals.create", kwargs={"project_id": self.project.pk})
        self.assertEqual(self.client.get(create_url).status_code, 200)

        response = self.client.post(
            create_url,
            {"type": "hackatime", "content": "Backfilled", "minutes_worked": "120", "reduced_minutes": ""},
        )

        self.assertRedirects(response, self.project_url())
        journal = Journal.objects.exclude(pk=self.journal.pk).get(project=self.project)
        self.assertEqual(journal.type, "hackatime")
        self.assertEqual(journal.minutes_worked, 120)
        self.assertEqual(journal.reduced_minutes, 120)
        audit = AuditLog.objects.filter(path=create_url, post=True).get()
        self.assertEqual(audit.additional_context["action"], "create_journal")  # pyright: ignore[reportIndexIssue, reportOptionalSubscript]

    def test_staff_can_create_journal_on_shipped_project(self) -> None:
        _ = ProjectShip.objects.create(project=self.project, status="pending")

        response = self.client.post(
            reverse("admin.journals.create", kwargs={"project_id": self.project.pk}),
            {"type": "untracked", "content": "Late entry", "minutes_worked": "30"},
        )

        self.assertRedirects(response, self.project_url())
        self.assertEqual(self.project.journals.count(), 2)  # pyright: ignore[reportAttributeAccessIssue]

    def test_journal_form_rejects_invalid_values(self) -> None:
        create_url = reverse("admin.journals.create", kwargs={"project_id": self.project.pk})
        cases = {
            "bad type": {"type": "made-up", "content": "x", "minutes_worked": "10"},
            "empty content": {"type": "untracked", "content": "  ", "minutes_worked": "10"},
            "non-numeric": {"type": "untracked", "content": "x", "minutes_worked": "ten"},
            "negative": {"type": "untracked", "content": "x", "minutes_worked": "-5"},
            "approved over worked": {
                "type": "untracked",
                "content": "x",
                "minutes_worked": "10",
                "reduced_minutes": "20",
            },
        }
        for name, data in cases.items():
            with self.subTest(name):
                response = self.client.post(create_url, data)

                self.assertEqual(response.status_code, 200)
                self.assertEqual(Journal.objects.count(), 1)

    def test_staff_can_edit_journal(self) -> None:
        edit_url = reverse("admin.journals.edit", kwargs={"journal_id": self.journal.pk})
        response = self.client.get(edit_url)
        self.assertContains(response, "Soldered the board")

        response = self.client.post(
            edit_url,
            {"type": "untracked", "content": "Soldered two boards", "minutes_worked": "100", "reduced_minutes": "45"},
        )

        self.assertRedirects(response, self.project_url())
        self.journal.refresh_from_db()
        self.assertEqual(self.journal.content, "Soldered two boards")
        self.assertEqual(self.journal.minutes_worked, 100)
        self.assertEqual(self.journal.reduced_minutes, 45)
        audit = AuditLog.objects.filter(path=edit_url, post=True).get()
        context = audit.additional_context
        self.assertEqual(context["before"]["reduced_minutes"], 60)  # pyright: ignore[reportIndexIssue, reportOptionalSubscript]
        self.assertEqual(context["after"]["reduced_minutes"], 45)  # pyright: ignore[reportIndexIssue, reportOptionalSubscript]
        self.assertTrue(context["content_changed"])  # pyright: ignore[reportIndexIssue, reportOptionalSubscript]

    def test_invalid_edit_keeps_journal_unchanged(self) -> None:
        response = self.client.post(
            reverse("admin.journals.edit", kwargs={"journal_id": self.journal.pk}),
            {"type": "untracked", "content": "Changed", "minutes_worked": "oops"},
        )

        self.assertContains(response, "Changed")
        self.journal.refresh_from_db()
        self.assertEqual(self.journal.content, "Soldered the board")

    def test_staff_can_delete_journal(self) -> None:
        delete_url = reverse("admin.journals.delete", kwargs={"journal_id": self.journal.pk})

        response = self.client.post(delete_url)

        self.assertRedirects(response, self.project_url())
        self.assertFalse(Journal.objects.filter(pk=self.journal.pk).exists())

    def test_journal_delete_is_post_only(self) -> None:
        response = self.client.get(
            reverse("admin.journals.delete", kwargs={"journal_id": self.journal.pk}),
        )

        # AdminView turns the 405 into a redirect, because no handler allowed the request.
        self.assertRedirects(response, reverse("admin.dash"))
        self.assertTrue(Journal.objects.filter(pk=self.journal.pk).exists())

    def test_journal_management_requires_manage_journals(self) -> None:
        self.permissions.manage_journals = False
        self.permissions.save(update_fields=("manage_journals",))
        requests = (
            ("get", reverse("admin.journals.create", kwargs={"project_id": self.project.pk}), {}),
            (
                "post",
                reverse("admin.journals.create", kwargs={"project_id": self.project.pk}),
                {"type": "untracked", "content": "x", "minutes_worked": "5"},
            ),
            ("get", reverse("admin.journals.edit", kwargs={"journal_id": self.journal.pk}), {}),
            (
                "post",
                reverse("admin.journals.edit", kwargs={"journal_id": self.journal.pk}),
                {"type": "untracked", "content": "x", "minutes_worked": "5"},
            ),
            ("post", reverse("admin.journals.delete", kwargs={"journal_id": self.journal.pk}), {}),
        )
        for method, url, data in requests:
            with self.subTest(method=method, url=url):
                response = getattr(self.client, method)(url, data)

                self.assertRedirects(response, reverse("admin.dash"))
        self.journal.refresh_from_db()
        self.assertEqual(self.journal.content, "Soldered the board")
        self.assertEqual(Journal.objects.count(), 1)

    def test_journal_management_also_requires_view_projects(self) -> None:
        self.permissions.view_projects = False
        self.permissions.save(update_fields=("view_projects",))

        response = self.client.post(
            reverse("admin.journals.delete", kwargs={"journal_id": self.journal.pk}),
        )

        self.assertRedirects(response, reverse("admin.dash"))
        self.assertTrue(Journal.objects.filter(pk=self.journal.pk).exists())
