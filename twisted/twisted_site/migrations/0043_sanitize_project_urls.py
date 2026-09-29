from urllib.parse import urlparse

from django.db import migrations

URL_FIELDS = ("repo_url", "playable_url", "screenshot_url")


def _is_http_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    hostname = parsed.hostname
    return parsed.scheme.lower() in {"http", "https"} and hostname is not None and hostname != ""


def sanitize_project_urls(apps, _schema_editor):
    project_model = apps.get_model("twisted_site", "Project")
    queryset = project_model.objects.only("id", *URL_FIELDS)
    for project in queryset:
        updates = {
            field: ""
            for field in URL_FIELDS
            if getattr(project, field) and not _is_http_url(getattr(project, field))
        }
        if updates:
            project_model.objects.filter(pk=project.pk).update(**updates)


class Migration(migrations.Migration):
    dependencies = [
        ("twisted_site", "0042_profilestaffpermissions_view_projects"),
    ]

    operations = [
        migrations.RunPython(sanitize_project_urls, migrations.RunPython.noop),
    ]
