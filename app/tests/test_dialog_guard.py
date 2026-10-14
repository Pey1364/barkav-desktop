"""The conftest guard: a test that reaches a real dialog fails fast, it never waits.

Every test here first checks that the guard is what it is about to call. If
conftest.py ever stops installing it, these must fail on that check and not turn
into the hang they exist to prevent.
"""

from __future__ import annotations

import time

import pytest

tk = pytest.importorskip('tkinter')


def _assert_guard_active(function) -> None:
    assert getattr(function, 'dialog_guard', False), 'the conftest dialog guard is not active'


@pytest.fixture()
def root():
    try:
        window = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f'no usable display: {exc}')
    window.withdraw()
    yield window
    window.destroy()


def test_a_dialog_call_fails_fast_naming_the_call_its_title_and_message():
    from tkinter import messagebox

    _assert_guard_active(messagebox.showerror)
    with pytest.raises(AssertionError) as caught:
        messagebox.showerror('خروجی', "got an unexpected keyword argument 'summary_lines'", parent=None)
    text = str(caught.value)
    assert 'messagebox.showerror' in text and 'خروجی' in text and 'summary_lines' in text


def test_every_public_stdlib_dialog_function_is_guarded():
    from tkinter import colorchooser, filedialog, messagebox, simpledialog

    for module in (messagebox, filedialog, simpledialog, colorchooser):
        names = [name for name in dir(module)
                 if name.startswith(('ask', 'show')) and callable(getattr(module, name))]
        assert names, module
        for name in names:
            _assert_guard_active(getattr(module, name))


def test_the_native_dialog_class_is_guarded_for_names_imported_before_the_swap():
    from tkinter import commondialog, messagebox

    _assert_guard_active(commondialog.Dialog.show)
    with pytest.raises(AssertionError, match=r'Message\.show'):
        messagebox.Message(title='خروجی', message='m').show()


def test_the_incident_shape_fails_the_test_with_the_original_error_in_it():
    """A stale stub raises TypeError, the code under test reports it through
    showerror, and the report used to wait for a click for ever."""

    from tkinter import messagebox

    def export(pdf_writer):
        try:
            pdf_writer('out.pdf', summary_lines=['جهت ارائه به: سایر'])
        except Exception as exc:
            messagebox.showerror('خروجی', str(exc))

    _assert_guard_active(messagebox.showerror)
    with pytest.raises(AssertionError, match="unexpected keyword argument 'summary_lines'"):
        export(lambda path: None)


def test_a_test_can_still_stub_a_dialog_itself(monkeypatch):
    from tkinter import messagebox

    monkeypatch.setattr(messagebox, 'askyesno', lambda *args, **options: True)
    assert messagebox.askyesno('عنوان', 'پیام') is True


def test_a_modal_wait_nobody_answers_gives_up_instead_of_blocking(root, monkeypatch):
    _assert_guard_active(tk.Misc.wait_window)
    monkeypatch.setattr(tk.Misc.wait_window, 'limit_seconds', 0.2)
    dialog = tk.Toplevel(root)

    started = time.monotonic()
    with pytest.raises(AssertionError, match='nobody can answer'):
        dialog.wait_window()
    assert time.monotonic() - started < 10
    assert not dialog.winfo_exists(), 'the window nobody answered is closed, not left open'


def test_a_modal_wait_that_is_answered_in_time_is_left_alone(root):
    _assert_guard_active(tk.Misc.wait_window)
    dialog = tk.Toplevel(root)
    dialog.after(30, dialog.destroy)
    dialog.wait_window()

    pending = [root.tk.call('after', 'info', event) for event in root.tk.splitlist(root.tk.call('after', 'info'))]
    assert not any('give_up' in str(script) for script in pending), 'the give-up timer was cancelled'
