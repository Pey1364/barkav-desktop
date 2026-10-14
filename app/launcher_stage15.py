from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from project_center_stage15 import choose_project
from project_registry import apply_project_environment

BASE=Path(__file__).resolve().parent


def main():
    project=choose_project(BASE)
    if project is None:
        return
    apply_project_environment(project)
    env=os.environ.copy()
    bot=subprocess.Popen([sys.executable,str(BASE/'telegram_stage15.py')],cwd=str(BASE),env=env)
    try:
        # Import only after the selected project's environment has been applied;
        # dashboard modules construct their DB singleton during import.
        from dashboard_stage15 import Stage15Dashboard
        Stage15Dashboard().mainloop()
    finally:
        if bot.poll() is None:
            bot.terminate()
            try:bot.wait(timeout=8)
            except subprocess.TimeoutExpired:bot.kill()


if __name__=='__main__':
    main()
