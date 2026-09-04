from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import TextField
from django.utils import timezone

from . import hackatime

User = get_user_model()

JOURNAL_TYPES = {
    "hackatime": "Hackatime",
    "lookout": "Lookout",
    "untracked": "Untracked",
}


class UploadedFile(models.Model):
    uploaded_by = models.ForeignKey(User, on_delete=models.PROTECT)
    link = models.CharField(max_length=500)
    cdn_response = models.JSONField()
    uploaded_thru = models.CharField(max_length=500)
    filesize = models.IntegerField()

    def __str__(self):
        return f"{self.cdn_response['filename']} uploaded by {self.uploaded_by.profile.slack_username}"


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

    is_staff = models.BooleanField(default=False)
    is_allowed = models.BooleanField(default=False)

    twists = models.IntegerField(default=0)

    referred_by = models.ForeignKey(
        "twisted_site.Profile",
        on_delete=models.PROTECT,
        null=True,
        default=None,
        related_name="referrals",
    )
    my_referral_code = models.CharField(max_length=200, blank=True, default="")

    def shipped_projects(self):
        shipped_projects = []
        for project in self.user.projects.all():
            if project.is_shipped():
                shipped_projects.append(project)
        return shipped_projects

    def time_logged(self):
        time_logged = 0
        for project in self.user.projects.all():
            time_logged += project.time_logged()
        return time_logged

    def time_shipped(self):
        time_shipped = 0
        for project in self.shipped_projects():
            time_shipped += project.time_logged()
        return time_shipped

    def __str__(self):
        return self.user.username


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

    def __str__(self):
        return self.project_name

    def get_hackatime_project(self) -> hackatime.HackatimeProject | None:
        if not self.hackatime_project_name:
            return
        projects = hackatime.projects(self.user.profile.hackatime_access_token)
        for project in projects:
            if project.name == self.hackatime_project_name:
                return project
        return

    def time_logged(self, include_all_minutes=False):
        minutes = 0
        for journal in self.journals.all():  # type: ignore  # Django generates this attribute at runtime
            if include_all_minutes:
                # django-orm-lens-disable-next-line DOL007
                minutes += journal.minutes_worked
            else:
                minutes += journal.reduced_minutes
        return minutes

    def hackatime_logged(self, include_all_minutes=False):
        minutes = 0
        for journal in self.journals.all():  # type: ignore  # Django generates this attribute at runtime
            if journal.type != "hackatime":
                continue
            if include_all_minutes:
                # django-orm-lens-disable-next-line DOL007
                minutes += journal.minutes_worked
            else:
                minutes += journal.reduced_minutes
        return minutes

    def time_spent(self):
        project = self.get_hackatime_project()
        if project is None:
            return 0
        return project.total_seconds // 60

    def hackatime_time_unjournaled(self):
        return self.time_spent() - self.hackatime_logged(include_all_minutes=True)

    def latest_ship(self):
        ship = self.ships.order_by("-created_at").first()
        return ship

    def is_shipped(self):
        latest_ship = self.latest_ship()
        if latest_ship is None:
            return False
        return latest_ship.latest_status() != "requested_changes"

    def is_approved(self):
        latest_ship = self.latest_ship()
        if latest_ship is None:
            return False
        return latest_ship.final_status == "approved"


class Journal(models.Model):
    project = models.ForeignKey(
        Project, on_delete=models.PROTECT, related_name="journals"
    )
    type = models.CharField(max_length=100, choices=JOURNAL_TYPES)

    content = TextField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    minutes_worked = models.IntegerField()
    reduced_minutes = models.IntegerField()

    def __str__(self):
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

    t1_status = models.CharField(
        default="pending", choices=PROJECT_SHIP_STATUSES, max_length=200
    )
    t1_updated_at = models.DateTimeField(default=None, null=True)
    t1_message = models.TextField(blank=True, default="")

    t2_status = models.CharField(
        default="pending", choices=PROJECT_SHIP_STATUSES, max_length=200
    )
    t2_updated_at = models.DateTimeField(default=None, null=True)
    t2_message = models.TextField(blank=True, default="")

    fraud_status = models.CharField(
        default="pending", choices=PROJECT_SHIP_STATUSES, max_length=200
    )
    fraud_updated_at = models.DateTimeField(default=None, null=True)
    fraud_message = models.TextField(blank=True, default="")

    final_status = models.CharField(
        default="pending", choices=PROJECT_SHIP_STATUSES, max_length=200
    )
    final_updated_at = models.DateTimeField(default=None, null=True)
    final_message = models.TextField(blank=True, default="")

    def latest_status(self):
        if self.final_status != "pending":
            return self.final_status
        if self.fraud_status != "pending":
            return self.fraud_status
        if self.t2_status != "pending":
            return self.t2_status
        return self.t1_status

    def get_latest_status_display(self):
        if self.final_status != "pending":
            string = "Final"
        elif self.fraud_status != "pending":
            string = "Fraud"
        elif self.t2_status != "pending":
            string = "T2"
        else:
            string = "T1"
        return string + ": " + PROJECT_SHIP_STATUSES[self.latest_status()]

    def save(self, *args, **kwargs):
        if not self.pk:  # Check if object already exists in the database
            return super().save(*args, **kwargs)

        original = ProjectShip.objects.get(pk=self.pk)

        if (
            original.t1_status != self.t1_status
            or original.t1_message != self.t1_message
        ):
            self.t1_updated_at = timezone.now()

        if (
            original.t2_status != self.t2_status
            or original.t2_message != self.t2_message
        ):
            self.t2_updated_at = timezone.now()

        if (
            original.fraud_status != self.fraud_status
            or original.fraud_message != self.fraud_message
        ):
            self.fraud_updated_at = timezone.now()

        if (
            original.final_status != self.final_status
            or original.final_message != self.final_message
        ):
            self.final_updated_at = timezone.now()

        return super().save(*args, **kwargs)

    def __str__(self):
        return f"Ship created at {self.created_at} ({PROJECT_SHIP_STATUSES.get(str(self.latest_status()), self.latest_status())})"


class Pathway(models.Model):
    start = models.DateTimeField()
    end = models.DateTimeField()

    name = models.CharField(max_length=200)
    min_mins = models.IntegerField(default=300)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def ended(self):
        return timezone.now() > self.end

    def didnt_start(self):
        return self.start > timezone.now()

    def in_progress(self):
        return not self.ended() and not self.didnt_start()

    def status(self):
        if self.ended():
            return "ended"
        if self.didnt_start():
            return "awaiting"
        if self.in_progress():
            return "in progress"

    def mins_spent(self, user: AbstractBaseUser):
        pathways = Pathway.objects.order_by("start").values(
            "id", "start", "end", "min_mins"
        )
        if not pathways:
            return 0

        pathway_totals = {p["id"]: 0 for p in pathways}

        journals = (
            Journal.objects.filter(project__user=user)
            .order_by("created_at")
            .values_list("created_at", "reduced_minutes")
        )

        for j_created, j_mins in journals:
            mins_remaining = j_mins
            for pathway in pathways:
                if mins_remaining <= 0:
                    break

                # Check if journal falls within the pathway window
                if pathway["start"] > j_created or pathway["end"] < j_created:
                    continue

                p_id = pathway["id"]
                mins_completed = pathway_totals.get(p_id, 0)
                mins_required = pathway["min_mins"]

                if mins_completed >= mins_required:
                    continue

                mins_needed = mins_required - mins_completed
                mins_donated = min(mins_remaining, mins_needed)

                mins_remaining -= mins_donated
                pathway_totals[p_id] = mins_completed + mins_donated

        return pathway_totals[self.id]

    def mins_spent_per_participant(self) -> dict[int, int]:
        """
        Calculates the minutes spent on this specific pathway for all participants.

        Returns:
            dict: {user_id: mins_spent}
        """
        # Fetch all pathways to accurately model the sequential time donation
        pathways = list(
            Pathway.objects.order_by("start").values("id", "start", "end", "min_mins")
        )
        if not pathways:
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

        user_pathway_totals = {}

        for user_id, j_created, j_mins in journals:
            if user_id not in user_pathway_totals:
                user_pathway_totals[user_id] = {p["id"]: 0 for p in pathways}

            pathway_totals = user_pathway_totals[user_id]
            mins_remaining = j_mins

            for pathway in pathways:
                if mins_remaining <= 0:
                    break

                if pathway["start"] > j_created or pathway["end"] < j_created:
                    continue

                p_id = pathway["id"]
                mins_completed = pathway_totals[p_id]
                mins_required = pathway["min_mins"]

                if mins_completed >= mins_required:
                    continue

                mins_needed = mins_required - mins_completed
                mins_donated = min(mins_remaining, mins_needed)

                mins_remaining -= mins_donated
                pathway_totals[p_id] += mins_donated

        # Extract only this pathway's result for each participant
        return {
            user_id: totals.get(self.id, 0)
            for user_id, totals in user_pathway_totals.items()
        }

    def qualified_participants(self):
        per_part = self.mins_spent_per_participant()
        qualified = []
        for userid, mins in per_part.items():
            if mins >= self.min_mins:
                qualified.append(User.objects.get(id=userid))
        return qualified

    def __str__(self):
        return self.name


class AuditLog(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="audit_logs")
    path = models.CharField(max_length=400)
    post = models.BooleanField()
    pii = models.BooleanField(default=False)

    additional_context = models.JSONField(null=True, default=None)

    def __str__(self):
        return f"Audit log for {self.user.profile.slack_username}. PII: {self.pii}"
