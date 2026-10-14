"""tools/audit_ledger_ownership.py: read-only by default, deletes only the leftovers when told to, after a backup."""
import sys
from pathlib import Path
import pytest
from test_cheque_resolution_lifecycle187 import _issue
from test_transaction_lifecycle_matrix import m, runtime, register  # noqa: F401

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import audit_ledger_ownership as tool  # noqa: E402


def _leftover(runtime):
    from transaction_review import ReviewReturn
    issue, cheque_id = _issue(runtime)
    ReviewReturn(runtime.db).return_to_review([issue])
    return issue, cheque_id


def _cheques(runtime):
    with runtime.db.read() as con:
        return [row['cheque_id'] for row in con.execute('SELECT cheque_id FROM cheques')]


def test_the_audit_lists_a_leftover_and_changes_nothing(runtime, capsys):
    issue, cheque_id = _leftover(runtime)
    assert tool.main(['--db', runtime.db.db_path]) == 0
    out = capsys.readouterr().out
    assert 'orphans: 0' in out and cheque_id in out
    assert tool.main(['--db', runtime.db.db_path, '--remove-leftovers']) == 0  # a dry run
    assert _cheques(runtime) == [cheque_id]


def test_the_audit_exits_with_one_for_an_orphan(runtime, capsys):
    runtime.db.create_cheque(amount=1000, issue_date='2026-09-30', due_date='2026-10-30')
    assert tool.main(['--db', runtime.db.db_path]) == 1
    assert 'orphans: 1' in capsys.readouterr().out


def test_apply_makes_a_backup_and_removes_only_the_leftover(runtime):
    issue, cheque_id = _leftover(runtime)
    assert tool.main(['--db', runtime.db.db_path, '--remove-leftovers', '--apply']) == 0
    assert _cheques(runtime) == []
    backups = list((Path(runtime.db.db_path).parent / '.barkav-migration-backups').glob('*.pre-ownership-repair.sqlite3'))
    assert len(backups) == 1
    # the record can still post its cheque again on the id it had
    m.v18.submit_v18(issue, runtime.db.get_pending_item(issue)['payload'], runtime.rich)
    assert _cheques(runtime) == [cheque_id]
