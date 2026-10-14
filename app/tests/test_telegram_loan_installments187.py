"""A loan-installment receipt in the group becomes a «خروجی / اقساط» Data Entry record with its receipt, not an error."""
import asyncio
from types import SimpleNamespace

import telegram_loan_installments187 as li
from test_transaction_lifecycle_matrix import m, runtime, register  # noqa: F401

CAPTION = 'خروجی\nپرداخت قسط اول\nوام ۴۱۸۸'


def _loan(loan_id, name, principal, bank='بانک ملی', **extra):
    return dict(loan_id=loan_id, loan_name=name, principal_amount=principal, lender_name=bank, status='ACTIVE',
                description=f'اعتبار {name}', installment_count=12, paid_installments=0, **extra)


def _rows(amount=3_940_478, paid=0):
    return [dict(installment_number=1, amount=amount, paid_amount=paid, status='UPCOMING' if not paid else 'PARTIALLY_PAID'),
            dict(installment_number=2, amount=amount, paid_amount=0, status='UPCOMING')]


# ---- reading the caption --------------------------------------------------------------------------------------------

def test_the_instalment_a_caption_names():
    assert li.installment_number('پرداخت قسط اول وام') == 1
    assert li.installment_number('پرداخت قسط دوم') == 2
    assert li.installment_number('قسط ۳ وام ۴۱۸۸') == 3
    assert li.installment_number('قسط 12') == 12
    assert li.installment_number('واریز وام') is None


def test_the_loan_a_caption_points_at():
    loans = [_loan('LOAN-A', '4188', 41_885_972), _loan('LOAN-B', '6663', 66_635_054), _loan('LOAN-C', '3970', 39_707_149)]
    assert li.match_loan(CAPTION, loans)['loan_id'] == 'LOAN-A'
    assert li.match_loan('پرداخت قسط وام ۶۶۶۳', loans)['loan_id'] == 'LOAN-B'
    assert li.match_loan('قسط وام 3970', loans)['loan_id'] == 'LOAN-C'
    assert li.match_loan('قسط وام 6663', [dict(l, status='CANCELLED') for l in loans]) is None


def test_a_caption_that_names_no_loan_takes_the_only_active_loan_or_none():
    assert li.match_loan('قسط وام', [_loan('LOAN-A', '4188', 41_885_972)])['loan_id'] == 'LOAN-A'
    assert li.match_loan('قسط وام', [_loan('LOAN-A', '4188', 41_885_972), _loan('LOAN-B', '6663', 66_635_054)]) is None


def test_two_loans_of_one_bank_are_told_apart_by_their_number_not_the_bank():
    loans = [_loan('LOAN-A', '4188', 41_885_972), _loan('LOAN-B', '6663', 66_635_054)]
    assert li.match_loan('قسط وام بانک ملی', loans) is None
    assert li.match_loan('قسط وام بانک ملی 6663', loans)['loan_id'] == 'LOAN-B'


# ---- completing the payload -----------------------------------------------------------------------------------------

def test_a_receipt_without_an_amount_gets_the_amount_of_the_next_open_instalment():
    out = li.enrich({'amount': 0, 'notes': ''}, CAPTION, [_loan('LOAN-A', '4188', 41_885_972)], lambda _id: _rows())
    assert (out['v18_title'], out['v18_subtype'], out['detected_type']) == ('خروجی', 'اقساط', 'OUTFLOW')
    assert out['loan_id'] == 'LOAN-A' and out['installments_paid_now'] == 1
    assert out['amount'] == 3_940_478 and 'مبلغ از رسید خوانده نشد' in out['notes']
    assert out['source'] == li.SOURCE


def test_the_amount_read_from_the_receipt_is_kept():
    out = li.enrich({'amount': 3_900_000}, CAPTION, [_loan('LOAN-A', '4188', 41_885_972)], lambda _id: _rows())
    assert out['amount'] == 3_900_000 and 'مبلغ از رسید' not in out['notes']


def test_a_caption_naming_another_instalment_than_the_open_one_is_noted_not_obeyed():
    out = li.enrich({'amount': 0}, 'خروجی\nپرداخت قسط دوم\nوام ۴۱۸۸', [_loan('LOAN-A', '4188', 41_885_972)], lambda _id: _rows())
    assert 'قسط 2 آمده' in out['notes'] and 'قسط 1' in out['notes'] and out['installments_paid_now'] == 1


def test_a_loan_that_cannot_be_named_leaves_the_pick_to_the_person():
    out = li.enrich({'amount': 5}, 'قسط وام', [_loan('LOAN-A', '4188', 41_885_972), _loan('LOAN-B', '6663', 66_635_054)],
                    lambda _id: _rows())
    assert 'loan_id' not in out and out['amount'] == 5 and 'وام این پرداخت' in out['notes']


# ---- the payload is approvable --------------------------------------------------------------------------------------

def test_the_completed_payload_pays_the_instalment_when_the_record_is_approved(runtime):
    service = m.LoanService(runtime.db)
    loan = service.create_loan(lender_name='بانک ملی', principal_amount=41_885_972, net_received_amount=41_000_000,
                               received_date_shamsi='1405/05/28', total_interest=5_399_764, bank_fees=885_972,
                               installment_count=12, installment_amount=3_940_478, first_due_date_shamsi='1405/06/28')
    assert loan['loan_name'] == '4188'
    payload = li.enrich({'amount': 0, 'event_date_shamsi': '1405/07/14'}, CAPTION, service.list_loans(), service.list_installments)
    assert payload['loan_id'] == loan['loan_id'] and payload['amount'] == 3_940_478
    pid = register(runtime, payload)
    m.v18.submit_v18(pid, runtime.db.get_pending_item(pid)['payload'], runtime.rich)
    first = service.list_installments(loan['loan_id'])[0]
    assert first['paid_amount'] == 3_940_478 and first['status'] == 'PAID'


# ---- routing --------------------------------------------------------------------------------------------------------

class _Legacy:
    def __init__(self):
        self.calls = []
        self.LOANS = SimpleNamespace(list_loans=lambda: [_loan('LOAN-A', '4188', 41_885_972)], list_installments=lambda _id: _rows())

        async def regular(update, context):
            self.calls.append('regular')

        async def group(update, context):
            self.calls.append('original')

        async def review(message, context, pending_id, payload):
            self.calls.append('review')

        async def private():
            return 7

        async def send(bot, chat_id, text, **kwargs):
            self.calls.append(('sent', text, kwargs))

        self.apply_explicit_note_title = lambda payload, text: dict(payload)
        self.handle_group_message = group
        self._handle_regular_financial_message = regular
        self._send_private_review_if_enabled = review
        self._private_id = private
        self._safe_send = send
        self.fmt_money = lambda value: str(value)
        self._loan_message_kind = lambda text: 'INSTALLMENT' if 'قسط' in text and 'وام' in text else None


def _update(text):
    return SimpleNamespace(effective_message=SimpleNamespace(caption=text, text=None))


def test_an_instalment_message_goes_through_the_regular_pipeline_and_others_keep_their_way():
    legacy = _Legacy()
    li.install(legacy)
    asyncio.run(legacy.handle_group_message(_update(CAPTION), SimpleNamespace(bot=None)))
    asyncio.run(legacy.handle_group_message(_update('هزینه ساخت\nنقدی'), SimpleNamespace(bot=None)))
    assert legacy.calls == ['regular', 'original']


def test_the_title_hook_completes_only_instalment_payloads():
    legacy = _Legacy()
    li.install(legacy)
    out = legacy.apply_explicit_note_title({'amount': 0}, CAPTION)
    assert out['v18_subtype'] == 'اقساط' and out['loan_id'] == 'LOAN-A'
    other = legacy.apply_explicit_note_title({'amount': 7}, 'هزینه ساخت')
    assert other == {'amount': 7}


def test_an_instalment_record_gets_a_note_in_telegram_without_an_approve_button():
    legacy = _Legacy()
    li.install(legacy)
    payload = li.enrich({'amount': 0}, CAPTION, legacy.LOANS.list_loans(), legacy.LOANS.list_installments)
    asyncio.run(legacy._send_private_review_if_enabled(None, SimpleNamespace(bot=object()), 'PEN-1', payload))
    asyncio.run(legacy._send_private_review_if_enabled(None, SimpleNamespace(bot=object()), 'PEN-2', {'amount': 1}))
    sent = [call for call in legacy.calls if isinstance(call, tuple)]
    assert len(sent) == 1 and 'ثبت دیتا' in sent[0][1] and 'reply_markup' not in sent[0][2]
    assert legacy.calls.count('review') == 1  # the ordinary record keeps its review message


def test_a_loan_named_in_the_caption_wins_over_a_principal_that_starts_with_the_same_digits():
    loans = [_loan('LOAN-A', '4188', 41_885_972), _loan('LOAN-D', 'اعتبار ملی پیمان-2', 41_880_000)]
    assert li.match_loan(CAPTION, loans)['loan_id'] == 'LOAN-A'


def test_the_payload_names_its_loan_the_way_the_picker_does():
    loans = [_loan('LOAN-A', '4188', 41_885_972)]
    payload = li.enrich({'amount': 0}, CAPTION, loans, lambda _id: _rows())
    assert payload['loan_id'] == 'LOAN-A' and payload['selected_loan_name'] == '4188'
