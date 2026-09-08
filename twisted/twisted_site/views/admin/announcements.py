from django.template.response import TemplateResponse
from .admin import AdminView
from django.shortcuts import render, redirect

# Create your views here.
class AnnouncementsView(AdminView):
    def get(self, request):
        context = self.get_context_data(page='announcements')
        if self.request.user.is_anonymous:
            return redirect('homepage')
        return TemplateResponse(request, "admin/announcements.html", context=context)
