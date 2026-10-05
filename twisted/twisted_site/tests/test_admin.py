from typing import cast, override
from unittest.mock import patch

from django.contrib.auth.models import User
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.test import Client, TestCase
from django.urls import reverse

from twisted_site.models import AuditLog, Journal, Profile, ProfileStaffPermissions, Project


class AdminAuthorizationTests(TestCase):
    user: User  # pyright: ignore[reportUninitializedInstanceVariable]
    profile: Profile  # pyright: ignore[reportUninitializedInstanceVariable]
    permissions: ProfileStaffPermissions  # pyright: ignore[reportUninitializedInstanceVariable]

    @override
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="staff")
        self.permissions = ProfileStaffPermissions.objects.create()
        self.profile = Profile.objects.create(
            user=self.user,
            is_staff=True,
            staff_permissions=self.permissions,
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_non_staff_user_cannot_enter_admin(self) -> None:
        user = User.objects.create_user(username="regular")
        _ = Profile.objects.create(user=user)
        self.client.force_login(user)

        response = self.client.get(reverse("admin.dash"))

        self.assertRedirects(response, reverse("dashboard"))

    def test_staff_permissions_are_created_on_first_admin_request(self) -> None:
        user = User.objects.create_user(username="new-staff")
        profile = Profile.objects.create(user=user, is_staff=True)
        self.client.force_login(user)

        response = self.client.get(reverse("admin.dash"))

        self.assertEqual(response.status_code, 200)
        profile.refresh_from_db()
        self.assertIsNotNone(profile.staff_permissions)

    def test_staff_without_granular_permissions_cannot_open_admin_pages(self) -> None:
        protected_pages = (
            "admin.users",
            "admin.pathways",
            "admin.announcements",
            "admin.logs",
            "admin.fulfillment",
            "admin.shop",
        )
        for page in protected_pages:
            with self.subTest(page=page):
                response = self.client.get(reverse(page))

                self.assertRedirects(response, reverse("admin.dash"))

    def test_view_users_permission_grants_user_administration_access(self) -> None:
        self.permissions.view_users = True
        self.permissions.save(update_fields=("view_users",))

        response = self.client.get(reverse("admin.users"))

        self.assertEqual(response.status_code, 200)

    def test_view_projects_permission_grants_project_detail_access(self) -> None:
        self.permissions.view_projects = True
        self.permissions.save(update_fields=("view_projects",))
        owner = User.objects.create_user(username="project-owner")
        _ = Profile.objects.create(user=owner)
        project = Project.objects.create(
            user=owner,
            project_name="Test project",
            project_description="A project",
            project_type="software",
        )

        response = self.client.get(
            reverse("admin.projects.detail", kwargs={"project_id": project.pk}),
        )

        self.assertEqual(response.status_code, 200)

    def test_project_detail_requires_view_projects_permission(self) -> None:
        owner = User.objects.create_user(username="project-owner-2")
        _ = Profile.objects.create(user=owner)
        project = Project.objects.create(
            user=owner,
            project_name="Test project",
            project_description="A project",
            project_type="software",
        )

        response = self.client.get(
            reverse("admin.projects.detail", kwargs={"project_id": project.pk}),
        )

        self.assertRedirects(response, reverse("admin.dash"))

    def test_view_audit_logs_permission_grants_audit_access(self) -> None:
        self.permissions.view_auditlogs = True
        self.permissions.save(update_fields=("view_auditlogs",))

        response = self.client.get(f"{reverse('admin.logs')}?page=1")

        self.assertEqual(response.status_code, 200)

    def test_dashboard_quick_actions_link_to_admin_pages(self) -> None:
        response = self.client.get(reverse("admin.dash"))

        self.assertEqual(response.status_code, 200)
        for page in (
            "admin.users",
            "admin.pathways",
            "admin.fulfillment",
            "admin.shop",
            "admin.announcements",
        ):
            self.assertContains(response, reverse(page))

    def test_audit_log_context_mode_filters_empty_entries(self) -> None:
        self.permissions.view_auditlogs = True
        self.permissions.save(update_fields=("view_auditlogs",))
        _ = AuditLog.objects.create(
            user=self.user,
            path="/fake/empty/",
            post=False,
            additional_context={},
        )
        _ = AuditLog.objects.create(
            user=self.user,
            path="/fake/context/",
            post=True,
            additional_context={"note": "distinctive-note-123"},
        )

        response = self.client.get(f"{reverse('admin.logs')}?page=1&context_mode=true")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "distinctive-note-123")
        self.assertNotContains(response, "/fake/empty/")

    def test_user_detail_shows_verification_status(self) -> None:
        self.permissions.view_users = True
        self.permissions.save(update_fields=("view_users",))
        target_user = User.objects.create_user(username="verified-target")
        target_profile = Profile.objects.create(user=target_user)
        target_profile.verification_status = "verified"
        target_profile.save(update_fields=("verification_status",))

        response = self.client.get(
            reverse("admin.users.detail", kwargs={"user_id": target_user.pk}),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "IDV:")
        self.assertContains(response, "verified")

    def test_admin_dashboard_tolerates_unknown_project_types(self) -> None:
        owner = User.objects.create_user(username="odd-type-owner")
        _ = Profile.objects.create(user=owner)
        project = Project.objects.create(
            user=owner,
            project_name="Odd project",
            project_description="x",
            project_type="experimental",
        )
        _ = Journal.objects.create(
            project=project,
            type="untracked",
            content="x",
            minutes_worked=30,
            reduced_minutes=30,
        )

        with patch("twisted_site.models.Profile.get_country", return_value="Unknown"):
            response = self.client.get(reverse("admin.dash"))

        self.assertEqual(response.status_code, 200)

    def test_non_superuser_cannot_change_user_permissions(self) -> None:
        target_user = User.objects.create_user(username="target")
        target_permissions = ProfileStaffPermissions.objects.create()
        target_profile = Profile.objects.create(
            user=target_user,
            staff_permissions=target_permissions,
        )
        detail_url = reverse(
            "admin.users.detail",
            kwargs={"user_id": target_user.pk},
        )

        response = self.client.post(
            detail_url,
            {"action": "change_permissions", "key": "view_users", "value": "True"},
        )

        self.assertRedirects(response, reverse("admin.dash"))
        target_profile.refresh_from_db()
        target_permissions.refresh_from_db()
        self.assertFalse(target_permissions.view_users)
        self.assertIsNotNone(target_profile.staff_permissions)

    def test_superuser_can_toggle_user_allowlist(self) -> None:
        self.permissions.superuser = True
        self.permissions.save(update_fields=("superuser",))
        target_user = User.objects.create_user(username="allow-target")
        target_profile = Profile.objects.create(user=target_user, is_allowed=False)
        detail_url = reverse(
            "admin.users.detail",
            kwargs={"user_id": target_user.pk},
        )

        response = self.client.post(detail_url, {"action": "toggle_is_allowed"})

        self.assertEqual(response.status_code, 302)
        target_profile.refresh_from_db()
        self.assertTrue(target_profile.is_allowed)

    def test_superuser_can_change_permission_and_make_admin(self) -> None:
        self.permissions.superuser = True
        self.permissions.save(update_fields=("superuser",))
        target_user = User.objects.create_user(username="permission-target")
        target_permissions = ProfileStaffPermissions.objects.create()
        target_profile = Profile.objects.create(
            user=target_user,
            staff_permissions=target_permissions,
        )
        detail_url = reverse(
            "admin.users.detail",
            kwargs={"user_id": target_user.pk},
        )

        _ = self.client.post(
            detail_url,
            {"action": "change_permissions", "key": "view_users", "value": "True"},
        )
        target_permissions.refresh_from_db()
        self.assertTrue(target_permissions.view_users)
        _ = self.client.post(detail_url, {"action": "make_admin"})

        target_profile.refresh_from_db()
        self.assertTrue(target_profile.is_staff)
        self.assertIsNotNone(target_profile.staff_permissions)

    def test_make_admin_preserves_existing_permissions(self) -> None:
        self.permissions.superuser = True
        self.permissions.save(update_fields=("superuser",))
        target_user = User.objects.create_user(username="keep-perms-target")
        target_permissions = ProfileStaffPermissions.objects.create(view_users=True)
        target_profile = Profile.objects.create(
            user=target_user,
            staff_permissions=target_permissions,
        )
        detail_url = reverse(
            "admin.users.detail",
            kwargs={"user_id": target_user.pk},
        )

        _ = self.client.post(detail_url, {"action": "make_admin"})

        target_profile.refresh_from_db()
        target_permissions.refresh_from_db()
        self.assertTrue(target_profile.is_staff)
        kept_permissions = cast(
            "ProfileStaffPermissions",
            target_profile.staff_permissions,
        )
        self.assertEqual(kept_permissions.pk, target_permissions.pk)
        self.assertTrue(target_permissions.view_users)

    def test_superuser_can_remove_admin(self) -> None:
        self.permissions.superuser = True
        self.permissions.save(update_fields=("superuser",))
        target_user = User.objects.create_user(username="demote-target")
        target_profile = Profile.objects.create(
            user=target_user,
            is_staff=True,
            staff_permissions=ProfileStaffPermissions.objects.create(),
        )
        detail_url = reverse(
            "admin.users.detail",
            kwargs={"user_id": target_user.pk},
        )

        response = self.client.post(detail_url, {"action": "remove_admin"})

        self.assertEqual(response.status_code, 302)
        target_profile.refresh_from_db()
        self.assertFalse(target_profile.is_staff)

    def test_non_superuser_cannot_remove_admin(self) -> None:
        target_user = User.objects.create_user(username="demote-denied-target")
        target_profile = Profile.objects.create(
            user=target_user,
            is_staff=True,
            staff_permissions=ProfileStaffPermissions.objects.create(),
        )
        detail_url = reverse(
            "admin.users.detail",
            kwargs={"user_id": target_user.pk},
        )

        response = self.client.post(detail_url, {"action": "remove_admin"})

        self.assertRedirects(response, reverse("admin.dash"))
        target_profile.refresh_from_db()
        self.assertTrue(target_profile.is_staff)

    def test_change_permissions_rejects_unknown_and_missing_keys(self) -> None:
        self.permissions.superuser = True
        self.permissions.save(update_fields=("superuser",))
        target_user = User.objects.create_user(username="mass-assignment-target")
        target_permissions = ProfileStaffPermissions.objects.create()
        target_profile = Profile.objects.create(
            user=target_user,
            staff_permissions=target_permissions,
        )
        detail_url = reverse(
            "admin.users.detail",
            kwargs={"user_id": target_user.pk},
        )

        for payload in (
            {"action": "change_permissions", "key": "id", "value": "True"},
            {"action": "change_permissions", "key": "is_staff", "value": "True"},
            {"action": "change_permissions"},
        ):
            with self.subTest(payload=payload):
                response = self.client.post(detail_url, payload)

                self.assertRedirects(
                    response,
                    f"{detail_url}#adminperms",
                    fetch_redirect_response=False,
                )
                target_profile.refresh_from_db()
                target_permissions.refresh_from_db()
                self.assertFalse(target_permissions.view_users)
                updated_permissions = cast(
                    "ProfileStaffPermissions",
                    target_profile.staff_permissions,
                )
                self.assertEqual(target_permissions.pk, updated_permissions.pk)

    def test_logout_all_requires_superuser_and_does_not_delete_sessions(self) -> None:
        session = SessionStore()
        _ = session.create()
        session_key = session.session_key

        response = self.client.post(
            reverse("admin.users"),
            {"action": "logoutall"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Session.objects.filter(session_key=session_key).exists())
        denial = AuditLog.objects.filter(path=reverse("admin.users")).get()
        context = cast("dict[str, object]", denial.additional_context)
        self.assertEqual(context["allowed"], False)

    def test_superuser_logout_all_deletes_sessions_and_records_audit(self) -> None:
        self.permissions.superuser = True
        self.permissions.save(update_fields=("superuser",))
        session = SessionStore()
        _ = session.create()
        deleted_session_count = Session.objects.count()

        response = self.client.post(
            reverse("admin.users"),
            {"action": "logoutall"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Session.objects.count(), 0)
        audit_log = AuditLog.objects.get()
        self.assertEqual(audit_log.path, reverse("admin.users"))
        self.assertTrue(audit_log.post)
        context = cast("dict[str, object]", audit_log.additional_context)
        self.assertEqual(context["action"], "logoutall")
        self.assertEqual(context["sessions_deleted"], deleted_session_count)
