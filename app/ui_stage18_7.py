from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from pathlib import Path
import sys

import ui_stage18_6 as legacy_ui
from barkav_themes.engine import ThemeSelection, apply_ttk_theme, legacy_palette
from barkav_themes.tokens import get_theme
from v18_store import load_ui
from runtime_base import resolve_base


BACKGROUND_COLORS_187 = {
    'سرمه‌ای': {'dark': '#071525', 'light': '#EAF2FA'},
    'ذغالی': {'dark': '#1F2937', 'light': '#F1F3F5'},
    'سبزآبی': {'dark': '#0B3036', 'light': '#E8F5F2'},
    'بنفش خاکستری': {'dark': '#28243D', 'light': '#F1EEFA'},
}

FONT_CATALOG_187 = {
    # Bundled Persian web fonts are followed by families available from the
    # user's Windows font installation; these are never shipped by BARKAV.
    'Vazirmatn': 'وزیرمتن', 'Vazirmatn UI': 'وزیرمتن UI', 'Sahel': 'ساحل',
    'Shabnam': 'شبنم', 'Samim': 'صمیم', 'Parastoo': 'پرستو',
    'IRANSansX': 'ایران سنس X', 'IRANYekanX': 'ایران یکان X',
    'Yekan Bakh': 'یکان بخ', 'Dana': 'دانا',
    'Peyda': 'پیدا', 'Estedad': 'استعداد', 'Kalameh': 'کلمب',
    'Noto Sans Arabic': 'نوتو سنس عربی',
    'IBM Plex Sans Arabic': 'آی‌بی‌ام پلکس سنس عربی',
    'Cairo': 'کایرو',
    'Almarai': 'المراعی',
    'Mada': 'مدی',
    'Harmattan': 'هرمتان',
    'Noto Kufi Arabic': 'نوتو کوفی عربی',
    'Changa': 'چانگا',
    'El Messiri': 'المسیری',
    'Noto Naskh Arabic': 'نوتو نسخ عربی',
    'Scheherazade New': 'شهرزاد جدید',
    'Lateef': 'لطیف',
    'Markazi Text': 'مرکزی تکست',
    'Lalezar': 'لاله‌زار',
}
# Persian-only faces fall back to a Latin face in the English interface.
PERSIAN_ONLY_FONTS_187 = frozenset(FONT_CATALOG_187)
FONT_ASSET_DIRS_187 = tuple(resolve_base(__file__) / name for name in ('assets/fonts', 'fonts', 'new theme/fonts'))
_FONT_ASSETS_REGISTERED_187 = False

def _register_font_assets_187() -> None:
    global _FONT_ASSETS_REGISTERED_187
    if _FONT_ASSETS_REGISTERED_187 or not sys.platform.startswith('win'):
        return
    _FONT_ASSETS_REGISTERED_187 = True
    try:
        import ctypes
        for directory in FONT_ASSET_DIRS_187:
            for path in directory.glob('*'):
                if path.suffix.lower() in {'.ttf', '.otf'}:
                    ctypes.windll.gdi32.AddFontResourceExW(str(path), 0x10, 0)
    except (OSError, AttributeError):
        return

def installed_font_families_187(root: tk.Misc) -> tuple[str, ...]:
    _register_font_assets_187()
    try:
        return tuple(sorted({str(name).strip() for name in tkfont.families(root) if str(name).strip()}))
    except tk.TclError:
        return ()

def available_font_families_187(root: tk.Misc) -> tuple[str, ...]:
    installed = set(installed_font_families_187(root))
    # The product default leads the list so it also becomes the fallback when
    # a stored preference names a family this machine does not have.
    ordered = (DEFAULT_FONT_FAMILY_187,) + tuple(
        name for name in FONT_CATALOG_187 if name != DEFAULT_FONT_FAMILY_187)
    requested = tuple(name for name in ordered if name in installed)
    fallback = tuple(name for name in ('Segoe UI', 'Tahoma', 'Arial') if name in installed)
    if requested or fallback:
        return requested + tuple(name for name in fallback if name not in requested)
    try:
        return (str(tkfont.nametofont('TkDefaultFont', root=root).actual().get('family') or 'TkDefaultFont'),)
    except (tk.TclError, TypeError):
        return ('TkDefaultFont',)

def font_catalog_families_187(root: tk.Misc) -> tuple[str, ...]:
    """Return the complete user-facing catalog, including missing families."""
    available = available_font_families_187(root)
    return tuple(FONT_CATALOG_187) + tuple(name for name in available if name not in FONT_CATALOG_187)

def font_status_label_187(root: tk.Misc, family: str) -> str:
    label = font_display_name_187(family)
    if family in set(installed_font_families_187(root)):
        return label
    fallback = available_font_families_187(root)[0]
    return f'{label} (مفقود؛ fallback: {font_display_name_187(fallback)})'

def missing_font_assets_187(root: tk.Misc) -> tuple[str, ...]:
    installed = set(installed_font_families_187(root))
    return tuple(name for name in FONT_CATALOG_187 if name not in installed)

def font_display_name_187(family: str) -> str:
    return FONT_CATALOG_187.get(family, family)

def resolve_font_family_187(root: tk.Misc, requested: str | None = None) -> str:
    available = available_font_families_187(root)
    if str(load_ui().get('language') or 'fa') == 'en':
        latin = [name for name in available if name not in PERSIAN_ONLY_FONTS_187]
        if requested in latin:
            return str(requested)
        if latin:
            return latin[0]
    return str(requested) if requested in available else available[0]

def available_font_weights_187(root: tk.Misc, family: str) -> tuple[int, ...]:
    return (400, 700)

def resolve_font_weight_187(root: tk.Misc, family: str, requested: int | str | None = None) -> int:
    available = available_font_weights_187(root, family)
    try:
        value = int(requested or DEFAULT_FONT_WEIGHT_187)
    except (TypeError, ValueError):
        value = DEFAULT_FONT_WEIGHT_187
    return min(available, key=lambda candidate: abs(candidate - value))


# Theme 2 is the product default.  Theme 1 remains selectable as the frozen
# 18.6 appearance, but it is no longer what an unset preference resolves to.
DEFAULT_THEME_ID_187 = 2

# Product defaults for appearance. An unset preference resolves to these.
DEFAULT_FONT_FAMILY_187 = 'Vazirmatn'
DEFAULT_FONT_SIZE_187 = 10
DEFAULT_FONT_WEIGHT_187 = 400


def theme_id_187() -> int:
    """Return a safe UI-only theme selection; project/financial data is untouched."""
    try:
        return get_theme(load_ui().get('theme_id', DEFAULT_THEME_ID_187)).theme_id
    except Exception:
        return DEFAULT_THEME_ID_187


def theme_selection_187(light: bool | None = None) -> ThemeSelection:
    ui = load_ui()
    if light is None:
        light = str(ui.get('appearance') or 'dark').lower() == 'light'
    return ThemeSelection(theme_id_187(), 'light' if light else 'dark').normalized()


# «پنهان‌شده» in Data Entry: a cream, beside the yellow, green and red of the other states.
HIDDEN_CREAM_187 = {'dark': '#EFE0B5', 'light': '#C9AB63'}


def palette_187(light: bool | None = None) -> dict[str, str]:
    selected = theme_selection_187(light)
    palette = legacy_palette(selected)
    palette.setdefault('cream', HIDDEN_CREAM_187['light' if selected.mode == 'light' else 'dark'])
    choice = str(load_ui().get('background_color') or 'پیش‌فرض').strip()
    if choice in BACKGROUND_COLORS_187:
        palette['bg'] = BACKGROUND_COLORS_187[choice]['light' if selected.mode == 'light' else 'dark']
    return palette


def theme_metrics_187() -> dict[str, int]:
    return dict(get_theme(theme_id_187()).metrics)


def style_ttk_187(
    root: tk.Misc,
    *,
    light: bool | None = None,
    font_size: int = DEFAULT_FONT_SIZE_187,
    row_height: int | None = None,
) -> None:
    from barkav_ui.clipboard import install as install_field_clipboard
    install_field_clipboard(root)
    selection = theme_selection_187(light)
    metrics = get_theme(selection.theme_id).metrics
    apply_ttk_theme(
        root,
        selection,
        palette_override=palette_187(light),
        font_family=resolve_font_family_187(root, load_ui().get('font_family')),
        font_weight=resolve_font_weight_187(root, load_ui().get('font_family'), load_ui().get('font_weight')),
        font_size=font_size,
        row_height=row_height or metrics['row_height'],
    )
    # Existing 18.6 widgets use this Tcl flag to choose their light palette.
    try:
        root.tk.call('set', '::barkav_light_186', '1' if selection.mode == 'light' else '0')
        root.tk.call('set', '::barkav_light_187', '1' if selection.mode == 'light' else '0')
    except Exception:
        pass


def activate_tab_strip_bridge_187() -> None:
    """Make every notebook in the product use the one kit tab strip.

    The inherited layers build their sub-tab strips with
    ``ui_stage18_3.RtlNotebookStrip``, a second implementation with its own
    colours, sizing and selected state.  With two implementations alive the
    strips could never look alike, so the name is rebound - in this process
    only - to the kit strip.  Every module that imported the class by name
    keeps its own binding, so each of those is rebound too.
    """
    from barkav_ui.tabs import LegacyTabStrip

    import ui_stage18_3
    ui_stage18_3.RtlNotebookStrip = LegacyTabStrip
    for module_name in ('dashboard_stage18_3', 'dashboard_stage18_5', 'dashboard_stage18_6'):
        try:
            module = __import__(module_name)
        except ImportError:
            continue
        if hasattr(module, 'RtlNotebookStrip'):
            module.RtlNotebookStrip = LegacyTabStrip


def activate_theme_bridge_187() -> None:
    """Point the inherited 18.6 presentation layer at the selected 18.7 tokens.

    This runs only in the separate 18.7 process.  It does not edit or persist
    anything in the 18.6 source tree.
    """
    legacy_ui.palette_186 = palette_187
    legacy_ui.style_ttk_186 = style_ttk_187
    activate_tab_strip_bridge_187()
    current = palette_187()
    legacy_ui.DARK_186.update(current)
    legacy_ui.LIGHT_186.update(palette_187(True))
    # Charts are inherited from these stable layers and read their module-level
    # semantic palette while drawing.
    for module_name in ('dashboard_stage16_3', 'dashboard_stage17_5'):
        try:
            module = __import__(module_name)
            module.DARK.update(current)
        except Exception:
            pass


# Re-export the accepted 18.6 helpers.  Their palette lookup is redirected by
# activate_theme_bridge_187, while all business/data behavior remains inherited.
attach_tree_grid_187 = legacy_ui.attach_tree_grid_186
bind_persian_digits = legacy_ui.bind_persian_digits
build_brand_widget_187 = legacy_ui.build_brand_widget_186
convert_tree_currency_187 = legacy_ui.convert_tree_currency_186
currency_unit_187 = legacy_ui.currency_unit_186
format_currency_187 = legacy_ui.format_currency_186
normalize_floor_structure_187 = legacy_ui.normalize_floor_structure_186
parse_display_amount_187 = legacy_ui.parse_display_amount_186
retarget_smarttable_187 = legacy_ui.retarget_smarttable_186
DashboardCard187 = legacy_ui.DashboardCard186
CompactMetric187 = legacy_ui.CompactMetric186
