from django.tasks import task

from .models import Profile


@task
def refresh_profile_countries(profile_ids: list[int]) -> None:
    """Re-fetch the HCA country of each profile, off the request path."""
    for profile in Profile.objects.filter(id__in=profile_ids):
        _ = profile.refresh_country()
