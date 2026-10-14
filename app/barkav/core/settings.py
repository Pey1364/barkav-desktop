from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any


def _project_dir() -> Path:
    raw = os.getenv('STAGE4_DB_PATH') or 'data/stage4_test.sqlite3'
    p = Path(raw)
    if not p.is_absolute():
        p = Path(__file__).resolve().parents[2] / p
    p.parent.mkdir(parents=True, exist_ok=True)
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
    'font_family': 'Segoe UI',
    'font_weight': 400,
    'font_size': 11,
    'language': 'fa',
    'appearance': 'dark',
    'background_color': 'پیش‌فرض',
    'row_height': 40,
    'open_maximized': True,
    'currency_unit': 'تومان',
    'usd_rate_current': 0,
    'usd_rate_baseline': 0,
    'external_injection': 0,
}


def _load(path: Path, default: dict[str, Any]) -> dict[str, Any]:
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
