from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt


# Create your views here.
@method_decorator(csrf_exempt, name="dispatch")
class AriView(View):
    def get(self, request):
        return ...
