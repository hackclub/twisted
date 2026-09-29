from typing import override
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from twisted_site.models import Journal, Profile, ProfileStaffPermissions, Project


class LocalStaticAssetTests(TestCase):
    user: User  # pyright: ignore[reportUninitializedInstanceVariable]
    profile: Profile  # pyright: ignore[reportUninitializedInstanceVariable]

    @override
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="asset-user")
        self.profile = Profile.objects.create(user=self.user)
        self.client = Client()
        self.client.force_login(self.user)

    def test_client_pages_load_vendored_markdown_libraries(self) -> None:
        response = self.client.get(reverse("dashboard"))
        content = response.content.decode()

        self.assertContains(response, "vendor/marked/marked.umd.js")
        self.assertContains(response, "vendor/dompurify/purify.min.js")
        self.assertNotIn("cdn.jsdelivr.net", content)
        self.assertNotIn("gstatic.com", content)

    def test_admin_pages_load_vendored_charts_alpine_and_htmx(self) -> None:
        self.profile.is_staff = True
        self.profile.save(update_fields=("is_staff",))

        response = self.client.get(reverse("admin.dash"))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "vendor/chart.js/chart.umd.min.js")
        self.assertContains(response, "js/admin_charts.js")
        self.assertContains(response, "vendor/alpine/alpine.min.js")
        self.assertContains(response, "django_htmx/htmx-2.min.js")
        self.assertNotIn("cdn.jsdelivr.net", content)
        self.assertNotIn("gstatic.com", content)

    def test_admin_project_page_loads_vendored_markdown_libraries(self) -> None:
        permissions = ProfileStaffPermissions.objects.create(view_projects=True)
        self.profile.is_staff = True
        self.profile.staff_permissions = permissions
        self.profile.save(update_fields=("is_staff", "staff_permissions"))
        project = Project.objects.create(
            user=self.user,
            project_name="Assets project",
            project_description="x",
            project_type="software",
        )

        response = self.client.get(
            reverse("admin.projects.detail", kwargs={"project_id": project.pk}),
        )
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "vendor/marked/marked.umd.js")
        self.assertContains(response, "vendor/dompurify/purify.min.js")
        self.assertNotIn("cdn.jsdelivr.net", content)

    def test_chart_data_is_rendered_with_json_script(self) -> None:
        self.profile.is_staff = True
        self.profile.save(update_fields=("is_staff",))
        project = Project.objects.create(
            user=self.user,
            project_name="Chart project",
            project_description="x",
            project_type="software",
        )
        _ = Journal.objects.create(
            project=project,
            type="untracked",
            content="x",
            minutes_worked=60,
            reduced_minutes=60,
        )
        payload = "</script><script>alert(1)</script>"

        with patch("twisted_site.models.Profile.get_country", return_value=payload):
            response = self.client.get(reverse("admin.dash"))

        content = response.content.decode()
        self.assertContains(response, 'id="hours_logged_chart_data"')
        self.assertNotIn(payload, content)
        self.assertIn("\\u003C/script\\u003E", content)
