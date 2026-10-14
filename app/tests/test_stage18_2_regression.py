from __future__ import annotations

from pathlib import Path
import os
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_BOOT = tempfile.TemporaryDirectory()
os.environ.setdefault('TELEGRAM_BOT_TOKEN', 'reg182-token')
os.environ.setdefault('GEMINI_API_KEY', 'reg182-key')
os.environ.setdefault('ADMIN_USER_ID', '1')
os.environ['STAGE4_DB_PATH'] = str(Path(_BOOT.name) / 'reg182.sqlite3')
os.environ['STAGE4_SHEETS_ENABLED'] = 'false'

import dashboard_stage18_2 as m


def _keys(groups):
    return [[f.key for f in group] for group in groups]


def test_v182_cash_wizard_step_contract():
    # دسته‌بندی is asked on the wizard's first window, beside the amount and
    # the kind of transaction, so it must not appear among these groups - and
    # not as a leftover page of its own either.
    groups = _keys(m.wizard_steps_182('هزینه ساخت', 'نقدی'))
    assert groups == [
        ['payer_name', 'receiver_name', 'issuer_name'],
        ['description', 'payment_method'],
        ['invoice_amount', 'final_amount', 'discount_amount'],
        ['payment_state', 'total_debt', 'remaining_debt'],
        ['main_phase', 'sub_phase'],
    ]
    assert 'cost_group' not in {key for group in groups for key in group}


def test_v182_cheque_wizard_step_contract_has_no_duplicate_cheque_amount():
    groups = _keys(m.wizard_steps_182('هزینه ساخت', 'چک'))
    assert groups == [
        ['payer_name', 'receiver_name', 'description'],
        ['issuer_name', 'issuer_bank', 'cheque_type', 'is_guarantee'],
        ['cheque_registration_state', 'due_date_shamsi', 'cheque_status'],
        ['invoice_amount', 'final_amount', 'discount_amount'],
        ['payment_state', 'total_debt', 'remaining_debt'],
        ['main_phase', 'sub_phase'],
    ]
    flat = {key for group in groups for key in group}
    assert 'cheque_amount' not in flat
    # cost_group is asked on the first window, not here.
    assert 'cost_group' not in flat



def test_v182_sale_wizard_step_contract():
    assert _keys(m.wizard_steps_182('ورودی', 'فروش')) == [
        ['sale_id', 'sale_unit', 'sold_area'],
        ['payer_name', 'buyer_name'],
    ]


def test_v182_receipt_caption_prefers_exact_persisted_caption():
    row = {'raw_text': 'پیام خام مستقیم', 'payload': {'receipt_caption': 'خرید سیمان', 'description': 'متن طولانی اطراف گروه'}}
    assert m._receipt_caption(row) == 'خرید سیمان'


def test_v182_receipt_caption_falls_back_only_to_raw_message_text():
    row = {'raw_text': 'متن مستقیم همان پیام', 'payload': {'description': 'context بزرگ و نامرتبط'}}
    assert m._receipt_caption(row) == 'متن مستقیم همان پیام'


def test_v182_visible_navigation_contract():
    assert m.Stage182Dashboard._VISIBLE_NAV == [
        'داشبورد', 'ثبت دیتا', 'تراکنش‌ها', 'فروش و مطالبات', 'گزارش‌گیری', 'حساب مدیر'
    ]


def test_v182_theme_reference_palettes_are_locked():
    assert m._THEME_DARK['bg'] == '#0C192A'
    assert m._THEME_DARK['surface'] == '#0E1E31'
    assert m._THEME_DARK['cyan'] == '#28AEB8'
    assert m._THEME_LIGHT['bg'] == '#F8F9FA'
    assert m._THEME_LIGHT['surface'] == '#FFFFFF'
    assert m._THEME_LIGHT['cyan'] == '#20AEB9'


def test_pdf_runtime_dependencies_are_declared():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    for req in ('requirements_stage9.txt','requirements_stage15.txt'):
        text = (root / req).read_text(encoding='utf-8').lower()
        assert 'reportlab' in text
        assert 'arabic-reshaper' in text
        assert 'python-bidi' in text


def test_final_development_package_includes_v182_changed_sources_and_tests():
    from development_package_v174 import SAFE_SOURCE_FILES
    required = {
        'dashboard_stage18_2.py','dashboard_stage18.py','dashboard_stage16_3.py','ui_stage10.py',
        'approval_service.py','receipt_intelligence.py','launcher_stage18_2.py',
        'requirements_stage9.txt','requirements_stage15.txt',
        'tests/test_stage18_2_ui.py','tests/test_stage18_2_regression.py','tests/test_stage18_1_receipt.py',
    }
    assert required <= set(SAFE_SOURCE_FILES)


def test_v186_actually_resolves_to_v182s_wizard_and_editor_overrides():
    """The active layer deliberately wraps the inherited forms in place."""
    import dashboard_stage18_6 as m186
    import dashboard_stage18_7 as active
    assert m186.TransactionWizard186.next is active._wizard_next_187
    assert m186.UnifiedPendingEditor186._build is active._editor_build_187
    assert active._ORIGINAL_WIZARD_NEXT_187.__qualname__ == 'TransactionWizard182.next'
    assert active._ORIGINAL_EDITOR_BUILD_187.__qualname__ == '_UnifiedPendingEditor182Final._build'
    assert m.UnifiedPendingEditor182 is m._UnifiedPendingEditor182Final


def test_v182_transaction_wizards_final_step_revises_an_already_posted_item():
    """Editing an already-APPROVED هزینه through ثبت دیتا's double-click path
    used to call save_payload()+approve_v18() directly here - the exact
    unfixed pattern, duplicated in this override rather than inherited from
    the base class - and raised 'این مورد دیگر در انتظار تأیید نیست' the
    moment the item was no longer PENDING_REVIEW.
    """

    import inspect
    source = inspect.getsource(m.TransactionWizard182.next)
    assert 'v18.submit_v18(' in source
    assert 'APPROVAL.save_payload' not in source, \
        'the final-step branch must route through submit_v18, not call save_payload+approve_v18 raw'

    open_full_source = inspect.getsource(m.TransactionWizard182._open_full)
    assert 'get_financial_posting' in open_full_source
    assert 'begin_posting_revision' in open_full_source


def test_v182_editor_puts_دسته‌بندی_with_the_general_fields_not_buried_in_the_special_card():
    """Check the live controls, including the active layer's wrappers."""
    import tkinter as tk
    import dashboard_stage18_7  # installs the runtime form wrappers
    root = tk.Tk(); root.withdraw()
    try:
        editor = m.UnifiedPendingEditor182(root, _cash_expense_row(), _FakeRich(), lambda: None)
        try:
            assert editor.cost_group_row.master is editor.main.body
            assert int(editor.cost_group_row.grid_info()['row']) < int(editor.special_host.grid_info()['row'])
            assert editor.vars['cost_group'].get() == 'پیمانکار'
            assert editor.vars['contract_id'].get() == 'D05DD75F1704'
            editor.vars['cost_group'].set('مصالح')
            root.update_idletasks()
            assert editor.vars['contract_id'].get() == ''
            assert not editor.widgets['contract_id'].master.winfo_manager()
            editor.title_var.set('یادداشت')
            editor._title_changed()
            assert not editor.cost_group_row.winfo_manager()
        finally:
            editor.destroy()
    finally:
        root.destroy()


class _FakeRich:
    def list_phase_summary(self): return []
    def phase_candidates(self, *a, **k): return []
    def subphase_candidates(self, *a, **k): return []


def _cash_expense_row(**extra):
    payload = {
        'v18_title': 'هزینه ساخت', 'v18_subtype': 'نقدی',
        'event_date_shamsi': '1405/06/01', 'amount': 10_000_000, 'paid_amount': 10_000_000,
        'cost_group': 'پیمانکار', 'contract_id': 'D05DD75F1704',
        'payer_name': 'تنخواه', 'receiver_name': 'ابراهیم ازبک', 'description': 'تست',
    }
    payload.update(extra)
    return {'pending_id': 'TEST-PID', 'status': 'PENDING_REVIEW', 'message_date': '1405/06/01', 'payload': payload}


def test_reopening_the_wizard_restores_دسته‌بندی_and_انتخاب_قرارداد_instead_of_leaving_them_blank():
    """page_index==0 only ever restored event_date_shamsi/amount from self.payload
    - دسته‌بندی/انتخاب قرارداد were built on this same window (see the wizard
    step contract test above) but nothing filled their StringVars from a
    payload that already had them, so reopening an already-typed record for
    editing showed both empty even though _capture() had saved them.
    """
    import tkinter as tk
    root = tk.Tk(); root.withdraw()
    try:
        row = _cash_expense_row()
        w = m.TransactionWizard182(root, row, _FakeRich(), lambda: None, lambda: None)
        try:
            assert w.vars['cost_group'].get() == 'پیمانکار'
            assert w.vars['contract_id'].get() != '', \
                'انتخاب قرارداد must not come back blank when the payload already has a contract_id'
        finally:
            w.destroy()
    finally:
        root.destroy()


def test_reopening_the_full_editor_shows_the_contracts_title_not_just_its_bare_id(monkeypatch):
    """The editor's own _load_values() did restore contract_id (unlike the
    wizard), but as the bare id string, not the "id | title — family" text the
    readonly combobox's own values list actually holds - so عنوان قرارداد
    itself, the thing the user asked to see, was still missing.
    """
    import tkinter as tk
    import contractor_store_stage18_7 as store
    monkeypatch.setattr(store, 'load_contracts', lambda: [
        {'contract_id': 'D05DD75F1704', 'title': 'اجرت اجرای اسکلت', 'family_name': 'ابراهیم ازبک'},
    ])
    root = tk.Tk(); root.withdraw()
    try:
        row = _cash_expense_row()
        ed = m.UnifiedPendingEditor182(root, row, _FakeRich(), lambda: None)
        try:
            assert ed.vars['cost_group'].get() == 'پیمانکار'
            shown = ed.vars['contract_id'].get()
            assert shown == 'D05DD75F1704 | اجرت اجرای اسکلت — ابراهیم ازبک', \
                'the box must show the contract display text, not the raw id alone'
        finally:
            ed.destroy()
    finally:
        root.destroy()


def test_صاحب_حساب_field_exists_for_نقدی_in_both_wizard_and_editor_and_survives_posting():
    """پیمانکار sometimes has to give someone else's card/account for a cash
    payment; صاحب حساب already existed for چک (issuer_name) but نقدی had
    nowhere to record it, and build_posting_plan only ever copied issuer_name
    into the plan inside its is_cheque branch - so even if a caller stuffed it
    into the payload by hand, a plain cash EXPENSE plan silently dropped it.
    """
    import tkinter as tk
    from financial_posting import build_posting_plan
    root = tk.Tk(); root.withdraw()
    try:
        row = _cash_expense_row(detected_type='EXPENSE', issuer_name='علی رضایی')
        w = m.TransactionWizard182(root, row, _FakeRich(), lambda: None, lambda: None)
        try:
            w.next()
            assert [fd.key for fd in w.pages[w.page_index]] == ['payer_name', 'receiver_name', 'issuer_name']
            assert w.vars['issuer_name'].get() == 'علی رضایی'
        finally:
            w.destroy()

        ed = m.UnifiedPendingEditor182(root, row, _FakeRich(), lambda: None)
        try:
            assert ed.vars['issuer_name'].get() == 'علی رضایی'
            payload_out = ed._payload_from_vars(ed.title_var.get(), ed.subtype_var.get())
        finally:
            ed.destroy()

        plan = build_posting_plan(payload=payload_out, raw_text='', telegram_message_date='1405/06/01')
        assert plan['issuer_name'] == 'علی رضایی'
    finally:
        root.destroy()
