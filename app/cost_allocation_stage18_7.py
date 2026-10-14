"""Which line of the plan a construction cost belongs to.

A payment says what was bought in the operator's own words - 'خرید میلگرد',
'اجرت اسکلت' - while the plan says it in the workbook's words, split by phase
and by section. This module is the bridge: it reads the free text and answers
with one plan row, so the واقعی columns fill from what was actually spent
instead of being typed a second time.

The answer is a guess and is stored as one. It lands in ``expenses.plan_ref``,
where the operator can see it and change it, and every total downstream is
*recomputed* from that column rather than accumulated into place. A correction
is therefore one edit, re-running costs nothing, and no payment is ever counted
twice.

A payment usually arrives without an invoice breaking it down, so it cannot be
split across the four میلگرد lines of a phase. The rule the operator asked for
is the one implemented here: the whole amount goes on the single best line and
its siblings stay at zero.

Labour is the exception, because it is written down twice. Every line of
قیمت پیمانکار appears in a contract, and the contract records what was paid
against it - so for an اجرت line the contract is the source, and the payments
filed under تراکنش‌ها only speak for a contractor who has no contract. Taking
both would count the same money twice.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from typing import Any, Iterator

from budget_rich_v163 import norm
from contractor_store_stage18_7 import amount_of, get_contract, load_contracts, paid_total, upsert_contract
from phase_intelligence_v175 import STOPWORDS, SUBPHASE_SYNONYMS, suggest_phase

# What the entry form calls a section, and what the workbook calls it. The two
# vocabularies differ only for labour, which the form asks about as پیمانکار
# and the plan states as اجرت.
COST_TYPE_BY_GROUP = {'مصالح': 'مصالح', 'پیمانکار': 'اجرت', 'خدمات': 'خدمات'}

# The blank lines the workbook keeps under every اجرت heading. They name
# nothing, so they match a little of everything and are pushed below any line
# that names a real material or a real trade. 'متفرقه اسکلت' is not one of
# these: it names its phase and is where odd costs are meant to go.
_FILLER = ('سایر',)

# Below this a guess is not worth making; the cost stays unassigned and the
# plan shows a dash, which is honest and easy to fix by hand.
MIN_SCORE = 26.0

# Marks written into rich_phase_items.actual_source. A blank means a person
# typed that figure and it is theirs to keep.
_OWNED = ('EXPENSES', 'CONTRACTS')


@dataclass(frozen=True)
class PlanRowGuess:
    """One plan line, why it was chosen, and how sure the choice is."""

    plan_ref: str
    phase_no: int
    description: str
    section: str
    cost_type: str
    score: float
    confidence: float
    reason: str


def phase_of(stage: Any) -> int | None:
    """The phase number inside a stage label such as '08 — اسکلت'."""

    match = re.match(r'\s*(\d{1,2})', str(norm(stage) or ''))
    return int(match.group(1)) if match else None


def cost_type_of(cost_group: Any) -> str:
    return COST_TYPE_BY_GROUP.get(str(cost_group or '').strip(), '')


def _tokens(text: str) -> list[str]:
    """Words worth matching on: no stopwords, no digits standing alone."""

    parts = re.findall(r'[\wآ-ی]+', norm(text))
    return [p for p in parts if len(p) > 1 and p not in STOPWORDS]


def _is_filler(row: dict[str, Any]) -> bool:
    description = norm(row.get('description'))
    return any(description.startswith(word) for word in _FILLER)


def _row_score(row: dict[str, Any], text: str, tokens: list[str]) -> float:
    description = norm(row.get('description'))
    section = norm(row.get('section'))
    if not description:
        return 0.0

    score = 0.0
    # The plan's own wording quoted in the payment is the strongest signal
    # there is, and short words like 'بتن' are exactly the ones people write.
    if len(description) > 2 and description in text:
        score += 70.0 + min(20.0, len(description))
    if section and section != description and len(section) > 2 and section in text:
        score += 22.0

    haystack = f'{description} {section}'.strip()
    for token in tokens:
        if token in haystack:
            # A long token carries more meaning than a short one: 'میلگرد'
            # identifies a line, '12' only narrows it.
            score += 9.0 + min(9.0, len(token) * 1.5)

    # How much of the *line's own* wording the payment repeats. 'خرید میلگرد'
    # names half of 'میلگرد Ø8' and none of 'اجرت اجرای اسکلت', which is the
    # difference the token count alone misses: without it a one-word payment
    # scores below every threshold and lands nowhere.
    own = _tokens(description)
    if own:
        score += 55.0 * sum(1 for token in own if token in text) / len(own)

    for triggers, targets in SUBPHASE_SYNONYMS:
        if any(norm(t) in text for t in triggers) and any(norm(t) in haystack for t in targets):
            score += 34.0

    if _is_filler(row):
        score -= 45.0
    return max(0.0, score)


def _weight(row: dict[str, Any]) -> float:
    """How much of the phase this line was planned to be.

    Used only to break a tie. Four میلگرد lines all match 'خرید میلگرد'
    equally; the one the plan expected most of is the least surprising place
    to put an unsplit payment.
    """

    try:
        quantity = float(row.get('qty_estimate') or 0)
        rate = float(row.get('estimate_rate') or row.get('local_estimate_rate') or 0)
    except (TypeError, ValueError):
        return 0.0
    return quantity * rate


def candidate_rows(rich: Any, phase_no: int, cost_type: str) -> list[dict[str, Any]]:
    """The plan lines a cost of this section, in this phase, could belong to."""

    rows = list(rich.list_phase_items(int(phase_no)) or [])
    if cost_type:
        rows = [r for r in rows if norm(r.get('cost_type')) == norm(cost_type)]
    return [r for r in rows if str(r.get('plan_ref') or '').strip()]


def suggest_plan_row(rich: Any, *, text: str, cost_group: str = '', phase_no: int | None = None,
                     sub_phase: str = '') -> PlanRowGuess | None:
    """The plan line a construction cost most likely belongs to.

    ``sub_phase`` is whatever the operator picked in فاز فرعی. When it names a
    line outright that is not a guess at all, and it wins.
    """

    cost_type = cost_type_of(cost_group)
    blob = norm(f'{text} {sub_phase}')
    if phase_no is None:
        # No phase on the payment: fall back to the suggestion the entry form
        # already shows, so the two screens never disagree about the phase.
        try:
            hint = suggest_phase(blob, rich)
        except Exception:
            hint = None
        phase_no = hint.phase_no if hint else None
    if not phase_no:
        return None

    rows = candidate_rows(rich, int(phase_no), cost_type)
    if not rows:
        return None

    chosen = norm(sub_phase)
    if int(phase_no) == 4 and chosen:
        from engineering_phase187 import group_of, normalized, SUPERVISION_COST, SUPERVISION_TAX
        members = [r for r in rows if norm(group_of(r)) == chosen]
        tax_only = normalized(text).startswith(('مالیات ', 'کل مالیات '))
        summary = SUPERVISION_TAX if tax_only else SUPERVISION_COST
        prefix = 'مالیات ' if tax_only else 'اصل '
        target = next((r for r in members if r['description'] == summary
                       or normalized(r['description']).startswith(prefix)), None)
        if target:
            return PlanRowGuess(plan_ref=target['plan_ref'], phase_no=4,
                description=target['description'], section=group_of(target),
                cost_type=target['cost_type'], score=120, confidence=1,
                reason='فاز فرعی انتخاب‌شده؛ تقسیم اصل هزینه و مالیات')
    if int(phase_no) == 8 and chosen:
        # A sub-phase picked by its group's name (میلگرد، آزمایشگاه) chooses among that group's own lines.
        from skeleton_phase187 import members
        group_rows = members(rows, sub_phase)
        if group_rows:
            rows = group_rows
    tokens = _tokens(blob)
    ranked: list[tuple[float, float, dict[str, Any], str]] = []
    for row in rows:
        score = _row_score(row, blob, tokens)
        reason = 'واژه‌های تراکنش با این ردیف هم‌خوان است'
        if chosen and norm(row.get('description')) == chosen:
            score += 120.0
            reason = 'فاز فرعی انتخاب‌شده همین ردیف است'
        if score > 0:
            ranked.append((score, _weight(row), row, reason))
    if not ranked:
        return None

    ranked.sort(key=lambda item: (-item[0], -item[1], str(item[2].get('plan_ref'))))
    score, _, row, reason = ranked[0]
    if score < MIN_SCORE:
        return None

    runner_up = ranked[1][0] if len(ranked) > 1 else 0.0
    margin = max(0.0, score - runner_up)
    confidence = min(0.97, 0.45 + min(0.32, score / 300.0) + min(0.20, margin / 200.0))
    return PlanRowGuess(
        plan_ref=str(row.get('plan_ref') or ''), phase_no=int(row.get('phase_no') or phase_no),
        description=str(row.get('description') or ''), section=str(row.get('section') or ''),
        cost_type=str(row.get('cost_type') or ''), score=round(score, 2),
        confidence=round(confidence, 3), reason=reason,
    )


def guess_for_payload(rich: Any, plan: dict[str, Any]) -> str:
    """The plan line for a transaction payload, or '' when there is no guess.

    Only construction costs are placed. Everything else - a loan instalment, a
    sale - has no line in the build plan to belong to.
    """

    if not rich:
        return ''
    if str(plan.get('v18_title') or plan.get('transaction_title') or '').strip() != 'هزینه ساخت':
        return ''
    # The guess is a choice *within* a section, so an unclassified cost gets no
    # line at all. Leaving it blank shows up as a dash the operator can fix;
    # guessing across all three sections would quietly move somebody's money.
    if not cost_type_of(plan.get('cost_group')):
        return ''
    text = ' '.join(str(plan.get(key) or '') for key in
                    ('description', 'receiver_name', 'vendor_name', 'expense_category'))
    try:
        guess = suggest_plan_row(
            rich, text=text, cost_group=str(plan.get('cost_group') or ''),
            phase_no=phase_of(plan.get('construction_stage') or plan.get('main_phase')),
            sub_phase=str(plan.get('sub_phase') or ''),
        )
    except Exception:
        return ''
    return guess.plan_ref if guess else ''


def plan_row_labels(db: Any) -> dict[str, str]:
    """Every plan line's number and its wording, for screens that show a ref."""

    with db.read() as con:
        rows = con.execute(
            "SELECT plan_ref, description FROM rich_phase_items "
            "WHERE active=1 AND plan_ref<>''").fetchall()
    return {str(r['plan_ref']): str(r['description'] or '') for r in rows}


def _as_money(value: Any) -> int:
    """A figure as typed into a contract - grouped, Persian digits, or blank."""

    try:
        return int(round(float(norm(value).replace(',', '').replace('٬', '') or 0)))
    except (TypeError, ValueError):
        return 0


def labour_lines(db: Any) -> dict[str, str]:
    """Each اجرت price's wording, and the plan line it stands for.

    A contract names its work the way the price catalogue does, and the plan
    line points back at the same price - that shared name is the join. A price
    behind several plan lines resolves to the first, which is the same rule an
    unsplit payment follows everywhere else here.
    """

    with db.read() as con:
        try:
            rows = con.execute(
                """SELECT p.description price, pi.plan_ref plan_ref
                   FROM rich_phase_items pi JOIN rich_price_items p ON p.price_id=pi.price_id
                   WHERE pi.active=1 AND pi.cost_type='اجرت' AND pi.plan_ref<>''
                   ORDER BY pi.plan_ref""").fetchall()
        except sqlite3.Error:
            # A project with no price catalogue imported yet has no اجرت lines
            # to name, which is a state to pass through rather than fail on.
            return {}
    lines: dict[str, str] = {}
    for row in rows:
        key = norm(row['price'])
        if not key or key.startswith(_FILLER) or key in lines:
            continue
        lines[key] = str(row['plan_ref'])
    return lines


def _contract_lines(contract: dict[str, Any], lines: dict[str, str]) -> list[tuple[str, int]]:
    """The plan lines one contract covers, and what each was agreed to be worth."""

    covered: list[tuple[str, int]] = []
    for row in contract.get('rows') or []:
        # The plan filled this row in and left its own number on it, which
        # survives the operator renaming the row. Matching on the wording is
        # the fallback, for contracts entered before that was recorded.
        ref = str(row.get('plan_ref') or '').strip() or lines.get(norm(row.get('description')))
        if not ref:
            continue
        worth = _as_money(row.get('line_total'))
        if not worth:
            worth = _as_money(row.get('unit_price')) * _as_money(row.get('quantity'))
        covered.append((ref, worth))
    if covered:
        return covered
    # A contract whose rows name nothing recognisable still names its own
    # work in its title, which is chosen from the same catalogue.
    ref = lines.get(norm(contract.get('title')))
    return [(ref, 0)] if ref else []


def _share(amount: int, covered: list[tuple[str, int]]) -> dict[str, int]:
    """Split what was paid across the lines a contract covers.

    In proportion to what each line was agreed to be worth, because that is
    the only split the contract states. When it states none, the whole amount
    goes on the first line and the others stay at zero - money that was never
    divided is not divided here either. Rounding is given to the largest line
    so the parts still add up to what was paid.
    """

    if not covered:
        return {}
    worth = sum(max(0, w) for _ref, w in covered)
    if worth <= 0:
        return {covered[0][0]: amount}
    parts = {ref: 0 for ref, _w in covered}
    for ref, own in covered:
        parts[ref] += int(amount * max(0, own) / worth)
    biggest = max(covered, key=lambda item: item[1])[0]
    parts[biggest] += amount - sum(parts.values())
    return parts


def contract_worth(contract: dict[str, Any]) -> int:
    """What a contract is worth toward واقعی, by the operator's settlement rule.

    While the contractor has not yet been paid in full, the contract's own
    stated total governs: that is the commitment the work was engaged under,
    and a first deposit does not yet say what the trade will end up costing.
    Once the cumulative deposits reach or pass that total, the account is
    settled and the deposits themselves become the final figure - whatever
    was actually paid, not what was originally agreed, which is what 'مبلغ
    کل واریزی ملاک قیمت واقعی است' means once a contract is closed out.

    A contract with no stated total has nothing to fall back on but the
    deposits, so those are what it is worth throughout.
    """

    paid = paid_total(contract)
    stated = amount_of(contract.get('total_amount'))
    if stated <= 0:
        return paid
    return paid if paid >= stated else stated


def contract_actuals(db: Any) -> dict[str, int]:
    """What each اجرت plan line has cost, from the contracts that cover it."""

    lines = labour_lines(db)
    if not lines:
        return {}
    totals: dict[str, int] = {}
    for contract in load_contracts():
        worth = contract_worth(contract)
        if worth <= 0:
            continue
        for ref, amount in _share(worth, _contract_lines(contract, lines)).items():
            totals[ref] = totals.get(ref, 0) + amount
    return totals


def _stated_rows(contract: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    for row in contract.get('rows') or []:
        ref = str(row.get('plan_ref') or '').strip()
        if ref:
            yield ref, row


def apply_contract_rows(db: Any) -> int:
    """Write what a contract says about its lines onto the plan.

    A contract is where the workbook's blank 'سایر' lines get a name, and
    where a trade's agreed unit price and volume are written down. The plan
    sheet and the فازها tab show those as the line's title and its واقعی unit
    price and quantity, because a contract is the only place they are stated.

    Applied on every pass rather than once. Re-importing the reference
    workbook resets a line to 'سایر 1', and the contract's own wording has to
    come back rather than be lost - which it does on the next refresh.
    """

    import json
    stated = {}
    for contract in load_contracts():
        for ref, row in _stated_rows(contract):
            stated[ref] = (str(contract.get('contract_id') or ''),row)
    provenance=json.loads(db.get_setting('contract_actual_field_provenance') or '{}')
    previous_provenance=json.dumps(provenance,ensure_ascii=False,sort_keys=True)
    changed=0
    with db.atomic() as con:
        try:
            lines=con.execute("""SELECT phase_item_id,plan_ref,description,qty_actual,
                local_actual_rate,actual_source FROM rich_phase_items WHERE active=1 AND plan_ref<>''""").fetchall()
        except sqlite3.Error:return 0
        for line in lines:
            lid=str(line['phase_item_id']);entry=provenance.get(lid)
            target=stated.get(str(line['plan_ref'] or ''))
            current={key:line[key] for key in ('description','qty_actual','local_actual_rate')}
            if not target:
                if not entry:continue
                # Only fields still equal to our last derived write are reverted.
                fields={key:value for key,value in entry['before'].items()
                    if key in current and current[key]==entry['after'].get(key)}
                provenance.pop(lid,None)
            else:
                cid,row=target
                desired={'description':str(row.get('description') or '').strip() or current['description'],
                    'local_actual_rate':_as_money(row.get('unit_price')),'qty_actual':_as_number(row.get('quantity'))}
                before=entry['before'] if entry else current
                if not entry and line['actual_source']=='CONTRACTS':
                    # A legacy override has no reliable earlier manual values.
                    # Do not invent a baseline for deleting that contract.
                    from finance_db import _now
                    decisions=json.loads(db.get_setting('transaction_lifecycle_decisions') or '{}')
                    key='CONTRACT:'+cid
                    reason='مقادیر قبلی قیمت و مقدار واقعی این قرارداد قدیمی مشخص نیست؛ پیش از حذف تعیین تکلیف لازم است.'
                    if decisions.get(key,{}).get('reason')!=reason:
                        decisions[key]={'operation':'PRICE_FIELDS','reason':reason,'updated_at':_now()}
                        db.set_setting('transaction_lifecycle_decisions',json.dumps(decisions,ensure_ascii=False))
                else:
                    provenance[lid]={'contract_id':cid,'before':before,'after':desired}
                fields={key:value for key,value in desired.items() if current[key]!=value}
            if not fields:continue
            con.execute('UPDATE rich_phase_items SET '+','.join(key+'=?' for key in fields)+
                ',updated_at=datetime("now") WHERE phase_item_id=?',(*fields.values(),lid))
            db._audit(con,'phase_item',lid,'DERIVED_CONTRACT_FIELDS','CONTRACT_SYNC',
                before=current,after={**current,**fields},actor_id='GUI')
            changed+=1
        if json.dumps(provenance,ensure_ascii=False,sort_keys=True)!=previous_provenance:
            db.set_setting('contract_actual_field_provenance',json.dumps(provenance,ensure_ascii=False))
    return changed


def _as_number(value: Any) -> float:
    try:
        return float(norm(value).replace(',', '').replace('\u066c', '') or 0)
    except (TypeError, ValueError):
        return 0.0


def _detach_payment(pending_id: str) -> None:
    """Remove a pending item's own attached payment, from whichever
    contract it landed on last time.

    A revision of an already-approved transaction can move it to a
    different contract, drop its تسویه state, or clear the contract choice
    entirely - in every one of those cases the old deposit has to go before
    a new one (if any) is attached, or the contract it used to sit on keeps
    reporting money that was corrected away.
    """

    if not pending_id:
        return
    for contract in load_contracts():
        payments = contract.get('payments') or []
        kept = [p for p in payments if str(p.get('pending_id') or '') != pending_id]
        if len(kept) != len(payments):
            upsert_contract({**contract, 'payments': kept})


def attach_payment_to_contract(plan: dict[str, Any], *, pending_id: str = '') -> bool:
    """Record a تسویه‌شده construction cost as a deposit on the contract it pays.

    The entry form lets the operator tie a هزینه ساخت payment to one of the
    project's contracts; this is where that tie becomes money the contract
    itself can report - contract_worth() reads exactly this list, so a
    contract's واقعی figure moves the moment its final payment is posted.

    'تسویه' is the trigger, cash or cheque alike. A cheque's own clearing is
    a separate event this does not wait for: once the operator marks the
    last cheque of a contract تسویه, its face amount is understood to have
    reached the contractor, and joins واقعی the same way a cash settlement
    would. Only 'علی‌الحساب' and 'پرداخت‌نشده' are excluded - a promise, not
    yet a payment either way.

    ``pending_id``, when given, tags the attached deposit with the
    transaction that produced it and first clears any earlier deposit that
    same transaction left behind - so revising an already-approved payment
    (see ``revise_v18``) replaces its deposit in place instead of stacking
    a second one on top.
    """

    _detach_payment(pending_id)
    contract_id = str(plan.get('contract_id') or '').split('|', 1)[0].strip()
    if not contract_id:
        return False
    if str(plan.get('payment_state') or '').upper() != 'PAID':
        return False
    amount = int(plan.get('final_amount') or 0)
    if amount <= 0:
        return False
    contract = get_contract(contract_id)
    if contract is None:
        return False
    contract = dict(contract)
    contract['payments'] = [
        *(contract.get('payments') or []),
        {'date': str(plan.get('event_date_shamsi') or ''), 'amount': str(amount),
         'receiver': str(plan.get('receiver_name') or ''),
         'issuer': str(plan.get('issuer_name') or ''),
         'pending_id': str(pending_id or '')},
    ]
    upsert_contract(contract)
    return True


def expense_actuals(db: Any) -> dict[str, int]:
    """What each plan line has actually cost, from the expenses posted to it."""

    with db.read() as con:
        rows = con.execute(
            """SELECT plan_ref, SUM(final_amount) total FROM expenses
               WHERE deleted_at IS NULL AND status<>'CANCELLED' AND plan_ref<>''
               GROUP BY plan_ref""").fetchall()
    return {str(r['plan_ref']): int(r['total'] or 0) for r in rows}


def actual_totals(db: Any) -> dict[str, tuple[int, str]]:
    """Every plan line's spend and where the figure came from.

    A contract overrules the transactions on the same line. The two describe
    the same money from different ends - the payment the operator recorded,
    and the payment the contract acknowledges - so adding them would double
    every contracted trade. Transactions still speak for the lines no
    contract covers, which is the case the operator described: a contractor
    with no contract is worth whatever was paid to them.
    """

    totals = {ref: (amount, 'EXPENSES') for ref, amount in expense_actuals(db).items()}
    totals.update((ref, (amount, 'CONTRACTS')) for ref, amount in contract_actuals(db).items())
    from engineering_phase187 import allocate_actuals
    with db.read() as con:
        rows = [dict(r) for r in con.execute('SELECT * FROM rich_phase_items WHERE active=1 AND phase_no=4').fetchall()]
    return allocate_actuals(rows, totals)


def apply_actuals(db: Any) -> int:
    """Write the spent totals onto the plan, and return how many lines moved.

    Lines the operator filled in by hand are left alone: only a line this
    function has written before carries a source mark, and only those are
    cleared when the money behind them goes away.

    A contract's own statements about its lines - their names, their agreed
    unit price and volume - are written first, by apply_contract_rows.
    """

    # What the contracts say about their lines first: a line renamed by a
    # contract is the same line, and the totals below do not depend on it.
    changed = apply_contract_rows(db)
    totals = actual_totals(db)
    with db.tx() as con:
        rows = con.execute(
            """SELECT phase_item_id, plan_ref, total_actual, actual_source
               FROM rich_phase_items WHERE active=1 AND (plan_ref<>'' OR actual_source<>'')""").fetchall()
        for row in rows:
            ref = str(row['plan_ref'] or '')
            owned = str(row['actual_source'] or '') in _OWNED
            if ref in totals:
                want, source = totals[ref]
                want = int(want)
            elif owned:
                want, source = 0, ''
            else:
                continue
            if int(row['total_actual'] or 0) == want and str(row['actual_source'] or '') == source:
                continue
            con.execute(
                'UPDATE rich_phase_items SET total_actual=?, actual_source=?, updated_at=datetime("now") '
                'WHERE phase_item_id=?', (want, source, row['phase_item_id']))
            changed += 1
    return changed
