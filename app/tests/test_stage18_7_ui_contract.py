"""Conformance guard for docs/theme_18_7/BARKAV_UI_CONTRACT.md.

Two rules, deliberately different in strictness:

* ``barkav_ui/`` must be perfectly clean.  It is new code with no legacy
  excuse, and it is what every future screen inherits from.
* The active 18.7 layer is held to a *ratchet*: each file's known count of
  hard-coded values is recorded below and may only shrink.  This lets the
  existing screens migrate gradually while making it impossible to add new
  violations, which is the property that actually protects future tabs.

Older inherited stage files are reported, never failed.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / 'barkav_ui'

HEX_COLOUR = re.compile(r'#[0-9A-Fa-f]{6}\b')
# A literal font tuple such as ('Segoe UI', 11, 'bold') - the family and the
# point size both have to come from barkav_ui.theme instead.  A font tuple is
# recognised by a multi-word family or by a trailing style word; matching any
# (string, number) pair caught ordinary data like ('radius', 6).
FONT_TUPLE = re.compile(
    r"""\(\s*['"][A-Za-z][A-Za-z0-9]*(?:\ [A-Za-z0-9]+)+['"]\s*,\s*\d+"""
    r"""|\(\s*['"][A-Za-z][A-Za-z0-9\ ]*['"]\s*,\s*\d+\s*,\s*['"](?:bold|normal|italic|roman)['"]"""
)

# Section 10: screens must not build their own windows any more.
RAW_TOPLEVEL = re.compile(r'\btk\.Toplevel\b')

# Ratchet baselines captured on 2026-08-27.  Lower these as screens migrate;
# never raise one.
HEX_BUDGET = {
    'dashboard_stage18_7.py': 2,
    # Includes the shared report canvas palette added by the current
    # integration/final project-report export path.
    'sales_claims_stage18_7.py': 49,
    'ui_stage18_7.py': 8,
    'reports_stage18_7.py': 0,   # migrated to the kit
    'financial_calendar_stage18_7.py': 0,   # migrated to the kit
    'project_center_stage18_7.py': 2,
    'telegram_stage18_7.py': 0,
    'launcher_stage18_7.py': 0,
    'project_runner_stage18_7.py': 0,
}

# Counts both `tk.Toplevel(...)` calls and `class X(tk.Toplevel)` bases.
# dashboard keeps 1: the File menu popup, which is an intentionally chrome-less
# overrideredirect surface; the chart detail now uses BarkavWindow.
TOPLEVEL_BUDGET = {
    'dashboard_stage18_7.py': 1,
    'sales_claims_stage18_7.py': 8,
    'reports_stage18_7.py': 0,   # migrated to the kit
    'financial_calendar_stage18_7.py': 0,   # migrated to the kit
}


def _source(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def test_component_kit_contains_no_literal_colours_or_fonts():
    """The kit is the single place styling is decided; it must stay pure."""

    offenders = {}
    for path in sorted(KIT.glob('*.py')):
        text = _source(path)
        found = HEX_COLOUR.findall(text) + FONT_TUPLE.findall(text)
        if found:
            offenders[path.name] = found
    assert not offenders, (
        'barkav_ui must read every colour and font from barkav_ui.theme. '
        f'Literals found: {offenders}'
    )


def test_component_kit_builds_windows_through_the_shell():
    """Only window.py may touch tk.Toplevel; everything else inherits it."""

    offenders = [
        path.name for path in sorted(KIT.glob('*.py'))
        if path.name != 'window.py' and RAW_TOPLEVEL.search(_source(path))
    ]
    assert not offenders, (
        'Use BarkavWindow/BarkavDialog/BarkavWizard instead of tk.Toplevel. '
        f'Offending kit modules: {offenders}'
    )


def test_active_187_layer_hardcoded_colours_never_increase():
    """Ratchet: a migrating screen may drop literals, never add them."""

    regressions = {}
    for name, budget in HEX_BUDGET.items():
        path = ROOT / name
        if not path.is_file():
            continue
        count = len(HEX_COLOUR.findall(_source(path)))
        if count > budget:
            regressions[name] = f'{count} > allowed {budget}'
    assert not regressions, (
        'New hard-coded colours were added to the active 18.7 layer. '
        'Read them from barkav_ui.theme instead. '
        f'Regressions: {regressions}'
    )


def test_active_187_layer_raw_toplevels_never_increase():
    regressions = {}
    for name, budget in TOPLEVEL_BUDGET.items():
        path = ROOT / name
        if not path.is_file():
            continue
        count = len(RAW_TOPLEVEL.findall(_source(path)))
        if count > budget:
            regressions[name] = f'{count} > allowed {budget}'
    assert not regressions, (
        'New tk.Toplevel windows were added. Subclass BarkavWindow so the '
        'window gets minimize/maximize/close and the themed title bar. '
        f'Regressions: {regressions}'
    )


def test_ratchet_budgets_are_not_quietly_inflated():
    """A budget above its recorded value would silently disarm the ratchet."""

    recorded = {
        'dashboard_stage18_7.py': 2, 'sales_claims_stage18_7.py': 119,
        'ui_stage18_7.py': 8, 'reports_stage18_7.py': 9,
        'financial_calendar_stage18_7.py': 2, 'project_center_stage18_7.py': 2,
        'telegram_stage18_7.py': 0, 'launcher_stage18_7.py': 0,
        'project_runner_stage18_7.py': 0,
    }
    inflated = {
        name: (HEX_BUDGET[name], value)
        for name, value in recorded.items()
        if HEX_BUDGET.get(name, 0) > value
    }
    assert not inflated, f'Ratchet budgets were raised instead of lowered: {inflated}'


def test_template_tab_demonstrates_every_contract_region():
    """The copy-me template must keep showing the full structure."""

    text = _source(KIT / 'template_tab.py')
    for marker in ('sub_notebook', 'DataTable', 'add_search', 'add_action', 'BarkavWizard'):
        assert marker in text, f'template_tab.py no longer demonstrates {marker}'
    # Section 6: the destructive action is declared last so it lands furthest
    # from the actions the user reaches for first.
    assert text.index("'create'") < text.index("'destructive'")


def test_tables_are_laid_out_from_the_right_and_can_be_scrolled_sideways():
    """Section 5: RTL order, content-sized columns, and a horizontal bar.

    Fixed widths spread the headings so far apart that a heading no longer
    sat above its own column, and pushed the last column off the edge with
    no way to reach it.
    """

    text = _source(KIT / 'table.py')
    # The first declared column has to end up right-most.
    assert 'list(reversed(self._columns))' in text
    # Width comes from what a column holds, not from a hand-written number.
    assert 'def _fit_columns' in text
    assert 'heading.measure(label)' in text
    # Slack collects at the left, which is where an RTL row ends.
    assert "self.tree.column(self._columns[-1][0], stretch=True)" in text
    # A table wider than its panel must still be readable end to end, and it
    # opens at the right, where the row begins.
    assert "orient='horizontal'" in text
    assert 'xview_moveto(1.0)' in text


def test_legacy_tree_rtl_bridge_lives_in_the_shared_table_kit():
    """Legacy Treeviews must reuse the same RTL implementation as DataTable."""

    table_source = _source(KIT / 'table.py')
    dashboard_source = _source(ROOT / 'dashboard_stage18_7.py')
    assert 'def apply_tree_rtl(' in table_source
    assert 'from barkav_ui.table import apply_tree_rtl as apply_tree_rtl_kit' in dashboard_source

def test_shared_legacy_tree_rtl_helper_reverses_columns_and_aligns_cells():
    """The extracted bridge performs the same legacy Treeview transformation."""

    from barkav_ui.table import apply_tree_rtl

    class FakeTree:
        def __init__(self):
            self.options = {'columns': ('first', 'second'), 'displaycolumns': '#all'}
            self.configured = []
            self.headings = []
            self.column_calls = []

        def cget(self, name):
            return self.options[name]

        def configure(self, **kwargs):
            self.configured.append(kwargs)
            self.options.update(kwargs)

        def heading(self, column, **kwargs):
            self.headings.append((column, kwargs))

        def column(self, column, **kwargs):
            self.column_calls.append((column, kwargs))

    tree = FakeTree()
    apply_tree_rtl(tree)

    assert tree.options['displaycolumns'] == ('second', 'first')
    assert [column for column, _ in tree.headings] == ['first', 'second']
    assert all(kwargs['anchor'] == 'e' for _, kwargs in tree.headings)
    assert all(kwargs['anchor'] == 'e' for _, kwargs in tree.column_calls)
    assert tree._barkav_rtl_187 is True


def test_contracts_toolbar_reads_from_the_right():
    """Section 4: actions right, what you are looking at next, output left."""

    text = _source(ROOT / 'contractors_stage18_7.py')
    order = [text.index(marker) for marker in (
        "add_tool('قرارداد جدید +'",     # right-most: what you do
        "add_filter('نمایش براساس'",     # then: what you are looking at
        "side='left'",                    # left: what you take out
    )]
    assert order == sorted(order), 'Toolbar controls are no longer declared right to left'
    # 'نمایش بر اساس' is two stages - a field, then that field's own values.
    assert 'FILTER_KEYS' in text and 'filter_value_combo' in text
    # The export control names itself rather than being labelled from outside.
    assert "EXPORT_PROMPT = 'خروجی'" in text


def test_kit_tables_are_not_re_mirrored_by_the_shell():
    """The shell reverses every tree's columns; a kit table is already reversed.

    Without the opt-out flag the two passes cancelled and the first column
    landed back on the left, which is why a kit table looked right on its own
    and wrong inside the running app.
    """

    assert "_barkav_rtl_187 = True" in _source(KIT / 'table.py')


def test_project_plan_is_an_outline_over_the_estimate():
    """The plan sheet folds: phase, cost type, section, then the rows."""

    text = _source(ROOT / 'project_plan_stage18_7.py')
    for marker in ('_outline', "('phase', phase_no)", "('kind', phase_no, kind)",
                   "('section', phase_no, kind, section)"):
        assert marker in text, f'project plan no longer groups by {marker}'
    # Only what is open is emitted, so the sheet opens on the phases alone.
    assert 'if phase_key not in self._open:' in text
    # وضعیت and منبع were dropped; what is left is the workbook's own row.
    labels = [label for _key, label in
              __import__('project_plan_stage18_7').PLAN_COLUMNS]
    assert 'وضعیت' not in labels and 'منبع / توضیح' not in labels


def test_both_reference_workbook_layouts_are_recognised():
    """The reference file was rebuilt; the old one must still import."""

    text = _source(ROOT / 'budget_rich_v163.py')
    assert 'def workbook_layout' in text
    assert '_phase_rows_v2' in text and '_main_price_rows_v2' in text
    assert "OVERALL_ESTIMATE_SHEETS=('براورد کلی','برآورد کلی')" in text
    assert 'rows=read_sheet(path,name=overall_sheet)' in text
    # The legacy accounting path parses the workbook separately, so it needs
    # the second layout too - without it the import died on the last-resort
    # parser with 'فاز ساخت در قالب اکسل پیدا نشد'.
    assert '_parse_peymaan_v2_workbook' in _source(ROOT / 'xlsx_simple.py')


def test_importing_a_workbook_redraws_the_plan():
    """A new reference file must reach the screens, not just the database."""

    text = _source(ROOT / 'reports_stage18_7.py')
    assert 'install_budget_import_refresh_187' in text
    # The plan keeps its rows between redraws, so the import has to drop them.
    assert 'plan._cache = None' in text


def test_plan_is_read_from_the_rollup_sheet():
    """'براورد کلی' is where the workbook presents the estimate.

    The per-phase sheets carry 635 flat rows; the rollup carries 1217 in the
    hierarchy the user reads, with its own row numbering. Reading the phase
    sheets produced a screen that looked nothing like the file.
    """

    text = _source(ROOT / 'budget_rich_v163.py')
    assert 'OVERALL_ESTIMATE_SHEETS' in text
    # A row other rows hang off carries their sum; counting both doubles it.
    assert "parents={r['ref'].rsplit('-',1)[0]" in text
    # The workbook's own row number is stored, and it identifies the line.
    assert 'plan_ref' in text and "stable('PHITEM',r['ref'])" in text
    plan = _source(ROOT / 'project_plan_stage18_7.py')
    assert "KIND_LETTERS = (('A', 'مصالح'), ('B', 'اجرت'), ('C', 'خدمات'), ('D', 'خرید زمین'))" in plan
    # A right-to-left embedding, not a mark: only the embedding works.
    assert "'\u202b'" in plan and "'\u202c'" in plan


def test_workbook_figures_are_not_invented():
    """بروز and واقعی are zero until the workbook says otherwise.

    Three separate places filled them from برآورد اولیه, and the ON CONFLICT
    clauses then refused to overwrite what had been filled in, so the wrong
    figure survived every re-import.
    """

    text = _source(ROOT / 'budget_rich_v163.py')
    assert text.count("if 'rate_actual' in") >= 3, 'a price path still invents بروز/واقعی'
    assert "if not old or 'qty_actual' in r:" in text
    # A reader that changed must reach data an older one produced.
    assert 'READER_VERSION' in text and '_reread_if_stale' in text
    plan = _source(ROOT / 'project_plan_stage18_7.py')
    assert "int(row.get('forecast_rate') or 0)" in plan


def test_stored_estimate_is_checked_three_ways_against_the_file():
    """A stored estimate goes stale for three reasons, and all three are checked.

    The file is edited between sessions; the reader is improved; or an import
    ran against a half-finished build and left fewer rows than it recorded.
    The version number alone missed the last two - and forgetting to bump it
    is exactly how the third happens.
    """

    text = _source(ROOT / 'budget_rich_v163.py')
    assert "changed=self._hash(source)!=str(row['source_hash'] or '')" in text
    assert "short=live<int(row['phase_item_count'] or 0)" in text
    assert 'if not (outdated or changed or short):return' in text


def test_sorting_is_opt_in_and_keeps_row_identity():
    """A sortable table must not be addressed by row position.

    Mapping the selected row's index to the caller's own list is only true
    while the two orders agree, which sorting ends.
    """

    text = _source(KIT / 'table.py')
    assert 'sortable: bool = False' in text, 'sorting must be opt-in'
    assert 'def selected_key' in text and 'keys: Sequence | None = None' in text
    # Amounts sort as amounts: the digits shown are Persian and grouped.
    assert "plain = en(raw).replace(',', '').strip()" in text

    plan = _source(ROOT / 'project_plan_stage18_7.py')
    # The outline table must stay unsorted, or its levels come apart.
    assert 'sortable=True' in plan
    assert plan.count('sortable=True') == 1, 'only the price tabs may sort'
    assert 'price_id = self.table.selected_key()' in plan


def test_price_editor_names_the_rates_as_the_table_does():
    """One name per column across the tab and the window that edits it.

    The editor called forecast_rate 'پیش‌بینی' and actual_rate 'واقعی مرجع',
    the table beside it called them 'برآورد بروز' and 'واقعی' - the same two
    fields, named the other way round. All three are the price of one unit,
    and every heading says so.
    """

    text = _source(ROOT / 'reports_stage18_7.py')
    assert "('estimate_rate', 'قیمت واحد برآورد')" in text
    assert "('forecast_rate', 'قیمت واحد بروز'), ('actual_rate', 'قیمت واحد واقعی')" in text
    assert "('code', 'شماره ردیف')" in text and "('source', 'فاز اجرا')" in text
    # Amounts group as they are typed, and a price can be retired from here.
    assert 'formatted_amount_input_187' in text and 'def delete(self)' in text


def test_price_rows_are_renumbered_and_reachable_by_right_click():
    text = _source(ROOT / 'project_plan_stage18_7.py')
    assert 'def _context_menu' in text and 'def renumber' in text
    # Added below its neighbour as a half step, made whole by renumbering.
    assert "+ 0.5)" in text
    # A phase opens whole; a row opens alone.
    assert 'class PhasePlanWindow187' in text
    assert "if key is not None and key[0] == 'phase':" in text


def test_a_window_outlives_its_owner_redrawing():
    """<Destroy> reaches a toplevel for every widget inside it.

    Closing on any of them meant a screen rebuilding its table took down every
    window opened from it - which read as a dialog refusing to save.
    """

    text = _source(KIT / 'window.py')
    assert 'if event is not None and event.widget is not owner:' in text


def test_the_plan_row_window_carries_the_sheets_columns():
    text = _source(ROOT / 'project_plan_stage18_7.py')
    for key in ("('forecast_rate', 'قیمت واحد-بروز')",
                "('actual_rate', 'قیمت واحد-واقعی')",
                "('qty_actual', 'مقدار-واقعی')"):
        assert key in text, f'the add window is missing {key}'
    # Totals follow what is typed rather than being typed.
    assert 'def _retotal' in text
    # A saved row is placed under the selected one and then shown.
    assert 'def _reveal' in text and 'self.on_saved(self.created)' in text


def test_one_code_ties_a_rate_across_the_plan_and_the_price_tabs():
    """A rate belongs to the price, and the code makes that visible.

    میلگرد is bought for several phases at one rate, so its rows move
    together; the quantity does not, because what is used in اسکلت is not what
    is used elsewhere. The code says which is which.
    """

    plan = _source(ROOT / 'project_plan_stage18_7.py')
    assert 'def price_code' in plan
    assert "CATEGORY_LETTERS = {'MATERIAL': 'A', 'LABOR': 'B', 'SERVICE': 'C', 'LAND': 'D'}" in plan
    # Shown in the plan sheet and in the price tabs, from the same function.
    assert "('code', 'کد قیمت')" in plan and "('price_code', 'کد قیمت')" in plan
    # A phase row cannot build the code from its own columns, so the join
    # brings the price's code and category across.
    rich = _source(ROOT / 'budget_rich_v163.py')
    assert 'p.code code,p.category category' in rich


def test_the_actual_total_is_recorded_not_derived():
    """A payment is often known when the quantity behind it is not.

    برآورد and بروز stay quantity times coefficient times rate. واقعی is the
    money paid and only that - the plan sheet and the phase roll-up read the
    same stored figure, or they report different actuals for the same rows.
    """

    plan = _source(ROOT / 'project_plan_stage18_7.py')
    assert "computed[2] = int(row.get('total_actual') or 0)" in plan
    assert "('total_actual', 'مبلغ کل-واقعی', 15)" in plan

    rich = _source(ROOT / 'budget_rich_v163.py')
    assert "act+=int(r.get('total_actual') or 0)" in rich
    # A re-import must not erase it: the workbook does not know what was spent.
    conflict = rich[rich.index('ON CONFLICT(phase_item_id) DO UPDATE'):][:600]
    assert 'total_actual=excluded' not in conflict


def test_construction_costs_carry_a_section_and_nothing_else_does():
    """دسته‌بندی belongs to a construction cost, not to every transaction.

    An instalment or a sale has no place in the plan's three sections, so the
    field is offered only where it means something.
    """

    import dashboard_stage18 as v18
    import dashboard_stage18_2 as v182

    assert v18.COST_GROUPS == ['مصالح', 'پیمانکار', 'خدمات']
    for subtype in v18.TITLE_TYPES['هزینه ساخت']:
        keys = [f.key for f in v18._special_fields('هزینه ساخت', subtype)]
        assert 'cost_group' in keys, f'هزینه ساخت/{subtype} is missing it'
        # And it is asked on the first window, with the amount and the date -
        # not pages later, among the payment details.
        later = {f.key for group in v182.wizard_steps_182('هزینه ساخت', subtype)
                 for f in group}
        assert 'cost_group' not in later, f'هزینه ساخت/{subtype} asks twice'
    for title in ('ورودی', 'خروجی', 'یادداشت'):
        for subtype in v18.TITLE_TYPES[title]:
            keys = [f.key for f in v18._special_fields(title, subtype)]
            assert 'cost_group' not in keys, f'{title}/{subtype} should not offer it'
    source = _source(ROOT / 'dashboard_stage18.py')
    assert "first.append(FieldDef('cost_group'" in source

    # It reaches the expense row, and the table that lists them shows it.
    assert 'cost_group TEXT NOT NULL' in _source(ROOT / 'finance_db.py')
    assert 'ALTER TABLE expenses ADD COLUMN cost_group' in _source(ROOT / 'finance_db.py')
    assert 'def install_cost_group_column_187' in _source(ROOT / 'reports_stage18_7.py')


# --- Which plan line a construction cost lands on ---------------------------

class _FakePlan:
    """A two-phase plan, enough to ask the matcher a real question."""

    ROWS = [
        dict(phase_no=8, plan_ref='08-1', description='میلگرد Ø8', section='',
             cost_type='مصالح', unit='کیلوگرم', qty_estimate=3000, local_estimate_rate=500),
        dict(phase_no=8, plan_ref='08-2', description='میلگرد Ø10', section='',
             cost_type='مصالح', unit='کیلوگرم', qty_estimate=11610, local_estimate_rate=500),
        dict(phase_no=8, plan_ref='08-11', description='بتن', section='',
             cost_type='مصالح', unit='مترمکعب', qty_estimate=453, local_estimate_rate=4000),
        dict(phase_no=8, plan_ref='08-16-1', description='اجرت اجرای اسکلت',
             section='اجرت اجرای اسکلت', cost_type='اجرت', unit='مترمربع',
             qty_estimate=1914, local_estimate_rate=900),
        dict(phase_no=8, plan_ref='08-16-2', description='سایر 1',
             section='اجرت اجرای اسکلت', cost_type='اجرت', unit='مقطوع',
             qty_estimate=0, local_estimate_rate=0),
        dict(phase_no=8, plan_ref='08-20', description='غذا', section='',
             cost_type='خدمات', unit='پرس', qty_estimate=30, local_estimate_rate=250),
        dict(phase_no=9, plan_ref='09-1', description='لوله سیمانی', section='',
             cost_type='مصالح', unit='عدد', qty_estimate=60, local_estimate_rate=400),
    ]

    def list_phase_items(self, no):
        return [dict(r) for r in self.ROWS if r['phase_no'] == int(no)]

    def list_phase_summary(self):
        return [{'phase_no': 8, 'phase': 'اسکلت'}, {'phase_no': 9, 'phase': 'چاه'}]

    def get_phase_progress(self):
        return {}

    def subphase_candidates(self, no, query=''):
        return self.list_phase_items(no) if no else []


def test_a_construction_cost_is_read_onto_one_plan_line():
    """The wording of a payment decides which line of the plan it belongs to.

    Every case here is one an operator would type, and the answer has to be a
    single line - a payment arrives without an invoice splitting it, so the
    whole amount goes somewhere or nowhere.
    """

    from cost_allocation_stage18_7 import suggest_plan_row

    plan = _FakePlan()
    cases = [
        ('خرید بتن آماده برای سقف', 'مصالح', 8, '08-11'),
        ('پرداخت اجرت اجرای اسکلت به علی رضایی', 'پیمانکار', 8, '08-16-1'),
        ('غذای کارگران', 'خدمات', 8, '08-20'),
        ('لوله سیمانی چاه', 'مصالح', 9, '09-1'),
    ]
    for text, group, phase, expected in cases:
        guess = suggest_plan_row(plan, text=text, cost_group=group, phase_no=phase)
        assert guess is not None, text
        assert guess.plan_ref == expected, f'{text} -> {guess.plan_ref}'

    # A one-word payment cannot choose between the میلگرد lines. It still has
    # to choose one, and it must be a میلگرد line rather than the concrete.
    guess = suggest_plan_row(plan, text='خرید میلگرد', cost_group='مصالح', phase_no=8)
    assert guess is not None and guess.plan_ref in {'08-1', '08-2'}
    assert guess.confidence < 0.75, 'an unresolved choice must not read as certain'

    # Saying which one settles it.
    guess = suggest_plan_row(plan, text='خرید میلگرد', cost_group='مصالح', phase_no=8,
                             sub_phase='میلگرد Ø8')
    assert guess is not None and guess.plan_ref == '08-1'


def test_a_cost_lands_only_in_its_own_section_or_nowhere():
    """A wrong line is worse than no line, and مصالح money is not اجرت money."""

    from cost_allocation_stage18_7 import suggest_plan_row

    plan = _FakePlan()
    # Wording that names nothing in the plan gets no line at all.
    assert suggest_plan_row(plan, text='قسط وام مسکن', cost_group='مصالح', phase_no=8) is None

    # 'اجرت اجرای اسکلت' is an اجرت line; asking as مصالح must not reach it.
    guess = suggest_plan_row(plan, text='اجرت اجرای اسکلت', cost_group='مصالح', phase_no=8)
    assert guess is None or guess.cost_type == 'مصالح'

    # The blank 'سایر' lines exist to be filled in later, not to absorb a cost
    # that names a real trade.
    guess = suggest_plan_row(plan, text='اجرت اجرای اسکلت', cost_group='پیمانکار', phase_no=8)
    assert guess is not None and guess.plan_ref == '08-16-1'


class _AllocationMetadata:
    """The projection test DB also persists the new contract field provenance."""
    def get_setting(self,key):
        self.con.execute('CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT)')
        row=self.con.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
        return row[0] if row else None

    def set_setting(self,key,value):
        self.con.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',(key,value))

    def atomic(self):return self._ctx()

    def _audit(self,*args,**kwargs):pass


def test_the_plan_totals_what_was_spent_and_can_take_it_back():
    """Actuals are recomputed from the expenses, never accumulated in place.

    That is what makes a corrected assignment move the money instead of
    doubling it, and what lets a deleted cost leave the plan.
    """

    import sqlite3
    import cost_allocation_stage18_7 as alloc

    class _DB(_AllocationMetadata):
        def __init__(self):
            self.con = sqlite3.connect(':memory:')
            self.con.row_factory = sqlite3.Row
            self.con.executescript("""
              CREATE TABLE expenses(expense_id TEXT, final_amount INTEGER,
                status TEXT DEFAULT 'APPROVED', deleted_at TEXT, plan_ref TEXT DEFAULT '');
              CREATE TABLE rich_phase_items(phase_item_id TEXT, plan_ref TEXT DEFAULT '',
                total_actual INTEGER DEFAULT 0, actual_source TEXT DEFAULT '',
                active INTEGER DEFAULT 1, updated_at TEXT);
              INSERT INTO rich_phase_items(phase_item_id,plan_ref)
                VALUES('A','08-11'),('B','08-2'),('C','08-6');
            """)

        def _ctx(db_self):
            class _Ctx:
                def __enter__(self):
                    return db_self.con

                def __exit__(self, *exc):
                    db_self.con.commit()
                    return False
            return _Ctx()

        read = tx = _ctx

        def spent(self, ref):
            return self.con.execute(
                'SELECT total_actual FROM rich_phase_items WHERE plan_ref=?', (ref,)).fetchone()[0]

    db = _DB()
    db.con.executemany('INSERT INTO expenses(expense_id,final_amount,plan_ref) VALUES(?,?,?)',
                       [('E1', 120, '08-11'), ('E2', 900, '08-2'), ('E3', 30, '08-11')])
    # A line with a hand-typed actual and no payments behind it.
    db.con.execute("UPDATE rich_phase_items SET total_actual=777 WHERE plan_ref='08-6'")

    assert alloc.apply_actuals(db) == 2
    assert alloc.apply_actuals(db) == 0, 'must be idempotent'
    assert db.spent('08-11') == 150, 'two payments on one line add up'
    assert db.spent('08-2') == 900
    assert db.spent('08-6') == 777, 'a hand-typed figure is not overwritten'

    # Deleting the money takes it off the plan again.
    db.con.execute("UPDATE expenses SET deleted_at='now' WHERE expense_id IN ('E1','E3')")
    assert alloc.apply_actuals(db) == 1
    assert db.spent('08-11') == 0
    assert db.spent('08-6') == 777


def test_every_unit_price_on_the_sheet_is_a_stated_one():
    """قیمت واحد واقعی is agreed, not calculated.

    It is what a contract set (قیمت واحد قرارداد), or what was typed straight
    into the column. Dividing the money spent by the quantity produced a
    "unit price" nobody had agreed to, and it is not done: a line can carry
    a total with no unit price at all, which the operator said is real.
    """

    from project_plan_stage18_7 import PRICE_COLUMNS, _rates, _totals

    spent_only = {'local_estimate_rate': 1000, 'qty_estimate': 10, 'qty_actual': 4,
                  'factor': 1, 'total_actual': 6000}
    assert _rates(spent_only)[2] == 0, 'nothing was agreed, so nothing is claimed'
    assert _totals(spent_only)[2] == 6000, 'the total stands on its own'

    agreed = dict(spent_only, local_actual_rate=800)
    assert _rates(agreed)[2] == 800
    # The operator requested bidirectional prices: the linked catalogue is
    # authoritative; a missing catalogue retains the legacy local fallback.
    assert _rates(dict(agreed, actual_rate=999))[2] == 999
    assert _rates(dict(spent_only, actual_rate=999))[2] == 999

    # And the sheets say 'unit' in every one of the three headings.
    for key, label in PRICE_COLUMNS:
        if key.endswith('_rate'):
            assert 'قیمت واحد' in label, (key, label)


def test_a_construction_cost_records_which_plan_line_it_paid_for():
    """The guess is stored where it can be seen, not recomputed out of sight."""

    finance = _source(ROOT / 'finance_db.py')
    assert 'plan_ref TEXT NOT NULL' in finance
    assert 'ALTER TABLE expenses ADD COLUMN plan_ref' in finance

    dashboard = _source(ROOT / 'dashboard_stage18.py')
    assert "p['plan_ref']=guess_for_payload(" in dashboard

    reports = _source(ROOT / 'reports_stage18_7.py')
    assert "'ردیف پلان'" in reports
    assert 'def install_actual_cost_sync_187' in reports
    assert 'install_actual_cost_sync_187(app)' in reports


@contextlib.contextmanager
def _alloc_project(contracts):
    """A database with four اجرت lines, and a contracts file beside it.

    pytest's own tmp_path is avoided deliberately: its root on this machine is
    unreadable, which is what makes several inherited tests error out.
    """

    import sqlite3

    folder = tempfile.mkdtemp()
    (Path(folder) / 'contractor_contracts_18_7.json').write_text(
        json.dumps({'contracts': contracts}, ensure_ascii=False), encoding='utf-8')
    previous = os.environ.get('STAGE4_DB_PATH')
    os.environ['STAGE4_DB_PATH'] = str(Path(folder) / 'x.sqlite3')

    class _DB(_AllocationMetadata):
        def __init__(self):
            self.con = sqlite3.connect(':memory:')
            self.con.row_factory = sqlite3.Row
            self.con.executescript("""
              CREATE TABLE expenses(expense_id TEXT, final_amount INTEGER,
                status TEXT DEFAULT 'APPROVED', deleted_at TEXT, plan_ref TEXT DEFAULT '');
              CREATE TABLE rich_price_items(price_id TEXT, description TEXT, category TEXT);
              CREATE TABLE rich_phase_items(phase_item_id TEXT, plan_ref TEXT DEFAULT '',
                price_id TEXT, cost_type TEXT, description TEXT DEFAULT '',
                qty_actual REAL DEFAULT 0, local_actual_rate INTEGER DEFAULT 0,
                total_actual INTEGER DEFAULT 0,
                actual_source TEXT DEFAULT '', active INTEGER DEFAULT 1, updated_at TEXT);
              INSERT INTO rich_price_items VALUES
                ('P1','اجرت اجرای اسکلت','LABOR'), ('P2','جرثقیل','LABOR'),
                ('P3','همبندی سقفی','LABOR'), ('P4','اجرت بنا','LABOR');
              INSERT INTO rich_phase_items(phase_item_id,plan_ref,price_id,cost_type,description) VALUES
                ('A','08-16-1','P1','اجرت','اجرت اجرای اسکلت'),
                ('B','08-19-1','P2','اجرت','سایر 1'),
                ('C','08-17-1','P3','اجرت','همبندی سقفی'),
                ('D','09-5-1','P4','اجرت','اجرت بنا');
            """)
            self.folder = Path(folder)

        def _ctx(db_self):
            class _Ctx:
                def __enter__(self):
                    return db_self.con

                def __exit__(self, *exc):
                    db_self.con.commit()
                    return False
            return _Ctx()

        read = tx = _ctx

        def spent(self, ref):
            row = self.con.execute(
                'SELECT total_actual, actual_source FROM rich_phase_items WHERE plan_ref=?',
                (ref,)).fetchone()
            return row['total_actual'], row['actual_source']

        def rewrite_contracts(self, records):
            (self.folder / 'contractor_contracts_18_7.json').write_text(
                json.dumps({'contracts': records}, ensure_ascii=False), encoding='utf-8')

    try:
        yield _DB()
    finally:
        if previous is None:
            os.environ.pop('STAGE4_DB_PATH', None)
        else:
            os.environ['STAGE4_DB_PATH'] = previous
        shutil.rmtree(folder, ignore_errors=True)


def test_a_contract_puts_what_it_paid_on_the_lines_it_covers():
    """A contract states its own payments, so those are the اجرت actuals.

    Split across the lines the contract covers the way the contract splits the
    work - the only division it states - and all on the first line when it
    states none.
    """

    import cost_allocation_stage18_7 as alloc

    with _alloc_project([
        {'contract_id': 'C1', 'title': 'اجرت اجرای اسکلت',
         'rows': [{'description': 'اجرت اجرای اسکلت', 'line_total': '1,722,600,000'}],
         'payments': [{'amount': '400,000,000'}, {'amount': '450,000,000'}]},
        {'contract_id': 'C2', 'title': 'جرثقیل',
         'rows': [{'description': 'جرثقیل', 'line_total': '60,000,000'},
                  {'description': 'همبندی سقفی', 'line_total': '20,000,000'}],
         'payments': [{'amount': '40,000,000'}]},
    ]) as db:
        assert alloc.apply_actuals(db) == 3
        assert alloc.apply_actuals(db) == 0, 'must be idempotent'
        assert db.spent('08-16-1') == (850_000_000, 'CONTRACTS')
        # 60 to 20 of the work, so 30 and 10 of the money - and they add up.
        assert db.spent('08-19-1') == (30_000_000, 'CONTRACTS')
        assert db.spent('08-17-1') == (10_000_000, 'CONTRACTS')


def test_a_contract_and_its_transactions_are_the_same_money():
    """Counting both would double every contracted trade.

    The operator's rule: a contractor's payments come from the contract, and
    the transactions speak only for a contractor with no contract.
    """

    import cost_allocation_stage18_7 as alloc

    with _alloc_project([
        {'contract_id': 'C1', 'title': 'اجرت اجرای اسکلت',
         'rows': [{'description': 'اجرت اجرای اسکلت'}],
         'payments': [{'amount': '850,000,000'}]},
    ]) as db:
        db.con.executemany(
            'INSERT INTO expenses(expense_id,final_amount,plan_ref) VALUES(?,?,?)',
            [('E1', 850_000_000, '08-16-1'), ('E2', 6_000_000, '09-5-1')])

        alloc.apply_actuals(db)
        assert db.spent('08-16-1') == (850_000_000, 'CONTRACTS'), 'not 1.7 billion'
        assert db.spent('09-5-1') == (6_000_000, 'EXPENSES'), 'no contract, so what was paid'

        # Remove the contract and the line falls back to its transactions.
        db.rewrite_contracts([])
        assert alloc.apply_actuals(db) == 1
        assert db.spent('08-16-1') == (850_000_000, 'EXPENSES')


def test_the_plan_is_what_a_phase_has_actually_cost():
    """One figure, not two.

    The فازها tab used to take its actual from the legacy budget service,
    which groups spend by the old activity taxonomy - so it and the plan sheet
    could report different amounts for the same phase. The operator settled
    it: the plan is the authority.
    """

    source = _source(ROOT / 'dashboard_stage16_3.py')
    live = source[source.index('def _phase_summary_live'):]
    live = live[:live.index('\n    def ')]
    assert 'return [dict(r) for r in self.rich.list_phase_summary()]' in live
    assert 'SERVICE.budget.phase_summary()' not in live, 'the legacy figure is back'


def test_a_contract_names_and_prices_the_plan_lines_it_covers():
    """The workbook leaves 'سایر' lines blank; a contract is where they are filled.

    The name, the agreed unit price and the volume are typed into the
    contract, and the plan shows them - because the contract is the only
    place they are stated. The link is the plan's own line number, so
    renaming the row moves the name rather than losing the line.
    """

    import cost_allocation_stage18_7 as alloc

    with _alloc_project([
        {'contract_id': 'C1', 'title': 'اجرت اجرای اسکلت',
         'rows': [{'plan_ref': '08-19-1', 'description': 'اجرت میلگردبندی سقف',
                   'unit_price': '۱۲۰,۰۰۰', 'quantity': '500'}],
         'payments': [{'amount': '40,000,000'}]},
    ]) as db:
        assert alloc.apply_contract_rows(db) == 1
        assert alloc.apply_contract_rows(db) == 0, 'must be idempotent'
        line = db.con.execute(
            'SELECT description, qty_actual, local_actual_rate FROM rich_phase_items '
            "WHERE plan_ref='08-19-1'").fetchone()
        assert line['description'] == 'اجرت میلگردبندی سقف'
        assert line['local_actual_rate'] == 120_000
        assert line['qty_actual'] == 500

        # Renaming again follows the same line, because the link is its number.
        db.rewrite_contracts([
            {'contract_id': 'C1', 'title': 'اجرت اجرای اسکلت',
             'rows': [{'plan_ref': '08-19-1', 'description': 'اجرت آرماتوربندی',
                       'unit_price': '۱۲۰,۰۰۰', 'quantity': '500'}],
             'payments': [{'amount': '40,000,000'}]},
        ])
        assert alloc.apply_contract_rows(db) == 1
        renamed = db.con.execute(
            "SELECT description FROM rich_phase_items WHERE plan_ref='08-19-1'").fetchone()
        assert renamed['description'] == 'اجرت آرماتوربندی'


def test_the_contract_rows_are_one_grid_in_both_windows():
    """Editable in the record window too, and without rules between the cells."""

    import contractor_contracts_stage18_7 as cc

    labels = dict(cc.ROW_COLUMNS)
    assert labels['unit_price'] == 'مبلغ واحد قرارداد'
    assert labels['estimate_price'] == 'مبلغ واحد برآورد'
    # Each column carries its own heading, so none of them is cut short.
    for key, label in cc.ROW_COLUMNS:
        assert cc.ROW_WIDTHS[key] >= min(len(label), 11), key

    source = _source(ROOT / 'contractor_contracts_stage18_7.py')
    assert 'def render_row_grid_187' in source
    # Both windows draw the same grid, and neither builds a read-only table -
    # the wizard's own rows page, the record window's, the record window
    # redrawing it after a بازخوانی از پلان repairs a broken contract, and
    # after تعداد ردیف changes the row count.
    assert source.count('render_row_grid_187(') == 5


def test_the_contract_amount_is_the_rows_own_total_not_the_plans_estimate():
    """مبلغ قرارداد جدول قراردادها = مبلغ کل واقعی مدیریت پروژه = مبلغ کل
    قرارداد در پنجره‌ها - all three read total_amount, so it has to be
    honest. Choosing فاز ساخت used to fill it from the phase's own estimate,
    which is a projection, not what anyone had agreed to pay; the caption
    said 'مبلغ کل قرارداد' over a number that was really 'مبلغ برآورد'.
    contract_worth() (the settlement rule) reads this same field as the
    contract's commitment before it is settled, so an inflated estimate here
    was reaching مبلغ کل واقعی on every covered plan line too.
    """

    import tkinter as tk
    import contractor_contracts_stage18_7 as cc

    source = _source(ROOT / 'contractor_contracts_stage18_7.py')
    assert 'def _line_estimate' not in source, 'the estimate-based total must be gone entirely'
    assert 'def plan_line_estimate' not in source

    chosen = source[source.index('    def _phase_chosen(self, *_args) -> None:'):]
    chosen = chosen[:chosen.index('\n    def ', 10)]
    assert "self._var('total_amount')" not in chosen, \
        'choosing a phase must not touch the contract amount at all'

    retotal = source[source.index('    def _retotal_contract(self) -> None:'):]
    retotal = retotal[:retotal.index('\n    def ', 10)]
    assert 'contract_rows_total(self.row_values)' in retotal

    root = tk.Tk()
    root.withdraw()
    try:
        row_values = [cc.blank_row_187(), cc.blank_row_187()]
        row_values[0]['unit_price'].set('750000')
        row_values[0]['quantity'].set('1914')
        row_values[1]['line_total'].set('1000000')
        assert cc.contract_rows_total(row_values) == 1_436_500_000
    finally:
        root.destroy()


def test_a_row_totals_itself_but_a_typed_total_still_wins():
    """مبلغ کل قرارداد follows مبلغ واحد قرارداد × حجم قرارداد, unless typed.

    Multiplying is the common case, so typing either the price or the volume
    recomputes the total. A trade agreed as one lump sum has no meaningful
    unit price, so its total is left exactly as typed - only a price and a
    volume both present ever overwrite it, which a blank unit price never is.
    """

    import tkinter as tk
    import contractor_contracts_stage18_7 as cc

    def grouped_int(text: str) -> str:
        digits = str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')
        return text.translate(digits).replace(',', '').replace('٬', '')

    root = tk.Tk()
    root.withdraw()
    try:
        row = cc.blank_row_187()
        row['unit_price'].set('750000')
        assert row['line_total'].get() == '', 'no quantity yet - nothing to multiply'
        row['quantity'].set('1914')
        assert grouped_int(row['line_total'].get()) == '1435500000'

        row['unit_price'].set('800000')
        assert grouped_int(row['line_total'].get()) == '1531200000', 'the price still drives it'

        row['line_total'].set('999000000')
        assert grouped_int(row['line_total'].get()) == '999000000', 'typed by hand, and it stands'

        lump = cc.blank_row_187()
        lump['line_total'].set('50000000')
        lump['quantity'].set('1')
        assert grouped_int(lump['line_total'].get()) == '50000000', \
            'no unit price at all - the typed total is not touched'
    finally:
        root.destroy()


def test_editing_a_contract_keeps_its_rows_instead_of_starting_blank():
    """self.row_values began empty on every wizard open, edit or not.

    _seed_from_record restored the scalar fields - title, build_phase, the
    lot - from the saved contract, but never touched self.row_values, and
    collect() only ever reads self.row_values. So closing the wizard on an
    edit - even to fix one unrelated typo - saved blank rows over agreed,
    priced, metred ones the moment ✕ was pressed. This is the bug that put
    real rows in production data.
    """

    source = _source(ROOT / 'contractor_contracts_stage18_7.py')
    seed = source[source.index('    def _seed_from_record(self) -> None:'):]
    seed = seed[:seed.index('\n    def ', 10)]
    assert "stored_rows = [r for r in (self.record.get('rows') or [])" in seed
    assert 'self.row_values = []' in seed
    assert "row['plan_ref'].set(str(stored.get('plan_ref') or ''))" in seed


def test_a_broken_contracts_estimate_values_can_be_repaired_from_the_record():
    """انتخاب قرارداد اسکلت showed blank ردیف‌های قرارداد for exactly this reason:

    a real contract, edited once through the buggy wizard above, had every
    row saved empty. The record window had no فاز ساخت field at all to
    re-trigger a pull from the plan with - so once a contract's rows were
    blank there was no way back to the numbers short of retyping them.
    """

    source = _source(ROOT / 'contractor_contracts_stage18_7.py')
    assert 'def plan_phase_choices(rich)' in source
    assert 'def plan_rows_for_title(rich' in source
    assert 'def apply_plan_rows(' in source
    assert 'def _repull_from_plan(self) -> None:' in source

    terms = source[source.index('    def _page_terms(self, page) -> None:'):]
    terms = terms[:terms.index('\n    def ', 10)]
    assert "'build_phase'" in terms
    assert 'self._repull_from_plan' in terms
    # Choosing the phase triggers it, the way the wizard's own combo does.
    assert "phase_var.trace_add('write'" in terms


def test_the_record_window_shows_every_section_together_not_behind_tabs():
    """The operator asked for one page, not four hidden behind a tab strip -
    and later, one scrollbar for the whole window rather than a second one
    just for ردیف‌های قرارداد. All four sections, rows included, sit in the
    one _vertical_scroll_area now; render_row_grid_187's own max_height (a
    separate, bounded inner scroll) is not used here any more.
    """

    source = _source(ROOT / 'contractor_contracts_stage18_7.py')
    details = source[source.index('    def _build_details(self, parent) -> None:'):]
    details = details[:details.index('\n    def ', 10)]
    assert 'ttk.Notebook' not in details
    assert 'sub_notebook' not in details
    assert '_vertical_scroll_area(' in details
    assert 'self._page_rows(rows_section)' in details

    build_rows = source[source.index('    def _build_rows(self, group) -> None:'):]
    build_rows = build_rows[:build_rows.index('\n    def ', 10)]
    assert 'max_height' not in build_rows
    assert 'self._rows_grid_host' in build_rows
    assert "'تعداد ردیف'" in build_rows
    assert 'DataTable(group, ROW_COLUMNS' not in source


def test_the_record_window_lets_the_operator_change_the_row_count():
    """ردیف‌های قرارداد used to only ever show exactly the rows already
    stored, with no way to add or drop one short of «بازخوانی مقادیر از
    پلان» pulling a whole new set - the wizard's own row page has always had
    a تعداد ردیف control and the record window now mirrors it.
    """

    source = _source(ROOT / 'contractor_contracts_stage18_7.py')
    resize = source[source.index('    def _resize_rows(self) -> None:',
                                  source.index('class ContractRecordWindow187')):]
    resize = resize[:resize.index('\n    def ', 10)]
    assert 'self._row_count_var' in resize
    assert "'_rows_grid_host'" in resize
    assert 'self._retotal_contract()' in resize


def test_a_line_costs_what_was_paid_on_it_and_not_a_toman_more():
    """مبلغ کل واقعی is the money paid. It is never the price times the volume.

    A line can be priced and metred long before anything is paid against it -
    a contract signed, a quantity surveyed - and reporting that product as
    spent showed money that had not moved, on the line and in the phase total
    above it.
    """

    from project_plan_stage18_7 import _rates, _totals

    signed = {'local_estimate_rate': 900, 'qty_estimate': 10, 'qty_actual': 10,
              'factor': 1, 'local_actual_rate': 800, 'total_actual': 0}
    assert _rates(signed)[2] == 800, 'the agreed unit price stands'
    assert _totals(signed)[2] == 0, 'nothing has been paid'

    part_paid = dict(signed, total_actual=3000)
    assert _totals(part_paid)[2] == 3000
    assert _rates(part_paid)[2] == 800, 'paying does not change the agreement'

    # The phase total is the same sum, so the tab and the sheet agree.
    summary = _source(ROOT / 'budget_rich_v163.py')
    body = summary[summary.index('def list_phase_summary'):]
    body = body[:body.index(chr(10) + '    def ')]
    assert "act+=int(r.get('total_actual') or 0)" in body
    assert 'qa*factor*ar' not in body, 'a phase is not spent because it is priced'


def test_no_legacy_sweep_touches_a_kit_table():
    """A DataTable already decided its own grid, headings and row colours.

    Five generations of the same blanket pass (18.3 through 18.6) walk every
    Treeview in the window and restyle it - a grid overlay, a currency suffix
    on the heading, a different palette on the row tags. Reaching a kit table
    broke it two different ways at once: 'شماره قرارداد' and 'مدت پرداخت'
    were relabelled '(تومان)' for containing the words 'قرارداد'/'پرداخت',
    and DataTable had already sized those columns for the shorter, correct
    heading - so the new one no longer fit. Every one of the five now checks
    the same flag before touching a tree.
    """

    kit = _source(KIT / 'table.py')
    assert '_barkav_kit_table_187 = True' in kit

    class _FakeTree:
        _barkav_kit_table_187 = True

    class _FakeTable:
        tree = _FakeTree()

    import ui_stage18_3 as v183
    import ui_stage18_4 as v184
    import ui_stage18_5 as v185
    import ui_stage18_6 as v186

    # None of these may get far enough to touch the fake tree's other
    # attributes - if the guard is missing, the next line inside each
    # function raises AttributeError instead of returning quietly.
    assert v183.attach_tree_grid(_FakeTree()) is None
    assert v184.attach_tree_grid_184(_FakeTree()) is None
    checkbox_tree = _FakeTree()
    assert v184.enable_tree_checkboxes(checkbox_tree) is checkbox_tree
    assert v185.attach_tree_grid_185(_FakeTree()) is None
    assert v186.attach_tree_grid_186(_FakeTree()) is None
    assert v186.convert_tree_currency_186(_FakeTree()) is None
    assert v186.retarget_smarttable_186(_FakeTable()) is None


def test_a_contract_is_worth_its_total_until_the_deposits_settle_it():
    """The operator's settlement rule, stated in three cases.

    Before the deposits catch up to what was agreed, the contract's own
    total is the figure - a first instalment does not yet say what a trade
    will end up costing. Once the deposits reach or pass it, the account is
    settled and the true deposits become the figure, whatever was agreed.
    """

    from cost_allocation_stage18_7 import contract_worth

    signed = {'total_amount': '1,435,500,000', 'payments': []}
    assert contract_worth(signed) == 1_435_500_000, 'unpaid: the commitment stands'

    part_paid = dict(signed, payments=[{'amount': '400,000,000'}])
    assert contract_worth(part_paid) == 1_435_500_000, 'a first deposit does not move it'

    settled = dict(signed, payments=[{'amount': '1,435,500,000'}])
    assert contract_worth(settled) == 1_435_500_000

    overpaid = dict(signed, payments=[{'amount': '1,500,000,000'}])
    assert contract_worth(overpaid) == 1_500_000_000, 'settled: the true deposits win'

    no_total = {'total_amount': '', 'payments': [{'amount': '20,000,000'}]}
    assert contract_worth(no_total) == 20_000_000, 'nothing agreed: the deposits are all there is'

    nothing_yet = {'total_amount': '', 'payments': []}
    assert contract_worth(nothing_yet) == 0


def test_a_settled_payment_becomes_a_deposit_on_its_contract_cash_or_cheque():
    """انتخاب قرارداد ties a هزینه ساخت payment to a contract; تسویه posts it.

    'علی‌الحساب' and 'پرداخت‌نشده' are a promise, not a payment. A cheque is
    different: the operator settles the account the moment the last cheque
    is marked تسویه, regardless of whether it has actually cleared - its
    face amount joins واقعی right there, the same as a cash settlement.
    """

    from cost_allocation_stage18_7 import attach_payment_to_contract
    import contractor_store_stage18_7 as store

    with _alloc_project([{'contract_id': 'C1', 'title': 'اجرت اجرای اسکلت',
                          'rows': [], 'payments': []}]) as db:
        base = {'contract_id': 'C1', 'final_amount': 400_000_000,
                'event_date_shamsi': '1405/05/10', 'receiver_name': 'علی رضایی'}

        assert attach_payment_to_contract(dict(base, payment_state='PARTIAL')) is False
        assert attach_payment_to_contract(dict(base, payment_state='UNPAID')) is False
        assert store.paid_total(store.get_contract('C1')) == 0, 'nothing should have posted yet'

        assert attach_payment_to_contract(dict(base, payment_state='PAID')) is True
        assert store.paid_total(store.get_contract('C1')) == 400_000_000

        # A settled cheque, on the same contract, adds its face amount too -
        # its own clearing is a later, separate event this does not wait for.
        assert attach_payment_to_contract(
            dict(base, payment_state='PAID', is_cheque=True, final_amount=200_000_000)) is True
        assert store.paid_total(store.get_contract('C1')) == 600_000_000

        # No contract chosen: the field was left blank, nothing to attach to.
        assert attach_payment_to_contract({'contract_id': '', 'final_amount': 1,
                                           'payment_state': 'PAID'}) is False


def test_the_contract_field_only_means_something_for_پیمانکار():
    """The field appears for پیمانکار and is hidden for مصالح and خدمات.

    Both the wizard's first window and the full record editor toggle it from
    the same رشته, since a payment for materials or services has no contract
    to name.
    """

    wizard_source = _source(ROOT / 'dashboard_stage18_2.py')
    assert "shown.get() == 'پیمانکار'" in wizard_source
    assert 'contract_box.grid_remove()' in wizard_source

    editor_source = _source(ROOT / 'dashboard_stage18.py')
    assert "def _contract_field_sync(self):" in editor_source
    assert "shown.get()=='پیمانکار'" in editor_source

    # It is asked for both هزینه ساخت subtypes, on the wizard's first window,
    # never on any of the pages built from the remaining fields.
    for source_path in ('dashboard_stage18.py', 'dashboard_stage18_1.py'):
        source = _source(ROOT / source_path)
        assert source.count("'contract_id','انتخاب قرارداد','contract'") >= 1 \
            or source.count("'contract_id', 'انتخاب قرارداد', 'contract'") >= 1


def test_a_page_zero_field_survives_leaving_page_zero():
    """دسته‌بندی and انتخاب قرارداد are asked on the wizard's first window and
    nowhere else - every later _show_page clears self.vars, which used to
    carry both of them away with it. A construction cost saved through the
    real multi-page wizard read back with an empty دسته‌بندی until _capture
    was made to save the two before the window that built them is torn down.
    """

    source = _source(ROOT / 'dashboard_stage18_2.py')
    capture = source[source.index('    def _capture(self):'):]
    capture = capture[:capture.index('\n    def ', 10)]
    assert "self.payload['cost_group'] = self.vars['cost_group'].get().strip()" in capture
    assert "self.payload['contract_id']" in capture


def test_closing_an_edit_without_confirming_leaves_the_contract_unchanged():
    """پنجره ویزارد closed without تأیید نهایی must not touch an EXISTING
    contract - retyping a value and pressing ✕ used to save it anyway, the
    moment anything at all had been retyped. A brand-new contract is
    different: nothing has been confirmed for it either, but there is
    nothing on disk yet to protect, and the record window is how a
    contract closed part-way through is carried on - so it still saves on
    any close, exactly as before.
    """

    import tkinter as tk
    import contractor_contracts_stage18_7 as cc
    import contractor_store_stage18_7 as store

    with _alloc_project([{'contract_id': 'C1', 'title': 'اجرت اجرای اسکلت',
                          'family_name': 'پیمانکار اصلی', 'rows': [], 'payments': []}]):
        root = tk.Tk()
        root.withdraw()
        try:
            original = store.get_contract('C1')

            wiz = cc.ContractWizard187(root, rich=None, contract=original)
            wiz._var('family_name').set('دستکاری‌شده - نباید ذخیره شود')
            wiz.close()
            assert store.get_contract('C1')['family_name'] == 'پیمانکار اصلی', \
                'closing an edit without confirming must not have applied it'

            wiz2 = cc.ContractWizard187(root, rich=None, contract=original)
            wiz2._var('family_name').set('تایید شده')
            wiz2.finish()
            assert store.get_contract('C1')['family_name'] == 'تایید شده', \
                'تأیید نهایی is the one place an edit is actually confirmed'

            before = len(store.load_contracts())
            wiz3 = cc.ContractWizard187(root, rich=None)
            wiz3._var('title').set('قرارداد جدید نیمه‌کاره')
            wiz3.close()
            assert len(store.load_contracts()) == before + 1, \
                'a brand-new contract must still be carried on, saved on close'
        finally:
            root.destroy()


def test_a_contracts_paid_total_updates_when_data_entry_refreshes(monkeypatch, tmp_path):
    """Assert the refresh notification, regardless of inheritance strategy."""
    from types import SimpleNamespace
    for key, value in {'TELEGRAM_BOT_TOKEN': 'test-token', 'GEMINI_API_KEY': 'test-key',
                       'ADMIN_USER_ID': '1', 'GROUP_CHAT_ID': '-100777',
                       'STAGE4_SHEETS_ENABLED': 'false',
                       'STAGE4_DB_PATH': str(tmp_path / 'contract-refresh.sqlite3')}.items():
        monkeypatch.setenv(key, value)
    import dashboard_stage18_7 as active
    calls = []
    contractors = SimpleNamespace(refresh=lambda: calls.append('contracts'))
    monkeypatch.setattr(active.v182, 'APPROVAL', SimpleNamespace(list_reviews=lambda **kwargs: []))
    fake = SimpleNamespace(
        rich=SimpleNamespace(hidden_review_ids=lambda: set()),
        filter=SimpleNamespace(get=lambda: 'همه'),
        table=SimpleNamespace(set_rows=lambda rows, render: calls.append(('rows', rows)),
            tree=SimpleNamespace(_barkav_rows=SimpleNamespace(schedule=lambda: calls.append('overlay')))),
        winfo_toplevel=lambda: SimpleNamespace(contractors187=contractors),
        after_idle=lambda fn: None, _pending_review_marker_187=lambda: (),
        _data_entry_sort187='row',
    )
    for name in ('_auto_phase_suggestions', '_update_status_buttons', '_row_colors_185',
                 '_append_data_entry_columns_187', '_fit_data_entry_table_187',
                 '_install_data_entry_row_separators_187', '_scroll_data_entry_right_187',
                 '_refresh_data_entry_counts_187', '_sync_data_entry_checks_187'):
        setattr(fake, name, lambda *args: None)
    fake._row_colors_185 = lambda: calls.append('stripes')
    active.DataEntryCenter187.refresh(fake)
    assert calls == [('rows', []), 'stripes', 'overlay', 'contracts']
    calls.clear(); fake._skip_contractors_refresh187 = True
    active.DataEntryCenter187.refresh(fake)
    assert calls == [('rows', []), 'stripes', 'overlay']


def test_editing_an_already_approved_item_revises_it_instead_of_re_approving():
    """دبل کلیک روی یک هزینه تأییدشده و زدن تأیید used to raise 'این مورد
    دیگر در انتظار تأیید نیست' - save_payload()/approve_v18() both assume
    the item is still awaiting its first approval. submit_v18() checks
    whether a financial_postings row already exists and, if so, revises the
    existing posting through finance_db's own begin_posting_revision() /
    revise_financial_posting() instead of trying to re-approve.
    """

    source = _source(ROOT / 'dashboard_stage18.py')
    assert 'def revise_v18(' in source
    assert 'def submit_v18(' in source

    submit = source[source.index('def submit_v18('):]
    submit = submit[:submit.index('\n# ---', 10)]
    assert 'DB.get_financial_posting(pid)' in submit
    assert 'return revise_v18(pid,payload,rich)' in submit
    assert 'APPROVAL.save_payload(pid,payload,learn=True)' in submit
    assert 'return approve_v18(pid,payload,rich)' in submit

    revise = source[source.index('def revise_v18('):]
    revise = revise[:revise.index('\ndef ', 10)]
    assert 'DB.begin_posting_revision(' in revise
    assert 'DB.revise_financial_posting(' in revise
    assert 'DB.reject_posting_revision(' in revise, \
        'a failed revision must roll back the open revision, not leave it dangling'
    assert 'attach_payment_to_contract(settled,pending_id=pid)' in revise

    # The three GUI call sites (mini-wizard, full editor's تأیید, its
    # ذخیره اصلاحات) must all have moved off the raw save_payload()+
    # approve_v18() pair that only ever worked for a still-pending item.
    assert 'APPROVAL.save_payload(self.pid,p,learn=True);msg=approve_v18' not in source
    assert 'APPROVAL.save_payload(self.pid,self.payload,learn=True);msg=approve_v18' not in source
    assert source.count('msg=submit_v18(') >= 2


def test_a_revised_deposit_replaces_its_earlier_one_instead_of_stacking():
    """attach_payment_to_contract(plan, pending_id=...) is what revise_v18
    calls on a corrected هزینه ساخت - it has to replace the one deposit
    that transaction already left on a contract, not add a second, or a
    correction from 20 to 25 would report 45 paid instead of 25. Moving the
    contract choice, or turning تسویه off, must also take the old deposit
    off the contract it used to sit on.
    """

    from cost_allocation_stage18_7 import attach_payment_to_contract
    import contractor_store_stage18_7 as store

    with _alloc_project([
        {'contract_id': 'C1', 'title': 'اجرت اجرای اسکلت', 'rows': [], 'payments': []},
        {'contract_id': 'C2', 'title': 'جرثقیل', 'rows': [], 'payments': []},
    ]):
        base = {'contract_id': 'C1', 'payment_state': 'PAID',
                'event_date_shamsi': '1405/05/10', 'receiver_name': 'علی رضایی'}

        assert attach_payment_to_contract(dict(base, final_amount=20_000_000), pending_id='PEN1') is True
        assert store.paid_total(store.get_contract('C1')) == 20_000_000

        # Correcting the same transaction's amount replaces its one deposit.
        assert attach_payment_to_contract(dict(base, final_amount=25_000_000), pending_id='PEN1') is True
        c1 = store.get_contract('C1')
        assert store.paid_total(c1) == 25_000_000
        assert len(c1.get('payments') or []) == 1

        # A second, unrelated transaction on the same contract still stacks.
        assert attach_payment_to_contract(
            dict(base, final_amount=5_000_000), pending_id='PEN2') is True
        assert store.paid_total(store.get_contract('C1')) == 30_000_000

        # Correcting PEN1's contract choice from C1 to C2 moves its deposit,
        # not duplicates it - C1 keeps only PEN2's.
        assert attach_payment_to_contract(
            dict(base, contract_id='C2', final_amount=25_000_000), pending_id='PEN1') is True
        assert store.paid_total(store.get_contract('C1')) == 5_000_000
        assert store.paid_total(store.get_contract('C2')) == 25_000_000

        # Turning تسویه off for PEN2 removes its deposit entirely.
        assert attach_payment_to_contract(
            dict(base, payment_state='PARTIAL', final_amount=5_000_000), pending_id='PEN2') is False
        assert store.paid_total(store.get_contract('C1')) == 0


def test_the_contract_wizard_asks_دسته‌بندی_the_same_way_ثبت_دیتا_does():
    """عنوان قرارداد used to read only اجرت/اجرا titles - a contract meant
    پیمانکار and nothing else. مصالح and خدمات contracts read the same
    three-way COST_GROUPS split ثبت دیتا already asks a هزینه ساخت
    transaction for, against the matching tab of the same reference file.
    """

    import contractor_store_stage18_7 as store
    assert store.COST_GROUPS == ('مصالح', 'پیمانکار', 'خدمات')
    assert store.PRICE_CATEGORY_BY_GROUP == {
        'مصالح': 'MATERIAL', 'پیمانکار': 'LABOR', 'خدمات': 'SERVICE'}

    source = _source(ROOT / 'contractor_contracts_stage18_7.py')
    assert 'COST_GROUPS' in source
    assert "self._var('cost_group', 'پیمانکار')" in source
    assert "reference_titles(self.rich, group_var.get())" in source

    plan_rows = source[source.index('def plan_rows_for_title('):]
    plan_rows = plan_rows[:plan_rows.index('\ndef ', 10)]
    assert "cost_group: str = 'پیمانکار'" in plan_rows
    assert 'COST_TYPES.get(cost_group' in plan_rows

    # The record window itself does not show دسته‌بندی at all - it is asked
    # once, at creation, and has no role to play once a contract exists;
    # _repull_from_plan still reads it from self.contract directly.
    documents = source[source.index('    def _page_documents(self, page) -> None:'):]
    documents = documents[:documents.index('\n    def ', 10)]
    assert "'cost_group'" not in documents
    repull = source[source.index('    def _repull_from_plan(self) -> None:'):]
    repull = repull[:repull.index('\n    def ', 10)]
    assert "self.contract.get('cost_group')" in repull


def test_closing_the_wizard_still_opens_the_record_window_on_a_cancelled_edit():
    """The cancel-on-close fix stopped an unconfirmed edit from being
    applied, but closing the wizard is also how the record window is
    reached - both for a brand-new contract and for one whose edit was
    just cancelled, it should still open, just showing the contract
    exactly as it already was rather than the discarded edit. finish()
    already opens it itself through its own on_saved(open_record=False)
    call chained into close() - close() must not pop a second one on top
    when that happens, so it only acts when nothing was saved yet.
    """

    source = _source(ROOT / 'contractor_contracts_stage18_7.py')
    close_body = source[source.index('    def close(self) -> None:'):]
    close_body = close_body[:close_body.index('\n    def ', 10)]
    assert 'if self._saved_once:' in close_body, \
        'closing after finish() already saved must not also fire the reopen branch'
    assert "self.on_saved(self.record, True)" in close_body


def test_a_brand_new_contract_always_opens_its_record_on_close_even_untouched():
    """قرارداد جدید + then closing immediately, with nothing typed at all,
    used to leave neither a saved contract nor a record window - 'a wizard
    opened and shut without a single entry is a mistake, not a contract'.
    The operator wants the opposite: closing قرارداد جدید is always how its
    record window is reached, whatever was or was not typed first.
    """

    source = _source(ROOT / 'contractor_contracts_stage18_7.py')
    save_body = source[source.index('    def _save(self, *, open_record: bool) -> None:'):]
    save_body = save_body[:save_body.index('\n\nclass ', 10)]
    assert '_touched' not in save_body, \
        'a brand-new contract must save on close regardless of whether anything was typed'
    assert 'self._saved_once = True' in save_body

    import tkinter as tk
    import contractor_contracts_stage18_7 as cc
    import contractor_store_stage18_7 as store

    with _alloc_project([]):
        root = tk.Tk()
        root.withdraw()
        try:
            before = len(store.load_contracts())
            wiz = cc.ContractWizard187(root, rich=None)
            wiz.close()  # ✕ immediately, nothing typed at all
            after = store.load_contracts()
            assert len(after) == before + 1, \
                'closing a completely untouched new-contract wizard must still save one'
        finally:
            root.destroy()


def test_changing_دسته‌بندی_after_leaving_اسناد_قرارداد_does_not_touch_destroyed_widgets():
    """دسته‌بندی/عنوان قرارداد live on اسناد قرارداد, but their StringVars are
    self.values entries that outlive that one render - paging forward
    destroys the combo/custom-title widgets their trace_add callbacks close
    over, and nothing ever removed those callbacks. Revisiting اسناد قرارداد
    and changing دسته‌بندی a second time used to throw
    "invalid command name ...searchablecombo187!" from the stale first
    callback (harmless to the operator - Tkinter swallows callback
    exceptions - but real noise on every repeat visit).
    """

    import tkinter as tk
    import contractor_contracts_stage18_7 as cc

    errors = []
    root = tk.Tk()
    root.report_callback_exception = lambda *exc: errors.append(exc)
    try:
        wiz = cc.ContractWizard187(root, rich=None)
        wiz.next_step()  # اسناد قرارداد -> مشخصات پیمانکار, destroying the combo
        wiz.previous_step()  # back to اسناد قرارداد: a fresh combo, a second trace
        wiz._var('cost_group', 'پیمانکار').set('مصالح')
        assert not errors, f'stale trace touched a destroyed widget: {errors}'
    finally:
        wiz.destroy()
        root.destroy()


def test_attach_payment_reads_the_posted_amount_not_the_raw_form_payload():
    """A real contract sat at پرداخت‌شده=0 despite a linked, posted, PAID
    هزینه ساخت: the operator's form still carried final_amount=0 and
    payment_state=PARTIAL (paid_amount covered it, but the وضعیت پرداخت
    combo was never explicitly flipped) - build_posting_plan already
    cascades final_amount from amount and promotes PARTIAL to PAID once
    paid_amount covers it, which is exactly why the posted expense read
    PAID/10,000,000 while attach_payment_to_contract, fed the raw payload
    instead of what was actually posted, still saw PARTIAL/0 and refused.
    """

    source = _source(ROOT / 'dashboard_stage18.py')

    approve = source[source.index('def approve_v18('):]
    approve = approve[:approve.index('\ndef ', 10)]
    assert "settled['final_amount']=plan['final_amount']" in approve
    assert "settled['payment_state']=plan['payment_state']" in approve
    assert 'attach_payment_to_contract(settled,pending_id=pid)' in approve

    revise = source[source.index('def revise_v18('):]
    revise = revise[:revise.index('\ndef ', 10)]
    assert "settled['final_amount']=plan.get('final_amount')" in revise
    assert "settled['payment_state']=plan.get('payment_state')" in revise
    assert 'attach_payment_to_contract(settled,pending_id=pid)' in revise


def test_a_deposits_issuer_is_stored_alongside_its_receiver():
    """attach_payment_to_contract only ever recorded receiver_name - صاحب
    حساب (issuer_name) never reached a deposit even once it existed on the
    posting plan, so واریزی‌ها had nowhere to read it from.
    """

    import cost_allocation_stage18_7 as alloc

    with _alloc_project([{'contract_id': 'C1', 'title': 'اجرت اجرای اسکلت',
                          'rows': [], 'payments': []}]) as db:
        assert alloc.attach_payment_to_contract(
            {'contract_id': 'C1', 'payment_state': 'PAID', 'final_amount': 1000,
             'event_date_shamsi': '1405/06/12', 'receiver_name': 'ابراهیم ازبک',
             'issuer_name': 'علی رضایی'},
            pending_id='PEN-1')
        contract = db.folder and json.loads(
            (db.folder / 'contractor_contracts_18_7.json').read_text(encoding='utf-8'))
        deposit = contract['contracts'][0]['payments'][0]
        assert deposit['receiver'] == 'ابراهیم ازبک'
        assert deposit['issuer'] == 'علی رضایی'


def test_contract_detail_window_matches_the_four_requested_fixes():
    """Four things reported against a real screenshot of this window:

    1. ردیف‌های قرارداد's box used to stretch with expand=True regardless of
       how many rows it actually had, leaving a wide empty gap under the last
       one - it now ends where the last row does.
    2. واریزی‌ها had no صاحب حساب column, and its گیرندهٔ حساب heading read as
       two words for one thing (a card's operator, not the account itself).
       Both PAYMENT_COLUMNS and each rendered card must show the fix.
    3. The summary line had no wraplength, so a tk.Label never wraps it - it
       just keeps going past the window's right-to-left edge until the rest
       is clipped off-screen. justify='right' never had a second line to
       apply to until wrapping existed at all.
    4. Three literal PDF/Excel/چاپ action buttons stood in for what قراردادها's
       own tab already solved with one control: a placeholder-default dropdown
       named انتخاب فرمت خروجی, reset to itself after firing.
    """

    import tkinter as tk
    from tkinter import ttk
    import contractor_contracts_stage18_7 as cc
    import dashboard_stage18_6 as m186
    from PIL import Image as PILImage

    assert cc.PAYMENT_COLUMNS == (
        ('no', 'ردیف'), ('date', 'تاریخ'), ('amount', 'مبلغ واریزی (تومان)'),
        ('receiver', 'گیرنده'), ('issuer', 'صاحب حساب'),
    )

    tmp = tempfile.mkdtemp()
    try:
        img_path = os.path.join(tmp, 'receipt.jpg')
        PILImage.new('RGB', (40, 60), color=(1, 2, 3)).save(img_path)
        m186.DB.register_telegram_message(chat_id=-777, message_id=990001, raw_text='x',
                                          content_type='TEXT', message_date='2026-09-05T10:00:00')
        pid = m186.DB.create_or_replace_pending(
            telegram_chat_id=-777, telegram_message_id=990001, detected_type='EXPENSE',
            payload={}, confidence=.9, status='APPROVED')
        m186.DB.upsert_receipt_analysis(pending_id=pid, provider='TEST', image_path=img_path)
        assert cc._receipt_image_path(pid) == img_path
        assert cc._receipt_image_path('NO-SUCH-PENDING-ID') == ''

        contract = {
            'contract_id': 'C1', 'contract_number': 'CN-1', 'title': 'اجرت اجرای اسکلت',
            'family_name': 'ابراهیم ازبک', 'total_amount': '1339800000',
            'rows': [{'description': 'اجرت اجرای اسکلت', 'unit_price': '750000',
                     'quantity': '1914', 'line_total': '1339800000'}],
            'payments': [{'date': '1405/06/12', 'amount': '10000000',
                         'receiver': 'ابراهیم ازبک', 'issuer': 'علی رضایی', 'pending_id': pid}],
        }

        root = tk.Tk()
        root.withdraw()
        try:
            win = cc.ContractDetailWindow187(root, contract=contract, on_export=lambda *a: None)
            root.update()
            try:
                # 1. One row -> the tree asks for exactly one row of height.
                def find_all(widget, kind):
                    found = []
                    for child in widget.winfo_children():
                        if isinstance(child, kind):
                            found.append(child)
                        found.extend(find_all(child, kind))
                    return found

                tables = find_all(win.body, cc.DataTable)
                assert len(tables) == 1, 'only ردیف‌های قرارداد should still be a DataTable'
                assert int(tables[0].tree.cget('height')) == 1

                # 2. صاحب حساب/گیرنده show on the rendered card, and its
                # receipt loaded a real image rather than the placeholder.
                labels = find_all(win.body, tk.Label)
                texts = [str(lbl.cget('text') or '') for lbl in labels]
                assert any(t.strip() == 'صاحب حساب:' for t in texts)
                assert any(t.strip() == 'گیرنده:' for t in texts)
                assert not any('گیرندهٔ حساب' in t for t in texts)
                assert not any(t == 'رسیدی ثبت نشده' for t in texts), \
                    'a deposit with a real receipt must not fall back to the empty placeholder'

                # 3. The summary line wraps instead of being clipped.
                summary_labels = [lbl for lbl in labels if 'شماره قرارداد' in str(lbl.cget('text') or '')]
                assert summary_labels and int(summary_labels[0].cget('wraplength')) > 0

                # 4. One placeholder-default dropdown, not three literal buttons.
                combos = find_all(win.body, ttk.Combobox)
                assert len(combos) == 1
                assert combos[0].get() == cc.EXPORT_PROMPT_187
                assert set(combos[0].cget('values')) == {cc.EXPORT_PROMPT_187, *cc.EXPORT_FORMATS_187}
                footer_labels = {str(child.cget('text')) for child in win.footer.winfo_children()}
                assert footer_labels == {'بستن'}, \
                    'PDF/Excel/چاپ must be gone from the footer, replaced by the dropdown'
            finally:
                win.destroy()
        finally:
            root.destroy()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_the_summary_line_is_two_short_lines_not_one_that_might_wrap_mid_word():
    """A single long line relied on tk.Label's own word-wrap once wraplength
    existed at all - which does not treat the ZWNJ inside «پرداخت‌شده» as
    non-breaking, so the word could split there and its tail resurface
    ahead of the rest of the line. Two lines short enough on real data to
    never need that automatic break avoid it outright.
    """

    source = _source(ROOT / 'contractor_contracts_stage18_7.py')
    build = source[source.index('    def _build(self) -> None:'):]
    build = build[:build.index('\n    def _build_payments', 10)]
    assert "پیمانکار: {self.contract.get('family_name') or '-'}\\n" in build
    assert 'wraplength=1300' in build


def test_a_deposits_receipt_thumbnail_is_a6_proportioned():
    import contractor_contracts_stage18_7 as cc

    width, height = cc.RECEIPT_THUMB_SIZE
    # A6 is 105x148mm - within a couple of percent of √2, same as every
    # other ISO paper-size step; a wrong constant here would drift further.
    assert abs((height / width) - (148 / 105)) < 0.02


def test_the_pdf_export_includes_rows_deposits_and_receipt_images():
    """قراردادها's shared list export writes only five summary fields for
    every sub-tab alike - a real screenshot of that PDF showed exactly that
    and nothing else. PDF/چاپ from this window must write its own richer
    document instead: the summary, ردیف‌های قرارداد, واریزی‌ها and each
    deposit's own receipt image, or a viewer opens the same thin export the
    bug was filed against.
    """

    import contractor_contracts_stage18_7 as cc
    import dashboard_stage18_6 as m186
    from PIL import Image as PILImage

    export_body = _source(ROOT / 'contractor_contracts_stage18_7.py')
    method = export_body[export_body.index('    def _export(self, fmt: str) -> None:'):]
    method = method[:method.index('\n    def _export_pdf', 10)]
    assert "self._export_pdf(print_after=fmt == 'print', preview=True" in method
    assert "self._save_detail_export(choice, selected_orientation" in export_body

    tmp = tempfile.mkdtemp()
    try:
        img_path = os.path.join(tmp, 'receipt.jpg')
        PILImage.new('RGB', (400, 600), color=(10, 20, 30)).save(img_path)
        m186.DB.register_telegram_message(chat_id=-654, message_id=321001, raw_text='x',
                                          content_type='TEXT', message_date='2026-09-05T10:00:00')
        pid = m186.DB.create_or_replace_pending(
            telegram_chat_id=-654, telegram_message_id=321001, detected_type='EXPENSE',
            payload={}, confidence=.9, status='APPROVED')
        m186.DB.upsert_receipt_analysis(pending_id=pid, provider='TEST', image_path=img_path)

        contract = {
            'contract_id': 'C2', 'contract_number': 'CN-2', 'title': 'اجرت اجرای اسکلت',
            'family_name': 'ابراهیم ازبک', 'total_amount': '1339800000',
            'rows': [{'description': 'اجرت اجرای اسکلت', 'unit_price': '750000', 'quantity': '1914',
                     'estimate_price': '', 'estimate_quantity': '', 'line_total': '1339800000',
                     'estimate_total': ''}],
            'payments': [{'date': '1405/06/12', 'amount': '10000000', 'receiver': 'ابراهیم ازبک',
                         'issuer': 'علی رضایی', 'pending_id': pid}],
        }
        out_pdf = Path(tmp) / 'out.pdf'
        cc._export_contract_detail_pdf(out_pdf, contract)

        assert out_pdf.exists() and out_pdf.stat().st_size > 0
        data = out_pdf.read_bytes()
        assert b'/Image' in data, 'the receipt must be embedded as a real PDF image object'
        assert b'/DCTDecode' in data, 'a JPEG receipt must round-trip as one, not be dropped'
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
