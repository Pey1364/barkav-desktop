"""Keep Persian lines in RTL order around embedded Latin text and numbers."""

from __future__ import annotations

import re
from decimal import Decimal

RLM = '‏'
LRI = '\u2066'
PDI = '\u2069'
_LTR_RUN = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:/+\-]*(?:[ \t]+[A-Za-z0-9][A-Za-z0-9._:/+\-]*)*')
_GROUPABLE_NUMBER = re.compile(r'\s*([+-]?)([0-9][0-9,٬ ]*)(?:[.٫]([0-9]+))?\s*\Z')
_PERSIAN_DIGITS = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')
_ASCII_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')


def fa_grouped_number(value):
    """Format a numeric cell with Persian digits and Persian thousands marks."""

    if isinstance(value, bool):
        return value
    if not isinstance(value, (int, float, Decimal)):
        if not isinstance(value, str):
            return value
        match = _GROUPABLE_NUMBER.fullmatch(value.translate(_ASCII_DIGITS))
        if not match:
            return value
        sign, integer, fraction = match.groups()
        integer = re.sub(r'[,٬ ]', '', integer)
    else:
        raw = str(value)
        match = _GROUPABLE_NUMBER.fullmatch(raw)
        if not match:
            return value
        sign, integer, fraction = match.groups()
        integer = re.sub(r'[,٬ ]', '', integer)
    grouped = re.sub(r'\B(?=(\d{3})+(?!\d))', '٬', integer)
    result = sign + grouped + (f'٫{fraction}' if fraction is not None else '')
    return result.translate(_PERSIAN_DIGITS)


def rtl(text) -> str:
    """Set an RTL base direction and isolate inline Latin runs."""

    text = str(text)
    if not text:
        return text
    if not text.startswith(RLM):
        text = RLM + text
    return _LTR_RUN.sub(lambda match: LRI + match.group(0) + PDI, text)
