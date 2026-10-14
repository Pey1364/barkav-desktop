from __future__ import annotations

import pytest

import price_index_fetch as fetch


def _opener(html: str):
    def opener(_url: str, _timeout: float) -> bytes:
        return html.encode('utf-8')
    return opener


def test_fetch_tgju_value_matches_primary_pattern():
    html = '<div>نرخ فعلی</div><div>232,500</div>'
    value = fetch.fetch_tgju_value('https://example.test', fetch._TGJU_VALUE_PATTERNS,
                                    opener=_opener(html))
    assert value == 232_500


def test_fetch_tgju_value_handles_persian_digits_and_separators():
    html = '<div>نرخ فعلی</div><div>۲۳۲٬۵۰۰</div>'
    value = fetch.fetch_tgju_value('https://example.test', fetch._TGJU_VALUE_PATTERNS,
                                    opener=_opener(html))
    assert value == 232_500


def test_fetch_tgju_value_falls_back_to_stripped_text():
    # No markup right beside the label -- the last-resort stripped-text pass must catch it.
    html = '<html><body><p>در حال حاضر قیمت هر دلار 2325000 ریال</p></body></html>'
    value = fetch.fetch_tgju_value('https://example.test', fetch._TGJU_VALUE_PATTERNS,
                                    opener=_opener(html))
    assert value == 2_325_000


def test_fetch_tgju_value_raises_when_nothing_matches():
    html = '<html><body>صفحه مورد نظر موجود نمی‌باشد</body></html>'
    with pytest.raises(ValueError):
        fetch.fetch_tgju_value('https://example.test', fetch._TGJU_VALUE_PATTERNS,
                                opener=_opener(html))


def test_fetch_usd_toman_converts_rial_page_to_toman():
    html = '<div>نرخ فعلی</div><div>2,325,000</div>'
    toman, timestamp = fetch.fetch_usd_toman(opener=_opener(html))
    assert toman == 232_500
    assert timestamp  # non-empty ISO timestamp


def test_fetch_tgju_value_handles_a_decimal_value():
    # The exact regression that would have silently dropped copper's cents:
    # the value must come back as 13269.60, not truncated to 13269.
    html = '<div>نرخ فعلی</div><div>13,269.60</div>'
    value = fetch.fetch_tgju_value('https://example.test', fetch._TGJU_VALUE_PATTERNS,
                                    opener=_opener(html))
    assert value == 13_269.60


def test_fetch_copper_usd_per_ton_does_not_convert_rial_to_toman():
    # Copper's TGJU page already reports دلار directly -- unlike the dollar
    # page, this value must NOT be divided by 10.
    html = '<div>نرخ فعلی</div><div>14,722.50</div>'
    value, timestamp = fetch.fetch_copper_usd_per_ton(opener=_opener(html))
    assert value == 14_722.50
    assert timestamp
