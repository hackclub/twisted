from django.views import View
from django.shortcuts import render, redirect, resolve_url
from dataclasses import dataclass
import json
from typing import Literal
from django_htmx.http import trigger_client_event
from ...models import AuditLog


@dataclass
class SidebarLink:
    name: str
    icon: str
    text: str
    href: str


# Create your views here.
class AdminView(View):
    def get_context_data(self, page, subpage=None) -> dict:
        context = {}
        context["page"] = page
        context["subpage"] = subpage
        context["sidebar_links"] = [
            SidebarLink(
                name="dashboard",
                icon="analytics",
                text="Analytics",
                href=resolve_url("admin.dash"),
            ),
            SidebarLink(
                name="users",
                icon="profile",
                text="Users",
                href=resolve_url("admin.users"),
            ),
            SidebarLink(
                name="pathways",
                icon="controls",
                text="Pathways",
                href=resolve_url("admin.pathways"),
            ),
            SidebarLink(
                name="fulfillment",
                icon="list",
                text="Fulfillment",
                href=resolve_url("admin.fulfillment"),
            ),
            SidebarLink(
                name="shop", icon="bag-add", text="Shop", href=resolve_url("admin.shop")
            ),
            SidebarLink(
                name="review",
                icon="message-new",
                text="Review",
                href=resolve_url("admin.review"),
            ),
            SidebarLink(
                name="announcements",
                icon="important",
                text="Announcements",
                href=resolve_url("admin.announcements"),
            ),
            SidebarLink(
                name="logs",
                icon="view",
                text="Audit Logs",
                href=resolve_url("admin.logs") + "?page=1",
            ),
        ]
        context["profile"] = self.request.user.profile
        return context

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_anonymous:
            return redirect("homepage")
        if not request.user.profile.is_staff:
            return redirect("dashboard")
        self.audit_log = AuditLog(
            user=request.user,
            path=self.request.get_full_path(),
            post=(request.method.lower() == "post"),
            additional_context={},
        )
        response = super().dispatch(request, *args, **kwargs)
        self.audit_log.save()
        return response
