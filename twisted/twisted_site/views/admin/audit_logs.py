from django.core.paginator import Paginator
from django.db.models.query_utils import Q
from django.shortcuts import redirect, render
from django.template.response import TemplateResponse

from ...models import AuditLog
from .admin import AdminView


# Create your views here.
class AuditLogsView(AdminView):
    def get(self, request):
        page_number = request.GET.get("page")
        if page_number is None:
            return redirect(self.request.get_full_path() + "?page=1")

        context = self.get_context_data(page="logs")

        auditlogs = AuditLog.objects.order_by("-timestamp")

        context_mode = request.GET.get("context_mode", "false") == "true"
        if context_mode:
            auditlogs = auditlogs.exclude(
                Q(additional_context__isnull=True) | Q(additional_context={})
            )

        paginator = Paginator(auditlogs, 250, orphans=50)
        context["logs"] = paginator.get_page(page_number)
        context["log_count"] = len(auditlogs)
        return TemplateResponse(request, "admin/logs.html", context=context)
