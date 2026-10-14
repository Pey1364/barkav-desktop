"""Right-to-left typing in Tk's Text widget.

Tk 8.6 lays a line out left to right and only lets Windows reorder the glyphs of each chunk it draws, and it
keeps the caret and every click in its left-to-right model. For Persian text that has three visible effects:

* a Latin word or number in the line is placed at the wrong end of it (the base direction is left to right);
* the caret is drawn at the opposite end of the text from where the next letter appears, and a click at the
  end of the text where letters are added lands at its start, so a letter typed there joins the first word;
* a caret in the middle of the text splits it into two chunks, which are laid out left to right, so the words
  jump around while one types.

A box that has been taught here keeps every line inside an invisible right-to-left embedding (U+202B), keeps the
real insertion point at the end of the text, draws its own caret where the next letter will appear, and lets a
click or a navigation key leave the caret at the end instead of moving it into the middle. Typing, deleting
from the end, a new line, paste, and «انتخاب همه» then replace everything. The embedding marks never leave the
widget: get() hands out the text without them.
"""
from __future__ import annotations

import tkinter as tk

RLE = '‫'  # right-to-left embedding: the paragraph is read from the right whatever it contains
PDF = '‬'
TAG = 'rtl187'

_NAVIGATION = frozenset({
    'Left', 'Right', 'Up', 'Down', 'Home', 'End', 'Prior', 'Next',
    'KP_Left', 'KP_Right', 'KP_Up', 'KP_Down', 'KP_Home', 'KP_End', 'KP_Prior', 'KP_Next',
})
_BLINK_MS = 530


def plain(text) -> str:
    """The text the user sees, without the direction marks the box keeps in it."""
    return str(text).replace(RLE, '').replace(PDF, '')


def install(widget: tk.Text) -> '_RtlText':
    """Teach a Text widget to be typed in from the right (idempotent)."""
    controller = getattr(widget, '_rtl_text187', None)
    if controller is None:
        controller = _RtlText(widget)
        widget._rtl_text187 = controller
    return controller


class _RtlText:
    def __init__(self, widget: tk.Text):
        self.widget = widget
        self._busy = False
        self._blink_job = None
        self._visible = True
        self._read = widget.get
        self._offset = None  # where place() puts (0, 0) inside the box: its border and padding
        widget.get = self.get  # every reader of the box gets the text without the marks
        widget.tag_configure(TAG, justify='right')
        try:
            colour = str(widget.cget('insertbackground'))
        except tk.TclError:
            colour = 'white'
        widget.configure(insertwidth=0)  # Tk's own caret sits at the other end of the text
        self.caret = tk.Frame(widget, width=2, bg=colour, bd=0, highlightthickness=0, cursor='xterm')
        for sequence, handler in (
                ('<<Modified>>', self.normalize), ('<KeyPress>', self.on_key),
                ('<KeyRelease>', self.refresh_caret), ('<Button-1>', self.on_click),
                ('<Shift-Button-1>', self.on_click), ('<Control-Button-1>', self.on_click),
                ('<B1-Motion>', self.on_drag), ('<Double-Button-1>', self.on_click),
                ('<Triple-Button-1>', self.on_click), ('<ButtonRelease-1>', self.refresh_caret),
                ('<FocusIn>', self.on_focus_in), ('<FocusOut>', self.on_focus_out),
                ('<Configure>', self.refresh_caret), ('<Destroy>', self.on_destroy)):
            widget.bind(sequence, handler, add='+')
        self.caret.bind('<Button-1>', self.on_click, add='+')
        self.normalize()

    # ---- the text without the marks ---------------------------------------------------------------------
    def get(self, *args):
        value = self._read(*args)
        return plain(value) if isinstance(value, str) else value

    def editable(self) -> bool:
        try:
            return str(self.widget.cget('state')) == 'normal'
        except tk.TclError:
            return False

    # ---- every line inside its embedding --------------------------------------------------------------------
    def normalize(self, _event=None):
        if self._busy:
            return
        widget = self.widget
        self._busy = True
        try:
            state = str(widget.cget('state'))
            last = int(widget.index('end-1c').split('.')[0])
            missing = [line for line in range(1, last + 1) if self._read(f'{line}.0', f'{line}.1') != RLE]
            if missing:
                if state != 'normal':
                    widget.configure(state='normal')
                for line in missing:
                    widget.insert(f'{line}.0', RLE, TAG)
                if state != 'normal':
                    widget.configure(state=state)
            if self.editable() and not widget.tag_ranges('sel'):
                widget.mark_set('insert', 'end-1c')
            # <<Modified>> is raised only when the flag goes from clear to set, so the last listener (this one:
            # the box is taught at the end of its construction) clears it, as the box's other listeners do. The
            # marks put in above are no edit of the user's either.
            widget.edit_modified(False)
        except tk.TclError:
            return
        finally:
            self._busy = False
        self.refresh_caret()

    # ---- the caret stays at the end; keys and clicks cannot move it into the middle ------------------------------
    def to_end(self):
        try:
            self.widget.mark_set('insert', 'end-1c')
            self.widget.see('end-1c')
        except tk.TclError:
            pass

    def on_key(self, event):
        if not self.editable():
            return None
        key = event.keysym
        if key in _NAVIGATION:
            self.to_end()
            self.refresh_caret()
            return 'break'
        widget = self.widget
        if key == 'Return' or key == 'KP_Enter':
            if widget.tag_ranges('sel'):
                widget.delete('sel.first', 'sel.last')
            widget.insert('end-1c', '\n' + RLE, TAG)  # the new line and its mark are one edit
            self.to_end()
            self.refresh_caret()
            return 'break'
        if key == 'BackSpace' and not widget.tag_ranges('sel'):
            end = widget.index('end-1c')
            if self._read(f'{end}-1c', end) == RLE:
                # nothing but the mark is left of this line: take the mark and the line break before it
                start = f'{end}-2c' if int(end.split('.')[0]) > 1 else f'{end}-1c'
                widget.delete(start, end)
                self.to_end()
                self.refresh_caret()
                return 'break'
        self.to_end()
        return None

    def on_click(self, event=None):
        if not self.editable():
            return None
        self.widget.focus_set()
        self.widget.tag_remove('sel', '1.0', 'end')
        self.to_end()
        self.refresh_caret()
        return 'break'

    def on_drag(self, event=None):
        return 'break' if self.editable() else None

    # ---- the caret drawn where the next letter appears --------------------------------------------------------------
    def on_focus_in(self, _event=None):
        self._visible = True
        self.refresh_caret()
        self._schedule_blink()

    def on_focus_out(self, _event=None):
        self._cancel_blink()
        self.caret.place_forget()

    def on_destroy(self, event=None):
        if event is not None and event.widget is not self.widget:
            return
        self._cancel_blink()

    def refresh_caret(self, _event=None):
        widget = self.widget
        try:
            if not self.editable() or widget.focus_get() is not widget:
                self.caret.place_forget()
                return
            widget.update_idletasks()
            widget.see('end-1c')
            info = widget.dlineinfo('end-1c')
            if info is None or not self._visible:
                self.caret.place_forget()
                return
            x, y, _width, height, _baseline = info
            if self._offset is None:
                if not widget.winfo_ismapped():
                    return
                self.caret.place(x=0, y=0, width=2, height=1)
                widget.update_idletasks()
                self._offset = (self.caret.winfo_rootx() - widget.winfo_rootx(),
                                self.caret.winfo_rooty() - widget.winfo_rooty())
            # a theme pass over the window's frames may have repainted the caret
            self.caret.configure(bg=str(widget.cget('insertbackground')))
            # dlineinfo counts from the box's corner, place() from inside its border and padding
            self.caret.place(x=max(0, x - 3 - self._offset[0]), y=y - self._offset[1], width=2, height=height)
            self.caret.lift()
        except tk.TclError:
            pass

    def _schedule_blink(self):
        self._cancel_blink()
        try:
            self._blink_job = self.widget.after(_BLINK_MS, self._blink)
        except tk.TclError:
            self._blink_job = None

    def _cancel_blink(self):
        job, self._blink_job = self._blink_job, None
        if job is not None:
            try:
                self.widget.after_cancel(job)
            except tk.TclError:
                pass

    def _blink(self):
        self._blink_job = None
        try:
            if self.widget.focus_get() is not self.widget:
                return
        except (tk.TclError, KeyError):
            return
        self._visible = not self._visible
        self.refresh_caret()
        self._schedule_blink()
