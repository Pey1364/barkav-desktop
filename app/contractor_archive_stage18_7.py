"""Contractor آرشیو profiles: the rating wizard, record and detail windows.

آرشیو rates a طرف حساب - پیمانکار, تامین‌کنندهٔ مصالح or خدمات‌دهنده alike -
against a weighted set of criteria that depends on which of those three it
is. Same wizard/record split and the same cancel-on-close rule as
قراردادها and صورت‌وضعیت; the detail window (opened by double-click) mirrors
ContractDetailWindow187's own shape - export pill top-left, the same data
the record window holds, read-only.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from barkav_ui.theme import font as kit_font, metrics as kit_metrics, palette as kit_palette
from barkav_ui.window import BarkavWindow, BarkavWizard
from contractor_store_stage18_7 import get_contract, load_contracts, upsert_profile
from sales_claims_stage18_7 import show_export_preview_187
from ui_stage18_3 import en, fa

# «پاسخگویی» و «خوش‌قولی» و هر معیار دیگر: امتیاز ۱ تا ۱۰، بازهٔ روشن‌تر
# خوانده‌شدهٔ دست‌نویس - همیشه با رقم فارسی، چون این مقادیر مستقیم در کرکرهٔ
# امتیاز دیده می‌شوند.
SCORE_RANGE = tuple(fa(str(n)) for n in range(1, 11))
# آرشیو is a registry of every طرف حساب, not فقط پیمانکار خودش - دسته‌بندی is
# what the جدول's own نمایش‌براساس filters by, and what selects which
# معیارهای نظرسنجی apply below.
CATEGORY_OPTIONS = ('تامین‌کننده مصالح', 'پیمانکار', 'خدماتی')
DEFAULT_CATEGORY = CATEGORY_OPTIONS[1]
PAYMENT_TYPES = ('نقدی-چکی', 'نقدی', 'چکی')

IDENTITY_FIELDS = (
    ('family_name', 'نام و نام خانوادگی'), ('phone', 'شماره تماس'),
    ('address', 'آدرس'),
)
CATEGORY_FIELDS = (('category', 'دسته‌بندی فعالیت'),)
ACTIVITY_FIELDS = (('activity', 'عنوان فعالیت'),)
PAYMENT_TYPE_FIELDS = (('payment_type', 'نوع پرداخت'),)

# Section نظرسنجی: هر دسته‌بندی معیارهای خودش را دارد - کلید مشترک بین دو
# دسته (مثل «صداقت») یعنی همان مفهوم در هر دو صدق می‌کند؛ برچسب جداگانه
# («رفع نواقص کار» در برابر «رفع نواقص کالا») یعنی مفهوم نزدیک ولی خودش را
# دارد و کلید هم جداست.
CONTRACTOR_CRITERIA = (
    ('quality_of_work', 'کیفیت کار'), ('work_speed', 'سرعت کار'),
    ('fair_price', 'قیمت منصفانه'), ('honesty', 'صداقت'), ('ethics', 'اخلاق'),
    ('labor_supply', 'تامین نیروی کار'), ('equipment_supply', 'تامین وسایل و لوازم کار'),
    ('site_discipline', 'نظم حضور در کارگاه'), ('financial_resilience', 'تاب‌آوری مالی'),
    ('equipment_maintenance', 'نگهداری لوازم'), ('cheque_acceptance', 'موافقت با پرداخت چکی'),
    ('extra_work', 'انجام کارهای خارج از قرارداد'), ('contractor_defect_resolution', 'رفع نواقص کار'),
    ('responsiveness', 'پاسخگویی'), ('reliability', 'خوش‌قولی'),
    ('no_substance_use', 'عدم مصرف دخانیات و مواد'), ('etiquette', 'رعایت شئونات'),
)
SUPPLIER_CRITERIA = (
    ('goods_quality', 'کیفیت کالا'), ('delivery_speed', 'سرعت ارسال'),
    ('fair_price', 'قیمت منصفانه'), ('supply_power', 'قدرت تامین کالا'), ('honesty', 'صداقت'),
    ('financial_resilience', 'تاب‌آوری مالی'), ('availability', 'در دسترس بودن'),
    ('cheque_acceptance', 'موافقت با پرداخت چکی'), ('supplier_defect_resolution', 'رفع نواقص کالا'),
    ('responsiveness', 'پاسخگویی'), ('reliability', 'خوش‌قولی'),
    ('regular_invoicing', 'ارسال منظم فاکتور'), ('return_exchange', 'عودت و تعویض کالا'),
    ('delivery_coordination', 'هماهنگی برای تحویل کالا'),
)
SERVICE_CRITERIA = (
    ('quality_of_work', 'کیفیت کار'), ('work_speed', 'سرعت کار'),
    ('fair_price', 'قیمت منصفانه'), ('honesty', 'صداقت'), ('ethics', 'اخلاق'),
    ('site_discipline', 'نظم حضور در کارگاه'), ('financial_resilience', 'تاب‌آوری مالی'),
    ('cheque_acceptance', 'موافقت با پرداخت چکی'), ('extra_work', 'انجام کارهای خارج از قرارداد'),
    ('contractor_defect_resolution', 'رفع نواقص کار'), ('responsiveness', 'پاسخگویی'),
    ('reliability', 'خوش‌قولی'), ('no_substance_use', 'عدم مصرف دخانیات و مواد'),
    ('etiquette', 'رعایت شئونات'), ('availability', 'در دسترس بودن'),
)
CRITERIA_BY_CATEGORY = {
    'پیمانکار': CONTRACTOR_CRITERIA,
    'تامین‌کننده مصالح': SUPPLIER_CRITERIA,
    'خدماتی': SERVICE_CRITERIA,
}
# هر پنجرهٔ نظرسنجی ۶ معیار می‌گیرد؛ پنجرهٔ سوم (سوم از سه پنجره - «الباقی»)
# هر چه از معیارهای آن دسته‌بندی باقی مانده باشد.
CRITERIA_PAGE_SIZE = 6
CRITERIA_PAGE_COUNT = 3

REHIRE_BANDS = (
    (90, 'اولویت اول'), (80, 'اولویت دوم'), (70, 'اولویت سوم'), (60, 'اولویت چهارم'),
)
NO_REHIRE_CHANCE = 'احتمال همکاری ندارد'


def _score(value) -> str:
    text = str(value or '').strip()
    return fa(text) if text else '-'


def _as_float(value) -> float:
    text = str(en(str(value or '0'))).replace(',', '').strip()
    try:
        return float(text or 0)
    except (TypeError, ValueError):
        return 0.0


def _persian_digits_while_typing(variable: tk.StringVar) -> None:
    """Show whatever is typed in Persian digits - ضریب is a small manual
    weight, not an amount to group."""

    state = {'busy': False}

    def reformat(*_args):
        if state['busy']:
            return
        converted = fa(variable.get())
        if converted != variable.get():
            state['busy'] = True
            try:
                variable.set(converted)
            finally:
                state['busy'] = False

    variable.trace_add('write', reformat)


def criteria_for(category: str) -> tuple[tuple[str, str], ...]:
    return CRITERIA_BY_CATEGORY.get(str(category or '').strip(), ())


def criteria_page(category: str, page_index: int) -> tuple[tuple[str, str], ...]:
    """Page 0 and 1 hold exactly six معیار each; page 2 holds whatever is
    left - «در هر پنجره ۶ عنوان و الباقی در پنجره چهارم»."""

    criteria = criteria_for(category)
    start = page_index * CRITERIA_PAGE_SIZE
    if page_index >= CRITERIA_PAGE_COUNT - 1:
        return criteria[start:]
    return criteria[start:start + CRITERIA_PAGE_SIZE]


def compute_overall_score(values: dict, category: str) -> float:
    """میانگین امتیازات (۱ تا ۱۰) با اعمال وزن ضرایب, از ۱۰۰."""

    total_weighted = total_weight = 0.0
    for key, _label in criteria_for(category):
        weight = _as_float(values.get(f'{key}_weight'))
        if weight <= 0:
            continue
        score = _as_float(values.get(f'{key}_score'))
        total_weighted += score * weight
        total_weight += weight
    if total_weight <= 0:
        return 0.0
    return (total_weighted / total_weight) * 10


def compute_rehire_chance(overall_score: float) -> str:
    for threshold, label in REHIRE_BANDS:
        if overall_score >= threshold:
            return label
    return NO_REHIRE_CHANCE


def archive_identity_segments(profile: dict) -> list[str]:
    return [
        f"نام: {profile.get('family_name') or '-'}",
        f"دسته‌بندی: {profile.get('category') or '-'}",
        f"عنوان فعالیت: {profile.get('activity') or '-'}",
        f"شماره تماس: {fa(str(profile.get('phone') or '-'))}",
        f"آدرس: {profile.get('address') or '-'}",
        f"نوع پرداخت: {profile.get('payment_type') or '-'}",
    ]


def archive_score_line(profile: dict) -> str:
    overall = compute_overall_score(profile, profile.get('category'))
    return (f"امتیاز کلی: {_score(str(profile.get('overall_score') or round(overall, 1)))} از ۱۰۰    |    "
           f"احتمال همکاری مجدد: {profile.get('rehire_chance') or compute_rehire_chance(overall)}")


def archive_criteria_export_rows(profile: dict) -> tuple[list[str], list[list[str]]]:
    """معیارها در دو ستون کنار هم (نه یک فهرست بلند) - یک ردیف, یک معیار از
    نیمهٔ راست و یک از نیمهٔ چپ. هم پنجرهٔ جزئیات هم خروجی PDF/xlsx خودش
    همین تقسیم را می‌خوانند، نه هرکدام حسابِ خودشان."""

    criteria = criteria_for(profile.get('category'))
    headers = ['معیار', 'امتیاز (از ۱۰)', 'ضریب', 'معیار', 'امتیاز (از ۱۰)', 'ضریب']
    half = (len(criteria) + 1) // 2
    right_half, left_half = criteria[:half], criteria[half:]
    rows = []
    for index in range(len(right_half)):
        row = []
        for group in (right_half, left_half):
            if index < len(group):
                key, label = group[index]
                row.extend([label, _score(profile.get(f'{key}_score')),
                           _score(profile.get(f'{key}_weight'))])
            else:
                row.extend(['', '', ''])
        rows.append(row)
    return headers, rows


def archive_history_export_rows(profile: dict) -> tuple[list[str], list[list[str]]]:
    headers = ['ردیف', 'تاریخ همکاری', 'فاز ساخت', 'موضوع همکاری']
    rows = [
        [fa(index + 1), str(entry.get('date') or '-'), str(entry.get('phase') or '-'),
         str(entry.get('subject') or '-')]
        for index, entry in enumerate(profile.get('history') or [])
    ]
    return headers, rows


class ArchiveWizard187(BarkavWizard):
    """شش پنجره: مشخصات کلی, نظرسنجی×۳, محاسبهٔ امتیاز, بررسی نهایی."""

    size_class = 'medium'
    step_titles = ('مشخصات کلی', 'نظرسنجی (۱)', 'نظرسنجی (۲)', 'نظرسنجی (۳)',
                  'محاسبهٔ امتیاز', 'بررسی نهایی')

    def __init__(self, parent, *, rich=None, on_saved=None, profile: dict | None = None):
        self.rich = rich
        self.on_saved = on_saved
        self.record = dict(profile or {})
        self.values: dict[str, tk.StringVar] = {}
        self._saved_once = False
        title = 'ویرایش رده‌بندی' if profile else 'ثبت رده‌بندی جدید'
        # قبل از super().__init__(): آن متد بی‌درنگ render_step(0, ...) را صدا
        # می‌زند، و اگر category هنوز مقداردهی نشده باشد، آن رندر اول خودش یک
        # متغیر با اولین گزینهٔ CATEGORY_OPTIONS می‌سازد - نه DEFAULT_CATEGORY -
        # و چون _var() یک کلید موجود را دوباره مقداردهی نمی‌کند، آن انتخاب غلط
        # برای همیشه می‌ماند.
        self._seed_from_record()
        super().__init__(parent, title, subtitle='BARKAV 18.7')

    def _var(self, key: str, default: str = '') -> tk.StringVar:
        if key not in self.values:
            self.values[key] = tk.StringVar(value=str(default))
        return self.values[key]

    def _seed_from_record(self) -> None:
        self._var('category', DEFAULT_CATEGORY)
        for key, value in self.record.items():
            if isinstance(value, (str, int, float)):
                self._var(key).set(str(value))

    def _category(self) -> str:
        return self._var('category', DEFAULT_CATEGORY).get()

    def _raw_values(self) -> dict:
        return {key: variable.get() for key, variable in self.values.items()}

    # --- rendering -----------------------------------------------------------

    def render_step(self, index: int, parent: tk.Frame) -> None:
        p = kit_palette()
        m = kit_metrics()
        # RLM (U+200F) پیش از عدد لازم است - وگرنه Tk ترکیب «عدد. متن» را در
        # یک عنوان راست‌به‌چپ برعکس می‌چیند (عدد به‌جای راست، در چپ می‌نشیند).
        tk.Label(parent, text=f'‏{fa(index + 1)}. {self.step_titles[index]}',
                bg=p['bg'], fg=p['text_primary'], font=kit_font('title'),
                anchor='e').pack(fill='x', pady=(0, m['gap']))
        card = ttk.Frame(parent, style='Card.TFrame')
        card.pack(fill='x')
        if index == 0:
            self._render_fields(card, IDENTITY_FIELDS)
            self._render_fields(card, CATEGORY_FIELDS, combo=CATEGORY_OPTIONS)
            self._render_fields(card, ACTIVITY_FIELDS)
            self._render_fields(card, PAYMENT_TYPE_FIELDS, combo=PAYMENT_TYPES)
        elif index in (1, 2, 3):
            self._render_criteria_page(card, index - 1)
        elif index == 4:
            self._render_score_summary(card)
        else:
            self._render_confirm(card)

    def _render_fields(self, parent, fields, *, combo: tuple[str, ...] | None = None) -> None:
        p = kit_palette()
        m = kit_metrics()
        bg = p['card']
        grid = tk.Frame(parent, bg=bg)
        grid.pack(fill='x', padx=m['gap'], pady=m['gap'])
        grid.columnconfigure((0, 1), weight=1, uniform='archive')
        for position, (key, label) in enumerate(fields):
            row, column = divmod(position, 2)
            cell = tk.Frame(grid, bg=bg)
            cell.grid(row=row, column=1 - column, sticky='ew',
                     padx=m['gap'] // 2, pady=m['gap'] // 2)
            tk.Label(cell, text=label, bg=bg, fg=p['text_secondary'],
                    font=kit_font('small'), anchor='e').pack(fill='x')
            variable = self._var(key, combo[0] if combo else '')
            if combo:
                ttk.Combobox(cell, textvariable=variable, values=combo,
                            state='readonly', justify='right').pack(fill='x')
            else:
                ttk.Entry(cell, textvariable=variable, justify='right').pack(fill='x')
                if key == 'phone':
                    _persian_digits_while_typing(variable)
                    variable.set(variable.get())

    def _render_criteria_page(self, parent, page_index: int) -> None:
        """هر ردیف: عنوان معیار، کرکرهٔ امتیاز ۱ تا ۱۰، و کادر ضریب دستی -
        همه چسبیده به سمت راست، نزدیک عنوان خودشان؛ ردیف‌ها یک‌درمیان تیره و
        روشن برای تضاد بصری بهتر."""

        p = kit_palette()
        m = kit_metrics()
        chunk = criteria_page(self._category(), page_index)
        if not chunk:
            tk.Label(parent, text='معیاری برای این دسته‌بندی در این صفحه نیست.',
                    bg=p['card'], fg=p['text_secondary'], font=kit_font('body'),
                    anchor='e').pack(fill='x', padx=m['gap'], pady=m['gap'])
            return
        grid = tk.Frame(parent, bg=p['card'])
        grid.pack(fill='x', padx=m['gap'] // 2, pady=m['gap'] // 2)
        grid.columnconfigure(0, weight=1)
        # A fixed label width from this page's own longest معیار pins
        # امتیاز/ضریب to one vertical line regardless of each row's own
        # label length - see ArchiveRecordWindow187._render_criteria.
        label_width = max(len(label) for _key, label in chunk) + 1
        stripes = (p['row_even'], p['row_odd'])
        for row, (key, label) in enumerate(chunk):
            stripe = stripes[row % 2]
            line = tk.Frame(grid, bg=stripe)
            line.grid(row=row, column=0, sticky='ew', pady=1)
            tk.Label(line, text=label, bg=stripe, fg=p['text_primary'],
                    font=kit_font('body'), anchor='e', width=label_width).pack(
                side='right', padx=m['gap'] // 2, pady=m['gap'] // 2)
            score_var = self._var(f'{key}_score', SCORE_RANGE[0])
            ttk.Combobox(line, textvariable=score_var, values=SCORE_RANGE, state='readonly',
                        justify='center', width=4).pack(side='right', pady=m['gap'] // 2)
            tk.Label(line, text='ضریب', bg=stripe, fg=p['text_secondary'],
                    font=kit_font('small')).pack(side='right', padx=(m['gap'] // 2, m['gap'] // 4))
            weight_var = self._var(f'{key}_weight', '1')
            weight_entry = ttk.Entry(line, textvariable=weight_var, justify='center', width=5)
            weight_entry.pack(side='right', padx=(0, m['gap'] // 2), pady=m['gap'] // 2)
            _persian_digits_while_typing(weight_var)
            weight_var.set(weight_var.get())

    def _render_score_summary(self, parent) -> None:
        p = kit_palette()
        m = kit_metrics()
        overall = compute_overall_score(self._raw_values(), self._category())
        rehire = compute_rehire_chance(overall)
        summary = (
            f"امتیاز کلی: {_score(round(overall, 1))} از ۱۰۰\n"
            f"احتمال همکاری مجدد: {rehire}"
        )
        tk.Label(parent, text=summary, bg=p['panel'], fg=p['text_primary'],
                font=kit_font('title'), anchor='e', justify='right',
                padx=m['outer_pad'], pady=m['outer_pad']).pack(
            fill='x', padx=m['gap'] // 2, pady=m['gap'] // 2)

    def _render_confirm(self, parent) -> None:
        p = kit_palette()
        m = kit_metrics()
        overall = compute_overall_score(self._raw_values(), self._category())
        summary = (
            f"نام: {self._var('family_name').get() or '-'}\n"
            f"دسته‌بندی: {self._category() or '-'}\n"
            f"عنوان فعالیت: {self._var('activity').get() or '-'}\n"
            f"امتیاز کلی: {_score(round(overall, 1))} از ۱۰۰\n"
            f"احتمال همکاری مجدد: {compute_rehire_chance(overall)}"
        )
        tk.Label(parent, text=summary, bg=p['panel'], fg=p['text_primary'],
                font=kit_font('body'), anchor='e', justify='right',
                padx=m['outer_pad'], pady=m['outer_pad']).pack(
            fill='x', padx=m['gap'] // 2, pady=m['gap'] // 2)

    # --- persistence -----------------------------------------------------------

    def collect(self) -> dict:
        record = dict(self.record)
        record.update(self._raw_values())
        overall = compute_overall_score(record, record.get('category'))
        record['overall_score'] = str(round(overall, 1))
        record['rehire_chance'] = compute_rehire_chance(overall)
        return record

    def finish(self) -> None:
        self._save(open_record=False)
        self.close()

    def close(self) -> None:
        """Mirrors ContractWizard187.close(): cancel an edit, carry on a draft."""

        if self._saved_once:
            super().close()
            return
        if not self.record.get('profile_id'):
            self._save(open_record=True)
        elif self.on_saved is not None:
            self.on_saved(self.record, True)
        super().close()

    def _save(self, *, open_record: bool) -> None:
        if self._saved_once:
            return
        record = self.collect()
        if not str(record.get('family_name') or '').strip():
            return
        self._saved_once = True
        saved = upsert_profile(record)
        if self.on_saved is not None:
            self.on_saved(saved, open_record)


class ArchiveRecordWindow187(BarkavWindow):
    """همان مشخصات/نظرسنجی/محاسبهٔ امتیاز ویزارد, بدون بررسی نهایی - به‌علاوهٔ
    تاریخ‌های همکاری در طول پروژه.
    """

    size_class = 'full'

    def __init__(self, parent, *, profile: dict, rich=None, on_saved=None):
        self.profile = dict(profile)
        self.rich = rich
        self.on_saved = on_saved
        self.values: dict[str, tk.StringVar] = {}
        super().__init__(parent, 'پنجره رکورد',
                         subtitle=str(profile.get('family_name') or ''), show_footer=True,
                         scrollable=True)
        self._build()
        self.add_action('ذخیره', self.save, style='Primary.TButton')
        self.add_action('بستن', self.close)

    def _var(self, key: str, default: str = '') -> tk.StringVar:
        return self.values.setdefault(key, tk.StringVar(value=str(self.profile.get(key) or default)))

    def _category(self) -> str:
        return self._var('category', DEFAULT_CATEGORY).get()

    def _raw_values(self) -> dict:
        return {key: variable.get() for key, variable in self.values.items()}

    def _build(self) -> None:
        p = kit_palette()
        m = kit_metrics()

        heading = tk.Frame(self.body, bg=p['bg'])
        heading.pack(fill='x', pady=(0, m['gap'] // 2))
        tk.Label(heading, text='‏۱. مشخصات کلی', bg=p['bg'], fg=p['text_primary'],
                font=kit_font('title'), anchor='e').pack(fill='x')
        identity = ttk.Frame(self.body, style='Card.TFrame')
        identity.pack(fill='x', pady=(0, m['gap']))
        self._render_identity_fields(identity)

        survey_heading = tk.Frame(self.body, bg=p['bg'])
        survey_heading.pack(fill='x', pady=(0, m['gap'] // 2))
        tk.Label(survey_heading, text='‏۲. نظرسنجی', bg=p['bg'], fg=p['text_primary'],
                font=kit_font('title'), anchor='e').pack(fill='x')

        # نظرسنجی در سه ستون کنار هم (همان سه صفحهٔ ویزارد, این‌بار پهلوی هم
        # نه پیاپی), و ۳/محاسبهٔ امتیاز + ۴/تاریخ‌های همکاری در یک ستون کناری -
        # نه زیر آن. پنجره خودش scrollable است، برای وقتی جا کم بیاید.
        category = self._category()
        combo_row = tk.Frame(self.body, bg=p['bg'])
        combo_row.pack(fill='both', expand=True, pady=(0, m['gap']))
        for column in range(CRITERIA_PAGE_COUNT):
            grid_column = CRITERIA_PAGE_COUNT - column
            combo_row.columnconfigure(grid_column, weight=1, uniform='survey_col')
            column_card = ttk.Frame(combo_row, style='Card.TFrame')
            column_card.grid(row=0, column=grid_column, sticky='nsew', padx=m['gap'] // 2)
            self._render_criteria(column_card, criteria_page(category, column))
        combo_row.columnconfigure(0, weight=1, uniform='survey_col')

        side = tk.Frame(combo_row, bg=p['bg'])
        side.grid(row=0, column=0, sticky='nsew', padx=(m['gap'] // 2, 0))

        score_heading = tk.Frame(side, bg=p['bg'])
        score_heading.pack(fill='x', pady=(0, m['gap'] // 2))
        tk.Label(score_heading, text='‏۳. محاسبهٔ امتیاز', bg=p['bg'], fg=p['text_primary'],
                font=kit_font('title'), anchor='e').pack(fill='x')
        score_section = ttk.Frame(side, style='Card.TFrame')
        score_section.pack(fill='both', expand=True)
        self._score_caption = tk.Label(score_section, bg=p['card'], fg=p['text_primary'],
                                       font=kit_font('title'), anchor='e', justify='right',
                                       wraplength=320)
        self._score_caption.pack(fill='x', padx=m['outer_pad'], pady=m['outer_pad'])
        self._show_score()

        # کادر ۴ خودش, تمام عرض, زیر کادرهای نظرسنجی - نه فشرده در ستون کناری
        # کنار محاسبهٔ امتیاز, که برایش فقط عرض یک‌سوم صفحه می‌ماند.
        history_heading = tk.Frame(self.body, bg=p['bg'])
        history_heading.pack(fill='x', pady=(m['gap'], m['gap'] // 2))
        tk.Label(history_heading, text='‏۴. تاریخ‌های همکاری در طول پروژه', bg=p['bg'],
                fg=p['text_primary'], font=kit_font('title'), anchor='e').pack(fill='x')
        history = ttk.Frame(self.body, style='Card.TFrame')
        history.pack(fill='both', expand=True)
        self._render_history(history)

    def _render_identity_fields(self, group) -> None:
        """مشخصات کلی's شش فیلد در یک کادر ۲×۳ - نه چهار گروه پیاپی که هرکدام
        فقط یکی-دو فیلد داشتند و ارتفاع را بی‌جهت بالا می‌بردند."""

        m = kit_metrics()
        fields = (
            (*IDENTITY_FIELDS[0], None), (*IDENTITY_FIELDS[1], None), (*IDENTITY_FIELDS[2], None),
            (*CATEGORY_FIELDS[0], CATEGORY_OPTIONS), (*ACTIVITY_FIELDS[0], None),
            (*PAYMENT_TYPE_FIELDS[0], PAYMENT_TYPES),
        )
        grid = ttk.Frame(group, style='Card.TFrame')
        grid.pack(fill='x')
        grid.columnconfigure((0, 1), weight=1, uniform='archive_record')
        for position, (key, label, combo) in enumerate(fields):
            row, column = divmod(position, 2)
            cell = ttk.Frame(grid, style='Card.TFrame')
            cell.grid(row=row, column=1 - column, sticky='ew',
                     padx=m['gap'] // 2, pady=m['gap'] // 2)
            # bare ttk.Label carries no font override of its own here, so it
            # fell back to the ttk theme's own default font/family - visibly
            # different from every other caption on this page, which all set
            # kit_font('small') explicitly.
            ttk.Label(cell, text=label, anchor='e', justify='right',
                     font=kit_font('small')).pack(fill='x')
            variable = self._var(key, combo[0] if combo else '')
            if combo:
                widget = ttk.Combobox(cell, textvariable=variable, values=combo,
                                      state='readonly', justify='right')
                widget.pack(fill='x')
                if key == 'category':
                    widget.bind('<<ComboboxSelected>>', lambda _e: self._category_changed())
            else:
                ttk.Entry(cell, textvariable=variable, justify='right').pack(fill='x')
                if key == 'phone':
                    _persian_digits_while_typing(variable)
                    variable.set(variable.get())

    def _category_changed(self) -> None:
        """دسته‌بندی که عوض شود, معیارهای نظرسنجی هم عوض می‌شوند - رکورد را
        از نو می‌سازیم تا کادر درست را نشان دهد."""

        for child in list(self.body.winfo_children()):
            child.destroy()
        self._build()

    def _render_criteria(self, parent, criteria) -> None:
        """``criteria`` is one column's own slice - criteria_page(category, N),
        the same three-way split the wizard's own نظرسنجی pages use."""

        p = kit_palette()
        m = kit_metrics()
        if not criteria:
            return
        # A bare pack(side='right') puts امتیاز/ضریب right after however much
        # room each row's OWN معیار text needs - رفع نواقص کار (13 حرف) and
        # انجام کارهای خارج از قرارداد (28 حرف) in the same column land their
        # boxes at completely different x - a fixed width from this column's
        # own longest label pins them to one vertical line instead.
        label_width = max(len(label) for _key, label in criteria) + 1
        stripes = (p['row_even'], p['row_odd'])
        for index, (key, label) in enumerate(criteria):
            stripe = stripes[index % 2]
            line = tk.Frame(parent, bg=stripe)
            line.pack(fill='x')
            tk.Label(line, text=label, bg=stripe, fg=p['text_primary'],
                    font=kit_font('body'), anchor='e', width=label_width).pack(
                side='right', padx=m['gap'] // 2, pady=m['gap'] // 2)
            score_var = self._var(f'{key}_score', SCORE_RANGE[0])
            ttk.Combobox(line, textvariable=score_var, values=SCORE_RANGE, state='readonly',
                        justify='center', width=4).pack(side='right', pady=m['gap'] // 2)
            tk.Label(line, text='ضریب', bg=stripe, fg=p['text_secondary'],
                    font=kit_font('small')).pack(side='right', padx=(m['gap'] // 2, m['gap'] // 4))
            weight_var = self._var(f'{key}_weight', '1')
            weight_entry = ttk.Entry(line, textvariable=weight_var, justify='center', width=5)
            weight_entry.pack(side='right', padx=(0, m['gap'] // 2), pady=m['gap'] // 2)
            _persian_digits_while_typing(weight_var)
            weight_var.set(weight_var.get())
            weight_var.trace_add('write', lambda *_a: self._show_score())
            score_var.trace_add('write', lambda *_a: self._show_score())

    def _show_score(self) -> None:
        caption = getattr(self, '_score_caption', None)
        if caption is None or not caption.winfo_exists():
            return
        overall = compute_overall_score(self._raw_values(), self._category())
        caption.configure(
            text=f'امتیاز کلی: {_score(round(overall, 1))} از ۱۰۰    |    '
                 f'احتمال همکاری مجدد: {compute_rehire_chance(overall)}')

    def _render_history(self, parent) -> None:
        p = kit_palette()
        m = kit_metrics()
        rows = self.profile.get('history') or []
        if not rows:
            tk.Label(parent, text='تاریخ همکاری‌ای برای این ردیف ثبت نشده است.',
                    bg=p['card'], fg=p['text_secondary'], font=kit_font('body'),
                    anchor='e').pack(fill='x', pady=m['gap'] // 2)
            return
        header = tk.Frame(parent, bg=p['heading'])
        header.pack(fill='x')
        for text, width in (('ردیف', 6), ('تاریخ همکاری', 16), ('فاز ساخت', 20), ('موضوع همکاری', 40)):
            # Same font as the row cells below it - tk.Label's width=N is a
            # character count in THAT label's own font, so a smaller header
            # font renders the same width= narrower than the row under it.
            tk.Label(header, text=text, bg=p['heading'], fg=p['text_primary'],
                    font=kit_font('body'), anchor='e', width=width).pack(side='right')
        for index, entry in enumerate(rows):
            line = tk.Frame(parent, bg=p['card'])
            line.pack(fill='x')
            for text, width in (
                (fa(index + 1), 6), (str(entry.get('date') or '-'), 16),
                (str(entry.get('phase') or '-'), 20), (str(entry.get('subject') or '-'), 40),
            ):
                tk.Label(line, text=text, bg=p['card'], fg=p['text_primary'],
                        font=kit_font('body'), anchor='e', width=width).pack(side='right')

    def save(self) -> None:
        record = dict(self.profile)
        record.update(self._raw_values())
        overall = compute_overall_score(record, record.get('category'))
        record['overall_score'] = str(round(overall, 1))
        record['rehire_chance'] = compute_rehire_chance(overall)
        self.profile = upsert_profile(record)
        if self.on_saved is not None:
            self.on_saved(self.profile)


EXPORT_PROMPT = 'خروجی'
EXPORT_FORMATS = {'پی‌دی‌اف': 'pdf', 'اکسل': 'xlsx', 'پرینت': 'print'}


class ArchiveDetailWindow187(BarkavWindow):
    """دبل‌کلیک روی یک ردیف آرشیو - نه پنجرهٔ رکورد قابل‌ویرایش, بلکه نمایش/
    خروجی فقط‌خواندنی: مشخصات کلی، جدول معیارهای نظرسنجی، و تاریخ‌های
    همکاری در طول پروژه.
    """

    size_class = 'full'

    def __init__(self, parent, *, profile: dict, on_export=None):
        self.profile = dict(profile)
        self.on_export = on_export
        super().__init__(parent, 'جزئیات رده‌بندی',
                         subtitle=str(profile.get('family_name') or ''), show_footer=True)
        self._build()
        self.add_action('بستن', self.close)

    def _build(self) -> None:
        p = kit_palette()
        m = kit_metrics()

        top = tk.Frame(self.body, bg=p['bg'])
        top.pack(fill='x', pady=(0, m['gap']))
        self.export_choice = tk.StringVar(value=EXPORT_PROMPT)
        combo = ttk.Combobox(top, textvariable=self.export_choice,
                             values=(EXPORT_PROMPT, *EXPORT_FORMATS),
                             state='readonly', justify='right', width=18, style='Toolbar.TCombobox')
        combo.pack(side='left')
        combo.bind('<<ComboboxSelected>>', lambda _e: self._export_chosen())

        # هر بخش ویجت Label جداگانهٔ خودش را می‌گیرد، نه یک رشتهٔ ترکیبی با
        # \n میان‌شان - همان قاعدهٔ StatementFinanceDetailWindow187, هم برای
        # یک ردیف افقی یک‌جا (نه سه ردیف پیاپی), هم چون Tk بدون الگوریتم
        # bidi واقعی رشته‌های ترکیبی چندبخشی را گاهی به‌هم می‌ریزد.
        identity_row = tk.Frame(self.body, bg=p['bg'])
        identity_row.pack(fill='x', pady=(0, m['gap']))
        for segment in self._identity_segments():
            tk.Label(identity_row, text=segment, bg=p['bg'], fg=p['text_primary'],
                    font=kit_font('body'), anchor='e').pack(side='right', padx=(m['gap'], 0))

        tk.Label(self.body, text=self._score_line(), bg=p['panel'], fg=p['text_primary'],
                font=kit_font('title'), anchor='e', justify='right',
                padx=m['outer_pad'], pady=m['outer_pad']).pack(fill='x', pady=(0, m['gap']))

        criteria_heading = tk.Frame(self.body, bg=p['bg'])
        criteria_heading.pack(fill='x', pady=(0, m['gap'] // 2))
        tk.Label(criteria_heading, text='معیارهای نظرسنجی', bg=p['bg'], fg=p['text_primary'],
                font=kit_font('title'), anchor='e').pack(fill='x')
        criteria_section = ttk.Frame(self.body, style='Card.TFrame')
        criteria_section.pack(fill='x', pady=(0, m['gap']))
        self._render_criteria_table(criteria_section)

        history_heading = tk.Frame(self.body, bg=p['bg'])
        history_heading.pack(fill='x', pady=(0, m['gap'] // 2))
        tk.Label(history_heading, text='تاریخ‌های همکاری در طول پروژه', bg=p['bg'],
                fg=p['text_primary'], font=kit_font('title'), anchor='e').pack(fill='x')
        history_section = ttk.Frame(self.body, style='Card.TFrame')
        history_section.pack(fill='x')
        self._render_history_table(history_section)

    def _identity_segments(self) -> list[str]:
        return archive_identity_segments(self.profile)

    def _score_line(self) -> str:
        return archive_score_line(self.profile)

    def _criteria_export_rows(self) -> tuple[list[str], list[list[str]]]:
        return archive_criteria_export_rows(self.profile)

    def _history_export_rows(self) -> tuple[list[str], list[list[str]]]:
        return archive_history_export_rows(self.profile)

    def _render_criteria_table(self, parent) -> None:
        p = kit_palette()
        headers, rows = self._criteria_export_rows()
        if not rows:
            tk.Label(parent, text='معیاری برای این دسته‌بندی ثبت نشده است.',
                    bg=p['card'], fg=p['text_secondary'], font=kit_font('body'),
                    anchor='e').pack(fill='x', pady=kit_metrics()['gap'] // 2)
            return
        widths = (34, 14, 10, 34, 14, 10)
        header = tk.Frame(parent, bg=p['heading'])
        header.pack(fill='x')
        for text, width in zip(headers, widths):
            # Same font as the row cells below it - see _render_history_table.
            tk.Label(header, text=text, bg=p['heading'], fg=p['text_primary'],
                    font=kit_font('body'), anchor='e', width=width).pack(side='right')
        for row in rows:
            line = tk.Frame(parent, bg=p['card'])
            line.pack(fill='x')
            for text, width in zip(row, widths):
                tk.Label(line, text=text, bg=p['card'], fg=p['text_primary'],
                        font=kit_font('body'), anchor='e', width=width).pack(side='right')

    def _render_history_table(self, parent) -> None:
        p = kit_palette()
        m = kit_metrics()
        rows = self.profile.get('history') or []
        if not rows:
            tk.Label(parent, text='تاریخ همکاری‌ای برای این ردیف ثبت نشده است.',
                    bg=p['card'], fg=p['text_secondary'], font=kit_font('body'),
                    anchor='e').pack(fill='x', pady=m['gap'] // 2)
            return
        header = tk.Frame(parent, bg=p['heading'])
        header.pack(fill='x')
        for text, width in (('ردیف', 6), ('تاریخ همکاری', 16), ('فاز ساخت', 20), ('موضوع همکاری', 40)):
            # Same font as the row cells below it - tk.Label's width=N is a
            # character count in THAT label's own font, so a smaller header
            # font renders the same width= narrower than the row under it.
            tk.Label(header, text=text, bg=p['heading'], fg=p['text_primary'],
                    font=kit_font('body'), anchor='e', width=width).pack(side='right')
        for index, entry in enumerate(rows):
            line = tk.Frame(parent, bg=p['card'])
            line.pack(fill='x')
            for text, width in (
                (fa(index + 1), 6), (str(entry.get('date') or '-'), 16),
                (str(entry.get('phase') or '-'), 20), (str(entry.get('subject') or '-'), 40),
            ):
                tk.Label(line, text=text, bg=p['card'], fg=p['text_primary'],
                        font=kit_font('body'), anchor='e', width=width).pack(side='right')

    def _confirm_export_choice(self, choice: str, addressee='سایر'):
        fmt = {'Excel': 'xlsx', 'PDF': 'pdf', 'پرینت': 'print'}.get(choice)
        if fmt is None or self.on_export is None:
            return False
        self.on_export(self.profile, fmt, addressee)
        return True

    def _export_chosen(self) -> None:
        fmt = EXPORT_FORMATS.get(self.export_choice.get())
        self.export_choice.set(EXPORT_PROMPT)
        if fmt is None or self.on_export is None:
            return
        criteria_headers, criteria_rows = self._criteria_export_rows()
        if not criteria_rows:
            criteria_headers = ['بخش', 'شرح']
            criteria_rows = [['نظرسنجی', 'معیاری برای این دسته‌بندی ثبت نشده است']]
        specs = [
            ('مشخصات', 'اطلاعات', segment)
            for segment in self._identity_segments()
        ]
        specs.append(('امتیاز', 'جمع‌بندی', self._score_line()))
        history_headers, history_rows = self._history_export_rows()
        for row in history_rows:
            specs.append((
                'تاریخ همکاری',
                f'ردیف {row[0] if row else "-"}',
                ' | '.join(str(value or '-') for value in row[1:]),
            ))
        choices = {'xlsx': 'Excel', 'pdf': 'PDF', 'print': 'پرینت'}
        return show_export_preview_187(
            self,
            export_format=choices.get(fmt, 'PDF'),
            headers=criteria_headers,
            rows=criteria_rows,
            specs=specs,
            title='پیش‌نمایش جزئیات رده‌بندی',
            table_caption='معیارهای نظرسنجی',
            row_label='ردیف',
            include_addressee=True,
            on_confirm=lambda choice, _orientation, addressee, _include_documents:
                self._confirm_export_choice(choice, addressee),
        )
