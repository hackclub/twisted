from django.contrib.sessions.models import Session
from django.template.response import TemplateResponse
from django.http import HttpResponse
from .admin import AdminView
from django.shortcuts import render, redirect
from ...models import User, Profile
from django.db.models import Q
import os
import json


# Create your views here.
class UsersView(AdminView):
    def get(self, request):
        context = self.get_context_data(page="users")
        if request.GET.get("search"):
            query = request.GET["search"]
            context["users"] = User.objects.all()
            context["users"] = User.objects.filter(
                Q(profile__slack_username__icontains=query)
                | Q(profile__slack_id__icontains=query)
                | Q(first_name__icontains=query)
                | Q(last_name__icontains=query)
            ).order_by("profile__slack_username")
            context["search"] = True
        else:
            context["users"] = User.objects.all().order_by("profile__slack_username")
        return TemplateResponse(request, "admin/users.html", context)

    def post(self, request):
        if request.POST.get("action") == "logoutall":
            Session.objects.all().delete()

        return redirect(self.request.path)


class UserDetailView(AdminView):
    def get(self, request, id):
        context = self.get_context_data(page="users", subpage="detail")
        user = User.objects.get(id=id)

        self.audit_log.additional_context["user_pfp__img"] = user.profile.slack_pfp_url
        self.audit_log.additional_context["user"] = user.profile.slack_username

        context["user"] = user
        context["login_maybe"] = os.environ.get("LOGIN_ENABLED") == "maybe"
        return TemplateResponse(request, "admin/user.html", context)

    def post(self, request, id):
        user = User.objects.get(id=id)

        self.audit_log.additional_context["user_pfp__img"] = user.profile.slack_pfp_url
        self.audit_log.additional_context["user"] = user.profile.slack_username

        if request.POST.get("action") == "toggle_is_allowed":
            prof = user.profile
            prof.is_allowed = not prof.is_allowed
            self.audit_log.additional_context["is_allowed"] = (
                f"Set to {prof.is_allowed}"
            )
            prof.save()
            resp = redirect(self.request.path)
            resp["HX-Trigger"] = json.dumps(
                {
                    "toast": {
                        "message": f"Set is_allowed to {prof.is_allowed}",
                        "variant": "success",
                    }
                }
            )
            return resp
