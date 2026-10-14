from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

import release_builder_v186 as base


VERSION = '18.7'
ROOT_NAME = 'BARKAV_Peymaan_18.7'


def include_file(source: Path, path: Path) -> bool:
    relative = path.relative_to(source)
    if any(part.startswith('.test_tmp') for part in relative.parts):
        return False
    if not base.include_file(source, path):
        return False
    if re.fullmatch(r'BARKAV_[0-9.]+\.bat', path.name, re.I):
        return path.name.lower() == 'barkav_18.7.bat'
    return True


def build_release(base_dir: str | Path, destination: str | Path) -> dict:
    source = Path(base_dir).resolve()
    target = Path(destination).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    files = [path for path in source.rglob('*') if path.is_file() and include_file(source, path)]
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(files):
            archive.write(path, f'{ROOT_NAME}/{path.relative_to(source).as_posix()}')
    return verify_release(target)


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
        product_bats = sorted(
            Path(name).name for name in names
            if re.fullmatch(r'BARKAV_[0-9.]+\.bat', Path(name).name, re.I)
        )
        if product_bats != ['BARKAV_18.7.bat']:
            raise RuntimeError('Unexpected product BAT files: ' + ', '.join(product_bats))
        required = [
            f'{ROOT_NAME}/BARKAV_18.7.bat', f'{ROOT_NAME}/launcher_stage18_7.py',
            f'{ROOT_NAME}/dashboard_stage18_7.py', f'{ROOT_NAME}/barkav_themes/tokens.py',
            f'{ROOT_NAME}/assets/barkav_brand_header.png',
            f'{ROOT_NAME}/assets/BARKAV_18_4.ico', f'{ROOT_NAME}/VERSION.txt',
            f'{ROOT_NAME}/data/COPY_LIVE_DATA_HERE.txt',
        ]
        missing = [name for name in required if name.lower() not in lower]
        if missing:
            raise RuntimeError('Required release files missing: ' + ', '.join(missing))
    return {
        'path': str(archive_path), 'file_count': len(names),
        'size': archive_path.stat().st_size, 'product_bats': product_bats,
        'contains_sensitive': False,
    }


if __name__ == '__main__':
    print(build_release(sys.argv[1], sys.argv[2]))
