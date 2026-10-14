"""Data Entry gaps (2026-10-11 list) against disposable data and real Tk widgets."""
import pytest
from PIL import Image

from test_transaction_lifecycle_matrix import m, runtime, register
from test_stage18_7_record_fields import root, record


def _center(root, runtime, monkeypatch):
    m.style_ttk_187(root)
    monkeypatch.setattr(m.DataEntryCenter187, '_service_status_181', lambda self: None)
    for name in ('_start_telegram_probe_187', '_start_gemini_probe_187'):
        if hasattr(m.DataEntryCenter187, name):
            monkeypatch.setattr(m.DataEntryCenter187, name, lambda self: None)
    center = m.DataEntryCenter187(root, runtime.rich)
    center.pack(fill='both', expand=True)
    return center


DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')


def _number(value):
    return int(''.join(ch for ch in str(value).translate(DIGITS) if ch.isdigit()))


def _png(tmp_path, size=(40, 20), name='r.png'):
    path = tmp_path / name
    Image.new('RGB', size, 'navy').save(path)
    return path


# 3
@pytest.mark.parametrize('how', ['attachment', 'payload_only', 'both'])
def test_preview_image_of_a_pending_row_can_be_deleted(root, runtime, monkeypatch, tmp_path, how):
    row = record(runtime)
    pid = row['pending_id']
    source = _png(tmp_path, (30, 30))
    payload = dict(row['payload'])
    if how in ('payload_only', 'both'):
        payload['receipt_image_path'] = str(source)
        runtime.db.update_pending(pid, payload=payload)
    if how in ('attachment', 'both'):
        runtime.db.attach_file_to_pending(pending_id=pid, local_path=str(source), mime_type='image/png',
                                          document_type='RECEIPT')
    center = _center(root, runtime, monkeypatch)
    center._show(runtime.db.get_pending_item(pid))
    root.update()
    assert center._image is not None
    center._receipt_preview187.image_action('delete')
    root.update()
    assert center._image is None
    center._preview_signature_185 = None
    center._show(runtime.db.get_pending_item(pid))
    root.update()
    assert center._image is None


# 1 + 8: rotate, crop and download in the record window
def test_record_receipt_can_be_rotated_cropped_and_downloaded(root, runtime, monkeypatch, tmp_path):
    from receipt_evidence187 import upload_image
    import receipt_image_edit187 as editing
    row = record(runtime)
    pid = row['pending_id']
    upload_image(runtime.db, pid, _png(tmp_path), '')
    row = runtime.db.get_pending_item(pid)
    editor = m.v182.UnifiedPendingEditor182(root, row, runtime.rich, lambda: None)
    root.update()
    controller = editor._receipt_controller187
    controller.refresh_gallery()
    first = controller.gallery.path
    assert Image.open(first).size == (40, 20)
    controller.image_action('rotate_right')
    second = controller.gallery.path
    assert second != first and Image.open(second).size == (20, 40)
    assert Image.open(first).size == (40, 20)  # the original stays in the archive
    assert runtime.db.get_pending_item(pid)['payload']['receipt_image_path'] == second
    assert [a['local_path'] for a in runtime.db.list_pending_attachments(pid)].count(first) == 0
    monkeypatch.setattr(editing, 'ask_crop', lambda parent, image: (0, 0, 10, 30))
    controller.image_action('crop')
    assert Image.open(controller.gallery.path).size == (10, 30)
    controller.image_action('rotate_left')
    assert Image.open(controller.gallery.path).size == (30, 10)
    target = tmp_path / 'saved.png'
    monkeypatch.setattr('record_receipt187.filedialog.asksaveasfilename', lambda **kw: str(target))
    controller.download()
    assert Image.open(target).size == (30, 10)
    assert runtime.db.get_pending_item(pid)['status'] == 'PENDING_REVIEW'


def test_crop_box_stays_inside_the_picture_and_ignores_a_speck():
    from receipt_image_edit187 import crop_box
    assert crop_box((10, 10, 110, 60), 0.5, (400, 300)) == (20, 20, 220, 120)
    assert crop_box((-5, -5, 900, 900), 1, (400, 300)) == (0, 0, 400, 300)
    assert crop_box((50, 50, 51, 51), 1, (400, 300)) is None


def test_crop_dialog_returns_the_dragged_box(root):
    from receipt_image_edit187 import CropDialog187, crop_box
    image = Image.new('RGB', (2000, 1000), 'white')
    dialog = CropDialog187(root, image)
    root.update()
    assert dialog.scale < 1
    dialog.accept()  # nothing is dragged yet: the dialog stays open
    assert dialog.winfo_exists() and dialog.result is None
    dialog.set_selection(10, 20, 110, 70)
    dialog.accept()
    assert dialog.result == crop_box((10, 20, 110, 70), dialog.scale, image.size)
    assert not dialog.winfo_exists()


# 1 + 2 + 3 + 7: the options of the preview and of the record
def _two_documents(runtime, tmp_path, pid):
    from receipt_evidence187 import upload_image
    upload_image(runtime.db, pid, _png(tmp_path, (60, 80), 'a.png'), '')
    upload_image(runtime.db, pid, _png(tmp_path, (80, 60), 'b.png'), '')


def _hover_tip(root, widget):
    """The text of the hint the pointer reveals on a widget, or None when it shows none."""
    import time
    import tkinter as tk
    widget.event_generate('<Enter>')
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        root.update()
        tips = [child for child in widget.winfo_children() if isinstance(child, tk.Toplevel)]
        if tips:
            text = tips[0].winfo_children()[0].cget('text')
            widget.event_generate('<Leave>')
            root.update()
            assert not [c for c in widget.winfo_children() if isinstance(c, tk.Toplevel)]
            return text
        time.sleep(0.03)
    widget.event_generate('<Leave>')
    return None


def _check_options(root, controller, canvas, text_widget):
    tools = controller.edit_buttons
    assert [b.hint for b in tools] == ['چرخش به راست', 'چرخش به چپ', 'برش تصویر']
    for button in tools:  # icons only, on the right of the box, one under the other
        assert button.cget('text') == '' and str(button.cget('image'))
        assert button.winfo_ismapped()
        assert button.winfo_rootx() >= canvas.winfo_rootx() + canvas.winfo_width() - 2
        assert canvas.winfo_rooty() - 2 <= button.winfo_rooty() <= canvas.winfo_rooty() + canvas.winfo_height()
    ys = [b.winfo_rooty() for b in tools]
    assert ys == sorted(ys) and len(set(ys)) == 3
    assert _hover_tip(root, tools[0]) == 'چرخش به راست' and _hover_tip(root, tools[2]) == 'برش تصویر'
    # nothing else is on the right: the others are one row under the box
    row = [button for button, *_rest in controller._row]
    assert max(b.winfo_rooty() for b in row) - min(b.winfo_rooty() for b in row) <= 2
    for button in row:
        assert button.winfo_ismapped()
        assert button.winfo_rooty() >= canvas.winfo_rooty() + canvas.winfo_height() - 2
    assert text_widget.winfo_rooty() >= max(b.winfo_rooty() + b.winfo_height() for b in row) - 2
    return row


def _check_arrows(root, controller, canvas):
    gallery = controller.gallery
    assert gallery.next.winfo_ismapped() and gallery.previous.winfo_ismapped()
    left, right = canvas.winfo_rootx(), canvas.winfo_rootx() + canvas.winfo_width()
    assert left <= gallery.next.winfo_rootx() < left + 40
    assert right - 40 < gallery.previous.winfo_rootx() + gallery.previous.winfo_width() <= right
    assert abs((gallery.next.winfo_rooty() + gallery.next.winfo_height() / 2)
               - (canvas.winfo_rooty() + canvas.winfo_height() / 2)) < 6
    assert _hover_tip(root, gallery.next) == 'سند بعدی' and _hover_tip(root, gallery.previous) == 'سند قبلی'
    first = gallery.path
    gallery.next.invoke()
    assert gallery.path != first and gallery.badge_text.get()
    gallery.previous.invoke()
    assert gallery.path == first


def test_preview_options_are_three_icons_beside_the_box_and_one_row_under_it(root, runtime, monkeypatch, tmp_path):
    root.geometry('1366x740+0+0')
    center = _center(root, runtime, monkeypatch)
    row = record(runtime)
    _two_documents(runtime, tmp_path, row['pending_id'])
    center.refresh()
    center.table.tree.selection_set(center.table.tree.get_children()[0])
    center._select18()
    root.update()
    controller, canvas = center._receipt_preview187, center.preview
    buttons = _check_options(root, controller, canvas, center.text)
    assert not controller._icon_only and all(b.cget('text') for b in buttons)
    for button in buttons:  # the words fit: no button is narrower than its own label
        assert button.winfo_width() >= button.winfo_reqwidth() - 2
    _check_arrows(root, controller, canvas)


def test_one_document_has_no_arrows(root, runtime, monkeypatch, tmp_path):
    from receipt_evidence187 import upload_image
    root.geometry('1366x740+0+0')
    center = _center(root, runtime, monkeypatch)
    row = record(runtime)
    upload_image(runtime.db, row['pending_id'], _png(tmp_path), '')
    center.refresh()
    center.table.tree.selection_set(center.table.tree.get_children()[0])
    center._select18()
    root.update()
    gallery = center._receipt_preview187.gallery
    assert len(gallery.paths) == 1
    assert not gallery.next.winfo_ismapped() and not gallery.previous.winfo_ismapped()


def test_option_row_falls_back_to_icons_when_the_pane_is_too_narrow(root, runtime, monkeypatch):
    root.geometry('1366x740+0+0')
    center = _center(root, runtime, monkeypatch)
    root.update()
    controller = center._receipt_preview187
    controller.bar.winfo_width = lambda: 100
    controller._fit_bar()
    assert controller._icon_only
    for button, title, _icon, _ink in controller._row:
        assert button.cget('text') == '' and str(button.cget('image'))
    controller.bar.winfo_width = lambda: 1000
    controller._fit_bar()
    assert not controller._icon_only
    for button, title, _icon, _ink in controller._row:
        assert button.cget('text') == title


def test_record_options_are_three_icons_beside_the_box_and_one_row_under_it(root, runtime, tmp_path):
    row = record(runtime)
    _two_documents(runtime, tmp_path, row['pending_id'])
    editor = m.v182.UnifiedPendingEditor182(root, runtime.db.get_pending_item(row['pending_id']), runtime.rich,
                                            lambda: None)
    editor.geometry('1400x800+0+0')
    editor.update()
    controller, box = editor._receipt_controller187, editor.canvas.master
    buttons = _check_options(editor, controller, editor.canvas, editor.caption)
    assert not controller._icon_only
    # the zoom buttons share the row with the others
    zoom = controller._zoom
    assert zoom is not None and abs(zoom.winfo_rooty() - buttons[0].winfo_rooty()) <= 6
    _check_arrows(editor, controller, editor.canvas)


# 8
def test_preview_right_click_menu_offers_download_receipt(root, runtime, monkeypatch):
    import barkav_ui.window as windows
    seen = []
    monkeypatch.setattr(windows, 'PopupMenu', lambda parent, groups, **kw: seen.append(groups))
    center = _center(root, runtime, monkeypatch)
    center._receipt_preview187.image_menu()
    labels = [item['label'] for _title, items in seen[0] for item in items]
    assert 'دانلود رسید' in labels and 'برش تصویر' in labels and 'چرخش به راست' in labels


# 4
def test_model_picker_default_caption(root, tmp_path):
    from ai_section_models187 import AIModelPicker187
    default = AIModelPicker187(root, section='data_entry', base_dir=tmp_path, persist=False,
                               choice={'mode': 'AUTO'}, default_caption='مدل هوش مصنوعی')
    assert 'مدل هوش مصنوعی' in default.button.cget('text')
    picked = AIModelPicker187(root, section='data_entry', base_dir=tmp_path, persist=False,
                              choice={'mode': 'SELECTED', 'models': ['GEMINI']}, default_caption='مدل هوش مصنوعی')
    assert 'Gemini' in picked.button.cget('text')
    other = AIModelPicker187(root, section='data_entry', base_dir=tmp_path, persist=False, choice={'mode': 'AUTO'})
    assert 'پیش‌فرض' in other.button.cget('text')


# 5
def test_row_numbers_close_up_after_rows_are_hidden(root, runtime, monkeypatch):
    import data_entry_extras_ui as extras
    ids = [record(runtime, mid=index)['pending_id'] for index in range(1, 5)]
    center = _center(root, runtime, monkeypatch)
    center.refresh()

    def numbers():
        tree = center.table.tree
        return [_number(tree.item(iid, 'values')[0]) for iid in tree.get_children()]
    assert numbers() == [1, 2, 3, 4]
    center.table.tree.selection_set(center.table.tree.get_children())
    center._sync_data_entry_checks_187()
    assert center.table.tree.heading('row')['text'].startswith('☑')
    extras.hide_rows(center, ids[:2])
    assert numbers() == [1, 2]
    center.table.tree.selection_set(center.table.tree.get_children())
    center._sync_data_entry_checks_187()
    extras.hide_rows(center, ids[2:3])
    assert numbers() == [1]


# 6
def test_no_kind_of_note_asks_for_a_payment_method():
    for subtype in ('فاکتور', 'داکیومنت', 'اطلاع‌رسانی', 'یادداشت', 'یادآوری', 'گزارش روزانه', 'تقویم کارگاهی'):
        assert m._note_without_payment_method_187('یادداشت', subtype), subtype
        assert not [f for f in m._special_fields_187('یادداشت', subtype) if f.key == 'payment_method']
        assert not [f for page in m._wizard_steps_187('یادداشت', subtype) for f in page if f.key == 'payment_method']
    assert not m._note_without_payment_method_187('هزینه ساخت', 'نقدی')
    assert [f for f in m._special_fields_187('هزینه ساخت', 'نقدی') if f.key == 'payment_method']


def test_note_forms_have_no_payment_method_field(root, runtime):
    for subtype in ('فاکتور', 'گزارش روزانه'):
        row = record(runtime, title='یادداشت', mid=11)
        row['payload'].update(v18_subtype=subtype, transaction_subtype=subtype)
        editor = m.v182.UnifiedPendingEditor182(root, row, runtime.rich, lambda: None)
        root.update()
        assert 'payment_method' not in editor.widgets and 'payment_method' not in editor.vars, subtype
        editor.destroy()


# 2
def test_confirming_the_wizard_does_not_open_the_record_window(root, runtime, monkeypatch):
    import tkinter as tk
    opened, selected = [], []
    parent = tk.Frame(root)
    parent.notebook = type('N', (), {'select': lambda self, tab: selected.append(tab)})()
    parent.approval_tab = object()
    parent.approval_center = type('C', (), {'open_editor': lambda self, item, **kw: opened.append(item)})()
    for name in ('showinfo', 'showwarning', 'showerror'):
        monkeypatch.setattr(m.messagebox, name, lambda *a, **k: None)
    monkeypatch.setattr(m.messagebox, 'askyesno', lambda *a, **k: True)
    monkeypatch.setattr(m, '_confirm_debt_warning_187', lambda *a: True)
    done = []
    row = record(runtime)
    wizard = m.v182.TransactionWizard182(parent, row, runtime.rich, lambda: done.append(1), lambda: None)
    for _ in range(8):
        if not wizard.winfo_exists():
            break
        wizard.next()
    assert not wizard.winfo_exists() and done
    assert runtime.db.get_pending_item(row['pending_id'])['status'] == 'APPROVED'
    assert opened == []  # back on the Data Entry tab, with no record window
    assert selected == [parent.approval_tab]


# 9 + 10
def _plan(runtime):
    for description, cost_type in (('میلگرد Ø8', 'مصالح'), ('اجرت اجرای اسکلت', 'اجرت'), ('غذا', 'خدمات')):
        runtime.rich.add_phase_item(8, 'اسکلت', dict(description=description, cost_type=cost_type, unit='عدد',
                                                      qty_estimate=1, qty_forecast=1, estimate_rate=10,
                                                      forecast_rate=10))


def test_sub_phase_lists_only_the_lines_of_the_chosen_category_in_a_wide_box(root, runtime):
    _plan(runtime)
    row = record(runtime)
    row['payload'].update(main_phase='08 — اسکلت', construction_stage='08 — اسکلت', cost_group='مصالح')
    editor = m.v182.UnifiedPendingEditor182(root, row, runtime.rich, lambda: None)
    root.update()
    box = editor.widgets['sub_phase']
    assert 'میلگرد Ø8' in box._all and 'اجرت اجرای اسکلت' not in box._all and 'غذا' not in box._all
    editor.vars['cost_group'].set('پیمانکار')
    assert list(box._all) == ['اجرت اجرای اسکلت']
    editor.vars['cost_group'].set('خدمات')
    assert list(box._all) == ['غذا']
    assert int(box.cget('width')) >= m.SUBPHASE_MIN_WIDTH_187
    editor.geometry('1400x800+30+30'); editor.update()
    assert box.winfo_width() > 2 * editor.widgets['main_phase'].winfo_width()


# 11
def test_skeleton_phase_has_rebar_and_laboratory_groups(runtime):
    import skeleton_phase187 as skeleton
    from cost_allocation_stage18_7 import suggest_plan_row
    for size in ('Ø8', 'Ø10', 'Ø12', 'بیشتر از Ø12'):
        runtime.rich.add_phase_item(8, 'اسکلت', dict(
            description=f'میلگرد {size}', cost_type='مصالح', unit='کیلوگرم', section='آرماتوربندی و میلگرد',
            qty_estimate=1, qty_forecast=1, estimate_rate=10, forecast_rate=10))
    runtime.rich.add_phase_item(8, 'اسکلت', dict(
        description='بتن', cost_type='مصالح', unit='مترمکعب', qty_estimate=1, qty_forecast=1,
        estimate_rate=10, forecast_rate=10))
    skeleton.ensure_groups(runtime.rich)
    rows = runtime.rich.list_phase_items(8)
    assert {r['section'] for r in rows if r['description'].startswith('میلگرد')} == {skeleton.REBAR}
    lab = [r for r in rows if r['section'] == skeleton.LAB]
    assert [r['description'] for r in lab] == list(skeleton.LAB_LINES)
    assert all(r['cost_type'] == 'خدمات' and r['plan_ref'] for r in lab)
    assert len({r['plan_ref'] for r in rows}) == len(rows)
    choices = [r['description'] for r in runtime.rich.subphase_candidates(8)]
    assert choices.index('میلگرد') < choices.index('میلگرد Ø8')
    assert choices.index('آزمایشگاه') < choices.index('آزمایشگاه بتن') < choices.index('آزمایشگاه میلگرد')
    again = [dict(r) for r in runtime.rich.list_phase_items(8)]
    skeleton.ensure_groups(runtime.rich)
    assert [dict(r) for r in runtime.rich.list_phase_items(8)] == again  # idempotent
    chosen = suggest_plan_row(runtime.rich, text='آزمایش بتن', cost_group='خدمات', phase_no=8, sub_phase='آزمایشگاه')
    assert chosen and chosen.description == 'آزمایشگاه بتن'
    chosen = suggest_plan_row(runtime.rich, text='میلگرد 10', cost_group='مصالح', phase_no=8, sub_phase='میلگرد')
    assert chosen and chosen.description.startswith('میلگرد')


def test_skeleton_import_rows_get_the_same_groups():
    import skeleton_phase187 as skeleton
    rows = [dict(phase_no=8, phase_name='اسکلت', section='آرماتوربندی و میلگرد', description=f'میلگرد {n}',
                 sort_order=i, ref=f'08-{i}') for i, n in enumerate(('Ø8', 'Ø10'), 1)]
    rows.append(dict(phase_no=8, phase_name='اسکلت', section='بتن', description='بتن', sort_order=3, ref='08-3'))
    rows.append(dict(phase_no=9, phase_name='چاه', section='x', description='حفاری', sort_order=1, ref='09-1'))
    out = skeleton.grouped_import_rows(rows)
    phase = [r for r in out if r['phase_no'] == 8]
    assert [r['description'] for r in phase] == ['میلگرد Ø8', 'میلگرد Ø10', 'آزمایشگاه بتن', 'آزمایشگاه میلگرد', 'بتن']
    assert [r['section'] for r in phase[:2]] == ['میلگرد'] * 2 and phase[2]['section'] == 'آزمایشگاه'
    assert len({r['ref'] for r in phase}) == 5 and out[-1]['phase_no'] == 9


def test_skeleton_import_keeps_lab_lines_a_workbook_already_has():
    import skeleton_phase187 as skeleton
    rows = [dict(phase_no=8, phase_name='اسکلت', section='', description=name, sort_order=i, ref=f'08-{20 + i}')
            for i, name in enumerate(skeleton.LAB_LINES, 1)]
    out = skeleton.grouped_import_rows(rows)
    assert [r['description'] for r in out] == list(skeleton.LAB_LINES)
    assert {r['section'] for r in out} == {skeleton.LAB}

