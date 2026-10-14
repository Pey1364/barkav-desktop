"""Versioned 18.7 sales, contracts and claims workspace.

This module is deliberately a presentation layer over ``RevenueService``.  A
contract does not create cash; only the existing receipt workflow may do that.
Extended contract details are stored as JSON in the existing sales ``notes``
field, so this UI needs no database migration.
"""
from __future__ import annotations

import csv
import math
import json
from datetime import date, datetime
import os
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any

import jdatetime

from attachment_service import AttachmentService
from export_utils import choose_pdf_orientation, export_pdf, style_xlsx_workbook
from revenue_input import parse_money, parse_sale_form
from revenue_service import RevenueService, gregorian_to_shamsi, normalize_shamsi
from barkav_ui import BarkavWindow, art
from barkav_ui.table import apply_tree_rtl
from barkav_ui.row_overlay import CHECK_COLUMN
from barkav_ui.tabs import TabStrip
from barkav_ui.theme import font as kit_font
from barkav_ui.theme import metrics as kit_metrics, palette as kit_palette
from ui_stage18_3 import en, fa


CONTRACT_STEPS_187 = (
    '۱. بارگذاری قرارداد و مورد معامله', '۲. تاریخ‌ها', '۳. خریدار',
    '۴. مالی', '۵. شرایط پرداخت', '۶. امضاکنندگان', '۷. تأیید نهایی',
)
PAYMENT_LABELS_187 = ('پرداخت نقدی', 'قسط اول', 'قسط دوم', 'قسط سوم', 'قسط چهارم', 'قسط پنجم',
                      'قسط ششم', 'قسط هفتم', 'موعد تحویل', 'موعد سند')
INSTALLMENT_LABELS_187 = ('قسط اول', 'قسط دوم', 'قسط سوم', 'قسط چهارم', 'قسط پنجم',
                          'قسط ششم', 'قسط هفتم', 'قسط هشتم', 'قسط نهم', 'قسط دهم')


def _p(token: str) -> str:
    """One colour from the active palette.

    Sales used to carry its own private palette as literals in every method;
    routing them through here means a theme change reaches this screen too.
    """
    return kit_palette()[token]


def payment_labels_for_installments_187(installment_count: int) -> tuple[str, ...]:
    """Contract-wizard order: cash, chosen installments, delivery, then deed."""
    count = max(1, min(10, int(installment_count)))
    return ('پرداخت نقدی', *INSTALLMENT_LABELS_187[:count], 'موعد تحویل', 'موعد سند')

CONTRACT_TABLE_COLUMNS_187 = (
    ('row', 'ردیف', 80), ('floor', 'طبقه', 80), ('unit', 'شماره واحد', 90),
    ('date', 'تاریخ قرارداد', 110), ('buyer', 'خریدار', 150), ('kind', 'نوع فروش', 100),
    ('area', 'متراژ فروخته‌شده', 125), ('price', 'قیمت هر مترمربع (تومان)', 170),
    ('total', 'مبلغ قرارداد (تومان)', 150), ('delivery', 'تاریخ تحویل', 110),
    ('deed', 'تاریخ سند', 110), ('received', 'واریزی (تومان)', 140),
    ('remain', 'مانده (تومان)', 140), ('select', 'انتخاب', 75),
)
CONTRACT_NON_MONEY_COLUMNS_187 = ('date', 'buyer', 'kind')
EXPORT_PLACEHOLDER_187 = 'خروجی'
SALES_FINANCE_PENDING_SOURCE_187 = 'MANUAL_SALES_FINANCE'
SALES_FINANCE_PENDING_ACTIONS_187 = frozenset({'ADD', 'EDIT'})

PAYMENT_DETAIL_COLUMNS_187 = (
    ('row', 'ردیف', 70), ('stage', 'مرحله', 125), ('contract_date', 'تاریخ قرارداد', 110),
    ('contract_amount', 'مبلغ قرارداد (تومان)', 150), ('contract_due_date', 'تاریخ واریز طبق قرارداد', 150),
    ('received_date', 'تاریخ واریز', 110),
    ('received_amount', 'مبلغ واریز (تومان)', 150), ('late', 'دیرکرد (روز)', 100),
    ('balance', 'بدهکار/بستانکار (تومان)', 170), ('document', 'نمایش سند', 120),
)


def toman(value: Any) -> str:
    """Render monetary values with Persian digits and three-digit grouping."""
    return fa(f"{int(value or 0):,}")


def persian_digits_187(value: Any) -> str:
    """Display ASCII/Arabic-Indic digits as Persian without changing stored values."""
    return fa(en(value))


def formatted_amount_input_187(value: Any) -> str:
    """Format wizard money input with Persian digits and thousands separators."""
    raw = en(value).replace(',', '').replace('٬', '').strip()
    if not raw:
        return ''
    try:
        return fa(f'{int(raw):,}')
    except (TypeError, ValueError):
        return persian_digits_187(value)


def group_amount_while_typing_187(variable) -> None:
    """Keep an amount's thousands separated while it is being typed.

    Attached to the variable rather than the widget, so every entry box bound
    to that amount stays in step. The trace fires on its own write, so a guard
    stops it looping.
    """

    state = {'busy': False}

    def reformat(*_args):
        if state['busy']:
            return
        grouped = formatted_amount_input_187(variable.get())
        if grouped != variable.get():
            state['busy'] = True
            try:
                variable.set(grouped)
            finally:
                state['busy'] = False

    variable.trace_add('write', reformat)


def selectable_row_187(number: int, checked: bool = False) -> str:
    """A Persian row label with a visible, keyboard-independent check mark."""
    return f"{'☑' if checked else '☐'} {fa(number)}"


def selection_cell_187(checked: bool = False) -> str:
    """Render the independent selection column without polluting row numbers."""
    return '☑' if checked else '☐'


def visible_rows_payload_187(headers: list[str], rows: list[tuple[Any, ...]]) -> list[dict[str, str]]:
    """Return only the already-visible table data for safe, local export."""
    return [dict(zip(headers, (str(value) for value in row))) for row in rows]


def finance_export_rows_187(headers: list[str], rows: list[tuple[Any, ...]]) -> list[dict[str, str]]:
    """Export finance rows without UI checkbox glyphs in the row-number column."""
    payload = visible_rows_payload_187(headers, rows)
    for row in payload:
        if 'ردیف' in row:
            row['ردیف'] = row['ردیف'].replace('☐', '').replace('☑', '').strip()
        if 'انتخاب' in row:
            row['انتخاب'] = 'انتخاب شده' if '☑' in row['انتخاب'] else 'انتخاب نشده'
    return payload


def sales_finance_pending_payload_187(*, action: str, sale: dict[str, Any], installment: dict[str, Any] | None,
                                      receipt: dict[str, Any] | None) -> dict[str, Any]:
    """Build an approval-only sales receipt draft; it never posts cash by itself."""
    current_action = str(action or '').upper()
    if current_action not in {'ADD', 'EDIT', 'DELETE'}:
        raise ValueError('عملیات مالی فروش نامعتبر است.')
    installment = installment or {}
    receipt = receipt or {}
    amount = int(receipt.get('amount') or installment.get('amount') or 0)
    operation = {'ADD': 'ADD_REQUEST', 'DELETE': 'DELETE_REQUEST', 'EDIT': 'EDIT_REQUEST'}[current_action]
    description = {
        'ADD': 'درخواست افزودن ورودی فروش',
        'DELETE': 'درخواست حذف/اصلاح ردیف مالی',
        'EDIT': 'درخواست ویرایش تراکنش ثبت‌شده فروش',
    }[current_action]
    return {
        'detected_type': 'TRANSACTION',
        # These are the actual title/type fields consumed by the Data Entry wizard.
        'v18_title': 'ورودی', 'v18_subtype': 'فروش',
        'event_date_shamsi': receipt.get('received_date_shamsi') or gregorian_to_shamsi(date.today()),
        'amount': amount, 'payment_state': 'UNPAID',
        'sale_id': sale.get('sale_id') or '', 'buyer_name': sale.get('buyer_name') or '',
        'unit_number': sale.get('unit_number') or '', 'contract_number': sale.get('contract_number') or '',
        'installment_id': installment.get('installment_id') or '',
        'received_payment_id': receipt.get('received_payment_id') or '',
        'transaction_id': receipt.get('transaction_id') or '',
        'operation': operation, 'sales_pending_action': current_action,
        'description': description, 'source': SALES_FINANCE_PENDING_SOURCE_187,
    }


def sales_finance_pending_message_date_187(payload: dict[str, Any], now: datetime | None = None) -> str:
    """Return the Persian/Shamsi display date used by the sales Pending row."""
    raw = str((payload or {}).get('event_date_shamsi') or '').strip()
    if not raw:
        raw = gregorian_to_shamsi((now or datetime.now()).date())
    return persian_digits_187(raw.split()[0])


def is_temporary_sales_finance_pending_187(payload: dict[str, Any] | None) -> bool:
    """Only Add/Edit receipt drafts may be discarded before approval."""
    payload = payload or {}
    return (
        payload.get('source') == SALES_FINANCE_PENDING_SOURCE_187
        and str(payload.get('sales_pending_action') or '').upper() in SALES_FINANCE_PENDING_ACTIONS_187
    )


def payment_detail_export_payload_187(headers: list[str], rows: list[tuple[Any, ...]], installment_ids: list[str],
                                      documents_by_installment: dict[str, list[dict[str, Any]]], include_documents: bool) -> list[dict[str, str]]:
    """Keep documents opt-in and expose every receipt as its own preview row."""
    document_header = 'نمایش سند'
    if not include_documents:
        index = headers.index(document_header)
        headers = headers[:index] + headers[index + 1:]
        rows = [row[:index] + row[index + 1:] for row in rows]
        return visible_rows_payload_187(headers, rows)
    payload: list[dict[str, str]] = []
    for installment_id, row in zip(installment_ids, rows):
        payment = dict(zip(headers, (str(value) for value in row)))
        paths = []
        for document in documents_by_installment.get(str(installment_id), []):
            path = str(document.get('local_path') or document.get('attachment_id') or '').strip()
            if path and path not in paths:
                paths.append(path)
        # Each payment document must have a visible row.  Extra supporting
        # receipts intentionally leave amount/date blank to avoid duplicating
        # accounting figures in the exported contract table.
        stage_header = next((header for header in headers if header == 'مرحله' or 'مرحله پرداخت' in header), '')
        received_date_header = next((header for header in headers if header == 'تاریخ واریز'), '')
        received_amount_header = next((header for header in headers if 'مبلغ واریز' in header and 'کل مبلغ' not in header), '')
        for document_number, path in enumerate(paths or [''], 1):
            entry = dict(payment)
            if len(paths) > 1 and stage_header:
                entry[stage_header] = f"{entry.get(stage_header) or 'مرحله'} · فیش {persian_digits_187(document_number)}"
            if document_number > 1:
                if received_date_header:
                    entry[received_date_header] = '—'
                if received_amount_header:
                    entry[received_amount_header] = '—'
            entry[document_header] = path
            payload.append(entry)
    return payload

def export_document_paths_187(value: Any) -> list[str]:
    """Split local attachment paths from cells, lists, or row metadata."""
    if isinstance(value, dict):
        value = value.get('local_path') or value.get('path') or value.get('attachment_id') or ''
    if isinstance(value, (list, tuple, set)):
        paths: list[str] = []
        for item in value:
            for path in export_document_paths_187(item):
                if path not in paths:
                    paths.append(path)
        return paths
    return [item.strip() for item in str(value or '').replace('\r', '').split('\n') if item.strip()]


def export_payload_document_paths_187(payload: list[dict[str, Any]], document_header: str) -> list[str]:
    """Return every unique document referenced by visible export rows."""
    paths: list[str] = []
    for row in payload:
        for path in export_document_paths_187(row.get(document_header, '')):
            if path not in paths:
                paths.append(path)
    return paths


def export_project_name_187(specs) -> str:
    """Resolve the project label used by every saved export header."""
    for spec in specs or ():
        if isinstance(spec, (tuple, list)) and len(spec) >= 3:
            label, value = str(spec[1] or '').strip(), str(spec[2] or '').strip()
            if label in {'نام پروژه', 'پروژه'} and value:
                return value
            continue
        text = str(spec or '').strip()
        if 'نام پروژه' in text or text.startswith('پروژه'):
            value = text.split(':', 1)[-1].strip(' -—:')
            if value and value != text:
                return value
    return 'پروژه'


def export_output_title_187(window_title: str) -> str:
    """Use the same human-readable output title in preview and saved files."""
    cleaned = str(window_title or '').replace('پیش‌نمایش', '').replace('پیش نمایش', '').strip()
    return {
        'خروجی قرارداد': 'جزئیات قرارداد فروش',
        'خروجی جزئیات قرارداد': 'جزئیات قرارداد فروش',
        'اسناد واریزی': 'اسناد واریزی',
    }.get(cleaned, cleaned or 'خروجی')


def _export_logo_image_187(*, background: str, height: int):
    """Return the BARKAV mark flattened onto the export header background.

    The source PNG has a baked light plate. Keying and flattening it here keeps
    the Excel/PDF logo cell identical to the surrounding header.
    """
    try:
        from PIL import Image
        logo_path = getattr(art, 'LOGO', None)
        if not logo_path or not Path(logo_path).is_file():
            return None
        source = Image.open(logo_path).convert('RGB')
        bands = art._ink_bands(source)
        if len(bands) >= 3:
            keep_to = (bands[-2][1] + bands[-1][0]) // 2
            source = source.crop((0, 0, source.width, keep_to))
        keyed = art.key_white_backdrop(source, floor=art.CHECKERBOARD_FLOOR, gain=6.0)
        ink = art.tint(keyed, _p('on_accent'))
        ratio = int(height) / max(1, ink.height)
        ink = ink.resize((max(1, int(ink.width * ratio)), max(1, int(height))), Image.LANCZOS)
        return art._flatten(ink, background)
    except (OSError, ValueError, TypeError, AttributeError):
        return None

def export_header_label_187(value: Any) -> str:
    """Keep the contract date label free of the money-unit suffix."""
    text = str(value or '').strip()
    return 'تاریخ قرارداد' if text.startswith('تاریخ قرارداد') else text

def apply_export_workbook_header_187(sheet, *, headers, specs=(), output_title='خروجی', add_logo=True) -> None:
    """Add the three-section BARKAV header to an openpyxl export sheet.

    Excel sheets are RTL, therefore column A is the visual right section. The
    body still starts at row 4, so the new header cannot shift or overwrite any
    table fields.
    """
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    headers = [export_header_label_187(header) for header in (headers or ())]
    max_column = max(3, len(headers))
    center_column = max(2, (max_column + 1) // 2)
    left_column = max_column
    sheet.cell(1, 1).value = export_output_title_187(output_title)
    sheet.cell(1, center_column).value = 'شرکت مهندسی ساخت بارکاو'
    sheet.cell(2, center_column).value = f'پروژه {export_project_name_187(specs)}'
    sheet.cell(1, left_column).value = 'BARKAV'
    # Materialise the spacer row so append() starts the body at row 4.
    sheet.cell(3, 1).value = ''
    sheet.freeze_panes = 'A4'
    palette = kit_palette()
    thin = Side(style='thin', color=str(palette['border_subtle']).lstrip('#'))
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    fill = PatternFill(fill_type='solid', fgColor=str(palette['heading']).lstrip('#'))
    for row_index in (1, 2):
        for column_index in range(1, max_column + 1):
            cell = sheet.cell(row_index, column_index)
            cell.fill = fill
            cell.border = border
            cell.font = Font(name='Tahoma', size=11, bold=True, color='FFFFFF')
            cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    sheet.row_dimensions[1].height = 44
    sheet.row_dimensions[2].height = 30
    sheet.row_dimensions[3].height = 10
    if not add_logo:
        return
    try:
        from openpyxl.drawing.image import Image as ExcelImage
        logo_image = _export_logo_image_187(background=str(palette['heading']), height=38)
        if logo_image is not None:
            logo_buffer = __import__('io').BytesIO()
            logo_image.save(logo_buffer, format='PNG')
            logo_buffer.seek(0)
            image = ExcelImage(logo_buffer)
            image.anchor = f'{get_column_letter(left_column)}1'
            sheet.add_image(image)
    except (OSError, ImportError, ValueError, TypeError):
        # The text fallback in the left section remains visible when an Excel
        # installation cannot decode the optional PNG.
        pass

def wizard_export_payload_187(values: dict[str, Any], document_path: str = '') -> dict[str, str]:
    """Serialize the current wizard draft only; it does not save a contract or payment."""
    payload = {str(key): str(value or '') for key, value in values.items()}
    payload['contract_document_path'] = str(document_path or '')
    return payload


# چند تابع خروجی PDF این فایل همین دو رنگ را برای تیتر جدول و خط‌های
# داخلی به کار می‌برند - یک‌بار اینجا، نه literal پراکنده در هرکدام.
_PDF_TABLE_HEADER_BG = '#153B5B'
_PDF_TABLE_GRID_LINE = '#B8C2CC'


def export_contract_pdf_187(path: str | Path, headers: list[str], rows: list[Any], title: str,
                            *, orientation: str | None = None,
                            summary_lines: list[str] | None = None) -> Path:
    """Write Persian contract text with the project's embedded RTL PDF font."""
    from export_utils import export_pdf
    values = [[row.get(header, '') for header in headers] if isinstance(row, dict) else list(row) for row in rows]
    return export_pdf(
        path, [export_header_label_187(header) for header in headers], values,
        title=title, summary_lines=summary_lines, orientation=orientation,
    )


def export_receipts_pdf_187(path: str | Path, headers: list[str], rows: list[list[Any]], title: str,
                            summary_lines: list[str], document_paths: list[str], *, orientation: str | None = None,
                            contract_document_paths: list[str] | None = None,
                            documents_below_rows: bool = False,
                            report_audience: str = '', report_progress: float | None = None,
                            report_project_name: str = '', blank_missing: bool = False) -> Path:
    """Export the same grouped specifications, summary and receipt-in-cell table used by the preview."""
    from reportlab import platypus
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A3, A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from export_utils import _pdf_font, _rtl
    row_documents: list[list[str]] = []
    headers = list(headers)
    rows = [list(row) for row in rows]
    if documents_below_rows:
        document_index = next((index for index, value in enumerate(headers)
                               if value in {'نمایش سند', 'فیش واریزی', 'رسید', 'سند'}), None)
        if document_index is not None:
            for row in rows:
                cell_value = row[document_index] if document_index < len(row) else ''
                row_documents.append(export_document_paths_187(cell_value))
            headers = [value for index, value in enumerate(headers) if index != document_index]
            rows = [[value for index, value in enumerate(row) if index != document_index] for row in rows]
            document_paths = [path for group in row_documents for path in group]
    selected_orientation = orientation if orientation in {'افقی', 'عمودی'} else choose_pdf_orientation(headers, rows)
    font = _pdf_font(); path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    # Source tables store fields in logical order; a Persian PDF table must
    # display that order from right to left, with the receipt column on left.
    headers = list(reversed(headers))
    headers = [export_header_label_187(header) for header in headers]
    rows = [list(reversed(row)) for row in rows]
    document_headers = [header for header in headers if header in {'نمایش سند', 'فیش واریزی', 'رسید', 'سند'}]
    has_receipts = bool(document_paths) or any(any(export_document_paths_187(row[index]) for index, header in enumerate(headers) if header in document_headers) for row in rows)
    page_size = A3 if has_receipts else A4
    if selected_orientation == 'افقی':
        page_size = landscape(page_size)
    doc = platypus.SimpleDocTemplate(str(path), pagesize=page_size, rightMargin=18, leftMargin=18, topMargin=18, bottomMargin=18)
    compact_vertical = selected_orientation == 'عمودی'
    # Payment-table text must remain readable beside a compact receipt image.
    style = ParagraphStyle('receipt_rtl', fontName=font, fontSize=8 if compact_vertical else 9,
                           leading=10 if compact_vertical else 12, alignment=TA_RIGHT)
    table_header_style = ParagraphStyle(
        'receipt_table_header', parent=style, textColor=colors.white,
        fontSize=8 if compact_vertical else 9,
    )
    page_width = page_size[0] - doc.leftMargin - doc.rightMargin
    output_title = export_output_title_187(title)
    project_name = str(report_project_name or export_project_name_187(summary_lines))
    header_style = ParagraphStyle('receipt_header', parent=style, fontSize=11, leading=14, alignment=1, textColor=colors.white)
    try:
        logo_image = _export_logo_image_187(background=_PDF_TABLE_HEADER_BG, height=180)
        if logo_image is not None:
            logo_buffer = __import__('io').BytesIO()
            logo_image.save(logo_buffer, format='PNG')
            logo_buffer.seek(0)
            logo_cell = platypus.Image(logo_buffer, width=40 * mm, height=18 * mm, kind='proportional')
        else:
            logo_cell = platypus.Paragraph(_rtl('BARKAV'), header_style)
    except (OSError, ValueError, TypeError):
        logo_cell = platypus.Paragraph(_rtl('BARKAV'), header_style)
    title_cell = [platypus.Paragraph(_rtl(output_title), header_style)]
    if report_audience:
        audience_style = ParagraphStyle(
            'receipt_audience', parent=style, fontSize=10, leading=13,
            alignment=1, textColor=colors.white,
        )
        title_cell.extend([
            platypus.Spacer(1, 3),
            platypus.Paragraph(_rtl(f'جهت ارائه به: {report_audience}'), audience_style),
        ])
    export_header = platypus.Table([[
        logo_cell,
        [platypus.Paragraph(_rtl('شرکت مهندسی ساخت بارکاو'), header_style),
         platypus.Paragraph(_rtl(f'پروژه {project_name}'), header_style)],
        title_cell,
    ]], colWidths=[page_width / 3] * 3, rowHeights=[68 if report_audience else 58], hAlign='RIGHT')
    export_header.setStyle(platypus.TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(_PDF_TABLE_HEADER_BG)),
        ('BOX', (0, 0), (-1, -1), .8, colors.HexColor(_PDF_TABLE_GRID_LINE)),
        ('INNERGRID', (0, 0), (-1, -1), .6, colors.HexColor(_PDF_TABLE_GRID_LINE)),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6), ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story = [export_header, platypus.Spacer(1, 8)]
    grouped: dict[str, list[tuple[str, str]]] = {}
    plain_lines: list[str] = []
    for line in summary_lines:
        text = str(line)
        if report_project_name and text.startswith('پروژه:'):
            continue
        if ' — ' in text and ':' in text:
            group, remainder = text.split(' — ', 1)
            label, value = remainder.split(':', 1)
            grouped.setdefault(group.strip(), []).append((label.strip(), value.strip()))
        else:
            plain_lines.append(text)
    if plain_lines:
        summary_cells = [platypus.Paragraph(_rtl(line), style) for line in plain_lines]
        summary = platypus.Table([summary_cells], hAlign='RIGHT')
        summary.setStyle(platypus.TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#E8F0F7')),
            ('BOX', (0, 0), (-1, -1), .6, colors.HexColor(_PDF_TABLE_GRID_LINE)),
            ('INNERGRID', (0, 0), (-1, -1), .35, colors.HexColor(_PDF_TABLE_GRID_LINE)),
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ]))
        story.extend([summary, platypus.Spacer(1, 8)])
    # The export and its preview use the same RTL grid: ۱/۲, ۳/۴ and ۵/۶.
    # ReportLab's left physical cell is the second RTL box in each pair.
    spec_boxes = []
    paired_box_width = page_width / 2
    for group, entries in grouped.items():
        box_rows = [[platypus.Paragraph(_rtl(group), ParagraphStyle(
            f'box_title_{len(story)}', parent=style, fontSize=10, leading=13,
        ))]]
        # ReportLab's physical right column is the RTL label column.
        box_rows.extend([[platypus.Paragraph(_rtl(value), style), platypus.Paragraph(_rtl(label), style)]
                         for label, value in entries])
        box = platypus.Table(box_rows, colWidths=[paired_box_width / 2, paired_box_width / 2], hAlign='RIGHT')
        box.setStyle(platypus.TableStyle([
            ('SPAN', (0, 0), (-1, 0)), ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#DCE8F2')),
            ('BOX', (0, 0), (-1, -1), .8, colors.HexColor(_PDF_TABLE_GRID_LINE)),
            ('INNERGRID', (0, 1), (-1, -1), .35, colors.HexColor(_PDF_TABLE_GRID_LINE)),
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 7), ('RIGHTPADDING', (0, 0), (-1, -1), 7),
            ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        spec_boxes.append(box)
    if spec_boxes:
        pair_rows = []
        for index in range(0, len(spec_boxes), 2):
            right_box = spec_boxes[index]
            left_box = spec_boxes[index + 1] if index + 1 < len(spec_boxes) else ''
            pair_rows.append([left_box, right_box])
        pair_table = platypus.Table(pair_rows, colWidths=[paired_box_width, paired_box_width], hAlign='RIGHT')
        pair_table.setStyle(platypus.TableStyle([
            # Keep all contract sections inside one continuous frame: the outer
            # border and shared dividers belong to the paired grid, not a gap
            # between each nested section box.
            ('BOX', (0, 0), (-1, -1), .8, colors.HexColor('#496176')),
            ('INNERGRID', (0, 0), (-1, -1), .8, colors.HexColor('#496176')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))
        story.append(pair_table)
    document_width = 48 * mm if has_receipts else max(28 * mm, page_width / max(3, len(headers)))
    remaining_width = (page_width - document_width) / max(1, len(headers) - len(document_headers)) if compact_vertical else max(24 * mm, (page_width - document_width) / max(1, len(headers) - len(document_headers)))
    col_widths = [document_width if header in document_headers else remaining_width for header in headers]
    # Daily-report images use reduced A6 boxes; other receipt exports keep
    # their established compact size.
    receipt_width = (74 if documents_below_rows else 45) * mm if has_receipts else 0
    receipt_height = (105 if documents_below_rows else 64) * mm if has_receipts else 0

    def cell(header: str, value: Any):
        if header not in document_headers:
            missing = '' if blank_missing else '-'
            return platypus.Paragraph(_rtl(str(value if value not in (None, '') else missing)), style)
        paths = export_document_paths_187(value)
        documents = []
        for item in paths:
            candidate = Path(item)
            if candidate.exists() and candidate.suffix.lower() in {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}:
                try:
                    documents.append(platypus.Image(str(candidate), width=receipt_width, height=receipt_height, kind='proportional'))
                except (OSError, ValueError):
                    continue
        if documents:
            return documents
        if blank_missing and not paths:
            return platypus.Paragraph('', style)
        return platypus.Paragraph(_rtl('سند ثبت نشده است' if not paths else '\n'.join(Path(item).name for item in paths)), style)

    data = [[platypus.Paragraph(_rtl(header), table_header_style) for header in headers]]
    data.extend([[cell(header, value) for header, value in zip(headers, row)] for row in rows])
    # Keep the table itself on the right edge too.  Cell paragraphs already use
    # RTL/right alignment, but ReportLab otherwise places the whole table left.
    table = platypus.Table(data, colWidths=col_widths, repeatRows=1, splitByRow=1, hAlign='RIGHT')
    table.setStyle(platypus.TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), font), ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(_PDF_TABLE_HEADER_BG)),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white), ('GRID', (0, 0), (-1, -1), .4, colors.HexColor(_PDF_TABLE_GRID_LINE)),
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    if documents_below_rows and row_documents:
        header_table = platypus.Table(data[:1], colWidths=col_widths, repeatRows=1, hAlign='RIGHT')
        header_table.setStyle(platypus.TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), font), ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(_PDF_TABLE_HEADER_BG)),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white), ('GRID', (0, 0), (-1, -1), .4, colors.HexColor(_PDF_TABLE_GRID_LINE)),
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        story.append(header_table)
        for row_index, row_data in enumerate(data[1:]):
            row_table = platypus.Table([row_data], colWidths=col_widths, hAlign='RIGHT')
            row_table.setStyle(platypus.TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), font), ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), .4, colors.HexColor(_PDF_TABLE_GRID_LINE)),
                ('BACKGROUND', (0, 0), (-1, -1), colors.white if row_index % 2 == 0 else colors.HexColor('#F5F8FA')),
                ('ALIGN', (0, 0), (-1, -1), 'RIGHT'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            story.append(row_table)
            paths = row_documents[row_index] if row_index < len(row_documents) else []
            images = []
            image_width = min(74 * mm, page_width / max(1, min(4, len(paths))))
            image_height = image_width * 148 / 105
            for raw_path in paths[:4]:
                candidate = Path(raw_path)
                if candidate.exists() and candidate.suffix.lower() in {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}:
                    try:
                        images.append(platypus.Image(str(candidate), width=image_width, height=image_height, kind='proportional'))
                    except (OSError, ValueError):
                        continue
            if images:
                widths = [image_width] * len(images)
                image_row = platypus.Table([images], colWidths=widths, hAlign='RIGHT')
                image_row.setStyle(platypus.TableStyle([
                    ('BOX', (0, 0), (-1, -1), .5, colors.HexColor(_PDF_TABLE_GRID_LINE)),
                    ('INNERGRID', (0, 0), (-1, -1), .4, colors.HexColor('#B8C2CC')),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
                    ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                ]))
                story.append(platypus.Paragraph(_rtl('اسناد و تصاویر فعالیت'), style))
                story.append(image_row)
            elif paths:
                story.append(platypus.Paragraph(_rtl(' | '.join(Path(path).name for path in paths)), style))
    else:
        story.append(table)
    if report_progress is not None:
        overall = max(0.0, min(100.0, float(report_progress or 0)))

        class ProjectProgressBarFlowable(platypus.Flowable):
            """Compact report-width replica of the dashboard's filled progress bar."""
            def __init__(self, width, percent):
                super().__init__()
                self.width = width
                self.height = 24
                self.percent = percent

            def wrap(self, avail_width, avail_height):
                self.width = min(self.width, avail_width)
                return self.width, self.height

            def draw(self):
                canvas = self.canv
                radius = self.height / 2
                canvas.setFillColor(colors.HexColor('#496176'))
                canvas.setStrokeColor(colors.HexColor('#496176'))
                canvas.roundRect(0, 0, self.width, self.height, radius, fill=1, stroke=1)
                filled = self.width * self.percent / 100
                if filled > 0:
                    canvas.setFillColor(colors.HexColor('#2583D8'))
                    canvas.setStrokeColor(colors.HexColor('#2583D8'))
                    canvas.roundRect(0, 0, max(filled, self.height), self.height, radius, fill=1, stroke=0)
                label_style = ParagraphStyle(
                    'project_progress_label_187', parent=style, fontSize=8, leading=10,
                    alignment=1, textColor=colors.white,
                )
                label = platypus.Paragraph(
                    _rtl(f'پیشرفت کلی پروژه  {fa(f"{self.percent:.1f}")}٪'), label_style,
                )
                _label_width, label_height = label.wrap(max(1, self.width - 12), self.height)
                label.drawOn(canvas, 6, (self.height - label_height) / 2)

        story.extend([platypus.Spacer(1, 12), ProjectProgressBarFlowable(page_width, overall)])
    contract_images = [Path(str(item)) for item in (contract_document_paths or [])]
    if contract_images:
        story.extend([platypus.PageBreak(), platypus.Paragraph(_rtl('تصویر قرارداد'), ParagraphStyle(
            'contract_image_title', parent=style, fontSize=14, leading=18,
        ))])
        for candidate in contract_images:
            if not candidate.exists() or candidate.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}:
                story.append(platypus.Paragraph(_rtl(candidate.name), style)); continue
            try:
                story.extend([platypus.Spacer(1, 8), platypus.Image(str(candidate), width=105 * mm, height=148 * mm, kind='proportional')])
            except (OSError, ValueError):
                story.append(platypus.Paragraph(_rtl(candidate.name), style))
    doc.build(story); return path


def export_statement_finance_detail_pdf_187(
    path: str | Path, *, title: str, identity_lines: list[str],
    statement_headers: list[str], statement_rows: list[list[str]], statement_caption: str,
    payment_headers: list[str], payment_rows: list[list[str]], receipt_paths: list[str],
    orientation: str | None = None,
) -> Path:
    """صورت‌وضعیت/امور مالی's own دبل‌کلیک detail window: identity + summary
    lines, این صورت‌وضعیت's own ردیف‌ها (already formatted text, same as the
    on-screen table), and every واریز with its فیش نمایش‌داده at A6 - the
    same size export_receipts_pdf_187 already uses for a contract's own
    image, one receipt per واریز row instead of one shared table column.
    """

    from reportlab import platypus
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from export_utils import _pdf_font, _rtl

    font = _pdf_font()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    page_size = landscape(A4) if orientation == 'افقی' else A4
    doc = platypus.SimpleDocTemplate(str(path), pagesize=page_size, rightMargin=18, leftMargin=18,
                                     topMargin=18, bottomMargin=18)
    style = ParagraphStyle('detail_rtl', fontName=font, fontSize=9, leading=13, alignment=TA_RIGHT)
    title_style = ParagraphStyle('detail_title', parent=style, fontSize=15, leading=20)
    heading_style = ParagraphStyle('detail_heading', parent=style, fontSize=11, leading=15)
    story: list[Any] = [platypus.Paragraph(_rtl(title), title_style), platypus.Spacer(1, 6)]
    for line in identity_lines:
        story.append(platypus.Paragraph(_rtl(line), style))
    story.append(platypus.Spacer(1, 10))

    def table_style(header_rows: int = 1):
        return platypus.TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), font),
            ('BACKGROUND', (0, 0), (-1, header_rows - 1), colors.HexColor(_PDF_TABLE_HEADER_BG)),
            ('TEXTCOLOR', (0, 0), (-1, header_rows - 1), colors.white),
            ('GRID', (0, 0), (-1, -1), .4, colors.HexColor(_PDF_TABLE_GRID_LINE)),
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ])

    # ReportLab always lays a Table's column 0 out at the sheet's physical
    # left, whatever alignment the style or the table itself asks for - a
    # logical-order header list puts ردیف there instead of the right, unlike
    # the on-screen table. Reversed here, the same way export_receipts_pdf_187
    # and export_contract_pdf_187's own caller already reverse their tables.
    story.append(platypus.Paragraph(_rtl('ردیف‌های صورت‌وضعیت'), heading_style))
    reversed_statement_headers = list(reversed(statement_headers))
    statement_data = [[platypus.Paragraph(_rtl(h), style) for h in reversed_statement_headers]]
    statement_data.extend([[platypus.Paragraph(_rtl(str(v)), style) for v in reversed(row)]
                           for row in statement_rows] or [[platypus.Paragraph(_rtl('ردیفی ثبت نشده است'), style)]
                                                          + [''] * (len(statement_headers) - 1)])
    statement_table = platypus.Table(statement_data, repeatRows=1, hAlign='RIGHT')
    statement_table.setStyle(table_style())
    story.extend([statement_table, platypus.Paragraph(_rtl(statement_caption), style),
                 platypus.Spacer(1, 12)])

    story.append(platypus.Paragraph(_rtl('واریزی‌ها و فیش‌های آن'), heading_style))
    if not payment_rows:
        story.append(platypus.Paragraph(_rtl('واریزی‌ای ثبت نشده است'), style))
    reversed_payment_headers = list(reversed(payment_headers))
    for header, cells, receipt in zip(
        [reversed_payment_headers] * len(payment_rows), payment_rows, receipt_paths,
    ):
        row_table = platypus.Table(
            [[platypus.Paragraph(_rtl(h), style) for h in header]] +
            [[platypus.Paragraph(_rtl(str(v)), style) for v in reversed(cells)]],
            hAlign='RIGHT')
        row_table.setStyle(table_style())
        story.append(row_table)
        candidate = Path(str(receipt)) if receipt else None
        if candidate is not None and candidate.exists() and \
                candidate.suffix.lower() in {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}:
            try:
                story.append(platypus.Image(str(candidate), width=105 * mm, height=148 * mm,
                                            kind='proportional'))
            except (OSError, ValueError):
                story.append(platypus.Paragraph(_rtl('فیش قابل‌نمایش نیست'), style))
        else:
            story.append(platypus.Paragraph(_rtl('بدون فیش'), style))
        story.append(platypus.Spacer(1, 10))

    doc.build(story)
    return path


def export_archive_profile_pdf_187(
    path: str | Path, *, title: str, identity_lines: list[str], score_line: str,
    criteria_headers: list[str], criteria_rows: list[list[str]],
    history_headers: list[str], history_rows: list[list[str]],
) -> Path:
    """آرشیو's own دبل‌کلیک detail window: identity + امتیاز, معیارهای
    نظرسنجی (already split two columns wide - a row holds one معیار from
    each half, not one long list), and تاریخ‌های همکاری در طول پروژه. The
    survey table used to be missing from this export entirely - only the
    five summary columns (نام/دسته‌بندی/عنوان فعالیت/امتیاز/احتمال) went
    out, never the معیار-by-معیار detail behind that overall score.
    """

    from reportlab import platypus
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from export_utils import _pdf_font, _rtl

    font = _pdf_font()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = platypus.SimpleDocTemplate(str(path), pagesize=A4, rightMargin=18, leftMargin=18,
                                     topMargin=18, bottomMargin=18)
    style = ParagraphStyle('archive_rtl', fontName=font, fontSize=9, leading=13, alignment=TA_RIGHT)
    title_style = ParagraphStyle('archive_title', parent=style, fontSize=15, leading=20)
    heading_style = ParagraphStyle('archive_heading', parent=style, fontSize=11, leading=15)
    story: list[Any] = [platypus.Paragraph(_rtl(title), title_style), platypus.Spacer(1, 6)]
    for line in identity_lines:
        story.append(platypus.Paragraph(_rtl(line), style))
    story.extend([platypus.Paragraph(_rtl(score_line), heading_style), platypus.Spacer(1, 10)])

    def table_style(header_rows: int = 1):
        return platypus.TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), font),
            ('BACKGROUND', (0, 0), (-1, header_rows - 1), colors.HexColor(_PDF_TABLE_HEADER_BG)),
            ('TEXTCOLOR', (0, 0), (-1, header_rows - 1), colors.white),
            ('GRID', (0, 0), (-1, -1), .4, colors.HexColor(_PDF_TABLE_GRID_LINE)),
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ])

    # ReportLab always lays a Table's column 0 out at the sheet's physical
    # left regardless of alignment styling - reversed here the same way
    # export_statement_finance_detail_pdf_187 already reverses its own
    # tables, so معیار stays at the reader's right in each of the two
    # column-groups.
    story.append(platypus.Paragraph(_rtl('معیارهای نظرسنجی'), heading_style))
    reversed_criteria_headers = list(reversed(criteria_headers))
    criteria_data = [[platypus.Paragraph(_rtl(h), style) for h in reversed_criteria_headers]]
    criteria_data.extend([platypus.Paragraph(_rtl(str(v)), style) for v in reversed(row)]
                         for row in criteria_rows)
    if not criteria_rows:
        criteria_data.append([platypus.Paragraph(_rtl('معیاری برای این دسته‌بندی ثبت نشده است'), style)]
                             + [''] * (len(criteria_headers) - 1))
    criteria_table = platypus.Table(criteria_data, repeatRows=1, hAlign='RIGHT')
    criteria_table.setStyle(table_style())
    story.extend([criteria_table, platypus.Spacer(1, 12)])

    story.append(platypus.Paragraph(_rtl('تاریخ‌های همکاری در طول پروژه'), heading_style))
    if not history_rows:
        story.append(platypus.Paragraph(_rtl('تاریخ همکاری‌ای برای این ردیف ثبت نشده است'), style))
    else:
        reversed_history_headers = list(reversed(history_headers))
        history_data = [[platypus.Paragraph(_rtl(h), style) for h in reversed_history_headers]]
        history_data.extend([platypus.Paragraph(_rtl(str(v)), style) for v in reversed(row)]
                            for row in history_rows)
        history_table = platypus.Table(history_data, repeatRows=1, hAlign='RIGHT')
        history_table.setStyle(table_style())
        story.append(history_table)

    doc.build(story)
    return path




def contract_price_per_m2_187(row: dict[str, Any], meta: dict[str, Any]) -> str:
    area = en(str(meta.get('contract_area') or '')).replace(',', '').strip()
    try:
        numeric_area = float(area)
    except ValueError:
        numeric_area = 0
    return toman(int(row.get('contract_amount') or 0) / numeric_area) if numeric_area > 0 else '-'


def contract_table_values_187(number: int, row: dict[str, Any], meta: dict[str, Any], detail: Any) -> tuple[str, ...]:
    """Present a contract from the existing ledger; derived prices are never posted back."""
    return (
        selectable_row_187(number), persian_digits_187(row.get('floor') or '-'), persian_digits_187(row.get('unit_number') or '-'),
        persian_digits_187(row.get('contract_date_shamsi') or '-'), persian_digits_187(row.get('buyer_name') or '-'),
        str(meta.get('sale_kind') or '-'), persian_digits_187(meta.get('contract_area') or '-'),
        contract_price_per_m2_187(row, meta), toman(row.get('contract_amount')),
        persian_digits_187(meta.get('delivery_date') or '-'), persian_digits_187(meta.get('deed_date') or '-'),
        toman(detail.cash_received), toman(detail.receivable), selection_cell_187(),
    )


def filter_contract_rows_187(rows: list[dict[str, Any]], kind: str, value: str) -> list[dict[str, Any]]:
    """Two-stage contract filtering with a stable «همه» default."""
    if kind == 'همه' or value in ('', 'همه'):
        return rows
    key = {'نام خریدار': 'buyer_name', 'شماره واحد': 'unit_number', 'شماره قرارداد': 'contract_number'}.get(kind)
    return [row for row in rows if key and str(row.get(key) or '') == value]


def finance_sales_for_filter_187(
    rows: list[dict[str, Any]], kind: str, value: str, selected_sale_id: str = ''
) -> list[dict[str, Any]]:
    """Resolve the finance search without treating «همه» as an empty result.

    A specific second-combobox value selects one matching contract.  When the
    second combobox is «همه», an explicit contract selection is respected;
    otherwise every active contract is returned.
    """
    if kind != 'همه' and value not in ('', 'همه'):
        key = {
            'نام خریدار': 'buyer_name',
            'شماره واحد': 'unit_number',
            'شماره قرارداد': 'contract_number',
        }.get(kind)
        return [row for row in rows if key and str(row.get(key) or '') == value]
    if selected_sale_id:
        selected = [row for row in rows if str(row.get('sale_id') or '') == selected_sale_id]
        if selected:
            return selected
    return rows


def contract_note_187(values: dict[str, Any]) -> str:
    """Keep only non-ledger contract metadata in the pre-existing notes column."""
    return json.dumps({'contract_v': 1, **values}, ensure_ascii=False, sort_keys=True)


def payment_plan_187(values: dict[str, Any]) -> list[dict[str, Any]]:
    """Build the installment plan; never invent money or dates.

    The delivery/deed dates are copied to their payment rows when the user did
    not type another date.  Zero-amount stages are intentionally omitted.
    """
    count_text = en(str(values.get('payment_count') or '4'))
    try: count = max(1, min(10, int(count_text)))
    except ValueError: count = 4
    labels = payment_labels_for_installments_187(count)
    plan: list[dict[str, Any]] = []
    for index, label in enumerate(labels, 1):
        amount = parse_money(str(values.get(f'pay_{index}_amount') or ''))
        due = normalize_shamsi(str(values.get(f'pay_{index}_date') or ''))
        if index == count + 2 and not due:
            due = normalize_shamsi(str(values.get('delivery_date') or ''))
        if index == count + 3 and not due:
            due = normalize_shamsi(str(values.get('deed_date') or ''))
        if not amount:
            continue
        if not due:
            raise ValueError(f'تاریخ «{label}» را وارد کنید.')
        plan.append({'sequence_no': index, 'amount': amount, 'due_date_shamsi': due, 'description': label})
    if not plan:
        raise ValueError('حداقل یک مرحله پرداخت با مبلغ و تاریخ لازم است.')
    return plan


class ShamsiDatePicker187(BarkavWindow):
    """RTL Persian calendar picker used by contract and payment wizard dates."""
    MONTHS = ('', 'فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور', 'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند')
    DAYS = ('شنبه', 'یکشنبه', 'دوشنبه', 'سه‌شنبه', 'چهارشنبه', 'پنجشنبه', 'جمعه')

    def __init__(self, parent, variable, *, compact: bool = False):
        super().__init__(parent, 'انتخاب تاریخ شمسی', size_class='small', show_footer=False,
                         show_immediately=False)
        self.variable = variable
        today = jdatetime.date.today()
        raw = normalize_shamsi(variable.get())
        try: parsed = [int(part) for part in raw.split('/')]
        except (ValueError, AttributeError): parsed = []
        self.year, self.month = (parsed[0], parsed[1]) if len(parsed) == 3 else (today.year, today.month)
        width, height = (410, 370) if compact else (470, 430)
        self.geometry(f'{width}x{height}')
        self.minsize(width - 40, height - 40)
        self.transient(parent)
        self._build()
        # Build and size while withdrawn; caption/idle callbacks must never
        # expose the picker's provisional geometry at the edge of the screen.
        self._render()
        self._center_on_parent(width, height)
        self._take_focus()
        self.grab_set()

    @staticmethod
    def _month_days(year, month):
        if month <= 6: return 31
        if month <= 11: return 30
        return 30 if jdatetime.date(year, 1, 1).isleap() else 29

    def _build(self):
        self.configure(bg=_p('bg'))
        nav = tk.Frame(self.body, bg=_p('surface')); nav.pack(fill='x', padx=8, pady=8)
        self.year_var = tk.StringVar(); self.month_var = tk.StringVar()
        self.month_box = ttk.Combobox(nav, textvariable=self.month_var, values=self.MONTHS[1:], state='readonly', justify='right', width=12)
        self.month_box.pack(side='right', padx=3, pady=6); self.month_box.bind('<<ComboboxSelected>>', lambda _e: self._month_changed())
        years = tuple(persian_digits_187(year) for year in range(jdatetime.date.today().year - 30, jdatetime.date.today().year + 31))
        self.year_box = ttk.Combobox(nav, textvariable=self.year_var, values=years, state='readonly', justify='right', width=8)
        self.year_box.pack(side='right', padx=3, pady=6); self.year_box.bind('<<ComboboxSelected>>', lambda _e: self._year_changed())
        button_style = {
            'bg': _p('border'), 'fg': _p('on_accent'), 'activebackground': _p('blue_hover'),
            'activeforeground': _p('on_accent'), 'font': kit_font('body', bold=True),
            'relief': 'raised', 'bd': 1, 'width': 10, 'anchor': 'center',
            'padx': 6, 'pady': 4,
        }
        tk.Button(nav, text='ماه قبل', command=lambda: self._move(-1), **button_style).pack(side='left', padx=4, pady=6)
        tk.Button(nav, text='ماه بعد', command=lambda: self._move(1), **button_style).pack(side='left', padx=4, pady=6)
        self.grid_host = tk.Frame(self.body, bg=_p('bg')); self.grid_host.pack(fill='both', expand=True, padx=8, pady=(0, 8))
        for column in range(7): self.grid_host.grid_columnconfigure(column, weight=1)
        for row in range(7): self.grid_host.grid_rowconfigure(row, weight=1)

    def _sync_selectors(self):
        self.year_var.set(persian_digits_187(self.year)); self.month_var.set(self.MONTHS[self.month])

    def _year_changed(self):
        digits = en(self.year_var.get())
        try: self.year = int(digits)
        except ValueError: return
        self._render()

    def _month_changed(self):
        try: self.month = self.MONTHS.index(self.month_var.get())
        except ValueError: return
        self._render()

    def _move(self, delta):
        value = self.year * 12 + self.month - 1 + delta; self.year, zero = divmod(value, 12); self.month = zero + 1; self._render()

    def _render(self):
        self._render_pending_187 = False
        self._sync_selectors()
        for child in self.grid_host.winfo_children(): child.destroy()
        for index, label in enumerate(self.DAYS):
            tk.Label(self.grid_host, text=label, bg=_p('panel'), fg=_p('text_primary'), anchor='center').grid(row=0, column=6 - index, sticky='nsew', padx=1, pady=1)
        first = jdatetime.date(self.year, self.month, 1).togregorian(); first_index = (first.weekday() + 2) % 7
        for day in range(1, self._month_days(self.year, self.month) + 1):
            slot = first_index + day - 1; row, day_index = divmod(slot, 7)
            tk.Button(self.grid_host, text=persian_digits_187(day), command=lambda value=day: self._select(value),
                      bg=_p('panel'), fg=_p('text_primary'), activebackground=_p('blue'), activeforeground='white', relief='flat').grid(
                          row=row + 1, column=6 - day_index, sticky='nsew', padx=1, pady=1)

    def _select(self, day):
        self.variable.set(persian_digits_187(f'{self.year:04d}/{self.month:02d}/{day:02d}')); self.destroy()


class PaymentDocuments187(BarkavWindow):
    """Scrollable, grouped receipt-document viewer for selected finance rows."""
    def __init__(self, parent, *, db, base_dir, payments, contract_total=0):
        super().__init__(parent, 'اسناد واریزی', size_class='medium', show_footer=False)
        self.db, self.base_dir = db, Path(base_dir)
        self.payments = list(payments)
        self.contract_total = int(contract_total or 0)
        self.attachments = AttachmentService(db, self.base_dir)
        self.title('اسناد واریزی')

        self.geometry('980x650'); self.minsize(700, 440); self.resizable(True, True)
        self._build(); self._refresh()

    def _build(self):
        self.configure(bg=_p('bg'))
        top = tk.Frame(self.body, bg=_p('surface')); top.pack(fill='x', padx=8, pady=8)
        tk.Label(top, text='نمایش اسناد واریزی', bg=_p('surface'), fg=_p('text_primary'),
                 font=kit_font('title'), anchor='e').pack(side='right', padx=8, pady=6)
        self.stage_filter = tk.StringVar(value='همه موارد')
        self.filter_box = ttk.Combobox(top, textvariable=self.stage_filter, state='readonly', justify='right', width=24)
        self.filter_box.pack(side='right', padx=8, pady=5); self.filter_box.bind('<<ComboboxSelected>>', lambda _e: self._refresh())
        self.export_choice = tk.StringVar(value=EXPORT_PLACEHOLDER_187)
        self.export_box = ttk.Combobox(top, textvariable=self.export_choice,
                                       values=(EXPORT_PLACEHOLDER_187, 'PDF', 'Excel', 'پرینت'),
                                       state='readonly', justify='right', width=20)
        self.export_box.pack(side='left', padx=8, pady=5)
        self.export_box.bind('<<ComboboxSelected>>', self._export_selected)
        area = ttk.Frame(self.body); area.pack(fill='both', expand=True, padx=8, pady=(0, 8))
        self.tree = ttk.Treeview(area, columns=('stage', 'date', 'amount', 'document'), show='headings')
        for key, label, width in (('stage', 'مرحله پرداخت', 180), ('date', 'تاریخ واریز', 140), ('amount', 'مبلغ واریز (تومان)', 170), ('document', 'فیش واریزی', 420)):
            self.tree.heading(key, text=label, anchor='e'); self.tree.column(key, width=width, anchor='e', stretch=True)
        apply_tree_rtl(self.tree)
        scroll = ttk.Scrollbar(area, orient='vertical', command=self.tree.yview); xscroll = ttk.Scrollbar(area, orient='horizontal', command=self.tree.xview)
        self.tree.configure(yscrollcommand=scroll.set, xscrollcommand=xscroll.set)
        self._model_tree_scrollbars = (scroll, xscroll)
        self.cards_canvas = tk.Canvas(area, bg=_p('bg'), highlightthickness=0)
        self.cards_scroll = ttk.Scrollbar(area, orient='vertical', command=self.cards_canvas.yview)
        self.cards_host = tk.Frame(self.cards_canvas, bg=_p('bg'))
        self.cards_window = self.cards_canvas.create_window((0, 0), window=self.cards_host, anchor='nw')
        self.cards_host.bind('<Configure>', lambda _e: self.cards_canvas.configure(scrollregion=self.cards_canvas.bbox('all')))
        self.cards_canvas.bind('<Configure>', lambda event: self.cards_canvas.itemconfigure(self.cards_window, width=event.width))
        self.cards_canvas.configure(yscrollcommand=self.cards_scroll.set)
        self.cards_scroll.pack(side='right', fill='y'); self.cards_canvas.pack(side='left', fill='both', expand=True)
        self.tree.bind('<Double-1>', self._open_document)
        summary_bar = tk.Frame(self.body, bg=_p('surface')); summary_bar.pack(fill='x', padx=8, pady=(0, 8))
        self.summary_values = {}
        for key, label in (('contract', 'مبلغ کل قرارداد (تومان)'), ('paid', 'مبلغ واریزی (تومان)'), ('debt', 'مبلغ بدهکار/بستانکار (تومان)')):
            item = tk.Frame(summary_bar, bg=_p('surface')); item.pack(side='right', padx=12, pady=7)
            value = tk.StringVar(value='۰'); self.summary_values[key] = value
            tk.Label(item, textvariable=value, bg=_p('surface'), fg=_p('on_accent'), anchor='e', justify='right', width=16).pack(side='right')
            tk.Label(item, text=label, bg=_p('surface'), fg=_p('text_primary'), anchor='e', justify='right').pack(side='right', padx=(5, 0))

    def _rows_for_filter(self):
        selected = self.stage_filter.get()
        return [item for item in self.payments if selected == 'همه موارد' or item['stage'] == selected]

    def _refresh(self):
        stages = ['همه موارد'] + list(dict.fromkeys(item['stage'] for item in self.payments))
        self.filter_box.configure(values=stages)
        if self.stage_filter.get() not in stages: self.stage_filter.set('همه موارد')
        for iid in self.tree.get_children(): self.tree.delete(iid)
        for index, item in enumerate(self._rows_for_filter(), 1):
            parent = self.tree.insert('', 'end', values=(item['stage'], item['date'], toman(item['amount']), ''))
            documents = item.get('documents', [])
            for document in documents:
                self.tree.insert(parent, 'end', values=(f"↳ {item['stage']}", '', '', document.get('local_path') or document.get('attachment_id') or ''), iid=f'doc_{index}_{document.get("attachment_id", index)}')
            if not documents:
                self.tree.insert(parent, 'end', values=(f"↳ {item['stage']}", '', '', 'سند ثبت نشده است'))
            self.tree.item(parent, open=True)
        self._render_cards()

    def _render_cards(self):
        for child in self.cards_host.winfo_children():
            child.destroy()
        visible = self._rows_for_filter()
        paid_total = sum(int(item.get('amount') or 0) for item in visible)
        debt = max(0, self.contract_total - paid_total)
        self.summary_values['contract'].set(toman(self.contract_total))
        self.summary_values['paid'].set(toman(paid_total))
        self.summary_values['debt'].set(toman(debt))
        for index in range(0, len(visible), 2):
            row = tk.Frame(self.cards_host, bg=_p('bg')); row.pack(fill='x', pady=5)
            for item in visible[index:index + 2]:
                self._payment_card(row, item)

    def _payment_card(self, parent, item):
        card = tk.Frame(parent, bg=_p('surface'), highlightbackground=_p('border'), highlightthickness=1)
        card.pack(side='right', fill='both', expand=True, padx=5)
        tk.Label(card, text=str(item.get('stage') or 'مرحله پرداخت'), bg=_p('panel2'), fg=_p('text_primary'),
                 anchor='e', justify='right', padx=8, pady=5).pack(fill='x')
        meta = tk.Frame(card, bg=_p('surface')); meta.pack(fill='x', padx=8, pady=5)
        tk.Label(meta, text=f"مبلغ پرداختی (تومان): {toman(item.get('amount') or 0)}",
                 bg=_p('surface'), fg=_p('text_primary'), anchor='e').pack(fill='x')
        tk.Label(meta, text=f"تاریخ پرداختی: {persian_digits_187(item.get('date') or '-')}",
                 bg=_p('surface'), fg=_p('text_primary'), anchor='e').pack(fill='x')
        docs = list(item.get('documents') or [])
        if not docs:
            tk.Label(card, text='سند ثبت نشده است', bg=_p('surface'), fg=_p('danger'), anchor='e', padx=8).pack(fill='x', pady=8)
        for document in docs:
            self._document_card(card, document)

    def _document_card(self, parent, document):
        path = str(document.get('local_path') or '')
        if not path and document.get('attachment_id'):
            path = str((self.attachments.get(str(document['attachment_id'])) or {}).get('local_path') or '')
        label = Path(path).name if path else str(document.get('attachment_id') or 'سند')
        mime = str(document.get('mime_type') or '')
        if mime.startswith('image/') or Path(path).suffix.lower() in {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}:
            try:
                from PIL import Image, ImageTk
                image = Image.open(path).convert('RGB')
                image_host = tk.Frame(parent, bg=_p('surface')); image_host.pack(side='left', padx=8, pady=6)
                canvas = tk.Canvas(image_host, width=190, height=210, bg=_p('bg'), highlightthickness=1,
                                   highlightbackground=_p('border'))
                canvas.pack()
                zoom = tk.DoubleVar(value=1.0)
                def draw(_event=None):
                    width = max(1, canvas.winfo_width() - 8); height = max(1, canvas.winfo_height() - 8)
                    fit = min(width / max(1, image.width), height / max(1, image.height), 1.0)
                    scale = max(0.05, fit * zoom.get())
                    size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
                    photo = ImageTk.PhotoImage(image.resize(size)); canvas.delete('all')
                    canvas.create_image(width // 2, height // 2, image=photo, anchor='center'); canvas.image = photo
                    canvas.configure(scrollregion=canvas.bbox('all'))
                controls = tk.Frame(image_host, bg=_p('surface')); controls.pack(fill='x')
                tk.Button(controls, text='+', command=lambda: (zoom.set(min(4.0, zoom.get() + .2)), draw()),
                          bg=_p('blue'), fg='white', relief='flat', width=2).pack(side='left', padx=1)
                tk.Button(controls, text='−', command=lambda: (zoom.set(max(.2, zoom.get() - .2)), draw()),
                          bg=_p('blue'), fg='white', relief='flat', width=2).pack(side='left', padx=1)
                canvas.bind('<Configure>', draw, add='+')
                canvas.bind('<MouseWheel>', lambda event: (zoom.set(max(.2, min(4.0, zoom.get() + (.2 if event.delta > 0 else -.2)))), draw()), add='+')
                # Keep the receipt in this card: left-click and drag pans a zoomed image.
                canvas.bind('<ButtonPress-1>', lambda event: canvas.scan_mark(event.x, event.y), add='+')
                canvas.bind('<B1-Motion>', lambda event: canvas.scan_dragto(event.x, event.y, gain=1), add='+')
                draw()
                return
            except Exception:
                pass
        tk.Button(parent, text=f'نمایش سند: {label}', command=lambda d=document: self._open_document_data(d),
                  bg=_p('blue'), fg='white', relief='flat', anchor='e').pack(fill='x', padx=8, pady=6)

    def _export_selected(self, _event=None):
        export_format = {'Excel': 'xlsx', 'PDF': 'pdf', 'پرینت': 'print'}.get(self.export_choice.get())
        if export_format:
            self._export(export_format)

    def _open_image_zoom(self, document, initial_zoom=1.0):
        path = str(document.get('local_path') or '')
        if not path and document.get('attachment_id'):
            path = str((self.attachments.get(str(document['attachment_id'])) or {}).get('local_path') or '')
        try:
            from PIL import Image, ImageTk
            image = Image.open(path)
        except Exception as exc:
            return messagebox.showerror('فیش واریزی', str(exc), parent=self)
        viewer = tk.Toplevel(self); viewer.title('پیش‌نمایش فیش واریزی'); viewer.geometry('800x600'); viewer.minsize(480, 360); viewer.resizable(True, True)
        zoom = tk.DoubleVar(value=max(0.2, min(4.0, float(initial_zoom or 1.0))))
        canvas = tk.Canvas(viewer, bg=_p('input')); canvas.pack(fill='both', expand=True)
        def draw(_event=None):
            scale = max(0.2, min(4.0, zoom.get())); size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
            photo = ImageTk.PhotoImage(image.resize(size)); canvas.delete('all'); canvas.create_image(10, 10, image=photo, anchor='nw'); canvas.image = photo
            canvas.configure(scrollregion=canvas.bbox('all'))
        controls = tk.Frame(viewer, bg=_p('surface')); controls.pack(fill='x')
        tk.Button(controls, text='+', command=lambda: (zoom.set(zoom.get() + .2), draw()), bg=_p('blue'), fg='white').pack(side='left')
        tk.Button(controls, text='−', command=lambda: (zoom.set(zoom.get() - .2), draw()), bg=_p('blue'), fg='white').pack(side='left')
        canvas.bind('<MouseWheel>', lambda event: (zoom.set(max(0.2, min(4.0, zoom.get() + (0.2 if event.delta > 0 else -0.2)))), draw()))
        viewer.bind('<Configure>', draw); draw()

    def _open_document_data(self, document):
        local_path = Path(str(document.get('local_path') or ''))
        if str(document.get('mime_type') or '').startswith('text/') or local_path.suffix.lower() in {'.txt', '.csv', '.log'}:
            try:
                text = local_path.read_text(encoding='utf-8', errors='replace')
                viewer = tk.Toplevel(self); viewer.title('متن سند مالی'); viewer.geometry('760x520'); viewer.minsize(480, 320)
                box = tk.Text(viewer, wrap='word', padx=10, pady=10); scroll = ttk.Scrollbar(viewer, orient='vertical', command=box.yview)
                box.configure(yscrollcommand=scroll.set); scroll.pack(side='right', fill='y'); box.pack(side='left', fill='both', expand=True); box.insert('1.0', text); box.configure(state='disabled')
            except OSError as exc:
                messagebox.showerror('متن سند مالی', str(exc), parent=self)
        else:
            try: self.attachments.open(str(document.get('attachment_id')))
            except Exception as exc: messagebox.showerror('فیش واریزی', str(exc), parent=self)

    def _open_document(self, _event=None):
        selected = self.tree.selection()
        if not selected: return
        values = self.tree.item(selected[0], 'values')
        path = str(values[3] or '')
        if path == 'سند ثبت نشده است':
            return messagebox.showinfo('اسناد واریزی', 'سند ثبت نشده است.', parent=self)
        document = next((d for item in self.payments for d in item.get('documents', []) if str(d.get('local_path') or d.get('attachment_id') or '') == path), None)
        if document:
            local_path = Path(str(document.get('local_path') or ''))
            if str(document.get('mime_type') or '').startswith('text/') or local_path.suffix.lower() in {'.txt', '.csv', '.log'}:
                try:
                    text = local_path.read_text(encoding='utf-8', errors='replace')
                    viewer = tk.Toplevel(self); viewer.title('متن سند مالی'); viewer.geometry('760x520'); viewer.minsize(480, 320)
                    box = tk.Text(viewer, wrap='word', padx=10, pady=10); scroll = ttk.Scrollbar(viewer, orient='vertical', command=box.yview)
                    box.configure(yscrollcommand=scroll.set); scroll.pack(side='right', fill='y'); box.pack(side='left', fill='both', expand=True)
                    box.insert('1.0', text); box.configure(state='disabled')
                except OSError as exc:
                    messagebox.showerror('متن سند مالی', str(exc), parent=self)
            else:
                try: self.attachments.open(str(document.get('attachment_id')))
                except Exception as exc: messagebox.showerror('فیش واریزی', str(exc), parent=self)

    def _visible_rows(self):
        rows = []
        for parent in self.tree.get_children():
            rows.append(tuple(self.tree.item(parent, 'values')))
            rows.extend(tuple(self.tree.item(child, 'values')) for child in self.tree.get_children(parent))
        return rows

    def _export(self, fmt):
        headers = ('مرحله پرداخت', 'تاریخ واریز', 'مبلغ واریز (تومان)', 'فیش واریزی')
        visible = self._rows_for_filter()
        if not visible: return messagebox.showinfo('خروجی اسناد', 'سندی برای خروجی وجود ندارد.', parent=self)
        paid_total = sum(int(item.get('amount') or 0) for item in visible)
        debt = max(0, self.contract_total - paid_total)
        summary_lines = [
            f'مبلغ کل قرارداد (تومان): {toman(self.contract_total)}',
            f'مبلغ واریزی (تومان): {toman(paid_total)}',
            f'مبلغ بدهکار/بستانکار (تومان): {toman(debt)}',
        ]
        payload = []
        document_paths = []
        for item in visible:
            paths = []
            for document in item.get('documents', []):
                path = str(document.get('local_path') or '').strip()
                if not path and document.get('attachment_id'):
                    path = str((self.attachments.get(str(document['attachment_id'])) or {}).get('local_path') or '').strip()
                if path and path not in paths:
                    paths.append(path)
                if path and path not in document_paths:
                    document_paths.append(path)
            # One visible row per receipt makes every selected voucher visible
            # in the preview.  Only the first supporting document carries the
            # payment amount/date, so summary totals are never duplicated.
            document_rows = paths or ['']
            for document_number, path in enumerate(document_rows, 1):
                row_stage = str(item.get('stage') or 'مرحله پرداخت')
                if len(document_rows) > 1:
                    row_stage = f'{row_stage} · فیش {persian_digits_187(document_number)}'
                payload.append({
                    'مرحله پرداخت': row_stage,
                    'تاریخ واریز': persian_digits_187(item.get('date') or '-') if document_number == 1 else '—',
                    'مبلغ واریز (تومان)': toman(item.get('amount') or 0) if document_number == 1 else '—',
                    'فیش واریزی': path,
                })
        specs = [('خلاصه', line.split(':', 1)[0], line.split(':', 1)[1].strip()) for line in summary_lines]
        choices = {'xlsx': 'Excel', 'pdf': 'PDF', 'print': 'پرینت'}
        return ContractExportPreview187(
            self, export_format=choices.get(fmt, 'PDF'), headers=list(headers), payload=payload, specs=specs,
            window_title='پیش‌نمایش اسناد واریزی',
            include_addressee=True,
            on_confirm=lambda choice, orientation, addressee, include_documents:
                self._save_export(choice, list(headers), payload, specs, document_paths,
                                  orientation, addressee, include_documents),
        )

    def _save_export(self, choice, headers, payload, specs, document_paths,
                     orientation='افقی', addressee='سایر', include_documents=True):
        export_format = {'Excel': 'xlsx', 'PDF': 'pdf', 'پرینت': 'print'}.get(choice, 'pdf')
        actual_format = 'pdf' if export_format == 'print' else export_format
        export_specs = [*specs, ('خلاصه', 'جهت ارائه به', addressee)]
        export_payload = [dict(row) for row in payload]
        export_document_paths = list(document_paths or []) if include_documents else []
        if not include_documents:
            for row in export_payload:
                if 'فیش واریزی' in row:
                    row['فیش واریزی'] = '-'
        try:
            path = filedialog.asksaveasfilename(
                parent=self, title=f'خروجی {actual_format.upper()} اسناد واریزی',
                defaultextension=f'.{actual_format}',
                filetypes=[('Excel', '*.xlsx')] if actual_format == 'xlsx' else [('PDF', '*.pdf')],
            )
            if not path:
                return False
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            if actual_format == 'xlsx':
                from openpyxl import Workbook
                book = Workbook(); sheet = book.active
                apply_export_workbook_header_187(sheet, headers=headers, specs=export_specs, output_title='اسناد واریزی')
                sheet.append(headers)
                for row in export_payload:
                    sheet.append([row.get(header, '') for header in headers])
                    document_path = str(row.get('فیش واریزی') or '') if include_documents else ''
                    if document_path and Path(document_path).exists() and Path(document_path).suffix.lower() in {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}:
                        try:
                            from openpyxl.drawing.image import Image as ExcelImage
                            image = ExcelImage(document_path); image.width, image.height = 160, 110
                            image.anchor = f'{chr(65 + max(0, len(headers) - 1))}{sheet.max_row}'
                            sheet.add_image(image)
                        except (OSError, ImportError, ValueError):
                            pass
                sheet.append(())
                for group, label, value in export_specs: sheet.append((label, value))
                style_xlsx_workbook(book)
                apply_export_workbook_header_187(sheet, headers=headers, specs=export_specs, output_title='اسناد واریزی', add_logo=False)
                book.save(path)
            else:
                export_receipts_pdf_187(
                    path, headers, [[row.get(header, '') for header in headers] for row in export_payload],
                    'اسناد واریزی', [f'{label}: {value}' for _group, label, value in export_specs], export_document_paths,
                    orientation=orientation,
                )
                if export_format == 'print' and hasattr(os, 'startfile'):
                    os.startfile(path, 'print')
        except Exception as exc:
            messagebox.showerror('خروجی اسناد', str(exc), parent=self)
            return False
        messagebox.showinfo('خروجی اسناد', 'خروجی آماده شد.', parent=self)
        return True


class ContractWizard187(BarkavWindow):
    # Shell only: the step machinery below is deliberately left alone, since
    # rewriting a financial data-entry flow is not a styling change.
    size_class = 'medium'

    def __init__(self, parent, *, db, base_dir: Path, on_saved, record_opener=None, initial: dict[str, Any] | None = None, document_path: str = '', sale_id: str = ''):
        super().__init__(parent, 'ثبت قرارداد فروش', subtitle='BARKAV 18.7',
                         show_header=True, scrollable=True, show_footer=True)
        self.db, self.base_dir, self.on_saved, self.sale_id = db, Path(base_dir), on_saved, str(sale_id or '')
        self.record_opener = record_opener
        self.revenue = RevenueService(db)
        self.step, self.document_path = 0, str(document_path or '')
        self.values = {key: tk.StringVar() for key in (
            'project_name', 'block_name', 'deal_mode', 'sale_kind', 'unit_number', 'floor', 'map_area', 'contract_area',
            'contract_number', 'contract_date', 'delivery_date', 'deed_date', 'buyer_name', 'father_name',
            'national_id', 'buyer_phone', 'total_price', 'price_per_m2', 'broker_fee', 'payment_count',
            'notary_name', 'witness_1', 'witness_2', 'buyer_representative', 'seller_representative',
        )}
        for number in range(1, 14):
            self.values[f'pay_{number}_amount'] = tk.StringVar()
            self.values[f'pay_{number}_date'] = tk.StringVar()
        self.values['sale_kind'].set('پیش‌فروش')
        self.values['deal_mode'].set('واحد کامل')
        self.values['payment_count'].set('۴')
        self._payment_visible_installments = 4
        self._unit_combo = None
        self._unit_records: dict[str, dict[str, Any]] = {}
        for key, value in (initial or {}).items():
            if key in self.values and value not in (None, ''):
                self.values[key].set(str(value))
        self._digit_normalizing = False
        for key, variable in self.values.items():
            variable.trace_add('write', lambda *_args, current=variable, field=key: self._format_wizard_variable(field, current))
            self._persianize_variable(variable)
        self.values['project_name'].trace_add('write', lambda *_: self._refresh_unit_choices())
        self.values['block_name'].trace_add('write', lambda *_: self._refresh_unit_choices())
        self.protocol('WM_DELETE_WINDOW', self._close_to_record)
        self._build_shell()
        self._show_step()

    def _persianize_variable(self, variable):
        if self._digit_normalizing:
            return
        value = variable.get(); display = persian_digits_187(value)
        if value != display:
            self._digit_normalizing = True
            try: variable.set(display)
            finally: self._digit_normalizing = False

    def _format_wizard_variable(self, key, variable):
        self._persianize_variable(variable)
        if key not in {'total_price', 'broker_fee', 'price_per_m2'} and not key.startswith('pay_'):
            return
        value = formatted_amount_input_187(variable.get())
        if value != variable.get() and not self._digit_normalizing:
            self._digit_normalizing = True
            try: variable.set(value)
            finally: self._digit_normalizing = False

    def _build_shell(self):
        """Fill the shell's header and footer; body and scrolling are inherited."""
        p = kit_palette()
        m = kit_metrics()
        header = self.header
        header.grid_columnconfigure(1, weight=1)
        self.title_var = tk.StringVar()
        tk.Label(header, text='ثبت مرحله‌ای قرارداد', bg=p['surface'], fg=p['text_primary'],
                 anchor='e', justify='right', font=kit_font('title')).grid(
                     row=0, column=2, sticky='e', padx=m['outer_pad'], pady=m['gap'])
        self.progress_status = tk.Label(
            header, text='هر مرحله فقط اطلاعات مرتبط با قرارداد را نشان می‌دهد.',
            bg=p['surface'], fg=p['text_secondary'], anchor='e', justify='right',
            font=kit_font('small'))
        self.progress_status.grid(row=0, column=1, sticky='ew', padx=m['outer_pad'])
        progress = tk.Frame(header, bg=p['surface'])
        progress.grid(row=0, column=0, sticky='w', padx=m['outer_pad'])
        self.step_label = tk.Label(progress, text='', bg=p['surface'], fg=p['text_secondary'],
                                   anchor='e', font=kit_font('small'))
        self.step_label.pack(side='right', padx=(0, 8))
        self.progress_canvas = tk.Canvas(progress, width=128, height=16,
                                         bg=p['surface'], highlightthickness=0)
        self.progress_canvas.pack(side='left')
        self.progress_canvas.bind('<Configure>', lambda _event: self._render_progress(), add='+')
        # Section 10: primary action leftmost, back stays visible but disabled.
        self.next = self.add_action('بعدی ←', self._next, style='Primary.TButton')
        self.back = self.add_action('→ قبلی', self._back)
        self.add_action('پنجره رکورد فروش', self._close_to_record)

    def _render_progress(self):
        """Draw the same compact stage-progress treatment used by the data wizard."""
        canvas = getattr(self, 'progress_canvas', None)
        if canvas is None:
            return
        canvas.delete('all')
        width, height = max(int(canvas.winfo_width()), 128), max(int(canvas.winfo_height()), 16)
        canvas.create_rectangle(0, 0, width - 1, height - 1, fill=_p('input'), outline=_p('border'))
        filled = max(2, int((width - 4) * (self.step + 1) / len(CONTRACT_STEPS_187)))
        canvas.create_rectangle(2, 2, 2 + filled, height - 3, fill=_p('accent'), outline='')
        self.step_label.configure(text=f"مرحله {fa(self.step + 1)} از {fa(len(CONTRACT_STEPS_187))}")

    def _export_wizard(self, export_format: str):
        payload = wizard_export_payload_187({key: value.get().strip() for key, value in self.values.items()}, self.document_path)
        extension = f'.{export_format}'
        path = filedialog.asksaveasfilename(parent=self, title=f'خروجی {export_format.upper()} ویزارد قرارداد', defaultextension=extension, filetypes=[(export_format.upper(), f'*{extension}')])
        if not path:
            return
        try:
            destination = Path(path)
            if export_format == 'csv':
                with destination.open('w', encoding='utf-8-sig', newline='') as handle:
                    writer = csv.DictWriter(handle, fieldnames=list(payload)); writer.writeheader(); writer.writerow(payload)
            elif export_format == 'txt':
                destination.write_text('\n'.join(f'{key}: {value}' for key, value in payload.items()), encoding='utf-8')
            else:
                destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        except OSError as exc:
            return messagebox.showerror('خروجی ویزارد', str(exc), parent=self)
        messagebox.showinfo('خروجی ویزارد', 'پیش‌نویس فعلی ویزارد صادر شد.', parent=self)

    def _field(self, parent, key, label, row, column=0, *, readonly=False, values=None):
        box = tk.Frame(parent, bg=_p('surface'))
        box.grid(row=row, column=column, sticky='ew', padx=6, pady=5)
        tk.Label(box, text=label, bg=_p('surface'), fg=_p('text_primary'), anchor='e').pack(fill='x', padx=6, pady=(5, 1))
        # An empty project-unit list must still render as a dropdown; the
        # choices are populated as soon as project/block is selected.
        if values is not None:
            widget = ttk.Combobox(box, textvariable=self.values[key], values=values, state='readonly', justify='right')
            widget.pack(fill='x', padx=6, pady=(0, 6))
        else:
            date_field = key in {'contract_date', 'delivery_date', 'deed_date'} or (key.startswith('pay_') and key.endswith('_date')) or key.endswith('_date')
            if date_field:
                line = tk.Frame(box, bg=_p('surface')); line.pack(fill='x', padx=6, pady=(0, 6))
                widget = ttk.Entry(line, textvariable=self.values[key], justify='right')
                widget.pack(side='right', fill='x', expand=True)
                tk.Button(line, text='تقویم', command=lambda current=self.values[key]: ShamsiDatePicker187(self, current),
                          bg=_p('border'), fg=_p('text_primary'), relief='flat', padx=7).pack(side='left', padx=(5, 0))
            else:
                widget = ttk.Entry(box, textvariable=self.values[key], justify='right')
            if readonly:
                widget.configure(state='readonly')
                widget.pack(fill='x', padx=6, pady=(0, 6))
            elif not (values is None and (key in {'contract_date', 'delivery_date', 'deed_date'} or key.endswith('_date'))):
                widget.pack(fill='x', padx=6, pady=(0, 6))
        return widget

    def _available_units(self) -> dict[str, dict[str, Any]]:
        """Read project units for selection; never creates or mutates units."""
        project = self.values['project_name'].get().strip()
        block = self.values['block_name'].get().strip()
        try:
            with self.db.read() as con:
                rows = con.execute(
                    """SELECT unit_number, floor, area FROM units
                       WHERE status!='CANCELLED'
                         AND (?='' OR COALESCE(project_name,'')=?)
                         AND (?='' OR COALESCE(block_name,'')=?)
                       ORDER BY unit_number""",
                    (project, project, block, block),
                ).fetchall()
        except Exception:
            rows = []
        return {str(row['unit_number']): {'floor': row['floor'], 'area': row['area']} for row in rows if row['unit_number'] not in (None, '')}

    def _refresh_unit_choices(self):
        combo = getattr(self, '_unit_combo', None)
        if combo is None:
            return
        self._unit_records = self._available_units()
        current = self.values['unit_number'].get().strip()
        choices = list(self._unit_records)
        if current and current not in choices:
            choices.insert(0, current)
        combo.configure(values=tuple(persian_digits_187(value) for value in choices))

    def _unit_selected(self, _event=None):
        selected = self.values['unit_number'].get().strip()
        key = en(selected)
        record = self._unit_records.get(selected) or self._unit_records.get(key)
        if not record:
            return
        self.values['floor'].set(persian_digits_187(record.get('floor') or ''))
        self.values['map_area'].set(persian_digits_187(record.get('area') or ''))

    def _show_step(self):
        for child in self.body.winfo_children():
            child.destroy()
        self.title_var.set(CONTRACT_STEPS_187[self.step])
        self._render_progress()
        self.back.configure(state='normal' if self.step else 'disabled')
        self.next.configure(text='ثبت قرارداد' if self.step == len(CONTRACT_STEPS_187) - 1 else 'بعدی ←')
        page = tk.LabelFrame(self.body, text=CONTRACT_STEPS_187[self.step], labelanchor='ne', bg=_p('bg'), fg=_p('text_primary'),
                             font=kit_font('body', bold=True), padx=8, pady=8)
        page.pack(fill='both', expand=True)
        page.grid_columnconfigure((0, 1), weight=1)
        if self.step == 0:
            ttk.Button(page, text='بارگذاری قرارداد', command=self._load_document).grid(row=0, column=1, sticky='e', padx=8)
            self.document_label = tk.Label(page, text=self.document_path or 'فایلی انتخاب نشده است', bg=_p('bg'), fg=_p('text_secondary'), anchor='e', justify='right')
            self.document_label.grid(row=1, column=0, columnspan=2, sticky='ew', padx=8, pady=10)
            self.deal_mode_combo = self._field(page, 'deal_mode', 'روش معامله', 2, 1, values=('واحد کامل', 'فروش متری'))
            self.sale_kind_combo = self._field(page, 'sale_kind', 'نوع فروش', 2, 0, values=('پیش‌فروش', 'آماده'))
            # Keep both step-one selectors explicit/read-only so the dropdown
            # affordance remains available with every active ttk theme.
            self.deal_mode_combo.configure(values=('واحد کامل', 'فروش متری'), state='readonly')
            self.sale_kind_combo.configure(values=('پیش‌فروش', 'آماده'), state='readonly')
            self._field(page, 'project_name', 'نام پروژه', 3, 1)
            self._field(page, 'block_name', 'بلوک', 3, 0)
            self._unit_records = self._available_units()
            self._deal_widgets = [
                self._field(page, 'unit_number', 'شماره واحد', 4, 1, values=tuple(persian_digits_187(value) for value in self._unit_records)),
                self._field(page, 'floor', 'طبقه', 4, 0),
                self._field(page, 'map_area', 'متراژ طبق نقشه', 5, 1),
            ]
            self._unit_combo = self._deal_widgets[0]
            self._unit_combo.bind('<<ComboboxSelected>>', self._unit_selected)
            self._field(page, 'contract_area', 'متراژ قرارداد', 5, 0)
            self.values['deal_mode'].trace_add('write', lambda *_: self._toggle_deal_mode())
            self._toggle_deal_mode()
        elif self.step == 1:
            self._field(page, 'contract_number', 'شماره قرارداد', 0, 1)
            self._field(page, 'contract_date', 'تاریخ قرارداد', 1, 1)
            self._field(page, 'delivery_date', 'تاریخ تحویل', 2, 1)
            self._field(page, 'deed_date', 'تاریخ سند', 3, 1)
        elif self.step == 2:
            self._field(page, 'buyer_name', 'نام و نام خانوادگی', 0, 1)
            self._field(page, 'father_name', 'نام پدر', 1, 1)
            self._field(page, 'national_id', 'شماره ملی', 2, 1)
            self._field(page, 'buyer_phone', 'شماره تماس', 3, 1)
        elif self.step == 3:
            self._field(page, 'total_price', 'قیمت کل (تومان)', 0, 1)
            price = self._field(page, 'price_per_m2', 'قیمت هر متر مربع (تومان)', 1, 1, readonly=True)
            self._field(page, 'broker_fee', 'کمیسیون بنگاه (تومان)', 2, 1)
            self.values['total_price'].trace_add('write', lambda *_: self._price_per_m2())
            self.values['contract_area'].trace_add('write', lambda *_: self._price_per_m2())
            self._price_per_m2()
        elif self.step == 4:
            count_box = self._field(page, 'payment_count', 'تعداد اقساط', 0, 1)
            count_box.bind('<FocusOut>', self._payment_count_changed)
            count_box.bind('<Return>', self._payment_count_changed)
            count = self._payment_installment_count()
            self._payment_visible_installments = count
            labels = payment_labels_for_installments_187(count)
            self._payment_widgets = []
            for index, label in enumerate(labels, 1):
                amount = self._field(page, f'pay_{index}_amount', f'{label} (تومان)', index, 1)
                due = self._field(page, f'pay_{index}_date', f'تاریخ {label}', index, 0)
                self._payment_widgets.append((self._payment_widget_container(amount), self._payment_widget_container(due)))
            self._toggle_payment_rows()
        elif self.step == 5:
            self._field(page, 'notary_name', 'نام دفترخانه', 0, 1)
            self._field(page, 'witness_1', 'شاهد ۱', 1, 1)
            self._field(page, 'witness_2', 'شاهد ۲', 2, 1)
            self._field(page, 'buyer_representative', 'نماینده خریدار', 3, 1)
            self._field(page, 'seller_representative', 'نماینده فروشنده', 4, 1)
        else:
            summary = self._summary_text()
            label = tk.Label(page, text=summary, bg=_p('surface'), fg=_p('text_primary'), justify='right', anchor='ne',
                             font=kit_font('body'), padx=16, pady=16)
            label.pack(fill='both', expand=True)

    def _load_document(self):
        path = filedialog.askopenfilename(parent=self, title='قرارداد', filetypes=[('Documents', '*.pdf *.jpg *.jpeg *.png *.doc *.docx *.txt'), ('All files', '*.*')])
        if not path:
            return
        self.document_path = path
        text = ''
        if Path(path).suffix.lower() == '.txt':
            try: text = Path(path).read_text(encoding='utf-8')
            except UnicodeDecodeError: text = Path(path).read_text(encoding='utf-8-sig')
        else:
            try:
                from receipt_intelligence import LocalOCREngine
                text = LocalOCREngine().extract(Path(path)).text
            except Exception:
                text = ''
        parsed = parse_sale_form(text)
        mapping = {'project_name': 'project_name', 'block_name': 'block_name', 'unit_number': 'unit_number',
                   'floor': 'floor', 'contract_area': 'area', 'buyer_name': 'buyer_name', 'buyer_phone': 'buyer_phone',
                   'contract_number': 'contract_number', 'contract_date': 'contract_date_shamsi', 'total_price': 'contract_amount'}
        for target, source in mapping.items():
            if parsed.get(source) not in (None, '', 0): self.values[target].set(str(parsed[source]))
        for row in parsed.get('installments') or []:
            number = min(13, int(row.get('sequence_no') or 1))
            self.values[f'pay_{number}_amount'].set(str(row.get('amount') or ''))
            self.values[f'pay_{number}_date'].set(str(row.get('due_date_shamsi') or ''))
        self._show_step()

    def _price_per_m2(self):
        area = float(en(str(self.values['contract_area'].get() or '0')).replace(',', '') or 0)
        price = parse_money(self.values['total_price'].get())
        self.values['price_per_m2'].set(toman(price / area) if area > 0 else '')

    def _toggle_deal_mode(self):
        """In a meter-sale only contract area remains editable, as specified."""
        meter_sale = self.values['deal_mode'].get() == 'فروش متری'
        for widget in getattr(self, '_deal_widgets', []):
            widget.configure(state='disabled' if meter_sale else 'normal')

    @staticmethod
    def _payment_widget_container(widget):
        """Return the outer grid-managed field frame, not a packed date line."""
        current = widget
        while current.winfo_manager() == 'pack':
            current = current.master
        return current

    def _payment_installment_count(self) -> int:
        try:
            # The entered stage count includes cash, delivery and deed.  Only
            # the remaining stages are dynamic installment rows.
            return max(1, min(10, int(en(self.values['payment_count'].get())) - 3))
        except ValueError:
            return 1

    def _payment_count_changed(self, _event=None):
        """Keep cash and the two fixed final stages intact when count changes."""
        old_count = getattr(self, '_payment_visible_installments', self._payment_installment_count())
        new_count = self._payment_installment_count()
        if old_count != new_count:
            old_delivery, old_deed = old_count + 2, old_count + 3
            new_delivery, new_deed = new_count + 2, new_count + 3
            for suffix in ('amount', 'date'):
                delivery_value = self.values[f'pay_{old_delivery}_{suffix}'].get()
                deed_value = self.values[f'pay_{old_deed}_{suffix}'].get()
                if old_delivery != new_delivery:
                    self.values[f'pay_{old_delivery}_{suffix}'].set('')
                    self.values[f'pay_{new_delivery}_{suffix}'].set(delivery_value)
                if old_deed != new_deed:
                    self.values[f'pay_{old_deed}_{suffix}'].set('')
                    self.values[f'pay_{new_deed}_{suffix}'].set(deed_value)
        self._payment_visible_installments = new_count
        self._show_step()

    def _toggle_payment_rows(self):
        count = self._payment_installment_count() + 3
        for index, widgets in enumerate(getattr(self, '_payment_widgets', []), 1):
            for widget in widgets:
                if index <= count:
                    widget.grid()
                else:
                    widget.grid_remove()

    def _summary_text(self):
        labels = {
            'project_name': 'نام پروژه', 'block_name': 'بلوک', 'deal_mode': 'روش معامله', 'sale_kind': 'نوع فروش',
            'unit_number': 'شماره واحد', 'floor': 'طبقه', 'map_area': 'متراژ طبق نقشه', 'contract_area': 'متراژ قرارداد',
            'contract_number': 'شماره قرارداد', 'contract_date': 'تاریخ قرارداد', 'delivery_date': 'تاریخ تحویل',
            'deed_date': 'تاریخ سند', 'buyer_name': 'نام و نام خانوادگی', 'father_name': 'نام پدر',
            'national_id': 'شماره ملی', 'buyer_phone': 'شماره تماس', 'total_price': 'قیمت کل (تومان)',
            'price_per_m2': 'قیمت هر مترمربع (تومان)', 'broker_fee': 'کمیسیون بنگاه (تومان)',
            'payment_count': 'تعداد مراحل پرداخت', 'notary_name': 'نام دفترخانه', 'witness_1': 'شاهد ۱',
            'witness_2': 'شاهد ۲', 'buyer_representative': 'نماینده خریدار', 'seller_representative': 'نماینده فروشنده',
        }
        lines = [f"{labels.get(key, 'اطلاعات')}: {persian_digits_187(value.get() or '-')}"
                 for key, value in self.values.items() if not key.startswith('pay_')]
        for index, title in enumerate(payment_labels_for_installments_187(self._payment_installment_count()), 1):
            amount = self.values[f'pay_{index}_amount'].get() or '-'; due = self.values[f'pay_{index}_date'].get() or '-'
            lines.append(f'{title}: مبلغ {persian_digits_187(amount)} تومان | تاریخ {persian_digits_187(due)}')
        return '\n'.join(lines)

    def _back(self):
        self.step = max(0, self.step - 1); self._show_step()

    def _next(self):
        if self.step < len(CONTRACT_STEPS_187) - 1:
            self.step += 1; self._show_step(); return
        self._save()

    def _save(self):
        raw = {key: value.get().strip() for key, value in self.values.items()}
        try:
            raw['payment_count'] = str(self._payment_installment_count())
            plan = payment_plan_187(raw)
            total = parse_money(raw['total_price'])
            if total <= 0 or total != sum(int(row['amount']) for row in plan):
                raise ValueError('جمع مراحل پرداخت باید دقیقاً با قیمت کل قرارداد برابر باشد.')
            contract_date = normalize_shamsi(raw['contract_date'])
            unit_number = raw['unit_number']
            if raw['deal_mode'] == 'فروش متری':
                unit_number = f"متری-{raw['contract_number'] or raw['buyer_name']}"
            if not contract_date or not raw['buyer_name'] or not unit_number:
                raise ValueError('شماره واحد، نام خریدار و تاریخ قرارداد الزامی است.')
            result = self.revenue.create_sale_bundle(
                project_name=raw['project_name'] or 'پروژه', block_name=raw['block_name'], unit_number=unit_number,
                floor=raw['floor'], area=float(en(raw['contract_area']).replace(',', '') or 0) or None,
                buyer_name=raw['buyer_name'], buyer_phone=raw['buyer_phone'], contract_number=raw['contract_number'],
                contract_date_shamsi=contract_date, contract_amount=total, installments=plan,
                notes=contract_note_187(raw), source='GUI_187_CONTRACT', actor_id='GUI_187',
            )
            if self.document_path:
                AttachmentService(self.db, self.base_dir).add_local(entity_type='SALE', entity_id=result['sale_id'], source_path=self.document_path, document_type='CONTRACT')
        except Exception as exc:
            messagebox.showerror('ثبت قرارداد', str(exc), parent=self); return
        self.on_saved(); self.destroy()

    def _close_to_record(self):
        draft = {key: value.get().strip() for key, value in self.values.items()}
        if self.record_opener:
            self.record_opener(sale_id=self.sale_id, draft=draft, document_path=self.document_path)
        else:
            try: self.master.open_selected_record_187(sale_id=self.sale_id, draft=draft, document_path=self.document_path)
            except Exception: pass
        self.destroy()


class SalesRecord187(BarkavWindow):
    """Dedicated sales record: one editable view, separate from data-entry records."""
    _FIELDS = (
        ('project_name', 'نام پروژه'), ('block_name', 'بلوک'), ('deal_mode', 'روش معامله'),
        ('sale_kind', 'نوع فروش'), ('unit_number', 'شماره واحد'), ('floor', 'طبقه'),
        ('map_area', 'متراژ طبق نقشه'), ('contract_area', 'متراژ قرارداد'),
        ('contract_number', 'شماره قرارداد'), ('contract_date', 'تاریخ قرارداد'),
        ('delivery_date', 'تاریخ تحویل'), ('deed_date', 'تاریخ سند'),
        ('buyer_name', 'نام و نام خانوادگی'), ('father_name', 'نام پدر'),
        ('national_id', 'شماره ملی'), ('buyer_phone', 'شماره تماس'),
        ('total_price', 'قیمت کل (تومان)'), ('price_per_m2', 'قیمت هر مترمربع (تومان)'),
        ('broker_fee', 'کمیسیون بنگاه (تومان)'), ('payment_count', 'تعداد مراحل پرداخت'),
        ('notary_name', 'نام دفترخانه'), ('witness_1', 'شاهد ۱'),
        ('witness_2', 'شاهد ۲'), ('buyer_representative', 'نماینده خریدار'), ('seller_representative', 'نماینده فروشنده'),
    )
    _WIZARD_GROUPS = (
        ('۱. مورد معامله', ('project_name', 'block_name', 'deal_mode', 'sale_kind', 'unit_number', 'floor', 'map_area', 'contract_area')),
        ('۲. تاریخ‌ها', ('contract_number', 'contract_date', 'delivery_date', 'deed_date')),
        ('۳. خریدار', ('buyer_name', 'father_name', 'national_id', 'buyer_phone')),
        ('۴. مالی', ('total_price', 'price_per_m2', 'broker_fee')),
        ('۶. امضاکنندگان', ('notary_name', 'witness_1', 'witness_2', 'buyer_representative', 'seller_representative')),
    )
    _FIELD_LABELS = dict(_FIELDS)

    def __init__(self, parent, *, db, base_dir: Path, sale_id: str = '', draft: dict[str, Any] | None = None,
                 document_path: str = '', on_saved=None):
        super().__init__(parent, 'پنجره رکورد فروش', size_class='large', show_footer=False)
        self.db, self.base_dir, self.sale_id, self.on_saved = db, Path(base_dir), str(sale_id or ''), on_saved
        self.revenue = RevenueService(db)
        self.document_path = document_path
        initial = self._initial_values(draft or {})
        self.values = {key: tk.StringVar(value=str(initial.get(key) or '')) for key, _label in self._FIELDS}
        if not self.values['payment_count'].get().strip():
            self.values['payment_count'].set('۴')
        for index in range(1, 14):
            self.values[f'pay_{index}_amount'] = tk.StringVar(value=str(initial.get(f'pay_{index}_amount') or ''))
            self.values[f'pay_{index}_date'] = tk.StringVar(value=str(initial.get(f'pay_{index}_date') or ''))
        self._payment_visible_installments = self._payment_installment_count()
        self._unit_records: dict[str, dict[str, Any]] = {}
        self._unit_combo = None
        self._digit_normalizing = False
        for key, variable in self.values.items():
            variable.trace_add('write', lambda *_args, current=variable, field=key: self._format_record_variable(field, current))
            self._persianize_variable(variable)
        self.values['project_name'].trace_add('write', lambda *_: self._refresh_unit_choices())
        self.values['block_name'].trace_add('write', lambda *_: self._refresh_unit_choices())
        self.values['total_price'].trace_add('write', lambda *_: self._record_price_per_m2())
        self.values['contract_area'].trace_add('write', lambda *_: self._record_price_per_m2())
        self._record_price_per_m2()
        self.title('پنجره رکورد فروش')
        # Keep the normal Windows title bar so native minimize/maximize/close
        # controls remain available in the white title area.
        self.geometry('1120x720'); self.minsize(860, 560); self.resizable(True, True)
        self._preview_image = None
        self._preview_pil_image = None
        self._build()

    def _initial_values(self, draft: dict[str, Any]) -> dict[str, Any]:
        values = dict(draft)
        if not self.sale_id:
            return values
        row = self.revenue.get_sale(self.sale_id) or {}
        try: metadata = json.loads(str(row.get('notes') or '{}'))
        except (ValueError, TypeError, json.JSONDecodeError): metadata = {}
        values = {**metadata, **values}
        values.update({
            'project_name': values.get('project_name') or row.get('project_name'),
            'block_name': values.get('block_name') or row.get('block_name'),
            'unit_number': values.get('unit_number') or row.get('unit_number'),
            'floor': values.get('floor') or row.get('floor'),
            'map_area': values.get('map_area') or row.get('area'),
            'contract_area': values.get('contract_area') or row.get('area'),
            'contract_number': values.get('contract_number') or row.get('contract_number'),
            'contract_date': values.get('contract_date') or row.get('contract_date_shamsi'),
            'buyer_name': values.get('buyer_name') or row.get('buyer_name'),
            'buyer_phone': values.get('buyer_phone') or row.get('buyer_phone'),
            'total_price': values.get('total_price') or row.get('contract_amount'),
        })
        return values

    def _persianize_variable(self, variable):
        if self._digit_normalizing:
            return
        value = variable.get(); display = persian_digits_187(value)
        if value != display:
            self._digit_normalizing = True
            try: variable.set(display)
            finally: self._digit_normalizing = False

    def _format_record_variable(self, key, variable):
        self._persianize_variable(variable)
        if key not in {'total_price', 'broker_fee', 'price_per_m2'} and not key.startswith('pay_'):
            return
        value = formatted_amount_input_187(variable.get())
        if value != variable.get() and not self._digit_normalizing:
            self._digit_normalizing = True
            try: variable.set(value)
            finally: self._digit_normalizing = False

    def _build(self):
        bg, surface, panel, line, text = _p('bg'), _p('surface'), _p('panel'), _p('border'), _p('text_primary')
        self.configure(bg=bg)
        header = tk.Frame(self.body, bg=surface, highlightbackground=line, highlightthickness=1)
        header.pack(fill='x', padx=10, pady=8)
        tk.Label(header, text='پنجره رکورد فروش', bg=surface, fg=text,
                 font=kit_font('title'), anchor='e').pack(side='right', padx=14, pady=9)
        tk.Label(header, text='اطلاعات اختصاصی قرارداد و فروش', bg=surface, fg=_p('text_secondary'),
                 anchor='w').pack(side='left', padx=14, pady=9)
        body = tk.PanedWindow(self.body, orient='horizontal', bg=line, sashwidth=6, relief='flat', bd=0)
        body.pack(fill='both', expand=True, padx=10, pady=(0, 8))
        preview = tk.Frame(body, bg=panel, highlightbackground=line, highlightthickness=1)
        form_area = tk.Frame(body, bg=panel, highlightbackground=line, highlightthickness=1)
        body.add(preview, minsize=260, stretch='always'); body.add(form_area, minsize=500, stretch='always')
        tk.Label(preview, text='پیش‌نمایش قرارداد', bg=panel, fg=text,
                 font=kit_font('body', bold=True), anchor='e').pack(fill='x', padx=10, pady=8)
        preview_tools = tk.Frame(preview, bg=panel); preview_tools.pack(fill='x', padx=8)
        tk.Button(preview_tools, text='+', command=lambda: self._zoom_preview(1), bg=surface, fg=text, relief='flat', width=3).pack(side='left', padx=2)
        tk.Button(preview_tools, text='−', command=lambda: self._zoom_preview(-1), bg=surface, fg=text, relief='flat', width=3).pack(side='left', padx=2)
        self.preview_zoom = 1
        preview_area = tk.Frame(preview, bg=_p('input')); preview_area.pack(fill='both', expand=True, padx=8, pady=8)
        self.preview_canvas = tk.Canvas(preview_area, bg=_p('input'), highlightthickness=0)
        preview_xscroll = ttk.Scrollbar(preview_area, orient='horizontal', command=self.preview_canvas.xview)
        preview_yscroll = ttk.Scrollbar(preview_area, orient='vertical', command=self.preview_canvas.yview)
        self.preview_canvas.configure(xscrollcommand=preview_xscroll.set, yscrollcommand=preview_yscroll.set)
        preview_yscroll.pack(side='right', fill='y'); preview_xscroll.pack(side='bottom', fill='x'); self.preview_canvas.pack(side='left', fill='both', expand=True)
        self.preview_canvas.bind('<Configure>', lambda _event: self._render_preview_image(), add='+')
        self.preview_canvas.bind('<MouseWheel>', self._preview_mouse_zoom, add='+')
        self._preview_source_image = None
        tk.Button(preview, text='نمایش فایل قرارداد', command=self._open_document, bg=_p('blue'), fg='white',
                  relief='flat', padx=8, pady=7).pack(fill='x', padx=8, pady=(0, 8))
        self._show_preview()
        tk.Label(form_area, text='مشخصات فروش', bg=panel, fg=text,
                 font=kit_font('body', bold=True), anchor='e').pack(fill='x', padx=10, pady=8)
        canvas = tk.Canvas(form_area, highlightthickness=0)
        scroll = ttk.Scrollbar(form_area, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y'); canvas.pack(side='left', fill='both', expand=True)
        form = ttk.Frame(canvas); window = canvas.create_window((0, 0), window=form, anchor='nw')
        form.bind('<Configure>', lambda _e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(window, width=event.width))
        form.grid_columnconfigure(0, weight=1)
        self._record_form = form
        upload = ttk.LabelFrame(form, text='۰. بارگذاری قرارداد', labelanchor='ne', padding=8)
        upload.grid(row=0, column=0, sticky='ew', padx=4, pady=4)
        ttk.Label(upload, text=self.document_path or 'فایلی انتخاب نشده است', anchor='e').pack(fill='x')
        tk.Button(upload, text='بارگذاری و تحلیل قرارداد', command=self._load_document, bg=_p('blue'), fg='white',
                  relief='flat', padx=14, pady=7).pack(anchor='e', pady=(7, 0))
        group_row = 1; signer_groups = []
        for title, keys in self._WIZARD_GROUPS:
            if title.startswith('۶.'):
                signer_groups.append((title, keys)); continue
            self._record_group(form, title, [(key, self._FIELD_LABELS[key]) for key in keys], group_row)
            group_row += 1
        self._payment_group_row = group_row
        self._render_payment_group()
        group_row += 1
        for title, keys in signer_groups:
            self._record_group(form, title, [(key, self._FIELD_LABELS[key]) for key in keys], group_row)
            group_row += 1
        final_group = self._record_group(form, '۷. تأیید نهایی', [], group_row)
        ttk.Label(final_group, text='اطلاعات این رکورد از ویزارد اختصاصی فروش قابل بازبینی و ثبت است.', anchor='e').pack(fill='x', padx=6, pady=4)
        actions = tk.Frame(self.body, bg=surface, highlightbackground=line, highlightthickness=1)
        actions.pack(fill='x', padx=10, pady=(0, 10))
        tk.Button(actions, text='ذخیرهٔ اطلاعات مجاز', command=self._save_metadata, bg='#2E6F4E', fg='white',
                  relief='flat', padx=16, pady=8).pack(side='right', padx=4, pady=5)
        tk.Button(actions, text='بستن', command=self.destroy, bg='#4A5568', fg='white',
                  relief='flat', padx=16, pady=8).pack(side='left', padx=4, pady=5)

    def _record_group(self, parent, title: str, fields: list[tuple[str, str]], row: int):
        group = ttk.LabelFrame(parent, text=title, labelanchor='ne', padding=8)
        group.grid(row=row, column=0, sticky='ew', padx=4, pady=4)
        for index, (key, label) in enumerate(fields):
            field_row, original_column = divmod(index, 2)
            field_column = 1 - original_column
            self._record_field(group, key, label, field_row, field_column)
        return group

    def _record_field(self, parent, key, label, row, column):
        box = ttk.Frame(parent); box.grid(row=row, column=column, sticky='ew', padx=6, pady=4)
        parent.grid_columnconfigure(column, weight=1)
        ttk.Label(box, text=label, anchor='e', justify='right').pack(fill='x')
        if key.endswith('_date'):
            line = ttk.Frame(box); line.pack(fill='x')
            ttk.Entry(line, textvariable=self.values[key], justify='right').pack(side='right', fill='x', expand=True)
            tk.Button(line, text='تقویم', command=lambda current=self.values[key]: ShamsiDatePicker187(self, current),
                      bg=_p('border'), fg=_p('text_primary'), relief='flat', padx=7).pack(side='left', padx=(5, 0))
        elif key == 'deal_mode':
            ttk.Combobox(box, textvariable=self.values[key], values=('واحد کامل', 'فروش متری'), state='readonly', justify='right').pack(fill='x')
        elif key == 'sale_kind':
            ttk.Combobox(box, textvariable=self.values[key], values=('پیش‌فروش', 'آماده'), state='readonly', justify='right').pack(fill='x')
        elif key == 'unit_number':
            self._unit_records = self._available_units()
            self._unit_combo = ttk.Combobox(box, textvariable=self.values[key], values=tuple(persian_digits_187(value) for value in self._unit_records), justify='right')
            self._unit_combo.bind('<<ComboboxSelected>>', self._unit_selected)
            self._unit_combo.pack(fill='x')
        elif key == 'floor':
            floors = tuple(dict.fromkeys(persian_digits_187(item.get('floor') or '') for item in self._unit_records.values() if item.get('floor') not in (None, '')))
            ttk.Combobox(box, textvariable=self.values[key], values=floors, justify='right').pack(fill='x')
        elif key == 'payment_count':
            widget = ttk.Entry(box, textvariable=self.values[key], justify='right')
            widget.bind('<FocusOut>', self._payment_count_changed)
            widget.bind('<Return>', self._payment_count_changed)
            widget.pack(fill='x')
        elif key == 'price_per_m2':
            ttk.Entry(box, textvariable=self.values[key], justify='right', state='readonly').pack(fill='x')
        else:
            ttk.Entry(box, textvariable=self.values[key], justify='right').pack(fill='x')

    def _payment_installment_count(self) -> int:
        try:
            # The entered stage count includes cash, delivery and deed.
            return max(1, min(10, int(en(self.values['payment_count'].get())) - 3))
        except ValueError:
            return 1

    def _render_payment_group(self):
        old_group = getattr(self, '_payment_group', None)
        if old_group is not None and old_group.winfo_exists():
            old_group.destroy()
        labels = payment_labels_for_installments_187(self._payment_installment_count())
        payment_fields = [('payment_count', 'تعداد اقساط')]
        self._payment_group = self._record_group(self._record_form, '۵. شرایط پرداخت', payment_fields, self._payment_group_row)
        for index, label in enumerate(labels, 1):
            self._record_field(self._payment_group, f'pay_{index}_amount', f'{label} (تومان)', index, 1)
            self._record_field(self._payment_group, f'pay_{index}_date', f'تاریخ {label}', index, 0)

    def _payment_count_changed(self, _event=None):
        old_count = getattr(self, '_payment_visible_installments', self._payment_installment_count())
        new_count = self._payment_installment_count()
        if old_count != new_count:
            old_delivery, old_deed = old_count + 2, old_count + 3
            new_delivery, new_deed = new_count + 2, new_count + 3
            for suffix in ('amount', 'date'):
                delivery_value = self.values[f'pay_{old_delivery}_{suffix}'].get()
                deed_value = self.values[f'pay_{old_deed}_{suffix}'].get()
                self.values[f'pay_{old_delivery}_{suffix}'].set('')
                self.values[f'pay_{old_deed}_{suffix}'].set('')
                self.values[f'pay_{new_delivery}_{suffix}'].set(delivery_value)
                self.values[f'pay_{new_deed}_{suffix}'].set(deed_value)
        self._payment_visible_installments = new_count
        self._render_payment_group()

    def _available_units(self) -> dict[str, dict[str, Any]]:
        project = self.values['project_name'].get().strip()
        block = self.values['block_name'].get().strip()
        try:
            with self.db.read() as con:
                rows = con.execute(
                    """SELECT unit_number, floor, area FROM units
                       WHERE status!='CANCELLED'
                         AND (?='' OR COALESCE(project_name,'')=?)
                         AND (?='' OR COALESCE(block_name,'')=?)
                       ORDER BY unit_number""",
                    (project, project, block, block),
                ).fetchall()
        except Exception:
            rows = []
        return {str(row['unit_number']): {'floor': row['floor'], 'area': row['area']} for row in rows if row['unit_number'] not in (None, '')}

    def _refresh_unit_choices(self):
        combo = self._unit_combo
        if combo is None:
            return
        self._unit_records = self._available_units()
        current = self.values['unit_number'].get().strip()
        choices = list(self._unit_records)
        if current and current not in choices:
            choices.insert(0, current)
        combo.configure(values=tuple(persian_digits_187(value) for value in choices))

    def _unit_selected(self, _event=None):
        selected = self.values['unit_number'].get().strip()
        record = self._unit_records.get(selected) or self._unit_records.get(en(selected))
        if not record:
            return
        self.values['floor'].set(persian_digits_187(record.get('floor') or ''))
        self.values['map_area'].set(persian_digits_187(record.get('area') or ''))

    def _record_price_per_m2(self):
        try:
            area = float(en(self.values['contract_area'].get()).replace(',', '') or 0)
        except ValueError:
            area = 0
        price = parse_money(self.values['total_price'].get())
        self.values['price_per_m2'].set(toman(price / area) if area > 0 else '')

    def _show_preview(self):
        path = Path(self.document_path) if self.document_path else None
        label = str(path) if path else 'فایل قرارداد انتخاب نشده است'
        self.preview_canvas.delete('all'); self._preview_source_image = None; self._preview_pil_image = None
        if path and path.suffix.lower() in {'.png', '.gif', '.jpg', '.jpeg', '.webp', '.bmp'} and path.exists():
            try:
                from PIL import Image
                self._preview_pil_image = Image.open(path).convert('RGB')
                self._render_preview_image()
            except (OSError, ValueError, tk.TclError):
                self.preview_canvas.create_text(10, 10, text=label, fill='#DDE7F0', anchor='nw')
        else:
            self.preview_canvas.create_text(10, 10, text=label, fill='#DDE7F0', anchor='nw')

    def _render_preview_image(self):
        self.preview_canvas.delete('all')
        if self._preview_pil_image is not None:
            from PIL import ImageTk
            source = self._preview_pil_image
            canvas_width = max(1, self.preview_canvas.winfo_width() - 8)
            canvas_height = max(1, self.preview_canvas.winfo_height() - 8)
            fit_scale = min(canvas_width / max(1, source.width), canvas_height / max(1, source.height))
            scale = max(0.05, min(1.0, fit_scale)) * self.preview_zoom
            size = (max(1, int(source.width * scale)), max(1, int(source.height * scale)))
            image = ImageTk.PhotoImage(source.resize(size))
            self._preview_image = image
            self.preview_canvas.create_image(0, 0, image=image, anchor='nw', tags=('preview-image',))
            self.preview_canvas.configure(scrollregion=(0, 0, image.width(), image.height()))
            return
        if self._preview_source_image is None:
            return
        image = self._preview_source_image
        if self.preview_zoom > 1:
            image = image.zoom(self.preview_zoom, self.preview_zoom)
        elif self.preview_zoom < 1:
            image = image.subsample(2, 2)
        self._preview_image = image
        self.preview_canvas.create_image(0, 0, image=image, anchor='nw', tags=('preview-image',))
        self.preview_canvas.configure(scrollregion=(0, 0, image.width(), image.height()))

    def _zoom_preview(self, delta):
        self.preview_zoom = max(0.2, min(4, self.preview_zoom + delta))
        self._render_preview_image()

    def _preview_mouse_zoom(self, event):
        """Zoom over the image; scroll the canvas outside it."""
        image_ids = set(self.preview_canvas.find_withtag('preview-image'))
        under_pointer = image_ids.intersection(
            self.preview_canvas.find_overlapping(event.x, event.y, event.x, event.y)
        )
        wheel_delta = event.delta if hasattr(event, 'delta') else 0
        direction = -1 if wheel_delta > 0 or getattr(event, 'num', 0) == 4 else 1
        if under_pointer:
            self._zoom_preview(0.2 if direction < 0 else -0.2)
        elif getattr(event, 'state', 0) & 0x0001:
            self.preview_canvas.xview_scroll(direction, 'units')
        else:
            self.preview_canvas.yview_scroll(direction, 'units')
        return 'break'

    def _open_document(self):
        path = Path(self.document_path) if self.document_path else None
        if not path or not path.exists():
            return messagebox.showinfo('قرارداد', 'فایلی برای باز کردن انتخاب نشده است.', parent=self)
        try:
            import os
            os.startfile(str(path))  # type: ignore[attr-defined]
        except Exception as exc:
            messagebox.showerror('قرارداد', str(exc), parent=self)

    def _load_document(self):
        path = filedialog.askopenfilename(parent=self, title='قرارداد', filetypes=[('Documents', '*.pdf *.jpg *.jpeg *.png *.doc *.docx *.txt'), ('All files', '*.*')])
        if not path:
            return
        self.document_path = path; text = ''
        try:
            text = Path(path).read_text(encoding='utf-8') if Path(path).suffix.lower() == '.txt' else ''
        except (OSError, UnicodeDecodeError):
            text = ''
        parsed = parse_sale_form(text)
        for target, source in {'buyer_name': 'buyer_name', 'unit_number': 'unit_number', 'floor': 'floor', 'contract_area': 'area', 'contract_number': 'contract_number', 'contract_date': 'contract_date_shamsi', 'total_price': 'contract_amount'}.items():
            if parsed.get(source) not in (None, '', 0): self.values[target].set(str(parsed[source]))
        self._show_preview()

    def _save_metadata(self):
        if not self.sale_id:
            return messagebox.showinfo('رکورد فروش', 'این پیش‌نویس هنوز قرارداد ثبت‌شده ندارد؛ ثبت نهایی فقط از ویزارد قرارداد انجام می‌شود.', parent=self)
        raw = {key: value.get().strip() for key, value in self.values.items()}
        try:
            self.revenue.update_sale_metadata(
                self.sale_id, buyer_name=raw['buyer_name'], buyer_phone=raw['buyer_phone'],
                contract_number=raw['contract_number'], contract_date_shamsi=raw['contract_date'],
                notes=contract_note_187(raw), source='GUI_187_SALES_RECORD', actor_id='GUI_187',
            )
        except Exception as exc:
            return messagebox.showerror('رکورد فروش', str(exc), parent=self)
        if self.on_saved: self.on_saved()
        messagebox.showinfo('رکورد فروش', 'اطلاعات غیرمالی ذخیره شد؛ مبالغ و وصول‌ها فقط از مسیر حسابرسی اصلاح می‌شوند.', parent=self)
        self.destroy()


def contract_export_preview_lines_187(specs, payload, headers, document_paths=None) -> list[tuple[str, str]]:
    """Build a visible, resilient preview even when optional export fields are incomplete."""
    lines: list[tuple[str, str]] = [('section', 'مشخصات قرارداد')]
    current_group = None
    for spec in specs or ():
        if isinstance(spec, (tuple, list)) and len(spec) >= 3:
            group, label, value = spec[:3]
        else:
            group, label, value = 'مشخصات قرارداد', 'اطلاعات', spec
        group, label, value = str(group or 'مشخصات قرارداد'), str(label or 'اطلاعات'), str(value or '-')
        if group != current_group:
            lines.append(('section', f'[{group}]'))
            current_group = group
        lines.append(('rtl', f'{label}: {value}'))
    lines.append(('section', 'جدول پرداخت‌ها'))
    lines.append(('table_header', ' | '.join(str(header) for header in headers or ())))
    for row in payload or ():
        values = row if isinstance(row, dict) else dict(zip(headers or (), row))
        lines.append(('rtl', ' | '.join(str(values.get(header, '')) for header in headers or ())))
    if not specs and not payload:
        lines.append(('rtl', 'داده‌ای برای پیش‌نمایش انتخاب نشده است.'))
    paths = [str(path) for path in (document_paths or ()) if str(path).strip()]
    if paths:
        lines.append(('section', 'فیش‌های واریزی انتخاب‌شده:'))
        lines.extend(('rtl', Path(path).name) for path in paths)
    return lines


def contract_preview_payment_rows_187(headers, payload, *, include_documents=True) -> list[dict[str, Any]]:
    """Expand preview rows so every receipt has its own drawable table row."""
    document_headers = [header for header in headers if header in {'نمایش سند', 'فیش واریزی', 'رسید', 'سند'}]
    stage_header = next((header for header in headers if header == 'مرحله' or 'مرحله پرداخت' in header), '')
    date_headers = [header for header in headers if 'تاریخ واریز' in header]
    amount_headers = [header for header in headers if 'مبلغ واریز' in header and 'کل مبلغ' not in header]
    expanded: list[dict[str, Any]] = []
    for row in payload or ():
        values = dict(row) if isinstance(row, dict) else dict(zip(headers or (), row))
        paths: list[tuple[str, str]] = []
        if include_documents:
            for header in document_headers:
                paths.extend((header, path) for path in export_document_paths_187(values.get(header, '')))
            paths.extend(('نمایش سند', path) for path in export_document_paths_187(values.get('__document_paths_187', '')))
            if paths:
                values['__document_paths_187'] = [path for _header, path in paths]
        if not paths:
            expanded.append(values)
            continue
        for number, (header, path) in enumerate(paths, 1):
            entry = dict(values)
            for document_header in document_headers:
                entry[document_header] = ''
            entry[header] = path
            if number > 1:
                for field in (*date_headers, *amount_headers):
                    entry[field] = '—'
            if len(paths) > 1 and stage_header:
                entry[stage_header] = f"{entry.get(stage_header) or 'مرحله'} · فیش {persian_digits_187(number)}"
            expanded.append(entry)
    return expanded


class ContractExportPreview187(BarkavWindow):
    """Preview contract specs/payments before opening the native Save As dialog."""
    def __init__(self, parent, *, export_format, headers, payload, specs, on_confirm, document_paths=None,
                 contract_document_paths=None,
                 report_audience='', report_progress=None, report_project_name='',
                 documents_below_rows=False,
                 on_confirm_with_documents=False,
                 window_title='پیش‌نمایش خروجی قرارداد',
                 table_caption='جدول پرداخت‌ها', row_label='رسید', include_addressee=False):
        super().__init__(parent, window_title, size_class='medium', show_footer=False)
        self.title(window_title); self.output_title = self._output_title(window_title); self.geometry('980x650'); self.minsize(700, 440); self.resizable(True, True)
        self.headers, self.payload, self.specs, self.on_confirm = list(headers), [dict(row) for row in payload], list(specs), on_confirm
        self.table_caption, self.row_label = str(table_caption or 'داده‌های خروجی'), str(row_label or 'ردیف')
        self.document_paths = [str(path) for path in (document_paths or []) if str(path).strip()]
        self.contract_document_paths = [str(path) for path in (contract_document_paths or []) if str(path).strip()]
        self.include_addressee = bool(include_addressee)
        self.report_project_name = str(report_project_name or '').strip()
        self.addressee_choice = tk.StringVar(master=self, value='سایر')
        self.report_audience = str(report_audience or '').strip()
        try:
            self.report_progress = max(0.0, min(100.0, float(report_progress))) if report_progress is not None else None
        except (TypeError, ValueError):
            self.report_progress = None
        self.documents_below_rows = bool(documents_below_rows)
        self.on_confirm_with_documents = bool(on_confirm_with_documents)
        self._preview_images = []
        self._report_document = None
        self._report_key = None
        self._report_pages = []
        # Keep the standard Windows caption, including on focus changes.
        if self.include_addressee:
            self.wm_transient('')
            if __import__('os').name == 'nt':
                self.wm_attributes('-toolwindow', False)
        bar = ttk.Frame(self.body); bar.pack(fill='x', padx=8, pady=8)
        ttk.Button(bar, text='تأیید و ذخیره', command=self._confirm).pack(side='right', padx=6)
        self.format_choice = tk.StringVar(value=export_format)
        format_values = ('PDF', 'Excel', 'پرینت') if self.include_addressee else ('Excel', 'PDF', 'پرینت')
        self.format_combo = ttk.Combobox(bar, textvariable=self.format_choice, values=format_values, state='readonly', justify='right', width=18)
        self.format_combo.pack(side='right'); self.format_combo.bind('<<ComboboxSelected>>', lambda _e: self._render())
        ttk.Label(bar, text='نحوه نمایش').pack(side='right', padx=(18, 6))
        self.orientation_choice = tk.StringVar(value=choose_pdf_orientation(self.headers, self.payload))
        self.orientation_combo = ttk.Combobox(bar, textvariable=self.orientation_choice, values=('افقی', 'عمودی'), state='readonly', justify='right', width=12)
        self.orientation_combo.pack(side='right'); self.orientation_combo.bind('<<ComboboxSelected>>', lambda _e: self._render())
        self.include_documents = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text='نمایش سند', variable=self.include_documents,
                        command=self._render).pack(side='right', padx=(18, 6))
        self.page_count_label = None
        if self.include_addressee:
            self.page_count_label = ttk.Label(bar, text='')
            self.page_count_label.pack(side='left', padx=6)
        preview_area = ttk.Frame(self.body); preview_area.pack(fill='both', expand=True, padx=8, pady=(0, 8))
        # Canvas is already the stable visual primitive used by the active sales
        # windows. It avoids the blank native Text control seen in this dialog.
        self.preview = tk.Canvas(preview_area, bg='#0A1A2A', highlightthickness=0)
        preview_scroll = ttk.Scrollbar(preview_area, orient='vertical', command=self.preview.yview)
        preview_xscroll = ttk.Scrollbar(preview_area, orient='horizontal', command=self.preview.xview)
        self.preview.configure(yscrollcommand=preview_scroll.set, xscrollcommand=preview_xscroll.set)
        preview_scroll.pack(side='right', fill='y'); preview_xscroll.pack(side='bottom', fill='x'); self.preview.pack(side='left', fill='both', expand=True)
        self.addressee_combo = None
        if self.include_addressee:
            self.addressee_combo = ttk.Combobox(
                self.preview, textvariable=self.addressee_choice,
                values=('کارفرما', 'مجری', 'نظارت', 'سایر'),
                state='readonly', justify='right', width=18,
            )
            self.addressee_combo.bind('<<ComboboxSelected>>', lambda _e: self._render(), add='+')
        self.preview.bind('<Configure>', lambda _event: self._render(), add='+')
        self.preview.bind('<MouseWheel>', self._preview_mouse_zoom, add='+')
        self.preview.bind('<ButtonPress-1>', lambda event: self.preview.scan_mark(event.x, event.y), add='+')
        self.preview.bind('<B1-Motion>', lambda event: self.preview.scan_dragto(event.x, event.y, gain=1), add='+')
        self.preview_zoom = 1.0
        if self.include_addressee:
            self.bind('<Map>', self._preserve_native_caption_187, add='+')
            self._preserve_native_caption_187()
        self._render()

    @staticmethod
    def _group_specs(specs, *, blank_missing=False):
        groups: dict[str, list[tuple[str, str]]] = {}
        for spec in specs or ():
            if isinstance(spec, (tuple, list)) and len(spec) >= 3:
                group, label, value = spec[:3]
            else:
                group, label, value = 'مشخصات', 'اطلاعات', spec
            rendered_value = value if value not in (None, '') else ('' if blank_missing else '-')
            groups.setdefault(str(group or 'مشخصات'), []).append((str(label or 'اطلاعات'), str(rendered_value)))
        return groups

    @staticmethod
    def _project_name(specs) -> str:
        return export_project_name_187(specs)

    @staticmethod
    def _output_title(window_title: str) -> str:
        return export_output_title_187(window_title)

    def _render(self):
        if self.include_addressee:
            return self._render_document_187()
        self._preview_images = []
        self.preview.delete('all')
        preview_font_family = kit_font('title', widget=self, bold=True)[0]
        portrait = self.orientation_choice.get() == 'عمودی'
        page_width = 780 if portrait else 1120
        page_height = 1100 if portrait else 780
        # Fit the initial RTL page to the viewport, then let wheel zoom grow
        # beyond that fit instead of clamping the visual scale back down.
        viewport_width = self.preview.winfo_width()
        fit_scale = 1.0
        if viewport_width > 20 and page_width > viewport_width - 20:
            fit_scale = max(0.55, (viewport_width - 20) / page_width)
        scale = max(0.2, fit_scale * self.preview_zoom)
        margin = 24; x = margin; y = margin; page_start = 0
        def rect(left, top, right, bottom, **kwargs):
            return self.preview.create_rectangle(left * scale, top * scale, right * scale, bottom * scale, **kwargs)
        def text(right, top, value, *, width, size=9, bold=False, fill='#17212B'):
            return self.preview.create_text(right * scale, top * scale, text=value, anchor='ne', justify='right',
                                            width=width * scale, fill=fill, font=('Segoe UI', max(7, int(size * scale)), 'bold' if bold else 'normal'))
        def center_text(center, top, value, *, width, size=10, bold=True, fill=_p('heading')):
            return self.preview.create_text(center * scale, top * scale, text=value, anchor='n', justify='center',
                                            width=width * scale, fill=fill,
                                            font=(preview_font_family, max(7, int(size * scale)), 'bold'))
        rect(0, 0, page_width, page_height, fill='#FFFFFF', outline='#FFFFFF')
        header_top = y
        header_height = 146 if self.include_addressee else 112
        header_left, header_right = margin, page_width - margin
        section_width = (header_right - header_left) / 3
        header_bottom = header_top + header_height
        rect(header_left, header_top, header_right, header_bottom, fill='#F7FAFC', outline='#496176', width=2)
        for divider in (header_left + section_width, header_left + 2 * section_width):
            self.preview.create_line(divider * scale, header_top * scale, divider * scale, header_bottom * scale,
                                     fill='#496176', width=max(1, int(scale)))
        center_x = header_left + section_width * 1.5
        right_x = header_left + section_width * 2.5
        left_x = header_left + section_width * 0.5
        center_text(center_x, header_top + 18, 'شرکت مهندسی ساخت بارکاو', width=section_width - 18, size=12)
        project_label = f'پروژه {self._project_name(self.specs)}'
        if self.report_project_name:
            project_label = f'پروژه {self.report_project_name}'
        if project_label == 'پروژه پروژه':
            project_label = 'پروژه'
        center_text(center_x, header_top + 58, project_label, width=section_width - 18, size=11)
        center_text(right_x, header_top + (16 if self.include_addressee else 40), self.output_title, width=section_width - 18, size=12)
        if self.addressee_combo is not None:
            text(right_x + section_width / 2 - 8, header_top + 48, 'جهت ارائه به:', width=section_width - 28, size=8, bold=True)
            self.preview.create_window(
                right_x * scale, (header_top + 108) * scale,
                window=self.addressee_combo, width=(section_width - 26) * scale,
                height=27 * scale, anchor='center',
            )
        elif self.report_audience:
            center_text(right_x, header_top + 69, f'جهت ارائه به: {self.report_audience}',
                        width=section_width - 18, size=10, bold=True)
        logo = art.logo(height=38, background='#F7FAFC', colour='#102A43', drop_tagline=True,
                        wordmark_scale=1.0, align_wordmark=False, master=self)
        if logo is not None:
            self._preview_images.append(logo)
            self.preview.create_image(left_x * scale, (header_top + header_height / 2) * scale, image=logo, anchor='center')
        y = header_bottom + 18
        groups = self._group_specs(self.specs, blank_missing=bool(self.report_project_name))
        if groups:
            group_items = list(groups.items())
            table_width = page_width - 2 * margin
            full_width = len(group_items) == 1 and not self.report_project_name
            group_width = (page_width - 3 * margin) / 2
            if full_width:
                group_width = table_width
            for index in range(0, len(group_items), 2):
                row_groups = list(reversed(group_items[index:index + 2]))
                pair = list(reversed(row_groups))
                if full_width:
                    placements = [(margin, pair[0][0], pair[0][1])]
                elif len(pair) == 2:
                    placements = [
                        (margin, pair[1][0], pair[1][1]),
                        (page_width - margin - group_width, pair[0][0], pair[0][1]),
                    ]
                else:
                    placements = [(page_width - margin - group_width, pair[0][0], pair[0][1])]
                cell_width = (group_width - 16) / 2

                def entry_lines(label, value):
                    text_value = f'{label}: {value}'
                    chars_per_line = max(12, int(cell_width / 6.2))
                    return max(1, math.ceil(len(text_value) / chars_per_line))

                row_heights = []
                entry_heights = {}
                for _left, _group, entries in placements:
                    heights = []
                    for entry_index in range(0, len(entries), 2):
                        height = max(
                            25,
                            max(entry_lines(*entry) for entry in entries[entry_index:entry_index + 2]) * 15 + 8,
                        )
                        heights.append(height)
                        entry_heights[id(entries)] = heights
                    row_heights.append(32 + sum(heights or [25]))
                row_height = max(row_heights or [57])
                for left, group, entries in placements:
                    right = left + group_width
                    heights = entry_heights.get(id(entries), [25])
                    height = 32 + sum(heights)
                    rect(left, y, right, y + height, outline='#496176', width=1)
                    rect(left, y, right, y + 24, fill='#DCE8F2', outline='#496176')
                    text(right - 7, y + 5, group, width=group_width - 14, size=10, bold=True, fill='#102A43')
                    for entry_index, (label, value) in enumerate(entries):
                        row, column_in_row = divmod(entry_index, 2)
                        cell_right = right - 8 - column_in_row * cell_width
                        top = y + 30 + sum(heights[:row])
                        text(cell_right, top, f'{label}: {value}', width=cell_width - 6, size=8)
                y += row_height + 10
        if not self.specs:
            text(page_width - margin, y, 'داده‌ای برای پیش‌نمایش انتخاب نشده است.', width=page_width - 2 * margin, size=10); y += 30
        table_width = page_width - 2 * margin
        if self.documents_below_rows:
            preview_rows = [dict(row) for row in self.payload]
            if not self.include_documents.get():
                for row in preview_rows:
                    for header in self.headers:
                        if header in {'نمایش سند', 'فیش واریزی', 'رسید', 'سند'}:
                            row[header] = ''
        else:
            preview_rows = contract_preview_payment_rows_187(
                self.headers, self.payload, include_documents=self.include_documents.get(),
            )
        receipt_label = f'{self.table_caption} — {fa(len(preview_rows))} {self.row_label}'
        text(page_width - margin, y, receipt_label, width=table_width, size=11, bold=True, fill='#102A43'); y += 25
        display_headers = list(self.headers)
        document_headers = [header for header in display_headers if header in {'نمایش سند', 'فیش واریزی', 'رسید', 'سند'}]
        if self.documents_below_rows:
            display_headers = [header for header in display_headers if header not in document_headers]
        if self.include_documents.get() and not document_headers and any(export_document_paths_187(row.get('__document_paths_187', '')) for row in preview_rows):
            display_headers.append('نمایش سند')
            document_headers = ['نمایش سند']
        # A6-sized document slot in the shared preview (105x148 proportion).
        document_width = 0 if self.documents_below_rows else 300 if document_headers else 0
        other_width = (table_width - document_width) / max(1, len(display_headers) - len(document_headers))
        columns = []
        right = page_width - margin
        for header in display_headers:
            width = document_width if header in document_headers else other_width
            columns.append((header, right - width, right)); right -= width
        def draw_payment_header(top):
            bottom = top + 27
            for header, left, right in columns:
                rect(left, top, right, bottom, fill='#153B5B', outline='#B8C2CC')
                text(right - 4, top + 6, export_header_label_187(header), width=right - left - 8, size=8, bold=True, fill='#FFFFFF')
            return bottom

        y = draw_payment_header(y)
        for values in preview_rows:
            row_paths = []
            for header in document_headers:
                row_paths.extend(export_document_paths_187(values.get(header, '')))
            if not any(header in self.headers for header in document_headers):
                row_paths.extend(export_document_paths_187(values.get('__document_paths_187', '')))
            if not self.include_documents.get():
                row_paths = []
            # second-page receipts visible instead of drawing them past a cell.
            receipt_preview_height = 300 if self.documents_below_rows else 420
            row_height = max(32, 12 + receipt_preview_height * len(row_paths)) if document_headers and not self.documents_below_rows else 36
            row_content_height = row_height + (
                (receipt_preview_height + 36 if row_paths else 38)
                if self.documents_below_rows and self.include_documents.get() else 0
            )
            if y + row_content_height > page_start + page_height - margin:
                page_start += page_height + 18
                rect(0, page_start, page_width, page_start + page_height, fill='#FFFFFF', outline='#FFFFFF')
                text(page_width - margin, page_start + margin, 'ادامه جدول پرداخت‌ها', width=table_width, size=11, bold=True, fill='#102A43')
                y = draw_payment_header(page_start + margin + 25)
            for header, left, right in columns:
                rect(left, y, right, y + row_height, outline='#B8C2CC')
                if header not in document_headers and header in self.headers:
                    missing = '' if self.report_project_name else '-'
                    value = values.get(header, missing)
                    text(right - 4, y + 7, str(missing if value in (None, '') else value),
                         width=right - left - 8, size=8)
            if self.documents_below_rows and self.include_documents.get():
                y += row_height
                box_height = receipt_preview_height + 36 if row_paths else 38
                rect(margin, y, page_width - margin, y + box_height, outline='#496176', fill='#F7FAFC')
                if row_paths:
                    text(page_width - margin - 8, y + 5, 'اسناد و تصاویر فعالیت',
                         width=table_width - 16, size=8, bold=True, fill='#102A43')
                    per_image_width = min(215, (table_width - 16) / max(1, len(row_paths)))
                    per_image_height = per_image_width * 148 / 105
                    image_right = page_width - margin - 8
                    for path in row_paths[:4]:
                        try:
                            from PIL import Image, ImageTk
                            image = Image.open(path).convert('RGB')
                            image.thumbnail((int(per_image_width * scale), int(per_image_height * scale)))
                            photo = ImageTk.PhotoImage(image); self._preview_images.append(photo)
                            self.preview.create_image(image_right * scale, (y + 24) * scale,
                                                      image=photo, anchor='ne', tags=('preview-image',))
                            image_right -= per_image_width + 8
                        except (OSError, ValueError, tk.TclError):
                            text(image_right, y + 24, Path(path).name, width=per_image_width, size=8)
                            image_right -= per_image_width + 8
                elif not self.report_project_name:
                    text(page_width - margin - 8, y + 8, 'سند تصویری ثبت نشده است.',
                         width=table_width - 16, size=8)
                y += box_height
                continue
            if document_headers:
                doc_left, doc_right = next((left, right) for header, left, right in columns if header in document_headers)
                image_x, image_y = doc_right - 6, y + 6
                for path in row_paths:
                    try:
                        from PIL import Image, ImageTk
                        image = Image.open(path).convert('RGB'); image.thumbnail((int((doc_right - doc_left - 12) * scale), int(receipt_preview_height * scale)))
                        photo = ImageTk.PhotoImage(image); self._preview_images.append(photo)
                        self.preview.create_image(image_x * scale, image_y * scale, image=photo, anchor='ne', tags=('preview-image',))
                        image_y += image.height / scale + 6
                    except (OSError, ValueError, tk.TclError):
                        text(doc_right - 4, image_y, Path(path).name, width=doc_right - doc_left - 8, size=8)
                        image_y += 18
                if not row_paths and not self.report_project_name:
                    text(doc_right - 4, y + 7, 'سند ثبت نشده است', width=doc_right - doc_left - 8, size=8)
            y += row_height
        if not preview_rows:
            text(page_width - margin, y, 'رسیدی برای پیش‌نمایش انتخاب نشده است.', width=table_width, size=9)
            y += 28
        if self.contract_document_paths and self.include_documents.get():
            y += 18
            text(page_width - margin, y, 'تصویر قرارداد', width=table_width, size=11, bold=True, fill='#102A43'); y += 28
            for path in self.contract_document_paths:
                try:
                    from PIL import Image, ImageTk
                    image = Image.open(path).convert('RGB'); image.thumbnail((int(360 * scale), int(510 * scale)))
                    photo = ImageTk.PhotoImage(image); self._preview_images.append(photo)
                    self.preview.create_image((page_width - margin) * scale, y * scale, image=photo, anchor='ne', tags=('preview-image',))
                    y += image.height / scale + 18
                except (OSError, ValueError, tk.TclError):
                    text(page_width - margin, y, Path(path).name, width=table_width, size=8); y += 25
        if self.report_progress is not None:
            y += 18
            bar_height = 30
            if y + bar_height + 8 > page_start + page_height - margin:
                page_start += page_height + 18
                rect(0, page_start, page_width, page_start + page_height, fill='#FFFFFF', outline='#FFFFFF')
                y = page_start + margin
            track_left, track_right = margin, page_width - margin
            radius = bar_height / 2
            rect(track_left + radius, y, track_right - radius, y + bar_height,
                 fill='#496176', outline='#496176')
            self.preview.create_oval((track_left) * scale, y * scale,
                                     (track_left + bar_height) * scale, (y + bar_height) * scale,
                                     fill='#496176', outline='#496176', width=max(1, int(scale)))
            self.preview.create_oval((track_right - bar_height) * scale, y * scale,
                                     track_right * scale, (y + bar_height) * scale,
                                     fill='#496176', outline='#496176', width=max(1, int(scale)))
            self.preview.create_line((track_left + radius) * scale, y * scale,
                                     (track_right - radius) * scale, y * scale,
                                     fill='#496176', width=max(1, int(scale)))
            self.preview.create_line((track_left + radius) * scale, (y + bar_height) * scale,
                                     (track_right - radius) * scale, (y + bar_height) * scale,
                                     fill='#496176', width=max(1, int(scale)))
            filled = table_width * self.report_progress / 100
            if filled > 0:
                filled = max(filled, bar_height)
                fill_right = min(track_right, track_left + filled)
                fill_radius = min(radius, (fill_right - track_left) / 2)
                rect(track_left + fill_radius, y, fill_right - fill_radius, y + bar_height,
                     fill='#2583D8', outline='#2583D8')
                self.preview.create_oval(track_left * scale, y * scale,
                                         (track_left + fill_radius * 2) * scale, (y + bar_height) * scale,
                                         fill='#2583D8', outline='#2583D8')
                if fill_right - track_left > bar_height:
                    self.preview.create_oval((fill_right - bar_height) * scale, y * scale,
                                             fill_right * scale, (y + bar_height) * scale,
                                             fill='#2583D8', outline='#2583D8')
            center_text(page_width / 2, y + 5,
                        f'پیشرفت کلی پروژه  {fa(f"{self.report_progress:.1f}")}٪',
                        width=table_width - 12, size=9, fill='#FFFFFF')
            y += bar_height + 8
        self.preview.configure(scrollregion=(0, 0, page_width * scale + 20, y * scale + 30))
        self.preview.yview_moveto(0)
        # At higher zoom levels keep the initial RTL view on the physical right.
        self.preview.xview_moveto(1)

    def _preserve_native_caption_187(self, event=None):
        if event is not None and event.widget is not self:
            return
        if __import__('os').name != 'nt':
            return
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            # Keep all three system buttons even when the preview loses focus.
            style = ctypes.windll.user32.GetWindowLongW(hwnd, -16)
            required = 0x00020000 | 0x00010000 | 0x00080000
            if style & required != required:
                ctypes.windll.user32.SetWindowLongW(hwnd, -16, style | required)
                ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0037)
            # The Windows 10 inactive dark caption makes its buttons disappear
            # against the caption. A system caption keeps their contrast stable.
            value = ctypes.c_int(0)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))
        except (AttributeError, OSError, tk.TclError):
            return

    def _render_document_187(self):
        """Display the actual PDF pages, rather than a second layout."""
        from PIL import Image, ImageTk
        from report_document_stage18_7 import build_report_document, fa_number
        key = (self.orientation_choice.get(), self.addressee_choice.get(),
               bool(self.include_documents.get()))
        if key != self._report_key:
            self._report_document = build_report_document(
                self.headers, self.payload, self.specs, self.output_title,
                orientation=key[0], audience=key[1], include_documents=key[2],
                document_paths=self.document_paths,
                contract_document_paths=self.contract_document_paths,
                progress=self.report_progress, project_name=self.report_project_name,
            )
            self._report_pages = list(self._report_document.page_images(scale=1.5))
            self._report_key = key
        self.page_count_label.configure(text=f'تعداد صفحات گزارش: {fa_number(self._report_document.page_count)}')
        self.preview.delete('all')
        self._preview_images = []
        viewport = max(700, self.preview.winfo_width()) if self.preview.winfo_width() <= 20 else self.preview.winfo_width()
        page_width = self._report_pages[0].width if self._report_pages else 1
        scale = min(1, (viewport - 20) / page_width) * self.preview_zoom
        y = 8
        for index, page in enumerate(self._report_pages):
            image = page.resize((max(1, round(page.width * scale)), max(1, round(page.height * scale))), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(image, master=self.preview)
            self._preview_images.append(photo)
            self.preview.create_image(10, y, image=photo, anchor='nw', tags=('report-page',))
            if index == 0 and self.addressee_combo is not None:
                points_scale = scale * 1.5
                pdf_width = page.width / 1.5
                section = (pdf_width - 48) / 3
                self.preview.create_window(
                    10 + (24 + section * 2.5) * points_scale,
                    y + 80 * points_scale,
                    window=self.addressee_combo, width=max(70, (section - 18) * points_scale),
                    height=max(18, 19 * points_scale), anchor='center',
                )
            y += image.height + 18
        self.preview.configure(scrollregion=(0, 0, page_width * scale + 20, y))

    def _save_document_187(self):
        """Save the already displayed immutable report; cancellation keeps it open."""
        from export_utils import print_file
        choice = self.format_choice.get()
        suffix = '.xlsx' if choice == 'Excel' else '.pdf'
        path = filedialog.asksaveasfilename(
            parent=self, title=f'خروجی {self.output_title}',
            defaultextension=suffix, initialfile=f'{self.output_title}{suffix}',
            filetypes=[('Excel', '*.xlsx')] if choice == 'Excel' else [('PDF', '*.pdf')],
        )
        if not path:
            self._take_focus()
            return False
        try:
            # A snapshot of the preview is also the output in every format.
            self._report_document.save(path, choice)
            if choice == 'پرینت':
                print_file(path)
        except Exception as exc:
            messagebox.showerror('خروجی', f'خروجی انجام نشد:\n{exc}', parent=self)
            self._take_focus()
            return False
        messagebox.showinfo('خروجی', f'فایل ساخته شد:\n{path}', parent=self)
        return True

    def _preview_mouse_zoom(self, event):
        """Zoom over receipt/contract images; scroll the page elsewhere."""
        if self.include_addressee and getattr(event, 'state', 0) & 0x0004:
            direction = 1 if getattr(event, 'delta', 0) > 0 else -1
            self.preview_zoom = max(.5, min(2.5, self.preview_zoom + direction * .1))
            self._render()
            return 'break'
        image_ids = set(self.preview.find_withtag('preview-image'))
        under_pointer = image_ids.intersection(
            self.preview.find_overlapping(event.x, event.y, event.x, event.y)
        )
        wheel_delta = event.delta if hasattr(event, 'delta') else 0
        direction = -1 if wheel_delta > 0 or getattr(event, 'num', 0) == 4 else 1
        if image_ids.intersection(
            self.preview.find_overlapping(event.x, event.y, event.x, event.y)
        ):
            self.preview_zoom = max(.5, min(2.5, self.preview_zoom + (.1 if direction < 0 else -.1)))
            self._render()
        elif getattr(event, 'state', 0) & 0x0001:
            self.preview.xview_scroll(direction, 'units')
        else:
            self.preview.yview_scroll(direction, 'units')
        return 'break'

    def _confirm(self):
        # Keep the populated preview open if Save As is cancelled or fails.
        if getattr(self, 'include_addressee', False) and getattr(self, '_report_document', None) is not None:
            saved = self._save_document_187()
        elif getattr(self, 'include_addressee', False):
            saved = self.on_confirm(
                self.format_choice.get(), self.orientation_choice.get(),
                self.addressee_choice.get(), self.include_documents.get(),
            )
        elif getattr(self, 'on_confirm_with_documents', False):
            saved = self.on_confirm(self.format_choice.get(), self.orientation_choice.get(),
                                    bool(self.include_documents.get()))
        else:
            saved = self.on_confirm(self.format_choice.get(), self.orientation_choice.get())
        if saved:
            self.destroy()


def show_export_preview_187(parent, *, export_format, headers, rows, title,
                            on_confirm, specs=(), document_paths=None,
                            contract_document_paths=None,
                            report_audience='', report_progress=None, report_project_name='',
                            documents_below_rows=False,
                            on_confirm_with_documents=False,
                            table_caption='داده‌های خروجی', row_label='ردیف',
                            include_addressee=False):
    """Open the shared RTL preview used by every active 18.7 export surface.

    rows may be dictionaries or sequences in the same logical order as
    headers. The existing save callback remains the source of truth, so
    previewing never writes to disk or mutates financial data.
    """
    headers = list(headers or ())
    payload = []
    for row in rows or ():
        if isinstance(row, dict):
            payload.append(dict(row))
        else:
            record = dict(zip(headers, row))
            record['__values_187'] = list(row)
            payload.append(record)
    choices = {'xlsx': 'Excel', 'pdf': 'PDF', 'print': 'پرینت'}
    selected_format = choices.get(str(export_format or '').lower(), export_format or 'PDF')
    return ContractExportPreview187(
        parent,
        export_format=selected_format,
        headers=headers,
        payload=payload,
        specs=list(specs or ()),
        document_paths=document_paths,
        contract_document_paths=contract_document_paths,
        report_audience=report_audience,
        report_progress=report_progress,
        report_project_name=report_project_name,
        documents_below_rows=documents_below_rows,
        on_confirm_with_documents=on_confirm_with_documents,
        window_title=title,
        table_caption=table_caption,
        row_label=row_label,
        include_addressee=include_addressee,
        on_confirm=on_confirm,
    )
class ContractDetails187(BarkavWindow):
    """Read-only contract and payment detail window over the existing revenue ledger."""
    _WIZARD_BOXES = (
        ('۱. مورد معامله', ('project_name', 'block_name', 'deal_mode', 'sale_kind', 'unit_number', 'floor', 'map_area', 'contract_area')),
        ('۲. تاریخ‌ها', ('contract_number', 'contract_date', 'delivery_date', 'deed_date')),
        ('۳. خریدار', ('buyer_name', 'father_name', 'national_id', 'buyer_phone')),
        ('۴. مالی', ('total_price', 'price_per_m2', 'broker_fee')),
        ('۶. امضاکنندگان', ('notary_name', 'witness_1', 'witness_2', 'buyer_representative', 'seller_representative')),
    )
    _FIELD_LABELS = dict(SalesRecord187._FIELDS)
    def __init__(self, parent, *, db, base_dir: Path, sale_id: str):
        super().__init__(parent, 'جزئیات قرارداد فروش', size_class='large', show_footer=False)
        self.db, self.base_dir, self.sale_id = db, Path(base_dir), str(sale_id)
        self.revenue = RevenueService(db); self.attachments = AttachmentService(db, self.base_dir)
        self.include_documents = tk.BooleanVar(value=True); self._documents: dict[str, list[dict[str, Any]]] = {}
        # The contract grid is stage-oriented, whereas receipt exports must
        # preserve the finance ledger's one-row-per-received-payment evidence.
        self._receipt_rows_by_installment: dict[str, list[dict[str, Any]]] = {}
        # Keep a normal overlapped Toplevel so Windows supplies native
        # minimize/maximize/restore/close controls in its title bar.
        self.title('جزئیات قرارداد فروش'); self.geometry('1280x720'); self.minsize(950, 560); self.resizable(True, True)
        self._build(); self._refresh()

    def _build(self):
        tools = ttk.Frame(self.body); tools.pack(fill='x', padx=8, pady=8)
        self.export_choice = tk.StringVar(value=EXPORT_PLACEHOLDER_187)
        export_combo = ttk.Combobox(tools, textvariable=self.export_choice, values=(EXPORT_PLACEHOLDER_187, 'PDF', 'Excel', 'پرینت'), state='readonly', justify='right', width=18)
        export_combo.pack(side='right', padx=3)
        export_combo.bind('<<ComboboxSelected>>', self._export_selected)
        ttk.Checkbutton(tools, text='نمایش سندهای واریزی در خروجی', variable=self.include_documents).pack(side='right', padx=8)
        self.summary = tk.StringVar(value='')
        ttk.Label(self.body, textvariable=self.summary, anchor='e').pack(fill='x', padx=10, pady=(0, 8))
        cards_area = ttk.Frame(self.body); cards_area.pack(fill='both', expand=True, padx=10, pady=(0, 8))
        self.cards_canvas = tk.Canvas(cards_area, height=290, highlightthickness=0)
        cards_scroll = ttk.Scrollbar(cards_area, orient='vertical', command=self.cards_canvas.yview)
        self.cards_canvas.configure(yscrollcommand=cards_scroll.set)
        cards_scroll.pack(side='right', fill='y'); self.cards_canvas.pack(side='left', fill='both', expand=True)
        self.wizard_cards = ttk.Frame(self.cards_canvas)
        cards_window = self.cards_canvas.create_window((0, 0), window=self.wizard_cards, anchor='nw')
        self.wizard_cards.bind('<Configure>', lambda _e: self.cards_canvas.configure(scrollregion=self.cards_canvas.bbox('all')))
        self.cards_canvas.bind('<Configure>', lambda event: self.cards_canvas.itemconfigure(cards_window, width=event.width))
        table_area = ttk.Frame(self.body); table_area.pack(fill='both', expand=True, padx=10, pady=(0, 10))
        self.tree = ttk.Treeview(table_area, columns=tuple(key for key, _label, _width in PAYMENT_DETAIL_COLUMNS_187), show='headings')
        for key, label, width in PAYMENT_DETAIL_COLUMNS_187:
            self.tree.heading(key, text=export_header_label_187(label), anchor='e'); self.tree.column(key, width=width, anchor='e', stretch=True)
        apply_tree_rtl(self.tree)
        table_xscroll = ttk.Scrollbar(table_area, orient='horizontal', command=self.tree.xview)
        table_yscroll = ttk.Scrollbar(table_area, orient='vertical', command=self.tree.yview)
        self.tree.configure(xscrollcommand=table_xscroll.set, yscrollcommand=table_yscroll.set)
        table_yscroll.pack(side='right', fill='y'); table_xscroll.pack(side='bottom', fill='x'); self.tree.pack(side='left', fill='both', expand=True)
        self.tree.bind('<Double-1>', lambda _event: self._open_document())

    def _toggle_maximize(self):
        try:
            self.state('normal' if self.state() == 'zoomed' else 'zoomed')
        except tk.TclError:
            self.attributes('-zoomed', self.state() != 'zoomed')

    def _refresh(self):
        sale = self.revenue.get_sale(self.sale_id) or {}; summary = self.revenue.sale_summary(self.sale_id)
        self.summary.set(f"مبلغ کل: {toman(sale.get('contract_amount'))} تومان | کل پرداختی: {toman(summary.cash_received)} تومان | معوق: {toman(summary.overdue_amount)} تومان | مانده: {toman(summary.receivable)} تومان")
        self._set_wizard_fields(sale)
        for iid in self.tree.get_children(): self.tree.delete(iid)
        self._documents = {}; self._receipt_rows_by_installment = {}
        with self.db.read() as con:
            rows = con.execute("""SELECT i.*, COALESCE(SUM(a.amount),0) paid, MAX(r.received_date_shamsi) received_date,
                                      MAX(r.transaction_id) transaction_id
                               FROM installments i
                               LEFT JOIN payment_allocations a ON a.installment_id=i.installment_id
                               LEFT JOIN received_payments r ON r.received_payment_id=a.received_payment_id AND r.status!='CANCELLED'
                               WHERE i.sale_id=? AND i.status!='CANCELLED'
                               GROUP BY i.installment_id ORDER BY COALESCE(i.sequence_no,999999),i.due_date""", (self.sale_id,)).fetchall()
            payment_links = con.execute("""SELECT a.installment_id, r.transaction_id, r.received_payment_id,
                                                  r.amount, r.received_date_shamsi
                                           FROM payment_allocations a
                                           JOIN received_payments r ON r.received_payment_id=a.received_payment_id
                                           WHERE a.installment_id IN (SELECT installment_id FROM installments WHERE sale_id=?)""", (self.sale_id,)).fetchall()
        links_by_installment: dict[str, list[dict[str, Any]]] = {}
        for link in payment_links:
            links_by_installment.setdefault(str(link['installment_id']), []).append(dict(link))
        today = date.today()
        for number, source in enumerate(rows, 1):
            item = dict(source); amount, paid = int(item.get('amount') or 0), int(item.get('paid') or 0)
            try: late = max(0, (today - date.fromisoformat(str(item.get('due_date')))).days) if paid < amount else 0
            except ValueError: late = 0
            documents, seen_documents, receipt_rows = [], set(), []
            for link in links_by_installment.get(str(item['installment_id']), []):
                entities = []
                if link.get('transaction_id'):
                    entities.append(('TRANSACTION', str(link['transaction_id'])))
                if link.get('received_payment_id'):
                    entities.extend([('RECEIVED_PAYMENT', str(link['received_payment_id'])), ('SALE_PAYMENT', str(link['received_payment_id']))])
                receipt_documents, seen_receipt_documents = [], set()
                for document in self.attachments.list_for_entities(entities):
                    marker = str(document.get('attachment_id') or document.get('local_path') or '')
                    if marker and marker not in seen_receipt_documents:
                        receipt_documents.append(document); seen_receipt_documents.add(marker)
                    if marker and marker not in seen_documents:
                        documents.append(document); seen_documents.add(marker)
                receipt_rows.append({
                    'received_payment_id': str(link.get('received_payment_id') or ''),
                    'amount': int(link.get('amount') or 0),
                    'received_date_shamsi': str(link.get('received_date_shamsi') or '-'),
                    'documents': receipt_documents,
                })
            self._documents[str(item['installment_id'])] = documents
            self._receipt_rows_by_installment[str(item['installment_id'])] = receipt_rows
            debt = amount - paid; balance = f"{'بدهکار' if debt >= 0 else 'بستانکار'}: {toman(abs(debt))}"
            self.tree.insert('', 'end', iid=str(item['installment_id']), values=(
                selectable_row_187(number), item.get('description') or f'قسط {number}', persian_digits_187(item.get('due_date_shamsi') or '-'),
                toman(amount), persian_digits_187(item.get('due_date_shamsi') or '-'), persian_digits_187(item.get('received_date') or '-'), toman(paid), fa(late), balance,
                'نمایش سند' if documents else '-',
            ))

    def _set_wizard_fields(self, sale: dict[str, Any]):
        try: metadata = json.loads(str(sale.get('notes') or '{}'))
        except (ValueError, TypeError, json.JSONDecodeError): metadata = {}
        fallback = {
            'project_name': sale.get('project_name'), 'block_name': sale.get('block_name'),
            'unit_number': sale.get('unit_number'), 'floor': sale.get('floor'), 'map_area': sale.get('area'),
            'contract_area': sale.get('area'), 'contract_number': sale.get('contract_number'),
            'contract_date': sale.get('contract_date_shamsi'), 'buyer_name': sale.get('buyer_name'),
            'buyer_phone': sale.get('buyer_phone'), 'total_price': toman(sale.get('contract_amount')),
        }
        values = {**fallback, **metadata}
        documents = self.attachments.list_for_entities([('SALE', self.sale_id)])
        self._contract_document_paths = [str(item.get('local_path') or '') for item in documents if str(item.get('local_path') or '').strip()]
        export_fields = []
        signer_boxes = []
        for title, keys in self._WIZARD_BOXES:
            if title.startswith('۶.'):
                signer_boxes.append((title, keys)); continue
            fields = [(self._FIELD_LABELS[key], str(values.get(key) or '-')) for key in keys]
            export_fields.extend((title, label, value) for (label, value) in fields)
            self._build_wizard_box(title, fields)
        # The ledger is authoritative for an existing contract.  Do not render
        # a fixed legacy ten-installment list when this sale actually has fewer
        # stages (for example cash + four agreed installments).
        recorded_installments = self.revenue.list_installments(self.sale_id)
        if recorded_installments:
            payments = [
                (
                    str(item.get('description') or f"مرحله {item.get('sequence_no') or '-'}"),
                    f"{toman(item.get('amount') or 0)} تومان | تاریخ: {item.get('due_date_shamsi') or '-'}",
                )
                for item in recorded_installments
            ]
        else:
            try:
                installment_count = max(1, min(10, int(en(str(values.get('payment_count') or '1')))))
            except ValueError:
                installment_count = 1
            labels = payment_labels_for_installments_187(installment_count)
            payments = [
                (label, f"{values.get(f'pay_{index}_amount') or '-'} تومان | تاریخ: {values.get(f'pay_{index}_date') or '-'}")
                for index, label in enumerate(labels, 1)
            ]
        export_fields.extend(('۵. شرایط پرداخت', label, value) for label, value in payments)
        self._build_wizard_box('۵. شرایط پرداخت', payments)
        for title, keys in signer_boxes:
            fields = [(self._FIELD_LABELS[key], str(values.get(key) or '-')) for key in keys]
            export_fields.extend((title, label, value) for (label, value) in fields)
            self._build_wizard_box(title, fields)
        self._wizard_export_fields = export_fields

    def _build_wizard_box(self, title: str, fields: list[tuple[str, str]]):
        box = ttk.LabelFrame(self.wizard_cards, text=title, labelanchor='ne', padding=8)
        box.pack(fill='x', expand=True, pady=4)
        for index, (label, value) in enumerate(fields):
            row, original_column = divmod(index, 2); column = 1 - original_column; box.grid_columnconfigure(column, weight=1)
            item = ttk.Frame(box); item.grid(row=row, column=column, sticky='ew', padx=5, pady=3)
            ttk.Label(item, text=label, anchor='e').pack(fill='x')
            ttk.Label(item, text=persian_digits_187(value), anchor='e', justify='right').pack(fill='x')

    def _open_document(self):
        selected = self.tree.selection()
        if not selected: return
        documents = self._documents.get(selected[0], [])
        if not documents:
            return messagebox.showinfo('سند پرداخت', 'برای این ردیف سندی ثبت نشده است.', parent=self)
        values = self.tree.item(selected[0], 'values')
        try:
            PaymentDocuments187(
                self, db=self.db, base_dir=self.base_dir,
                payments=[{
                    'stage': str(values[1] or 'مرحله پرداخت'),
                    'date': str(values[5] or '-'),
                    'amount': parse_money(str(values[6] or '0')),
                    'documents': documents,
                }],
            )
        except Exception as exc:
            messagebox.showerror('سند پرداخت', str(exc), parent=self)

    def _export_selected(self, _event=None):
        export_format = {'Excel': 'xlsx', 'PDF': 'pdf', 'پرینت': 'print'}.get(self.export_choice.get())
        if export_format:
            self._export(export_format)

    def _export(self, export_format: str):
        # Keep contract metadata from the stage grid, but build its receipt
        # rows from the same individual payment allocations used by Finance.
        from report_document_stage18_7 import selected_tree_items
        selected = selected_tree_items(self.tree)
        headers = [export_header_label_187(self.tree.heading(key, 'text'))
                   for key in self.tree['columns'] if key != CHECK_COLUMN]
        row_index = {header: index for index, header in enumerate(headers)}
        stage_index = row_index.get('مرحله'); date_index = row_index.get('تاریخ واریز')
        amount_index = row_index.get('مبلغ واریز (تومان)')
        export_rows, export_ids, documents_by_export_row = [], [], {}
        for installment_id in selected:
            source = list(self.tree.item(installment_id, 'values'))
            receipt_rows = list(self._receipt_rows_by_installment.get(str(installment_id), []))
            if not receipt_rows:
                export_id = f'{installment_id}:stage'
                export_rows.append(tuple(source)); export_ids.append(export_id)
                documents_by_export_row[export_id] = list(self._documents.get(str(installment_id), []))
                continue
            multiple_receipts = len(receipt_rows) > 1
            for number, receipt in enumerate(receipt_rows, 1):
                row = list(source)
                if multiple_receipts and stage_index is not None:
                    row[stage_index] = f"{row[stage_index]}-{persian_digits_187(number)}"
                if date_index is not None:
                    row[date_index] = persian_digits_187(receipt.get('received_date_shamsi') or '-')
                if amount_index is not None:
                    row[amount_index] = toman(receipt.get('amount') or 0)
                export_id = f"{installment_id}:{receipt.get('received_payment_id') or number}"
                export_rows.append(tuple(row)); export_ids.append(export_id)
                documents_by_export_row[export_id] = list(receipt.get('documents') or [])
        payload = payment_detail_export_payload_187(headers, export_rows, export_ids,
                                                     documents_by_export_row, self.include_documents.get())
        specs = list(getattr(self, '_wizard_export_fields', []))
        choices = {'xlsx': 'Excel', 'pdf': 'PDF', 'print': 'پرینت'}
        document_paths = export_payload_document_paths_187(payload, 'نمایش سند')
        contract_document_paths = list(getattr(self, '_contract_document_paths', []))
        return ContractExportPreview187(self, export_format=choices.get(export_format, 'PDF'), headers=headers,
                                        payload=payload, specs=specs,
                                        document_paths=document_paths,
                                        contract_document_paths=contract_document_paths,
                                        include_addressee=True,
                                        on_confirm=lambda choice, orientation, addressee, include_documents:
                                            self._save_export(choice, headers, payload, specs, document_paths,
                                                              orientation, contract_document_paths,
                                                              addressee, include_documents))

    def _save_export(self, choice: str, headers, payload, specs, document_paths=None,
                     orientation='افقی', contract_document_paths=None,
                     addressee='سایر', include_documents=True):
        export_format = {'Excel': 'xlsx', 'PDF': 'pdf', 'پرینت': 'print'}.get(choice, 'pdf')
        actual_format = 'pdf' if export_format == 'print' else export_format
        extension = f'.{actual_format}'
        path = filedialog.asksaveasfilename(parent=self, title=f'خروجی {actual_format.upper()} جزئیات قرارداد', defaultextension=extension, filetypes=[('Excel', '*.xlsx')] if actual_format == 'xlsx' else [('PDF', '*.pdf')])
        if not path:
            return False
        export_specs = [*specs, ('خلاصه', 'جهت ارائه به', addressee)]
        export_payload = [dict(row) for row in payload]
        export_document_paths = list(document_paths or []) if include_documents else []
        export_contract_document_paths = list(contract_document_paths or []) if include_documents else []
        if not include_documents:
            for row in export_payload:
                for header in ('فیش واریزی', 'نمایش سند'):
                    if header in row:
                        row[header] = '-'
                row.pop('__document_paths_187', None)
        try:
            destination = Path(path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if actual_format == 'xlsx':
                from openpyxl import Workbook
                book = Workbook(); sheet = book.active; sheet.title = 'مشخصات قرارداد'
                apply_export_workbook_header_187(sheet, headers=headers, specs=export_specs, output_title='خروجی جزئیات قرارداد')
                sheet.append(('کادر ویزارد', 'عنوان', 'مقدار'))
                for group, label, value in getattr(self, '_wizard_export_fields', []):
                    sheet.append((group, label, value))
                sheet.append(())
                sheet.append(('جدول پرداخت‌ها',))
                sheet.append(headers)
                for row in export_payload:
                    sheet.append([row.get(header, '') for header in headers])
                    document_path = str(row.get('نمایش سند') or '') if include_documents else ''
                    if document_path and Path(document_path).exists() and Path(document_path).suffix.lower() in {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}:
                        try:
                            from openpyxl.drawing.image import Image as ExcelImage
                            image = ExcelImage(document_path); image.width, image.height = 160, 110
                            image.anchor = f'{chr(65 + max(0, len(headers) - 1))}{sheet.max_row}'
                            sheet.add_image(image)
                        except (OSError, ImportError, ValueError):
                            pass
                style_xlsx_workbook(book)
                apply_export_workbook_header_187(sheet, headers=headers, specs=export_specs, output_title='خروجی جزئیات قرارداد', add_logo=False)
                book.save(destination)
            else:
                summary = [f'{group} — {label}: {value}' for group, label, value in export_specs]
                export_receipts_pdf_187(destination, headers, [[row.get(header, '') for header in headers] for row in export_payload],
                                        'خروجی جزئیات قرارداد', summary, export_document_paths, orientation=orientation,
                                        contract_document_paths=export_contract_document_paths)
                if export_format == 'print' and hasattr(os, 'startfile'):
                    os.startfile(str(destination), 'print')
        except Exception as exc:
            messagebox.showerror('خروجی', str(exc), parent=self)
            return False
        messagebox.showinfo('خروجی', 'خروجی جزئیات قرارداد آماده شد.', parent=self)
        return True


class SalesClaimsPanel187(ttk.Frame):
    """Right-to-left contracts and finance workspace backed by the existing ledger."""
    def __init__(self, parent, *, db, base_dir, on_changed=None):
        super().__init__(parent, padding=6)
        self.db, self.base_dir, self.on_changed = db, Path(base_dir), on_changed
        self.revenue = RevenueService(db)
        self.attachments = AttachmentService(db, self.base_dir)
        self.selected_sale_id = ''
        self.nb = ttk.Notebook(self); self.nb.pack(fill='both', expand=True)
        self.contracts = ttk.Frame(self.nb, padding=5); self.finance = ttk.Frame(self.nb, padding=5)
        self.nb.add(self.contracts, text='قراردادها'); self.nb.add(self.finance, text='مالی')
        style = ttk.Style(self)
        p = kit_palette()
        style.configure('SalesClaims.Treeview', background=p['row_card_even'], fieldbackground=p['row_card_even'],
                        foreground=p['text_primary'], borderwidth=0, relief='flat',
                        rowheight=kit_metrics()['row_height'])
        style.configure('SalesClaims.Treeview.Heading', background=p['heading'],
                        foreground=p['text_primary'], borderwidth=0, relief='flat')
        style.configure('SalesClaims.Summary.TLabel', background=p['panel2'], foreground=p['text_primary'])
        # Section 3: sales used to draw its own rounded canvas tabs with their
        # own sizing and a green active label, which made this the one tab
        # strip in the product that did not match the others.
        self._rtl_tabs = TabStrip(self.nb, level=1)
        self._build_contracts(); self._build_finance(); self.refresh()
        # The inherited global currency pass treats words such as «قرارداد» and
        # «فروش» as monetary.  Keep these three sales-table headings semantic.
        self.after(80, self._restore_contract_non_money_headings)
        self._price_refresh_job = self.after(60000, self._auto_refresh_prices)

    def _toolbar(self, parent, actions):
        bar = ttk.Frame(parent); bar.pack(fill='x', pady=(0, 5))
        for icon, title, command in actions:
            ttk.Button(bar, text=f'{icon} {title}', command=command).pack(side='right', padx=2)
        return bar

    def _tree(self, parent, columns):
        table_area = ttk.Frame(parent, style='Card.TFrame', padding=5)
        table_area.pack(fill='both', expand=True)
        tree = ttk.Treeview(table_area, columns=tuple(key for key, _label, _width in columns), show='headings', selectmode='extended', style='SalesClaims.Treeview')
        # The active 18.7 card-table contract never receives the inherited
        # ruled-grid overlay, including during later refreshes.
        tree._barkav_line_free_187 = True
        for key, label, width in columns:
            tree.heading(key, text=label, anchor='e'); tree.column(key, width=width, anchor='e', stretch=False)
            if key == 'select':
                tree.heading(key, text='انتخاب ☐', command=lambda target=tree: self._toggle_all_checkboxes(target))
        apply_tree_rtl(tree)
        xscroll = ttk.Scrollbar(table_area, orient='horizontal', command=tree.xview)
        yscroll = ttk.Scrollbar(table_area, orient='vertical', command=tree.yview)
        tree.configure(xscrollcommand=xscroll.set, yscrollcommand=yscroll.set)
        tree._barkav_xscroll187 = xscroll
        tree._barkav_yscroll187 = yscroll
        table_area.rowconfigure(0, weight=1)
        table_area.columnconfigure(1, weight=1)
        yscroll.grid(row=0, column=0, sticky='ns', padx=(0, 3))
        tree.grid(row=0, column=1, sticky='nsew')
        xscroll.grid(row=1, column=1, sticky='ew', pady=(3, 0))
        return tree

    def _install_row_checkbox(self, tree):
        tree.bind('<Button-1>', lambda event: self._toggle_row_checkbox(event, tree), add='+')

    def _toggle_row_checkbox(self, event, tree):
        """Toggle the visible row checkbox while retaining normal Treeview selection."""
        iid = tree.identify_row(event.y)
        if tree.identify_region(event.x, event.y) != 'cell' or not iid:
            return
        visible_columns = tuple(tree['displaycolumns'] or tree['columns'])
        column_id = tree.identify_column(event.x)
        try:
            visible_key = visible_columns[int(column_id[1:]) - 1]
        except (ValueError, IndexError):
            return
        if visible_key != 'select':
            return
        values = list(tree.item(iid, 'values'))
        column_index = list(tree['columns']).index('select')
        checked = not str(values[column_index]).startswith('☑')
        values[column_index] = selection_cell_187(checked)
        tree.item(iid, values=values)
        # The dedicated checkbox is the explicit multi-selection control.
        # Do not replace earlier checked rows while the user ticks another one.
        if checked:
            tree.selection_add(iid)
        else:
            tree.selection_remove(iid)
        tree.focus(iid)
        tree.see(iid)
        return 'break'

    def _toggle_all_checkboxes(self, tree):
        """Toggle every visible row from the dedicated selection-column header."""
        item_ids = list(tree.get_children())
        if not item_ids:
            return
        column_index = list(tree['columns']).index('select')
        checked = not all(str(tree.item(iid, 'values')[column_index]).startswith('☑') for iid in item_ids)
        for iid in item_ids:
            values = list(tree.item(iid, 'values')); values[column_index] = selection_cell_187(checked)
            tree.item(iid, values=values)
        if checked:
            tree.selection_set(item_ids)
        else:
            tree.selection_remove(item_ids)
        tree.heading('select', text=f"انتخاب {'☑' if checked else '☐'}")

    def _checked_or_selected_rows(self, tree):
        """Return every checked row, falling back to normal Treeview selection."""
        try:
            select_index = list(tree['columns']).index('select')
            checked = [iid for iid in tree.get_children()
                       if str(tree.item(iid, 'values')[select_index]).startswith('☑')]
        except (ValueError, IndexError, tk.TclError):
            checked = []
        return checked or list(tree.selection())

    def _export_tree(self, tree, title: str, export_format: str | None = None):
        """Export selected rows, or the visible table when none is selected, without mutation."""
        item_ids = tree.selection() or tree.get_children()
        # The kit's tick column draws the selection and holds no value.
        headers = [str(tree.heading(key, 'text')) for key in tree['columns'] if key != CHECK_COLUMN]
        rows = [tuple(tree.item(iid, 'values')) for iid in item_ids]
        payload = finance_export_rows_187(headers, rows) if tree is getattr(self, 'finance_tree', None) else visible_rows_payload_187(headers, rows)
        if not payload:
            messagebox.showinfo('خروجی', 'داده‌ای برای خروجی وجود ندارد.', parent=self)
            return
        formats = {'json': ('JSON', '.json', [('JSON', '*.json')]),
                   'csv': ('CSV', '.csv', [('CSV', '*.csv')]),
                   'txt': ('TXT', '.txt', [('Text', '*.txt')]),
                   'xlsx': ('Excel', '.xlsx', [('Excel', '*.xlsx')]),
                   'pdf': ('PDF', '.pdf', [('PDF', '*.pdf')]),
                   'print': ('پرینت', '.pdf', [('PDF', '*.pdf')])}
        selected = formats.get(str(export_format or '').lower())
        path = filedialog.asksaveasfilename(
            parent=self, title=f'خروجی {selected[0] if selected else "JSON/CSV/TXT"} {title}',
            defaultextension=selected[1] if selected else '.json',
            filetypes=selected[2] if selected else [item[2][0] for item in formats.values()],
        )
        if not path:
            return
        destination = Path(path)
        try:
            suffix = selected[1] if selected else destination.suffix.lower()
            if suffix == '.xlsx':
                from openpyxl import Workbook
                book = Workbook(); sheet = book.active
                apply_export_workbook_header_187(sheet, headers=headers, specs=(), output_title=f'خروجی {title}')
                sheet.append(headers)
                for row in payload: sheet.append([row.get(header, '') for header in headers])
                style_xlsx_workbook(book)
                apply_export_workbook_header_187(sheet, headers=headers, specs=(), output_title=f'خروجی {title}', add_logo=False)
                book.save(destination)
            elif suffix == '.pdf':
                export_contract_pdf_187(destination, headers, payload, f'خروجی {title}')
                if export_format == 'print' and hasattr(os, 'startfile'):
                    os.startfile(str(destination), 'print')
            elif suffix == '.csv':
                with destination.open('w', encoding='utf-8-sig', newline='') as handle:
                    writer = csv.DictWriter(handle, fieldnames=headers)
                    writer.writeheader(); writer.writerows(payload)
            elif suffix == '.txt':
                with destination.open('w', encoding='utf-8') as handle:
                    handle.write('\n'.join('\t'.join(row.get(header, '') for header in headers) for row in payload))
            else:
                destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        except OSError as exc:
            messagebox.showerror('خروجی', str(exc), parent=self)
            return
        messagebox.showinfo('خروجی', f'فقط دادهٔ نمایش‌داده‌شده صادر شد:\n{destination.name}', parent=self)

    def _export_contract_selected(self, _event=None):
        export_label = {'Excel': 'Excel', 'PDF': 'PDF', 'پرینت': 'پرینت'}.get(self.contract_export_choice.get())
        if not export_label:
            return
        selected = list(self.contract_tree.selection())
        if not selected:
            return messagebox.showwarning('خروجی قرارداد', 'ابتدا یک قرارداد را انتخاب کنید.', parent=self)
        if len(selected) > 1:
            columns = [key for key in self.contract_tree['columns'] if key != CHECK_COLUMN]
            headers = [self.contract_tree.heading(key, 'text') for key in columns]
            indexes = [list(self.contract_tree['columns']).index(key) for key in columns]
            selected_set = set(selected)
            rows = [[self.contract_tree.item(iid, 'values')[index] for index in indexes]
                    for iid in self.contract_tree.get_children() if iid in selected_set]
            self.contract_export_choice.set(EXPORT_PLACEHOLDER_187)
            return show_export_preview_187(
                self, export_format=export_label, headers=headers, rows=rows,
                title='پیش‌نمایش قراردادهای فروش', include_addressee=True,
                on_confirm=lambda *_args: False,
            )
        # The main-tab selector opens the relevant contract only.  The actual
        # format is selected inside that window, where its populated preview
        # can be reviewed before Save As is opened.
        details = ContractDetails187(
            self.winfo_toplevel(), db=self.db, base_dir=self.base_dir,
            sale_id=str(selected[0]),
        )
        details.export_choice.set(export_label)
        details._export_selected()
        self.contract_export_choice.set(EXPORT_PLACEHOLDER_187)

    def _build_contracts(self):
        # Item 2: actions, filter and export share one row.  They used to be
        # three stacked strips, which read as three unrelated toolbars.
        row = ttk.Frame(self.contracts, style='Card.TFrame', padding=4)
        row.pack(fill='x', pady=(0, 5))
        for glyph, label, command in (
            # «افزودن», as every tab names its create action (operator round
            # 2026-09-27); the wizard it opens is still «ثبت قرارداد فروش».
            ('➕', 'افزودن', self.open_wizard),
            ('✏️', 'ویرایش', self.open_edit_wizard),
        ):
            # Words alone, the create action in the create colour - the
            # shared toolbar's look (operator round 2026-09-27); the glyph
            # stays with the context menu's entries.
            ttk.Button(row, text=label, command=command,
                       style='Success.TButton' if glyph == '➕' else 'Toolbar.TButton',
                       ).pack(side='right', padx=3)

        # The filter sits beside the actions on the right; the export controls
        # move to the far left, away from the row's busy end.
        self.contract_search_kind = tk.StringVar(value='همه'); self.contract_search_value = tk.StringVar(value='همه')
        ttk.Label(row, text='نمایش بر اساس:', style='Caption.TLabel').pack(
            side='right', padx=(10, 2))
        kind = ttk.Combobox(row, textvariable=self.contract_search_kind, values=('همه', 'نام خریدار', 'شماره واحد', 'شماره قرارداد'), state='readonly', justify='right', width=16)
        kind.pack(side='right', padx=3); kind.bind('<<ComboboxSelected>>', lambda _e: self._refresh_contract_search_values())
        self.contract_search_combo = ttk.Combobox(row, textvariable=self.contract_search_value, state='readonly', justify='right', width=22)
        self.contract_search_combo.pack(side='right', padx=3); self.contract_search_combo.bind('<<ComboboxSelected>>', lambda _e: self.refresh())

        self.contract_export_choice = tk.StringVar(value=EXPORT_PLACEHOLDER_187)
        contract_export_combo = ttk.Combobox(row, textvariable=self.contract_export_choice, values=(EXPORT_PLACEHOLDER_187, 'PDF', 'Excel', 'پرینت'), state='readonly', justify='right', width=16)
        contract_export_combo.pack(side='left', padx=3)
        contract_export_combo.bind('<<ComboboxSelected>>', self._export_contract_selected)
        self._refresh_contract_search_values()
        self.contract_tree = self._tree(self.contracts, CONTRACT_TABLE_COLUMNS_187)
        self.contract_tree._barkav_non_currency_columns_186 = CONTRACT_NON_MONEY_COLUMNS_187
        self._install_row_checkbox(self.contract_tree)
        self.contract_tree.bind('<<TreeviewSelect>>', lambda _e: self._select_contract())
        self.contract_tree.bind('<Button-3>', lambda e: self._context(e, self.contract_tree))
        self.contract_tree.bind('<Double-1>', lambda _e: self._open_contract_details())

    def _restore_contract_non_money_headings(self):
        """Undo inherited currency decoration on non-monetary contract headings."""
        try:
            labels = {key: label for key, label, _width in CONTRACT_TABLE_COLUMNS_187}
            for key in CONTRACT_NON_MONEY_COLUMNS_187:
                self.contract_tree.heading(key, text=labels[key])
        except tk.TclError:
            return

    def _build_finance(self):
        controls = ttk.Frame(self.finance, style='Card.TFrame', padding=4)
        controls.pack(fill='x', pady=(0, 5))
        self.finance_controls187 = controls
        for column in (0, 2):
            controls.columnconfigure(column, weight=1, uniform='finance_sides')
        controls.columnconfigure(1, weight=0)

        actions = ttk.Frame(controls, style='Card.TFrame')
        actions.grid(row=0, column=2, sticky='e')
        self.finance_actions187 = actions
        for glyph, label, command in (
            ('➕', 'اضافه', self._finance_add),
            ('✏️', 'ویرایش', self._finance_edit),
            ('🗑', 'حذف', self._finance_delete),
        ):
            # Words alone, like every tab's toolbar (2026-09-27).
            ttk.Button(actions, text=label, command=command,
                       style='Toolbar.TButton').pack(side='right', padx=2)

        filters = ttk.Frame(controls, style='Card.TFrame')
        filters.grid(row=0, column=1)
        self.finance_filters187 = filters
        self.finance_search_kind = tk.StringVar(value='همه')
        self.finance_search_value = tk.StringVar(value='همه')
        ttk.Label(filters, text='نمایش بر اساس', style='Caption.TLabel').pack(
            side='right', padx=3)
        kind = ttk.Combobox(
            filters, textvariable=self.finance_search_kind,
            values=('همه', 'نام خریدار', 'شماره واحد', 'شماره قرارداد'),
            state='readonly', justify='right', width=14,
        )
        kind.pack(side='right', padx=3)
        kind.bind('<<ComboboxSelected>>', lambda _e: self._refresh_finance_search_values())
        self.finance_search_combo = ttk.Combobox(
            filters, textvariable=self.finance_search_value,
            state='readonly', justify='right', width=20,
        )
        self.finance_search_combo.pack(side='right', padx=3)
        self.finance_search_combo.bind(
            '<<ComboboxSelected>>', lambda _e: self._select_finance_search())

        output = ttk.Frame(controls, style='Card.TFrame')
        output.grid(row=0, column=0, sticky='w')
        self.finance_output187 = output
        self.finance_export_choice = tk.StringVar(value=EXPORT_PLACEHOLDER_187)
        finance_export_combo = ttk.Combobox(
            output, textvariable=self.finance_export_choice,
            values=(EXPORT_PLACEHOLDER_187, 'PDF', 'Excel', 'پرینت'),
            state='readonly', justify='right', width=16,
        )
        finance_export_combo.pack(side='right', padx=3)
        finance_export_combo.bind(
            '<<ComboboxSelected>>', self._export_finance_selected)

        self.finance_summary = tk.StringVar(value='قراردادی انتخاب نشده است')
        summary_card = ttk.Frame(self.finance, padding=5)
        summary_card.pack(fill='x', padx=5, pady=5)
        ttk.Label(
            summary_card, textvariable=self.finance_summary,
            anchor='e', justify='right', style='SalesClaims.Summary.TLabel',
        ).pack(fill='x')
        self._refresh_finance_search_values()
        self.finance_tree = self._tree(self.finance, [('row', 'ردیف', 80), ('stage', 'مرحله پرداخت', 130), ('due', 'تاریخ پرداخت', 110), ('amount', 'مبلغ پرداخت (تومان)', 150), ('late', 'دیرکرد (روز)', 100), ('paid', 'کل مبلغ واریزی مرحله (تومان)', 180), ('balance', 'بدهکار/بستانکار تا این مرحله (تومان)', 180), ('final', 'بدهکار تا پایان قرارداد (تومان)', 180), ('document', 'نمایش سند', 110), ('select', 'انتخاب', 75)])
        self.finance_tree._barkav_non_currency_columns_186 = ('row', 'stage', 'due', 'late', 'document')
        self.finance_tree.heading('row', text='ردیف', anchor='e')
        # Keep non-monetary finance headings free of the money unit even if a
        # shared tree/theme layer supplies legacy heading text.
        self.finance_tree.heading('stage', text='مرحله پرداخت', anchor='e')
        self.finance_tree.heading('due', text='تاریخ پرداخت', anchor='e')
        self._install_row_checkbox(self.finance_tree)
        self.finance_tree.bind('<Double-1>', self._double_click_finance_payment)
        self.finance_tree.bind('<Button-1>', self._finance_document_click, add='+')
        self.finance_tree.bind('<Button-3>', lambda e: self._context(e, self.finance_tree))
    def _export_finance_selected(self, _event=None):
        export_label = {'Excel': 'Excel', 'PDF': 'PDF', 'پرینت': 'پرینت'}.get(self.finance_export_choice.get())
        if not export_label:
            return
        # Reuse the receipt viewer's populated rows and open the shared preview
        # in the format already selected on the finance toolbar.
        documents = self._open_selected_documents()
        self.finance_export_choice.set(EXPORT_PLACEHOLDER_187)
        if isinstance(documents, PaymentDocuments187):
            documents.export_choice.set(export_label)
            documents._export_selected()

    def _save_finance_export(self, choice, headers, payload, item_ids):
        export_format = {'Excel': 'xlsx', 'PDF': 'pdf', 'پرینت': 'print'}.get(choice, 'pdf')
        actual_format = 'pdf' if export_format == 'print' else export_format
        path = filedialog.asksaveasfilename(parent=self, title=f'خروجی {actual_format.upper()} مالی',
                                            defaultextension=f'.{actual_format}',
                                            filetypes=[('Excel', '*.xlsx')] if actual_format == 'xlsx' else [('PDF', '*.pdf')])
        if not path:
            return
        destination = Path(path)
        try:
            if actual_format == 'xlsx':
                from openpyxl import Workbook
                book = Workbook(); sheet = book.active
                apply_export_workbook_header_187(sheet, headers=headers, specs=(), output_title='خروجی مالی')
                sheet.append(headers)
                for row in payload: sheet.append([row.get(header, '') for header in headers])
                style_xlsx_workbook(book)
                apply_export_workbook_header_187(sheet, headers=headers, specs=(), output_title='خروجی مالی', add_logo=False)
                book.save(destination)
            else:
                documents = self._finance_export_documents(item_ids)
                export_receipts_pdf_187(destination, headers, [[row.get(header, '') for header in headers] for row in payload],
                                        'خروجی مالی', [], documents)
                if export_format == 'print' and hasattr(os, 'startfile'):
                    os.startfile(str(destination), 'print')
        except (OSError, ImportError) as exc:
            return messagebox.showerror('خروجی مالی', str(exc), parent=self)
        messagebox.showinfo('خروجی مالی', 'خروجی آماده شد.', parent=self)

    def _finance_export_documents(self, installment_ids):
        paths, seen = [], set()
        for installment_id in installment_ids:
            receipt = self._finance_receipt_context(str(installment_id))
            if not receipt:
                continue
            entities = [('RECEIVED_PAYMENT', str(receipt.get('received_payment_id') or '')),
                        ('SALE_PAYMENT', str(receipt.get('received_payment_id') or '')),
                        ('TRANSACTION', str(receipt.get('transaction_id') or ''))]
            for document in self.attachments.list_for_entities(entities):
                path = str(document.get('local_path') or '')
                if path and path not in seen:
                    paths.append(path); seen.add(path)
        return paths

    def _finance_document_click(self, event):
        """Open the selected row's receipts when the leftmost document cell is clicked."""
        iid = self.finance_tree.identify_row(event.y)
        if not iid or self.finance_tree.identify_region(event.x, event.y) != 'cell':
            return
        visible = tuple(self.finance_tree['displaycolumns'] or self.finance_tree['columns'])
        try:
            key = visible[int(self.finance_tree.identify_column(event.x)[1:]) - 1]
        except (ValueError, IndexError):
            return
        if key != 'document':
            return
        self.finance_tree.selection_set(iid); self.finance_tree.focus(iid)
        self._open_selected_documents()
        return 'break'

    def open_wizard(self, initial: dict[str, Any] | None = None, document_path: str = '', sale_id: str = ''):
        ContractWizard187(self.winfo_toplevel(), db=self.db, base_dir=self.base_dir, on_saved=self._changed,
                          record_opener=self.open_sales_record, initial=initial, document_path=document_path, sale_id=sale_id)

    def open_edit_wizard(self):
        if not self.selected_sale_id:
            return messagebox.showwarning('ویرایش قرارداد', 'ابتدا یک قرارداد را انتخاب کنید.', parent=self)
        row = self.revenue.get_sale(self.selected_sale_id) or {}
        metadata = self._meta(row)
        initial = {
            **metadata,
            'project_name': metadata.get('project_name') or row.get('project_name'),
            'block_name': metadata.get('block_name') or row.get('block_name'),
            'unit_number': metadata.get('unit_number') or row.get('unit_number'),
            'floor': metadata.get('floor') or row.get('floor'),
            'map_area': metadata.get('map_area') or row.get('area'),
            'contract_area': metadata.get('contract_area') or row.get('area'),
            'contract_number': metadata.get('contract_number') or row.get('contract_number'),
            'contract_date': metadata.get('contract_date') or row.get('contract_date_shamsi'),
            'buyer_name': metadata.get('buyer_name') or row.get('buyer_name'),
            'buyer_phone': metadata.get('buyer_phone') or row.get('buyer_phone'),
            'total_price': metadata.get('total_price') or row.get('contract_amount'),
        }
        documents = self.attachments.list_for_entities([('SALE', self.selected_sale_id)])
        document_path = str((documents[0] if documents else {}).get('local_path') or '')
        self.open_wizard(initial=initial, document_path=document_path, sale_id=self.selected_sale_id)

    def open_sales_record(self, sale_id: str = '', draft: dict[str, Any] | None = None, document_path: str = ''):
        # A new wizard draft must never inherit the previously selected sale.
        # Keep the selected-sale fallback only for opening an existing record.
        sale_id = str(sale_id or (self.selected_sale_id if draft is None else '') or '')
        SalesRecord187(self.winfo_toplevel(), db=self.db, base_dir=self.base_dir, sale_id=sale_id,
                       draft=draft, document_path=document_path, on_saved=self._changed)

    def _auto_refresh_prices(self):
        """The table price is derived from the ledger on every refresh; no price is posted."""
        try:
            if self.winfo_exists():
                self.refresh(); self._price_refresh_job = self.after(60000, self._auto_refresh_prices)
        except tk.TclError:
            pass

    def _refresh_contract_search_values(self):
        kind = getattr(self, 'contract_search_kind', tk.StringVar(value='همه')).get()
        if kind == 'همه':
            self.contract_search_value.set('همه'); self.contract_search_combo.configure(values=('همه',)); return
        key = {'نام خریدار': 'buyer_name', 'شماره واحد': 'unit_number', 'شماره قرارداد': 'contract_number'}[kind]
        values = sorted({str(row.get(key) or '') for row in self.revenue.list_sales(active_only=True, limit=500) if row.get(key)})
        self.contract_search_combo.configure(values=('همه', *values)); self.contract_search_value.set('همه')

    def _refresh_finance_search_values(self):
        kind = self.finance_search_kind.get()
        if kind == 'همه':
            values = ()
        else:
            key = {'نام خریدار': 'buyer_name', 'شماره واحد': 'unit_number', 'شماره قرارداد': 'contract_number'}[kind]
            values = sorted({str(row.get(key) or '') for row in self.revenue.list_sales(active_only=True, limit=500) if row.get(key)})
        self.finance_search_combo.configure(values=('همه', *values))
        self.finance_search_value.set('همه')
        # Changing the first filter means «همه» in the second filter is a real
        # request for all rows, not a reason to retain the previous contract.
        self.selected_sale_id = ''
        if hasattr(self, 'finance_tree'):
            self.contract_tree.selection_remove(*self.contract_tree.selection())
            self._select_finance_search()

    def _select_finance_search(self):
        kind, value = self.finance_search_kind.get(), self.finance_search_value.get()
        if kind == 'همه' or value == 'همه':
            self.selected_sale_id = ''
            self.contract_tree.selection_remove(*self.contract_tree.selection())
            self._refresh_finance()
            return
        key = {'نام خریدار': 'buyer_name', 'شماره واحد': 'unit_number', 'شماره قرارداد': 'contract_number'}[kind]
        match = next((row for row in self.revenue.list_sales(active_only=True, limit=500) if str(row.get(key) or '') == value), None)
        if not match:
            return
        self.selected_sale_id = str(match['sale_id'])
        if self.contract_tree.exists(self.selected_sale_id):
            self.contract_tree.selection_set(self.selected_sale_id)
        self._select_contract()

    def refresh(self):
        previous = self.selected_sale_id
        for iid in self.contract_tree.get_children(): self.contract_tree.delete(iid)
        rows = filter_contract_rows_187(self.revenue.list_sales(active_only=True, limit=500), self.contract_search_kind.get(), self.contract_search_value.get())
        for number, row in enumerate(rows, 1):
            detail = self.revenue.sale_summary(row['sale_id']); meta = self._meta(row)
            self.contract_tree.insert(
                '', 'end', iid=row['sale_id'],
                values=contract_table_values_187(number, row, meta, detail),
                tags=('even' if number % 2 else 'odd',),
            )
        self._restore_contract_non_money_headings()
        if previous and self.contract_tree.exists(previous):
            self.contract_tree.selection_set(previous); self._select_contract()
        else:
            self._refresh_finance()

    def _meta(self, row):
        try: return json.loads(str(row.get('notes') or '{}'))
        except (TypeError, ValueError, json.JSONDecodeError): return {}

    def _select_contract(self, open_docs=False):
        selected = self.contract_tree.selection()
        if not selected: return
        self.selected_sale_id = selected[0]
        row = self.revenue.get_sale(self.selected_sale_id) or {}; detail = self.revenue.sale_summary(self.selected_sale_id)
        self.finance_summary.set(f"قرارداد {row.get('contract_number') or '-'} | مبلغ کل: {toman(row.get('contract_amount'))} تومان | کل پرداختی: {toman(detail.cash_received)} تومان | معوق: {toman(detail.overdue_amount)} تومان | مانده: {toman(detail.receivable)} تومان")
        self._refresh_finance()

    def _open_contract_details(self):
        selected = self.contract_tree.selection()
        if not selected:
            return
        self.selected_sale_id = selected[0]
        ContractDetails187(self.winfo_toplevel(), db=self.db, base_dir=self.base_dir, sale_id=self.selected_sale_id)

    def _refresh_finance(self):
        for iid in self.finance_tree.get_children(): self.finance_tree.delete(iid)
        sales = finance_sales_for_filter_187(
            self.revenue.list_sales(active_only=True, limit=500),
            self.finance_search_kind.get(),
            self.finance_search_value.get(),
            self.selected_sale_id,
        )
        if not sales:
            self.finance_summary.set('ردیف مالی مطابق جستجو پیدا نشد')
            return
        if not self.selected_sale_id:
            self.finance_summary.set(f'نمایش همه ردیف‌های مالی | {fa(len(sales))} قرارداد')
        today = date.today()
        row_number = 0
        for sale in sales:
            installments = self.revenue.list_installments(str(sale['sale_id']))
            running = 0
            total = sum(int(item.get('amount') or 0) for item in installments)
            for local_number, item in enumerate(installments, 1):
                row_number += 1
                amount, paid = int(item.get('amount') or 0), int(item.get('paid_amount') or 0)
                running += max(0, amount - paid)
                try: late = max(0, (today - date.fromisoformat(str(item.get('due_date')))).days) if paid < amount else 0
                except ValueError: late = 0
                stage = item.get('description') or f'قسط {local_number}'
                if len(sales) > 1:
                    identity = sale.get('buyer_name') or sale.get('contract_number') or sale.get('unit_number') or '-'
                    stage = f'{stage} — {identity}'
                self.finance_tree.insert(
                    '', 'end', iid=item['installment_id'],
                    values=(fa(row_number), stage, persian_digits_187(item.get('due_date_shamsi') or '-'), toman(amount), fa(late), toman(paid), f'بدهکار: {toman(max(0, running))}', toman(max(0, total - sum(int(x.get('paid_amount') or 0) for x in installments[:local_number]))), 'نمایش سند', selection_cell_187()),
                    tags=('even' if row_number % 2 else 'odd',),
                )

    def _context(self, event, tree):
        iid = tree.identify_row(event.y)
        if iid:
            if iid not in tree.selection(): tree.selection_set(iid)
            tree.focus(iid)
        menu = tk.Menu(self, tearoff=0)
        if tree is self.finance_tree:
            menu.add_command(label='➕ اضافه', command=self._finance_add)
            menu.add_command(label='✏️ ویرایش', command=self._finance_edit)
            menu.add_command(label='🗑 حذف', command=self._finance_delete)
        else:
            menu.add_command(label='➕ ثبت قرارداد', command=self.open_wizard)
            menu.add_command(label='✏️ ویرایش', command=self._edit_hint)
            menu.add_command(label='🗑 لغو/حذف', command=self._cancel)
            menu.add_separator(); menu.add_command(label='📋 کپی', command=self._copy)
            menu.add_command(label='📥 پیست', command=lambda: messagebox.showinfo('پیست', 'پیست فقط برای فیلترهای متنی فعال است.', parent=self))
        try: menu.tk_popup(event.x_root, event.y_root)
        finally: menu.grab_release()

    def _copy(self):
        tree = self.contract_tree if self.nb.index(self.nb.select()) == 0 else self.finance_tree
        lines = ['\t'.join(map(str, tree.item(iid, 'values'))) for iid in tree.selection()]
        if lines: self.clipboard_clear(); self.clipboard_append('\n'.join(lines))

    def _edit_hint(self):
        self.open_edit_wizard()

    def _cancel(self):
        from table_actions import select_delete_rows
        selected = self._checked_or_selected_rows(self.contract_tree)
        if not selected: return
        with self.revenue.db.read() as con:
            count=sum(con.execute("SELECT COUNT(*) FROM received_payments WHERE sale_id=? AND status!='CANCELLED'",(sale_id,)).fetchone()[0] for sale_id in selected)
        selected = select_delete_rows(self, selected, messagebox=messagebox,
            detail=f'{count} رسید واریزی مرتبط به ردشده‌ها منتقل می‌شوند و اثرشان برداشته می‌شود.')
        if not selected: return
        from contract_deletion import delete_sale
        from transaction_lifecycle import TransactionLifecycle
        import row_journal
        try:
            with row_journal.suspended(), self.revenue.db.atomic():
                for sale_id in selected: delete_sale(self.revenue.db,sale_id)
        except (ValueError,KeyError) as exc:
            TransactionLifecycle(self.revenue.db).flag_decision('SALE:'+sale_id,'DELETE',exc)
            messagebox.showerror('تعیین تکلیف',str(exc),parent=self);return
        self.selected_sale_id = ''; self._changed()

    def _open_document(self):
        selected = self.doc_tree.selection()
        if not selected: return
        try: self.attachments.open(str(self.doc_tree.item(selected[0], 'values')[-1]))
        except Exception as exc: messagebox.showerror('اسناد', str(exc), parent=self)

    def _document_delete_hint(self):
        messagebox.showinfo('اسناد', 'حذف سند از این صفحه انجام نمی‌شود تا سابقهٔ مالی و پیوست‌ها حفظ شود.', parent=self)

    def _finance_delete_hint(self):
        messagebox.showinfo('مالی', 'ابطال واریزی فقط از مسیر بازبینی حسابرسی در تب ثبت تراکنش انجام می‌شود.', parent=self)

    def _finance_add(self):
        self._create_finance_pending('ADD')

    def _finance_delete(self):
        """Delete the selected receipts through the original posting lifecycle."""
        rows = self._selected_finance_receipts_187(all_receipts=True)
        if not rows: return
        remove = getattr(self.winfo_toplevel(), '_delete_lifecycle_rows187', None)
        if not callable(remove):
            return messagebox.showwarning('عملیات مالی', 'مسیر حذف مالی در دسترس نیست.', parent=self)
        remove(rows)
        self._changed()

    def _create_finance_pending(self, action):
        dashboard = self.winfo_toplevel(); center = getattr(dashboard, 'approval_center', None)
        if center is None or not callable(getattr(center, 'open_wizard', None)):
            return messagebox.showwarning('عملیات مالی', 'پنجره ثبت دیتا در دسترس نیست.', parent=self)
        if not self.selected_sale_id:
            return messagebox.showwarning('عملیات مالی', 'ابتدا قرارداد را انتخاب کنید.', parent=self)
        sale = self.revenue.get_sale(self.selected_sale_id) or {}
        selected = self.finance_tree.selection()
        installment = self.revenue.get_installment(str(selected[0])) if selected else None
        receipt = self._finance_receipt_context(str(selected[0])) if selected else {}
        if action == 'EDIT' and not receipt:
            return messagebox.showinfo('ویرایش مالی', 'برای این مرحله پرداخت ثبت‌شده‌ای وجود ندارد.', parent=self)
        now_id = int(datetime.now().timestamp() * 1_000_000)
        payload = sales_finance_pending_payload_187(action=action, sale={**sale, 'sale_id': self.selected_sale_id},
                                                     installment=installment, receipt=receipt)
        try:
            self.db.register_telegram_message(chat_id=-187, message_id=now_id, raw_text='', content_type='sales_finance',
                                              message_date=sales_finance_pending_message_date_187(payload), state='RECEIVED')
            pending_id = self.db.create_or_replace_pending(telegram_chat_id=-187, telegram_message_id=now_id,
                                                            detected_type='TRANSACTION', payload=payload, confidence=1.0,
                                                            status='PENDING_REVIEW')
            center.refresh()
            row = next((item for item in getattr(center, 'rows', []) if str(item.get('pending_id')) == str(pending_id)), None)
            if row:
                notebook = getattr(dashboard, 'notebook', None); approval_tab = getattr(dashboard, 'approval_tab', None)
                if notebook is not None and approval_tab is not None: notebook.select(approval_tab)
                center.open_wizard(row)
        except Exception as exc:
            messagebox.showerror('عملیات مالی', str(exc), parent=self)

    def _finance_edit(self):
        """Edit the receipt's own Data Entry record, retaining its identity."""
        rows = self._selected_finance_receipts_187()
        if not rows: return
        edit = getattr(self.winfo_toplevel(), 'edit_transaction_row', None)
        if not callable(edit):
            return messagebox.showwarning('عملیات مالی', 'مسیر ویرایش مالی در دسترس نیست.', parent=self)
        return edit(rows[0])

    def _selected_finance_receipts_187(self, *, all_receipts=False):
        selected = self._checked_or_selected_rows(self.finance_tree)
        if not all_receipts: selected = selected[:1]
        if not selected:
            messagebox.showinfo('عملیات مالی', 'ابتدا یک ردیف را انتخاب کنید.', parent=self)
            return []
        rows, seen = [], set()
        with self.db.read() as con:
            for installment_id in selected:
                receipts = con.execute(
                    """SELECT DISTINCT r.received_payment_id, r.transaction_id, r.amount,
                              r.received_date_shamsi, r.sale_id
                       FROM payment_allocations a
                       JOIN received_payments r ON r.received_payment_id=a.received_payment_id
                       WHERE a.installment_id=? AND r.status!='CANCELLED'
                       ORDER BY r.received_date_shamsi DESC, r.received_payment_id DESC""",
                    (str(installment_id),)).fetchall()
                if not receipts:
                    messagebox.showinfo('عملیات مالی', 'برای یکی از مرحله‌های انتخاب‌شده پرداخت ثبت‌شده‌ای وجود ندارد؛ هیچ ردیفی تغییر نکرد.', parent=self)
                    return []
                for receipt in receipts if all_receipts else receipts[:1]:
                    if receipt['received_payment_id'] not in seen:
                        rows.append(dict(receipt)); seen.add(receipt['received_payment_id'])
        return rows

    def _finance_receipt_context(self, installment_id):
        """Read an existing receipt reference only; no financial row is mutated here."""
        with self.db.read() as con:
            row = con.execute(
                """SELECT r.received_payment_id, r.transaction_id, r.amount, r.received_date_shamsi
                   FROM payment_allocations a
                   JOIN received_payments r ON r.received_payment_id=a.received_payment_id
                   WHERE a.installment_id=? ORDER BY r.received_date_shamsi DESC LIMIT 1""",
                (str(installment_id),),
            ).fetchone()
        return dict(row) if row else {}

    def _open_pending_editor_for_finance(self, title):
        dashboard = self.winfo_toplevel()
        center = getattr(dashboard, 'approval_center', None)
        if center is None:
            messagebox.showwarning(title, 'پنجره ثبت دیتا در دسترس نیست.', parent=self); return False
        rows = list(getattr(center, 'rows', []) or [])
        candidates = []
        for row in rows:
            payload = row.get('payload') or {}
            if str(payload.get('sale_id') or '') == str(self.selected_sale_id):
                candidates.append(row)
        if len(candidates) != 1:
            messagebox.showinfo(title, 'برای این قرارداد ردیف متناظر یکتا در Pending پیدا نشد.', parent=self); return False
        row = candidates[0]
        try:
            center.current = row
            center.open_editor(row)
            notebook = getattr(dashboard, 'notebook', None)
            approval_tab = getattr(dashboard, 'approval_tab', None)
            if notebook is not None and approval_tab is not None:
                notebook.select(approval_tab)
            return True
        except Exception as exc:
            messagebox.showerror(title, str(exc), parent=self); return False

    def _open_record(self):
        self.open_sales_record()

    def _show_payment_documents(self):
        messagebox.showinfo('اسناد پرداخت', 'اسناد پرداخت از تب ثبت تراکنش به همین قرارداد متصل می‌شوند. برای نمایش فیش، رکورد واریزی متناظر را باز کنید.', parent=self)

    def _double_click_finance_payment(self, event):
        iid = self.finance_tree.identify_row(event.y)
        if iid:
            self.finance_tree.selection_set(iid); self.finance_tree.focus(iid)
            self._open_selected_documents()

    def _open_selected_documents(self):
        selected = self._checked_or_selected_rows(self.finance_tree)
        if not selected:
            return messagebox.showwarning('اسناد واریزی', 'ابتدا ردیف‌های موردنظر را انتخاب کنید.', parent=self)
        payments = []
        with self.db.read() as con:
            for installment_id in selected:
                row = [dict(item) for item in con.execute(
                    """SELECT i.description, i.sequence_no, r.received_payment_id, r.transaction_id,
                              r.amount, r.received_date_shamsi
                       FROM installments i
                       LEFT JOIN payment_allocations a ON a.installment_id=i.installment_id
                       LEFT JOIN received_payments r ON r.received_payment_id=a.received_payment_id
                       WHERE i.installment_id=? ORDER BY r.received_date_shamsi""", (str(installment_id),)
                ).fetchall()]
                if not row:
                    continue
                first = row[0]; stage = str(first.get('description') or f"مرحله {first.get('sequence_no') or '-'}")
                receipts, known_receipts = [], set()
                for item in row:
                    receipt_id = str(item.get('received_payment_id') or '')
                    if not receipt_id or receipt_id in known_receipts:
                        continue
                    receipts.append(item); known_receipts.add(receipt_id)
                # An installment may receive several payments.  Preserve each
                # receipt as its own export/card row, rather than summing it
                # into one stage and losing the one-to-one receipt evidence.
                if not receipts:
                    payments.append({'stage': stage, 'date': '-', 'amount': 0, 'documents': []})
                    continue
                multiple_receipts = len(receipts) > 1
                for number, receipt in enumerate(receipts, 1):
                    entities = [('RECEIVED_PAYMENT', str(receipt['received_payment_id'])),
                                ('SALE_PAYMENT', str(receipt['received_payment_id']))]
                    transaction_id = str(receipt.get('transaction_id') or '')
                    if transaction_id:
                        entities.append(('TRANSACTION', transaction_id))
                    documents, known = [], set()
                    for document in self.attachments.list_for_entities(entities):
                        attachment_id = str(document.get('attachment_id') or '')
                        if attachment_id and attachment_id in known:
                            continue
                        documents.append(document)
                        if attachment_id:
                            known.add(attachment_id)
                    receipt_stage = f'{stage}-{persian_digits_187(number)}' if multiple_receipts else stage
                    payments.append({
                        'stage': receipt_stage,
                        'date': receipt.get('received_date_shamsi') or '-',
                        'amount': int(receipt.get('amount') or 0),
                        'documents': documents,
                    })
        sale = self.revenue.get_sale(self.selected_sale_id) or {}
        return PaymentDocuments187(self.winfo_toplevel(), db=self.db, base_dir=self.base_dir,
                                   payments=payments, contract_total=int(sale.get('contract_amount') or 0))

    def _changed(self):
        self.refresh()
        if self.on_changed: self.on_changed()
