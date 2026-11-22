import json
import os
from dataclasses import dataclass

from django.contrib import messages
from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.sessions.models import Session
from django.db import models as django_models
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.forms.models import model_to_dict
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse

from twisted_site.models import (
    PROJECT_SHIP_STATUSES,
    Profile,
    ProfileStaffPermissions,
    Project,
    User,
    as_user,
    latest_ship_status,
    status_is_shipped,
)

from .admin import AdminView

#: Permission fields a superuser may change through the admin UI. Derived from
#: the model so it stays in sync; anything else (e.g. `id`) is rejected.
STAFF_PERMISSION_FIELDS = frozenset(
    field.name
    for field in ProfileStaffPermissions._meta.get_fields()  # noqa: SLF001
    if isinstance(field, django_models.BooleanField)
)


@dataclass
class UserProjectStats:
    projects: int = 0
    shipped: int = 0
    minutes_logged: int = 0
    minutes_shipped: int = 0


def with_project_stats[UserT: AbstractBaseUser](users: list[UserT]) -> list[UserT]:
    """
    Set `user.project_stats` on each user with one query for all of them.

    This replaces `Profile.time_logged()` and friends in lists, which run several
    queries per project.
    """
    stats = {user.pk: UserProjectStats() for user in users}
    rows = (
        Project.objects.filter(user__in=stats.keys())
        .annotate(
            minutes=Sum("journals__reduced_minutes"),
            ship_status=latest_ship_status(),
        )
        .values_list("user_id", "minutes", "ship_status")
    )
    for user_id, minutes, ship_status in rows:
        user_stats = stats[user_id]
        user_stats.projects += 1
        user_stats.minutes_logged += minutes or 0
        if status_is_shipped(ship_status):
            user_stats.shipped += 1
            user_stats.minutes_shipped += minutes or 0
    for user in users:
        user.project_stats = stats[user.pk]  # pyright: ignore[reportAttributeAccessIssue]
    return users


# Create your views here.
class UsersView(AdminView):
    def get(self, request: HttpRequest) -> HttpResponse:
        if self.perms.view_users:
            self.allowed = True
        else:
            return HttpResponse("err")

        context = self.get_context_data(page="users")
        context["user_count"] = User.objects.count()
        users = User.objects.select_related("profile").order_by("profile__slack_username")
        if request.GET.get("search") not in (None, ""):
            query: str = request.GET["search"]
            users = users.filter(
                Q(profile__slack_username__icontains=query)
                | Q(profile__slack_id__icontains=query)
                | Q(first_name__icontains=query)
                | Q(last_name__icontains=query),
            )[:50]
            context["search"] = True
        else:
            users = users[:75]
        context["users"] = with_project_stats(list(users))
        return TemplateResponse(request, "admin/users.html", context)

    def post(self, request: HttpRequest) -> HttpResponse:
        if request.POST.get("action") == "logoutall":
            if self.perms.superuser:
                self.allowed = True
            else:
                return HttpResponse("err")

            session_count = Session.objects.count()
            _ = Session.objects.all().delete()
            if not isinstance(self.audit_log.additional_context, dict):
                self.audit_log.additional_context = {}

            self.audit_log.additional_context["action"] = "logoutall"
            self.audit_log.additional_context["sessions_deleted"] = session_count

        return redirect(self.request.path)


class UserDetailView(AdminView):
    def get(self, request: HttpRequest, user_id: int) -> HttpResponse:
        if self.perms.view_users:
            self.allowed = True
        else:
            return HttpResponse("err")

        context = self.get_context_data(page="users", subpage="detail")
        user = get_object_or_404(User, id=user_id)

        if not isinstance(self.audit_log.additional_context, dict):
            self.audit_log.additional_context = {}

        self.audit_log.additional_context["user_pfp__img"] = as_user(user).profile.slack_pfp_url
        self.audit_log.additional_context["user"] = as_user(user).profile.slack_username

        context["user"] = user
        projects = list(
            Project.objects.filter(user=user)
            .annotate(
                minutes=Coalesce(Sum("journals__reduced_minutes"), 0),
                ship_status=latest_ship_status(),
            )
            .order_by("-created_at"),
        )
        for project in projects:
            project.ship_status_display = PROJECT_SHIP_STATUSES.get(  # pyright: ignore[reportAttributeAccessIssue]
                project.ship_status,  # pyright: ignore[reportAttributeAccessIssue]
                project.ship_status,  # pyright: ignore[reportAttributeAccessIssue]
            )
        context["projects"] = projects
        context["referrals"] = (
            Profile.objects.filter(referred_by=as_user(user).profile)
            .select_related("user")
            .annotate(minutes=Coalesce(Sum("user__projects__journals__reduced_minutes"), 0))
            .order_by("slack_username")
        )
        staff_permissions = as_user(user).profile.staff_permissions
        context["staff_perms"] = (
            model_to_dict(staff_permissions) if staff_permissions is not None else None
        )

        context["login_maybe"] = os.environ.get("LOGIN_ENABLED") == "maybe"
        return TemplateResponse(request, "admin/user.html", context)

    def post(self, request: HttpRequest, user_id: int) -> HttpResponse | None:
        if self.perms.superuser:
            self.allowed = True
        else:
            return HttpResponse("err")

        user = get_object_or_404(User, id=user_id)

        if not isinstance(self.audit_log.additional_context, dict):
            self.audit_log.additional_context = {}

        self.audit_log.additional_context["user_pfp__img"] = as_user(user).profile.slack_pfp_url
        self.audit_log.additional_context["user"] = as_user(user).profile.slack_username

        if request.POST.get("action") == "toggle_is_allowed":
            prof = as_user(user).profile
            prof.is_allowed = not prof.is_allowed
            self.audit_log.additional_context["is_allowed"] = f"Set to {prof.is_allowed}"
            prof.save()
            resp = redirect(self.request.path)
            resp["HX-Trigger"] = json.dumps(
                {
                    "toast": {
                        "message": f"Set is_allowed to {prof.is_allowed}",
                        "variant": "success",
                    },
                },
            )
            return resp
        if request.POST.get("action") == "change_permissions":
            request_perms = as_user(request.user).profile.staff_permissions
            if request_perms is None or not request_perms.superuser:
                messages.error(request, "You are not allowed to change the permissions!")
                return redirect(self.request.path)
            key = request.POST.get("key", "")
            if key not in STAFF_PERMISSION_FIELDS:
                messages.error(request, f"Unknown permission '{key}'.")
                return redirect(f"{self.request.path}#adminperms")
            value = request.POST.get("value") == "True"
            target_profile = as_user(user).profile
            perms = target_profile.staff_permissions
            if perms is None:
                perms = ProfileStaffPermissions.objects.create()
                target_profile.staff_permissions = perms
                target_profile.save()
            setattr(perms, key, value)
            perms.save()
            self.audit_log.pii = True
            self.audit_log.additional_context["permission_changed"] = f"'{key}' set to '{value}'"
            messages.success(request, f"Set permission '{key}' to '{value}' successfully.")
            return redirect(f"{self.request.path}#adminperms")

        if request.POST.get("action") == "make_admin":
            profile = as_user(user).profile
            profile.is_staff = True
            if profile.staff_permissions is None:
                profile.staff_permissions = ProfileStaffPermissions.objects.create()
            self.audit_log.pii = True
            self.audit_log.additional_context["permission_changed"] = "Made user an admin"
            messages.success(request, f"Made @{as_user(user).profile.slack_username} an admin.")
            profile.save()

        if request.POST.get("action") == "remove_admin":
            profile = as_user(user).profile
            profile.is_staff = False
            self.audit_log.pii = True
            self.audit_log.additional_context["permission_changed"] = "Removed user from admin"
            messages.success(
                request,
                f"Removed @{as_user(user).profile.slack_username} from admin.",
            )
            profile.save()

        return redirect(self.request.path)
