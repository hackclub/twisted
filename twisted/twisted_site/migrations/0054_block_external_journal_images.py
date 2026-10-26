import os
import re

from django.db import migrations

# ![alt](target) where target is the URL plus an optional title.
IMAGE_REGEX = re.compile(r"!\[([^\]]*)\]\(([^)]*)\)")
NOTICE = "External image not supported"
# Matches links written by block_external_images, so they can be turned back into images.
NOTICE_REGEX = re.compile(r"\[" + NOTICE + r"(?:: ([^\]]*))?\]\(([^)]*)\)")


def _image_base() -> str:
    return os.environ["R2_PUBLIC_URL"].rstrip("/") + "/"


def block_external_images_in(content: str, image_base: str) -> str:
    def replace(match: re.Match[str]) -> str:
        alt, target = match.group(1), match.group(2)
        url = target.strip().split(maxsplit=1)[0].strip("<>") if target.strip() else ""
        # Empty targets are upload placeholders ("Uploading...", "Error: ..."), not images.
        if not url or url.startswith(image_base):
            return match.group(0)
        label = f"{NOTICE}: {alt}" if alt else NOTICE
        return f"[{label}]({target})"

    return IMAGE_REGEX.sub(replace, content)


def restore_external_images_in(content: str) -> str:
    return NOTICE_REGEX.sub(lambda m: f"![{m.group(1) or ''}]({m.group(2)})", content)


def _rewrite(apps, transform) -> None:
    journal_model = apps.get_model("twisted_site", "Journal")
    changed = []
    for journal in journal_model.objects.filter(content__contains="](").only("id", "content"):
        new_content = transform(journal.content)
        if new_content != journal.content:
            journal.content = new_content
            changed.append(journal)
    # bulk_update skips auto_now, so updated_at is left alone.
    journal_model.objects.bulk_update(changed, ["content"], batch_size=500)


def block_external_images(apps, _schema_editor):
    image_base = _image_base()
    _rewrite(apps, lambda content: block_external_images_in(content, image_base))


def restore_external_images(apps, _schema_editor):
    _rewrite(apps, restore_external_images_in)


class Migration(migrations.Migration):
    dependencies = [
        ("twisted_site", "0053_use_cachet_pfp_urls"),
    ]

    operations = [
        migrations.RunPython(block_external_images, restore_external_images),
    ]
