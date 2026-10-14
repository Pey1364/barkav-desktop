from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from types import SimpleNamespace

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_BOOT = tempfile.TemporaryDirectory()
os.environ.setdefault('STAGE4_DB_PATH', str(Path(_BOOT.name) / 'import_flow.sqlite3'))
os.environ.setdefault('TELEGRAM_BOT_TOKEN', 'import-flow-token')
os.environ.setdefault('GEMINI_API_KEY', 'import-flow-gemini')
os.environ.setdefault('ADMIN_USER_ID', '187')
os.environ.setdefault('GROUP_CHAT_ID', '-100187')

import dashboard_stage18_7 as d187  # noqa: E402
from approval_service import ApprovalCenterService  # noqa: E402
from barkav_ui.messages import MessageDialog  # noqa: E402
from finance_db import FinanceDB  # noqa: E402
from receipt_intelligence import OCRResult  # noqa: E402
from telegram_history_import import import_telegram_export  # noqa: E402
from barkav_ui.window import fade_in, hide_for_fade, work_area  # noqa: E402

Center = d187.DataEntryCenter187


@pytest.fixture()
def root():
    try:
        window = tk.Tk()
    except tk.TclError:
        pytest.skip('no display available')
    window.geometry('520x320+60+60')
    window.update()
    yield window
    window.destroy()


class Harness(tk.Tk):
    """The few Data Entry methods the progress windows and the import button need."""

    _progress_dialog_187 = Center._progress_dialog_187
    _present_dialog_187 = Center._present_dialog_187
    _progress_phase_187 = staticmethod(Center._progress_phase_187)
    _close_progress_dialog_187 = staticmethod(Center._close_progress_dialog_187)
    _center_reprocess_dialog_187 = Center._center_reprocess_dialog_187
    _unhide_imported_reviews_187 = staticmethod(Center._unhide_imported_reviews_187)
    import_chat_backup = Center.import_chat_backup

    def refresh(self):
        self.refresh_calls.append(self.dialog_state())

    def dialog_state(self):
        return None

    def _run_ai_ids(self, ids):
        self.ai_ids = list(ids)


def _walk(widget):
    yield widget
    for child in widget.winfo_children():
        yield from _walk(child)


def _photo_backup(root_dir: Path, count: int) -> Path:
    export = root_dir / 'export'
    (export / 'photos').mkdir(parents=True)
    messages = []
    for index in range(1, count + 1):
        Image.new('RGB', (40, 30), (index * 30, 9, 9)).save(export / 'photos' / f'r{index}.jpg')
        messages.append({
            'id': 200 + index, 'type': 'message', 'date': f'2026-08-10T10:0{index}:00',
            'from': 'Peyman', 'text': '', 'photo': f'photos/r{index}.jpg',
        })
    path = export / 'result.json'
    path.write_text(json.dumps(
        {'name': 'Project', 'type': 'private_supergroup', 'id': 1, 'messages': messages},
        ensure_ascii=False,
    ), encoding='utf-8')
    return path


def _alpha_spy(monkeypatch):
    writes = []
    original = tk.Wm.wm_attributes

    def spy(self, *args, **kwargs):
        if len(args) > 1 and args[0] in ('-alpha', 'alpha'):
            writes.append((str(self), float(args[1])))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(tk.Wm, 'wm_attributes', spy)
    monkeypatch.setattr(tk.Wm, 'attributes', spy)
    return writes


def _shell_map_hook(root):
    fake = SimpleNamespace(
        _main_window=root,
        _normalise_window_187=lambda _window: None,
        _normalise_toplevel_once_187=lambda _window: None,
    )
    root.bind_all(
        '<Map>', lambda event: d187.Stage187Dashboard._on_toplevel_map_187(fake, event), add='+')


def _pump(root, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        root.update()
        time.sleep(0.005)


def test_themed_dialog_shows_without_alpha_animation_even_with_the_shell_map_hook(root, monkeypatch):
    writes = _alpha_spy(monkeypatch)
    _shell_map_hook(root)

    dialog = MessageDialog(root, 't', 'm', kind='info', buttons=(('ok', True, 'Primary.TButton'),))
    _pump(root, 0.05)
    alphas = [value for path, value in writes if path == str(dialog)]
    assert dialog.winfo_ismapped()
    center_x = dialog.winfo_rootx() + dialog.winfo_width() // 2
    center_y = dialog.winfo_rooty() + dialog.winfo_height() // 2
    _usable_width, usable_height = work_area(dialog)
    assert abs(center_x - root.winfo_screenwidth() // 2) <= 20
    assert abs(center_y - usable_height // 2) <= 20
    dialog.destroy()
    _pump(root, 0.03)

    assert alphas == []


def test_other_toplevels_are_centered_and_show_without_fade(root, monkeypatch):
    writes = _alpha_spy(monkeypatch)
    _shell_map_hook(root)

    plain = tk.Toplevel(root)
    plain.geometry('300x180+0+0')
    _pump(root, 0.08)
    alphas = [value for path, value in writes if path == str(plain)]
    center_x = plain.winfo_rootx() + plain.winfo_width() // 2
    center_y = plain.winfo_rooty() + plain.winfo_height() // 2
    _usable_width, usable_height = work_area(plain)
    assert abs(center_x - root.winfo_screenwidth() // 2) <= 20
    assert abs(center_y - usable_height // 2) <= 20
    root.iconify()
    root.update()
    plain.destroy()
    _pump(root, 0.03)

    assert alphas == []
    assert root.state() != 'iconic'


def test_fade_compatibility_helper_reveals_immediately_without_alpha(root, monkeypatch):
    writes = _alpha_spy(monkeypatch)
    dialog = tk.Toplevel(root)
    hide_for_fade(dialog)
    fade_in(dialog, step=0.01, interval_ms=1)
    root.update()

    assert dialog.winfo_ismapped()
    assert writes == []
    dialog.destroy()


def test_window_text_alignment_and_numeric_leading_lines_are_rtl(root):
    root._walk_187 = lambda target: list(_walk(target))
    root._apply_widget_font_187 = lambda *_args: None
    dialog = tk.Toplevel(root)
    label = ttk.Label(dialog, text='۱۲ مرحله\n  2 وضعیت')
    label.pack()
    button = ttk.Button(dialog, text='2026 وضعیت')
    button.pack()
    numeric_only = ttk.Label(dialog, text='۱۲۳')
    numeric_only.pack()
    entry = ttk.Entry(dialog)
    entry.pack()
    d187.Stage187Dashboard._normalise_dialog_rtl_187(root, dialog)
    root.update_idletasks()

    assert str(label.cget('anchor')) == 'e'
    assert str(label.cget('justify')) == 'right'
    assert label.cget('text') == '‏۱۲ مرحله\n  ‏2 وضعیت'
    assert button.cget('text') == '‏2026 وضعیت'
    assert numeric_only.cget('text') == '۱۲۳'
    assert entry.cget('justify') == 'right'
    dialog.destroy()


def test_progress_window_is_built_hidden_then_shown_centred_and_modal(monkeypatch):
    states = []

    class SpyToplevel(d187.BarkavWindow):
        def deiconify(self):
            states.append(self.wm_state())
            super().deiconify()

    monkeypatch.setattr(d187, 'BarkavWindow', SpyToplevel)
    harness = Harness()
    try:
        harness.geometry('640x360+80+80')
        harness.update()
        dialog, label, bar = harness._progress_dialog_187('t', 'در حال کار…', total=5)
        harness.update()

        assert states == ['withdrawn'], 'the window mapped before it was fully built'
        assert dialog.winfo_ismapped()
        assert dialog.winfo_width() >= 520
        assert dialog.grab_current() is dialog
        dialog.event_generate('<Escape>')
        harness.update()
        assert dialog.winfo_exists(), 'active processing must not close through Escape'
        assert str(bar['mode']) == 'determinate' and float(bar['maximum']) == 5

        harness._progress_phase_187(label, bar, 'مرحلهٔ بعد', 9)
        assert label.get() == 'مرحلهٔ بعد'
        assert str(bar['mode']) == 'determinate' and float(bar['maximum']) == 9 and float(bar['value']) == 0
        harness._progress_phase_187(label, bar, 'در حال به‌روزرسانی جدول…')
        assert str(bar['mode']) == 'indeterminate'
        harness._close_progress_dialog_187(dialog, bar)
        assert not dialog.winfo_exists()
    finally:
        harness.destroy()


def test_backup_button_counts_messages_keeps_the_window_for_the_repaint_and_asks_once(
        tmp_path, monkeypatch):
    db = FinanceDB(tmp_path / 'db.sqlite3')
    with db.tx() as con:
        con.execute(
            'CREATE TABLE IF NOT EXISTS rich_ui_hidden_reviews('
            'pending_id TEXT PRIMARY KEY,hidden INTEGER NOT NULL DEFAULT 1,updated_at TEXT NOT NULL)')

    class Vision:
        async def analyze(self, **_kwargs):
            return {}

    approval = ApprovalCenterService(db, tmp_path, parser=Vision())
    approval.receipts.ocr.extract = lambda _path: OCRResult('', 'TEST', False)
    backup = _photo_backup(tmp_path, 6)
    monkeypatch.setattr(d187, 'DB', db)
    monkeypatch.setattr(d187.v182, 'APPROVAL', approval)

    real_import = d187.import_telegram_export

    def slow_import(db_, path, *, receipt_service=None, progress=None):
        def slow(done, total):
            progress(done, total)
            time.sleep(0.12)  # long enough for the window to be seen mid-import

        return real_import(db_, path, receipt_service=receipt_service, progress=slow)

    monkeypatch.setattr(d187, 'import_telegram_export', slow_import)

    shown = []
    monkeypatch.setattr(d187, 'filedialog', SimpleNamespace(askopenfilename=lambda **_k: str(backup)))
    monkeypatch.setattr(d187, 'messagebox', SimpleNamespace(
        showinfo=lambda _t, text, **_k: shown.append(('info', text)),
        showerror=lambda _t, text, **_k: shown.append(('error', text)),
        askyesno=lambda _t, text, **_k: (shown.append(('ask', text)) or True),
    ))

    harness = Harness()
    try:
        harness.geometry('640x360+80+80')
        harness.update()
        harness.ai_ids = None
        harness.refresh_calls = []
        dialog = harness.import_chat_backup()
        bar = next(w for w in _walk(dialog) if isinstance(w, ttk.Progressbar))
        text_label = next(w for w in _walk(dialog) if isinstance(w, tk.Label))
        variable = str(text_label.cget('textvariable'))

        def snapshot():
            return dialog.winfo_exists() and (str(bar['mode']), float(bar['value']), harness.getvar(variable))

        harness.dialog_state = lambda: snapshot()
        modes, texts = set(), []
        deadline = time.monotonic() + 30
        while harness.ai_ids is None and time.monotonic() < deadline:
            harness.update()
            state = snapshot() if dialog.winfo_exists() else None
            if state:
                modes.add(state[0])
                texts.append(state[2])
            time.sleep(0.005)
    finally:
        harness.destroy()

    assert harness.ai_ids is not None and len(harness.ai_ids) == 6
    assert 'determinate' in modes
    assert any('افزودن پیام' in text and 'از ۶' in text for text in texts), (modes, sorted(set(texts)))
    # The window was still open, showing the repaint stage, when the table refreshed.
    assert harness.refresh_calls and harness.refresh_calls[0][2] == 'در حال نمایش نتیجه در جدول…'
    assert [kind for kind, _text in shown] == ['ask']
    assert 'زمان بارگذاری' in shown[0][1]
    assert '۶ تصویر آمادهٔ تحلیل است' in shown[0][1]


def test_import_reports_every_message_to_the_progress_callback(tmp_path):
    db = FinanceDB(tmp_path / 'db.sqlite3')
    approval = ApprovalCenterService(db, tmp_path, parser=None)
    approval.receipts.ocr.extract = lambda _path: OCRResult('', 'TEST', False)
    backup = _photo_backup(tmp_path, 4)
    seen = []

    import_telegram_export(
        db, backup, receipt_service=approval.receipts, progress=lambda done, total: seen.append((done, total)))

    assert seen == [(1, 4), (2, 4), (3, 4), (4, 4)]


def test_api_gate_pauses_after_a_rate_limit_and_counts_its_calls():
    starts = []

    class Parser:
        first = True

        async def analyze(self, **_kwargs):
            starts.append(time.monotonic())
            if Parser.first:
                Parser.first = False
                raise RuntimeError('GEMINI: 429 Resource exhausted')
            return {}

    async def go():
        gate = d187.ReprocessApiGate187(Parser(), 2, pause=0.3)
        with pytest.raises(RuntimeError):
            await gate.analyze()
        await gate.analyze()
        return gate

    gate = asyncio.run(go())

    assert gate.rate_limited == 1 and gate.calls == 2
    assert starts[1] - starts[0] >= 0.25
    assert gate.api_seconds > 0


def test_time_left_only_shows_once_there_is_a_pace_to_go_by():
    assert d187.format_duration_187(0) == '۰ ثانیه'
    assert d187.format_duration_187(61) == '۱ دقیقه و ۱ ثانیه'
    assert d187.format_duration_187(120) == '۲ دقیقه'
    early = d187.reprocess_status_text_187('رسید', 1, 18, 5)
    assert 'مانده' not in early and '۱ از ۱۸' in early
    later = d187.reprocess_status_text_187('رسید', 8, 18, 60)
    assert '۸ از ۱۸' in later and 'مانده' in later and '۱ دقیقه و ۱۵ ثانیه' in later
    assert d187.reprocess_status_text_187('پیام', 3, 9, 6, verb='افزودن').startswith('افزودن پیام ۳ از ۹')
