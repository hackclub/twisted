from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from twisted_site.models import (
    Pathway,
    PathwayTimeSpent,
    Profile,
    ShopItem,
    ShopItemRegionalPricing,
    ShopRegion,
    as_user,
)

PROJECTS_PER_PAGE = 120


class ShopView(View):
    def get(self, request: HttpRequest) -> HttpResponse:
        if self.request.user.is_anonymous:
            return redirect("homepage")

        context: dict[str, object] = {}

        regions = ShopRegion.objects.all()
        context["regions"] = regions
        pathways = Pathway.objects.filter(
            start__lt=timezone.now(),
            pathwaytimespent__user=request.user,
            pathwaytimespent__unlocked=True,
        )
        context["pathways"] = pathways
        shop_items: list[ShopItem] = []
        pathway_id = request.GET.get("pathway", "")
        try:
            pathway_pk = int(pathway_id)
        except ValueError:
            pathway_pk = None
        if pathway_pk is not None:
            pathway = Pathway.objects.filter(id=pathway_pk).first()
            if pathway is not None:
                context["pathway"] = pathway
                shop_items = list(ShopItem.objects.filter(pathway=pathway))
                pathway_timespent = PathwayTimeSpent.objects.filter(
                    pathway=pathway,
                    user=request.user,
                ).first()
                if pathway_timespent is not None:
                    context["pathway_timespent"] = pathway_timespent

        parsed_shop_items: list[dict[str, object]] = []
        profile = as_user(request.user).profile
        for item in shop_items:
            if item.stock <= 0:
                continue
            region = profile.region
            if region is None:
                continue
            price = ShopItemRegionalPricing.objects.filter(
                item=item,
                region=region,
            ).first()
            if price is None:
                continue
            parsed_shop_items.append(
                {
                    "item": item,
                    "price": price,
                },
            )
        context["shop_items"] = parsed_shop_items
        return render(
            request,
            "client/shop.html",
            context,
        )

    def post(self, request: HttpRequest) -> HttpResponse:
        if self.request.user.is_anonymous:
            return redirect("homepage")

        if request.POST.get("action") == "setRegion":
            try:
                region_pk = int(request.POST.get("region", ""))
            except ValueError:
                return HttpResponseBadRequest("Invalid region")
            profile: Profile = as_user(request.user).profile
            profile.region = get_object_or_404(ShopRegion, id=region_pk)
            profile.save()

            return redirect(request.get_full_path())

        return redirect(request.path_info)
