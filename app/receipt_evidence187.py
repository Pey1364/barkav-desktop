"""Receipt evidence edits, independent of transaction approval or cash effects."""
from __future__ import annotations

import hashlib
import io
import json
import mimetypes
import os
import shutil
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageGrab, ImageOps
from finance_db import _now

EVIDENCE_KEYS = ('receipt_image_path', 'receipt_image_deleted187', 'receipt_caption')


def _sync_lifecycle(db, con, pending_id, *, payload=None, detached=(), link=None):
    """Reconcile explicit receipt edits while retaining every financial effect."""
    if not con.execute("SELECT 1 FROM sqlite_master WHERE name='transaction_lifecycle'").fetchone():
        return
    record = con.execute('SELECT * FROM transaction_lifecycle WHERE pending_id=?', (pending_id,)).fetchone()
    if not record or record['state'] == 'PURGED':
        return
    def keep(effect):
        return not (effect['table'] == 'attachments' and effect['key'][0] in detached)
    effects = [effect for effect in json.loads(record['effects_json']) if keep(effect)]
    rejected = [effect for effect in json.loads(record['rejected_json']) if keep(effect)]
    if link:
        effects.append(link)
        if record['state'] == 'REJECTED':
            rejected.append(dict(link, rejected=link['before']))
    saved = json.loads(record['payload_json'])
    if payload is not None:
        saved.update({key: payload[key] for key in EVIDENCE_KEYS if key in payload})
    con.execute('UPDATE transaction_lifecycle SET effects_json=?,rejected_json=?,payload_json=?,updated_at=? WHERE pending_id=?',
        (json.dumps(effects, ensure_ascii=False), json.dumps(rejected, ensure_ascii=False),
         json.dumps(saved, ensure_ascii=False), _now(), pending_id))
    db._audit(con, 'transaction_lifecycle', pending_id, 'RECEIPT_EDIT', 'GUI_187_RECEIPT',
              before=dict(record), after=dict(con.execute('SELECT * FROM transaction_lifecycle WHERE pending_id=?', (pending_id,)).fetchone()), actor_id='GUI')


def clipboard_image():
    value = ImageGrab.grabclipboard()
    if isinstance(value, Image.Image):
        return value
    if isinstance(value, list):
        for path in value:
            try:
                with Image.open(path) as image:
                    return ImageOps.exif_transpose(image).convert('RGB')
            except (OSError, ValueError):
                continue
    return None


def copy_image(image, owner):
    """Publish a bitmap, so paste works in image editors and other applications."""
    if os.name != 'nt':
        raise OSError('کپی تصویر در این سیستم پشتیبانی نمی‌شود.')
    import ctypes
    from ctypes import wintypes
    user = ctypes.WinDLL('user32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    user.OpenClipboard.argtypes = [wintypes.HWND]
    user.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user.SetClipboardData.restype = wintypes.HANDLE
    kernel.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel.GlobalLock.restype = ctypes.c_void_p
    kernel.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel.GlobalFree.argtypes = [wintypes.HGLOBAL]
    stream = io.BytesIO()
    image.convert('RGB').save(stream, format='BMP')
    data = stream.getvalue()[14:]
    if not user.OpenClipboard(owner):
        raise OSError('کلیپ‌بورد در دسترس نیست؛ دوباره کپی کنید.')
    memory = None
    try:
        memory = kernel.GlobalAlloc(0x0002, len(data))
        pointer = kernel.GlobalLock(memory) if memory else None
        if not pointer:
            raise OSError('کپی تصویر انجام نشد.')
        ctypes.memmove(pointer, data, len(data))
        kernel.GlobalUnlock(memory)
        if not user.EmptyClipboard() or not user.SetClipboardData(8, memory):
            raise OSError('کپی تصویر انجام نشد.')
        memory = None  # Clipboard now owns this allocation.
    finally:
        if memory:
            kernel.GlobalFree(memory)
        user.CloseClipboard()


def save_evidence(db, pending_id, changes):
    with db.atomic() as con:
        item = db.get_pending_item(pending_id)
        if not item:
            raise KeyError(pending_id)
        before = dict(item['payload'])
        payload = dict(before, **{key: changes[key] for key in EVIDENCE_KEYS if key in changes})
        db.update_pending(pending_id, payload=payload)
        db._audit(con, 'pending_receipt', pending_id, 'UPDATE', 'GUI_187_RECEIPT',
                  before=before, after=payload, actor_id='GUI')
        _sync_lifecycle(db, con, pending_id, payload=payload)
    return db.get_pending_item(pending_id)


def upload_file(db, pending_id, source, document_type='DATA_ENTRY_FILE'):
    """Archive any non-image Data Entry file and attach it without changing receipt fields."""
    source = Path(source)
    if not source.is_file():
        raise FileNotFoundError(str(source))
    safe_name = ''.join(char for char in source.name if char not in '<>:"/\\|?*').strip() or 'attachment'
    archive = Path(db.db_path).parent / 'receipt_archive' / 'files'
    archive.mkdir(parents=True, exist_ok=True)
    archived_path = archive / f'{uuid4().hex}_{safe_name}'
    shutil.copy2(source, archived_path)
    mime_type = mimetypes.guess_type(source.name)[0] or 'application/octet-stream'
    if mime_type.lower().startswith('image/'):
        # Files routed here were not decodable images; keep them out of AI image selection.
        mime_type = 'application/octet-stream'
    try:
        with db.atomic() as con:
            item = db.get_pending_item(pending_id)
            if not item:
                raise KeyError(pending_id)
            attachment_id = db.attach_file_to_pending(
                pending_id=pending_id, local_path=str(archived_path),
                mime_type=mime_type, document_type=document_type,
            )
            attachment = dict(con.execute(
                'SELECT * FROM attachments WHERE attachment_id=?', (attachment_id,),
            ).fetchone())
            message = db.get_telegram_message(
                item['telegram_chat_id'], item['telegram_message_id'],
            ) or {}
            linked_type = str(message.get('linked_entity_type') or '').upper()
            linked_id = str(message.get('linked_entity_id') or '')
            if item['status'] == 'APPROVED' and linked_type and linked_id:
                con.execute(
                    'UPDATE attachments SET entity_type=?,entity_id=? WHERE attachment_id=?',
                    (linked_type, linked_id, attachment_id),
                )
            current = dict(con.execute(
                'SELECT * FROM attachments WHERE attachment_id=?', (attachment_id,),
            ).fetchone())
            db._audit(con, 'attachment', attachment_id, 'CREATE', 'GUI_187_FILE',
                      after=current, actor_id='GUI')
            if item['status'] in {'APPROVED', 'REJECTED'} and linked_type and linked_id:
                _sync_lifecycle(db, con, pending_id, link=dict(
                    table='attachments', pk=['attachment_id'], key=[attachment_id],
                    before=attachment,
                    after=dict(attachment, entity_type=linked_type, entity_id=linked_id),
                ))
        return {
            'attachment_id': attachment_id,
            'local_path': str(archived_path),
            'file_name': safe_name,
            'mime_type': mime_type,
            'document_type': document_type,
        }
    except Exception:
        archived_path.unlink(missing_ok=True)
        raise


def is_image_file(source):
    """Distinguish image evidence from arbitrary attached files by decoding it."""
    if isinstance(source, Image.Image):
        return True
    try:
        with Image.open(source) as image:
            image.verify()
        return True
    except Exception:
        return False


def upload_image(db, pending_id, source, caption):
    if isinstance(source, Image.Image):
        image = ImageOps.exif_transpose(source).convert('RGB')
    else:
        with Image.open(source) as original:
            image = ImageOps.exif_transpose(original).convert('RGB')
    archive = Path(db.db_path).parent / 'receipt_archive' / 'manual'
    archive.mkdir(parents=True, exist_ok=True)
    path = archive / (uuid4().hex + '.png')
    image.save(path, format='PNG')
    try:
        with db.atomic() as con:
            item = db.get_pending_item(pending_id)
            # Legacy records may have only a receipt pointer, not an attachment
            # row. Preserve it before selecting the newly uploaded image.
            old = (item.get('payload') or {}).get('receipt_image_path') or ''
            if old and not (item.get('payload') or {}).get('receipt_image_deleted187') and Path(old).is_file():
                attached = db.list_pending_attachments(pending_id)
                message = db.get_telegram_message(item['telegram_chat_id'],item['telegram_message_id']) or {}
                if message.get('linked_entity_id'):
                    attached += db.list_entity_attachments(message['linked_entity_type'],message['linked_entity_id'])
                if not any(str(row.get('local_path') or '') == str(old) for row in attached):
                    db.attach_file_to_pending(pending_id=pending_id,local_path=str(old),mime_type='image/png')
            aid = db.attach_file_to_pending(pending_id=pending_id, local_path=str(path), mime_type='image/png')
            attachment = dict(con.execute('SELECT * FROM attachments WHERE attachment_id=?', (aid,)).fetchone())
            message = db.get_telegram_message(item['telegram_chat_id'], item['telegram_message_id']) or {}
            if item['status'] == 'APPROVED' and message.get('linked_entity_id'):
                con.execute('UPDATE attachments SET entity_type=?,entity_id=? WHERE attachment_id=?',
                    (str(message['linked_entity_type']).upper(), message['linked_entity_id'], aid))
            db._audit(con, 'attachment', aid, 'CREATE', 'GUI_187_RECEIPT',
                      after=dict(con.execute('SELECT * FROM attachments WHERE attachment_id=?', (aid,)).fetchone()), actor_id='GUI')
            saved = save_evidence(db, pending_id, dict(receipt_image_path=str(path),
                receipt_image_deleted187=False, receipt_caption=caption))
            if item['status'] in {'APPROVED', 'REJECTED'} and message.get('linked_entity_id'):
                _sync_lifecycle(db, con, pending_id, link=dict(table='attachments', pk=['attachment_id'],
                    key=[aid], before=attachment, after=dict(attachment,
                        entity_type=str(message['linked_entity_type']).upper(), entity_id=message['linked_entity_id'])))
            return saved
    except Exception:
        path.unlink(missing_ok=True)
        raise


def replace_image(db, pending_id, visible_path, image, caption):
    """Swap one document for an edited copy of it (rotated, cropped). The edited picture becomes the receipt;
    the original file stays in the archive, unlinked like a deleted document, so the edit can be undone."""
    saved = upload_image(db, pending_id, image, caption)
    new_path = saved['payload']['receipt_image_path']
    if str(visible_path or '') and str(visible_path) != str(new_path):
        saved = remove_image(db, pending_id, visible_path, caption)
    return saved


def remove_image(db, pending_id, visible_path, caption):
    """Unlink only the selected document; retain its file and audit trail."""
    with db.atomic() as con:
        item = db.get_pending_item(pending_id)
        message = db.get_telegram_message(item['telegram_chat_id'], item['telegram_message_id']) or {}
        current_image = str((item.get('payload') or {}).get('receipt_image_path') or '')
        attachments = db.list_pending_attachments(pending_id)
        if message.get('linked_entity_type') and message.get('linked_entity_id'):
            attachments += db.list_entity_attachments(message['linked_entity_type'], message['linked_entity_id'])
        detached = set()
        for attachment in attachments:
            path = Path(str(attachment.get('local_path') or ''))
            if str(path) != str(visible_path):
                continue
            con.execute("UPDATE attachments SET entity_type='RECEIPT_ARCHIVE',entity_id=? WHERE attachment_id=?",
                        (pending_id, attachment['attachment_id']))
            detached.add(attachment['attachment_id'])
            db._audit(con, 'attachment', attachment['attachment_id'], 'UNLINK', 'GUI_187_RECEIPT',
                      before=attachment, after=dict(attachment, entity_type='RECEIPT_ARCHIVE', entity_id=pending_id), actor_id='GUI')
        saved = item
        if current_image == str(visible_path):
            replacement = ''
            for attachment in attachments:
                path = str(attachment.get('local_path') or '')
                if not path or path == str(visible_path) or attachment.get('attachment_id') in detached:
                    continue
                if Path(path).is_file() and is_image_file(path):
                    replacement = path
                    break
            saved = save_evidence(db, pending_id, dict(
                receipt_image_path=replacement,
                receipt_image_deleted187=not bool(replacement),
                receipt_caption=caption,
            ))
        elif caption != str((item.get('payload') or {}).get('receipt_caption') or ''):
            saved = save_evidence(db, pending_id, {'receipt_caption': caption})
        _sync_lifecycle(db, con, pending_id, detached=detached)
        return saved


def restore_archived_image(db, pending_id, source_path, caption):
    """Restore an image unlinked by ``remove_image`` without duplicating its file."""
    source_path = str(source_path or '')
    source = Path(source_path)
    if not source.is_file():
        raise FileNotFoundError('فایل رسید آرشیوشده پیدا نشد.')
    digest = hashlib.sha256(source.read_bytes()).hexdigest()

    with db.atomic() as con:
        item = db.get_pending_item(pending_id)
        if not item:
            raise KeyError(pending_id)
        message = db.get_telegram_message(item['telegram_chat_id'], item['telegram_message_id']) or {}
        candidates = [dict(row) for row in con.execute(
            "SELECT * FROM attachments WHERE entity_type='RECEIPT_ARCHIVE' AND entity_id=?",
            (pending_id,),
        ).fetchall()]
        archived = []
        for attachment in candidates:
            path = Path(str(attachment.get('local_path') or ''))
            same = str(path) == source_path
            if not same and path.is_file():
                try:
                    same = hashlib.sha256(path.read_bytes()).hexdigest() == digest
                except OSError:
                    same = False
            if same:
                archived.append(attachment)
        if not archived:
            # Some legacy previews refer to the receipt analysis file without
            # a matching attachment row. Reuse the normal audited upload path.
            return upload_image(db, pending_id, source_path, caption)

        linked_type = str(message.get('linked_entity_type') or '').upper()
        linked_id = str(message.get('linked_entity_id') or '')
        for attachment in archived:
            attachment_id = str(attachment['attachment_id'])
            pending_link = dict(attachment, entity_type='PENDING', entity_id=str(pending_id))
            actual_link = pending_link
            if str(item.get('status') or '').upper() == 'APPROVED' and linked_type and linked_id:
                actual_link = dict(pending_link, entity_type=linked_type, entity_id=linked_id)
            con.execute(
                "UPDATE attachments SET entity_type=?,entity_id=? WHERE attachment_id=? "
                "AND entity_type='RECEIPT_ARCHIVE' AND entity_id=?",
                (actual_link['entity_type'], actual_link['entity_id'], attachment_id, pending_id),
            )
            db._audit(
                con, 'attachment', attachment_id, 'RESTORE', 'GUI_187_RECEIPT',
                before=attachment, after=actual_link, actor_id='GUI',
            )
            if (str(item.get('status') or '').upper() in {'APPROVED', 'REJECTED'}
                    and linked_type and linked_id):
                _sync_lifecycle(db, con, pending_id, link={
                    'table': 'attachments', 'pk': ['attachment_id'],
                    'key': [attachment_id], 'before': pending_link,
                    'after': dict(pending_link, entity_type=linked_type, entity_id=linked_id),
                })
        return save_evidence(db, pending_id, dict(
            receipt_image_path=source_path,
            receipt_image_deleted187=False,
            receipt_caption=caption,
        ))
