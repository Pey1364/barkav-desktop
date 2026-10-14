from __future__ import annotations

import asyncio

from approval_service import ApprovalCenterService


class FakeParser:
    def __init__(self):
        self.calls = []

    async def analyze(self, **kwargs):
        self.calls.append(kwargs)
        return {
            'detected_type': 'EXPENSE', 'confidence': 0.9,
            'amount': 2500, 'description': 'سیمان',
        }


class FakeDB:
    def __init__(self):
        self.item = {'pending_id': 'P-1', 'status': 'NEEDS_REVIEW', 'telegram_chat_id': -1, 'telegram_message_id': 7}
        self.saved = None

    def get_pending_item(self, _pending_id):
        return dict(self.item)

    def apply_learned_rules(self, _text, payload):
        return dict(payload)

    def update_pending(self, pending_id, **kwargs):
        self.saved = (pending_id, kwargs)

    def update_telegram_message(self, **kwargs):
        self.telegram_update = kwargs


def test_text_only_reprocess_uses_only_preview_text_and_keeps_item_reviewable():
    service = object.__new__(ApprovalCenterService)
    service.db = FakeDB()
    parser = FakeParser()
    service.receipts = type('Receipts', (), {'parser': parser})()

    result = asyncio.run(service.analyze_pending_text_only('P-1', 'فاکتور سیمان مبلغ ۲۵۰۰ تومان'))

    assert len(parser.calls) == 1
    assert parser.calls[0]['image_bytes'] is None
    assert parser.calls[0]['text'] == 'فاکتور سیمان مبلغ ۲۵۰۰ تومان'
    assert result['payload']['reprocess_mode'] == 'TEXT_ONLY'
    assert service.db.saved[1]['status'] == 'PENDING_REVIEW'
    assert service.db.telegram_update['state'] == 'PENDING_REVIEW'
