from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path


VERSION = '18.6'
ROOT_NAME = 'BARKAV_Peymaan_18.6'
EXCLUDED_DIRS = {
    '.git', '.agents', '.codex', '.pytest_cache', '__pycache__',
    'runtime', 'logs', 'exports', 'attachments', '_roadmap_render', 'tools',
}
EXCLUDED_NAMES = {
    'secrets.local.json', 'historical_seed_barkav0.jsonl',
}
EXCLUDED_SUFFIXES = {'.pyc', '.pyo', '.sqlite', '.sqlite3', '.db', '.log', '.tmp'}


def include_file(base: Path, path: Path) -> bool:
    relative = path.relative_to(base)
    if any(part in EXCLUDED_DIRS for part in relative.parts):
        return False
    if path.name.lower() in {name.lower() for name in EXCLUDED_NAMES}:
        return False
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return False
    if relative.parts and relative.parts[0].lower() == 'data':
        return relative.as_posix() == 'data/COPY_LIVE_DATA_HERE.txt'
    return True


def build_release(base_dir: str | Path, destination: str | Path, roadmap: str | Path | None = None) -> dict:
    base = Path(base_dir).resolve()
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    files = [path for path in base.rglob('*') if path.is_file() and include_file(base, path)]
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(files):
            archive.write(path, f'{ROOT_NAME}/{path.relative_to(base).as_posix()}')
        if roadmap:
            roadmap_path = Path(roadmap).resolve()
            if not roadmap_path.is_file():
                raise FileNotFoundError(str(roadmap_path))
            archive.write(roadmap_path, f'{ROOT_NAME}/{roadmap_path.name}')
    return verify_release(destination)


def verify_release(path: str | Path) -> dict:
    archive_path = Path(path).resolve()
    with zipfile.ZipFile(archive_path, 'r') as archive:
        bad_member = archive.testzip()
        if bad_member:
            raise RuntimeError(f'ZIP CRC failed: {bad_member}')
        names = archive.namelist()
        lower = [name.lower() for name in names]
        forbidden = [
            name for name in names
            if name.lower().endswith(('secrets.local.json', '.sqlite', '.sqlite3', '.db', '.log', '.pyc'))
            or '/runtime/' in name.lower() or '/attachments/' in name.lower()
            or 'historical_seed_' in name.lower()
        ]
        if forbidden:
            raise RuntimeError('Sensitive/runtime files found: ' + ', '.join(forbidden[:8]))
        product_bats = sorted(Path(name).name for name in names if re.fullmatch(r'BARKAV_[0-9.]+\.bat', Path(name).name, re.I))
        if product_bats != ['BARKAV_18.6.bat']:
            raise RuntimeError('Unexpected product BAT files: ' + ', '.join(product_bats))
        required = [
            f'{ROOT_NAME}/BARKAV_18.6.bat',
            f'{ROOT_NAME}/launcher_stage18_6.py',
            f'{ROOT_NAME}/dashboard_stage18_6.py',
            f'{ROOT_NAME}/VERSION.txt',
            f'{ROOT_NAME}/data/COPY_LIVE_DATA_HERE.txt',
        ]
        missing = [name for name in required if name.lower() not in lower]
        if missing:
            raise RuntimeError('Required release files missing: ' + ', '.join(missing))
    return {
        'path': str(archive_path),
        'file_count': len(names),
        'size': archive_path.stat().st_size,
        'product_bats': product_bats,
        'contains_sensitive': False,
    }


if __name__ == '__main__':
    roadmap_arg = sys.argv[3] if len(sys.argv) > 3 else None
    print(build_release(sys.argv[1], sys.argv[2], roadmap_arg))
