from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_pyinstaller_spec_targets_the_real_launcher_and_assets():
    spec = (ROOT / "BARKAV.spec").read_text(encoding="utf-8")
    assert "launcher_stage18_7.py" in spec
    assert "APP_ROOT / 'assets'" in spec
    assert (ROOT / "launcher_stage18_7.py").is_file()
    assert (ROOT / "assets").is_dir()


def test_inno_setup_script_version_matches_the_app_version_and_never_ships_real_secrets():
    iss = (ROOT / "BARKAV.iss").read_text(encoding="utf-8")
    version = (ROOT / "VERSION.txt").read_text(encoding="utf-8").strip()
    assert f'MyAppVersion "{version}"' in iss
    assert "secrets.local.example.json" in iss
    assert "secrets.local.json\"" not in iss


def test_register_script_points_at_a_launcher_batch_file_that_actually_exists():
    register = (ROOT / "REGISTER_BARKAV_FILE_ICON.ps1").read_text(encoding="utf-8")
    batch_name = register.split("$launcherBat = Join-Path $PSScriptRoot '", 1)[1].split("'", 1)[0]
    assert (ROOT / batch_name).is_file()
    assert "HKCU:\\Software\\Classes\\.brk" in register


def test_unregister_script_removes_the_same_registry_root_register_creates():
    register = (ROOT / "REGISTER_BARKAV_FILE_ICON.ps1").read_text(encoding="utf-8")
    unregister = (ROOT / "UNREGISTER_BARKAV_FILE_ICON.ps1").read_text(encoding="utf-8")
    assert "'BARKAV.ProjectShortcut'" in register
    assert "'BARKAV.ProjectShortcut'" in unregister


def test_build_portable_readme_describes_the_actual_shortcut_model_not_a_single_file_format():
    source = (ROOT / "build_portable.py").read_text(encoding="utf-8")
    assert "شورتکات .brk" in source
    assert "پوشهٔ data/" in source
    # The single-file (whole project = one .brk) architecture is Cloud-only
    # and was deliberately not ported (see docs/HANDOFF.md) - the portable
    # README must not claim it.
    assert "تمام دادهٔ آن پروژه همان یک فایل است" not in source


def test_make_installer_art_imports_resolve_against_this_codebases_art_module():
    # Smoke-check the script's own dependency imports resolve against this
    # tree's actual barkav_ui.art (CHECKERBOARD_FLOOR/_ink_bands/_ink_span/
    # key_white_backdrop/tint/_flatten) rather than executing it end to end -
    # a real run writes into the shared assets/ folder, which is out of
    # scope for a test.
    source = (ROOT / "tools" / "make_installer_art.py").read_text(encoding="utf-8")
    assert "from barkav_ui.art import" in source
    imported = source.split("from barkav_ui.art import", 1)[1].split("\n", 1)[0]
    names = [n.strip() for n in imported.split(",")]
    import barkav_ui.art as art_module
    for name in names:
        assert hasattr(art_module, name), f"barkav_ui.art.{name} missing"
