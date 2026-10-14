"""Row journal: what an action changed can be undone and redone, safely.

Uses real FinanceDB / service objects on a throwaway database, never live data.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

import row_journal
from action_history import TabHistory, UndoRefused
from dashboard_service_stage9 import DashboardServiceStage9
from budget_rich_v163 import RichBudgetService
from finance_db import FinanceDB
from telegram_stage5_workflow import TelegramStage5Workflow


@pytest.fixture()
def env(tmp_path):
    db = FinanceDB(Path(tmp_path) / 'journal.sqlite3')
    service = DashboardServiceStage9(db, Path(tmp_path))
    return db, service


@pytest.fixture()
def captured():
    seen = []
    row_journal.install(lambda db, changes: seen.append((db, changes)))
    yield seen
    row_journal.uninstall()


def _row(db, table, column, value):
    with db.read() as con:
        found = con.execute(f'SELECT * FROM "{table}" WHERE "{column}"=?', (value,)).fetchone()
    return dict(found) if found else None


def _new_transaction(db, amount=1000):
    return db.post_transaction(event_date='2026-09-01', direction='OUT', amount=amount,
                               category='مصالح', description='خرید')


def _action_of(seen, index=-1):
    db, changes = seen[index]
    return row_journal.build_action(db, changes)


def test_deleting_a_manual_transaction_can_be_undone_and_redone(env, captured):
    db, service = env
    tx = _new_transaction(db)
    cash_before = db.snapshot().cash_balance
    captured.clear()

    service.delete_manual_transaction(tx)
    assert _row(db, 'transactions', 'transaction_id', tx)['status'] == 'VOIDED'
    action = _action_of(captured)
    assert action.label == 'حذف تراکنش' and action.undoable

    action.undo()
    restored = _row(db, 'transactions', 'transaction_id', tx)
    assert restored['status'] == 'POSTED' and restored['deleted_at'] is None
    assert db.snapshot().cash_balance == cash_before
    with db.read() as con:
        assert con.execute("SELECT COUNT(*) FROM audit_log WHERE source='GUI_UNDO' AND action='UNDO'").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM sync_queue WHERE entity_id=? AND operation='UPDATE'", (tx,)).fetchone()[0] >= 1

    action.redo()
    assert _row(db, 'transactions', 'transaction_id', tx)['status'] == 'VOIDED'
    assert db.snapshot().cash_balance != cash_before


def test_deleting_a_posting_restores_every_linked_row(tmp_path):
    db = FinanceDB(Path(tmp_path) / 'posting.sqlite3')
    flow = TelegramStage5Workflow(db)
    received = flow.receive_message(
        chat_id=-1001234567890, message_id=101, raw_text='#تست', content_type='TEXT',
        message_date='1405/05/19 12:00',
        analysis={
            'detected_type': 'EXPENSE', 'document_type': 'TEXT', 'amount': 100_000_000,
            'invoice_amount': 100_000_000, 'final_amount': 100_000_000, 'discount_amount': 0,
            'paid_amount': 100_000_000, 'payment_state': 'PAID', 'description': 'خرید بتن',
            'expense_category': 'مصالح', 'payment_method': 'BANK_TRANSFER', 'is_cheque': False,
            'manager_fee_eligible': True, 'confidence': .99,
        })
    posting = flow.approve_and_post(received.pending_id).posting
    before = db.snapshot()
    seen = []
    row_journal.install(lambda database, changes: seen.append((database, changes)))
    try:
        db.delete_financial_posting(pending_id=received.pending_id, source='GUI')
        assert db.snapshot().cash_balance == 0
        action = _action_of(seen)
        assert action.undoable and action.label == 'حذف تراکنش'

        action.undo()
        assert db.snapshot().cash_balance == before.cash_balance
        assert db.snapshot().construction_cost == before.construction_cost
        assert _row(db, 'expenses', 'expense_id', posting.expense_id)['status'] != 'CANCELLED'
        assert _row(db, 'transactions', 'transaction_id', posting.transaction_id)['status'] == 'POSTED'
        assert _row(db, 'payments', 'payment_id', posting.payment_id)['status'] != 'CANCELLED'
        assert _row(db, 'financial_postings', 'pending_id', received.pending_id)['status'] == 'ACTIVE'

        action.redo()
        assert db.snapshot().cash_balance == 0
        assert _row(db, 'financial_postings', 'pending_id', received.pending_id)['status'] == 'DELETED'
    finally:
        row_journal.uninstall()


def test_editing_a_manual_transaction_is_undone_to_the_old_values(env, captured):
    db, service = env
    tx = _new_transaction(db, amount=1000)
    captured.clear()

    service.edit_manual_transaction(tx, amount=2500, description='اصلاح‌شده')
    action = _action_of(captured)
    assert action.label == 'ویرایش تراکنش'
    assert _row(db, 'transactions', 'transaction_id', tx)['amount'] == 2500

    action.undo()
    old = _row(db, 'transactions', 'transaction_id', tx)
    assert old['amount'] == 1000 and old['description'] == 'خرید'
    action.redo()
    assert _row(db, 'transactions', 'transaction_id', tx)['amount'] == 2500


def test_undo_is_refused_and_writes_nothing_when_rows_changed_since(env, captured):
    db, service = env
    tx = _new_transaction(db)
    captured.clear()
    service.delete_manual_transaction(tx)
    delete_action = _action_of(captured)

    with db.tx() as con:  # someone edits the voided row afterwards
        con.execute("UPDATE transactions SET description='دست‌کاری' WHERE transaction_id=?", (tx,))

    with pytest.raises(UndoRefused):
        delete_action.undo()
    current = _row(db, 'transactions', 'transaction_id', tx)
    assert current['status'] == 'VOIDED' and current['description'] == 'دست‌کاری'

    history = TabHistory()
    history.push(delete_action)
    assert 'دوباره تغییر کرده‌اند' in history.undo()


def test_a_row_the_action_inserted_is_cancelled_by_undo_never_deleted(env, captured):
    db, _service = env
    tx = _new_transaction(db)
    action = _action_of(captured)
    assert action.label == 'افزودن تراکنش'

    action.undo()
    row = _row(db, 'transactions', 'transaction_id', tx)
    assert row is not None and row['status'] == 'VOIDED' and row['deleted_at']
    with db.read() as con:
        assert con.execute('SELECT COUNT(*) FROM transactions').fetchone()[0] == 1

    action.redo()
    assert _row(db, 'transactions', 'transaction_id', tx)['status'] == 'POSTED'


def test_a_hard_delete_is_recorded_as_not_undoable(env, captured):
    db, _service = env
    tx = _new_transaction(db)
    captured.clear()

    with db.tx() as con:
        con.execute('DELETE FROM transactions WHERE transaction_id=?', (tx,))

    action = _action_of(captured)
    assert not action.undoable and 'به‌طور کامل حذف' in action.reason
    history = TabHistory()
    history.push(action)
    assert history.undo().startswith('«حذف تراکنش» قابل بازگشت نیست.')


def test_cancelling_a_cheque_is_undone_to_its_previous_state(env, captured):
    db, _service = env
    cheque = db.create_cheque(amount=5_000_000, issue_date='2026-09-01', due_date='2026-10-01')
    old_status = _row(db, 'cheques', 'cheque_id', cheque)['status']
    captured.clear()

    db.cancel_cheque(cheque, source='GUI', actor_id='GUI')
    action = _action_of(captured)
    assert action.label == 'حذف چک'
    assert _row(db, 'cheques', 'cheque_id', cheque)['status'] == 'CANCELLED'

    action.undo()
    assert _row(db, 'cheques', 'cheque_id', cheque)['status'] == old_status


def test_one_action_over_several_rows_is_one_undo_step(env, captured):
    db, _service = env
    ids = [_new_transaction(db, amount=100 * (n + 1)) for n in range(3)]
    captured.clear()

    with db.tx() as con:
        for tx in ids:
            con.execute("UPDATE transactions SET status='VOIDED', deleted_at='2026-09-29T10:00:00' WHERE transaction_id=?", (tx,))

    action = _action_of(captured)
    assert action.label == 'حذف ۳ تراکنش'
    action.undo()
    assert all(_row(db, 'transactions', 'transaction_id', tx)['status'] == 'POSTED' for tx in ids)


def test_undo_and_redo_writes_are_not_recorded_again(env, captured):
    db, service = env
    tx = _new_transaction(db)
    captured.clear()
    service.delete_manual_transaction(tx)
    action = _action_of(captured)
    recorded = len(captured)

    action.undo()
    action.redo()

    assert len(captured) == recorded


def test_bookkeeping_and_volatile_only_writes_create_no_action(env, captured):
    db, _service = env
    tx = _new_transaction(db)
    captured.clear()

    with db.tx() as con:
        con.execute("UPDATE transactions SET sync_status='SYNCED', updated_at='2026-09-29T09:00:00' WHERE transaction_id=?", (tx,))
        con.execute("INSERT INTO audit_log(entity_type,entity_id,action,source,created_at) VALUES('x','y','NOTE','TEST','2026-09-29T09:00:00')")

    assert captured == []


def test_a_failed_transaction_records_nothing_and_rolls_back(env, captured):
    db, _service = env
    tx = _new_transaction(db)
    captured.clear()

    with pytest.raises(RuntimeError):
        with db.tx() as con:
            con.execute("UPDATE transactions SET status='VOIDED' WHERE transaction_id=?", (tx,))
            raise RuntimeError('boom')

    assert captured == []
    assert _row(db, 'transactions', 'transaction_id', tx)['status'] == 'POSTED'


def test_writes_from_a_background_thread_are_not_recorded(env, captured):
    db, _service = env
    captured.clear()

    worker = threading.Thread(target=_new_transaction, args=(db,))
    worker.start()
    worker.join()

    assert captured == []


def test_a_closed_gate_records_nothing(env):
    db, service = env
    tx = _new_transaction(db)
    seen = []
    row_journal.install(lambda database, changes: seen.append(changes), gate=lambda: False)
    try:
        service.delete_manual_transaction(tx)
    finally:
        row_journal.uninstall()

    assert seen == []
    assert _row(db, 'transactions', 'transaction_id', tx)['status'] == 'VOIDED'


def test_uninstall_restores_the_plain_transaction_block(env):
    db, _service = env
    original = FinanceDB.tx
    row_journal.install(lambda database, changes: None)
    assert FinanceDB.tx is not original
    row_journal.uninstall()
    assert FinanceDB.tx is original
    _new_transaction(db)


def test_a_derived_status_flip_is_not_a_user_change_but_cancelling_is():
    stable = row_journal._stable
    assert stable({'status': 'OVERDUE', 'paid_amount': 0}, 'loan_installments') == \
        stable({'status': 'UPCOMING', 'paid_amount': 0}, 'loan_installments')
    assert stable({'status': 'CANCELLED'}, 'loan_installments') != stable({'status': 'UPCOMING'}, 'loan_installments')
    assert stable({'status': 'COMPLETED'}, 'sales') == stable({'status': 'ACTIVE'}, 'sales')
    assert stable({'status': 'VOIDED'}, 'transactions') != stable({'status': 'POSTED'}, 'transactions')


def test_a_huge_action_is_recorded_as_not_undoable_without_keeping_its_rows(env):
    db, _service = env
    changes = [row_journal.RowChange('rich_price_items', ('price_id',), (n,), 'INSERT', None, {'price_id': n})
               for n in range(row_journal.MAX_ROWS + 1)]
    action = row_journal.build_action(db, changes)
    assert not action.undoable and 'بیش از حد مجاز' in action.reason


def test_an_unknown_table_still_gets_a_readable_label():
    changes = [row_journal.RowChange('mystery_table', ('id',), (1,), 'UPDATE', {'id': 1, 'x': 1}, {'id': 1, 'x': 2})]
    assert row_journal.describe(changes) == 'ویرایش رکورد'


def _merged_action(seen):
    """What the window does: every write of one user action becomes one step."""
    changes = [change for _db, batch in seen for change in batch]
    return row_journal.build_action(seen[0][0], changes)


def test_plan_rows_and_prices_use_the_same_journal(tmp_path, captured):
    db = FinanceDB(Path(tmp_path) / 'plan.sqlite3')
    rich = RichBudgetService(db, tmp_path)
    captured.clear()

    item = rich.add_phase_item(1, 'فاز ۱', {'description': 'بتن‌ریزی', 'estimate_rate': 100})
    added = _merged_action(captured)
    price = rich.get_phase_item(item)['price_id']
    assert added.label == 'افزودن ردیف فاز' and added.undoable
    added.undo()
    assert rich.get_phase_item(item)['active'] == 0 and rich.get_price(price)['active'] == 0
    added.redo()
    assert rich.get_phase_item(item)['active'] == 1 and rich.get_price(price)['active'] == 1

    captured.clear()
    rich.save_price_rates(price, 1, 2, 3)
    edited = _merged_action(captured)
    assert edited.label == 'ویرایش قیمت'
    edited.undo()
    assert rich.get_price(price)['estimate_rate'] == 100
    edited.redo()
    assert rich.get_price(price)['estimate_rate'] == 1

    captured.clear()
    rich.delete_phase_item(item)
    deleted = _merged_action(captured)
    assert deleted.label == 'حذف ردیف فاز'
    deleted.undo()
    assert rich.get_phase_item(item)['active'] == 1
