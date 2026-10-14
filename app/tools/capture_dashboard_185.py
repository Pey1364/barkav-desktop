from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

from PIL import ImageGrab


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT.parent / "_visual_review" / "BARKAV_18.5_before.png"
sys.path.insert(0, str(ROOT))


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="barkav_185_capture_") as temp_dir:
        os.environ["STAGE4_DB_PATH"] = str(Path(temp_dir) / "capture.sqlite3")
        os.environ.setdefault("TELEGRAM_BOT_TOKEN", "capture-token")
        os.environ.setdefault("GEMINI_API_KEY", "capture-gemini")
        os.environ.setdefault("ADMIN_USER_ID", "185")
        os.environ.setdefault("GROUP_CHAT_ID", "-100185")

        import dashboard_stage18_5 as dashboard

        dashboard.fetch_tgju_usd_toman = lambda timeout=6.0: (70_000, "2026-08-20T12:00:00")
        app = dashboard.Stage185Dashboard()
        app.geometry("1280x760+30+30")
        app.update_idletasks()
        app.update()
        time.sleep(0.6)
        app.update_idletasks()
        app.update()
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        left = app.winfo_rootx()
        top = app.winfo_rooty()
        width = app.winfo_width()
        height = app.winfo_height()
        ImageGrab.grab((left, top, left + width, top + height)).save(OUTPUT)
        app.destroy()
        print(OUTPUT)


if __name__ == "__main__":
    main()
