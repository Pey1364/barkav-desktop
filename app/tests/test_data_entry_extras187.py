"""«رفتن به رکورد متناظر» and the deleted records that stay in the database."""
import os
import pytest
from test_cheque_resolution_lifecycle187 import _issue, _resolve
from test_transaction_lifecycle_matrix import m, runtime, register, case_payload, CASES
import data_entry_extras_ui as extras
from transaction_lifecycle import TransactionLifecycle


def test_a_resolved_cheque_row_offers_the_issue_and_the_resolution_record(runtime):
    issue, cheque_id = _issue(runtime)
    row = runtime.db.get_cheque(cheque_id)
    assert extras.records_for_row(runtime.db, row) == [(extras.ISSUE_LABEL, issue)]
    resolution = _resolve(runtime, cheque_id, 'پاس‌شده', 2)
    assert extras.records_for_row(runtime.db, row) == [(extras.ISSUE_LABEL, issue),
                                                       (extras.RESOLUTION_LABEL, resolution)]


def test_a_plain_row_goes_to_its_one_record(runtime):
    payload = case_payload(runtime, CASES[0])
    pid = register(runtime, payload)
    m.v18.submit_v18(pid, payload, runtime.rich)
    with runtime.db.read() as con:
        expense = dict(con.execute('SELECT * FROM expenses').fetchone())
    assert extras.records_for_row(runtime.db, expense) == [('رکورد ثبت', pid)]


def _center(runtime, pushed=None):
    from types import SimpleNamespace
    return SimpleNamespace(rich=runtime.rich, refresh=lambda: None, on_posted=None,
                           action=SimpleNamespace(set=lambda text: None),
                           _push_history=(pushed.append if pushed is not None else (lambda entry: None)))


def _approved(runtime, case=0, message_id=1):
    payload = case_payload(runtime, CASES[case])
    pid = register(runtime, payload, message_id)
    m.v18.submit_v18(pid, payload, runtime.rich)
    return pid


def test_hiding_a_record_keeps_it_and_its_financial_effect(runtime):
    pid = _approved(runtime)
    cash = runtime.db.snapshot().cash_balance
    pushed = []

    extras.hide_rows(_center(runtime, pushed), [pid])

    assert runtime.db.get_pending_item(pid)['status'] == 'APPROVED'
    assert runtime.db.snapshot().cash_balance == cash
    assert [row['pending_id'] for row in extras.hidden_rows(runtime.db, runtime.rich)] == [pid]
    # it can be undone and done again
    entry = pushed[-1]
    entry['action'].undo()
    assert extras.hidden_rows(runtime.db, runtime.rich) == []
    entry['action'].redo()
    assert [row['pending_id'] for row in extras.hidden_rows(runtime.db, runtime.rich)] == [pid]


def test_a_hidden_record_comes_back_with_the_status_it_had(runtime):
    approved = _approved(runtime)
    rejected = _approved(runtime, 1, 2)
    runtime.approval.reject(rejected)
    extras.hide_rows(_center(runtime), [approved, rejected])

    shown = {row['pending_id']: row['status'] for row in extras.hidden_rows(runtime.db, runtime.rich)}
    assert shown == {approved: 'APPROVED', rejected: 'REJECTED'}

    extras.show_rows_again(_center(runtime), [approved, rejected])

    assert extras.hidden_rows(runtime.db, runtime.rich) == []
    assert runtime.db.get_pending_item(approved)['status'] == 'APPROVED'
    assert runtime.db.get_pending_item(rejected)['status'] == 'REJECTED'


def test_a_record_deleted_completely_is_in_no_category_but_stays_in_the_database(runtime):
    import data_entry_read_service as service
    pid = _approved(runtime)
    cash = runtime.db.snapshot().cash_balance
    TransactionLifecycle(runtime.db).change_many([pid], permanent=True)

    assert runtime.db.get_pending_item(pid) is not None  # the database keeps it
    assert runtime.db.snapshot().cash_balance != cash  # its financial effect is gone
    assert extras.hidden_rows(runtime.db, runtime.rich) == []
    assert service.hidden_count(runtime.db, runtime.rich.hidden_review_ids()) == 0
    assert service.hidden_count(runtime.db) == 0
    assert extras.unhide(runtime.db, [pid]) == 0  # nothing brings it back into the table
    assert pid not in {row['pending_id'] for row in runtime.approval.list_reviews()}


def test_the_hidden_count_is_apart_from_the_other_counters(runtime):
    import data_entry_read_service as service
    pid = _approved(runtime)
    other = register(runtime, case_payload(runtime, CASES[1]), 2)
    before = service.pending_counts(runtime.db, runtime.rich.hidden_review_ids())
    extras.hide_rows(_center(runtime), [pid])
    after = service.pending_counts(runtime.db, runtime.rich.hidden_review_ids())
    assert after['approved'] == before['approved'] - 1 and after['total'] == before['total'] - 1
    assert service.hidden_count(runtime.db, runtime.rich.hidden_review_ids()) == 1
    assert service.hidden_count(runtime.db) == 1
    assert runtime.db.get_pending_item(other)['status'] == 'PENDING_REVIEW'  # waiting for review, not hidden


def test_delete_in_data_entry_hides_by_default_and_deletes_completely_when_asked(runtime, monkeypatch):
    import transaction_lifecycle_ui as ui
    from transaction_lifecycle import TransactionLifecycle as T
    kept = _approved(runtime)
    gone = _approved(runtime, 2, 2)
    snap = runtime.db.snapshot()
    cash = (snap.cash_balance, snap.construction_cost)
    state = lambda: (runtime.db.snapshot().cash_balance, runtime.db.snapshot().construction_cost)
    center = _center(runtime)
    center.tk = object()  # a table with a window asks the new question (the test answers it)
    rows = lambda pid: [runtime.db.get_pending_item(pid)]

    monkeypatch.setattr(extras, 'ask_delete', lambda *a, **k: extras.DeleteDecision('hide'))
    ui.delete_rows(center, rows(kept), runtime.db, m.messagebox, kind='delete')
    assert runtime.db.get_pending_item(kept)['status'] == 'APPROVED'
    assert state() == cash

    monkeypatch.setattr(extras, 'ask_delete', lambda *a, **k: extras.DeleteDecision('delete'))
    ui.delete_rows(center, rows(gone), runtime.db, m.messagebox, kind='delete')
    assert runtime.db.get_pending_item(gone)['status'] == 'REJECTED'
    assert T(runtime.db).get(gone)['state'] == 'PURGED'
    assert state() != cash

    monkeypatch.setattr(extras, 'ask_delete', lambda *a, **k: None)
    ui.delete_rows(center, rows(kept), runtime.db, m.messagebox, kind='delete')  # cancelled
    assert runtime.db.get_pending_item(kept)['status'] == 'APPROVED'


def test_reject_in_the_table_still_moves_rows_to_the_rejected_pile(runtime, monkeypatch):
    import transaction_lifecycle_ui as ui
    from transaction_lifecycle import TransactionLifecycle as T
    pid = _approved(runtime)
    monkeypatch.setattr(m.messagebox, 'askyesno', lambda *a, **k: True)
    ui.delete_rows(_center(runtime), [runtime.db.get_pending_item(pid)], runtime.db, m.messagebox)
    assert runtime.db.get_pending_item(pid)['status'] == 'REJECTED'
    assert T(runtime.db).get(pid)['state'] == 'REJECTED'  # restorable, not purged


# --- the real dashboard (opt-in): the menus a user right-clicks ---------------------------------
gui_only = pytest.mark.skipif(os.environ.get('BARKAV_RUN_UI_TESTS') != '1', reason='GUI opt-in')
if os.environ.get('BARKAV_RUN_UI_TESTS') == '1':
    from test_transaction_review_ui import window, _popup, _show_tab, _right_click, _labels  # noqa: F401
else:
    window = None


@gui_only
def test_right_click_on_a_cheque_row_goes_to_the_chosen_record_and_negative_control(runtime, window, monkeypatch):
    shown = _popup(monkeypatch)
    issue, cheque_id = _issue(runtime)
    resolution = _resolve(runtime, cheque_id, 'پاس‌شده', 2)
    window.refresh_all()
    table = window.cheque_table
    _show_tab(window, table)
    iid = next(i for i, r in table._iid_to_row.items() if r.get('cheque_id') == cheque_id)

    table.tree.selection_set(())
    shown.clear()
    _right_click(window, table.tree, iid)
    assert dict(_labels(shown[-1])).get(extras.GO_LABEL) == 'normal'

    asked = []
    monkeypatch.setattr(extras, 'choose_record', lambda parent, options: asked.append(options) or resolution)
    shown[-1].invoke(extras.GO_LABEL)
    window.update()
    assert [label for label, _pid in asked[0]] == [extras.ISSUE_LABEL, extras.RESOLUTION_LABEL]
    center = window.approval_center
    assert window.notebook.select() == str(window.approval_tab)
    selected = [center.table.iid_to_row[i]['pending_id'] for i in center.table.tree.selection()]
    assert selected == [resolution]

    shown.clear()
    table.tree.selection_set(())
    _right_click(window, table.tree)  # below the rows: nothing selected
    assert dict(_labels(shown[-1])).get(extras.GO_LABEL) == 'disabled'


@gui_only
def test_the_hidden_category_lists_hidden_rows_in_cream_and_shows_them_again(runtime, window, monkeypatch):
    pid = _approved(runtime)
    window.refresh_all()
    center = window.approval_center
    center.filter.set('همه'); center.refresh(); window.update()
    assert pid in {r['pending_id'] for r in center.table.iid_to_row.values()}
    assert extras.HIDDEN_LABEL in center.status_filter_combo187['values']
    assert center.data_entry_count_labels187['hidden'].cget('text') in ('۰', '0')

    extras.hide_rows(center, [pid])
    window.update()
    assert pid not in {r['pending_id'] for r in center.table.iid_to_row.values()}
    assert center.data_entry_count_labels187['hidden'].cget('text') == m.fa(1)

    center.table.menu.invoke(extras.HIDDEN_MENU_LABEL)
    window.update()
    assert center.status_filter187.get() == extras.HIDDEN_LABEL
    iid = next(i for i, r in center.table.iid_to_row.items() if r['pending_id'] == pid)
    assert 'status_hidden' in center.table.tree.item(iid, 'tags')
    assert center.table.iid_to_row[iid]['status'] == 'APPROVED'

    center.table.tree.selection_set(iid)
    window.update()
    center.table.menu.tk.call(str(center.table.menu.cget('postcommand')))
    assert dict(_labels(center.table.menu)).get(extras.SHOW_AGAIN_LABEL) == 'normal'
    center.table.menu.invoke(extras.SHOW_AGAIN_LABEL)
    window.update()
    assert runtime.db.get_pending_item(pid)['status'] == 'APPROVED'
    center.filter.set('همه'); center.refresh(); window.update()
    assert pid in {r['pending_id'] for r in center.table.iid_to_row.values()}


@gui_only
def test_the_delete_question_has_both_choices_and_the_default_only_hides(runtime, window, monkeypatch):
    pid = _approved(runtime)
    window.refresh_all()
    center = window.approval_center

    def walk(widget):
        yield widget
        for child in widget.winfo_children():
            yield from walk(child)

    def answer(target_action):
        dialog = next(w for w in walk(window) if getattr(w, '_ask_delete_accept187', None) is not None)
        if target_action:
            dialog._ask_delete_action187.set(target_action)
        dialog._ask_delete_accept187()

    def ask(target_action=None):
        window.after(300, lambda: answer(target_action))
        return extras.ask_delete(center, [runtime.db.get_pending_item(pid)], messagebox=m.messagebox)

    assert ask() == extras.DeleteDecision('hide', False)
    assert ask('delete') == extras.DeleteDecision('delete', False)
