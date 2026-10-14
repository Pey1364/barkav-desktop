from __future__ import annotations

import math

import price_calc_engine as calc


def test_wage_growth_rate_matches_reference_workbook():
    """گرمسار reference: 60% annual, 5 months elapsed -> H column value 1.216326007054794."""
    rate = calc.wage_growth_rate(0.60, 5)
    assert math.isclose(rate, 1.216326007054794, rel_tol=1e-9)


def test_wage_growth_is_compounded_not_linear():
    # قوانین سند: "۵/۱۲ خطیِ ۶۰٪ عدد غلط می‌دهد" -- the two must NOT agree.
    # (For a sub-annual exponent, compounding is actually *below* the naive
    # linear scaling by Bernoulli's inequality -- the point of the test is
    # that the module uses the compounded formula, not which one is larger.)
    linear_would_be = 1 + 0.60 * (5 / 12)
    rate = calc.wage_growth_rate(0.60, 5)
    assert not math.isclose(rate, linear_would_be)


def test_growth_ratio_basic():
    assert calc.growth_ratio(232500, 150000) == 232500 / 150000
    assert calc.growth_ratio(100, 0) == 1.0  # no base -> no claimed growth, never a crash


def test_positive_ratio_excludes_one_and_below():
    assert calc.is_positive_ratio(1.0) is False
    assert calc.is_positive_ratio(0.95) is False
    assert calc.is_positive_ratio(None) is False
    assert calc.is_positive_ratio(1.0001) is True


def test_positive_average_ignores_non_positive_entries():
    assert calc.positive_average([1.3, 0.9, 1.0, None, 1.1]) == (1.3 + 1.1) / 2
    assert calc.positive_average([0.8, 1.0, None]) is None


def test_resolve_with_fallback_prefers_own_positive_ratio():
    result = calc.resolve_with_fallback(
        1.35, peer_ratios=[1.1], phase_ratios=[1.2], wage_growth=1.2, usd_growth=1.5,
    )
    assert result.ratio == 1.35
    assert result.method_used == calc.METHOD_WEB
    assert result.needs_review is False


def test_resolve_with_fallback_falls_through_to_peer_then_phase_then_wage():
    # Own ratio decreasing -> peer average used.
    result = calc.resolve_with_fallback(
        0.9, peer_ratios=[1.2, 1.4], phase_ratios=[1.9], wage_growth=1.2, usd_growth=1.5,
    )
    assert math.isclose(result.ratio, 1.3)
    assert result.method_used == calc.METHOD_PEER_AVERAGE
    assert result.needs_review is True

    # No own ratio, no peer group -> phase average used.
    result = calc.resolve_with_fallback(
        None, peer_ratios=[], phase_ratios=[1.1, 0.8, 1.3], wage_growth=1.2, usd_growth=1.5,
    )
    assert math.isclose(result.ratio, 1.2)  # average of 1.1 and 1.3 only
    assert result.method_used == calc.METHOD_PHASE_AVERAGE

    # Nothing usable anywhere -> wage growth floor, always positive.
    result = calc.resolve_with_fallback(
        0.7, peer_ratios=[0.8], phase_ratios=[1.0], wage_growth=1.216326, usd_growth=1.5,
    )
    assert result.ratio == 1.216326
    assert result.needs_review is True


def test_ceiling_never_caps_but_always_flags():
    needs_review, reason = calc.flag_if_above_usd_growth(1.8, 1.5)
    assert needs_review is True
    assert reason
    needs_review, reason = calc.flag_if_above_usd_growth(1.3, 1.5)
    assert needs_review is False
    assert reason == ''


def test_material_web_ratio_chain():
    computed, ratio = calc.material_web_ratio(
        [100_000, 110_000, 105_000], base_price=100_000,
        carry_rate=0.30, tax_rate=0.0, regional_factor=1.0, connection_factor=1.0,
    )
    avg = (100_000 + 110_000 + 105_000) / 3
    assert math.isclose(computed, avg * 1.30)
    assert math.isclose(ratio, computed / 100_000)


def test_material_web_ratio_requires_at_least_one_price():
    try:
        calc.material_web_ratio([], base_price=100)
    except ValueError:
        pass
    else:
        raise AssertionError('expected ValueError for an empty web price list')


def test_contractor_weighted_ratio_is_a_plain_weighted_average():
    # کارگری خالص family: weights 0.60/0.25/0.15/0 (بخش ۳ سند).
    weights = calc.ContractorWeights(wage=0.60, adjustment=0.25, inflation=0.15, dollar_or_metal=0.0)
    ratio = calc.contractor_weighted_ratio(
        weights, wage_growth=1.216326007054794, adjustment_index=1.10, inflation_rate=1.20,
        dollar_or_metal_growth=1.0,
    )
    expected = 0.60 * 1.216326007054794 + 0.25 * 1.10 + 0.15 * 1.20
    assert math.isclose(ratio, expected)


def test_contractor_floor_replaces_below_floor_index_and_flags_review():
    weights = calc.ContractorWeights(wage=0.60, adjustment=0.25, inflation=0.15, dollar_or_metal=0.0)
    result = calc.contractor_ratio_with_floor(
        weights, wage_growth=1.216326007054794, adjustment_index=1.0, inflation_rate=1.0,
        dollar_or_metal_growth=1.0, usd_growth=1.55,
    )
    # 1.166 computed index is below the 1.216326 floor -> floor wins.
    assert math.isclose(result.ratio, 1.216326007054794)
    assert result.needs_review is True


def test_contractor_floor_keeps_computed_index_when_above_floor():
    weights = calc.ContractorWeights(wage=0.25, adjustment=0.15, inflation=0.30, dollar_or_metal=0.30)
    result = calc.contractor_ratio_with_floor(
        weights, wage_growth=1.216326007054794, adjustment_index=1.3, inflation_rate=1.4,
        dollar_or_metal_growth=1.6, usd_growth=1.55,
    )
    computed = 0.25 * 1.216326007054794 + 0.15 * 1.3 + 0.30 * 1.4 + 0.30 * 1.6
    assert computed > 1.216326007054794
    assert math.isclose(result.ratio, computed)


def test_duct_split_ratio_uses_copper_not_dollar():
    ratio = calc.duct_split_ratio(copper_growth=1.30, wage_growth=1.216326007054794)
    assert math.isclose(ratio, 0.7 * 1.30 + 0.3 * 1.216326007054794)


def test_service_tariff_matches_reference_workbook_zero_annual_case():
    # Reference row 1, قیمت خدمات: annual/monthly rate is 0 for this row's own
    # formula slot (its growth instead comes from a researched anchor number),
    # so the generic formula alone must reduce to a no-op ratio of 1.0.
    ratio = calc.service_tariff_ratio(0.0, 5 / 12)
    assert math.isclose(ratio, 1.0)


def test_enforce_phase_uniformity_uses_first_declared_phase():
    by_code = {'06': 1.216326007054794, '12': 1.05}
    assert calc.enforce_phase_uniformity(by_code, ['06']) == by_code['06']
    assert calc.enforce_phase_uniformity(by_code, ['12', '06']) == by_code['12']
