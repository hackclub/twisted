from django.db import migrations
from django.db.models import Value
from django.db.models.functions import Concat


def use_cachet_pfps(apps, _schema_editor):
    profile_model = apps.get_model("twisted_site", "Profile")
    profile_model.objects.exclude(slack_id="").update(
        slack_pfp_url=Concat(
            Value("https://cachet.hackclub.com/users/"),
            "slack_id",
            Value("/r"),
        )
    )


class Migration(migrations.Migration):
    dependencies = [
        ("twisted_site", "0052_reset_twists_and_golden_twists"),
    ]

    operations = [
        migrations.RunPython(use_cachet_pfps, migrations.RunPython.noop),
    ]
