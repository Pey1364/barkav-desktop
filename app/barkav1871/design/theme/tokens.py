from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


ColorMap = Mapping[str, str]
MetricMap = Mapping[str, int]


@dataclass(frozen=True)
class ThemeSpec:
    """A complete semantic theme; application labels intentionally live elsewhere."""

    theme_id: int
    name_fa: str
    description_fa: str
    dark: ColorMap
    light: ColorMap
    metrics: MetricMap

    def palette(self, mode: str = "dark") -> dict[str, str]:
        normalized = str(mode or "dark").strip().lower()
        if normalized not in {"dark", "light"}:
            raise ValueError(f"Unsupported theme mode: {mode!r}")
        palette = dict(self.light if normalized == "light" else self.dark)
        # Semantic aliases keep Dashboard styling consistent without changing
        # the legacy token names consumed by inherited widgets.
        palette.update({
            "surface_alt": palette["panel2"],
            "border": palette["line"],
            "border_subtle": palette["line_soft"],
            "text_primary": palette["text"],
            "text_secondary": palette["muted"],
            "text_muted": palette["muted"],
            "accent": palette["cyan"],
            "info": palette["blue"],
            "success": palette["green"],
            "warning": palette["yellow"],
            "danger": palette["red"],
            "on_accent": "#FFFFFF",
            "on_warning": "#17212F",
        })
        return palette


# Theme 1 is an exact token snapshot of the accepted BARKAV 18.6 GUI.  The
# additional semantic keys are aliases/derivatives and do not alter 18.6.
THEME_1_DARK = {
    "bg": "#091423",
    "surface": "#0D192A",
    "panel": "#111F33",
    "panel2": "#17283F",
    "raised": "#17283F",
    "glass": "#132238",
    "nav": "#0D192A",
    "nav_active": "#17283F",
    "card": "#111F33",
    "row_even": "#111F33",
    "row_odd": "#17283F",
    "heading": "#17283F",
    "input": "#0D192A",
    "line": "#22344B",
    "line_soft": "#1B2C42",
    "text": "#F1F5FA",
    "muted": "#96A4B7",
    "blue": "#2F78EE",
    "blue_hover": "#3C86F2",
    "cyan": "#58A8F8",
    "green": "#43BE82",
    "yellow": "#E7C158",
    "orange": "#E4A34C",
    "red": "#DE6671",
    "violet": "#9A83E7",
    "selection": "#2F78EE",
    "selection_text": "#FFFFFF",
    "shadow": "#050B14",
    "scroll_track": "#091423",
    "scroll_thumb": "#17283F",
    "empty": "#516075",
}

THEME_1_LIGHT = {
    "bg": "#F5F7FA",
    "surface": "#FFFFFF",
    "panel": "#FFFFFF",
    "panel2": "#F2F5F9",
    "raised": "#FFFFFF",
    "glass": "#F7F9FC",
    "nav": "#FFFFFF",
    "nav_active": "#F2F5F9",
    "card": "#FFFFFF",
    "row_even": "#FFFFFF",
    "row_odd": "#F2F5F9",
    "heading": "#F2F5F9",
    "input": "#FFFFFF",
    "line": "#E1E7EE",
    "line_soft": "#EDF1F5",
    "text": "#1B2738",
    "muted": "#6B788A",
    "blue": "#2D72DE",
    "blue_hover": "#2264C9",
    "cyan": "#2479D0",
    "green": "#27855E",
    "yellow": "#A97B13",
    "orange": "#B87317",
    "red": "#C34F5B",
    "violet": "#7057BE",
    "selection": "#2D72DE",
    "selection_text": "#FFFFFF",
    "shadow": "#DDE3EA",
    "scroll_track": "#F5F7FA",
    "scroll_thumb": "#C7D0DC",
    "empty": "#98A5B5",
}


# Theme 2 is sampled and normalized from reference images 1.png ... 16.png.
# It follows their deep blue-black executive dark mode and near-white light
# mode, cyan/blue active edge, low-contrast grid and spacious flat cards.
THEME_2_DARK = {
    "bg": "#071525",
    "surface": "#0B1A2A",
    "panel": "#0F1F32",
    "panel2": "#152639",
    "raised": "#1B2D47",
    "glass": "#12253B",
    "nav": "#0D2136",
    "nav_active": "#18344D",
    "card": "#152639",
    "row_even": "#0E1C2D",
    "row_odd": "#162B43",
    "heading": "#1B2D47",
    "input": "#09192B",
    "line": "#33485E",
    "line_soft": "#20344A",
    "text": "#F5F7FA",
    "muted": "#A7B2BF",
    "blue": "#2588D8",
    "blue_hover": "#319BEA",
    "cyan": "#28B8C8",
    "green": "#25A66A",
    "yellow": "#F1C04E",
    "orange": "#E6A544",
    "red": "#E8324C",
    "violet": "#5C58C9",
    "selection": "#244D7B",
    "selection_text": "#FFFFFF",
    "shadow": "#020A12",
    "scroll_track": "#0A1727",
    "scroll_thumb": "#7F8998",
    "empty": "#516075",
}

THEME_2_LIGHT = {
    "bg": "#F7F8FA",
    "surface": "#FCFCFD",
    "panel": "#FFFFFF",
    "panel2": "#F4F6F8",
    "raised": "#FFFFFF",
    "glass": "#FBFCFD",
    "nav": "#FFFFFF",
    "nav_active": "#FFFFFF",
    "card": "#FFFFFF",
    "row_even": "#FFFFFF",
    "row_odd": "#F5F6F8",
    "heading": "#FAFBFC",
    "input": "#FFFFFF",
    "line": "#D8DEE6",
    "line_soft": "#E9EDF2",
    "text": "#172B46",
    "muted": "#6D7B8D",
    "blue": "#1E83D5",
    "blue_hover": "#1474C3",
    "cyan": "#19A8C3",
    "green": "#4FB28E",
    "yellow": "#F5C84B",
    "orange": "#E9A63B",
    "red": "#EE6872",
    "violet": "#5669C9",
    "selection": "#E8F2FC",
    "selection_text": "#172B46",
    "shadow": "#E5E9EE",
    "scroll_track": "#F1F3F6",
    "scroll_thumb": "#AEB8C5",
    "empty": "#A2ADBB",
}


THEME_1 = ThemeSpec(
    theme_id=1,
    name_fa="تم ۱ — ظاهر تثبیت‌شده ۱۸.۶",
    description_fa="نسخه بدون تغییر تم فعلی ۱۸.۶ برای بازگشت امن و مقایسه.",
    dark=THEME_1_DARK,
    light=THEME_1_LIGHT,
    metrics={
        "title_height": 34,
        "command_height": 62,
        "nav_height": 46,
        "toolbar_height": 42,
        "row_height": 31,
        "button_height": 34,
        "card_header_height": 36,
        "outer_pad": 8,
        "gap": 6,
        "radius": 5,
    },
)

THEME_2 = ThemeSpec(
    theme_id=2,
    name_fa="تم ۲ — مرجع ۱۶ تصویر",
    description_fa="پوسته مدیریتی آبی‌سرمه‌ای/سفید با ناوبری دوطبقه و جدول‌های کم‌کنتراست.",
    dark=THEME_2_DARK,
    light=THEME_2_LIGHT,
    metrics={
        "title_height": 36,
        "command_height": 54,
        "nav_height": 58,
        "toolbar_height": 44,
        "row_height": 34,
        "button_height": 38,
        "card_header_height": 44,
        "outer_pad": 10,
        "gap": 8,
        "radius": 7,
    },
)


THEMES = {1: THEME_1, 2: THEME_2}


def get_theme(theme_id: int | str = 1) -> ThemeSpec:
    try:
        normalized = int(theme_id)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Unsupported theme id: {theme_id!r}") from exc
    try:
        return THEMES[normalized]
    except KeyError as exc:
        raise ValueError(f"Unsupported theme id: {theme_id!r}") from exc
