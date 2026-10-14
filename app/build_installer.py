"""Compiles BARKAV.iss with Inno Setup, then signs the resulting installer.

Run build_portable.py first - this packages its dist\\BARKAV_Portable\\
output (BARKAV.iss expects it to already exist).

Usage: python build_installer.py
"""

from __future__ import annotations

import glob
import subprocess
from pathlib import Path

from build_portable import sign

APP_ROOT = Path(__file__).resolve().parent


def find_iscc() -> str | None:
    for candidate in (
        r'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',
        r'C:\Program Files\Inno Setup 6\ISCC.exe',
    ):
        if Path(candidate).is_file():
            return candidate
    return None


def main() -> None:
    iscc = find_iscc()
    if not iscc:
        raise SystemExit('ISCC.exe not found - install Inno Setup 6 from https://jrsoftware.org first.')

    subprocess.run([iscc, str(APP_ROOT / 'BARKAV.iss')], cwd=APP_ROOT, check=True)

    outputs = sorted(glob.glob(str(APP_ROOT / 'dist' / 'installer' / 'BARKAV_*_Setup.exe')))
    if not outputs:
        raise SystemExit('ISCC reported success but no BARKAV_*_Setup.exe was found.')
    installer = Path(outputs[-1])

    sign(installer)
    print(f'Installer ready: {installer}')


if __name__ == '__main__':
    main()
