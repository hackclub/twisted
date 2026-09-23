from datetime import UTC, datetime
from typing import override

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from twisted_site.models import (
    Pathway,
    Profile,
    ProfileStaffPermissions,
    Project,
    ProjectShip,
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
        self.assertTrue(
            ShopItem.objects.filter(pathway=pathway, item_name="Sticker").exists(),
        )

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

    @override_settings(DEBUG_REVIEW=True)
    def test_debug_review_updates_ship_fields(self) -> None:
        user = User.objects.create_user(username="reviewed-maker")
        _ = Profile.objects.create(user=user)
        project = Project.objects.create(
            user=user,
            project_name="Review project",
            project_description="Description",
            project_type="software",
        )
        ship = ProjectShip.objects.create(project=project)

        response = self.client.post(
            reverse("admin.review"),
            {
                "id": ship.pk,
                "status": "approved",
                "note_to_maker": "Looks good",
                "audit_note": "Verified",
                "technical_features": "Canvas",
                "deflation_reason": "None",
                "final_status": "approved",
                "final_note_to_maker": "Final approval",
                "final_audit_note": "Complete",
            },
        )

        self.assertRedirects(response, reverse("admin.review"))
        ship.refresh_from_db()
        self.assertEqual(ship.status, "approved")
        self.assertEqual(ship.final_status, "approved")
        self.assertEqual(ship.final_note_to_maker, "Final approval")

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
