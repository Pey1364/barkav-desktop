"""Deterministic (non-AI) fetchers for the price-update module's macro indices.

No network call happens without an explicit, verified source: guessing a
plausible-looking URL for a financial number this module then multiplies
every price by is exactly the kind of silent-wrong-number risk the reference
workbook's own rules warn against (« خروجی هرگز نباید صفر یا خالی باشد» cuts
both ways -- a wrong non-zero number is worse than an honest failure).

USD reuses the exact regex patterns already shipping (and battle-tested) in
``ui_stage18_3.fetch_tgju_usd_toman``, generalized into a reusable,
unit-testable shape with an injectable HTTP opener so tests never touch the
real network.

Copper (قیمت مس کاتد) is wired to TGJU's ``base_global_copper`` page (London
copper, USD/tonne) -- not the domestic Iran Mercantile Exchange Toman/kg
market قوانین_محاسبه_بروز.txt originally described. This was a deliberate,
operator-confirmed call after the base value (13,269.60 -- verified by
paging through this exact page's own history to 1405/01/31, 2026-09-23)
could not be reconciled with any Toman/kg domestic reading. It stays
arithmetically valid because ``price_calc_engine`` only ever consumes
``current/base`` as a pure ratio (see ``growth_ratio``/``duct_split_ratio``)
-- unit-invariant as long as BOTH readings come from this same USD/tonne
series, every month, forever. Never mix a Toman-basis copper reading into
this parameter's history.
"""

from __future__ import annotations

import re
import urllib.request
from datetime import datetime
from typing import Callable

_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')

TGJU_USD_URL = 'https://www.tgju.org/profile/price_dollar_rl'
TGJU_COPPER_URL = 'https://www.tgju.org/profile/base_global_copper'

# Same fragments ui_stage18_3.fetch_tgju_usd_toman already relies on, but with
# an optional decimal part added ("." in the character class): the dollar
# page never needed it (whole rial amounts), but copper's "13,269.60" would
# otherwise match only "13,269" and silently drop the cents -- a wrong,
# plausible-looking number is exactly the failure mode this module exists to
# avoid, so this had to be fixed before copper could be wired in at all.
_TGJU_VALUE_PATTERNS = [
    r'نرخ\s*فعلی\s*</[^>]+>\s*<[^>]+>\s*([0-9۰-۹٠-٩,٬]+(?:\.[0-9۰-۹٠-٩]+)?)',
    r'نرخ\s*فعلی\s*[:：]*\s*</?[^>]*>\s*([0-9۰-۹٠-٩,٬]{5,}(?:\.[0-9۰-۹٠-٩]+)?)',
    r'در\s*حال\s*حاضر\s*قیمت\s*هر\s*دلار\s*([0-9۰-۹٠-٩,٬]+)\s*ریال',
    r'نرخ\s*فعلی\s*[:：]+\s*([0-9۰-۹٠-٩,٬]{5,}(?:\.[0-9۰-۹٠-٩]+)?)',
]

Opener = Callable[[str, float], bytes]


def _default_opener(url: str, timeout: float) -> bytes:
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 BARKAV/PriceUpdate',
        'Accept-Language': 'fa-IR,fa;q=0.9,en;q=0.6',
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _parse_number(raw: str) -> float:
    cleaned = raw.translate(_DIGITS).replace(',', '').replace('٬', '')
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def fetch_tgju_value(url: str, patterns: list[str], *, timeout: float = 8.0,
                      opener: Opener = _default_opener) -> float:
    """Fetch one numeric value off a TGJU profile page by trying each pattern in order.

    ``opener`` is injectable so tests can supply canned HTML instead of a real
    HTTP call -- see tests/test_price_index_fetch.py.
    """

    html = opener(url, timeout).decode('utf-8', 'ignore')
    raw = ''
    for pattern in patterns:
        m = re.search(pattern, html, re.I | re.S)
        if m:
            raw = m.group(1)
            break
    if not raw:
        text = re.sub(r'<[^>]+>', ' ', html)
        text = re.sub(r'\s+', ' ', text)
        for pattern in patterns:
            m = re.search(pattern.replace(r'</[^>]+>', ' ').replace(r'</?[^>]*>', ' '), text, re.I)
            if m:
                raw = m.group(1)
                break
    value = _parse_number(raw)
    if value <= 0:
        raise ValueError(f'مقدار عددی در صفحه {url} پیدا نشد.')
    return value


def fetch_usd_toman(*, timeout: float = 8.0, opener: Opener = _default_opener) -> tuple[int, str]:
    """نرخ دلار آزاد از TGJU، به تومان (صفحه ریالی است، بر ۱۰ تقسیم می‌شود)."""

    rial = fetch_tgju_value(TGJU_USD_URL, _TGJU_VALUE_PATTERNS, timeout=timeout, opener=opener)
    toman = round(rial / 10)
    return toman, datetime.now().isoformat(timespec='seconds')


def fetch_copper_usd_per_ton(*, timeout: float = 8.0, opener: Opener = _default_opener) -> tuple[float, str]:
    """قیمت مس (دلار/تن، بازار لندن) از TGJU -- نه بورس کالای ایران/تومان.

    سند قوانین محاسبه اصلی «میانگین ماهانه بورس کالا» (تومان/کیلوگرم) را منبع
    می‌دانست، اما مقدار مبنای تأییدشده‌ی اپراتور (۱۳,۲۶۹.۶۰ برای ۱۴۰۵/۰۱/۳۱)
    فقط با همین صفحه‌ی لندن جور درمی‌آمد -- نه با بورس کالا، نه با هیچ صفحه‌ی
    دیگر TGJU. تصمیم عملیاتی: همین صفحه، همیشه، برای مبنا و جاری هر دو. چون
    موتور محاسبه فقط نسبت (جاری÷مبنا) را مصرف می‌کند، این انتخاب معتبر می‌ماند
    مادامی که هیچ خواندن دیگری با واحد/بازار متفاوت با این تاریخچه قاطی نشود.
    """

    value = fetch_tgju_value(TGJU_COPPER_URL, _TGJU_VALUE_PATTERNS, timeout=timeout, opener=opener)
    return float(value), datetime.now().isoformat(timespec='seconds')
