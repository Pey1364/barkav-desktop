"""Right-to-left typing in the record window's text boxes («بابت» and the receipt text): see rtl_text187."""
import os
import tkinter as tk
from copy import deepcopy
from types import SimpleNamespace

import pytest

import rtl_text187 as rtl
from test_transaction_lifecycle_matrix import m, runtime, register, case_payload, CASES  # noqa: F401

gui_only = pytest.mark.skipif(os.environ.get('BARKAV_RUN_UI_TESTS') != '1', reason='GUI opt-in')
if os.environ.get('BARKAV_RUN_UI_TESTS') == '1':
    from test_stage18_7_record_fields import root  # noqa: F401
else:
    root = None

SENTENCE = 'چک آزمایشگاه خاک پاس کردن'


def key(name, char=''):
    return SimpleNamespace(keysym=name, char=char, state=0)


def box(root, text='', *, state='normal'):
    widget = tk.Text(root, height=4, width=60, wrap='word', undo=True)
    widget.pack()
    widget.insert('1.0', text)
    rtl.install(widget)
    widget.configure(state=state)
    root.update()
    return widget


def raw(widget):
    return widget._rtl_text187._read('1.0', 'end-1c')


# ---- the marks never leave the box ------------------------------------------------------------------------

def test_plain_drops_the_marks_and_nothing_else():
    assert rtl.plain(rtl.RLE + SENTENCE + rtl.PDF) == SENTENCE
    assert rtl.plain('abc ۱۲۳\n' + rtl.RLE + 'خط') == 'abc ۱۲۳\nخط'
    assert rtl.plain('') == ''


@gui_only
def test_every_line_starts_inside_the_embedding_and_the_value_has_no_marks(root):
    widget = box(root, 'خط اول\nخط دوم')
    assert raw(widget) == f'{rtl.RLE}خط اول\n{rtl.RLE}خط دوم'
    assert widget.get('1.0', 'end-1c') == 'خط اول\nخط دوم'
    assert widget.get('1.0', 'end') == 'خط اول\nخط دوم\n'
    assert widget.get('1.0', '1.3') == 'خط'  # the first index is the mark; get() leaves it out
    # text that is put in later by the program gets its marks too
    widget.delete('1.0', 'end')
    widget.insert('1.0', 'متن تازه\nخط ۲')
    root.update()
    assert raw(widget) == f'{rtl.RLE}متن تازه\n{rtl.RLE}خط ۲'
    assert widget.get('1.0', 'end-1c') == 'متن تازه\nخط ۲'
    widget.destroy()


@gui_only
def test_the_marks_are_no_edit_of_the_users(root):
    widget = box(root, SENTENCE)
    widget.edit_modified(False)
    widget.delete('1.0', 'end')
    widget.edit_modified(False)
    widget.insert('1.0', 'متن')
    widget.edit_modified(False)
    root.update()
    assert raw(widget).startswith(rtl.RLE)
    assert not widget.edit_modified()
    widget.destroy()


@gui_only
def test_a_read_only_box_is_marked_too_and_stays_read_only(root):
    widget = box(root, SENTENCE, state='disabled')
    assert raw(widget) == rtl.RLE + SENTENCE
    assert str(widget.cget('state')) == 'disabled'
    widget.configure(state='normal')
    widget.delete('1.0', 'end')
    widget.insert('1.0', 'متن دیگر')
    widget.configure(state='disabled')
    root.update()
    assert raw(widget) == rtl.RLE + 'متن دیگر' and str(widget.cget('state')) == 'disabled'
    widget.destroy()


# ---- the caret stays at the end, where the next letter appears ---------------------------------------------------

@gui_only
@pytest.mark.parametrize('name', ['Left', 'Right', 'Up', 'Down', 'Home', 'End', 'Prior', 'Next'])
def test_navigation_keys_leave_the_caret_at_the_end(root, name):
    widget = box(root, SENTENCE)
    widget.mark_set('insert', '1.4')
    assert widget._rtl_text187.on_key(key(name)) == 'break'
    assert widget.index('insert') == widget.index('end-1c')
    widget.destroy()


@gui_only
def test_a_click_leaves_the_caret_at_the_end_and_clears_a_selection(root):
    widget = box(root, SENTENCE)
    widget.tag_add('sel', '1.2', '1.6')
    widget.mark_set('insert', '1.3')
    assert widget._rtl_text187.on_click(SimpleNamespace(x=5, y=5)) == 'break'
    assert widget.index('insert') == widget.index('end-1c') and not widget.tag_ranges('sel')
    assert widget._rtl_text187.on_drag(SimpleNamespace(x=9, y=5)) == 'break'
    widget.destroy()


@gui_only
def test_a_read_only_box_keeps_its_own_clicks_and_keys(root):
    widget = box(root, SENTENCE, state='disabled')
    controller = widget._rtl_text187
    assert controller.on_click(SimpleNamespace(x=5, y=5)) is None
    assert controller.on_drag(SimpleNamespace(x=5, y=5)) is None
    assert controller.on_key(key('Left')) is None
    widget.destroy()


@gui_only
def test_typing_appends_and_a_letter_never_joins_the_first_word(root):
    widget = box(root, SENTENCE)
    widget.mark_set('insert', '1.0')  # as a click at the wrong end used to leave it
    widget._rtl_text187.on_key(key('x', 'x'))  # any key moves the caret back to the end first
    widget.insert('insert', 'ک')
    assert widget.get('1.0', 'end-1c') == SENTENCE + 'ک'
    widget.destroy()


@gui_only
def test_return_makes_a_new_line_inside_the_embedding_and_backspace_takes_it_back(root):
    widget = box(root, 'اول')
    controller = widget._rtl_text187
    assert controller.on_key(key('Return', '\r')) == 'break'
    root.update()
    assert raw(widget) == f'{rtl.RLE}اول\n{rtl.RLE}'
    widget.insert('end-1c', 'دوم')
    assert widget.get('1.0', 'end-1c') == 'اول\nدوم'
    for _ in 'دوم':
        assert controller.on_key(key('BackSpace')) is None  # the box deletes the letters itself
        widget.delete('end-2c', 'end-1c')
    assert controller.on_key(key('BackSpace')) == 'break'   # the line is empty: its mark and break go
    root.update()
    assert raw(widget) == f'{rtl.RLE}اول' and widget.get('1.0', 'end-1c') == 'اول'
    widget.destroy()


@gui_only
def test_select_all_then_typing_replaces_everything(root):
    widget = box(root, SENTENCE)
    widget.focus_force()
    widget.tag_add('sel', '1.0', 'end-1c')
    assert widget._rtl_text187.on_key(key('x', 'x')) is None  # the key itself goes on to Tk's own typing
    widget.tk.call('tk::TextInsert', widget._w, 'a')          # which replaces the selection, as a typed letter does
    root.update()
    assert widget.get('1.0', 'end-1c') == 'a'
    assert raw(widget) == rtl.RLE + 'a'
    widget.destroy()


@gui_only
def test_the_real_events_do_not_move_the_caret_into_the_middle(root):
    widget = box(root, SENTENCE)
    widget.focus_force()
    root.update()
    widget.event_generate('<KeyPress>', keysym='Home')
    widget.event_generate('<KeyPress>', keysym='Left')
    root.update()
    assert widget.index('insert') == widget.index('end-1c')
    widget.event_generate('<Button-1>', x=3, y=3)
    widget.event_generate('<ButtonRelease-1>', x=3, y=3)
    root.update()
    assert widget.index('insert') == widget.index('end-1c')
    widget.destroy()


@gui_only
def test_the_caret_is_drawn_just_left_of_the_text_and_follows_it(root, monkeypatch):
    monkeypatch.setattr(rtl, '_BLINK_MS', 10 ** 9)  # no blinking while the position is measured
    widget = box(root, '')
    widget.focus_force()
    root.update()
    caret = widget._rtl_text187.caret
    positions = []
    for letter in SENTENCE.replace(' ', ''):
        widget.insert('insert', letter)
        root.update()
        info = widget.dlineinfo('end-1c')
        assert caret.winfo_ismapped()
        # in the widget's own coordinates: two pixels wide, right before the first letter of the line
        left = caret.winfo_rootx() - widget.winfo_rootx()
        assert left + 2 <= info[0] and info[0] - (left + 2) <= 2, (left, info)
        positions.append(left)
    assert positions[-1] < positions[0]  # the text grows to the left and the caret goes with it
    widget.destroy()


@gui_only
def test_the_caret_is_hidden_when_the_box_is_not_focused_or_not_editable(root, monkeypatch):
    monkeypatch.setattr(rtl, '_BLINK_MS', 10 ** 9)
    widget = box(root, SENTENCE)
    widget.focus_force()
    root.update()
    assert widget._rtl_text187.caret.winfo_ismapped()
    other = tk.Entry(root)
    other.pack()
    other.focus_force()
    root.update()
    assert not widget._rtl_text187.caret.winfo_ismapped()
    widget.destroy()
    other.destroy()


# ---- the record window ----------------------------------------------------------------------------------------

def _boxes(window):
    found, stack = [], [window]
    while stack:
        item = stack.pop()
        stack.extend(item.winfo_children())
        if isinstance(item, tk.Text):
            found.append(item)
    return found


@gui_only
def test_the_record_window_boxes_are_typed_from_the_right_and_save_clean_text(root, runtime, monkeypatch):
    errors = []
    for name in ('showerror', 'showwarning'):
        monkeypatch.setattr(m.messagebox, name, lambda *a, **k: errors.append(a))
    monkeypatch.setattr(m, '_confirm_debt_warning_187', lambda *a: True)
    payload = case_payload(runtime, CASES[0])
    pid = register(runtime, payload)
    item = deepcopy(runtime.db.get_pending_item(pid))
    editor = m.v182.UnifiedPendingEditor182(root, item, runtime.rich, lambda: None)
    editor.update()
    boxes = _boxes(editor)
    assert len(boxes) == 2 and all(hasattr(item, '_rtl_text187') for item in boxes)
    about, caption = editor.about_text187, editor.caption
    for widget, text in ((about, 'بابت آزمایشی ۱۲۳ و abc'), (caption, 'متن رسید ۴۵')):
        widget.delete('1.0', 'end')
        widget.insert('insert', text)
        editor.update()
        assert raw(widget) == rtl.RLE + text and widget.get('1.0', 'end-1c') == text
    m._editor_approve_187(editor)
    assert not errors
    saved = runtime.db.get_pending_item(pid)['payload']
    assert saved['description'] == 'بابت آزمایشی ۱۲۳ و abc'
    assert saved['receipt_caption'] == 'متن رسید ۴۵'
    assert rtl.RLE not in str(saved) and rtl.PDF not in str(saved)


@gui_only
def test_the_multi_line_description_of_a_document_is_typed_from_the_right_too(root, runtime):
    variable = tk.StringVar(value='شرح قدیمی')
    form = SimpleNamespace(font_family='Segoe UI', font_size=11, _mark_manual=lambda key: None)
    widget = m._multiline_description_widget_187(root, variable, form, height=3)
    widget.pack()
    root.update()
    assert hasattr(widget, '_rtl_text187') and raw(widget) == rtl.RLE + 'شرح قدیمی'
    widget.delete('1.0', 'end')
    widget.insert('insert', 'شرح تازه abc')
    root.update()
    assert variable.get() == 'شرح تازه abc'  # the form's value is free of the marks
    variable.set('از برنامه')
    root.update()
    assert widget.get('1.0', 'end-1c') == 'از برنامه' and raw(widget) == rtl.RLE + 'از برنامه'
    widget.destroy()
