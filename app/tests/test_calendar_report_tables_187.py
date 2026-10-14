import json
from datetime import date
from types import SimpleNamespace
import pytest
from calendar_report_tables_187 import (REPORT_FIELDS, prepare_answer_records,
    parse_grounded_answer, counting_days, phase_parts)
from financial_calendar_stage18_7 import daily_report_rows_187


def event(day, title, identifier='A', details='', **meta):
    import jdatetime
    return SimpleNamespace(kind='DAILY_REPORT', due_date=day.isoformat(),
        due_date_shamsi=jdatetime.date.fromgregorian(date=day).strftime('%Y/%m/%d'),
        title=title, details=details, source_id=identifier, phase='اسکلت', metadata=meta)


def test_daily_inclusive_range_keeps_empty_days_and_combines_all_entries():
    first=date(2025,9,23); last=date(2025,9,25)
    rows=daily_report_rows_187([event(first,'تیغه‌چینی','A'),event(first,'وال‌پست','B')],first,last,deduplicate=False)
    assert len(rows)==3
    assert 'تیغه‌چینی' in rows[0]['شرح گزارش'] and 'وال‌پست' in rows[0]['شرح گزارش']
    assert rows[0]['_source_ids']==['A','B'] or set(rows[0]['_source_ids'])=={'A','B'}
    assert rows[0]['_source_id']==''
    assert [row['شرح گزارش'] for row in rows[1:]]==['اطلاعات ثبت نشده']*2


@pytest.mark.parametrize('structured',[False,True])
def test_weekly_groups_each_activity_once_and_retains_every_date(structured):
    first=date(2025,9,23)
    events=[event(first,'تیغه‌چینی، وال‌پست، بالاکشیدن مصالح','A',**({'row_description':'تیغه‌چینی، وال‌پست، بالاکشیدن مصالح'} if structured else {})),
        event(date(2025,9,24),'تیغه چینی','B'),event(date(2025,9,25),'وال پست','C'),
        event(date(2025,9,26),'بالاکشیدن مصالح','D')]
    rows=daily_report_rows_187(events,first,date(2025,9,29))
    assert len(rows)==3
    assert all(len(row['_dates'])==2 for row in rows)
    assert all(len(row['تاریخ'].splitlines())==2 for row in rows)
    assert all(len(row['روز هفته'].splitlines())==2 for row in rows)
    assert set().union(*(set(row['_source_ids']) for row in rows))=={'A','B','C','D'}


def test_zero_counts_and_phase_numbers_are_not_lost():
    day=date(2025,9,23)
    row=daily_report_rows_187([event(day,'کارکرد','A',main_phase='۸- اسکلت',
        sub_phase='۸.۲- تیر',report_contractor_count=0)],day,day,deduplicate=False)[0]
    assert row['شماره فاز اصلی']=='۸' and row['عنوان فاز اصلی']=='اسکلت'
    assert row['شماره فاز فرعی']=='۸.۲' and row['عنوان فاز فرعی']=='تیر'
    assert row['تعداد عوامل پیمانکار']=='0'


def test_same_day_and_record_are_not_counted_twice():
    records=prepare_answer_records([{'تاریخ':'۱۴۰۴/۰۷/۰۱','شرح':'حضور ناصر'},
        {'تاریخ':'1404/07/01','شرح':'کارکرد ناصر'}, {'تاریخ':'1404/07/03','شرح':'حضور ناصر'}])
    raw=json.dumps({'columns':['تاریخ','شرح'],'record_ids':['R1','R2','R3','R1']})
    headers,rows=parse_grounded_answer(raw,records,count_days=True)
    assert headers[0]=='ردیف' and 'تاریخ' in headers
    assert len(rows)==3 and rows[-1]['تعداد روزها']=='۲'
    assert 'حضور ناصر' in rows[0]['شرح'] and 'کارکرد ناصر' in rows[0]['شرح']


@pytest.mark.parametrize('payload', [
    {'columns':['تاریخ'],'record_ids':['R99']},
    {'columns':['تاریخ'],'record_ids':['R1'],'answer':'با توجه به درخواست کارفرما'},
    {'columns':['اطلاعات ساختگی'],'record_ids':['R1']},
])
def test_generated_values_or_unknown_sources_cannot_enter_the_answer(payload):
    records=prepare_answer_records([{'تاریخ':'1404/07/01','شرح':'حضور ناصر'}])
    with pytest.raises(RuntimeError): parse_grounded_answer(json.dumps(payload),records)


def test_empty_answer_and_total_stay_inside_the_table():
    headers,rows=parse_grounded_answer('{"columns":["تاریخ","شرح"],"record_ids":[]}',[],count_days=True)
    assert rows[-1]['تعداد روزها']=='۰' and rows[-1]['شرح']=='تعداد کل روزها'


def test_periodic_ai_cannot_drop_a_missing_day():
    records=prepare_answer_records([{'تاریخ':'1404/07/01','شرح گزارش':'کارکرد'},
        {'تاریخ':'1404/07/02','شرح گزارش':'اطلاعات ثبت نشده'}])
    with pytest.raises(RuntimeError):
        parse_grounded_answer('{"columns":["تاریخ"],"record_ids":["R1"]}',records,require_all=True)


def test_day_count_query_and_unknown_phase_stay_conservative():
    assert counting_days('ناصر چند روز در کارگاه حاضر بوده؟')
    assert counting_days('تعداد روزهای حضور ناصر')
    assert not counting_days('جمع هزینه‌های کارگاه چقدر است؟')
    assert phase_parts('نام فاز ثبت‌شدهٔ سفارشی')==('', 'نام فاز ثبت‌شدهٔ سفارشی')


def test_real_pdf_contains_progress_and_is_the_same_immutable_preview(tmp_path):
    from report_document_stage18_7 import build_report_document
    from pypdf import PdfReader
    document=build_report_document(['ردیف',*REPORT_FIELDS],[{
        'ردیف':'۱','تاریخ':'۱۴۰۴/۰۷/۰۱','شرح گزارش':'اطلاعات ثبت نشده',
    }],[],'گزارش روزانه',progress=37.5,project_name='پروژه نمونه')
    output=tmp_path/'daily.pdf'; document.save(output,'PDF')
    assert output.read_bytes()==document.pdf
    reader=PdfReader(output)
    assert len(reader.pages)==document.page_count
    assert '٪' in ''.join(page.extract_text() for page in reader.pages)



def test_response_window_is_a_wrapped_table_and_preview_uses_the_actual_pdf(monkeypatch):
    import tkinter as tk
    from ui_stage18_7 import style_ttk_187
    import financial_calendar_stage18_7 as module
    root=tk.Tk(); root.withdraw(); style_ttk_187(root)
    records=prepare_answer_records([{'تاریخ':'1404/07/01','شرح':'حضور ناصر'}])
    table=parse_grounded_answer('{"columns":["تاریخ","شرح"],"record_ids":["R1"]}',records,count_days=True)
    window=None
    try:
        window=module.ProjectAIResultDialog187(root,service=SimpleNamespace(db=None),model='مدل آزمایشی',
            text='با توجه به درخواست کارفرما متن اضافه',audience='کارفرما',start='',end='',answer_table=table)
        root.update()
        window.output._draw()
        texts=[window.output.canvas.itemcget(item,'text').lstrip('\u200f') for item in window.output.canvas.find_all()
               if window.output.canvas.type(item)=='text']
        assert 'حضور ناصر' in texts and 'تعداد کل روزها' in texts
        assert not any('با توجه به' in value for value in texts)
        captured={}
        monkeypatch.setattr(module,'show_export_preview_187',lambda *args,**kwargs:captured.update(kwargs))
        monkeypatch.setattr(module,'_project_report_overall_progress_187',lambda service:37.5)
        window._preview187()
        assert captured['include_addressee'] is True
        assert captured['headers']==table[0] and captured['rows']==table[1]
        assert captured['report_progress']==37.5
    finally:
        if window is not None: window.destroy()
        root.destroy()


def test_question_insert_and_empty_count_answer_are_rtl_and_tabular():
    import tkinter as tk
    from ui_stage18_7 import style_ttk_187
    import financial_calendar_stage18_7 as module
    root=tk.Tk(); root.withdraw(); style_ttk_187(root)
    request=result=None
    try:
        root.service=SimpleNamespace(db=None)
        root.events=[]
        request=module.ProjectAIRequestDialog187(root)
        request.question.insert('1.0','ناصر چند روز در کارگاه حاضر بوده؟')
        root.update()
        assert request.question.tag_cget('rtl','justify')=='right'
        assert request.question.tag_ranges('rtl')
        result=request._ask187()
        headers,rows=result._table_data187()
        assert 'تاریخ' in headers and rows[-1]['تعداد روزها']=='۰'
    finally:
        if result is not None: result.destroy()
        if request is not None: request.destroy()
        root.destroy()


@pytest.mark.parametrize('end',[date(2025,9,29),date(2025,10,22)])
def test_weekly_and_monthly_share_activity_grouping(end):
    first=date(2025,9,23)
    rows=daily_report_rows_187([event(first,'تیغه‌چینی','A'),event(end,'تیغه‌چینی','B')],first,end)
    assert len(rows)==1 and len(rows[0]['_dates'])==2
    assert rows[0]['شرح گزارش']=='تیغه‌چینی'


def test_shared_daily_details_are_displayed_once():
    day=date(2025,9,23)
    rows=daily_report_rows_187([event(day,'تیغه‌چینی، وال‌پست','A',details='حمل مصالح تا طبقه سوم')],day,day,deduplicate=False)
    assert rows[0]['شرح گزارش'].count('حمل مصالح تا طبقه سوم')==1


def test_ai_context_preserves_recorded_headcounts_and_separate_phases():
    from financial_calendar_stage18_7 import _project_report_context_187
    source=event(date(2025,9,23),'کارکرد','A',main_phase='۸ — اسکلت',sub_phase='۸.۲ — تیر',report_contractor_count=0)
    source.registered_date_shamsi='1404/07/02'; source.amount=0
    rows=prepare_answer_records(_project_report_context_187([source]))
    assert rows[0]['تعداد عوامل پیمانکار']==0
    assert rows[0]['شماره فاز اصلی']=='۸' and rows[0]['عنوان فاز فرعی']=='تیر'


def test_grounded_prompt_requests_only_record_selection():
    from project_report_ai_187 import build_project_prompt
    prompt=build_project_prompt(query='ناصر چند روز حاضر بوده؟',events=[{'_record_ref':'R1','شرح':'حضور ناصر'}],grounded_table=True)
    assert '"columns"' in prompt and '"record_ids"' in prompt
    assert 'پرداخت وجه' in prompt and 'هیچ مقدار' in prompt


def test_count_rejects_a_source_without_a_valid_date():
    records=prepare_answer_records([{'تاریخ':'تاریخ نامشخص','شرح':'حضور ناصر'}])
    with pytest.raises(RuntimeError,match='تاریخ معتبر'):
        parse_grounded_answer('{"columns":["تاریخ","شرح"],"record_ids":["R1"]}',records,count_days=True)


def test_request_provider_response_displays_only_the_selected_source_records(monkeypatch):
    import tkinter as tk
    from ui_stage18_7 import style_ttk_187
    import financial_calendar_stage18_7 as module
    root=tk.Tk();root.withdraw();style_ttk_187(root)
    request=None
    try:
        root.service=SimpleNamespace(db=None)
        root.events=[event(date(2025,9,23),'حضور ناصر','A'),event(date(2025,9,25),'کارکرد ناصر','B'),
                     event(date(2025,9,26),'پرداخت به ناصر','C')]
        for item in root.events:
            item.registered_date_shamsi=item.due_date_shamsi;item.amount=0
        captured={}
        def generate(prompt,**options):
            captured['prompt']=prompt
            return 'مدل آزمایشی','{"columns":["تاریخ","شرح"],"record_ids":["R1","R2"]}'
        monkeypatch.setattr(module,'generate_project_text',generate)
        monkeypatch.setattr(module.threading,'Thread',lambda target,daemon:SimpleNamespace(start=target))
        request=module.ProjectAIRequestDialog187(root)
        request.question.insert('1.0','ناصر چند روز در کارگاه حاضر بوده؟')
        request._ask187();root.update()
        windows=[child for child in request.winfo_children() if isinstance(child,module.ProjectAIResultDialog187)]
        assert len(windows)==1
        headers,rows=windows[0]._table_data187()
        assert rows[-1]['تعداد روزها']=='۲' and len(rows)==3
        assert [row['شرح'] for row in rows[:-1]]==['حضور ناصر','کارکرد ناصر']
        assert '"_record_ref": "R3"' in captured['prompt']
        assert not request._running187
    finally:
        if request is not None: request.destroy()
        root.destroy()


def test_invoice_question_uses_only_registered_values(monkeypatch):
    import tkinter as tk
    from ui_stage18_7 import style_ttk_187
    import financial_calendar_stage18_7 as module
    root=tk.Tk();root.withdraw();style_ttk_187(root)
    request=None
    try:
        root.service=SimpleNamespace(db=None)
        source=event(date(2025,9,23),'فاکتور مصالح','A')
        source.kind='INVOICE_NOTE';source.amount=2500;source.registered_date_shamsi=source.due_date_shamsi
        root.events=[source]
        def generate(prompt,**options):
            assert '"record_ids"' in prompt and not options.get('image_paths')
            return 'مدل آزمایشی','{"columns":["تاریخ","شرح","مبلغ ثبت‌شده"],"record_ids":["R1"]}'
        monkeypatch.setattr(module,'generate_project_text',generate)
        monkeypatch.setattr(module.threading,'Thread',lambda target,daemon:SimpleNamespace(start=target))
        request=module.ProjectAIRequestDialog187(root)
        request.question.insert('1.0','فاکتورهای ثبت‌شده را نشان بده')
        request._ask187();root.update()
        result=next(child for child in request.winfo_children() if isinstance(child,module.ProjectAIResultDialog187))
        headers,rows=result._table_data187()
        assert rows==[{'ردیف':'۱','تاریخ':'سه‌شنبه ۱۴۰۴/۰۷/۰۱','شرح':'فاکتور مصالح','مبلغ ثبت‌شده':'2500'}]
        assert not result.is_invoice_report
    finally:
        if request is not None:request.destroy()
        root.destroy()


def test_ai_date_filter_uses_execution_date_and_keeps_registration_date():
    from financial_calendar_stage18_7 import _project_report_context_187
    source=event(date(2026,8,25),'گزارش روزانه ۱۷ شهریور ۱۴۰۵ — حضور ناصر','A')
    source.registered_date_shamsi='1405/06/03';source.amount=0
    assert _project_report_context_187([source],'1405/06/03','1405/06/03')==[]
    rows=_project_report_context_187([source],'1405/06/17','1405/06/17')
    assert len(rows)==1 and rows[0]['تاریخ']=='1405/06/17'
    assert rows[0]['تاریخ ثبت']=='1405/06/03' and rows[0]['روز هفته']=='سه‌شنبه'
