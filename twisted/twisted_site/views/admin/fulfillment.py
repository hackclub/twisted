from typing import cast

from django.contrib import messages
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from twisted_site.models import PathwayTimeSpent, Profile, ShopOrder, as_user
from twisted_site.slack import escape_mrkdwn, log_to_channel

from .admin import AdminView

ORDER_STATUS_FILTERS = ("all", "pending", "fulfilled", "rejected")


# Create your views here.
class FulfillmentView(AdminView):
    def get_context(self, request: HttpRequest) -> dict[str, object]:
        context = self.get_context_data(page="fulfillment")
        context = cast("dict[str, object]", context)
        status_filter = request.GET.get("status", "pending")
        if status_filter not in ORDER_STATUS_FILTERS:
            status_filter = "pending"
        orders = ShopOrder.objects.select_related("user", "item", "pathway").order_by(
            "-created_at",
        )
        if status_filter != "all":
            orders = orders.filter(status=status_filter)
        context["orders"] = orders
        context["status_filter"] = status_filter
        context["pending_count"] = ShopOrder.objects.filter(status="pending").count()
        return context

    def get(self, request: HttpRequest) -> HttpResponse:
        if self.perms.manage_fulfillments:
            self.allowed = True
        else:
            return HttpResponse("err")

        return render(request, "admin/fulfillment.html", context=self.get_context(request))

    def post(self, request: HttpRequest) -> HttpResponse:
        if self.perms.manage_fulfillments:
            self.allowed = True
        else:
            return HttpResponse("err")

        if not isinstance(self.audit_log.additional_context, dict):
            self.audit_log.additional_context = {}

        action = request.POST.get("action")
        if action not in ("fulfill", "reject"):
            messages.error(request, "Unknown fulfillment action.")
            return redirect("admin.fulfillment")

        try:
            order_pk = int(request.POST.get("order", ""))
        except ValueError:
            messages.error(request, "Select a valid order.")
            return redirect("admin.fulfillment")

        staff_note = request.POST.get("note", "").strip()

        with transaction.atomic():
            order = ShopOrder.objects.select_for_update().filter(id=order_pk).first()
            if order is None:
                messages.error(request, "That order does not exist.")
                return redirect("admin.fulfillment")
            if order.status != "pending":
                messages.error(request, f"Order #{order.id} is already {order.status}.")
                return redirect("admin.fulfillment")

            if action == "fulfill":
                order.status = "fulfilled"
            else:
                order.status = "rejected"
                item = order.item
                item.stock += 1
                item.save(update_fields=("stock",))
                time_spent, _ = PathwayTimeSpent.objects.select_for_update().get_or_create(
                    pathway=order.pathway,
                    user=order.user,
                    defaults={"minutes": 0, "unlocked": False, "golden_twists": 0},
                )
                maker_profile: Profile = as_user(order.user).profile
                time_spent.pathway.add_currency(maker_profile, order.price_paid, f"Refunded shop order for {order.item.item_name} (#{order.id})")
                time_spent.save(update_fields=("golden_twists",))

            order.staff_note = staff_note
            order.save(update_fields=("status", "staff_note"))

        self.audit_log.additional_context["action"] = f"order_{action}"
        self.audit_log.additional_context["order_id"] = order.id

        maker_name = as_user(order.user).profile.slack_username
        if action == "fulfill":
            messages.success(request, f"Order #{order.id} marked as fulfilled.")
            log_to_channel(
                f":package: Order *#{order.id}* (*{escape_mrkdwn(order.item.item_name)}* for *{escape_mrkdwn(maker_name)}*) "
                "was fulfilled!",
            )
        else:
            messages.success(
                request,
                f"Order #{order.id} rejected; {order.price_paid} golden twists refunded.",
            )
            log_to_channel(
                f":x: Order *#{order.id}* (*{escape_mrkdwn(order.item.item_name)}* for *{escape_mrkdwn(maker_name)}*) "
                "was rejected and refunded.",
            )

        return redirect("admin.fulfillment")
