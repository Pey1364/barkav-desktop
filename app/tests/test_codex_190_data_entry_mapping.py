from data_entry_mapping_187 import map_data_entry_values_187


def test_stage187_data_entry_maps_payload_fields_to_the_new_column_order():
    projected = map_data_entry_values_187(
        ('☐', 'date', 'type', 'description', 'amount', 'old-phase', 'old-sub', 'method', 'confidence', 'status'),
        {'payload': {
            'event_date_shamsi': '1405/06/01', 'v18_title': 'هزینه ساخت',
            'payer_name': 'پرداخت‌کننده', 'receiver_name': 'گیرنده',
            'construction_stage': 'اسکلت', 'subphase': 'بتن‌ریزی',
        }},
        fa=lambda value: value.translate(str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')),
        cell_text=lambda value: value,
    )

    assert projected == (
        '☐', '۱۴۰۵/۰۶/۰۱', 'هزینه ساخت', 'type', 'description', 'amount',
        'پرداخت‌کننده', 'گیرنده', 'اسکلت', 'بتن‌ریزی',
    )


def test_active_twelve_field_review_maps_without_shifting_or_losing_zero():
    values = ('☐ 1', '1405/06/11', 'هزینه ساخت', 'نقدی', 'خرید میلگرد', '0',
              'گیرنده', 'صاحب حساب', 'نقدی', '—', 'اسکلت', 'فونداسیون')
    row = {'payload': {'payer_name': 'تنخواه'}}
    result = map_data_entry_values_187(values, row, fa=lambda x: x, cell_text=lambda x: x)
    assert result == ('☐ 1', '1405/06/11', 'هزینه ساخت', 'نقدی', 'خرید میلگرد', '0',
                      'تنخواه', 'گیرنده', 'اسکلت', 'فونداسیون')
    assert map_data_entry_values_187(result, row, fa=lambda x: x, cell_text=lambda x: x,
                                     source_layout='current') == result


def test_active_review_uses_payload_aliases_without_swapping_parties():
    values = ('☐', 'old date', 'یادداشت', 'اطلاع‌رسانی', 'شرح', '0', 'old receiver',
              'owner', '—', '—', 'old phase', 'old subphase')
    row = {'payload': {'event_date_shamsi': '1405/07/01', 'v18_title': 'هزینه ساخت',
                      'payer_name': 'پرداخت‌کننده', 'receiver_name': 'گیرنده',
                      'main_phase': 'فاز اصلی', 'sub_phase': 'زیر فاز'}}
    result = map_data_entry_values_187(values, row, fa=lambda x: x, cell_text=lambda x: x)
    assert result[1:3] == ('1405/07/01', 'هزینه ساخت')
    assert result[6:] == ('پرداخت‌کننده', 'گیرنده', 'فاز اصلی', 'زیر فاز')
