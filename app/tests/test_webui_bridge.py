"""Read-only pywebview prototype: bridge surface, envelopes and isolation.

None of these tests need pywebview or a display; they exercise the Python
side the window calls into.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from webui import bridge as bridge_module  # noqa: E402
from webui.bridge import PUBLIC_METHODS, DashboardBridge, load_dashboard  # noqa: E402
from webui.snapshot import resolve_project  # noqa: E402
from webui.summary import pending_counts  # noqa: E402


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture()
def project_db(tmp_path):
    """A migrated project database with a few pending rows, created the
    normal way so the schema matches the real app."""
    from finance_db import FinanceDB
    db_file = tmp_path / 'project' / 'project.sqlite3'
    db = FinanceDB(db_file)
    for i, status in enumerate(['PENDING_REVIEW', 'NEEDS_REVIEW', 'APPROVED', 'REJECTED']):
        db.create_or_replace_pending(
            telegram_chat_id=-100, telegram_message_id=i + 1, detected_type='EXPENSE',
            payload={'amount': 1000 * (i + 1)}, status=status,
        )
    # Checkpoint so the file hash below reflects everything written.
    con = sqlite3.connect(db_file)
    con.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    con.close()
    return db_file


def test_js_can_only_reach_the_listed_methods():
    # pywebview exposes every public attribute recursively (webview/util.py
    # get_functions); anything public beyond these two would reach the page.
    bridge = DashboardBridge(APP_DIR, loader=lambda *a: {})
    public = sorted(n for n in dir(bridge) if not n.startswith('_'))
    assert public == sorted(PUBLIC_METHODS)
    for name in public:
        assert callable(getattr(bridge, name))


def test_summary_reads_a_snapshot_and_leaves_the_project_database_untouched(project_db):
    before_hash, before_mtime = _sha(project_db), project_db.stat().st_mtime_ns
    before_files = sorted(p.name for p in project_db.parent.iterdir())
    leftovers_before = set(Path(tempfile.gettempdir()).glob('barkav_webui_*'))

    data = load_dashboard(APP_DIR, db_path=project_db)

    assert _sha(project_db) == before_hash
    assert project_db.stat().st_mtime_ns == before_mtime
    # Opening a WAL database, even with mode=ro, lets SQLite create its
    # -wal/-shm side files (the live app always has them). They must hold
    # no new data: the main file is byte-identical and the WAL is empty.
    after_files = sorted(p.name for p in project_db.parent.iterdir())
    assert set(after_files) - set(before_files) <= {'project.sqlite3-wal', 'project.sqlite3-shm'}
    wal = project_db.with_name('project.sqlite3-wal')
    assert not wal.exists() or wal.stat().st_size == 0
    assert set(Path(tempfile.gettempdir()).glob('barkav_webui_*')) == leftovers_before
    assert data['snapshot']['read_only'] is True
    assert data['pending'] == {'total': 4, 'review': 2, 'approved': 1, 'rejected': 1}
    assert 'partial' not in data['liquidity_30d']
    # JSON-only payload, and no file-system path leaks to the page.
    text = json.dumps(data, ensure_ascii=False)
    assert str(project_db.parent) not in text and 'sqlite3' not in text


def test_pending_counts_skip_hidden_reviews_like_the_data_entry_toolbar(project_db):
    from finance_db import FinanceDB
    db = FinanceDB(project_db)
    with db.read() as con:
        first = con.execute("SELECT pending_id FROM pending_items WHERE status='PENDING_REVIEW'").fetchone()[0]
    with db.tx() as con:
        con.execute('CREATE TABLE IF NOT EXISTS rich_ui_hidden_reviews '
                    '(pending_id TEXT PRIMARY KEY, hidden INTEGER, updated_at TEXT)')
        con.execute('INSERT INTO rich_ui_hidden_reviews VALUES (?, 1, ?)', (first, 'now'))
    assert pending_counts(db) == {'total': 3, 'review': 1, 'approved': 1, 'rejected': 1}


def test_missing_registry_is_a_stable_error_envelope(tmp_path):
    result = DashboardBridge(tmp_path / 'app').get_dashboard_summary()
    assert result['ok'] is False
    assert result['error']['code'] == 'PROJECT_REGISTRY_MISSING'
    assert result['error']['retryable'] is False
    assert result['meta']['api_version'] == bridge_module.API_VERSION


def test_unexpected_failure_hides_internals(tmp_path):
    def boom(*_args):
        raise RuntimeError(r'C:\secret\path token=123')
    result = DashboardBridge(tmp_path, loader=boom).get_dashboard_summary()
    assert result['ok'] is False and result['error']['code'] == 'INTERNAL_ERROR'
    assert 'secret' not in json.dumps(result) and 'token' not in json.dumps(result)


def test_summary_is_cached_briefly_and_refresh_forces_a_new_snapshot(tmp_path):
    calls = []
    bridge = DashboardBridge(tmp_path, cache_seconds=60,
                             loader=lambda *a: calls.append(a) or {'n': len(calls)})
    assert bridge.get_dashboard_summary()['data'] == {'n': 1}
    assert bridge.get_dashboard_summary()['data'] == {'n': 1}
    assert bridge.get_dashboard_summary(force_refresh=True)['data'] == {'n': 2}


def test_registry_lookup_is_read_only(tmp_path):
    registry = tmp_path / 'data' / 'project_registry.json'
    registry.parent.mkdir()
    registry.write_text(json.dumps({'active_project_id': 'PRJ-002', 'projects': [
        {'project_id': 'PRJ-001', 'name': 'الف', 'db_path': 'a.sqlite3'},
        {'project_id': 'PRJ-002', 'name': 'ب', 'db_path': str(tmp_path / 'b.brk')},
    ]}, ensure_ascii=False), encoding='utf-8')
    before = registry.read_bytes()
    assert resolve_project(tmp_path).project_id == 'PRJ-002'
    assert resolve_project(tmp_path, 'PRJ-001').db_path == registry.parent / 'a.sqlite3'
    assert registry.read_bytes() == before
    assert sorted(p.name for p in registry.parent.iterdir()) == ['project_registry.json']


def test_contracts_file_name_matches_the_contractor_store(tmp_path, monkeypatch):
    from contractor_store_stage18_7 import store_path
    from webui.snapshot import CONTRACTS_FILE_NAME
    monkeypatch.setenv('STAGE4_DB_PATH', str(tmp_path / 'x' / 'p.sqlite3'))
    assert store_path().name == CONTRACTS_FILE_NAME


def test_contracts_are_read_beside_the_project_database_without_side_effects(project_db, tmp_path):
    from webui.snapshot import CONTRACTS_FILE_NAME, read_contracts_beside
    folder = project_db.parent
    assert read_contracts_beside(project_db) == []          # missing file -> []
    (folder / CONTRACTS_FILE_NAME).write_text(
        json.dumps({'contracts': [{'contract_id': 'C1', 'title': 'الف'}]}, ensure_ascii=False),
        encoding='utf-8')
    before = sorted(p.name for p in folder.iterdir())
    assert read_contracts_beside(project_db) == [{'contract_id': 'C1', 'title': 'الف'}]
    data = load_dashboard(APP_DIR, db_path=project_db)
    assert sorted(p.name for p in folder.iterdir() if not p.name.endswith(('-wal', '-shm'))) == \
        sorted(n for n in before if not n.endswith(('-wal', '-shm')))
    liq = data['liquidity_30d']
    assert 'partial' not in liq
    assert set(liq) >= {'claims', 'commitments', 'cheques', 'installments', 'balance',
                        'cash', 'liquidity_needed', 'commitment_rows',
                        'overdue_commitments', 'overdue_rows'}
    assert liq['liquidity_needed'] == liq['cash'] + liq['balance']
