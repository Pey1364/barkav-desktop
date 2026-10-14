from __future__ import annotations
import os, sys, subprocess
from pathlib import Path
from project_registry import ProjectRegistry, apply_project_environment
BASE=Path(__file__).resolve().parent

def main():
    if len(sys.argv)<2:raise SystemExit('project id required')
    p=ProjectRegistry(BASE).get(sys.argv[1])
    if not p:raise SystemExit('project not found')
    apply_project_environment(p);os.environ.setdefault('PEYMAAN_TIMEZONE','Asia/Tehran');os.environ['STAGE4_REQUIRE_TEST_TAG']='false'
    from dashboard_stage18_4 import Stage184Dashboard
    log=BASE/'runtime'/'telegram_bot_18_4.log';log.parent.mkdir(parents=True,exist_ok=True);fp=None;bot=None
    try:
        try:
            fp=log.open('a',encoding='utf-8',buffering=1);env=os.environ.copy();env['PYTHONUNBUFFERED']='1';bot=subprocess.Popen([sys.executable,'-u',str(BASE/'telegram_stage15.py')],cwd=str(BASE),env=env,stdout=fp,stderr=subprocess.STDOUT,text=True)
        except Exception:bot=None
        while True:
            app=Stage184Dashboard()
            if bot:app.set_bot_process(bot,log)
            app.mainloop()
            if not getattr(app,'_restart_requested',False):break
    finally:
        if bot and bot.poll() is None:
            bot.terminate()
            try:bot.wait(timeout=5)
            except Exception:bot.kill()
        if fp:fp.close()
if __name__=='__main__':main()
