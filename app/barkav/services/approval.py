from __future__ import annotations

from typing import Any

from finance_db import FinanceDB
from telegram_approval_workflow import TelegramStage5Workflow
from receipt_intelligence import ReceiptIntelligenceService


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

    def list_reviews(self, statuses=("PENDING_REVIEW","NEEDS_REVIEW","APPROVED","REJECTED","EDIT_PENDING"), limit:int=2000) -> list[dict[str,Any]]:
        return self.db.list_pending_reviews(statuses=tuple(statuses), limit=limit)

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
        atts = self.db.list_pending_attachments(pending_id)
        image = next((a for a in atts if str(a.get("mime_type") or "").lower().startswith("image/")), None)
        if not image:
            analysis = self.db.get_receipt_analysis(pending_id) or {}
            path = str(analysis.get("image_path") or "")
        else:
            path = str(image.get("local_path") or "")
        if not path:
            raise FileNotFoundError("برای این مورد تصویر آرشیوشده موجود نیست.")
        # Keep direct receipt text separate from adjacent Telegram context.
        # The AI may use one message on either side as corroborating evidence,
        # but that context must never be persisted as the Wizard purpose.
        bundle=self.evidence_bundle(pending_id,window=1)
        row=bundle.get('current') or {}
        base_caption=str(row.get('raw_text') or '').strip()
        nearby_lines=[]
        for m in bundle.get('nearby') or []:
            txt=str(m.get('raw_text') or '').strip()
            if txt:
                nearby_lines.append(f"[پیام مجاور {m.get('message_id')}] {txt}")
        context_text="\n".join(nearby_lines[:2])
        message_date=str(row.get('message_date') or '')
        intel = await self.receipts.analyze_archived(
            pending_id=pending_id, caption=base_caption, image_path=path,
            message_date_shamsi=message_date, context_text=context_text,
        )
        payload = dict(intel.get("payload") or {})
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

    def approve(self, pending_id: str, *, actor_id: str = "GUI"):
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
        result = self.workflow.reject(pending_id)
        try:
            self.db.update_receipt_analysis_status(pending_id, "REJECTED")
        except Exception:
            pass
        self.db.enqueue_integration_event("GUI_REJECTED", pending_id=pending_id, payload={"actor_id": actor_id})
        return result

    def reopen(self, pending_id: str) -> None:
        item = self.db.get_pending_item(pending_id)
        if not item:
            raise KeyError(pending_id)
        if item.get("status") != "REJECTED":
            return
        self.db.update_pending(pending_id, status="PENDING_REVIEW")
        self.db.update_telegram_message(
            chat_id=item["telegram_chat_id"], message_id=item["telegram_message_id"], state="PENDING_REVIEW"
        )
