"""مرکز پروژه: اولین پنجره‌ای که با اجرای برنامه دیده می‌شود.

الگوی این پنجره از تب Start در AutoCAD گرفته شده (به تقاضای مستقیم
کاربر، با اسکرین‌شات مرجع) - یک نوار تب بالا با تب اول «شروع» (بازکردن/
پروژه جدید/اخیر) و یک تب به ازای هر پروژهٔ باز.

هر پروژه همچنان پنجرهٔ واقعی و مستقل خودش را در یک ساب‌پروسس جدا دارد
(project_runner_stage18_7.py، با قفل و ربات تلگرام اختصاصی خودش - همان
مدلی که چند پروژهٔ هم‌زمان را از قبل پشتیبانی می‌کند). تب پروژه در همین
پنجره فقط یک کارت خلاصه است، نه جاسازی زندهٔ خودِ Stage187Dashboard - آن
کلاس مستقیماً و در چهارده لایه از tk.Tk ارث می‌برد (نه tk.Frame)، پس
اصلاً قابل‌جاسازی داخل یک تب دیگر نیست؛ جاسازی واقعی منتظر یکسان‌سازی
فایل‌های stage است که قرار است بعداً انجام شود.

ProjectWizard/ProjectRegistry/validate_project_shortcut از قبل کار
می‌کنند و اینجا فقط صدا زده می‌شوند - بازسازی نشده‌اند.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import jdatetime

from barkav_themes.tokens import mix
from barkav_ui import art
from barkav_ui.art import logo as barkav_logo
from barkav_ui.theme import font as kit_font
from barkav_ui.window import fade_in, hide_for_fade, work_area
from runtime_base import frozen, load_local_secrets
from instance_guard_v185 import ProjectInstanceGuard, bring_process_window_to_front
from phase_intelligence_v175 import PHASE_HINTS
from project_center_stage15 import ProjectWizard
from project_center_stage18_4 import _safe_name
from project_center_stage18_6 import validate_project_shortcut
from project_registry import ProjectEntry, ProjectRegistry
from ui_stage18_3 import fa
from ui_stage18_7 import (
    palette_187,
    style_ttk_187,
)
from v18_store import load_ui

# پروژه‌های ۱۸.۷ نسخهٔ نمایشی خودشان را دارند (DISPLAY_VERSION_187 در
# dashboard_stage18_7)؛ همین‌جا هم یک نسخهٔ محلی کافی است - مرکز پروژهٔ
# موجود هم دقیقاً همین قرارداد را دارد (VERSION = '18.7' در
# project_center_stage18_7.py)، نه ایمپورت کل ماژول سنگین داشبورد فقط
# برای یک رشته.
#
# دلیل مهم‌تر همین ایمپورت‌نکردن: dashboard_stage18_7 در سطح ماژول خودش
# activate_theme_bridge_187() را صدا می‌زند که dashboard_stage16_3/
# dashboard_stage17_5 را (فقط برای هماهنگی رنگ نمودار) ایمپورت می‌کند -
# همان ایمپورتی که به‌تنهایی ۱۵-۲۰ ثانیه طول می‌کشد و علت واقعی «باز
# نمیه» بود (رفع‌شده در کامیت afafc9e). این پنجره نموداری ندارد که به آن
# رنگ‌ها نیاز داشته باشد، پس هرگز نباید از dashboard_stage18_7 چیزی
# ایمپورت کند - حتی یک تابع کوچک مثل is_tab_close_hit_187، که به همین
# دلیل پایین‌تر دوباره (کوتاه) نوشته شده، نه ایمپورت شده.
DISPLAY_VERSION = '19.1.1'


def _current_light() -> bool:
    return str(load_ui().get('appearance') or 'dark').lower() == 'light'


class ProjectHub187(tk.Tk):
    """مرکز پروژه: تب «شروع» (بازکردن/پروژه جدید/اخیر) + یک تب به ازای
    هر پروژهٔ باز.

    نوار تب خودش دست‌ساز است، نه ttk.Notebook: آن ویجت گزینهٔ
    ``tabposition`` را با اسکین سفارشی این برنامه اصلاً پیاده نمی‌کند
    (خطای ``unknown option "-tabposition"`` - تأییدشده با تست زنده)، پس
    نمی‌شد نوار تب را واقعاً راست‌چین کرد. اینجا هر تب یک Frame معمولی
    است که با ``pack(side='right')`` به نوار اضافه می‌شود - «شروع» اول
    پک می‌شود و همیشه همان‌جا (سمت راست) می‌ماند، تب‌های پروژهٔ بعدی هرکدام
    سمت چپِ تب قبلی جا می‌گیرند."""

    def __init__(self, base_dir: str | Path, open_path: str | Path | None = None):
        super().__init__()
        hide_for_fade(self)
        self.base_dir = Path(base_dir)
        self.registry = ProjectRegistry(self.base_dir)
        # فایل‌های .brk دیگر تو data/project_shortcuts قایم نیستند - طبق
        # ساختار جدید (کد در app/، دیتا و آیکون هر پروژه یک پوشه بالاتر،
        # کنار آیکون خودِ برنامه) مستقیم در پوشهٔ اصلی (یکی بالاتر از app/)
        # نشسته‌اند؛ چیزی که کاربر باز می‌کند فقط آیکون برنامه و آیکون هر
        # پروژه است، نه یک ساختار پوشهٔ تودرتو.
        self.shortcut_dir = self.base_dir.parent
        # شورتکات‌های نسخه‌های قبلی را هم از مسیر قدیمی می‌خوانیم تا دادهٔ کاربر از دسترس خارج نشود.
        self.legacy_shortcut_dir = self.base_dir / 'data' / 'project_shortcuts'
        self.shortcut_dir.mkdir(parents=True, exist_ok=True)
        self.processes: dict[str, subprocess.Popen] = {}
        self._dismissed_recent_ids = self._load_dismissed_recent()
        self.tab_buttons: dict[str, tk.Frame] = {}
        self.tab_pages: dict[str, tk.Frame] = {}
        self.tab_project_ids: dict[str, str] = {}
        self.active_tab_key: str | None = None
        self._logo_ref = None
        self._action_icon_refs: list = []
        self.title(f'BARKAV {DISPLAY_VERSION}')
        self.geometry('980x620')
        self.minsize(780, 480)
        # مرکز پروژه (چه با دابل‌کلیک روی .brk چه با باز کردن مستقیم) باید
        # تمام‌صفحه باز شود - 980x620 فقط اندازهٔ بازگشت هنگام خروج از حالت
        # maximize می‌ماند. همون الگوی maximize-نه-fullscreen که
        # project_center_stage18_7.py از قبل استفاده می‌کند (state('zoomed')
        # روی ویندوز، attributes('-zoomed', True) به‌عنوان جایگزین روی X11).
        try:
            self.state('zoomed')
        except tk.TclError:
            try:
                self.attributes('-zoomed', True)
            except tk.TclError:
                pass
        try:
            self.iconbitmap(default=str(self.base_dir / 'assets' / 'BARKAV.ico'))
        except Exception:
            pass
        self._build()
        # از دابل‌کلیک روی فایل .brk خودِ ویندوز مسیر آن فایل را به‌عنوان
        # آرگومان خط‌فرمان می‌دهد (launcher_stage18_7.py آن را می‌گیرد و
        # اینجا پاس می‌دهد) - اگر معتبر بود، همان پروژه بلافاصله باز و
        # تبش فعال می‌شود، نه فقط تبِ خالیِ «شروع».
        if open_path:
            path = Path(open_path)
            if path.is_file():
                self._open_shortcut_path(path)
        fade_in(self)

    # --- build -----------------------------------------------------------

    def _build(self) -> None:
        light = _current_light()
        p = self.palette = palette_187(light)
        style_ttk_187(self, light=light, font_size=int(load_ui().get('font_size') or 10))
        self.configure(bg=p['bg'])

        top = tk.Frame(self, bg=p['surface'], height=66,
                       highlightbackground=p['border_subtle'], highlightthickness=1)
        top.pack(fill='x')
        top.pack_propagate(False)
        self._build_brand_header(top)

        self.tab_bar = tk.Frame(self, bg=p['surface'], height=40,
                                highlightbackground=p['border_subtle'], highlightthickness=1)
        self.tab_bar.pack(fill='x')
        self.tab_bar.pack_propagate(False)

        self.content_host = tk.Frame(self, bg=p['bg'])
        self.content_host.pack(fill='both', expand=True, padx=10, pady=10)

        self.start_tab = self._add_tab('start', 'شروع', closable=False)
        self._build_start_tab(self.start_tab)
        self._select_tab('start')

    def _build_brand_header(self, parent) -> None:
        """نوار بالا: همون art.logo() که واترمارک هم ازش استفاده می‌کنه -
        قبلاً اینجا build_brand_widget_187 (=build_brand_widget_186، از
        assets/barkav_brand_header.png) بود که «BARKAV» را با فونت عمومی
        Segoe UI جدا می‌کشید، نه با حروفِ خودِ آرم؛ برای همین با واترمارکِ
        همین صفحه (که از همون لوگوی فعلی می‌آید) یکی نبود."""

        p = self.palette
        try:
            image = barkav_logo(
                height=40, background=p['surface'], colour=p['text'],
                drop_tagline=False, wordmark_scale=1.15, align_wordmark=True,
                master=self,
            )
        except Exception:
            image = None
        if image is not None:
            self._brand_logo_ref = image
            tk.Label(parent, image=image, bg=p['surface']).pack(
                side='right', padx=14, pady=4)

    def _build_start_tab(self, parent) -> None:
        """راست: بازکردن/پروژه جدید. وسط: اخیر. چپ: جای خالی + واترمارک -
        آینهٔ راست‌چین همان سه ناحیهٔ تب Start در AutoCAD (چپ: Open/New،
        وسط: Recent، راست: Connect)."""

        p = self.palette
        parent.grid_columnconfigure(0, weight=0, minsize=320)
        parent.grid_columnconfigure(1, weight=1)
        parent.grid_columnconfigure(2, weight=0, minsize=1)
        parent.grid_columnconfigure(3, weight=0, minsize=200)
        parent.grid_rowconfigure(0, weight=1)

        divider = tk.Frame(parent, bg=p['border_subtle'], width=1)
        divider.grid(row=0, column=2, sticky='ns', pady=24)

        actions = tk.Frame(parent, bg=p['bg'])
        actions.grid(row=0, column=3, sticky='n', padx=(12, 18), pady=24)

        icons = self._action_icons(p['accent'])
        self._action_icon_refs = icons
        for index, (label, command) in enumerate((
            ('بازکردن...', self.open_shortcut),
            ('پروژه جدید', self.new_project),
            ('ویرایش', self.edit_project),
        )):
            row = tk.Frame(actions, bg=p['bg'], cursor='hand2')
            row.pack(fill='x', pady=(0, 10))
            icon = tk.Label(row, image=icons[index], bg=p['bg'], cursor='hand2')
            icon.pack(side='right', padx=(0, 8))
            text = tk.Label(row, text=label, bg=p['bg'], fg=p['accent'],
                            font=kit_font('body', widget=self, bold=True),
                            anchor='e', cursor='hand2')
            text.pack(side='right')
            for widget in (row, icon, text):
                widget.bind('<Button-1>', lambda _e, cmd=command: cmd())

        center = tk.Frame(parent, bg=p['bg'])
        center.grid(row=0, column=1, sticky='nsew', padx=8, pady=24)
        tk.Label(center, text='پروژه‌های اخیر', bg=p['bg'], fg=p['text'],
                font=kit_font('title', widget=self, bold=True), anchor='e').pack(
            fill='x', pady=(0, 10))

        list_host = tk.Frame(center, bg=p['bg'])
        list_host.pack(fill='both', expand=True)
        canvas = tk.Canvas(list_host, bg=p['bg'], highlightthickness=0, bd=0)
        scroll = ttk.Scrollbar(list_host, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side='left', fill='y')
        canvas.pack(side='right', fill='both', expand=True)
        inner = tk.Frame(canvas, bg=p['bg'])
        inner_window = canvas.create_window((0, 0), window=inner, anchor='nw')

        def _sync_scrollregion(_event=None):
            canvas.configure(scrollregion=canvas.bbox('all'))

        def _sync_inner_width(event):
            # کارت‌ها باید کل عرض کانواس را پر کنند - نه فقط عرض طبیعی
            # محتوایشان - وگرنه نوار پیشرفت هر پروژه باریک‌تر از ستون
            # می‌ماند.
            canvas.itemconfigure(inner_window, width=event.width)

        inner.bind('<Configure>', _sync_scrollregion)
        canvas.bind('<Configure>', _sync_inner_width)
        canvas.bind('<MouseWheel>', lambda e: canvas.yview_scroll(-1 if e.delta > 0 else 1, 'units'))
        canvas.bind('<Button-4>', lambda _e: canvas.yview_scroll(-3, 'units'))
        canvas.bind('<Button-5>', lambda _e: canvas.yview_scroll(3, 'units'))

        self.recent_list_canvas = canvas
        self.recent_list_inner = inner
        self._refresh_recent()

        empty = tk.Frame(parent, bg=p['bg'])
        empty.grid(row=0, column=0, sticky='nsew')
        empty.grid_rowconfigure(0, weight=1)
        empty.grid_rowconfigure(1, weight=1)
        empty.grid_columnconfigure(0, weight=1)
        top_half = tk.Frame(empty, bg=p['bg'])
        top_half.grid(row=0, column=0, sticky='nsew')
        bottom_half = tk.Frame(empty, bg=p['bg'])
        bottom_half.grid(row=1, column=0, sticky='nsew')
        self._paint_watermark(top_half)
        self._paint_construction_watermark(bottom_half)

    def _action_icons(self, color: str) -> list:
        glyphs = ('\ue8e5', '\ue710', '\ue70f')  # OpenFile, Add, Edit - Segoe MDL2 Assets
        try:
            from PIL import Image, ImageDraw, ImageFont, ImageTk
            font_path = Path(os.environ.get('WINDIR', 'C:\\Windows')) / 'Fonts' / 'segmdl2.ttf'
            font = ImageFont.truetype(str(font_path), 20)
            icons = []
            for glyph in glyphs:
                canvas = Image.new('RGBA', (28, 28), (0, 0, 0, 0))
                draw = ImageDraw.Draw(canvas)
                draw.text((14, 14), glyph, font=font, fill=color, anchor='mm')
                icons.append(ImageTk.PhotoImage(canvas, master=self))
            return icons
        except Exception:
            return [None] * len(glyphs)

    def _paint_watermark(self, parent) -> None:
        """جای خالی سمت چپ: همان نشان بارکاوِ کم‌رنگ که در نسخه‌های قبلی
        داشبورد بود (dashboard_stage18_7's own removed watermark - دیدن
        art.logo's حالا-دوباره-اضافه‌شدهٔ transparent=True) - اینجا پشت
        یک ستون کاملاً خودش، بدون تداخل با اخیر/دکمه‌ها که هرکدام ستون
        مجزای خود را دارند."""

        p = self.palette
        tint_colour = mix(p['bg'], p['accent'], 0.10)
        try:
            # ارتفاع طوری انتخاب شده که عرض واقعی نشان (که با
            # wordmark_scale=1.15 نسبتش تقریباً ۳.۷ به ۱ است) داخل ستون
            # ۳۲۰پیکسلی جا شود، نه اینکه از لبه‌اش بزند بیرون.
            image = barkav_logo(
                height=80, background=p['bg'], colour=tint_colour,
                drop_tagline=True, wordmark_scale=1.15, align_wordmark=True,
                transparent=True, master=self,
            )
        except Exception:
            image = None
        if image is None:
            return
        self._logo_ref = image
        tk.Label(parent, image=image, bg=p['bg']).place(relx=0.5, rely=0.5, anchor='center')

    def _paint_construction_watermark(self, parent) -> None:
        """نیمهٔ پایینِ ستون چپ: همون تصویر کروکیِ ساختمان+جرثقیل که قبلاً
        تو assets بود ولی هیچ‌جای برنامه صداش نمی‌زد (construction_watermark
        در art.py) - اندازه‌اش با <Configure> خودِ این نیمه هماهنگ می‌مونه
        که از کادرش بیرون نزنه، دقیقاً مثل واترمارک بالا."""

        p = self.palette
        tint_colour = mix(p['bg'], p['accent'], 0.10)
        label = tk.Label(parent, bg=p['bg'], bd=0, highlightthickness=0)
        label.place(relx=0.5, rely=0.5, anchor='center')

        def _repaint(event, _label=label):
            if event.width < 10 or event.height < 10:
                return
            try:
                image = art.construction_watermark(
                    max_width=max(1, event.width - 16),
                    max_height=max(1, event.height - 16),
                    background=p['bg'], colour=tint_colour, transparent=True,
                    master=self,
                )
            except Exception:
                image = None
            if image is None:
                return
            self._construction_watermark_ref = image
            _label.configure(image=image)

        parent.bind('<Configure>', _repaint)

    # --- recent list -------------------------------------------------------

    PHASE_COUNT = 32

    def _shortcut_files(self) -> list[Path]:
        paths = list(self.shortcut_dir.glob('*.brk'))
        paths.extend(self.shortcut_dir.glob('*.barkav'))
        if self.legacy_shortcut_dir.exists():
            paths.extend(self.legacy_shortcut_dir.glob('*.brk'))
            paths.extend(self.legacy_shortcut_dir.glob('*.barkav'))
        return sorted(
            {path for path in paths},
            key=lambda path: path.stat().st_mtime, reverse=True,
        )

    def _dismissed_recent_path(self) -> Path:
        return self.base_dir / 'data' / 'dismissed_recent.json'

    def _load_dismissed_recent(self) -> set:
        try:
            raw = json.loads(self._dismissed_recent_path().read_text(encoding='utf-8'))
            return set(str(x) for x in raw) if isinstance(raw, list) else set()
        except Exception:
            return set()

    def _save_dismissed_recent(self) -> None:
        try:
            path = self._dismissed_recent_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(sorted(self._dismissed_recent_ids), ensure_ascii=False), encoding='utf-8')
        except Exception:
            pass

    def _dismiss_recent(self, project_id: str) -> None:
        # فقط از فهرست «اخیر» پنهان می‌شود - خودِ پروژه/دیتابیسش دست‌نخورده
        # می‌ماند و از «ویرایش» یا «بازکردن...» همچنان در دسترس است.
        # _sync_shortcuts_from_registry فایل .brk را برای هر پروژهٔ ثبت‌شده
        # در رجیستری که فایلش نیست دوباره می‌سازد؛ پس حذفِ خودِ فایل کافی
        # نبود - این فهرستِ جداگانه دائمی است تا با باز کردن دوبارهٔ برنامه
        # هم آن پروژه برنگردد.
        if not project_id:
            return
        self._dismissed_recent_ids.add(project_id)
        self._save_dismissed_recent()
        self._refresh_recent()

    def _phase_status_colors(self, light: bool) -> dict[str, str]:
        # همون رنگ‌های وضعیت فاز که dashboard_stage18_2.refresh_phase_strip
        # برای نوار فازهای خودِ داشبورد استفاده می‌کند - عیناً همان‌ها، نه
        # رنگ‌های تازه، تا نوار کوچک این‌جا با نوار واقعیِ داخل پروژه یک
        # زبان بصری داشته باشد.
        return ({
            'NOT_STARTED': '#E7ECEF', 'ACTIVE': '#28A875',
            'PAUSED': '#D8A33D', 'COMPLETED': '#239A70',
        } if light else {
            'NOT_STARTED': '#10243A', 'ACTIVE': '#177A59',
            'PAUSED': '#76571C', 'COMPLETED': '#16805D',
        })

    def _read_phase_progress(self, db_path: str) -> tuple[dict[int, dict], float]:
        """فقط خواندنی (mode=ro) از دیتابیس یک پروژه - حتی اگر آن پروژه
        هم‌زمان به‌عنوان یک پنجرهٔ مستقل باز و در حال نوشتن باشد، این
        اتصال هرگز چیزی نمی‌نویسد و migrate/seed هم صدا نمی‌زند (برخلاف
        BudgetService/RichBudgetService که برای همین کار ساخته نشده‌اند).
        نبودِ جدول یا نبودِ خودِ فایل فقط یعنی «هنوز داده‌ای نیست»، نه خطا."""

        try:
            path = Path(db_path)
            if not path.is_file():
                return {}, 0.0
            uri = f'file:{path.resolve().as_posix()}?mode=ro'
            conn = sqlite3.connect(uri, uri=True, timeout=1.0)
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(
                    'SELECT phase_no, status, physical_progress FROM phase_progress_v163'
                ).fetchall()
            finally:
                conn.close()
            progress = {int(row['phase_no']): dict(row) for row in rows}
        except Exception:
            return {}, 0.0
        total = sum(
            float((progress.get(n) or {}).get('physical_progress') or 0)
            for n in range(1, self.PHASE_COUNT + 1)
        )
        return progress, total / self.PHASE_COUNT

    def _phase_name(self, db_path: str, phase_no: int) -> str:
        """نام واقعیِ فاز از rich_phase_items خودِ همان پروژه (فقط‌خواندنی)؛
        اگر آن پروژه هنوز آیتمی برای این فاز ثبت نکرده، به نام رسمیِ همان
        فاز در تاکسونومیِ ۳۲گانهٔ phase_intelligence_v175 برمی‌گردد - نه
        یک نام اختراعی."""

        try:
            path = Path(db_path)
            if path.is_file():
                uri = f'file:{path.resolve().as_posix()}?mode=ro'
                conn = sqlite3.connect(uri, uri=True, timeout=1.0)
                try:
                    row = conn.execute(
                        "SELECT phase_name FROM rich_phase_items WHERE phase_no=? "
                        "AND phase_name IS NOT NULL AND phase_name != '' LIMIT 1",
                        (phase_no,),
                    ).fetchone()
                finally:
                    conn.close()
                if row and row[0]:
                    return str(row[0])
        except Exception:
            pass
        hints = PHASE_HINTS.get(phase_no)
        return hints[0] if hints else f'فاز {phase_no}'

    def _build_recent_card(self, parent, path: Path, data: dict) -> None:
        p = self.palette
        light = _current_light()
        name = str(data.get('name') or path.stem)
        opened_gregorian = datetime.fromtimestamp(path.stat().st_mtime)
        opened = jdatetime.datetime.fromgregorian(datetime=opened_gregorian).strftime('%Y/%m/%d %H:%M')

        card = tk.Frame(parent, bg=p['card'], cursor='hand2',
                        highlightbackground=p['border_subtle'], highlightthickness=1)
        card.pack(fill='x', pady=(0, 8))

        header = tk.Frame(card, bg=p['card'], cursor='hand2')
        header.pack(fill='x', padx=12, pady=(10, 6))
        project_id = str(data.get('project_id') or '')
        dismiss = tk.Label(header, text='×', bg=p['card'], fg=p['muted'], cursor='hand2',
                           font=kit_font('body', widget=self, bold=True))
        dismiss.pack(side='left', padx=(0, 8))
        dismiss.bind('<Button-1>', lambda _e, pid=project_id: self._dismiss_recent(pid))
        tk.Label(header, text=fa(name), bg=p['card'], fg=p['text'], cursor='hand2',
                font=kit_font('body', widget=self, bold=True), anchor='e').pack(side='right')
        tk.Label(header, text=fa(opened), bg=p['card'], fg=p['muted'], cursor='hand2',
                font=kit_font('small', widget=self), anchor='w').pack(side='left')

        progress, overall = self._read_phase_progress(str(data.get('db_path') or ''))
        colors = self._phase_status_colors(light)
        strip = tk.Frame(card, bg=p['card'], cursor='hand2')
        strip.pack(fill='x', padx=12, pady=(0, 6))
        for phase_no in range(1, self.PHASE_COUNT + 1):
            status = str((progress.get(phase_no) or {}).get('status') or 'NOT_STARTED')
            seg = tk.Frame(strip, bg=colors.get(status, colors['NOT_STARTED']),
                          width=8, height=14, cursor='hand2')
            seg.pack(side='right', padx=1)
            seg.pack_propagate(False)

        completed = sum(
            1 for phase_no in range(1, self.PHASE_COUNT + 1)
            if str((progress.get(phase_no) or {}).get('status') or '') == 'COMPLETED'
        )
        summary = f'پیشرفت کلی {fa(f"{overall:.0f}")}٪   •   {fa(completed)}/{fa(self.PHASE_COUNT)} فاز تکمیل‌شده'
        active_phases = sorted(
            n for n in range(1, self.PHASE_COUNT + 1)
            if str((progress.get(n) or {}).get('status') or '') == 'ACTIVE'
        )
        footer = tk.Label(card, text=summary, bg=p['card'], fg=p['muted'], cursor='hand2',
                          font=kit_font('small', widget=self), anchor='e')
        footer.pack(fill='x', padx=12, pady=(0, 2 if active_phases else 10))

        current_label = None
        if active_phases:
            current_name = self._phase_name(str(data.get('db_path') or ''), active_phases[0])
            current_label = tk.Label(
                card, text=f'فاز جاری: {fa(current_name)}', bg=p['card'], fg=p['accent'],
                cursor='hand2', font=kit_font('small', widget=self, bold=True), anchor='e',
            )
            current_label.pack(fill='x', padx=12, pady=(0, 10))

        bound = (card, header, strip, footer, *strip.winfo_children())
        if current_label is not None:
            bound = (*bound, current_label)
        for widget in bound:
            widget.bind('<Double-1>', lambda _e, _path=path: self._open_shortcut_path(_path))

    def _sync_shortcuts_from_registry(self) -> None:
        """اگر پروژه‌ای در ProjectRegistry (مرجع واقعی) ثبت است ولی هیچ
        فایل .brk برایش نیست - مثلاً چون کسی/چیزی آن فایل را پاک کرده -
        یکی دوباره می‌سازد. «پروژه‌های اخیر» فقط از روی فایل‌های .brk
        پر می‌شود، پس بدون این خودترمیمی، پاک‌شدنِ آن فایل به‌تنهایی (که
        فقط یک میانبر است، نه خودِ داده) باعث می‌شد پروژه‌ای که واقعاً در
        رجیستری و دیتابیسش کاملاً سالم است، از این لیست ناپدید شود."""

        try:
            existing_ids = set()
            for path in self.shortcut_dir.glob('*.brk'):
                try:
                    existing_ids.add(json.loads(path.read_text(encoding='utf-8')).get('project_id'))
                except Exception:
                    continue
            for project in self.registry.list():
                if project.project_id not in existing_ids:
                    self._write_shortcut(project)
        except Exception:
            pass

    def _refresh_recent(self) -> None:
        inner = getattr(self, 'recent_list_inner', None)
        if inner is None or not inner.winfo_exists():
            return
        self._sync_shortcuts_from_registry()
        for child in inner.winfo_children():
            child.destroy()
        for path in self._shortcut_files():
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
            except Exception:
                continue
            if str(data.get('project_id') or '') in self._dismissed_recent_ids:
                continue
            self._build_recent_card(inner, path, data)
        self._bind_wheel_recursive(inner, self.recent_list_canvas)

    def _bind_wheel_recursive(self, widget, canvas) -> None:
        # قبلاً bind_all بود تا چرخ ماوس روی هر کارتِ فهرست هم کار کند (نه
        # فقط روی پسِ‌زمینهٔ خالیِ کانواس) - ولی bind_all سراسریِ کل برنامه
        # است، نه فقط این پنجره؛ با اضافه‌شدنِ کانواسِ قابل‌اسکرولِ دیگری در
        # ویزارد پروژه (یک Toplevel دیگر)، همان چرخِ ماوس هر دو کانواس را
        # هم‌زمان اسکرول می‌کرد. اینجا به‌جایش هر ویجتِ داخلِ خودِ این فهرست
        # (بازگشتی، چون هر کارت لایه‌های تودرتوی خودش را دارد) را مستقیماً
        # به همین canvas وصل می‌کنیم - محدود به همین پنجره.
        widget.bind('<MouseWheel>', lambda e: canvas.yview_scroll(-1 if e.delta > 0 else 1, 'units'))
        widget.bind('<Button-4>', lambda _e: canvas.yview_scroll(-3, 'units'))
        widget.bind('<Button-5>', lambda _e: canvas.yview_scroll(3, 'units'))
        for child in widget.winfo_children():
            self._bind_wheel_recursive(child, canvas)

    # --- tabs ----------------------------------------------------------
    # نوار تب دست‌ساز: هر تب یک دکمهٔ خودش در tab_bar دارد و یک صفحهٔ خودش
    # در content_host (همه با place روی هم، فقط صفحهٔ فعال با tkraise بالا
    # می‌آید) - دیدن توضیح بالای کلاس برای اینکه چرا به‌جای ttk.Notebook.

    def _add_tab(self, key: str, label: str, *, closable: bool) -> tk.Frame:
        p = self.palette
        page = tk.Frame(self.content_host, bg=p['bg'])
        page.place(x=0, y=0, relwidth=1, relheight=1)
        self.tab_pages[key] = page

        button = tk.Frame(self.tab_bar, bg=p['surface'], cursor='hand2')
        button.pack(side='right', padx=(0, 1), fill='y')
        text = tk.Label(button, text=label, bg=p['surface'], fg=p['text'],
                        font=kit_font('body', widget=self), padx=14, cursor='hand2')
        text.pack(side='right', fill='y')
        widgets = [button, text]
        if closable:
            close = tk.Label(button, text='×', bg=p['surface'], fg=p['muted'],
                             font=kit_font('body', widget=self, bold=True),
                             padx=8, cursor='hand2')
            close.pack(side='left', fill='y')
            close.bind('<Button-1>', lambda _e, k=key: self._close_tab(k))
            widgets.append(close)
        for widget in widgets[:2]:
            widget.bind('<Button-1>', lambda _e, k=key: self._select_tab(k))
        self.tab_buttons[key] = button
        return page

    def _select_tab(self, key: str) -> None:
        page = self.tab_pages.get(key)
        if page is None or not page.winfo_exists():
            return
        page.tkraise()
        self.active_tab_key = key
        p = self.palette
        for tab_key, button in self.tab_buttons.items():
            active_bg = p['bg'] if tab_key == key else p['surface']
            button.configure(bg=active_bg)
            for child in button.winfo_children():
                child.configure(bg=active_bg)

    def _close_tab(self, key: str) -> None:
        project_id = self.tab_project_ids.pop(key, None)
        if project_id:
            proc = self.processes.pop(project_id, None)
            if proc and proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=3)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
        button = self.tab_buttons.pop(key, None)
        if button is not None and button.winfo_exists():
            button.destroy()
        page = self.tab_pages.pop(key, None)
        if page is not None and page.winfo_exists():
            page.destroy()
        if self.active_tab_key == key:
            self._select_tab('start')

    def _open_project_tab(self, project: ProjectEntry) -> None:
        key = f'project:{project.project_id}'
        if key in self.tab_pages:
            self._select_tab(key)
            return
        page = self._add_tab(key, fa(project.name), closable=True)
        self.tab_project_ids[key] = project.project_id
        self._build_project_tab(page, project)
        self._select_tab(key)

    def _build_project_tab(self, parent, project: ProjectEntry) -> None:
        """فقط کارت خلاصهٔ یک پروژه - نه جاسازی زندهٔ Stage187Dashboard؛
        دیدن توضیح بالای فایل برای اینکه چرا (آن کلاس از tk.Tk ارث
        می‌برد، نه tk.Frame، پس قابل‌جاسازی داخل تب دیگری نیست)."""

        p = self.palette
        card = tk.Frame(parent, bg=p['card'], highlightbackground=p['border_subtle'],
                        highlightthickness=1)
        card.pack(padx=24, pady=24)
        tk.Label(card, text=project.name, bg=p['card'], fg=p['text'],
                font=kit_font('title', widget=self, bold=True), anchor='e',
                justify='right', width=40).pack(fill='x', padx=18, pady=(16, 4))
        # این کارت قبلاً فقط project.group_chat_id (اولین گروه، برای
        # سازگاریِ قدیمی) را نشان می‌داد - بعد از ویرایش یک پروژهٔ چندگروهی
        # و اضافه‌شدنِ گروه دوم، همچنان فقط همان یکی دیده می‌شد. حالا کل
        # فهرست را نشان می‌دهد.
        group_ids = project.group_chat_ids or ([project.group_chat_id] if project.group_chat_id is not None else [])
        group_display = ", ".join(fa(g) for g in group_ids) if group_ids else "-"
        for line in (
            f"شناسهٔ پروژه: {project.project_id}",
            f"Group ID: {group_display}",
            f"Spreadsheet: {project.spreadsheet_name or '-'}",
        ):
            tk.Label(card, text=line, bg=p['card'], fg=p['muted'],
                    font=kit_font('body', widget=self), anchor='e',
                    justify='right').pack(fill='x', padx=18, pady=2)
        tk.Frame(card, bg=p['card'], height=8).pack()
        tk.Button(
            card, text='باز کردن پنجرهٔ کامل این پروژه',
            command=lambda: self._launch_project(project),
            bg=p['blue'], fg='#FFFFFF', activebackground=p['cyan'],
            relief='flat', padx=16, pady=8, cursor='hand2',
            font=kit_font('body', widget=self, bold=True),
        ).pack(pady=(8, 18))

    # --- actions -----------------------------------------------------------

    def _load_secrets(self) -> dict:
        return load_local_secrets(self.base_dir)

    def _write_shortcut(self, project: ProjectEntry) -> Path:
        # همان قالب BARKAV_PROJECT_SHORTCUT که project_center_stage18_4's
        # own _write_shortcut/_new_done از قبل می‌نویسد - با یک اضافه:
        # یک کپی از سکرت‌های فعلی (توکن ربات، کلید Gemini، ...) هم داخل
        # خودِ فایل ذخیره می‌شود. این عمداً یک "کپی" است، نه اینکه از این
        # پس برنامه سکرت را فقط از این فایل بخواند - secrets.local.json
        # هنوز منبع واقعی است؛ این کپی فقط باعث می‌شود خودِ فایل .brk
        # به‌تنهایی (کنار پوشهٔ برنامه) برای انتقال/پشتیبان کافی باشد.
        # سطح دسترسی/چند کاربری روی این کپی، طبق خواستهٔ کاربر، بعداً اضافه
        # می‌شود - فعلاً فقط یک کپیِ ساده از کل secrets.local.json است.
        path = self.shortcut_dir / f"{_safe_name(project.name)}_{project.project_id}.brk"
        # ویرایش پروژه (مثلاً تغییر نام - چه دستی چه با تبدیل خودکار اعداد
        # فارسی روی نام) نامِ فایل .brk را عوض می‌کند چون نام در خودِ نامِ
        # فایل است؛ بدون این پاک‌سازی، فایل قدیمی با نام قبلی می‌ماند و
        # «پروژه‌های اخیر» همان پروژه را دوبار (یک‌بار با نام کهنه) نشان
        # می‌دهد.
        for stale in self.shortcut_dir.glob('*.brk'):
            if stale == path:
                continue
            try:
                stale_data = json.loads(stale.read_text(encoding='utf-8'))
            except Exception:
                continue
            if str(stale_data.get('project_id') or '') == str(project.project_id):
                try:
                    stale.unlink()
                except OSError:
                    pass
        groups = list(project.group_chat_ids or ([project.group_chat_id] if project.group_chat_id is not None else []))
        payload = {
            'format': 'BARKAV_PROJECT_SHORTCUT', 'version': 1,
            'project_id': project.project_id, 'name': project.name,
            'db_path': project.db_path, 'group_chat_id': project.group_chat_id,
            "group_chat_ids": groups,
            'spreadsheet_name': project.spreadsheet_name, 'address': project.address,
            'postal_code': project.postal_code, 'registration_plate': project.registration_plate,
            'municipal_file_no': project.municipal_file_no,
            'telegram_verified': project.telegram_verified,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        return path

    def _open_shortcut_path(self, path: Path) -> None:
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            project, is_new = validate_project_shortcut(data, path, self.registry.list())
            if is_new:
                rows = [item.__dict__ for item in self.registry.list()]
                rows.append(project.__dict__)
                self.registry.data['projects'] = rows
                self.registry.save()
            # تازه‌شدن mtime همان چیزی است که «اخیر» را بر اساسش می‌چیند -
            # هربار بازشدن یک پروژه، آن را دوباره به بالای فهرست می‌آورد.
            path.touch()
            self._refresh_recent()
            self._open_project_tab(project)
            self._launch_project(project)
        except Exception as exc:
            messagebox.showerror('باز کردن پروژه', str(exc), parent=self)

    def open_shortcut(self) -> None:
        path = filedialog.askopenfilename(
            parent=self, title='انتخاب میانبر پروژه BARKAV',
            filetypes=[('BARKAV Project', '*.brk'), ('All files', '*.*')],
        )
        if not path:
            return
        self._open_shortcut_path(Path(path))

    def new_project(self) -> None:
        ProjectWizard(self, self.registry, self._load_secrets(),
                     on_done=self._project_created, palette=self.palette)

    def edit_project(self) -> None:
        """کادر انتخاب پروژه برای ویرایش - همان ویزارد ساخت پروژه را با
        existing=project باز می‌کند تا مشخصات/گروه‌های آن قابل‌تغییر شوند
        (دیدن ProjectWizard.editing_project_id)."""

        projects = self.registry.list()
        if not projects:
            messagebox.showinfo('ویرایش پروژه', 'هنوز پروژه‌ای ساخته نشده.', parent=self)
            return
        p = self.palette
        dialog = tk.Toplevel(self)
        dialog.title('انتخاب پروژه برای ویرایش')
        dialog.configure(bg=p['bg'])
        dialog.transient(self)
        dialog.grab_set()
        width, height = 420, 190
        try:
            avail_w, avail_h = work_area(self)
        except Exception:
            avail_w, avail_h = self.winfo_screenwidth(), self.winfo_screenheight() - 64
        dialog.geometry(f'{width}x{height}+{max(0,(avail_w-width)//2)}+{max(0,(avail_h-height)//2)}')
        dialog.resizable(False, False)

        tk.Label(dialog, text='پروژهٔ مورد نظر برای ویرایش را انتخاب کن:', bg=p['bg'], fg=p['text'],
                anchor='e', justify='right', font=kit_font('body', widget=self)).pack(fill='x', padx=18, pady=(20, 8))
        names = [f'{proj.name} ({proj.project_id})' for proj in projects]
        choice = tk.StringVar(value=names[0])
        combo = ttk.Combobox(dialog, textvariable=choice, values=names, state='readonly', justify='right')
        combo.pack(fill='x', padx=18, pady=8)

        def proceed() -> None:
            selected = projects[names.index(choice.get())]
            dialog.destroy()
            ProjectWizard(self, self.registry, self._load_secrets(), on_done=self._project_edited,
                         palette=self.palette, existing=selected)

        buttons = tk.Frame(dialog, bg=p['bg'])
        buttons.pack(fill='x', padx=18, pady=(12, 18))
        ttk.Button(buttons, text='ادامه', command=proceed).pack(side='left')
        ttk.Button(buttons, text='انصراف', command=dialog.destroy).pack(side='right')
        dialog.bind('<Escape>', lambda _e: dialog.destroy())
        combo.focus_set()

    def _project_created(self, project: ProjectEntry) -> None:
        try:
            path = self._write_shortcut(project)
            path.touch()
        except Exception:
            pass
        self._refresh_recent()
        self._open_project_tab(project)
        self._launch_project(project)

    def _project_edited(self, project: ProjectEntry) -> None:
        # میانبر .brk این پروژه (اگر وجود داشته باشد) گروه/مشخصات را در
        # لحظهٔ ساخت داخل خودش کپی کرده بود؛ بازنویسی‌اش تازه نگه می‌دارد
        # تا دابل‌کلیک بعدی روی همان فایل با «Group ID میانبر با پروژهٔ
        # ثبت‌شده یکسان نیست» رد نشود (دیدن validate_project_shortcut).
        try:
            path = self._write_shortcut(project)
            path.touch()
        except Exception:
            pass
        self._refresh_recent()
        key = f'project:{project.project_id}'
        if key in self.tab_pages:
            page = self.tab_pages[key]
            for child in page.winfo_children():
                child.destroy()
            self._build_project_tab(page, project)
        # ربات و داشبورد پروژه فقط یک‌بار موقع اجرا env را می‌خوانند - اگر
        # همین الان برای این پروژه روشن است، تغییرات گروه تا ری‌استارت
        # واقعی اعمال نمی‌شوند؛ برای همین بعد از ویرایش می‌پرسیم.
        # self.processes به‌تنهایی کافی نبود: فقط پردازش‌هایی را می‌شناسد
        # که خودِ همین پنجرهٔ Hub روشن کرده - اگر پروژه از یک مسیر دیگر
        # باز شده باشد (مثلاً دابل‌کلیکِ مستقیمِ فایلِ .brk، در یک پنجرهٔ
        # کاملاً جداگانه)، آن دیکشنری خالی می‌ماند و این پیام اصلاً نشان
        # داده نمی‌شد؛ حالا وضعیتِ واقعی از همان قفلِ ProjectInstanceGuard
        # (project_runner_stage18_7.py برای همین دقیقاً همین منظور
        # استفاده‌اش می‌کند) خوانده می‌شود - مستقل از این‌که پروژه از کجا
        # باز شده.
        if self._project_is_running(project.project_id):
            if messagebox.askyesno(
                'ری‌استارت پروژه',
                'برای ثبت تغییرات جدید پروژه را ری‌استارت کنید؟',
                parent=self,
            ):
                self._restart_project(project)

    def _project_is_running(self, project_id: str) -> bool:
        from instance_guard_v185 import ProjectInstanceGuard
        guard = ProjectInstanceGuard(self.base_dir / 'runtime', project_id)
        if guard.acquire():
            guard.release()
            return False
        return True

    def _restart_project(self, project: ProjectEntry) -> None:
        # همون روش خاموش‌کردنِ terminate/wait/kill که _close_tab برای بستن
        # تب پروژه استفاده می‌کند - اینجا فقط دوباره هم راه‌اندازی می‌شود.
        # زیرپردازشِ ربات (که خودِ project_runner_stage18_7.py اسپان
        # می‌کند) با این terminate یتیم نمی‌ماند - آن فایل حالا زیرپردازش
        # را در یک Windows Job Object با KILL_ON_JOB_CLOSE می‌گذارد، پس
        # همین‌که این پردازشِ بیرونی (parent) بمیرد، ویندوز خودش آن
        # زیرپردازش را هم می‌کشد؛ وگرنه یک long-poller قدیمی و یتیم با
        # env قبل از ویرایش، رقیبِ پردازشِ تازه برای همان توکنِ تلگرام
        # می‌ماند و تغییراتِ گروه با وجودِ یک «ری‌استارتِ موفق» بی‌اثر
        # می‌ماندند.
        proc = self.processes.pop(project.project_id, None)
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            self._launch_project(project)
            return
        # این پنجرهٔ Hub خودش این پروژه را روشن نکرده، پس پردازشی برای
        # بستنِ امن نداریم - حدس‌زدن/کشتنِ یک PID ناشناس از روی فایل قفل
        # ریسکِ بی‌مورد است (آن PID ممکن است بازیافت‌شده و به یک پردازشِ
        # کاملاً بی‌ربط تعلق داشته باشد). اگر واقعاً چیزی هنوز روشن است، از
        # اپراتور می‌خواهیم خودش آن پنجره را ببندد.
        if self._project_is_running(project.project_id):
            messagebox.showinfo(
                'ری‌استارت پروژه',
                'این پروژه در یک پنجرهٔ دیگر باز است. آن پنجره را ببند و دوباره باز کن تا تغییرات اعمال شود.',
                parent=self,
            )
        else:
            self._launch_project(project)

    def _launch_project(self, project: ProjectEntry) -> None:
        proc = self.processes.get(project.project_id)
        if proc and proc.poll() is None:
            # The project tab is only a summary; the real dashboard lives in
            # this child process.  Re-selecting the project must focus that
            # existing window instead of silently returning behind another app.
            if bring_process_window_to_front(proc.pid):
                self.destroy()
            return
        # A project may have been opened from a .brk file or another launcher,
        # so it is not necessarily present in ``self.processes``.  The lock
        # records its owner PID and lets us focus the already-running dashboard
        # without starting a duplicate runner.
        guard = ProjectInstanceGuard(self.base_dir / 'runtime', project.project_id)
        if not guard.acquire():
            owner_pid = guard.owner_pid()
            if owner_pid and bring_process_window_to_front(owner_pid):
                self.destroy()
            return
        guard.release()
        # Packaged as one exe, project_runner_stage18_7.py isn't a separate
        # file on disk any more - re-launch this same exe with an internal
        # flag instead (dispatched in launcher_stage18_7.main). Dev mode is
        # unchanged: the loose script's own argv-based main() still runs.
        args = ([sys.executable, '--run-project', project.project_id] if frozen()
                else [sys.executable, str(self.base_dir / 'project_runner_stage18_7.py'), project.project_id])
        process = subprocess.Popen(args, cwd=str(self.base_dir))
        self.processes[project.project_id] = process

        # Tk needs a short turn to create its native HWND.  Retry through the
        # same helper so a launch from another foreground application is still
        # visible as soon as the dashboard exists.
        attempts = {'count': 0}

        def focus_when_ready(p=process):
            if p.poll() is not None or attempts['count'] >= 8:
                return
            attempts['count'] += 1
            if bring_process_window_to_front(p.pid):
                # The dashboard has its own Start/Project tabs, so the Hub
                # must not remain as a second visible application window.
                self.after(350, self.destroy)
            else:
                self.after(350, focus_when_ready)

        self.after(180, focus_when_ready)


def run_bare_launcher(base_dir: str | Path, open_path: str | Path | None = None) -> None:
    app = ProjectHub187(base_dir, open_path=open_path)
    app.mainloop()


if __name__ == '__main__':
    run_bare_launcher(Path(__file__).resolve().parent)
