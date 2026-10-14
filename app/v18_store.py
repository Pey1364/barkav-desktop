from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any


_PROJECT_DIR_CACHE: dict[str, Path] = {}


def _project_dir() -> Path:
    raw = os.getenv('STAGE4_DB_PATH') or 'data/stage4_test.sqlite3'
    cached = _PROJECT_DIR_CACHE.get(raw)
    if cached is not None:
        return cached
    p = Path(raw)
    if not p.is_absolute():
        p = Path(__file__).resolve().parent / p
    p.parent.mkdir(parents=True, exist_ok=True)
    _PROJECT_DIR_CACHE[raw] = p.parent
    return p.parent


DEFAULT_PROFILE: dict[str, Any] = {
    'floors': [],
    'team': {
        'executor': {'name': '', 'phone': '', 'license_no': '', 'company': ''},
        'supervisor': {'name': '', 'phone': '', 'license_no': '', 'company': ''},
        'designer': {'name': '', 'phone': '', 'license_no': '', 'company': ''},
    },
    'partners': ['پیمان', 'پیام', 'سامان'],
}

DEFAULT_UI: dict[str, Any] = {
    # Appearance defaults for a project that has never been configured.
    # Vazirmatn at 10/400 on theme 2 is the product's designed look; a
    # project opened for the first time should already show it.
    'font_family': 'Vazirmatn',
    'font_weight': 400,
    'font_size': 10,
    'theme_id': 2,
    'language': 'fa',
    'appearance': 'dark',
    'background_color': 'پیش‌فرض',
    'row_height': 34,
    'open_maximized': True,
    'currency_unit': 'تومان',
    'usd_rate_current': 0,
    'usd_rate_baseline': 0,
    'gold_rate_current': 0,
    'gold_rate_baseline': 0,
    'updated_rate_basis_187': 'دلار و طلا',
    'external_injection': 0,
}


_LOAD_CACHE: dict[tuple, dict[str, Any]] = {}


def _load(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    # load_ui() is called hundreds of times a minute from styling/font
    # helpers; re-parse the file only when its mtime/size actually changed.
    try:
        st = path.stat()
        key = (str(path), st.st_mtime_ns, st.st_size, id(default))
    except OSError:
        key = None
    if key is not None and key in _LOAD_CACHE:
        return deepcopy(_LOAD_CACHE[key])
    data = _load_uncached(path, default)
    if key is not None:
        for old in [k for k in _LOAD_CACHE if k[0] == key[0] and k[3] == key[3]]:
            del _LOAD_CACHE[old]
        _LOAD_CACHE[key] = deepcopy(data)
    return data


def _load_uncached(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    data = deepcopy(default)
    try:
        if path.exists():
            raw = json.loads(path.read_text(encoding='utf-8'))
            if isinstance(raw, dict):
                for k, v in raw.items():
                    if isinstance(v, dict) and isinstance(data.get(k), dict):
                        data[k].update(v)
                    else:
                        data[k] = v
    except Exception:
        pass
    return data


def _save(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)


def profile_path() -> Path:
    return _project_dir() / 'project_profile_v18.json'


def ui_path() -> Path:
    return _project_dir() / 'ui_settings_v18.json'


def load_profile() -> dict[str, Any]:
    return _load(profile_path(), DEFAULT_PROFILE)


def save_profile(data: dict[str, Any]) -> None:
    _save(profile_path(), data)


def load_ui() -> dict[str, Any]:
    return _load(ui_path(), DEFAULT_UI)


def save_ui(data: dict[str, Any]) -> None:
    _save(ui_path(), data)
