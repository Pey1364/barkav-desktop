"""Real runtime integration checks, disposable database and offline GUI."""
import tkinter as tk
from test_undo_redo_tabs_ui import app, m, pytestmark
import dashboard_stage18_2 as editor

def test_record_navigation_and_approval_keep_same_window(app, monkeypatch):
    rows=[]
    for i in range(3):
        m.DB.register_telegram_message(chat_id=-100999, message_id=100+i,
            raw_text='متن یادداشت', content_type='TEXT', message_date='2026-09-29T12:00:00')
        pid=m.DB.create_or_replace_pending(telegram_chat_id=-100999,
            telegram_message_id=100+i, detected_type='INFO', confidence=1.0,
            status='PENDING_REVIEW', payload={'detected_type':'INFO',
                'v18_title':'یادداشت','v18_subtype':'اطلاع‌رسانی',
                'event_date_shamsi':'1405/07/07','description':'متن یادداشت','amount':0})
        rows.append(m.DB.get_pending_item(pid))
    center=app.approval_center
    center.refresh()
    center.open_editor(rows[1])
    app.update()
    windows=[w for w in center.winfo_children()
             if isinstance(w, editor.UnifiedPendingEditor182)]
    assert len(windows)==1
    window=windows[0]
    identity=str(window)
    nav=window._navigation_rows_182
    index=window._navigation_index_182
    assert len(nav)>=3
    if index+1<len(nav):
        window._navigate_record_182(1)
        app.update()
        assert window.pid==str(nav[index+1]['pending_id'])
        window._navigate_record_182(-1)
    else:
        window._navigate_record_182(-1)
        app.update()
        assert window.pid==str(nav[index-1]['pending_id'])
        window._navigate_record_182(1)
    assert str(window)==identity and window.winfo_exists()
    errors=[]
    monkeypatch.setattr(editor.messagebox,'showerror',lambda *a,**k:errors.append(a))
    window.approve()
    app.update()
    assert not errors
    assert window.winfo_exists() and str(window)==identity
    assert m.DB.get_pending_item(window.pid)['status']=='APPROVED'
    assert any(r.get('pending_id')==window.pid for r in app.all_tx_table.all_rows)
    assert str(window._confirm_button_182['state'])=='disabled'
    window.destroy()
