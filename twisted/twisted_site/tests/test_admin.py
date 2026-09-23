from typing import cast, override

from django.contrib.auth.models import User
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.test import Client, TestCase
from django.urls import reverse

from twisted_site.models import AuditLog, Profile, ProfileStaffPermissions


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
            "admin.review",
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

    def test_view_audit_logs_permission_grants_audit_access(self) -> None:
        self.permissions.view_auditlogs = True
        self.permissions.save(update_fields=("view_auditlogs",))

        response = self.client.get(f"{reverse('admin.logs')}?page=1")

        self.assertEqual(response.status_code, 200)

    def test_non_superuser_cannot_change_user_permissions(self) -> None:
        target_user = User.objects.create_user(username="target")
        target_permissions = ProfileStaffPermissions.objects.create()
        target_profile = Profile.objects.create(
            user=target_user, staff_permissions=target_permissions,
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
            user=target_user, staff_permissions=target_permissions,
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
        self.assertFalse(AuditLog.objects.exists())

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
