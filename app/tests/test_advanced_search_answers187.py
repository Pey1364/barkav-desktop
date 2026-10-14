"""New questions must compute from evidence, including cash/cheque distinctions."""
import json
from pathlib import Path

import jdatetime
import pytest

from test_advanced_search187 import search, document
from advanced_search187 import requested_period
from advanced_search_answers187 import MISSING


def expression(op, path=None, **kwargs):
    return {'op':op, **({'path':path} if path else {}), **kwargs}


def generator_for(view, tables):
    def generate(prompt, **kwargs):
        batch=json.loads(prompt.split('رکوردها:\n',1)[1])
        raw=json.dumps({'record_ids':[r['_id'] for r in batch if r['_table'] in tables], 'view':view},ensure_ascii=False)
        kwargs['validator'](raw)
        return 'test-model',raw
    return generate


def expense(search, title, amount, day='01'):
    return search.db.create_expense(event_date=f'2026-09-{22+int(day):02}',shamsi_date=f'1405/07/{day}',
        final_amount=amount,description=title,construction_stage='08 — اسکلت')


def test_new_question_groups_costs_then_computes_difference_without_model_numbers(search):
    expense(search,'سیمان',1200)
    expense(search,'ماسه',500)
    expense(search,'سیمان',900,'02')
    before=search.db.snapshot()
    total=expression('sum','_amount',table='expenses')
    difference=expression('subtract',args=[
        expression('sum','_amount',table='expenses',where=[{'path':'شرح','op':'contains','value':'سیمان'}]),
        expression('sum','_amount',table='expenses',where=[{'path':'شرح','op':'contains','value':'ماسه'}]),
    ])
    view={'mode':'aggregate','group_by':['تاریخ'],
        'columns':[{'title':'مبلغ (تومان)','expr':total},{'title':'تعداد','expr':expression('count',table='expenses')}],
        'footer':[{'title':'جمع هزینه','column':'مبلغ (تومان)','expr':total},
            {'title':'اختلاف سیمان و ماسه','column':'مبلغ (تومان)','expr':difference},
            {'title':'تعداد ثبت‌ها','column':'تعداد','expr':expression('count',table='expenses')}]}
    _,(headers,rows)=search.ask('هزینه هر روز و اختلاف هزینه سیمان با ماسه را حساب کن',
        scope='تراکنش‌ها',settings={},generator=generator_for(view,{'expenses'}))
    assert [(r['تاریخ'],r['مبلغ (تومان)']) for r in rows[:2]]==[('1405/07/01',1700),('1405/07/02',900)]
    assert [r['مبلغ (تومان)'] for r in rows[2:4]]==[2600,1600]
    assert rows[-1]['تعداد']==3 and headers[0]=='ردیف'
    assert search.db.snapshot()==before


def test_general_expression_cannot_inject_a_financial_number_or_code(search):
    expense(search,'سیمان',100)
    for expr in (expression('constant',value=987654),expression('eval',value='__import__("os").system("x")'),
                 expression('field','جزئیات.unknown_amount')):
        with pytest.raises(ValueError):
            search.ask('هزینه سیمان',scope='تراکنش‌ها',settings={},generator=generator_for(
                {'columns':[{'title':'مبلغ (تومان)','expr':expr}]},{'expenses'}))


def test_payment_count_uses_individual_completed_payments_and_actual_dates(search):
    eid=expense(search,'سیمان',1200)
    for day,amount in ((23,200),(24,300),(25,400)):
        search.db.add_payment(expense_id=eid,payment_date=f'2026-09-{day}',amount=amount,method='CASH')
    search.db.add_payment(expense_id=eid,payment_date='2026-09-26',amount=100,method='CASH',status='PENDING')
    view={'columns':[{'title':'مبلغ (تومان)','expr':expression('field','_amount')}],
        'footer':[{'title':'جمع پرداخت','column':'مبلغ (تومان)','expr':expression('sum','_amount',table='payments')},
            {'title':'تعداد پرداخت','column':'مبلغ (تومان)','expr':expression('count',table='payments')}]}
    _,(_,rows)=search.ask('چند پرداخت بابت سیمان انجام شده و در چه تاریخ‌هایی؟',
        scope='تراکنش‌ها',settings={},generator=generator_for(view,{'payments'}))
    assert [row['تاریخ'] for row in rows[:3]]==['1405/07/01','1405/07/02','1405/07/03']
    assert [row['مبلغ (تومان)'] for row in rows]==[200,300,400,900,3]
    assert not any(row['_table']=='payments' for row in search.records())


def test_financial_mirrors_cannot_be_added_to_the_expense_again(search):
    expense(search,'سیمان',1000)
    view={'mode':'aggregate','columns':[{'title':'مبلغ (تومان)','expr':expression('sum','_amount')}]}
    with pytest.raises(ValueError,match='منابع متفاوت'):
        search.ask('جمع هزینه و مانده',scope='تراکنش‌ها',settings={},
            generator=generator_for(view,{'expenses','expense_balance'}))


def test_per_field_missing_values_and_zero_denominator_do_not_become_money(search,monkeypatch):
    record={'_id':'facts:1','_table':'facts','_amount':None,'_bucket':'','_dates':{},
        'بخش':'داشبورد','تاریخ':'','شرح':'اطلاعات ثبت‌شده','مرجع':'facts:1',
        'جزئیات':{'هزینه':1000,'متراژ':0,'مبلغ ناخوانا':'خوانده نشد'}}
    monkeypatch.setattr(search,'search',lambda *a,**kw:[record])
    monkeypatch.setattr(search,'metric_records',lambda:[])
    view={'columns':[{'title':'هزینه هر متر','expr':expression('divide',args=[
        expression('field','جزئیات.هزینه'),expression('field','جزئیات.متراژ')])},
        {'title':'مبلغ (تومان)','expr':expression('sum','جزئیات.مبلغ ناخوانا',table='facts')}]}
    _,(_,rows)=search.ask('هزینه هر متر و مبلغ سند چقدر است؟',settings={},generator=generator_for(view,{'facts'}))
    assert rows[0]['هزینه هر متر']==MISSING and rows[0]['مبلغ (تومان)']==MISSING


def test_grouped_count_covers_all_batches_and_unique_days(search,monkeypatch):
    import advanced_search187 as module
    for number in range(8):document(search,f'D{number}','DAILY_REPORT','حضور نیروی خدمات',stamp=f'1405/07/{1+number%2:02}')
    monkeypatch.setattr(module,'AI_CONTEXT_CHARS',1600)
    view={'group_by':['تاریخ'],'columns':[{'title':'تعداد','expr':expression('count',table='financial_documents')}],
        'footer':[{'title':'تعداد کل ثبت‌ها','column':'تعداد','expr':expression('count',table='financial_documents')},
            {'title':'روزهای دارای حضور ثبت‌شده','column':'تعداد','expr':expression('distinct_count','تاریخ',table='financial_documents')}]}
    seen=[]
    base=generator_for(view,{'financial_documents'})
    def generate(prompt,**kwargs):
        seen.extend(r['_id'] for r in json.loads(prompt.split('رکوردها:\n',1)[1]))
        return base(prompt,**kwargs)
    _,(_,rows)=search.ask('حضور در هر روز را بشمار',scope='تقویم',settings={},generator=generate)
    assert len(seen)==len(set(seen))==8
    assert [r['تعداد'] for r in rows]==[4,4,8,2]


def test_new_comparison_computes_percentage_from_two_registered_budget_bases(search,monkeypatch):
    monkeypatch.setattr(search.rich,'all_phase_items',lambda:[{'phase_no':8,'qty_estimate':1,
        'estimate_rate':10000,'forecast_rate':20000,'total_actual':12000}])
    monkeypatch.setattr(search.rich,'get_phase_progress',lambda:{8:{'physical_progress':50}})
    def basis(name):
        return expression('field','مبلغ (تومان)',table='phase_summary',
            where=[{'path':'جزئیات.مبنای محاسبه','op':'eq','value':name}])
    baseline=basis('برآورد اولیه');actual=basis('هزینه انجام‌شده')
    percentage=expression('percent',args=[expression('subtract',args=[actual,baseline]),baseline])
    view={'mode':'aggregate','columns':[{'title':'برآورد اولیه (تومان)','expr':baseline},
        {'title':'هزینه واقعی (تومان)','expr':actual},{'title':'اختلاف (درصد)','expr':percentage}]}
    _,(_,rows)=search.ask('میزان اختلاف هزینه واقعی فاز هشت با برآورد اولیه به درصد چقدر است؟',
        scope='مدیریت پروژه',settings={},generator=generator_for(view,{'phase_summary'}))
    assert rows[0]['برآورد اولیه (تومان)']==10000
    assert rows[0]['هزینه واقعی (تومان)']==12000
    assert rows[0]['اختلاف (درصد)']==20


def test_elapsed_duration_and_days_with_evidence_are_different(search):
    document(search,'D1','DAILY_REPORT','شروع عملیات','',stamp='1405/07/01')
    document(search,'D2','DAILY_REPORT','پایان عملیات','',stamp='1405/07/07')
    view={'mode':'aggregate','columns':[{'title':'مدت (روز)','expr':expression('duration_days',args=[
        expression('min','تاریخ',table='financial_documents'),expression('max','تاریخ',table='financial_documents')])},
        {'title':'روزهای دارای گزارش','expr':expression('distinct_count','تاریخ',table='financial_documents')}]}
    _,(_,rows)=search.ask('مدت این عملیات و تعداد روزهای دارای گزارش را مقایسه کن',scope='تقویم',settings={},
        generator=generator_for(view,{'financial_documents'}))
    assert rows[0]['مدت (روز)']==7 and rows[0]['روزهای دارای گزارش']==2


def test_closing_request_stops_before_the_next_external_batch(search):
    document(search,'D1','DAILY_REPORT','گزارش روزانه')
    calls=[]
    with pytest.raises(RuntimeError,match='لغو'):
        search.ask('گزارش',settings={},cancelled=lambda:True,generator=lambda *a,**kw:calls.append(a))
    assert not calls


def test_literal_phrase_and_legacy_scope_spelling_remain_supported(search):
    first=expense(search,'سیمان سفید',100)
    second=expense(search,'سفید سیمان',200)
    search.db.add_payment(expense_id=first,payment_date='2026-09-23',amount=100,method='CASH')
    search.db.add_payment(expense_id=second,payment_date='2026-09-23',amount=200,method='CASH')
    rows=search.search('سيمان سفيد',scope='تراکنشها')
    assert len(rows)==1 and rows[0]['مبلغ (تومان)']==100
    assert rows[0]['بخش']=='تراکنش‌ها'


@pytest.mark.parametrize('query,first,last',[
    ('در تاریخ ۱۴۰۵/۷/۲','1405/07/02','1405/07/02'),
    ('از ۱۴۰۵/۷/۲ تا ۱۴۰۵/۷/۵','1405/07/02','1405/07/05'),
    ('از ۱۴۰۵/۷/۲','1405/07/02',''),
    ('تا امروز','','1404/12/29'),
    ('یک ماه آینده','1404/12/29','1405/01/29'),
    ('ماه آینده','1405/01/01','1405/01/31'),
])
def test_relative_and_written_dates_are_shown_as_exact_jalali_ranges(query,first,last):
    assert requested_period(query,today=jdatetime.date(1404,12,29))==(first,last)


def test_cheque_is_a_payment_on_clearing_date_not_issue_date(search):
    eid=expense(search,'سیمان',1000)
    cid=search.db.create_cheque(amount=600,expense_id=eid,issue_date='2026-09-23',due_date='2026-09-25')
    search.db.add_payment(expense_id=eid,payment_date='2026-09-23',amount=600,method='CHEQUE',cheque_id=cid,status='PENDING')
    search.db.cash_cheque(cid,cashed_date='2026-09-25')
    assert not search.search('سیمان',start='1405/07/01',end='1405/07/01',date_basis='تاریخ پرداخت')
    rows=search.search('سیمان',start='1405/07/03',end='1405/07/03',date_basis='تاریخ پرداخت')
    assert len(rows)==1 and search.totals(rows)[0]['مبلغ (تومان)']==600


def test_contractor_balance_separates_work_cash_open_cheque_and_guarantee(search):
    directory=Path(search.db.db_path).parent
    open_id=search.db.create_cheque(amount=300,issue_date='2026-09-23',due_date='2026-10-10')
    guarantee_id=search.db.create_cheque(amount=100,issue_date='2026-09-23',due_date='2026-10-10',is_guarantee=True)
    (directory/'contractor_contracts_18_7.json').write_text(json.dumps({'contracts':[
        {'contract_id':'C1','family_name':'نیکزاد','total_amount':2000,
         'payments':[{'amount':200},{'amount':300,'cheque_id':open_id},{'amount':300,'cheque_id':open_id},
                     {'amount':100,'cheque_id':guarantee_id}]}]}),encoding='utf-8')
    (directory/'contractor_statements_18_7.json').write_text(json.dumps({'statements':[
        {'statement_id':'S1','contract_id':'C1','statement_date':'1405/07/01','rows':[{'line_total':1000}]}]}),encoding='utf-8')
    source=next(r for r in search.records() if r['_table']=='contract_statement_balance')
    assert source['_amount']==800
    assert source['جزئیات']['دریافتی']==200
    assert source['جزئیات']['چک باز']==300
    assert source['جزئیات']['مانده بدون چک باز']==500
    assert source['جزئیات']['مراجع صورت‌وضعیت']==['S1']


def test_historical_manager_balance_uses_ledger_cutoff(search):
    expense(search,'اسکلت',1000)
    expense(search,'دیوار',900,'03')
    before=search.db.snapshot()
    records=search.account_period_records('1405/07/01','1405/07/01')
    values={r['شرح']:r['_amount'] for r in records}
    assert values['مانده حساب مدیر تا پایان بازه']==100
    assert values['مانده حساب مدیر پیش از بازه']==0
    assert values['حقوق مدیر در بازه']==100
    assert search.db.snapshot()==before


def test_message_flags_come_from_the_same_local_read_and_alarm_state(search,monkeypatch):
    import financial_calendar_stage18_7 as calendar
    event=calendar.FinancialEvent187('2026-09-23','1405/07/01','NOTE','بازدید ناظر',0,'',source_id='N1')
    monkeypatch.setattr(calendar,'message_events_187',lambda *a,**kw:[event])
    local=Path(search.db.db_path).parent/'ui_settings_v18.json'
    local.write_text(json.dumps({calendar.ROW_ALERT_PREFS_KEY_187:{calendar._event_alert_key_187(event):True}}),encoding='utf-8')
    record=search.message_records()[0]
    assert record['جزئیات']['هشدار'] is True and record['جزئیات']['خوانده‌نشده'] is True
    local.write_text(json.dumps({calendar.ROW_ALERT_PREFS_KEY_187:{calendar._event_alert_key_187(event):True},
        calendar.READ_EVENTS_KEY_187:{calendar._message_state_key_187(event):True}}),encoding='utf-8')
    assert search.message_records()[0]['جزئیات']['خوانده‌نشده'] is False
