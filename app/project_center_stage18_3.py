from __future__ import annotations
import json, subprocess, sys, tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox
from project_registry import ProjectRegistry, ProjectEntry
from project_center_stage15 import ProjectWizard
from ui_stage18_3 import fa

class ProjectCenter183(tk.Tk):
    """Persistent project center: every project is a tab and opening it does not close the center."""
    def __init__(self,base_dir: str|Path):
        super().__init__();self.base_dir=Path(base_dir);self.title('BARKAV 18.3 — مرکز پروژه‌ها');self.geometry('980x620');self.minsize(820,520)
        self.configure(bg='#071523');self.processes={}
        sp=self.base_dir/'secrets.local.json';self.secrets=json.loads(sp.read_text(encoding='utf-8')) if sp.exists() else {}
        self.registry=ProjectRegistry(self.base_dir);self.registry.ensure_legacy_project(self.secrets)
        self._build();self.refresh_tabs();self.protocol('WM_DELETE_WINDOW',self.close_all)
        try:self.iconbitmap(default=str(self.base_dir/'assets'/'BARKAV.ico'))
        except Exception:pass
    def _build(self):
        head=tk.Frame(self,bg='#0B1B2C',height=72,highlightbackground='#35516C',highlightthickness=1);head.pack(fill='x');head.pack_propagate(False)
        tk.Label(head,text='مرکز پروژه‌ها',bg='#0B1B2C',fg='#F4F7FA',font=('Segoe UI',16,'bold')).pack(side='right',padx=20,pady=17)
        tk.Label(head,text='هر پروژه در یک تب مستقل — مرکز پروژه‌ها باز می‌ماند',bg='#0B1B2C',fg='#9BAFC1',font=('Segoe UI',10)).pack(side='right')
        tk.Button(head,text='پروژه جدید',command=self.new_project,bg='#17334F',fg='#F4F7FA',relief='flat',padx=14,pady=7).pack(side='left',padx=8)
        tk.Button(head,text='بروزرسانی',command=self.refresh_tabs,bg='#17334F',fg='#F4F7FA',relief='flat',padx=14,pady=7).pack(side='left',padx=4)
        self.nb=ttk.Notebook(self);self.nb.pack(fill='both',expand=True,padx=12,pady=12)
        self.info=tk.StringVar(value='');tk.Label(self,textvariable=self.info,bg='#071523',fg='#9BAFC1',font=('Segoe UI',9)).pack(fill='x',padx=14,pady=(0,10),anchor='e')
    def refresh_tabs(self):
        # Refresh process state and rebuild project tabs deterministically.
        for pid,p in list(self.processes.items()):
            if p.poll() is not None:self.processes.pop(pid,None)
        current={self.nb.tab(t,'text'):t for t in self.nb.tabs()}
        for t in self.nb.tabs():self.nb.forget(t)
        for p in self.registry.list():
            tab=ttk.Frame(self.nb,padding=20);label=f'{p.name}  ({p.project_id})';self.nb.add(tab,text=label)
            tab.grid_columnconfigure(0,weight=1)
            card=tk.Frame(tab,bg='#102238',highlightbackground='#35516C',highlightthickness=1);card.grid(row=0,column=0,sticky='nsew',padx=12,pady=12);card.grid_columnconfigure(0,weight=1)
            tk.Label(card,text=p.name,bg='#102238',fg='#F4F7FA',font=('Segoe UI',18,'bold'),anchor='e').grid(row=0,column=0,sticky='ew',padx=18,pady=(18,5))
            details=[('کد پروژه',p.project_id),('Group ID',p.group_chat_id or '-'),('Google Sheet',p.spreadsheet_name or '-'),('آدرس',p.address or '-'),('پرونده شهرداری',p.municipal_file_no or '-')]
            for i,(k,v) in enumerate(details,1):
                row=tk.Frame(card,bg='#102238',highlightbackground='#29415A',highlightthickness=1);row.grid(row=i,column=0,sticky='ew',padx=18,pady=3);tk.Label(row,text=k,bg='#102238',fg='#9BAFC1',width=22,anchor='e').pack(side='right',padx=8,pady=6);tk.Label(row,text=fa(v),bg='#102238',fg='#F4F7FA',anchor='e').pack(side='right',fill='x',expand=True,padx=8)
            opened=p.project_id in self.processes
            status='باز است' if opened else 'آماده'
            foot=tk.Frame(card,bg='#102238');foot.grid(row=len(details)+1,column=0,sticky='ew',padx=18,pady=18)
            tk.Label(foot,text=f'وضعیت: {status}',bg='#102238',fg='#46C48E' if opened else '#9BAFC1',font=('Segoe UI',10,'bold')).pack(side='right')
            tk.Button(foot,text='باز کردن پروژه' if not opened else 'پروژه در حال اجراست',state='normal' if not opened else 'disabled',command=lambda x=p:self.open_project(x),bg='#24B7C6',fg='#071523',activebackground='#45A5EB',relief='flat',font=('Segoe UI',11,'bold'),padx=20,pady=8).pack(side='left')
        self.info.set(f'{fa(len(self.registry.list()))} پروژه | پروژه‌های باز: {fa(len(self.processes))}')
    def open_project(self,p:ProjectEntry):
        if p.project_id in self.processes and self.processes[p.project_id].poll() is None:return
        self.registry.set_active(p.project_id)
        env=None
        proc=subprocess.Popen([sys.executable,str(self.base_dir/'project_runner_stage18_3.py'),p.project_id],cwd=str(self.base_dir),env=env)
        self.processes[p.project_id]=proc;self.info.set(f'پروژه «{p.name}» باز شد. مرکز پروژه‌ها باز می‌ماند.');self.after(250,self.refresh_tabs)
    def new_project(self):ProjectWizard(self,self.registry,self.secrets,on_done=lambda p:(self.refresh_tabs(),self.info.set(f'پروژه {p.name} ساخته شد.')))
    def close_all(self):
        # Closing the project center does not force running project windows closed; this mirrors a launcher/workspace.
        self.destroy()

def run_project_center(base_dir: str|Path):
    app=ProjectCenter183(base_dir);app.mainloop()

if __name__=='__main__':run_project_center(Path(__file__).resolve().parent)
