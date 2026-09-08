from .views.client.auth import (
    LoginView,
    AuthCallbackView,
    HackatimeCallbackView,
    LogoutView,
)
from django.urls import path
from .views import client
from .views import admin
from .views.image_upload import upload_file
from .views.ari import AriView

urlpatterns = [
    path("", view=client.HomepageView.as_view(), name="homepage"),
    path("faqs/", view=client.FaqsView.as_view(), name="faqs"),
    path("api/upload_image/", upload_file, name="misc.upload_file"),
    path("api/ari/", AriView.as_view(), name="ari"),
    path("auth/login/", LoginView.as_view(), name="login"),
    path("oauth/callback/", AuthCallbackView.as_view(), name="auth_callback"),
    path(
        "oauth/hackatime_callback/",
        HackatimeCallbackView.as_view(),
        name="auth_callback",
    ),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path("dashboard/", client.DashboardView.as_view(), name="dashboard"),
    path(
        "dashboard/frame/projects/", client.ListProjects.as_view(), name="fr.projects"
    ),
    path(
        "dashboard/frame/projects/create/",
        client.CreateProject.as_view(),
        name="fr.projects.create",
    ),
    path(
        "dashboard/frame/projects/<int:id>/",
        client.ProjectDetail.as_view(),
        name="fr.projects.detail",
    ),
    path(
        "dashboard/frame/projects/ship/<int:id>/",
        client.SubmitProject.as_view(),
        name="fr.projects.ship",
    ),
    path(
        "dashboard/frame/projects/<int:id>/settings/",
        client.ProjectSettings.as_view(),
        name="fr.projects.settings",
    ),
    path(
        "dashboard/frame/projects/<int:id>/journals/new/hackatime/",
        client.NewProjectHackatimeJournal.as_view(),
        name="fr.projects.journals.new.hackatime",
    ),
    path(
        "dashboard/frame/projects/<int:id>/journals/new/untracked/",
        client.NewProjectUntrackedJournal.as_view(),
        name="fr.projects.journals.new.untracked",
    ),
    path(
        "dashboard/frame/journals/delete/<int:id>/",
        client.DeleteJournal.as_view(),
        name="fr.projects.journals.delete",
    ),
    path(
        "dashboard/frame/pathways/", client.PathwaysView.as_view(), name="fr.pathways"
    ),
    path(
        "dashboard/frame/referrals/",
        client.ReferralsView.as_view(),
        name="fr.referrals",
    ),
    path(
        "dashboard/frame/discover/", client.DiscoverView.as_view(), name="fr.discover"
    ),
    path("admin/", admin.DashboardView.as_view(), name="admin.dash"),
    path("admin/users/", admin.UsersView.as_view(), name="admin.users"),
    path(
        "admin/users/<int:id>/",
        admin.UserDetailView.as_view(),
        name="admin.users.detail",
    ),
    path("admin/pathways/", admin.PathwayListView.as_view(), name="admin.pathways"),
    path(
        "admin/pathways/<int:id>",
        admin.PathwayDetailView.as_view(),
        name="admin.pathways.detail",
    ),
    path(
        "admin/pathways/new/",
        admin.PathwayCreateView.as_view(),
        name="admin.pathways.create",
    ),
    path(
        "admin/fulfillment/", admin.FulfillmentView.as_view(), name="admin.fulfillment"
    ),
    path("admin/shop/", admin.ShopView.as_view(), name="admin.shop"),
    path("admin/review/", admin.ReviewView.as_view(), name="admin.review"),
    path(
        "admin/announcements/",
        admin.AnnouncementsView.as_view(),
        name="admin.announcements",
    ),
    path("admin/logs/", admin.AuditLogsView.as_view(), name="admin.logs"),
]
