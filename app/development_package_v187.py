from __future__ import annotations

from pathlib import Path
import development_package_v174 as base
import development_package_v186 as v186_package


V187_FILES = [
    'dashboard_stage18_7.py', 'ui_stage18_7.py', 'reports_stage18_7.py',
    'financial_calendar_stage18_7.py', 'launcher_stage18_7.py',
    'project_center_stage18_7.py', 'project_runner_stage18_7.py',
    'telegram_stage18_7.py', 'development_package_v187.py',
    'release_builder_v187.py', 'BARKAV_18.7.bat', 'VERSION.txt', 'AGENTS.md',
    'README_18.7_WORKING.txt', 'TEST_PLAN_18.7.txt',
    'BARKAV_TEST_RESULTS_18.7_WORKING.txt',
    'BARKAV_Checkpoint_17_V18.7_WORD_THEME_2026-08-21.txt',
    'tests/test_stage18_7_word_and_theme.py', 'tests/test_stage18_7_ui.py',
    'barkav_themes/__init__.py', 'barkav_themes/tokens.py',
    'barkav_themes/engine.py', 'barkav_themes/widgets.py',
    'docs/theme_18_7/reference_manifest.json',
    'docs/theme_18_7/REFERENCE_ANALYSIS.md',
    'docs/theme_18_7/README_THEME_18.7_FA.md',
    'docs/requirements_18_7/اصلاحات18.6.docx',
]


def build_development_package(base_dir: Path, destination: Path, version: str = '18.7') -> dict:
    original = list(base.SAFE_SOURCE_FILES)
    try:
        inherited = list(v186_package.V186_FILES) + list(original)
        base.SAFE_SOURCE_FILES = V187_FILES + [item for item in inherited if item not in V187_FILES]
        return base.build_development_package(base_dir, destination, version)
    finally:
        base.SAFE_SOURCE_FILES = original
