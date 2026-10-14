"""Window shells - section 10 of the UI contract.

Every BARKAV window carries minimize, maximize and close in the *native*
Windows caption, top right, matching both the platform and the reference
design.  The caption is themed dark where Windows allows it.

Two earlier approaches were tried and rejected.  ``transient(parent)`` is
what stripped minimize and maximize from the product's dialogs in the first
place, so windows are tied to their owner by binding instead.  Drawing a
custom caption put the controls on the left, and left migrated windows
looking unlike the ones still waiting - the opposite of the point.
"""

from __future__ import annotations

import re
import sys
import tkinter as tk
from tkinter import ttk

from .widget_lifetime import install_callback_cleanup
from .bidi import rtl

from ui_stage18_3 import fa

from .theme import font, metrics, palette


# Section 10: the five approved window sizes.  A screen picks a class; it does
# not invent a geometry.
SIZE_CLASSES = {
    'tiny':   ((520, 300),   (420, 240)),
    'small':  ((760, 520),   (600, 420)),
    'medium': ((980, 650),   (700, 440)),
    'large':  ((1280, 720),  (950, 560)),
    'full':   ((1480, 880),  (1180, 720)),
}

_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_WINDOW_CORNER_PREFERENCE = 33
_DWMWCP_ROUND = 2
_SPI_GETWORKAREA = 0x0030
# What Windows spends on a resizable window's own frame: the caption plus the
# borders.  A window sized to the full work area would otherwise overflow it
# by exactly this much and push its footer under the taskbar.
_FRAME_RESERVE = 48

def hide_for_fade(window: tk.Misc) -> None:
    """Build a window while withdrawn so its first visible frame is complete."""
    install_callback_cleanup(window)
    try:
        window.withdraw()
    except tk.TclError:
        pass


def fade_in(window: tk.Misc, *, step: float = 0.05, interval_ms: int = 20) -> None:
    """Compatibility helper that shows a window immediately, without animation."""
    del step, interval_ms  # Keep the old call signature for existing callers.
    try:
        window.deiconify()
    except tk.TclError:
        pass


def work_area(window: tk.Misc) -> tuple[int, int]:
    """Usable desktop size - the screen minus the taskbar.

    ``winfo_screenheight`` counts the whole display, so a window sized from it
    hides its own footer behind the taskbar.  Windows reports the real figure;
    everywhere else a conservative reserve is taken off instead.
    """

    if sys.platform.startswith('win'):
        try:
            import ctypes
            from ctypes import wintypes

            rect = wintypes.RECT()
            ok = ctypes.windll.user32.SystemParametersInfoW(
                _SPI_GETWORKAREA, 0, ctypes.byref(rect), 0)
            if ok and rect.right > rect.left and rect.bottom > rect.top:
                return rect.right - rect.left, rect.bottom - rect.top
        except (AttributeError, OSError, ImportError, ValueError):
            pass
    return window.winfo_screenwidth(), window.winfo_screenheight() - 64


def center_toplevel_on_screen(window: tk.Toplevel, *, width: int | None = None,
                              height: int | None = None) -> None:
    """Place a normal secondary window in the centre of the usable screen."""
    try:
        if window.overrideredirect():
            return
        resize = width is not None or height is not None
        width = max(1, int(width if width is not None else window.winfo_width()))
        height = max(1, int(height if height is not None else window.winfo_height()))
        screen_width, screen_height = work_area(window)
        x = max(0, (screen_width - width) // 2)
        y = max(0, (screen_height - height - _FRAME_RESERVE) // 2)
        window.geometry(f'{width}x{height}+{x}+{y}' if resize else f'+{x}+{y}')
    except (tk.TclError, AttributeError):
        pass


def normalize_window_rtl(window: tk.Misc) -> None:
    """Right-align textual controls and isolate numeric-leading label lines."""
    stack = [window]
    while stack:
        parent = stack.pop()
        try:
            stack.extend(parent.winfo_children())
        except tk.TclError:
            continue
        try:
            options = set(parent.keys())
            if isinstance(parent, (tk.Entry, ttk.Entry, ttk.Combobox,
                                   tk.Spinbox, tk.Text)):
                if 'justify' in options:
                    parent.configure(justify='right')
                continue

            alignment = {}
            if 'justify' in options:
                alignment['justify'] = 'right'
            if 'anchor' in options:
                alignment['anchor'] = 'e'
            if alignment:
                parent.configure(**alignment)

            if 'text' in options:
                original = str(parent.cget('text') or '')
                directed = re.sub(
                    r'(?m)^([ \t]*)(?=\d)(?=[^\r\n]*[\u0620-\u064a\u066e-\u06d3])',
                    lambda match: match.group(1) + '\u200f',
                    original,
                )
                if directed != original:
                    parent.configure(text=directed)
        except (tk.TclError, AttributeError):
            continue


def apply_dark_caption(window: tk.Misc) -> bool:
    """Ask Windows to draw this window's native caption in dark mode.

    The product keeps the native title bar: it puts minimize, maximize and
    close where Windows users expect them - top right - which is also where
    the reference design has them.  Drawing our own caption instead put the
    controls on the left and, worse, left migrated windows looking unlike the
    ones not yet migrated.

    Only the dark-mode attribute is available here; DWMWA_CAPTION_COLOR and
    DWMWA_TEXT_COLOR are Windows 11 and return E_INVALIDARG on Windows 10, so
    the caption can be dark but cannot be tinted to the theme exactly.
    """

    install_callback_cleanup(window)
    if not sys.platform.startswith('win'):
        return False
    try:
        import ctypes
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        if not hwnd:
            return False
        value = ctypes.c_int(1)
        result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, _DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(value), ctypes.sizeof(value))
        return result == 0
    except (AttributeError, OSError, tk.TclError, ImportError):
        return False


def apply_rounded_corners(window: tk.Misc) -> bool:
    """Ask Windows 11 to round this window's corners, caption included.

    A secondary window keeps its native caption (see :func:`apply_dark_caption`
    for why), so the kit's own ``rounded_backdrop`` trick - a hand-drawn plate
    blended into the page behind it - cannot round it the way an
    ``overrideredirect`` popup draws its own corners: DWM, not this process,
    owns those pixels. DWMWA_WINDOW_CORNER_PREFERENCE is the one attribute
    that reaches them, and like the caption's dark-mode flag it is Windows 11
    only; asking on Windows 10 fails quietly and the window stays square.
    """

    if not sys.platform.startswith('win'):
        return False
    try:
        import ctypes
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        if not hwnd:
            return False
        value = ctypes.c_int(_DWMWCP_ROUND)
        result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, _DWMWA_WINDOW_CORNER_PREFERENCE, ctypes.byref(value), ctypes.sizeof(value))
        return result == 0
    except (AttributeError, OSError, tk.TclError, ImportError):
        return False


def keep_above_parent(window: tk.Toplevel, parent: tk.Misc) -> None:
    """Tie a window's lifetime and stacking to its parent without transient().

    ``transient()`` is what removed minimize and maximize from every dialog in
    this product - Windows drops both from a tool window's caption. Binding
    the parent's destruction gives the same "closes with its owner" behaviour
    while leaving the caption complete.

    A plain ``Toplevel`` also gets its own independent taskbar entry, so
    picking the child back up from the taskbar must restore a minimized
    owner too. The focused child is raised last. A visible owner is not
    raised on FocusIn: Windows can activate it, then reactivate the child,
    producing a repeating focus cycle that stalls the event loop.
    """

    try:
        owner = parent.winfo_toplevel()
        if window.overrideredirect() or getattr(window, '_barkav_owner_stacking_bound', False):
            return
        window._barkav_owner_stacking_bound = True
    except tk.TclError:
        return

    def _close(event=None):
        # <Destroy> reaches a toplevel for every widget inside it, not just
        # for itself, so a screen merely rebuilding its table used to take
        # every window opened from it down with the redraw.
        if event is not None and event.widget is not owner:
            return
        try:
            if window.winfo_exists():
                window.destroy()
        except tk.TclError:
            pass

    try:
        owner.bind('<Destroy>', _close, add='+')
    except tk.TclError:
        pass

    def _bring_owner_forward(event=None):
        # <FocusIn> fans out the same way <Destroy> does above - every widget
        # inside the child reports it, not only the child itself - so without
        # this filter a click anywhere inside the child keeps re-lifting the
        # owner on top of the child it is meant to sit behind.
        if event is not None and event.widget is not window:
            return
        try:
            if not owner.winfo_exists():
                return
            if str(owner.state()) == 'iconic':
                owner.deiconify()
            # Keep the child foremost without activating its visible owner.
            window.lift()
        except tk.TclError:
            pass

    try:
        window.bind('<FocusIn>', _bring_owner_forward, add='+')
    except tk.TclError:
        pass


def bind_main_window_focus_on_destroy(window: tk.Toplevel, main_window: tk.Misc) -> None:
    """Return to an open dialog, or to the main window when none remain."""
    if getattr(window, '_barkav_focus_restore_bound', False):
        return
    try:
        # Toasts, tooltips and menus can close while a dialog still owns focus.
        if window.overrideredirect():
            return
        owner = window.master.winfo_toplevel()
    except (tk.TclError, AttributeError):
        return
    keep_above_parent(window, owner)
    window._barkav_focus_restore_bound = True

    pending = {'after_id': None}

    def _restore(event=None) -> None:
        if event is not None and event.widget is not window:
            return

        def _activate() -> None:
            pending['after_id'] = None
            try:
                if not main_window.winfo_exists():
                    return
                # A dialog can close while its owner or a replacement dialog
                # remains open. Never raise the main window over that dialog.
                candidates = []
                grabbed = main_window.grab_current()
                if grabbed is not None:
                    candidates.append(grabbed.winfo_toplevel())
                candidates.append(owner)
                for path in reversed(main_window.tk.splitlist(
                        main_window.tk.call('wm', 'stackorder', main_window))):
                    try:
                        candidates.append(main_window.nametowidget(path))
                    except KeyError:
                        continue
                target = main_window
                for candidate in candidates:
                    if candidate is window or candidate is main_window:
                        continue
                    try:
                        if (candidate.winfo_exists() and candidate.winfo_viewable()
                                and not candidate.overrideredirect()):
                            target = candidate
                            break
                    except tk.TclError:
                        continue
                if main_window.state() == 'iconic':
                    main_window.state('normal')
                main_window.deiconify()
                main_window.lift()
                if target is not main_window:
                    target.lift()
                target.focus_force()
            except tk.TclError:
                pass

        try:
            pending['after_id'] = main_window.after_idle(_activate)
        except tk.TclError:
            pass

    def _cancel_on_main_destroy(event=None) -> None:
        if event is not None and event.widget is not main_window:
            return
        after_id = pending.get('after_id')
        if not after_id:
            return
        try:
            main_window.after_cancel(after_id)
        except tk.TclError:
            pass
        pending['after_id'] = None

    try:
        window.bind('<Destroy>', _restore, add='+')
        main_window.bind('<Destroy>', _cancel_on_main_destroy, add='+')
    except tk.TclError:
        pass


def show_toast(parent: tk.Misc, message: str, *, kind: str = 'success',
               duration_ms: int = 2600) -> None:
    """A small, self-dismissing confirmation instead of a blocking dialog.

    ``messagebox.showinfo`` is a native OS dialog: it ignores the product's
    dark theme entirely, and freezes the owning window until the user clicks
    OK - a lot of weight for a routine "ذخیره شد". This is for exactly that
    routine case, not for anything the operator must consciously read and
    acknowledge (a warning, a result with details worth keeping on screen) -
    those stay real dialogs on purpose.
    """

    p = palette()
    m = metrics()
    accent = p['success'] if kind == 'success' else p['danger']
    host = parent.winfo_toplevel()

    toast = tk.Toplevel(host)
    toast.overrideredirect(True)
    try:
        toast.attributes('-topmost', True)
    except tk.TclError:
        pass

    plate = tk.Frame(toast, bg=p['toast_bg'])
    plate.pack(fill='both', expand=True)
    tk.Frame(plate, bg=accent, width=3).pack(side='right', fill='y')
    tk.Label(
        plate, text=str(message), bg=p['toast_bg'], fg=p['text_primary'],
        font=font('body'), padx=16, pady=10, justify='right', anchor='e',
        wraplength=320,
    ).pack(side='right', fill='both', expand=True)

    host.update_idletasks()
    toast.update_idletasks()
    width = min(360, max(180, toast.winfo_reqwidth()))
    height = toast.winfo_reqheight()
    x = host.winfo_rootx() + (host.winfo_width() - width) // 2
    y = host.winfo_rooty() + host.winfo_height() - height - m['gap'] * 3
    try:
        toast.geometry(f'{width}x{height}+{max(0, x)}+{max(0, y)}')
    except tk.TclError:
        pass

    fade_in(toast, step=0.15, interval_ms=16)

    def _dismiss() -> None:
        try:
            if toast.winfo_exists():
                toast.destroy()
        except tk.TclError:
            pass

    toast.after(duration_ms, _dismiss)


class BarkavWindow(tk.Toplevel):
    """Base window: native dark caption, contract geometry, themed body.

    Subclasses build into :attr:`body`, and put action buttons in
    :attr:`footer` via :meth:`add_action`.
    """

    #: Overridden by subclasses; must be a key of SIZE_CLASSES.
    size_class = 'medium'

    def __init__(
        self,
        parent: tk.Misc,
        title: str,
        *,
        subtitle: str = '',
        size_class: str | None = None,
        show_footer: bool = True,
        show_header: bool = False,
        scrollable: bool = False,
        show_immediately: bool = True,
    ):
        super().__init__(parent)
        hide_for_fade(self)
        self._parent = parent
        self._scrollable = scrollable
        self._show_header = show_header
        try:
            self._main_window = parent._root()
        except (AttributeError, tk.TclError):
            self._main_window = parent.winfo_toplevel()
        self._title_text = str(title)
        self._subtitle_text = str(subtitle)
        self._maximized = False

        chosen = size_class or self.size_class
        if chosen not in SIZE_CLASSES:
            raise ValueError(f'Unknown size class {chosen!r}; expected one of {sorted(SIZE_CLASSES)}')
        (width, height), (min_width, min_height) = SIZE_CLASSES[chosen]

        self.title(f'{self._title_text} — {self._subtitle_text}' if self._subtitle_text
                   else self._title_text)
        self.geometry(f'{width}x{height}')
        self.minsize(min_width, min_height)
        self.resizable(True, True)

        apply_dark_caption(self)
        apply_rounded_corners(self)
        keep_above_parent(self, parent)
        bind_main_window_focus_on_destroy(self, self._main_window)
        self._build_chrome(show_footer=show_footer)
        self._center_on_parent(width, height)
        if show_immediately:
            self._take_focus()

        # Section 10: Esc always closes; the window is never trapped.
        self.bind('<Escape>', lambda _event: self.close())
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.bind('<Map>', self._normalise_on_map, add='+')
        if show_immediately:
            fade_in(self)

        # Operator request 2026-09-28: a secondary window owns the
        # interaction until it is resolved - the parent must not be
        # reachable while it is still open. grab_set() needs a viewable
        # window, so it runs last, after fade_in() has deiconified this one;
        # Tk releases the grab automatically when the window is destroyed.
        if show_immediately:
            try:
                self.grab_set()
            except tk.TclError:
                pass

    # ------------------------------------------------------------------ chrome

    def _build_chrome(self, *, show_footer: bool) -> None:
        p = palette()
        m = metrics()
        # A secondary window is a raised surface, not a patch of the page it
        # floats over (UI/UX review 2026-09-28) - the header and footer
        # already read p['surface'] below; the body matches instead of
        # standing out as the page's own colour showing through.
        self.configure(bg=p['surface'])

        # A fixed region under the title bar for things that must not scroll
        # away with the content - a wizard's progress, a screen's filter bar.
        self.header = None
        if self._show_header:
            self.header = tk.Frame(
                self, bg=p['surface'],
                highlightbackground=p['border_subtle'], highlightthickness=1)
            self.header.pack(fill='x', side='top')

        # The footer is packed before the body, not after. pack gives space in
        # the order it is asked, so a body that expands takes what it wants
        # first and pushes the footer - and the primary action with it - off
        # the bottom of a window that is too short for its content.
        self.footer = None
        if show_footer:
            self.footer = tk.Frame(
                self, bg=p['dialog_footer'],
                highlightbackground=p['border_subtle'], highlightthickness=1,
            )
            self.footer.pack(fill='x', side='bottom')

        if self._scrollable:
            self.body = self._build_scrollable_body(p, m)
        else:
            self.body = tk.Frame(self, bg=p['surface'])
            self.body.pack(fill='both', expand=True, padx=m['outer_pad'], pady=m['outer_pad'])

    def _build_scrollable_body(self, p: dict[str, str], m: dict[str, int]) -> tk.Frame:
        """Section 10: scrolling belongs to the shell, not the screen.

        Returns the inner frame callers build into; the canvas and scrollbars
        stay private so no window has to reimplement wheel handling.

        Both directions scroll. A window whose content is a wide grid runs off
        the side as readily as off the bottom, and only the bottom had a way
        back.
        """

        shell = tk.Frame(self, bg=p['surface'])
        shell.pack(fill='both', expand=True, padx=m['outer_pad'], pady=m['outer_pad'])
        shell.rowconfigure(0, weight=1)
        shell.columnconfigure(1, weight=1)
        canvas = tk.Canvas(shell, bg=p['surface'], highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(shell, orient='vertical', command=canvas.yview)
        sideways = ttk.Scrollbar(shell, orient='horizontal', command=canvas.xview)
        canvas.configure(yscrollcommand=scrollbar.set, xscrollcommand=sideways.set)
        # RTL: the vertical bar sits on the left.
        scrollbar.grid(row=0, column=0, sticky='ns')
        canvas.grid(row=0, column=1, sticky='nsew')
        sideways.grid(row=1, column=1, sticky='ew')

        inner = tk.Frame(canvas, bg=p['surface'])
        item = canvas.create_window((0, 0), window=inner, anchor='nw')
        inner.bind(
            '<Configure>',
            lambda _e: canvas.configure(scrollregion=canvas.bbox('all')), add='+')
        canvas.bind(
            '<Configure>',
            # Only stretch the content to the canvas when it is the narrower of
            # the two; forcing it always is what stopped anything wide from
            # scrolling sideways at all.
            lambda e: canvas.itemconfigure(item, width=max(e.width, inner.winfo_reqwidth())),
            add='+')
        canvas.bind('<Shift-MouseWheel>',
                    lambda e: canvas.xview_scroll(int(-e.delta / 120), 'units'), add='+')
        canvas.bind(
            '<MouseWheel>',
            lambda e: canvas.yview_scroll(int(-e.delta / 120), 'units'), add='+')
        canvas.bind('<Button-4>', lambda _e: canvas.yview_scroll(-3, 'units'), add='+')
        canvas.bind('<Button-5>', lambda _e: canvas.yview_scroll(3, 'units'), add='+')
        self._scroll_canvas = canvas
        return inner

    def _center_on_parent(self, width: int, height: int) -> None:
        """Open secondary windows in the centre of the usable desktop.

        The nominal size is clamped to the display first.  On a 1366x768
        laptop the 'large' and 'full' classes are taller than the usable
        desktop, and an unclamped window pushes its own footer - and with it
        the primary action - off the bottom of the screen.
        """

        try:
            self.update_idletasks()
            margin = 2 * metrics()['outer_pad']
            usable_width, usable_height = work_area(self)
            width = min(width, usable_width - margin)
            # The frame the window wears is counted too, or the footer - and
            # with it the primary action - lands under the taskbar.
            height = min(height, usable_height - margin - _FRAME_RESERVE)
            x = (usable_width - width) // 2
            y = (usable_height - height - _FRAME_RESERVE) // 2
            x = max(0, min(x, usable_width - width))
            y = max(0, min(y, usable_height - height - _FRAME_RESERVE))
            self.geometry(f'{width}x{height}+{x}+{y}')
        except tk.TclError:
            return

    def _normalise_on_map(self, event=None) -> None:
        if event is not None and event.widget is not self:
            return
        try:
            self.after_idle(lambda target=self: normalize_window_rtl(target))
        except tk.TclError:
            pass

    def _take_focus(self) -> None:
        """Open as the active window.

        A dark caption on an *inactive* window draws minimize, maximize and
        close in a grey so close to the caption itself that they read as
        missing until the user clicks the title bar.  The window opening in
        front, focused, is what makes the three controls visible.
        """

        try:
            self.deiconify()
            self.lift()
            self.focus_force()
        except tk.TclError:
            pass

    def minimize(self) -> None:
        self.state('iconic')

    def toggle_maximize(self) -> None:
        self.state('normal' if self._maximized else 'zoomed')
        self._maximized = not self._maximized

    def add_action(self, text: str, command, *, style: str = 'Ghost.TButton') -> ttk.Button:
        """Add a footer button.  The primary action is added first (leftmost).

        A destructive action next to a separate primary one goes to the far
        right, away from the primary and cancel pair (operator-approved N6);
        when the destructive action *is* the primary (a delete confirmation)
        it stays first like any other primary.
        """

        if self.footer is None:
            raise RuntimeError('This window was created with show_footer=False')
        button = ttk.Button(self.footer, text=text, command=command, style=style)
        actions = getattr(self, '_footer_actions', [])
        actions.append((button, style))
        self._footer_actions = actions
        self._layout_footer()
        return button

    def _layout_footer(self) -> None:
        m = metrics()
        actions = [(b, s) for b, s in getattr(self, '_footer_actions', []) if b.winfo_exists()]
        primary = {'Primary.TButton', 'Success.TButton', 'Warning.TButton'}
        split = any(s in primary for _b, s in actions) and any(s == 'Danger.TButton' for _b, s in actions)
        for button, _style in actions:
            button.pack_forget()
        for button, style in actions:
            side = 'right' if split and style == 'Danger.TButton' else 'left'
            button.pack(side=side, padx=m['gap'] // 2, pady=m['gap'])

    def close(self) -> None:
        # The window this one was opened from - a body Frame the caller
        # passed, not necessarily a toplevel itself, so its own toplevel is
        # what may need its grab restored below.
        parent = getattr(self, '_parent', None)
        try:
            owner = parent.winfo_toplevel() if parent is not None else None
        except tk.TclError:
            owner = None
        self.destroy()
        # Tk drops a local grab on destroy but does not hand it back to
        # whichever window held one before - closing this window would
        # otherwise leave ITS OWN owner window reachable again while that
        # owner is itself a still-open secondary window waiting to be
        # resolved (operator request 2026-09-28).
        try:
            if isinstance(owner, BarkavWindow) and owner.winfo_exists():
                owner.grab_set()
        except tk.TclError:
            pass


class BarkavDialog(BarkavWindow):
    """A focused window that owns the interaction until dismissed.

    Every BarkavWindow is already modal to its parent (see
    BarkavWindow.__init__); this subclass only picks the smaller default
    size a dialog needs, unlike a full screen.
    """

    size_class = 'small'


class BarkavWizard(BarkavWindow):
    """Multi-step window - section 10, wizard rules.

    Subclasses implement :meth:`render_step` and set :attr:`step_titles`.
    """

    size_class = 'large'
    step_titles: tuple[str, ...] = ()

    def __init__(self, parent: tk.Misc, title: str, **kwargs):
        self._step = 0
        super().__init__(parent, title, **kwargs)
        self._build_progress()
        self._build_navigation()
        self.show_step(0)

    @property
    def step_count(self) -> int:
        return max(1, len(self.step_titles))

    def _build_progress(self) -> None:
        p = palette()
        m = metrics()
        self.progress_bar = tk.Frame(
            self.body, bg=p['panel'], highlightbackground=p['border_subtle'], highlightthickness=1)
        self.progress_bar.pack(fill='x', pady=(0, m['gap']))
        # The count and the bar are one reading: which step of how many, and
        # how far along.  They are stacked on the left so the eye takes both
        # in at once instead of crossing the window between them.
        gauge = tk.Frame(self.progress_bar, bg=p['panel'])
        gauge.pack(side='left', padx=m['outer_pad'], pady=m['gap'])
        self._progress_label = tk.Label(
            gauge, bg=p['panel'], fg=p['text_secondary'], font=font('small'), anchor='w')
        self._progress_label.pack(anchor='w')
        self._progress_track = tk.Frame(gauge, bg=p['surface_alt'], height=6, width=220)
        self._progress_track.pack(anchor='w', pady=(3, 0))
        self._progress_track.pack_propagate(False)
        self._progress_fill = tk.Frame(self._progress_track, bg=p['accent'])
        self._progress_fill.place(x=0, y=0, relheight=1, relwidth=0)

        self.step_host = tk.Frame(self.body, bg=p['surface'])
        self.step_host.pack(fill='both', expand=True)

    def _build_navigation(self) -> None:
        # Primary action leftmost, per section 10.
        self._next_button = self.add_action('بعدی  ←', self.next_step, style='Primary.TButton')
        self._back_button = self.add_action('→  قبلی', self.previous_step)

    def show_step(self, index: int) -> None:
        self._step = max(0, min(index, self.step_count - 1))
        for child in self.step_host.winfo_children():
            child.destroy()
        self.render_step(self._step, self.step_host)
        self._sync_navigation()

    def _sync_navigation(self) -> None:
        current, total = self._step + 1, self.step_count
        self._progress_label.configure(text=f'مرحله {fa(current)} از {fa(total)}')
        self._progress_fill.place_configure(relwidth=current / total)
        # Section 10: "back" stays visible but disabled on the first step.
        self._back_button.state(['disabled'] if self._step == 0 else ['!disabled'])
        self._next_button.configure(text='ذخیره' if self._step == total - 1 else 'بعدی  ←')

    def next_step(self) -> None:
        if not self.validate_step(self._step):
            return
        if self._step == self.step_count - 1:
            self.finish()
            return
        self.show_step(self._step + 1)

    def previous_step(self) -> None:
        self.show_step(self._step - 1)

    # ------------------------------------------------------ subclass contract

    def render_step(self, index: int, parent: tk.Frame) -> None:
        raise NotImplementedError('Wizards must implement render_step()')

    def validate_step(self, index: int) -> bool:
        """Return False to keep the user on the current step."""

        return True

    def finish(self) -> None:
        self.close()


class ConfirmDialog(BarkavDialog):
    """A yes/no confirmation with full window chrome - section 10.

    ``messagebox.askyesno`` never carries the app's caption, theme or
    minimize/maximize controls; section 10 requires every window, dialogs
    included, to have all three. Use :func:`confirm` rather than this class
    directly.
    """

    size_class = 'tiny'

    def __init__(self, parent: tk.Misc, title: str, message: str, *,
                 confirm_text: str = 'تأیید', cancel_text: str = 'انصراف',
                 destructive: bool = True):
        self.result = False
        super().__init__(parent, title)
        p = palette()
        tk.Label(
            self.body, text=message, bg=p['surface'], fg=p['text_primary'],
            font=font('body'), justify='right', anchor='e', wraplength=380,
        ).pack(fill='both', expand=True)
        # Section 10: the primary action is leftmost. It is styled destructive
        # here because the action it confirms is the destructive one - a
        # generic Primary.TButton would read as safe on a delete prompt.
        self.add_action(confirm_text, self._accept,
                        style='Danger.TButton' if destructive else 'Primary.TButton')
        self.add_action(cancel_text, self.close, style='Ghost.TButton')

    def _accept(self) -> None:
        self.result = True
        self.close()


def confirm(parent: tk.Misc, title: str, message: str, *, confirm_text: str = 'تأیید',
            cancel_text: str = 'انصراف', destructive: bool = True) -> bool:
    """A themed replacement for ``messagebox.askyesno``.

    Blocks until the dialog is answered or closed, same as ``askyesno``, and
    returns whether the confirming action was chosen.
    """

    from table_actions import current_delete_choice
    if current_delete_choice() is not None and any(word in title for word in ('حذف','لغو','ابطال')):
        return True
    dialog = ConfirmDialog(parent, title, message, confirm_text=confirm_text,
                          cancel_text=cancel_text, destructive=destructive)
    dialog.wait_window()
    return dialog.result


def attach_tooltip(widget: tk.Misc, text, *, delay_ms=450, side: str = 'left') -> None:
    """Section 11: a small hover hint beside ``widget``.

    ``text`` and ``delay_ms`` may be callables, so a hint can follow state
    (a collapsed rail shows its hints sooner, for example). ``side`` is where
    the hint opens relative to the widget; the rail sits on the right edge,
    so its hints open to the left, over the page.
    """

    state = {'after': None, 'tip': None}

    def cancel() -> None:
        if state['after'] is not None:
            try:
                widget.after_cancel(state['after'])
            except tk.TclError:
                pass
            state['after'] = None

    def hide(_event=None) -> None:
        cancel()
        tip = state['tip']
        state['tip'] = None
        if tip is not None:
            try:
                tip.destroy()
            except tk.TclError:
                pass

    def show() -> None:
        state['after'] = None
        value = text() if callable(text) else text
        try:
            if not value or not widget.winfo_exists() or not widget.winfo_ismapped():
                return
        except tk.TclError:
            return
        p = palette()
        tip = tk.Toplevel(widget)
        tip._barkav_normalise_job187 = 'chrome'   # a hint, not a dialog to restyle
        tip.overrideredirect(True)
        try:
            tip.attributes('-topmost', True)
        except tk.TclError:
            pass
        tk.Label(
            tip, text=str(value), bg=p['surface_alt'], fg=p['text_primary'],
            font=font('small'), padx=10, pady=4, bd=0, justify='right',
            highlightthickness=1, highlightbackground=p['border'],
        ).pack()
        tip.update_idletasks()
        width, height = tip.winfo_reqwidth(), tip.winfo_reqheight()
        if side == 'left':
            x = widget.winfo_rootx() - width - 8
        elif side == 'below':
            x = widget.winfo_rootx() + (widget.winfo_width() - width) // 2
        else:
            x = widget.winfo_rootx() + widget.winfo_width() + 8
        if side == 'below':
            y = widget.winfo_rooty() + widget.winfo_height() + 6
        else:
            y = widget.winfo_rooty() + (widget.winfo_height() - height) // 2
        tip.geometry(f'+{max(0, x)}+{max(0, y)}')
        state['tip'] = tip

    def enter(_event=None) -> None:
        hide()
        delay = delay_ms() if callable(delay_ms) else delay_ms
        try:
            state['after'] = widget.after(int(delay), show)
        except tk.TclError:
            state['after'] = None

    widget.bind('<Enter>', enter, add='+')
    widget.bind('<Leave>', hide, add='+')
    widget.bind('<ButtonPress>', hide, add='+')
    widget.bind('<Destroy>', hide, add='+')


def _fold(text: str) -> str:
    """Search key: Arabic ي/ك folded to Persian, ZWNJ and case ignored."""

    return (str(text).replace('ي', 'ی').replace('ك', 'ک').replace('‌', ' ')
            .replace('ة', 'ه').lower())


class CommandPalette(tk.Toplevel):
    """Section 11: the Ctrl+K "go anywhere, run anything" surface.

    ``entries`` are ``(title, subtitle, group, icon, callback)`` tuples. Typing
    filters them; Up/Down move, Enter runs, Esc or clicking away closes.
    """

    MAX_ROWS = 10
    WIDTH = 560

    def __init__(self, parent: tk.Misc, entries, *, placeholder: str = ''):
        from barkav_themes.tokens import mix
        from .line_icons import icon as line_icon

        host = parent.winfo_toplevel()
        super().__init__(host)
        self.overrideredirect(True)
        try:
            self.attributes('-topmost', True)
        except tk.TclError:
            pass
        self._line_icon = line_icon
        self._entries = list(entries)
        self._shown: list[tuple] = []
        self._rows: list[tuple] = []
        self._index = 0
        self._last_query = None
        self._closing = False
        p = palette()
        self._p = p
        self._bg = p['surface_alt']
        self._hot = mix(p['surface_alt'], p['accent'], 0.16)
        self._muted = mix(p['text_secondary'], p['surface_alt'], 0.25)

        shell = tk.Frame(self, bg=self._bg, highlightthickness=1,
                         highlightbackground=p['border'], bd=0)
        shell.pack(fill='both', expand=True)
        head = tk.Frame(shell, bg=self._bg)
        head.pack(fill='x', padx=12, pady=(10, 8))
        self._search_icon = line_icon('search', size=18, colour=p['text_secondary'],
                                      background=self._bg, master=self)
        tk.Label(head, image=self._search_icon, bg=self._bg).pack(side='right')
        self.query = tk.StringVar()
        self.entry = tk.Entry(
            head, textvariable=self.query, bg=self._bg, fg=p['text_primary'],
            insertbackground=p['text_primary'], relief='flat', bd=0,
            highlightthickness=0, font=font('title', bold=False), justify='right',
        )
        self.entry.pack(side='right', fill='x', expand=True, padx=(8, 8), ipady=4)
        tk.Label(head, text='Esc', bg=self._bg, fg=self._muted, font=font('small')).pack(side='left')
        tk.Frame(shell, bg=p['border'], height=1).pack(fill='x')
        self._hint = tk.Label(shell, text=placeholder, bg=self._bg, fg=self._muted,
                              font=font('small'), anchor='e', justify='right')
        self._hint.pack(fill='x', padx=14, pady=(6, 0))
        self.results = tk.Frame(shell, bg=self._bg)
        self.results.pack(fill='both', expand=True, padx=6, pady=(4, 8))

        for sequence, handler in (
            ('<Escape>', lambda _e: self.close()),
            ('<Return>', lambda _e: self.run()),
            ('<KP_Enter>', lambda _e: self.run()),
            ('<Down>', lambda _e: self.move(1)),
            ('<Up>', lambda _e: self.move(-1)),
        ):
            self.entry.bind(sequence, lambda e, h=handler: (h(e), 'break')[1])
        self.entry.bind('<KeyRelease>', lambda _e: self.refresh(), add='+')
        # Closing is explicit - Esc, running an entry, or the owner closing
        # it on a click elsewhere - never on focus loss: a background task
        # that moves keyboard focus must not snatch the palette away.
        self._barkav_normalise_job187 = 'chrome'   # not a dialog to restyle

        self.refresh()
        self.update_idletasks()
        x = host.winfo_rootx() + (host.winfo_width() - self.WIDTH) // 2
        y = host.winfo_rooty() + 90
        self.geometry(f'{self.WIDTH}x{self.winfo_reqheight()}+{max(0, x)}+{max(0, y)}')
        self.lift()
        self.entry.focus_force()

    # -- filtering -----------------------------------------------------
    def _matches(self, query: str) -> list[tuple]:
        words = [w for w in _fold(query).split() if w]
        if not words:
            seen: dict[str, int] = {}
            picked = []
            for entry in self._entries:
                group = entry[2]
                if seen.get(group, 0) < 5:
                    seen[group] = seen.get(group, 0) + 1
                    picked.append(entry)
            return picked[:self.MAX_ROWS]
        ranked = []
        for order, entry in enumerate(self._entries):
            title, subtitle = _fold(entry[0]), _fold(entry[1])
            haystack = f'{title} {subtitle}'
            if not all(w in haystack for w in words):
                continue
            if title.startswith(words[0]):
                score = 0
            elif all(w in title for w in words):
                score = 1
            else:
                score = 2
            ranked.append((score, order, entry))
        ranked.sort(key=lambda item: (item[0], item[1]))
        return [entry for _score, _order, entry in ranked[:self.MAX_ROWS]]

    def refresh(self) -> None:
        query = self.query.get()
        if query == self._last_query:
            return
        self._last_query = query
        self._shown = self._matches(query)
        self._index = 0
        self._render()

    def _render(self) -> None:
        for child in self.results.winfo_children():
            child.destroy()
        self._rows = []
        p = self._p
        if not self._shown:
            tk.Label(self.results, text='چیزی پیدا نشد.', bg=self._bg, fg=self._muted,
                     font=font('body'), anchor='e').pack(fill='x', padx=10, pady=10)
        group = None
        for position, entry in enumerate(self._shown):
            title, subtitle, entry_group, icon_name, _callback = entry
            if entry_group != group:
                group = entry_group
                tk.Label(self.results, text=str(group), bg=self._bg, fg=self._muted,
                         font=font('small'), anchor='e').pack(fill='x', padx=10, pady=(6, 1))
            row = tk.Frame(self.results, bg=self._bg, cursor='hand2')
            row.pack(fill='x', padx=2, pady=1)
            image_label = tk.Label(row, bg=self._bg)
            image_label.pack(side='right', padx=(8, 8), pady=5)
            name = tk.Label(row, text=str(title), bg=self._bg, fg=p['text_primary'],
                            font=font('body'), anchor='e')
            name.pack(side='right')
            detail = tk.Label(row, text=str(subtitle or ''), bg=self._bg, fg=self._muted,
                              font=font('small'), anchor='w')
            detail.pack(side='left', padx=(10, 6))
            for widget in (row, image_label, name, detail):
                widget.bind('<Button-1>', lambda _e, i=position: self.run(i))
                widget.bind('<Enter>', lambda _e, i=position: self._select(i))
            self._rows.append((row, image_label, name, detail, icon_name))
        self._paint()
        try:
            self.update_idletasks()
            self.geometry(f'{self.WIDTH}x{self.winfo_reqheight()}')
        except tk.TclError:
            pass

    def _paint(self) -> None:
        p = self._p
        for position, (row, image_label, name, detail, icon_name) in enumerate(self._rows):
            hot = position == self._index
            bg = self._hot if hot else self._bg
            for widget in (row, image_label, name, detail):
                widget.configure(bg=bg)
            image = self._line_icon(icon_name or 'page', size=16,
                                    colour=p['accent'] if hot else p['text_secondary'],
                                    background=bg, master=self)
            image_label.configure(image=image)
            image_label.image = image

    def _select(self, position: int) -> None:
        if position != self._index:
            self._index = position
            self._paint()

    def move(self, step: int) -> None:
        if self._rows:
            self._index = (self._index + step) % len(self._rows)
            self._paint()

    def run(self, position: int | None = None) -> None:
        if position is not None:
            self._index = position
        if not self._shown:
            return
        callback = self._shown[max(0, min(self._index, len(self._shown) - 1))][4]
        master = self.master
        self.close()
        try:
            master.after(15, callback)
        except tk.TclError:
            pass

    def close(self) -> None:
        if self._closing:
            return
        self._closing = True
        try:
            self.destroy()
        except tk.TclError:
            pass


def show_inline_error(window: tk.Misc, message: str, *, kind: str = 'error',
                      duration_ms: int = 8000, on_lost=None) -> tk.Frame:
    """Section 11: a form's error shown inside the form (operator-approved N5).

    A strip at the bottom of ``window``, above its footer when it has one,
    instead of a separate modal box. ``on_lost`` is called if the window
    closes within a moment of the message appearing, so a message about a
    dialog that closes itself right after is never silently lost.
    """

    import time

    from barkav_themes.tokens import mix

    p = palette()
    accent = p['danger'] if kind == 'error' else p['warning']
    old = getattr(window, '_barkav_inline_error', None)
    if old is not None:
        try:
            old.destroy()
        except tk.TclError:
            pass
    fill = mix(p['surface_alt'], accent, 0.18)
    bar = tk.Frame(window, bg=fill, highlightthickness=1, highlightbackground=accent, bd=0)
    tk.Frame(bar, bg=accent, width=4).pack(side='right', fill='y')
    close = tk.Label(bar, text='×', bg=fill, fg=p['text_secondary'], font=font('body'),
                     cursor='hand2', padx=10)
    close.pack(side='left', fill='y')
    tk.Label(bar, text=str(message), bg=fill, fg=p['text_primary'], font=font('body'),
             justify='right', anchor='e', wraplength=520, padx=12, pady=8,
             ).pack(side='right', fill='both', expand=True)
    window._barkav_inline_error = bar
    shown_at = time.monotonic()

    def dismiss(_event=None) -> None:
        try:
            bar.destroy()
        except tk.TclError:
            pass

    close.bind('<Button-1>', dismiss)
    try:
        window.update_idletasks()
        footer = getattr(window, 'footer', None)
        lift = footer.winfo_height() if footer is not None and footer.winfo_ismapped() else 0
        bar.place(relx=0.5, rely=1.0, y=-(lift + 10), anchor='s',
                  width=max(240, min(640, window.winfo_width() - 32)))
        bar.lift()
        timer = window.after(duration_ms, dismiss)
    except tk.TclError:
        timer = None

    def lost(event) -> None:
        if event.widget is not window:
            return
        if timer is not None:
            try:
                window.after_cancel(timer)
            except tk.TclError:
                pass
        if on_lost is not None and time.monotonic() - shown_at < 2.5:
            on_lost()

    window.bind('<Destroy>', lost, add='+')
    return bar


class PopupMenu(tk.Toplevel):
    """Section 11: the product's own drop-down instead of the native menu.

    A native ``tk.Menu`` is drawn by Windows in its own light colours, so a
    theme or export menu looked like it belonged to another program. This is
    the same list in the theme's colours: optional section titles, an icon,
    a check mark on the current choice and a muted hint per row.

    ``sections`` is ``[(title_or_None, [item, ...]), ...]`` where an item is
    a dict with ``label`` and ``command`` and optionally ``icon`` (a
    line_icons name), ``checked`` and ``hint``. It closes on Esc, on a click
    anywhere else in the window that opened it, or once a row is chosen.

    ``compact`` packs the rows closer (the rail's theme flyout, operator
    round 2026-09-27); with ``hover_close`` a menu that opened on pointing
    also closes once the pointer has left it and its anchor.
    """

    _current: 'PopupMenu | None' = None

    def __init__(self, anchor: tk.Misc, sections, *, side: str = 'below', min_width: int = 200,
                 align: str = 'right', compact: bool = False, hover_close: bool = False):
        from barkav_themes.tokens import mix
        from .line_icons import icon as line_icon
        from .skin import rounded_backdrop

        PopupMenu.close_open()
        host = anchor.winfo_toplevel()
        super().__init__(host)
        self._barkav_normalise_job187 = 'chrome'
        self.overrideredirect(True)
        try:
            self.attributes('-topmost', True)
        except tk.TclError:
            pass
        p = palette()
        m = metrics()
        self._bg = p['surface_alt']
        self._hot = mix(p['surface_alt'], p['accent'], 0.16)
        self._muted = mix(p['text_secondary'], p['surface_alt'], 0.2)
        self.configure(bg=p['bg'])
        rounded_backdrop(self, fill=self._bg, page=p['bg'], radius=max(8, m.get('radius', 6) + 2),
                         border=p['border'], master=self)
        body = tk.Frame(self, bg=self._bg, bd=0)
        body.pack(fill='both', expand=True, padx=3, pady=3 if compact else 5)
        self._images = []
        self._row_pad = 3 if compact else 6
        self._keyboard_rows = []
        for index, (title, items) in enumerate(sections):
            if index:
                tk.Frame(body, bg=p['border_subtle'], height=1).pack(
                    fill='x', padx=10, pady=2 if compact else 4)
            if title:
                tk.Label(body, text=rtl(str(title)), bg=self._bg, fg=self._muted, font=font('small'),
                         anchor='e').pack(fill='x', padx=12, pady=(2, 0) if compact else (4, 2))
            for item in items:
                self._row(body, item, p, line_icon)
        self.bind('<Escape>', lambda _e: self.close())
        self.bind('<Down>', lambda _e: self._move_active_row(1), add='+')
        self.bind('<Up>', lambda _e: self._move_active_row(-1), add='+')
        self.bind('<Return>', self._choose_active_row, add='+')
        self.bind('<KP_Enter>', self._choose_active_row, add='+')
        self.update_idletasks()
        width = max(min_width, self.winfo_reqwidth())
        height = self.winfo_reqheight()
        ax, ay = anchor.winfo_rootx(), anchor.winfo_rooty()
        aw, ah = anchor.winfo_width(), anchor.winfo_height()
        # ``align`` lines the menu up with the anchor's right edge (where an
        # RTL row starts) or, for an anchor at the window's left end, its left.
        edge = ax if align == 'left' else ax + aw - width
        if side == 'left':
            x, y = ax - width - 6, ay + ah - height
        elif side == 'above':
            x, y = edge, ay - height - 4
        else:
            x, y = edge, ay + ah + 4
        screen_w, screen_h = self.winfo_screenwidth(), self.winfo_screenheight()
        x = max(4, min(x, screen_w - width - 4))
        y = max(4, min(y, screen_h - height - 4))
        self.geometry(f'{width}x{height}+{x}+{y}')
        rounded_backdrop(self, fill=self._bg, page=p['bg'], radius=max(8, m.get('radius', 6) + 2),
                         border=p['border'], master=self)
        self.lift()
        try:
            self.focus_force()
        except tk.TclError:
            pass
        if self._keyboard_rows:
            self._set_active_row(0)
        PopupMenu._current = self
        self._anchor = anchor
        if hover_close:
            self.bind('<Leave>', lambda _e: self.after(300, self.close_if_away), add='+')
        if not getattr(host, '_barkav_popup_click_bound', False):
            host._barkav_popup_click_bound = True
            host.bind('<ButtonPress>', PopupMenu._host_press, add='+')

    @classmethod
    def _host_press(cls, event) -> None:
        # The press that opened the menu reaches the window too; a click on
        # the anchor itself must not close what it just opened.
        current = cls._current
        if current is None:
            return
        anchor = getattr(current, '_anchor', None)
        try:
            if anchor is not None and str(event.widget).startswith(str(anchor)):
                return
        except (tk.TclError, AttributeError):
            pass
        cls.close_open()

    def _row(self, parent, item, p, line_icon) -> None:
        row = tk.Frame(parent, bg=self._bg, cursor='hand2', highlightthickness=0)
        row.pack(fill='x', padx=4, pady=1)
        icon_name = item.get('icon')
        parts = [row]
        if icon_name:
            image = line_icon(icon_name, size=16, colour=p['text_secondary'], background=None, master=self)
            if image is not None:
                self._images.append(image)
                label = tk.Label(row, image=image, bg=self._bg)
                label.pack(side='right', padx=(10, 2), pady=self._row_pad)
                parts.append(label)
        text = tk.Label(row, text=rtl(str(item.get('label', ''))), bg=self._bg, fg=p['text_primary'],
                        font=font('body', bold=bool(item.get('checked'))), anchor='e')
        text.pack(side='right', padx=(6 if icon_name else 12, 6), pady=self._row_pad)
        parts.append(text)
        if item.get('checked'):
            mark = tk.Label(row, text='✓', bg=self._bg, fg=p['accent'], font=font('body', bold=True))
            mark.pack(side='left', padx=(10, 4))
            parts.append(mark)
        if item.get('hint'):
            hint = tk.Label(row, text=rtl(str(item['hint'])), bg=self._bg, fg=self._muted, font=font('small'))
            hint.pack(side='left', padx=(10, 4))
            parts.append(hint)

        def paint(on: bool) -> None:
            for widget in parts:
                try:
                    widget.configure(bg=self._hot if on else self._bg)
                except tk.TclError:
                    pass
            try:
                row.configure(
                    highlightbackground=p['accent'] if on else self._bg,
                    highlightcolor=p['accent'] if on else self._bg,
                    highlightthickness=1 if on else 0,
                )
            except tk.TclError:
                pass

        command = item.get('command')
        row_index = len(self._keyboard_rows)
        self._keyboard_rows.append((paint, command))
        for widget in parts:
            widget.bind('<Enter>', lambda _e, i=row_index: self._set_active_row(i), add='+')
            widget.bind('<ButtonRelease-1>', lambda _e, c=command: self._choose(c), add='+')

    def _set_active_row(self, index: int) -> None:
        if not self._keyboard_rows:
            return
        self._active_row = max(0, min(index, len(self._keyboard_rows) - 1))
        for row_index, (paint, _command) in enumerate(self._keyboard_rows):
            paint(row_index == self._active_row)

    def _move_active_row(self, direction: int):
        if self._keyboard_rows:
            current = getattr(self, '_active_row', 0)
            self._set_active_row((current + direction) % len(self._keyboard_rows))
        return 'break'

    def _choose_active_row(self, _event=None):
        if self._keyboard_rows:
            _paint, command = self._keyboard_rows[getattr(self, '_active_row', 0)]
            self._choose(command)
        return 'break'

    def close_if_away(self) -> None:
        """Close unless the pointer is over this menu or its anchor."""
        try:
            if not self.winfo_exists():
                return
            under = self.winfo_containing(*self.winfo_pointerxy())
        except (tk.TclError, KeyError):
            under = None
        path = str(under) if under is not None else ''
        for keep in (self, getattr(self, '_anchor', None)):
            if keep is not None and (path == str(keep) or path.startswith(f'{keep}.')):
                return
        if PopupMenu._current is self:
            PopupMenu.close_open()
        else:
            try:
                self.destroy()
            except tk.TclError:
                pass

    def _choose(self, command) -> None:
        master = self.master
        self.close()
        if command is not None:
            try:
                master.after(10, command)
            except tk.TclError:
                pass

    @classmethod
    def close_open(cls) -> None:
        current, cls._current = cls._current, None
        if current is not None:
            try:
                current.destroy()
            except tk.TclError:
                pass

    def close(self) -> None:
        if PopupMenu._current is self:
            PopupMenu._current = None
        try:
            self.destroy()
        except tk.TclError:
            pass
