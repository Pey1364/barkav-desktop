from copy import deepcopy
from types import SimpleNamespace
from pathlib import Path
import pytest
from PIL import Image
from test_transaction_lifecycle_matrix import m, runtime, register
from test_cheque_workflow187 import cheque_payload
from test_stage18_7_record_fields import root
from cheque_record_edit187 import open_cheque_record
from receipt_evidence187 import upload_image, remove_image, upload_file
from receipt_gallery187 import receipt_paths, ReceiptGallery187


@pytest.fixture
def dashboard(runtime,monkeypatch):
    from barkav_ui import art
    art.clear_cache()
    monkeypatch.setattr(m.v186.v185,'fetch_tgju_usd_toman',lambda timeout=6:(70000,'2026-10-05'))
    monkeypatch.setattr(m.DataEntryCenter187,'_start_gemini_probe_187',lambda self:None)
    monkeypatch.setattr(m.DataEntryCenter187,'_start_telegram_probe_187',lambda self:None)
    monkeypatch.setattr(m.Stage187Dashboard,'_show_startup_reminders_187',lambda self:None)
    app=m.Stage187Dashboard();app.update()
    yield app
    app.destroy()


def issued(runtime):
    payload=cheque_payload();pid=register(runtime,payload)
    m.v18.submit_v18(pid,payload,runtime.rich)
    return pid,runtime.db.list_cheques(open_only=False)[0]


def test_cheque_double_edit_cancel_restores_original(dashboard,runtime):
    pid,row=issued(runtime)
    before=deepcopy(runtime.db.get_pending_item(pid))
    cheque=deepcopy(row)
    e=dashboard.edit_cheque_row(row)
    assert isinstance(e,m.v182.UnifiedPendingEditor182)
    assert runtime.db.get_pending_item(pid)['status']=='EDIT_PENDING'
    e.vars['issuer_name'].set('تغییر لغوشده')
    e._receipt_controller187.upload(Image.new('RGB',(50,50),'blue'))
    e.destroy();dashboard.update()
    assert runtime.db.get_pending_item(pid)['status']==before['status']=='APPROVED'
    assert runtime.db.get_pending_item(pid)['payload']==before['payload']
    assert runtime.db.get_cheque(row['cheque_id'])==cheque
    assert receipt_paths(runtime.db,pid, row)==[]


@pytest.mark.parametrize('status',m.CHEQUE_RESOLUTION_STATUS_CHOICES_187)
def test_settled_cheque_record_edits_without_new_rows(dashboard,runtime,monkeypatch,status):
    errors=[]
    for name in ('showerror','showwarning'):
        monkeypatch.setattr(m.messagebox,name,lambda *a,**kw:errors.append(a))
    monkeypatch.setattr(m,'_confirm_debt_warning_187',lambda *a:True)
    pid,row=issued(runtime)
    runtime.db.update_cheque_workflow_state(row['cheque_id'],lifecycle='CASHED')
    cost=runtime.db.snapshot().construction_cost
    e=dashboard.edit_cheque_row(runtime.db.get_cheque(row['cheque_id']))
    assert row['cheque_id'] in {item['cheque_id'] for item in m._registered_cheques_for_clearing_187()}
    e.vars['issuer_name'].set('صاحب حساب ویرایش‌شده')
    e.vars['cheque_status'].set(status)
    e.vars['cheque_return_disposition187'].set(m.CHEQUE_RETURN_DISPOSITION_CHOICES_187[3])
    e.vars['cheque_return_account_holder187'].set('حساب آزمون')
    e.vars['cheque_void_reason187'].set('دلیل آزمون')
    e._receipt_controller187.upload(Image.new('RGB',(50,50),'green'))
    e.approve()
    assert not errors,errors
    saved=runtime.db.get_cheque(row['cheque_id'])
    assert saved['issuer_name']=='صاحب حساب ویرایش‌شده'
    assert m._cheque_status_label_187(saved)==status
    assert len(runtime.db.list_cheques(open_only=False))==1
    assert runtime.db.get_pending_item(pid)['status']=='APPROVED'
    assert len(receipt_paths(runtime.db,pid,saved))==1
    assert runtime.db.snapshot().construction_cost==cost
    e.destroy()


def test_upload_adds_documents_and_gallery_navigates(root,runtime,tmp_path):
    pid,row=issued(runtime)
    upload_image(runtime.db,pid,Image.new('RGB',(60,60),'red'),'')
    upload_image(runtime.db,pid,Image.new('RGB',(60,60),'blue'),'')
    file=tmp_path/'drawing.dwg';file.write_bytes(b'test drawing')
    upload_file(runtime.db,pid,file)
    paths=receipt_paths(runtime.db,pid,row)
    assert len(paths)==3
    bar=m.ttk.Frame(root);bar.pack();canvas=m.tk.Canvas(root);canvas.pack()
    gallery=ReceiptGallery187(canvas,bar,paths)
    assert str(gallery.previous['state'])=='normal'
    assert str(gallery.next['state'])=='normal'
    first=gallery.path;gallery.move(1);assert gallery.path!=first
    gallery.move(1);assert gallery.path!=first
    assert str(gallery.previous['state'])=='normal'
    assert str(gallery.next['state'])=='normal'
    gallery.move(-2);assert gallery.path==first
    remove_image(runtime.db,pid,first,'')
    assert len(receipt_paths(runtime.db,pid,row))==2


def test_all_financial_tabs_have_receipt_column(dashboard,runtime,monkeypatch):
    pid,row=issued(runtime)
    upload_image(runtime.db,pid,Image.new('RGB',(60,60),'red'),'')
    upload_image(runtime.db,pid,Image.new('RGB',(60,60),'blue'),'')
    dashboard.refresh_all();dashboard.update()
    for name in ('all_tx_table','land_table','exp_table','cheque_table','in_table','out_table','loan_table','document_table'):
        table=getattr(dashboard,name)
        assert 'receipt' in table.tree['columns'],name
        assert table.tree.heading('receipt','text')=='رسید'
    table=dashboard.cheque_table
    values=table.row_values(runtime.db.get_cheque(row['cheque_id']))
    assert any('📎' in str(value) for value in values)
    iid=table.tree.get_children()[0]
    displayed=tuple(table.tree['displaycolumns'])
    monkeypatch.setattr(table.tree,'identify_row',lambda y:iid)
    monkeypatch.setattr(table.tree,'identify_column',lambda x:'#'+str(displayed.index('receipt')+1))
    preview=dashboard._open_transaction_record_on_double_click_187(table,SimpleNamespace(x=2,y=2))
    assert len(preview.gallery187.paths)==2
    preview.gallery187.move(1)
    assert preview.gallery187.index==1
    preview.destroy()
