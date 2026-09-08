from .admin import AdminView
from django.shortcuts import render, redirect

# Create your views here.
class FulfillmentView(AdminView):
    def get(self, request):
        context = self.get_context_data(page='fulfillment')
        return render(request, "admin/fulfillment.html", context=context)
