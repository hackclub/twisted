from django.conf import settings
from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from twisted_site.models import PROJECT_SHIP_STATUSES, ProjectShip

from .admin import AdminView

REVIEW_FILTERS = ("open", "needs_final", "finalized", "all")
DECIDED_STATUSES = ("approved", "rejected")


# Create your views here.
class ReviewView(AdminView):
    def get(self, request: HttpRequest) -> HttpResponse:
        if self.perms.view_review:
            self.allowed = True
        else:
            return HttpResponse("err")

        if settings.DEBUG_REVIEW:
            return self.debug_get(request)

        status_filter = request.GET.get("filter", "open")
        if status_filter not in REVIEW_FILTERS:
            status_filter = "open"

        ships = ProjectShip.objects.select_related("project", "project__user").order_by(
            "-created_at",
        )
        if status_filter == "open":
            ships = ships.filter(final_status="pending")
        elif status_filter == "needs_final":
            ships = ships.filter(final_status="pending", status__in=DECIDED_STATUSES)
        elif status_filter == "finalized":
            ships = ships.exclude(final_status="pending")

        context = self.get_context_data(page="review")
        context["ships"] = ships
        context["status_filter"] = status_filter
        context["statuses"] = PROJECT_SHIP_STATUSES
        context["open_count"] = ProjectShip.objects.filter(final_status="pending").count()
        context["needs_final_count"] = ProjectShip.objects.filter(
            final_status="pending",
            status__in=DECIDED_STATUSES,
        ).count()
        context["finalized_count"] = ProjectShip.objects.exclude(final_status="pending").count()
        return render(request, "admin/review.html", context=context)

    def post(self, request: HttpRequest) -> HttpResponse:
        if self.perms.manage_review:
            self.allowed = True
        else:
            return HttpResponse("err")

        if settings.DEBUG_REVIEW:
            return self.debug_post(request)

        status_filter = request.POST.get("filter", "open")
        if status_filter not in REVIEW_FILTERS:
            status_filter = "open"
        redirect_url = f"{self.request.path}?filter={status_filter}"

        try:
            ship_pk = int(request.POST.get("ship", ""))
        except ValueError:
            messages.error(request, "Select a valid ship.")
            return redirect(redirect_url)

        final_status = request.POST.get("final_status", "")
        if final_status not in PROJECT_SHIP_STATUSES:
            messages.error(request, f"'{final_status}' is not a valid final status.")
            return redirect(redirect_url)

        ship = get_object_or_404(ProjectShip, id=ship_pk)

        if not isinstance(self.audit_log.additional_context, dict):
            self.audit_log.additional_context = {}

        old_final_status = ship.final_status
        ship.final_status = final_status
        ship.final_note_to_maker = request.POST.get("final_note_to_maker", "")
        ship.final_audit_note = request.POST.get("final_audit_note", "")
        ship.save(update_fields=("final_status", "final_note_to_maker", "final_audit_note"))

        self.audit_log.pii = True
        self.audit_log.additional_context["ship_id"] = ship.id
        self.audit_log.additional_context["project"] = ship.project.project_name
        self.audit_log.additional_context["final_status"] = f"{old_final_status} -> {final_status}"
        messages.success(
            request,
            f"Final review for {ship.project.project_name} set to {final_status}.",
        )
        return redirect(redirect_url)

    def debug_get(self, request: HttpRequest) -> HttpResponse:
        context = self.get_context_data(page="review")
        context["ships"] = ProjectShip.objects.all().order_by("-created_at")
        return render(request, "admin/debug/review.html", context=context)

    def debug_post(self, request: HttpRequest) -> HttpResponse:
        ship_id: str = request.POST["id"]

        status: str = request.POST["status"]
        note_to_maker: str = request.POST["note_to_maker"]
        audit_note: str = request.POST["audit_note"]
        technical_features: str = request.POST["technical_features"]
        deflation_reason: str = request.POST["deflation_reason"]

        final_status: str = request.POST["final_status"]
        final_note_to_maker: str = request.POST["final_note_to_maker"]
        final_audit_note: str = request.POST["final_audit_note"]

        ship = get_object_or_404(ProjectShip, id=ship_id)

        ship.status = status
        ship.note_to_maker = note_to_maker
        ship.audit_note = audit_note
        ship.technical_features = technical_features
        ship.deflation_reason = deflation_reason

        ship.final_status = final_status
        ship.final_note_to_maker = final_note_to_maker
        ship.final_audit_note = final_audit_note

        ship.save()
        messages.info(request, f"Ship with id {ship_id} updated.")
        return redirect(self.request.path_info)
