"""Receipt controls and AI routing against disposable data and real Tk forms."""
import asyncio
import os
import time

from PIL import Image
import pytest

from test_transaction_lifecycle_matrix import m, runtime, register
from test_stage18_7_record_fields import root, record
from receipt_evidence187 import upload_image, remove_image, copy_image, clipboard_image
from transaction_lifecycle import TransactionLifecycle


@pytest.mark.parametrize('status', ['PENDING_REVIEW', 'APPROVED', 'REJECTED'])
def test_upload_delete_keeps_transaction_state_and_archive(runtime, tmp_path, status):
    row = record(runtime)
    runtime.db.update_pending(row['pending_id'], status=status)
    source = tmp_path / 'receipt.png'
    Image.new('RGB', (20, 20), 'navy').save(source)
    before = runtime.db.snapshot()
    saved = upload_image(runtime.db, row['pending_id'], source, 'متن جدید')
    path = saved['payload']['receipt_image_path']
    assert saved['status'] == status
    assert runtime.db.snapshot() == before
    assert runtime.db.list_pending_attachments(row['pending_id'])
    removed = remove_image(runtime.db, row['pending_id'], path, '')
    assert removed['status'] == status and removed['payload']['receipt_image_deleted187']
    assert removed['payload']['receipt_caption'] == ''
    assert runtime.db.list_pending_attachments(row['pending_id']) == []
    assert runtime.db.snapshot() == before
    from pathlib import Path
    assert source.is_file() and Path(path).is_file()


@pytest.mark.parametrize('caption', ['شرح اصلاح‌شده', ''])
def test_ai_reads_latest_uploaded_image_and_explicit_caption(runtime, tmp_path, monkeypatch, caption):
    row = record(runtime)
    first = tmp_path / 'first.png'
    second = tmp_path / 'second.png'
    Image.new('RGB', (10, 10), 'red').save(first)
    Image.new('RGB', (10, 10), 'blue').save(second)
    upload_image(runtime.db, row['pending_id'], first, 'قدیمی')
    saved = upload_image(runtime.db, row['pending_id'], second, caption)
    calls = []
    async def analyze(**kwargs):
        calls.append(kwargs)
        return dict(payload=dict(detected_type='EXPENSE', amount=375, confidence=.9, description='مصالح نمونه'))
    monkeypatch.setattr(runtime.approval.receipts, 'analyze_archived', analyze)
    asyncio.run(runtime.approval.analyze_pending_with_ai(row['pending_id']))
    assert calls[0]['image_path'] == saved['payload']['receipt_image_path']
    assert calls[0]['caption'] == caption
    fresh = runtime.db.get_pending_item(row['pending_id'])
    assert fresh['payload']['amount'] == 375 and fresh['payload']['receipt_caption'] == caption
    assert fresh['payload']['receipt_image_path'] == saved['payload']['receipt_image_path']
    assert runtime.db.snapshot().cash_balance == 0
    remove_image(runtime.db, row['pending_id'], fresh['payload']['receipt_image_path'], caption)
    with pytest.raises(FileNotFoundError):
        asyncio.run(runtime.approval.analyze_pending_with_ai(row['pending_id']))
    assert len(calls) == 1


def test_actual_record_image_paste_caption_edit_delete_and_reopen(root, runtime, monkeypatch):
    from barkav_ui.clipboard import action
    row = record(runtime)
    editor = m.v182.UnifiedPendingEditor182(root, row, runtime.rich, lambda: None)
    root.update()
    controller = editor._receipt_controller187
    assert controller.upload_button.cget('text') == 'بارگذاری رسید/فایل'
    monkeypatch.setattr('record_receipt187.clipboard_image', lambda: Image.new('RGB', (30, 20), 'red'))
    action(editor.caption, 'paste')
    assert editor._image is not None
    monkeypatch.setattr('record_receipt187.clipboard_image', lambda: None)
    action(editor.caption, 'select')
    root.clipboard_clear(); root.clipboard_append('متن رسید آزمایشی')
    action(editor.caption, 'paste')
    assert editor.caption.get('1.0', 'end-1c') == 'متن رسید آزمایشی'
    controller.delete_text()
    assert editor.caption.get('1.0', 'end-1c') == ''
    controller.image_action('delete')
    assert editor._image is None
    pid = row['pending_id']
    editor.destroy()
    reopened = m.v182.UnifiedPendingEditor182(root, runtime.db.get_pending_item(pid), runtime.rich, lambda: None)
    root.update()
    assert reopened._image is None and reopened.caption.get('1.0', 'end-1c') == ''
    assert runtime.db.get_pending_item(pid)['status'] == 'PENDING_REVIEW'


@pytest.mark.skipif(os.name != 'nt', reason='Windows bitmap clipboard')
def test_windows_bitmap_clipboard_round_trip(root):
    previous_image = clipboard_image()
    try:
        previous_text = root.clipboard_get() if previous_image is None else None
    except Exception:
        previous_text = ''
    try:
        copy_image(Image.new('RGB', (12, 9), (25, 90, 160)), root.winfo_id())
        pasted = clipboard_image()
        assert pasted.size == (12, 9) and pasted.convert('RGB').getpixel((3, 3)) == (25, 90, 160)
    finally:
        if previous_image is not None:
            copy_image(previous_image, root.winfo_id())
        else:
            root.clipboard_clear(); root.clipboard_append(previous_text)


def test_record_reprocess_fills_fields_from_receipt_without_posting(root, runtime, monkeypatch):
    row = record(runtime)
    row['payload']['source'] = 'MANUAL_GUI_18_7'
    runtime.db.update_pending(row['pending_id'], payload=row['payload'])
    editor = m.v182.UnifiedPendingEditor182(root, row, runtime.rich, lambda: None)
    editor._receipt_controller187.upload(Image.new('RGB', (20, 20), 'blue'))
    editor.caption.delete('1.0', 'end'); editor.caption.insert('1.0', 'خرید مصالح مبلغ ۳۷۵ تومان')
    calls = []
    async def analyze(**kwargs):
        calls.append(kwargs)
        return dict(payload=dict(detected_type='EXPENSE', amount=375, confidence=.9,
                                 description='مصالح نمونه', payment_method='BANK_TRANSFER'))
    monkeypatch.setattr(runtime.approval.receipts, 'analyze_archived', analyze)
    editor._receipt_controller187.reprocess()
    deadline = time.monotonic() + 10
    while editor._receipt_controller187.busy and time.monotonic() < deadline:
        root.update()
        time.sleep(.02)
    assert calls and calls[0]['caption'] == 'خرید مصالح مبلغ ۳۷۵ تومان'
    assert not editor._receipt_controller187.busy
    assert m.parse_int(editor.vars['amount'].get()) == 375
    assert runtime.db.get_pending_item(editor.pid)['status'] == 'PENDING_REVIEW'
    assert runtime.db.snapshot().cash_balance == 0
    assert not runtime.db.get_financial_posting(editor.pid)


def test_table_preview_receipt_text_and_approved_copy_preserve_filter(root, runtime, monkeypatch):
    m.style_ttk_187(root)
    monkeypatch.setattr(m.DataEntryCenter187, '_service_status_181', lambda self: None)
    for name in ('_start_telegram_probe_187', '_start_gemini_probe_187'):
        if hasattr(m.DataEntryCenter187, name):
            monkeypatch.setattr(m.DataEntryCenter187, name, lambda self: None)
    row = record(runtime)
    m.v18.submit_v18(row['pending_id'], row['payload'], runtime.rich)
    row = runtime.db.get_pending_item(row['pending_id'])
    center = m.DataEntryCenter187(root, runtime.rich)
    center.pack(fill='both', expand=True)
    center._show(row)
    center.text.delete('1.0', 'end'); center.text.insert('1.0', 'کپشن جدید جدول')
    center._receipt_preview187.save_caption()
    assert runtime.db.get_pending_item(row['pending_id'])['payload']['receipt_caption'] == 'کپشن جدید جدول'
    center._receipt_preview187.upload(Image.new('RGB', (20, 20), 'green'))
    assert center._image is not None
    center._receipt_preview187.image_action('delete')
    assert center._image is None
    with runtime.db.read() as con:
        attached = [dict(item) for item in con.execute('SELECT entity_type,local_path FROM attachments')]
    assert all(item['entity_type'] == 'RECEIPT_ARCHIVE' for item in attached), attached
    for filter_value in ('همه', 'Pending', 'تأییدشده', 'ردشده'):
        center.filter.set(filter_value)
        center.copy_rows([runtime.db.get_pending_item(row['pending_id'])])
        copied = center.paste_rows([row])
        assert center.filter.get() == filter_value
        assert runtime.db.get_pending_item(copied[0])['status'] == 'PENDING_REVIEW'
        assert runtime.db.list_pending_attachments(copied[0]) == []
        assert runtime.db.get_pending_item(row['pending_id'])['status'] == 'APPROVED'


@pytest.mark.parametrize('edit_after_reject', [False, True])
def test_receipt_changes_on_posted_record_keep_financial_reject_restore(runtime, edit_after_reject):
    row = record(runtime)
    pid = row['pending_id']
    upload_image(runtime.db, pid, Image.new('RGB', (20, 20), 'navy'), 'رسید اول')
    row = runtime.db.get_pending_item(pid)
    m.v18.submit_v18(pid, row['payload'], runtime.rich)
    baseline = runtime.db.snapshot()
    lifecycle = TransactionLifecycle(runtime.db)
    if edit_after_reject:
        lifecycle.reject(pid)
    current = runtime.db.get_pending_item(pid)
    remove_image(runtime.db, pid, current['payload']['receipt_image_path'], 'بدون رسید قبلی')
    uploaded = upload_image(runtime.db, pid, Image.new('RGB', (20, 20), 'green'), 'رسید جایگزین')
    if not edit_after_reject:
        lifecycle.reject(pid)
    assert runtime.db.snapshot().cash_balance == 0
    lifecycle.restore(pid)
    assert runtime.db.snapshot() == baseline
    saved = runtime.db.get_pending_item(pid)['payload']
    assert saved['receipt_caption'] == 'رسید جایگزین'
    assert saved['receipt_image_path'] == uploaded['payload']['receipt_image_path']
    assert not saved['receipt_image_deleted187']
    lifecycle.reject(pid)
    assert runtime.db.snapshot().cash_balance == 0


def test_copy_from_transaction_table_also_preserves_data_entry_filter(runtime, monkeypatch):
    from types import SimpleNamespace
    import tkinter as tk
    root = tk.Tcl()
    selected_filter = tk.StringVar(root, 'همه')
    center = SimpleNamespace(filter=selected_filter, refresh=lambda: None)
    owner = SimpleNamespace(approval_center=center, document_table=object(),
        _transaction_payload_187=lambda row: row['payload'])
    monkeypatch.setattr(m, 'show_toast', lambda *args: None)
    source = record(runtime)
    m.v18.submit_v18(source['pending_id'], source['payload'], runtime.rich)
    pid = m.Stage187Dashboard._copy_transaction_row_187(owner, object(), source)
    assert selected_filter.get() == 'همه'
    assert runtime.db.get_pending_item(pid)['status'] == 'PENDING_REVIEW'
