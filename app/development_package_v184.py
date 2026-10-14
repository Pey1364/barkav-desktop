from __future__ import annotations
from pathlib import Path
import development_package_v174 as base

V184_FILES = [
    'dashboard_stage18_4.py',
    'ui_stage18_4.py',
    'launcher_stage18_4.py',
    'project_center_stage18_4.py',
    'project_runner_stage18_4.py',
    'development_package_v184.py',
    'tests/test_stage18_4_regression.py',
    'tests/test_stage18_4_ui.py',
    'BARKAV_18.4.bat',
    'README_18.4_FINAL.txt',
    'TEST_PLAN_18.4.txt',
    'BARKAV_TEST_RESULTS_18.4_FINAL.txt',
    'BARKAV_Checkpoint_14_V18.4_Targeted_Fixes_2026-08-19.txt',
    'BARKAV_V18.4_16_POINT_CHECKLIST_COMPLETED_2026-08-19.txt',
    'assets/BARKAV_18_4.ico',
]


def build_development_package(base_dir: Path, dest: Path, version: str = '18.4') -> dict:
    old = list(base.SAFE_SOURCE_FILES)
    try:
        # V18.4 files first, then the inherited development context without duplicates.
        base.SAFE_SOURCE_FILES = V184_FILES + [x for x in old if x not in V184_FILES]
        return base.build_development_package(base_dir, dest, version)
    finally:
        base.SAFE_SOURCE_FILES = old
