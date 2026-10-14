"""BARKAV shared UI kit.

Every widget here implements a numbered section of
``docs/theme_18_7/BARKAV_UI_CONTRACT.md``.  Screens compose these components
instead of styling raw Tk widgets, which is what keeps tabs, tables and
windows identical to each other.

Nothing in this package may contain a literal colour, font family or size.
Read them from :mod:`barkav_ui.theme` instead; the conformance test enforces it.
"""

from .theme import font, metrics, palette
from .window import (
    BarkavDialog, BarkavWindow, BarkavWizard, ConfirmDialog, SIZE_CLASSES,
    confirm, show_toast,
)

__all__ = [
    'BarkavDialog',
    'BarkavWindow',
    'BarkavWizard',
    'ConfirmDialog',
    'SIZE_CLASSES',
    'confirm',
    'font',
    'metrics',
    'palette',
    'show_toast',
]
