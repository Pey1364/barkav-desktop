"""«بروزرسانی قیمت‌ها» on a real Tk root, against the operator's reference workbook.

Opt-in like every other GUI test here (``BARKAV_RUN_UI_TESTS=1``), and the
workbook itself is private project data outside the repository, so these
also skip on a machine that does not have it.
"""

from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.environ.get('BARKAV_RUN_UI_TESTS') != '1', reason='GUI tests opt-in')

REAL_REFERENCE = Path(os.environ.get('BARKAV_REAL_REFERENCE_WORKBOOK', ''))
needs_real_reference = pytest.mark.skipif(not REAL_REFERENCE.is_file(),
                                          reason='reference workbook not on this machine')


@pytest.fixture()
def panel(tmp_path: Path, monkeypatch):
    import price_update_stage18_7 as module
    from budget_rich_v163 import RichBudgetService
    from finance_db import FinanceDB
    from price_update_service import PriceUpdateService

    # The operator's own تنظیمات must not leak into what the test expects.
    monkeypatch.setattr(module, '_app_settings', lambda: {})
    # Nor may a run write the wizard's AI choice into the operator's ui.json.
    monkeypatch.setattr(module.PriceUpdateRunWizard187, '_remember_ai_choice', lambda self: None)
    db = FinanceDB(tmp_path / 'project.sqlite3')
    RichBudgetService(db, tmp_path).import_workbook(REAL_REFERENCE)
    root = tk.Tk()
    root.geometry('1400x800')
    try:
        widget = module.PriceUpdatePanel187(root, service=PriceUpdateService(db, tmp_path), rich_db=db)
        widget.pack(fill='both', expand=True)
        root.update()
        yield widget
    finally:
        root.destroy()


def _texts(frame: tk.Misc) -> list[str]:
    return [str(w.cget('text')) for w in frame.winfo_children() if 'text' in w.keys()]


@needs_real_reference
def test_row_actions_sit_on_the_toolbar_right_of_the_display_filter(panel):
    toolbar_texts = _texts(panel.table.toolbar)
    for label in ('افزودن', 'ویرایش', 'کپی', 'حذف', 'نمایش بر اساس'):
        assert label in toolbar_texts
    assert not {'افزودن', 'ویرایش', 'کپی', 'حذف'} & set(_texts(panel.table.actionbar))
    buttons = {str(w.cget('text')): w for w in panel.table.toolbar.winfo_children() if 'text' in w.keys()}
    caption = buttons['نمایش بر اساس']
    for label in ('افزودن', 'ویرایش', 'کپی', 'حذف'):
        assert buttons[label].winfo_ismapped()
        # RTL: every row action is further right than the filter's caption.
        assert buttons[label].winfo_rootx() > caption.winfo_rootx()
    assert buttons['افزودن'].winfo_rootx() > buttons['حذف'].winfo_rootx()


@needs_real_reference
def test_opening_the_tab_fills_methods_details_and_rules_from_the_reference_workbook(panel):
    import price_update_stage18_7 as module

    items = panel.service.list_catalog_items()
    assert len(items) == 456 and all(item['calc_method'] for item in items)
    assert len(panel.table.sorted_rows()) == 456

    details = module.DetailsWindow187(panel, panel.service)
    try:
        rows = details.table.sorted_rows()
        assert len(rows) == 456
        basis = [row[13] for row in rows]
        assert sum(1 for text in basis if text != '-') > 400
    finally:
        details.close()

    rules = module.CalcRulesWindow187(panel, panel.service)
    try:
        rule_rows = rules.table.sorted_rows()
        assert len(rule_rows) > 40
        assert any('ممنوعیت ضریب کاهشی' == row[3] for row in rule_rows)
    finally:
        rules.close()


@needs_real_reference
def test_run_wizard_opens_with_the_workbook_parameters_and_an_rtl_header(panel):
    import price_update_stage18_7 as module
    from ui_stage18_3 import fa

    wizard = module.PriceUpdateRunWizard187(panel, panel.service, panel.rich_db, on_done=lambda _r: None)
    try:
        assert wizard._progress_label.master.pack_info()['side'] == 'right'
        assert wizard._step_title_label.cget('text') == 'تاریخ براورد'
        wizard.show_step(module.PARAMETERS_STEP_187)
        assert wizard._step_title_label.cget('text') == 'پارامترها'
        usd = wizard.param_vars['usd']
        assert usd['base'].get() == fa('150,000')
        assert usd['current'].get() == fa('232,500')
        assert wizard.param_vars['copper']['base'].get() == fa('2,003,030')
        assert wizard.param_vars['months_elapsed']['current'].get() == fa('5')
    finally:
        wizard.close()


@needs_real_reference
def test_rules_and_details_filter_by_category_and_phase_and_start_at_the_wizard_scope(panel):
    import price_update_stage18_7 as module

    # From the table's own buttons: «همه».
    rules = module.CalcRulesWindow187(panel, panel.service)
    try:
        assert 'روش محاسبه' not in _texts(rules.table.toolbar)
        assert 'نمایش بر اساس' in _texts(rules.table.toolbar)
        assert rules.scope.category is None and rules.scope.phase is None
        everything = len(rules.table.sorted_rows())
    finally:
        rules.close()

    # From the wizard: its «دامنه اجرا».
    wizard = module.PriceUpdateRunWizard187(panel, panel.service, panel.rich_db, on_done=lambda _r: None)
    try:
        wizard.category_var.set('مصالح')
        wizard.phase_var.set(module.phase_label('22'))
        rules = module.CalcRulesWindow187(wizard, panel.service, category=wizard.selected_category(),
                                          phase=wizard.selected_phase())
        try:
            assert rules.scope.category == 'MATERIAL' and rules.scope.phase == '22'
            scoped = rules.table.sorted_rows()
            assert 0 < len(scoped) < everything
            assert {row[2] for row in scoped} <= {'مصالح', 'همه دسته‌ها'}
        finally:
            rules.close()
        details = module.DetailsWindow187(wizard, panel.service, category=wizard.selected_category(),
                                          phase=wizard.selected_phase())
        try:
            rows = details.table.sorted_rows()
            assert rows and all(row[2] == 'مصالح' for row in rows)
            # A shared item («07,22») belongs to phase 22 too, even if listed under its first phase.
            assert all('22' in item['phase_codes'].split(',') for item in details._by_key.values())
            details.scope.category_var.set(module.ALL_LABEL)
            details.scope._category_changed()
            details.scope.phase_var.set(module.ALL_LABEL)
            details._refresh()
            assert len(details.table.sorted_rows()) == 456
        finally:
            details.close()
    finally:
        wizard.close()


@needs_real_reference
def test_every_export_on_the_tab_opens_the_shared_preview(panel, monkeypatch):
    import price_update_stage18_7 as module
    import sales_claims_stage18_7

    opened = []
    monkeypatch.setattr(sales_claims_stage18_7, 'show_export_preview_187',
                        lambda parent, **kw: opened.append(kw['title']))
    panel.output_format_var.set('PDF')
    panel._export()
    details = module.DetailsWindow187(panel, panel.service)
    try:
        details.output_format_var.set('Excel')
        details.table.toolbar  # the control lives on the toolbar
        module.preview_export(details, details.output_format_var, ['a'], [['1']], 'جزئیات بروزرسانی')
    finally:
        details.close()
    assert opened == ['پیش‌نمایش بروزرسانی قیمت‌ها', 'پیش‌نمایش جزئیات بروزرسانی']
    assert panel.output_format_var.get() == module.EXPORT_PLACEHOLDER


@needs_real_reference
def test_rules_category_filter_shows_only_that_categorys_rules(panel):
    import price_update_stage18_7 as module

    rules = module.CalcRulesWindow187(panel, panel.service)
    try:
        for label in ('مصالح', 'پیمانکار', 'خدمات'):
            rules.scope.category_var.set(label)
            rules.scope._category_changed()
            shown = {row[2] for row in rules.table.sorted_rows()}
            assert shown == {label}
    finally:
        rules.close()


@needs_real_reference
def test_scope_step_offers_one_item_of_the_chosen_category_and_runs_only_it(panel):
    import price_update_stage18_7 as module

    wizard = module.PriceUpdateRunWizard187(panel, panel.service, panel.rich_db, on_done=lambda _r: None)
    try:
        wizard.show_step(module.SCOPE_STEP_187)
        assert wizard.item_combo.cget('values') == (module.ALL_LABEL,) or \
            tuple(wizard.item_combo.cget('values')) == (module.ALL_LABEL,)
        wizard.category_var.set('مصالح')
        wizard._scope_category_changed()
        options = tuple(wizard.item_combo.cget('values'))
        cement = next(label for label in options if label == '۰۷-سیمان')
        wizard.item_var.set(cement)
        assert len(wizard.scope_items()) == 1
        target = wizard.selected_item()
        before = {i['price_id']: i['updated_at'] for i in panel.service.list_catalog_items()}
        wizard.show_step(module.PARAMETERS_STEP_187)
        assert wizard.validate_step(module.PARAMETERS_STEP_187)
        assert wizard._result is None  # the run waits for the AI step
        wizard.ai_mode_var.set(module.ai_research.PRICE_AI_MODES['OFF'])
        assert wizard.validate_step(module.AI_STEP_187)
        assert wizard._result.item_count == 1
        after = {i['price_id']: i['updated_at'] for i in panel.service.list_catalog_items()}
        assert {k for k in after if after[k] != before[k]} <= {target}
    finally:
        wizard.close()


@needs_real_reference
def test_item_boxes_read_phase_then_name_and_narrow_details_and_rules_to_one_item(panel):
    import price_update_stage18_7 as module

    labels = module.item_option_map(panel.service, 'MATERIAL', None)
    assert '۰۸-میلگرد Ø۸' in labels and '۰۷-سیمان' in labels  # «فاز-نام», Persian digits
    assert len(labels) == 282  # every مصالح item, duplicates told apart

    details = module.DetailsWindow187(panel, panel.service)
    try:
        assert str(details.scope.item_combo.cget('state')) == 'disabled'  # no دسته‌بندی yet
        details.scope.category_var.set('مصالح')
        details.scope._category_changed()
        details.scope.item_var.set('۰۷-سیمان')
        details._refresh()
        rows = details.table.sorted_rows()
        assert [row[3] for row in rows] == ['سیمان']
    finally:
        details.close()

    cement = labels['۰۷-سیمان']
    rules = module.CalcRulesWindow187(panel, panel.service, category='MATERIAL', item=cement)
    try:
        assert rules.scope.item == cement
        shown = rules.table.sorted_rows()
        # First the item's own rule, then the workbook rule named after it,
        # then only rules that are about cement -- nothing unrelated.
        assert shown[0][3] == 'قانون اختصاصی: سیمان' and shown[1][3] == 'سیمان'
        assert {row[2] for row in shown} == {'مصالح'}
        assert all('سیمان' in f'{row[3]} {row[6]}' for row in shown[1:])
    finally:
        rules.close()


@needs_real_reference
def test_rules_window_shows_phase_names_and_persian_digits(panel):
    import price_update_stage18_7 as module

    rules = module.CalcRulesWindow187(panel, panel.service, category='MATERIAL')
    try:
        rows = {row[3]: row for row in rules.table.sorted_rows()}
        assert rows['بتن'][5] == '۰۸ - اسکلت'            # phase number and name
        assert rows['آهن‌آلات'][5] == 'همه فازها'
        assert all(not any(ch.isascii() and ch.isdigit() for ch in ''.join(row)) for row in rows.values())
    finally:
        rules.close()


@needs_real_reference
def test_option_editor_rewrites_an_items_method_and_options(panel):
    import json
    import price_update_stage18_7 as module
    import price_calc_engine as calc

    cement = module.item_option_map(panel.service, 'MATERIAL', None)['۰۷-سیمان']
    item = panel.service.get_catalog_item(cement)
    saved = []
    dialog = module.RuleOptionsDialog187(panel, panel.service, item=item, on_saved=lambda: saved.append(1))
    assert dialog.method_var.get() == calc.METHOD_WEB
    assert str(dialog.sections['web'].winfo_manager()) == 'pack'
    assert not dialog.sections['weights'].winfo_manager()
    dialog.vars['carry_rate'].set('۰.۱۵')
    dialog.web_price_vars[0].set('۲۵۰,۰۰۰')
    dialog._save()
    params = json.loads(panel.service.get_catalog_item(cement)['calc_params_json'])
    assert saved and params['carry_rate'] == 0.15 and params['web_prices'][0] == 250_000

    item = panel.service.get_catalog_item(cement)
    dialog = module.RuleOptionsDialog187(panel, panel.service, item=item, on_saved=lambda: None)
    dialog.method_var.set(calc.METHOD_OTHER)
    dialog._sync_sections()
    dialog.choice_vars['index'][0].set('ضریب رشد دلار')
    dialog._save()
    changed = panel.service.get_catalog_item(cement)
    assert changed['calc_method'] == calc.METHOD_OTHER
    assert json.loads(changed['calc_params_json'])['index'] == 'usd'


@needs_real_reference
def test_general_rules_window_lists_parameters_and_whole_catalog_rules(panel):
    import price_update_stage18_7 as module

    window = module.GeneralRulesWindow187(panel, panel.service)
    try:
        params = {row[0]: row for row in window.params_table.sorted_rows()}
        assert params['نرخ دلار آزاد'][2] == '۱۵۰,۰۰۰' and params['نرخ دلار آزاد'][5] == '۱.۵۵۰۰'
        topics = [row[2] for row in window.rules_table.sorted_rows()]
        assert 'کف حداقل حقوق پیمانکار' in topics and 'ممنوعیت ضریب کاهشی' in topics
        window.category_var.set('خدمات')
        window._refresh()
        catalogs = {row[1] for row in window.rules_table.sorted_rows()}
        assert catalogs <= {'همه دسته‌ها', 'خدمات'}
    finally:
        window.close()


@needs_real_reference
def test_one_items_rules_are_only_those_of_its_own_phase(panel):
    import price_update_stage18_7 as module

    labels = module.item_option_map(panel.service, 'MATERIAL', '08')
    rebar = next(price_id for label, price_id in labels.items() if 'بیشتر از' in label)
    rules = module.CalcRulesWindow187(panel, panel.service, category='MATERIAL', phase='08', item=rebar)
    try:
        rows = rules.table.sorted_rows()
        assert rows[0][3].startswith('قانون اختصاصی')
        assert all(row[5].startswith('۰۸') or '، ۰۸' in row[5] for row in rows)  # phase 08 only
        topics = {row[3] for row in rows}
        assert 'گیره و قلاب' not in topics and 'آهن‌آلات' not in topics
    finally:
        rules.close()


@needs_real_reference
def test_general_rules_top_actions_follow_the_selected_table_and_show_phase_scope(panel, monkeypatch):
    import price_update_stage18_7 as module

    monkeypatch.setattr(module.messagebox, 'askyesno', lambda *a, **k: True)
    monkeypatch.setattr(module.messagebox, 'showinfo', lambda *a, **k: None)
    window = module.GeneralRulesWindow187(panel, panel.service, category='MATERIAL')
    try:
        texts = [str(w.cget('text')) for w in window.body.winfo_children()[0].winfo_children()]
        assert {'افزودن', 'ویرایش', 'حذف'} <= set(texts)
        params = {row[0]: row for row in window.params_table.sorted_rows()}
        assert '۲۵' in params['نرخ دلار آزاد'][6]          # UPVC, phase 25, follows the dollar
        assert '۱۶' in params['قیمت مس کاتد'][6]           # duct split, phase 16
        rules = window.rules_table.sorted_rows()
        cement = next(row for row in rules if row[2].endswith('-سیمان'))
        assert cement[2].startswith('۰۷')                   # phase beside the item's name
        assert all(row[3] != '—' for row in rules)          # every rule states its phases

        # Parameters: add an optional one, then delete it; the built-ins stay.
        window.params_table.tree.selection_set(window.params_table.tree.get_children()[0])
        window._activate('params')
        dialog = module.ParameterDialog187(window, panel.service, None, on_saved=window._after_change)
        dialog.kind_var.set(panel.service.OPTIONAL_PARAMETERS['inflation_rate'])
        dialog.vars['current'].set('۱.۲')
        dialog._save()
        assert panel.service.get_parameter('inflation_rate')['current_value'] == 1.2
        assert panel.service.growth_context()['inflation_rate'] == 1.2
        keys = window.params_table.sorted_rows()
        window.params_table.tree.selection_set(
            [iid for iid in window.params_table.tree.get_children()
             if window.params_table.tree.item(iid, 'values') and 'تورم' in ''.join(window.params_table.tree.item(iid, 'values'))])
        window._activate('params')
        window._delete()
        assert panel.service.get_parameter('inflation_rate') is None
        with pytest.raises(ValueError):
            panel.service.delete_parameter('usd')

        # Rules: the same buttons now act on the lower table.
        tree = window.rules_table.tree
        stored = next(iid for iid in tree.get_children() if 'ثبت‌شده' in ''.join(tree.item(iid, 'values')))
        tree.selection_set(stored)
        window._activate('rules')
        before = len(panel.service.list_calc_rules())
        window._delete()
        assert len(panel.service.list_calc_rules()) == before - 1
        assert len(keys) >= 4
    finally:
        window.close()


def _fake_catalog(research):
    info = research.ModelInfo
    return [
        info('GEMINI', 'Gemini', 'Google', research.ROLE_SEARCH, 'g', '', 'K1', True, free=True),
        info('OPENROUTER:QWEN', 'Qwen', 'Openrouter', research.ROLE_CHECK, 'q', '', 'K2', True, free=True),
        info('BASETEN:KIMI', 'Kimi', 'Baseten', research.ROLE_CHECK, 'k', '', 'K3', True),
        info('OPENAI', 'OpenAI', 'OpenAI', research.ROLE_CHECK, 'o', '', 'K4', False),
    ]


@needs_real_reference
def test_step_five_lists_every_model_with_status_and_ticks_follow_the_mode(panel, monkeypatch):
    import price_update_stage18_7 as module
    research = module.ai_research

    monkeypatch.setattr(research, 'model_catalog', lambda _base: _fake_catalog(research))
    wizard = module.PriceUpdateRunWizard187(panel, panel.service, panel.rich_db, on_done=lambda _r: None)
    try:
        assert wizard.step_titles[module.AI_STEP_187] == 'مدل هوش مصنوعی'
        assert wizard.step_titles[module.SUMMARY_STEP_187] == 'اجرا و خلاصه'
        wizard.show_step(module.PARAMETERS_STEP_187)
        wizard.show_step(module.AI_STEP_187)
        rows = wizard.ai_table.sorted_rows()
        assert len(rows) == 4
        assert rows[3][-1] == 'غیرفعال (کلید ندارد)' and rows[0][-1] == 'فعال'
        # خودکار: Gemini + the free checker, never the paid or the key-less one.
        assert wizard.ai_selected() == ['GEMINI', 'OPENROUTER:QWEN']
        assert sorted(wizard.ai_table.selected_keys()) == ['GEMINI', 'OPENROUTER:QWEN']
        assert tuple(wizard.ai_mode_combo.cget('values')) == tuple(research.PRICE_AI_MODES.values())

        # Ticking a paid engine by hand switches to «فقط مدل‌های انتخاب‌شده».
        tree = wizard.ai_table.tree
        tree.selection_add(tree.get_children()[2])
        wizard._ai_ticks_changed()
        panel.update()
        assert wizard.ai_mode() == 'SELECTED'
        assert wizard.ai_selected() == ['GEMINI', 'OPENROUTER:QWEN', 'BASETEN:KIMI']
        # The key-less engine cannot be ticked.
        tree.selection_add(tree.get_children()[3])
        wizard._ai_ticks_changed()
        panel.update()
        assert 'OPENAI' not in wizard.ai_selected()

        wizard.ai_mode_var.set(research.PRICE_AI_MODES['OFF'])
        wizard._ai_mode_changed()
        assert wizard.ai_selected() == [] and wizard.ai_table.selected_keys() == []
    finally:
        wizard.close()


@needs_real_reference
def test_ai_research_is_advisory_until_a_row_is_applied(panel, monkeypatch):
    import price_update_stage18_7 as module
    research = module.ai_research

    class Grounded:
        def fetch_grounded_value(self, prompt):
            value = 10_000.0 if 'مس' in prompt else 45.0 if 'دستمزد' in prompt else 150_000.0
            return research.GroundedResult(value, 'ok', ['https://example.test/a'])

    class Checker:
        def check_plausible(self, value, context):
            return research.SanityCheckResult('Qwen', 'مس' not in context, 'x')

    monkeypatch.setattr(research, 'model_catalog', lambda _base: _fake_catalog(research))
    monkeypatch.setattr(research, 'build_clients', lambda _base, _ids: (Grounded(), [Checker()]))
    wizard = module.PriceUpdateRunWizard187(panel, panel.service, panel.rich_db, on_done=lambda _r: None)
    try:
        wizard.show_step(module.PARAMETERS_STEP_187)
        assert wizard.validate_step(module.PARAMETERS_STEP_187)
        wizard.show_step(module.AI_STEP_187)
        before = panel.service.get_parameter('usd')['current_value']
        wizard._start_ai_research()
        for _ in range(100):
            panel.update()
            if not wizard._ai_busy:
                break
            panel.after(50)
        assert not wizard._ai_busy
        rows = {row[0]: row for row in wizard.ai_results_table.sorted_rows()}
        assert set(rows) == set(module.AI_PARAMETER_LABELS.values())
        assert rows['نرخ دلار آزاد'][2] == module.fa('150,000')
        assert 'عدم توافق' in rows['قیمت مس'][4]
        assert panel.service.get_parameter('usd')['current_value'] == before  # nothing applied yet

        tree = wizard.ai_results_table.tree
        order = [key for _r, _s, key in wizard.ai_results_table._sorted()]
        tree.selection_set(tree.get_children()[order.index('usd')])
        wizard._apply_ai_result()
        assert panel.service.get_parameter('usd')['current_value'] == 150_000
        assert panel.service.get_parameter('usd')['source'] == 'ai'
        assert wizard.param_vars['usd']['current'].get() == module.fa('150,000')
    finally:
        wizard.close()


@needs_real_reference
def test_months_elapsed_is_suggested_from_the_last_run_and_the_new_date(panel):
    import price_update_stage18_7 as module

    service = panel.service
    service.save_parameter('months_elapsed', base_value=0, previous_value=0, current_value=5)
    service.run_update(estimate_date_shamsi='1405/01/15')
    wizard = module.PriceUpdateRunWizard187(panel, service, panel.rich_db, on_done=lambda _r: None)
    try:
        wizard.date_var.set('1405/01/20')
        assert wizard.suggested_months_elapsed() is None   # same month: nothing to add
        wizard.date_var.set('1405/04/15')
        assert wizard.suggested_months_elapsed() == (8, '1405/01/15')
        service.save_parameter('months_elapsed', base_value=0, previous_value=5, current_value=9)
        assert wizard.suggested_months_elapsed() is None   # already raised past it
    finally:
        wizard.close()
