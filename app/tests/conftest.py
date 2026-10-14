"""Fail a test that reaches a dialog nobody can answer, instead of blocking the run.

A modal box - Windows' native MessageBox, Tk's own on X11, a simpledialog, a file
chooser - waits for a click that never comes in a test run. When the code under
test lands on an error path and calls messagebox.showerror, the test never
finishes, every later test is held back and the box is left on the desktop.
test_pdf_export_reverses_columns_to_match_the_on_screen_rtl_order did exactly
that once its stub stopped matching what _write_export passes: the TypeError went
to a showerror the test had not patched and a full run stopped at 46 %.

For the length of every test the stdlib dialog functions raise AssertionError
naming the call (title and message included), and Misc.wait_window - what the
themed barkav_ui boxes block in - gives up after WAIT_LIMIT_SECONDS. A test that
needs a particular answer patches that one function itself, as the export tests
do; that replaces the guard for the rest of the test.
"""

from __future__ import annotations

import pytest

try:
    import tkinter as tk
    from tkinter import colorchooser, commondialog, filedialog, messagebox, simpledialog
except ImportError:  # no Tk on this machine: the tests that need none still run
    tk = None

WAIT_LIMIT_SECONDS = 20

_DIALOG_FUNCTIONS = {
    'messagebox': ('showinfo', 'showwarning', 'showerror', 'askquestion', 'askokcancel',
                   'askyesno', 'askyesnocancel', 'askretrycancel'),
    'filedialog': ('asksaveasfilename', 'asksaveasfile', 'askopenfilename', 'askopenfilenames',
                   'askopenfile', 'askopenfiles', 'askdirectory'),
    'simpledialog': ('askstring', 'askinteger', 'askfloat'),
    'colorchooser': ('askcolor',),
}


def _refusal(call: str, args=(), options=None) -> AssertionError:
    shown = [repr(arg) for arg in args]
    shown += [f'{key}={value!r}' for key, value in (options or {}).items() if key != 'parent']
    text = ', '.join(shown)
    if len(text) > 400:
        text = text[:400] + '...'
    return AssertionError(
        f'a test reached a real dialog nobody can answer: {call}({text}). '
        'Patch it in the test, so a failure is an assertion and not a box that holds the run.')


def _refuse(call: str):
    def refuse(*args, **options):
        raise _refusal(call, args, options)

    refuse.dialog_guard = True
    return refuse


def _refuse_show(self, **options):
    # Every native box (messagebox, filedialog, colorchooser) ends here, also the
    # ones a module imported by name before the functions above were swapped.
    merged = {**getattr(self, 'options', {}), **options}
    raise _refusal(f'{type(self).__name__}.show',
                   options={key: merged[key] for key in ('title', 'message') if key in merged})


_refuse_show.dialog_guard = True


def _bounded(wait_window):
    def bounded_wait_window(self, window=None):
        target = self if window is None else window
        gave_up = []

        def give_up():
            gave_up.append(True)
            try:
                target.destroy()
            except Exception:  # a destroy() that misbehaves must not keep the run blocked
                target.tk.call('destroy', str(target))

        try:
            # On the root: its after-commands outlive the dialog being waited on.
            root = self
            while getattr(root, 'master', None) is not None:
                root = root.master
            timer = root.after(int(bounded_wait_window.limit_seconds * 1000), give_up)
        except Exception:  # not a live widget: nothing to bound
            return wait_window(self, window)
        try:
            wait_window(self, window)
        finally:
            try:
                root.after_cancel(timer)
            except tk.TclError:  # the interpreter was destroyed meanwhile
                pass
        if gave_up:
            raise AssertionError(
                f'a test waited {bounded_wait_window.limit_seconds:g} s for {target} to close: '
                'nobody can answer a modal window here. Patch the dialog the code under test opens.')

    bounded_wait_window.limit_seconds = WAIT_LIMIT_SECONDS
    bounded_wait_window.dialog_guard = True
    return bounded_wait_window


@pytest.fixture(autouse=True)
def _no_dialog_waits_for_a_person(monkeypatch):
    if tk is not None:
        modules = {'messagebox': messagebox, 'filedialog': filedialog,
                   'simpledialog': simpledialog, 'colorchooser': colorchooser}
        for module_name, names in _DIALOG_FUNCTIONS.items():
            for name in names:
                if hasattr(modules[module_name], name):
                    monkeypatch.setattr(modules[module_name], name, _refuse(f'{module_name}.{name}'))
        monkeypatch.setattr(commondialog.Dialog, 'show', _refuse_show)
        monkeypatch.setattr(tk.Misc, 'wait_window', _bounded(tk.Misc.wait_window))
    yield
