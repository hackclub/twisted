from django.template.response import TemplateResponse
from .admin import AdminView
from django.shortcuts import render, redirect
from ...models import Journal, Project, ProjectShip
import json
# Create your views here.
class DashboardView(AdminView):
    def get(self, request):
        context = self.get_context_data(page='dashboard')
        if self.request.user.is_anonymous:
            return redirect('homepage')
        hours_logged = 0
        hours_logged_chart = {}
        logged_project_type = {"Software": 0, "Hardware": 0}
        shipped_project_type = {"Software": 0, "Hardware": 0}
        hours_shipped = 0
        hours_shipped_chart = {}
        for journal in Journal.objects.all().prefetch_related('project'):
            hours = journal.reduced_minutes / 60
            hours_logged += hours
            
            date = journal.created_at.date().strftime("%a, %d %b")
            hours_logged_chart[date] = hours_logged_chart.get(date, 0) + hours
            
            logged_project_type[journal.project.get_project_type_display()] += hours
            
            if journal.project.is_shipped():
                hours_shipped += hours
                hours_shipped_chart[date] = hours_shipped_chart.get(date, 0) + hours
                shipped_project_type[journal.project.get_project_type_display()] += hours

        context['hours_logged'] = round(hours_logged, 2)
        context['hours_logged_chart'] = json.dumps([['Date', 'Hours']] + list(hours_logged_chart.items()))
        context['logged_project_type'] = json.dumps([['Type', 'Hours']] + list(logged_project_type.items()))
        
        context['hours_shipped'] = round(hours_shipped, 2)
        context['hours_shipped_chart'] = json.dumps([['Date', 'Hours']] + list(hours_shipped_chart.items()))
        context['shipped_project_type'] = json.dumps([['Type', 'Hours']] + list(shipped_project_type.items()))
        
        
        return TemplateResponse(request, "admin/dashboard.html", context=context)