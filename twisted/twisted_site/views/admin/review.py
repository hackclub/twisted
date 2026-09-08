from django.contrib import messages
from django.http import HttpResponse
from .admin import AdminView
from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
from ...models import ProjectShip

# Create your views here.
class ReviewView(AdminView):
    def get(self, request):
        if settings.DEBUG_REVIEW:
            return self.debug_get(request)
        
        context = self.get_context_data(page='review')
        return render(request, "admin/review.html", context=context)
    
    def post(self, request):
        if settings.DEBUG_REVIEW:
            return self.debug_post(request)
        
        context = self.get_context_data(page='review')
        return redirect(self.request.path_info)
    
    def debug_get(self, request):
        context = self.get_context_data(page='review')
        context['ships'] = ProjectShip.objects.all().order_by('-created_at')
        return render(request, "admin/debug/review.html", context=context)
    
    def debug_post(self, request):
        id = request.POST['id']

        status = request.POST['status']
        note_to_maker = request.POST['note_to_maker']
        audit_note = request.POST['audit_note']
        technical_features = request.POST['technical_features']
        deflation_reason = request.POST['deflation_reason']

        final_status = request.POST['final_status']
        final_note_to_maker = request.POST['final_note_to_maker']
        final_audit_note = request.POST['final_audit_note']

        ship = get_object_or_404(ProjectShip, id=id)

        ship.status = status
        ship.note_to_maker = note_to_maker
        ship.audit_note = audit_note
        ship.technical_features = technical_features
        ship.deflation_reason = deflation_reason

        ship.final_status = final_status
        ship.final_note_to_maker = final_note_to_maker
        ship.final_audit_note = final_audit_note

        ship.save()
        messages.info(request, f"Ship with id {id} updated.")
        return redirect(self.request.path_info)