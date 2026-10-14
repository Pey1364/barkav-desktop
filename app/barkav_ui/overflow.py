"""Section 11: a row of buttons that runs out of room keeps working.

When a toolbar is narrower than its buttons, Tk's packer simply unmaps the
ones it cannot fit and they vanish.  ``watch`` adds a "بیشتر" menu button to
such a row the moment that happens, listing exactly the buttons the packer
dropped; it disappears again once everything fits.  No button is moved,
re-packed or removed, so screens that show and hide their own buttons keep
full control of them.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .theme import font, palette

MORE_TEXT = 'بیشتر ⋯'
_MIN_BUTTONS = 3


def watch(frame: tk.Misc) -> 'Overflow':
    current = getattr(frame, '_barkav_overflow', None)
    if current is None:
        current = Overflow(frame)
        frame._barkav_overflow = current
    current.schedule()
    return current


def _is_button(widget) -> bool:
    return isinstance(widget, (tk.Button, ttk.Button))


class Overflow:
    def __init__(self, frame: tk.Misc):
        self.frame = frame
        self.more: ttk.Menubutton | None = None
        self.menu: tk.Menu | None = None
        self._job = None
        frame.bind('<Configure>', self.schedule, add='+')
        frame.bind('<Map>', self.schedule, add='+')
        frame.bind('<Destroy>', self._destroyed, add='+')

    def _destroyed(self, event) -> None:
        if event.widget is self.frame and self._job is not None:
            try:
                self.frame.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None

    def schedule(self, _event=None) -> None:
        if self._job is None:
            try:
                self._job = self.frame.after_idle(self.update)
            except tk.TclError:
                self._job = None

    def _buttons(self) -> list:
        try:
            slaves = self.frame.pack_slaves()
        except tk.TclError:
            return []
        return [w for w in slaves if _is_button(w) and w is not self.more]

    def _ensure_more(self, side: str) -> None:
        if self.more is not None and self.more.winfo_exists():
            return
        p = palette()
        self.more = ttk.Menubutton(self.frame, text=MORE_TEXT, direction='below')
        self.menu = tk.Menu(self.more, tearoff=False, bg=p['surface'], fg=p['text_primary'],
                            activebackground=p['accent'], activeforeground=p['bg'],
                            font=font('body'))
        self.more.configure(menu=self.menu)

    def update(self) -> None:
        self._job = None
        frame = self.frame
        try:
            if not frame.winfo_exists() or not frame.winfo_ismapped():
                return
        except tk.TclError:
            return
        buttons = self._buttons()
        if len(buttons) < _MIN_BUTTONS:
            self._hide()
            return
        hidden = [b for b in buttons if not b.winfo_ismapped()]
        if not hidden:
            self._hide()
            return
        # The side most buttons are on: an export control alone at the other
        # end (packed first, so it is never the one dropped) does not decide.
        sides = [str(b.pack_info().get('side') or 'left') for b in buttons]
        side = max(('right', 'left'), key=sides.count)
        self._ensure_more(side)
        if not self.more.winfo_manager():
            # Packed first, on the far end of the row, so it always gets
            # room; whichever button that pushes out joins the menu below.
            first = frame.pack_slaves()[0]
            self.more.pack(side='left' if side == 'right' else 'right', padx=4,
                           before=first)
            frame.update_idletasks()
            hidden = [b for b in self._buttons() if not b.winfo_ismapped()]
        self.menu.delete(0, 'end')
        for button in hidden:
            try:
                text = str(button.cget('text') or '').strip()
                state = 'disabled' if str(button.cget('state')) == 'disabled' else 'normal'
            except tk.TclError:
                continue
            if text:
                self.menu.add_command(label=text, command=button.invoke, state=state)

    def _hide(self) -> None:
        if self.more is not None and self.more.winfo_exists() and self.more.winfo_manager():
            self.more.pack_forget()
