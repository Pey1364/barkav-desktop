from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'project_center_stage18_7.py').read_text(encoding='utf-8')


class ProjectCenter188BatchTests(unittest.TestCase):
    def test_header_layout_and_title_contract(self):
        self.assertIn("text='مرکز پروژه'", SOURCE)
        self.assertNotIn("text='مرکز پروژه‌ها'", SOURCE)
        self.assertNotIn("text='بروزرسانی'", SOURCE)
        self.assertNotIn('پروژه‌ها در تب‌های مستقل مدیریت می‌شوند', SOURCE)
        self.assertIn("style.configure('ProjectCenter187.TNotebook.Tab', anchor='e')", SOURCE)
        self.assertIn("self.overrideredirect(False)", SOURCE)

    def test_project_card_metrics_and_progress_contract(self):
        for label in ('تعداد طبقه', 'تعداد واحد', 'هزینه کل ساخت', 'نمودار پیشرفت', 'فاز در حال اجرا'):
            self.assertIn(f"('{label}',", SOURCE) if label in ('تعداد طبقه', 'تعداد واحد', 'هزینه کل ساخت') else self.assertIn(f"text='{label}'", SOURCE)
        self.assertIn('def _project_summary', SOURCE)
        self.assertIn("sqlite3.connect(db_path.resolve().as_uri() + '?mode=ro', uri=True)", SOURCE)
        self.assertIn("result['progress']", SOURCE)

    def test_progress_panel_does_not_render_phase_count_or_detail(self):
        panel = SOURCE.split("text='فاز در حال اجرا'", 1)[1].split("foot =", 1)[0]
        self.assertNotIn('تعداد فاز', panel)
        self.assertNotIn('phase_name', panel)
        self.assertNotIn('phase_detail', panel)

    def test_project_selector_stays_outside_scrollable_view(self):
        self.assertIn("text='انتخاب پروژه'", SOURCE)
        self.assertIn('self.project_selector = ttk.Combobox', SOURCE)
        self.assertIn("self.project_selector.bind('<<ComboboxSelected>>'", SOURCE)
        self.assertIn('self._selector_project_ids', SOURCE)
        self.assertIn('scrollbar = ttk.Scrollbar', SOURCE)
        self.assertIn("widget.bind('<MouseWheel>'", SOURCE)
        self.assertIn('canvas.configure(yscrollcommand=scrollbar.set)', SOURCE)
        self.assertEqual(SOURCE.count('ttk.Notebook('), 1)

    def test_project_center_03_two_rtl_info_boxes_and_real_wheel_bindings(self):
        self.assertIn("self.nb.configure(tabposition='ne')", SOURCE)
        self.assertIn("info_grid.grid_columnconfigure((0, 1), weight=1, uniform='project_info_box')", SOURCE)
        self.assertIn("box.grid(row=0, column=1 - box_index", SOURCE)
        self.assertIn("widget.bind('<Button-4>', scroll", SOURCE)
        self.assertIn("widget.bind('<Button-5>', scroll", SOURCE)
        self.assertIn('def bind_scroll(widget):', SOURCE)

    def test_tray_request_is_explicitly_not_faked(self):
        self.assertNotIn('pystray', SOURCE.lower())
        self.assertNotIn('win32gui', SOURCE.lower())

    def test_project_center_launches_maximized_without_fullscreen(self):
        self.assertIn("self.state('zoomed')", SOURCE)
        self.assertIn("self.attributes('-zoomed', True)", SOURCE)
        self.assertNotIn("self.attributes('-fullscreen'", SOURCE)


if __name__ == '__main__':
    unittest.main()
