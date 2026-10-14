from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import budget_rich_v163 as budget_module
from budget_rich_v163 import RichBudgetService
from finance_db import FinanceDB


@pytest.mark.parametrize('overall_sheet', ['براورد کلی', 'برآورد کلی'])
def test_overall_estimate_import_preserves_row_order(monkeypatch, overall_sheet):
    """The consolidated sheet is enough to populate every management row."""
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / 'overall.xlsx'
        source.write_bytes(b'fixture')
        rows = [
            ['برآورد کلی'],
            [None, 'ردیف', 'عنوان', 'فاز اجرایی', 'واحد', 'قیمت واحد-اولیه',
             'قیمت واحد-بروز', 'قیمت واحد-واقعی', 'مقدار-اولیه', 'مقدار-بروز',
             'مقدار-واقعی', 'مبلغ کل-اولیه', 'مبلغ کل-بروز', 'مبلغ کل-واقعی'],
            [None, 'فاز 01 — خرید زمین'],
            [None, 'C. خدمات'],
            [None, '01-1', 'بنگاه', 1, 'مقطوع', 10, 20, 30, 2, 3, 4, 20, 60, 120],
            [None, '01-2', 'دفترخانه', 1, 'مقطوع', 11, 21, 31, 2, 3, 4, 22, 63, 124],
            [None, 'جمع فاز 01'],
        ]
        monkeypatch.setattr(budget_module, 'list_sheet_names', lambda _path: [overall_sheet, 'نباید خوانده شود'])
        seen = []

        def read_one_sheet(_path, *, name):
            seen.append(name)
            assert name == overall_sheet
            return rows

        monkeypatch.setattr(budget_module, 'read_sheet', read_one_sheet)
        service = RichBudgetService(FinanceDB(Path(directory) / 'budget.sqlite3'), directory)
        result = service.import_workbook(source, title='test overall estimate', preserve_manual=False)
        assert result.phase_count == 1
        assert result.phase_item_count == 2
        assert seen == [overall_sheet]
        first_phase = service.list_phase_items(1)
        assert first_phase and first_phase[0]['plan_ref'] == '01-1'
        assert first_phase[0]['description'] == 'بنگاه'
        assert first_phase[0]['qty_estimate'] == 2
        assert first_phase[0]['local_estimate_rate'] == 10
        assert [row['plan_ref'] for row in first_phase] == ['01-1', '01-2']
        assert [row['sort_order'] for row in first_phase] == [1, 2]


def test_workbook_layout_keeps_known_layouts_and_rejects_unrelated_sheets(monkeypatch, tmp_path):
    names = []
    monkeypatch.setattr(budget_module, 'list_sheet_names', lambda _path: names)

    names[:] = ['شیت اصلی', 'روکش']
    assert RichBudgetService.workbook_layout(tmp_path / 'legacy.xlsx') == 'v1'

    names[:] = [*RichBudgetService.PRICE_SHEETS_V2, 'برآورد کلی', 'روکش مالی']
    assert RichBudgetService.workbook_layout(tmp_path / 'v2.xlsx') == 'v2'

    names[:] = ['برآورد کلی', 'نباید خوانده شود']
    assert RichBudgetService.workbook_layout(tmp_path / 'overall.xlsx') == 'v2_overall'

    names[:] = ['نباید خوانده شود']
    assert RichBudgetService.workbook_layout(tmp_path / 'unrelated.xlsx') == ''


def test_dashboard_chart_rollup_matches_the_project_plan_totals():
    """Zero بروز in the plan must remain zero in every dashboard chart."""
    import dashboard_stage18_7 as dashboard

    class Rich:
        def all_phase_items(self):
            return [
                {
                    'phase_no': 1, 'phase_name': 'خرید زمین',
                    'local_estimate_rate': 100, 'qty_estimate': 2,
                    'forecast_rate': 0, 'qty_forecast': 0,
                    'total_actual': 50,
                },
                {
                    'phase_no': 1, 'phase_name': 'خرید زمین', 'factor': 2,
                    'local_estimate_rate': 10, 'qty_estimate': 3,
                    'forecast_rate': 5, 'qty_forecast': 4,
                    'total_actual': 0,
                },
                {
                    'phase_no': 2, 'phase_name': 'عملیات خاکی',
                    'local_estimate_rate': 20, 'qty_estimate': 4,
                    'forecast_rate': 0, 'qty_forecast': 0,
                    'total_actual': 25,
                },
            ]

    plan_backed_dashboard = type('Dashboard', (), {'rich': Rich()})()
    rows = dashboard.Stage187Dashboard._phase_summary_live(plan_backed_dashboard)

    assert rows == [
        {
            'phase_no': 1, 'phase': 'خرید زمین', 'phase_id': 'PH-01',
            'estimate': 260, 'actual': 50, 'remaining_base': 210,
            'forecast': 40, 'variance': -220,
        },
        {
            'phase_no': 2, 'phase': 'عملیات خاکی', 'phase_id': 'PH-02',
            'estimate': 80, 'actual': 25, 'remaining_base': 55,
            'forecast': 0, 'variance': -80,
        },
    ]


@pytest.mark.parametrize('qty,rate,expected', [(0, 120, 0), (3, 0, 0), (4, 5, 40)])
def test_plan_current_totals_preserve_explicit_zero_and_updated_quantity(qty, rate, expected):
    from project_plan_stage18_7 import _totals
    row = {'qty_estimate': 3, 'qty_forecast': qty, 'estimate_rate': 100,
           'forecast_rate': rate, 'factor': 2, 'total_actual': 7}
    assert _totals(row) == (600, expected, 7)


def test_plan_missing_updated_fields_keep_original_fallback(monkeypatch):
    import project_plan_stage18_7 as plan
    monkeypatch.setattr(plan, 'load_ui', lambda: {})
    assert plan._totals({'qty_estimate': 3, 'estimate_rate': 100, 'factor': 2}) == (600, 600, 0)
