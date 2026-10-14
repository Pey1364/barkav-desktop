"""Contractor contracts store.

Kept in its own JSON file beside the project's other UI state rather than in
the financial SQLite database.  Contractor contracts are new ground and the
ledger's schema is live production data; a separate file can be added,
reshaped and removed without touching it.

The reference titles come from the project's price catalogue - the same
"فایل مرجع" the specification points at - so a contract title matches a
budget line and its rows can be pre-filled from it.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

CONTRACT_STATUSES = ('فعال', 'خاتمه‌یافته')
OTHER_TITLE = 'سایر'

# The price catalogue's اجرت/اجرا category - what the مدیریت پروژه tab shows
# under قیمت when 'دستمزد/اجرا' is picked.  Contract titles come from there.
LABOUR_CATEGORY = 'LABOR'

# دسته‌بندی: which of the three price-catalogue tabs a contract's own title
# comes from.  A contract used to mean پیمانکار (labour) only; مصالح and
# خدمات contracts read the same way, just against a different tab of the
# same reference file - the same three names dashboard_stage18.COST_GROUPS
# asks a هزینه ساخت transaction for.
COST_GROUPS = ('مصالح', 'پیمانکار', 'خدمات')
PRICE_CATEGORY_BY_GROUP = {'مصالح': 'MATERIAL', 'پیمانکار': 'LABOR', 'خدمات': 'SERVICE'}

# Section 3, window 3: who supplies what. Contractor is the default.
SUPPLY_ROLES = ('پیمانکار', 'کارفرما')
SUPPLY_FIELDS = (
    # No 'تأمین دستمزد': the wage is what the contract itself is for, so
    # asking who supplies it had no answer other than the contract.
    ('food_supply', 'تأمین غذا'),
    ('tools_supply', 'تأمین وسیله'),
    ('consumables_supply', 'تأمین لوازم مصرفی'),
    ('lodging_supply', 'تأمین محل اقامت'),
)

# Section 3, window 4: five rows to a wizard page; more rows add pages.
ROWS_PER_PAGE = 5


def _project_dir() -> Path:
    raw = os.getenv('STAGE4_DB_PATH') or 'data/stage4_test.sqlite3'
    path = Path(raw)
    if not path.is_absolute():
        path = Path(__file__).resolve().parent / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.parent


def store_path() -> Path:
    return _project_dir() / 'contractor_contracts_18_7.json'


def _blank() -> dict[str, Any]:
    return {'contracts': []}


def load_contracts() -> list[dict[str, Any]]:
    path = store_path()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError, json.JSONDecodeError):
        return []
    contracts = data.get('contracts')
    return list(contracts) if isinstance(contracts, list) else []


def save_contracts(contracts: list[dict[str, Any]]) -> None:
    path = store_path()
    payload = dict(_blank())
    payload['contracts'] = list(contracts)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                         encoding='utf-8')
    temporary.replace(path)


def upsert_contract(record: dict[str, Any]) -> dict[str, Any]:
    """Insert or replace one contract, returning the stored copy."""

    record = dict(record)
    if not record.get('contract_id'):
        record['contract_id'] = uuid.uuid4().hex[:12].upper()
    contracts = load_contracts()
    for index, existing in enumerate(contracts):
        if existing.get('contract_id') == record['contract_id']:
            contracts[index] = record
            break
    else:
        contracts.append(record)
    save_contracts(contracts)
    return record


def delete_contract(contract_id: str) -> None:
    delete_contracts([contract_id])


def delete_contracts(contract_ids: list[str]) -> int:
    """Remove selected contractor contracts in one atomic store update."""

    selected = {str(contract_id) for contract_id in contract_ids if str(contract_id)}
    if not selected:
        return 0
    contracts = load_contracts()
    if any(contract.get('payments') for contract in contracts if str(contract.get('contract_id') or '') in selected):
        raise ValueError('پیش از حذف قرارداد، رسیدهای واریزی باید تعیین تکلیف شوند.')
    kept = [contract for contract in contracts
            if str(contract.get('contract_id') or '') not in selected]
    removed = len(contracts) - len(kept)
    if removed:
        save_contracts(kept)
    return removed


def get_contract(contract_id: str) -> dict[str, Any] | None:
    for contract in load_contracts():
        if contract.get('contract_id') == str(contract_id):
            return contract
    return None


_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')


def amount_of(value: Any) -> int:
    """An amount however it was typed: Persian digits, grouped, or blank.

    The entry boxes separate thousands as you type and show Persian digits,
    so what is stored is what was on screen. Reading it back has to undo both
    or every contract reports a balance of zero.
    """

    raw = str(value or '0').translate(_DIGITS)
    for separator in (',', '\u066c', '\u2009', ' '):
        raw = raw.replace(separator, '')
    try:
        return int(round(float(raw or 0)))
    except (TypeError, ValueError):
        return 0


def quantity_of(value: Any) -> float:
    """A row quantity however it was typed - same digits/grouping as
    amount_of, but not rounded to an int; a کارکرد can be fractional."""

    raw = str(value or '0').translate(_DIGITS)
    for separator in (',', '٬', ' ', ' '):
        raw = raw.replace(separator, '')
    try:
        return float(raw or 0)
    except (TypeError, ValueError):
        return 0.0


def paid_total(contract: dict[str, Any]) -> int:
    return sum(amount_of(payment.get('amount'))
               for payment in contract.get('payments') or [])


def balance(contract: dict[str, Any]) -> int:
    """Positive means still owed to the contractor; negative means overpaid."""

    return amount_of(contract.get('total_amount')) - paid_total(contract)


def reference_titles(rich=None, cost_group: str = 'پیمانکار') -> list[str]:
    """Contract titles offered by the project's reference price catalogue.

    Which tab of the catalogue - مصالح, پیمانکار or خدمات - follows the
    contract's own دسته‌بندی, the same three-way split a هزینه ساخت
    transaction asks for. A پیمانکار contract still reads only اجرت/اجرا
    lines, as it always did.

    ``سایر`` leads the list and is the default: the specification wants a
    manual title available for work the reference file does not cover.
    """

    titles: list[str] = []
    for row in _catalogue_prices(rich, cost_group):
        description = str(row.get('description') or '').strip()
        if description and description not in titles:
            titles.append(description)
    return [OTHER_TITLE, *titles]


def reference_row(rich, description: str, cost_group: str = 'پیمانکار') -> dict[str, Any]:
    """The estimate line behind one title, used to pre-fill a contract row."""

    if not description:
        return {}
    for row in _catalogue_prices(rich, cost_group):
        if str(row.get('description') or '').strip() == str(description).strip():
            return dict(row)
    return {}


def _catalogue_prices(rich, cost_group: str) -> list[dict[str, Any]]:
    if rich is None:
        return []
    category = PRICE_CATEGORY_BY_GROUP.get(cost_group, LABOUR_CATEGORY)
    try:
        return list(rich.list_prices(category=category, visible_only=True))
    except Exception:
        return []


# ---------------------------------------------------------------------------
# صورت‌وضعیت - one JSON file beside the contracts one, for the same reason:
# new ground, kept clear of the ledger's own schema.
# ---------------------------------------------------------------------------

def statements_path() -> Path:
    return _project_dir() / 'contractor_statements_18_7.json'


def load_statements() -> list[dict[str, Any]]:
    path = statements_path()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError, json.JSONDecodeError):
        return []
    statements = data.get('statements')
    return list(statements) if isinstance(statements, list) else []


def save_statements(statements: list[dict[str, Any]]) -> None:
    path = statements_path()
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps({'statements': list(statements)}, ensure_ascii=False, indent=2),
                         encoding='utf-8')
    temporary.replace(path)


def upsert_statement(record: dict[str, Any]) -> dict[str, Any]:
    """Insert or replace one صورت‌وضعیت, returning the stored copy."""

    record = dict(record)
    if not record.get('statement_id'):
        record['statement_id'] = uuid.uuid4().hex[:12].upper()
    statements = load_statements()
    for index, existing in enumerate(statements):
        if existing.get('statement_id') == record['statement_id']:
            statements[index] = record
            break
    else:
        statements.append(record)
    save_statements(statements)
    return record


def delete_statement(statement_id: str) -> None:
    save_statements([s for s in load_statements()
                     if s.get('statement_id') != str(statement_id)])


def get_statement(statement_id: str) -> dict[str, Any] | None:
    for statement in load_statements():
        if statement.get('statement_id') == str(statement_id):
            return statement
    return None


def statements_for_contract(contract_id: str) -> list[dict[str, Any]]:
    """A contract's own صورت‌وضعیت history, oldest first - what مبلغ صورت‌وضعیت
    تجمعی adds up.
    """

    own = [s for s in load_statements() if s.get('contract_id') == str(contract_id)]
    # تاریخ صورت‌وضعیت may be stored in Persian or ASCII digits depending on
    # when it was saved - sorting the raw string would put every ASCII-digit
    # date before every Persian-digit one (their code points compare lower),
    # scrambling "oldest first" for a mix of old and freshly-saved records.
    return sorted(own, key=lambda s: str(s.get('statement_date') or '').translate(_DIGITS))


def statement_rows_total(rows: list[dict[str, Any]]) -> int:
    return sum(amount_of(row.get('line_total')) for row in rows or [])


def statement_amount(statement: dict[str, Any]) -> int:
    """مبلغ صورت‌وضعیت: what the rows this period cover, plus پاداش, minus جریمه."""

    return (statement_rows_total(statement.get('rows') or [])
           + amount_of(statement.get('bonus_amount'))
           - amount_of(statement.get('penalty_amount')))


def cumulative_statement_amount(contract_id: str, upto_statement_id: str | None = None) -> int:
    """مبلغ صورت‌وضعیت تجمعی: every صورت‌وضعیت on this contract up to and
    including the one named, oldest first."""

    total = 0
    for statement in statements_for_contract(contract_id):
        total += statement_amount(statement)
        if upto_statement_id and statement.get('statement_id') == upto_statement_id:
            break
    return total


def previous_statement_row_totals(contract_id: str, description: str,
                                   *, before_statement_id: str | None = None) -> tuple[float, int]:
    """کارکرد کل / مبلغ کارکرد تجمیعی از صورت‌وضعیت ای که بلافاصله پیش از این
    یکی آمده و ردیفی با یک شرح یکسان دارد - صورت‌وضعیت شماره ۲ و به
    بعد این را با مقدار/مبلغ خود این دوره جمع می‌کنند. صورت‌وضعیت شماره ۱
    (هیچ چیزی پیش از آن نیست) صفر می‌خواند - دقیقاً همان قاعده‌ای که یک ردیف
    تازه از این قرارداد خود را می خواند.

    اگر صورت‌وضعیت قبلی هنوز این دو ستون را ذخیره نکرده بود (از پیش از این
    ویژگی)، مقدار/مبلغ دورهٔ خودش را جایگزین می‌خواند - برای یک
    صورت‌وضعیت تنها و تنها قبل از این ویژگی، تجمیعیش همان دورهٔ خودش بود.
    """

    statements = statements_for_contract(contract_id)
    if before_statement_id:
        ids = [s.get('statement_id') for s in statements]
        try:
            statements = statements[:ids.index(before_statement_id)]
        except ValueError:
            pass
    if not statements:
        return 0.0, 0
    previous = statements[-1]
    wanted = description.strip()
    for row in previous.get('rows') or []:
        if str(row.get('description') or '').strip() != wanted:
            continue
        quantity = row.get('cumulative_quantity')
        amount = row.get('cumulative_amount')
        return (
            quantity_of(quantity) if quantity not in (None, '') else quantity_of(row.get('worked_quantity')),
            amount_of(amount) if amount not in (None, '') else amount_of(row.get('line_total')),
        )
    return 0.0, 0


# ---------------------------------------------------------------------------
# آرشیو - a پیمانکار's own rated profile, not any one contract's.  Kept by
# family_name + national_id, the same identity CONTRACTOR_FIELDS already
# asks a contract for, so a contract does not have to name a profile that
# does not exist yet.
# ---------------------------------------------------------------------------

def archive_path() -> Path:
    return _project_dir() / 'contractor_archive_18_7.json'


def load_profiles() -> list[dict[str, Any]]:
    path = archive_path()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError, json.JSONDecodeError):
        return []
    profiles = data.get('profiles')
    return list(profiles) if isinstance(profiles, list) else []


def save_profiles(profiles: list[dict[str, Any]]) -> None:
    path = archive_path()
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps({'profiles': list(profiles)}, ensure_ascii=False, indent=2),
                         encoding='utf-8')
    temporary.replace(path)


def upsert_profile(record: dict[str, Any]) -> dict[str, Any]:
    """Insert or replace one contractor's رده‌بندی profile."""

    record = dict(record)
    if not record.get('profile_id'):
        record['profile_id'] = uuid.uuid4().hex[:12].upper()
    profiles = load_profiles()
    for index, existing in enumerate(profiles):
        if existing.get('profile_id') == record['profile_id']:
            profiles[index] = record
            break
    else:
        profiles.append(record)
    save_profiles(profiles)
    return record


def delete_profile(profile_id: str) -> None:
    save_profiles([p for p in load_profiles() if p.get('profile_id') != str(profile_id)])


def get_profile(profile_id: str) -> dict[str, Any] | None:
    for profile in load_profiles():
        if profile.get('profile_id') == str(profile_id):
            return profile
    return None


def _normalize_person_name(name: Any) -> str:
    """Same طرف‌حساب, however their name was typed - the key آرشیو's own
    auto-sync deduplicates by."""

    text = str(name or '').strip().replace('ي', 'ی').replace('ك', 'ک').replace('‌', ' ')
    return ' '.join(text.split())


# دسته‌بندی یک تراکنش هزینه‌ساخت از قبل هست - cost_group همان انتخابی است
# که عملگر یا هوش مصنوعی موقع ثبت هزینه انتخاب کرده (COST_GROUPS بالا)،
# نیازی به یک طبقه‌بند هوش مصنوعی تازه نیست.
ARCHIVE_CATEGORY_BY_COST_GROUP = {'مصالح': 'تامین‌کننده مصالح', 'خدمات': 'خدماتی'}


def sync_archive_from_sources() -> int:
    """آرشیو را از قراردادها (پیمانکار), تراکنش‌های تأییدشدهٔ هزینهٔ ساخت
    (تامین‌کننده مصالح/خدماتی، بر اساس دسته‌بندی خودشان) و عوامل پروژه
    (خدماتی) پر می‌کند.

    یک نام تکراری هرگز ردیف دوم نمی‌سازد - اگر پیش از این ثبت شده باشد،
    فقط فیلدهای ساختاری خالی‌اش (دسته‌بندی/تلفن/آدرس/فعالیت/نوع پرداخت) پر
    می‌شوند؛ امتیاز، ضریب هر معیار و رتبه‌بندی دستی یک نفر هرگز از اینجا
    دست نمی‌خورد. همه چیز در حافظه ساخته و فقط یک‌بار ذخیره می‌شود - نه یک
    خواندن/نوشتن جداگانهٔ فایل به‌ازای هر طرف حساب.

    Returns چند ردیف آرشیو ساخته یا تکمیل شد.
    """

    profiles = load_profiles()
    by_name = {_normalize_person_name(p.get('family_name')): p for p in profiles}
    touched = 0

    def merge(name: Any, *, category: str, phone: str = '', address: str = '',
             activity: str = '', payment_type: str = '') -> None:
        nonlocal touched
        key = _normalize_person_name(name)
        if not key:
            return
        existing = by_name.get(key)
        if existing is None:
            record = {
                'family_name': str(name).strip(), 'category': category, 'phone': phone,
                'address': address, 'activity': activity, 'payment_type': payment_type,
                'source': 'auto',
            }
            profiles.append(record)
            by_name[key] = record
            touched += 1
            return
        changed = False
        for field, value in (('category', category), ('phone', phone), ('address', address),
                             ('activity', activity), ('payment_type', payment_type)):
            if value and not str(existing.get(field) or '').strip():
                existing[field] = value
                changed = True
        if changed:
            touched += 1

    # ۱) پیمانکار - از خود قراردادها.
    for contract in load_contracts():
        name = contract.get('family_name')
        if str(name or '').strip():
            merge(name, category='پیمانکار', phone=str(contract.get('phone') or ''),
                 activity=str(contract.get('title') or ''))

    # ۲) تامین‌کننده مصالح / خدماتی - از تراکنش‌های تأییدشدهٔ هزینهٔ ساخت.
    # لایهٔ قدیمی‌تر دشبورد اختیاری است - نبودش نباید این تب را بترکاند،
    # فقط یعنی بخش تراکنش‌ها این‌بار همگام نمی‌شود.
    try:
        from dashboard_stage18 import APPROVAL
        for row in APPROVAL.list_reviews(limit=3000):
            if row.get('status') != 'APPROVED':
                continue
            payload = row.get('payload') or {}
            category = ARCHIVE_CATEGORY_BY_COST_GROUP.get(str(payload.get('cost_group') or '').strip())
            if category is None:
                continue
            name = payload.get('receiver_name') or payload.get('issuer_name')
            if not str(name or '').strip():
                continue
            payment_type = 'چکی' if str(payload.get('v18_subtype') or '').strip() == 'چک' else 'نقدی'
            merge(name, category=category, payment_type=payment_type)
    except Exception:
        pass

    # ۳) عوامل پروژه (مجری/ناظر/طراح) - خدماتی.
    try:
        from v18_store import load_profile as load_project_profile
        team = (load_project_profile() or {}).get('team') or {}
        for role_key, role_label in (('executor', 'مجری'), ('supervisor', 'ناظر'), ('designer', 'طراح')):
            info = team.get(role_key) or {}
            name = info.get('name')
            if str(name or '').strip():
                merge(name, category='خدماتی', activity=role_label, phone=str(info.get('phone') or ''))
    except Exception:
        pass

    if touched:
        save_profiles(profiles)
    return touched
