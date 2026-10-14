from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_active_direct_row_renderers_keep_alternating_theme_stripes():
    for name in ('contractor_archive_stage18_7.py', 'contractor_statements_stage18_7.py'):
        source = (ROOT / name).read_text(encoding='utf-8')
        assert source.count("stripes = (p['row_even'], p['row_odd'])") == 2

    plan_source = (ROOT / 'project_plan_stage18_7.py').read_text(encoding='utf-8')
    assert "stripe = p['row_even'] if line % 2 else p['row_odd']" in plan_source
    assert 'bg=stripe' in plan_source


def test_shared_theme_keeps_semantic_status_colors_separate_from_ordinary_rows():
    from barkav_themes.tokens import get_theme

    palette = get_theme(1).palette('dark')
    assert palette['row_even'] != palette['row_approved']
    assert palette['row_even'] != palette['row_pending']
    assert palette['row_even'] != palette['row_rejected']
