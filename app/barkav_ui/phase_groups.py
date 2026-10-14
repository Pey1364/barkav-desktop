"""Section 11 (operator-approved D3, reworked 2026-09-27): the 32 phases.

One row of 32 cells across the card, phase 1 on the right where the row
starts; each phase's name runs diagonally under its own cell. A cell fills
from the bottom - to the physical progress the operator recorded for it, or,
where none is recorded, to the share of its budget already spent, so the row
moves as costs are recorded. Its colour is the phase's state; a phase with
money spent and no state of its own reads as in progress. The ring on the
right is the whole project, each phase weighed by its budget.

Pointing at a cell shows a small card with that phase's figures; a click
opens the phase and a double click edits its progress, as the numbered
buttons this replaced did. The colour key is a separate small canvas
(PhaseLegend) that the dashboard puts in the card's heading.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont

from PIL import Image, ImageDraw, ImageTk

from barkav_themes.tokens import mix

from .art import rgb
from .badges import progress_ring
from .bidi import rtl
from .skin import rounded_plate_image
from .theme import font

PHASES = 32
STATUS_TEXT = {
    'NOT_STARTED': 'شروع‌نشده', 'ACTIVE': 'در حال انجام',
    'PAUSED': 'متوقف', 'COMPLETED': 'تکمیل‌شده',
}
LEGEND = (('ACTIVE', 'فعال یا تکمیل'), ('PAUSED', 'متوقف'), ('NOT_STARTED', 'شروع‌نشده'))
_RING = 52
_RING_COLUMN = 128
# Operator round 2026-09-27: each cell carries its own percent above it and
# its phase number under it; the name shows on hover. The cells are taller
# so the fill reads at a glance.
_PERCENT_TOP = 2
_CELL_HEIGHT = 40
_CELL_GAP = 3
_SUPERSAMPLE = 4
_PERSIAN = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')


def _fa(value) -> str:
    return str(value).translate(_PERSIAN)


def _money(value) -> str:
    try:
        return _fa(f'{int(value):,}')
    except (TypeError, ValueError):
        return _fa(value)


class PhaseGroups(tk.Canvas):
    """``colours`` names the four status fills and 'track', 'text', 'muted',
    'accent' and 'ring' (optionally 'card' and 'border' for the hover card);
    ``on_open``/``on_edit`` take a phase number."""

    def __init__(self, parent: tk.Misc, *, background: str, colours: dict[str, str],
                 on_open=None, on_edit=None, on_overall=None):
        super().__init__(parent, height=100, bg=background, bd=0, highlightthickness=0)
        self._background = background
        self._colours = dict(colours)
        self._colours.setdefault('card', mix(background, self._colours['text'], 0.08))
        self._colours.setdefault('border', self._colours['accent'])
        self._on_open, self._on_edit, self._on_overall = on_open, on_edit, on_overall
        self._progress: dict[int, dict] = {}
        self._spending: dict[int, tuple[int, int]] = {}
        self._names: dict[int, str] = {}
        self._overall = 0.0
        self._cells: dict[int, tuple[int, int, int, int]] = {}
        self._ring_box = (0, 0, 0, 0)
        self._hover: int | None = None
        self._images: list = []
        self._cell_cache: dict[tuple, object] = {}
        self._font = font('small', widget=self)
        self._font_bold = font('small', widget=self, bold=True)
        self._ring_font = font('body', widget=self, bold=True)
        self._measure = tkfont.Font(root=self, font=self._font)
        self._measure_bold = tkfont.Font(root=self, font=self._font_bold)
        line = int(self._measure.metrics('linespace') or 14)
        self._line = line
        self._cell_top = _PERCENT_TOP + line + 2
        # The percents, the cells and the numbers under them.
        self.configure(height=max(self._cell_top + _CELL_HEIGHT + 3 + line + 3, _RING + 18 + line))
        self.bind('<Configure>', lambda _e: self._redraw(), add='+')
        self.bind('<Motion>', self._motion, add='+')
        self.bind('<Leave>', lambda _e: self._set_hover(None), add='+')
        self.bind('<Button-1>', self._click, add='+')
        self.bind('<Double-1>', self._double, add='+')

    # ------------------------------------------------------------ public
    def set_data(self, progress: dict[int, dict], names: dict[int, str], overall: float = 0.0,
                 spending: dict[int, tuple[int, int]] | None = None) -> None:
        """``progress``: the recorded status and physical_progress per phase;
        ``spending``: (spent, budget) per phase. With spending, the ring is
        worked out from the cells; without, ``overall`` (0..1) is shown."""

        self._progress = {int(k): dict(v or {}) for k, v in (progress or {}).items()}
        self._names = {int(k): str(v) for k, v in (names or {}).items()}
        self._spending = {}
        for key, value in (spending or {}).items():
            try:
                spent, budget = value
                self._spending[int(key)] = (max(0, int(spent or 0)), max(0, int(budget or 0)))
            except (TypeError, ValueError):
                continue
        if spending is not None:
            self._overall = self.overall()
        else:
            try:
                self._overall = max(0.0, min(1.0, float(overall or 0)))
            except (TypeError, ValueError):
                self._overall = 0.0
        self._redraw()

    def _figures(self, number: int) -> tuple[str, float, int, int, float]:
        info = self._progress.get(number) or {}
        state = str(info.get('status') or 'NOT_STARTED').upper()
        try:
            physical = max(0.0, min(100.0, float(info.get('physical_progress') or 0)))
        except (TypeError, ValueError):
            physical = 0.0
        spent, budget = self._spending.get(number, (0, 0))
        cost = min(100.0, spent * 100.0 / budget) if budget > 0 else 0.0
        return state, physical, spent, budget, cost

    def status(self, number: int) -> tuple[str, float]:
        """The state and fill (0-100) the cell shows."""

        state, physical, spent, _budget, cost = self._figures(number)
        if state == 'COMPLETED':
            percent = physical if physical > 0 else 100.0
        elif physical > 0:
            percent = physical
        else:
            percent = cost
        if state == 'NOT_STARTED' and (physical > 0 or spent > 0):
            state = 'ACTIVE'
        return state, percent

    def started(self) -> int:
        return sum(1 for n in range(1, PHASES + 1) if self.status(n)[0] != 'NOT_STARTED')

    def overall(self) -> float:
        """The cells' fills averaged, each phase weighed by its budget."""

        pairs = [(self._spending.get(n, (0, 0))[1], self.status(n)[1]) for n in range(1, PHASES + 1)]
        weight = sum(budget for budget, _percent in pairs)
        if weight > 0:
            return max(0.0, min(1.0, sum(b * pct for b, pct in pairs) / weight / 100))
        return max(0.0, min(1.0, sum(pct for _b, pct in pairs) / PHASES / 100))

    # ---------------------------------------------------------- painting
    def _cell_image(self, width: int, height: int, state: str, percent: float, hot: bool):
        c = self._colours
        fill = c.get(state) or c['ACTIVE']
        level = 0 if percent <= 0 else max(3, round(height * percent / 100))
        if level == 0 and state in ('ACTIVE', 'PAUSED'):
            level = 3  # started, nothing measured yet: a sliver shows it
        key = (width, height, fill, level, hot)
        cached = self._cell_cache.get(key)
        if cached is not None:
            return cached
        s = _SUPERSAMPLE
        w, h = width * s, height * s
        radius = min(5, width // 3) * s
        cell = Image.new('RGBA', (w, h), rgb(c['track']) + (255,))
        if level:
            ImageDraw.Draw(cell).rectangle((0, h - level * s, w, h), fill=rgb(fill) + (255,))
        mask = Image.new('L', (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, fill=255)
        plate = Image.new('RGBA', (w, h), rgb(self._background) + (255,))
        plate.paste(cell, (0, 0), mask)
        if hot:
            ImageDraw.Draw(plate).rounded_rectangle((0, 0, w - 1, h - 1), radius=radius,
                                                    outline=rgb(c['accent']) + (255,), width=2 * s)
        photo = ImageTk.PhotoImage(plate.resize((width, height), Image.LANCZOS).convert('RGB'),
                                   master=self)
        self._cell_cache[key] = photo
        return photo

    def _fit(self, text: str, width: int, measure: tkfont.Font | None = None) -> str:
        measure = measure or self._measure
        if width <= 0 or measure.measure(text) <= width:
            return text
        while text and measure.measure(text + '…') > width:
            text = text[:-1]
        return text + '…'

    def _redraw(self) -> None:
        try:
            width = self.winfo_width()
        except tk.TclError:
            return
        if width < 200:
            return
        self.delete('all')
        self._images = []
        self._cells = {}
        c = self._colours
        # The ring and its caption on the right, where the row starts.
        ring_left = width - 6 - _RING_COLUMN
        ring_x = ring_left + _RING_COLUMN // 2
        ring = progress_ring(self._overall, size=_RING, width=6, colour=c['ring'], track=c['track'],
                             background=self._background, master=self)
        self._images.append(ring)
        self.create_image(ring_x, 4 + _RING // 2, image=ring)
        self.create_text(ring_x, 4 + _RING // 2, text=f'{_fa(round(self._overall * 100))}٪',
                         fill=c['text'], font=self._ring_font)
        self.create_text(ring_x, 4 + _RING + 12,
                         text=rtl(f'{_fa(self.started())} از {_fa(PHASES)} فاز شروع شده'),
                         fill=c['muted'], font=self._font)
        self._ring_box = (ring_x - _RING // 2, 4, ring_x + _RING // 2, 4 + _RING)

        right, left = ring_left - 14, 8
        cell_width = (right - left - _CELL_GAP * (PHASES - 1)) / PHASES
        top = self._cell_top
        number_top = top + _CELL_HEIGHT + 3 + self._line // 2
        percent_y = _PERCENT_TOP + self._line // 2
        for number in range(1, PHASES + 1):
            x1 = int(round(right - (number - 1) * (cell_width + _CELL_GAP)))
            x0 = int(round(x1 - cell_width))
            state, percent = self.status(number)
            hot = number == self._hover
            image = self._cell_image(max(6, x1 - x0), _CELL_HEIGHT, state, percent, hot)
            self._images.append(image)
            self.create_image(x0, top, image=image, anchor='nw')
            self._cells[number] = (x0, top, x1, top + _CELL_HEIGHT)
            centre = (x0 + x1) / 2
            label = f'{_fa(round(percent))}٪'
            if self._measure.measure(label) > x1 - x0 + _CELL_GAP:
                label = _fa(round(percent))
            self.create_text(centre, percent_y, text=label,
                             fill=c['text'] if percent > 0 else c['muted'], font=self._font)
            self.create_text(centre, number_top, text=_fa(format(number, '02d')),
                             fill=c['text'] if hot else c['muted'],
                             font=self._font_bold if hot else self._font)
        if self._hover is not None:
            self._hover_card(self._hover, left, right)

    def _hover_card(self, number: int, left: int, right: int) -> None:
        c = self._colours
        state, percent = self.status(number)
        _raw, physical, spent, budget, cost = self._figures(number)
        name = self._names.get(number) or ''
        state_line = f'{_fa(round(percent))}٪ · {STATUS_TEXT.get(state, "")}'
        if physical > 0:
            state_line += f' · فیزیکی {_fa(round(physical))}٪'
        lines = [
            (' · '.join(part for part in (f'فاز {_fa(format(number, "02d"))}', name) if part), True),
            (rtl(state_line), False),
        ]
        if budget > 0 or spent > 0:
            spent_text = f'هزینه‌شده {_money(spent)}'
            if budget > 0:
                spent_text += f' از {_money(budget)} ({_fa(round(cost))}٪)'
            lines.append((spent_text, False))
        line_height = int(self._measure.metrics('linespace') or 14) + 1
        text_width = max(self._measure_bold.measure(text) if bold else self._measure.measure(text)
                         for text, bold in lines)
        box_w = min(int(text_width) + 22, right - left)
        box_h = line_height * len(lines) + 10
        x0, y0, x1, _y1 = self._cells[number]
        box_right = max(left + box_w, min(right, x1 + 8))
        # Under the cell, but never past the canvas's foot.
        top = max(0, min(self._cell_top + _CELL_HEIGHT + 4, self.winfo_height() - box_h - 2))
        plate = rounded_plate_image(box_w, box_h, fill=c['card'], page=self._background, radius=8,
                                    border=c['border'], master=self)
        self._images.append(plate)
        self.create_image(box_right - box_w, top, image=plate, anchor='nw')
        y = top + 5 + line_height // 2
        for text, bold in lines:
            self.create_text(box_right - 11, y, text=text, anchor='e', fill=c['text'] if bold else c['muted'],
                             font=self._font_bold if bold else self._font)
            y += line_height

    # ------------------------------------------------------------ pointer
    def _phase_at(self, x: int, y: int) -> int | None:
        for number, (x0, y0, x1, y1) in self._cells.items():
            if x0 <= x <= x1 and y0 <= y <= y1:
                return number
        return None

    def _set_hover(self, number: int | None) -> None:
        if number != self._hover:
            self._hover = number
            self._redraw()

    def _motion(self, event) -> None:
        number = self._phase_at(event.x, event.y)
        self._set_hover(number)
        x0, y0, x1, y1 = self._ring_box
        over_ring = x0 <= event.x <= x1 and y0 <= event.y <= y1
        try:
            self.configure(cursor='hand2' if number or (over_ring and self._on_overall) else '')
        except tk.TclError:
            pass

    def _click(self, event) -> None:
        number = self._phase_at(event.x, event.y)
        if number is not None and self._on_open is not None:
            self._on_open(number)
            return
        x0, y0, x1, y1 = self._ring_box
        if x0 <= event.x <= x1 and y0 <= event.y <= y1 and self._on_overall is not None:
            self._on_overall()

    def _double(self, event) -> None:
        number = self._phase_at(event.x, event.y)
        if number is not None and self._on_edit is not None:
            self._on_edit(number)


class PhaseLegend(tk.Canvas):
    """The phase strip's colour key, sized to its text, for a card heading."""

    def __init__(self, parent: tk.Misc, *, background: str, colours: dict[str, str]):
        super().__init__(parent, bg=background, bd=0, highlightthickness=0, height=18)
        text_font = font('small', widget=self)
        measure = tkfont.Font(root=self, font=text_font)
        x = 2
        for state, label in LEGEND:
            colour = colours['track'] if state == 'NOT_STARTED' else colours[state]
            self.create_oval(x, 5, x + 8, 13, fill=colour, outline='')
            self.create_text(x + 13, 9, text=label, anchor='w', fill=colours['muted'], font=text_font)
            x += 13 + measure.measure(label) + 16
        self.configure(width=x)
