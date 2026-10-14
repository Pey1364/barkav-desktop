from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_BOOT = tempfile.TemporaryDirectory()
os.environ.setdefault('STAGE4_DB_PATH', str(Path(_BOOT.name) / 'separate.sqlite3'))
os.environ.setdefault('TELEGRAM_BOT_TOKEN', 'separate-token')
os.environ.setdefault('GEMINI_API_KEY', 'separate-gemini')
os.environ.setdefault('ADMIN_USER_ID', '1')
os.environ.setdefault('GROUP_CHAT_ID', '-1001')

import telegram_stage15 as bot  # noqa: E402
from approval_service import ApprovalCenterService  # noqa: E402
from finance_db import FinanceDB  # noqa: E402
from telegram_workflow import TelegramReviewWorkflow  # noqa: E402

CHAT_ID = -1001


def _update(message_id, *, text='', photo=False):
    message = SimpleNamespace(
        message_id=message_id, caption=text if photo else None, text=None if photo else text,
        photo=[object()] if photo else [], document=None,
        date=datetime(2026, 9, 29, 10, message_id % 60, tzinfo=ZoneInfo('Asia/Tehran')),
    )
    return SimpleNamespace(
        effective_message=message, effective_user=SimpleNamespace(id=1),
        effective_chat=SimpleNamespace(id=CHAT_ID, type='supergroup'),
    )


def _wire(monkeypatch, tmp_path):
    db = FinanceDB(tmp_path / 'db.sqlite3')
    reviews = []

    async def learn_group(*_args):
        return True

    async def analyze_text(_message, _context, text, _date):
        return {'detected_type': 'INFO', 'amount': 0, 'confidence': 0.5, 'description': text}

    async def download(_message, _context, pending_id):
        db.attach_file_to_pending(
            pending_id=pending_id, local_path=str(tmp_path / f'{pending_id}.jpg'),
            mime_type='image/jpeg', document_type='RECEIPT',
        )
        return str(tmp_path / f'{pending_id}.jpg')

    async def analyze_archived(*, pending_id, caption, image_path, message_date_shamsi):
        return {'status': 'PENDING_REVIEW', 'payload': {
            'detected_type': 'EXPENSE', 'amount': 4_000_000, 'confidence': 0.9,
            'description': caption, 'receipt_caption': caption,
        }}

    async def send_review(_message, _context, pending_id, payload):
        reviews.append(pending_id)

    monkeypatch.setattr(bot, 'DB', db)
    monkeypatch.setattr(bot, 'CONFIG', SimpleNamespace(admin_user_id=1, require_test_tag=False, test_tag='#'))
    monkeypatch.setattr(bot, 'APPROVAL', ApprovalCenterService(db, tmp_path))
    monkeypatch.setattr(bot, 'RECEIPTS', SimpleNamespace(analyze_archived=analyze_archived))
    monkeypatch.setattr(bot.s6, 'WORKFLOW', TelegramReviewWorkflow(db))
    monkeypatch.setattr(bot.s6, '_maybe_learn_group', learn_group)
    monkeypatch.setattr(bot.s6, '_analyze_message_payload', analyze_text)
    monkeypatch.setattr(bot, '_record_inbound', lambda *_a, **_k: None)
    monkeypatch.setattr(bot, '_download_media_archive', download)
    monkeypatch.setattr(bot, '_send_private_review_if_enabled', send_review)
    return db, reviews


def _run(update):
    asyncio.run(bot._handle_regular_financial_message(update, SimpleNamespace(bot=None)))


def _pending(db, message_id):
    return db.get_pending_by_message(CHAT_ID, message_id)


def test_a_note_after_a_receipt_stays_its_own_record_and_the_receipt_keeps_only_its_caption(
        monkeypatch, tmp_path):
    db, reviews = _wire(monkeypatch, tmp_path)

    _run(_update(601, text='خرید آهن‌آلات', photo=True))
    _run(_update(602, text='بتن‌ریزی سقف دوم انجام شد'))

    receipt, note = _pending(db, 601), _pending(db, 602)
    assert receipt['status'] == 'PENDING_REVIEW' and note['status'] in {'PENDING_REVIEW', 'NEEDS_REVIEW'}
    assert reviews == [receipt['pending_id'], note['pending_id']]
    assert 'related_pending_ids' not in receipt['payload']
    assert 'linked_to_pending_id' not in note['payload']
    assert receipt['payload']['receipt_caption'] == 'خرید آهن‌آلات'
    assert len(db.list_pending_attachments(receipt['pending_id'])) == 1
    assert db.list_pending_attachments(note['pending_id']) == []


def test_a_note_before_a_receipt_stays_its_own_record_too(monkeypatch, tmp_path):
    db, reviews = _wire(monkeypatch, tmp_path)

    _run(_update(611, text='تحویل بار در محل انجام شد'))
    _run(_update(612, text='پرداخت دستمزد', photo=True))

    note, receipt = _pending(db, 611), _pending(db, 612)
    assert note['status'] in {'PENDING_REVIEW', 'NEEDS_REVIEW'} and receipt['status'] == 'PENDING_REVIEW'
    assert reviews == [note['pending_id'], receipt['pending_id']]
    assert 'related_pending_ids' not in receipt['payload']
    assert len(db.list_pending_attachments(receipt['pending_id'])) == 1


def test_two_receipts_with_the_same_amount_are_never_merged(monkeypatch, tmp_path):
    db, reviews = _wire(monkeypatch, tmp_path)

    _run(_update(621, text='قسط اول', photo=True))
    _run(_update(622, text='قسط دوم', photo=True))

    first, second = _pending(db, 621), _pending(db, 622)
    assert first['status'] == second['status'] == 'PENDING_REVIEW'
    assert reviews == [first['pending_id'], second['pending_id']]
    assert [len(db.list_pending_attachments(item['pending_id'])) for item in (first, second)] == [1, 1]
    assert first['payload']['receipt_caption'] == 'قسط اول'
    assert second['payload']['receipt_caption'] == 'قسط دوم'


def test_the_joining_hooks_are_gone():
    assert not hasattr(bot, '_link_adjacent_pending_evidence')
    assert not hasattr(ApprovalCenterService, 'link_pending_evidence')
