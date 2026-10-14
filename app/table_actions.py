"""Selection and confirmation rules shared by active table actions."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class DeleteChoice:
    permanent: bool = False
    grouped: bool = True


_confirmed_delete = ContextVar('barkav_confirmed_delete', default=None)


def normalize_delete_choice(value):
    if value is None:
        return None
    return value if isinstance(value, DeleteChoice) else DeleteChoice(bool(value))


def current_delete_choice():
    return _confirmed_delete.get()


@contextmanager
def confirmed_delete(choice):
    token = _confirmed_delete.set(choice)
    try:
        yield
    finally:
        _confirmed_delete.reset(token)


def select_delete_rows(parent, rows, *, messagebox, detail=''):
    """Take a stable snapshot before a handler refreshes its table."""
    from transaction_lifecycle_ui import confirm_delete
    rows = list(rows or [])
    if not rows:
        return []
    choice = normalize_delete_choice(confirm_delete(
        parent, len(rows), messagebox=messagebox, financial=False, detail=detail))
    if choice is None:
        return []
    return rows if choice.grouped else rows[:1]


def copy_payload(payload):
    from copy import deepcopy
    result = deepcopy(dict(payload or {}))
    for key in ('pending_id','posting_id','transaction_id','expense_id','cheque_id',
                'document_id','receive_transaction_id','payment_id','received_payment_id',
                'operation','sales_pending_action','land_expense_id187','_debt_source_pending_id187',
                '_cheque_hint187'):
        result.pop(key,None)
    if result.get('v18_title')=='ورودی' and result.get('v18_subtype')=='تسهیلات':
        result.pop('loan_id',None)
    return result


def copy_pending_attachments(db, source_id, target_id):
    """Give the copy its own attachment links while keeping receipt files intact."""
    source = db.get_pending_item(str(source_id)) if source_id else None
    if not source:
        return
    message = db.get_telegram_message(source['telegram_chat_id'], source['telegram_message_id']) or {}
    with db.read() as con:
        attachments = [dict(item) for item in con.execute(
            "SELECT * FROM attachments WHERE entity_type<>'RECEIPT_ARCHIVE' AND ("
            "(telegram_chat_id=? AND telegram_message_id=?) OR "
            "(entity_type='PENDING' AND entity_id=?) OR "
            "(entity_type=? AND entity_id=? AND telegram_chat_id IS NULL AND telegram_message_id IS NULL))",
            (source['telegram_chat_id'], source['telegram_message_id'], str(source_id),
             str(message.get('linked_entity_type') or '').upper(), str(message.get('linked_entity_id') or '')))]
    for item in attachments:
        db.attach_file_to_pending(
            pending_id=target_id,local_path=str(item.get('local_path') or ''),
            mime_type=str(item.get('mime_type') or ''),
            document_type=str(item.get('document_type') or 'RECEIPT'),
            telegram_file_id=item.get('telegram_file_id'),
            telegram_file_unique_id=item.get('telegram_file_unique_id'))
