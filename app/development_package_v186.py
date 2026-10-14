from __future__ import annotations

from pathlib import Path
import development_package_v174 as base


V186_FILES = [
    'dashboard_stage18_6.py',
    'ui_stage18_6.py',
    'launcher_stage18_6.py',
    'project_center_stage18_6.py',
    'project_runner_stage18_6.py',
    'development_package_v186.py',
    'release_builder_v186.py',
    'tests/test_stage18_6_regression.py',
    'tests/test_stage18_6_ui.py',
    'BARKAV_18.6.bat',
    'README_18.6_FINAL.txt',
    'TEST_PLAN_18.6.txt',
    'BARKAV_TEST_RESULTS_18.6_FINAL.txt',
    'BARKAV_Checkpoint_16_V18.6_GUI_Focus_2026-08-20.txt',
    'BARKAV_V18.6_GUI_FOCUS_CHECKLIST_COMPLETED_2026-08-20.txt',
    'assets/BARKAV_18_6.ico',
    'requirements_18.6.lock',
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


def build_development_package(base_dir: Path, destination: Path, version: str = '18.6') -> dict:
    previous = list(base.SAFE_SOURCE_FILES)
    try:
        base.SAFE_SOURCE_FILES = V186_FILES + [item for item in previous if item not in V186_FILES]
        return base.build_development_package(base_dir, destination, version)
    finally:
        base.SAFE_SOURCE_FILES = previous
