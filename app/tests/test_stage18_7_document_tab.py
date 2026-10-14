import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'dashboard_stage18_7.py').read_text(encoding='utf-8')


def _method(name):
    tree = ast.parse(SOURCE)
    dashboard = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == 'Stage187Dashboard'
    )
    return next(node for node in dashboard.body if isinstance(node, ast.FunctionDef) and node.name == name)


def test_document_table_hides_reference_amount_and_has_document_filters():
    method = _method('_apply_financial_table_columns_187')
    text = ast.get_source_segment(SOURCE, method)
    assert "table is getattr(self, 'document_table', None)" in text
    assert "'amount', 'reference_amount', 'source_amount'" in text
    assert "not in {'مبلغ مرجع', 'اتصال به'}" in text
    assert "return self._DOCUMENT_FILTER_FIELDS_187" in SOURCE


def test_document_copy_and_edit_route_through_the_shared_wizard():
    dispatcher = ast.get_source_segment(SOURCE, _method('_copy_transaction_187'))
    assert 'self._copy_transaction_row_187(table,rows[0])' in dispatcher
    assert 'with DB.atomic()' in dispatcher
    copy_method = _method('_copy_transaction_row_187')
    action_method = _method('_transaction_action_187')
    copy_text = ast.get_source_segment(SOURCE, copy_method)
    action_text = ast.get_source_segment(SOURCE, action_method)
    assert "self._open_document_pending_wizard_187(pending_id" in copy_text
    assert "self._open_document_edit_wizard_187(row)" in action_text
    assert "payload['_document_edit_id_187']" in SOURCE


def test_document_edit_updates_the_existing_nonfinancial_record():
    function = next(
        node for node in ast.parse(SOURCE).body
        if isinstance(node, ast.FunctionDef) and node.name == '_approve_nonfinancial_187'
    )
    text = ast.get_source_segment(SOURCE, function)
    assert "edit_document_id = str(payload.get('_document_edit_id_187') or '').strip()" in text
    assert "UPDATE financial_documents" in text
    assert "return f'{subtype} اصلاح شد؛ اثر مالی ندارد.'" in text


def test_document_refresh_is_deferred_until_the_modal_is_closed_and_retried():
    method = _method('_refresh_after_document_change_187')
    text = ast.get_source_segment(SOURCE, method)
    assert 'self.after_idle(refresh_once)' in text
    assert 'self.after(120, self.refresh_financial)' in text

def test_document_table_uses_image_column_and_preview():
    columns = ast.get_source_segment(SOURCE, _method('_apply_financial_table_columns_187'))
    renderer = ast.get_source_segment(SOURCE, _method('_wrap_financial_row_values_187'))
    install = ast.get_source_segment(SOURCE, _method('_install_financial_transaction_ui_187'))
    assert "('image', 'تصویر سند', 112)" in columns
    assert "'links', 'image'" in columns
    assert "'image': self._document_image_indicator_187(row)" in renderer
    assert "self._install_document_preview_187(table)" in install
    assert '_show_document_preview_187' in SOURCE
