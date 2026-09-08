from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from .admin import AdminView


# Create your views here.
class ShopView(AdminView):
    def get(self, request: HttpRequest) -> HttpResponse:
        context = self.get_context_data(page="shop")
        return render(request, "admin/shop.html", context=context)
