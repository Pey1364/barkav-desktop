from __future__ import annotations

from pathlib import Path
import development_package_v174 as base


V185_FILES = [
    'dashboard_stage18_5.py',
    'ui_stage18_5.py',
    'launcher_stage18_5.py',
    'project_center_stage18_5.py',
    'project_runner_stage18_5.py',
    'instance_guard_v185.py',
    'development_package_v185.py',
    'tests/test_stage18_5_regression.py',
    'tests/test_stage18_5_ui.py',
    'BARKAV_18.5.bat',
    'CREATE_SHORTCUT.bat',
    'README_18.5_FINAL.txt',
    'TEST_PLAN_18.5.txt',
    'BARKAV_TEST_RESULTS_18.5_FINAL.txt',
    'BARKAV_Checkpoint_15_V18.5_Feature_Freeze_2026-08-20.txt',
    'assets/BARKAV_18_5.ico',
    'requirements_18.5.lock',
]


def build_development_package(base_dir: Path, destination: Path, version: str = '18.5') -> dict:
    previous = list(base.SAFE_SOURCE_FILES)
    try:
        base.SAFE_SOURCE_FILES = V185_FILES + [item for item in previous if item not in V185_FILES]
        return base.build_development_package(base_dir, destination, version)
    finally:
        base.SAFE_SOURCE_FILES = previous

