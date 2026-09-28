from itertools import chain
from operator import attrgetter

from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse

from twisted_site.models import Project, as_user

from .admin import AdminView


class ProjectDetailView(AdminView):
    def get(self, request: HttpRequest, project_id: int) -> HttpResponse:
        if self.perms.view_projects:
            self.allowed = True
        else:
            return HttpResponse("err")

        context = self.get_context_data(page="projects", subpage="detail")
        project = get_object_or_404(Project, id=project_id)

        if not isinstance(self.audit_log.additional_context, dict):
            self.audit_log.additional_context = {}

        self.audit_log.additional_context["project"] = project.project_name
        self.audit_log.additional_context["project_owner"] = as_user(project.user).profile.slack_username

        context["project"] = project

        journals = project.journals.all()  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue] # pyrefly: ignore[missing-attribute]
        ships = project.ships.all()  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue] # pyrefly: ignore[missing-attribute]
        activity = list(chain(journals, ships))
        activity.sort(key=attrgetter("created_at"), reverse=True)
        context["activity"] = activity

        return TemplateResponse(request, "admin/project.html", context)
