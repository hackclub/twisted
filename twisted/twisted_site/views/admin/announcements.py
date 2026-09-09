from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.template.response import TemplateResponse

from .admin import AdminView


# Create your views here.
class AnnouncementsView(AdminView):
    def get(self, request: HttpRequest) -> HttpResponse:
        context = self.get_context_data(page="announcements")
        if self.request.user.is_anonymous:
            return redirect("homepage")
        return TemplateResponse(request, "admin/announcements.html", context=context)
