from __future__ import annotations

import asyncio
import json
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox, ttk

from project_registry import ProjectEntry, ProjectRegistry
from barkav_ui.window import fade_in, hide_for_fade, work_area, _FRAME_RESERVE
from ui_stage18_3 import persianize_var


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
    # عناوین پنجره به‌ازای هر مرحله - جدا از عنوانِ داخلِ محتوا (titles در
    # _render) چون آن یکی شمارهٔ مرحله را هم دارد و برای تیتر پنجره لازم
    # نیست.
    WINDOW_TITLES = (
        "مشخصات پروژه", "مشخصات گروه تلگرام",
        "بررسی اتصال ربات", "شیت‌های گوگل و تأیید نهایی",
    )

    def __init__(self,parent,registry:ProjectRegistry,secrets:dict,on_done,palette:dict|None=None,
                 existing:ProjectEntry|None=None):
        super().__init__(parent);hide_for_fade(self);self.parent=parent;self.registry=registry;self.secrets=secrets;self.on_done=on_done
        # existing یعنی حالت ویرایش: یک پروژهٔ از قبل ساخته‌شده - همون
        # مراحل ساخت پروژه، فقط مشخصات/گروه‌هایش از قبل پر شده و در پایان
        # به‌جای registry.create روی همین project_id، registry.update
        # صدا زده می‌شود (دیدن next_step).
        self.editing_project_id = existing.project_id if existing else None
        # palette اختیاری است: ProjectCenter قدیمی بدون آن صدا می‌زند و
        # ظاهر قبلی (ttk پیش‌فرض روشن) را حفظ می‌کند؛ مرکز پروژهٔ جدید
        # (ProjectHub187) همان پالت تیرهٔ خودش را پاس می‌دهد تا این پنجره
        # با بقیهٔ برنامه یک‌دست باشد.
        self.palette = palette or {}
        # ارتفاعِ پنجره دیگر یک عددِ ثابتِ یکسان برای هر ۴ مرحله نیست - هر
        # بار _render صدا زده می‌شود (یا تعداد گروه‌ها با دکمهٔ
        # «به‌روزرسانی» عوض می‌شود)، _fit_window پنجره را دقیقاً به اندازهٔ
        # محتوای همان مرحله می‌رساند؛ مرحلهٔ اول (فقط ۵ ردیف) دیگر یک کادرِ
        # خالیِ بزرگ زیرش نمی‌ماند، و مرحلهٔ دوم (راهنما + چند ردیف Group
        # ID) هنوز جا دارد چون work_area (کمکیِ SPI_GETWORKAREA در
        # barkav_ui/window.py، همان چیزی که بقیهٔ پنجره‌های برنامه استفاده
        # می‌کنند) سقفِ ارتفاع را ناحیهٔ واقعیِ قابل‌استفادهٔ صفحه (منهای
        # نوار وظیفهٔ ویندوز) می‌گیرد - همان چیزی که قبلاً باعث می‌شد نوار
        # قبلی/بعدی پشتِ نوار وظیفه گم شود (تأییدشده با اسکرین‌شات واقعی).
        self._wizard_width = 610
        self.geometry(f"{self._wizard_width}x480")
        self.transient(parent);self.grab_set();self.resizable(False,False)
        self.step=0;self.telegram_verified=False
        # "group" حذف شد - حالا group_0/group_1/... طبق تعدادِ گروه‌ها،
        # هروقت مرحلهٔ ۲ رندر شد، تو _rebuild_group_rows اضافه می‌شن.
        self.vars={k:tk.StringVar() for k in ("name","address","postal","plate","municipal","sheet")}
        self.vars["sheet"].set("")
        # اعداد همه‌جای برنامه باید فارسی دیده بشن - fa() فقط رقم‌های
        # ۰-۹ لاتین را برمی‌گرداند، بقیهٔ رشته (خط تیره، اسلش، حروف) دست‌نخورده
        # می‌ماند؛ "sheet" (نام Spreadsheet) عمداً بیرون است چون یک شناسهٔ
        # فنی برای Google Sheets است، نه متنی برای خواندن.
        for key in ("name", "address", "postal", "plate", "municipal"):
            persianize_var(self.vars[key])
        if existing:
            self.vars["name"].set(existing.name)
            self.vars["address"].set(existing.address)
            self.vars["postal"].set(existing.postal_code)
            self.vars["plate"].set(existing.registration_plate)
            self.vars["municipal"].set(existing.municipal_file_no)
            self.vars["sheet"].set(existing.spreadsheet_name)
            ids = existing.group_chat_ids or ([existing.group_chat_id] if existing.group_chat_id is not None else [])
            self.vars["group_count"] = tk.StringVar(value=str(max(1, len(ids))))
            persianize_var(self.vars["group_count"])
            for index, gid in enumerate(ids):
                self.vars[f"group_{index}"] = tk.StringVar(value=str(gid))
                persianize_var(self.vars[f"group_{index}"])
            self._wizard_group_ids = ids
        if self.palette:
            self.configure(bg=self.palette.get('bg', '#0E141B'))
            self._entry_style, self._button_style = self._install_dark_ttk_styles()
        else:
            self._entry_style = self._button_style = None
        # nav با side="bottom" قبل از container پک می‌شود تا جایش همیشه
        # پایینِ پنجره رزرو بماند - وگرنه با متن راهنمای بلندِ مرحلهٔ ۲
        # (که ارتفاعش را container خودش تعیین می‌کند) نوار قبلی/بعدی از
        # کادر ۴۸۰پیکسلیِ قبلی کاملاً بیرون می‌افتاد و اصلاً دیده نمی‌شد.
        nav=self._frame(self);nav.pack(side="bottom",fill="x",padx=16,pady=12)
        self.container=self._frame(self);self.container.pack(fill="both",expand=True,padx=16,pady=16)
        self.back=ttk.Button(nav,text="قبلی",command=self.prev,style=self._button_style or 'TButton');self.back.pack(side="right")
        self.next=ttk.Button(nav,text="بعدی",command=self.next_step,style=self._button_style or 'TButton');self.next.pack(side="left")
        self._render()
        fade_in(self)

    def _frame(self, parent) -> tk.Frame:
        if self.palette:
            return tk.Frame(parent, bg=self.palette.get('bg', '#0E141B'))
        return tk.Frame(parent)

    def _label(self, parent, **kw):
        if self.palette:
            kw.setdefault('bg', self.palette.get('bg', '#0E141B'))
            if 'fg' not in kw:
                kw['fg'] = self.palette.get('text', '#F1F5F9')
        return tk.Label(parent, **kw)

    def _install_dark_ttk_styles(self) -> tuple[str, str]:
        # نام‌های اختصاصی، نه 'TEntry'/'TButton' خودِ ttk - چون آن‌ها
        # سراسریِ کل تفسیرگر Tcl هستند و تغییرشان روی هر ویجت ttk دیگری
        # در کل برنامه هم اثر می‌گذاشت.
        style = ttk.Style(self)
        surface = self.palette.get('surface', self.palette.get('card', '#111820'))
        text = self.palette.get('text', '#F1F5F9')
        border = self.palette.get('border_subtle', '#243244')
        entry_style, button_style = 'BarkavWizard.TEntry', 'BarkavWizard.TButton'
        style.configure(entry_style, fieldbackground=surface, foreground=text, insertcolor=text)
        style.configure(button_style, background=surface, foreground=text, bordercolor=border)
        style.map(button_style, background=[('active', border)])
        return entry_style, button_style

    def _clear(self):
        for w in self.container.winfo_children():w.destroy()

    def _fit_window(self) -> None:
        """پنجره را دقیقاً به اندازهٔ محتوای مرحلهٔ فعلی می‌رساند - دیدن
        یادداشتِ __init__ برای اینکه چرا یک ارتفاعِ ثابتِ مشترک بین هر ۴
        مرحله جواب نمی‌داد. مرحلهٔ دوم استثناست: راهنمای آن حالا خودش
        اسکرول می‌شود (دیدن Canvas+Scrollbar در _render)، پس به‌جای
        کوچک‌شدن به اندازهٔ محتوای طبیعی، از کل ارتفاعِ موجود استفاده
        می‌کند تا فضای بیشتری برای دیدنِ راهنما (بدون اسکرول‌کردنِ زیاد)
        داشته باشد.

        work_area فقط نوار وظیفهٔ ویندوز را کم می‌کند - خودِ قابِ پنجره
        (نوار عنوان + حاشیه‌ها) روی این مقدار اضافه می‌شود، جدا از آنچه
        geometry() می‌گیرد. بدون کم‌کردنِ _FRAME_RESERVE (همان مقداری که
        barkav_ui/window.py برای دقیقاً همین مشکل استفاده می‌کند)، لبهٔ
        پایینِ پنجره (نوار قبلی/بعدی) چند پیکسل پشتِ نوار وظیفه می‌رفت -
        تأییدشده با اسکرین‌شات واقعی."""

        self.update_idletasks()
        try:
            avail_w, avail_h = work_area(self)
        except Exception:
            avail_w, avail_h = self.winfo_screenwidth(), self.winfo_screenheight() - 64
        max_height = avail_h - 20 - _FRAME_RESERVE
        height = max_height if self.step == 1 else min(max(self.winfo_reqheight(), 300), max_height)
        pos_x = max(0, (avail_w - self._wizard_width) // 2)
        pos_y = max(0, min((avail_h - height) // 2, avail_h - height - _FRAME_RESERVE))
        self.geometry(f"{self._wizard_width}x{height}+{pos_x}+{pos_y}")

    def _add_entry_context_menu(self, entry: ttk.Entry) -> None:
        """راست‌کلیک روی کادر → برش/کپی/چسباندن/انتخابِ‌همه - ttk.Entry با
        کیبورد (Ctrl+C/V) از قبل کار می‌کرد، ولی بدون این منو راهِ آشنای
        ویندوزی (راست‌کلیک) برای چسباندنِ یک Group ID کپی‌شده وجود نداشت."""

        menu = tk.Menu(entry, tearoff=False)
        menu.add_command(label="برش", command=lambda: entry.event_generate('<<Cut>>'))
        menu.add_command(label="کپی", command=lambda: entry.event_generate('<<Copy>>'))
        menu.add_command(label="چسباندن", command=lambda: entry.event_generate('<<Paste>>'))
        menu.add_separator()
        menu.add_command(label="انتخاب همه", command=lambda: entry.select_range(0, 'end'))

        def _popup(event):
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()
        entry.bind('<Button-3>', _popup)

    def _row(self,label,key):
        r=self._frame(self.container);r.pack(fill="x",pady=5)
        self._label(r,text=label,width=24,anchor="e").pack(side="right")
        ttk.Entry(r,textvariable=self.vars[key],justify="right",style=self._entry_style or 'TEntry').pack(side="right",fill="x",expand=True,padx=8)

    def _line(self, parent, text, *, indent=0, **kw):
        # هر خط ویجتِ pack‌شدهٔ خودش را دارد با anchor="e" صریح (هم روی
        # pack هم روی خودِ Label) - راست‌چین از geometry manager می‌آید،
        # نه از تشخیصِ جهتِ متنِ خودِ Tk، که برای خط‌های کاملاً لاتین یا
        # رقم+پرانتزِ چسبیده به فارسی قابل‌اعتماد نیست (دیدن یادداشت‌های
        # مرحلهٔ ۲ برای هر دو مورد).
        kw.setdefault('wraplength', 540 - indent)
        kw.setdefault('justify', 'right')
        kw.setdefault('anchor', 'e')
        self._label(parent, text=text, **kw).pack(anchor='e', fill='x', padx=(0, indent))

    def _copy_line(self, parent, text: str, *, indent: int = 0):
        """یک خطِ کاملاً لاتین (یوزرنیم ربات و مانند آن) که با کلیک، خودش
        را در کلیپ‌بورد کپی می‌کند - همون نیازِ راست‌چینِ صریح خطِ خودش
        (دیدن _line) به‌علاوهٔ قابلیتِ کلیک."""

        accent = self.palette.get('accent', '#3B82F6') if self.palette else '#1a56db'
        label = self._label(parent, text=text, fg=accent, cursor='hand2',
                            justify='left', wraplength=0, anchor='e')
        label.pack(anchor='e', fill='x', padx=(0, indent))

        def _do_copy(_event=None):
            try:
                self.clipboard_clear();self.clipboard_append(text)
            except Exception:
                return
            label.configure(text='کپی شد')
            def _revert():
                try:label.configure(text=text)
                except tk.TclError:pass
            self.after(900, _revert)
        label.bind('<Button-1>', _do_copy)
        return label

    def _link_line(self, parent, text: str, url: str, *, indent: int = 0):
        """یک خطِ کاملاً لاتین که با کلیک، در مرورگرِ پیش‌فرضِ ویندوز باز
        می‌شود."""

        accent = self.palette.get('accent', '#3B82F6') if self.palette else '#1a56db'
        label = self._label(parent, text=text, fg=accent, cursor='hand2',
                            justify='left', wraplength=0, anchor='e')
        label.pack(anchor='e', fill='x', padx=(0, indent))
        label.bind('<Button-1>', lambda _e: webbrowser.open(url))
        return label

    def _rebuild_group_rows(self) -> None:
        """ردیف‌های Group ID را طبق تعداد فعلیِ group_count دوباره می‌سازد -
        از دکمهٔ «به‌روزرسانی» صدا زده می‌شود، هم از _render خودِ مرحلهٔ ۲."""

        try:
            count = max(1, min(20, int(str(self.vars['group_count'].get() or '1').strip())))
        except Exception:
            count = 1
        self.vars['group_count'].set(str(count))
        for widget in self.group_rows_frame.winfo_children():
            widget.destroy()
        for index in range(count):
            key = f'group_{index}'
            if key not in self.vars:
                self.vars[key] = tk.StringVar()
                persianize_var(self.vars[key])
            row = self._frame(self.group_rows_frame)
            row.pack(fill="x", pady=3)
            label_text = "Group ID" if count == 1 else f"Group ID {index + 1}"
            self._label(row, text=label_text, width=24, anchor="e").pack(side="right")
            entry = ttk.Entry(row, textvariable=self.vars[key], justify="right",
                              style=self._entry_style or 'TEntry')
            entry.pack(side="right", fill="x", expand=True, padx=8)
            self._add_entry_context_menu(entry)
        self._fit_window()

    def _render(self):
        self._clear();self.back.configure(state="normal" if self.step else "disabled")
        title = self.WINDOW_TITLES[self.step]
        self.title(f"ویرایش پروژه — {title}" if self.editing_project_id else title)
        # همون رقم‌فارسی+پرانتزِ چسبیده به متنِ فارسی که تو راهنمای مرحلهٔ ۲
        # به‌هم می‌ریخت (دیدن توضیح پایین‌تر) اینجا هم بود؛ به کلمهٔ ترتیبی
        # فارسی تغییر کرد. «Google Sheets» لاتین هم از وسط رشته بیرون
        # کشیده شد - «شیت‌های گوگل» جایگزینش شد.
        titles=["اول: مشخصات پروژه","دوم: گروه تلگرام","سوم: بررسی اتصال ربات","چهارم: شیت‌های گوگل و تأیید نهایی"]
        self._label(self.container,text=titles[self.step],font=("Tahoma",12,"bold")).pack(anchor="e",pady=(0,14))
        if self.step==0:
            self._row("نام پروژه","name");self._row("آدرس","address");self._row("کد پستی","postal");self._row("پلاک ثبتی","plate");self._row("شماره پرونده شهرداری","municipal")
        elif self.step==1:
            # جملهٔ قبلی «Group ID» لاتین را وسط یک جملهٔ فارسی می‌گذاشت -
            # Tk بدون الگوریتم واقعی بی‌دی، ترتیب چنین متن مخلوطی را قاطی
            # نشان می‌داد. اصطلاح لاتین را از وسط جمله بیرون کشیدیم؛ همان
            # عبارت هنوز روی خودِ کادر ورودی، جدا از جمله، دیده می‌شود.
            # نکتهٔ مهم‌تر (بعد از دیدن باگ دوباره تو یک برچسبِ کوتاهِ
            # بدون wraplength هم): مشکل فقط «وسط جمله» نبود - هر رشته‌ای که
            # یک کلمهٔ فارسی را مستقیماً کنار یک قطعهٔ لاتین/عددی می‌گذاشت
            # (مثلاً «Group ID (مثلاً -100...)») هم همین‌طور به‌هم می‌ریخت.
            # قانون امن‌تر: هیچ رشته‌ای هم‌زمان فارسی و لاتین نداشته باشد؛
            # اگر یک عبارت لاتین لازم است، خط/ویجت خودش را جدا داشته باشد.
            self._label(self.container,text="ابتدا ربات را به گروه پروژه اضافه کن، سپس شناسهٔ گروه را در کادر زیر وارد کن.",wraplength=540,justify="right").pack(anchor="e",pady=8)

            # بعضی پروژه‌ها بیش از یک گروه تلگرام دارند (مثلاً یکی برای
            # گزارش روزانه، یکی برای اسناد مالی) - همون یک ربات با شناسهٔ
            # گروهِ هر پیام تشخیص می‌ده کدوم گروهه و طبق منطق خودش (نه یک
            # برچسبِ دستی) دسته‌بندی می‌کنه؛ اینجا فقط باید بشه چندتا
            # Group ID وارد کرد.
            count_row = self._frame(self.container)
            count_row.pack(fill="x", pady=(4, 4))
            self._label(count_row, text="تعداد گروه‌های تلگرام:", anchor="e").pack(side="right")
            if 'group_count' not in self.vars:
                self.vars['group_count'] = tk.StringVar(value='1')
                persianize_var(self.vars['group_count'])
            ttk.Entry(count_row, textvariable=self.vars['group_count'], justify="center",
                     width=4, style=self._entry_style or 'TEntry').pack(side="right", padx=8)
            ttk.Button(count_row, text="به‌روزرسانی", command=self._rebuild_group_rows,
                      style=self._button_style or 'TButton').pack(side="right", padx=(0, 8))

            self.group_rows_frame = self._frame(self.container)
            self.group_rows_frame.pack(fill="x")
            self._rebuild_group_rows()

            self._label(self.container,text="هر شناسهٔ گروه فقط می‌تواند به یک پروژه متصل باشد.",fg="#B84B4B").pack(anchor="e",pady=8)
            # قبلاً یک رشتهٔ بلندِ چندخطی با justify="right" بود - Tk هر خط را
            # که کاملاً لاتین بود (نام ربات‌ها، آدرس وب) بدون توجه به
            # راست‌چینِ بقیهٔ پاراگراف نشان می‌داد (لبهٔ راستِ آن خط‌ها با
            # لبهٔ راستِ خط‌های فارسی یکی نبود - چون خودِ Tk، نه فونت و نه
            # این کد، جهتِ هر خط را جدا تشخیص می‌دهد). راه‌حلِ مطمئن: هر خط
            # ویجتِ pack‌شدهٔ خودش را دارد با anchor="e" صریح - این را از
            # geometry manager می‌گیریم، نه از تشخیصِ جهتِ متنِ خودِ Tk.
            guide = self._frame(self.container)
            guide.configure(highlightbackground=self.palette.get('border_subtle', '#243244'), highlightthickness=1) if self.palette else None
            guide.pack(fill="both", expand=True, pady=(10, 0))

            # راهنما به‌مرور طولانی‌تر شده (چند ربات، دستور /getgroupid،
            # توضیح پیشوند -100) و دیگر همیشه در ارتفاعِ باقی‌مانده جا
            # نمی‌شود؛ برخلاف بقیهٔ این پنجره که دیگر اسکرول ندارد (دیدنِ
            # _fit_window)، همینِ یک بخش با Canvas+Scrollbar اسکرول می‌شود
            # تا هیچ‌وقت متنِ آخرش (دستورالعملِ نهاییِ «چهارم...») پشتِ لبهٔ
            # پنجره گم نشود - دقیقاً همون الگوی BarkavWindow._build_scrollable_body
            # در barkav_ui/window.py.
            bg = self.palette.get('bg', '#0E141B') if self.palette else guide.cget('bg')
            canvas = tk.Canvas(guide, bg=bg, highlightthickness=0, bd=0)
            scrollbar = ttk.Scrollbar(guide, orient='vertical', command=canvas.yview)
            canvas.configure(yscrollcommand=scrollbar.set)
            scrollbar.pack(side='left', fill='y')
            canvas.pack(side='left', fill='both', expand=True)

            inner = self._frame(canvas)
            item = canvas.create_window((10, 10), window=inner, anchor='nw')
            inner.bind('<Configure>', lambda _e: canvas.configure(scrollregion=canvas.bbox('all')))
            canvas.bind('<Configure>', lambda e: canvas.itemconfigure(item, width=max(0, e.width - 20)))
            canvas.bind('<MouseWheel>', lambda e: canvas.yview_scroll(int(-e.delta / 120), 'units'))
            canvas.bind('<Button-4>', lambda _e: canvas.yview_scroll(-3, 'units'))
            canvas.bind('<Button-5>', lambda _e: canvas.yview_scroll(3, 'units'))

            # نکتهٔ تازه (دیدیم حتی رقم فارسیِ چسبیده به پرانتز هم همین
            # مشکل رو داره): «۱) ...» با رقم فارسی+پرانتز شروع می‌شد و
            # همون رقم به‌جای لبهٔ راست، وسط/چپِ خط ظاهر می‌شد - یعنی این
            # باگ فقط دربارهٔ لاتین نبود، هر رقمی (حتی فارسی) که مستقیم به
            # یک علامتِ خنثی مثل ")" بچسبد و بعدش هم متنِ فارسی بیاد، دوباره
            # به‌هم می‌ریزد. راه‌حل امن: به‌جای «۱)»/«۲)» از خودِ کلمهٔ
            # فارسیِ ترتیبی (اول/دوم/...) استفاده شد - هیچ رقمی توش نیست.
            self._line(inner, "راهنما:")
            self._line(inner, "اول، یک گروه تلگرام برای این پروژه بساز (اگر هنوز نساخته‌ای).")
            self._line(inner, "دوم، از داخل گروه، گزینهٔ افزودن عضو را بزن و ربات بارکاو را با یوزرنیمش پیدا و اضافه کن؛ "
                  "بهتر است ربات را ادمین گروه هم بکنی تا بتواند پیام‌ها و رسیدها را بخواند.")
            self._line(inner, "سوم، برای پیدا کردن شناسهٔ عددی گروه، یکی از این دو راه را برو:")
            self._line(inner, "• یک ربات عمومیِ نمایش شناسه را موقتاً به همان گروه اضافه کن - بعد می‌توانی "
                  "آن را از گروه حذف کنی. نمونهٔ این ربات‌ها (با کلیک، کپی می‌شوند):", indent=20)
            self._copy_line(inner, "@getidsbot", indent=40)
            self._line(inner, "همین که اضافه شود، شناسهٔ گروه را خودش در یک پیام نشان می‌دهد "
                  "(معمولاً با علامت منفی شروع می‌شود).", indent=40)
            self._copy_line(inner, "@myidbot", indent=40)
            self._line(inner, "بعد از اضافه‌شدنِ این یکی، دستور زیر را همان‌جا داخل گروه بفرست تا شناسه را نشان دهد:", indent=40)
            self._copy_line(inner, "/getgroupid", indent=60)
            self._line(inner, "• یا نسخهٔ وب تلگرام را باز کن و همان عدد را از نشانیِ بالای صفحه ببین (با کلیک باز می‌شود):", indent=20)
            self._link_line(inner, "web.telegram.org", "https://web.telegram.org", indent=40)
            self._line(inner, "این عدد به‌تنهایی شناسهٔ گروه نیست - باید جلویش این پیشوند اضافه شود:", indent=20)
            self._line(inner, "-100", indent=40, justify='left', wraplength=0)
            self._line(inner, "مثال:", indent=20)
            self._line(inner, "1234567890  →  -1001234567890", indent=40, justify='left', wraplength=0)
            self._line(inner, "چهارم، همان عدد نهایی را (با علامت منفیِ جلویش) در کادر بالا وارد کن و به مرحلهٔ بعد برو تا اتصال بررسی شود.")
        elif self.step==2:
            # همین مشکل با «Bot API» وسط جمله - همان دلیل، همان راه‌حل.
            self._label(self.container,text="بعد از اضافه‌کردن ربات، روی «بررسی اتصال» بزن؛ برنامه عضویت و دسترسیِ گروه را از طریق واسط ربات تلگرام بررسی می‌کند.",wraplength=540,justify="right").pack(anchor="e",pady=10)
            self.verify_status=tk.StringVar(value="هنوز بررسی نشده")
            ttk.Button(self.container,text="🔌 بررسی اتصال ربات",command=self.verify_telegram,style=self._button_style or 'TButton').pack(pady=18)
            self.verify_status_label=self._label(self.container,textvariable=self.verify_status,font=("Tahoma",10,"bold"))
            self.verify_status_label.pack()
        else:
            if not self.vars["sheet"].get().strip():
                self.vars["sheet"].set(f"PEYMAAN-{self.registry._next_id()}")
            # همون قانون: "نام Spreadsheet" فارسی+لاتین بود، و پایین‌تر
            # "Group ID: ..." یک خط کاملاً لاتین وسط دو خط فارسی (نام/اتصال
            # ربات) بود - دقیقاً همون الگوی خط‌های @RawDataBot که راست‌چین
            # نمی‌شدن. هر دو با self._line/self._row پاک شدن.
            self._row("Spreadsheet","sheet")
            self._label(self.container,text="خلاصه",font=("Tahoma",10,"bold")).pack(anchor="e",pady=(18,4))
            group_ids = getattr(self, '_wizard_group_ids', [])
            self._line(self.container, f"نام: {self.vars['name'].get()}")
            self._line(self.container, "Group ID: " + ", ".join(str(g) for g in group_ids),
                      justify='left', wraplength=0)
            self._line(self.container, f"اتصال ربات: {'تأیید شده' if self.telegram_verified else 'تأیید نشده'}")
            self.next.configure(text="ذخیرهٔ تغییرات" if self.editing_project_id else "ایجاد پروژه")
        if self.step<3:self.next.configure(text="بعدی")
        self._fit_window()

    def prev(self):
        if self.step>0:self.step-=1;self._render()

    def next_step(self):
        if self.step==0 and not self.vars["name"].get().strip():
            messagebox.showwarning("پروژه","نام پروژه را وارد کن.",parent=self);return
        if self.step==1:
            try:
                count = max(1, min(20, int(str(self.vars['group_count'].get() or '1').strip())))
            except Exception:
                count = 1
            ids: list[int] = []
            for index in range(count):
                raw = self.vars.get(f'group_{index}')
                raw = raw.get().strip() if raw else ''
                label = "Group ID" if count == 1 else f"Group ID {index + 1}"
                try:
                    ids.append(int(raw))
                except Exception:
                    messagebox.showwarning("گروه", f"{label} را معتبر وارد کن.", parent=self); return
            if len(set(ids)) != len(ids):
                messagebox.showwarning("گروه", "دو گروه با شناسهٔ یکسان وارد شده.", parent=self); return
            for p in self.registry.list():
                if p.project_id == self.editing_project_id:
                    continue
                for gid in ids:
                    if p.group_chat_id == gid or gid in (p.group_chat_ids or []):
                        messagebox.showerror("گروه", f"این گروه قبلاً به «{p.name}» متصل است.", parent=self); return
            self._wizard_group_ids = ids
        if self.step==2 and not self.telegram_verified:
            messagebox.showwarning("اتصال","ابتدا اتصال ربات به گروه را با موفقیت بررسی کن.",parent=self);return
        if self.step<3:self.step+=1;self._render();return
        try:
            ids = getattr(self, '_wizard_group_ids', [])
            kwargs=dict(name=self.vars["name"].get(),group_chat_id=(ids[0] if ids else None),
                        group_chat_ids=ids,spreadsheet_name=self.vars["sheet"].get(),
                        address=self.vars["address"].get(),postal_code=self.vars["postal"].get(),
                        registration_plate=self.vars["plate"].get(),municipal_file_no=self.vars["municipal"].get(),
                        telegram_verified=self.telegram_verified)
            if self.editing_project_id:
                p=self.registry.update(self.editing_project_id,**kwargs)
            else:
                p=self.registry.create(**kwargs)
            self.on_done(p);self.destroy()
        except Exception as exc:
            messagebox.showerror("ذخیرهٔ پروژه" if self.editing_project_id else "ساخت پروژه",str(exc),parent=self)

    def verify_telegram(self):
        token=str(self.secrets.get("TELEGRAM_BOT_TOKEN") or "").strip()
        if not token:
            messagebox.showerror("Telegram","TELEGRAM_BOT_TOKEN در secrets.local.json نیست.",parent=self);return
        # حالا ممکنه چند گروه باشه - همه‌شون باید عضویت معتبر داشته باشن
        # تا پروژه «تأییدشده» حساب بشه، وگرنه ممکنه یکیشون اصلاً هنوز
        # ربات رو نداشته باشه و خبردار نشیم.
        ids = getattr(self, '_wizard_group_ids', None)
        if not ids:
            return
        default_fg=self.palette.get('text','#F1F5F9') if self.palette else 'black'
        self.verify_status_label.configure(fg=default_fg)
        self.verify_status.set("در حال بررسی...");self.update_idletasks()
        status_fa={"creator":"سازنده","administrator":"ادمین","member":"عضو عادی",
                   "restricted":"محدودشده","left":"خارج‌شده","kicked":"اخراج‌شده"}
        async def check_all():
            from telegram import Bot
            from telegram.request import HTTPXRequest
            req=HTTPXRequest(connect_timeout=20,read_timeout=30,write_timeout=30,pool_timeout=10,http_version="1.1")
            async with Bot(token=token,request=req) as bot:
                me=await bot.get_me()
                results=[]
                for gid in ids:
                    chat=await bot.get_chat(gid);member=await bot.get_chat_member(gid,me.id)
                    results.append((str(getattr(chat,"title","") or gid),str(getattr(member,"status","") or "")))
                return results
        try:
            results=asyncio.run(check_all())
            self.telegram_verified=all(status not in {"left","kicked"} for _title,status in results)
            summary="، ".join(f"«{title}» ({status_fa.get(status,status)})" for title,status in results)
            self.verify_status_label.configure(fg=self.palette.get('success','#22C55E') if self.telegram_verified
                                               else self.palette.get('danger','#DE6671'))
            self.verify_status.set(f"✓ اتصال تأیید شد — {summary}" if self.telegram_verified else f"عضویت معتبر نیست: {summary}")
        except Exception as exc:
            self.telegram_verified=False
            self.verify_status_label.configure(fg=self.palette.get('danger','#DE6671'))
            self.verify_status.set(f"✗ بررسی ناموفق: {exc.__class__.__name__}")
            messagebox.showerror("بررسی اتصال",f"اتصال به گروه تأیید نشد:\n{exc}",parent=self)


def choose_project(base_dir: str | Path) -> ProjectEntry | None:
    app=ProjectCenter(base_dir);app.mainloop();return app.result
