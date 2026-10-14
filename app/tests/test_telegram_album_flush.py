"""One Telegram album -> one review transaction, even when its parts arrive late."""

from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest

import telegram_stage15 as bot


class FakeDB:
    def __init__(self):
        self.messages: dict[tuple[int, int], dict] = {}
        self.pending: dict[str, dict] = {}

    def get_telegram_message(self, chat_id, message_id):
        return self.messages.get((int(chat_id), int(message_id)))

    def register_telegram_message(self, *, chat_id, message_id, **fields):
        key = (int(chat_id), int(message_id))
        if key in self.messages:
            return False
        self.messages[key] = dict(fields)
        return True

    def update_telegram_message(self, *, chat_id, message_id, **fields):
        self.messages[(int(chat_id), int(message_id))].update(fields)

    def get_pending_by_message(self, chat_id, message_id):
        return next((dict(p) for p in self.pending.values()
                     if (p['telegram_chat_id'], p['telegram_message_id']) == (chat_id, message_id)), None)

    def get_pending_item(self, pending_id):
        item = self.pending.get(pending_id)
        return dict(item) if item else None

    def update_pending(self, pending_id, *, payload):
        self.pending[pending_id]['payload'] = payload


def _message(message_id, caption=''):
    return SimpleNamespace(message_id=message_id, caption=caption, text=None, photo=[object()],
                           document=None, date=datetime(2026, 9, 27, 10, 0))


@pytest.fixture()
def fake_bot(monkeypatch):
    db = FakeDB()
    handled, archived = [], []

    async def handle(update, _context):
        message = update.effective_message
        handled.append(message.message_id)
        await asyncio.sleep(0.2)  # the AI read of the lead photo takes a while
        db.register_telegram_message(chat_id=-1, message_id=message.message_id)
        db.pending['PEN-1'] = {'pending_id': 'PEN-1', 'telegram_chat_id': -1,
                               'telegram_message_id': message.message_id,
                               'status': 'PENDING_REVIEW', 'payload': {}}

    async def download(item, _context, pending_id):
        archived.append((item.message_id, pending_id))
        return 'ok'

    monkeypatch.setattr(bot, 'DB', db)
    monkeypatch.setattr(bot, '_handle_regular_financial_message', handle)
    monkeypatch.setattr(bot, '_download_media_archive', download)
    monkeypatch.setattr(bot, 'ALBUM_SETTLE_SECONDS', 0.05)
    # A stand-in, never the real config: it carries the bot's keys.
    monkeypatch.setattr(bot, 'CONFIG', SimpleNamespace(require_test_tag=False, test_tag=''))
    bot._MEDIA_ALBUMS.clear()
    bot._MEDIA_ALBUM_TASKS.clear()
    bot._MEDIA_ALBUM_STATE.clear()
    return db, handled, archived


def _arrive(key, message):
    bot._MEDIA_ALBUMS.setdefault(key, []).append((SimpleNamespace(effective_message=message), None))
    old = bot._MEDIA_ALBUM_TASKS.get(key)
    if old and not old.done():
        old.cancel()
    bot._MEDIA_ALBUM_TASKS[key] = asyncio.get_running_loop().create_task(bot._flush_media_album(key))
    return bot._MEDIA_ALBUM_TASKS[key]


def test_a_part_arriving_while_the_lead_is_analysed_joins_the_same_transaction(fake_bot):
    db, handled, archived = fake_bot
    key = (-1, 'album-1')

    async def scenario():
        _arrive(key, _message(11, 'هزینه ساخت\nمصالح'))
        first = _arrive(key, _message(12))
        await asyncio.sleep(0.1)          # the album is flushed; the lead is being read
        late = _arrive(key, _message(13, 'قبض دوم'))
        await asyncio.gather(first, late)
        await asyncio.sleep(0.1)
        # Arriving after the row exists, a part is still attached, not a new row.
        await _arrive(key, _message(14))

    asyncio.run(scenario())
    assert handled == [11]                       # one transaction, analysed once
    assert len(db.pending) == 1
    assert sorted(m for m, _p in archived) == [12, 13, 14]
    assert {p for _m, p in archived} == {'PEN-1'}
    for message_id in (12, 13, 14):
        assert db.messages[(-1, message_id)]['linked_entity_id'] == 'PEN-1'
    assert db.pending['PEN-1']['payload']['related_document_captions'] == ['هزینه ساخت\nمصالح', 'قبض دوم']


def test_two_albums_stay_two_transactions(fake_bot):
    db, handled, _archived = fake_bot

    async def scenario():
        a = _arrive((-1, 'a'), _message(21, 'اولی'))
        await a
        db.pending['PEN-A'] = db.pending.pop('PEN-1')
        b = _arrive((-1, 'b'), _message(31, 'دومی'))
        await b

    asyncio.run(scenario())
    assert handled == [21, 31]
