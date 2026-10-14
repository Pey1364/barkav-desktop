from __future__ import annotations

from pathlib import Path

from project_center_stage18_6 import validate_project_shortcut
from instance_guard_v185 import ProjectInstanceGuard
from runtime_base import self_reexec_args


ROOT = Path(__file__).resolve().parents[1]


def test_cloud_launcher_is_the_default_and_legacy_center_is_opt_in(monkeypatch, tmp_path):
    """Existing projects open their dashboard; an empty registry opens the hub."""
    from types import SimpleNamespace
    import sys
    import launcher_stage18_7 as launcher
    import project_registry
    import project_runner_stage18_7 as runner
    import barkav_bare_launcher_187 as hub
    import project_center_stage18_7 as center
    calls = []
    project = SimpleNamespace(project_id='TEST-PROJECT')
    projects = [project]
    registry = SimpleNamespace(data={'active_project_id': project.project_id},
        list=lambda: projects, get=lambda _key: project if projects else None)
    monkeypatch.setattr(launcher, 'BASE', tmp_path)
    monkeypatch.setattr(launcher, 'LOG_DIR', tmp_path)
    monkeypatch.setattr(launcher, 'STARTUP_LOG', tmp_path / 'startup.log')
    monkeypatch.setattr(launcher, 'preflight', lambda: True)
    monkeypatch.setattr(sys, 'argv', ['launcher_stage18_7.py'])
    monkeypatch.delenv('BARKAV_PROJECT_CENTER', raising=False)
    monkeypatch.setattr(project_registry, 'ProjectRegistry', lambda _base: registry)
    monkeypatch.setattr(runner, 'run_project', lambda p: calls.append(('dashboard', p)))
    monkeypatch.setattr(hub, 'run_bare_launcher', lambda base: calls.append(('hub', base)))
    monkeypatch.setattr(center, 'run_project_center', lambda base: calls.append(('legacy', base)))
    launcher.main()
    assert calls == [('dashboard', project)]
    projects.clear(); calls.clear()
    launcher.main()
    assert calls == [('hub', tmp_path)]
    monkeypatch.setenv('BARKAV_PROJECT_CENTER', '1'); calls.clear()
    launcher.main()
    assert calls == [('legacy', tmp_path)]


def test_cloud_shortcut_payload_never_embeds_secrets():
    source = (ROOT / "barkav_bare_launcher_187.py").read_text(encoding="utf-8")
    assert 'path = self.shortcut_dir / f"{_safe_name(project.name)}_{project.project_id}.brk"' in source
    assert '"group_chat_ids": groups' in source
    assert '"secrets":' not in source


def test_project_window_reopen_focuses_existing_runner_and_delayed_launch():
    source = (ROOT / "barkav_bare_launcher_187.py").read_text(encoding="utf-8")
    runner = (ROOT / "project_runner_stage18_7.py").read_text(encoding="utf-8")
    assert "bring_process_window_to_front(proc.pid)" in source
    assert "if not guard.acquire():" in source
    assert "owner_pid = guard.owner_pid()" in source
    assert "self.after(180, focus_when_ready)" in source
    assert "bring_process_window_to_front(guard.owner_pid())" in runner


def test_startup_message_popup_has_explicit_close_action_and_native_protocol():
    source = (ROOT / "financial_calendar_stage18_7.py").read_text(encoding="utf-8")
    popup = source.split("class StartupMessagesPopup187", 1)[1].split(
        "class FinancialMessagesDialog187", 1
    )[0]
    assert "text='✕ بستن'" in popup
    assert "self.protocol('WM_DELETE_WINDOW', self._close_modal_187)" in popup


def test_project_lock_owner_pid_is_readable(tmp_path):
    guard = ProjectInstanceGuard(tmp_path, 'PRJ-FOCUS')
    guard.path.write_text('4242', encoding='ascii')
    assert guard.owner_pid() == 4242


def test_bot_subprocess_uses_self_reexec_args_not_a_hardcoded_python_call():
    source = (ROOT / "launcher_stage18_7.py").read_text(encoding="utf-8")
    runner = (ROOT / "project_runner_stage18_7.py").read_text(encoding="utf-8")
    assert 'sys.argv[1] == "--run-bot"' in source
    assert "telegram_stage18_7.main()" in source
    assert "self_reexec_args(BASE / 'telegram_stage18_7.py', '--run-bot')" in runner
    # start_bot() still assigns the freshly-spawned process to the
    # kill-on-close Job Object regardless of how its argv is built.
    assert "_assign_to_job(_create_kill_on_close_job(), process)" in runner


def test_self_reexec_args_targets_the_dev_script_unfrozen_and_the_flag_alone_frozen(monkeypatch):
    import runtime_base

    monkeypatch.setattr(runtime_base, 'frozen', lambda: False)
    dev_args = self_reexec_args(Path('/app/telegram_stage18_7.py'), '--run-bot')
    assert dev_args[-2:] == [str(Path('/app/telegram_stage18_7.py')), '--run-bot']

    monkeypatch.setattr(runtime_base, 'frozen', lambda: True)
    frozen_args = self_reexec_args(Path('/app/telegram_stage18_7.py'), '--run-bot')
    assert frozen_args[-1] == '--run-bot'
    assert str(Path('/app/telegram_stage18_7.py')) not in frozen_args


def test_validator_accepts_cloud_groups_and_legacy_single_group(tmp_path):
    db = tmp_path / "finance.sqlite3"
    db.write_bytes(bytes.fromhex("53514c69746520666f726d6174203300" + "00" * 32))
    cloud = {
        "format": "BARKAV_PROJECT_SHORTCUT",
        "version": 1,
        "project_id": "PRJ-009",
        "name": "Demo",
        "db_path": str(db),
        "group_chat_id": -1001,
        "group_chat_ids": [-1001, -1002],
    }
    entry, is_new = validate_project_shortcut(cloud, tmp_path / "demo.brk", [])
    assert is_new
    assert entry.group_chat_ids == [-1001, -1002]

    legacy = dict(cloud)
    legacy.pop("group_chat_ids")
    entry, is_new = validate_project_shortcut(legacy, tmp_path / "old.barkav", [])
    assert is_new
    assert entry.group_chat_ids == [-1001]
