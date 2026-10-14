from types import SimpleNamespace

from telegram_album import prepare_album_entries, telegram_document_kind


def _entry(message_id, caption=''):
    message = SimpleNamespace(message_id=message_id, caption=caption, text=None)
    return (SimpleNamespace(effective_message=message), object())


def test_album_selects_tagged_message_as_review_anchor_and_keeps_every_other_image():
    entries = [_entry(52), _entry(50), _entry(51, '#تست شرح مشترک')]

    lead, extras = prepare_album_entries(entries, require_tag=True, test_tag='#تست')

    assert lead.message_id == 51
    assert [item.message_id for item in extras] == [50, 52]


def test_album_without_required_test_tag_is_rejected():
    lead, messages = prepare_album_entries([_entry(1, 'بدون برچسب')], require_tag=True, test_tag='#تست')

    assert lead is None
    assert len(messages) == 1


def test_live_album_keeps_first_captioned_message_as_anchor():
    lead, extras = prepare_album_entries([_entry(8), _entry(9, 'متن مشترک')], require_tag=False, test_tag='#تست')

    assert lead.message_id == 9
    assert [item.message_id for item in extras] == [8]


def test_telegram_document_allowlist_keeps_invoice_files_and_rejects_oversized_or_unknown_files():
    assert telegram_document_kind('application/pdf', 'invoice.pdf', 5000) == 'SUPPORTING_DOCUMENT'
    assert telegram_document_kind('image/jpeg', 'receipt.jpg', 5000) == 'IMAGE'
    assert telegram_document_kind('application/octet-stream', 'invoice.pdf', 5000) == 'SUPPORTING_DOCUMENT'
    assert telegram_document_kind('application/x-msdownload', 'invoice.pdf', 5000) is None
    assert telegram_document_kind('application/x-msdownload', 'program.exe', 5000) is None
    assert telegram_document_kind('application/pdf', 'invoice.pdf', 20 * 1024 * 1024 + 1) is None
