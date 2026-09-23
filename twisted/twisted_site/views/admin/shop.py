from django.contrib import messages
from django.db.models import ProtectedError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from twisted_site.models import ShopRegion

from .admin import AdminView


# Create your views here.
class ShopView(AdminView):
    def get(self, request: HttpRequest) -> HttpResponse:
        if self.perms.manage_shop:
            self.allowed = True
        else:
            return HttpResponse("err")

        context = self.get_context_data(page="shop")
        return render(request, "admin/shop.html", context=context)


class ShopRegionsView(AdminView):
    def get(self, request: HttpRequest) -> HttpResponse:
        if self.perms.manage_shop:
            self.allowed = True
        else:
            return HttpResponse("err")

        context = self.get_context_data(page="shop", subpage="regions")
        context["regions"] = ShopRegion.objects.order_by("name").all()
        return render(request, "admin/shop_regions.html", context=context)

    def post(self, request: HttpRequest) -> HttpResponse:
        if self.perms.manage_shop:
            self.allowed = True
        else:
            return HttpResponse("err")

        if not isinstance(self.audit_log.additional_context, dict):
            self.audit_log.additional_context = {}

        action = request.POST.get("action")

        if action == "create":
            name = (request.POST.get("name") or "").strip()
            if name == "":
                messages.error(request, "Region name cannot be empty!")
                return redirect("admin.shop.regions")

            region = ShopRegion.objects.create(name=name)
            self.audit_log.additional_context["action"] = "create_region"
            self.audit_log.additional_context["region_id"] = region.id
            self.audit_log.additional_context["region_name"] = region.name
            messages.success(request, f'Successfully created region "{region.name}"!')

        elif action == "update":
            region = get_object_or_404(ShopRegion, id=request.POST.get("region_id"))
            name = (request.POST.get("name") or "").strip()
            if name == "":
                messages.error(request, "Region name cannot be empty!")
                return redirect("admin.shop.regions")

            self.audit_log.additional_context["action"] = "update_region"
            self.audit_log.additional_context["region_id"] = region.id
            self.audit_log.additional_context["old_name"] = region.name
            self.audit_log.additional_context["new_name"] = name

            region.name = name
            region.save()
            messages.success(request, f'Successfully renamed region to "{region.name}"!')

        elif action == "delete":
            region = get_object_or_404(ShopRegion, id=request.POST.get("region_id"))

            self.audit_log.additional_context["action"] = "delete_region"
            self.audit_log.additional_context["region_id"] = region.id
            self.audit_log.additional_context["region_name"] = region.name

            try:
                region.delete()
            except ProtectedError:
                messages.error(
                    request,
                    f'Cannot delete region "{region.name}" because it still has pricing attached to it!',
                )
                return redirect("admin.shop.regions")

            messages.success(request, f'Successfully deleted region "{region.name}"!')

        return redirect("admin.shop.regions")
