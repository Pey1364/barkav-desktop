from __future__ import annotations

from price_update_stage18_7 import _format_param_value, _parse_param_float


def test_parse_param_float_preserves_decimals():
    # The exact regression parse_int() would cause: "." stripped entirely
    # turns 13269.6 into 132696, a ~10x magnitude error on مس's price.
    assert _parse_param_float('13,269.60') == 13269.60


def test_parse_param_float_handles_whole_numbers():
    assert _parse_param_float('232,500') == 232500.0


def test_parse_param_float_handles_empty_and_garbage():
    assert _parse_param_float('') == 0.0
    assert _parse_param_float('-') == 0.0
    assert _parse_param_float('abc') == 0.0


def test_format_param_value_shows_whole_numbers_clean():
    assert _format_param_value(232500) == '232,500'


def test_format_param_value_keeps_two_decimals_for_fractional_values():
    # Regression: :,.0f would round 13269.60 to "13,270" on every redisplay,
    # and re-saving that rounded text would lose the cents permanently.
    assert _format_param_value(13269.60) == '13,269.60'


def test_format_and_parse_round_trip_preserves_copper_precision():
    value = 13269.60
    displayed = _format_param_value(value)
    assert _parse_param_float(displayed) == value
