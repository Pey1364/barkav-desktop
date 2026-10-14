"""Pure calculation engine for the monthly price-escalation module.

No SQLite, no Tk: every function here takes plain numbers/dicts and returns
plain numbers/dicts, so the macro rules from ``قوانین_محاسبه_بروز.txt`` can be
unit-tested against real numbers from the reference workbook without a
database or a window. ``price_update_service.py`` is the only caller.

Macro rules enforced everywhere in this module (شرح کامل: بخش ۱ سند قوانین):
  * A ratio of 1.0 or less ("کاهشی یا خنثی") is never applied on its own; the
    caller falls back to a peer/phase average of ratios that ARE above 1, and
    in the last resort to the day-wage growth ratio.
  * A negative/non-positive ratio never enters an averaging pool.
  * A ratio above the USD growth ratio is applied as-is (never capped) but is
    flagged for the «لیست بررسی مجدد» review queue.
  * Output is never zero/empty.
"""

from __future__ import annotations

from dataclasses import dataclass, field

POSITIVE_EPS = 1e-9


def is_positive_ratio(ratio: float | None) -> bool:
    """A ratio counts as usable only if it is strictly above 1.0.

    ۱ هرگز اعمال نمی‌شود (قوانین بخش ۱) — a flat or shrinking ratio is treated
    the same as a decreasing one: neither is a real growth signal to average.
    """

    return ratio is not None and ratio > 1.0 + POSITIVE_EPS


def positive_average(ratios: list[float | None]) -> float | None:
    """Average of only the positive ratios in ``ratios``; ``None`` if none qualify."""

    usable = [r for r in ratios if is_positive_ratio(r)]
    if not usable:
        return None
    return sum(usable) / len(usable)


def wage_growth_rate(annual_rate: float, months_elapsed: float) -> float:
    """پارامترها!B9 = (1 + B10) ^ (B11 / 12) — compounded, never linear.

    ``annual_rate`` is a fraction (0.60 for the 60% مصوبه شورای عالی کار), and
    ``months_elapsed`` is months since the estimate's base month. This single
    figure is the floor for the whole workbook: every fallback chain in every
    catalog bottoms out here.
    """

    return (1.0 + annual_rate) ** (months_elapsed / 12.0)


def growth_ratio(current: float, base: float) -> float:
    """current / base — used for دلار, مس, or any other simple index."""

    if base == 0:
        return 1.0
    return current / base


@dataclass
class RatioResult:
    """One row's resolved ratio plus the audit trail a UI needs to show it."""

    ratio: float
    method_used: str
    needs_review: bool = False
    review_reason: str = ''


# --- method identifiers (also the دسته‌بندی values a rule row can declare) ---
METHOD_WEB = 'وب'
METHOD_PHASE_AVERAGE = 'میانگین فاز'
METHOD_PEER_AVERAGE = 'میانگین ردیف‌ها'
METHOD_WEIGHTED_INDEX = 'شاخص ترکیبی وزنی'
METHOD_SERVICE_TARIFF = 'تعرفه خدمات و شاخص ترکیبی وزنی'
METHOD_OTHER = 'سایر'


def flag_if_above_usd_growth(ratio: float, usd_growth: float) -> tuple[bool, str]:
    """Rule ۲: a ratio above دلار growth is applied as-is, only flagged.

    Never a ceiling — the caller must still use ``ratio`` unchanged.
    """

    if ratio > usd_growth + POSITIVE_EPS:
        return True, f'ضریب محاسباتی ({ratio:.4f}) بالاتر از رشد دلار ({usd_growth:.4f}) است'
    return False, ''


def resolve_with_fallback(
    own_ratio: float | None,
    *,
    peer_ratios: list[float | None] | None = None,
    phase_ratios: list[float | None] | None = None,
    wage_growth: float,
    usd_growth: float,
    own_method: str = METHOD_WEB,
) -> RatioResult:
    """Section ۱'s fallback ladder, shared by every catalog.

    اولویت: ۱) ضریب مستقل خودِ ردیف (وب/شاخص محاسباتی) اگر مثبت باشد
             ۲) میانگین ردیف‌های هم‌گروه (مثلاً «گروه هم‌رده» در قیمت مصالح)
             ۳) میانگین مثبت هم‌فاز
             ۴) ضریب رشد دستمزد روزمزد (کف نهایی، همیشه مثبت)
    هر مرحله که استفاده شد، اگر باز هم از رشد دلار بیشتر بود، برای بازبینی
    پرچم می‌خورد؛ افتادن به فال‌بک خودش هم پرچم بازبینی می‌زند چون یعنی ضریب
    اصلی رد شده است.
    """

    if is_positive_ratio(own_ratio):
        needs_review, reason = flag_if_above_usd_growth(own_ratio, usd_growth)
        return RatioResult(own_ratio, own_method, needs_review, reason)

    peer_avg = positive_average(peer_ratios or [])
    if peer_avg is not None:
        needs_review, reason = flag_if_above_usd_growth(peer_avg, usd_growth)
        note = 'ضریب مستقل ردیف کاهشی/خنثی بود؛ میانگین ردیف‌های هم‌گروه جایگزین شد'
        return RatioResult(peer_avg, METHOD_PEER_AVERAGE, True,
                            reason or note)

    phase_avg = positive_average(phase_ratios or [])
    if phase_avg is not None:
        note = 'ضریب مستقل ردیف کاهشی/خنثی بود؛ میانگین ضرایب مثبت هم‌فاز جایگزین شد'
        needs_review, reason = flag_if_above_usd_growth(phase_avg, usd_growth)
        return RatioResult(phase_avg, METHOD_PHASE_AVERAGE, True, reason or note)

    note = 'هیچ ضریب مثبتی (نه خودش، نه هم‌گروه، نه هم‌فاز) یافت نشد؛ ضریب رشد دستمزد روزمزد اعمال شد'
    needs_review, reason = flag_if_above_usd_growth(wage_growth, usd_growth)
    return RatioResult(wage_growth, METHOD_PHASE_AVERAGE, True, reason or note)


def material_web_ratio(
    web_prices: list[float],
    base_price: float,
    *,
    carry_rate: float = 0.0,
    tax_rate: float = 0.0,
    regional_factor: float = 1.0,
    connection_factor: float = 1.0,
) -> tuple[float, float]:
    """بخش ۲: قیمت وب۱/۲/۳ ← میانگین ← × (۱+حمل) × (۱+مالیات) × منطقه × اتصال.

    Returns ``(computed_price, ratio)``; ``ratio`` is computed independently
    from ``base_price`` per rule «استقلال بروز از اولیه» — the caller decides
    what to do when ``base_price`` is 0 (ratio is undefined, not zero).
    """

    prices = [p for p in web_prices if p]
    if not prices:
        raise ValueError('material_web_ratio requires at least one web price')
    avg = sum(prices) / len(prices)
    computed = avg * (1 + carry_rate) * (1 + tax_rate) * regional_factor * connection_factor
    ratio = (computed / base_price) if base_price else 1.0
    return computed, ratio


@dataclass
class ContractorWeights:
    """چهار وزن شاخص ترکیبی (بخش ۳ سند)؛ جمعشان معمولاً ۱ است ولی اجباری نیست."""

    wage: float = 0.0
    adjustment: float = 0.0
    inflation: float = 0.0
    dollar_or_metal: float = 0.0


def contractor_weighted_ratio(
    weights: ContractorWeights,
    *,
    wage_growth: float,
    adjustment_index: float,
    inflation_rate: float,
    dollar_or_metal_growth: float,
) -> float:
    """ضریب شاخص محاسباتی = میانگین وزنی چهار مؤلفه (بدون کف؛ کف را caller می‌زند)."""

    return (
        weights.wage * wage_growth
        + weights.adjustment * adjustment_index
        + weights.inflation * inflation_rate
        + weights.dollar_or_metal * dollar_or_metal_growth
    )


def contractor_ratio_with_floor(
    weights: ContractorWeights,
    *,
    wage_growth: float,
    adjustment_index: float,
    inflation_rate: float,
    dollar_or_metal_growth: float,
    usd_growth: float,
) -> RatioResult:
    """کف حداقل حقوق (قانون اصلی بخش ۳): ضریب = بیشینه(شاخص ترکیبی، رشد حداقل حقوق)."""

    computed = contractor_weighted_ratio(
        weights, wage_growth=wage_growth, adjustment_index=adjustment_index,
        inflation_rate=inflation_rate, dollar_or_metal_growth=dollar_or_metal_growth,
    )
    if computed >= wage_growth:
        needs_review, reason = flag_if_above_usd_growth(computed, usd_growth)
        return RatioResult(computed, METHOD_WEIGHTED_INDEX, needs_review, reason)
    # Falling back to the floor is itself review-worthy (مطابق «بررسی مجدد:
    # ضریب کاهشی — میانگین ضرایب مثبت فاز جایگزین شد» در شیت مصالح) regardless
    # of whether the floor value also happens to clear the USD-growth ceiling.
    _above_ceiling, ceiling_reason = flag_if_above_usd_growth(wage_growth, usd_growth)
    reason = ceiling_reason or 'شاخص ترکیبی محاسباتی زیر کف حداقل حقوق بود؛ نرخ رشد حداقل حقوق اعمال شد'
    return RatioResult(wage_growth, METHOD_WEIGHTED_INDEX, True, reason)


def duct_split_ratio(copper_growth: float, wage_growth: float,
                      *, copper_weight: float = 0.7, wage_weight: float = 0.3) -> float:
    """داکت اسپلیت (بخش ۳): ۷۰٪ رشد مس کاتد + ۳۰٪ رشد حداقل حقوق — بدون کف اضافه.

    Still passed through :func:`contractor_ratio_with_floor`'s max() by the
    caller, since it is still a قیمت پیمانکار row (a floor never hurts a
    ratio already computed to be at or above it).
    """

    return copper_weight * copper_growth + wage_weight * wage_growth


def service_tariff_ratio(annual_rate: float, months_elapsed: float,
                          *, regional_factor: float = 1.0, tax_rate: float = 0.0) -> float:
    """بخش ۴: (۱+ضریب سالانه/ماهانه)^(نسبت ماه‌های سپری‌شده) × منطقه × (۱+مالیات)."""

    base = (1.0 + annual_rate) ** months_elapsed
    return base * regional_factor * (1 + tax_rate)


def enforce_phase_uniformity(phase_ratio_by_code: dict[str, float],
                              row_phase_codes: list[str]) -> float:
    """قانون یکنواختی فاز: هر ردیفی که چند فاز دارد، فاز اول تعیین‌کننده است.

    یک ردیف معمولاً یک فاز دارد؛ چند فاز فقط برای اقلام مشترک (مثل لوازم
    مصرفی تیغه‌چینی) پیش می‌آید و آن‌ها مسیر «میانگین ردیف‌ها»ی خودشان را دارند،
    نه این فراخوان مستقیم را.
    """

    if not row_phase_codes:
        raise ValueError('a row must declare at least one phase code')
    return phase_ratio_by_code[row_phase_codes[0]]
