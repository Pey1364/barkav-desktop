"""Section 10: every message carries the app's own window, not the system's.

``tkinter.messagebox`` draws a native Windows box - white, system font, no
theme - in the middle of an otherwise themed app (operator round
2026-09-27: "the final message after processing looks like a Windows
window"). :func:`install` swaps the module's functions for themed dialogs;
it only replaces functions nobody has already replaced (a test's stub, for
instance, stays in place).

:func:`restyle_raw_dialog` dresses a plain toplevel that a screen built by
hand - a label or two, a row of buttons, maybe a progress bar - in the kit's
dialog look: the dark caption, a bold first line, a footer band with the
standard button styles, a themed progress bar.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from .theme import font, metrics, palette
from .window import BarkavDialog, apply_dark_caption

#: kind -> (line icon, palette role for the tile)
KINDS = {
    'info': ('check', 'info'),
    'success': ('check', 'success'),
    'warning': ('bell', 'warning'),
    'error': ('close', 'danger'),
    # 'more' draws a row of three dots - a menu's "more options" glyph -
    # so every حذف/کپی confirmation (askyesno's 'question' kind) carried
    # that instead of anything answering the question (UI/UX review
    # 2026-09-28). No dedicated question-mark glyph exists yet, so this
    # reuses 'check', the same neutral icon 'info'/'success' already do.
    'question': ('check', 'info'),
}

CANCEL_WORDS = ('انصراف', 'لغو', 'بستن', 'خیر')
_ORIGINALS = {name: getattr(messagebox, name) for name in (
    'showinfo', 'showwarning', 'showerror', 'askyesno', 'askokcancel')}


class MessageDialog(BarkavDialog):
    """A themed message or yes/no question with the kit's chrome."""

    size_class = 'tiny'

    def __init__(self, parent: tk.Misc, title: str, message: str, *, kind: str = 'info',
                 buttons: tuple[tuple[str, object, str], ...] = (('باشه', True, 'Primary.TButton'),)):
        self.result = None
        super().__init__(parent, title)
        p = palette()
        row = tk.Frame(self.body, bg=p['surface'])
        row.pack(fill='both', expand=True)
        icon_name, role = KINDS.get(kind, KINDS['info'])
        try:
            from .badges import glass_tile
            image = glass_tile(icon_name, size=34, colour=p.get(role) or p['accent'],
                               ink=p['on_accent'], background=p['surface'], shadow=p['shadow'], master=self)
        except Exception:  # noqa: BLE001 - the text still carries the message
            image = None
        if image is not None:
            tile = tk.Label(row, image=image, bg=p['surface'])
            tile.image = image
            tile.pack(side='right', anchor='n', padx=(0, 12))
        tk.Label(row, text=str(message or ''), bg=p['surface'], fg=p['text_primary'],
                 font=font('body'), justify='right', anchor='ne', wraplength=380).pack(
                     side='right', fill='both', expand=True)
        # Not add_action(): its shared footer packs every button from the
        # left, which is right for a screen's افزودن/ویرایش/حذف row but
        # left this yes/no prompt's «بله»/«خیر» hugging the window's left
        # edge with the whole right half empty - backwards for a راست‌چین
        # dialog (UI/UX review 2026-09-28). Packed from the right instead,
        # the first button (the primary answer) lands at the right edge,
        # reading first for RTL, with the rest following to its left.
        m = metrics()
        for text, value, style in buttons:
            button = ttk.Button(self.footer, text=text,
                                command=lambda v=value: self._answer(v), style=style)
            button.pack(side='right', padx=m['gap'] // 2, pady=m['gap'])
        self.bind('<Return>', lambda _e: self._answer(buttons[0][1]), add='+')
        self.protocol('WM_DELETE_WINDOW', lambda: self._answer(None))
        # As large as the message, not the size class: a one-line note
        # should not open a half-empty window.
        try:
            self.update_idletasks()
            width = min(max(self.winfo_reqwidth(), 380), 560)
            height = self.winfo_reqheight()
            self.minsize(width, height)
            self.geometry(f'{width}x{height}')
            self._center_on_parent(width, height)
        except tk.TclError:
            pass

    def _answer(self, value) -> None:
        self.result = value
        self.close()


def _parent_of(options: dict) -> tk.Misc | None:
    parent = options.get('parent')
    if parent is not None:
        try:
            if parent.winfo_exists():
                return parent
        except tk.TclError:
            return None
    return getattr(tk, '_default_root', None)


def _themed(name: str, kind: str, buttons):
    original = _ORIGINALS[name]

    def show(title=None, message=None, **options):
        if name in ('askyesno','askokcancel'):
            from table_actions import current_delete_choice
            # Only deletion questions inside an already confirmed table action
            # are covered. Other confirmations keep their normal behavior.
            if current_delete_choice() is not None and any(word in str(title or '') for word in ('حذف','لغو','ابطال')):
                return True
        parent = _parent_of(options)
        if parent is None:
            return original(title, message, **options)
        try:
            dialog = MessageDialog(parent, str(title or ''), str(message or ''),
                                   kind=kind, buttons=buttons)
            dialog.wait_window()
        except tk.TclError:
            return original(title, message, **options)
        if name.startswith('ask'):
            return bool(dialog.result)
        return 'ok'

    show._barkav_themed = True
    return show


def install() -> None:
    """Route messagebox's boxes through :class:`MessageDialog`."""

    ok = (('باشه', True, 'Primary.TButton'),)
    replacements = {
        'showinfo': _themed('showinfo', 'info', ok),
        'showwarning': _themed('showwarning', 'warning', ok),
        'showerror': _themed('showerror', 'error', ok),
        'askyesno': _themed('askyesno', 'question', (('بله', True, 'Primary.TButton'),
                                                     ('خیر', False, 'Ghost.TButton'))),
        'askokcancel': _themed('askokcancel', 'question', (('تأیید', True, 'Primary.TButton'),
                                                           ('انصراف', False, 'Ghost.TButton'))),
    }
    for name, replacement in replacements.items():
        if getattr(messagebox, name) is _ORIGINALS[name]:
            setattr(messagebox, name, replacement)


def restyle_raw_dialog(dialog: tk.Misc) -> bool:
    """Dress a hand-built dialog in the kit's look. Returns whether it did."""

    if getattr(dialog, '_barkav_dressed', False) or isinstance(dialog, BarkavDialog):
        return False
    try:
        if dialog.winfo_class() != 'Toplevel' or dialog.overrideredirect():
            return False
        if not str(dialog.wm_transient() or ''):
            return False
    except tk.TclError:
        return False
    dialog._barkav_dressed = True
    p = palette()
    style = ttk.Style(dialog)
    try:
        apply_dark_caption(dialog)
        dialog.configure(bg=p['bg'])
    except tk.TclError:
        return False
    style.configure('RawDialogFooter.TFrame', background=p['dialog_footer'])
    style.configure('Barkav.Horizontal.TProgressbar', troughcolor=p['input'],
                    background=p['accent'], bordercolor=p['input'],
                    lightcolor=p['accent'], darkcolor=p['accent'], thickness=6)
    labels = [w for w in dialog.winfo_children() if isinstance(w, tk.Label)]
    if labels:
        try:
            labels[0].configure(font=font('title'), fg=p['text_primary'])
            for label in labels[1:]:
                label.configure(font=font('body'), fg=p['text_secondary'])
            for label in labels:
                label.configure(bg=p['bg'])
        except tk.TclError:
            pass
    for child in dialog.winfo_children():
        if isinstance(child, ttk.Progressbar):
            try:
                child.configure(style='Barkav.Horizontal.TProgressbar')
            except tk.TclError:
                pass
        buttons = [w for w in child.winfo_children() if isinstance(w, ttk.Button)] \
            if isinstance(child, (ttk.Frame, tk.Frame)) else []
        if not buttons:
            continue
        # The row of buttons becomes the footer band every kit dialog has.
        try:
            tk.Frame(dialog, height=1, bg=p['border_subtle']).pack(fill='x', before=child)
            if isinstance(child, ttk.Frame):
                child.configure(style='RawDialogFooter.TFrame', padding=(12, 10))
            else:
                child.configure(bg=p['dialog_footer'], padx=12, pady=10)
            child.pack_configure(padx=0, pady=0, fill='x')
        except tk.TclError:
            pass
        for button in buttons:
            try:
                text = str(button.cget('text') or '')
                current = str(button.cget('style') or '')
                if any(word in text for word in CANCEL_WORDS):
                    button.configure(style='Ghost.TButton')
                elif current in ('', 'TButton'):
                    button.configure(style='Toolbar.TButton')
            except tk.TclError:
                continue
    try:
        dialog.update_idletasks()
        width = max(dialog.winfo_reqwidth(), 460)
        dialog.minsize(width, dialog.winfo_reqheight())
    except tk.TclError:
        pass
    return True


def watch_raw_dialogs(root: tk.Misc) -> None:
    """Dress every hand-built dialog of ``root``'s app as it opens."""

    def mapped(event) -> None:
        widget = event.widget
        if isinstance(widget, str):
            try:
                widget = root.nametowidget(widget)
            except (KeyError, tk.TclError):
                return
        try:
            restyle_raw_dialog(widget)
        except Exception:  # noqa: BLE001 - a look, never worth breaking a dialog
            pass

    root.bind_class('Toplevel', '<Map>', mapped, add='+')
