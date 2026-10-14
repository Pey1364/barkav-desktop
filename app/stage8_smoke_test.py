from pathlib import Path
from tempfile import TemporaryDirectory

from dashboard_service import DashboardService
from finance_db import FinanceDB
from telegram_stage3_workflow import TelegramStage3Workflow


def main():
    with TemporaryDirectory() as td:
        db = FinanceDB(Path(td) / 'stage8.sqlite3')
        svc = DashboardService(db)
        flow = TelegramStage3Workflow(db)
        payload = {
            'detected_type':'EXPENSE','document_type':'TEXT','amount':100_000_000,
            'invoice_amount':100_000_000,'final_amount':100_000_000,'discount_amount':0,
            'paid_amount':100_000_000,'payment_state':'PAID','description':'بتن',
            'expense_category':'مصالح','payment_method':'BANK_TRANSFER','is_cheque':False,
            'manager_fee_eligible':True,'confidence':.99,
        }
        r = flow.receive_message(
            chat_id=-1001234567890,message_id=8001,raw_text='#تست 100 میلیون بتن پرداخت کردم',
            content_type='TEXT',message_date='1405/05/19 12:30',analysis=payload,
        )
        flow.approve_and_post(r.pending_id)
        svc.edit_posting(r.pending_id, {'amount':120_000_000,'final_amount':120_000_000})
        rec = svc.record_reconciliation(bank_balance=-118_000_000, shamsi_date='1405/05/19', notes='smoke')
        o = svc.overview()
        assert o.cash_balance == -120_000_000
        assert o.construction_cost == 120_000_000
        assert o.manager_fee_accrued == 12_000_000
        assert rec['difference'] == 2_000_000
        assert db.health_check()['sqlite_integrity'] == 'ok'
        print('STAGE 8 SMOKE TEST: OK')
        print(f'cash={o.cash_balance:,}')
        print(f'construction={o.construction_cost:,}')
        print(f'manager_fee={o.manager_fee_accrued:,}')
        print(f'bank_difference={rec["difference"]:,}')


if __name__ == '__main__':
    main()
