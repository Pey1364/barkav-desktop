from __future__ import annotations
import subprocess
import sys
from pathlib import Path

BASE=Path(__file__).resolve().parent


def main():
    bot=subprocess.Popen([sys.executable,str(BASE/'telegram_stage11.py')],cwd=str(BASE))
    try:
        from dashboard_stage11 import Stage11Dashboard
        Stage11Dashboard().mainloop()
    finally:
        if bot.poll() is None:
            bot.terminate()
            try:bot.wait(timeout=8)
            except subprocess.TimeoutExpired:bot.kill()


if __name__=='__main__':
    main()
