import json
import os

from django.contrib import messages
from django.contrib.sessions.models import Session
from django.db.models import Q
from django.forms.models import model_to_dict
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse

from twisted_site.models import ProfileStaffPermissions, User, as_user

from .admin import AdminView


# Create your views here.
class UsersView(AdminView):
    def get(self, request: HttpRequest) -> HttpResponse:
        if self.perms.view_users:
            self.allowed = True
        else:
            return HttpResponse("err")

        context = self.get_context_data(page="users")
        context["user_count"] = User.objects.count()
        if request.GET.get("search") not in (None, ""):
            query: str = request.GET["search"]
            context["users"] = (
                User.objects.filter(
                    Q(profile__slack_username__icontains=query)
                    | Q(profile__slack_id__icontains=query)
                    | Q(first_name__icontains=query)
                    | Q(last_name__icontains=query),
                )
                .order_by("profile__slack_username")
                .all()[:50]
            )
            context["search"] = True
        else:
            context["users"] = User.objects.order_by("profile__slack_username").all()[:75]
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
            key: str = request.POST["key"]
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
            profile.staff_permissions = ProfileStaffPermissions.objects.create()
            self.audit_log.pii = True
            self.audit_log.additional_context["permission_changed"] = "Made user an admin"
            messages.success(request, f"Made @{as_user(user).profile.slack_username} an admin.")
            profile.save()

        return redirect(self.request.path)
