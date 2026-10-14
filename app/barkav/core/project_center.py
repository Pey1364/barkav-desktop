"""Standalone Project Center runtime extracted from active BARKAV 18.7."""
from __future__ import annotations

# Consolidated Project Center layer 1
import asyncio
import json
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from project_registry import ProjectEntry, ProjectRegistry


class ProjectCenter(tk.Tk):
    def __init__(self, base_dir: str | Path):
        super().__init__()
        self.base_dir=Path(base_dir)
        self.title("Peymaan — مرکز پروژه‌ها")
        self.geometry("760x470")
        self.minsize(680,420)
        self.configure(bg="#09111D")
        self.result: ProjectEntry | None=None
        secrets_path=self.base_dir/"secrets.local.json"
        self.secrets=json.loads(secrets_path.read_text(encoding="utf-8")) if secrets_path.exists() else {}
        self.registry=ProjectRegistry(self.base_dir)
        self.registry.ensure_legacy_project(self.secrets)
        self._build();self._refresh()
        self.protocol("WM_DELETE_WINDOW",self.destroy)

    def _build(self):
        head=tk.Frame(self,bg="#0B1726",height=64);head.pack(fill="x");head.pack_propagate(False)
        tk.Label(head,text="PEYMAAN  •  انتخاب پروژه",bg="#0B1726",fg="white",font=("Tahoma",15,"bold")).pack(side="right",padx=22,pady=16)
        tk.Label(head,text="ابتدا پروژه فعال را انتخاب کن",bg="#0B1726",fg="#DCEAF4",font=("Tahoma",9)).pack(side="right")
        body=ttk.Frame(self,padding=16);body.pack(fill="both",expand=True)
        self.tree=ttk.Treeview(body,columns=("id","name","group","sheet","status"),show="headings",height=12,selectmode="browse")
        for k,t,w in [("id","کد پروژه",90),("name","نام پروژه",220),("group","Group ID",150),("sheet","Google Sheet",150),("status","تلگرام",90)]:
            self.tree.heading(k,text=t);self.tree.column(k,width=w,anchor="center")
        self.tree.pack(fill="both",expand=True)
        self.tree.bind("<Double-1>",lambda e:self.enter_selected())
        foot=ttk.Frame(body);foot.pack(fill="x",pady=(12,0))
        ttk.Button(foot,text="➕ پروژه جدید",command=self.new_project).pack(side="right")
        ttk.Button(foot,text="🔄 بروزرسانی",command=self._refresh).pack(side="right",padx=6)
        ttk.Button(foot,text="ورود به پروژه",command=self.enter_selected).pack(side="left")
        self.info=tk.StringVar(value="")
        ttk.Label(foot,textvariable=self.info).pack(side="left",padx=12)

    def _refresh(self):
        for x in self.tree.get_children(): self.tree.delete(x)
        active=self.registry.data.get("active_project_id")
        for p in self.registry.list():
            iid=self.tree.insert("","end",values=(p.project_id,p.name,p.group_chat_id or "-",p.spreadsheet_name,"✓" if p.telegram_verified else "نیاز به بررسی"))
            if p.project_id==active: self.tree.selection_set(iid);self.tree.focus(iid)

    def _selected(self) -> ProjectEntry | None:
        sel=self.tree.selection()
        if not sel:return None
        pid=str(self.tree.item(sel[0],"values")[0]);return self.registry.get(pid)

    def enter_selected(self):
        p=self._selected()
        if not p:
            messagebox.showwarning("پروژه","یک پروژه را انتخاب کن.",parent=self);return
        if not messagebox.askyesno("ورود به پروژه",f"ورود به «{p.name}» تأیید شود؟",parent=self):return
        self.result=self.registry.set_active(p.project_id);self.destroy()

    def new_project(self):
        ProjectWizard(self,self.registry,self.secrets,on_done=lambda p:(self._refresh(),self.info.set(f"پروژه {p.name} ساخته شد")))


class ProjectWizard(tk.Toplevel):
    def __init__(self,parent,registry:ProjectRegistry,secrets:dict,on_done):
        super().__init__(parent);self.parent=parent;self.registry=registry;self.secrets=secrets;self.on_done=on_done
        self.title("ساخت پروژه جدید");self.geometry("610x480");self.transient(parent);self.grab_set();self.resizable(False,False)
        self.step=0;self.telegram_verified=False
        self.vars={k:tk.StringVar() for k in ("name","address","postal","plate","municipal","group","sheet")}
        self.vars["sheet"].set("")
        self.container=ttk.Frame(self,padding=16);self.container.pack(fill="both",expand=True)
        nav=ttk.Frame(self);nav.pack(fill="x",padx=16,pady=12)
        self.back=ttk.Button(nav,text="قبلی",command=self.prev);self.back.pack(side="right")
        self.next=ttk.Button(nav,text="بعدی",command=self.next_step);self.next.pack(side="left")
        self._render()

    def _clear(self):
        for w in self.container.winfo_children():w.destroy()

    def _row(self,label,key):
        r=ttk.Frame(self.container);r.pack(fill="x",pady=5);ttk.Label(r,text=label,width=24,anchor="e").pack(side="right");ttk.Entry(r,textvariable=self.vars[key],justify="right").pack(side="right",fill="x",expand=True,padx=8)

    def _render(self):
        self._clear();self.back.configure(state="normal" if self.step else "disabled")
        titles=["۱) مشخصات پروژه","۲) گروه تلگرام","۳) بررسی اتصال ربات","۴) Google Sheets و تأیید نهایی"]
        ttk.Label(self.container,text=titles[self.step],font=("Tahoma",12,"bold")).pack(anchor="e",pady=(0,14))
        if self.step==0:
            self._row("نام پروژه","name");self._row("آدرس","address");self._row("کد پستی","postal");self._row("پلاک ثبتی","plate");self._row("شماره پرونده شهرداری","municipal")
        elif self.step==1:
            ttk.Label(self.container,text="ربات را به گروه پروژه اضافه کن، سپس Group ID را وارد کن.",wraplength=540,justify="right").pack(anchor="e",pady=8)
            self._row("Group ID (مثلاً -100...)","group")
            ttk.Label(self.container,text="هر Group ID فقط می‌تواند به یک پروژه متصل باشد.",foreground="#B84B4B").pack(anchor="e",pady=8)
        elif self.step==2:
            ttk.Label(self.container,text="بعد از اضافه‌کردن ربات، روی «بررسی اتصال» بزن. برنامه با Bot API عضویت/دسترسی گروه را بررسی می‌کند.",wraplength=540,justify="right").pack(anchor="e",pady=10)
            self.verify_status=tk.StringVar(value="هنوز بررسی نشده")
            ttk.Button(self.container,text="🔌 بررسی اتصال ربات",command=self.verify_telegram).pack(pady=18)
            ttk.Label(self.container,textvariable=self.verify_status,font=("Tahoma",10,"bold")).pack()
        else:
            if not self.vars["sheet"].get().strip():
                self.vars["sheet"].set(f"PEYMAAN-{self.registry._next_id()}")
            self._row("نام Spreadsheet","sheet")
            ttk.Label(self.container,text="خلاصه",font=("Tahoma",10,"bold")).pack(anchor="e",pady=(18,4))
            txt=f"نام: {self.vars['name'].get()}\nGroup ID: {self.vars['group'].get()}\nاتصال ربات: {'تأیید شده' if self.telegram_verified else 'تأیید نشده'}"
            ttk.Label(self.container,text=txt,justify="right").pack(anchor="e")
            self.next.configure(text="ایجاد پروژه")
        if self.step<3:self.next.configure(text="بعدی")

    def prev(self):
        if self.step>0:self.step-=1;self._render()

    def next_step(self):
        if self.step==0 and not self.vars["name"].get().strip():
            messagebox.showwarning("پروژه","نام پروژه را وارد کن.",parent=self);return
        if self.step==1:
            try:g=int(self.vars["group"].get().strip())
            except Exception:messagebox.showwarning("گروه","Group ID معتبر وارد کن.",parent=self);return
            for p in self.registry.list():
                if p.group_chat_id==g:
                    messagebox.showerror("گروه",f"این گروه قبلاً به «{p.name}» متصل است.",parent=self);return
        if self.step==2 and not self.telegram_verified:
            messagebox.showwarning("اتصال","ابتدا اتصال ربات به گروه را با موفقیت بررسی کن.",parent=self);return
        if self.step<3:self.step+=1;self._render();return
        try:
            p=self.registry.create(name=self.vars["name"].get(),group_chat_id=int(self.vars["group"].get()),spreadsheet_name=self.vars["sheet"].get(),address=self.vars["address"].get(),postal_code=self.vars["postal"].get(),registration_plate=self.vars["plate"].get(),municipal_file_no=self.vars["municipal"].get(),telegram_verified=self.telegram_verified)
            self.on_done(p);self.destroy()
        except Exception as exc:messagebox.showerror("ساخت پروژه",str(exc),parent=self)

    def verify_telegram(self):
        token=str(self.secrets.get("TELEGRAM_BOT_TOKEN") or "").strip()
        if not token:
            messagebox.showerror("Telegram","TELEGRAM_BOT_TOKEN در secrets.local.json نیست.",parent=self);return
        try:gid=int(self.vars["group"].get().strip())
        except Exception:return
        self.verify_status.set("در حال بررسی...");self.update_idletasks()
        async def check():
            from telegram import Bot
            from telegram.request import HTTPXRequest
            req=HTTPXRequest(connect_timeout=20,read_timeout=30,write_timeout=30,pool_timeout=10,http_version="1.1")
            async with Bot(token=token,request=req) as bot:
                me=await bot.get_me();chat=await bot.get_chat(gid);member=await bot.get_chat_member(gid,me.id)
                return str(getattr(chat,"title","") or gid),str(getattr(member,"status","") or "")
        try:
            title,status=asyncio.run(check());self.telegram_verified=status not in {"left","kicked"}
            self.verify_status.set(f"✓ اتصال تأیید شد — {title} ({status})" if self.telegram_verified else f"عضویت معتبر نیست: {status}")
        except Exception as exc:
            self.telegram_verified=False;self.verify_status.set(f"✗ بررسی ناموفق: {exc.__class__.__name__}")
            messagebox.showerror("بررسی اتصال",f"اتصال به گروه تأیید نشد:\n{exc}",parent=self)


def choose_project(base_dir: str | Path) -> ProjectEntry | None:
    app=ProjectCenter(base_dir);app.mainloop();return app.result

# Consolidated Project Center layer 2
import json, re, subprocess, sys, tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox, filedialog

from project_registry import ProjectRegistry, ProjectEntry
from ui import fa
from ui import build_brand_widget_184, attach_table_visuals_recursive

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

if __name__=='__main__':run_project_center(Path(__file__).resolve().parents[2])

# Consolidated Project Center layer 3
import json
import re
import subprocess
import sys
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from project_registry import ProjectEntry
from ui import fa
from ui import build_brand_widget_186, palette_186, style_ttk_186
from v18_store import load_ui


VERSION = '18.6'


def _canonical(path: Path) -> str:
    return str(path.resolve()).casefold()


def validate_project_shortcut(data: dict, shortcut_path: str | Path, projects: list[ProjectEntry]):
    """Validate identity, SQLite target and project isolation before registration."""
    if not isinstance(data, dict) or data.get('format') != 'BARKAV_PROJECT_SHORTCUT':
        raise ValueError('فایل انتخاب‌شده میانبر معتبر پروژه BARKAV نیست.')
    project_id = str(data.get('project_id') or '').strip()
    if not project_id or not re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', project_id):
        raise ValueError('شناسه پروژه در میانبر معتبر نیست.')
    raw_db = str(data.get('db_path') or '').strip()
    if not raw_db:
        raise ValueError('مسیر دیتابیس در میانبر ثبت نشده است.')
    db_path = Path(raw_db)
    if not db_path.is_absolute():
        db_path = (Path(shortcut_path).resolve().parent / db_path).resolve()
    if not db_path.is_file():
        raise FileNotFoundError(f'فایل دیتابیس پروژه پیدا نشد:\n{db_path}')
    try:
        with db_path.open('rb') as handle:
            sqlite_header = handle.read(16)
        if sqlite_header != b'SQLite format 3\x00':
            raise ValueError('فایل معرفی‌شده دیتابیس SQLite معتبر نیست.')
    except PermissionError as exc:
        raise ValueError('دسترسی خواندن دیتابیس پروژه ممکن نیست.') from exc
    group = data.get('group_chat_id')
    if group in (None, '', 0, '0'):
        group = None
    else:
        try:
            group = int(str(group).strip())
        except Exception as exc:
            raise ValueError('Group ID میانبر معتبر نیست.') from exc
    existing = next((project for project in projects if project.project_id == project_id), None)
    if existing:
        if _canonical(Path(existing.db_path)) != _canonical(db_path):
            raise ValueError('این شناسه پروژه قبلاً با دیتابیس دیگری ثبت شده است؛ میانبر بازنویسی نشد.')
        if existing.group_chat_id not in (None, group) and group is not None:
            raise ValueError('Group ID میانبر با پروژه ثبت‌شده یکسان نیست؛ میانبر بازنویسی نشد.')
        return existing, False
    for project in projects:
        if _canonical(Path(project.db_path)) == _canonical(db_path):
            raise ValueError(f'این دیتابیس قبلاً به پروژه «{project.name}» متصل است.')
        if group is not None and project.group_chat_id == group:
            raise ValueError(f'این Group ID قبلاً به پروژه «{project.name}» متصل است.')
    entry = ProjectEntry(
        project_id=project_id,
        name=str(data.get('name') or project_id).strip() or project_id,
        db_path=str(db_path),
        group_chat_id=group,
        spreadsheet_name=str(data.get('spreadsheet_name') or ''),
        address=str(data.get('address') or ''),
        postal_code=str(data.get('postal_code') or ''),
        registration_plate=str(data.get('registration_plate') or ''),
        municipal_file_no=str(data.get('municipal_file_no') or ''),
        telegram_verified=bool(data.get('telegram_verified')),
        created_at='',
    )
    return entry, True


class ProjectCenter186(ProjectCenter184):
    def __init__(self, base_dir: str | Path):
        super().__init__(base_dir)
        self.title(f'BARKAV {VERSION} — مرکز پروژه‌ها')
        try:
            self.iconbitmap(default=str(self.base_dir / 'assets' / 'BARKAV_18_6.ico'))
        except Exception:
            pass

    @property
    def colors(self):
        light = str(load_ui().get('appearance') or 'dark').lower() == 'light'
        return palette_186(light), light

    def _build(self):
        p, light = self.colors
        self.configure(bg=p['bg'])
        style_ttk_186(self, light=light, font_size=int(load_ui().get('font_size') or 10), row_height=31)
        head = tk.Frame(self, bg=p['surface'], height=66, highlightbackground=p['line'], highlightthickness=1)
        head.pack(fill='x')
        head.pack_propagate(False)
        brand = build_brand_widget_186(head, self.base_dir / 'assets' / 'barkav_brand_header.png', bg=p['surface'], fg=p['text'], muted=p['muted'], compact=True)
        brand.pack(side='left', padx=(14, 6), pady=4)
        tk.Label(head, text='مرکز پروژه‌ها', bg=p['surface'], fg=p['text'], font=('Segoe UI', 14, 'bold')).pack(side='right', padx=18, pady=14)
        tk.Label(head, text='پروژه‌ها در تب‌های مستقل مدیریت می‌شوند', bg=p['surface'], fg=p['muted'], font=('Segoe UI', 9)).pack(side='right')
        tk.Button(head, text='پروژه جدید', command=self.project_new_or_open, bg=p['blue'], fg='#FFFFFF',
                  activebackground=p['cyan'], relief='flat', padx=14, pady=7).pack(side='left', padx=8)
        tk.Button(head, text='بروزرسانی', command=self.refresh_tabs, bg=p['glass'], fg=p['text'],
                  activebackground=p['panel2'], relief='flat', padx=14, pady=7).pack(side='left', padx=4)
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill='both', expand=True, padx=12, pady=12)
        self.nb.bind('<Button-1>', self._tab_click, add='+')
        self.info = tk.StringVar(value='')
        tk.Label(self, textvariable=self.info, bg=p['bg'], fg=p['muted'], font=('Segoe UI', 10, 'bold')).pack(fill='x', padx=14, pady=(0, 10), anchor='e')

    def refresh_tabs(self):
        p, _light = self.colors
        for project_id, process in list(self.processes.items()):
            if process.poll() is not None:
                self.processes.pop(project_id, None)
        for tab in self.nb.tabs():
            self.nb.forget(tab)
        self._tab_project_ids = {}
        for project in self.registry.list():
            if project.project_id in self.closed_tabs:
                continue
            tab = ttk.Frame(self.nb, padding=20, style='Panel.TFrame')
            self.nb.add(tab, text=f'{fa(project.name)}  ({fa(project.project_id)})  ×')
            self._tab_project_ids[str(tab)] = project.project_id
            tab.grid_columnconfigure(0, weight=1)
            card = tk.Frame(tab, bg=p['surface'], highlightbackground=p['line'], highlightthickness=1)
            card.grid(row=0, column=0, sticky='nsew', padx=12, pady=12)
            card.grid_columnconfigure(0, weight=1)
            tk.Label(card, text=fa(project.name), bg=p['surface'], fg=p['text'], font=('Segoe UI', 18, 'bold'), anchor='e').grid(row=0, column=0, sticky='ew', padx=18, pady=(18, 5))
            details = [
                ('کد پروژه', fa(project.project_id)), ('Group ID', fa(project.group_chat_id or '-')),
                ('Google Sheet', fa(project.spreadsheet_name or '-')), ('آدرس', fa(project.address or '-')),
                ('پرونده شهرداری', fa(project.municipal_file_no or '-')),
            ]
            for index, (label, value) in enumerate(details, 1):
                row = tk.Frame(card, bg=p['surface'], highlightbackground=p['line'], highlightthickness=1)
                row.grid(row=index, column=0, sticky='ew', padx=18, pady=3)
                tk.Label(row, text=label, bg=p['surface'], fg=p['muted'], width=22, anchor='e').pack(side='right', padx=8, pady=6)
                tk.Label(row, text=value, bg=p['surface'], fg=p['text'], anchor='e').pack(side='right', fill='x', expand=True, padx=8)
            opened = project.project_id in self.processes and self.processes[project.project_id].poll() is None
            foot = tk.Frame(card, bg=p['surface'])
            foot.grid(row=len(details) + 1, column=0, sticky='ew', padx=18, pady=18)
            tk.Label(foot, text=f"وضعیت: {'باز است' if opened else 'آماده'}", bg=p['surface'],
                     fg=p['green'] if opened else p['muted'], font=('Segoe UI', 10, 'bold')).pack(side='right')
            tk.Button(foot, text='باز کردن پروژه' if not opened else 'پروژه در حال اجراست',
                      state='normal' if not opened else 'disabled', command=lambda item=project: self.open_project(item),
                      bg=p['blue'], fg='#FFFFFF', activebackground=p['cyan'], relief='flat',
                      font=('Segoe UI', 11, 'bold'), padx=20, pady=8).pack(side='left')
            tk.Label(foot, text=f'میانبر: {self._shortcut_path(project).name}', bg=p['surface'], fg=p['muted'], font=('Segoe UI', 8)).pack(side='left', padx=8)
        self.info.set(self._status_text())

    def open_project(self, project: ProjectEntry):
        self.closed_tabs.discard(project.project_id)
        if project.project_id in self.processes and self.processes[project.project_id].poll() is None:
            return
        self.registry.set_active(project.project_id)
        process = subprocess.Popen([sys.executable, str(self.base_dir / 'project_runner_stage18_6.py'), project.project_id], cwd=str(self.base_dir))
        self.processes[project.project_id] = process
        self.info.set(f'پروژه «{project.name}» باز شد.')
        self.after(250, self.refresh_tabs)

    def project_new_or_open(self):
        p, _light = self.colors
        window = tk.Toplevel(self)
        window.title('پروژه — New / Open')
        window.transient(self)
        window.grab_set()
        window.resizable(False, False)
        window.configure(bg=p['surface'])
        tk.Label(window, text='پروژه جدید یا پروژه موجود؟', bg=p['surface'], fg=p['text'], font=('Segoe UI', 13, 'bold')).pack(padx=28, pady=(22, 12))
        bar = tk.Frame(window, bg=p['surface'])
        bar.pack(padx=24, pady=(0, 24))
        tk.Button(bar, text='New', command=lambda: (window.destroy(), self.new_project()), bg=p['blue'], fg='#FFFFFF',
                  font=('Segoe UI', 11, 'bold'), relief='flat', padx=28, pady=9).pack(side='right', padx=6)
        tk.Button(bar, text='Open', command=lambda: (window.destroy(), self.open_shortcut()), bg=p['glass'], fg=p['text'],
                  font=('Segoe UI', 11, 'bold'), relief='flat', padx=28, pady=9).pack(side='right', padx=6)

    def new_project(self):
        ProjectWizard(self, self.registry, self.secrets, on_done=self._new_done)

    def open_shortcut(self):
        path = filedialog.askopenfilename(parent=self, title='انتخاب میانبر پروژه BARKAV',
                                          filetypes=[('BARKAV Project', '*.barkav'), ('All files', '*.*')])
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding='utf-8'))
            project, is_new = validate_project_shortcut(data, path, self.registry.list())
            if is_new:
                rows = [item.__dict__ for item in self.registry.list()]
                rows.append(project.__dict__)
                self.registry.data['projects'] = rows
                self.registry.save()
            self.closed_tabs.discard(project.project_id)
            self.refresh_tabs()
            self.open_project(project)
        except Exception as exc:
            messagebox.showerror('Open Project', str(exc), parent=self)


def run_project_center(base_dir: str | Path):
    app = ProjectCenter186(base_dir)
    app.mainloop()


if __name__ == '__main__':
    run_project_center(Path(__file__).resolve().parents[2])

# Consolidated Project Center layer 4
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tkinter as tk
from tkinter import ttk

from dashboard import is_tab_close_hit_187
from project_registry import ProjectEntry
from ui import (
    activate_theme_bridge_187,
    build_brand_widget_187,
    palette_187,
    style_ttk_187,
)
from v18_store import load_ui


VERSION = '18.7.1'

activate_theme_bridge_187()
palette_186 = palette_187
style_ttk_186 = style_ttk_187
build_brand_widget_186 = build_brand_widget_187


class ProjectCenter187(ProjectCenter186):
    def __init__(self, base_dir: str | Path):
        super().__init__(base_dir)
        self.title(f'BARKAV {VERSION} — مرکز پروژه')
        try:
            self.overrideredirect(False)
        except tk.TclError:
            pass
        try:
            self.state('zoomed')
        except tk.TclError:
            try:
                self.attributes('-zoomed', True)
            except tk.TclError:
                pass

    def _build(self):
        p, light = self.colors
        self.configure(bg=p['bg'])
        style_ttk_187(self, light=light, font_size=int(load_ui().get('font_size') or 10), row_height=31)
        style = ttk.Style(self)
        style.configure('ProjectCenter187.TNotebook.Tab', anchor='e')
        head = tk.Frame(self, bg=p['surface'], height=66, highlightbackground=p['line'], highlightthickness=1)
        head.pack(fill='x')
        head.pack_propagate(False)
        head.grid_columnconfigure(0, weight=1)
        head.grid_columnconfigure(1, weight=0)
        head.grid_columnconfigure(2, weight=1)
        brand = build_brand_widget_187(
            head, self.base_dir / 'assets' / 'barkav_brand_header.png',
            bg=p['surface'], fg=p['text'], muted=p['muted'], compact=True,
        )
        brand.grid(row=0, column=0, sticky='w', padx=(14, 6), pady=4)
        tk.Label(
            head, text='مرکز پروژه', bg=p['surface'], fg=p['text'],
            font=('Segoe UI', 14, 'bold'), anchor='center',
        ).grid(row=0, column=1, padx=18, pady=14)
        tk.Button(
            head, text='پروژه جدید', command=self.project_new_or_open,
            bg=p['blue'], fg='#FFFFFF', activebackground=p['cyan'],
            relief='flat', padx=14, pady=7,
        ).grid(row=0, column=2, sticky='e', padx=8)
        selector_bar = tk.Frame(self, bg=p['bg'])
        selector_bar.pack(fill='x', padx=12, pady=(8, 0))
        tk.Label(
            selector_bar, text='انتخاب پروژه', bg=p['bg'], fg=p['text'],
            font=('Segoe UI', 10, 'bold'), anchor='e',
        ).pack(side='right', padx=(8, 4))
        self.project_selector = ttk.Combobox(
            selector_bar, state='readonly', justify='right', width=34,
        )
        self.project_selector.pack(side='right', fill='x', expand=True, padx=(4, 0))
        self.project_selector.bind('<<ComboboxSelected>>', self._select_project, add='+')
        self.nb = ttk.Notebook(self, style='ProjectCenter187.TNotebook')
        self.nb.pack(fill='both', expand=True, padx=12, pady=12)
        try:
            self.nb.configure(tabposition='ne')
        except tk.TclError:
            pass
        self.nb.bind('<Button-1>', self._tab_click, add='+')
        self.nb.bind('<<NotebookTabChanged>>', self._sync_project_selector, add='+')
        self.info = tk.StringVar(value='')
        tk.Label(
            self, textvariable=self.info, bg=p['bg'], fg=p['muted'],
            font=('Segoe UI', 10, 'bold'), anchor='e',
        ).pack(fill='x', padx=14, pady=(0, 10), anchor='e')

    def _select_project(self, _event=None):
        index = self.project_selector.current()
        if index < 0 or index >= len(self._selector_project_ids):
            return
        project_id = self._selector_project_ids[index]
        tab_id = next(
            (tab for tab, value in self._tab_project_ids.items() if value == project_id),
            None,
        )
        if tab_id:
            self.nb.select(tab_id)

    def _sync_project_selector(self, _event=None):
        if not getattr(self, 'project_selector', None):
            return
        try:
            tab_id = self.nb.select()
            project_id = self._tab_project_ids.get(str(tab_id))
            if project_id in self._selector_project_ids:
                self.project_selector.current(self._selector_project_ids.index(project_id))
        except tk.TclError:
            pass

    @staticmethod
    def _project_summary(project: ProjectEntry) -> dict[str, object]:
        """Read optional project-card metrics without changing DB/profile data."""
        result: dict[str, object] = {
            'floor_count': '', 'unit_count': '', 'total_cost': '', 'progress': 0.0,
        }
        db_path = Path(project.db_path)
        profile_path = db_path.resolve().parent / 'project_profile_v18.json'
        try:
            profile = json.loads(profile_path.read_text(encoding='utf-8')) if profile_path.is_file() else {}
            if isinstance(profile, dict):
                floors = [row for row in (profile.get('floors') or []) if isinstance(row, dict)]
                regular = [row for row in floors if not row.get('is_roof')]
                floor_meta = profile.get('floor_meta') or {}
                floor_count = floor_meta.get('total_floor_count') or len(regular)
                unit_count = sum(len(row.get('units') or []) for row in regular)
                if floor_count:
                    result['floor_count'] = fa(floor_count)
                if unit_count:
                    result['unit_count'] = fa(unit_count)
                progress = profile.get('progress_percent', profile.get('physical_progress', 0))
                try:
                    result['progress'] = max(0.0, min(float(progress or 0), 100.0))
                except (TypeError, ValueError):
                    pass
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            pass
        try:
            if db_path.is_file():
                with sqlite3.connect(db_path.resolve().as_uri() + '?mode=ro', uri=True) as connection:
                    table = connection.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='expenses'"
                    ).fetchone()
                    if table:
                        amount = connection.execute(
                            """SELECT COALESCE(SUM(final_amount), 0) FROM expenses
                               WHERE deleted_at IS NULL AND status='APPROVED'
                                 AND construction_stage IS NOT NULL AND TRIM(construction_stage) <> ''"""
                        ).fetchone()[0]
                        if amount:
                            result['total_cost'] = fa(f'{int(amount):,}')
        except (OSError, sqlite3.Error):
            pass
        return result

    @staticmethod
    def _card_value(value: object) -> str:
        return str(value) if value not in (None, '') else '—'

    @staticmethod
    def _progress_chart(parent, percent: float, palette: dict[str, str]):
        chart = tk.Canvas(
            parent, height=42, bg=palette['surface'],
            highlightbackground=palette['line'], highlightthickness=1,
        )
        chart.percent = percent

        def redraw(_event=None):
            chart.delete('all')
            width = max(chart.winfo_width(), 120)
            margin = 6
            chart.create_rectangle(
                margin, margin, width - margin, 36,
                fill=palette['panel2'], outline=palette['line'], width=1,
            )
            filled = (width - 2 * margin) * chart.percent / 100.0
            if filled > 0:
                chart.create_rectangle(
                    margin, margin, margin + filled, 36,
                    fill=palette['blue'], outline='',
                )
            text = '—' if chart.percent <= 0 else f'{fa(f"{chart.percent:.1f}")}٪'
            chart.create_text(width / 2, 21, text=text, fill=palette['text'], font=('Segoe UI', 10, 'bold'))

        chart.bind('<Configure>', redraw)
        chart.redraw = redraw
        chart.after_idle(redraw)
        return chart

    def refresh_tabs(self):
        p, _light = self.colors
        for project_id, process in list(self.processes.items()):
            if process.poll() is not None:
                self.processes.pop(project_id, None)
        for tab in self.nb.tabs():
            self.nb.forget(tab)
        self._tab_project_ids = {}
        projects = [project for project in self.registry.list() if project.project_id not in self.closed_tabs]
        self._selector_project_ids = [project.project_id for project in projects]
        self.project_selector.configure(
            values=[f'{fa(project.name)}  ({fa(project.project_id)})' for project in projects]
        )
        for project in projects:
            tab = ttk.Frame(self.nb, padding=20, style='Panel.TFrame')
            self.nb.add(tab, text=f'{fa(project.name)}  ({fa(project.project_id)})  ×')
            self._tab_project_ids[str(tab)] = project.project_id
            tab.grid_rowconfigure(0, weight=1)
            tab.grid_columnconfigure(0, weight=1)
            viewport = tk.Frame(tab, bg=p['bg'])
            viewport.grid(row=0, column=0, sticky='nsew')
            viewport.grid_rowconfigure(0, weight=1)
            viewport.grid_columnconfigure(0, weight=1)
            canvas = tk.Canvas(viewport, bg=p['bg'], highlightthickness=0)
            scrollbar = ttk.Scrollbar(viewport, orient='vertical', command=canvas.yview)
            canvas.configure(yscrollcommand=scrollbar.set)
            canvas.grid(row=0, column=0, sticky='nsew')
            scrollbar.grid(row=0, column=1, sticky='ns')
            body = tk.Frame(canvas, bg=p['bg'])
            window = canvas.create_window((0, 0), window=body, anchor='nw')
            body.bind('<Configure>', lambda _event, c=canvas: c.configure(scrollregion=c.bbox('all')), add='+')
            canvas.bind('<Configure>', lambda event, c=canvas, w=window: c.itemconfigure(w, width=event.width), add='+')

            def scroll(event, c=canvas):
                if event.delta:
                    units = int(-event.delta / 120) or (-1 if event.delta > 0 else 1)
                else:
                    units = -1 if getattr(event, 'num', 4) == 4 else 1
                c.yview_scroll(units, 'units')
                return 'break'

            def bind_scroll(widget):
                widget.bind('<MouseWheel>', scroll, add='+')
                widget.bind('<Button-4>', scroll, add='+')
                widget.bind('<Button-5>', scroll, add='+')
                for child in widget.winfo_children():
                    bind_scroll(child)

            card = tk.Frame(body, bg=p['surface'], highlightbackground=p['line'], highlightthickness=1)
            card.pack(fill='x', expand=True, padx=12, pady=12)
            summary = self._project_summary(project)
            tk.Label(
                card, text=fa(project.name), bg=p['surface'], fg=p['text'],
                font=('Segoe UI', 18, 'bold'), anchor='e',
            ).grid(row=0, column=0, sticky='ew', padx=18, pady=(18, 5))
            details = [
                ('کد پروژه', fa(project.project_id)),
                ('Group ID', fa(project.group_chat_id or '-')),
                ('Google Sheet', fa(project.spreadsheet_name or '-')),
                ('آدرس', fa(project.address or '-')),
                ('پرونده شهرداری', fa(project.municipal_file_no or '-')),
                ('تعداد طبقه', self._card_value(summary['floor_count'])),
                ('تعداد واحد', self._card_value(summary['unit_count'])),
                ('هزینه کل ساخت', self._card_value(summary['total_cost'])),
            ]
            card.grid_columnconfigure((0, 1), weight=1, uniform='project_info')
            info_grid = tk.Frame(card, bg=p['surface'])
            info_grid.grid(row=1, column=0, columnspan=2, sticky='ew', padx=18, pady=3)
            info_grid.grid_columnconfigure((0, 1), weight=1, uniform='project_info_box')
            for box_index, subset in enumerate((details[:4], details[4:])):
                box = tk.Frame(info_grid, bg=p['panel2'], highlightbackground=p['line'], highlightthickness=1)
                box.grid(row=0, column=1 - box_index, sticky='nsew', padx=4)
                box.grid_columnconfigure(0, weight=1)
                for index, (label, value) in enumerate(subset):
                    row = tk.Frame(box, bg=p['surface'], highlightbackground=p['line'], highlightthickness=1)
                    row.grid(row=index, column=0, sticky='ew', padx=6, pady=3)
                    tk.Label(row, text=label, bg=p['surface'], fg=p['muted'], width=18, anchor='e').pack(side='right', padx=8, pady=6)
                    tk.Label(row, text=value, bg=p['surface'], fg=p['text'], anchor='e').pack(side='right', fill='x', expand=True, padx=8)
            progress = tk.Frame(card, bg=p['surface'])
            progress.grid(row=2, column=0, columnspan=2, sticky='ew', padx=18, pady=(10, 3))
            tk.Label(progress, text='نمودار پیشرفت', bg=p['surface'], fg=p['muted'], anchor='e').pack(fill='x', pady=(0, 4))
            self._progress_chart(progress, float(summary['progress']), p).pack(fill='x')
            running = tk.Frame(card, bg=p['surface'], highlightbackground=p['line'], highlightthickness=1)
            running.grid(row=3, column=0, columnspan=2, sticky='ew', padx=18, pady=3)
            tk.Label(running, text='فاز در حال اجرا', bg=p['surface'], fg=p['muted'], anchor='e').pack(fill='x', padx=8, pady=8)
            foot = tk.Frame(card, bg=p['surface'])
            foot.grid(row=4, column=0, columnspan=2, sticky='ew', padx=18, pady=18)
            opened = project.project_id in self.processes and self.processes[project.project_id].poll() is None
            tk.Label(
                foot, text=f"وضعیت: {'باز است' if opened else 'آماده'}", bg=p['surface'],
                fg=p['green'] if opened else p['muted'], font=('Segoe UI', 10, 'bold'),
            ).pack(side='right')
            tk.Button(
                foot, text='باز کردن پروژه' if not opened else 'پروژه در حال اجراست',
                state='normal' if not opened else 'disabled', command=lambda item=project: self.open_project(item),
                bg=p['blue'], fg='#FFFFFF', activebackground=p['cyan'], relief='flat',
                font=('Segoe UI', 11, 'bold'), padx=20, pady=8,
            ).pack(side='left')
            tk.Label(
                foot, text=f'میانبر: {self._shortcut_path(project).name}', bg=p['surface'],
                fg=p['muted'], font=('Segoe UI', 8),
            ).pack(side='left', padx=8)
            bind_scroll(body)
        if projects:
            active_id = self.registry.data.get('active_project_id')
            selected_id = active_id if active_id in self._selector_project_ids else projects[0].project_id
            self.project_selector.current(self._selector_project_ids.index(selected_id))
            self._select_project()
        else:
            self.project_selector.set('')
        self.info.set(self._status_text())

    @property
    def colors(self):
        light = str(load_ui().get('appearance') or 'dark').lower() == 'light'
        return palette_187(light), light

    def _tab_click(self, event):
        try:
            index = self.nb.index(f'@{event.x},{event.y}')
            bbox = self.nb.bbox(index)
            if not bbox or not is_tab_close_hit_187(event.x, bbox):
                return None
            tab_id = self.nb.tabs()[index]
            project_id = self._tab_project_ids.get(str(tab_id))
            if project_id:
                self.close_project(project_id)
                return 'break'
        except Exception:
            return None
        return None

    def open_project(self, project: ProjectEntry):
        self.closed_tabs.discard(project.project_id)
        if project.project_id in self.processes and self.processes[project.project_id].poll() is None:
            return
        self.registry.set_active(project.project_id)
        process = subprocess.Popen(
            [sys.executable, str(self.base_dir / 'project_runner.py'), project.project_id],
            cwd=str(self.base_dir),
        )
        self.processes[project.project_id] = process
        self.info.set(f'پروژه «{project.name}» باز شد.')
        self.after(250, self.refresh_tabs)


def run_project_center(base_dir: str | Path):
    app = ProjectCenter187(base_dir)
    app.mainloop()


if __name__ == '__main__':
    run_project_center(Path(__file__).resolve().parents[2])
