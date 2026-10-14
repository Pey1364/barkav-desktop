from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from copy import deepcopy
import asyncio
import threading
import tempfile
import os
import json
import sqlite3
import queue
import tkinter as tk
from tkinter import ttk, messagebox, filedialog


import dashboard_stage18 as v18
import dashboard_stage18_1 as v181
from dashboard_stage18_1 import (
    DARK, DB, APPROVAL, BASE_DIR, DateField, load_ui, fa, parse_int,
    normalize_shamsi, shamsi_to_gregorian, gregorian_to_shamsi,
)
from loan_service import LoanService, _add_months
import dashboard_stage16_3 as v163
import history_scope
import row_journal

VERSION = '18.2'
v18.VERSION = VERSION
v181.VERSION = VERSION

_PARTNER_NAMES = ('پیمان', 'پیام', 'سامان', 'سایر')
_PARTNER_KINDS = ('قرض', 'تزریق پول')

# Visual reference palettes sampled from the user-provided 2560x1440 target screens.
_THEME_DARK = {
    'bg': '#0C192A', 'surface': '#0E1E31', 'panel': '#152639', 'panel2': '#1B2D40',
    'glass': '#263648', 'line': '#384657', 'text': '#F3F5F7', 'muted': '#9AA8B8',
    'blue': '#55A3EC', 'green': '#57C894', 'orange': '#E6B34F', 'red': '#F1767D',
    'cyan': '#28AEB8', 'violet': '#9C8DDB', 'yellow': '#F4CE5B',
}
_THEME_LIGHT = {
    'bg': '#F8F9FA', 'surface': '#FFFFFF', 'panel': '#FDFDFD', 'panel2': '#F4F7FA',
    'glass': '#F3F6F9', 'line': '#D6DCE3', 'text': '#263442', 'muted': '#748292',
    'blue': '#3C8ED4', 'green': '#45B987', 'orange': '#E3A93F', 'red': '#E96F78',
    'cyan': '#20AEB9', 'violet': '#8F82D0', 'yellow': '#EFC95A',
}


def _is_light() -> bool:
    try:
        return str(load_ui().get('appearance') or 'dark').lower() == 'light'
    except Exception:
        return False


def _receipt_caption(row: dict, payload: dict | None = None) -> str:
    """Return only text directly attached to the receipt/message.

    New receipt analyses persist ``receipt_caption`` explicitly.  Older records
    fall back to Telegram ``raw_text`` which, for live photo messages, is the
    exact Telegram caption rather than the evidence window.
    """
    p = payload or row.get('payload') or {}
    for value in (p.get('receipt_caption'), row.get('raw_text')):
        text = str(value or '').strip()
        if text:
            return text
    return ''


def wizard_steps_182(title: str, subtype: str):
    """Final V18.2 wizard grouping locked by the user."""
    fields = v181.special_fields_181(title, subtype)
    by = {f.key: f for f in fields}
    preferred: list[list[str]] = []
    if title == 'هزینه ساخت' and subtype == 'نقدی':
        preferred = [
            ['payer_name', 'receiver_name', 'issuer_name'],
            ['description', 'payment_method'],
            ['invoice_amount', 'final_amount', 'discount_amount'],
            ['payment_state', 'total_debt', 'remaining_debt'],
            ['main_phase', 'sub_phase'],
        ]
    elif title == 'هزینه ساخت' and subtype == 'چک':
        preferred = [
            ['payer_name', 'receiver_name', 'description'],
            ['issuer_name', 'issuer_bank', 'cheque_type', 'is_guarantee'],
            ['cheque_registration_state', 'due_date_shamsi', 'cheque_status'],
            ['invoice_amount', 'final_amount', 'discount_amount'],
            ['payment_state', 'total_debt', 'remaining_debt'],
            ['main_phase', 'sub_phase'],
        ]
    elif title == 'ورودی' and subtype == 'فروش':
        preferred = [
            ['sale_id', 'sale_unit', 'sold_area'],
            ['payer_name', 'buyer_name'],
        ]
    elif title == 'ورودی' and subtype == 'تسهیلات':
        preferred = [
            ['loan_name', 'loan_bank', 'loan_total_amount'],
            ['installment_count', 'interest_rate'],
            ['guarantor_1', 'guarantor_2', 'guarantor_3'],
            ['loan_start_date', 'loan_end_date'],
        ]
    elif title == 'ورودی' and subtype == 'شرکا/قرض':
        preferred = [
            ['partner_name', 'partner_other_name'],
            ['partner_kind', 'loan_days', 'partner_return_date'],
        ]
    elif title == 'خروجی' and subtype == 'اقساط':
        preferred = [
            ['payer_name', 'loan_id'],
            ['loan_bank', 'loan_total_amount'],
            ['installment_count', 'paid_installments_before'],
            ['installments_paid_now', 'remaining_installments'],
        ]

    groups = []
    for keys in preferred:
        arr = [by[k] for k in keys if k in by]
        if arr:
            groups.append(arr)
    used = {f.key for group in groups for f in group}
    # cost_group and contract_id are asked on the wizard's first window, so
    # neither must fall through to a page of its own here as well.
    rest = [f for f in fields if f.key not in used
            and f.key not in ('cheque_amount', 'cost_group', 'contract_id')]
    for i in range(0, len(rest), 3):
        groups.append(rest[i:i + 3])
    return groups


def _retarget_fonts(root: tk.Misc, family: str = 'Segoe UI') -> None:
    """Normalize legacy explicit Tahoma/Arial widgets without changing sizes."""
    stack = [root]
    while stack:
        w = stack.pop()
        try:
            stack.extend(w.winfo_children())
        except Exception:
            pass
        try:
            font_value = w.cget('font')
        except Exception:
            continue
        if not font_value:
            continue
        try:
            import tkinter.font as tkfont
            actual = tkfont.Font(font=font_value).actual()
            fam = str(actual.get('family') or '')
            if fam.lower() in {'tahoma', 'arial', 'sans', 'sans-serif'}:
                weight = actual.get('weight', 'normal')
                slant = actual.get('slant', 'roman')
                size = int(actual.get('size') or 10)
                spec = [family, size]
                if weight == 'bold':
                    spec.append('bold')
                if slant == 'italic':
                    spec.append('italic')
                w.configure(font=tuple(spec))
        except Exception:
            pass



def _field_keys(title: str, subtype: str) -> set[str]:
    return {f.key for f in v181.special_fields_181(title, subtype)}


def _widget_host(widget):
    try:
        return widget.master if widget is not None else None
    except Exception:
        return None


class TransactionWizard182(v181.TransactionWizard181):
    """V18.2 wizard: persistent payload, true RTL pages and cross-step dependencies."""

    def __init__(self, parent, row, rich, on_done, on_full):
        self._closing_to_full = False
        # Work on a shallow row/deep payload copy so the cheque Wizard can use
        # the exact receipt caption as «بابت» without mutating the table object.
        row = dict(row or {})
        payload = deepcopy(dict(row.get('payload') or {}))
        title, subtype = v18._title_type_from_payload(payload)
        if title == 'هزینه ساخت' and subtype == 'چک':
            caption = _receipt_caption(row, payload)
            if caption:
                payload['description'] = caption
                payload['receipt_caption'] = caption
            # Keep backend compatibility even though cheque amount is no longer
            # displayed twice in the Wizard.
            payload['cheque_amount'] = int(payload.get('amount') or payload.get('paid_amount') or payload.get('cheque_amount') or 0)
        row['payload'] = payload
        super().__init__(parent, row, rich, on_done, on_full)
        self.font_family = 'Segoe UI'
        self.title('ثبت مرحله‌ای تراکنش — BARKAV 18.2')
        self.geometry('780x560')
        self.minsize(720, 520)

    def _build_shell(self):
        top = tk.Frame(self, bg=DARK['surface'], highlightbackground=DARK['line'], highlightthickness=1)
        top.pack(fill='x', padx=10, pady=10)
        tk.Label(top, text='ثبت مرحله‌ای', bg=DARK['surface'], fg=DARK['text'],
                 font=(self.font_family, self.font_size + 2, 'bold')).pack(side='right', padx=10, pady=(7, 2))
        tk.Label(top, text='هر مرحله فقط اطلاعات مرتبط با همان تراکنش را نشان می‌دهد.',
                 bg=DARK['surface'], fg=DARK['muted'],
                 font=(self.font_family, max(9, self.font_size - 1))).pack(side='right', padx=4, pady=(9, 2))
        self.step_lbl = tk.Label(top, text='', bg=DARK['surface'], fg=DARK['muted'],
                                 font=(self.font_family, self.font_size - 1, 'bold'))
        self.step_lbl.pack(side='left', padx=10)
        self.progress = ttk.Progressbar(top, mode='determinate', maximum=100, length=130)
        self.progress.pack(side='left', padx=8, pady=12)

        self.host = tk.Frame(self, bg=DARK['panel'], highlightbackground=DARK['line'], highlightthickness=1)
        self.host.pack(fill='both', expand=True, padx=10, pady=(0, 8))

        nav = tk.Frame(self, bg=DARK['bg'])
        nav.pack(fill='x', padx=10, pady=(0, 10))
        self.next_b = tk.Button(nav, text='بعدی', command=self.next, bg=DARK['blue'], fg='#FFFFFF',
                                activebackground='#8BC3F2', relief='flat', padx=22, pady=9,
                                font=(self.font_family, self.font_size, 'bold'))
        self.next_b.pack(side='right', padx=3)
        self.prev_b = tk.Button(nav, text='قبلی', command=self.prev, bg=DARK['glass'], fg=DARK['text'],
                                relief='flat', padx=16, pady=9, font=(self.font_family, self.font_size, 'bold'))
        self.prev_b.pack(side='right', padx=3)
        tk.Button(nav, text='رد کردن مرحله', command=self.next, bg=DARK['surface'], fg=DARK['muted'],
                  relief='flat', padx=12, pady=9).pack(side='left', padx=3)
        tk.Button(nav, text='فرم کامل', command=self._open_full, bg=DARK['surface'], fg=DARK['text'],
                  relief='flat', padx=12, pady=9).pack(side='left', padx=3)

    def _payload_from_vars(self, title: str, subtype: str):
        # The V18 base renderer recreates self.vars on every page.  Preserve the
        # four common values when the current specialization page does not have them.
        before = dict(self.payload or {})
        p = super()._payload_from_vars(title, subtype)
        if 'event_date_shamsi' not in self.vars:
            p['event_date_shamsi'] = before.get('event_date_shamsi') or ''
        if 'amount' not in self.vars:
            amount = int(before.get('amount') or before.get('paid_amount') or 0)
            p['amount'] = amount
            p['paid_amount'] = amount
        return p

    def _clear(self):
        for w in self.host.winfo_children():
            w.destroy()
        self.vars = {}
        self.widgets = {}

    def _show_page(self, load=False):
        self._clear()
        page = self.pages[self.page_index]

        # Every page lives in a scrollable canvas; navigation remains fixed below.
        shell = tk.Frame(self.host, bg=DARK['panel'])
        shell.pack(fill='both', expand=True)
        canvas = tk.Canvas(shell, bg=DARK['panel'], highlightthickness=0)
        scroll = ttk.Scrollbar(shell, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        body = tk.Frame(canvas, bg=DARK['panel'])
        body_id = canvas.create_window((0, 0), window=body, anchor='nw')
        body.grid_columnconfigure((0, 1), weight=1, uniform='wizard182')
        body.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')), add='+')
        canvas.bind('<Configure>', lambda e: canvas.itemconfigure(body_id, width=e.width), add='+')
        canvas.bind('<MouseWheel>', lambda e: (canvas.yview_scroll(int(-e.delta / 120), 'units'), 'break')[1], add='+')
        self._page_canvas = canvas

        content = tk.Frame(body, bg=DARK['panel'])
        content.pack(fill='both', expand=True, padx=20, pady=18)
        content.grid_columnconfigure((0, 1), weight=1, uniform='wizard182content')

        if self.page_index == 0:
            fds = page
            for i, fd in enumerate(fds):
                row, col = i // 2, 1 - (i % 2)  # true RTL: first field is right column
                # Everything except the two transaction-kind combos is an
                # ordinary field and is built as one. Naming the exceptions the
                # other way round meant a field added to this window later - the
                # دسته‌بندی combo - was drawn as the نوع تراکنش list.
                if fd.key not in {'v18_title', 'v18_subtype'}:
                    self._field(content, fd, row, col, width=29)
                    continue
                box = tk.Frame(content, bg=DARK['panel'])
                box.grid(row=row, column=col, sticky='nsew', padx=7, pady=8)
                box.grid_columnconfigure(0, weight=1)
                tk.Label(box, text=fd.label, bg=DARK['panel'], fg=DARK['text'],
                         font=(self.font_family, self.font_size, 'bold')).grid(row=0, column=0, sticky='e')
                if fd.key == 'v18_title':
                    value = tk.StringVar(value=self.title_var.get())
                    widget = ttk.Combobox(box, textvariable=value, state='readonly',
                                          values=list(v18.TITLE_TYPES), width=29)
                    widget.bind('<<ComboboxSelected>>',
                                lambda e, vv=value: self._title_changed(vv.get()), add='+')
                else:
                    values = list(v18.TITLE_TYPES.get(self.title_var.get(), []))
                    current = self.subtype_var.get()
                    if current not in values:
                        current = values[0] if values else ''
                        self.subtype_var.set(current)
                    value = tk.StringVar(value=current)
                    widget = ttk.Combobox(box, textvariable=value, state='readonly',
                                          values=values, width=29)
                    widget.bind('<<ComboboxSelected>>',
                                lambda e, vv=value: self._sub_changed(vv.get()), add='+')
                widget.grid(row=1, column=0, sticky='ew', pady=(5, 0))
                self.vars[fd.key] = value
                self.widgets[fd.key] = widget
                tk.Label(box, text=f"AI: {v18._ai_value(self.ai_original, fd.key)}",
                         bg=DARK['panel'], fg=DARK['muted'],
                         font=(self.font_family, max(8, self.font_size - 2))).grid(
                             row=2, column=0, sticky='e', pady=2)

            self._loading = True
            raw_date = str(self.payload.get('event_date_shamsi') or self.row.get('message_date') or '').strip()
            self.vars['event_date_shamsi'].set(raw_date.split()[0] if raw_date else '')
            self.vars['amount'].set(v18._group_money(
                self.payload.get('amount') or self.payload.get('paid_amount')
                or self.payload.get('final_amount') or 0))
            # دسته‌بندی/انتخاب قرارداد live only on this window - a re-edit that
            # doesn't restore them here shows both empty even though the payload
            # already carries them (this is the class the real app actually runs;
            # the base TransactionWizard18._show_page above is never reached for it).
            if 'cost_group' in self.vars:
                self.vars['cost_group'].set(str(self.payload.get('cost_group') or ''))
            if 'contract_id' in self.vars:
                self.vars['contract_id'].set(v18._contract_display(self.payload.get('contract_id')))
            self._loading = False

            # انتخاب قرارداد only means anything for پیمانکار work; خدمات and
            # مصالح have no contract to tie it to, so the box stays out of
            # the layout rather than sitting there disabled and unexplained.
            contract_box = self.widgets.get('contract_id')
            contract_box = contract_box.master if contract_box is not None else None

            def sync_contract_field(*_a):
                if contract_box is None:
                    return
                shown = self.vars.get('cost_group')
                if shown is not None and shown.get() == 'پیمانکار':
                    contract_box.grid()
                else:
                    contract_box.grid_remove()

            if 'cost_group' in self.vars:
                self.vars['cost_group'].trace_add('write', sync_contract_field)
            sync_contract_field()
        elif page:
            keys = [fd.key for fd in page]
            # Sale payer/buyer is intentionally vertical, payer first.
            if self.title_var.get() == 'ورودی' and self.subtype_var.get() == 'فروش' and keys == ['payer_name', 'buyer_name']:
                stack = tk.Frame(content, bg=DARK['panel'])
                stack.grid(row=0, column=0, columnspan=2, sticky='nsew', padx=40)
                stack.grid_columnconfigure(0, weight=1)
                for i, fd in enumerate(page):
                    self._field(stack, fd, i, 0, width=52)
            else:
                for i, fd in enumerate(page):
                    self._field(content, fd, i // 2, 1 - (i % 2), width=31)
            self._load_values(self.title_var.get(), self.subtype_var.get())
            self._after_page_render()
        else:
            self._render_review(content)

        total = max(1, len(self.pages))
        self.step_lbl.configure(text=f"مرحله {fa(self.page_index + 1)} از {fa(total)}")
        try:
            self.progress['value'] = ((self.page_index + 1) / total) * 100
        except Exception:
            pass
        self.prev_b.configure(state='normal' if self.page_index > 0 else 'disabled')
        self.next_b.configure(text='تأیید و ثبت' if self.page_index == len(self.pages) - 1 else 'بعدی')

    def _render_review(self, body):
        tk.Label(body, text='مرور نهایی', bg=DARK['panel'], fg=DARK['text'],
                 font=(self.font_family, self.font_size + 3, 'bold')).pack(anchor='e', pady=(8, 12))
        p = self.payload
        lines = [
            f"تاریخ: {fa(p.get('event_date_shamsi') or '-')}",
            f"مبلغ: {v18._group_money(p.get('amount'))}",
            f"عنوان: {self.title_var.get()}",
            f"نوع: {self.subtype_var.get()}",
        ]
        for fd in v181.special_fields_181(self.title_var.get(), self.subtype_var.get()):
            value = p.get(fd.key)
            if fd.key == 'partner_other_name' or value in (None, '', False):
                continue
            if fd.kind in {'money', 'int'}:
                value = v18._group_money(value)
            elif isinstance(value, (int, float)):
                value = fa(value)
            lines.append(f"{fd.label}: {value}")
        tk.Label(body, text='\n'.join(lines), bg=DARK['panel2'], fg=DARK['text'], justify='right', anchor='ne',
                 font=(self.font_family, self.font_size), padx=18, pady=16, wraplength=690).pack(fill='both', expand=True)

    def _after_page_render(self):
        title, subtype = self.title_var.get(), self.subtype_var.get()

        if title == 'ورودی' and subtype == 'شرکا/قرض':
            self._normalize_partner_display()
            if 'partner_name' in self.vars:
                self.vars['partner_name'].trace_add('write', lambda *_: self._partner_visibility_182())
            if 'partner_kind' in self.vars:
                self.vars['partner_kind'].trace_add('write', lambda *_: self._partner_visibility_182())
            if 'loan_days' in self.vars:
                self.vars['loan_days'].trace_add('write', lambda *_: self._partner_date_sync_182())
            self._partner_visibility_182()

        if title == 'ورودی' and subtype == 'فروش':
            if 'sale_unit' in self.vars:
                self.vars['sale_unit'].trace_add('write', lambda *_: self._sale_area_visibility_182())
            self._sale_area_visibility_182()

        if title == 'ورودی' and subtype == 'تسهیلات':
            if 'loan_start_date' in self.vars:
                self.vars['loan_start_date'].trace_add('write', lambda *_: self._loan_date_sync_182())
            if 'installment_count' in self.vars:
                self.vars['installment_count'].trace_add('write', lambda *_: self._loan_date_sync_182())
            self._loan_date_sync_182()

        if title == 'خروجی' and subtype == 'اقساط':
            if 'installments_paid_now' in self.vars:
                self.vars['installments_paid_now'].trace_add('write', lambda *_: self._installment_count_sync_182())
            self._installment_count_sync_182()

        if title == 'هزینه ساخت':
            if 'invoice_amount' in self.vars:
                self.vars['invoice_amount'].trace_add('write', lambda *_: self._sync_discount_182())
            if 'final_amount' in self.vars:
                self.vars['final_amount'].trace_add('write', lambda *_: self._sync_discount_182())
            if 'payment_state' in self.vars:
                self.vars['payment_state'].trace_add('write', lambda *_: self._sync_remaining_debt_182())
            if 'total_debt' in self.vars:
                self.vars['total_debt'].trace_add('write', lambda *_: self._sync_remaining_debt_182())
            self._sync_discount_182()
            self._sync_remaining_debt_182()

    def _title_changed(self, title):
        self.title_var.set(title)
        values = list(v18.TITLE_TYPES.get(title, []))
        first = values[0] if values else ''
        self.subtype_var.set(first)
        w = self.widgets.get('v18_subtype')
        if w is not None:
            try:
                w.configure(values=values)
                if 'v18_subtype' in self.vars:
                    self.vars['v18_subtype'].set(first)
            except Exception:
                pass

    def _sub_changed(self, sub):
        self.subtype_var.set(sub)

    def _refresh_subphase(self):
        super()._refresh_subphase()
        try:
            var = self.vars.get('sub_phase')
            widget = self.widgets.get('sub_phase')
            if var is not None and widget is not None and not str(var.get() or '').strip():
                vals = list(getattr(widget, '_all', []) or widget.cget('values') or [])
                if vals:
                    var.set(vals[0])
        except Exception:
            pass

    def _sync_discount_182(self):
        if getattr(self, '_loading', False):
            return
        if not all(k in self.vars for k in ('invoice_amount', 'final_amount', 'discount_amount')):
            return
        try:
            invoice = parse_int(self.vars['invoice_amount'].get())
            final = parse_int(self.vars['final_amount'].get())
            value = max(invoice - final, 0) if invoice > 0 and final >= 0 else 0
            self._loading = True
            self.vars['discount_amount'].set(v18._group_money(value))
            self.payload['discount_amount'] = value
        finally:
            self._loading = False

    def _sync_remaining_debt_182(self):
        if getattr(self, '_loading', False):
            return
        if not all(k in self.vars for k in ('payment_state', 'total_debt', 'remaining_debt')):
            return
        try:
            state = str(self.vars['payment_state'].get() or '')
            total = max(0, parse_int(self.vars['total_debt'].get()))
            paid = max(0, int(self.payload.get('amount') or self.payload.get('paid_amount') or 0))
            if state == 'تسویه':
                remaining = 0
            elif state == 'پرداخت‌نشده':
                remaining = total
            else:
                remaining = max(total - paid, 0)
            self._loading = True
            self.vars['remaining_debt'].set(v18._group_money(remaining))
            self.payload['remaining_debt'] = remaining
        finally:
            self._loading = False

    def _normalize_partner_display(self):
        actual = str(self.payload.get('partner_name') or '').strip()
        other = str(self.payload.get('partner_other_name') or '').strip()
        self._loading = True
        try:
            if 'partner_name' in self.vars:
                if actual and actual not in _PARTNER_NAMES:
                    self.vars['partner_name'].set('سایر')
                    if 'partner_other_name' in self.vars:
                        self.vars['partner_other_name'].set(other or actual)
                elif not actual:
                    self.vars['partner_name'].set('پیمان')
            if 'partner_kind' in self.vars and self.vars['partner_kind'].get() not in _PARTNER_KINDS:
                self.vars['partner_kind'].set(str(self.payload.get('partner_kind') or 'تزریق پول') if str(self.payload.get('partner_kind') or '') in _PARTNER_KINDS else 'تزریق پول')
        finally:
            self._loading = False

    def _partner_visibility_182(self):
        name = str(self.vars['partner_name'].get() if self.vars.get('partner_name') else self.payload.get('partner_name') or '')
        kind = str(self.vars['partner_kind'].get() if self.vars.get('partner_kind') else self.payload.get('partner_kind') or 'تزریق پول')
        if kind not in _PARTNER_KINDS:
            kind = 'تزریق پول'
            if self.vars.get('partner_kind'):
                self.vars['partner_kind'].set(kind)
        w = self.widgets.get('partner_other_name')
        host = _widget_host(w)
        try:
            (host.grid() if name == 'سایر' else host.grid_remove())
            w.configure(state='normal' if name == 'سایر' else 'disabled')
        except Exception:
            pass
        for key in ('loan_days', 'partner_return_date'):
            w = self.widgets.get(key)
            host = _widget_host(w)
            try:
                if kind == 'قرض':
                    host.grid()
                else:
                    host.grid_remove()
                if isinstance(w, DateField):
                    w.entry.configure(state='normal' if kind == 'قرض' else 'disabled')
                else:
                    w.configure(state='normal' if kind == 'قرض' else 'disabled')
            except Exception:
                pass

    def _partner_date_sync_182(self):
        if 'partner_return_date' not in self.vars:
            return
        try:
            days = parse_int(self.vars['loan_days'].get() if self.vars.get('loan_days') else self.payload.get('loan_days'))
            sh = normalize_shamsi(str(self.payload.get('event_date_shamsi') or ''))
            if not sh or days <= 0:
                return
            gd = date.fromisoformat(shamsi_to_gregorian(sh)) + timedelta(days=days)
            self._loading = True
            self.vars['partner_return_date'].set(gregorian_to_shamsi(gd))
        except Exception:
            pass
        finally:
            self._loading = False

    def _loan_date_sync_182(self):
        if 'loan_end_date' not in self.vars:
            return
        try:
            start = str(self.vars['loan_start_date'].get() if self.vars.get('loan_start_date') else self.payload.get('loan_start_date') or '')
            count = parse_int(self.vars['installment_count'].get() if self.vars.get('installment_count') else self.payload.get('installment_count'))
            sh = normalize_shamsi(start)
            if not sh or count <= 0:
                return
            gd = date.fromisoformat(shamsi_to_gregorian(sh))
            self._loading = True
            self.vars['loan_end_date'].set(gregorian_to_shamsi(_add_months(gd, count)))
        except Exception:
            pass
        finally:
            self._loading = False

    def _installment_count_sync_182(self):
        if 'remaining_installments' not in self.vars:
            return
        total = parse_int(self.vars['installment_count'].get() if self.vars.get('installment_count') else self.payload.get('installment_count'))
        before = parse_int(self.vars['paid_installments_before'].get() if self.vars.get('paid_installments_before') else self.payload.get('paid_installments_before'))
        now = max(0, parse_int(self.vars['installments_paid_now'].get() if self.vars.get('installments_paid_now') else self.payload.get('installments_paid_now')))
        self._loading = True
        try:
            self.vars['remaining_installments'].set(v18._group_money(max(total - before - now, 0)))
        finally:
            self._loading = False

    def _loan_selected(self, value: str):
        lid = str(value or '').split('|', 1)[0].strip()
        if not lid:
            return
        try:
            loan = LoanService(DB).get_loan(lid) or {}
            paid = int(loan.get('paid_installments') or 0)
            if not paid:
                with DB.read() as con:
                    paid = con.execute("SELECT COUNT(*) FROM loan_installments WHERE loan_id=? AND status='PAID'", (lid,)).fetchone()[0]
            vals = {
                'loan_id': value,
                'loan_bank': loan.get('lender_name') or '',
                'loan_total_amount': loan.get('principal_amount') or 0,
                'installment_count': loan.get('installment_count') or 0,
                'paid_installments_before': paid,
                'installments_paid_now': 1,
                'remaining_installments': max(int(loan.get('installment_count') or 0) - paid - 1, 0),
            }
            self.payload['selected_loan_name'] = loan.get('description') or loan.get('lender_name') or lid
            self.payload.update(vals)
            self._loading = True
            for key, val in vals.items():
                if key in self.vars:
                    self.vars[key].set(v18._group_money(val) if isinstance(val, (int, float)) else str(val))
        finally:
            self._loading = False

    def _sale_selected_181(self, value: str):
        sid = str(value or '').split('|', 1)[0].strip()
        if not sid:
            return
        try:
            with DB.read() as con:
                r = con.execute("""
                    SELECT s.sale_id,s.buyer_name,s.unit_id,u.display_unit_id,u.unit_number,u.floor,u.area
                    FROM sales s LEFT JOIN units u ON u.unit_id=s.unit_id WHERE s.sale_id=?
                """, (sid,)).fetchone()
            if not r:
                return
            unit_display = 'سایر'
            if r['unit_id']:
                unit_display = f"{r['unit_id']} | {r['display_unit_id'] or r['unit_number'] or '-'} | طبقه {r['floor'] or '-'} | {r['area'] or 0} M2"
            vals = {
                'sale_id': sid,
                'sale_unit': unit_display,
                'buyer_name': r['buyer_name'] or '',
                'payer_name': r['buyer_name'] or '',
                'sold_area': r['area'] or 0,
            }
            self.payload.update(vals)
            self._loading = True
            for key, val in vals.items():
                if key in self.vars:
                    self.vars[key].set(str(val))
        finally:
            self._loading = False
        self._sale_area_visibility_182()

    def _sale_unit_selected_181(self, value: str):
        value = str(value or '').strip()
        if not value:
            return
        if value == 'سایر':
            self.payload['sale_unit'] = 'سایر'
            if 'sale_unit' in self.vars:
                self.vars['sale_unit'].set('سایر')
            self._sale_area_visibility_182()
            return
        uid = value.split('|', 1)[0].strip()
        try:
            with DB.read() as con:
                r = con.execute("""
                    SELECT u.area,s.sale_id,s.buyer_name
                    FROM units u LEFT JOIN sales s ON s.unit_id=u.unit_id AND s.status!='CANCELLED'
                    WHERE u.unit_id=? ORDER BY s.created_at DESC LIMIT 1
                """, (uid,)).fetchone()
            vals = {'sale_unit': value, 'sold_area': (r['area'] if r else 0) or 0}
            if r and r['sale_id']:
                vals.update({'sale_id': r['sale_id'], 'buyer_name': r['buyer_name'] or '', 'payer_name': r['buyer_name'] or ''})
            self.payload.update(vals)
            self._loading = True
            for key, val in vals.items():
                if key in self.vars:
                    self.vars[key].set(str(val))
        finally:
            self._loading = False
        self._sale_area_visibility_182()

    def _sale_area_visibility_182(self):
        selected = str(self.vars['sale_unit'].get() if self.vars.get('sale_unit') else self.payload.get('sale_unit') or '')
        other = selected == 'سایر'
        w = self.widgets.get('sold_area')
        host = _widget_host(w)
        try:
            (host.grid() if other else host.grid_remove())
            w.configure(state='normal' if other else 'disabled')
        except Exception:
            pass

    def _capture(self):
        if self.page_index == 0:
            self.title_var.set(self.vars['v18_title'].get())
            self.subtype_var.set(self.vars['v18_subtype'].get())
            self.payload['event_date_shamsi'] = self.vars['event_date_shamsi'].get().strip()
            self.payload['amount'] = parse_int(self.vars['amount'].get())
            self.payload['paid_amount'] = self.payload['amount']
            self.payload['v18_title'] = self.title_var.get()
            self.payload['v18_subtype'] = self.subtype_var.get()
            # دسته‌بندی and انتخاب قرارداد exist only on this window (see
            # _rebuild_pages); leaving this page clears self.vars for every
            # key it built, so unlike an ordinary field, nothing captures
            # them again once the wizard has moved on - they have to be
            # saved here or they are gone.
            if 'cost_group' in self.vars:
                self.payload['cost_group'] = self.vars['cost_group'].get().strip()
            if 'contract_id' in self.vars:
                self.payload['contract_id'] = self.vars['contract_id'].get().split('|', 1)[0].strip()
            return
        if self.pages[self.page_index]:
            self.payload = self._payload_from_vars(self.title_var.get(), self.subtype_var.get())

    def _validate_current(self):
        title, sub = self.title_var.get(), self.subtype_var.get()
        if self.page_index == 0:
            if not title or not sub:
                raise ValueError('عنوان تراکنش و نوع تراکنش را انتخاب کن.')
            return
        if title == 'ورودی' and sub == 'شرکا/قرض':
            visible_name = str(self.vars['partner_name'].get() if self.vars.get('partner_name') else '')
            name = str(self.payload.get('partner_name') or '')
            other = str(self.payload.get('partner_other_name') or '')
            if visible_name == 'سایر' and not other:
                raise ValueError('نام واریزکننده را برای گزینه «سایر» وارد کن.')
            kind = str(self.payload.get('partner_kind') or 'تزریق پول')
            if kind == 'قرض' and self.page_index >= 2:
                if parse_int(self.payload.get('loan_days')) <= 0 and not normalize_shamsi(str(self.payload.get('partner_return_date') or '')):
                    raise ValueError('برای قرض، مدت قرض یا تاریخ برگشت را وارد کن.')
        if title == 'ورودی' and sub == 'فروش' and str(self.payload.get('sale_unit') or '') == 'سایر':
            if float(self.payload.get('sold_area') or 0) <= 0:
                raise ValueError('متراژ فروخته‌شده را برای گزینه «سایر» وارد کن.')

    def next(self):
        try:
            self._capture()
            self._validate_current()
        except Exception as exc:
            return messagebox.showwarning('ثبت مرحله‌ای', str(exc), parent=self)

        if self.page_index == 0:
            self.pages = [[
                v18.FieldDef('event_date_shamsi', 'تاریخ', 'date'),
                v18.FieldDef('amount', 'مبلغ', 'money'),
                v18.FieldDef('v18_title', 'عنوان تراکنش', 'titlecombo'),
                v18.FieldDef('v18_subtype', 'نوع تراکنش', 'subcombo'),
            ]] + wizard_steps_182(self.title_var.get(), self.subtype_var.get()) + [[]]
            self.page_index = 1 if len(self.pages) > 1 else 0
            return self._show_page()

        if self.page_index >= len(self.pages) - 1:
            try:
                p = dict(self.payload)
                p['v18_manual_fields'] = sorted(self.manual_fields)
                msg = v18.submit_v18(self.pid, p, self.rich)
                messagebox.showinfo('ثبت', msg, parent=self)
                self.on_done()
                self.destroy()
            except Exception as exc:
                messagebox.showerror('تأیید انجام نشد', str(exc), parent=self)
            return

        self.page_index += 1
        self._show_page()

    def prev(self):
        try:
            self._capture()
        except Exception:
            pass
        if self.page_index > 0:
            self.page_index -= 1
            self._show_page()

    def _open_full(self):
        if self._closing_to_full:
            return
        self._closing_to_full = True
        try:
            self._capture()
            if v18.DB.get_financial_posting(self.pid):
                v18.DB.begin_posting_revision(pending_id=self.pid, new_payload=dict(self.payload),
                                              source='GUI_187_EDIT', actor_id='GUI')
            else:
                APPROVAL.save_payload(self.pid, self.payload, learn=False)
        except Exception:
            pass
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()
        self.on_full()


class UnifiedPendingEditor182(v181.UnifiedPendingEditor181):
    """Full editor with the same partner defaults/conditional behavior as the wizard."""

    def _load_values(self, title: str, subtype: str):
        super()._load_values(title, subtype)
        if title == 'ورودی' and subtype == 'شرکا/قرض':
            actual = str(self.payload.get('partner_name') or '').strip()
            other = str(self.payload.get('partner_other_name') or '').strip()
            self._loading = True
            try:
                if 'partner_name' in self.vars:
                    if actual and actual not in _PARTNER_NAMES:
                        self.vars['partner_name'].set('سایر')
                        if 'partner_other_name' in self.vars:
                            self.vars['partner_other_name'].set(other or actual)
                    elif not actual:
                        self.vars['partner_name'].set('پیمان')
                if 'partner_kind' in self.vars and self.vars['partner_kind'].get() not in _PARTNER_KINDS:
                    self.vars['partner_kind'].set('تزریق پول')
            finally:
                self._loading = False

    def payload_from_form(self):
        p = super().payload_from_form()
        title, subtype = self.title_var.get(), self.subtype_var.get()
        if title == 'ورودی' and subtype == 'شرکا/قرض':
            if str(p.get('partner_kind') or '') not in _PARTNER_KINDS:
                p['partner_kind'] = 'تزریق پول'
            if str(self.vars.get('partner_name').get() if self.vars.get('partner_name') else '') == 'سایر' and not str(p.get('partner_name') or '').strip():
                raise ValueError('نام واریزکننده را برای گزینه «سایر» وارد کن.')
            if p.get('partner_kind') == 'قرض' and parse_int(p.get('loan_days')) <= 0 and not normalize_shamsi(str(p.get('partner_return_date') or '')):
                raise ValueError('برای قرض، مدت قرض یا تاریخ برگشت را وارد کن.')
        if title == 'ورودی' and subtype == 'فروش' and str(p.get('sale_unit') or '') == 'سایر' and float(p.get('sold_area') or 0) <= 0:
            raise ValueError('متراژ فروخته‌شده را برای گزینه «سایر» وارد کن.')
        return p


class DataEntryCenter182(v181.DataEntryCenter181):
    def open_wizard(self, row=None):
        row = row or self.current
        if not row:
            return messagebox.showwarning('ثبت دیتا', 'یک سطر را انتخاب کن.', parent=self)

        def full():
            fresh = DB.get_pending_item(str(row['pending_id'])) or row
            fresh = dict(fresh)
            fresh['raw_text'] = v18._raw_text(str(row['pending_id']), row)
            UnifiedPendingEditor182(self, fresh, self.rich, self.refresh)

        TransactionWizard182(self, row, self.rich, self.refresh, full)

    def open_editor(self, row=None):
        row = row or self.current
        if row:
            UnifiedPendingEditor182(self, row, self.rich, self.refresh)


class Stage182Dashboard(v181.Stage181Dashboard):
    def __init__(self):
        super().__init__()
        self.title('BARKAV — Engineering & Construction — Version 18.2')

    def _build_approval_center(self):
        tab = ttk.Frame(self.notebook, style='Panel.TFrame')
        self.approval_tab = tab
        self.notebook.insert(1, tab, text='ثبت دیتا')
        self.approval_center = DataEntryCenter182(tab, self.rich, on_posted=self.refresh_all)
        self.approval_center.pack(fill='both', expand=True)
        if self._bot_process:
            self.approval_center.set_bot_process(self._bot_process, self._bot_log)
        self.after_idle(self._rebuild_navbar)

    def export_development_package(self):
        from tkinter import filedialog
        dest = filedialog.asksaveasfilename(parent=self, defaultextension='.zip',
                                            initialfile='BARKAV_Development_Package_18.2.zip',
                                            filetypes=[('ZIP', '*.zip')])
        if not dest:
            return
        try:
            res = v18.v175.v174.build_development_package(BASE_DIR, Path(dest), VERSION)
            messagebox.showinfo('بسته توسعه', f"بسته توسعه {VERSION} ساخته شد:\n{res['path']}\n\nدیتابیس زنده و secrets وارد بسته نشده‌اند.", parent=self)
        except Exception as exc:
            messagebox.showerror('بسته توسعه', str(exc), parent=self)


# ---------------------------------------------------------------------------
# V18.2 final stabilization layer — user-locked Data Entry + visual behavior
# ---------------------------------------------------------------------------
class PendingTable182(v181.PendingTable181):
    """V18.2 table with deterministic paste below the selected target row."""
    def __init__(self, parent, on_open, on_delete, on_copy, on_paste, on_add,
                 on_approve, on_reject, on_reprocess, on_export):
        super().__init__(parent, on_open, on_delete, on_copy, on_add,
                         on_approve, on_reject, on_reprocess, on_export)
        self.on_paste = on_paste
        try:
            self.menu.insert_command(6, label='📌 چسباندن زیر سطر', command=lambda: self.on_paste(self.selected_rows()))
        except Exception:
            self.menu.add_command(label='📌 چسباندن زیر سطر', command=lambda: self.on_paste(self.selected_rows()))


class _UnifiedPendingEditor182Final(UnifiedPendingEditor182):
    """Scrollable RTL full editor matching the final 18.2 specification."""
    def __init__(self, parent, row, rich, on_done, *, navigation_rows=None,
                 navigation_index=0, on_record_open=None):
        self._navigation_rows_182 = [dict(item) for item in (navigation_rows or [])]
        self._navigation_index_182 = int(navigation_index or 0)
        self._approved_editor_182 = False
        self._on_record_open_182 = on_record_open
        row = dict(row or {})
        payload = deepcopy(dict(row.get('payload') or {}))
        title, subtype = v18._title_type_from_payload(payload)
        if title == 'هزینه ساخت' and subtype == 'چک':
            caption = _receipt_caption(row, payload)
            if caption:
                payload['description'] = caption
                payload['receipt_caption'] = caption
            payload['cheque_amount'] = int(payload.get('amount') or payload.get('paid_amount') or payload.get('cheque_amount') or 0)
        row['payload'] = payload
        super().__init__(parent, row, rich, on_done)
        self.font_family = 'Segoe UI'
        _retarget_fonts(self)
        self._navigation_baseline_182 = self._navigation_values_182()
        if callable(self._on_record_open_182):
            self._on_record_open_182(self.pid)

    def _build(self):
        head = tk.Frame(self, bg=DARK['surface'], highlightbackground=DARK['line'], highlightthickness=1)
        head.pack(fill='x', padx=10, pady=8)
        tk.Label(head, text='ویرایش و تأیید رکورد', bg=DARK['surface'], fg=DARK['text'],
                 font=('Segoe UI', self.font_size + 2, 'bold')).pack(side='right', padx=12, pady=8)
        self.msg = tk.StringVar(value='')
        tk.Label(head, textvariable=self.msg, bg=DARK['surface'], fg=DARK['muted'],
                 font=('Segoe UI', max(8, self.font_size - 1))).pack(side='left', padx=10)

        pane = ttk.Panedwindow(self, orient='horizontal')
        pane.pack(fill='both', expand=True, padx=10, pady=(0, 8))
        left = tk.Frame(pane, bg=DARK['panel'], highlightbackground=DARK['line'], highlightthickness=1)
        right = tk.Frame(pane, bg=DARK['panel'], highlightbackground=DARK['line'], highlightthickness=1)
        pane.add(left, weight=35)
        pane.add(right, weight=65)

        # Evidence / receipt side.
        imgf = tk.Frame(left, bg=DARK['surface'])
        imgf.pack(fill='both', expand=True, padx=7, pady=(7, 4))
        imgf.grid_rowconfigure(0, weight=1); imgf.grid_columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(imgf, bg=DARK['surface'], highlightthickness=0)
        ys = ttk.Scrollbar(imgf, orient='vertical', command=self.canvas.yview)
        xs = ttk.Scrollbar(imgf, orient='horizontal', command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        self.canvas.grid(row=0, column=0, sticky='nsew'); ys.grid(row=0, column=1, sticky='ns'); xs.grid(row=1, column=0, sticky='ew')
        self.canvas.bind('<MouseWheel>', self._wheel)
        self.canvas.bind('<ButtonPress-1>', lambda e: self.canvas.scan_mark(e.x, e.y))
        self.canvas.bind('<B1-Motion>', lambda e: self.canvas.scan_dragto(e.x, e.y, gain=1))
        z = tk.Frame(left, bg=DARK['panel']); z.pack(fill='x', padx=7)
        for text, cmd in [('−', lambda: self._set_zoom(self._zoom / 1.2)), ('Fit', self._fit_image), ('+', lambda: self._set_zoom(self._zoom * 1.2))]:
            tk.Button(z, text=text, command=cmd, bg=DARK['glass'], fg=DARK['text'], relief='flat', width=5).pack(side='left', padx=2, pady=3)
        self.caption = tk.Text(left, height=7, wrap='word', bg=DARK['surface'], fg=DARK['text'],
                               insertbackground=DARK['text'], relief='flat', font=('Segoe UI', self.font_size + 1), padx=10, pady=8)
        self.caption.pack(fill='x', padx=7, pady=(3, 7)); self.caption.configure(state='disabled')

        # Right side is one scrollable form canvas; action buttons stay fixed below.
        scroll_shell = tk.Frame(right, bg=DARK['panel'])
        scroll_shell.pack(fill='both', expand=True)
        form_canvas = tk.Canvas(scroll_shell, bg=DARK['panel'], highlightthickness=0)
        form_scroll = ttk.Scrollbar(scroll_shell, orient='vertical', command=form_canvas.yview)
        form_canvas.configure(yscrollcommand=form_scroll.set)
        form_canvas.pack(side='left', fill='both', expand=True); form_scroll.pack(side='right', fill='y')
        form_body = tk.Frame(form_canvas, bg=DARK['panel'])
        form_id = form_canvas.create_window((0, 0), window=form_body, anchor='nw')
        form_body.bind('<Configure>', lambda e: form_canvas.configure(scrollregion=form_canvas.bbox('all')), add='+')
        form_canvas.bind('<Configure>', lambda e: form_canvas.itemconfigure(form_id, width=e.width), add='+')
        form_canvas.bind('<MouseWheel>', lambda e: (form_canvas.yview_scroll(int(-e.delta / 120), 'units'), 'break')[1], add='+')
        self._form_canvas = form_canvas

        self.main = v18.GlassSection(form_body, 'مشخصات تراکنش')
        self.main.pack(fill='both', expand=True, padx=8, pady=8)
        b = self.main.body; b.grid_columnconfigure((0, 1), weight=1, uniform='editor182')
        self.title_var = tk.StringVar(); self.subtype_var = tk.StringVar()

        # User-locked RTL pairing: date right / amount left.
        for fd, col in [(v18.FieldDef('event_date_shamsi', 'تاریخ', 'date'), 1),
                        (v18.FieldDef('amount', 'مبلغ', 'money'), 0)]:
            self._field(b, fd, 0, col, width=28)

        # User-locked RTL pairing: title right / subtype left.
        for key, label, col in [('v18_title', 'عنوان تراکنش', 1), ('v18_subtype', 'نوع تراکنش', 0)]:
            box = tk.Frame(b, bg=DARK['panel']); box.grid(row=1, column=col, sticky='nsew', padx=5, pady=4); box.grid_columnconfigure(0, weight=1)
            tk.Label(box, text=label, bg=DARK['panel'], fg=DARK['text'], font=('Segoe UI', self.font_size, 'bold')).grid(row=0, column=0, sticky='e')
            var = self.title_var if key == 'v18_title' else self.subtype_var
            vals = list(v18.TITLE_TYPES) if key == 'v18_title' else []
            w = ttk.Combobox(box, textvariable=var, state='readonly', values=vals, width=28)
            w.grid(row=1, column=0, sticky='ew', pady=(3, 0)); self.vars[key] = var; self.widgets[key] = w
            tk.Label(box, text=f"AI: {v18._ai_value(self.ai_original, key)}", bg=DARK['panel'], fg=DARK['muted'],
                     font=('Segoe UI', max(7, self.font_size - 2))).grid(row=2, column=0, sticky='e', pady=2)
        self.widgets['v18_title'].bind('<<ComboboxSelected>>', lambda e: self._title_changed(), add='+')
        self.widgets['v18_subtype'].bind('<<ComboboxSelected>>', lambda e: self._sub_changed(), add='+')

        # دسته‌بندی sits with the general fields, the same box ثبت دیتا's own
        # wizard already puts it in - not buried inside the type-specific card
        # below, which is also where انتخاب قرارداد's own show/hide depends on
        # it. Built once here rather than by _build_special, which tears its
        # own card down and rebuilds it on every subtype change.
        self.cost_group_row = tk.Frame(b, bg=DARK['panel'])
        self.cost_group_row.grid(row=2, column=0, columnspan=2, sticky='nsew', pady=(4, 0))
        self.cost_group_row.grid_columnconfigure((0, 1), weight=1, uniform='editor182')
        self._field(self.cost_group_row, v18.FieldDef('contract_id', 'انتخاب قرارداد', 'contract'), 0, 0, width=28)
        self._field(self.cost_group_row, v18.FieldDef('cost_group', 'دسته‌بندی', 'combo', tuple(v18.COST_GROUPS)), 0, 1, width=28)
        self.vars['cost_group'].trace_add('write', lambda *_: self._contract_field_sync())

        self.special_host = tk.Frame(b, bg=DARK['panel'])
        self.special_host.grid(row=3, column=0, columnspan=2, sticky='nsew', pady=(8, 0)); b.grid_rowconfigure(3, weight=1)
        title, sub = v18._title_type_from_payload(self.payload)
        valid = list(v18.TITLE_TYPES.get(title, []))
        if sub not in valid: sub = valid[0] if valid else ''
        self.title_var.set(title); self.subtype_var.set(sub); self.widgets['v18_subtype'].configure(values=valid)
        self._sync_cost_group_row_182()
        self._build_special(title, sub); self._load_values(title, sub)
        self._contract_field_sync()

        action = tk.Frame(self, bg=DARK['surface'], highlightbackground=DARK['line'], highlightthickness=1)
        action.pack(fill='x', padx=10, pady=(0, 10))
        self._confirm_button_182 = ttk.Button(
            action, text='تأیید و ثبت', command=self.approve,
            style='Primary.TButton',
        )
        self._confirm_button_182.pack(side='right', padx=4, pady=5)
        ttk.Button(
            action, text='رد', command=self.reject, style='Toolbar.TButton',
        ).pack(side='right', padx=4, pady=5)
        self._previous_button_182 = ttk.Button(
            action, text='‹ قبلی', command=lambda: self._navigate_record_182(-1),
            style='Toolbar.TButton',
        )
        self._previous_button_182.pack(side='left', padx=4, pady=5)
        self._next_button_182 = ttk.Button(
            action, text='بعدی ›', command=lambda: self._navigate_record_182(1),
            style='Toolbar.TButton',
        )
        self._next_button_182.pack(side='left', padx=4, pady=5)
        self._sync_navigation_buttons_182()

    def _navigation_values_182(self):
        values = {}
        for key, variable in (getattr(self, 'vars', {}) or {}).items():
            try:
                values[key] = variable.get()
            except (AttributeError, tk.TclError):
                continue
        return values

    def _sync_navigation_buttons_182(self):
        rows = getattr(self, '_navigation_rows_182', [])
        index = getattr(self, '_navigation_index_182', 0)
        try:
            self._previous_button_182.configure(state='normal' if index > 0 else 'disabled')
            self._next_button_182.configure(state='normal' if index < len(rows) - 1 else 'disabled')
        except (AttributeError, tk.TclError):
            pass

    def _mark_manual(self, key):
        super()._mark_manual(key)
        if getattr(self, '_approved_editor_182', False):
            self._approved_editor_182 = False
            try:
                self._confirm_button_182.configure(text='تأیید و ثبت', state='normal')
                self.msg.set('اصلاح جدید وارد شد؛ برای اعمال آن دوباره «تأیید و ثبت» را بزنید.')
            except (AttributeError, tk.TclError):
                pass

    def _navigate_record_182(self, direction):
        rows = getattr(self, '_navigation_rows_182', [])
        target_index = self._navigation_index_182 + int(direction)
        if target_index < 0 or target_index >= len(rows):
            return
        current_values = self._navigation_values_182()
        if current_values != getattr(self, '_navigation_baseline_182', {}):
            save = messagebox.askyesnocancel(
                'تغییرات رکورد',
                'تغییرات این رکورد ذخیره شود؟ «خیر» تغییرات فعلی را کنار می‌گذارد.',
                parent=self,
            )
            if save is None:
                return
            if save:
                try:
                    payload = self.payload_from_form()
                    if DB.get_financial_posting(self.pid):
                        DB.begin_posting_revision(
                            pending_id=self.pid, new_payload=dict(payload),
                            source='GUI_187_EDIT', actor_id='GUI',
                        )
                    else:
                        APPROVAL.save_payload(self.pid, payload, learn=True)
                    self.payload = dict(payload)
                    self.on_done()
                except Exception as exc:
                    return messagebox.showerror('ذخیره اصلاحات', str(exc), parent=self)

        target = dict(rows[target_index])
        pending_id = str(target.get('pending_id') or '')
        fresh = DB.get_pending_item(pending_id) if pending_id else None
        if fresh:
            target = dict(fresh)
        target['raw_text'] = v18._raw_text(pending_id, target)
        self._reload_record_182(target, target_index)

    def _reload_record_182(self, row, index):
        row = dict(row or {})
        payload = deepcopy(dict(row.get('payload') or {}))
        title, subtype = v18._title_type_from_payload(payload)
        if title == 'هزینه ساخت' and subtype == 'چک':
            caption = _receipt_caption(row, payload)
            if caption:
                payload['description'] = caption
                payload['receipt_caption'] = caption
            payload['cheque_amount'] = int(
                payload.get('amount') or payload.get('paid_amount') or
                payload.get('cheque_amount') or 0
            )
        row['payload'] = payload
        for child in self.winfo_children():
            child.destroy()
        self.row = row
        self.pid = str(row.get('pending_id') or '')
        if callable(self._on_record_open_182):
            self._on_record_open_182(self.pid)
        self._init_dynamic(payload)
        self._special_initialized = False
        self._navigation_index_182 = int(index)
        self._approved_editor_182 = False
        self._image = None
        self._tkimg = None
        self._zoom = .65
        self.title(f'ویرایش و تأیید رکورد — {self.pid}')
        self._build()
        self._load_evidence()
        self._navigation_baseline_182 = self._navigation_values_182()
        _retarget_fonts(self)
        self.after(120, self._fit_image)

    def approve(self):
        if self._approved_editor_182:
            return
        try:
            self.payload = self.payload_from_form()
            self.payload['v18_manual_fields'] = sorted(self.manual_fields)
            if DB.get_financial_posting(self.pid):
                DB.begin_posting_revision(
                    pending_id=self.pid, new_payload=dict(self.payload),
                    source='GUI_187_EDIT', actor_id='GUI',
                )
            result = v18.submit_v18(self.pid, self.payload, self.rich)
        except Exception as exc:
            return messagebox.showerror('تأیید انجام نشد', str(exc), parent=self)
        self._approved_editor_182 = True
        self._navigation_baseline_182 = self._navigation_values_182()
        self.msg.set(f'ثبت شد — {result}')
        self._confirm_button_182.configure(text='ثبت شد', state='disabled')
        try:
            self.on_done()
        except Exception as exc:
            self.msg.set(f'ثبت شد؛ تازه‌سازی فهرست با خطا روبه‌رو شد: {exc}')

    def _title_changed(self):
        title = self.title_var.get(); subs = list(v18.TITLE_TYPES.get(title, []))
        current = self.subtype_var.get()
        sub = current if current in subs else (subs[0] if subs else '')
        self.subtype_var.set(sub)
        try: self.widgets['v18_subtype'].configure(values=subs)
        except Exception: pass
        self._sync_cost_group_row_182()
        if sub: self._build_special(title, sub)

    def _sync_cost_group_row_182(self):
        """دسته‌بندی only means anything for هزینه ساخت."""
        row = getattr(self, 'cost_group_row', None)
        if row is None:
            return
        if self.title_var.get() == 'هزینه ساخت':
            row.grid()
        else:
            row.grid_remove()

    def _build_special(self, title, sub):
        try:
            if getattr(self, '_special_initialized', False) and self.vars and 'event_date_shamsi' in self.vars:
                self.payload = self._payload_from_vars(self.title_var.get(), self.subtype_var.get())
        except Exception:
            pass
        for w in self.special_host.winfo_children(): w.destroy()
        # cost_group/contract_id live in cost_group_row now, built once by
        # _build() - kept here too, or this rebuild (every subtype change)
        # would silently drop them from self.vars/self.widgets and break
        # both the payload capture and the _contract_field_sync() trace.
        keep = {'event_date_shamsi', 'amount', 'v18_title', 'v18_subtype', 'cost_group', 'contract_id'}
        self.vars = {k: v for k, v in self.vars.items() if k in keep}; self.widgets = {k: v for k, v in self.widgets.items() if k in keep}
        card = v18.GlassSection(self.special_host, f'{title} — {sub}'); card.pack(fill='both', expand=True)
        body = card.body; body.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform='special182')
        fields = v181.special_fields_181(title, sub); by = {f.key: f for f in fields}
        if title == 'هزینه ساخت' and sub == 'نقدی':
            rows = [['cost_group', 'payer_name', 'receiver_name', 'description'],
                    ['payment_method', 'invoice_amount', 'final_amount', 'discount_amount'],
                    ['payment_state', 'total_debt', 'remaining_debt'], ['main_phase', 'sub_phase']]
        elif title == 'هزینه ساخت' and sub == 'چک':
            rows = [['cost_group', 'payer_name', 'receiver_name', 'description', 'is_guarantee'],
                    ['issuer_name', 'issuer_bank', 'cheque_type'],
                    ['cheque_registration_state', 'due_date_shamsi', 'cheque_status'],
                    ['payment_method', 'invoice_amount', 'final_amount', 'discount_amount'],
                    ['payment_state', 'total_debt', 'remaining_debt'], ['main_phase', 'sub_phase']]
        elif title == 'ورودی' and sub == 'فروش':
            rows = [['sale_id', 'sale_unit', 'sold_area'], ['payer_name', 'buyer_name']]
        elif title == 'ورودی' and sub == 'تسهیلات':
            rows = [['loan_name', 'loan_bank', 'loan_total_amount'], ['installment_count', 'interest_rate'],
                    ['guarantor_1', 'guarantor_2', 'guarantor_3'], ['loan_start_date', 'loan_end_date']]
        elif title == 'ورودی' and sub == 'شرکا/قرض':
            rows = [['partner_name', 'partner_other_name', 'partner_kind'], ['loan_days', 'partner_return_date']]
        elif title == 'خروجی' and sub == 'اقساط':
            rows = [['payer_name', 'loan_id'], ['loan_bank', 'loan_total_amount'],
                    ['installment_count', 'paid_installments_before'], ['installments_paid_now', 'remaining_installments']]
        else:
            ks = [f.key for f in fields if f.key != 'cheque_amount']; rows = [ks[i:i+4] for i in range(0, len(ks), 4)]
        for rr, keys in enumerate(rows):
            for cc, key in enumerate(keys):
                if key in by: self._field(body, by[key], rr, 3 - cc, width=20)
        self._load_values(title, sub); self._special_initialized = True

        if 'partner_kind' in self.vars:
            self.vars['partner_kind'].trace_add('write', lambda *_: self._partner_sync_181()); self._partner_sync_181()
        if 'partner_name' in self.vars:
            self.vars['partner_name'].trace_add('write', lambda *_: self._partner_sync_181()); self._partner_sync_181()
        if 'loan_days' in self.vars: self.vars['loan_days'].trace_add('write', lambda *_: self._partner_date_sync())
        if 'loan_start_date' in self.vars: self.vars['loan_start_date'].trace_add('write', lambda *_: self._loan_date_sync())
        if 'installment_count' in self.vars: self.vars['installment_count'].trace_add('write', lambda *_: self._loan_date_sync())
        if 'installments_paid_now' in self.vars: self.vars['installments_paid_now'].trace_add('write', lambda *_: self._installment_count_sync())
        if 'sale_unit' in self.vars:
            self.vars['sale_unit'].trace_add('write', lambda *_: self._sync_sale_area_181()); self._sync_sale_area_181()
        if title == 'هزینه ساخت':
            for key in ('invoice_amount', 'final_amount'):
                if key in self.vars: self.vars[key].trace_add('write', lambda *_: self._sync_discount_182_editor())
            for key in ('payment_state', 'total_debt', 'amount'):
                if key in self.vars: self.vars[key].trace_add('write', lambda *_: self._sync_debt_182_editor())
            self._sync_discount_182_editor(); self._sync_debt_182_editor()
            bar = tk.Frame(body, bg=DARK['panel']); bar.grid(row=len(rows), column=0, columnspan=4, sticky='ew', padx=5, pady=7)
            self.phase_hint = tk.StringVar(value='')
            tk.Label(bar, textvariable=self.phase_hint, bg=DARK['panel'], fg=DARK['muted'], font=('Segoe UI', max(8, self.font_size - 1))).pack(side='right', padx=7)
            tk.Button(bar, text='پیشنهاد فاز', command=self._phase_suggest, bg=DARK['glass'], fg=DARK['text'], relief='flat', padx=10, pady=6).pack(side='left')

    def _sync_discount_182_editor(self):
        if getattr(self, '_loading', False) or not all(k in self.vars for k in ('invoice_amount', 'final_amount', 'discount_amount')): return
        invoice = parse_int(self.vars['invoice_amount'].get()); final = parse_int(self.vars['final_amount'].get())
        value = max(invoice - final, 0) if invoice > 0 else 0
        self._loading = True
        try: self.vars['discount_amount'].set(v18._group_money(value)); self.payload['discount_amount'] = value
        finally: self._loading = False

    def _sync_debt_182_editor(self):
        if getattr(self, '_loading', False) or not all(k in self.vars for k in ('payment_state', 'total_debt', 'remaining_debt')): return
        state = str(self.vars['payment_state'].get() or ''); total = max(0, parse_int(self.vars['total_debt'].get()))
        paid = max(0, parse_int(self.vars['amount'].get()) if self.vars.get('amount') else int(self.payload.get('amount') or 0))
        remaining = 0 if state == 'تسویه' else (total if state == 'پرداخت‌نشده' else max(total - paid, 0))
        self._loading = True
        try: self.vars['remaining_debt'].set(v18._group_money(remaining)); self.payload['remaining_debt'] = remaining
        finally: self._loading = False

    def _load_evidence(self):
        super()._load_evidence()
        direct = _receipt_caption(self.row, self.payload)
        self.caption.configure(state='normal'); self.caption.delete('1.0', 'end')
        self.caption.insert('1.0', direct or 'متن همراه همین رسید ثبت نشده است.')
        self.caption.configure(state='disabled')


def _editor_refresh_subphase_182(self):
    v18.DynamicFormMixin._refresh_subphase(self)
    try:
        var = self.vars.get('sub_phase'); widget = self.widgets.get('sub_phase')
        if var is not None and widget is not None and not str(var.get() or '').strip():
            vals = list(getattr(widget, '_all', []) or widget.cget('values') or [])
            if vals: var.set(vals[0])
    except Exception:
        pass

_UnifiedPendingEditor182Final._refresh_subphase = _editor_refresh_subphase_182


UnifiedPendingEditor182 = _UnifiedPendingEditor182Final


class _DataEntryCenter182Final(DataEntryCenter182):
    """Final Data Entry behavior: 70/30 layout, local history and clear AI status."""
    _UNDO_HISTORY_LIMIT = 100
    def __init__(self, parent, rich, on_posted=None):
        self._undo_stack = []
        self._redo_stack = []
        self._copied_rows = []
        self._layout_ratio = (70, 30)
        self._reprocess_dialog = None
        super().__init__(parent, rich, on_posted)

    def _build(self):
        ui = load_ui(); self.font_family = 'Segoe UI'; self.font_size = int(ui.get('font_size', 11))
        top = tk.Frame(self, bg=DARK['surface'], highlightbackground=DARK['line'], highlightthickness=1); top.pack(fill='x', pady=(0, 5)); tb = top
        self.filter = tk.StringVar(value='Pending'); self.status_buttons = {}
        for key, label in [('همه', 'همه'), ('Pending', 'در انتظار بررسی'), ('تأییدشده', 'تأییدشده'), ('ردشده', 'ردشده')]:
            b = tk.Button(tb, text=label, command=lambda k=key: self._set_status(k), bg=DARK['glass'], fg=DARK['text'],
                          activebackground=DARK['panel2'], relief='flat', font=('Segoe UI', self.font_size, 'bold'), padx=11, pady=7)
            b.pack(side='right', padx=3, pady=5); self.status_buttons[key] = (b, '')
        self.bot = tk.StringVar(value='تلگرام: بررسی...'); self.gemini = tk.StringVar(value='جمینای: بررسی...')
        self.bot_label = tk.Label(tb, textvariable=self.bot, bg=DARK['surface'], fg=DARK['muted'], font=('Segoe UI', max(9, self.font_size - 1), 'bold')); self.bot_label.pack(side='left', padx=6)
        self.gemini_label = tk.Label(tb, textvariable=self.gemini, bg=DARK['surface'], fg=DARK['muted'], font=('Segoe UI', max(9, self.font_size - 1), 'bold')); self.gemini_label.pack(side='left', padx=6)
        tk.Button(tb, text='بازخوانی پیام‌ها', command=self.re_read_messages, bg=DARK['glass'], fg=DARK['text'], relief='flat', padx=10, pady=7).pack(side='left', padx=3)
        tk.Button(tb, text='پردازش مجدد', command=lambda: self.reprocess_rows(self.table.selected_rows()), bg=DARK['glass'], fg=DARK['text'], relief='flat', padx=10, pady=7).pack(side='left', padx=3)

        pane = ttk.Panedwindow(self, orient='horizontal'); pane.pack(fill='both', expand=True); self._data_pane = pane
        preview = tk.Frame(pane, bg=DARK['panel'], highlightbackground=DARK['line'], highlightthickness=1)
        table_side = tk.Frame(pane, bg=DARK['panel'])
        # Left preview = 30%, right table = 70%.
        pane.add(preview, weight=30); pane.add(table_side, weight=70)
        def _settle_data_entry_split(event=None):
            try:
                width = pane.winfo_width()
                # This panel is initially built while its hidden notebook tab is
                # unmapped (width==1).  Only set the real 30/70 sash once the
                # tab has an actual width; keep it proportional on window resize.
                if width > 200:
                    pane.sashpos(0, int(width * 0.30))
            except Exception:
                pass
        pane.bind('<Configure>', _settle_data_entry_split, add='+')
        self.after_idle(_settle_data_entry_split)
        self.after(250, _settle_data_entry_split)

        bottom = tk.Frame(table_side, bg=DARK['bg']); bottom.pack(side='bottom', fill='x', pady=5)
        tk.Button(bottom, text='حذف', command=lambda: self.batch_delete18(self.table.selected_rows()), bg=DARK['red'], fg='#FFFFFF', relief='flat', font=('Segoe UI', self.font_size, 'bold'), padx=18, pady=9).pack(side='right', padx=3)
        tk.Button(bottom, text='کپی', command=lambda: self.copy_rows(self.table.selected_rows()), bg=DARK['yellow'], fg='#171A1F', relief='flat', font=('Segoe UI', self.font_size, 'bold'), padx=18, pady=9).pack(side='right', padx=3)
        tk.Button(bottom, text='پیست', command=lambda: self.paste_rows(self.table.selected_rows()), bg=DARK['blue'], fg='#FFFFFF', relief='flat', font=('Segoe UI', self.font_size, 'bold'), padx=18, pady=9).pack(side='right', padx=3)
        tk.Button(bottom, text='اضافه کردن', command=self.manual_transaction, bg=DARK['green'], fg='#102018', relief='flat', font=('Segoe UI', self.font_size, 'bold'), padx=18, pady=9).pack(side='right', padx=3)
        self.table = PendingTable182(table_side, self.open_wizard, self.batch_delete18, self.copy_rows, self.paste_rows,
                                     self.manual_transaction, self.batch_approve18, self.batch_reject18, self.reprocess_rows, self.export_rows)
        self.table.pack(side='top', fill='both', expand=True)

        tk.Label(preview, text='پیش‌نمایش', bg=DARK['panel'], fg=DARK['text'], font=('Segoe UI', self.font_size + 1, 'bold')).pack(anchor='e', padx=8, pady=7)
        self.preview = tk.Canvas(preview, bg=DARK['surface'], highlightthickness=0, height=260); self.preview.pack(fill='both', expand=True, padx=7)
        self.preview.bind('<MouseWheel>', self._wheel); self.preview.bind('<ButtonPress-1>', lambda e: self.preview.scan_mark(e.x, e.y)); self.preview.bind('<B1-Motion>', lambda e: self.preview.scan_dragto(e.x, e.y, gain=1))
        self.text = tk.Text(preview, height=8, wrap='word', bg=DARK['surface'], fg=DARK['text'], relief='flat', font=('Segoe UI', self.font_size + 1), padx=8, pady=8)
        self.text.pack(fill='x', padx=7, pady=7); self.text.configure(state='disabled')
        self.action = tk.StringVar(); tk.Label(preview, textvariable=self.action, bg=DARK['panel'], fg=DARK['muted'], font=('Segoe UI', max(9, self.font_size - 1)), wraplength=320, justify='right').pack(fill='x', padx=7, pady=(0, 7))
        self._update_status_buttons(); self.after(1200, self._service_status_181); self.after(4000, self._periodic); self.table.tree.bind('<<TreeviewSelect>>', self._select18, add='+')

    @staticmethod
    def _pending_snapshot(pending_id):
        row = DB.get_pending_item(str(pending_id)) or {}
        return {
            'pending_id': str(pending_id),
            'payload': deepcopy(dict(row.get('payload') or {})),
            'detected_type': row.get('detected_type'),
            'confidence': row.get('confidence'),
            'status': row.get('status'),
        }

    def _record_pending_edit(self, before):
        """Record a reversible pending-only edit, never a posted financial action."""
        if not before or not before.get('pending_id'):
            return
        after = self._pending_snapshot(before['pending_id'])
        if after.get('status') not in {'PENDING_REVIEW', 'NEEDS_REVIEW', 'EDIT_PENDING'}:
            return
        same = all(before.get(k) == after.get(k) for k in ('payload', 'detected_type', 'confidence', 'status'))
        if not same:
            self._push_history({'kind': 'edit', 'before': before, 'after': after})

    def open_editor(self, row=None):
        row = row or getattr(self, 'current', None)
        if not row:
            return
        pid = str(row.get('pending_id') or '')
        snapshots = {}
        current_pid = [pid]
        rows = list(getattr(self.table, 'all_rows', ()) or self.rows)
        if not any(str(item.get('pending_id') or '') == pid for item in rows):
            rows = [row]
        index = next(i for i, item in enumerate(rows)
                     if str(item.get('pending_id') or '') == pid)
        def opened(record_id):
            current_pid[0] = str(record_id)
            snapshots[str(record_id)] = self._pending_snapshot(str(record_id))
        def done():
            record_id = current_pid[0]
            self._record_pending_edit(snapshots.get(record_id))
            snapshots[record_id] = self._pending_snapshot(record_id)
            self.refresh()
            if callable(self.on_posted):
                self.on_posted()
        UnifiedPendingEditor182(self, row, self.rich, done,
                                navigation_rows=rows, navigation_index=index,
                                on_record_open=opened)

    def open_wizard(self, row=None):
        row = row or getattr(self, 'current', None)
        if not row:
            return messagebox.showwarning('ثبت دیتا', 'یک سطر را انتخاب کن.', parent=self)
        pid = str(row.get('pending_id') or '')
        before = self._pending_snapshot(pid)
        def done():
            # Wizard approval may post financially. Only record an edit while
            # the pending record is still in a review state.
            self._record_pending_edit(before)
            self.refresh()
            if callable(self.on_posted):
                self.on_posted()
        def full():
            fresh = DB.get_pending_item(pid) or row
            fresh = dict(fresh); fresh['raw_text'] = v18._raw_text(pid, row)
            self.open_editor(fresh)
        TransactionWizard182(self, row, self.rich, done, full)

    def manual_transaction(self):
        mid = int(datetime.now().timestamp() * 1_000_000)
        sh = gregorian_to_shamsi(datetime.now().date())
        p = {'detected_type':'EXPENSE','v18_title':'هزینه ساخت','v18_subtype':'نقدی',
             'event_date_shamsi':sh,'amount':0,'payment_state':'UNPAID','source':'MANUAL_GUI_18_2'}
        DB.register_telegram_message(chat_id=-180, message_id=mid, raw_text='', content_type='manual_gui',
                                     message_date=datetime.now().isoformat(timespec='seconds'), state='RECEIVED')
        pid = DB.create_or_replace_pending(telegram_chat_id=-180, telegram_message_id=mid,
                                           detected_type='EXPENSE', payload=p, confidence=1.0,
                                           status='PENDING_REVIEW')
        self._push_history({'kind':'add', 'pending_ids':[str(pid)]})
        self.refresh()
        row = next((x for x in self.rows if str(x.get('pending_id')) == str(pid)), None)
        if row:
            self.open_wizard(row)

    def _service_status_181(self):
        try:
            proc = getattr(self, '_bot_process', None); ready = (BASE_DIR / 'runtime' / 'telegram_bot_ready.flag').exists(); bot_ok = bool(proc and proc.poll() is None and ready)
            inbound = None
            try:
                hb = BASE_DIR / 'runtime' / 'telegram_inbound_last.json'
                if hb.exists(): inbound = json.loads(hb.read_text(encoding='utf-8'))
            except Exception: inbound = None
            if bot_ok:
                suffix = f" | آخرین پیام #{fa(inbound.get('message_id'))}" if inbound and inbound.get('message_id') else ''
                self.bot.set('تلگرام: آنلاین و آماده' + suffix); self.bot_label.configure(fg=DARK['green'])
            elif proc and proc.poll() is None:
                self.bot.set('تلگرام: در حال اتصال'); self.bot_label.configure(fg=DARK['yellow'])
            else:
                self.bot.set('تلگرام: قطع'); self.bot_label.configure(fg=DARK['red'])

            parser = getattr(getattr(APPROVAL, 'receipts', None), 'parser', None)
            names = [str(x[0]) for x in getattr(parser, 'providers', [])]; configured = any('GEMINI' in n.upper() for n in names)
            last = None
            try:
                with DB.read() as con: last = con.execute("SELECT provider,status,created_at FROM receipt_analyses ORDER BY created_at DESC LIMIT 1").fetchone()
            except Exception: pass
            failed = bool(last and 'VISION_FAILED' in str(last['provider']))
            if not configured:
                self.gemini.set('جمینای: تنظیم نشده'); self.gemini_label.configure(fg=DARK['red'])
            elif failed:
                self.gemini.set('جمینای: خطای آخرین تحلیل'); self.gemini_label.configure(fg=DARK['red'])
            elif last:
                self.gemini.set('جمینای: آماده | آخرین تحلیل انجام شد'); self.gemini_label.configure(fg=DARK['green'])
            else:
                self.gemini.set('جمینای: تنظیم شده | در انتظار اولین تحلیل'); self.gemini_label.configure(fg=DARK['yellow'])
        except Exception:
            pass
        self.after(4000, self._service_status_181)

    def _show(self, row):
        self.preview.delete('all'); self._image = None; self._tkimg = None; self.zoom = 1
        path = self._path(row)
        if path and v18.Image is not None:
            try: self._image = v18.ImageOps.exif_transpose(v18.Image.open(path)).convert('RGB'); self.after(30, self._fit)
            except Exception: pass
        if not self._image: self.preview.create_text(150, 120, text='بدون تصویر', fill=DARK['muted'], font=('Segoe UI', 10))
        p = row.get('payload') or {}; direct = _receipt_caption(row, p)
        # The preview shows only the text attached to this receipt itself. The
        # messages next to it belong to other receipts (or are unrelated chat),
        # and showing them made every receipt look like it carried the previous
        # receipt's title. AI metadata stays out of this box as well.
        lines = [direct] if direct else ['متن همراه همین رسید ثبت نشده است.']
        self.text.configure(state='normal'); self.text.delete('1.0', 'end'); self.text.insert('1.0', '\n'.join(lines)); self.text.configure(state='disabled')

    def copy_rows(self, rows):
        if not rows: return
        self._copied_rows = [deepcopy(dict(r)) for r in rows]
        lines = []
        for r in rows:
            p = r.get('payload') or {}; title, sub = v18._title_type_from_payload(p)
            lines.append(f"{r.get('message_date') or '-'}\t{title}\t{sub}\t{p.get('description') or _receipt_caption(r,p)}\t{int(p.get('amount') or 0):,}")
        try: self.clipboard_clear(); self.clipboard_append('\n'.join(lines))
        except Exception: pass
        self.action.set(f'{fa(len(rows))} ردیف کپی شد؛ سطر مقصد را انتخاب و «پیست» را بزن.')

    def _set_hidden(self, pending_ids, hidden):
        now = datetime.now().isoformat(timespec='seconds')
        with DB.tx() as con:
            for pid in pending_ids:
                con.execute("INSERT INTO rich_ui_hidden_reviews(pending_id,hidden,updated_at) VALUES(?,?,?) ON CONFLICT(pending_id) DO UPDATE SET hidden=excluded.hidden,updated_at=excluded.updated_at", (str(pid), 1 if hidden else 0, now))

    def _push_history(self, action):
        self._undo_stack.append(action)
        self._undo_stack = self._undo_stack[-self._UNDO_HISTORY_LIMIT:]
        self._redo_stack.clear()

    def paste_rows(self, target_rows=None):
        if not self._copied_rows:
            return messagebox.showinfo('پیست', 'ابتدا یک یا چند سطر را کپی کن.', parent=self)
        target_rows = target_rows or self.table.selected_rows()
        target = target_rows[-1] if target_rows else None
        target_dt = None
        if target:
            # Query the source of truth instead of trusting a possibly stale
            # table-row copy. This makes paste positioning deterministic after
            # refreshes and external status updates.
            try:
                fresh_target = DB.get_pending_item(str(target.get('pending_id') or '')) or target
                target_dt = datetime.fromisoformat(str(fresh_target.get('created_at') or ''))
            except Exception:
                target_dt = None
        new_ids = []
        base_mid = int(datetime.now().timestamp() * 1_000_000)
        for i, src in enumerate(self._copied_rows):
            p = deepcopy(dict(src.get('payload') or {})); p['source'] = 'COPY_GUI_18_2'; p['copied_from_pending_id'] = str(src.get('pending_id') or '')
            raw = _receipt_caption(src, p)
            mid = base_mid + i
            DB.register_telegram_message(chat_id=-182, message_id=mid, raw_text=raw, content_type='copy_gui', message_date=datetime.now().isoformat(timespec='seconds'), state='RECEIVED')
            pid = DB.create_or_replace_pending(telegram_chat_id=-182, telegram_message_id=mid,
                                               detected_type=str(src.get('detected_type') or p.get('detected_type') or 'UNKNOWN'),
                                               payload=p, confidence=float(src.get('confidence') or 1.0), status='PENDING_REVIEW')
            if target_dt:
                stamp = (target_dt + timedelta(microseconds=i + 1)).isoformat(timespec='microseconds')
                with DB.tx() as con: con.execute('UPDATE pending_items SET created_at=?,updated_at=? WHERE pending_id=?', (stamp, stamp, pid))
            new_ids.append(str(pid))
        self._set_hidden(new_ids, False); self._push_history({'kind': 'paste', 'pending_ids': new_ids})
        self.filter.set('Pending'); self.refresh(); self._select_pending_ids(new_ids)
        self.action.set(f'{fa(len(new_ids))} سطر زیر سطر انتخاب‌شده درج شد.' if target else f'{fa(len(new_ids))} سطر به انتهای جدول اضافه شد.')

    def _select_pending_ids(self, ids):
        wanted = set(map(str, ids)); found = []
        mapping = getattr(self.table, 'iid_to_row', {})
        for iid, row in mapping.items():
            if str(row.get('pending_id')) in wanted: found.append(iid)
        if found:
            self.table.tree.selection_set(found); self.table.tree.see(found[-1]); self.table._sync_checks()

    def batch_delete18(self, rows):
        if not rows: return
        if not messagebox.askyesno('حذف', f'{fa(len(rows))} ردیف انتخاب‌شده حذف/مخفی شوند؟\nاین عملیات با Undo قابل بازگشت است.', parent=self): return
        states = []
        hidden_now = self.rich.hidden_review_ids()
        ids = []
        for r in rows:
            pid = str(r.get('pending_id') or '')
            if not pid: continue
            states.append({'pending_id': pid, 'status': str(r.get('status') or 'PENDING_REVIEW'), 'hidden': pid in hidden_now})
            if r.get('status') not in {'APPROVED', 'REJECTED'}:
                try: APPROVAL.reject(pid, actor_id='GUI_18_2_DELETE')
                except Exception: pass
            ids.append(pid)
        if ids: self.rich.hide_review(ids); self._push_history({'kind': 'delete', 'states': states})
        self.refresh(); self.action.set(f'{fa(len(ids))} سطر حذف/مخفی شد؛ Undo برای بازگردانی آماده است.')

    def undo_data_entry(self):
        if not self._undo_stack: return 'عملیات قابل بازگشتی در ثبت دیتا وجود ندارد.'
        a = self._undo_stack.pop(); kind = a.get('kind')
        if kind == 'delete':
            for st in a['states']:
                try: DB.update_pending(st['pending_id'], status=st['status'])
                except Exception: pass
            self._set_hidden([st['pending_id'] for st in a['states']], False)
            msg = 'حذف سطرها بازگردانی شد.'
        elif kind == 'paste':
            self._set_hidden(a['pending_ids'], True); msg = 'پیست سطرها بازگردانی شد.'
        elif kind == 'add':
            blocked = [pid for pid in a['pending_ids'] if str((DB.get_pending_item(pid) or {}).get('status')) == 'APPROVED']
            if blocked:
                self._undo_stack.append(a)
                return 'رکورد اضافه‌شده قبلاً ثبت مالی شده و از ثبت دیتا قابل Undo نیست.'
            self._set_hidden(a['pending_ids'], True); msg = 'اضافه‌کردن رکورد بازگردانی شد.'
        elif kind == 'edit':
            b = a['before']; DB.update_pending(b['pending_id'], payload=b['payload'], detected_type=b.get('detected_type'),
                                              confidence=b.get('confidence'), status=b.get('status'))
            msg = 'ویرایش رکورد بازگردانی شد.'
        else: msg = 'Undo انجام شد.'
        self._redo_stack.append(a); self.refresh(); self.action.set(msg); return msg

    def redo_data_entry(self):
        if not self._redo_stack: return 'عملیات قابل Redo در ثبت دیتا وجود ندارد.'
        a = self._redo_stack.pop(); kind = a.get('kind')
        if kind == 'delete':
            for st in a['states']:
                if st['status'] not in {'APPROVED', 'REJECTED'}:
                    try: APPROVAL.reject(st['pending_id'], actor_id='GUI_18_2_REDO')
                    except Exception: pass
            self._set_hidden([st['pending_id'] for st in a['states']], True); msg = 'حذف سطرها دوباره اعمال شد.'
        elif kind == 'paste':
            self._set_hidden(a['pending_ids'], False); msg = 'پیست سطرها دوباره اعمال شد.'
        elif kind == 'add':
            self._set_hidden(a['pending_ids'], False); msg = 'اضافه‌کردن رکورد دوباره اعمال شد.'
        elif kind == 'edit':
            aft = a['after']; DB.update_pending(aft['pending_id'], payload=aft['payload'], detected_type=aft.get('detected_type'),
                                                confidence=aft.get('confidence'), status=aft.get('status'))
            msg = 'ویرایش رکورد دوباره اعمال شد.'
        else: msg = 'Redo انجام شد.'
        self._undo_stack.append(a); self.refresh(); self.action.set(msg); return msg

    def can_undo(self): return bool(self._undo_stack)
    def can_redo(self): return bool(self._redo_stack)

    def reprocess_rows(self, rows):
        rows = rows or ([self.current] if getattr(self, 'current', None) else [])
        rows = [r for r in rows if r and r.get('status') in {'PENDING_REVIEW', 'NEEDS_REVIEW', 'EDIT_PENDING'}]
        if not rows: return messagebox.showinfo('پردازش مجدد', 'رکورد قابل پردازش انتخاب نشده است.', parent=self)
        dlg = tk.Toplevel(self); self._reprocess_dialog = dlg; dlg.title('پردازش مجدد فیش'); dlg.configure(bg=DARK['surface']); dlg.transient(self); dlg.resizable(False, False)
        status = tk.StringVar(value=f'در حال پردازش {fa(len(rows))} فیش...')
        tk.Label(dlg, textvariable=status, bg=DARK['surface'], fg=DARK['text'], font=('Segoe UI', self.font_size + 1, 'bold'), padx=28, pady=18).pack(fill='x')
        pb = ttk.Progressbar(dlg, mode='indeterminate', length=380); pb.pack(fill='x', padx=24, pady=(0, 18)); pb.start(10)
        dlg.update_idletasks(); dlg.geometry(f'440x130+{self.winfo_rootx()+max(20,(self.winfo_width()-440)//2)}+{self.winfo_rooty()+100}')
        self.action.set(status.get())

        async def analyze_one(r):
            pid = str(r['pending_id']); old = dict(r.get('payload') or {}); manual = set(old.get('v18_manual_fields') or [])
            await APPROVAL.analyze_pending_with_ai(pid)
            fresh = DB.get_pending_item(pid) or {}; new = dict(fresh.get('payload') or {}); suggest = {}
            for k in manual:
                if k in old and new.get(k) != old.get(k): suggest[k] = new.get(k); new[k] = old.get(k)
            new['v18_manual_fields'] = sorted(manual)
            if suggest: new['v18_reprocess_suggestions'] = suggest
            APPROVAL.save_payload(pid, new, learn=False)
            return pid

        results = queue.Queue(maxsize=1)
        def worker():
            ok = 0; errs = []
            async def batch():
                nonlocal ok
                # A small concurrency cap reduces multi-receipt waiting time while
                # avoiding aggressive provider/SQLite contention.
                sem = asyncio.Semaphore(2)
                async def run(r):
                    nonlocal ok
                    try:
                        async with sem: await analyze_one(r)
                        ok += 1
                    except Exception as exc: errs.append(f"{r.get('pending_id')}: {exc}")
                await asyncio.gather(*(run(r) for r in rows))
            try: asyncio.run(batch())
            except Exception as exc: errs.append(str(exc))
            # Tk must never be touched from the worker thread.
            try: results.put_nowait((ok, errs))
            except Exception: pass

        def poll_result():
            try:
                ok, errs = results.get_nowait()
            except queue.Empty:
                try:
                    if dlg.winfo_exists(): self.after(40, poll_result)
                except Exception:
                    pass
                return
            self._finish_reprocess_182(ok, errs, status, pb, dlg)

        threading.Thread(target=worker, daemon=True).start()
        self.after(40, poll_result)

    def _finish_reprocess_182(self, ok, errs, status, pb, dlg):
        try: pb.stop()
        except Exception: pass
        # self.refresh() used to run unguarded here: an exception in it (a
        # real possibility - it repaints the whole dashboard from the DB)
        # skipped every branch below, including dlg.destroy(), and left this
        # processing window open forever. It is caught and reported on its
        # own below instead, so the reprocess result and dlg.destroy() are
        # unaffected either way.
        refresh_error = None
        try:
            self.refresh()
        except Exception as exc:
            refresh_error = exc
        if errs and not ok:
            text = 'پردازش انجام نشد.'; detail = '\n'.join(errs[:6])
            status.set(text); self.action.set(text)
            try: dlg.destroy()
            except Exception: pass
            messagebox.showerror('پردازش مجدد', text + '\n\n' + detail, parent=self)
        elif errs:
            text = f'{fa(ok)} فیش به‌روزرسانی شد؛ {fa(len(errs))} خطا.'; status.set(text); self.action.set(text)
            try: dlg.destroy()
            except Exception: pass
            messagebox.showwarning('پردازش مجدد', text + '\n\n' + '\n'.join(errs[:6]), parent=self)
        else:
            text = f'پردازش با موفقیت انجام شد — {fa(ok)} فیش به‌روزرسانی شد.'; status.set(text); self.action.set(text)
            try: dlg.destroy()
            except Exception: pass
            messagebox.showinfo('پردازش مجدد', text, parent=self)
        if refresh_error is not None:
            # A separate, distinctly-titled report - not folded into errs
            # above, which is the reprocess outcome, a different thing.
            messagebox.showerror(
                'به‌روزرسانی نمایش',
                f'نتیجهٔ پردازش ثبت شد، اما نمایش داشبورد به‌روز نشد:\n{refresh_error}',
                parent=self,
            )


DataEntryCenter182 = _DataEntryCenter182Final

class _Stage182DashboardFinal(Stage182Dashboard):
    """Final 18.2 shell using the user-supplied dark/light reference screens."""
    _VISIBLE_NAV = ['داشبورد', 'ثبت دیتا', 'تراکنش‌ها', 'فروش و مطالبات', 'گزارش‌گیری', 'حساب مدیر']

    def __init__(self):
        super().__init__()
        self.title('BARKAV — Engineering & Construction — Version 18.2')
        try: self.iconbitmap(default=str(BASE_DIR / 'assets' / 'BARKAV.ico'))
        except Exception: pass
        self.after_idle(lambda: _retarget_fonts(self, 'Segoe UI'))
        history_scope.install(self)

    def refresh_all(self, *args, **kwargs):
        # Refreshing re-derives statuses and rewrites bookkeeping columns; none
        # of that is a user action, so it is kept out of every tab's history.
        with row_journal.suspended():
            return super().refresh_all(*args, **kwargs)

    def _style(self):
        palette = dict(_THEME_LIGHT if _is_light() else _THEME_DARK)
        DARK.update(palette)
        light = _is_light()
        try:
            v18.v175.v16.d12.COLORS.update({
                'bg': DARK['bg'], 'panel': DARK['panel'], 'soft': DARK['surface'],
                'rowblue': '#F4F7FA' if light else '#10243A', 'text': DARK['text'],
                'muted': DARK['muted'], 'line': DARK['line'], 'navy': DARK['blue'],
                'blue': DARK['blue'], 'cyan': DARK['cyan'], 'green': DARK['green'],
                'yellow': DARK['yellow'], 'orange': DARK['orange'], 'red': DARK['red'],
            })
        except Exception:
            pass
        st = ttk.Style(self)
        try: st.theme_use('clam')
        except Exception: pass
        fs = int(load_ui().get('font_size') or 11); ff = 'Segoe UI'; rh = int(load_ui().get('row_height') or 40)
        entry_bg = '#FFFFFF' if light else '#102238'
        tree_bg = '#FFFFFF' if light else '#10243A'
        tree_alt = '#F7F9FB' if light else '#132A43'
        head_bg = '#F1F5F8' if light else '#1B3653'
        tab_bg = '#FFFFFF' if light else '#11243A'
        tab_active = '#EAF8FB' if light else '#214B6E'
        select_bg = '#DCEFF8' if light else '#315D86'
        select_fg = '#16324C' if light else '#FFFFFF'
        st.configure('.', font=(ff, fs), background=DARK['bg'], foreground=DARK['text'])
        st.configure('TFrame', background=DARK['bg']); st.configure('Panel.TFrame', background=DARK['panel'])
        st.configure('TLabel', background=DARK['bg'], foreground=DARK['text'])
        st.configure('TButton', padding=(11, 7), background=DARK['glass'], foreground=DARK['text'], bordercolor=DARK['line'], relief='flat', font=(ff, fs))
        st.map('TButton', background=[('active', DARK['panel2']), ('pressed', select_bg)], foreground=[('disabled', DARK['muted'])])
        st.configure('Primary.TButton', background=DARK['blue'], foreground='#FFFFFF', font=(ff, fs, 'bold'))
        st.configure('Toolbar.TButton', padding=(7, 5), font=(ff, max(9, fs-1)), background=DARK['glass'])
        st.configure('Compact.TButton', padding=(6, 4), font=(ff, max(8, fs-2)), background=DARK['glass'])
        st.configure('Danger.TButton', background=DARK['red'], foreground='#FFFFFF')
        st.configure('TEntry', fieldbackground=entry_bg, foreground=DARK['text'], insertcolor=DARK['text'], bordercolor=DARK['line'], padding=6)
        st.configure('Compact.TEntry', fieldbackground=entry_bg, foreground=DARK['text'])
        st.configure('TCombobox', fieldbackground=entry_bg, background=entry_bg, foreground=DARK['text'], arrowcolor=DARK['text'], bordercolor=DARK['line'], padding=5)
        st.map('TCombobox', fieldbackground=[('readonly', entry_bg)], foreground=[('readonly', DARK['text'])], selectbackground=[('readonly', entry_bg)], selectforeground=[('readonly', DARK['text'])])
        st.configure('TScrollbar', background=DARK['glass'], troughcolor=DARK['surface'], bordercolor=DARK['line'], arrowcolor=DARK['muted'], relief='flat')
        st.configure('TPanedwindow', background=DARK['bg']); st.configure('TCheckbutton', background=DARK['panel'], foreground=DARK['text'])
        st.configure('TLabelframe', background=DARK['panel'], bordercolor=DARK['line'], relief='solid', borderwidth=1)
        st.configure('TLabelframe.Label', background=DARK['panel'], foreground=DARK['blue'], font=(ff, fs, 'bold'))
        st.configure('Dashboard.TLabelframe', background=DARK['panel'], bordercolor=DARK['line'])
        st.configure('Dashboard.TLabelframe.Label', background=DARK['panel'], foreground=DARK['blue'], font=(ff, fs+1, 'bold'))
        st.configure('Report.TLabelframe', background=DARK['panel'], bordercolor=DARK['line'])
        st.configure('Report.TLabelframe.Label', background=DARK['panel'], foreground=DARK['blue'], font=(ff, fs, 'bold'))
        st.configure('Treeview', rowheight=rh, background=tree_bg, fieldbackground=tree_bg, foreground=DARK['text'], bordercolor=DARK['line'], font=(ff, fs))
        st.configure('Treeview.Heading', background=head_bg, foreground=DARK['text'], font=(ff, max(9, fs-1), 'bold'), padding=(6, 9), relief='flat')
        st.map('Treeview', background=[('selected', select_bg)], foreground=[('selected', select_fg)])
        # Strong active/inactive contrast for Transactions and Reporting subtabs.
        st.configure('TNotebook', background=DARK['bg'], borderwidth=0, tabmargins=(0, 3, 0, 0))
        st.configure('TNotebook.Tab', background=tab_bg, foreground=DARK['muted'], padding=(18, 9), font=(ff, max(9, fs-1), 'bold'), borderwidth=1)
        st.map('TNotebook.Tab', background=[('selected', tab_active), ('active', DARK['panel2'])], foreground=[('selected', DARK['text']), ('active', DARK['text'])], expand=[('selected', (1, 1, 1, 0))])
        st.configure('Hidden.TNotebook', background=DARK['bg'], borderwidth=0, tabmargins=0)
        try: st.layout('Hidden.TNotebook.Tab', [])
        except Exception: pass
        self._theme_tree_alt = tree_alt

    def _load_nav_icon(self, name):
        # Bind PhotoImage explicitly to this Tk interpreter. This also makes
        # repeated GUI smoke construction reliable and avoids stale pyimage IDs.
        if not hasattr(self, '_nav_images'):
            self._nav_images = {}
        if name in self._nav_images:
            return self._nav_images[name]
        p = BASE_DIR / 'assets' / f'nav_{name}.png'
        try:
            im = v181.Image.open(p).convert('RGBA').resize((28, 28), v181.Image.Resampling.LANCZOS)
            img = v181.ImageTk.PhotoImage(im, master=self)
            self._nav_images[name] = img
            return img
        except Exception:
            return None

    def _build(self):
        self.configure(bg=DARK['bg']); fs = int(load_ui().get('font_size') or 11); ff = 'Segoe UI'; light = _is_light()
        top_bg = '#FBFCFD' if light else '#07192B'; top_line = '#DCE3E9' if light else '#29445F'
        button_bg = '#FFFFFF' if light else '#10243A'; button_active = '#EAF4F8' if light else '#1D3B58'
        button_fg = '#284A6A' if light else '#F2F5F8'
        top = tk.Frame(self, bg=top_bg, height=70, highlightbackground=top_line, highlightthickness=1); top.pack(fill='x'); top.pack_propagate(False)
        self.datetime_top = tk.StringVar(value='')
        tk.Label(top, textvariable=self.datetime_top, bg=top_bg, fg=button_fg, font=(ff, fs+1, 'bold')).pack(side='left', padx=(20, 10))
        tk.Label(top, text='BARKAV — Engineering & Construction — Version 18.2', bg=top_bg, fg=button_fg, font=(ff, fs, 'bold')).pack(side='left', padx=18)
        # No BARKAV image/logo in this area — user explicitly requested removal.
        tools = tk.Frame(top, bg=top_bg); tools.pack(side='right', padx=10, pady=10)
        commands = [
            ('ذخیره', self.manual_save, 'بکاپ دستی'),
            ('Undo', self.undo, 'بازگشت آخرین عملیات'),
            ('Redo', self.redo, 'اجرای دوباره'),
            ('بروزرسانی', self.refresh_all, 'بروزرسانی همه اطلاعات'),
            ('تنظیمات', lambda: self._select_tab_text('تنظیمات'), 'تنظیمات'),
            ('بسته توسعه', self.export_development_package, 'خروجی امن توسعه'),
            ('سیستم', lambda: self._select_tab_text('سیستم'), 'وضعیت سیستم'),
        ]
        self.command_buttons = []
        for text, cmd, tip in commands:
            b = tk.Button(tools, text=text, command=cmd, bg=button_bg, fg=button_fg, activebackground=button_active,
                          activeforeground=button_fg, relief='flat', bd=0, highlightbackground=top_line, highlightthickness=1,
                          font=(ff, max(9, fs-1), 'bold'), padx=12, pady=8, cursor='hand2')
            b.pack(side='right', padx=4); v18.add_tooltip(b, tip); self.command_buttons.append(b)
        self.project_name_top = tk.StringVar(value='پروژه')

        nav_bg = '#FFFFFF' if light else '#0A1C2F'
        self.navbar = tk.Frame(self, bg=nav_bg, height=66, highlightbackground=DARK['line'], highlightthickness=1)
        self.navbar.pack(fill='x', padx=10, pady=(8, 0)); self.navbar.pack_propagate(False)
        self.notebook = ttk.Notebook(self, style='Hidden.TNotebook'); self.notebook.pack(fill='both', expand=True, padx=10, pady=(7, 9))
        self._build_overview(); self._build_manager(); self._build_financial(); self._build_cheques(); self._build_sales(); self._build_reconciliation(); self._build_reports(); self._build_market(); self._build_system(); self._build_settings()
        self._rebuild_navbar()
        self.notebook.bind('<<NotebookTabChanged>>', lambda e: (self._sync_nav(), v18._maximize(self)), add='+')
        self._attach_common_tooltips(self); self._tick_clock(); self.after_idle(lambda: _retarget_fonts(self, 'Segoe UI'))

    def _build_overview(self):
        super()._build_overview()
        # Stage 18.1 had a hard-coded dark phase strip. Repaint it so the
        # supplied light reference stays genuinely light while preserving the
        # same compact 32-phase geometry in both appearances.
        light = _is_light()
        try:
            self.phase_strip.configure(bg=DARK['panel'])
            for b in self.phase_buttons.values():
                b.configure(
                    bg='#F7F9FB' if light else '#10243A',
                    fg='#4A6178' if light else '#C8D7E5',
                    activebackground='#E5F5F8' if light else '#214B6E',
                    activeforeground='#147F91' if light else '#FFFFFF',
                    highlightbackground=DARK['line'],
                    highlightthickness=1,
                )
            # The inherited progress canvas hard-coded a dark track.  Replace
            # only its paint routine so Light and Dark both match the supplied
            # reference, while preserving all existing progress semantics.
            bar = self.overall_progress
            bar.configure(bg=DARK['surface'], highlightbackground=DARK['line'])
            def _theme_progress_redraw():
                bar.delete('all')
                w=max(bar.winfo_width(),100); h=max(bar.winfo_height(),40); m=6
                track='#EEF3F6' if light else '#0A1421'
                outline='#D7E0E7' if light else DARK['line']
                bar.create_rectangle(m,m,w-m,h-m,fill=track,outline=outline,width=1)
                fill=(w-2*m)*bar.percent/100
                if fill>0:
                    bar.create_rectangle(m,m,m+fill,h-m,fill=DARK['blue'],outline='')
                text_fill='#27445E' if light else '#FFFFFF'
                bar.create_text(w/2,h/2,text=f"پیشرفت کلی پروژه  {fa(f'{bar.percent:.1f}')}٪",fill=text_fill,font=('Segoe UI',10,'bold'))
            bar.redraw = _theme_progress_redraw
            bar.redraw()
        except Exception:
            pass

    def refresh_phase_strip(self):
        # Preserve the phase/status semantics, but use the reference-theme
        # colors instead of the legacy hard-coded dark palette.
        super().refresh_phase_strip()
        light = _is_light()
        try:
            progress = self.rich.get_phase_progress()
            colors = ({
                'NOT_STARTED': ('#FFFFFF', '#536579'),
                'ACTIVE': ('#28A875', '#FFFFFF'),
                'PAUSED': ('#D8A33D', '#FFFFFF'),
                'COMPLETED': ('#239A70', '#FFFFFF'),
            } if light else {
                'NOT_STARTED': ('#10243A', '#C8D7E5'),
                'ACTIVE': ('#177A59', '#FFFFFF'),
                'PAUSED': ('#76571C', '#FFFFFF'),
                'COMPLETED': ('#16805D', '#FFFFFF'),
            })
            for n, b in self.phase_buttons.items():
                st = str((progress.get(n) or {}).get('status') or 'NOT_STARTED')
                bg, fg = colors.get(st, colors['NOT_STARTED'])
                b.configure(bg=bg, fg=fg, activebackground=('#DDF4ED' if light else '#214B6E'),
                            activeforeground=('#176B59' if light else '#FFFFFF'),
                            highlightbackground=DARK['line'], highlightthickness=1)
        except Exception:
            pass

    def _build_manager(self):
        before = set(self.notebook.tabs()); super()._build_manager(); new = [x for x in self.notebook.tabs() if x not in before]
        tid = new[-1] if new else self.notebook.tabs()[-1]; self.manager_tab_id = tid; self.notebook.tab(tid, text='حساب مدیر')
        tab = self.nametowidget(tid)
        bar = tk.Frame(tab, bg=DARK['surface'], highlightbackground=DARK['line'], highlightthickness=1)
        first = tab.winfo_children()[0] if tab.winfo_children() else None
        try: bar.pack(fill='x', padx=6, pady=(5, 1), before=first)
        except Exception: bar.pack(fill='x', padx=6, pady=(5, 1))
        tk.Label(bar, text='دسترسی‌های مدیریتی', bg=DARK['surface'], fg=DARK['muted'], font=('Segoe UI', 10, 'bold')).pack(side='right', padx=10, pady=8)
        tk.Button(bar, text='تطبیق بانک', command=lambda: self._select_tab_text('تطبیق بانکی'), bg=DARK['glass'], fg=DARK['text'], relief='flat', padx=14, pady=7, font=('Segoe UI', 10, 'bold')).pack(side='right', padx=4, pady=5)
        self.manager_bank_button = bar.winfo_children()[-1]

    def _rebuild_navbar(self):
        if not getattr(self, 'navbar', None): return
        for w in self.navbar.winfo_children(): w.destroy()
        self.nav_buttons = {}; fs = int(load_ui().get('font_size') or 11); light = _is_light()
        by_text = {self.notebook.tab(t, 'text'): t for t in self.notebook.tabs()}
        # Backward compatibility if an inherited builder still used the old manager label.
        if 'حساب مدیر' not in by_text and 'حساب مدیر پروژه' in by_text:
            tid = by_text['حساب مدیر پروژه']; self.notebook.tab(tid, text='حساب مدیر'); by_text['حساب مدیر'] = tid
        icon_map = {'داشبورد':'dashboard','ثبت دیتا':'data','تراکنش‌ها':'transactions','فروش و مطالبات':'sales','گزارش‌گیری':'reports','حساب مدیر':'manager'}
        inactive_bg = '#FFFFFF' if light else '#0E2237'; active_bg = '#F0FBFD' if light else '#153653'
        inactive_fg = '#294A69' if light else '#E7EDF3'; active_fg = '#129EAE' if light else '#FFFFFF'
        for label in self._VISIBLE_NAV:
            tid = by_text.get(label)
            if not tid: continue
            img = self._load_nav_icon(icon_map[label])
            b = tk.Button(self.navbar, text=label, image=img, compound='right' if img else 'none', command=lambda t=tid: self.notebook.select(t),
                          bg=inactive_bg, fg=inactive_fg, activebackground=active_bg, activeforeground=active_fg, relief='flat', bd=0,
                          font=('Segoe UI', fs, 'bold'), padx=16, pady=8, cursor='hand2', highlightbackground=DARK['line'], highlightthickness=1)
            b.pack(side='right', fill='y', padx=2, pady=5); self.nav_buttons[tid] = b
        self._sync_nav()

    def _sync_nav(self):
        try: sel = str(self.notebook.select())
        except Exception: return
        light = _is_light(); active_bg = '#F0FBFD' if light else '#153653'; inactive_bg = '#FFFFFF' if light else '#0E2237'
        for tid, b in self.nav_buttons.items():
            active = str(tid) == sel
            b.configure(bg=active_bg if active else inactive_bg,
                        fg=('#129EAE' if light else '#FFFFFF') if active else ('#294A69' if light else '#E7EDF3'),
                        relief='raised' if active else 'flat', bd=1 if active else 0)

    def _build_reports(self):
        super()._build_reports()
        # Keep output controls available regardless of which valid report tab is active.
        report_root = self.report_main.master
        export_bar = tk.Frame(report_root, bg=DARK['surface'], highlightbackground=DARK['line'], highlightthickness=1)
        try: export_bar.pack(fill='x', padx=5, pady=(0,5), before=self.report_main)
        except Exception: export_bar.pack(fill='x', padx=5, pady=(0,5))
        tk.Label(export_bar, text='خروجی گزارش فعال', bg=DARK['surface'], fg=DARK['muted'], font=('Segoe UI',10,'bold')).pack(side='right', padx=8, pady=6)
        ttk.Combobox(export_bar, textvariable=self.report_export_mode, state='readonly', values=['Print','PDF','Excel'], width=10).pack(side='right', padx=4, pady=5)
        tk.Button(export_bar, text='خروجی', command=self.export_report_choose, bg=DARK['glass'], fg=DARK['text'], relief='flat', padx=14, pady=7).pack(side='right', padx=4, pady=5)
        self.report_export_bar = export_bar
        # Add the valid summary/trend report target requested by the user.
        summary = ttk.Frame(self.report_nb, style='Panel.TFrame'); self.report_nb.add(summary, text='خلاصه روندهای گزارش'); self.report_summary_tab = summary
        head = tk.Frame(summary, bg=DARK['surface'], highlightbackground=DARK['line'], highlightthickness=1); head.pack(fill='x', padx=5, pady=5)
        tk.Label(head, text='خلاصه روندهای برآورد، واقعی و پیش‌بینی', bg=DARK['surface'], fg=DARK['text'], font=('Segoe UI', 12, 'bold')).pack(side='right', padx=10, pady=8)
        self.report_summary_tree = ttk.Treeview(summary, columns=('metric','value','details'), show='headings', height=13)
        self.report_summary_tree.heading('metric', text='شاخص'); self.report_summary_tree.heading('value', text='مقدار'); self.report_summary_tree.heading('details', text='جزئیات')
        self.report_summary_tree.column('metric', width=250, anchor='e'); self.report_summary_tree.column('value', width=180, anchor='center'); self.report_summary_tree.column('details', width=520, anchor='e')
        self.report_summary_tree.pack(fill='both', expand=True, padx=5, pady=(0,5))
        # Explicit RTL/right-alignment for the financial indicators tab.
        try:
            idx_tid = self.report_main.tabs()[1]; self.report_indices_root = self.nametowidget(idx_tid)
            self.index_table.column('metric', anchor='e')
            self.index_table.configure(displaycolumns=('s3','s2','s1','metric'))
        except Exception: pass

    def _report_export_rows(self):
        """Return active report headers/rows/title. No checkbox chooser ambiguity."""
        main_text = self.report_main.tab(self.report_main.select(), 'text') if self.report_main.select() else ''
        if main_text == 'شاخص‌های مالی':
            headers = ['شاخص', 'برآورد اولیه', 'انجام‌شده + بروز تا پایان', 'بروز صفر تا ۱۰۰']
            rows = [list(self.index_table.item(i, 'values')) for i in self.index_table.get_children()]
            return headers, rows, 'شاخص‌های مالی'
        sub_text = self.report_nb.tab(self.report_nb.select(), 'text') if self.report_nb.select() else ''
        if sub_text == 'قیمت':
            headers = ['گروه','کد','شرح','واحد','برآورد','واقعی مرجع','پیش‌بینی','منبع']; rows = []
            catfa = {'MATERIAL':'مصالح','LABOR':'اجرت/اجرا','SERVICE':'خدمات','INSTALLATION_GROUP':'تأسیسات (تجمیعی)'}
            for r in self.rich.list_prices(visible_only=True):
                rows.append([catfa.get(r.get('category'), r.get('category') or '-'), r.get('code') or '-', r.get('description') or '-', r.get('unit') or '-', fa(f"{int(r.get('estimate_rate') or 0):,}"), fa(f"{int(r.get('actual_rate') or 0):,}"), fa(f"{int(r.get('forecast_rate') or 0):,}"), r.get('source') or '-'])
            return headers, rows, 'گزارش قیمت‌ها'
        if sub_text == 'فازها':
            headers = ['شماره فاز','فاز','برآورد','واقعی','مانده پایه','پیش‌بینی','ID','انحراف']; rows = []
            for r in self._phase_summary_live():
                rows.append([fa(f"{int(r['phase_no']):02d}"), r['phase'], fa(f"{int(r['estimate']):,}"), fa(f"{int(r['actual']):,}"), fa(f"{int(r['remaining_base']):,}"), fa(f"{int(r['forecast']):,}"), r['phase_id'], fa(f"{int(r['variance']):,}")])
            return headers, rows, 'گزارش فازها'
        if sub_text == 'خلاصه روندهای گزارش':
            headers = ['شاخص','مقدار','جزئیات']; rows = [list(self.report_summary_tree.item(i,'values')) for i in self.report_summary_tree.get_children()]
            return headers, rows, 'خلاصه روندهای گزارش'
        return [], [], ''

    def export_report_choose(self):
        headers, rows, title = self._report_export_rows()
        if not title:
            return messagebox.showwarning('خروجی', 'تب گزارش فعال قابل شناسایی نیست.', parent=self)
        if not rows:
            return messagebox.showinfo('خروجی', f'تب «{title}» شناسایی شد، اما هنوز داده‌ای برای خروجی ندارد.', parent=self)
        mode = str(getattr(self, 'report_export_mode', tk.StringVar(value='PDF')).get() or 'PDF')
        try:
            if mode == 'Print':
                fd, path = tempfile.mkstemp(suffix='.pdf'); os.close(fd); v163.export_pdf(path, headers, rows, title=f'BARKAV — {title}'); v163.print_file(path); return
            is_xlsx = mode == 'Excel'; ext = '.xlsx' if is_xlsx else '.pdf'
            types = [('Excel','*.xlsx')] if is_xlsx else [('PDF','*.pdf')]
            path = filedialog.asksaveasfilename(parent=self, defaultextension=ext, filetypes=types, initialfile=f'BARKAV_{title}{ext}')
            if not path: return
            if is_xlsx: v163.export_xlsx(path, headers, rows, title=f'BARKAV — {title}')
            else: v163.export_pdf(path, headers, rows, title=f'BARKAV — {title}')
            messagebox.showinfo('خروجی', f'فایل ساخته شد:\n{path}', parent=self)
        except Exception as exc:
            messagebox.showerror('خروجی', str(exc), parent=self)

    def refresh_reports(self):
        super().refresh_reports()
        if not hasattr(self, 'report_summary_tree'): return
        phases = self._phase_summary_live(); est = sum(int(r.get('estimate') or 0) for r in phases); actual = sum(int(r.get('actual') or 0) for r in phases); forecast = sum(int(r.get('forecast') or 0) for r in phases)
        done = sum(1 for r in phases if int(r.get('actual') or 0) > 0); variance = forecast - est
        rows = [
            ('برآورد کل فازها', fa(f'{est:,}'), 'جمع برآورد اولیه فازهای پروژه'),
            ('واقعی ثبت‌شده', fa(f'{actual:,}'), 'جمع هزینه واقعی متصل به فازها'),
            ('پیش‌بینی نهایی', fa(f'{forecast:,}'), 'جمع پیش‌بینی به‌روز فازها'),
            ('انحراف پیش‌بینی', fa(f'{variance:,}'), 'پیش‌بینی منهای برآورد اولیه'),
            ('فازهای دارای عملکرد واقعی', fa(done), f'از {fa(len(phases))} فاز'),
        ]
        for i in self.report_summary_tree.get_children(): self.report_summary_tree.delete(i)
        for r in rows: self.report_summary_tree.insert('', 'end', values=r)

    def undo(self):
        # Each tab has its own history (history_scope); the Data Entry tab keeps
        # the one it always had. Never another tab's, and never a global stack.
        messagebox.showinfo('Undo', history_scope.install(self).undo(), parent=self)

    def redo(self):
        messagebox.showinfo('Redo', history_scope.install(self).redo(), parent=self)


Stage182Dashboard = _Stage182DashboardFinal
Stage18Dashboard = Stage182Dashboard
Stage181Dashboard = Stage182Dashboard
Stage175Dashboard = Stage182Dashboard
Stage17Dashboard = Stage182Dashboard


if __name__ == '__main__':
    Stage182Dashboard().mainloop()
