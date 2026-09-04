from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect, render

from ...models import ProjectShip
from .admin import AdminView


# Create your views here.
class ReviewView(AdminView):
    def get(self, request):
        if settings.DEBUG_REVIEW:
            return self.debug_get(request)

        context = self.get_context_data(page="review")
        return render(request, "admin/review.html", context=context)

    def post(self, request):
        if settings.DEBUG_REVIEW:
            return self.debug_post(request)

        self.get_context_data(page="review")
        return redirect(self.request.path_info)

    def debug_get(self, request):
        context = self.get_context_data(page="review")
        context["ships"] = ProjectShip.objects.all().order_by("-created_at")
        return render(request, "admin/debug/review.html", context=context)

    def debug_post(self, request):
        id = request.POST["id"]

        t1_status = request.POST["t1_status"]
        t2_status = request.POST["t2_status"]
        fraud_status = request.POST["fraud_status"]
        final_status = request.POST["final_status"]

        t1_message = request.POST["t1_message"]
        t2_message = request.POST["t2_message"]
        fraud_message = request.POST["fraud_message"]
        final_message = request.POST["final_message"]

        ship = ProjectShip.objects.get(id=id)

        ship.t1_status = t1_status
        ship.t2_status = t2_status
        ship.fraud_status = fraud_status
        ship.final_status = final_status

        ship.t1_message = t1_message
        ship.t2_message = t2_message
        ship.fraud_message = fraud_message
        ship.final_message = final_message

        ship.save()
        messages.info(request, f"Ship with id {id} updated.")
        return redirect(self.request.path_info)
