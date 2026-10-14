from __future__ import annotations

from typing import Any


def _int(value: Any) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def normalize_financial_edit(old_payload: dict[str, Any], changes: dict[str, Any]) -> dict[str, Any]:
    """Apply user edit changes while preserving accounting intent.

    The key rule is that a fully-paid text expense behaves as one amount unless
    the user explicitly separates invoice/final/paid values. Therefore changing
    ``amount``/``final_amount`` on a PAID expense cascades to ``paid_amount``
    (and to the auto-derived invoice amount) unless those fields were explicitly
    supplied in the same edit.

    PARTIAL expenses deliberately do *not* auto-increase paid_amount.
    """
    old = dict(old_payload or {})
    explicit = {k for k, v in (changes or {}).items() if v is not None}
    new = dict(old)
    for key, value in (changes or {}).items():
        if value is not None:
            new[key] = value

    detected = str(new.get("detected_type") or old.get("detected_type") or "UNKNOWN").upper()
    if detected != "EXPENSE":
        return new

    old_amount = _int(old.get("amount"))
    old_final = _int(old.get("final_amount")) or old_amount
    old_invoice = _int(old.get("invoice_amount"))
    old_paid = _int(old.get("paid_amount"))
    old_state = str(old.get("payment_state") or "UNKNOWN").upper()

    amount = _int(new.get("amount"))
    final_amount = _int(new.get("final_amount"))

    # A simple text expense normally has one amount. If final_amount was
    # auto-derived from the old amount, changing only amount should change the
    # final amount too.
    if "amount" in explicit and "final_amount" not in explicit:
        if old_final in {0, old_amount}:
            final_amount = amount
            new["final_amount"] = final_amount

    if "final_amount" in explicit:
        final_amount = _int(new.get("final_amount"))
    elif final_amount <= 0:
        final_amount = amount
        if final_amount > 0:
            new["final_amount"] = final_amount

    # When invoice_amount was simply auto-filled from the same old amount,
    # keep it in lockstep unless the user explicitly edits it.
    if "invoice_amount" not in explicit and ("amount" in explicit or "final_amount" in explicit):
        if old_invoice in {0, old_amount, old_final}:
            new["invoice_amount"] = final_amount or amount

    state = str(new.get("payment_state") or old_state or "UNKNOWN").upper()

    # Explicit paid_amount always wins. Otherwise a PAID expense means the
    # full final amount has been paid. This prevents 100 -> 120 edits from
    # silently leaving a 100 payment behind.
    amount_changed = bool({"amount", "final_amount"} & explicit)
    state_changed = "payment_state" in explicit
    if "paid_amount" not in explicit:
        if state == "PAID" and (amount_changed or state_changed):
            new["paid_amount"] = final_amount or amount
        elif state == "UNPAID" and state_changed:
            new["paid_amount"] = 0
        elif state == "PAID" and old_state == "PAID" and old_paid in {0, old_amount, old_final} and amount_changed:
            new["paid_amount"] = final_amount or amount

    # If the user explicitly enters a paid amount smaller than final amount,
    # and did not explicitly insist on PAID, classify it as PARTIAL.
    if "paid_amount" in explicit and "payment_state" not in explicit:
        paid = _int(new.get("paid_amount"))
        if final_amount > 0:
            if paid <= 0:
                new["payment_state"] = "UNPAID"
            elif paid < final_amount:
                new["payment_state"] = "PARTIAL"
            else:
                new["payment_state"] = "PAID"

    return new
