from django.db import migrations, models


def backfill_group_names(apps, schema_editor):
    PathwayGroup = apps.get_model("twisted_site", "PathwayGroup")
    for group in PathwayGroup.objects.filter(name=""):
        group.name = f"Group ({group.start.date()} - {group.end.date()})"
        group.save(update_fields=["name"])


class Migration(migrations.Migration):
    dependencies = [
        ("twisted_site", "0034_pathwaygroup"),
    ]

    operations = [
        migrations.AddField(
            model_name="pathwaygroup",
            name="name",
            field=models.CharField(default="", max_length=200),
            preserve_default=False,
        ),
        migrations.RunPython(backfill_group_names, migrations.RunPython.noop),
    ]
