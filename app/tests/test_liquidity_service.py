"""liquidity_service: the ۳۰ روز آینده logic moved out of dashboard_stage18_7."""
from __future__ import annotations

import ast
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import liquidity_service as ls  # noqa: E402

TODAY = date(2026, 9, 11)
DATES = {
    '1405/06/20': TODAY,
    '1405/07/01': TODAY + timedelta(days=10),
    '1405/07/02': TODAY + timedelta(days=11),
}
CONTRACTS = [
    {
        'contract_id': 'C1', 'title': 'قرارداد اول',
        'payments': [{'amount': '100'}],
        'payment_schedule': [
            {'label': 'پیش پرداخت', 'due_date_shamsi': '1405/06/20', 'amount': '100'},
            {'label': 'مرحله اول', 'due_date_shamsi': '1405/07/01', 'amount': '300'},
        ],
    },
    {
        'contract_id': 'C2', 'title': 'قرارداد دوم',
        'payment_schedule': [
            {'label': 'پیش پرداخت', 'due_date_shamsi': '1405/07/02', 'amount': '۲۰۰'},
        ],
    },
]


def test_module_imports_no_ui_toolkit():
    code = ('import sys; sys.path.insert(0, r"%s"); import liquidity_service; '
            'print(sorted(m for m in sys.modules if m.split(".")[0] in '
            '{"tkinter", "_tkinter", "webview"}))' % APP_DIR)
    out = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == '[]'


@pytest.mark.parametrize('value', [
    '0', '12', '۱۲٬۳۴۵', '١٢٣', '1,234,567', '1،234', ' 42 ', '-7', '-', '', None,
    '12.5', 'abc', '12-3', '۵۰۰ تومان', 0, 1500, -3,
])
def test_parse_amount_matches_the_tk_parser_it_replaces(value):
    from ui_stage18_3 import parse_int
    assert ls.parse_amount(value) == parse_int(value)


def test_commitments_exclude_paid_and_issued_cheque_amounts():
    total, rows = ls.contractor_commitments_30d(
        CONTRACTS, TODAY, TODAY + timedelta(days=30), {'C1': 125},
        to_gregorian=lambda value: DATES[value],
    )
    assert total == 375
    assert [(r['contract_id'], r['amount'], r['due_date']) for r in rows] == [
        ('C1', 175, TODAY + timedelta(days=10)), ('C2', 200, TODAY + timedelta(days=11)),
    ]


def test_default_converter_iso_strings_are_counted():
    # revenue_service.shamsi_to_gregorian returns an ISO string; the loop
    # used to skip it, so commitments were always 0.
    from revenue_service import gregorian_to_shamsi
    assert isinstance(ls.shamsi_to_gregorian('1405/07/01'), str)
    contracts = [{'contract_id': 'C1', 'title': 'x', 'payment_schedule': [
        {'label': 'a', 'due_date_shamsi': gregorian_to_shamsi(TODAY + timedelta(days=3)), 'amount': '70'},
        {'label': 'b', 'due_date_shamsi': 'نامعتبر', 'amount': '5'},
    ]}]
    total, rows = ls.contractor_commitments_30d(contracts, TODAY, TODAY + timedelta(days=30))
    assert total == 70
    assert rows[0]['due_date'] == TODAY + timedelta(days=3)


def test_breakdown_keeps_cash_separate_from_net_commitment_balance():
    b = ls.thirty_day_liquidity_breakdown(claims=1_000, commitments=200, cheques=300,
                                          installments=100, cash=500)
    assert (b['balance'], b['cash'], b['liquidity_needed']) == (400, 500, 900)


class _Con:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, _sql, args):
        return type('R', (), {'fetchall': lambda _s: [r for r in self.rows if r['expense_id'] in args]})()


class _DB:
    def __init__(self):
        self.postings = [{'expense_id': 'E1', 'pending_id': 'P1'}, {'expense_id': 'E2', 'pending_id': 'P2'}]
        self.pending = {'P1': {'payload': {'contract_id': 'C1'}}, 'P2': {'payload': {}}}

    def read(self):
        db = self

        class _Ctx:
            def __enter__(self):
                return _Con(db.postings)

            def __exit__(self, *a):
                return False
        return _Ctx()

    def get_pending_item(self, pid):
        return self.pending.get(pid)

    def cash_balance(self):
        return 1_000


def test_issued_cheques_are_summed_per_contract():
    rows = [{'expense_id': 'E1', 'amount': 60}, {'expense_id': 'E1', 'amount': 65},
            {'expense_id': 'E2', 'amount': 999}, {'expense_id': '', 'amount': 5}]
    assert ls.issued_cheques_by_contract(_DB(), rows) == {'C1': 125}


def test_thirty_day_summary_combines_the_service_figures():
    class Service:
        db = _DB()

        def cheque_30d_summary(self, days):
            return {'amount': 125, 'rows': [{'expense_id': 'E1', 'amount': 125}]}

        def loans_30d_summary(self, days):
            return {'upcoming_amount': 50}

        def sales_30d_summary(self, days):
            return {'upcoming_amount': 2_000}

    out = ls.thirty_day_summary(Service(), CONTRACTS, today=TODAY,
                                to_gregorian=lambda value: DATES[value])
    assert out['commitments'] == 375 and out['cheques'] == 125 and out['installments'] == 50
    assert out['claims'] == 2_000 and out['cash'] == 1_000
    assert out['balance'] == 2_000 - 375 - 125 - 50
    assert out['liquidity_needed'] == 1_000 + out['balance']


def test_tk_dashboard_only_delegates_to_the_service():
    tree = ast.parse((APP_DIR / 'dashboard_stage18_7.py').read_text(encoding='utf-8'))
    bodies = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in {
            '_thirty_day_summary_187', '_issued_cheques_by_contract_187', 'contractor_commitments_30d_187',
        }:
            bodies[node.name] = ast.unparse(node)
    assert 'liquidity_service.thirty_day_summary(' in bodies['_thirty_day_summary_187']
    assert 'liquidity_service.issued_cheques_by_contract(' in bodies['_issued_cheques_by_contract_187']
    assert 'liquidity_service.contractor_commitments_30d(' in bodies['contractor_commitments_30d_187']
    for body in bodies.values():
        assert 'execute(' not in body and 'for contract in' not in body


OVERDUE_CONTRACTS = [{
    'contract_id': 'C9', 'title': 'معوق',
    'payments': [{'amount': '30'}],
    'payment_schedule': [
        {'label': 'قدیمی', 'due_date_shamsi': 'd-40', 'amount': '50'},    # 30 paid -> 20 overdue
        {'label': 'معوق دوم', 'due_date_shamsi': 'd-5', 'amount': '40'},
        {'label': 'آینده', 'due_date_shamsi': 'd+10', 'amount': '100'},
        {'label': 'دور', 'due_date_shamsi': 'd+90', 'amount': '500'},
    ],
}]


def _rel(value):
    sign, days = value[1], int(value[2:])
    return TODAY + timedelta(days=days if sign == '+' else -days)


def test_overdue_amounts_are_separate_and_never_in_the_window():
    due = ls.contractor_schedule_due(OVERDUE_CONTRACTS, TODAY, TODAY + timedelta(days=30),
                                     to_gregorian=_rel)
    assert due['window_total'] == 100
    assert [(r['label'], r['amount']) for r in due['window_rows']] == [('آینده', 100)]
    assert due['overdue_total'] == 60
    assert [(r['label'], r['amount'], r['days_overdue']) for r in due['overdue_rows']] == [
        ('قدیمی', 20, 40), ('معوق دوم', 40, 5)]
    # contractor_commitments_30d (the card's figure) is exactly the window part.
    assert ls.contractor_commitments_30d(OVERDUE_CONTRACTS, TODAY, TODAY + timedelta(days=30),
                                         to_gregorian=_rel) == (100, due['window_rows'])


def test_issued_cheques_cover_the_window_first_then_overdue():
    due = ls.contractor_schedule_due(OVERDUE_CONTRACTS, TODAY, TODAY + timedelta(days=30),
                                     {'C9': 130}, to_gregorian=_rel)
    # 100 of the cheque reserves the in-window milestone (unchanged rule);
    # the 30 left covers the oldest overdue amount.
    assert due['window_total'] == 0
    assert [(r['label'], r['amount']) for r in due['overdue_rows']] == [('معوق دوم', 30)]
    assert due['overdue_total'] == 30


def test_overdue_is_reported_but_not_in_the_balance():
    class Service:
        db = _DB()

        def cheque_30d_summary(self, days):
            return {'amount': 0, 'rows': []}

        def loans_30d_summary(self, days):
            return {'upcoming_amount': 0}

        def sales_30d_summary(self, days):
            return {'upcoming_amount': 0}

    out = ls.thirty_day_summary(Service(), OVERDUE_CONTRACTS, today=TODAY, to_gregorian=_rel)
    assert out['commitments'] == 100 and out['overdue_commitments'] == 60
    assert out['balance'] == -100 and out['liquidity_needed'] == 1_000 - 100
    assert len(out['overdue_rows']) == 2
