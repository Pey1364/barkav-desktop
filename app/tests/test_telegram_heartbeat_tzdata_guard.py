"""Coverage for telegram_stage15's heartbeat tzdata crash guard.

Ported from origin/master (HANDOFF entry 12): _record_inbound is a
diagnostics-only heartbeat write called on every single inbound group
message. It used ZoneInfo(os.getenv("PEYMAAN_TIMEZONE", "Asia/Tehran")) with
no try/except. Windows Python ships no IANA tz database and the tzdata pip
package was never in any requirements file, so a fresh install without it
raised ZoneInfoNotFoundError uncaught, which propagated straight into the
real message handlers that call this - aborting every inbound group message,
in both groups, identically, for about a week before this was diagnosed.

This test reproduces the exact failure mode (a bad/unresolvable timezone
name) without needing a real missing-tzdata environment, and confirms
neither function lets that exception escape.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault('TELEGRAM_BOT_TOKEN', 'test-token')
os.environ.setdefault('GEMINI_API_KEY', 'test-gemini-key')
os.environ.setdefault('ADMIN_USER_ID', '1')
os.environ.setdefault('GROUP_CHAT_ID', '-1')

import telegram_stage15 as s15


class _FakeMessage:
    photo = None
    document = None
    message_id = 42


def test_record_inbound_survives_an_unresolvable_timezone(monkeypatch):
    monkeypatch.setenv('PEYMAAN_TIMEZONE', 'Not/A_Real_Zone')
    writes = []
    monkeypatch.setattr(s15, '_write_runtime_json', lambda path, payload: writes.append(payload))

    # Must not raise - this is exactly what took down real message handling
    # for a week when tzdata was missing (ZoneInfo raising the same way).
    s15._record_inbound(_FakeMessage(), chat_id=-100123, state='ACCEPTED')

    # The heartbeat write itself is best-effort: it's fine that it didn't
    # happen (ZoneInfo failed before _write_runtime_json was ever called),
    # the guarantee is only that the caller never sees an exception.
    assert writes == []


def test_record_receipt_error_survives_an_unresolvable_timezone(monkeypatch):
    monkeypatch.setenv('PEYMAAN_TIMEZONE', 'Not/A_Real_Zone')
    writes = []
    monkeypatch.setattr(s15, '_write_runtime_json', lambda path, payload: writes.append(payload))

    s15._record_receipt_error(_FakeMessage(), chat_id=-100123, pending_id='PEN-1',
                              exc=ValueError('boom'))

    assert writes == []


def test_record_inbound_writes_the_heartbeat_on_a_valid_timezone(monkeypatch):
    monkeypatch.setenv('PEYMAAN_TIMEZONE', 'Asia/Tehran')
    writes = []
    monkeypatch.setattr(s15, '_write_runtime_json', lambda path, payload: writes.append(payload))

    s15._record_inbound(_FakeMessage(), chat_id=-100123, state='ACCEPTED')

    # The try/except guard must not swallow the normal, working path.
    assert len(writes) == 1
    assert writes[0]['chat_id'] == -100123
    assert writes[0]['content_type'] == 'TEXT'
