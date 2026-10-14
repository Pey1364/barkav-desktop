"""Shared transaction-title classification for table views and filters."""
from data_entry_rules187 import LAND_TITLE

MANAGER_TITLE = 'حقوق مدیر پروژه'

TRANSACTION_TITLES = ('هزینه ساخت', 'ورودی', 'خروجی', 'یادداشت', LAND_TITLE, MANAGER_TITLE)


def transaction_title(row, payload=None):
    payload = payload or {}
    category = str(row.get('category') or payload.get('expense_category') or '').upper()
    phase = str(payload.get('construction_stage') or row.get('construction_stage') or row.get('phase_name') or '')
    if category == 'CONTRACTOR_FEE':
        return MANAGER_TITLE
    if category in {'LAND', 'LAND_PURCHASE', 'LAND_PURCHASE_PAYMENT'}:
        return LAND_TITLE
    if category.startswith('LOAN_INSTALLMENT') or category == 'LOAN_PAYMENT':
        return 'خروجی'
    for source in (payload, row):
        for key in ('v18_title', 'transaction_title', '_ui_title187'):
            value = str(source.get(key) or '').strip()
            if value in TRANSACTION_TITLES:
                return LAND_TITLE if value == 'هزینه ساخت' and LAND_TITLE in phase else value
    if LAND_TITLE in phase:
        return LAND_TITLE
    detected = str(payload.get('detected_type') or row.get('detected_type') or '').upper()
    if row.get('document_id') or row.get('document_type') or detected in {'INFO', 'DOCUMENT', 'NOTE'}:
        return 'یادداشت'
    if row.get('expense_id') or row.get('cheque_id') or detected in {'EXPENSE', 'CHEQUE'}:
        return 'هزینه ساخت'
    if row.get('loan_id') or str(row.get('direction') or '').upper() == 'IN' or detected == 'INCOME':
        return 'ورودی'
    return 'خروجی'


def normalize_manager_salary(payload):
    result = dict(payload)
    result.update(v18_title=MANAGER_TITLE, v18_subtype='نقدی',
                  transaction_title=MANAGER_TITLE, transaction_subtype='نقدی', detected_type='OUTFLOW',
                  is_cheque=False, expense_category='CONTRACTOR_FEE')
    for key in ('construction_stage', 'activity_name', 'plan_ref', 'cost_group',
                'contract_id', 'phase_id', 'activity_id', 'main_phase', 'sub_phase', 'is_guarantee'):
        result.pop(key, None)
    return result
