from django.db import migrations


def reset_twists(apps, _schema_editor):
    profile_model = apps.get_model("twisted_site", "Profile")
    profile_model.objects.update(twists=0)

    pathway_time_spent_model = apps.get_model("twisted_site", "PathwayTimeSpent")
    pathway_time_spent_model.objects.update(golden_twists=0)


class Migration(migrations.Migration):
    dependencies = [
        ("twisted_site", "0051_currencylog_created_at_pathwaycurrencylog_created_at_and_more"),
    ]

    operations = [
        migrations.RunPython(reset_twists, migrations.RunPython.noop),
    ]
