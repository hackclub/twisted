from django.contrib import messages
from django.db import transaction
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
    ShopOrder,
    ShopRegion,
    as_user,
)
from twisted_site.slack import escape_mrkdwn, log_to_channel


def _selected_pathway(request: HttpRequest) -> Pathway | None:
    """Return the pathway referenced by the request, or None when it is missing/invalid."""
    raw = request.POST.get("pathway", "")
    if raw == "":
        raw = request.GET.get("pathway", "")
    try:
        pathway_pk = int(raw)
    except ValueError:
        return None
    return Pathway.objects.filter(id=pathway_pk).first()


class ShopView(View):
    def get(self, request: HttpRequest) -> HttpResponse:
        if self.request.user.is_anonymous:
            return redirect("homepage")

        profile = as_user(request.user).profile

        context: dict[str, object] = {}

        regions = ShopRegion.objects.all()
        context["regions"] = regions
        pathways = Pathway.objects.filter(
            start__lt=timezone.now(),
            pathwaytimespent__user=request.user,
            pathwaytimespent__unlocked=True,
        )
        context["pathways"] = pathways
        context["twists_available"] = profile.twists
        shop_items: list[ShopItem] = []
        pathway = _selected_pathway(request)
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

        if request.POST.get("action") == "deposit":
            return self.deposit(request)

        if request.POST.get("action") == "purchase":
            return self.purchase(request)

        return redirect(request.path_info)

    def _shop_redirect(self, request: HttpRequest, pathway: Pathway | None) -> HttpResponse:
        if pathway is not None:
            return redirect(f"{request.path}?pathway={pathway.id}")
        return redirect(request.path)

    def deposit(self, request: HttpRequest) -> HttpResponse:
        pathway = _selected_pathway(request)
        if pathway is None:
            messages.error(request, "Select a pathway first.")
            return self._shop_redirect(request, None)

        try:
            amount = int(request.POST.get("amount", ""))
        except ValueError:
            messages.error(request, "Deposit amount must be a whole number of twists.")
            return self._shop_redirect(request, pathway)
        if amount <= 0:
            messages.error(request, "Deposit amount must be positive.")
            return self._shop_redirect(request, pathway)

        profile = as_user(request.user).profile
        with transaction.atomic():
            time_spent = (
                PathwayTimeSpent.objects.select_for_update()
                .filter(
                    pathway=pathway,
                    user=request.user,
                )
                .first()
            )
            if time_spent is None or not time_spent.unlocked:
                messages.error(request, "Unlock this pathway before depositing twists.")
                return self._shop_redirect(request, pathway)

            profile.remove_currency(amount, f"Transfer to pathway: {pathway}")
            pathway.add_currency(profile, amount, "Transferred from user balance")

        messages.success(
            request,
            f"Deposited {amount} twists into {pathway.name} ({time_spent.golden_twists} golden twists).",
        )
        return self._shop_redirect(request, pathway)

    def purchase(self, request: HttpRequest) -> HttpResponse:
        pathway = _selected_pathway(request)
        if pathway is None:
            messages.error(request, "Select a pathway first.")
            return self._shop_redirect(request, None)

        try:
            item_pk = int(request.POST.get("item", ""))
        except ValueError:
            messages.error(request, "Select an item to purchase.")
            return self._shop_redirect(request, pathway)

        profile = as_user(request.user).profile
        with transaction.atomic():
            time_spent = (
                PathwayTimeSpent.objects.select_for_update()
                .filter(
                    pathway=pathway,
                    user=request.user,
                )
                .first()
            )
            if time_spent is None or not time_spent.unlocked:
                messages.error(request, "Unlock this pathway before buying from its shop.")
                return self._shop_redirect(request, pathway)

            item = ShopItem.objects.select_for_update().filter(id=item_pk, pathway=pathway).first()
            if item is None:
                messages.error(request, "That item is not available in this pathway's shop.")
                return self._shop_redirect(request, pathway)
            if item.stock <= 0:
                messages.error(request, f"{item.item_name} is out of stock.")
                return self._shop_redirect(request, pathway)

            region = profile.region
            if region is None:
                messages.error(request, "Select a region first.")
                return self._shop_redirect(request, pathway)
            price = ShopItemRegionalPricing.objects.filter(item=item, region=region).first()
            if price is None:
                messages.error(request, f"{item.item_name} is not available in your region.")
                return self._shop_redirect(request, pathway)
            if time_spent.golden_twists < price.price:
                messages.error(
                    request,
                    f"You need {price.price} golden twists for {item.item_name} "
                    f"(you have {time_spent.golden_twists} in {pathway.name}).",
                )
                return self._shop_redirect(request, pathway)

            item.stock -= 1
            item.save(update_fields=("stock",))
            pathway.remove_currency(profile, price.price, f"Bought shop item {item.item_name}")
            order = ShopOrder.objects.create(
                user=request.user,
                item=item,
                pathway=pathway,
                region_name=region.name,
                price_paid=price.price,
            )

        log_to_channel(
            f":shopping-bags: *{escape_mrkdwn(profile.slack_username)}* ordered *{escape_mrkdwn(item.item_name)}* "
            f"from *{escape_mrkdwn(pathway.name)}* for *{price.price} golden twists* (order #{order.id})",
        )
        messages.success(
            request,
            f"Ordered {item.item_name} for {price.price} golden twists! "
            "Staff will fulfill it soon.",
        )
        return self._shop_redirect(request, pathway)
