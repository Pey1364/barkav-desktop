"""Protect the active runtime from the asynchronous traceback watchdog.

The prior Windows dump faults while reading a Python frame in that diagnostic
thread. Fatal fault reporting stays enabled; this guards periodic diagnostics.
"""
import ast
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]

@pytest.mark.parametrize("module", ["launcher_stage18_7.py", "project_runner_stage18_7.py",
    "barkav_bare_launcher_187.py", "dashboard_stage18_7.py"])
def test_active_runtime_does_not_install_periodic_native_traceback_dump(module):
    tree = ast.parse((ROOT / module).read_text(encoding="utf-8-sig"))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    assert not any(isinstance(call.func, ast.Attribute) and
                   call.func.attr == "dump_traceback_later" for call in calls)
    assert not any(isinstance(call.func, ast.Name) and
                   call.func.id == "dump_traceback_later" for call in calls)


def test_pytest_does_not_enable_async_watchdog_but_keeps_fault_reporting(pytestconfig):
    assert float(pytestconfig.getini("faulthandler_timeout")) == 0
    assert pytestconfig.pluginmanager.hasplugin("faulthandler")
