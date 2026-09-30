from datetime import timedelta
from typing import cast, override
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from twisted_site.models import (
    Journal,
    Pathway,
    PathwayTimeSpent,
    Profile,
    ProfileStaffPermissions,
    Project,
    ShopItem,
    ShopItemRegionalPricing,
    ShopOrder,
    ShopRegion,
)


def make_pathway(name: str = "Economy Pathway") -> Pathway:
    now = timezone.now()
    return Pathway.objects.create(
        name=name,
        min_mins=60,
        start=now - timedelta(days=1),
        end=now + timedelta(days=7),
    )


def make_journal(project: Project, minutes: int) -> Journal:
    return Journal.objects.create(
        project=project,
        type="untracked",
        content="x" * 250,
        minutes_worked=minutes,
        reduced_minutes=minutes,
    )


class TwistEarningTests(TestCase):
    user: User  # pyright: ignore[reportUninitializedInstanceVariable]
    profile: Profile  # pyright: ignore[reportUninitializedInstanceVariable]
    project: Project  # pyright: ignore[reportUninitializedInstanceVariable]

    @override
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="earner")
        self.profile = Profile.objects.create(user=self.user)
        self.project = Project.objects.create(
            user=self.user,
            project_name="Earning",
            project_description="x",
            project_type="hardware",
        )

    def test_twists_accrue_at_fifty_per_hour(self) -> None:
        _ = make_journal(self.project, 120)

        self.assertEqual(self.profile.twists_earned(), 100)
        self.assertEqual(self.profile.refresh_twists(), 100)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.twists, 100)

    def test_deleted_journals_reduce_earnings(self) -> None:
        journal = make_journal(self.project, 60)
        self.assertEqual(self.profile.refresh_twists(), 50)

        _ = journal.delete()

        self.assertEqual(self.profile.refresh_twists(), 0)


class DepositTests(TestCase):
    user: User  # pyright: ignore[reportUninitializedInstanceVariable]
    profile: Profile  # pyright: ignore[reportUninitializedInstanceVariable]
    project: Project  # pyright: ignore[reportUninitializedInstanceVariable]
    pathway: Pathway  # pyright: ignore[reportUninitializedInstanceVariable]

    @override
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="depositor")
        self.profile = Profile.objects.create(user=self.user)
        self.project = Project.objects.create(
            user=self.user,
            project_name="Deposit source",
            project_description="x",
            project_type="hardware",
        )
        _ = make_journal(self.project, 120)
        self.pathway = make_pathway()
        _ = PathwayTimeSpent.objects.create(
            pathway=self.pathway,
            user=self.user,
            unlocked=True,
            minutes=60,
        )
        _ = self.profile.refresh_twists()
        self.client = Client()
        self.client.force_login(self.user)

    def deposit_url(self) -> str:
        return reverse("fr.shop")

    def post_deposit(self, amount: object) -> None:
        _ = self.client.post(
            self.deposit_url(),
            {"action": "deposit", "pathway": self.pathway.pk, "amount": amount},
        )

    def test_deposit_converts_twists_one_to_one(self) -> None:
        self.post_deposit(30)

        self.profile.refresh_from_db()
        time_spent = PathwayTimeSpent.objects.get(pathway=self.pathway, user=self.user)
        self.assertEqual(self.profile.twists, 70)
        self.assertEqual(time_spent.golden_twists, 30)

    def test_deposit_rejects_invalid_amounts(self) -> None:
        for amount in ("0", "-5", "abc", "", "1000"):
            with self.subTest(amount=amount):
                self.post_deposit(amount)

        self.profile.refresh_from_db()
        time_spent = PathwayTimeSpent.objects.get(pathway=self.pathway, user=self.user)
        self.assertEqual(self.profile.twists, 100)
        self.assertEqual(time_spent.golden_twists, 0)

    def test_deposit_requires_an_unlocked_pathway(self) -> None:
        locked = make_pathway("Locked Pathway")

        _ = self.client.post(
            self.deposit_url(),
            {"action": "deposit", "pathway": locked.pk, "amount": 10},
        )

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.twists, 100)
        self.assertFalse(
            PathwayTimeSpent.objects.filter(pathway=locked, user=self.user).exists(),
        )


class PurchaseTests(TestCase):
    user: User  # pyright: ignore[reportUninitializedInstanceVariable]
    profile: Profile  # pyright: ignore[reportUninitializedInstanceVariable]
    pathway: Pathway  # pyright: ignore[reportUninitializedInstanceVariable]
    region: ShopRegion  # pyright: ignore[reportUninitializedInstanceVariable]
    item: ShopItem  # pyright: ignore[reportUninitializedInstanceVariable]

    @override
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="buyer")
        self.profile = Profile.objects.create(user=self.user)
        project = Project.objects.create(
            user=self.user,
            project_name="Buying power",
            project_description="x",
            project_type="hardware",
        )
        _ = make_journal(project, 240)
        self.pathway = make_pathway()
        _ = PathwayTimeSpent.objects.create(
            pathway=self.pathway,
            user=self.user,
            unlocked=True,
            minutes=60,
            golden_twists=0,
        )
        self.region = ShopRegion.objects.create(name="Test Region")
        self.profile.region = self.region
        self.profile.save(update_fields=("region",))
        self.item = ShopItem.objects.create(
            pathway=self.pathway,
            item_name="Sticker Pack",
            item_description="Cool stickers",
            stock=2,
        )
        _ = ShopItemRegionalPricing.objects.create(
            region=self.region,
            item=self.item,
            price=25,
        )
        _ = self.profile.refresh_twists()
        self.client = Client()
        self.client.force_login(self.user)

    def post_purchase(self, item_pk: object = None) -> None:
        _ = self.client.post(
            reverse("fr.shop"),
            {
                "action": "purchase",
                "pathway": self.pathway.pk,
                "item": self.item.pk if item_pk is None else item_pk,
            },
        )

    def balances(self) -> tuple[int, int, int]:
        self.profile.refresh_from_db()
        self.item.refresh_from_db()
        time_spent = PathwayTimeSpent.objects.get(pathway=self.pathway, user=self.user)
        return (
            cast("int", self.profile.twists),  # pyrefly: ignore[redundant-cast]
            cast("int", time_spent.golden_twists),  # pyrefly: ignore[redundant-cast]
            cast("int", self.item.stock),  # pyrefly: ignore[redundant-cast]
        )

    def test_purchase_creates_order_and_moves_currency(self) -> None:
        _ = self.client.post(
            reverse("fr.shop"),
            {"action": "deposit", "pathway": self.pathway.pk, "amount": 100},
        )
        with patch("twisted_site.views.client.shop.log_to_channel") as log_to_channel:
            self.post_purchase()

        twists, golden, stock = self.balances()
        order = ShopOrder.objects.get(user=self.user, item=self.item)
        self.assertEqual(order.status, "pending")
        self.assertEqual(order.price_paid, 25)
        self.assertEqual(order.region_name, "Test Region")
        self.assertEqual(order.pathway, self.pathway)
        self.assertEqual((twists, golden, stock), (100, 75, 1))
        log_to_channel.assert_called_once()

    def test_purchase_requires_deposited_golden_twists(self) -> None:
        with patch("twisted_site.views.client.shop.log_to_channel") as log_to_channel:
            self.post_purchase()

        twists, golden, stock = self.balances()
        self.assertEqual((twists, golden, stock), (200, 0, 2))
        self.assertFalse(ShopOrder.objects.exists())
        log_to_channel.assert_not_called()

    def test_purchase_fails_when_out_of_stock(self) -> None:
        _ = self.client.post(
            reverse("fr.shop"),
            {"action": "deposit", "pathway": self.pathway.pk, "amount": 200},
        )
        self.item.stock = 0
        self.item.save(update_fields=("stock",))

        self.post_purchase()

        twists, golden, stock = self.balances()
        self.assertEqual((twists, golden, stock), (0, 200, 0))
        self.assertFalse(ShopOrder.objects.exists())

    def test_purchase_requires_a_regional_price(self) -> None:
        other_region = ShopRegion.objects.create(name="Other Region")
        self.profile.region = other_region
        self.profile.save(update_fields=("region",))
        _ = self.client.post(
            reverse("fr.shop"),
            {"action": "deposit", "pathway": self.pathway.pk, "amount": 200},
        )

        self.post_purchase()

        self.assertFalse(ShopOrder.objects.exists())
        self.assertEqual(
            PathwayTimeSpent.objects.get(pathway=self.pathway, user=self.user).golden_twists,
            200,
        )

    def test_second_purchase_can_exhaust_stock(self) -> None:
        _ = self.client.post(
            reverse("fr.shop"),
            {"action": "deposit", "pathway": self.pathway.pk, "amount": 200},
        )
        with patch("twisted_site.views.client.shop.log_to_channel"):
            self.post_purchase()
            self.item.stock = 1
            self.item.save(update_fields=("stock",))
            self.post_purchase()
            self.post_purchase()

        self.assertEqual(ShopOrder.objects.filter(user=self.user).count(), 2)
        _, _, stock = self.balances()
        self.assertEqual(stock, 0)

    def test_purchase_of_other_pathway_item_is_rejected(self) -> None:
        other_pathway = make_pathway("Other Pathway")
        other_item = ShopItem.objects.create(
            pathway=other_pathway,
            item_name="Wrong Shop Item",
            item_description="x",
            stock=5,
        )
        _ = self.client.post(
            reverse("fr.shop"),
            {"action": "deposit", "pathway": self.pathway.pk, "amount": 200},
        )

        self.post_purchase(item_pk=other_item.pk)

        self.assertFalse(ShopOrder.objects.exists())


class FulfillmentTests(TestCase):
    staff: User  # pyright: ignore[reportUninitializedInstanceVariable]
    maker: User  # pyright: ignore[reportUninitializedInstanceVariable]
    maker_profile: Profile  # pyright: ignore[reportUninitializedInstanceVariable]
    order: ShopOrder  # pyright: ignore[reportUninitializedInstanceVariable]
    item: ShopItem  # pyright: ignore[reportUninitializedInstanceVariable]
    pathway: Pathway  # pyright: ignore[reportUninitializedInstanceVariable]

    @override
    def setUp(self) -> None:
        self.staff = User.objects.create_user(username="fulfiller")
        permissions = ProfileStaffPermissions.objects.create(manage_fulfillments=True)
        _ = Profile.objects.create(
            user=self.staff,
            is_staff=True,
            staff_permissions=permissions,
        )
        self.maker = User.objects.create_user(username="order-maker")
        self.maker_profile = Profile.objects.create(user=self.maker, slack_username="Maker")
        project = Project.objects.create(
            user=self.maker,
            project_name="Order funds",
            project_description="x",
            project_type="hardware",
        )
        _ = make_journal(project, 120)
        self.pathway = make_pathway()
        _ = PathwayTimeSpent.objects.create(
            pathway=self.pathway,
            user=self.maker,
            unlocked=True,
            minutes=60,
            golden_twists=70,
        )
        self.maker_profile.twists = 30
        self.maker_profile.save(update_fields=("twists",))
        self.item = ShopItem.objects.create(
            pathway=self.pathway,
            item_name="T-shirt",
            item_description="A shirt",
            stock=4,
        )
        self.order = ShopOrder.objects.create(
            user=self.maker,
            item=self.item,
            pathway=self.pathway,
            region_name="Test Region",
            price_paid=30,
        )
        self.client = Client()
        self.client.force_login(self.staff)

    def fulfillment_url(self) -> str:
        return reverse("admin.fulfillment")

    def test_fulfillment_queue_lists_pending_orders(self) -> None:
        response = self.client.get(self.fulfillment_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "T-shirt")
        self.assertContains(response, "Maker")

    def test_non_staff_cannot_open_fulfillment(self) -> None:
        self.client.force_login(self.maker)

        response = self.client.get(self.fulfillment_url())

        self.assertRedirects(response, reverse("dashboard"))

    def test_fulfill_marks_order_done(self) -> None:
        with patch("twisted_site.views.admin.fulfillment.log_to_channel") as log_to_channel:
            response = self.client.post(
                self.fulfillment_url(),
                {"action": "fulfill", "order": self.order.pk, "note": "Shipped!"},
            )

        self.assertRedirects(response, self.fulfillment_url())
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "fulfilled")
        self.assertEqual(self.order.staff_note, "Shipped!")
        log_to_channel.assert_called_once()

    def test_reject_refunds_golden_twists_and_restores_stock(self) -> None:
        with patch("twisted_site.views.admin.fulfillment.log_to_channel"):
            response = self.client.post(
                self.fulfillment_url(),
                {"action": "reject", "order": self.order.pk, "note": "Out of stock"},
            )

        self.assertRedirects(response, self.fulfillment_url())
        self.order.refresh_from_db()
        self.item.refresh_from_db()
        self.maker_profile.refresh_from_db()
        time_spent = PathwayTimeSpent.objects.get(pathway=self.pathway, user=self.maker)
        self.assertEqual(self.order.status, "rejected")
        self.assertEqual(self.item.stock, 5)
        self.assertEqual(time_spent.golden_twists, 100)
        self.assertEqual(self.maker_profile.twists, 0)

    def test_completed_order_cannot_be_actioned_twice(self) -> None:
        with patch("twisted_site.views.admin.fulfillment.log_to_channel"):
            _ = self.client.post(
                self.fulfillment_url(),
                {"action": "fulfill", "order": self.order.pk},
            )

            response = self.client.post(
                self.fulfillment_url(),
                {"action": "reject", "order": self.order.pk},
            )

        self.assertRedirects(response, self.fulfillment_url())
        self.order.refresh_from_db()
        self.item.refresh_from_db()
        self.assertEqual(self.order.status, "fulfilled")
        self.assertEqual(self.item.stock, 4)
