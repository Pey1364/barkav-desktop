"""The canonical construction-phase taxonomy from the local project reference.

This module deliberately contains names and stable identifiers only.  It does
not import Excel values, prices, quantities, formulas, or project data.
"""

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class PhaseSpec:
    number: int
    code: str
    title_fa: str


_TITLES: Final[tuple[str, ...]] = (
    "خرید زمین", "مطالعات اولیه", "طراحی", "نظام مهندسی", "جواز",
    "تجهیز کارگاه", "خاکی و تخریب", "اسکلت", "چاه", "کف سازی",
    "شاسی آسانسور", "وال پست", "میلگرد بستر", "وال مش", "تیغه چینی",
    "تاسیسات", "عایق و بام", "چهارچوب و فریم", "شاسی نما", "آسانسور",
    "درب ضدسرقت", "کاشی و سنگ", "سقف کاذب", "گچکاری", "UPVC",
    "نرده و هندریل", "درب پارکینگ", "نقاشی", "درب اتاق", "انشعابات",
    "پایان کار", "سند و فروش",
)

PHASES: Final[tuple[PhaseSpec, ...]] = tuple(
    PhaseSpec(index, f"{index:02d}", title) for index, title in enumerate(_TITLES, start=1)
)


def phase_by_number(number: int | str) -> PhaseSpec:
    value = int(number)
    if not 1 <= value <= len(PHASES):
        raise KeyError(f"Unknown project phase: {number}")
    return PHASES[value - 1]
