"""Resolve linked receipts before deleting a contractor or sales contract."""
from __future__ import annotations
from transaction_lifecycle import TransactionLifecycle, LifecycleDecision


def delete_sale(db,sale_id):
    from revenue_service import RevenueService
    lifecycle=TransactionLifecycle(db)
    with db.read() as con:
        rows=[dict(r) for r in con.execute("SELECT * FROM received_payments WHERE sale_id=? AND status!='CANCELLED' ORDER BY created_at DESC,rowid DESC",(sale_id,))]
    ids=[lifecycle.pending_for_row(row) for row in rows]
    with db.atomic():
        lifecycle.change_many(ids)
        RevenueService(db).cancel_sale(sale_id,source='GUI_LIFECYCLE',actor_id='GUI')
    return len(ids)


def delete_contractors(db,contract_ids):
    from contractor_store_stage18_7 import load_contracts,delete_contracts,save_contracts
    lifecycle=TransactionLifecycle(db)
    selected={str(i) for i in contract_ids}
    original=[c for c in load_contracts() if str(c.get('contract_id')) in selected]
    import json
    provenance=json.loads(db.get_setting('contract_actual_field_provenance') or '{}')
    for contract in original:
        refs=[str(row.get('plan_ref') or '') for row in contract.get('rows') or [] if row.get('plan_ref')]
        with db.read() as con:
            for ref in refs:
                lines=con.execute("SELECT phase_item_id FROM rich_phase_items WHERE plan_ref=? AND actual_source='CONTRACTS'",(ref,)).fetchall()
                if any(str(line['phase_item_id']) not in provenance for line in lines):
                    raise LifecycleDecision('قرارداد قدیمی مقادیر واقعی را تغییر داده و سابقه مقادیر قبلی ندارد؛ تعیین تکلیف قیمت لازم است.')
    payments=[p for c in original for p in c.get('payments') or []]
    if any(not p.get('pending_id') for p in payments):
        raise LifecycleDecision('رسید قرارداد فاقد رکورد مبدا است؛ پیش از حذف قرارداد تعیین تکلیف لازم است.')
    ids=list(dict.fromkeys(str(p['pending_id']) for p in payments))
    with db.read() as con:
        stamps={r['pending_id']:(r['created_at'],r['rowid']) for r in con.execute('SELECT rowid,pending_id,created_at FROM pending_items')}
    ids.sort(key=lambda pid:stamps.get(pid,('',0)),reverse=True)
    try:
        with db.atomic():
            lifecycle.change_many(ids)
            removed=delete_contracts(list(selected))
            from cost_allocation_stage18_7 import apply_actuals
            apply_actuals(db)
            return removed
    except Exception:
        # Restore only selected contracts, retaining unrelated file changes.
        others=[c for c in load_contracts() if str(c.get('contract_id')) not in selected]
        save_contracts(others+original)
        raise


def delete_contractors_with_history(db, contract_ids):
    """Delete contracts as one safe Undo/Redo action, including linked money.

    Contract JSON and SQLite are separate stores. The UI deliberately suspends
    the generic row journal for this lifecycle operation, because receipt
    effects must be restored through ``TransactionLifecycle`` rather than by
    replaying stale SQL rows. This helper records the corresponding business
    inverse as one action so deleting a contract cannot invalidate the prior
    file action in history.
    """

    import file_journal
    import row_journal
    from action_history import HistoryAction, UndoRefused
    from contractor_store_stage18_7 import load_contracts, store_path

    selected = list(dict.fromkeys(str(value) for value in contract_ids if str(value)))
    path = store_path()
    before = file_journal._read(path)
    if before is None:
        raise LifecycleDecision('فایل قراردادها در دسترس نیست؛ حذف انجام نشد.')
    originals = [contract for contract in load_contracts()
                 if str(contract.get('contract_id') or '') in set(selected)]
    payment_ids = list(dict.fromkeys(
        str(payment['pending_id'])
        for contract in originals
        for payment in contract.get('payments') or []
        if payment.get('pending_id')
    ))

    with row_journal.suspended():
        removed = delete_contractors(db, selected)
    after = file_journal._read(path)
    if not removed or before == after:
        return removed, None

    state = {'deleted': after, 'restored': before}

    def restore_deleted() -> None:
        if file_journal._read(path) != state['deleted']:
            raise UndoRefused('فایل قراردادها پس از حذف دوباره تغییر کرده است.')
        try:
            # The parent contracts must exist before the lifecycle can restore
            # receipt links into them.
            file_journal._write(path, before)
            with row_journal.suspended(), db.atomic():
                lifecycle = TransactionLifecycle(db)
                if payment_ids:
                    lifecycle.change_many(payment_ids, restore=True)
                from cost_allocation_stage18_7 import apply_actuals
                apply_actuals(db)
        except Exception as exc:
            try:
                file_journal._write(path, state['deleted'])
            except Exception as rollback_exc:
                raise UndoRefused(
                    f'بازگردانی کامل نشد و فایل حذف‌شده هم بازیابی نشد: {rollback_exc}') from exc
            raise UndoRefused(f'آثار مالی قرارداد به‌طور امن بازنگشتند: {exc}') from exc
        state['restored'] = file_journal._read(path)

    def delete_restored() -> None:
        if file_journal._read(path) != state['restored']:
            raise UndoRefused('فایل قراردادها پس از بازگردانی دوباره تغییر کرده است.')
        try:
            with row_journal.suspended():
                delete_contractors(db, selected)
        except Exception as exc:
            try:
                file_journal._write(path, state['restored'])
            except Exception as rollback_exc:
                raise UndoRefused(
                    f'اجرای دوباره کامل نشد و فایل بازگردانی‌شده هم بازیابی نشد: {rollback_exc}') from exc
            raise UndoRefused(f'حذف دوبارهٔ قرارداد به‌طور امن انجام نشد: {exc}') from exc
        state['deleted'] = file_journal._read(path)

    label = ('حذف قرارداد پیمانکار' if removed == 1
             else f'حذف {removed} قرارداد پیمانکار')
    return removed, HistoryAction(label, restore_deleted, delete_restored)
