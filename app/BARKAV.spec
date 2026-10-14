# PyInstaller spec for the portable BARKAV build.
#
# One exe for three roles: Hub (double-click), project runner, and the
# Telegram bot. There is no separate .py file on disk to hand a subprocess
# once frozen, so runtime_base.self_reexec_args / launcher_stage18_7.main's
# --run-project / --run-bot dispatch re-launch THIS SAME exe instead - see
# those for the reasoning. Build with: pyinstaller BARKAV.spec

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

block_cipher = None
APP_ROOT = Path(SPECPATH)

datas = [(str(APP_ROOT / 'assets'), 'assets')]
binaries = []
hiddenimports = [
    'telegram.ext._utils.webhookhandler',
    'PIL._tkinter_finder',
]

# google-genai, gspread and google-auth resolve a lot of their real modules
# dynamically at import time - a plain hiddenimports list can't realistically
# enumerate all of that, so pull each package's own files in wholesale
# instead of guessing at individual submodules. Must happen BEFORE
# Analysis() is constructed: collect_all() returns plain (src, dest) pairs
# meant for Analysis's own datas=/binaries= kwargs, which normalize them -
# appending to a.datas/a.binaries afterwards feeds them to code that expects
# the internal 3-tuple TOC format instead and raises a ValueError.
for _pkg in ('google.genai', 'google.auth', 'google_auth_httplib2', 'gspread', 'telegram'):
    try:
        _d, _b, _h = collect_all(_pkg)
        datas += _d
        binaries += _b
        hiddenimports += _h
    except Exception:
        pass

a = Analysis(
    ['launcher_stage18_7.py'],
    pathex=[str(APP_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='BARKAV',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(APP_ROOT / 'assets' / 'BARKAV.ico'),
    # PyInstaller >=6 defaults onedir builds to a _internal/ subfolder for
    # everything but the exe. runtime_base.resolve_base() (secrets.local.json,
    # data/, runtime/, .brk) and every assets/ reference in this codebase
    # assume the flat pre-6.0 layout - everything next to the exe - so
    # restore that instead of teaching every one of those call sites about
    # an extra _internal hop. COLLECT reads this off the EXE instance, not
    # its own kwargs, despite most docs showing it passed to COLLECT.
    contents_directory='.',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='BARKAV',
)
