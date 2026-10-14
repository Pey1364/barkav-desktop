"""The baseline comparison tool: only new failures are reported, known ones are counted."""
import importlib.util
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[1] / 'tools' / 'test_baseline187.py'
spec = importlib.util.spec_from_file_location('test_baseline187_tool', TOOL)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)

LOG = """\
============================= short test summary info =============================
FAILED tests/test_a.py::test_known - AssertionError: old
FAILED tests/test_a.py::test_new - KeyError: 'x'
FAILED tests/test_b.py::test_param[\\u062a\\u0642\\u0648\\u06cc\\u0645 \\u06a9\\u0627\\u0631\\u06af\\u0627\\u0647\\u06cc] - TypeError
ERROR tests/test_c.py::test_collect - ImportError
3 failed, 1 passed in 2.10s
"""

BASELINE = """\
# comment line
tests/test_a.py::test_known
tests/test_b.py::test_param[\\u062a\\u0642\\u0648\\u06cc\\u0645 \\u06a9\\u0627\\u0631\\u06af\\u0627\\u0647\\u06cc]
"""


def test_failures_are_read_with_or_without_reason_and_with_escaped_spaces():
    found = tool.failures_in(LOG)
    assert 'tests/test_a.py::test_known' in found
    assert 'tests/test_a.py::test_new' in found
    assert 'tests/test_c.py::test_collect' in found
    assert any(name.startswith('tests/test_b.py::test_param[') for name in found)


def test_only_new_failures_are_listed_and_known_ones_are_counted():
    new, known_seen = tool.compare(LOG, BASELINE)
    assert new == ['tests/test_a.py::test_new', 'tests/test_c.py::test_collect']
    assert known_seen == 2


def test_main_exit_codes_and_output(tmp_path, capsys):
    log = tmp_path / 'run.log'
    base = tmp_path / 'known.txt'
    log.write_text(LOG, encoding='utf-8')
    base.write_text(BASELINE, encoding='utf-8')
    assert tool.main([str(log), '--baseline', str(base)]) == 1
    out = capsys.readouterr().out
    assert 'NEW  tests/test_a.py::test_new' in out and 'test_known' not in out.split('new failure')[0]
    base.write_text(BASELINE + 'tests/test_a.py::test_new\ntests/test_c.py::test_collect\n', encoding='utf-8')
    assert tool.main([str(log), '--baseline', str(base)]) == 0


def test_a_log_without_summary_is_refused(tmp_path, capsys):
    log = tmp_path / 'cut.log'
    log.write_text('tests/test_a.py .....', encoding='utf-8')
    base = tmp_path / 'known.txt'
    base.write_text(BASELINE, encoding='utf-8')
    assert tool.main([str(log), '--baseline', str(base)]) == 2
    assert 'did the run finish' in capsys.readouterr().err


@pytest.mark.parametrize('text', ['', '# only a comment\n'])
def test_empty_baseline_makes_every_failure_new(text):
    new, known_seen = tool.compare(LOG, text)
    assert len(new) == 4 and known_seen == 0  # three FAILED lines and one ERROR line
