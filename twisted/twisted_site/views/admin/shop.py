from .admin import AdminView
from django.shortcuts import render, redirect

# Create your views here.
class ShopView(AdminView):
    def get(self, request):
        context = self.get_context_data(page='shop')
        return render(request, "admin/shop.html", context=context)
