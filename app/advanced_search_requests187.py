"""Request modes, reusable questions and safe local evidence lookup."""
from __future__ import annotations
import json
import re

REQUEST_TYPES = ('جستجوی پیشرفته', 'گزارش‌های مرحله‌ای', 'درخواست از هوش مصنوعی')

# The workbook is an example catalogue, never the limit of supported questions.
FAQ = (
    ('پیام‌ها', 'پیام‌های خوانده‌نشده را فهرست کن.'),
    ('پیام‌ها', 'پیام‌های دارای هشدار را فهرست کن.'),
    ('تقویم', 'گزارش روزانه پروژه را با یک ردیف برای هر روز ارائه کن.'),
    ('تقویم', 'گزارش هفتگی پروژه را ارائه کن.'),
    ('تقویم', 'گزارش ماهانه پروژه را ارائه کن.'),
    ('تقویم', 'تعداد کارکرد پیمانکاران و کارگران را در بازهٔ انتخابی گزارش کن.'),
    ('تقویم', 'تاریخ شروع عملیات اجرایی پروژه چه زمانی است؟'),
    ('تقویم', 'مدت تکمیل عملیات اجرایی ثبت‌شده چقدر است؟'),
    ('تقویم', 'تعداد و تاریخ روزهای تعطیلی کارگاه را گزارش کن.'),
    ('تقویم', 'تاریخ‌های بازدید ناظران از پروژه را فهرست کن.'),
    ('پیام‌ها', 'موارد ثبت‌شده در یادداشت‌ها را با تاریخ و موضوع فهرست کن.'),
    ('پیام‌ها', 'موارد ثبت‌شده در اطلاع‌رسانی‌ها را با تاریخ و موضوع فهرست کن.'),
    ('سایر', 'فاکتورهای ثبت‌شده در اسناد پروژه را نمایش بده.'),
    ('تقویم', 'در بازهٔ انتخابی چه نیروهایی در کارگاه حضور داشتند؟'),
    ('تقویم', 'در بازهٔ انتخابی چه عملیاتی در کارگاه انجام شده است؟'),
    ('داشبورد', 'مدل‌های هوش مصنوعی در دسترس و مدل انتخاب‌شده کدام‌اند؟'),
    ('داشبورد', 'نرخ دلار و طلا با تاریخ ثبت‌شده در برنامه چقدر است؟'),
    ('داشبورد', 'فونت‌ها و تم فعال برنامه کدام‌اند؟'),
    ('داشبورد', 'متراژ واحد شمالی طبقه ۴ چند مترمربع است؟'),
    ('داشبورد', 'شماره تلفن ناظر برق چیست؟'),
    ('داشبورد', 'کد پستی پروژه چیست؟'),
    ('داشبورد', 'در طبقه همکف چند انباری داریم و متراژ هرکدام چقدر است؟'),
    ('داشبورد', 'متراژ مفید پروژه چقدر است؟'),
    ('حساب مدیر', 'بیلان و مانده حساب مدیر پروژه چقدر است؟'),
    ('تراکنش‌ها', 'یک ماه آینده چند چک داریم، با چه مبالغی و بابت چه مواردی؟'),
    ('درآمد', 'هفته آینده چند قسط فروش داریم و مبلغ و مانده هر قسط چقدر است؟'),
    ('تسهیلات', 'هفته آینده چند قسط تسهیلات داریم و مبلغ هر قسط چقدر است؟'),
    ('مدیریت پروژه', 'فاز ۰۵ چند درصد پیشرفت داشته است؟'),
    ('مدیریت پروژه', 'هر فاز اجرایی چند روز طول کشیده است؟'),
    ('مدیریت پروژه', 'در هر فاز چقدر هزینه شده است؟'),
    ('مدیریت پروژه', 'هزینه واقعی تا امروز را با برآورد اولیه و به‌روز هر فاز مقایسه کن.'),
    ('تراکنش‌ها', 'هزینه‌های ثبت‌شده و پرداخت‌های قطعی هر مورد را گزارش کن.'),
    ('تسهیلات', 'اقساط باقی‌مانده هر تسهیلات با تاریخ و مبلغ چقدر است؟'),
    ('درآمد', 'تاریخ و مبلغ واریزی شرکا را فهرست کن.'),
    ('پیمانکاران', 'طلب، کارکرد و دریافتی هر پیمانکار با احتساب چک‌های باز چقدر است؟'),
    ('درآمد', 'مبلغ فروش، واریزی و مانده طلب هر واحد چقدر است؟'),
    ('مدیریت پروژه', 'هزینه ساخت هر مترمربع بر اساس برآورد اولیه، به‌روز و واقعی تا پایان چقدر است؟'),
    ('ثبت دیتا', 'اطلاعات ثبت‌شده و موارد در انتظار بررسی را فهرست کن.'),
    ('سایر', 'اطلاعات موجود در اسناد پروژه را با تاریخ و مرجع فهرست کن.'),
)


def questions_for(scope):
    return [question for section, question in FAQ if scope == 'همه' or section == scope]


def parse_response(raw):
    """Accept a JSON object in fences or prose without evaluating model text."""
    if isinstance(raw, dict):return raw
    raw = str(raw).strip()
    decoder = json.JSONDecoder()
    for match in re.finditer(r'\{', raw):
        try:
            value, _ = decoder.raw_decode(raw[match.start():])
        except ValueError:
            continue
        if isinstance(value, dict) and 'record_ids' in value:return value
    raise ValueError('پاسخ قابل تطبیق با اطلاعات ثبت‌شده نبود.')


def context_parts(record, limit):
    """Split large leaf text, preserving every character and source identity."""
    raw = json.dumps(record, ensure_ascii=False, default=str)
    if len(raw) <= limit:return [record]
    leaves = []
    def visit(value, path=''):
        if isinstance(value, dict):
            for key, child in value.items():visit(child, f'{path}.{key}' if path else str(key))
        elif isinstance(value, list):
            for index, child in enumerate(value):visit(child, f'{path}[{index}]')
        else:
            value = json.dumps(value, ensure_ascii=False, default=str)
            for index in range(0, len(value), max(100, limit // 2)):
                leaves.append({'field':path,'offset':index,'text':value[index:index + max(100, limit // 2)]})
    visit(record)
    return [{'_id':record['_id'],'_table':record['_table'],'تاریخ':record.get('تاریخ',''),
             'بخش':record.get('بخش',''),'part':index,'parts':len(leaves),'content':leaf}
            for index,leaf in enumerate(leaves,1)]


def local_matches(query, records):
    """A labelled local lookup when AI is unavailable, never a fabricated answer."""
    from advanced_search187 import normalized
    words = re.findall(r'[\w]+', normalized(query))
    generic = set('در از تا و را رو برای با به چه چقدر چند چیست کدام گزارش کن بده نمایش فهرست تعداد مبلغ هزینه ثبت شده شده‌اند پروژه اطلاعات مورد سوال سوالات تاریخ عملیات درخواست حساب هر یک آن این های ها است هست بدهد ساخت پرداخت مانده'.split())
    tokens = [word for word in words if word not in generic and len(word) > 1 and not word.isdigit()]
    if not tokens:return records
    return [row for row in records if any(token in normalized(json.dumps(row,ensure_ascii=False,default=str)) for token in tokens)]
