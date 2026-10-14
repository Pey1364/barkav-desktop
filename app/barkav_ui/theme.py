"""Single access point for colour, font and metric values.

Components never read ``load_ui()`` or ``barkav_themes`` directly, and never
hard-code a value.  Routing everything through here is what lets a theme or
font change reach every screen at once.

Section 0 of the UI contract defines the font ladder implemented by
:func:`font`.
"""

from __future__ import annotations

import tkinter as tk

from barkav_themes.engine import legacy_palette
from barkav_themes.tokens import get_theme


# Section 0: one size ladder for the whole product.  Values are offsets from
# the user's base font size; sub-tabs step down exactly one level per depth.
ROLE_STEPS = {
    'title': 2,
    'tab1': 0,
    'tab2': -1,
    'tab3': -2,
    'body': 0,
    'small': -2,
}

_MIN_POINT_SIZE = 8


def _ui_settings() -> dict:
    """User appearance settings, or an empty mapping before the app boots."""

    try:
        from v18_store import load_ui
    except ImportError:
        return {}
    try:
        return dict(load_ui() or {})
    except (OSError, ValueError):
        return {}


def palette(light: bool | None = None) -> dict[str, str]:
    """The active palette, including every UI-contract token."""

    try:
        from ui_stage18_7 import palette_187
    except ImportError:
        return legacy_palette()
    return palette_187(light)


def metrics() -> dict[str, int]:
    """Active theme metrics (heights, padding, radius) from the token layer."""

    settings = _ui_settings()
    try:
        from ui_stage18_7 import DEFAULT_THEME_ID_187 as default_theme
    except ImportError:
        default_theme = 1
    values = dict(get_theme(settings.get('theme_id', default_theme)).metrics)
    # Row height is the one metric the user can override from Settings.
    row_height = settings.get('row_height')
    if row_height:
        try:
            values['row_height'] = max(28, min(46, int(row_height)))
        except (TypeError, ValueError):
            pass
    return values


def base_size() -> int:
    try:
        from ui_stage18_7 import DEFAULT_FONT_SIZE_187 as default_size
    except ImportError:
        default_size = 10
    try:
        return max(9, min(14, int(_ui_settings().get('font_size') or default_size)))
    except (TypeError, ValueError):
        return default_size


def family(widget: tk.Misc | None = None) -> str:
    try:
        from ui_stage18_7 import resolve_font_family_187
    except ImportError:
        return 'TkDefaultFont'
    if widget is None:
        try:
            from ui_stage18_7 import DEFAULT_FONT_FAMILY_187 as default_family
        except ImportError:
            default_family = 'TkDefaultFont'
        return str(_ui_settings().get('font_family') or default_family)
    return resolve_font_family_187(widget, _ui_settings().get('font_family'))


def font(role: str = 'body', *, widget: tk.Misc | None = None, bold: bool | None = None):
    """A ``(family, size, style)`` tuple for one contract role.

    ``bold`` defaults to what the role implies - titles are bold, everything
    else follows the user's configured weight.
    """

    step = ROLE_STEPS.get(role)
    if step is None:
        raise ValueError(f'Unknown font role: {role!r}; expected one of {sorted(ROLE_STEPS)}')
    size = max(_MIN_POINT_SIZE, base_size() + step)
    if bold is None:
        try:
            weight = int(_ui_settings().get('font_weight') or 400)
        except (TypeError, ValueError):
            weight = 400
        bold = role == 'title' or weight >= 700
    return (family(widget), size, 'bold' if bold else 'normal')
