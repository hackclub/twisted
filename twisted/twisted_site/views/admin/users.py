import json
import os

from django.contrib.sessions.models import Session
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse

from twisted_site.models import User

from .admin import AdminView


# Create your views here.
class UsersView(AdminView):
    def get(self, request: HttpRequest) -> HttpResponse:
        context = self.get_context_data(page="users")
        if request.GET.get("search") not in (None, ""):
            query: str = request.GET["search"]
            context["users"] = User.objects.all()
            context["users"] = User.objects.filter(
                Q(profile__slack_username__icontains=query)
                | Q(profile__slack_id__icontains=query)
                | Q(first_name__icontains=query)
                | Q(last_name__icontains=query),
            ).order_by("profile__slack_username")
            context["search"] = True
        else:
            context["users"] = User.objects.all().order_by("profile__slack_username")
        return TemplateResponse(request, "admin/users.html", context)

    def post(self, request: HttpRequest) -> HttpResponse:
        if request.POST.get("action") == "logoutall":
            session_count = Session.objects.count()
            _ = Session.objects.all().delete()
            if not isinstance(self.audit_log.additional_context, dict):
                self.audit_log.additional_context = {}

            self.audit_log.additional_context["action"] = "logoutall"
            self.audit_log.additional_context["sessions_deleted"] = session_count

        return redirect(self.request.path)


class UserDetailView(AdminView):
    def get(self, request: HttpRequest, id: int) -> HttpResponse:
        context = self.get_context_data(page="users", subpage="detail")
        user = get_object_or_404(User, id=id)

        if not isinstance(self.audit_log.additional_context, dict):
            self.audit_log.additional_context = {}

        self.audit_log.additional_context["user_pfp__img"] = user.profile.slack_pfp_url  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue] # pyrefly: ignore[missing-attribute]
        self.audit_log.additional_context["user"] = user.profile.slack_username  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue] # pyrefly: ignore[missing-attribute]

        context["user"] = user
        context["login_maybe"] = os.environ.get("LOGIN_ENABLED") == "maybe"
        return TemplateResponse(request, "admin/user.html", context)

    def post(self, request: HttpRequest, id: int) -> HttpResponse | None:
        user = get_object_or_404(User, id=id)

        if not isinstance(self.audit_log.additional_context, dict):
            self.audit_log.additional_context = {}

        self.audit_log.additional_context["user_pfp__img"] = user.profile.slack_pfp_url  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue] # pyrefly: ignore[missing-attribute]
        self.audit_log.additional_context["user"] = user.profile.slack_username  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue] # pyrefly: ignore[missing-attribute]

        if request.POST.get("action") == "toggle_is_allowed":
            prof = user.profile  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue] # pyrefly: ignore[missing-attribute]
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
        return None
