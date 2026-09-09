from typing import TYPE_CHECKING, Any, cast, override

from django.contrib.auth import get_user_model
from django.contrib.auth.base_user import AbstractBaseUser
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import TextField
from django.utils import timezone

from . import hackatime

if TYPE_CHECKING:
    from datetime import datetime

User = get_user_model()

#: Template context dictionaries mix value types by design (mirroring
#: `django.shortcuts.render`), so they are typed loosely.
TemplateContext = dict[str, Any]  # pyrefly: ignore[explicit-any]


class UploadedFile(models.Model):
    uploaded_by = models.ForeignKey(User, on_delete=models.PROTECT)
    link = models.CharField(max_length=500)
    cdn_response = models.JSONField()
    uploaded_thru = models.CharField(max_length=500)
    filesize = models.IntegerField()

    @override
    def __str__(self) -> str:
        return (
            f"{self.cdn_response['filename']} uploaded by {self.uploaded_by.profile.slack_username}"  # pyrefly: ignore[missing-attribute]
        )


# Create your models here.
class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    verification_status = models.CharField(max_length=64, blank=True, default="")
    ysws_eligible = models.BooleanField(default=False)
    slack_id = models.CharField(max_length=64, blank=True, default="")
    slack_username = models.CharField(max_length=64, blank=True, default="")
    slack_pfp_url = models.CharField(max_length=200, blank=True, default="")

    hackatime_access_token = models.CharField(max_length=2000, blank=True, default="")
    hackatime_state = models.CharField(max_length=100, blank=True, default="")

    hca_access_token = models.CharField(max_length=2000, blank=True, default="")

    is_allowed = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
    staff_permissions = models.OneToOneField(
        "twisted_site.ProfileStaffPermissions",
        on_delete=models.PROTECT,
        default=None,
        null=True,
    )

    twists = models.IntegerField(default=0)

    referred_by = models.ForeignKey(
        "twisted_site.Profile",
        on_delete=models.PROTECT,
        null=True,
        default=None,
        related_name="referrals",
    )
    my_referral_code = models.CharField(max_length=200, blank=True, default="")

    def shipped_projects(self) -> list["Project"]:
        shipped_projects: list[Project] = []
        for project in cast("list[Project]", self.user.projects.all()):  # pyrefly: ignore[missing-attribute]
            if project.is_shipped():
                shipped_projects.append(project)
        return shipped_projects

    def time_logged(self) -> int:
        time_logged = 0
        for project in cast("list[Project]", self.user.projects.all()):  # pyrefly: ignore[missing-attribute]
            time_logged += project.time_logged()
        return time_logged

    def time_shipped(self) -> int:
        time_shipped = 0
        for project in self.shipped_projects():
            time_shipped += project.time_logged()
        return time_shipped

    @override
    def __str__(self) -> str:
        return cast("str", self.user.username)  # pyrefly: ignore[missing-attribute]


class ProfileStaffPermissions(models.Model):
    superuser = models.BooleanField(default=False)

    view_users = models.BooleanField(default=False)

    view_pathways = models.BooleanField(default=False)
    manage_pathways = models.BooleanField(default=False)

    manage_fulfillments = models.BooleanField(default=False)

    manage_shop = models.BooleanField(default=False)

    view_review = models.BooleanField(default=False)
    manage_review = models.BooleanField(default=False)

    manage_announcements = models.BooleanField(default=False)

    view_auditlogs = models.BooleanField(default=False)


PROJECT_TYPE_CHOICES = {"software": "Software", "hardware": "Hardware"}


class Project(models.Model):
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="projects")

    project_name = models.CharField(max_length=50)
    project_description = models.TextField(max_length=2000)

    project_type = models.CharField(choices=PROJECT_TYPE_CHOICES, max_length=100)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    hackatime_project_name = models.CharField(max_length=200, blank=True, default="")
    repo_url = models.CharField(max_length=200, blank=True, default="")
    playable_url = models.CharField(max_length=200, blank=True, default="")
    screenshot_url = models.CharField(max_length=500, blank=True, default="")

    @override
    def __str__(self) -> str:
        return cast("str", self.project_name)  # pyrefly: ignore[redundant-cast]

    def get_hackatime_project(self) -> hackatime.HackatimeProject | None:
        if self.hackatime_project_name == "":
            return None
        projects = hackatime.projects(self.user.profile.hackatime_access_token)  # pyrefly: ignore[missing-attribute]
        for project in projects:
            if project.name == self.hackatime_project_name:
                return project
        return None

    def time_logged(self, include_all_minutes: bool = False) -> int:
        minutes = 0
        for journal in self.journals.all():  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue] # pyrefly: ignore[missing-attribute]
            if include_all_minutes:
                # django-orm-lens-disable-next-line DOL007
                minutes += cast("int", journal.minutes_worked)
            else:
                minutes += cast("int", journal.reduced_minutes)
        return minutes

    def hackatime_logged(self, include_all_minutes: bool = False) -> int:
        minutes = 0
        for journal in self.journals.all():  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue] # pyrefly: ignore[missing-attribute]
            if journal.type != "hackatime":
                continue
            if include_all_minutes:
                # django-orm-lens-disable-next-line DOL007
                minutes += cast("int", journal.minutes_worked)
            else:
                minutes += cast("int", journal.reduced_minutes)
        return minutes

    def time_spent(self) -> int:
        project = self.get_hackatime_project()
        if project is None:
            return 0
        return project.total_seconds // 60

    def hackatime_time_unjournaled(self) -> int:
        return self.time_spent() - self.hackatime_logged(include_all_minutes=True)

    def latest_ship(self) -> "ProjectShip | None":
        ship = self.ships.order_by("-created_at").first()  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue] # pyrefly: ignore[missing-attribute]
        return cast("ProjectShip | None", ship)

    def is_shipped(self) -> bool:
        latest_ship = self.latest_ship()
        if latest_ship is None:
            return False
        return cast("bool", latest_ship.status != "requested_changes")  # pyrefly: ignore[redundant-cast]

    def is_approved(self) -> bool:
        latest_ship = self.latest_ship()
        if latest_ship is None:
            return False
        return cast("bool", latest_ship.status == "approved")  # pyrefly: ignore[redundant-cast]


JOURNAL_TYPES = {
    "hackatime": "Hackatime",
    "lookout": "Lookout",
    "untracked": "Untracked",
}


class Journal(models.Model):
    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="journals")
    type = models.CharField(max_length=100, choices=JOURNAL_TYPES)

    content = TextField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    minutes_worked = models.IntegerField(validators=[MinValueValidator(0)])
    reduced_minutes = models.IntegerField(validators=[MinValueValidator(0)])

    @override
    def __str__(self) -> str:
        return f"{self.reduced_minutes} mins on {self.project}"


PROJECT_SHIP_STATUSES = {
    "pending": "Awaiting review",
    "requested_changes": "Changes Requested",
    "rejected": "Rejected",
    "approved": "Approved",
}


class ProjectShip(models.Model):
    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="ships")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    status = models.CharField(default="pending", choices=PROJECT_SHIP_STATUSES, max_length=200)

    note_to_maker = models.TextField(blank=True, default="")
    audit_note = models.TextField(blank=True, default="")
    technical_features = models.CharField(blank=True, default="", max_length=255)
    deflation_reason = models.CharField(blank=True, default="", max_length=255)

    final_status = models.CharField(
        default="pending",
        choices=PROJECT_SHIP_STATUSES,
        max_length=200,
    )
    final_note_to_maker = models.TextField(blank=True, default="")
    final_audit_note = models.TextField(blank=True, default="")

    @override
    def __str__(self) -> str:
        return f"Ship created at {self.created_at} ({self.get_status_display()})"  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue]


class Pathway(models.Model):
    start = models.DateTimeField()
    end = models.DateTimeField()

    name = models.CharField(max_length=200)
    min_mins = models.IntegerField(default=300)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def ended(self) -> bool:
        return timezone.now() > cast("datetime", self.end)  # pyrefly: ignore[redundant-cast]

    def didnt_start(self) -> bool:
        return cast("datetime", self.start) > timezone.now()  # pyrefly: ignore[redundant-cast]

    def in_progress(self) -> bool:
        return not self.ended() and not self.didnt_start()

    def status(self) -> str | None:
        if self.ended():
            return "ended"
        if self.didnt_start():
            return "awaiting"
        if self.in_progress():
            return "in progress"
        return None

    def mins_spent(self, user: AbstractBaseUser) -> int:
        pathways = Pathway.objects.order_by("start").values("id", "start", "end", "min_mins")
        if not pathways.exists():
            return 0

        pathway_totals: dict[int, int] = {p["id"]: 0 for p in pathways}

        journals = (
            Journal.objects.filter(project__user=user)
            .order_by("created_at")
            .values_list("created_at", "reduced_minutes")
        )

        for j_created, j_mins in journals:
            mins_remaining = cast("int", j_mins)
            for pathway in pathways:
                if mins_remaining <= 0:
                    break

                # Check if journal falls within the pathway window
                if pathway["start"] > j_created or pathway["end"] < j_created:
                    continue

                p_id = cast("int", pathway["id"])
                mins_completed = pathway_totals.get(p_id, 0)
                mins_required = cast("int", pathway["min_mins"])

                if mins_completed >= mins_required:
                    continue

                mins_needed = mins_required - mins_completed
                mins_donated = min(mins_remaining, mins_needed)

                mins_remaining -= mins_donated
                pathway_totals[p_id] = mins_completed + mins_donated

        return pathway_totals[self.id]  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue]

    def mins_spent_per_participant(self) -> dict[int, int]:
        """
        Calculates the minutes spent on this specific pathway for all participants.

        Returns:
            dict: {user_id: mins_spent}

        """
        # Fetch all pathways to accurately model the sequential time donation
        pathways = list(Pathway.objects.order_by("start").values("id", "start", "end", "min_mins"))
        if len(pathways) == 0:
            return {}

        # Fetch journals from all users that fit within this pathway's active time frame
        journals = (
            Journal.objects.filter(
                created_at__gte=self.start,
                created_at__lte=self.end,
                reduced_minutes__gt=0,
            )
            .order_by("project__user_id", "created_at")
            .values_list("project__user_id", "created_at", "reduced_minutes")
        )

        user_pathway_totals: dict[int, dict[int, int]] = {}

        for user_id, j_created, j_mins in journals:
            if user_id not in user_pathway_totals:
                user_pathway_totals[user_id] = {p["id"]: 0 for p in pathways}

            pathway_totals = user_pathway_totals[user_id]
            mins_remaining = cast("int", j_mins)

            for pathway in pathways:
                if mins_remaining <= 0:
                    break

                if pathway["start"] > j_created or pathway["end"] < j_created:
                    continue

                p_id = cast("int", pathway["id"])
                mins_completed = pathway_totals[p_id]
                mins_required = cast("int", pathway["min_mins"])

                if mins_completed >= mins_required:
                    continue

                mins_needed = mins_required - mins_completed
                mins_donated = min(mins_remaining, mins_needed)

                mins_remaining -= mins_donated
                pathway_totals[p_id] += mins_donated

        # Extract only this pathway's result for each participant
        return {
            user_id: totals.get(self.id, 0)  # ty:ignore[unresolved-attribute] # pyright: ignore[reportAttributeAccessIssue]
            for user_id, totals in user_pathway_totals.items()
        }

    def qualified_participants(self) -> list[AbstractBaseUser]:
        per_part = self.mins_spent_per_participant()
        qualified: list[AbstractBaseUser] = []
        for userid, mins in per_part.items():
            if mins >= self.min_mins:
                qualified.append(User.objects.get(id=userid))
        return qualified

    @override
    def __str__(self) -> str:
        return cast("str", self.name)  # pyrefly: ignore[redundant-cast]


class AuditLog(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="audit_logs")
    path = models.CharField(max_length=400)
    post = models.BooleanField()
    pii = models.BooleanField(default=False)

    additional_context = models.JSONField(null=True, default=None)

    @override
    def __str__(self) -> str:
        return f"Audit log for {self.user.profile.slack_username}. PII: {self.pii}"  # pyrefly: ignore[missing-attribute]
