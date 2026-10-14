from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

from PIL import ImageGrab


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT.parent / '_visual_review'
sys.path.insert(0, str(ROOT))


def main() -> None:
    with tempfile.TemporaryDirectory(prefix='barkav_186_capture_') as temp_dir:
        os.environ['STAGE4_DB_PATH'] = str(Path(temp_dir) / 'capture.sqlite3')
        os.environ.setdefault('TELEGRAM_BOT_TOKEN', 'capture-token')
        os.environ.setdefault('GEMINI_API_KEY', 'capture-gemini')
        os.environ.setdefault('ADMIN_USER_ID', '186')
        os.environ.setdefault('GROUP_CHAT_ID', '-100186')
        from v18_store import load_ui, save_ui
        ui = load_ui()
        ui.update({
            'appearance': 'dark', 'font_size': 10, 'row_height': 31,
            'currency_unit': 'تومان', 'usd_rate_current': 70_000,
        })
        save_ui(ui)
        import dashboard_stage18_6 as dashboard
        dashboard.v185.fetch_tgju_usd_toman = lambda timeout=6.0: (70_000, '2026-08-20T12:00:00')
        app = dashboard.Stage186Dashboard()
        app.geometry('1280x720+30+30')
        for tab_id in app.notebook.tabs():
            if app.notebook.tab(tab_id, 'text') == 'داشبورد':
                app.notebook.select(tab_id)
                break
        app.update_idletasks()
        app.update()
        time.sleep(0.7)
        app.update_idletasks()
        app.update()
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        def grab(window, name: str):
            window.update_idletasks()
            window.update()
            left, top = window.winfo_rootx(), window.winfo_rooty()
            path = OUTPUT_DIR / name
            ImageGrab.grab((left, top, left + window.winfo_width(), top + window.winfo_height())).save(path)
            print(path)

        grab(app, 'BARKAV_18.6_dashboard.png')
        for tab_id in app.notebook.tabs():
            if app.notebook.tab(tab_id, 'text') == 'ثبت دیتا':
                app.notebook.select(tab_id)
                break
        grab(app, 'BARKAV_18.6_data_entry.png')

        dialog = dashboard.ProjectSettingsDialog186(app)
        dialog.geometry('1180x760+70+45')
        dialog.vars['floor_count'].set('۴')
        dialog.vars['parking_floor_count'].set('۱')
        dialog.vars['negative_floor_count'].set('۱')
        dialog.rebuild_floor_rows(preserve=False)
        dialog.nb.select(1)
        grab(dialog, 'BARKAV_18.6_project_floors.png')
        dialog.nb.select(2)
        grab(dialog, 'BARKAV_18.6_project_team.png')
        dialog.destroy()
        app.destroy()


if __name__ == '__main__':
    main()
