import io
import tarfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import override
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from twisted_site.management.commands.update_vendor_assets import (
    ASSETS,
    major_version,
    read_readme_versions,
    set_readme_version,
    strip_source_map_comments,
)

FAKE_JS = b"//# sourceMappingURL=package.map\nfake javascript\n"


def make_tarball(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def sample_readme() -> str:
    rows = "\n".join(
        f"| `{asset.target}` | [{asset.package}](https://www.npmjs.com/package/{asset.package}) "
        f"| 1.0.0 | `{asset.source}` |"
        for asset in ASSETS
    )
    return (
        "# Vendored frontend dependencies\n\n"
        "| File | Package | Version | Source file |\n"
        "|---|---|---|---|\n"
        f"{rows}\n"
    )


class VendorUpdateHelperTests(SimpleTestCase):
    def test_strip_source_map_comments_removes_only_map_lines(self) -> None:
        data = b"var a = 1;\n//# sourceMappingURL=a.map\nvar b = 2;\n"

        self.assertEqual(strip_source_map_comments(data), b"var a = 1;\nvar b = 2;\n")

    def test_read_readme_versions_parses_every_row(self) -> None:
        versions = read_readme_versions(sample_readme())

        self.assertEqual(len(versions), len(ASSETS))
        self.assertEqual(versions["marked/marked.umd.js"], "1.0.0")

    def test_set_readme_version_replaces_only_the_target_row(self) -> None:
        updated = set_readme_version(sample_readme(), "dompurify/purify.min.js", "9.9.9")
        versions = read_readme_versions(updated)

        self.assertEqual(versions["dompurify/purify.min.js"], "9.9.9")
        self.assertEqual(versions["marked/marked.umd.js"], "1.0.0")

    def test_set_readme_version_rejects_unknown_rows(self) -> None:
        with self.assertRaises(LookupError):
            _ = set_readme_version(sample_readme(), "unknown/unknown.js", "1.0.0")

    def test_major_version(self) -> None:
        self.assertEqual(major_version("18.0.14"), "18")
        self.assertEqual(major_version("3.17.4"), "3")


class UpdateVendorAssetsCommandTests(SimpleTestCase):
    vendor_dir: Path  # pyright: ignore[reportUninitializedInstanceVariable]
    readme_path: Path  # pyright: ignore[reportUninitializedInstanceVariable]

    @override
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.vendor_dir = Path(self.tmp.name)
        self.readme_path = self.vendor_dir / "README.md"
        _ = self.readme_path.write_text(sample_readme(), encoding="utf-8")

    @contextmanager
    def patched_registry(self, versions: dict[str, str]) -> Iterator[None]:
        tarballs = {
            asset.package: make_tarball(
                {
                    f"package/{asset.source}": FAKE_JS,
                    **{
                        f"package/{license_name}": b"license text"
                        for license_name in asset.licenses
                    },
                },
            )
            for asset in ASSETS
        }
        urls = {
            asset.package: f"https://registry.npmjs.org/{asset.package}/-/package.tgz"
            for asset in ASSETS
        }

        def fake_fetch(package: str) -> tuple[str, str]:
            return versions[package], urls[package]

        def fake_download(url: str) -> bytes:
            for package, package_url in urls.items():
                if url == package_url:
                    return tarballs[package]
            msg = f"unexpected tarball URL: {url}"
            raise AssertionError(msg)

        with (
            patch(
                "twisted_site.management.commands.update_vendor_assets.fetch_latest",
                side_effect=fake_fetch,
            ),
            patch(
                "twisted_site.management.commands.update_vendor_assets.download_tarball",
                side_effect=fake_download,
            ),
        ):
            yield

    def test_update_installs_new_files_and_updates_readme(self) -> None:
        versions = dict.fromkeys((asset.package for asset in ASSETS), "1.0.0")
        versions["marked"] = "2.0.0"
        versions["alpinejs"] = "3.5.0"

        with self.patched_registry(versions):
            output = io.StringIO()
            call_command("update_vendor_assets", vendor_dir=self.vendor_dir, stdout=output)

        marked = self.vendor_dir / "marked/marked.umd.js"
        self.assertTrue(marked.exists())
        data = marked.read_bytes()
        self.assertIn(b"fake javascript", data)
        self.assertNotIn(b"sourceMappingURL", data)
        self.assertTrue((self.vendor_dir / "marked/LICENSE").exists())

        alpine = self.vendor_dir / "alpine/alpine.min.js"
        self.assertTrue(alpine.exists())
        self.assertFalse((self.vendor_dir / "alpine/LICENSE").exists())

        # Assets that were already current are left alone.
        self.assertFalse((self.vendor_dir / "chart.js/chart.umd.min.js").exists())

        self.assertIn("updated: marked/marked.umd.js: 1.0.0 -> 2.0.0", output.getvalue())
        self.assertIn("major version update 1.0.0 -> 2.0.0", output.getvalue())
        versions_after = read_readme_versions(self.readme_path.read_text(encoding="utf-8"))
        self.assertEqual(versions_after["marked/marked.umd.js"], "2.0.0")
        self.assertEqual(versions_after["alpine/alpine.min.js"], "3.5.0")
        self.assertEqual(versions_after["chart.js/chart.umd.min.js"], "1.0.0")

    def test_check_mode_fails_when_an_asset_is_outdated(self) -> None:
        versions = dict.fromkeys((asset.package for asset in ASSETS), "1.0.0")
        versions["chart.js"] = "2.0.0"

        with (
            self.patched_registry(versions),
            self.assertRaisesMessage(CommandError, "1 vendored asset(s) are outdated"),
        ):
            call_command(
                "update_vendor_assets",
                vendor_dir=self.vendor_dir,
                check=True,
                stdout=io.StringIO(),
            )

        self.assertFalse((self.vendor_dir / "chart.js/chart.umd.min.js").exists())
        versions_after = read_readme_versions(self.readme_path.read_text(encoding="utf-8"))
        self.assertEqual(versions_after["chart.js/chart.umd.min.js"], "1.0.0")

    def test_check_mode_passes_when_everything_is_current(self) -> None:
        versions = dict.fromkeys((asset.package for asset in ASSETS), "1.0.0")

        with self.patched_registry(versions):
            output = io.StringIO()
            call_command(
                "update_vendor_assets",
                vendor_dir=self.vendor_dir,
                check=True,
                stdout=output,
            )

        self.assertIn("All vendored assets are up to date.", output.getvalue())

    def test_missing_readme_row_is_reported(self) -> None:
        readme = sample_readme().replace("`marked/marked.umd.js` |", "`moved/marked.umd.js` |")
        _ = self.readme_path.write_text(readme, encoding="utf-8")

        with (
            self.patched_registry(dict.fromkeys((asset.package for asset in ASSETS), "1.0.0")),
            self.assertRaisesMessage(CommandError, "missing version table rows"),
        ):
            call_command("update_vendor_assets", vendor_dir=self.vendor_dir, stdout=io.StringIO())

    def test_registry_errors_are_reported(self) -> None:
        with (
            patch(
                "twisted_site.management.commands.update_vendor_assets.fetch_latest",
                side_effect=OSError("network down"),
            ),
            self.assertRaisesMessage(CommandError, "could not fetch"),
        ):
            call_command("update_vendor_assets", vendor_dir=self.vendor_dir, stdout=io.StringIO())
