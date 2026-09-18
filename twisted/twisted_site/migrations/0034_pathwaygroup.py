import django.contrib.postgres.constraints
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def migrate_pathways_to_groups(apps, schema_editor):
    """Group existing Pathways into PathwayGroups, merging any that overlap in time."""
    Pathway = apps.get_model("twisted_site", "Pathway")
    PathwayGroup = apps.get_model("twisted_site", "PathwayGroup")

    clusters = []
    for pathway in Pathway.objects.order_by("start"):
        target = None
        for cluster in clusters:
            if pathway.start < cluster["end"] and pathway.end > cluster["start"]:
                target = cluster
                break
        if target is None:
            clusters.append({"start": pathway.start, "end": pathway.end, "pathways": [pathway]})
            continue
        target["start"] = min(target["start"], pathway.start)
        target["end"] = max(target["end"], pathway.end)
        target["pathways"].append(pathway)

    # Widening a cluster above may make it overlap another cluster that was
    # already closed off; keep merging until no two clusters overlap.
    merged = True
    while merged:
        merged = False
        for i, cluster_a in enumerate(clusters):
            for cluster_b in clusters[i + 1 :]:
                if cluster_a["start"] < cluster_b["end"] and cluster_a["end"] > cluster_b["start"]:
                    cluster_a["start"] = min(cluster_a["start"], cluster_b["start"])
                    cluster_a["end"] = max(cluster_a["end"], cluster_b["end"])
                    cluster_a["pathways"].extend(cluster_b["pathways"])
                    clusters.remove(cluster_b)
                    merged = True
                    break
            if merged:
                break

    for cluster in clusters:
        group = PathwayGroup.objects.create(start=cluster["start"], end=cluster["end"])
        for pathway in cluster["pathways"]:
            pathway.group = group
            pathway.save(update_fields=["group"])


class Migration(migrations.Migration):
    dependencies = [
        ("twisted_site", "0033_project_hackatime_project_names"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PathwayGroup",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("start", models.DateTimeField()),
                ("end", models.DateTimeField()),
            ],
            options={
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("start__lt", models.F("end"))),
                        name="pathwaygroup_start_before_end",
                    ),
                    django.contrib.postgres.constraints.ExclusionConstraint(
                        expressions=[
                            (models.Func(models.F("start"), models.F("end"), function="tstzrange"), "&&"),
                        ],
                        name="pathwaygroup_no_overlapping_ranges",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="PathwayTimeSpent",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("minutes", models.IntegerField(default=0)),
                (
                    "pathway",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="twisted_site.pathway"),
                ),
                (
                    "user",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL),
                ),
            ],
            options={
                "unique_together": {("pathway", "user")},
            },
        ),
        migrations.AddField(
            model_name="pathway",
            name="group",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="pathways",
                to="twisted_site.pathwaygroup",
            ),
        ),
        migrations.RunPython(migrate_pathways_to_groups, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="pathway",
            name="group",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="pathways",
                to="twisted_site.pathwaygroup",
            ),
        ),
        migrations.RemoveField(
            model_name="pathway",
            name="end",
        ),
        migrations.RemoveField(
            model_name="pathway",
            name="start",
        ),
    ]
