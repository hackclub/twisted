from importlib import import_module

from django.apps import apps
from django.contrib.auth.models import User
from django.test import TestCase

from twisted_site.models import Journal, Project

migration = import_module("twisted_site.migrations.0054_block_external_journal_images")

BASE = "https://example.invalid/uploads/"


class BlockExternalImagesTests(TestCase):
    def test_external_images_become_links(self) -> None:
        content = "hi ![shot](https://evil.example/a.png) bye"
        self.assertEqual(
            migration.block_external_images_in(content, BASE),
            "hi [External image not supported: shot](https://evil.example/a.png) bye",
        )

    def test_uploaded_images_and_placeholders_are_kept(self) -> None:
        content = f"![ok]({BASE}abc/ok.png)\n![Error: too big]()\n[a link](https://x.example)"
        self.assertEqual(migration.block_external_images_in(content, BASE), content)

    def test_lookalike_host_is_blocked(self) -> None:
        content = "![x](https://example.invalid/uploads.evil/x.png)"
        self.assertNotEqual(migration.block_external_images_in(content, BASE), content)

    def test_restore_reverses_block(self) -> None:
        content = '![](https://a.example/1.png) ![alt](https://b.example/2.png "title")'
        blocked = migration.block_external_images_in(content, BASE)
        self.assertEqual(migration.restore_external_images_in(blocked), content)

    def test_migration_rewrites_stored_journals(self) -> None:
        user = User.objects.create_user(username="migration-user")
        project = Project.objects.create(
            user=user,
            project_name="p",
            project_description="x",
            project_type="software",
        )
        journal = Journal.objects.create(
            project=project,
            type="untracked",
            content=f"![a](https://evil.example/a.png) ![b]({BASE}b.png)",
            minutes_worked=60,
            reduced_minutes=60,
        )

        migration.block_external_images(apps, None)

        journal.refresh_from_db()
        self.assertEqual(
            journal.content,
            f"[External image not supported: a](https://evil.example/a.png) ![b]({BASE}b.png)",
        )
