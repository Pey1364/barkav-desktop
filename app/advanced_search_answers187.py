"""Evaluate an AI-selected answer layout against registered records only.

The model chooses fields and operations, never cell values, Python or SQL.
The same declarative operations serve new questions across project sections.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation
import json
import re
import jdatetime

MISSING = 'اطلاعات ثبت نشده'
AGGREGATES = {'count', 'distinct_count', 'sum', 'mean', 'min', 'max', 'join'}
ARITHMETIC = {'add', 'subtract', 'multiply', 'divide', 'percent', 'duration_days'}
OPS = AGGREGATES | ARITHMETIC | {'field', 'constant'}


def paths(value, prefix=''):
    """Describe fields without sending secret values or inventing a schema."""
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).startswith('__'):
                continue
            path = f'{prefix}.{key}' if prefix else str(key)
            yield from paths(child, path)
    else:
        yield prefix


def field(record, path):
    value = record
    while path:
        if not isinstance(value, dict):
            return None
        if path in value:
            return value[path]
        key, separator, path = path.partition('.')
        if key not in value:
            return None
        value = value[key]
        if not separator:return value
    return value


def catalog(records):
    sources = defaultdict(set)
    for record in records:
        sources[record['_table']].update(paths(record))
    return {table: sorted(fields) for table, fields in sorted(sources.items())}


def validate_view(view, records):
    if not isinstance(view, dict):
        raise ValueError('ساختار جدول پاسخ معتبر نیست.')
    schema = catalog(records)
    known = set().union(*schema.values()) if schema else set()
    def expression(expr, depth=0):
        if depth > 8 or not isinstance(expr, dict) or expr.get('op') not in OPS:
            raise ValueError('محاسبهٔ پاسخ معتبر نیست.')
        op = expr['op']
        if set(expr) - {'op', 'path', 'table', 'args', 'value', 'where'}:
            raise ValueError('محاسبه دارای فیلد ناشناخته است.')
        if expr.get('table') is not None and expr['table'] not in schema:
            raise ValueError('منبع محاسبه در پروژه وجود ندارد.')
        conditions = expr.get('where', [])
        if not isinstance(conditions, list) or len(conditions) > 6:
            raise ValueError('شرط محاسبه معتبر نیست.')
        for condition in conditions:
            if not isinstance(condition, dict) or set(condition) != {'path','op','value'} or condition['path'] not in known:
                raise ValueError('فیلتر محاسبه به فیلد ثبت‌شده ارجاع نمی‌دهد.')
            if condition['op'] not in {'eq','contains','gt','gte','lt','lte'} or not isinstance(condition['value'], (str,int,float,bool)):
                raise ValueError('شرط محاسبه معتبر نیست.')
        if op in (AGGREGATES - {'count'}) | {'field'}:
            path = expr.get('path')
            if not isinstance(path, str) or path not in known:
                raise ValueError('فیلد پاسخ در اطلاعات ثبت‌شده وجود ندارد.')
            if expr.get('table') and path not in schema[expr['table']]:
                raise ValueError('فیلد به منبع انتخاب‌شده تعلق ندارد.')
        if op == 'constant' and (type(expr.get('value')) is not int or expr['value'] not in {0, 1, 100}):
            raise ValueError('عدد مالی باید از اطلاعات ثبت‌شده خوانده شود.')
        if op in ARITHMETIC:
            args = expr.get('args')
            if not isinstance(args, list) or not 2 <= len(args) <= 8:
                raise ValueError('عملوندهای محاسبه معتبر نیستند.')
            if op in {'divide', 'percent', 'duration_days', 'subtract'} and len(args) != 2:
                raise ValueError('این محاسبه دو عملوند نیاز دارد.')
            for arg in args:
                expression(arg, depth + 1)
    if set(view) - {'mode', 'group_by', 'columns', 'footer'}:
        raise ValueError('ساختار جدول پاسخ دارای گزینهٔ ناشناخته است.')
    if view.get('mode', 'records') not in {'records', 'aggregate'}:
        raise ValueError('نوع جدول پاسخ معتبر نیست.')
    groups = view.get('group_by', [])
    if not isinstance(groups, list) or len(groups) > 3 or any(not isinstance(p, str) or p not in known for p in groups):
        raise ValueError('گروه‌بندی پاسخ معتبر نیست.')
    columns = view.get('columns')
    if not isinstance(columns, list) or not 1 <= len(columns) <= 12:
        raise ValueError('ستون‌های پاسخ معتبر نیستند.')
    titles = set()
    for column in columns:
        if not isinstance(column, dict) or set(column) != {'title', 'expr'}:
            raise ValueError('ستون پاسخ باید عنوان و محاسبه داشته باشد.')
        title = column['title']
        if not isinstance(title, str) or not title.strip() or len(title) > 80 or title in titles or title in {'ردیف', 'مرجع'}:
            raise ValueError('عنوان ستون پاسخ معتبر نیست.')
        titles.add(title)
        expression(column['expr'])
    footer = view.get('footer', [])
    if not isinstance(footer, list) or len(footer) > 12:
        raise ValueError('جمع‌بندی پاسخ معتبر نیست.')
    for item in footer:
        if not isinstance(item, dict) or set(item) != {'title', 'column', 'expr'}:
            raise ValueError('ردیف جمع‌بندی معتبر نیست.')
        if not isinstance(item['title'], str) or not item['title'].strip() or len(item['title']) > 100 or item['column'] not in titles - {'شرح', 'تاریخ'}:
            raise ValueError('ستون جمع‌بندی معتبر نیست.')
        expression(item['expr'])
    return view


def numeric(value):
    if value is None or value == '' or isinstance(value, bool):
        return None
    raw = str(value).translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789'))
    raw = raw.replace(',', '').replace('٬', '').replace(' ', '')
    if not re.fullmatch(r'[+-]?\d+(?:\.\d+)?', raw):
        return None
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def evaluate(expr, records):
    selected = [r for r in records if not expr.get('table') or r['_table'] == expr['table']]
    def matches(record, condition):
        value = field(record, condition['path'])
        expected = condition['value']
        if value is None:
            return False
        if condition['op'] in {'eq','contains'}:
            from advanced_search187 import normalized
            return normalized(expected) == normalized(value) if condition['op']=='eq' else normalized(expected) in normalized(value)
        left, right = numeric(value), numeric(expected)
        if left is None or right is None:
            return False
        return {'gt':left>right,'gte':left>=right,'lt':left<right,'lte':left<=right}[condition['op']]
    selected = [r for r in selected if all(matches(r,c) for c in expr.get('where', []))]
    selected = list({r['_id']: r for r in selected}.values())
    op = expr['op']
    if op == 'constant':
        return Decimal(expr['value'])
    if op == 'count':
        return len(selected)
    if op in ARITHMETIC:
        values = [evaluate(arg, selected) for arg in expr['args']]
        if any(value is None for value in values):
            return None
        if op == 'duration_days':
            try:
                dates = [jdatetime.date(*map(int, str(value).split('/'))).togregorian() for value in values]
                return (dates[1] - dates[0]).days + 1 if dates[1] >= dates[0] else None
            except (ValueError, TypeError):
                return None
        values = [numeric(value) for value in values]
        if any(value is None for value in values):
            return None
        if op == 'add':
            return sum(values)
        if op == 'subtract':
            return values[0] - values[1]
        if op == 'multiply':
            product = Decimal(1)
            for value in values:
                product *= value
            return product
        return None if values[1] == 0 else values[0] / values[1] * (100 if op == 'percent' else 1)
    values = [field(record, expr['path']) for record in selected]
    present = [value for value in values if value is not None and value != '']
    if op == 'distinct_count':
        return len({json.dumps(value, ensure_ascii=False, sort_keys=True) for value in present})
    if op == 'join':
        return '\n'.join(dict.fromkeys(str(value) for value in present)) or None
    if op == 'field':
        unique = list(dict.fromkeys(json.dumps(value, ensure_ascii=False, sort_keys=True) for value in present))
        return present[0] if len(unique) == 1 else None
    if op in {'min', 'max'} and present and all(re.fullmatch(r'\d{4}/\d{2}/\d{2}', str(value)) for value in present):
        return (min if op == 'min' else max)(present)
    numbers = [numeric(value) for value in values]
    # Missing/ambiguous financial values never silently become zero.
    if not numbers or any(value is None for value in numbers):
        return None
    if op in {'sum', 'mean'}:
        # A model must not add liabilities, cash and mirrors as one amount.
        monetary = any(token in expr['path'].lower() for token in ('amount','paid','balance','fee','rate','مبلغ','هزینه','واریزی','مانده','دریافتی'))
        kinds = {(r['_table'], r.get('_bucket', '')) for r in selected}
        if monetary and len(kinds) > 1:
            raise ValueError('جمع منابع متفاوت به یک مبلغ مجاز نیست؛ مبنای محاسبه را جدا کنید.')
        if monetary and any(r['_table'] in {'pending_items', 'financial_messages', 'telegram_messages'} for r in selected):
            raise ValueError('جمع مالی باید بر اساس رکوردهای نهایی حسابداری باشد.')
        if monetary and len(selected)>1 and selected[0]['_table'] in {'manager_summary','manager_period','construction_summary','sale_summary','contract_summary','metrics'}:
            raise ValueError('شاخص‌های مالی با مبناهای متفاوت قابل جمع نیستند؛ یک شاخص مشخص را انتخاب کنید.')
        if monetary and len({field(r,'جزئیات.مبنای محاسبه') for r in selected if r['_table']=='phase_summary'})>1:
            raise ValueError('مبناهای مختلف برآورد قابل جمع نیستند.')
        total = sum(numbers)
        return total if op == 'sum' else total / len(numbers)
    return (min if op == 'min' else max)(numbers)


def display(value):
    if value is None:
        return MISSING
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral() else float(value.quantize(Decimal('0.01')))
    if isinstance(value, bool):
        return 'بله' if value else 'خیر'
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


def answer_table(view, records, *, schema_records=None):
    validate_view(view, records if schema_records is None else schema_records)
    headers = list(dict.fromkeys(['ردیف', 'تاریخ', 'شرح', *[c['title'] for c in view['columns']], 'مرجع']))
    groups = defaultdict(list)
    if view.get('group_by'):
        for record in records:
            key = tuple(json.dumps(field(record, p), ensure_ascii=False, sort_keys=True) for p in view['group_by'])
            groups[key].append(record)
    elif view.get('mode') == 'aggregate':
        groups[()] = records
    else:
        for record in records:
            groups[(record['_id'],)] = [record]
    rows = []
    for group in groups.values():
        row = {'ردیف': len(rows) + 1, 'تاریخ': '\n'.join(sorted({r['تاریخ'] for r in group if r.get('تاریخ')})),
               'شرح': '\n'.join(dict.fromkeys(str(r.get('شرح', '')) for r in group)),
               'مرجع': '\n'.join(r['_id'] for r in group)}
        for column in view['columns']:
            row[column['title']] = display(evaluate(column['expr'], group))
            if any(word in column['title'] for word in ('تاریخ','سررسید')):
                from advanced_search187 import jalali
                value=row[column['title']]
                if isinstance(value,str) and re.fullmatch(r'\d{4}[/.-]\d{1,2}[/.-]\d{1,2}',value):
                    row[column['title']]=jalali(value) or MISSING
        row['__document_paths_187'] = list(dict.fromkeys(p for r in group for p in r.get('__document_paths_187', [])))
        rows.append(row)
    for item in view.get('footer', []):
        rows.append({'ردیف': 'جمع', 'شرح': item['title'], item['column']: display(evaluate(item['expr'], records))})
    return headers, rows


VIEW_INSTRUCTIONS = '''
برای پاسخ به سؤال جدید، فیلدها و عملیات لازم را در view انتخاب کن؛ هیچ مقدار سلولی یا عدد مالی تولید نکن.
view: {"mode":"records یا aggregate","group_by":[],"columns":[{"title":"عنوان فارسی","expr":{"op":"field","path":"مسیر فیلد"}}],"footer":[]}.
عملیات: field و join برای مقدار ثبت‌شده؛ count برای تعداد رکورد؛ distinct_count برای تعداد مقدار یکتا؛ sum، mean، min، max با path و در صورت لزوم table.
هر عبارت می‌تواند where شامل [{"path":"مسیر فیلد","op":"eq یا contains یا gt یا gte یا lt یا lte","value":"شرط مورد پرسش"}] داشته باشد؛ مثلاً برای تفکیک دو مبنای برآورد یا فقط پیام‌های دارای هشدار. شرط، مقدار پاسخ نیست.
add، subtract، multiply، divide، percent، duration_days دارای args از همین عبارت‌ها هستند. duration_days اختلاف تاریخ ابتدا و انتها به‌شکل شمسی با احتساب روز شروع است.
constant فقط برای 0، 1، 100 مجاز است. عدد، فیلد یا مرجع را حدس نزن. برای پیشرفت/مانده از فیلدهای محاسبه‌شدهٔ برنامه استفاده کن.
mode=records برای فهرست؛ aggregate برای یک نتیجهٔ محاسباتی یا group_by برای جمع/شمارش هر تاریخ یا گروه.
footer: [{"title":"جمع یا تعداد مورد درخواست","column":"عنوان ستون عددی موجود","expr":{"op":"count","table":"نام منبع"}}].
برای هر سؤال شمارشی/مالی، جزئیات با تاریخ و مرجع و جمع/تعداد در footer ارائه شود. برای سؤال متنی، فیلد دقیق پاسخ در ستون فارسی قرار گیرد؛ مقدمه یا توضیح عمومی ننویس.
در sum و mean منابع مختلف و نسخه‌های تکراری یک رخداد را مخلوط نکن؛ منبع table را مشخص کن. چک تضمینی هزینه یا پرداخت نیست. چک صادرشده نقد پرداخت‌شده نیست.
برای مانده پیمانکار، contract_statement_balance با تفکیک کارکرد، پرداخت قطعی، چک باز و مانده استفاده شود. قیمت اینترنتی، نرخ تاریخی یا دادهٔ ثبت‌نشده را نساز.
برای تعداد و تاریخ پرداخت‌های هزینه از payments استفاده کن؛ تعداد expenses تعداد هزینه‌ها است و تعداد پرداخت‌ها نیست. پرداخت و هزینه را با هم جمع نکن.
اطلاعات ناقص یعنی «اطلاعات ثبت نشده»، نه صفر. view فقط مسیر فیلدها را از فهرست منابع موجود زیر انتخاب کند:
'''
