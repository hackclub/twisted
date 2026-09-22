from dataclasses import dataclass
from typing import Any, override

from django.contrib import messages
from django.http import HttpRequest, HttpResponseBase
from django.shortcuts import redirect, resolve_url
from django.views import View

from twisted_site.models import AuditLog, ProfileStaffPermissions, as_user


@dataclass
class SidebarLink:
    name: str
    icon: str
    text: str
    href: str


# Create your views here.
class AdminView(View):
    audit_log: AuditLog  # pyright: ignore[reportUninitializedInstanceVariable]
    perms: ProfileStaffPermissions  # pyright: ignore[reportUninitializedInstanceVariable]
    allowed = False

    def get_context_data(self, page: str, subpage: str | None = None) -> dict[str, Any]:  # pyrefly: ignore[explicit-any]
        context: dict[str, Any] = {}  # pyrefly: ignore[explicit-any]
        context["page"] = page
        context["subpage"] = subpage
        sidebar_links = [
            SidebarLink(
                name="dashboard",
                icon="analytics",
                text="Analytics",
                href=resolve_url("admin.dash"),
            ),
        ]
        if self.perms.view_users:
            sidebar_links.append(
                SidebarLink(
                    name="users",
                    icon="profile",
                    text="Users",
                    href=resolve_url("admin.users"),
                ),
            )
        if self.perms.view_pathways:
            sidebar_links.append(
                SidebarLink(
                    name="pathways",
                    icon="controls",
                    text="Pathways",
                    href=resolve_url("admin.pathways"),
                ),
            )
        if self.perms.manage_fulfillments:
            sidebar_links.append(
                SidebarLink(
                    name="fulfillment",
                    icon="list",
                    text="Fulfillment",
                    href=resolve_url("admin.fulfillment"),
                ),
            )
        if self.perms.manage_shop:
            sidebar_links.append(
                SidebarLink(
                    name="shop",
                    icon="bag-add",
                    text="Shop",
                    href=resolve_url("admin.shop"),
                ),
            )
        if self.perms.view_review:
            sidebar_links.append(
                SidebarLink(
                    name="review",
                    icon="message-new",
                    text="Review",
                    href=resolve_url("admin.review"),
                ),
            )
        if self.perms.manage_announcements:
            sidebar_links.append(
                SidebarLink(
                    name="announcements",
                    icon="important",
                    text="Announcements",
                    href=resolve_url("admin.announcements"),
                ),
            )
        if self.perms.view_auditlogs:
            sidebar_links.append(
                SidebarLink(
                    name="logs",
                    icon="view",
                    text="Audit Logs",
                    href=f"{resolve_url("admin.logs")}?page=1",
                ),
            )

        context["sidebar_links"] = sidebar_links
        context["profile"] = as_user(self.request.user).profile
        return context

    @override
    def dispatch(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponseBase:
        if request.user.is_anonymous:
            return redirect("homepage")
        if not as_user(request.user).profile.is_staff:
            return redirect("dashboard")
        self.audit_log = AuditLog(
            user=request.user,
            path=self.request.get_full_path(),
            post=(("" if request.method in (None, "") else request.method).lower() == "post"),
            additional_context={},
        )

        perms = as_user(self.request.user).profile.staff_permissions
        if perms is None:
            profile = as_user(self.request.user).profile
            perms = ProfileStaffPermissions.objects.create()
            profile.staff_permissions = perms
            profile.save()

        self.perms = perms
        response = super().dispatch(request, *args, **kwargs)

        if not self.allowed:
            messages.error(request, "You arent allowed to visit this page!")
            return redirect("admin.dash")

        self.audit_log.save()
        return response
