"""Shared construction/land accounting rules; displayed budgets stay unchanged."""
import re


def is_land_phase(stage='', plan_ref='', category=''):
    table = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
    stage = str(stage or '').translate(table).replace('ي', 'ی').replace('ك', 'ک').strip()
    ref = str(plan_ref or '').translate(table).strip()
    return (str(category or '').upper() in {'LAND', 'LAND_PURCHASE', 'LAND_PURCHASE_PAYMENT'}
            or 'خرید زمین' in stage or bool(re.match(r'^0?1(?:\s*[—–:\-]|$)', stage))
            or bool(re.match(r'^0?1(?:[-.]|$)', ref)))


def manager_fee(base):
    return max(0, int(base or 0)) // 10


def construction_with_manager(base):
    return int(base or 0) + manager_fee(base)
