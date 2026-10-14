"""Rotate and crop a receipt image of a Data Entry record."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from PIL import ImageTk

from barkav_ui.theme import palette
from barkav_ui.window import BarkavWindow

ROTATIONS = {'rotate_right': -90, 'rotate_left': 90}
MIN_SELECTION = 4


def rotated(image, command):
    """The image turned a quarter: «rotate_right» clockwise, «rotate_left» counter-clockwise."""
    return image.rotate(ROTATIONS[command], expand=True)


def crop_box(selection, scale, size):
    """The selection of the scaled picture as a box of the real image, kept inside it; None for a speck."""
    width, height = size
    x0, y0, x1, y1 = (value / scale for value in selection)
    box = (max(0, round(min(x0, x1))), max(0, round(min(y0, y1))),
           min(width, round(max(x0, x1))), min(height, round(max(y0, y1))))
    if box[2] - box[0] < MIN_SELECTION or box[3] - box[1] < MIN_SELECTION:
        return None
    return box


class CropDialog187(BarkavWindow):
    """Drag a rectangle over the receipt, then apply; ``result`` is the crop box of the real image or None."""
    MAX_SIZE = (900, 430)

    def __init__(self, parent, image):
        super().__init__(parent, 'برش تصویر رسید', size_class='medium', show_footer=True)
        self.result = None
        self.image = image
        self.scale = min(1.0, self.MAX_SIZE[0] / image.width, self.MAX_SIZE[1] / image.height)
        shown = image.resize((max(1, round(image.width * self.scale)), max(1, round(image.height * self.scale))))
        self.photo = ImageTk.PhotoImage(shown, master=self)
        p = palette()
        ttk.Label(self.body, text='با کشیدن ماوس بخشی را که می‌خواهی نگه داشته شود انتخاب کن.',
                  anchor='e').pack(fill='x', pady=(0, 6))
        self.canvas = tk.Canvas(self.body, width=shown.width, height=shown.height, highlightthickness=0,
                                bg=p['surface'], cursor='crosshair')
        self.canvas.pack(pady=4)
        self.canvas.create_image(0, 0, image=self.photo, anchor='nw')
        self.selection = None
        self._rectangle = None
        self._start = None
        self._ink = p['accent']
        self.canvas.bind('<ButtonPress-1>', self._press)
        self.canvas.bind('<B1-Motion>', self._drag)
        self.apply_button = self.add_action('اعمال برش', self.accept, style='Primary.TButton')
        self.add_action('انصراف', self.close, style='Ghost.TButton')

    def _press(self, event):
        self._start = (event.x, event.y)
        self.set_selection(event.x, event.y, event.x, event.y)

    def _drag(self, event):
        if self._start:
            self.set_selection(*self._start, event.x, event.y)

    def set_selection(self, x0, y0, x1, y1):
        width, height = self.photo.width(), self.photo.height()
        clamp = lambda value, limit: max(0, min(limit, value))
        self.selection = (clamp(x0, width), clamp(y0, height), clamp(x1, width), clamp(y1, height))
        if self._rectangle is None:
            self._rectangle = self.canvas.create_rectangle(*self.selection, outline=self._ink, width=2, dash=(4, 3))
        else:
            self.canvas.coords(self._rectangle, *self.selection)

    def accept(self):
        box = crop_box(self.selection, self.scale, self.image.size) if self.selection else None
        if box is None:
            return
        self.result = box
        self.close()


def ask_crop(parent, image):
    """Modal crop dialog; the chosen box or None."""
    dialog = CropDialog187(parent, image)
    parent.wait_window(dialog)
    return dialog.result
