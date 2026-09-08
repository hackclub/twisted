from django.views import View
from django.shortcuts import render, redirect, resolve_url, get_object_or_404
from ...models import Project

# Create your views here.
class DashboardView(View):
    def get(self, request):
        if self.request.user.is_anonymous:
            return redirect('homepage')
        profile = self.request.user.profile
        
        context = {
            "profile": profile
        }
        
        startup_windows = []
        
        project_id = request.GET.get('project')
        
        if project_id:
            project = get_object_or_404(Project, id=project_id)
            startup_windows.append({"href": resolve_url('fr.projects.detail', project.id), "title": project.project_name})
        
        context['startup_windows'] = startup_windows
        
        return render(request, "client/dashboard.html", context)