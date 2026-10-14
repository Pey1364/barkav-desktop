"""Deterministic calendar rows and source-only AI tables (no posting or writes)."""
from __future__ import annotations
import json
import re
from datetime import date, timedelta
import jdatetime
from ui_stage18_3 import en, fa

REPORT_FIELDS = (
    'تاریخ', 'روز هفته', 'شرح گزارش', 'شماره فاز اصلی', 'عنوان فاز اصلی',
    'شماره فاز فرعی', 'عنوان فاز فرعی', 'تعداد عوامل پیمانکار',
    'تعداد عوامل روزمزد', 'ماشین‌آلات فعال', 'وضعیت آب‌وهوا',
)
WEEKDAYS = ('دوشنبه', 'سه‌شنبه', 'چهارشنبه', 'پنجشنبه', 'جمعه', 'شنبه', 'یکشنبه')
ANSWER_FIELDS = ('تاریخ', 'روز هفته', 'تاریخ ثبت', 'دسته‌بندی', 'شرح', 'جزئیات',
                 'مبلغ ثبت‌شده', 'فاز', *REPORT_FIELDS[2:])


def text(value):
    return '' if value is None or str(value).strip() == '—' else str(value).strip()


def normalized(value):
    value = en(text(value)).replace('ي', 'ی').replace('ك', 'ک').replace('\u200c', ' ')
    return ' '.join(re.sub(r'[ـ\u064b-\u065f]', '', value).split())


def day_values(day):
    return fa(jdatetime.date.fromgregorian(date=day).strftime('%Y/%m/%d')), WEEKDAYS[day.weekday()]


def unique_join(values):
    return '\n'.join(dict.fromkeys(value for value in map(text, values) if value))


_MONTH_NAMES = 'فروردین|اردیبهشت|خرداد|تیر|مرداد|شهریور|مهر|آبان|آذر|دی|بهمن|اسفند'
_SUMMARY = re.compile(
    r'(?:تعداد\s+[^\n؛;،.!؟]{1,40}?|[0-9۰-۹]+)\s+ردیف\s+'
    r'(?:گزارش\s+(?:روزانه|هفتگی|ماهانه)\s+)?ثبت\s+(?:شده\s+است|شد(?:ه)?)(?:[.!؛;])?'
)
_DATE_TEXT = re.compile(
    r'(?<![0-9۰-۹])(?:[1۱][3۳4۴][0-9۰-۹]{2}\s*[/.-]\s*[0-9۰-۹]{1,2}\s*[/.-]\s*[0-9۰-۹]{1,2}'
    r'|[0-9۰-۹]{1,2}\s+(?:' + _MONTH_NAMES + r')(?:\s+[1۱][3۳4۴][0-9۰-۹]{2})?)(?![0-9۰-۹])'
)


def clean_report_description(value):
    """Remove presentation boilerplate only; keep source records and line breaks."""
    value = _SUMMARY.sub('', text(value))
    output = []
    for line in value.splitlines():
        line = re.sub(r'^\s*(?:[0-9۰-۹]+\s*[.)،-]|[•●▪])\s*', '', line)
        has_date = bool(_DATE_TEXT.search(line))
        line = re.sub(r'^\s*گزارش\s+(?:روزانه|هفتگی|ماهانه)\s*', '', line)
        line = _DATE_TEXT.sub('', line)
        line = re.sub(r'(?<![0-9۰-۹])[0-9۰-۹]{1,2}[/.-][0-9۰-۹]{1,2}[/.-][1۱][3۳4۴][0-9۰-۹]{2}(?![0-9۰-۹])', '', line)
        if has_date:
            line = re.sub(r'^\s*(?:روز\s+)?(?:شنبه|یکشنبه|دوشنبه|سه[‌ ]?شنبه|چهارشنبه|پنج[‌ ]?شنبه|جمعه)(?=\s|[-—:،]|$)', '', line)
        line = ' '.join(line.split()).strip(' -–—،:؛;.!')
        if line and not is_report_fragment(line):
            output.append(line)
    return '\n'.join(output)



def is_report_fragment(value):
    value = normalized(value).strip(' -–—،:؛;.!•')
    if not value or not re.search(r'[آ-یa-zA-Z]', value):
        return True
    return value in {'از', 'تا', 'از تا', 'الی', 'و', 'در', 'روز', 'تاریخ', 'گزارش روزانه',
                     'گزارش هفتگی', 'گزارش ماهانه'}


def display_dates(value):
    """Combine weekdays with recorded dates; never guess an absent/invalid date."""
    output = []
    for line in text(value).splitlines():
        try:
            year, month, day = map(int, en(line).replace('-', '/').split('/'))
            actual = jdatetime.date(year, month, day).togregorian()
            stamp, weekday = day_values(actual)
            output.append(f'{weekday} {stamp}')
        except (ValueError, TypeError):
            output.append(line)
    return unique_join(output)


def report_table(rows, *, periodic=False, documents=True):
    fields = ['ردیف', 'شرح گزارش', 'تاریخ', 'تعداد روز'] if periodic else ['ردیف', 'تاریخ', 'شرح گزارش']
    fields.extend(REPORT_FIELDS[3:])
    if documents:
        fields.append('نمایش سند')
    output = []
    for index, source in enumerate(rows, 1):
        stamps = unique_join(day_values(date.fromisoformat(day))[0] for day in source.get('_dates', []))
        row = {key: source.get(key, '') for key in fields}
        row.update({'ردیف': fa(index), 'تاریخ': display_dates(stamps or source.get('تاریخ')),
                    'شرح گزارش': clean_report_description(source.get('شرح گزارش'))})
        if periodic:
            # Repeated registrations on one execution day count as one day.
            days = set(source.get('_dates') or text(source.get('تاریخ')).splitlines())
            days.discard('')
            row['تعداد روز'] = f'{fa(len(days))} روز'
        if documents:
            row['نمایش سند'] = '\n'.join(source.get('_document_paths', []))
        output.append(row)
    return fields, output


def present_answer_table(fields, rows):
    """Use one execution-date column, preserving an explicitly requested registration date."""
    fields = [field for field in fields if field not in {'روز هفته', 'تاریخ ثبت'}]
    rows = [dict(row) for row in rows]
    for row in rows:
        row.pop('روز هفته', None)
        row['تاریخ'] = display_dates(row.get('تاریخ'))
        registered = display_dates(row.pop('تاریخ ثبت', ''))
        if registered and registered != row['تاریخ']:
            row['تاریخ'] = unique_join([row['تاریخ'], f'تاریخ ثبت: {registered}'])
        for key in ('شرح', 'شرح گزارش', 'جزئیات', 'شرح کالا/مصالح'):
            if key in row:
                row[key] = clean_report_description(row[key])
    return fields, rows


def phase_parts(value, number=''):
    value = text(value)
    if re.fullmatch(r'[0-9۰-۹]+(?:[.][0-9۰-۹]+)*', value):
        return fa(text(number) or value), ''
    found = re.match(r'^([0-9۰-۹]+(?:[.][0-9۰-۹]+)*)\s*(?:[-–—:：.]\s*|\s+)(.+)$', value)
    if found:
        return fa(text(number) or found.group(1)), found.group(2).strip()
    if not number and value:
        from ai_parser import CONSTRUCTION_PHASES
        lookup = {normalized(title): index for index, title in enumerate(CONSTRUCTION_PHASES, 1)}
        number = lookup.get(normalized(value), '')
    return fa(text(number)), value


def phase_fields(meta, fallback=''):
    main = phase_parts(meta.get('main_phase') or fallback, meta.get('main_phase_no') or meta.get('phase_no'))
    # Subphase numbers are only supplied or explicitly written; never infer them.
    sub = phase_parts(meta.get('sub_phase'), meta.get('sub_phase_no')) if meta.get('sub_phase_no') else ('', text(meta.get('sub_phase')))
    explicit_sub = re.match(r'^([0-9۰-۹]+(?:[.][0-9۰-۹]+)*)\s*(?:[-–—:：.]\s*|\s+)(.+)$', sub[1])
    if explicit_sub:
        sub = (fa(explicit_sub.group(1)), explicit_sub.group(2).strip())
    return dict(zip(REPORT_FIELDS[3:7], (*main, *sub)))


def build_period_rows(entries, start, end, *, daily):
    """entries contain only extracted source values; all dates stay auditable."""
    grouped = {}
    for entry in sorted(entries, key=lambda row: (row['_day'], row['activity'])):
        if not start <= entry['_day'] <= end:
            continue
        key = entry['_day'] if daily else normalized(entry.get('activity_key') or entry['activity'])
        grouped.setdefault(key, []).append(entry)
    keys = sorted(grouped, key=lambda key: grouped[key][0]['_day'])
    if daily:
        keys = [start + timedelta(days=offset) for offset in range((end - start).days + 1)]
    rows = []
    for key in keys:
        sources = grouped.get(key, [])
        days = sorted({item['_day'] for item in sources}) or ([key] if daily else [])
        descriptions = []
        for source in sources:
            body = clean_report_description(source['activity'] if daily else source.get('activity_key') or source['activity'])
            if body and normalized(body) not in {normalized(item) for item in descriptions}:
                descriptions.append(body)
        if daily:
            for source in sources:
                details = clean_report_description(source.get('details'))
                for line in details.splitlines():
                    if line and not any(normalized(line) in normalized(body) for body in descriptions):
                        descriptions.append(line)
        elif descriptions:
            descriptions = descriptions[:1]
        row = {
            'تاریخ': unique_join(day_values(day)[0] for day in days),
            'روز هفته': unique_join(f'{day_values(day)[1]} {day_values(day)[0]}' for day in days),
            'شرح گزارش': unique_join(descriptions) if sources else 'اطلاعات ثبت نشده',
        }
        for number_field, title_field in (REPORT_FIELDS[3:5], REPORT_FIELDS[5:7]):
            pairs = list(dict.fromkeys((text(source.get(number_field)), text(source.get(title_field)))
                                      for source in sources if text(source.get(number_field)) or text(source.get(title_field))))
            row[number_field] = '\n'.join(number or ('ثبت نشده' if len(pairs) > 1 else '') for number, title in pairs)
            row[title_field] = '\n'.join(title or ('ثبت نشده' if len(pairs) > 1 else '') for number, title in pairs)
        for field in REPORT_FIELDS[7:]:
            values = [text(source.get(field)) for source in sources]
            nonempty = list(dict.fromkeys(value for value in values if value))
            # Preserve variable counts with their dates; do not sum snapshots.
            if not daily and len(nonempty) > 1 and field in REPORT_FIELDS[7:]:
                row[field] = unique_join(f'{day_values(source["_day"])[0]}: {text(source.get(field))}'
                                         for source in sources if text(source.get(field)))
            else:
                row[field] = unique_join(values)
        ids = list(dict.fromkeys(source['_source_id'] for source in sources if source['_source_id']))
        row['_source_ids'] = ids
        row['_source_id'] = ids[0] if len(ids) == 1 else ''
        row['_dates'] = [day.isoformat() for day in days]
        row['_activities'] = list(dict.fromkeys(source['activity'] for source in sources))
        row['فاز اصلی'] = row['عنوان فاز اصلی']
        row['فاز فرعی'] = row['عنوان فاز فرعی']
        row['مرحله ساخت'] = unique_join(source.get('_legacy_phase') for source in sources)
        row['توضیحات'] = unique_join(source.get('details') for source in sources)
        rows.append(row)
    return rows


def counting_days(query):
    value = normalized(query)
    return bool(re.search(r'چند\s*روز|تعداد[^؟?\n]{0,100}روز|چند\s*تا\s*روز', value))


def prepare_answer_records(records):
    return [{**{key: value for key, value in row.items() if key in ANSWER_FIELDS},
             '_record_ref': f'R{index}'} for index, row in enumerate(records, 1)]


def parse_grounded_answer(raw, records, *, count_days=False, require_all=False):
    """AI chooses columns/refs only. It cannot supply display values or totals."""
    value = str(raw or '').strip()
    if value.startswith('```json') and value.endswith('```'):
        value = value[7:-3].strip()
    elif value.startswith('```') and value.endswith('```'):
        value = value[3:-3].strip()
    try:
        payload = json.loads(value)
    except (ValueError, TypeError):
        raise RuntimeError('پاسخ مدل قالب جدولی قابل‌بررسی ندارد؛ پاسخی نمایش داده نشد.') from None
    if not isinstance(payload, dict) or set(payload) != {'columns', 'record_ids'}:
        raise RuntimeError('پاسخ مدل باید فقط ستون‌ها و شناسهٔ رکوردهای ثبت‌شده را مشخص کند.')
    fields, refs = payload['columns'], payload['record_ids']
    if (not isinstance(fields, list) or not all(isinstance(field, str) and field in ANSWER_FIELDS for field in fields)
            or not isinstance(refs, list) or not all(isinstance(ref, str) for ref in refs)):
        raise RuntimeError('ستون یا شناسهٔ پاسخ مدل قابل‌بررسی نیست.')
    source = {row['_record_ref']: row for row in records}
    if any(ref not in source for ref in refs) or (require_all and set(refs) != set(source)):
        raise RuntimeError('پاسخ مدل با رکوردهای ثبت‌شده مطابقت ندارد؛ گزارش ساخته نشد.')
    fields = list(dict.fromkeys(['تاریخ', *fields]))
    if count_days:
        fields = list(dict.fromkeys(['روز هفته', 'تاریخ', *fields, 'شرح']))
    selected = [source[ref] for ref in dict.fromkeys(refs)]
    rows = []
    if count_days:
        by_day = {}
        for row in selected:
            normalized_date = normalized(row.get('تاریخ')).replace('-', '/')
            try:
                year, month, day = map(int, normalized_date.split('/'))
                actual_day = jdatetime.date(year, month, day).togregorian()
            except (ValueError, TypeError):
                raise RuntimeError('یکی از رکوردهای پاسخ تاریخ معتبر ندارد؛ تعداد روزها اعلام نشد.') from None
            by_day.setdefault(actual_day, []).append(row)
        for day, sources in sorted(by_day.items()):
            row = {field: unique_join(source.get(field) for source in sources) for field in fields}
            row['تاریخ'], row['روز هفته'] = day_values(day)
            rows.append(row)
        fields.append('تعداد روزها')
        for row in rows:
            row['تعداد روزها'] = '۱'
        rows.append({'ردیف': 'جمع', 'تعداد روزها': fa(len(by_day)), 'شرح': 'تعداد کل روزها'})
    else:
        rows = [{field: text(source.get(field)) for field in fields} for source in selected]
    if not rows:
        if 'شرح' not in fields:
            fields.append('شرح')
        rows = [{'تاریخ': '', 'شرح': 'در اطلاعات ثبت‌شده یافت نشد'}]
    return present_answer_table(['ردیف', *fields], [{**row, 'ردیف': row.get('ردیف', fa(index))} for index, row in enumerate(rows, 1)])


# Use a wrapped table rather than a Text widget containing Markdown/prose.
import tkinter as tk
from tkinter import ttk
from barkav_ui.theme import font as kit_font
from barkav_ui.bidi import fa_grouped_number, rtl
from ui_stage18_7 import palette_187


class ReportTable187(ttk.Frame):
    def __init__(self, parent, headers, rows):
        super().__init__(parent)
        self.headers, self.rows = list(headers), list(rows)
        self.canvas = tk.Canvas(self, highlightthickness=0, bg=palette_187()['surface'])
        vertical = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        horizontal = ttk.Scrollbar(self, orient='horizontal', command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.columnconfigure(0, weight=1); self.rowconfigure(0, weight=1)
        self.canvas.grid(row=0, column=0, sticky='nsew')
        vertical.grid(row=0, column=1, sticky='ns')
        horizontal.grid(row=1, column=0, sticky='ew')
        self.canvas.bind('<Configure>', self._draw, add='+')
        self.canvas.bind('<MouseWheel>', lambda event: self.canvas.yview_scroll(-int(event.delta / 120), 'units'))

    def _draw(self, event=None):
        self.canvas.delete('all')
        palette = palette_187()
        weights = [3 if ('شرح' in key or 'جزئیات' in key) else 1.5 if 'تاریخ' in key else 1 for key in self.headers]
        total = sum(weights) or 1
        width = max(self.canvas.winfo_width(), len(self.headers) * 95)
        widths = [width * weight / total for weight in weights]
        top = 0
        for row_number, row in enumerate([dict(zip(self.headers, self.headers)), *self.rows]):
            right, boxes = width, []
            for key, cell_width in zip(self.headers, widths):
                left = right - cell_width
                value = fa_grouped_number(row.get(key, ''))
                item = self.canvas.create_text(right - 9, top + 9, text=rtl(fa(text(value))),
                    anchor='ne', justify='right', width=max(40, cell_width - 18),
                    font=kit_font('body', widget=self, bold=row_number == 0), fill=palette['text'])
                bounds = self.canvas.bbox(item)
                boxes.append((left, right, item, (bounds[3] - bounds[1]) if bounds else 18))
                right = left
            height = max([32, *[box[3] + 18 for box in boxes]])
            for left, right, item, _ in boxes:
                cell = self.canvas.create_rectangle(left, top, right, top + height,
                    fill=palette.get('surface_alt', palette['surface']) if row_number == 0 else palette['surface'],
                    outline=palette['border_subtle'])
                self.canvas.tag_lower(cell, item)
            top += height
        self.canvas.configure(scrollregion=(0, 0, width, top))
