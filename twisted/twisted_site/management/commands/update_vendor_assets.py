"""
Update the vendored frontend assets under ``twisted_site/static/vendor``.

Assets are downloaded straight from the npm registry (no npm/node required) and written
to the paths documented in ``static/vendor/README.md``; that README's version table is
updated to match. See the README for why these files are vendored at all.
"""

from __future__ import annotations

import json
import re
import tarfile
import tempfile
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

NPM_REGISTRY = "https://registry.npmjs.org"
NETWORK_TIMEOUT_SECONDS = 60
README_NAME = "README.md"
SOURCE_MAP_COMMENT = b"//# sourceMappingURL="

DEFAULT_VENDOR_DIR = Path(__file__).resolve().parents[2] / "static" / "vendor"


@dataclass(frozen=True)
class VendoredAsset:
    """An npm package file vendored into the repository."""

    package: str
    source: str
    target: str
    licenses: tuple[str, ...] = ()


ASSETS: tuple[VendoredAsset, ...] = (
    VendoredAsset("marked", "lib/marked.umd.js", "marked/marked.umd.js", ("LICENSE",)),
    VendoredAsset(
        "dompurify",
        "dist/purify.min.js",
        "dompurify/purify.min.js",
        ("LICENSE", "LICENSE-MPL"),
    ),
    VendoredAsset("alpinejs", "dist/cdn.min.js", "alpine/alpine.min.js"),
    VendoredAsset("@alpinejs/collapse", "dist/cdn.min.js", "alpine/collapse.min.js"),
    VendoredAsset("@alpinejs/focus", "dist/cdn.min.js", "alpine/focus.min.js"),
    VendoredAsset(
        "chart.js",
        "dist/chart.umd.min.js",
        "chart.js/chart.umd.min.js",
        ("LICENSE.md",),
    ),
)

README_ROW = re.compile(
    r"^\|\s*`(?P<target>[^`]+)`\s*\|[^|]*\|\s*(?P<version>[^|]+?)\s*\|",
    re.MULTILINE,
)


def package_metadata_url(package: str) -> str:
    """Return the npm registry "latest" metadata URL for ``package``."""
    return f"{NPM_REGISTRY}/{urllib.parse.quote(package, safe='@')}/latest"


def fetch_latest(package: str) -> tuple[str, str]:
    """Return ``(version, tarball_url)`` for the latest release of an npm package."""
    with urllib.request.urlopen(  # noqa: S310
        package_metadata_url(package),
        timeout=NETWORK_TIMEOUT_SECONDS,
    ) as response:
        metadata: dict[str, Any] = json.load(response)

    version = str(metadata["version"])
    tarball_url = str(metadata["dist"]["tarball"])
    if not tarball_url.startswith(f"{NPM_REGISTRY}/"):
        msg = f"refusing to download {package} from unexpected host: {tarball_url}"
        raise CommandError(msg)
    return version, tarball_url


def download_tarball(tarball_url: str) -> bytes:
    """Download a package tarball into memory."""
    with urllib.request.urlopen(tarball_url, timeout=NETWORK_TIMEOUT_SECONDS) as response:  # noqa: S310
        return response.read()


def read_tarball_member(tar: tarfile.TarFile, name: str) -> bytes:
    """Return one member of an open tarball, failing loudly when it is missing."""
    data = maybe_read_tarball_member(tar, name)
    if data is None:
        msg = f"{name} is missing from the package tarball"
        raise CommandError(msg)
    return data


def maybe_read_tarball_member(tar: tarfile.TarFile, name: str) -> bytes | None:
    """Return one member of an open tarball, or ``None`` when it does not exist."""
    try:
        member = tar.getmember(name)
    except KeyError:
        return None
    file = tar.extractfile(member)
    return None if file is None else file.read()


def strip_source_map_comments(data: bytes) -> bytes:
    """Drop ``//# sourceMappingURL=...`` lines: the maps themselves are not vendored."""
    return b"".join(
        line for line in data.splitlines(keepends=True) if not line.startswith(SOURCE_MAP_COMMENT)
    )


def major_version(version: str) -> str:
    """Return the major component of a semver-ish version string."""
    return version.split(".", maxsplit=1)[0]


def read_readme_versions(readme_text: str) -> dict[str, str]:
    """Map each vendored file path in the README version table to its recorded version."""
    return {
        match.group("target"): match.group("version") for match in README_ROW.finditer(readme_text)
    }


def set_readme_version(readme_text: str, target: str, version: str) -> str:
    """Return ``readme_text`` with the version cell of ``target``'s row replaced."""
    pattern = re.compile(
        rf"^(\|\s*`{re.escape(target)}`\s*\|[^|]*\|\s*)[^|]+?(\s*\|)",
        re.MULTILINE,
    )

    def replace(match: re.Match[str]) -> str:
        return f"{match.group(1)}{version}{match.group(2)}"

    new_text, count = pattern.subn(replace, readme_text)
    if count == 0:
        msg = f"no README row found for {target}"
        raise LookupError(msg)
    return new_text


class Command(BaseCommand):
    help = (
        "Update the vendored frontend assets in twisted_site/static/vendor to their "
        "latest npm releases."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        _ = parser.add_argument(
            "--check",
            action="store_true",
            help="Only report outdated assets; exit with an error if any are outdated.",
        )
        _ = parser.add_argument(
            "--vendor-dir",
            type=Path,
            default=DEFAULT_VENDOR_DIR,
            help="Directory containing the vendored assets and their README.",
        )

    def handle(self, *args: object, **options: object) -> None:  # noqa: ARG002
        vendor_dir: Path = options["vendor_dir"]
        check_only: bool = options["check"]

        readme_path = vendor_dir / README_NAME
        if not readme_path.exists():
            msg = f"{readme_path} does not exist"
            raise CommandError(msg)

        readme_text = readme_path.read_text(encoding="utf-8")
        versions = read_readme_versions(readme_text)
        missing_rows = [asset.target for asset in ASSETS if asset.target not in versions]
        if missing_rows:
            msg = f"{README_NAME} is missing version table rows for: {', '.join(missing_rows)}"
            raise CommandError(msg)

        outdated: list[str] = []
        updated: list[str] = []

        for asset in ASSETS:
            current = versions[asset.target]
            latest, tarball_url = self.fetch_latest_or_fail(asset)

            if current == latest:
                self.stdout.write(f"{asset.target}: {latest} (up to date)")
                continue

            outdated.append(f"{asset.target}: {current} -> {latest}")
            if check_only:
                self.stdout.write(self.style.WARNING(f"outdated: {outdated[-1]}"))
                continue

            if major_version(current) != major_version(latest):
                self.stdout.write(
                    self.style.WARNING(
                        f"{asset.package}: major version update {current} -> {latest}; "
                        "review the changelog before committing.",
                    ),
                )

            self.install_asset(asset, tarball_url, vendor_dir)
            readme_text = set_readme_version(readme_text, asset.target, latest)
            updated.append(asset.target)
            self.stdout.write(self.style.SUCCESS(f"updated: {outdated[-1]}"))

        if updated:
            _ = readme_path.write_text(readme_text, encoding="utf-8")
            self.stdout.write(
                self.style.SUCCESS(
                    f"Updated {len(updated)} asset(s). Review the diff, run the tests, and run "
                    "collectstatic with the production storage before deploying.",
                ),
            )

        if outdated and check_only:
            msg = f"{len(outdated)} vendored asset(s) are outdated"
            raise CommandError(msg)
        if not outdated:
            self.stdout.write(self.style.SUCCESS("All vendored assets are up to date."))

    def fetch_latest_or_fail(self, asset: VendoredAsset) -> tuple[str, str]:
        try:
            return fetch_latest(asset.package)
        except CommandError:
            raise
        except (KeyError, OSError, ValueError) as error:
            msg = f"could not fetch {asset.package} from the npm registry: {error}"
            raise CommandError(msg) from error

    def install_asset(self, asset: VendoredAsset, tarball_url: str, vendor_dir: Path) -> None:
        tarball = download_tarball(tarball_url)
        with tempfile.TemporaryDirectory() as tmp:
            tarball_path = Path(tmp) / "package.tgz"
            _ = tarball_path.write_bytes(tarball)
            with tarfile.open(tarball_path) as tar:
                target_path = vendor_dir / asset.target
                target_path.parent.mkdir(parents=True, exist_ok=True)
                data = strip_source_map_comments(
                    read_tarball_member(tar, f"package/{asset.source}"),
                )
                _ = target_path.write_bytes(data)

                for license_name in asset.licenses:
                    license_data = maybe_read_tarball_member(tar, f"package/{license_name}")
                    if license_data is not None:
                        _ = (target_path.parent / license_name).write_bytes(license_data)
