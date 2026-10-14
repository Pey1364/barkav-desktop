import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'dashboard_stage18_7.py').read_text(encoding='utf-8')


def test_daily_report_rows_include_workforce_weather_and_phases_in_window_two():
    assert "'گزارش روزانه': [['report_date_shamsi', 'report_row_count', 'report_contractor_count'" in SOURCE
    assert "'report_daily_wage_count', 'report_machinery', 'report_weather'" in SOURCE
    assert "('main_phase', 'فاز اصلی'), ('sub_phase', 'فاز فرعی')" in SOURCE
    assert "text='ردیف'" in SOURCE
    assert "text='شرح'" in SOURCE
    assert "_refresh_report_rows_187(self)" in SOURCE


def test_daily_report_confirmation_uses_the_row_count_summary():
    assert "def _daily_report_summary_187(count: int)" in SOURCE
    assert "return f'تعداد {display} ردیف گزارش روزانه ثبت شد'" in SOURCE
    assert "count = len(rows) or parse_int(payload.get('report_row_count'))" in SOURCE

    tree = ast.parse(SOURCE)
    function = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef)
                    and node.name == '_daily_report_summary_187')
    namespace = {
        'fa': lambda value: str(value),
        '_PERSIAN_COUNT_WORDS_187': {2: 'دو'},
    }
    exec(compile(ast.Module(body=[function], type_ignores=[]), '<summary>', 'exec'), namespace)
    assert namespace['_daily_report_summary_187'](2) == 'تعداد دو ردیف گزارش روزانه ثبت شد'
    assert namespace['_daily_report_summary_187'](11) == 'تعداد 11 ردیف گزارش روزانه ثبت شد'


def test_nonfinancial_wizard_uses_shared_rtl_date_picker_and_native_caption():
    assert 'class WizardDateField187(v182.DateField)' in SOURCE
    assert 'return ShamsiDatePicker187(self, self.variable)' in SOURCE
    assert 'ShamsiDatePicker187' in SOURCE
    assert 'self.resizable(True, True)' in SOURCE
    assert '_enable_caption_controls_187(self)' in SOURCE
    assert 'GWL_EXSTYLE' in SOURCE
    assert 'v182.TransactionWizard182._build_shell = _wizard_build_shell_187' in SOURCE


def test_document_page_two_has_a_working_previous_navigation_path():
    assert 'def _wizard_prev_187(self):' in SOURCE
    assert 'self.page_index = max(0, self.page_index - 1)' in SOURCE
    assert 'v182.TransactionWizard182.prev = _wizard_prev_187' in SOURCE


def test_active_wizard_keeps_transferred_fields_safe_on_windows():
    assert 'ctypes.c_long((int(style) | caption_controls)' in SOURCE
    assert 'v18._ai_value(self.ai_original, fd.key)' in SOURCE
    assert 'def _wizard_capture_187(self):' in SOURCE
    assert '_ORIGINAL_WIZARD_CAPTURE_187(self)' in SOURCE
    assert 'v182.TransactionWizard182._capture = _wizard_capture_187' in SOURCE


def test_data_entry_uses_claude_semantic_palette_not_transaction_family_tags():
    assert "background=p['row_even']" in SOURCE
    assert "background=p['row_odd']" in SOURCE
    assert "data_entry_{state}" in SOURCE
    assert "data_entry_{state}_text" in SOURCE
    assert "not str(tag).startswith('tx183_')" in SOURCE
    assert "status_by_value" in SOURCE
