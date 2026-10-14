"""Legacy linked-status compatibility, backups and migration rollback."""
import sqlite3
import pytest
from finance_db import FinanceDB
CHAT=-100

def _legacy_database(path, tmp_path):
    """A database whose CHECKs predate LINKED / LINKED_EVIDENCE, as on older installs."""
    FinanceDB(tmp_path / 'template.sqlite3')
    src = sqlite3.connect(tmp_path / 'template.sqlite3')
    statements = [r[0] for r in src.execute(
        "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' "
        "ORDER BY type='table' DESC, rowid"
    )]
    src.close()
    legacy = [s.replace(",'LINKED_EVIDENCE')", ")").replace(",'LINKED')", ")") for s in statements]
    assert not any('LINKED' in s for s in legacy)
    con = sqlite3.connect(path)
    for sql in legacy:
        con.execute(sql)
    con.execute("INSERT INTO telegram_messages(chat_id,message_id,raw_text,content_type,message_date,state,"
                "created_at,updated_at) VALUES(?,12,'a','TEXT','2026-01-01','PENDING_REVIEW','t','t')", (CHAT,))
    con.execute("INSERT INTO telegram_messages(chat_id,message_id,raw_text,content_type,message_date,state,"
                "created_at,updated_at) VALUES(?,13,'b','PHOTO','2026-01-01','NEEDS_REVIEW','t','t')", (CHAT,))
    con.execute("INSERT INTO pending_items(pending_id,telegram_chat_id,telegram_message_id,detected_type,"
                "payload_json,status,created_at,updated_at) VALUES('P1',?,12,'EXPENSE','{}','PENDING_REVIEW','t','t')",
                (CHAT,))
    con.execute("INSERT INTO pending_items(pending_id,telegram_chat_id,telegram_message_id,detected_type,"
                "payload_json,status,created_at,updated_at) VALUES('P2',?,13,'INFO','{}','NEEDS_REVIEW','t','t')",
                (CHAT,))
    con.execute("INSERT INTO posting_revisions(revision_id,pending_id,old_payload_json,new_payload_json,"
                "created_at,updated_at) VALUES('R1','P1','{}','{}','t','t')")
    # receipt_analyses cascades on delete: the rebuild's DROP TABLE must not reach it.
    con.execute("INSERT INTO receipt_analyses(analysis_id,pending_id,created_at,updated_at) "
                "VALUES('A1','P1','t','t')")
    con.commit()
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("UPDATE pending_items SET status='LINKED' WHERE pending_id='P2'")
    con.rollback()
    con.close()


def _schema(db: FinanceDB):
    with db.read() as con:
        return {r[0]: r[1] for r in con.execute(
            "SELECT name, sql FROM sqlite_master WHERE name IN ('pending_items','telegram_messages')")}


def test_older_database_is_migrated_to_accept_linked_statuses(tmp_path):
    path = tmp_path / 'legacy.sqlite3'
    _legacy_database(path, tmp_path)

    db = FinanceDB(path)

    schema = _schema(db)
    assert "'LINKED')" in schema['pending_items']
    assert "'LINKED_EVIDENCE')" in schema['telegram_messages']
    with db.read() as con:
        assert [tuple(r) for r in con.execute('SELECT pending_id,status FROM pending_items ORDER BY 1')] == [
            ('P1', 'PENDING_REVIEW'), ('P2', 'NEEDS_REVIEW')]
        assert con.execute('SELECT pending_id FROM posting_revisions').fetchone()[0] == 'P1'
        assert con.execute('SELECT pending_id FROM receipt_analyses').fetchone()[0] == 'P1'
        assert con.execute('PRAGMA foreign_key_check').fetchall() == []
        assert not con.execute("SELECT 1 FROM sqlite_master WHERE name LIKE '%widen_new'").fetchone()

    db.update_pending('P2', status='LINKED')
    db.update_telegram_message(chat_id=CHAT, message_id=13, state='LINKED_EVIDENCE')
    assert db.get_pending_item('P2')['status'] == 'LINKED'
    assert db.get_telegram_message(CHAT, 13)['state'] == 'LINKED_EVIDENCE'

    # Foreign keys into the rebuilt table still resolve to it.
    with pytest.raises(sqlite3.IntegrityError):
        with db.tx() as con:
            con.execute("INSERT INTO posting_revisions(revision_id,pending_id,old_payload_json,new_payload_json,"
                        "created_at,updated_at) VALUES('R2','NOPE','{}','{}','t','t')")

    # Reopening is a no-op: nothing is rebuilt a second time.
    FinanceDB(path)
    assert _schema(db) == schema


def test_migration_preserves_a_valid_pre_migration_snapshot(tmp_path):
    path = tmp_path / 'legacy.sqlite3'
    _legacy_database(path, tmp_path)
    FinanceDB(path)
    backups = list((tmp_path / '.barkav-migration-backups').glob('*.sqlite3'))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as old:
        assert old.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        sql = old.execute("SELECT sql FROM sqlite_master WHERE name='pending_items'").fetchone()[0]
        assert "'LINKED'" not in sql
        assert old.execute('SELECT COUNT(*) FROM pending_items').fetchone()[0] == 2

def test_migration_failure_rolls_back_status_schema_and_data(tmp_path, monkeypatch):
    path = tmp_path / 'legacy.sqlite3'
    _legacy_database(path, tmp_path)
    with sqlite3.connect(path) as old:
        before = old.execute("SELECT name,sql FROM sqlite_master WHERE name IN ('pending_items','telegram_messages') ORDER BY name").fetchall()
    original = FinanceDB._check_needs
    def broken(sql, column, value):
        result = original(sql, column, value)
        if result and column == 'state':
            return result.replace('telegram_messages', 'unexpected_table')
        return result
    monkeypatch.setattr(FinanceDB, '_check_needs', staticmethod(broken))
    with pytest.raises(sqlite3.DatabaseError):
        FinanceDB(path)
    with sqlite3.connect(path) as old:
        assert old.execute("SELECT name,sql FROM sqlite_master WHERE name IN ('pending_items','telegram_messages') ORDER BY name").fetchall() == before
        assert old.execute('SELECT COUNT(*) FROM pending_items').fetchone()[0] == 2
        assert old.execute('PRAGMA foreign_key_check').fetchall() == []
    assert len(list((tmp_path / '.barkav-migration-backups').glob('*.sqlite3'))) == 1
