"""The loan details window is a BarkavWindow (themed title bar, Esc, contract size) and still shows the schedule."""
from test_loan_record_approve187 import _approved_loan  # noqa: F401
from test_transaction_lifecycle_matrix import m, runtime  # noqa: F401
from test_stage18_7_record_fields import root  # noqa: F401


def test_the_loan_details_window_is_a_barkav_window_that_lists_the_installments(root, runtime):
    _pid, loan_id = _approved_loan(runtime)
    window = m.LoanDetailsWindow187(root, loan_id)
    try:
        root.update()
        assert isinstance(window, m.BarkavWindow)
        assert len(window.installment_tree.get_children()) == 2
        assert window.winfo_children() and window.body.winfo_children()
    finally:
        window.destroy()
