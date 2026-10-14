from __future__ import annotations
import os
import tempfile
import pytest
from datetime import date
from pathlib import Path

os.environ.setdefault('TELEGRAM_BOT_TOKEN','v18-test-token')
os.environ.setdefault('GEMINI_API_KEY','v18-test-key')
os.environ.setdefault('ADMIN_USER_ID','1')
os.environ.setdefault('STAGE4_SHEETS_ENABLED','false')

from finance_db import FinanceDB
from budget_rich_v163 import RichBudgetService
from phase04_v18 import apply_phase04_rules_v18


def test_schema_13_has_cheque_settlement_mode():
    with tempfile.TemporaryDirectory() as td:
        db=FinanceDB(Path(td)/'x.sqlite3')
        assert db.health_check()['schema_version'] == 13
        with db.read() as con:
            cols={r[1] for r in con.execute('PRAGMA table_info(cheques)').fetchall()}
        assert 'settlement_mode' in cols


def test_returned_settled_cheque_is_financially_closed_by_transfer():
    with tempfile.TemporaryDirectory() as td:
        db=FinanceDB(Path(td)/'x.sqlite3')
        today=date.today().isoformat()
        cid=db.create_cheque(amount=3_000_000,issue_date=today,due_date=today,receiver_name='فروشنده',description='تست عودت')
        tx=db.settle_returned_cheque(cid,settled_date=today)
        ch=db.get_cheque(cid)
        assert ch['status']=='CASHED'
        assert ch['settlement_mode']=='RETURNED_SETTLED'
        with db.read() as con:
            t=dict(con.execute('SELECT * FROM transactions WHERE transaction_id=?',(tx,)).fetchone())
        assert t['direction']=='OUT'
        assert t['category']=='EXPENSE_PAYMENT_TRANSFER'
        assert db.snapshot().cash_balance == -3_000_000


def test_guarantee_cheque_cannot_use_returned_settlement_path():
    with tempfile.TemporaryDirectory() as td:
        db=FinanceDB(Path(td)/'x.sqlite3');today=date.today().isoformat()
        cid=db.create_cheque(amount=1_000_000,issue_date=today,due_date=today,is_guarantee=True)
        try:
            db.settle_returned_cheque(cid,settled_date=today)
        except ValueError:
            pass
        else:
            raise AssertionError('guarantee cheque must not create financial settlement')


def test_phase04_rules_defer_to_a_workbook_that_states_its_own_rows():
    """The rule stands down when the workbook already says what it used to.

    It was written for a workbook that listed the five supervision booklets
    without their VAT, so it summed them into one line and folded each 10% tax
    row into the rate above it. The rebuilt reference workbook lists every one
    of those rows and numbers them, and applying the rule on top turned its
    thirty-four phase-04 lines back into nineteen - the screens stopped
    matching the file they are read from.
    """

    base=Path(__file__).resolve().parents[1]
    if not (base/'phase_budget_current.xlsx').exists():
        pytest.skip('phase_budget_current.xlsx is private project data and is not shipped in the public repository')
    with tempfile.TemporaryDirectory() as td:
        tdp=Path(td);db=FinanceDB(tdp/'x.sqlite3')
        import shutil
        shutil.copy2(base/'phase_budget_current.xlsx',tdp/'phase_budget_current.xlsx')
        rich=RichBudgetService(db,tdp)
        numbered=[x for x in rich.list_phase_items(4) if x.get('plan_ref')]
        assert numbered, 'fixture workbook should number its own rows'
        before=len(rich.list_phase_items(4))

        result=apply_phase04_rules_v18(rich)
        assert result.get('changed') is False
        assert result.get('reason')=='workbook-states-phase-04-itself'
        assert len(rich.list_phase_items(4))==before
        # Each tax line is still its own row, at its own rate.
        assert any(str(x['description']).startswith('مالیات 10٪')
                   for x in rich.list_phase_items(4))


def test_phase04_rules_still_apply_to_a_workbook_without_row_numbers():
    """An older workbook does not state them, so the rule still does."""

    base=Path(__file__).resolve().parents[1]
    if not (base/'phase_budget_current.xlsx').exists():
        pytest.skip('phase_budget_current.xlsx is private project data and is not shipped in the public repository')
    with tempfile.TemporaryDirectory() as td:
        tdp=Path(td);db=FinanceDB(tdp/'x.sqlite3')
        import shutil
        shutil.copy2(base/'phase_budget_current.xlsx',tdp/'phase_budget_current.xlsx')
        rich=RichBudgetService(db,tdp)
        # Stand in for a workbook that carries no numbering of its own.
        with rich.db.tx() as con:
            con.execute("UPDATE rich_phase_items SET plan_ref=''")

        result=apply_phase04_rules_v18(rich)
        assert result.get('changed') and result.get('main_count')==5
        target=next(x for x in rich.list_prices(visible_only=False)
                    if x.get('description')=='حق‌الزحمه نظارت‌های اصلی')
        # The five booklet rates total 441,436; with VAT, 485,580.
        assert int(target['estimate_rate'])==485_580
        active=[x for x in rich.list_phase_items(4)
                if x.get('description')=='حق‌الزحمه نظارت‌های اصلی']
        assert len(active)==1


def test_rich_history_supports_five_undo_and_redo_steps():
    """Repeated toolbar clicks must walk the full recent history."""
    with tempfile.TemporaryDirectory() as td:
        tdp=Path(td); db=FinanceDB(tdp/'x.sqlite3')
        rich=RichBudgetService(db,tdp)
        stamp='2026-01-01T00:00:00'
        with db.tx() as con:
            con.execute(
                """INSERT INTO rich_price_items(
                    price_id,code,description,category,unit,estimate_rate,
                    actual_rate,forecast_rate,status,source,visible,aggregate,
                    group_key,active,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                ('PRICE-UNDO','','test row','SERVICE','',0,0,0,
                 '','',1,0,'',1,stamp,stamp),
            )

        def history_counts():
            with db.read() as con:
                total, undone=con.execute(
                    'SELECT COUNT(*), COALESCE(SUM(undone),0) FROM rich_change_history'
                ).fetchone()
            return int(total-undone), int(undone)

        for value in range(1,6):
            rich.save_price_rates('PRICE-UNDO',value,value,value)
        assert history_counts()==(5,0)

        for _ in range(5):
            assert rich.undo_last()
        assert history_counts()==(0,5)
        assert rich.get_price('PRICE-UNDO')['forecast_rate']==0
        assert rich.undo_last()
        assert history_counts()==(0,5)

        for _ in range(5):
            assert rich.redo_last()
        assert history_counts()==(5,0)
        assert rich.get_price('PRICE-UNDO')['forecast_rate']==5
        assert rich.redo_last()
        assert history_counts()==(5,0)
