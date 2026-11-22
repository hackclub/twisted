from operator import attrgetter

from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse

from twisted_site.models import Journal, Project, ProjectShip, as_user

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
        context["can_manage_journals"] = self.perms.manage_journals

        journals = list(Journal.objects.filter(project=project))
        ships = list(ProjectShip.objects.filter(project=project))
        context["journal_count"] = len(journals)
        context["minutes_logged"] = sum(journal.reduced_minutes for journal in journals)
        context["latest_ship"] = max(ships, key=attrgetter("created_at"), default=None)

        activity = [
            *({"kind": "journal", "item": journal} for journal in journals),
            *({"kind": "ship", "item": ship} for ship in ships),
        ]
        activity.sort(key=lambda entry: entry["item"].created_at, reverse=True)  # pyrefly: ignore[implicit-any-lambda]
        context["activity"] = activity

        return TemplateResponse(request, "admin/project.html", context)
