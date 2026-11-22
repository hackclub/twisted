from datetime import UTC, datetime
from typing import override
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from twisted_site.models import (
    Pathway,
    PathwayTimeSpent,
    Profile,
    ProfileStaffPermissions,
    ShopItem,
    ShopItemRegionalPricing,
    ShopRegion,
)


class AdminWorkflowTests(TestCase):
    user: User  # pyright: ignore[reportUninitializedInstanceVariable]
    profile: Profile  # pyright: ignore[reportUninitializedInstanceVariable]
    permissions: ProfileStaffPermissions  # pyright: ignore[reportUninitializedInstanceVariable]

    @override
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="admin-workflow")
        self.permissions = ProfileStaffPermissions.objects.create(
            manage_pathways=True,
            view_pathways=True,
            view_review=True,
            manage_review=True,
            manage_shop=True,
        )
        self.profile = Profile.objects.create(
            user=self.user,
            is_staff=True,
            staff_permissions=self.permissions,
        )
        self.client = Client()
        self.client.force_login(self.user)

    def pathway_data(self) -> dict[str, str]:
        return {
            "name": "Browser Pathway",
            "mins": "300",
            "startDate": "2026-10-01",
            "startTime": "09:00",
            "endDate": "2026-10-08",
            "endTime": "17:00",
        }

    def test_pathway_can_be_created(self) -> None:
        response = self.client.post(reverse("admin.pathways.create"), self.pathway_data())

        self.assertRedirects(response, reverse("admin.pathways"))
        pathway = Pathway.objects.get(name="Browser Pathway")
        self.assertEqual(pathway.min_mins, 300)
        self.assertLess(pathway.start, pathway.end)

    def test_pathway_rejects_non_numeric_minutes(self) -> None:
        data = self.pathway_data()
        data["mins"] = "many"

        response = self.client.post(reverse("admin.pathways.create"), data)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Pathway.objects.exists())

    def test_pathway_rejects_malformed_dates(self) -> None:
        data = self.pathway_data()
        data["startDate"] = "not-a-date"

        response = self.client.post(reverse("admin.pathways.create"), data)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Pathway.objects.exists())

    def test_pathway_rejects_reversed_dates(self) -> None:
        data = self.pathway_data()
        data["startDate"], data["endDate"] = data["endDate"], data["startDate"]

        response = self.client.post(reverse("admin.pathways.create"), data)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Pathway.objects.exists())

    def make_pathway(self) -> Pathway:
        return Pathway.objects.create(
            name="Editable pathway",
            min_mins=60,
            start=datetime(2026, 10, 1, 9, tzinfo=UTC),
            end=datetime(2026, 10, 8, 17, tzinfo=UTC),
        )

    def test_pathway_dates_can_be_edited(self) -> None:
        pathway = self.make_pathway()
        edit_url = reverse("admin.pathways.edit", kwargs={"pathway_id": pathway.pk})

        response = self.client.get(edit_url)
        self.assertContains(response, "2026-10-01")
        self.assertContains(response, "09:00")

        response = self.client.post(
            edit_url,
            {
                "name": "Renamed pathway",
                "mins": "120",
                "startDate": "2026-11-02",
                "startTime": "08:30",
                "endDate": "2026-11-20",
                "endTime": "23:59",
            },
        )

        self.assertRedirects(
            response,
            reverse("admin.pathways.detail", kwargs={"pathway_id": pathway.pk}),
        )
        pathway.refresh_from_db()
        self.assertEqual(pathway.name, "Renamed pathway")
        self.assertEqual(pathway.min_mins, 120)
        self.assertEqual(pathway.start, datetime(2026, 11, 2, 8, 30, tzinfo=UTC))
        self.assertEqual(pathway.end, datetime(2026, 11, 20, 23, 59, tzinfo=UTC))

    def test_pathway_edit_uses_each_dates_own_utc_offset(self) -> None:
        pathway = self.make_pathway()
        self.client.cookies["django_timezone"] = "America/New_York"

        # New York is UTC-4 on Oct 20 and UTC-5 on Nov 20 (after DST ends).
        _ = self.client.post(
            reverse("admin.pathways.edit", kwargs={"pathway_id": pathway.pk}),
            {
                "name": pathway.name,
                "mins": "60",
                "startDate": "2026-10-20",
                "startTime": "09:00",
                "endDate": "2026-11-20",
                "endTime": "09:00",
            },
        )

        pathway.refresh_from_db()
        new_york = ZoneInfo("America/New_York")
        self.assertEqual(pathway.start, datetime(2026, 10, 20, 9, tzinfo=new_york))
        self.assertEqual(pathway.end, datetime(2026, 11, 20, 9, tzinfo=new_york))
        self.assertEqual(timezone.localtime(pathway.end, new_york).hour, 9)

    def test_pathway_edit_rejects_invalid_dates(self) -> None:
        pathway = self.make_pathway()
        data = self.pathway_data()
        data["startDate"], data["endDate"] = data["endDate"], data["startDate"]

        response = self.client.post(
            reverse("admin.pathways.edit", kwargs={"pathway_id": pathway.pk}),
            data,
        )

        self.assertContains(response, "Start must be before end!")
        pathway.refresh_from_db()
        self.assertEqual(pathway.name, "Editable pathway")
        self.assertEqual(pathway.start, datetime(2026, 10, 1, 9, tzinfo=UTC))

    def test_pathway_edit_requires_manage_pathways(self) -> None:
        self.permissions.manage_pathways = False
        self.permissions.save(update_fields=("manage_pathways",))
        pathway = self.make_pathway()
        edit_url = reverse("admin.pathways.edit", kwargs={"pathway_id": pathway.pk})

        self.assertRedirects(self.client.get(edit_url), reverse("admin.dash"))
        response = self.client.post(edit_url, self.pathway_data())

        self.assertRedirects(response, reverse("admin.dash"))
        pathway.refresh_from_db()
        self.assertEqual(pathway.name, "Editable pathway")
        detail = self.client.get(reverse("admin.pathways.detail", kwargs={"pathway_id": pathway.pk}))
        self.assertNotContains(detail, edit_url)

    def test_pathway_list_counts_participants_in_constant_queries(self) -> None:
        pathway = self.make_pathway()
        for index in range(5):
            user = User.objects.create_user(username=f"participant-{index}")
            _ = Profile.objects.create(user=user, slack_username=f"participant-{index}")
            _ = PathwayTimeSpent.objects.create(
                pathway=pathway,
                user=user,
                minutes=30 if index == 0 else 90,
            )

        with self.assertNumQueries(7):
            response = self.client.get(reverse("admin.pathways"))

        self.assertContains(response, "5 participants")
        self.assertContains(response, "4 qualified")

    def test_pathway_detail_can_create_shop_listing(self) -> None:
        pathway = Pathway.objects.create(
            name="Listing pathway",
            min_mins=60,
            start=datetime(2026, 10, 1, 9, tzinfo=UTC),
            end=datetime(2026, 10, 8, 17, tzinfo=UTC),
        )
        detail_url = reverse(
            "admin.pathways.detail",
            kwargs={"pathway_id": pathway.pk},
        )

        response = self.client.post(
            detail_url,
            {
                "action": "new_listing",
                "name": "Sticker",
                "description": "A sticker",
            },
        )

        self.assertRedirects(response, detail_url)
        item = ShopItem.objects.get(pathway=pathway, item_name="Sticker")
        self.assertEqual(item.stock, 999)

    def test_pathway_detail_listing_rejects_missing_fields(self) -> None:
        pathway = Pathway.objects.create(
            name="Invalid listing pathway",
            min_mins=60,
            start=datetime(2026, 10, 1, 9, tzinfo=UTC),
            end=datetime(2026, 10, 8, 17, tzinfo=UTC),
        )
        detail_url = reverse(
            "admin.pathways.detail",
            kwargs={"pathway_id": pathway.pk},
        )

        response = self.client.post(detail_url, {"action": "new_listing"})

        self.assertRedirects(response, detail_url, fetch_redirect_response=False)
        response = self.client.get(detail_url)
        self.assertContains(response, "Item name and description are required!")
        self.assertFalse(ShopItem.objects.filter(pathway=pathway).exists())

    def test_pathway_detail_listing_creation_requires_shop_permission(self) -> None:
        self.permissions.manage_shop = False
        self.permissions.save(update_fields=("manage_shop",))
        pathway = Pathway.objects.create(
            name="Protected listing pathway",
            min_mins=60,
            start=datetime(2026, 10, 1, 9, tzinfo=UTC),
            end=datetime(2026, 10, 8, 17, tzinfo=UTC),
        )

        response = self.client.post(
            reverse("admin.pathways.detail", kwargs={"pathway_id": pathway.pk}),
            {
                "action": "new_listing",
                "name": "Unauthorized",
                "description": "Should not be created",
            },
        )

        self.assertRedirects(response, reverse("admin.dash"))
        self.assertFalse(ShopItem.objects.exists())

    def test_invalid_shop_listing_returns_not_found(self) -> None:
        response = self.client.get(
            reverse("admin.pathways.shopitems", kwargs={"listing_id": 999}),
        )

        self.assertEqual(response.status_code, 404)

    def test_shop_listing_detail_requires_pathway_view_permission(self) -> None:
        pathway = Pathway.objects.create(
            name="Visible listing pathway",
            min_mins=60,
            start=datetime(2026, 10, 1, 9, tzinfo=UTC),
            end=datetime(2026, 10, 8, 17, tzinfo=UTC),
        )
        item = ShopItem.objects.create(
            pathway=pathway,
            item_name="Visible item",
            item_description="Description",
        )
        detail_url = reverse(
            "admin.pathways.shopitems",
            kwargs={"listing_id": item.pk},
        )

        visible_response = self.client.get(detail_url)
        self.permissions.view_pathways = False
        self.permissions.save(update_fields=("view_pathways",))
        denied_response = self.client.get(detail_url)

        self.assertEqual(visible_response.status_code, 200)
        self.assertRedirects(denied_response, reverse("admin.dash"))

    def test_shop_region_can_be_created(self) -> None:
        response = self.client.post(
            reverse("admin.shop.regions"),
            {"action": "create", "name": "Europe"},
        )

        self.assertRedirects(response, reverse("admin.shop.regions"))
        self.assertTrue(ShopRegion.objects.filter(name="Europe").exists())

    def test_shop_region_can_be_renamed(self) -> None:
        region = ShopRegion.objects.create(name="Old name")

        response = self.client.post(
            reverse("admin.shop.regions"),
            {"action": "update", "region_id": region.pk, "name": "New name"},
        )

        self.assertRedirects(response, reverse("admin.shop.regions"))
        region.refresh_from_db()
        self.assertEqual(region.name, "New name")

    def test_unused_shop_region_can_be_deleted(self) -> None:
        region = ShopRegion.objects.create(name="Temporary")

        response = self.client.post(
            reverse("admin.shop.regions"),
            {"action": "delete", "region_id": region.pk},
        )

        self.assertRedirects(response, reverse("admin.shop.regions"))
        self.assertFalse(ShopRegion.objects.filter(pk=region.pk).exists())

    def test_region_with_shop_pricing_cannot_be_deleted(self) -> None:
        region = ShopRegion.objects.create(name="Protected")
        pathway = Pathway.objects.create(
            name="Shop pathway",
            min_mins=60,
            start=datetime(2026, 10, 1, 9, tzinfo=UTC),
            end=datetime(2026, 10, 8, 17, tzinfo=UTC),
        )
        item = ShopItem.objects.create(
            pathway=pathway,
            item_name="Sticker",
            item_description="Sticker",
        )
        _ = ShopItemRegionalPricing.objects.create(region=region, item=item, price=5)

        response = self.client.post(
            reverse("admin.shop.regions"),
            {"action": "delete", "region_id": region.pk},
        )

        self.assertRedirects(response, reverse("admin.shop.regions"))
        self.assertTrue(ShopRegion.objects.filter(pk=region.pk).exists())

    def test_shop_region_creation_requires_permission(self) -> None:
        self.permissions.manage_shop = False
        self.permissions.save(update_fields=("manage_shop",))

        response = self.client.post(
            reverse("admin.shop.regions"),
            {"action": "create", "name": "Unauthorized"},
        )

        self.assertRedirects(response, reverse("admin.dash"))
        self.assertFalse(ShopRegion.objects.exists())

    def test_empty_shop_region_is_rejected(self) -> None:
        response = self.client.post(
            reverse("admin.shop.regions"),
            {"action": "create", "name": "  "},
        )

        self.assertRedirects(response, reverse("admin.shop.regions"))
        self.assertFalse(ShopRegion.objects.exists())

    def test_shop_region_update_requires_a_valid_region_id(self) -> None:
        response = self.client.post(
            reverse("admin.shop.regions"),
            {"action": "update", "name": "New name"},
        )

        self.assertRedirects(response, reverse("admin.shop.regions"))

    def test_shop_region_delete_requires_a_valid_region_id(self) -> None:
        response = self.client.post(
            reverse("admin.shop.regions"),
            {"action": "delete"},
        )

        self.assertRedirects(response, reverse("admin.shop.regions"))
