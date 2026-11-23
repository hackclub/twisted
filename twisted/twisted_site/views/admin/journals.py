from dataclasses import dataclass

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse

from twisted_site.models import JOURNAL_TYPES, Journal, Project, TemplateContext, as_user

from .admin import AdminView


@dataclass
class JournalFields:
    type: str
    content: str
    minutes_worked: int
    reduced_minutes: int


def _journal_form_values(request: HttpRequest) -> TemplateContext:
    """Return the raw journal form fields, to re-fill the form after an error."""
    return {
        "journal_type": request.POST.get("type", ""),
        "content": request.POST.get("content", ""),
        "minutes_worked": request.POST.get("minutes_worked", ""),
        "reduced_minutes": request.POST.get("reduced_minutes", ""),
    }


def _journal_initial_values(journal: Journal) -> TemplateContext:
    return {
        "journal_type": journal.type,
        "content": journal.content,
        "minutes_worked": journal.minutes_worked,
        "reduced_minutes": journal.reduced_minutes,
    }


def _parse_minutes(raw: str, label: str) -> int | str:
    try:
        minutes = int(raw.strip())
    except ValueError:
        return f"{label} must be a whole number of minutes!"
    if minutes < 0:
        return f"{label} cannot be negative!"
    return minutes


def parse_journal_form(request: HttpRequest) -> JournalFields | str:
    """
    Validate the staff journal form.

    Staff are trusted with the amounts, so the participant-side limits (the Hackatime
    budget, the untracked cap, minimum length and image counts) do not apply here.
    An empty "approved minutes" field means "same as minutes worked".

    Returns:
        The parsed fields, or an error message.

    """
    journal_type = request.POST.get("type", "")
    if journal_type not in JOURNAL_TYPES:
        return "Pick a valid journal type!"

    content = request.POST.get("content", "")
    if content.strip() == "":
        return "Journal content cannot be empty!"

    minutes_worked = _parse_minutes(request.POST.get("minutes_worked", ""), "Minutes worked")
    if isinstance(minutes_worked, str):
        return minutes_worked

    reduced_raw = request.POST.get("reduced_minutes", "")
    if reduced_raw.strip() == "":
        reduced_minutes: int | str = minutes_worked
    else:
        reduced_minutes = _parse_minutes(reduced_raw, "Approved minutes")
    if isinstance(reduced_minutes, str):
        return reduced_minutes

    if reduced_minutes > minutes_worked:
        return "Approved minutes cannot be more than minutes worked!"

    return JournalFields(
        type=journal_type,
        content=content,
        minutes_worked=minutes_worked,
        reduced_minutes=reduced_minutes,
    )


class _JournalAdminView(AdminView):
    """Shared permission check, audit details and form rendering for staff journal views."""

    def _allow(self) -> bool:
        if self.perms.view_projects and self.perms.manage_journals:
            self.allowed = True
        return self.allowed

    def _audit(self, project: Project, journal: Journal | None = None) -> TemplateContext:
        """Record which project and journal the request touched; returns the context dict."""
        audit_context: TemplateContext = (
            self.audit_log.additional_context
            if isinstance(self.audit_log.additional_context, dict)
            else {}
        )
        self.audit_log.additional_context = audit_context
        audit_context["project"] = project.project_name
        audit_context["project_owner"] = as_user(project.user).profile.slack_username
        if journal is not None:
            audit_context["journal_id"] = journal.id
        return audit_context

    def _render_form(
        self,
        request: HttpRequest,
        project: Project,
        values: TemplateContext,
        journal: Journal | None = None,
        error: str | None = None,
    ) -> HttpResponse:
        if error is not None:
            messages.error(request, error)
        context = self.get_context_data(page="projects", subpage="journal")
        context.update(values)
        context["project"] = project
        context["journal"] = journal
        context["journal_types"] = JOURNAL_TYPES
        context["project_shipped"] = project.is_shipped()
        return TemplateResponse(request, "admin/journal_form.html", context)


class JournalCreateView(_JournalAdminView):
    def get(self, request: HttpRequest, project_id: int) -> HttpResponse:
        if not self._allow():
            return HttpResponse("err")

        project = get_object_or_404(Project, id=project_id)
        _ = self._audit(project)
        default_type = "hackatime" if project.project_type == "software" else "untracked"
        return self._render_form(request, project, {"journal_type": default_type})

    def post(self, request: HttpRequest, project_id: int) -> HttpResponse:
        if not self._allow():
            return HttpResponse("err")

        project = get_object_or_404(Project, id=project_id)
        audit_context = self._audit(project)

        fields = parse_journal_form(request)
        if isinstance(fields, str):
            return self._render_form(request, project, _journal_form_values(request), error=fields)

        journal = Journal.objects.create(
            project=project,
            type=fields.type,
            content=fields.content,
            minutes_worked=fields.minutes_worked,
            reduced_minutes=fields.reduced_minutes,
        )
        after = _journal_initial_values(journal)
        _ = after.pop("content")
        audit_context["journal_id"] = journal.id
        audit_context["action"] = "create_journal"
        audit_context["after"] = after

        messages.success(request, f"Created a {fields.reduced_minutes} minute journal.")
        return redirect("admin.projects.detail", project.id)


class JournalEditView(_JournalAdminView):
    def get(self, request: HttpRequest, journal_id: int) -> HttpResponse:
        if not self._allow():
            return HttpResponse("err")

        journal = get_object_or_404(Journal.objects.select_related("project"), id=journal_id)
        _ = self._audit(journal.project, journal)
        return self._render_form(
            request,
            journal.project,
            _journal_initial_values(journal),
            journal=journal,
        )

    def post(self, request: HttpRequest, journal_id: int) -> HttpResponse:
        if not self._allow():
            return HttpResponse("err")

        journal = get_object_or_404(Journal.objects.select_related("project"), id=journal_id)
        audit_context = self._audit(journal.project, journal)

        fields = parse_journal_form(request)
        if isinstance(fields, str):
            return self._render_form(
                request,
                journal.project,
                _journal_form_values(request),
                journal=journal,
                error=fields,
            )

        # Journal text is kept out of the audit log: it is long and shown on the project.
        before = _journal_initial_values(journal)
        content_changed = before.pop("content") != fields.content

        journal.type = fields.type
        journal.content = fields.content
        journal.minutes_worked = fields.minutes_worked
        journal.reduced_minutes = fields.reduced_minutes
        journal.save()

        after = _journal_initial_values(journal)
        _ = after.pop("content")
        audit_context["action"] = "edit_journal"
        audit_context["before"] = before
        audit_context["after"] = after
        audit_context["content_changed"] = content_changed

        messages.success(request, "Journal updated.")
        return redirect("admin.projects.detail", journal.project.id)


class JournalDeleteView(_JournalAdminView):
    def post(self, request: HttpRequest, journal_id: int) -> HttpResponse:
        if not self._allow():
            return HttpResponse("err")

        journal = get_object_or_404(Journal.objects.select_related("project"), id=journal_id)
        project = journal.project
        audit_context = self._audit(project, journal)
        before = _journal_initial_values(journal)
        _ = before.pop("content")
        audit_context["action"] = "delete_journal"
        audit_context["before"] = before

        _ = journal.delete()

        messages.success(request, f"Deleted a {before['reduced_minutes']} minute journal.")
        return redirect("admin.projects.detail", project.id)
