"""Clipboard commands for the application's text and numeric fields."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

_TAG = 'BarkavFieldClipboard'
_FIELDS = (tk.Entry, ttk.Entry, ttk.Combobox, tk.Spinbox, ttk.Spinbox, tk.Text)
_READOUTS = (tk.Label, ttk.Label, tk.Message)


def _writable(widget):
    if isinstance(widget, _READOUTS):
        return False
    return str(widget.cget('state')) not in {'readonly', 'disabled'}


def action(widget, command):
    """Respect computed/disabled values; readonly choices accept valid items."""
    custom = getattr(widget, '_barkav_clipboard_action187', None)
    if custom:
        return custom(command)
    try:
        text_field = isinstance(widget, tk.Text)
        if command == 'select':
            if text_field:
                widget.tag_add('sel', '1.0', 'end-1c')
            else:
                widget.selection_range(0, 'end')
            return 'break'
        if command in {'copy', 'cut'}:
            if isinstance(widget, _READOUTS):
                variable = str(widget.cget('textvariable') or '')
                text = str(widget.getvar(variable)) if variable else str(widget.cget('text'))
                selected = False
            elif text_field:
                selected = bool(widget.tag_ranges('sel'))
                text = widget.get('sel.first', 'sel.last') if selected else widget.get('1.0', 'end-1c')
            else:
                selected = bool(widget.selection_present())
                text = widget.get()[widget.index('sel.first'):widget.index('sel.last')] if selected else widget.get()
            widget.clipboard_clear()
            widget.clipboard_append(text)
            if command == 'cut' and selected and _writable(widget):
                widget.delete('sel.first', 'sel.last') if text_field else widget.delete(
                    widget.index('sel.first'), widget.index('sel.last'))
        elif command == 'paste':
            text = widget.clipboard_get()
            if isinstance(widget, ttk.Combobox) and str(widget.cget('state')) == 'readonly':
                if text in tuple(str(item) for item in widget.cget('values')):
                    widget.set(text)
                    widget.event_generate('<<ComboboxSelected>>')
                else:
                    widget.bell()
            elif _writable(widget):
                if text_field:
                    if widget.tag_ranges('sel'):
                        widget.delete('sel.first', 'sel.last')
                    widget.insert('insert', text)
                else:
                    if widget.selection_present():
                        widget.delete(widget.index('sel.first'), widget.index('sel.last'))
                    elif getattr(widget, '_barkav_numeric_append', False):
                        widget.icursor('end')
                    widget.insert('insert', text)
    except tk.TclError:
        # An empty clipboard or absent selection is an ordinary no-op.
        return 'break'
    return 'break'


def install(root):
    """Install once per interpreter; cover present and subsequently mapped fields."""
    root = root._root()
    if getattr(root, '_barkav_field_clipboard', False):
        return
    root._barkav_field_clipboard = True

    def attach(widget):
        if isinstance(widget, (*_FIELDS, *_READOUTS)) and _TAG not in widget.bindtags():
            widget.bindtags((_TAG, *widget.bindtags()))

    def key(event):
        command = {65: 'select', 67: 'copy', 86: 'paste', 88: 'cut'}.get(event.keycode)
        command = command or {'a': 'select', 'c': 'copy', 'v': 'paste', 'x': 'cut'}.get(
            str(event.keysym).lower())
        return action(event.widget, command) if command else None

    def menu(event):
        widget = event.widget
        custom = getattr(widget, '_barkav_clipboard_menu187', None)
        if custom:
            return custom(event)
        widget.focus_set()
        popup = tk.Menu(widget, tearoff=False)
        popup.bind('<Unmap>', lambda event: popup.after_idle(popup.destroy)
                   if event.widget is popup else None, add='+')
        for label, command, shortcut in (
            ('کپی', 'copy', 'Ctrl+C'), ('برش', 'cut', 'Ctrl+X'),
            ('چسباندن', 'paste', 'Ctrl+V'), ('انتخاب همه', 'select', 'Ctrl+A')):
            allowed = command not in {'cut', 'paste'} or _writable(widget) or (
                command == 'paste' and isinstance(widget, ttk.Combobox)
                and str(widget.cget('state')) == 'readonly')
            popup.add_command(label=label, accelerator=shortcut,
                              state='normal' if allowed else 'disabled',
                              command=lambda value=command: action(widget, value))
        align_menu = getattr(widget.winfo_toplevel(), '_right_align_financial_menu_187', None)
        if callable(align_menu):
            align_menu(popup)
        try:
            popup.tk_popup(event.x_root, event.y_root)
        finally:
            popup.grab_release()
        return 'break'

    root.bind_class(_TAG, '<Control-KeyPress>', key)
    root.bind_class(_TAG, '<Button-3>', menu)
    for sequence, command in (
        ('<Control-Insert>', 'copy'), ('<Shift-Insert>', 'paste'),
        ('<<Copy>>', 'copy'), ('<<Cut>>', 'cut'), ('<<Paste>>', 'paste'),
        ('<<SelectAll>>', 'select')):
        root.bind_class(_TAG, sequence, lambda event, value=command: action(event.widget, value))
    root.bind_all('<Map>', lambda event: attach(event.widget), add='+')
    stack = [root]
    while stack:
        widget = stack.pop()
        attach(widget)
        stack.extend(widget.winfo_children())
