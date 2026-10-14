"""Pure helpers for coalescing Telegram media-group updates."""
from __future__ import annotations


def prepare_album_entries(entries, *, require_tag: bool, test_tag: str):
    messages = sorted(
        (entry[0].effective_message for entry in entries if entry[0].effective_message),
        key=lambda item: int(item.message_id),
    )
    if not messages:
        return None, ()

    def text(item):
        return str(getattr(item, 'caption', None) or getattr(item, 'text', None) or '').strip()

    if require_tag:
        tagged = [item for item in messages if test_tag in text(item)]
        if not tagged:
            return None, tuple(messages)
        lead = tagged[0]
    else:
        lead = next((item for item in messages if text(item)), messages[0])
    return lead, tuple(item for item in messages if item is not lead)


def telegram_document_kind(mime_type, file_name, file_size):
    """Return IMAGE/SUPPORTING_DOCUMENT for safe common files within Telegram's cap."""
    if int(file_size or 0) > 20 * 1024 * 1024:
        return None
    mime = str(mime_type or '').lower()
    suffix = str(file_name or '').lower().rsplit('.', 1)[-1] if '.' in str(file_name or '') else ''
    if mime.startswith('image/'):
        return 'IMAGE'
    if mime in {'', 'application/octet-stream'} and suffix in {'jpg', 'jpeg', 'png', 'webp', 'bmp', 'tif', 'tiff'}:
        return 'IMAGE'
    supported_mimes = {
        'application/pdf', 'text/plain', 'application/msword',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    }
    if mime in supported_mimes or (mime in {'', 'application/octet-stream'} and suffix in {'pdf', 'txt', 'doc', 'docx', 'xls', 'xlsx'}):
        return 'SUPPORTING_DOCUMENT'
    return None
