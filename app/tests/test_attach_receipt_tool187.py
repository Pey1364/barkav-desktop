"""tools/attach_receipt_to_record.py: one archived receipt becomes a record's own, after a backup, and nothing else changes."""
import sys
from pathlib import Path

import pytest

from receipt_gallery187 import receipt_paths
from test_cheque_resolution_lifecycle187 import _issue, _resolve
from test_transaction_lifecycle_matrix import m, runtime  # noqa: F401

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import attach_receipt_to_record as tool  # noqa: E402


def _slip(runtime, name='transfer-slip.jpg'):
    path = Path(runtime.db.db_path).parent / name
    path.write_bytes(b'\xff\xd8\xff\xe0 synthetic transfer slip')
    return path


def _attachments(runtime):
    with runtime.db.read() as con:
        return [tuple(row) for row in con.execute(
            'SELECT attachment_id,entity_type,entity_id,local_path FROM attachments ORDER BY attachment_id')]


def _backups(runtime):
    return list((Path(runtime.db.db_path).parent / '.barkav-migration-backups').glob('*.pre-receipt-attach.sqlite3'))


def _run(runtime, record, slip, *extra):
    return tool.main(['--db', runtime.db.db_path, '--record', record, '--file', str(slip), *extra])


def test_a_dry_run_changes_nothing(runtime, capsys):
    issue, cheque_id = _issue(runtime)
    resolution = _resolve(runtime, cheque_id, 'عودتی به شرط تسویه', 2)
    before = _attachments(runtime)
    assert _run(runtime, resolution, _slip(runtime)) == 0
    assert 'dry run' in capsys.readouterr().out
    assert _attachments(runtime) == before and _backups(runtime) == []


def test_apply_backs_up_then_attaches_one_receipt_that_every_window_lists_after_the_issue_s(runtime, capsys):
    issue, cheque_id = _issue(runtime)
    resolution = _resolve(runtime, cheque_id, 'عودتی به شرط تسویه', 2)
    slip = _slip(runtime)
    before = _attachments(runtime)

    assert _run(runtime, resolution, slip, '--apply') == 0

    added = [row for row in _attachments(runtime) if row not in before]
    assert len(added) == 1 and added[0][1:] == ('PENDING', resolution, str(slip.resolve()))
    assert len(_backups(runtime)) == 1
    assert slip.read_bytes().endswith(b'synthetic transfer slip')  # the file itself is untouched
    for window in (resolution, issue):
        assert str(slip.resolve()) in [str(Path(p)) for p in receipt_paths(runtime.db, window)]
    assert 'attached:' in capsys.readouterr().out


def test_attaching_the_same_file_again_does_nothing(runtime, capsys):
    issue, cheque_id = _issue(runtime)
    resolution = _resolve(runtime, cheque_id, 'برگشتی', 2)
    slip = _slip(runtime)
    assert _run(runtime, resolution, slip, '--apply') == 0
    once = _attachments(runtime)
    capsys.readouterr()
    assert _run(runtime, resolution, slip, '--apply') == 0
    assert 'already attached' in capsys.readouterr().out
    assert _attachments(runtime) == once and len(_backups(runtime)) == 1


def test_it_refuses_a_missing_file_an_unknown_record_and_a_rejected_one(runtime):
    issue, cheque_id = _issue(runtime)
    resolution = _resolve(runtime, cheque_id, 'برگشتی', 2)
    slip = _slip(runtime)
    with pytest.raises(SystemExit, match='not there'):
        _run(runtime, resolution, slip.with_name('absent.jpg'), '--apply')
    with pytest.raises(SystemExit, match='no such record'):
        _run(runtime, 'PEN-NOPE', slip, '--apply')
    runtime.db.update_pending(resolution, status='REJECTED')
    with pytest.raises(SystemExit, match='REJECTED'):
        _run(runtime, resolution, slip, '--apply')
    assert _backups(runtime) == []
