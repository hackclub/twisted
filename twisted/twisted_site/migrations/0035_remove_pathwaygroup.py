from django.db import migrations, models


def copy_group_dates_to_pathway(apps, schema_editor):
    Pathway = apps.get_model("twisted_site", "Pathway")
    for pathway in Pathway.objects.select_related("group"):
        pathway.start = pathway.group.start
        pathway.end = pathway.group.end
        pathway.save(update_fields=["start", "end"])


class Migration(migrations.Migration):

    dependencies = [
        ("twisted_site", "0034_pathwaygroup_squashed_0036_pathwaytimespent_golden_twists_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="pathway",
            name="start",
            field=models.DateTimeField(null=True),
        ),
        migrations.AddField(
            model_name="pathway",
            name="end",
            field=models.DateTimeField(null=True),
        ),
        migrations.RunPython(copy_group_dates_to_pathway, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="pathway",
            name="start",
            field=models.DateTimeField(),
        ),
        migrations.AlterField(
            model_name="pathway",
            name="end",
            field=models.DateTimeField(),
        ),
        migrations.RemoveField(
            model_name="pathway",
            name="group",
        ),
        migrations.DeleteModel(
            name="PathwayGroup",
        ),
    ]
