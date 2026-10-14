from __future__ import annotations

import json, re, subprocess, sys, tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox, filedialog

from project_registry import ProjectRegistry, ProjectEntry
from project_center_stage15 import ProjectWizard
from ui_stage18_3 import fa
from ui_stage18_4 import build_brand_widget_184, attach_table_visuals_recursive

VERSION='18.4'


def _safe_name(text: str) -> str:
    s=re.sub(r'[<>:"/\\|?*]+','_',str(text or '').strip())
    return s[:80] or 'project'


class ProjectCenter184(tk.Tk):
    """Persistent 18.4 project center with project shortcuts, New/Open, and closable tabs."""
    def __init__(self,base_dir: str|Path):
        super().__init__(); self.base_dir=Path(base_dir)
        self.title(f'BARKAV {VERSION} — مرکز پروژه‌ها'); self.geometry('1020x650'); self.minsize(860,540)
        self.configure(bg='#071523'); self.processes={}; self.closed_tabs=set(); self._tab_project_ids={}
        sp=self.base_dir/'secrets.local.json'; self.secrets=json.loads(sp.read_text(encoding='utf-8')) if sp.exists() else {}
        self.registry=ProjectRegistry(self.base_dir); self.registry.ensure_legacy_project(self.secrets)
        self.shortcut_dir=self.base_dir/'data'/'project_shortcuts'; self.shortcut_dir.mkdir(parents=True,exist_ok=True)
        self._ensure_project_shortcuts()
        self._build(); self.refresh_tabs(); self.protocol('WM_DELETE_WINDOW',self.close_center)
        try:self.iconbitmap(default=str(self.base_dir/'assets'/'BARKAV_18_4.ico'))
        except Exception:
            try:self.iconbitmap(default=str(self.base_dir/'assets'/'BARKAV.ico'))
            except Exception:pass

    def _build(self):
        head=tk.Frame(self,bg='#0B1B2C',height=86,highlightbackground='#35516C',highlightthickness=1);head.pack(fill='x');head.pack_propagate(False)
        brand=build_brand_widget_184(head,self.base_dir/'assets'/'barkav_brand_header.png',bg='#0B1B2C',fg='#F4F7FA',compact=True);brand.pack(side='left',padx=(16,6),pady=8)
        tk.Label(head,text='مرکز پروژه‌ها',bg='#0B1B2C',fg='#F4F7FA',font=('Segoe UI',16,'bold')).pack(side='right',padx=20,pady=17)
        tk.Label(head,text='پروژه‌ها به‌صورت تب باز می‌مانند',bg='#0B1B2C',fg='#9BAFC1',font=('Segoe UI',10)).pack(side='right')
        tk.Button(head,text='پروژه جدید',command=self.project_new_or_open,bg='#17334F',fg='#F4F7FA',relief='flat',padx=14,pady=7).pack(side='left',padx=8)
        tk.Button(head,text='بروزرسانی',command=self.refresh_tabs,bg='#17334F',fg='#F4F7FA',relief='flat',padx=14,pady=7).pack(side='left',padx=4)
        self.nb=ttk.Notebook(self);self.nb.pack(fill='both',expand=True,padx=12,pady=12)
        self.nb.bind('<Button-1>',self._tab_click,add='+')
        self.info=tk.StringVar(value='');tk.Label(self,textvariable=self.info,bg='#071523',fg='#9BAFC1',font=('Segoe UI',10,'bold')).pack(fill='x',padx=14,pady=(0,10),anchor='e')

    def _shortcut_path(self,p:ProjectEntry)->Path:
        return self.shortcut_dir/f'{_safe_name(p.name)}_{p.project_id}.barkav'

    def _write_shortcut(self,p:ProjectEntry)->Path:
        path=self._shortcut_path(p)
        payload={
            'format':'BARKAV_PROJECT_SHORTCUT','version':1,'project_id':p.project_id,'name':p.name,
            'db_path':p.db_path,'group_chat_id':p.group_chat_id,'spreadsheet_name':p.spreadsheet_name,
            'address':p.address,'postal_code':p.postal_code,'registration_plate':p.registration_plate,
            'municipal_file_no':p.municipal_file_no,'telegram_verified':p.telegram_verified,
        }
        path.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8');return path

    def _ensure_project_shortcuts(self):
        for p in self.registry.list():
            try:self._write_shortcut(p)
            except Exception:pass

    def _status_text(self):
        # Explicit labels/separator avoid bidi joining that could visually look like "11" for 1 + 1.
        total=fa(len(self.registry.list())); opened=fa(sum(1 for p in self.processes.values() if p.poll() is None))
        return f'پروژه‌های باز: {opened}    •    کل پروژه‌ها: {total}'

    def refresh_tabs(self):
        for pid,p in list(self.processes.items()):
            if p.poll() is not None:self.processes.pop(pid,None)
        for t in self.nb.tabs():self.nb.forget(t)
        self._tab_project_ids={}
        for p in self.registry.list():
            if p.project_id in self.closed_tabs:continue
            tab=ttk.Frame(self.nb,padding=20);label=f'{fa(p.name)}  ({fa(p.project_id)})  ×';self.nb.add(tab,text=label)
            self._tab_project_ids[str(tab)]=p.project_id
            tab.grid_columnconfigure(0,weight=1)
            card=tk.Frame(tab,bg='#102238',highlightbackground='#35516C',highlightthickness=1);card.grid(row=0,column=0,sticky='nsew',padx=12,pady=12);card.grid_columnconfigure(0,weight=1)
            tk.Label(card,text=fa(p.name),bg='#102238',fg='#F4F7FA',font=('Segoe UI',18,'bold'),anchor='e').grid(row=0,column=0,sticky='ew',padx=18,pady=(18,5))
            details=[('کد پروژه',fa(p.project_id)),('Group ID',fa(p.group_chat_id or '-')),('Google Sheet',fa(p.spreadsheet_name or '-')),('آدرس',fa(p.address or '-')),('پرونده شهرداری',fa(p.municipal_file_no or '-'))]
            for i,(k,v) in enumerate(details,1):
                row=tk.Frame(card,bg='#102238',highlightbackground='#1C3348',highlightthickness=1);row.grid(row=i,column=0,sticky='ew',padx=18,pady=3)
                tk.Label(row,text=k,bg='#102238',fg='#9BAFC1',width=22,anchor='e',font=('Segoe UI',10)).pack(side='right',padx=8,pady=6)
                tk.Label(row,text=v,bg='#102238',fg='#F4F7FA',anchor='e',font=('Segoe UI',10)).pack(side='right',fill='x',expand=True,padx=8)
            opened=p.project_id in self.processes and self.processes[p.project_id].poll() is None
            foot=tk.Frame(card,bg='#102238');foot.grid(row=len(details)+1,column=0,sticky='ew',padx=18,pady=18)
            tk.Label(foot,text=f"وضعیت: {'باز است' if opened else 'آماده'}",bg='#102238',fg='#46C48E' if opened else '#9BAFC1',font=('Segoe UI',10,'bold')).pack(side='right')
            tk.Button(foot,text='باز کردن پروژه' if not opened else 'پروژه در حال اجراست',state='normal' if not opened else 'disabled',command=lambda x=p:self.open_project(x),bg='#24B7C6',fg='#071523',activebackground='#45A5EB',relief='flat',font=('Segoe UI',11,'bold'),padx=20,pady=8).pack(side='left')
            tk.Label(foot,text=f'میانبر: {self._shortcut_path(p).name}',bg='#102238',fg='#7890A5',font=('Segoe UI',8)).pack(side='left',padx=8)
        self.info.set(self._status_text())
        self.after_idle(lambda:attach_table_visuals_recursive(self,light=False))

    def _tab_click(self,event):
        try:
            idx=self.nb.index(f'@{event.x},{event.y}'); bbox=self.nb.bbox(idx)
            if not bbox:return
            x,y,w,h=bbox
            # Allow the visible × at either visual edge because RTL font shaping can move it.
            if not (event.x<=x+28 or event.x>=x+w-28):return
            tid=self.nb.tabs()[idx]; pid=self._tab_project_ids.get(str(tid))
            if pid:self.close_project(pid)
        except Exception:pass

    def close_project(self,pid:str):
        proc=self.processes.pop(pid,None)
        if proc and proc.poll() is None:
            try:
                proc.terminate();proc.wait(timeout=3)
            except Exception:
                try:proc.kill()
                except Exception:pass
        self.closed_tabs.add(pid);self.refresh_tabs()

    def open_project(self,p:ProjectEntry):
        self.closed_tabs.discard(p.project_id)
        if p.project_id in self.processes and self.processes[p.project_id].poll() is None:return
        self.registry.set_active(p.project_id)
        proc=subprocess.Popen([sys.executable,str(self.base_dir/'project_runner_stage18_4.py'),p.project_id],cwd=str(self.base_dir))
        self.processes[p.project_id]=proc;self.info.set(f'پروژه «{p.name}» باز شد.');self.after(250,self.refresh_tabs)

    def project_new_or_open(self):
        win=tk.Toplevel(self);win.title('پروژه — New / Open');win.transient(self);win.grab_set();win.resizable(False,False);win.configure(bg='#0B1B2C')
        tk.Label(win,text='پروژه جدید یا پروژه موجود؟',bg='#0B1B2C',fg='#F4F7FA',font=('Segoe UI',13,'bold')).pack(padx=28,pady=(22,12))
        bar=tk.Frame(win,bg='#0B1B2C');bar.pack(padx=24,pady=(0,24))
        tk.Button(bar,text='New',command=lambda:(win.destroy(),self.new_project()),bg='#24B7C6',fg='#071523',font=('Segoe UI',11,'bold'),relief='flat',padx=28,pady=9).pack(side='right',padx=6)
        tk.Button(bar,text='Open',command=lambda:(win.destroy(),self.open_shortcut()),bg='#17334F',fg='#F4F7FA',font=('Segoe UI',11,'bold'),relief='flat',padx=28,pady=9).pack(side='right',padx=6)

    def new_project(self):
        ProjectWizard(self,self.registry,self.secrets,on_done=self._new_done)

    def _new_done(self,p:ProjectEntry):
        try:self._write_shortcut(p)
        except Exception:pass
        self.closed_tabs.discard(p.project_id);self.refresh_tabs();self.info.set(f'پروژه {p.name} ساخته شد.')

    def open_shortcut(self):
        path=filedialog.askopenfilename(parent=self,title='انتخاب میانبر پروژه BARKAV',filetypes=[('BARKAV Project','*.barkav'),('All files','*.*')])
        if not path:return
        try:
            d=json.loads(Path(path).read_text(encoding='utf-8'))
            if d.get('format')!='BARKAV_PROJECT_SHORTCUT':raise ValueError('فایل انتخاب‌شده میانبر پروژه BARKAV نیست.')
            pid=str(d.get('project_id') or '').strip();p=self.registry.get(pid)
            if not p:
                db=Path(str(d.get('db_path') or ''))
                if not db.is_absolute():db=(Path(path).parent/db).resolve()
                if not db.exists():raise FileNotFoundError(f'فایل دیتابیس پروژه پیدا نشد:\n{db}')
                p=ProjectEntry(project_id=pid or self.registry._next_id(),name=str(d.get('name') or pid or 'پروژه'),db_path=str(db),
                    group_chat_id=d.get('group_chat_id'),spreadsheet_name=str(d.get('spreadsheet_name') or ''),address=str(d.get('address') or ''),
                    postal_code=str(d.get('postal_code') or ''),registration_plate=str(d.get('registration_plate') or ''),municipal_file_no=str(d.get('municipal_file_no') or ''),
                    telegram_verified=bool(d.get('telegram_verified')),created_at='')
                rows=[x.__dict__ for x in self.registry.list()];rows.append(p.__dict__);self.registry.data['projects']=rows;self.registry.save()
            self.closed_tabs.discard(p.project_id);self.refresh_tabs();self.open_project(p)
        except Exception as exc:messagebox.showerror('Open Project',str(exc),parent=self)

    def close_center(self):
        # Keep project windows alive; the center is only the workspace/launcher.
        self.destroy()


def run_project_center(base_dir: str|Path):
    app=ProjectCenter184(base_dir);app.mainloop()

if __name__=='__main__':run_project_center(Path(__file__).resolve().parent)
