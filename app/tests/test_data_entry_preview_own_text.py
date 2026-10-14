from __future__ import annotations

import os
import sys
import tempfile
import tkinter as tk
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_BOOT = tempfile.TemporaryDirectory()
os.environ.setdefault('STAGE4_DB_PATH', str(Path(_BOOT.name) / 'own_text.sqlite3'))
os.environ.setdefault('TELEGRAM_BOT_TOKEN', 'own-text-token')
os.environ.setdefault('GEMINI_API_KEY', 'own-text-gemini')
os.environ.setdefault('ADMIN_USER_ID', '187')
os.environ.setdefault('GROUP_CHAT_ID', '-100187')

import dashboard_stage18_2 as d182  # noqa: E402
import dashboard_stage18_7 as d187  # noqa: E402


@pytest.fixture()
def preview_host():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip('no display available')
    host = SimpleNamespace(
        preview=tk.Canvas(root), text=tk.Text(root), _path=lambda _row: None,
        _image=None, _tkimg=None, zoom=1,
    )
    yield host
    root.destroy()


def _shown(host, row) -> str:
    d182._DataEntryCenter182Final._show(host, row)
    return host.text.get('1.0', 'end').strip()


def _row(message_id, caption, **payload):
    return {
        'pending_id': f'PEN-{message_id}', 'telegram_chat_id': -1,
        'telegram_message_id': message_id, 'raw_text': caption,
        'payload': {'receipt_caption': caption, **payload},
    }


def test_each_receipt_shows_only_its_own_caption_never_a_neighbours(preview_host, monkeypatch):
    messages = {10: 'هزینه ساخت بتن فاز ۲', 11: 'خرید آهن‌آلات', 12: 'پرداخت دستمزد'}

    def neighbours(pending_id, window=3):
        mid = int(pending_id.split('-')[1])
        return {'nearby': [{'message_id': other, 'raw_text': text}
                           for other, text in messages.items() if other != mid]}

    monkeypatch.setattr(d182.APPROVAL, 'evidence_bundle', neighbours)

    for mid, caption in messages.items():
        assert _shown(preview_host, _row(mid, caption)) == caption


def test_a_receipt_without_a_caption_says_so_instead_of_borrowing_one(preview_host, monkeypatch):
    monkeypatch.setattr(d182.APPROVAL, 'evidence_bundle', lambda *a, **k: {
        'nearby': [{'message_id': 20, 'raw_text': 'متن رسید قبلی'}]})
    bare = _row(21, '')

    assert _shown(preview_host, bare) == 'متن همراه همین رسید ثبت نشده است.'


def test_no_layer_of_the_data_entry_tab_reads_neighbouring_messages_for_its_preview():
    layers = [
        cls for cls in d187.DataEntryCenter187.__mro__
        if '_show' in vars(cls) and cls.__module__.startswith('dashboard_stage18')
    ]

    assert d182._DataEntryCenter182Final in layers
    for cls in layers:
        assert 'evidence_bundle' not in vars(cls)['_show'].__code__.co_names, cls
