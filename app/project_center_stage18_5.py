from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from project_center_stage18_4 import ProjectCenter184
from project_center_stage15 import ProjectWizard
from project_registry import ProjectEntry
from ui_stage18_3 import fa
from ui_stage18_5 import build_brand_widget_185, palette_185, style_ttk_185
from v18_store import load_ui


VERSION = '18.5'


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


class ProjectCenter185(ProjectCenter184):
    def __init__(self, base_dir: str | Path):
        super().__init__(base_dir)
        self.title(f'BARKAV {VERSION} — مرکز پروژه‌ها')
        try:
            self.iconbitmap(default=str(self.base_dir / 'assets' / 'BARKAV_18_5.ico'))
        except Exception:
            pass

    @property
    def colors(self):
        light = str(load_ui().get('appearance') or 'dark').lower() == 'light'
        return palette_185(light), light

    def _build(self):
        p, light = self.colors
        self.configure(bg=p['bg'])
        style_ttk_185(self, light=light, font_size=int(load_ui().get('font_size') or 11), row_height=38)
        head = tk.Frame(self, bg=p['surface'], height=82, highlightbackground=p['line'], highlightthickness=1)
        head.pack(fill='x')
        head.pack_propagate(False)
        brand = build_brand_widget_185(head, self.base_dir / 'assets' / 'BARKAV_shortcut.png', bg=p['surface'], fg=p['text'], muted=p['muted'], compact=True)
        brand.pack(side='left', padx=(16, 6), pady=8)
        tk.Label(head, text='مرکز پروژه‌ها', bg=p['surface'], fg=p['text'], font=('Segoe UI', 16, 'bold')).pack(side='right', padx=20, pady=17)
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
        process = subprocess.Popen([sys.executable, str(self.base_dir / 'project_runner_stage18_5.py'), project.project_id], cwd=str(self.base_dir))
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
    app = ProjectCenter185(base_dir)
    app.mainloop()


if __name__ == '__main__':
    run_project_center(Path(__file__).resolve().parent)
