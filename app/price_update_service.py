"""DB layer for the «بروزرسانی قیمت» (monthly price-escalation) module.

Deliberately isolated from ``budget_rich_v163.py``: it owns its own tables
(``price_catalog_items``, ``price_parameters``, ``price_snapshots``,
``price_snapshot_items``, ``price_calc_rules``) inside the same per-project
FinanceDB file, but never alters ``rich_price_items``'s schema or the rows
other tabs manage. The one place the two meet is :meth:`sync_forecast_to_rich`,
which does a narrow, value-only ``UPDATE ... SET forecast_rate=?`` so those
other tabs pick up a new run's prices without knowing this module exists.

Every project already has its own SQLite file (see ``project_registry.py``),
so this service needs no project_id column of its own to be per-project: it
is handed the same ``FinanceDB``/``base_dir`` pair the active project's
``RichBudgetService`` already uses.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import price_calc_engine as calc
from finance_db import FinanceDB, _id, _now
from budget_rich_v163 import stable as _rich_stable
from xlsx_simple import list_sheet_names, read_sheet
from project_management_rules187 import (
    MANAGEMENT_RULES, MANAGEMENT_RULE_HEADING, MANAGEMENT_RULE_SECTION,
)

_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')

CATALOG_TYPES = {'MATERIAL': 'مصالح', 'CONTRACTOR': 'پیمانکار', 'SERVICE': 'خدمات', 'LAND': 'خرید زمین'}
CATALOG_SHEET_NAMES = {'قیمت مصالح': 'MATERIAL', 'قیمت پیمانکار': 'CONTRACTOR',
                       'قیمت خدمات': 'SERVICE', 'قیمت زمین': 'LAND'}

# Default parameters every project starts with; a project's own workbook
# import overwrites the *values*, never adds/removes keys the engine depends on.
DEFAULT_PARAMETERS: tuple[tuple[str, str], ...] = (
    ('usd', 'نرخ دلار آزاد'),
    ('copper', 'قیمت مس کاتد'),
    ('wage_annual_growth', 'نرخ افزایش سالانه حداقل حقوق'),
    ('months_elapsed', 'ماه‌های سپری‌شده از مبنای برآورد'),
)

#: «پارامترها» sheet labels -> (parameter key, which of its values). Matched
#: as a normalized substring, so the sheet's own date notes in parentheses
#: («نرخ دلار آزاد - مبنا (فروردین ۱۴۰۵)») do not have to be kept verbatim.
REFERENCE_PARAMETER_LABELS: tuple[tuple[str, str, str], ...] = (
    ('نرخ دلار آزاد - مبنا', 'usd', 'base'),
    ('نرخ دلار آزاد - جاری', 'usd', 'current'),
    ('قیمت مس کاتد - مبنا', 'copper', 'base'),
    ('قیمت مس کاتد - جاری', 'copper', 'current'),
    ('نرخ افزایش سالانه حداقل حقوق', 'wage_annual_growth', 'both'),
    ('ماه‌های سپری‌شده از مبنای برآورد', 'months_elapsed', 'both'),
)

#: Reference workbook sheets beyond the price catalogs.
RULES_SHEET_NAME = 'قوانین محاسبه بروز'
REVIEW_SHEET_NAME = 'لیست بررسی مجدد'
PARAMETERS_SHEET_NAME = 'پارامترها'

#: Rule topics under «■ بخش N» in the rules sheet -> the catalog they govern.
#: Sections ۱ and ۵ are general (all three catalogs): stored as ``ALL``.
RULE_SECTION_CATALOGS = {'1': 'ALL', '2': 'MATERIAL', '3': 'CONTRACTOR', '4': 'SERVICE', '5': 'ALL'}

_CELL_REF_RE = re.compile(r"(?:'([^']+)'!)?\$?H\$?(\d+)")
_RESEARCHED_RE = re.compile(r'IFERROR\(\s*([0-9]+(?:\.[0-9]+)?)\s*/\s*D\d+')
_FIXED_RATIO_RE = re.compile(r'^=IF\(N\(\s*([0-9]+(?:\.[0-9]+)?)\s*\)\s*>\s*1')
_DUCT_RE = re.compile(r'([0-9.]+)\s*\*\s*پارامترها!\$?B\$?14\s*\+\s*([0-9.]+)\s*\*\s*پارامترها!\$?B\$?9')


def _norm(s: Any) -> str:
    return re.sub(r'\s+', ' ', str(s or '').translate(_DIGITS).replace('ي', 'ی').replace('ك', 'ک')
                  .replace('‌', ' ').strip()).lower()


def _stable(prefix: str, *parts: Any) -> str:
    raw = '|'.join(_norm(x) for x in parts).encode('utf-8')
    return f"{prefix}-{hashlib.sha1(raw).hexdigest()[:14].upper()}"


def _as_int(v: Any) -> int:
    try:
        return max(0, int(round(float(v or 0))))
    except Exception:
        return 0


def _as_float(v: Any) -> float:
    try:
        return float(v or 0)
    except Exception:
        return 0.0


def _number_or_none(v: Any) -> float | None:
    """A real number from a workbook cell, or ``None`` for '-', blanks and text."""

    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).translate(_DIGITS).replace(',', '').strip())
    except ValueError:
        return None


def normalize_phase_codes(raw: Any) -> str:
    """«07، 09» / «7,9» / «07 09» -> «07,09».

    The reference workbook separates phases with the Persian comma and a
    space; everything downstream (the cascade filter, run scoping, the
    phase-average pools) splits on a plain ',' and would otherwise treat the
    whole «07، 09» string as one unknown phase.
    """

    codes = []
    for part in re.split(r'[,،;\s]+', str(raw or '').translate(_DIGITS)):
        part = part.strip()
        if part.isdigit():
            code = f'{int(part):02d}'
            if code not in codes:
                codes.append(code)
    return ','.join(codes)


def _is_reference_rule(rule: dict[str, Any]) -> bool:
    try:
        params = json.loads(rule.get('params_json') or '{}')
    except (TypeError, ValueError):
        return False
    return isinstance(params, dict) and bool(params.get('reference'))


def _ratio_of(item: dict[str, Any]) -> float:
    return (item['forecast_rate'] / item['estimate_rate']) if item.get('estimate_rate') else 1.0


@dataclass
class RunResult:
    snapshot_id: str
    run_at: str
    item_count: int
    recalculated_count: int
    review_count: int
    estimate_date_shamsi: str = ''


class PriceUpdateService:
    def __init__(self, db: FinanceDB, base_dir: str | Path):
        self.db = db
        self.base_dir = Path(base_dir)
        self._migrate()

    # ------------------------------------------------------------- schema

    def _migrate(self) -> None:
        with self.db.tx() as con:
            con.executescript('''
            CREATE TABLE IF NOT EXISTS price_catalog_items(
              price_id TEXT PRIMARY KEY,
              code TEXT NOT NULL DEFAULT '',
              description TEXT NOT NULL,
              catalog_type TEXT NOT NULL,
              unit TEXT NOT NULL DEFAULT '',
              phase_codes TEXT NOT NULL DEFAULT '',
              group_key TEXT NOT NULL DEFAULT '',
              estimate_rate INTEGER NOT NULL DEFAULT 0,
              previous_rate INTEGER NOT NULL DEFAULT 0,
              forecast_rate INTEGER NOT NULL DEFAULT 0,
              actual_rate INTEGER NOT NULL DEFAULT 0,
              calc_method TEXT NOT NULL DEFAULT '',
              calc_params_json TEXT NOT NULL DEFAULT '{}',
              suggested_method TEXT NOT NULL DEFAULT '',
              executed_method TEXT NOT NULL DEFAULT '',
              brand TEXT NOT NULL DEFAULT '',
              needs_review INTEGER NOT NULL DEFAULT 0,
              review_reason TEXT NOT NULL DEFAULT '',
              ai_prompt TEXT NOT NULL DEFAULT '',
              rich_price_id TEXT,
              active INTEGER NOT NULL DEFAULT 1,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_price_catalog_type ON price_catalog_items(catalog_type,active);
            CREATE INDEX IF NOT EXISTS idx_price_catalog_group ON price_catalog_items(group_key);

            CREATE TABLE IF NOT EXISTS price_parameters(
              key TEXT PRIMARY KEY,
              label TEXT NOT NULL DEFAULT '',
              base_value REAL NOT NULL DEFAULT 0,
              previous_value REAL NOT NULL DEFAULT 0,
              current_value REAL NOT NULL DEFAULT 0,
              source TEXT NOT NULL DEFAULT '',
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS price_snapshots(
              snapshot_id TEXT PRIMARY KEY,
              estimate_date_shamsi TEXT NOT NULL,
              trigger_kind TEXT NOT NULL DEFAULT 'manual',
              parameters_json TEXT NOT NULL DEFAULT '{}',
              totals_json TEXT NOT NULL DEFAULT '{}',
              run_at TEXT NOT NULL,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS price_snapshot_items(
              snapshot_id TEXT NOT NULL REFERENCES price_snapshots(snapshot_id),
              price_id TEXT NOT NULL REFERENCES price_catalog_items(price_id),
              estimate_rate INTEGER NOT NULL DEFAULT 0,
              previous_rate INTEGER NOT NULL DEFAULT 0,
              computed_rate INTEGER NOT NULL DEFAULT 0,
              ratio REAL NOT NULL DEFAULT 1,
              method_used TEXT NOT NULL DEFAULT '',
              needs_review INTEGER NOT NULL DEFAULT 0,
              review_reason TEXT NOT NULL DEFAULT '',
              PRIMARY KEY(snapshot_id,price_id)
            );

            CREATE TABLE IF NOT EXISTS price_calc_rules(
              rule_id TEXT PRIMARY KEY,
              catalog_type TEXT NOT NULL,
              description TEXT NOT NULL,
              affected_phase_codes TEXT NOT NULL DEFAULT '',
              params_json TEXT NOT NULL DEFAULT '{}',
              active INTEGER NOT NULL DEFAULT 1,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            ''')
            for key, label in DEFAULT_PARAMETERS:
                con.execute(
                    'INSERT OR IGNORE INTO price_parameters(key,label,base_value,previous_value,'
                    'current_value,source,updated_at) VALUES(?,?,0,0,0,?,?)',
                    (key, label, '', _now()))

    # -------------------------------------------------------- catalog items

    def list_catalog_items(self, catalog_type: str | None = None,
                            phase_code: str | None = None, *,
                            active_only: bool = True) -> list[dict[str, Any]]:
        where = []
        args: list[Any] = []
        if active_only:
            where.append('active=1')
        if catalog_type:
            where.append('catalog_type=?')
            args.append(catalog_type)
        if phase_code:
            where.append("(',' || phase_codes || ',') LIKE ?")
            args.append(f'%,{phase_code},%')
        clause = f"WHERE {' AND '.join(where)}" if where else ''
        with self.db.read() as con:
            rows = con.execute(
                f'SELECT * FROM price_catalog_items {clause} ORDER BY catalog_type,description', args
            ).fetchall()
        return [dict(r) for r in rows]

    def available_phase_codes(self, catalog_type: str | None = None) -> list[str]:
        """Phase codes that active items in ``catalog_type`` actually use.

        This is what makes the tab's دسته‌بندی -> فاز filter a real cascade
        instead of two independent lists: the second box offers only phases
        the first box's rows can actually be in, so no combination can select
        an empty table. ``phase_codes`` holds a comma-joined list (a shared
        item may sit in two phases), so it is split here rather than trusted
        as a single value.
        """

        where = ['active=1', "phase_codes<>''"]
        args: list[Any] = []
        if catalog_type:
            where.append('catalog_type=?')
            args.append(catalog_type)
        with self.db.read() as con:
            rows = con.execute(
                f"SELECT DISTINCT phase_codes FROM price_catalog_items WHERE {' AND '.join(where)}",
                args).fetchall()
        codes = {code.strip() for row in rows for code in str(row[0] or '').split(',') if code.strip()}
        return sorted(codes)

    def get_catalog_item(self, price_id: str) -> dict[str, Any] | None:
        with self.db.read() as con:
            row = con.execute('SELECT * FROM price_catalog_items WHERE price_id=?', (price_id,)).fetchone()
        return dict(row) if row else None

    def upsert_catalog_item(self, price_id: str | None, **fields: Any) -> str:
        """Create (``price_id`` is ``None``) or update one catalog row.

        ``fields`` may set any column except ``price_id``/timestamps. Unknown
        keys are rejected rather than silently ignored, since a typo here
        would otherwise write nothing and look like it worked.
        """

        allowed = {
            'code', 'description', 'catalog_type', 'unit', 'phase_codes', 'group_key',
            'estimate_rate', 'previous_rate', 'forecast_rate', 'actual_rate',
            'calc_method', 'calc_params_json', 'suggested_method', 'executed_method',
            'brand', 'needs_review', 'review_reason', 'ai_prompt', 'rich_price_id', 'active',
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f'Unknown catalog field(s): {sorted(unknown)}')
        now = _now()
        if price_id is None:
            price_id = _id('PRICEU')
            # ASSUMPTION (operator confirmed this reading only for the general
            # fallback case, not explicitly for قیمت specifically -- flagged
            # here so it is easy to correct if wrong): a brand-new row with no
            # computed بروز yet starts with بروز = اولیه, never zero/blank,
            # exactly like «مقدار اولیه = مقدار بروز» for quantities. It is
            # overwritten the moment a real run_update() computes it.
            estimate_rate = _as_int(fields.get('estimate_rate', 0))
            forecast_rate = _as_int(fields['forecast_rate']) if 'forecast_rate' in fields else estimate_rate
            with self.db.tx() as con:
                con.execute(
                    'INSERT INTO price_catalog_items(price_id,description,catalog_type,estimate_rate,'
                    'forecast_rate,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
                    (price_id, fields.get('description', ''), fields.get('catalog_type', 'MATERIAL'),
                     estimate_rate, forecast_rate, now, now))
        if fields:
            sets = ','.join(f'{k}=?' for k in fields)
            with self.db.tx() as con:
                con.execute(f'UPDATE price_catalog_items SET {sets},updated_at=? WHERE price_id=?',
                            (*fields.values(), now, price_id))
        return price_id

    def copy_catalog_item(self, price_id: str) -> str:
        row = self.get_catalog_item(price_id)
        if not row:
            raise ValueError(f'Unknown price_id {price_id!r}')
        fields = {k: v for k, v in row.items()
                  if k not in ('price_id', 'created_at', 'updated_at')}
        fields['description'] = f"{fields['description']} (رونوشت)"
        return self.upsert_catalog_item(None, **fields)

    def soft_delete_catalog_item(self, price_id: str) -> None:
        with self.db.tx() as con:
            con.execute('UPDATE price_catalog_items SET active=0,updated_at=? WHERE price_id=?',
                        (_now(), price_id))

    # -------------------------------------------------------------- parameters

    def list_parameters(self) -> list[dict[str, Any]]:
        with self.db.read() as con:
            rows = con.execute('SELECT * FROM price_parameters ORDER BY key').fetchall()
        return [dict(r) for r in rows]

    def get_parameter(self, key: str) -> dict[str, Any] | None:
        with self.db.read() as con:
            row = con.execute('SELECT * FROM price_parameters WHERE key=?', (key,)).fetchone()
        return dict(row) if row else None

    def save_parameter(self, key: str, *, base_value: float | None = None,
                        previous_value: float | None = None,
                        current_value: float | None = None, source: str = '') -> None:
        """Update one macro parameter.

        Per the operator's three-field parameter screen (اولیه/قبلی/بروز):
        ``previous_value`` defaults to whatever ``current_value`` was *before*
        this call, not to the existing previous_value -- each save shifts the
        old بروز into قبلی automatically, exactly like a new month replacing
        last month's number, unless the caller explicitly overrides it.
        """

        existing = self.get_parameter(key)
        if existing is None:
            raise ValueError(f'Unknown parameter {key!r}; add it to DEFAULT_PARAMETERS first')
        base = existing['base_value'] if base_value is None else base_value
        if previous_value is not None:
            previous = previous_value
        elif current_value is not None:
            previous = existing['current_value']
        else:
            previous = existing['previous_value']
        current = existing['current_value'] if current_value is None else current_value
        with self.db.tx() as con:
            con.execute(
                'UPDATE price_parameters SET base_value=?,previous_value=?,current_value=?,'
                'source=?,updated_at=? WHERE key=?',
                (base, previous, current, source or existing['source'], _now(), key))

    #: Optional parameters the engine reads when they exist: a project-wide
    #: شاخص تعدیل / تورم for weighted-index rows that carry none of their own.
    OPTIONAL_PARAMETERS = {'adjustment_index': 'شاخص تعدیل فهرست‌بها (ضریب)',
                           'inflation_rate': 'تورم (ضریب)'}

    def add_parameter(self, label: str, *, key: str | None = None, base_value: float = 0,
                       previous_value: float = 0, current_value: float = 0) -> str:
        """A new macro parameter row (an optional engine one, or the operator's own).

        Rows only -- ``price_parameters`` already has every column this needs.
        """

        key = key or _id('PARAM')
        if self.get_parameter(key) is not None:
            raise ValueError(f'Parameter {key!r} already exists')
        with self.db.tx() as con:
            con.execute(
                'INSERT INTO price_parameters(key,label,base_value,previous_value,current_value,source,'
                'updated_at) VALUES(?,?,?,?,?,?,?)',
                (key, label, base_value, previous_value or current_value, current_value, 'wizard', _now()))
        return key

    def delete_parameter(self, key: str) -> None:
        """Remove an added parameter; the four the engine is built on cannot be removed."""

        if key in dict(DEFAULT_PARAMETERS):
            raise ValueError('این پارامتر پایه‌ی محاسبه است و حذف‌شدنی نیست')
        with self.db.tx() as con:
            con.execute('DELETE FROM price_parameters WHERE key=?', (key,))

    def parameter_values(self) -> dict[str, float]:
        """``{key: current_value}`` -- what the calc engine actually consumes."""

        return {p['key']: p['current_value'] for p in self.list_parameters()}

    # -------------------------------------------------------------- calc rules

    def list_calc_rules(self, catalog_type: str | None = None) -> list[dict[str, Any]]:
        """Active rules, most recently edited first.

        ``updated_at`` is second-precision, so two rules saved inside the same
        second tie on it and SQLite is free to return them in either order --
        which made both the list's order and «اعمال قوانین»'s "newest rule
        wins" behaviour arbitrary between refreshes. ``rule_id`` breaks the tie
        so the order is at least stable and reproducible.
        """

        # A rule stored as ``ALL`` (the reference workbook's general sections)
        # governs every catalog, so it belongs under each one's filter too.
        where = 'WHERE active=1' + (" AND catalog_type IN (?,'ALL')" if catalog_type else '')
        args = (catalog_type,) if catalog_type else ()
        with self.db.read() as con:
            rows = con.execute(
                f'SELECT * FROM price_calc_rules {where} ORDER BY updated_at DESC, rule_id DESC',
                args).fetchall()
        return [dict(r) for r in rows]

    def upsert_calc_rule(self, rule_id: str | None, *, catalog_type: str, description: str,
                          affected_phase_codes: str = '', params_json: str = '{}') -> str:
        now = _now()
        if rule_id is None:
            rule_id = _id('PRULE')
            with self.db.tx() as con:
                con.execute(
                    'INSERT INTO price_calc_rules(rule_id,catalog_type,description,affected_phase_codes,'
                    'params_json,active,created_at,updated_at) VALUES(?,?,?,?,?,1,?,?)',
                    (rule_id, catalog_type, description, affected_phase_codes, params_json, now, now))
        else:
            with self.db.tx() as con:
                con.execute(
                    'UPDATE price_calc_rules SET catalog_type=?,description=?,affected_phase_codes=?,'
                    'params_json=?,updated_at=? WHERE rule_id=?',
                    (catalog_type, description, affected_phase_codes, params_json, now, rule_id))
        return rule_id

    def delete_calc_rule(self, rule_id: str) -> None:
        with self.db.tx() as con:
            con.execute('UPDATE price_calc_rules SET active=0,updated_at=? WHERE rule_id=?', (_now(), rule_id))

    def apply_calc_rules(self, rule_ids: list[str] | None = None) -> dict[str, int]:
        """«اعمال قوانین» -- write each rule's method/params onto the rows it covers.

        A rule is a *classification*, not a calculation: it says «هر قلم این
        دسته‌بندی در این فازها با این روش و این ضرایب محاسبه شود». Until a rule
        (or a manual ویرایش جزئیات) has given a row a ``calc_method``,
        :meth:`run_update` deliberately leaves that row's price untouched --
        so this method is the step that actually makes a run do anything for
        freshly imported rows.

        The rule's ``params_json`` may carry a ``method`` key (one of
        ``price_calc_engine``'s METHOD_* values); its remaining keys are
        *merged* into each row's existing ``calc_params_json`` rather than
        replacing it, so a rule that only sets وزن‌ها cannot wipe out a row's
        hand-entered قیمت‌های وب.

        Rules are applied oldest-first, so when two overlap the more recently
        edited one has the final say -- the same way the operator would expect
        their latest correction to win.

        Returns counts for the UI to report: how many rules ran, how many rows
        were touched, and how many rules carried no ``method`` (those only
        merged params and left the rows still unclassified -- a silent no-op
        from the user's point of view unless it is reported).
        """

        rules = self.list_calc_rules()
        if rule_ids is not None:
            wanted = set(rule_ids)
            rules = [r for r in rules if r['rule_id'] in wanted]
        # list_calc_rules() is newest-first; apply in the opposite order so the
        # newest rule is the last writer on any row two rules both match.
        rules = list(reversed(rules))
        touched: set[str] = set()
        rules_without_method = 0
        now = _now()
        for rule in rules:
            try:
                params = json.loads(rule['params_json'] or '{}')
            except (TypeError, ValueError):
                params = {}
            if not isinstance(params, dict):
                params = {}
            if params.get('reference'):
                # A rule imported from the workbook's «قوانین محاسبه بروز» sheet
                # is the written rule itself, kept for reading and editing - the
                # per-row classification it describes was imported onto the rows
                # directly. Applying it would merge its prose into every row.
                continue
            method = str(params.get('method') or '').strip()
            # A rule's own bookkeeping (its text, section, order) is not a row option.
            merge = {k: v for k, v in params.items()
                     if k not in {'method', 'reference', 'section', 'order', 'rule_text'}}
            if not method:
                rules_without_method += 1
            wanted_phases = {c.strip() for c in str(rule['affected_phase_codes'] or '').split(',') if c.strip()}
            rule_catalog = None if rule['catalog_type'] == 'ALL' else rule['catalog_type']
            items = self.list_catalog_items(catalog_type=rule_catalog, active_only=True)
            for item in items:
                if wanted_phases and not (wanted_phases & set(self._phase_codes(item))):
                    continue
                try:
                    item_params = json.loads(item['calc_params_json'] or '{}')
                except (TypeError, ValueError):
                    item_params = {}
                if not isinstance(item_params, dict):
                    item_params = {}
                item_params.update(merge)
                sets = ['calc_params_json=?']
                args: list[Any] = [json.dumps(item_params, ensure_ascii=False)]
                if method:
                    sets += ['calc_method=?', 'suggested_method=?']
                    args += [method, method]
                with self.db.tx() as con:
                    con.execute(
                        f"UPDATE price_catalog_items SET {','.join(sets)},updated_at=? WHERE price_id=?",
                        (*args, now, item['price_id']))
                touched.add(item['price_id'])
        return {'rules': sum(1 for r in rules if not _is_reference_rule(r)), 'items': len(touched),
                'rules_without_method': rules_without_method}

    # ------------------------------------------------------------------ run

    def growth_context(self) -> dict[str, float]:
        """The three live macro ratios every row's calculation draws on.

        ``wage`` is پارامترها!B9 of the reference workbook: the annual
        minimum-wage rise compounded over the months elapsed since the
        estimate's base month (rule ۲۰ - compounded, never linear). A rate
        entered as a percentage (60) is read as the fraction it means (0.60).
        """

        params = self.parameter_values()
        annual = params.get('wage_annual_growth', 0)
        if annual > 1:
            annual = annual / 100.0
        return {
            'usd': calc.growth_ratio(params.get('usd', 0), self._param_base('usd')),
            'copper': calc.growth_ratio(params.get('copper', 0), self._param_base('copper')),
            'wage': calc.wage_growth_rate(annual, params.get('months_elapsed', 0)),
            'adjustment_index': params.get('adjustment_index') or 1.0,
            'inflation_rate': params.get('inflation_rate') or 1.0,
        }

    def run_update(self, *, trigger: str = 'manual', estimate_date_shamsi: str = '',
                    catalog_type: str | None = None, phase_code: str | None = None,
                    price_id: str | None = None) -> RunResult:
        """Recompute every catalog row with a structured ``calc_method`` and archive the run.

        ``price_id`` narrows the run to that one قلم (the wizard's «قلم» box):
        only it is written and archived, but its ratio is worked out against
        the whole active catalog -- a lone phase-average row has no siblings
        to average otherwise, and would silently drop to the wage floor.

        A row with no ``calc_method`` yet (still «سایر» from a first import,
        not classified through «قوانین بروزرسانی» یا ویرایش دستی) is left
        untouched -- its last forecast_rate carries over unchanged. This is
        deliberate: guessing a method for an unclassified row risks a wrong
        number more than leaving it as it was; خروجی هرگز نباید صفر یا خالی
        باشد, and "unchanged" is never zero.

        ``catalog_type``/``phase_code`` narrow the run to one دسته‌بندی/فاز, the
        scope the wizard's «دامنه اجرا» step collects. A scoped run is a real
        subset run, not a filtered view of a full one: rows outside the scope
        are neither recomputed nor written into this snapshot, and -- because
        the fallback ladder averages ratios of *sibling* rows -- the phase
        pools are built from the scoped rows only. A row that names specific
        other rows (``peer_refs``) still reads them when they sit outside the
        scope, at their current stored ratio.

        The order of resolution mirrors the reference workbook's formulas:
          1. every row with a ratio of its own (قیمت وب، قیمت تحقیق‌شده،
             شاخص/تعرفه، رشد دلار) -- a contractor row is floored at the
             wage growth here (rule ۲۳);
          2. rows that copy/average named rows («هم‌تراز با ...») once the
             rows they name are resolved;
          3. rows priced by phase average, and rows whose own ratio came out
             at or below 1 (never applied - rule «ممنوعیت ضریب کاهشی»): the
             positive average of that phase's web rows, then the contractor
             rows of that phase, then the wage growth;
          4. step 2 again for peers that were waiting on step 3.
        """

        ctx = self.growth_context()
        # Kept apart from the loop variables below, one of which is also called price_id.
        only_item = price_id
        if only_item:
            items = self.list_catalog_items(active_only=True)
        else:
            items = self.list_catalog_items(catalog_type=catalog_type, phase_code=phase_code,
                                            active_only=True)
        all_items = (items if only_item or not (catalog_type or phase_code)
                     else self.list_catalog_items(active_only=True))
        by_ref = {(r['catalog_type'], _norm(r['code'])): r for r in all_items if r['code']}
        in_scope = {r['price_id'] for r in items}
        params_of = {r['price_id']: self._params_of(r) for r in items}

        resolved: dict[str, calc.RatioResult] = {}
        web_pool: dict[str, list[float]] = {}
        pending_fallback: dict[str, str] = {}   # price_id -> review reason ('' = by design)
        peers: list[dict[str, Any]] = []

        # Step 1 -- own ratios.
        for item in items:
            if not item['calc_method']:
                continue
            params = params_of[item['price_id']]
            if params.get('peer_refs'):
                peers.append(item)
                continue
            outcome = self._own_ratio(item, params, ctx)
            if isinstance(outcome, calc.RatioResult):
                resolved[item['price_id']] = outcome
                if outcome.method_used == calc.METHOD_WEB and params.get('web_prices') \
                        and calc.is_positive_ratio(outcome.ratio):
                    first = self._first_phase(item)
                    if first:
                        web_pool.setdefault(first, []).append(outcome.ratio)
            else:
                pending_fallback[item['price_id']] = outcome or ''

        def resolve_peers() -> None:
            progress = True
            while progress:
                progress = False
                for item in peers:
                    if item['price_id'] in resolved or item['price_id'] in pending_fallback:
                        continue
                    ratios = []
                    waiting = False
                    for ref in params_of[item['price_id']]['peer_refs']:
                        catalog, _sep, code = str(ref).partition(':')
                        target = by_ref.get((catalog, _norm(code)))
                        if target is None or not target['active']:
                            continue
                        if target['price_id'] in resolved:
                            ratios.append(resolved[target['price_id']].ratio)
                        elif target['price_id'] in in_scope and target['calc_method']:
                            waiting = True
                            break
                        else:
                            ratios.append(_ratio_of(target))
                    if waiting:
                        continue
                    outcome = self._peer_ratio(item, params_of[item['price_id']], ratios, ctx)
                    if isinstance(outcome, calc.RatioResult):
                        resolved[item['price_id']] = outcome
                    else:
                        pending_fallback[item['price_id']] = outcome or ''
                    progress = True

        # Step 2 -- peers of rows resolved in step 1.
        resolve_peers()

        # Step 3 -- phase-average ladder.
        def contractor_phase_average(code: str) -> float | None:
            ratios = [resolved[r['price_id']].ratio for r in items
                      if r['catalog_type'] == 'CONTRACTOR' and r['price_id'] in resolved
                      and code in self._phase_codes(r)]
            if not ratios:
                return None
            average = sum(ratios) / len(ratios)
            return average if calc.is_positive_ratio(average) else None

        def fallback(item: dict[str, Any], reason: str) -> calc.RatioResult:
            params = params_of[item['price_id']]
            ratio = None
            if params.get('fallback') != 'wage':
                code = self._first_phase(item)
                ratio = calc.positive_average(web_pool.get(code, [])) if code else None
                if ratio is None and code:
                    ratio = contractor_phase_average(code)
            if ratio is None:
                ratio = ctx['wage']
            above, ceiling_reason = calc.flag_if_above_usd_growth(ratio, ctx['usd'])
            return calc.RatioResult(ratio, calc.METHOD_PHASE_AVERAGE, bool(reason) or above,
                                    reason or ceiling_reason)

        for item in items:
            price_id = item['price_id']
            if price_id in pending_fallback and price_id not in resolved:
                resolved[price_id] = fallback(item, pending_fallback[price_id])

        # Step 4 -- peers that were waiting on a phase-average row; anything
        # still unresolved (a reference loop) falls back like step 3.
        resolve_peers()
        for item in peers:
            if item['price_id'] not in resolved:
                resolved[item['price_id']] = fallback(item, '')

        if only_item:
            items = [item for item in items if item['price_id'] == only_item]
            resolved = {key: value for key, value in resolved.items() if key == only_item}
        now = _now()
        snapshot_id = _id('PSNAP')
        # The scope is archived with the run, not just used to pick rows: a
        # snapshot of 12 items means something different depending on whether
        # the operator ran the whole catalog or one فاز, and «سابقه بروزرسانی»
        # has no other way to tell the two apart later.
        totals = {'item_count': len(items), 'recalculated': len(resolved),
                  'needs_review': sum(1 for r in resolved.values() if r.needs_review),
                  'scope_catalog_type': catalog_type or '', 'scope_phase_code': phase_code or '',
                  'scope_price_id': only_item or ''}
        with self.db.tx() as con:
            con.execute(
                'INSERT INTO price_snapshots(snapshot_id,estimate_date_shamsi,trigger_kind,'
                'parameters_json,totals_json,run_at,created_at) VALUES(?,?,?,?,?,?,?)',
                (snapshot_id, estimate_date_shamsi, trigger,
                 json.dumps({**self.parameter_values(), **{f'growth_{k}': v for k, v in ctx.items()}},
                            ensure_ascii=False),
                 json.dumps(totals, ensure_ascii=False), now, now))
            for item in items:
                result = resolved.get(item['price_id'])
                computed_rate = item['forecast_rate']
                ratio = 1.0
                method_used = item['calc_method']
                needs_review = False
                review_reason = ''
                if result is not None:
                    computed_rate = _as_int(item['estimate_rate'] * result.ratio)
                    ratio = result.ratio
                    method_used = result.method_used
                    needs_review = result.needs_review
                    review_reason = result.review_reason
                con.execute(
                    'INSERT INTO price_snapshot_items(snapshot_id,price_id,estimate_rate,previous_rate,'
                    'computed_rate,ratio,method_used,needs_review,review_reason) VALUES(?,?,?,?,?,?,?,?,?)',
                    (snapshot_id, item['price_id'], item['estimate_rate'], item['forecast_rate'],
                     computed_rate, ratio, method_used, int(needs_review), review_reason))
                if result is not None:
                    con.execute(
                        'UPDATE price_catalog_items SET previous_rate=?,forecast_rate=?,executed_method=?,'
                        'needs_review=?,review_reason=?,updated_at=? WHERE price_id=?',
                        (item['forecast_rate'], computed_rate, method_used, int(needs_review),
                         review_reason, now, item['price_id']))
        return RunResult(snapshot_id, now, len(items), len(resolved), totals['needs_review'],
                          estimate_date_shamsi)

    def _param_base(self, key: str) -> float:
        p = self.get_parameter(key)
        return float(p['base_value']) if p else 0.0

    @staticmethod
    def _phase_codes(item: dict[str, Any]) -> list[str]:
        return [c.strip() for c in str(item.get('phase_codes') or '').split(',') if c.strip()]

    @classmethod
    def _first_phase(cls, item: dict[str, Any]) -> str:
        """قانون یکنواختی فاز: کلید فاز = فاز اول ستون «فازهای مورد استفاده»."""

        codes = cls._phase_codes(item)
        return codes[0] if codes else ''

    @staticmethod
    def _params_of(item: dict[str, Any]) -> dict[str, Any]:
        try:
            params = json.loads(item.get('calc_params_json') or '{}')
        except (TypeError, ValueError):
            return {}
        return params if isinstance(params, dict) else {}

    @staticmethod
    def _researched_ratio(item: dict[str, Any], params: dict[str, Any]) -> float | None:
        price = _number_or_none(params.get('researched_price'))
        if price and item['estimate_rate']:
            return price / item['estimate_rate']
        return None

    def _own_ratio(self, item: dict[str, Any], params: dict[str, Any],
                    ctx: dict[str, float]) -> calc.RatioResult | str | None:
        """A row's own result -- or why it has none and must take the fallback ladder.

        Returns a :class:`RatioResult` when the row's own ratio is usable, a
        non-empty review reason when it had one but it was rejected (at or
        below 1 -- a decreasing ratio is never applied), and ``None`` when the
        row has no ratio of its own by design (میانگین فاز).

        The USD-growth ceiling (rule ۲۲) only ever flags, never caps.
        """

        method = item['calc_method']
        usd = ctx['usd']
        rejected = 'ضریب کاهشی/خنثی بود — میانگین ضرایب مثبت فاز جایگزین شد'
        own: float | None = None
        if method == calc.METHOD_WEB:
            own = self._researched_ratio(item, params)
            web_prices = [p for p in (_number_or_none(x) for x in params.get('web_prices', [])) if p]
            if own is None and web_prices and item['estimate_rate']:
                computed, own = calc.material_web_ratio(
                    web_prices, item['estimate_rate'],
                    carry_rate=_as_float(params.get('carry_rate')), tax_rate=_as_float(params.get('tax_rate')),
                    regional_factor=_number_or_none(params.get('regional_factor')) or 1.0,
                    connection_factor=_number_or_none(params.get('connection_factor')) or 1.0,
                )
            if own is None:
                return None
        elif method == calc.METHOD_OTHER:
            index = params.get('index')
            if index in ('usd', 'copper', 'wage'):
                own = ctx[index]
            elif _number_or_none(params.get('reference_ratio')):
                own = _number_or_none(params.get('reference_ratio'))
            else:
                return None
        elif method == calc.METHOD_SERVICE_TARIFF:
            own = self._researched_ratio(item, params)
            if own is None and _number_or_none(params.get('reference_ratio')):
                own = _number_or_none(params.get('reference_ratio'))
            if own is None and 'annual_rate' in params:
                months = self.get_parameter('months_elapsed')
                months_elapsed = float(months['current_value']) if months else 0.0
                own = calc.service_tariff_ratio(
                    _as_float(params.get('annual_rate')), months_elapsed / 12.0,
                    regional_factor=_number_or_none(params.get('regional_factor')) or 1.0,
                    tax_rate=_as_float(params.get('tax_rate')),
                )
            if own is None:
                return None
            if not calc.is_positive_ratio(own):
                return 'ضریب کاهشی/خنثی بود — ضریب رشد دستمزد روزمزد جایگزین شد'
        elif method == calc.METHOD_WEIGHTED_INDEX:
            return self._contractor_ratio(item, params, ctx, [])
        else:
            # میانگین فاز / میانگین ردیف‌ها without named rows: no own ratio.
            return None
        if not calc.is_positive_ratio(own):
            return rejected
        needs_review, reason = calc.flag_if_above_usd_growth(own, usd)
        return calc.RatioResult(own, method, needs_review, reason)

    def _weighted_index(self, params: dict[str, Any], ctx: dict[str, float]) -> float | None:
        """شاخص ترکیبی وزنی from the row's own weights, or ``None`` if it has none.

        Reads both the four legacy keys (``wage_weight`` ...) and the seven
        per-component weights the جزئیات screen edits (``weight_wage`` ...).
        فولاد has no index of its own and moves with the dollar, which is how
        the workbook's «وزن دلار/فولاد» column already treats it; «سایر» is
        read as general inflation.
        """

        def weight(*keys: str) -> float:
            return sum(_as_float(params.get(k)) for k in keys)

        w_wage = weight('wage_weight', 'weight_wage')
        w_adjust = weight('adjustment_weight', 'weight_adjustment')
        w_inflation = weight('inflation_weight', 'weight_inflation')
        w_other = weight('weight_other')
        w_dollar = weight('weight_dollar', 'weight_steel')
        w_copper = weight('weight_copper')
        legacy_metal = weight('dollar_or_metal_weight')
        if legacy_metal:
            if params.get('metal') == 'copper':
                w_copper += legacy_metal
            else:
                w_dollar += legacy_metal
        if not any((w_wage, w_adjust, w_inflation, w_other, w_dollar, w_copper)):
            return None
        adjustment_index = _number_or_none(params.get('adjustment_index')) or ctx.get('adjustment_index', 1.0)
        inflation_rate = _number_or_none(params.get('inflation_rate')) or ctx.get('inflation_rate', 1.0)
        return (w_wage * ctx['wage'] + w_adjust * adjustment_index
                + (w_inflation + w_other) * inflation_rate
                + w_dollar * ctx['usd'] + w_copper * ctx['copper'])

    def _contractor_ratio(self, item: dict[str, Any], params: dict[str, Any],
                           ctx: dict[str, float], peer_ratios: list[float]) -> calc.RatioResult:
        """ضریب هر ردیف پیمانکار = بیشینهٔ(ضریب محاسباتی، نرخ رشد حداقل حقوق).

        The computed side is whichever of the row's own figures the workbook
        formula actually uses: a researched price ÷ اولیه, a named row's ratio,
        or the live weighted index (only when the row asks for it with
        ``index_mode='live'`` or carries the legacy weight keys -- the
        workbook's own «ضریب شاخص محاسباتی» column is informative, not part of
        its formula). Whenever the wage floor replaces the computed figure the
        row is flagged for review (rule ۲۳).
        """

        candidates = [r for r in (self._researched_ratio(item, params),) if r]
        candidates += [r for r in peer_ratios if r]
        live = params.get('index_mode') == 'live' or 'wage_weight' in params
        index = self._weighted_index(params, ctx) if live else None
        if index is not None:
            candidates.append(index)
        computed = max(candidates) if candidates else None
        floor = ctx['wage']
        if computed is not None and computed >= floor - calc.POSITIVE_EPS:
            needs_review, reason = calc.flag_if_above_usd_growth(computed, ctx['usd'])
            return calc.RatioResult(computed, calc.METHOD_WEIGHTED_INDEX, needs_review, reason)
        _above, ceiling_reason = calc.flag_if_above_usd_growth(floor, ctx['usd'])
        reason = ceiling_reason or 'ضریب محاسباتی زیر کف حداقل حقوق بود؛ نرخ رشد حداقل حقوق اعمال شد'
        return calc.RatioResult(floor, calc.METHOD_WEIGHTED_INDEX, True, reason)

    def _peer_ratio(self, item: dict[str, Any], params: dict[str, Any], ratios: list[float],
                     ctx: dict[str, float]) -> calc.RatioResult | str:
        """«هم‌تراز با ...» / «میانگین ضریب ...» -- the named rows' positive average."""

        if item['calc_method'] == calc.METHOD_WEIGHTED_INDEX:
            return self._contractor_ratio(item, params, ctx, ratios)
        average = calc.positive_average(ratios)
        if average is None:
            # Nothing positive to copy: the phase ladder, as the workbook's
            # IF(N(...)>1, ..., AB) does -- not a rejected own ratio, so no flag.
            return ''
        needs_review, reason = calc.flag_if_above_usd_growth(average, ctx['usd'])
        return calc.RatioResult(average, calc.METHOD_PEER_AVERAGE, needs_review, reason)

    # -------------------------------------------------------------- snapshots

    def list_snapshots(self) -> list[dict[str, Any]]:
        with self.db.read() as con:
            rows = con.execute('SELECT * FROM price_snapshots ORDER BY run_at DESC').fetchall()
        return [dict(r) for r in rows]

    def snapshot_items(self, snapshot_id: str) -> list[dict[str, Any]]:
        with self.db.read() as con:
            rows = con.execute(
                'SELECT si.*, ci.description, ci.catalog_type, ci.unit FROM price_snapshot_items si '
                'JOIN price_catalog_items ci ON ci.price_id=si.price_id WHERE si.snapshot_id=?',
                (snapshot_id,)).fetchall()
        return [dict(r) for r in rows]

    def needs_review_items(self) -> list[dict[str, Any]]:
        with self.db.read() as con:
            rows = con.execute(
                'SELECT * FROM price_catalog_items WHERE active=1 AND needs_review=1 ORDER BY catalog_type,description'
            ).fetchall()
        return [dict(r) for r in rows]

    # ---------------------------------------------------------- rich sync

    def sync_forecast_to_rich(self, rich_db: FinanceDB) -> int:
        """Write only the ``forecast_rate`` VALUE into rich_price_items, for matched rows.

        No schema change, no row insert/delete in ``rich_price_items`` --
        other tabs own that table's structure entirely. A catalog item with
        no ``rich_price_id`` link is skipped, not guessed at.
        """

        linked = [r for r in self.list_catalog_items(active_only=True) if r.get('rich_price_id')]
        if not linked:
            return 0
        now = _now()
        with rich_db.tx() as con:
            for item in linked:
                con.execute('UPDATE rich_price_items SET forecast_rate=?,updated_at=? WHERE price_id=?',
                            (item['forecast_rate'], now, item['rich_price_id']))
            self._sync_hidden_rich_copies(con, linked, now)
        return len(linked)

    @staticmethod
    def _sync_hidden_rich_copies(con, linked: list[dict[str, Any]], now: str) -> None:
        """Carry a price's بروز to the budget import's hidden per-line copies of it.

        The budget import prices every phase-16 installation line through its
        own hidden ``INSTALLATION_COMPONENT`` record (and a few formula lines
        through a hidden local one) rather than through the catalog price, and
        rolls the components up into visible «جمع کل» group rows. Updating only
        the catalog price would leave phase 16 -- and every plan/phase/summary
        figure built on it -- at the old بروز. Still value-only: forecast_rate
        on rows that already exist, nothing inserted, no column added.
        """

        try:
            hidden = con.execute(
                "SELECT price_id,description,category FROM rich_price_items "
                "WHERE active=1 AND visible=0 AND aggregate=0").fetchall()
        except Exception:
            return
        rich_category = {'MATERIAL': ('MATERIAL', 'INSTALLATION_COMPONENT'),
                         'CONTRACTOR': ('LABOR',), 'SERVICE': ('SERVICE',), 'LAND': ('LAND',)}
        by_description: dict[tuple[str, str], int] = {}
        for item in linked:
            for category in rich_category.get(item['catalog_type'], ()):
                by_description[(category, _norm(item['description']))] = item['forecast_rate']
        for row in hidden:
            forecast = by_description.get((row['category'], _norm(row['description'])))
            if forecast:
                con.execute('UPDATE rich_price_items SET forecast_rate=?,updated_at=? WHERE price_id=?',
                            (forecast, now, row['price_id']))
        PriceUpdateService.recompute_installation_groups(con, now)

    @staticmethod
    def recompute_installation_groups(con, now: str) -> None:
        """Each visible «لوازم تأسیسات ... — جمع کل» row's بروز = the sum of its lines' بروز.

        The budget import sets a group's بروز once, to its اولیه, and nothing
        recomputed it afterwards -- so the group row in «قیمت مصالح» showed no
        change even when every line under it had one. Quantities are the
        estimate's: «مقدار بروز» is by rule the same as «مقدار اولیه».
        """

        groups = con.execute(
            "SELECT price_id,group_key FROM rich_price_items "
            "WHERE active=1 AND aggregate=1 AND category='INSTALLATION_GROUP'").fetchall()
        for group in groups:
            total = con.execute(
                "SELECT SUM(pi.qty_estimate*pi.factor*p.forecast_rate) FROM rich_phase_items pi "
                "JOIN rich_price_items p ON p.price_id=pi.price_id "
                "WHERE pi.active=1 AND pi.phase_no=16 AND pi.section=? "
                "AND p.category='INSTALLATION_COMPONENT'", (group['group_key'],)).fetchone()[0]
            if total:
                con.execute('UPDATE rich_price_items SET forecast_rate=?,updated_at=? WHERE price_id=?',
                            (int(round(total)), now, group['price_id']))

    # ------------------------------------------------------- reference import

    #: rich_price_items.category -> catalog_type. LABOR has no catalog_type
    #: of its own (this module also supports the separate LAND catalog,
    #: matching CATALOG_TYPES above) so it maps to CONTRACTOR; both real
    #: installation categories (INSTALLATION_COMPONENT for an individual row,
    #: INSTALLATION_GROUP for an aggregate one - see budget_rich_v163.py) map
    #: to SERVICE for the same reason.
    RICH_CATEGORY_MAP = {
        'MATERIAL': 'MATERIAL',
        'LABOR': 'CONTRACTOR',
        'SERVICE': 'SERVICE',
        'LAND': 'LAND',
        'INSTALLATION_COMPONENT': 'SERVICE',
        'INSTALLATION_GROUP': 'SERVICE',
    }

    def import_from_rich_price_items(self) -> dict[str, int]:
        """Seed the catalog from this project's own existing rich_price_items.

        price_catalog_items starts empty for every project and the only way
        to put anything in it was a manual «افزودن» or an external reference
        workbook - so a project's real, already-priced items (entered months
        ago through the budget/estimate tabs, hundreds of rows on a real
        project) never reached this tab; «شروع براورد» had nothing to run
        against. Only real catalog rows are pulled in (``active=1``,
        ``visible=1``, ``aggregate=0`` - an aggregate row is a roll-up total,
        not something with its own escalatable price), and phase_codes is
        filled from rich_phase_items so the دسته‌بندی -> فاز cascade and the
        rule/phase scoping this module already has both work immediately.

        Idempotent: a row already imported (tracked by rich_price_id) is
        updated in place rather than duplicated, so re-running this after the
        project's price list changes is safe and expected, not a one-time
        migration.
        """

        now = _now()
        imported = updated = 0
        with self.db.tx() as con:
            existing_ids = {
                row[0] for row in con.execute(
                    'SELECT price_id FROM price_catalog_items').fetchall()
            }
            rows = con.execute(
                "SELECT price_id,code,description,category,unit,estimate_rate,forecast_rate,actual_rate "
                "FROM rich_price_items WHERE active=1 AND visible=1 AND aggregate=0"
            ).fetchall()
            for r in rows:
                phase_rows = con.execute(
                    'SELECT DISTINCT phase_no FROM rich_phase_items WHERE price_id=? AND active=1',
                    (r['price_id'],),
                ).fetchall()
                phase_codes = ','.join(f"{no:02d}" for no in sorted(p['phase_no'] for p in phase_rows))
                catalog_type = self.RICH_CATEGORY_MAP.get(str(r['category'] or '').upper(), 'MATERIAL')
                price_id = _stable('PRICER', r['price_id'])
                estimate_rate = _as_int(r['estimate_rate'])
                forecast_rate = (_as_int(r['forecast_rate']) if catalog_type == 'LAND'
                                 else _as_int(r['forecast_rate']) or estimate_rate)
                con.execute(
                    '''INSERT INTO price_catalog_items(price_id,code,description,catalog_type,unit,
                           phase_codes,estimate_rate,previous_rate,forecast_rate,actual_rate,
                           rich_price_id,active,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,0,?,1,?,?)
                       ON CONFLICT(price_id) DO UPDATE SET description=excluded.description,
                           unit=excluded.unit,phase_codes=excluded.phase_codes,active=1,
                           updated_at=excluded.updated_at''',
                    (price_id, r['code'] or '', r['description'], catalog_type, r['unit'] or '',
                     phase_codes, estimate_rate, estimate_rate, forecast_rate,
                     r['price_id'], now, now),
                )
                if catalog_type == 'LAND':
                    con.execute('UPDATE price_catalog_items SET actual_rate=? WHERE price_id=?',
                                (_as_int(r['actual_rate']), price_id))
                if price_id in existing_ids:
                    updated += 1
                else:
                    imported += 1
        return {'imported': imported, 'updated': updated, 'total_source_rows': len(rows)}

    def import_reference_workbook(self, path: str | Path, *,
                                   import_parameters: bool = True) -> dict[str, int]:
        """Seed/re-sync the catalog from a «قیمت بروز» reference workbook.

        Reads the catalog sheets (قیمت مصالح/پیمانکار/خدمات), optional
        «قیمت زمین» and, when present, «پارامترها», «قوانین محاسبه بروز» and «لیست بررسی مجدد».

        Every row's ``description``/``unit``/``phase_codes``/اولیه/بروز come
        from the sheet. Where the sheet's «ضریب رشد بروز» cell holds one of the
        workbook's own formulas, that formula also decides the row's روش
        محاسبه and the figures it needs (قیمت‌های وب، ضرایب حمل/مالیات/منطقه،
        وزن‌ها، قیمت تحقیق‌شده، ردیف‌های مرجع) -- so «جزئیات بروزرسانی» opens
        filled, and «شروع براورد» reproduces the workbook's own numbers. A row
        with no such formula (an app export, a hand-made sheet) keeps whatever
        روش and ضرایب the app already had for it: nothing is guessed.

        Matches an existing row by ``code`` first, then by ``description``,
        before falling back to a fresh stable id -- this is what makes the
        export -> edit in Excel -> re-import round trip update rows in place
        instead of duplicating every row the app itself created (those carry
        a random id, not the deterministic hash a first-ever import produces).
        A row the app seeded from the project's own price list keeps its link
        to it; a row that has none is linked when the matching project price
        exists, so «شروع براورد» can write its بروز back there.
        """

        path = Path(path)
        names = set(list_sheet_names(path))
        counts = {catalog: 0 for catalog in CATALOG_TYPES if catalog != 'LAND' or 'قیمت زمین' in names}
        now = _now()
        existing = {r['price_id']: r for r in self.list_catalog_items(active_only=True)}
        existing_by_code: dict[tuple[str, str], str] = {}
        existing_by_desc: dict[tuple[str, str], str] = {}
        for row in existing.values():
            if row['code']:
                existing_by_code[(row['catalog_type'], _norm(row['code']))] = row['price_id']
            existing_by_desc[(row['catalog_type'], _norm(row['description']))] = row['price_id']
        catalog = read_reference_catalog(path, names)
        review = read_review_list(path) if REVIEW_SHEET_NAME in names else {}
        rich_ids = self._rich_price_ids()
        with self.db.tx() as con:
            for catalog_type, rows in catalog.items():
                for ref in rows:
                    code, description = ref['code'], ref['description']
                    price_id = (
                        (existing_by_code.get((catalog_type, _norm(code))) if code else None)
                        or existing_by_desc.get((catalog_type, _norm(description)))
                        or _stable('PRICEU', catalog_type, code or description)
                    )
                    rich_category = 'LABOR' if catalog_type == 'CONTRACTOR' else catalog_type
                    # The budget import keys a price by its workbook row number, which
                    # its own reader may have kept as '12' or '12.0'.
                    rich_id = next((candidate for candidate in (
                        _rich_stable('PRICE', rich_category, key)
                        for key in ((code, f'{code}.0') if code else (description,)))
                        if candidate in rich_ids), None)
                    con.execute('''INSERT INTO price_catalog_items(price_id,code,description,catalog_type,
                        unit,phase_codes,estimate_rate,previous_rate,forecast_rate,rich_price_id,active,
                        created_at,updated_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?,1,?,?)
                        ON CONFLICT(price_id) DO UPDATE SET code=excluded.code,
                        description=excluded.description,unit=excluded.unit,
                        phase_codes=excluded.phase_codes,estimate_rate=excluded.estimate_rate,
                        forecast_rate=excluded.forecast_rate,
                        rich_price_id=COALESCE(price_catalog_items.rich_price_id,excluded.rich_price_id),
                        active=1,updated_at=excluded.updated_at''',
                        (price_id, code, description, catalog_type, ref['unit'], ref['phase_codes'],
                         ref['estimate_rate'], ref['estimate_rate'], ref['forecast_rate'],
                         rich_id, now, now))
                    if catalog_type == 'LAND' and ref['actual_rate'] is not None:
                        con.execute('UPDATE price_catalog_items SET actual_rate=? WHERE price_id=?',
                                    (ref['actual_rate'], price_id))
                    if ref['method']:
                        old_params = self._params_of(existing.get(price_id) or {})
                        params = {**old_params, **ref['params']}
                        flagged = review.get((catalog_type, ref['excel_row']))
                        con.execute(
                            'UPDATE price_catalog_items SET calc_method=?,suggested_method=?,'
                            'executed_method=?,calc_params_json=?,brand=?,ai_prompt=?,needs_review=?,'
                            'review_reason=? WHERE price_id=?',
                            (ref['method'], ref['method'], ref['method'],
                             json.dumps(params, ensure_ascii=False), ref['brand'], ref['ai_prompt'],
                             int(bool(flagged)), flagged or '', price_id))
                    counts[catalog_type] += 1
            if import_parameters and PARAMETERS_SHEET_NAME in names:
                self._import_parameters(con, path, now)
        if RULES_SHEET_NAME in names:
            self.import_reference_rules(path)
        return counts

    def import_reference_rules(self, path: str | Path) -> int:
        """«قوانین بروزرسانی» from the workbook's «قوانین محاسبه بروز» sheet.

        Each موضوع/قانون row becomes one rule, filed under the catalog its
        «■ بخش» heading names (sections ۱ and ۵ govern all three). They are
        the written rules - editable, exportable, readable in the rules
        window - marked ``reference`` so «اعمال قوانین» never merges their
        prose into rows. Idempotent: a rule is keyed by its section and
        topic, so re-importing the same (or an edited) workbook updates the
        text in place instead of adding a second copy.
        """

        rows = read_sheet(Path(path), name=RULES_SHEET_NAME)
        section = '1'
        now = _now()
        count = 0
        with self.db.tx() as con:
            for r in rows:
                topic = str(r[0] or '').strip() if r else ''
                text = str(r[1] or '').strip() if len(r) > 1 else ''
                if topic.startswith('■'):
                    match = re.search(r'بخش\s*(\S+)', topic.translate(_DIGITS))
                    section = match.group(1) if match else section
                    continue
                if not topic or not text or topic == 'موضوع':
                    continue
                catalog_type = RULE_SECTION_CATALOGS.get(section, 'ALL')
                rule_id = _stable('PRULEREF', section, topic)
                phases = normalize_phase_codes(' '.join(re.findall(r'فاز\s*([0-9۰-۹ /،,]+)', topic)))
                params = json.dumps({'reference': True, 'section': section, 'order': count,
                                     'rule_text': text},
                                    ensure_ascii=False)
                con.execute(
                    '''INSERT INTO price_calc_rules(rule_id,catalog_type,description,affected_phase_codes,
                       params_json,active,created_at,updated_at) VALUES(?,?,?,?,?,1,?,?)
                       ON CONFLICT(rule_id) DO UPDATE SET catalog_type=excluded.catalog_type,
                       description=excluded.description,affected_phase_codes=excluded.affected_phase_codes,
                       params_json=excluded.params_json,active=1,updated_at=excluded.updated_at''',
                    (rule_id, catalog_type, topic, phases, params, now, now))
                count += 1
        return count

    def _rich_price_ids(self) -> set[str]:
        """Active rich_price_items ids, or none when that table does not exist here."""

        try:
            with self.db.read() as con:
                return {row[0] for row in con.execute(
                    'SELECT price_id FROM rich_price_items WHERE active=1').fetchall()}
        except Exception:
            return set()

    def ensure_parameter_defaults(self, *, workbook: str | Path | None = None,
                                   settings: dict[str, Any] | None = None) -> list[str]:
        """Fill every still-empty (zero) parameter value from the workbook, then the app settings.

        Only a value that is still 0 is filled -- something the operator
        typed or fetched is never overwritten. The workbook's «پارامترها» is
        the first source (it is the file the estimate itself was built on);
        the app's own تنظیمات (``usd_rate_baseline``/``usd_rate_current``)
        cover the dollar when there is no workbook. قبلی defaults to بروز, so
        a first run compares against the same number rather than against 0.
        Returns the keys that changed.
        """

        found: dict[str, dict[str, float]] = {}
        if workbook:
            try:
                found = read_reference_parameters(Path(workbook))
            except Exception:
                found = {}
        settings = settings or {}
        usd_base = _as_float(settings.get('usd_rate_baseline'))
        usd_current = _as_float(settings.get('usd_rate_current'))
        if usd_base or usd_current:
            usd = found.setdefault('usd', {})
            usd.setdefault('base', usd_base or usd_current)
            usd.setdefault('current', usd_current or usd_base)
        changed = []
        for key, values in found.items():
            stored = self.get_parameter(key)
            if stored is None:
                continue
            base = stored['base_value'] or values.get('base', 0)
            current = stored['current_value'] or values.get('current', 0)
            previous = stored['previous_value'] or current
            if (base and current and values.get('current') and values.get('base') == base
                    and not 0.2 <= current / base <= 5):
                # A بروز in another unit than the workbook مبنا beside it (مس
                # fetched as دلار/تن against a تومان/کیلوگرم مبنا): a growth
                # ratio of 0.007 or 140 is a unit mix-up, never a real month,
                # and would wreck every row that uses it. The workbook's own
                # pair is taken together instead.
                current = values['current']
                previous = current
            if (base, current, previous) == (stored['base_value'], stored['current_value'],
                                              stored['previous_value']):
                continue
            self.save_parameter(key, base_value=base, previous_value=previous, current_value=current,
                                source=stored['source'] or 'reference_workbook')
            changed.append(key)
        return changed

    def latest_reference_workbook(self) -> Path | None:
        """The reference workbook this project's estimate was last imported from, if it still exists."""

        try:
            with self.db.read() as con:
                row = con.execute(
                    'SELECT source_file FROM rich_budget_imports ORDER BY created_at DESC LIMIT 1').fetchone()
        except Exception:
            return None
        path = Path(str(row[0] or '')) if row else None
        if path is None or not path.is_file():
            return None
        try:
            names = set(list_sheet_names(path))
        except Exception:
            return None
        return path if set(CATALOG_SHEET_NAMES) & names else None

    def has_classified_rows(self) -> bool:
        with self.db.read() as con:
            row = con.execute(
                "SELECT 1 FROM price_catalog_items WHERE active=1 AND calc_method<>'' LIMIT 1").fetchone()
        return row is not None

    # ------------------------------------------------------- reference export

    def export_reference_workbook(self, export_dir: str | Path | None = None, *,
                                   out_path: str | Path | None = None,
                                   catalog_type: str | None = None,
                                   phase_code: str | None = None) -> Path:
        """«اعمال تغییرات به فایل مرجع» -- write current catalog+parameters to a NEW xlsx.

        Always a new, timestamped file under ``base_dir/data/price_update_exports``
        -- never overwrites whatever the original reference file was, per the
        operator's explicit requirement. The catalog sheets, including «قیمت زمین», are written
        in the exact column layout :meth:`import_reference_workbook` reads, so
        the round trip (export -> edit in Excel -> re-import) works both ways.

        ``out_path`` writes to a filename the caller chose instead (what the
        tab's «خروجی -> Excel» does, after a save dialog). It is the caller's
        job to have confirmed an overwrite there -- the no-overwrite guarantee
        belongs to the automatic, unnamed export above, not to a path the user
        typed themselves.

        ``catalog_type``/``phase_code`` narrow which rows are written, so the
        export matches the filter the table is showing. A narrowed workbook is
        still a valid round trip: :meth:`import_reference_workbook` upserts by
        code/description, so re-importing it updates exactly those rows and
        leaves every row it omits alone.
        """

        import openpyxl

        if out_path is not None:
            out_path = Path(out_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            export_dir = Path(export_dir) if export_dir else self.base_dir / 'data' / 'price_update_exports'
            export_dir.mkdir(parents=True, exist_ok=True)
            timestamp = _now().replace(':', '-')
            # _now() is second-precision; two exports inside the same second would
            # otherwise collide on this filename and the second one would silently
            # overwrite the first -- exactly what "never overwrites" must not do.
            unique_suffix = _id('EXP').rsplit('-', 1)[-1]
            out_path = export_dir / f'قیمت بروز - نسخه {timestamp} {unique_suffix}.xlsx'

        workbook = openpyxl.Workbook()
        workbook.remove(workbook.active)
        header = ['ردیف', 'عنوان', 'واحد', 'برآورد اولیه', 'برآورد بروز', 'واقعی',
                  'فازهای مورد استفاده', 'ضریب رشد بروز', 'روش محاسبه بروز']
        sheet_names_by_type = {v: k for k, v in CATALOG_SHEET_NAMES.items()}
        for sheet_type, sheet_name in sheet_names_by_type.items():
            if catalog_type and sheet_type != catalog_type:
                continue
            sheet = workbook.create_sheet(sheet_name)
            sheet.append([f'کاتالوگ {sheet_name} (خروجی برنامه بارکاو -- بروزرسانی قیمت)'])
            sheet.append([])
            sheet.append(header)
            for row in self.list_catalog_items(catalog_type=sheet_type, phase_code=phase_code,
                                                active_only=True):
                ratio = (row['forecast_rate'] / row['estimate_rate']) if row['estimate_rate'] else 1.0
                sheet.append([
                    row['code'], row['description'], row['unit'], row['estimate_rate'],
                    row['forecast_rate'], row['actual_rate'] or None, row['phase_codes'],
                    round(ratio, 6), row['executed_method'] or row['calc_method'] or '',
                ])

        params_sheet = workbook.create_sheet('پارامترها')
        params_sheet.append(['کلید', 'مقدار'])
        param_labels = {
            'usd': ('نرخ دلار آزاد - مبنا', 'نرخ دلار آزاد - جاری'),
            'copper': ('قیمت مس کاتد - مبنا', 'قیمت مس کاتد - جاری'),
        }
        for param in self.list_parameters():
            if param['key'] in param_labels:
                base_label, current_label = param_labels[param['key']]
                params_sheet.append([base_label, param['base_value']])
                params_sheet.append([current_label, param['current_value']])
            else:
                params_sheet.append([param['label'] or param['key'], param['current_value']])

        rules_sheet = workbook.create_sheet(RULES_SHEET_NAME)
        rules_sheet.append(['قوانین محاسبه بروز و مدیریت پروژه'])
        rules_sheet.append(['قوانین مدیریت پروژه مرجع متنی‌اند؛ اعمال قوانین قیمت، مبالغ یا پیشرفت را تغییر نمی‌دهد.'])
        rules_sheet.append(['موضوع', 'قانون (پرامپت)'])
        reference_rules = {}
        for rule in self.list_calc_rules(catalog_type=catalog_type):
            if not _is_reference_rule(rule):
                continue
            params = json.loads(rule['params_json'])
            section = str(params.get('section') or '1')
            reference_rules[(section, rule['description'])] = (
                int(params.get('order') or 0), params.get('rule_text') or '')
        for order, (topic, text) in enumerate(MANAGEMENT_RULES):
            reference_rules.setdefault((MANAGEMENT_RULE_SECTION, topic), (order, text))
        section_now = None
        for (section, topic), (_order, text) in sorted(
                reference_rules.items(), key=lambda entry: (entry[0][0], entry[1][0], entry[0][1])):
            if section != section_now:
                heading = (MANAGEMENT_RULE_HEADING if section == MANAGEMENT_RULE_SECTION
                           else f'■ بخش {section} — قوانین مرجع')
                rules_sheet.append([heading])
                section_now = section
            rules_sheet.append([topic, text])
        from openpyxl.styles import Alignment
        rules_sheet.column_dimensions['A'].width = 48
        rules_sheet.column_dimensions['B'].width = 120
        for row in rules_sheet:
            for cell in row:
                cell.alignment = Alignment(horizontal='right', vertical='top', wrap_text=True)
        for sheet in workbook:
            sheet.sheet_view.rightToLeft = True
        workbook.save(out_path)
        return out_path

    def _import_parameters(self, con, path: Path, now: str) -> None:
        """Overwrite the parameters with the workbook's «پارامترها» -- an explicit import is the reference.

        The بروز the workbook replaces moves into قبلی, like any new month's figure.
        """

        for key, values in read_reference_parameters(path).items():
            existing = self.get_parameter(key)
            if existing is None:
                continue
            base_value = values.get('base', existing['base_value'])
            current_value = values.get('current', existing['current_value'])
            previous_value = existing['current_value'] or current_value
            con.execute('UPDATE price_parameters SET base_value=?,previous_value=?,'
                        'current_value=?,source=?,updated_at=? WHERE key=?',
                        (base_value, previous_value, current_value, 'reference_workbook', now, key))


# ---------------------------------------------------------------- workbook reading
#
# The reference workbook («2مرجع مدیریت پروژه - قیمت بروز.xlsx») carries each
# row's روش محاسبه only as the formula in its «ضریب رشد بروز» (H) cell, so the
# catalog sheets are read twice: cached values for the figures, formulas to
# tell the methods apart. The formulas fall into a handful of shapes, one per
# method, and are recognized by shape rather than by fixed row numbers.

_H_REF_RE = re.compile(r"(?:'([^']+)'!)?(?<![A-Z$])\$?H\$?(\d+)")


def _cell_text(v: Any) -> str:
    if v is None:
        return ''
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    text = str(v).strip()
    return '' if text == '-' else text


def _header_map(rows: list[tuple]) -> tuple[int, dict[str, int]]:
    """(index of the header row, {normalized header: column}); first header wins."""

    for index, row in enumerate(rows[:6]):
        if row and _norm(row[0]) == _norm('ردیف'):
            columns: dict[str, int] = {}
            for col, value in enumerate(row):
                key = _norm(value)
                if key and key not in columns:
                    columns[key] = col
            return index, columns
    return 0, {}


def _load_sheet_rows(path: Path, names: list[str]) -> dict[str, tuple[list[tuple], list[tuple]]]:
    """{sheet: (values rows, formula rows)} for ``names``, via openpyxl's read-only mode."""

    import openpyxl

    out: dict[str, tuple[list[tuple], list[tuple]]] = {}
    values_book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    formula_book = openpyxl.load_workbook(path, read_only=True, data_only=False)
    try:
        for name in names:
            if name not in values_book.sheetnames:
                continue
            values = [tuple(r) for r in values_book[name].iter_rows(values_only=True)]
            formulas = [tuple(r) for r in formula_book[name].iter_rows(values_only=True)]
            out[name] = (values, formulas)
    finally:
        values_book.close()
        formula_book.close()
    return out


def read_reference_catalog(path: Path, names: set[str] | None = None) -> dict[str, list[dict[str, Any]]]:
    """Every row of the three catalog sheets, with its روش and figures.

    Each row dict carries ``excel_row``, ``code``, ``description``, ``unit``,
    ``estimate_rate``, ``forecast_rate``, ``phase_codes``, ``method`` ('' when
    the row's H cell holds no recognizable formula), ``params``
    (``calc_params_json`` content), ``brand`` and ``ai_prompt``.
    """

    names = names if names is not None else set(list_sheet_names(path))
    wanted = [sheet for sheet in CATALOG_SHEET_NAMES if sheet in names]
    sheets = _load_sheet_rows(path, wanted)

    # Pass 1: excel row -> code, per catalog, so a formula naming another row
    # («=IF(N(H9)>1,H9,...)») can be stored as a stable reference to that row.
    codes: dict[str, dict[int, str]] = {}
    for sheet, (values, _formulas) in sheets.items():
        header_index, _columns = _header_map(values)
        table = codes.setdefault(CATALOG_SHEET_NAMES[sheet], {})
        for offset, row in enumerate(values[header_index + 1:], start=header_index + 2):
            if len(row) > 1 and _cell_text(row[1]) and _norm(row[1]) != _norm('عنوان'):
                table[offset] = _cell_text(row[0]) or _cell_text(row[1])

    out: dict[str, list[dict[str, Any]]] = {}
    for sheet, (values, formulas) in sheets.items():
        catalog_type = CATALOG_SHEET_NAMES[sheet]
        header_index, columns = _header_map(values)
        rows = out.setdefault(catalog_type, [])

        for offset, row in enumerate(values[header_index + 1:], start=header_index + 1):
            excel_row = offset + 1
            if len(row) < 5:
                continue
            description = _cell_text(row[1])
            if not description or _norm(description) == _norm('عنوان'):
                continue

            def cell(label: str) -> Any:
                col = columns.get(_norm(label))
                return row[col] if col is not None and col < len(row) else None

            estimate = _as_int(row[3])
            forecast = _number_or_none(row[4])
            formula_row = formulas[offset] if offset < len(formulas) else ()
            h_formula = formula_row[7] if len(formula_row) > 7 else None
            method, params = _classify(catalog_type, h_formula, row, cell, codes, excel_row)
            web_prices = [p for p in (_number_or_none(cell(f'قیمت وب{i}')) for i in (1, 2, 3)) if p]
            if web_prices:
                params.setdefault('web_prices', web_prices)
            rows.append({
                'excel_row': excel_row,
                'code': _cell_text(row[0]),
                'description': description,
                'unit': _cell_text(row[2]),
                'estimate_rate': estimate,
                'forecast_rate': (_as_int(forecast) if forecast is not None
                                  and (forecast or catalog_type == 'LAND') else estimate),
                'actual_rate': _number_or_none(row[5]) if len(row) > 5 else None,
                'phase_codes': normalize_phase_codes(row[6] if len(row) > 6 else ''),
                'method': method,
                'params': params,
                'brand': _cell_text(cell('برند مصالح')),
                'ai_prompt': _cell_text(cell('پرامپت AI')),
            })
    return out


def _classify(catalog_type: str, formula: Any, row: tuple, cell, codes: dict[str, dict[int, str]],
              excel_row: int) -> tuple[str, dict[str, Any]]:
    """(روش محاسبه, ضرایب) from one row's «ضریب رشد بروز» formula and its columns."""

    # Land has its own manually entered prices, independent of wage/tariff inflation.
    if catalog_type == 'LAND':
        return '', {}
    formula = str(formula or '') if isinstance(formula, str) and str(formula).startswith('=') else ''
    params: dict[str, Any] = {}

    def num(label: str) -> float | None:
        return _number_or_none(cell(label))

    def put(key: str, value: Any) -> None:
        if value not in (None, ''):
            params[key] = value

    if catalog_type == 'MATERIAL':
        sites = [s.strip() for s in re.split(r'[؛;]', _cell_text(cell('منابع قیمت وب (وب1/وب2/وب3)'))) if s.strip()]
        if sites:
            params['web_sites'] = sites[:3]
        put('carry_rate', num('ضریب حمل (نرخ)'))
        put('tax_rate', num('مالیات ارزش افزوده'))
        put('regional_factor', num('ضریب منطقه‌ای'))
        put('connection_factor', num('ضریب اتصال'))
        put('observed_date', _cell_text(cell('تاریخ مشاهده')))
        put('peer_group', _cell_text(cell('گروه هم‌رده')))
        put('basis_note', _cell_text(cell('روش محاسبه بروز')))
    elif catalog_type == 'CONTRACTOR':
        put('source', _cell_text(cell('منبع شاخص/تعرفه')))
        put('weight_wage', num('وزن حقوق'))
        put('weight_adjustment', num('وزن تعدیل'))
        put('weight_inflation', num('وزن تورم'))
        put('weight_dollar', num('وزن دلار/فولاد'))
        put('regional_factor', num('ضریب منطقه‌ای'))
        put('tax_rate', num('مالیات'))
        put('index_ratio', num('ضریب شاخص محاسباتی'))
        put('basis_note', _cell_text(cell('روش محاسبه بروز')))
    else:
        put('source', _cell_text(cell('منبع تعرفه/استعلام')))
        put('tariff_basis', _cell_text(cell('نحوه محاسبه قیمت بروز')))
        put('period_factor', num('ضریب سالانه/ماهانه'))
        put('months', num('ماه‌های سپری‌شده'))
        put('regional_factor', num('ضریب منطقه‌ای'))
        put('tax_rate', num('مالیات'))
        put('tariff_ratio', num('ضریب تعرفه محاسباتی'))
        put('basis_note', _cell_text(cell('روش محاسبه بروز')))
    if not formula:
        return '', params

    researched = _RESEARCHED_RE.search(formula)
    refs = []
    for sheet_name, ref_row in _H_REF_RE.findall(formula):
        ref_type = CATALOG_SHEET_NAMES.get(sheet_name, catalog_type) if sheet_name else catalog_type
        ref_row = int(ref_row)
        if ref_type == catalog_type and ref_row == excel_row:
            continue
        code = codes.get(ref_type, {}).get(ref_row)
        if code and f'{ref_type}:{code}' not in refs:
            refs.append(f'{ref_type}:{code}')

    if catalog_type == 'MATERIAL':
        if re.search(r'U\d+\s*/\s*D\d+', formula):
            return calc.METHOD_WEB, params
        if researched:
            params['researched_price'] = float(researched.group(1))
            return calc.METHOD_WEB, params
        if re.search(r'پارامترها!\$?B\$?5\b', formula):
            params['index'] = 'usd'
            return calc.METHOD_OTHER, params
        if refs:
            params['peer_refs'] = refs
            return calc.METHOD_PEER_AVERAGE, params
        return calc.METHOD_PHASE_AVERAGE, params
    if catalog_type == 'CONTRACTOR':
        duct = _DUCT_RE.search(formula)
        if duct:
            params.update({'weight_copper': float(duct.group(1)), 'weight_wage': float(duct.group(2)),
                           'weight_adjustment': 0.0, 'weight_inflation': 0.0, 'weight_dollar': 0.0,
                           'index_mode': 'live'})
        elif refs:
            params['peer_refs'] = refs
        elif researched:
            params['researched_price'] = float(researched.group(1))
        return calc.METHOD_WEIGHTED_INDEX, params
    params['fallback'] = 'wage'
    if researched:
        params['researched_price'] = float(researched.group(1))
    else:
        fixed = _FIXED_RATIO_RE.search(formula)
        ratio = float(fixed.group(1)) if fixed else _number_or_none(row[7] if len(row) > 7 else None)
        if ratio:
            params['reference_ratio'] = ratio
    return calc.METHOD_SERVICE_TARIFF, params


def read_review_list(path: Path) -> dict[tuple[str, int], str]:
    """{(catalog_type, excel row): علت} from «لیست بررسی مجدد»."""

    out: dict[tuple[str, int], str] = {}
    for row in read_sheet(path, name=REVIEW_SHEET_NAME):
        if len(row) < 2:
            continue
        catalog_type = CATALOG_SHEET_NAMES.get(str(row[0] or '').strip())
        excel_row = _number_or_none(row[1])
        if not catalog_type or not excel_row:
            continue
        reason = _cell_text(row[7]) if len(row) > 7 else ''
        out[(catalog_type, int(excel_row))] = reason or 'در «لیست بررسی مجدد» فایل مرجع'
    return out


def read_reference_parameters(path: Path) -> dict[str, dict[str, float]]:
    """{key: {'base': .., 'current': ..}} from the workbook's «پارامترها» sheet."""

    if PARAMETERS_SHEET_NAME not in set(list_sheet_names(path)):
        return {}
    found: dict[str, dict[str, float]] = {}
    for row in read_sheet(path, name=PARAMETERS_SHEET_NAME):
        if len(row) < 2:
            continue
        label = _norm(row[0])
        value = _number_or_none(row[1])
        if not label or value is None:
            continue
        for needle, key, which in REFERENCE_PARAMETER_LABELS:
            if _norm(needle) in label:
                slot = found.setdefault(key, {})
                for field in (('base', 'current') if which == 'both' else (which,)):
                    slot.setdefault(field, value)
                break
    return found
