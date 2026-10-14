"""Read-only project search, dates, provenance and financial deduplication."""
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from finance_db import FinanceDB
from dashboard_service_stage12 import DashboardServiceStage12
from budget_rich_v163 import RichBudgetService
from advanced_search187 import AdvancedSearchService187, normalized, named_period, validate_range

@pytest.fixture
def search(tmp_path,monkeypatch):
    monkeypatch.setenv('STAGE4_DB_PATH',str(tmp_path/'project.sqlite3'))
    db=FinanceDB(tmp_path/'project.sqlite3')
    service=DashboardServiceStage12(db,tmp_path)
    rich=RichBudgetService(db,tmp_path)
    return AdvancedSearchService187(service,rich)


def document(search, identity, kind, description, raw='', stamp='1405/07/01'):
    with search.db.tx() as con:
        con.execute("INSERT INTO financial_documents(document_id,document_type,event_date_shamsi,description,raw_text,status,created_at,updated_at) VALUES(?,?,?,?,?,'ACTIVE','2026-09-23','2026-09-23')",
                    (identity,kind,stamp,description,raw))


def test_normalizes_letters_digits_and_keeps_literal_words():
    assert normalized('پيمانكار ۱۲٣') == normalized('پیمانکار 123')
    assert normalized('عَلِي') == normalized('علی')
    assert normalized('هزینهٔ ساخت') != normalized('درآمد')


@pytest.mark.parametrize('query,start,end',[
    ('هفته اول مهرماه 1405','1405/07/01','1405/07/07'),
    ('هفته ۲ مهر ۱۴۰۵','1405/07/08','1405/07/14'),
    ('ماه مهر 1405','1405/07/01','1405/07/30'),
    ('اسفند 1404','1404/12/01','1404/12/29'),
])
def test_named_shamsi_periods(query,start,end):
    assert named_period(query)==(start,end)


def test_invalid_date_and_reversed_range_are_rejected():
    with pytest.raises(ValueError):validate_range('1405/13/01','')
    with pytest.raises(ValueError):validate_range('1405/07/10','1405/07/01')
    assert validate_range('۱۴۰۵/۷/۱','')==('1405/07/01','')


def test_financial_totals_count_expense_not_its_payment(search):
    expense=search.db.create_expense(event_date='2026-09-23',shamsi_date='1405/07/01',final_amount=1000,
        description='سيمان خرید',construction_stage='اسکلت')
    search.db.add_payment(expense_id=expense,payment_date='2026-09-23',amount=1000,method='CASH')
    before=search.db.snapshot()
    rows=search.search('سیمان')
    assert len(rows)==1
    assert search.totals(rows)[0]['مبلغ (تومان)']==1000
    assert search.db.snapshot()==before
    assert not search.search('سیمان',scope='تسهیلات')


def test_date_basis_matches_execution_or_registration_and_one_sided_range(search):
    search.db.create_expense(event_date='2026-09-23',shamsi_date='1405/07/01',final_amount=100,
        description='کارگر احمد',construction_stage='اسکلت')
    with search.db.tx() as con:con.execute("UPDATE expenses SET created_at='2026-10-04'")
    assert len(search.search('احمد',start='1405/07/12',end='1405/07/12',date_basis='تاریخ ثبت'))==1
    assert not search.search('احمد',start='1405/07/12',date_basis='تاریخ اجرا')
    assert len(search.search('احمد',start='1405/07/12',date_basis='همه'))==1


def test_documents_search_daily_text_and_exclude_deleted(search):
    document(search,'D1','DAILY_REPORT','گزارش روزانه','ناصر — والپست')
    document(search,'D2','NOTE','نکته راه پله','حفاظ الزامی')
    document(search,'D3','DAILY_REPORT','گزارش','ناصر')
    with search.db.tx() as con:con.execute("UPDATE financial_documents SET status='DELETED' WHERE document_id='D3'")
    assert [row['_id'] for row in search.search('ناصر',scope='تقویم')]==['financial_documents:D1']


def test_ai_selects_only_registered_records_and_counts_unique_days(search):
    document(search,'D1','DAILY_REPORT','ناصر در کارگاه')
    document(search,'D2','DAILY_REPORT','ناصر در کارگاه')
    seen={}
    def generator(prompt,**kwargs):
        seen.update(kwargs)
        records=json.loads(prompt.split('رکوردها:\n',1)[1])
        ids=[row['_id'] for row in records if row['_table']=='financial_documents']
        value=json.dumps({'record_ids':ids})
        kwargs['validator'](value)
        return 'test-model',value
    model,(headers,rows)=search.ask('ناصر چند روز کار کرده؟',scope='تقویم',generator=generator,settings={})
    assert model=='test-model' and seen['section']=='management'
    assert rows[-1]['تعداد روز']==1
    assert len(rows)==3
    assert all('مرجع' in row for row in rows[:-1])


def test_unknown_ai_record_is_rejected(search):
    document(search,'D1','DAILY_REPORT','ناصر در کارگاه')
    with pytest.raises(ValueError):
        search.ask('ناصر',scope='تقویم',generator=lambda *a,**kw:('fake','{"record_ids":["invented"]}'),settings={})


def test_invoice_uses_only_nonfinancial_invoice_and_95_percent_threshold(search):
    document(search,'I1','INVOICE_NOTE','فاکتور سیمان')
    document(search,'D1','DOCUMENT','قرارداد')
    seen=[]
    def generator(prompt,**kwargs):
        seen.append(prompt)
        row={key:{'value':value,'confidence':confidence} for key,value,confidence in (
            ('item','سیمان',.99),('weight','20 تن',.94),('date','1405/07/01',.99),
            ('vendor','فروشنده آزمون',.99),('amount','1000',.99))}
        raw=json.dumps({'relevant':True,'invoices':[row]})
        kwargs['validator'](raw)
        return 'test-model',raw
    _,(headers,rows)=search.ask('فاکتورهای سیمان',generator=generator,settings={})
    assert len(seen)==1 and 'قرارداد' not in seen[0]
    assert rows[0]['وزن']=='خوانده نشد'
    assert rows[0]['مرجع']=='financial_documents:I1'
    assert rows[-1]['مبلغ (تومان)']==1000


def test_private_runtime_fields_are_not_sent_to_model(search):
    document(search,'D1','NOTE','ایمنی')
    profile=Path(search.db.db_path).parent/'project_profile_v18.json'
    profile.write_text(json.dumps({'name':'پروژه','api_key':'hidden-fixture','password':'private-fixture'}))
    def generator(prompt,**kwargs):
        assert 'hidden-fixture' not in prompt and 'private-fixture' not in prompt
        return 'fake','{"record_ids":[]}'
    _,(_,rows)=search.ask('ایمنی',generator=generator,settings={})
    assert rows[0]['شرح']=='در اطلاعات ثبت‌شده یافت نشد'


def test_project_contract_store_isolated_from_global_environment(search,tmp_path,monkeypatch):
    local=Path(search.db.db_path).parent
    (local/'contractor_contracts_18_7.json').write_text(json.dumps({'contracts':[
        {'contract_id':'C1','title':'اسکلت','contractor_name':'ناصر','total_amount':1000,'payments':[{'amount':200}]}]}))
    monkeypatch.setenv('STAGE4_DB_PATH',str(tmp_path/'another'/'foreign.sqlite3'))
    rows=search.search('ناصر',scope='پیمانکاران')
    assert len(rows)==3
    assert next(row for row in rows if 'مانده قرارداد' in row['شرح'])['مبلغ (تومان)']==800


def test_all_area_definitions_and_partial_phase_actual_forecast(search,monkeypatch):
    search.service.budget.save_settings(gross_area=200,saleable_area=100)
    rows=[{'phase_no':1,'qty_estimate':1,'qty_forecast':1,'estimate_rate':5000,'forecast_rate':6000,'total_actual':5500},
          {'phase_no':8,'qty_estimate':1,'qty_forecast':1,'estimate_rate':10000,'forecast_rate':20000,'total_actual':12000}]
    monkeypatch.setattr(search.rich,'all_phase_items',lambda:rows)
    monkeypatch.setattr(search.rich,'get_phase_progress',lambda:{8:{'physical_progress':50}})
    records=search.metric_records()
    assert len(records)==12
    def value(title):return next(row['مبلغ (تومان)'] for row in records if row['شرح']==title)
    assert value('هزینه تمام‌شده هر مترمربع مفید — برآورد اولیه')==160
    assert value('هزینه ساخت هر مترمربع غیر مفید — برآورد بروز')==110
    assert value('هزینه تمام‌شده هر مترمربع مفید — برآورد واقعی')==297
    assert rows[1]['forecast_rate']==20000


def test_partial_payment_dates_match_without_double_counting(search):
    expense=search.db.create_expense(event_date='2026-09-23',shamsi_date='1405/07/01',final_amount=1000,
        description='سیمان',construction_stage='اسکلت')
    search.db.add_payment(expense_id=expense,payment_date='2026-09-24',amount=400,method='CASH')
    search.db.add_payment(expense_id=expense,payment_date='2026-09-25',amount=600,method='CASH')
    for day,amount in (('1405/07/02',400),('1405/07/03',600)):
        rows=search.search('سیمان',start=day,end=day,date_basis='تاریخ پرداخت')
        assert len(rows)==1 and rows[0]['تاریخ']==day
        assert search.totals(rows)[0]['مبلغ (تومان)']==amount


def test_statement_debt_uses_performed_work_not_remaining_contract(search):
    directory=Path(search.db.db_path).parent
    (directory/'contractor_contracts_18_7.json').write_text(json.dumps({'contracts':[
        {'contract_id':'C1','family_name':'ناصر','total_amount':1000,'payments':[{'amount':200}]}]}))
    (directory/'contractor_statements_18_7.json').write_text(json.dumps({'statements':[
        {'statement_id':'S1','contract_id':'C1','statement_date':'۱۴۰۵/۰۷/۰۱','rows':[{'line_total':300}]},
        {'statement_id':'S2','contract_id':'C1','statement_date':'۱۴۰۵/۰۷/۰۲','rows':[{'line_total':400}],'penalty_amount':50}]}))
    rows=search.search('ناصر',scope='پیمانکاران')
    debt=next(row for row in rows if row['_table']=='contract_statement_balance')
    assert debt['مبلغ (تومان)']==450
    assert debt['جزئیات']['مراجع صورت‌وضعیت']==['S1','S2']


def test_forecast_stays_unknown_when_executed_phase_progress_is_missing(search,monkeypatch):
    search.service.budget.save_settings(gross_area=200,saleable_area=100)
    monkeypatch.setattr(search.rich,'all_phase_items',lambda:[{'phase_no':8,'qty_estimate':1,'forecast_rate':20000,'total_actual':12000}])
    monkeypatch.setattr(search.rich,'get_phase_progress',lambda:{})
    rows=[row for row in search.metric_records() if row['شرح'].endswith('برآورد واقعی')]
    assert rows and all(row['مبلغ (تومان)']=='' and row['وضعیت']=='پیشرفت اجرایی ثبت نشده' for row in rows)


@pytest.mark.parametrize('confidence,amount',[('NaN','1000'),(1.1,'1000'),(.99,'1000 یا 2000')])
def test_invoice_invalid_confidence_and_ambiguous_amount_stay_unread(confidence,amount):
    from project_report_ai_187 import parse_invoice_response
    raw=json.dumps({'invoices':[{'amount':{'value':amount,'confidence':confidence}}]})
    rows,total,unread=parse_invoice_response(raw)
    assert rows[0]['مبلغ (تومان)']=='خوانده نشد' and total==0 and unread==1


def test_invoice_pdf_pages_are_read_only_and_temporary(search,tmp_path):
    from reportlab.pdfgen import canvas
    from advanced_search187 import invoice_images
    path=tmp_path/'invoice.pdf';pdf=canvas.Canvas(str(path));pdf.drawString(30,30,'invoice');pdf.showPage();pdf.save()
    original=path.read_bytes()
    with invoice_images([path]) as images:
        assert len(images)==1 and Path(images[0]).is_file()
        temporary=Path(images[0])
    assert not temporary.exists() and path.read_bytes()==original


def test_large_ai_context_batches_cover_every_source_once(search,monkeypatch):
    import advanced_search187 as module
    for number in range(8):document(search,f'D{number}','DAILY_REPORT','حضور ناصر در کارگاه')
    monkeypatch.setattr(module,'AI_CONTEXT_CHARS',1600)
    seen=[]
    def generator(prompt,**kwargs):
        batch=json.loads(prompt.split('رکوردها:\n',1)[1]);ids=[row['_id'] for row in batch]
        seen.extend(ids);raw=json.dumps({'record_ids':ids});kwargs['validator'](raw)
        return 'fake',raw
    _,(_,rows)=search.ask('ناصر چند روز کار کرده؟',scope='تقویم',generator=generator,settings={})
    assert len(seen)==len(set(seen))==8
    assert len(rows)==9 and rows[-1]['تعداد روز']==1


@pytest.mark.parametrize('query,kind',[
    ('گزارش هفتگی هفته اول مهرماه ۱۴۰۵','هفتگی'),
    ('گزارش روزانه پروژه','روزانه'),
    ('گزارش ماهانه هزینه سیمان',''),
    ('گزارش روزانه حضور ناصر',''),
])
def test_period_request_routing_preserves_topical_questions(query,kind):
    from advanced_search187 import period_request
    assert period_request(query)==kind


def test_construction_summary_excludes_land_and_adds_management_once(search):
    search.db.create_expense(event_date='2026-09-23',shamsi_date='1405/07/01',final_amount=1000,
        description='اسکلت',construction_stage='08 — اسکلت')
    search.db.create_expense(event_date='2026-09-23',shamsi_date='1405/07/01',final_amount=500,
        description='خرید زمین',construction_stage='01 — خرید زمین')
    rows=[row for row in search.records() if row['_table']=='construction_summary']
    amounts={row['شرح']:row['مبلغ (تومان)'] for row in rows}
    assert amounts['هزینه ساخت انجام‌شده با حقوق مدیر']==1100
    assert amounts['هزینه خرید زمین']==500
    assert amounts['هزینه تمام‌شده انجام‌شده']==1600


def test_profile_answer_displays_registered_field_value_without_secrets(search):
    path=Path(search.db.db_path).parent/'project_profile_v18.json'
    path.write_text(json.dumps({'team':{'employer':{'name':'نام آزمون','phone':'09120000000'}},'api_key':'never-display'}))
    fields=search.search('کارفرما',scope='داشبورد')
    assert any('نام آزمون' in row['شرح'] for row in fields if row['_table']=='profile_fields')
    assert 'never-display' not in json.dumps(fields,ensure_ascii=False)
    def generator(prompt,**kwargs):
        records=json.loads(prompt.split('رکوردها:\n',1)[1])
        identity=next(row['_id'] for row in records if row['_table']=='profile_fields' and 'نام آزمون' in row['شرح'])
        return 'fake',json.dumps({'record_ids':[identity]})
    _,(_,rows)=search.ask('نام کارفرما چیست؟',scope='داشبورد',generator=generator,settings={})
    assert 'نام آزمون' in rows[0]['شرح']


def test_phase_summary_preserves_raw_budget_and_forecasts_remaining_work(search,monkeypatch):
    source=[{'phase_no':8,'qty_estimate':1,'forecast_rate':20000,'estimate_rate':10000,'total_actual':12000}]
    monkeypatch.setattr(search.rich,'all_phase_items',lambda:source)
    monkeypatch.setattr(search.rich,'get_phase_progress',lambda:{8:{'physical_progress':50}})
    rows=search.phase_records()
    values={row['جزئیات']['مبنای محاسبه']:row['مبلغ (تومان)'] for row in rows}
    assert values=={'برآورد اولیه':10000,'برآورد بروز':20000,'هزینه انجام‌شده':12000,'برآورد واقعی تا پایان':22000}
    assert source[0]['forecast_rate']==20000
