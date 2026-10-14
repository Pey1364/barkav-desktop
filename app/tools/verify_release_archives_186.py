from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path


FORBIDDEN_SUFFIXES = (
    "secrets.local.json",
    ".sqlite",
    ".sqlite3",
    ".db",
    ".log",
    ".pyc",
)


def inspect_archive(path: Path, *, product: bool) -> tuple[int, int]:
    with zipfile.ZipFile(path) as archive:
        bad_member = archive.testzip()
        if bad_member:
            raise RuntimeError(f"CRC failure: {bad_member}")

        names = archive.namelist()
        lowered = [name.lower() for name in names]
        forbidden = [
            name
            for name in names
            if name.lower().endswith(FORBIDDEN_SUFFIXES)
            or "/runtime/" in name.lower()
            or "/attachments/" in name.lower()
            or "historical_seed_" in name.lower()
        ]
        if forbidden:
            raise RuntimeError(f"Forbidden archive members: {forbidden[:5]}")

        bats = sorted(
            Path(name).name
            for name in names
            if re.fullmatch(r"BARKAV_[0-9.]+\.bat", Path(name).name, re.I)
        )
        if bats != ["BARKAV_18.6.bat"]:
            raise RuntimeError(f"Unexpected product launchers: {bats}")

        if product:
            root = "barkav_peymaan_18.6/"
            if not all(name.lower().startswith(root) for name in names):
                raise RuntimeError("Product ZIP has files outside the 18.6 root")
            required = [
                root + "launcher_stage18_6.py",
                root + "dashboard_stage18_6.py",
                root + "ui_stage18_6.py",
                root + "version.txt",
                root + "data/copy_live_data_here.txt",
            ]
        else:
            required = [
                "development_package_manifest.json",
                "source/launcher_stage18_6.py",
                "source/dashboard_stage18_6.py",
                "source/ui_stage18_6.py",
                "source/barkav_18.6.bat",
                "handoff/barkav_project_handoff.md",
            ]
            manifest = json.loads(archive.read("DEVELOPMENT_PACKAGE_MANIFEST.json"))
            if manifest.get("contains_live_database") is not False:
                raise RuntimeError("Development manifest database flag is unsafe")
            if manifest.get("contains_secrets") is not False:
                raise RuntimeError("Development manifest secrets flag is unsafe")

        missing = [name for name in required if name not in lowered]
        if missing:
            raise RuntimeError(f"Missing archive members: {missing}")

    return len(names), path.stat().st_size


def main() -> int:
    product = Path(sys.argv[1]).resolve()
    development = Path(sys.argv[2]).resolve()
    product_count, product_size = inspect_archive(product, product=True)
    dev_count, dev_size = inspect_archive(development, product=False)
    print(f"PRODUCT_OK files={product_count} bytes={product_size}")
    print(f"DEVELOPMENT_OK files={dev_count} bytes={dev_size}")
    print("PRIVACY_OK live_database=false secrets=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
