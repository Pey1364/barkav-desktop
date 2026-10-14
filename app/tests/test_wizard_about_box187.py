"""«بابت» of a wizard is the same right-to-left box as the record window's, kept in step with its variable."""
from test_transaction_lifecycle_matrix import m, runtime  # noqa: F401
from test_stage18_7_record_fields import root  # noqa: F401
from test_land_wizard_settlement187 import wizard_for
from test_cheque_workflow187 import cheque_payload

RLE = '\u202b'


def _about(root, runtime):
    form = wizard_for(root, runtime, cheque_payload())
    form.page_index = 1
    form._show_page()
    for _ in range(10):
        form.update()
    return form, form.widgets['description']


def test_the_about_box_of_the_cheque_wizard_is_a_right_to_left_text_box(root, runtime):
    form, widget = _about(root, runtime)
    assert widget.winfo_class() == 'Text'
    assert widget.tag_cget('rtl187', 'justify') == 'right'
    assert widget.tk.call(widget._w, 'get', '1.0', 'end').startswith(RLE)  # the controller's invisible mark


def test_what_is_typed_in_the_about_box_reaches_the_variable_without_the_mark(root, runtime):
    form, widget = _about(root, runtime)
    widget.delete('1.0', 'end')
    widget.tk.call('tk::TextInsert', widget._w, 'چک بابت آزمایش خاک 2')
    for _ in range(5):
        form.update()
    assert form.vars['description'].get() == 'چک بابت آزمایش خاک 2'
    assert RLE not in form.vars['description'].get()
    form._capture()
    assert form.payload['description'] == 'چک بابت آزمایش خاک 2'


def test_a_value_set_on_the_variable_shows_in_the_about_box(root, runtime):
    form, widget = _about(root, runtime)
    form.vars['description'].set('تسهیلات اعتبار ملی')
    for _ in range(5):
        form.update()
    assert widget.get('1.0', 'end-1c') == 'تسهیلات اعتبار ملی'
