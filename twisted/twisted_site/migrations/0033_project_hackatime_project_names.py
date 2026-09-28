from django.db import migrations, models


def forwards(apps, schema_editor):
    Project = apps.get_model("twisted_site", "Project")
    for project in Project.objects.exclude(hackatime_project_name=""):
        project.hackatime_project_names = [project.hackatime_project_name]
        project.save(update_fields=["hackatime_project_names"])


def backwards(apps, schema_editor):
    Project = apps.get_model("twisted_site", "Project")
    for project in Project.objects.exclude(hackatime_project_names=[]):
        project.hackatime_project_name = project.hackatime_project_names[0]
        project.save(update_fields=["hackatime_project_name"])


class Migration(migrations.Migration):
    dependencies = [
        ("twisted_site", "0032_profilestaffpermissions_manage_announcements_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="hackatime_project_names",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.RunPython(forwards, backwards),
        migrations.RemoveField(
            model_name="project",
            name="hackatime_project_name",
        ),
    ]
