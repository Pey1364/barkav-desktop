from __future__ import annotations

import json
from typing import Any

from finance_db import FinanceDB, _now
from telegram_stage5_workflow import TelegramStage5Workflow
from receipt_intelligence import ReceiptIntelligenceService
from ai_parser import normalize_construction_stage


class ApprovalCenterService:
    """Shared approval application service used by GUI and Telegram.

    SQLite remains the single source of truth. GUI approvals create the same
    FinancialPosting records as Telegram approvals. Telegram side-effects are
    queued in integration_events so the bot process can apply reactions/update
    the private review card without coupling the GUI to Telegram networking.
    """
    def __init__(self, db: FinanceDB, base_dir, parser=None):
        self.db = db
        self.workflow = TelegramStage5Workflow(db)
        self.receipts = ReceiptIntelligenceService(db, base_dir, parser=parser)

    def list_pending(self, limit: int = 500) -> list[dict[str, Any]]:
        return self.db.list_pending_reviews(limit=limit)

    def list_reviews(self, statuses=("PENDING_REVIEW","NEEDS_REVIEW","APPROVED","REJECTED","EDIT_PENDING"),
                     limit:int=2000, *, newest_first: bool = False) -> list[dict[str,Any]]:
        return self.db.list_pending_reviews(
            statuses=tuple(statuses), limit=limit, newest_first=newest_first,
        )

    def evidence_bundle(self,pending_id:str,window:int=3)->dict[str,Any]:
        item=self.db.get_pending_item(pending_id)
        if not item:raise KeyError(pending_id)
        chat=int(item['telegram_chat_id']);mid=int(item['telegram_message_id'])
        with self.db.read() as con:
            current=con.execute('SELECT * FROM telegram_messages WHERE chat_id=? AND message_id=?',(chat,mid)).fetchone()
            nearby=con.execute('SELECT * FROM telegram_messages WHERE chat_id=? AND message_id BETWEEN ? AND ? ORDER BY message_id',(chat,mid-max(1,int(window)),mid+max(1,int(window)))).fetchall()
        atts=self.db.list_pending_attachments(pending_id)
        return {'current':dict(current) if current else {},'nearby':[dict(x) for x in nearby if int(x['message_id'])!=mid],'attachments':atts,'pending':item}

    def save_payload(self, pending_id: str, new_payload: dict[str, Any], *, learn: bool = True) -> dict[str, Any]:
        item = self.db.get_pending_item(pending_id)
        if not item:
            raise KeyError(pending_id)
        if item.get("status") not in {"PENDING_REVIEW", "NEEDS_REVIEW"}:
            raise ValueError("این مورد دیگر در انتظار تأیید نیست.")
        before = dict(item.get("payload") or {})
        detected = str(new_payload.get("detected_type") or item.get("detected_type") or "UNKNOWN").upper()
        confidence = float(new_payload.get("confidence") or item.get("confidence") or 0)
        self.db.update_pending(
            pending_id, payload=dict(new_payload), detected_type=detected,
            confidence=confidence,
            status="NEEDS_REVIEW" if detected == "UNKNOWN" else "PENDING_REVIEW",
        )
        if learn:
            source = ""
            with self.db.read() as con:
                row = con.execute(
                    """SELECT tm.raw_text FROM pending_items p JOIN telegram_messages tm
                       ON tm.chat_id=p.telegram_chat_id AND tm.message_id=p.telegram_message_id
                       WHERE p.pending_id=?""", (pending_id,),
                ).fetchone()
                source = row[0] if row else ""
            self.receipts.learn_from_correction(source_text=source, before=before, after=new_payload)
        return self.db.get_pending_item(pending_id) or {}


    async def analyze_pending_with_ai(self, pending_id: str) -> dict[str, Any]:
        """Run/re-run the image receipt pipeline for one pending item.

        This is intentionally callable from the GUI so an imported Telegram
        history item or a live item whose first network call failed can be
        analyzed later without re-sending the message.
        """
        item = self.db.get_pending_item(pending_id)
        if not item:
            raise KeyError(pending_id)
        if item.get("status") not in {"PENDING_REVIEW", "NEEDS_REVIEW"}:
            raise ValueError("این مورد دیگر در انتظار تأیید نیست.")
        evidence = dict(item.get('payload') or {})
        if evidence.get('receipt_image_deleted187'):
            raise FileNotFoundError('رسید تصویری حذف شده است؛ رسید جدید بارگذاری کنید یا متن را پردازش کنید.')
        atts = self.db.list_pending_attachments(pending_id)
        image = next((a for a in atts if str(a.get("mime_type") or "").lower().startswith("image/")), None)
        if evidence.get('receipt_image_path'):
            path = str(evidence['receipt_image_path'])
        elif not image:
            analysis = self.db.get_receipt_analysis(pending_id) or {}
            path = str(analysis.get("image_path") or "")
        else:
            path = str(image.get("local_path") or "")
        if not path:
            raise FileNotFoundError("برای این مورد تصویر آرشیوشده موجود نیست.")
        # Each receipt is analyzed from the text attached to its own Telegram
        # message only - no adjacent message's text is read or blended in.
        with self.db.read() as con:
            row = con.execute(
                'SELECT * FROM telegram_messages WHERE chat_id=? AND message_id=?',
                (int(item['telegram_chat_id']), int(item['telegram_message_id'])),
            ).fetchone()
        row = dict(row) if row else {}
        base_caption = str(evidence.get('receipt_caption') if 'receipt_caption' in evidence
                           else row.get('raw_text') or '').strip()
        message_date = str(row.get('message_date') or '')
        intel = await self.receipts.analyze_archived(
            pending_id=pending_id, caption=base_caption, image_path=path,
            message_date_shamsi=message_date,
        )
        payload = dict(intel.get("payload") or {})
        for key in ('receipt_image_path', 'receipt_image_deleted187', 'receipt_caption',
                    'source', 'copied_from_pending_id'):
            if key in evidence:
                payload[key] = evidence[key]
        detected = str(payload.get("detected_type") or "UNKNOWN").upper()
        status = "NEEDS_REVIEW" if intel.get("status") == "NEEDS_REVIEW" or detected == "UNKNOWN" else "PENDING_REVIEW"
        self.db.update_pending(
            pending_id, payload=payload, detected_type=detected,
            confidence=float(payload.get("confidence") or 0), status=status,
        )
        try:
            self.db.update_telegram_message(
                chat_id=int(item["telegram_chat_id"]), message_id=int(item["telegram_message_id"]), state=status
            )
        except Exception:
            pass
        return intel

    async def analyze_pending_text_only(self, pending_id: str, source_text: str) -> dict[str, Any]:
        """Reprocess user-reviewed text without reopening or resending the image."""
        item = self.db.get_pending_item(pending_id)
        if not item:
            raise KeyError(pending_id)
        if item.get('status') not in {'PENDING_REVIEW', 'NEEDS_REVIEW'}:
            raise ValueError('این مورد دیگر در انتظار تأیید نیست.')
        source_text = str(source_text or '').strip()
        if not source_text:
            raise ValueError('متن پیش‌نمایش خالی است.')
        if self.receipts.parser is not None:
            parsed = await self.receipts.parser.analyze(text=source_text, image_bytes=None, ocr_text=source_text)
        else:
            from local_fallback_parser import analyze_locally
            parsed = analyze_locally(source_text)
        payload = self.db.apply_learned_rules(source_text, dict(parsed or {}))
        evidence = item.get('payload') or {}
        for key in ('receipt_image_path', 'receipt_image_deleted187', 'receipt_caption',
                    'source', 'copied_from_pending_id'):
            if key in evidence:
                payload[key] = evidence[key]
        payload['construction_stage'] = normalize_construction_stage(payload.get('construction_stage'))
        payload['raw_visible_text'] = source_text
        payload['reprocess_mode'] = 'TEXT_ONLY'
        payload['reprocess_preview_text'] = source_text
        detected = str(payload.get('detected_type') or 'UNKNOWN').upper()
        status = 'NEEDS_REVIEW' if detected == 'UNKNOWN' else 'PENDING_REVIEW'
        self.db.update_pending(
            pending_id, payload=payload, detected_type=detected,
            confidence=float(payload.get('confidence') or 0), status=status,
        )
        try:
            self.db.update_telegram_message(
                chat_id=int(item['telegram_chat_id']),
                message_id=int(item['telegram_message_id']), state=status,
            )
        except Exception:
            pass
        return {'pending_id': pending_id, 'status': status, 'payload': payload}

    def approve(self, pending_id: str, *, actor_id: str = "GUI"):
        from transaction_lifecycle import TransactionLifecycle
        return TransactionLifecycle(self.db).run(pending_id,
            lambda: self._approve_without_lifecycle(pending_id, actor_id=actor_id))

    def _approve_without_lifecycle(self, pending_id: str, *, actor_id: str = "GUI"):
        item = self.db.get_pending_item(pending_id)
        if not item:
            raise KeyError(pending_id)
        if item.get('status') not in {'PENDING_REVIEW', 'NEEDS_REVIEW'}:
            raise ValueError('این مورد در انتظار تأیید نیست یا به سند دیگری پیوست شده است.')
        approval = self.workflow.approve_and_post(pending_id, actor_id=actor_id)
        posting = approval.posting
        # Attach the archived receipt to the most useful accounting entity.
        if posting.expense_id:
            self.db.relink_pending_attachments(pending_id, entity_type="EXPENSE", entity_id=posting.expense_id)
        elif posting.transaction_id:
            self.db.relink_pending_attachments(pending_id, entity_type="TRANSACTION", entity_id=posting.transaction_id)
        elif posting.cheque_id:
            self.db.relink_pending_attachments(pending_id, entity_type="CHEQUE", entity_id=posting.cheque_id)
        try:
            self.db.update_receipt_analysis_status(pending_id, "APPROVED")
        except Exception:
            pass
        self.db.enqueue_integration_event(
            "GUI_APPROVED", pending_id=pending_id,
            payload={"posting_type": posting.posting_type, "actor_id": actor_id},
        )
        return approval

    def link_existing(self, pending_id: str, *, entity_type: str, entity_id: str, actor_id: str = "GUI"):
        return self.db.link_pending_to_existing(
            pending_id=pending_id, entity_type=entity_type, entity_id=entity_id, source="GUI", actor_id=actor_id
        )


    def reject(self, pending_id: str, *, actor_id: str = "GUI"):
        from transaction_lifecycle import TransactionLifecycle
        TransactionLifecycle(self.db,actor_id=actor_id).reject(pending_id)
        result = self.db.get_pending_item(pending_id)
        return result

    def reopen(self, pending_id: str) -> None:
        item = self.db.get_pending_item(pending_id)
        if not item:
            raise KeyError(pending_id)
        if item.get("status") != "REJECTED":
            return
        from transaction_lifecycle import TransactionLifecycle
        lifecycle = TransactionLifecycle(self.db)
        if lifecycle.get(pending_id):
            lifecycle.restore(pending_id)
            return
        self.db.update_pending(pending_id, status="PENDING_REVIEW")
        self.db.update_telegram_message(
            chat_id=item["telegram_chat_id"], message_id=item["telegram_message_id"], state="PENDING_REVIEW"
        )
