from collections.abc import Iterable
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from twisted_site.models import Pathway, Profile, ShopRegion, ShopItem, as_user

PROJECTS_PER_PAGE = 120


class ShopView(View):
    def get(self, request: HttpRequest) -> HttpResponse:
        if self.request.user.is_anonymous:
            return redirect("homepage")

        context: dict[str, object] = {}

        regions = ShopRegion.objects.all()
        context["regions"] = regions
        pathways = Pathway.objects.filter(start__lt=timezone.now(), pathwaytimespent__user=request.user, pathwaytimespent__unlocked=True)
        context["pathways"] = pathways
        shop_items = []
        pathway_id = request.GET.get("pathway", "")
        if pathway_id.isnumeric():
            context["pathway"] = pathway = Pathway.objects.get(id=int(pathway_id))
            shop_items: Iterable[ShopItem] = pathway.shop.all()  # pyright: ignore[reportAttributeAccessIssue] # ty: ignore[unresolved-attribute]
            if pathway.pathwaytimespent_set.filter(user=request.user):
                context["pathway_timespent"] = pathway.pathwaytimespent_set.get(user=request.user)

        parsed_shop_items = []
        for item in shop_items:
            pricelist = item.prices.filter(region=request.user.profile.region)
            if not pricelist:
                continue
            if not item.stock:
                continue
            pricelist = pricelist.get()
            parsed_shop_items.append({
                "item": item,
                "price": pricelist,
            })
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
            profile: Profile = as_user(request.user).profile
            profile.region = get_object_or_404(ShopRegion, id=request.POST.get("region"))
            profile.save()

            return redirect(request.get_full_path())

        return redirect(request.path_info)
