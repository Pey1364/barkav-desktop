"""Idle numeric formatting for project editors and registration forms."""
from __future__ import annotations

import tkinter as tk


def format_numeric_entry(entry, variable, formatter, *, caret_at_end=False):
    """Format after Tk finishes inserting text, preserving the logical caret.

    Writing a StringVar from inside its write trace interrupts Tk's own
    insertion and leaves its caret one character behind. Queue one idle
    callback instead, then map the caret by characters other than grouping
    separators so both insertion and mid-number corrections keep their place.
    Registration opts into caret_at_end to append digits and clipboard input.
    """
    state = {'pending': None, 'busy': False}
    separators = ',،٬'

    def reformat():
        state['pending'] = None
        if not entry.winfo_exists():
            return
        raw = variable.get()
        grouped = raw if raw.strip() in ('', '-', '+', '.') else formatter(raw)
        if grouped == raw and not caret_at_end:
            return
        caret = entry.index(tk.INSERT)
        logical = sum(char not in separators for char in raw[:caret])
        selection = None
        if entry.selection_present():
            selection = tuple(sum(char not in separators for char in raw[:entry.index(index)])
                              for index in (tk.SEL_FIRST, tk.SEL_LAST))

        def position(count):
            if count <= 0:
                return 0
            seen = 0
            for index, char in enumerate(grouped):
                if char not in separators:
                    seen += 1
                if seen == count:
                    return index + 1
            return len(grouped)

        state['busy'] = True
        entry._numeric_formatting187 = True
        try:
            if grouped != raw:
                variable.set(grouped)
            entry.icursor(len(grouped) if caret_at_end or caret == len(raw) else position(logical))
            if selection is not None:
                entry.selection_range(*(position(count) for count in selection))
        finally:
            entry._numeric_formatting187 = False
            state['busy'] = False

    def schedule(*_args):
        if not state['busy'] and state['pending'] is None:
            state['pending'] = entry.after_idle(reformat)

    trace = variable.trace_add('write', schedule)

    if caret_at_end:
        entry._barkav_numeric_append = True
        def append_input(event=None):
            # Run before Tk's class binding, including fast consecutive keys.
            # A selected range still supports replacing/cutting/copying text.
            character = getattr(event, 'char', '') or ''
            key = getattr(event, 'keysym', '')
            if (event is None or character.isdecimal() or character in '.٫'
                    or key in ('BackSpace', 'Delete')):
                if not entry.selection_present():
                    entry.icursor(tk.END)
                schedule()

        entry.bind('<KeyPress>', append_input, add='+')
        entry.bind('<<Paste>>', lambda _event: append_input(), add='+')
        entry.bind('<<Cut>>', lambda _event: schedule(), add='+')
        schedule()

    def cleanup(_event):
        if state['pending'] is not None:
            entry.after_cancel(state['pending'])
            state['pending'] = None
        variable.trace_remove('write', trace)

    entry.bind('<Destroy>', cleanup, add='+')


def bind_editor_mousewheel(window):
    """Use the shell's scrollbars while the pointer is over body controls."""
    canvas = window._scroll_canvas

    def scroll(event):
        direction = -1 if getattr(event, 'num', None) == 4 else 1
        delta = getattr(event, 'delta', 0)
        units = (-1 if delta > 0 else 1) * max(1, abs(int(delta / 120))) if delta else direction * 3
        canvas.yview_scroll(units, 'units')
        return 'break'

    stack = [window.body]
    while stack:
        widget = stack.pop()
        stack.extend(widget.winfo_children())
        for event in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
            widget.bind(event, scroll, add='+')
