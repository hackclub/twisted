from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from twisted_site.models import (
    Pathway,
    PathwayTimeSpent,
    ShopItem,
    ShopItemRegionalPricing,
    ShopRegion,
    TemplateContext,
    User,
)

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
        pathways = list(Pathway.objects.order_by("start"))
        context["pathways"] = pathways

        # Load every pathway's participants in one query for the cards.
        participant_counts: dict[int, int] = {}
        qualified_users: dict[int, list[User]] = {}
        min_mins = {pathway.id: pathway.min_mins for pathway in pathways}
        for spent in PathwayTimeSpent.objects.select_related("user__profile"):
            participant_counts[spent.pathway_id] = participant_counts.get(spent.pathway_id, 0) + 1
            if spent.minutes >= min_mins.get(spent.pathway_id, 0):
                qualified_users.setdefault(spent.pathway_id, []).append(spent.user)
        for pathway in pathways:
            pathway.participant_count = participant_counts.get(pathway.id, 0)  # pyright: ignore[reportAttributeAccessIssue]
            pathway.qualified_users = qualified_users.get(pathway.id, [])  # pyright: ignore[reportAttributeAccessIssue]

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


@dataclass
class PathwayFields:
    name: str
    min_mins: int
    start: datetime
    end: datetime


def _pathway_form_values(request: HttpRequest) -> TemplateContext:
    """Return the raw pathway form fields, to re-fill the form after an error."""
    return {
        "pathway_name": request.POST.get("name"),
        "min_mins": request.POST.get("mins", "0"),
        # An empty date is None so the datepicker shows "Pick a date" again.
        "start_date": request.POST.get("startDate") or None,
        "start_time": request.POST.get("startTime"),
        "end_date": request.POST.get("endDate") or None,
        "end_time": request.POST.get("endTime"),
    }


def _pathway_initial_values(pathway: Pathway) -> TemplateContext:
    """Return a pathway's fields in the form's format, in the current timezone."""
    start = timezone.localtime(pathway.start)
    end = timezone.localtime(pathway.end)
    return {
        "pathway_name": pathway.name,
        "min_mins": pathway.min_mins,
        "start_date": start.strftime("%Y-%m-%d"),
        "start_time": start.strftime("%H:%M"),
        "end_date": end.strftime("%Y-%m-%d"),
        "end_time": end.strftime("%H:%M"),
    }


def _parse_local_datetime(date: str, time: str) -> datetime:
    naive = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")  # noqa: DTZ007
    return timezone.make_aware(naive, timezone.get_current_timezone())


def parse_pathway_form(request: HttpRequest) -> PathwayFields | str:
    """
    Validate the create/edit pathway form.

    Dates and times are read in the current (cookie) timezone, using that date's own
    UTC offset, so a pathway that spans a DST change still starts and ends on time.

    Returns:
        The parsed fields, or an error message.

    """
    values = _pathway_form_values(request)
    pathway_name = cast("str | None", values["pathway_name"])
    if pathway_name is None or pathway_name.strip() == "":
        return "No pathway name typed!"

    try:
        min_mins = int(cast("str", values["min_mins"]))
    except ValueError:
        return "Minimum minutes must be a whole number!"
    if min_mins <= 0:
        return "Minimum minutes must be greater than zero!"

    missing = {
        "start_date": "No start date selected!",
        "start_time": "No start time selected!",
        "end_date": "No end date selected!",
        "end_time": "No end time selected!",
    }
    for key, error in missing.items():
        if values[key] in (None, ""):
            return error

    try:
        start = _parse_local_datetime(values["start_date"], values["start_time"])
        end = _parse_local_datetime(values["end_date"], values["end_time"])
    except ValueError:
        return "Start and end must be valid dates and times!"

    if start >= end:
        return "Start must be before end!"

    return PathwayFields(name=pathway_name.strip(), min_mins=min_mins, start=start, end=end)


class PathwayCreateView(AdminView):
    def get(
        self,
        request: HttpRequest,
        error: str | None = None,
        extracontext: TemplateContext | None = None,
    ) -> HttpResponse:
        if self.perms.manage_pathways:
            self.allowed = True
        else:
            return HttpResponse("err")

        if extracontext is None:
            extracontext = {}

        context = self.get_context_data(page="pathways", subpage="create")
        # The datepickers bind these with `:value`, so they must exist (None = no date yet).
        context.update({"start_date": None, "end_date": None})
        context.update(extracontext)

        if error not in (None, ""):
            messages.error(request, error)

        return render(request, "admin/pathways/create.html", context=context)

    def post(self, request: HttpRequest) -> HttpResponse:
        if self.perms.manage_pathways:
            self.allowed = True
        else:
            return HttpResponse("err")

        fields = parse_pathway_form(request)
        if isinstance(fields, str):
            return self.get(request, fields, _pathway_form_values(request))

        _ = Pathway.objects.create(
            name=fields.name,
            min_mins=fields.min_mins,
            start=fields.start,
            end=fields.end,
        )

        messages.success(request, f'Successfully created Pathway for "{fields.name}"!')

        return redirect("admin.pathways")


class PathwayEditView(AdminView):
    def get(
        self,
        request: HttpRequest,
        pathway_id: int,
        error: str | None = None,
        extracontext: TemplateContext | None = None,
    ) -> HttpResponse:
        if self.perms.manage_pathways:
            self.allowed = True
        else:
            return HttpResponse("err")

        pathway = get_object_or_404(Pathway, id=pathway_id)
        context = self.get_context_data(page="pathways", subpage="edit")
        context["pathway"] = pathway
        context.update(extracontext if extracontext is not None else _pathway_initial_values(pathway))

        if error not in (None, ""):
            messages.error(request, error)

        return render(request, "admin/pathways/create.html", context=context)

    def post(self, request: HttpRequest, pathway_id: int) -> HttpResponse:
        if self.perms.manage_pathways:
            self.allowed = True
        else:
            return HttpResponse("err")

        pathway = get_object_or_404(Pathway, id=pathway_id)
        fields = parse_pathway_form(request)
        if isinstance(fields, str):
            return self.get(request, pathway_id, fields, _pathway_form_values(request))

        if not isinstance(self.audit_log.additional_context, dict):
            self.audit_log.additional_context = {}
        self.audit_log.additional_context["pathway"] = pathway.name
        self.audit_log.additional_context["before"] = {
            "name": pathway.name,
            "min_mins": pathway.min_mins,
            "start": pathway.start.isoformat(),
            "end": pathway.end.isoformat(),
        }
        self.audit_log.additional_context["after"] = {
            "name": fields.name,
            "min_mins": fields.min_mins,
            "start": fields.start.isoformat(),
            "end": fields.end.isoformat(),
        }

        pathway.name = fields.name
        pathway.min_mins = fields.min_mins
        pathway.start = fields.start
        pathway.end = fields.end
        pathway.save()

        messages.success(request, f'Updated pathway "{fields.name}"!')
        return redirect("admin.pathways.detail", pathway.id)


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
        golden_per_participant = dict(
            PathwayTimeSpent.objects.filter(pathway=pathway).values_list(
                "user_id",
                "golden_twists",
            ),
        )

        participants: list[dict[str, Any]] = [  # pyrefly: ignore[explicit-any]
            {
                "user": user,
                "mins": mins_per_participant[user.id],  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue]
                "golden_twists": golden_per_participant.get(user.id, 0),  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue]
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

        context["can_manage_pathways"] = self.perms.manage_pathways
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
                _ = ShopItemRegionalPricing.objects.create(
                    region=region,
                    item=shop_item,
                    price=price,
                )
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
