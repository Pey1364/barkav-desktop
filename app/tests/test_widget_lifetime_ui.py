"""Close real active windows without fixture-wide timer/cache workarounds."""
import os
import tkinter as tk
import pytest
from test_transaction_lifecycle_matrix import runtime, m, register, case_payload, CASES

pytestmark = pytest.mark.skipif(os.environ.get("BARKAV_RUN_UI_TESTS") != "1", reason="GUI opt-in")


def capture_errors(root):
    errors = []
    root.report_callback_exception = lambda cls, exc, tb: errors.append(str(exc))
    root.tk.eval("set lifetime_bgerrors {}; proc bgerror {message} {lappend ::lifetime_bgerrors $message}")
    return errors


def assert_no_background_errors(root, errors):
    root.tk.call("update")
    assert not errors
    assert not root.tk.splitlist(root.tk.getvar("lifetime_bgerrors"))


@pytest.mark.parametrize("kind", ["record", "wizard"])
def test_standalone_active_form_closes_before_image_fit_or_idle(runtime, kind):
    root = tk.Tk(); root.withdraw()
    errors = capture_errors(root)
    pid = register(runtime, case_payload(runtime, CASES[0]))
    row = runtime.db.get_pending_item(pid)
    try:
        if kind == "record":
            form = m.v182.UnifiedPendingEditor182(root, row, runtime.rich, lambda: None)
        else:
            form = m.v182.TransactionWizard182(root, row, runtime.rich, lambda: None, lambda: None)
        assert root._barkav_callback_cleanup
        commands = set(form._tclCommands or ())
        owned = [job for job in root.tk.call("after", "info")
                 if root.tk.splitlist(root.tk.call("after", "info", job)[0])[0] in commands]
        if kind == "record": assert owned, "must exercise the inherited image-fit timer"
        form.destroy()
        assert not set(owned) & set(root.tk.call("after", "info"))
        root.after(160, root.quit)
        root.mainloop()
        assert_no_background_errors(root, errors)
    finally:
        root.destroy()
    assert_no_background_errors(root, errors)


def test_reopening_dashboard_repaints_and_closes_without_cache_or_timer_clear(runtime, monkeypatch):
    from barkav_ui import row_overlay
    import row_journal, file_journal
    monkeypatch.setattr(m.v186.v185, "fetch_tgju_usd_toman", lambda **kw: (70000, "2026-10-01"))
    for cycle in range(2):
        root = m.Stage187Dashboard()
        root.title("BARKAV | آزمون بستن پنجره | دادهٔ موقت")
        errors = capture_errors(root)
        try:
            root.update()
            table = root.approval_center.table.tree
            row_overlay.decorate(table)
            root.update_idletasks()
            interpreter = id(root.tk)
            # Exercise actual corner/check photos even if this project's first
            # table has no selected rows when it opens.
            photos = row_overlay._corner_images("#00AABB", "#101010", 6, 2, table)
            assert all(photo.tk is root.tk for photo in photos)
            assert root.tk.call("after", "info"), "must close with scheduled application jobs"
        finally:
            root.destroy()
            row_journal.uninstall(); file_journal.uninstall()
        assert not root.tk.call("after", "info"), "application-owned jobs must all be removed"
        assert not any(key[0] == interpreter for key in row_overlay._images)
        assert_no_background_errors(root, errors)
