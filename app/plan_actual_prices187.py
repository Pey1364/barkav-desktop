"""Read contract/statement unit prices without changing posted financial totals."""
from collections import defaultdict
import math

from contractor_store_stage18_7 import load_contracts, load_statements
from ui_stage18_3 import en


def number187(value):
    try:
        value = float(str(en(str(value or '0'))).replace(',', '').replace('٬', '').replace('٫', '.'))
        return value if math.isfinite(value) else 0.0
    except (TypeError, ValueError):
        return 0.0


def wording187(value):
    return str(value or '').strip().replace('ي', 'ی').replace('ك', 'ک')


def contract_prices187(plan_rows):
    """Per plan reference: performed quantity and its weighted unit price.

    Statement period figures are summed; cumulative figures are only a
    fallback for legacy rows without period figures. Never sum both. Exact
    references win, and ambiguous statement descriptions are not guessed.
    """
    refs = {str(row.get('plan_ref') or '') for row in plan_rows}
    legacy_refs = {}
    for row in sorted(plan_rows, key=lambda r: str(r.get('plan_ref') or '')):
        if row.get('cost_type') == 'اجرت' and row.get('plan_ref'):
            legacy_refs.setdefault(wording187(row.get('description')), str(row['plan_ref']))
    statements = defaultdict(list)
    for statement in load_statements():
        statements[str(statement.get('contract_id') or '')].append(statement)
    accumulated = defaultdict(list)
    for contract in load_contracts():
        lines = []
        for line in contract.get('rows') or []:
            ref = str(line.get('plan_ref') or '').strip()
            if not ref:
                ref = legacy_refs.get(wording187(line.get('description')), '')
            if ref and ref in refs:
                lines.append((ref, line))
        descriptions = defaultdict(set)
        by_ref = defaultdict(list)
        for ref, line in lines:
            descriptions[wording187(line.get('description'))].add(ref)
            by_ref[ref].append(line)
        agreed = {}
        for ref, own_lines in by_ref.items():
            quantity = sum(max(0.0, number187(line.get('quantity'))) for line in own_lines)
            value = sum(max(0.0, number187(line.get('quantity'))) * number187(line.get('unit_price'))
                        if number187(line.get('unit_price')) > 0 else number187(line.get('line_total'))
                        for line in own_lines)
            rate = value / quantity if quantity > 0 else number187(own_lines[0].get('unit_price'))
            valid = any(line.get('unit_price') not in (None, '') or
                        (line.get('line_total') not in (None, '') and number187(line.get('quantity')) > 0)
                        for line in own_lines)
            agreed[ref] = dict(quantity=quantity, rate=rate, valid=valid)
        work = {}
        for statement in sorted(statements[str(contract.get('contract_id') or '')],
                                key=lambda s: str(en(str(s.get('statement_date') or '')))):
            for line in statement.get('rows') or []:
                ref = str(line.get('plan_ref') or '').strip()
                if not ref:
                    matches = descriptions.get(wording187(line.get('description')), set())
                    if len(matches) != 1:
                        continue
                    ref = next(iter(matches))
                if ref not in by_ref:
                    continue
                rate = (number187(line.get('unit_price')) if line.get('unit_price') not in (None, '')
                        else agreed[ref]['rate'])
                entry = work.setdefault(ref, dict(quantity=0.0, amount=0.0, valid=False))
                period = line.get('worked_quantity')
                if period not in (None, ''):
                    quantity = max(0.0, number187(period))
                    amount = line.get('line_total')
                    entry['valid'] |= amount not in (None, '') or line.get('unit_price') not in (None, '') or agreed[ref]['valid']
                    amount = number187(amount) if amount not in (None, '') else quantity * rate
                    entry['quantity'] += quantity
                    entry['amount'] += amount
                elif line.get('cumulative_quantity') not in (None, ''):
                    entry['quantity'] = max(0.0, number187(line['cumulative_quantity']))
                    amount = line.get('cumulative_amount')
                    entry['valid'] = amount not in (None, '') or line.get('unit_price') not in (None, '') or agreed[ref]['valid']
                    entry['amount'] = number187(amount) if amount not in (None, '') else entry['quantity'] * rate
        for ref, agreement in agreed.items():
            performed = work.get(ref)
            quantity = performed['quantity'] if performed is not None else agreement['quantity']
            rate = (performed['amount'] / quantity if performed is not None and quantity > 0
                    else agreement['rate'])
            valid = performed['valid'] if performed is not None and quantity > 0 else agreement['valid']
            if rate < 0 or not valid:
                continue
            accumulated[ref].append((quantity, rate))
    result = {}
    for ref, parts in accumulated.items():
        quantity = sum(q for q, _rate in parts)
        rate = (sum(q * rate for q, rate in parts) / quantity if quantity > 0
                else sum(rate for _q, rate in parts) / len(parts))
        result[ref] = dict(quantity=quantity, rate=int(round(rate)))
    return result
