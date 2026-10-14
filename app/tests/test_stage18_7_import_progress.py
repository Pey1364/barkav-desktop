from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from queue import Queue
from types import SimpleNamespace

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_BOOT = tempfile.TemporaryDirectory()
os.environ.setdefault('STAGE4_DB_PATH', str(Path(_BOOT.name) / 'import_progress.sqlite3'))
os.environ.setdefault('TELEGRAM_BOT_TOKEN', 'import-progress-token')
os.environ.setdefault('GEMINI_API_KEY', 'import-progress-gemini')
os.environ.setdefault('ADMIN_USER_ID', '187')
os.environ.setdefault('GROUP_CHAT_ID', '-100187')

import dashboard_stage18_7 as d187  # noqa: E402
from approval_service import ApprovalCenterService  # noqa: E402
from finance_db import FinanceDB  # noqa: E402
from receipt_intelligence import OCRResult, ReceiptIntelligenceService  # noqa: E402
from telegram_history_import import import_telegram_export  # noqa: E402


def _photo_backup(root: Path, count: int) -> Path:
    export = root / 'export'
    (export / 'photos').mkdir(parents=True)
    messages = []
    for index in range(1, count + 1):
        Image.new('RGB', (40, 30), (index * 30, 10, 10)).save(export / 'photos' / f'r{index}.jpg')
        messages.append({
            'id': 100 + index, 'type': 'message', 'date': f'2026-08-10T10:0{index}:00',
            'from': 'Peyman', 'text': '', 'photo': f'photos/r{index}.jpg',
        })
    path = export / 'result.json'
    path.write_text(json.dumps(
        {'name': 'Project', 'type': 'private_supergroup', 'id': 1, 'messages': messages},
        ensure_ascii=False,
    ), encoding='utf-8')
    return path


def _hidden_table(db: FinanceDB) -> None:
    with db.tx() as con:
        con.execute(
            'CREATE TABLE IF NOT EXISTS rich_ui_hidden_reviews('
            'pending_id TEXT PRIMARY KEY,hidden INTEGER NOT NULL DEFAULT 1,updated_at TEXT NOT NULL)'
        )


def _hide(db: FinanceDB, pending_id: str) -> None:
    with db.tx() as con:
        con.execute(
            'INSERT INTO rich_ui_hidden_reviews(pending_id,hidden,updated_at) VALUES(?,1,?)',
            (pending_id, '2026-08-10T10:00:00'),
        )


def _hidden(db: FinanceDB) -> set[str]:
    with db.read() as con:
        rows = con.execute('SELECT pending_id FROM rich_ui_hidden_reviews WHERE hidden=1').fetchall()
    return {row[0] for row in rows}


def test_reimporting_a_json_backup_reopens_deleted_receipts_and_keeps_approved(tmp_path, monkeypatch):
    db = FinanceDB(tmp_path / 'db.sqlite3')
    backup = _photo_backup(tmp_path, 3)
    receipts = ReceiptIntelligenceService(db, tmp_path, parser=None)

    first = import_telegram_export(db, backup, receipt_service=receipts)
    approved, rejected, waiting = first.media_pending_ids
    assert first.reopened_pending_ids == ()

    _hidden_table(db)
    db.update_pending(approved, status='APPROVED')
    _hide(db, approved)
    db.update_pending(rejected, status='REJECTED')
    _hide(db, rejected)

    again = import_telegram_export(db, backup, receipt_service=receipts)

    assert again.created == 0 and again.duplicates == 3
    assert set(again.media_pending_ids) == {rejected, waiting}
    assert again.reopened_pending_ids == (rejected,)
    assert db.get_pending_item(approved)['status'] == 'APPROVED'
    assert db.get_pending_item(rejected)['status'] == 'NEEDS_REVIEW'
    assert db.get_pending_item(waiting)['status'] == 'NEEDS_REVIEW'

    monkeypatch.setattr(d187, 'DB', db)
    restored = d187.DataEntryCenter187._unhide_imported_reviews_187(again.pending_ids)

    assert restored == 1
    assert _hidden(db) == {approved}


def test_unhide_handles_more_ids_than_one_sql_batch(tmp_path, monkeypatch):
    db = FinanceDB(tmp_path / 'db.sqlite3')
    _hidden_table(db)
    monkeypatch.setattr(d187, 'DB', db)
    assert d187.DataEntryCenter187._unhide_imported_reviews_187(()) == 0
    assert d187.DataEntryCenter187._unhide_imported_reviews_187([f'PEN-{i}' for i in range(1000)]) == 0


def test_latest_progress_keeps_the_last_count_when_nothing_new_arrived():
    events = Queue()
    assert d187.latest_reprocess_progress_187(events, 0) == 0
    events.put(3)
    events.put(4)
    assert d187.latest_reprocess_progress_187(events, 0) == 4
    assert d187.latest_reprocess_progress_187(events, 4) == 4


def test_api_gate_caps_concurrent_calls_and_passes_parser_attributes_through():
    class Parser:
        providers = [('GEMINI', object())]
        active = 0
        peak = 0

        async def analyze(self, **kwargs):
            Parser.active += 1
            Parser.peak = max(Parser.peak, Parser.active)
            await asyncio.sleep(0.02)
            Parser.active -= 1
            return {'text': kwargs['text']}

    parser = Parser()

    async def go():
        gate = d187.ReprocessApiGate187(parser, 3)
        results = await asyncio.gather(*(gate.analyze(text=str(i)) for i in range(12)))
        return gate, results

    gate, results = asyncio.run(go())

    assert Parser.peak == 3
    assert [item['text'] for item in results] == [str(i) for i in range(12)]
    assert gate.providers is Parser.providers


def _drive_batch(monkeypatch, *, kind, candidates, analyze=None, refresh=None, timeout=None,
                 approval=None, db=None):
    labels, shown, messages, scheduled, closed, phases = [], [], [], [], [], []
    progress: dict = {}
    status = SimpleNamespace(winfo_exists=lambda: True)
    fake = SimpleNamespace(
        _progress_dialog_187=lambda title, message, total=0: (
            status, SimpleNamespace(set=labels.append), progress),
        after=lambda _ms, callback: scheduled.append(callback),
        _close_progress_dialog_187=lambda *_args: closed.append(True),
        refresh=refresh or (lambda: None),
    )
    fake._refresh_after_reprocess_187 = (
        lambda: d187.DataEntryCenter187._refresh_after_reprocess_187(fake))
    fake._progress_phase_187 = lambda _label, _bar, message, total=None: phases.append(message)
    monkeypatch.setattr(d187, 'messagebox', SimpleNamespace(
        showinfo=lambda _t, text, **_k: messages.append(('info', text)),
        showwarning=lambda _t, text, **_k: messages.append(('warning', text)),
        showerror=lambda _t, text, **_k: messages.append(('error', text)),
    ))
    if approval is None:
        db = SimpleNamespace(
            get_pending_item=lambda _pid: {'payload': {'detected_type': 'EXPENSE', 'confidence': 0.9}},
            update_pending=lambda *_a, **_k: None,
        )
        approval = SimpleNamespace(
            receipts=SimpleNamespace(parser=SimpleNamespace(providers=[], analyze=None)),
            analyze_pending_with_ai=analyze,
            analyze_pending_text_only=lambda pid, _text: analyze(pid),
        )
    receipts = approval.receipts
    stub_parser = receipts.parser
    monkeypatch.setattr(d187, 'DB', db)
    monkeypatch.setattr(d187.v182, 'APPROVAL', approval)
    monkeypatch.delenv('OMP_THREAD_LIMIT', raising=False)
    if timeout is not None:
        monkeypatch.setattr(d187, 'REPROCESS_ITEM_TIMEOUT_187', timeout)

    center = d187.DataEntryCenter187
    if kind == 'image':
        center._start_image_reprocess_187(fake, candidates)
    else:
        center._start_text_reprocess_187(fake, candidates, ['متن'] * len(candidates))
    deadline = time.monotonic() + 20
    while not messages and time.monotonic() < deadline:
        if scheduled:
            scheduled.pop(0)()
        shown.append(progress.get('value'))
        time.sleep(0.01)
    return SimpleNamespace(
        messages=messages, shown=[v for v in shown if v is not None], labels=labels,
        closed=closed, parser=receipts.parser, stub=stub_parser, phases=phases,
    )


def _rows(count):
    return [{'pending_id': f'P{i}', 'payload': {}} for i in range(count)]


def test_image_batch_progress_only_moves_forward_and_runs_wide_but_gates_the_ai(monkeypatch):
    load = {'now': 0, 'peak': 0}
    seen = []

    async def analyze(_pid):
        load['now'] += 1
        load['peak'] = max(load['peak'], load['now'])
        seen.append((type(d187.v182.APPROVAL.receipts.parser).__name__,
                     os.environ.get('OMP_THREAD_LIMIT')))
        await asyncio.sleep(0.05)
        load['now'] -= 1
        return {}

    run = _drive_batch(monkeypatch, kind='image', candidates=_rows(12), analyze=analyze)

    assert run.messages and run.messages[0][0] == 'info'
    assert run.shown == sorted(run.shown), 'progress fell back to an earlier count'
    assert run.shown[-1] == 12
    assert any(0 < value < 12 for value in run.shown), 'progress never showed a partial count'
    assert load['peak'] == min(12, d187.REPROCESS_LOCAL_WORKERS_187)
    assert {name for name, _omp in seen} == {'ReprocessApiGate187'}
    assert {omp for _name, omp in seen} == {'1'}
    assert run.parser is run.stub
    assert 'OMP_THREAD_LIMIT' not in os.environ
    assert run.closed == [True]


def test_text_batch_progress_only_moves_forward(monkeypatch):
    async def analyze(_pid):
        await asyncio.sleep(0.05)
        return {}

    run = _drive_batch(monkeypatch, kind='text', candidates=_rows(9), analyze=analyze)

    assert run.messages and run.messages[0][0] == 'info'
    assert run.shown == sorted(run.shown)
    assert run.shown[-1] == 9
    assert any(0 < value < 9 for value in run.shown)


def test_a_stalled_receipt_is_reported_and_does_not_hold_the_batch(monkeypatch):
    async def analyze(pid):
        await asyncio.sleep(60 if pid == 'P1' else 0.01)
        return {}

    started = time.monotonic()
    run = _drive_batch(monkeypatch, kind='image', candidates=_rows(4), analyze=analyze, timeout=1)

    assert time.monotonic() - started < 10
    kind, text = run.messages[0]
    assert kind == 'warning'
    assert 'P1' in text and 'طول کشید' in text
    assert run.shown[-1] == 4


def test_a_failing_table_repaint_is_reported_without_hiding_the_batch_result(monkeypatch):
    async def analyze(_pid):
        return {}

    def broken_refresh():
        raise RuntimeError('repaint boom')

    run = _drive_batch(monkeypatch, kind='image', candidates=_rows(2), analyze=analyze,
                       refresh=broken_refresh)

    assert run.closed == [True]
    kind, text = run.messages[0]
    assert kind == 'info'
    assert 'repaint boom' in text


def test_json_backup_ends_processed_and_visible_in_the_pending_table(tmp_path, monkeypatch):
    db = FinanceDB(tmp_path / 'db.sqlite3')
    _hidden_table(db)
    backup = _photo_backup(tmp_path, 4)

    class Vision:
        async def analyze(self, **_kwargs):
            await asyncio.sleep(0.01)
            return {
                'detected_type': 'EXPENSE', 'document_type': 'RECEIPT', 'amount': 1_000_000,
                'final_amount': 1_000_000, 'confidence': 0.95, 'description': 'خرید مصالح',
                'field_confidences': {'amount': 0.95}, 'payment_state': 'PAID',
            }

    vision = Vision()
    approval = ApprovalCenterService(db, tmp_path, parser=vision)
    approval.receipts.ocr.extract = lambda _path: OCRResult('', 'TEST', False)

    first = import_telegram_export(db, backup, receipt_service=approval.receipts)
    assert len(first.media_pending_ids) == 4

    # What the Data Entry delete button does to two of the rows.
    for pending_id in first.media_pending_ids[:2]:
        approval.reject(pending_id)
        _hide(db, pending_id)

    again = import_telegram_export(db, backup, receipt_service=approval.receipts)
    monkeypatch.setattr(d187, 'DB', db)
    assert d187.DataEntryCenter187._unhide_imported_reviews_187(again.pending_ids) == 2

    def table_rows():
        hidden = _hidden(db)
        return [row for row in approval.list_reviews(limit=3000, newest_first=True)
                if str(row['pending_id']) not in hidden]

    assert {row['pending_id'] for row in table_rows()} == set(again.media_pending_ids)

    candidates = [db.get_pending_item(pid) for pid in again.media_pending_ids]
    run = _drive_batch(monkeypatch, kind='image', candidates=candidates,
                       approval=approval, db=db)

    assert run.messages[0][0] == 'info'
    assert run.parser is vision
    rows = table_rows()
    assert len(rows) == 4
    assert {row['status'] for row in rows} == {'PENDING_REVIEW'}
    assert {row['payload']['amount'] for row in rows} == {1_000_000}
    assert {row['payload']['detected_type'] for row in rows} == {'EXPENSE'}
