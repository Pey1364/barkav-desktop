from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tkinter as tk
from tkinter import ttk

import project_center_stage18_6 as legacy_center
from dashboard_stage18_7 import is_tab_close_hit_187
from project_registry import ProjectEntry
from ui_stage18_7 import (
    activate_theme_bridge_187,
    build_brand_widget_187,
    palette_187,
    style_ttk_187,
)
from barkav_ui.window import (
    bind_main_window_focus_on_destroy,
    center_toplevel_on_screen,
    normalize_window_rtl,
)
from v18_store import load_ui


VERSION = '18.7'

activate_theme_bridge_187()
legacy_center.palette_186 = palette_187
legacy_center.style_ttk_186 = style_ttk_187
legacy_center.build_brand_widget_186 = build_brand_widget_187


class ProjectCenter187(legacy_center.ProjectCenter186):
    def __init__(self, base_dir: str | Path):
        super().__init__(base_dir)
        self.title(f'BARKAV {VERSION} — مرکز پروژه')
        self.bind_all('<Map>', self._on_toplevel_map_187, add='+')
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

    def _on_toplevel_map_187(self, event):
        window = getattr(event, 'widget', None)
        if not isinstance(window, tk.Toplevel):
            return
        try:
            bind_main_window_focus_on_destroy(window, self)
            center_toplevel_on_screen(window)
            window.after_idle(lambda target=window: normalize_window_rtl(target))
        except tk.TclError:
            return

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
                    result['floor_count'] = legacy_center.fa(floor_count)
                if unit_count:
                    result['unit_count'] = legacy_center.fa(unit_count)
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
                            result['total_cost'] = legacy_center.fa(f'{int(amount):,}')
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
            text = '—' if chart.percent <= 0 else f'{legacy_center.fa(f"{chart.percent:.1f}")}٪'
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
            values=[f'{legacy_center.fa(project.name)}  ({legacy_center.fa(project.project_id)})' for project in projects]
        )
        for project in projects:
            tab = ttk.Frame(self.nb, padding=20, style='Panel.TFrame')
            self.nb.add(tab, text=f'{legacy_center.fa(project.name)}  ({legacy_center.fa(project.project_id)})  ×')
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
                card, text=legacy_center.fa(project.name), bg=p['surface'], fg=p['text'],
                font=('Segoe UI', 18, 'bold'), anchor='e',
            ).grid(row=0, column=0, sticky='ew', padx=18, pady=(18, 5))
            details = [
                ('کد پروژه', legacy_center.fa(project.project_id)),
                ('Group ID', legacy_center.fa(project.group_chat_id or '-')),
                ('Google Sheet', legacy_center.fa(project.spreadsheet_name or '-')),
                ('آدرس', legacy_center.fa(project.address or '-')),
                ('پرونده شهرداری', legacy_center.fa(project.municipal_file_no or '-')),
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
            [sys.executable, str(self.base_dir / 'project_runner_stage18_7.py'), project.project_id],
            cwd=str(self.base_dir),
        )
        self.processes[project.project_id] = process
        self.info.set(f'پروژه «{project.name}» باز شد.')
        self.after(250, self.refresh_tabs)


def run_project_center(base_dir: str | Path):
    app = ProjectCenter187(base_dir)
    app.mainloop()


if __name__ == '__main__':
    run_project_center(Path(__file__).resolve().parent)
