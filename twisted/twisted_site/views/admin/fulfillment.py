from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from .admin import AdminView


# Create your views here.
class FulfillmentView(AdminView):
    def get(self, request: HttpRequest) -> HttpResponse:
        context = self.get_context_data(page="fulfillment")
        return render(request, "admin/fulfillment.html", context=context)
