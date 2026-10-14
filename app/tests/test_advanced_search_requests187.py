import json
import pytest
from test_advanced_search187 import search, document
from advanced_search_requests187 import FAQ, questions_for, context_parts, parse_response


def test_faq_covers_workbook_and_filters_by_section():
    assert len(FAQ)>=35
    for scope in {section for section,_ in FAQ}:
        assert questions_for(scope)==[question for section,question in FAQ if section==scope]
    assert len(questions_for('همه'))==len(FAQ)
    assert any('هشدار' in question for question in questions_for('پیام‌ها'))
    assert any('طبقه ۴' in question for question in questions_for('داشبورد'))


def test_wrapped_json_is_parsed_without_executing_model_text():
    assert parse_response('پاسخ: ```json\n{"record_ids":["expenses:1"]}\n```')['record_ids']==['expenses:1']
    with pytest.raises(ValueError):parse_response('__import__("os")')


def test_large_text_is_split_without_losing_any_source_content():
    content='حضور ناصر در کارگاه؛ '*4000
    parts=context_parts({'_id':'document:1','_table':'documents','شرح':content},1000)
    text_parts=[part['content'] for part in parts if part['content']['field']=='شرح']
    assert ''.join(part['text'] for part in text_parts)==json.dumps(content,ensure_ascii=False)
    assert all(part['_id']=='document:1' for part in parts)


def test_provider_failure_returns_labelled_local_sources_not_error_or_fake_ai(search):
    document(search,'D1','DAILY_REPORT','کارکرد ناصر')
    before=search.db.snapshot()
    def failed(*args,**kwargs):raise RuntimeError('provider payload must not be exposed')
    model,(_,rows)=search.ask_safe('ناصر چند روز کار کرده؟',scope='تقویم',settings={},generator=failed)
    assert 'محلی' in model and any('ناصر' in row.get('شرح','') for row in rows)
    assert rows[-1]['ردیف']=='وضعیت' and 'AI' in rows[-1]['شرح']
    assert 'provider payload' not in json.dumps(rows)
    assert search.db.snapshot()==before


def test_default_provider_can_return_ids_without_a_view(search,monkeypatch):
    import project_report_ai_187 as module
    document(search,'D1','DAILY_REPORT','کارکرد ناصر')
    def generate(prompt,**kwargs):
        batch=json.loads(prompt.split('رکوردها:\n',1)[1])
        raw=json.dumps({'record_ids':[row['_id'] for row in batch if row['_table']=='financial_documents']})
        kwargs['validator'](raw)
        return 'test-provider',raw
    monkeypatch.setattr(module,'generate_project_text',generate)
    model,(_,rows)=search.ask('ناصر چند روز کار کرده؟',scope='تقویم',settings={})
    assert model=='test-provider' and rows[-1]['تعداد روز']==1


def test_period_report_without_dates_includes_registered_history(search):
    document(search,'D1','DAILY_REPORT','اجرای اسکلت',stamp='1403/01/01')
    document(search,'D2','DAILY_REPORT','اجرای دیوار',stamp='1403/01/02')
    _,rows=search.period_table('روزانه')
    assert any('اسکلت' in row.get('شرح گزارش','') for row in rows)
    assert any('دیوار' in row.get('شرح گزارش','') for row in rows)
    assert len(rows)==2


def test_transactions_show_individual_amount_not_total_expense_debt(search):
    eid=search.db.create_expense(event_date='2026-09-23',shamsi_date='1405/07/01',
        final_amount=10000,description='سیمان',construction_stage='اسکلت')
    search.db.add_payment(expense_id=eid,payment_date='2026-09-23',amount=2000,method='CASH')
    search.db.add_payment(expense_id=eid,payment_date='2026-09-24',amount=3000,method='CASH')
    rows=search.search('سیمان',scope='تراکنش‌ها')
    assert [row['_amount'] for row in rows]==[2000,3000]
    assert all(row['_table']=='payments' for row in rows)
    assert search.totals(rows)[0]['مبلغ (تومان)']==5000
    assert search.search('سیمان',scope='همه')[0]['_amount']==10000


def test_other_scope_contains_registered_invoice_documents(search):
    document(search,'D1','INVOICE_NOTE','فاکتور سیمان')
    document(search,'D2','DAILY_REPORT','اجرای سیمان')
    assert [row['_id'] for row in search.search('سیمان',scope='سایر')]==['financial_documents:D1']


def test_daily_title_and_identical_stored_text_are_displayed_once(search):
    document(search,'D1','DAILY_REPORT','اجرای اسکلت',raw='اجرای اسکلت')
    assert search.search('اسکلت',scope='تقویم')[0]['شرح']=='اجرای اسکلت'


def test_linked_ledger_transaction_appears_once_with_its_own_amount(search):
    eid=search.db.create_expense(event_date='2026-09-23',final_amount=10000,description='سیمان')
    tx=search.db.post_transaction(event_date='2026-09-24',direction='OUT',amount=2500,
        category='CONSTRUCTION_PAYMENT',expense_id=eid)
    search.db.add_payment(expense_id=eid,payment_date='2026-09-24',amount=2500,method='CASH',transaction_id=tx)
    rows=search.search('سیمان',scope='تراکنش‌ها')
    assert len(rows)==1 and rows[0]['_table']=='transactions' and rows[0]['_amount']==2500


def test_all_long_document_text_reaches_model_including_last_part(search,monkeypatch):
    import advanced_search187 as module
    monkeypatch.setattr(module,'AI_CONTEXT_CHARS',1000)
    content='حضور پیمانکار در محل اجرا؛ '*200+'آخرین بخش ناصر'
    document(search,'D1','DOCUMENT','سند کارگاه',raw=content)
    seen=[]
    def generator(prompt,**kwargs):
        batch=json.loads(prompt.split('رکوردها:\n',1)[1]);seen.extend(batch)
        raw=json.dumps({'record_ids':[row['_id'] for row in batch]})
        kwargs['validator'](raw)
        return 'test-model',raw
    _,(_,rows)=search.ask('ناصر',scope='سایر',settings={},generator=generator)
    fragments=[row['content'] for row in seen if row.get('content',{}).get('field')=='جزئیات.raw_text']
    assert json.loads(''.join(part['text'] for part in fragments))==content
    assert rows[0]['مرجع']=='financial_documents:D1'
