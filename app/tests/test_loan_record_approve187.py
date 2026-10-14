"""«تأیید و ثبت تغییرات» in the record window of a loan that already exists saves it through the dashboard's loan tab
(it used to say «فرم اصلی تسهیلات برای همگام‌سازی رکورد پیدا نشد»)."""
import tkinter as tk

from test_transaction_lifecycle_matrix import m, runtime, register  # noqa: F401
from test_stage18_7_record_fields import root  # noqa: F401

LOAN = dict(v18_title='ورودی', v18_subtype='تسهیلات', detected_type='INCOME', amount=1000,
            event_date_shamsi='1405/07/08', loan_total_amount=1000, loan_bank='بانک آزمون',
            loan_start_date='1405/07/08', installment_count=2, interest_rate=0)


class Dashboard(tk.Frame):
    """Stands in for the dashboard that owns the loan tab and saves loans."""
    def __init__(self, parent):
        super().__init__(parent)
        self.saved = []

    def _save_loan_edit_187(self, row, payload):
        self.saved.append(dict(row))
        return 'loan synced'


def _approved_loan(runtime):
    pid = register(runtime, dict(LOAN))
    m.v18.submit_v18(pid, runtime.db.get_pending_item(pid)['payload'], runtime.rich)
    with runtime.db.read() as con:
        return pid, con.execute('SELECT loan_id FROM loans').fetchone()[0]


def _errors(monkeypatch):
    errors = []
    monkeypatch.setattr(m.messagebox, 'showerror', lambda *args, **kwargs: errors.append(args))
    return errors


def test_the_record_window_of_an_existing_loan_saves_through_the_dashboard(root, runtime, monkeypatch):
    pid, loan_id = _approved_loan(runtime)
    errors = _errors(monkeypatch)
    dashboard = Dashboard(root)
    form = m.v182.UnifiedPendingEditor182(dashboard, runtime.db.get_pending_item(pid), runtime.rich, lambda: None)
    form.approve()
    root.update()
    assert errors == []
    assert dashboard.saved == [{'loan_id': loan_id}]
    assert form._approved_editor_182 and str(form.msg.get()).startswith('ثبت شد')


def test_without_a_dashboard_above_it_the_record_window_still_says_so(root, runtime, monkeypatch):
    pid, _loan_id = _approved_loan(runtime)
    errors = _errors(monkeypatch)
    form = m.v182.UnifiedPendingEditor182(root, runtime.db.get_pending_item(pid), runtime.rich, lambda: None)
    form.approve()
    assert len(errors) == 1 and 'فرم اصلی تسهیلات' in errors[0][1]
    assert not getattr(form, '_approved_editor_182', False)


class RealDashboard(tk.Frame):
    """The dashboard's own loan saver (`Stage187Dashboard._save_loan_edit_187`) on a stand-in that can refresh."""
    _save_loan_edit_187 = m.Stage187Dashboard._save_loan_edit_187

    def refresh_all(self):
        pass


def test_the_real_loan_saver_updates_the_loan_in_place_from_the_record_window(root, runtime, monkeypatch):
    pid, loan_id = _approved_loan(runtime)
    errors = _errors(monkeypatch)
    monkeypatch.setattr(m, 'show_toast', lambda *args, **kwargs: None)
    with runtime.db.read() as con:
        before = [con.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                  for table in ('loans', 'loan_installments', 'transactions')]
    form = m.v182.UnifiedPendingEditor182(RealDashboard(root), runtime.db.get_pending_item(pid), runtime.rich, lambda: None)
    form.vars['loan_bank'].set('بانک اصلاح‌شده')
    form.approve()
    root.update()
    assert errors == []
    with runtime.db.read() as con:
        after = [con.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                 for table in ('loans', 'loan_installments', 'transactions')]
        lender = con.execute('SELECT lender_name FROM loans WHERE loan_id=?', (loan_id,)).fetchone()[0]
    assert after == before and lender == 'بانک اصلاح‌شده'
    assert runtime.db.get_pending_item(pid)['payload']['loan_bank'] == 'بانک اصلاح‌شده'
