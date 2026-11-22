from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("twisted_site", "0054_block_external_journal_images"),
    ]

    operations = [
        migrations.AddField(
            model_name="profilestaffpermissions",
            name="manage_journals",
            field=models.BooleanField(default=False),
        ),
        # Some HCA country names ("Bosnia and Herzegovina") are longer than 20 characters.
        migrations.AlterField(
            model_name="profile",
            name="country",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
    ]
