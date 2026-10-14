from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


ColorMap = Mapping[str, str]
MetricMap = Mapping[str, int]


def _rgb(value: str) -> tuple[int, int, int]:
    text = str(value).lstrip("#")
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def mix(base: str, tint: str, ratio: float) -> str:
    """Blend ``tint`` over ``base``; ratio 0 keeps base, 1 returns tint."""

    weight = max(0.0, min(1.0, float(ratio)))
    blended = (
        round(a + (b - a) * weight)
        for a, b in zip(_rgb(base), _rgb(tint))
    )
    return "#%02X%02X%02X" % tuple(blended)


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
        # UI-contract tokens.  These are derived so both themes stay in step
        # and no screen has to invent its own separator or state colour.
        status_ratio = 0.16 if normalized == "light" else 0.20
        palette.update({
            # Section 2/3 - the only two active-tab indicators in the product.
            "nav_indicator": palette["accent"],
            "tab_indicator": palette["accent"],
            # Section 5 - the vertical rule is always softer than the horizontal.
            "grid_h": palette["line"],
            "grid_v": palette["line_soft"],
            "focus_ring": palette["accent"],
            # Line-free tables read as stacked horizontal cards.  The two
            # card surfaces are theme-derived and remain visible without a
            # ruled grid in both dark and light modes.
            "row_card_even": mix(palette["panel"], palette["text"], 0.025),
            # Keep the requested alternating green visible without replacing
            # status-specific pending/approved/rejected row tints.
            "row_card_odd": mix(
                palette["panel"], palette["green"],
                0.07 if normalized == "light" else 0.14,
            ),
            # Inactive tabs stay visibly elevated above their strip even when
            # the pointer is elsewhere; selected and unselected states must
            # be distinguishable at a glance.
            "tab_inactive": mix(palette["panel2"], palette["text"], 0.18),
            "subtab_inactive": mix(palette["glass"], palette["text"], 0.13),
            "row_pending": mix(palette["row_even"], palette["yellow"], status_ratio),
            "row_approved": mix(palette["row_even"], palette["green"], status_ratio),
            "row_rejected": mix(palette["row_even"], palette["red"], status_ratio),
            # Data Entry status rows (operator-approved N1, 2026-09-27): the
            # bright yellow/green/red swatches flooded whole rows and made
            # them hard to read.  They now take the same soft tint as every
            # other status row, keep the normal text colour, and the status
            # hue itself is a stripe on the row's start edge
            # (barkav_ui.row_overlay.STATUS_STRIPES).
            "data_entry_pending": mix(palette["row_even"], palette["yellow"], status_ratio),
            "data_entry_pending_text": palette["text"],
            "data_entry_approved": mix(palette["row_even"], palette["green"], status_ratio),
            "data_entry_approved_text": palette["text"],
            "data_entry_rejected": mix(palette["row_even"], palette["red"], status_ratio),
            "data_entry_rejected_text": palette["text"],
            # Phase-status colours: identical to what
            # dashboard_stage18_2.refresh_phase_strip already paints the
            # real in-project phase strip with, so a summary strip
            # elsewhere (the استارت view's recent-project cards) speaks the
            # same visual language instead of inventing its own palette.
            "phase_not_started": "#E7ECEF" if normalized == "light" else "#10243A",
            "phase_active": "#28A875" if normalized == "light" else "#177A59",
            "phase_paused": "#D8A33D" if normalized == "light" else "#76571C",
            # The استارت view's own glance-strip renders much smaller than
            # the real in-project phase strip and needed to be legible at a
            # glance - a plain mix() lift of the four tokens above toward
            # the theme's own text colour, brighter without inventing a
            # second palette or losing each status's hue identity.
            "phase_summary_not_started": mix(
                "#E7ECEF" if normalized == "light" else "#10243A", palette["text"], 0.35),
            "phase_summary_active": mix(
                "#28A875" if normalized == "light" else "#177A59", palette["text"], 0.22),
            "phase_summary_paused": mix(
                "#D8A33D" if normalized == "light" else "#76571C", palette["text"], 0.22),
            "phase_summary_completed": mix(
                "#239A70" if normalized == "light" else "#16805D", palette["text"], 0.22),
            "phase_completed": "#239A70" if normalized == "light" else "#16805D",
            # Selection reads as glass over the row rather than a slab of
            # accent: the accent is mixed into the row it covers, so the
            # status tint underneath still shows through and the text keeps
            # its own colour instead of being forced to white.
            # Softer since the selected row also gets an accent outline
            # (barkav_ui.row_overlay) - the outline now carries the selection,
            # the tint only has to separate the row from its stripe.
            "row_selected": mix(palette["row_even"], palette["accent"], 0.18),
            # Every tab strip, the window tabs and the rail share one
            # selected look: a soft accent pill, text colour unchanged.
            "tab_selected_fill": mix(palette["panel2"], palette["accent"], 0.17),
            # Section 10/12 - window chrome and transient surfaces.
            "dialog_header": palette["surface"],
            "dialog_footer": palette["surface"],
            # A toast floats over arbitrary content, so it is offset from the
            # panel rather than aliased to it - `raised` equals `panel` in the
            # flat light modes and would vanish.
            "toast_bg": mix(palette["panel"], palette["text"], 0.08),
            "disabled_bg": palette["panel2"],
            "disabled_fg": palette["empty"],
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


# Theme 2 is sampled from the `newest theme` reference screenshots.  Its dark
# mode is a near-neutral slate rather than the earlier navy, its light mode is
# flat near-white, and the single active accent is a teal-cyan.
THEME_2_DARK = {
    # The surface ramp is deliberately tight.  An earlier version stepped from
    # near-black inputs to navy panels, and the jump read as a hole punched in
    # the card rather than as a field inside it.  Each step here is a few
    # levels of lightness - enough to separate, not enough to fight.
    "bg": "#0E141B",
    "surface": "#111820",
    "panel": "#141C25",
    "panel2": "#182029",
    "raised": "#1C242E",
    "glass": "#161E27",
    "nav": "#0E151C",
    "nav_active": "#14202C",
    "card": "#141C25",
    "row_even": "#121A22",
    "row_odd": "#161E27",
    "heading": "#1A222B",
    "input": "#10171F",
    "line": "#2A3440",
    "line_soft": "#1D252E",
    "text": "#F1F5F9",
    "muted": "#94A3B0",
    # On a dark ground an accent has to be lighter than the mid point to read
    # as lit rather than as a stain.  The first pass sat at 40-56% lightness
    # and the screens looked switched off; these sit at 57-68%.
    "blue": "#3B8FE8",
    "blue_hover": "#52A0F5",
    "cyan": "#4FD1E0",
    "green": "#3ACB86",
    "yellow": "#F0B93C",
    "orange": "#F79A2E",
    "red": "#EC5563",
    "violet": "#9585EC",
    "selection": "#1B4D73",
    "selection_text": "#FFFFFF",
    "shadow": "#05090D",
    "scroll_track": "#0B1218",
    "scroll_thumb": "#3A4957",
    "empty": "#5D6B78",
}

THEME_2_LIGHT = {
    "bg": "#FCFDFF",
    "surface": "#FAFBFD",
    "panel": "#FFFFFF",
    "panel2": "#F4F6F9",
    "raised": "#FFFFFF",
    "glass": "#F7F8FB",
    "nav": "#FCFDFF",
    "nav_active": "#E0F4FA",
    "card": "#FFFFFF",
    "row_even": "#FFFFFF",
    "row_odd": "#F7F8FB",
    "heading": "#F2F4F7",
    "input": "#FFFFFF",
    "line": "#D9DFE6",
    "line_soft": "#EBEFF3",
    "text": "#16212E",
    "muted": "#64748B",
    "blue": "#1668C4",
    "blue_hover": "#0F5AAE",
    "cyan": "#0E8FA5",
    "green": "#12855A",
    "yellow": "#A87410",
    "orange": "#C06E10",
    "red": "#C4343F",
    "violet": "#5647C0",
    "selection": "#DCEDF9",
    "selection_text": "#16212E",
    "shadow": "#E3E8ED",
    "scroll_track": "#F2F4F7",
    "scroll_thumb": "#B4BFCB",
    "empty": "#94A3B0",
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
    name_fa="تم ۲ — مرجع طراحی جدید",
    description_fa="پوسته اسلیت تیره/سفید تخت با لهجه فیروزه‌ای و جدول‌های کم‌کنتراست.",
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


# Theme 3 is the "vivid" display mode.  Geometry is shared with the other
# themes; only colour differs.  Building it by saturating theme 2 made it look
# like theme 2 behind a filter, so it gets its own indigo ground and a hotter
# accent set instead.
THEME_3_DARK = {
    # The first vivid pass kept theme 2's lightness and only shifted hue, so
    # it still read as "another dark theme".  These surfaces are lifted a full
    # step and carry real chroma - the ground itself is the colour, not just
    # the accents sitting on it.
    "bg": "#1B1733",
    "surface": "#221D3F",
    "panel": "#29234B",
    "panel2": "#302957",
    "raised": "#382F65",
    "glass": "#2C2551",
    "nav": "#1D1937",
    "nav_active": "#2E3A82",
    "card": "#29234B",
    "row_even": "#251F45",
    "row_odd": "#2C2653",
    "heading": "#332C5D",
    "input": "#231E42",
    "line": "#4C4183",
    "line_soft": "#382F66",
    "text": "#F6F3FF",
    "muted": "#B9AFDC",
    "blue": "#5B9BFF",
    "blue_hover": "#78ADFF",
    "cyan": "#3FE3E8",
    "green": "#3FE39A",
    "yellow": "#FFD24D",
    "orange": "#FF9A4D",
    "red": "#FF6B84",
    "violet": "#B98CFF",
    "selection": "#3E4CA8",
    "selection_text": "#FFFFFF",
    "shadow": "#0D0A1B",
    "scroll_track": "#1B1733",
    "scroll_thumb": "#544A8C",
    "empty": "#8478B5",
}

THEME_3_LIGHT = {
    # The light half of a vivid theme should be tinted too, not the neutral
    # near-white of theme 2 with a couple of accents swapped.
    "bg": "#F7F5FF",
    "surface": "#FAF8FF",
    "panel": "#FFFFFF",
    "panel2": "#F0ECFF",
    "raised": "#FFFFFF",
    "glass": "#F4F1FF",
    "nav": "#F7F5FF",
    "nav_active": "#E3DBFF",
    "card": "#FFFFFF",
    "row_even": "#FFFFFF",
    "row_odd": "#F5F2FF",
    "heading": "#EDE8FF",
    "input": "#FFFFFF",
    "line": "#D6CDF0",
    "line_soft": "#E9E3FA",
    "text": "#1E1740",
    "muted": "#6C6193",
    "blue": "#2E5FE0",
    "blue_hover": "#2450C7",
    "cyan": "#0A93B8",
    "green": "#0E8F62",
    "yellow": "#A8760A",
    "orange": "#C4650C",
    "red": "#CE2F4E",
    "violet": "#6A34D8",
    "selection": "#DCD2FB",
    "selection_text": "#1E1740",
    "shadow": "#DED6F2",
    "scroll_track": "#F0ECFF",
    "scroll_thumb": "#BCAFE2",
    "empty": "#9A8FC0",
}

THEME_3 = ThemeSpec(
    theme_id=3,
    name_fa="تم ۳ — رنگی",
    description_fa="حالت نمایش رنگی؛ همان هندسه با زمینه نیلی و لهجه‌های پرانرژی.",
    dark=THEME_3_DARK,
    light=THEME_3_LIGHT,
    metrics=dict(THEME_2.metrics),
)

THEMES = {1: THEME_1, 2: THEME_2, 3: THEME_3}


def get_theme(theme_id: int | str = 1) -> ThemeSpec:
    try:
        normalized = int(theme_id)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Unsupported theme id: {theme_id!r}") from exc
    try:
        return THEMES[normalized]
    except KeyError as exc:
        raise ValueError(f"Unsupported theme id: {theme_id!r}") from exc
