"""Open the read-only dashboard prototype in a pywebview window.

Run from ``app/`` with the worktree's venv (see docs/PYWEBVIEW_MIGRATION_PLAN_19_1_1.md):

    ..\\.venv-webui\\Scripts\\python.exe -m webui.app [--registry PATH | --db PATH] [--project PRJ-001] [--dump] [--debug]

``--dump`` prints the bridge's JSON envelope and exits without a window
(no pywebview import), which is what tests and headless checks use.
This entry point is independent of launcher_stage18_7.py and writes nothing
to the project: no instance guard, no bot, no settings.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
FRONTEND = Path(__file__).resolve().parent / 'frontend' / 'index.html'
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from webui.bridge import DashboardBridge  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='BARKAV read-only pywebview dashboard prototype')
    parser.add_argument('--project', help='project id from the registry (default: active/first)')
    parser.add_argument('--db', help='read this SQLite file instead of the registry project')
    parser.add_argument('--registry', help='project_registry.json to use (default: app/data or ../data)')
    parser.add_argument('--dump', action='store_true', help='print the summary JSON and exit')
    parser.add_argument('--debug', action='store_true', help='enable WebView2 dev tools')
    args = parser.parse_args(argv)

    bridge = DashboardBridge(APP_DIR, project_id=args.project, db_path=args.db,
                             registry_path=args.registry)
    if args.dump:
        result = bridge.get_dashboard_summary(force_refresh=True)
        sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        return 0 if result['ok'] else 1

    import webview  # only the window path needs pywebview

    webview.create_window(
        'BARKAV — داشبورد (نمونهٔ فقط‌خواندنی)', url=str(FRONTEND), js_api=bridge,
        width=1280, height=820, min_size=(960, 640), background_color='#0E141B',
        text_select=True,
    )
    icon = APP_DIR / 'assets' / 'BARKAV.ico'
    webview.start(
        gui='edgechromium' if sys.platform == 'win32' else None,
        debug=args.debug, private_mode=True,
        icon=str(icon) if icon.is_file() else None,
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
