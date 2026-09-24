from datetime import datetime
from typing import Any

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from twisted_site.models import Pathway, ShopItem, ShopItemRegionalPricing, ShopRegion, User

from .admin import AdminView


def _post_text(request: HttpRequest, key: str, default: str = "") -> str:
    value = request.POST.get(key)
    return default if value is None else value


# Create your views here.
class PathwayListView(AdminView):
    def get(self, request: HttpRequest) -> HttpResponse:
        if self.perms.view_pathways:
            self.allowed = True
        else:
            return HttpResponse("err")

        context = self.get_context_data(page="pathways")
        context["pathways"] = Pathway.objects.all().order_by("start")

        pathways = Pathway.objects.order_by("start").all()

        current_pathways: list[Pathway] = []
        past_pathways: list[Pathway] = []
        future_pathways: list[Pathway] = []

        for pathway in pathways:
            if pathway.in_progress():
                current_pathways.append(pathway)
            if pathway.ended():
                past_pathways.append(pathway)
            if pathway.didnt_start():
                future_pathways.append(pathway)

        past_pathways.reverse()
        context["current_pathways"] = current_pathways
        context["past_pathways"] = past_pathways
        context["future_pathways"] = future_pathways

        return render(request, "admin/pathways/list.html", context=context)


class PathwayCreateView(AdminView):
    def get(
        self,
        request: HttpRequest,
        error: str | None = None,
        extracontext: dict[str, Any] | None = None,  # pyrefly: ignore[explicit-any]
    ) -> HttpResponse:
        if self.perms.manage_pathways:
            self.allowed = True
        else:
            return HttpResponse("err")

        if extracontext is None:
            extracontext = {}

        context = self.get_context_data(page="pathways", subpage="create")
        context.update(extracontext)

        if error not in (None, ""):
            messages.error(request, error)

        return render(request, "admin/pathways/create.html", context=context)

    def post(self, request: HttpRequest) -> HttpResponse:
        if self.perms.manage_pathways:
            self.allowed = True
        else:
            return HttpResponse("err")

        pathway_name: str | None = request.POST.get("name")
        min_mins_raw = request.POST.get("mins", "0")

        start_date: str | None = request.POST.get("startDate")
        start_time: str | None = request.POST.get("startTime")

        end_date: str | None = request.POST.get("endDate")
        end_time: str | None = request.POST.get("endTime")

        errcontext: dict[str, Any] = {  # pyrefly: ignore[explicit-any]
            "pathway_name": pathway_name,
            "min_mins": min_mins_raw,
            "start_date": start_date,
            "start_time": start_time,
            "end_date": end_date,
            "end_time": end_time,
        }

        if pathway_name in (None, ""):
            return self.get(request, "No pathway name typed!", errcontext)

        try:
            min_mins = int(min_mins_raw)
        except ValueError:
            return self.get(request, "Minimum minutes must be a whole number!", errcontext)

        if min_mins <= 0:
            return self.get(request, "Minimum minutes must be greater than zero!", errcontext)

        if start_date in (None, ""):
            return self.get(request, "No start date selected!", errcontext)

        if start_time in (None, ""):
            return self.get(request, "No start time selected!", errcontext)

        if end_date in (None, ""):
            return self.get(request, "No end date selected!", errcontext)

        if end_time in (None, ""):
            return self.get(request, "No end time selected!", errcontext)

        current_tz_offset = datetime.now(timezone.get_current_timezone()).strftime("%z")

        try:
            start = datetime.strptime(
                f"{start_date} {start_time} {current_tz_offset}",
                "%Y-%m-%d %H:%M %z",
            )
            end = datetime.strptime(
                f"{end_date} {end_time} {current_tz_offset}",
                "%Y-%m-%d %H:%M %z",
            )
        except ValueError:
            return self.get(request, "Start and end must be valid dates and times!", errcontext)

        if start >= end:
            return self.get(request, "Start must be before end!", errcontext)

        _ = Pathway.objects.create(name=pathway_name, min_mins=min_mins, start=start, end=end)

        messages.success(request, f'Successfully created Pathway for "{pathway_name}"!')

        return redirect("admin.pathways")


class PathwayDetailView(AdminView):
    def get(self, request: HttpRequest, pathway_id: int) -> HttpResponse:
        if self.perms.view_pathways:
            self.allowed = True
        else:
            return HttpResponse("err")

        context = self.get_context_data(page="pathways", subpage="detail")
        pathway = get_object_or_404(Pathway, id=pathway_id)
        context["pathway"] = pathway

        if not isinstance(self.audit_log.additional_context, dict):
            self.audit_log.additional_context = {}

        self.audit_log.additional_context["pathway_name"] = pathway.name

        mins_per_participant = pathway.mins_spent_per_participant()
        users = User.objects.filter(id__in=mins_per_participant.keys()).select_related("profile")

        participants: list[dict[str, Any]] = [  # pyrefly: ignore[explicit-any]
            {
                "user": user,
                "mins": mins_per_participant[user.id],  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue]
                "percent": min(
                    100,
                    round(mins_per_participant[user.id] / pathway.min_mins * 100),  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue]
                )
                if pathway.min_mins != 0
                else 0,
                "qualified": mins_per_participant[user.id] >= pathway.min_mins,  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue]
            }
            for user in users
        ]
        participants.sort(key=lambda p: p["mins"], reverse=True)  # pyrefly: ignore[implicit-any-lambda]

        context["participants"] = participants
        context["qualified_count"] = sum(1 for p in participants if p["qualified"])

        context["shop_items"] = ShopItem.objects.filter(pathway=pathway)
        context["shop_regions"] = ShopRegion.objects.all()

        return render(request, "admin/pathways/detail.html", context=context)

    def post(self, request: HttpRequest, pathway_id: int) -> HttpResponse:
        if self.perms.manage_shop:
            self.allowed = True
        else:
            return HttpResponse("err")

        pathway = get_object_or_404(Pathway, id=pathway_id)
        if request.POST.get("action") == "new_listing":
            item_name = _post_text(request, "name").strip()
            item_description = _post_text(request, "description").strip()
            stock_raw = _post_text(request, "stock", "999").strip()
            if stock_raw == "":
                stock_raw = "999"
            image_url = _post_text(request, "image_url").strip()

            if item_name == "" or item_description == "":
                messages.error(request, "Item name and description are required!")
                return redirect(request.path_info)

            try:
                stock = int(stock_raw)
            except ValueError:
                messages.error(request, "Item stock must be a whole number!")
                return redirect(request.path_info)
            if stock < 0:
                messages.error(request, "Item stock cannot be negative!")
                return redirect(request.path_info)

            regional_prices: list[tuple[ShopRegion, int]] = []
            for region in ShopRegion.objects.all():
                price_raw = _post_text(request, f"region-{region.id}-price").strip()
                if price_raw == "":
                    continue
                try:
                    price = int(price_raw)
                except ValueError:
                    messages.error(request, f"Price for {region.name} must be a whole number!")
                    return redirect(request.path_info)
                if price < 0:
                    messages.error(request, f"Price for {region.name} cannot be negative!")
                    return redirect(request.path_info)
                regional_prices.append((region, price))

            shop_item = ShopItem.objects.create(
                pathway=pathway,
                item_name=item_name,
                item_description=item_description,
                stock=stock,
                image_url=image_url,
            )
            for region, price in regional_prices:
                _ = ShopItemRegionalPricing.objects.create(region=region, item=shop_item, price=price)
            messages.success(request, f"Created new shop listing for {item_name}")
            return redirect(request.path_info)

        return redirect(request.path_info)


class PathwayShopItemDetailView(AdminView):
    def get(self, request: HttpRequest, listing_id: int) -> HttpResponse:
        context = self.get_context_data()
        if self.perms.view_pathways:
            self.allowed = True
        else:
            return HttpResponse("err")

        item = get_object_or_404(ShopItem, id=listing_id)
        context["item"] = item

        regions: list[dict[str, object]] = []

        for region in ShopRegion.objects.all():
            listing = ShopItemRegionalPricing.objects.filter(item=item, region=region).first()
            regions.append(
                {
                    "region": region,
                    "listing": listing,
                },
            )
        context["regions"] = regions

        return render(request, "admin/pathways/listing.html", context)

    def post(self, request: HttpRequest, listing_id: int) -> HttpResponse:
        if self.perms.manage_shop:
            self.allowed = True
        else:
            return HttpResponse("err")
        item = get_object_or_404(ShopItem, id=listing_id)
        item_name = _post_text(request, "name", item.item_name).strip()
        item_description = _post_text(request, "description", item.item_description).strip()
        stock_raw = _post_text(request, "stock", str(item.stock)).strip()
        if stock_raw == "":
            stock_raw = "0"
        image_url = _post_text(request, "image_url", item.image_url).strip()

        if item_name == "" or item_description == "":
            messages.error(request, "Item name and description are required!")
            return redirect("admin.pathways.detail", item.pathway.id)
        try:
            stock = int(stock_raw)
        except ValueError:
            messages.error(request, "Item stock must be a whole number!")
            return redirect("admin.pathways.detail", item.pathway.id)
        if stock < 0:
            messages.error(request, "Item stock cannot be negative!")
            return redirect("admin.pathways.detail", item.pathway.id)

        regional_prices: list[tuple[ShopRegion, int | None]] = []
        for region in ShopRegion.objects.all():
            price_raw = _post_text(request, f"region-{region.id}-price").strip()
            if price_raw == "":
                regional_prices.append((region, None))
                continue
            try:
                price = int(price_raw)
            except ValueError:
                messages.error(request, f"Price for {region.name} must be a whole number!")
                return redirect("admin.pathways.detail", item.pathway.id)
            if price < 0:
                messages.error(request, f"Price for {region.name} cannot be negative!")
                return redirect("admin.pathways.detail", item.pathway.id)
            regional_prices.append((region, price))

        item.item_name = item_name
        item.item_description = item_description
        item.stock = stock
        item.image_url = image_url
        item.save()

        for region, new_price in regional_prices:
            listing = ShopItemRegionalPricing.objects.filter(item=item, region=region).first()
            if new_price is not None:
                if listing is None:
                    _ = ShopItemRegionalPricing.objects.create(
                        region=region,
                        item=item,
                        price=new_price,
                    )
                else:
                    listing.price = new_price
                    listing.save()
            elif listing is not None:
                _ = listing.delete()

        messages.success(request, f"Updated item '{item.item_name}'!")
        return redirect("admin.pathways.detail", item.pathway.id)
