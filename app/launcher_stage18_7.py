from __future__ import annotations

import importlib.util
import json
import os
import sys
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
from runtime_base import frozen, local_secrets_path


BASE = Path(__file__).resolve().parent
LOG_DIR = BASE / 'runtime'
STARTUP_LOG = LOG_DIR / 'startup_18_7.log'
REQUIRED_MODULES = {
    'PIL': 'Pillow', 'telegram': 'python-telegram-bot', 'google.genai': 'google-genai',
    'jdatetime': 'jdatetime', 'reportlab': 'reportlab', 'pypdfium2': 'pypdfium2',
}


def _log(text: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with STARTUP_LOG.open('a', encoding='utf-8') as handle:
        handle.write(str(text) + '\n')


def dialog(title: str, text: str, kind: str = 'error') -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        getattr(messagebox, 'show' + kind)(title, text, parent=root)
    finally:
        root.destroy()


def preflight_report(base_dir: str | Path = BASE) -> tuple[list[str], list[str]]:
    base = Path(base_dir)
    errors: list[str] = []
    warnings: list[str] = []
    if sys.version_info < (3, 10):
        errors.append('Python 3.10 یا جدیدتر لازم است.')
    missing = [package for module, package in REQUIRED_MODULES.items() if importlib.util.find_spec(module) is None]
    if missing:
        errors.append('وابستگی‌های نصب‌نشده: ' + '، '.join(missing))
    secret_path = local_secrets_path(base)
    if secret_path is None:
        errors.append('فایل secrets.local.json پیدا نشد؛ آن را فقط به‌صورت محلی از نسخهٔ فعال کپی کنید.')
    else:
        try:
            secrets = json.loads(secret_path.read_text(encoding='utf-8'))
            missing_keys = [key for key in ('TELEGRAM_BOT_TOKEN', 'GEMINI_API_KEY', 'ADMIN_USER_ID') if not secrets.get(key)]
            if missing_keys:
                errors.append('کلیدهای ضروری فایل تنظیمات محلی کامل نیستند.')
        except Exception:
            errors.append('ساختار JSON فایل تنظیمات محلی معتبر نیست.')
    data_dir = base / 'data'
    # In the source layout, entrypoints live under ``app/`` and the live
    # registry/database live beside it at the release root.  Keep portable
    # bundles using app/data, but route this layout to its sibling data folder.
    sibling_data = base.parent / 'data'
    if not (data_dir / 'project_registry.json').is_file() and (
        sibling_data / 'project_registry.json'
    ).is_file():
        data_dir = sibling_data
    registry = data_dir / 'project_registry.json'
    databases = list(data_dir.glob('*.sqlite3')) if data_dir.is_dir() else []
    if not registry.is_file() and not databases:
        errors.append('دادهٔ پروژه پیدا نشد؛ پوشهٔ data نسخهٔ فعال را پس از تهیهٔ پشتیبان به ۱۸.۷ منتقل کنید.')
    if not frozen() and not (base / 'BARKAV_19.1.1.bat').is_file():
        warnings.append('فایل اجرای BARKAV_19.1.1.bat پیدا نشد.')
    return errors, warnings


def preflight() -> bool:
    errors, warnings = preflight_report(BASE)
    for warning in warnings:
        _log('WARNING: ' + warning)
    if errors:
        for error in errors:
            _log('ERROR: ' + error)
        dialog('BARKAV 19.1.1 — بررسی شروع', '\n\n'.join(errors))
        return False
    _log('Preflight passed (secret values were not logged).')
    return True


def main():
    # Cloud-format dispatch: the same launcher also starts an isolated project
    # runner when the Hub opens one in a subprocess.
    if len(sys.argv) > 1 and sys.argv[1] == "--run-project":
        if len(sys.argv) < 3:
            raise SystemExit("project id required")
        from project_runner_stage18_7 import run_project, ProjectRegistry
        project = ProjectRegistry(BASE).get(sys.argv[2])
        if project:
            run_project(project)
        return
    # Packaged as one exe, telegram_stage18_7.py is not a separate file on
    # disk a subprocess can be pointed at any more - project_runner_stage18_7's
    # start_bot() re-launches THIS SAME exe with this internal flag instead
    # (see runtime_base.self_reexec_args). Dev mode is unchanged: the loose
    # script's own argv-based main() still runs directly.
    if len(sys.argv) > 1 and sys.argv[1] == "--run-bot":
        import telegram_stage18_7
        telegram_stage18_7.main()
        return

    os.environ.setdefault("PEYMAAN_TIMEZONE", "Asia/Tehran")
    os.environ["STAGE4_REQUIRE_TEST_TAG"] = "false"
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    STARTUP_LOG.write_text("=== BARKAV 19.1.1 STARTUP ===\n", encoding="utf-8")
    try:
        if not preflight():
            return
        # The old tabbed center remains available explicitly; the default
        # startup is now the cloud-style Project Hub.
        if os.environ.get("BARKAV_PROJECT_CENTER") == "1":
            from project_center_stage18_7 import run_project_center
            _log("Opening legacy project center 18.7.1")
            run_project_center(BASE)
            return
        from project_registry import ProjectRegistry
        registry = ProjectRegistry(BASE)
        open_path = Path(sys.argv[1]) if len(sys.argv) > 1 and Path(sys.argv[1]).suffix.lower() == '.brk' else None
        if open_path is not None:
            from project_center_stage18_6 import validate_project_shortcut
            shortcut_data = json.loads(open_path.read_text(encoding='utf-8'))
            project, is_new = validate_project_shortcut(shortcut_data, open_path, registry.list())
            if is_new:
                rows = [item.__dict__ for item in registry.list()]
                rows.append(project.__dict__)
                registry.data['projects'] = rows
                registry.save()
            open_path.touch()
            _log(f"Opening validated project shortcut {open_path.name}")
        else:
            projects = registry.list()
            active_id = str(registry.data.get('active_project_id') or '')
            project = registry.get(active_id) if active_id else None
            if project is None and projects:
                project = projects[0]
                _log(f"No valid active project; using first registered project {project.project_id}")

        if project is None:
            _log('No registered project; opening the single-window project hub')
            from barkav_bare_launcher_187 import run_bare_launcher
            run_bare_launcher(BASE)
            return

        # Run the dashboard in this process. The dashboard already contains
        # Start and project tabs; opening the Hub first used to leave extra
        # Tk roots/process windows behind it.
        os.environ['BARKAV_LAND_ON_START187'] = '1'
        _log(f"Opening single-window dashboard for project {project.project_id}")
        from project_runner_stage18_7 import run_project
        run_project(project)
    except Exception as exc:
        _log(traceback.format_exc())
        dialog("BARKAV 19.1.1", f"خطا در اجرای برنامه:\n{exc}\n\nجزئیات در runtime/startup_18_7.log ذخیره شد.")


if __name__ == '__main__':
    main()
