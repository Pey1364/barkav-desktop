from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from budget_rich_v163 import norm


@dataclass(frozen=True)
class PhaseSuggestion:
    phase_no: int
    phase_name: str
    sub_phase: str
    confidence: float
    reason: str
    score: float


# Domain hints are deliberately small and auditable.  They are *priors*, not hard
# posting rules: the GUI still presents the result for human approval.
PHASE_HINTS: dict[int, tuple[str, ...]] = {
    1: ('زمین', 'سند زمین', 'خرید زمین', 'دفترخانه زمین', 'کمیسیون ملک'),
    2: ('مطالعات', 'آزمایش خاک', 'گمانه', 'ژئوتکنیک', 'نقشه برداری اولیه'),
    3: ('طراحی', 'نقشه معماری', 'نقشه سازه', 'طراحی سازه', 'طراحی برق', 'طراحی مکانیک', 'طراحی نما'),
    4: ('نظارت', 'ناظر', 'نظام مهندسی', 'کنترل کیفی', 'مجری ذیصلاح', 'آتش نشانی'),
    5: ('جواز', 'پروانه', 'شهرداری', 'ماده 5', 'ماده پنج', 'تامین اجتماعی'),
    6: ('تجهیز کارگاه', 'نگهبان', 'دفتر کارگاه', 'برق موقت', 'آب موقت', 'اتاق کارگر'),
    7: ('خاکبرداری', 'خاک برداری', 'گودبرداری', 'گود برداری', 'تخریب', 'پیکور', 'بیل مکانیکی', 'لودر', 'کمپرسی', 'بتن مگر', 'مگر', 'خاک', 'تسطیح'),
    8: ('اسکلت', 'میلگرد', 'آرماتور', 'بتن', 'قالب', 'تیرچه', 'سقف', 'جرثقیل', 'فوم سقف', 'همبندی سقف'),
    9: ('چاه', 'لوله سیمانی', 'حفاری چاه', 'کندن چاه'),
    10: ('کف سازی', 'کفسازی', 'زیرسازی کف'),
    11: ('شاسی آسانسور', 'شاسی کشی آسانسور', 'ریل آسانسور'),
    12: ('وال پست', 'وال‌پست'),
    13: ('میلگرد بستر',),
    14: ('وال مش', 'وال‌مش'),
    15: ('تیغه چینی', 'تیغه‌چینی', 'دیوارچینی', 'بلوک', 'سفال'),
    16: ('تاسیسات', 'تأسیسات', 'برق ساختمان', 'لوله برق', 'سیم برق', 'کابل', 'فاضلاب', 'لوله آب', 'لوله گاز', 'تابلو برق'),
    17: ('عایق', 'ایزوگام', 'بام', 'نمای سیمانی'),
    18: ('چهارچوب', 'چهارچوب فلزی', 'فریم فلزی', 'درب فلزی'),
    19: ('شاسی نما', 'شاسی کشی نما'),
    20: ('آسانسور', 'کابین آسانسور', 'موتور آسانسور'),
    21: ('درب ضدسرقت', 'درب ضد حریق', 'درب ضدحریق'),
    22: ('کاشی', 'سرامیک', 'سنگ کاری', 'سنگ‌کاری'),
    23: ('سقف کاذب', 'قرنیز'),
    24: ('گچ', 'گچکاری', 'گچ کاری'),
    25: ('upvc', 'پنجره', 'یو پی وی سی'),
    26: ('نرده', 'هندریل'),
    27: ('درب پارکینگ', 'درب حیاط'),
    28: ('نقاشی', 'رنگ آمیزی', 'رنگ‌آمیزی'),
    29: ('درب اتاق', 'درب داخلی'),
    30: ('انشعاب', 'آب دائم', 'برق دائم', 'گاز دائم'),
    31: ('پایان کار', 'پایان‌کار', 'تاییدیه نهایی', 'تأییدیه نهایی'),
    32: ('تفکیک', 'سند واحد', 'فروش واحد'),
}

# Terms that frequently describe *supporting cost* rather than a literal activity
# description.  These bridge the user's everyday wording to the metre taxonomy.
SUBPHASE_SYNONYMS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (('پیکور', 'چکش برقی', 'کمپرسور'), ('خاکبرداری دستی', 'خاک برداری دستی', 'تخریب', 'عملیات خاکی')),
    (('جرثقیل',), ('جرثقیل', 'سقف')),
    (('بیل مکانیکی', 'لودر', 'کمپرسی'), ('خاکبرداری ماشینی', 'خاک برداری ماشینی', 'حمل خاک')),
    (('سیم آرماتور', 'آرماتوربندی', 'آرماتور بندی'), ('میلگرد', 'آرماتور')),
    (('لوله سیمانی',), ('لوله سیمانی', 'چاه')),
    (('بتن مگر', 'مگر'), ('بتن مگر', 'مگر')),
    (('گچکار', 'گچ کار'), ('گچکاری', 'گچ کاری')),
    (('کاشیکار', 'کاشی کار'), ('کاشی', 'سرامیک')),
)

STOPWORDS = {
    'هزینه','پرداخت','خرید','بابت','تعمیر','اجرت','دستمزد','کرایه','برای','از','به','و','در','یک','عدد','تومان','ریال','فاکتور','رسید'
}


def _tokens(text: str) -> list[str]:
    n = norm(text)
    parts = re.findall(r'[\wآ-ی]+', n)
    return [x for x in parts if len(x) > 1 and x not in STOPWORDS]


def _phrase_score(text: str, phrases: tuple[str, ...]) -> float:
    n = norm(text)
    score = 0.0
    for p in phrases:
        pn = norm(p)
        if not pn:
            continue
        if pn in n:
            score += 42.0 + min(12.0, len(pn) / 2)
        else:
            pt = [t for t in _tokens(pn) if t]
            hits = sum(1 for t in pt if t in n)
            if pt and hits:
                score += 8.0 * hits / len(pt)
    return score


def suggest_phase(text: str, rich: Any, *, include_completed: bool = False) -> PhaseSuggestion | None:
    """Return a conservative phase/subphase suggestion for an expense description.

    The function uses three independent signals:
    1) words in the official phase/activity taxonomy,
    2) a small construction-domain synonym map,
    3) the project's explicit ACTIVE/PAUSED phase state.

    It never posts financially; callers decide whether to persist the suggestion.
    """
    raw = norm(text)
    if not raw:
        return None

    summaries = list(rich.list_phase_summary() or [])
    if not summaries:
        return None
    progress = rich.get_phase_progress() or {}
    toks = _tokens(raw)

    ranked: list[tuple[float, int, str, str, str]] = []
    for ph in summaries:
        no = int(ph.get('phase_no') or 0)
        name = str(ph.get('phase') or ph.get('phase_name') or '')
        state = str((progress.get(no) or {}).get('status') or 'NOT_STARTED').upper()
        if state == 'COMPLETED' and not include_completed:
            state_bias = -30.0
        elif state == 'ACTIVE':
            state_bias = 58.0
        elif state == 'PAUSED':
            state_bias = 12.0
        else:
            state_bias = 0.0

        score = state_bias
        reasons: list[str] = []
        nn = norm(name)
        if nn and nn in raw:
            score += 95.0
            reasons.append('نام فاز در شرح هزینه دیده شد')
        for t in toks:
            if t and t in nn:
                score += 18.0

        hint_score = _phrase_score(raw, PHASE_HINTS.get(no, ()))
        if hint_score:
            score += hint_score
            reasons.append('واژه‌های هزینه با این فاز هم‌خوان است')

        items = list(rich.subphase_candidates(no, '') or [])
        best_item = ''
        best_item_score = 0.0
        for item in items:
            desc = str(item.get('description') or '')
            sec = str(item.get('section') or '')
            hay = norm(desc + ' ' + sec)
            s = 0.0
            if hay and hay in raw:
                s += 75.0
            for t in toks:
                if t in hay:
                    s += 16.0
            # Everyday wording -> official subphase wording.
            for triggers, targets in SUBPHASE_SYNONYMS:
                if any(norm(x) in raw for x in triggers) and any(norm(x) in hay for x in targets):
                    s += 72.0
            if s > best_item_score:
                best_item_score = s
                best_item = desc
        if best_item_score:
            score += min(95.0, best_item_score)
            reasons.append('با ریزفعالیت متره تطبیق دارد')

        # An ACTIVE phase alone is not enough to make a high-confidence semantic
        # assignment if several phases are active.  Require some textual evidence.
        semantic = score - state_bias
        if semantic <= 0 and state == 'ACTIVE':
            score = 18.0
        reason = '؛ '.join(reasons) or ('فاز فعال پروژه' if state == 'ACTIVE' else 'تطبیق ضعیف')
        ranked.append((score, no, name, best_item, reason))

    ranked.sort(key=lambda x: (-x[0], x[1]))
    if not ranked or ranked[0][0] < 24:
        return None
    top = ranked[0]
    second = ranked[1][0] if len(ranked) > 1 else 0.0
    margin = max(0.0, top[0] - second)
    # Calibrated for UI colouring, not a statistical probability.
    confidence = min(0.97, 0.48 + min(0.30, top[0] / 320.0) + min(0.19, margin / 260.0))
    if top[0] < 55:
        confidence = min(confidence, 0.62)
    return PhaseSuggestion(
        phase_no=top[1], phase_name=top[2], sub_phase=top[3], confidence=round(confidence, 3), reason=top[4], score=round(top[0], 2)
    )


def apply_suggestion_to_payload(payload: dict[str, Any], text: str, rich: Any, *, force: bool = False) -> tuple[dict[str, Any], PhaseSuggestion | None, bool]:
    """Copy a phase suggestion into a pending payload without final posting.

    Existing user/AI assignments are preserved unless ``force`` is requested.
    Returns ``(payload_copy, suggestion, changed)``.
    """
    p = dict(payload or {})
    if str(p.get('detected_type') or '').upper() not in {'EXPENSE', 'UNKNOWN', ''}:
        return p, None, False
    existing = str(p.get('main_phase') or p.get('construction_stage') or '').strip()
    if existing and not force:
        return p, None, False
    s = suggest_phase(text or str(p.get('description') or ''), rich)
    if not s:
        return p, None, False
    phase_text = f'{s.phase_no:02d} — {s.phase_name}'
    changed = phase_text != str(p.get('main_phase') or '') or (s.sub_phase and s.sub_phase != str(p.get('sub_phase') or ''))
    p['main_phase'] = phase_text
    p['construction_stage'] = phase_text
    if s.sub_phase:
        p['sub_phase'] = s.sub_phase
        p['expense_category'] = s.sub_phase
    p['phase_suggestion_confidence'] = s.confidence
    p['phase_suggestion_reason'] = s.reason
    p['phase_assignment_source'] = 'PHASE_INTELLIGENCE_V175'
    return p, s, changed
