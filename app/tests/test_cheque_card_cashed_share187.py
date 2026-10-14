"""The cheques card of the dashboard fills with the share of cashed cheques in all cheques."""
import tkinter as tk
from types import SimpleNamespace

from test_transaction_lifecycle_matrix import m  # noqa: F401
from test_stage18_7_record_fields import root  # noqa: F401


def _bar(root, open_total, all_total):
    cards = {'ch_open_total': SimpleNamespace(var=tk.StringVar(root, open_total)),
             'ch_all_total': SimpleNamespace(var=tk.StringVar(root, all_total))}
    canvas = tk.Canvas(root, width=300, height=14, bg='#101820')
    canvas.pack()
    caption = tk.Label(root)
    caption.pack()
    root.update()
    metric = SimpleNamespace(_kpi_bar187=(canvas, caption, m.Stage187Dashboard._KPI_RATIOS_187['ch_all_total']))
    m.Stage187Dashboard._draw_kpi_bar_187(SimpleNamespace(cards=cards), metric)
    lit = [item for item in canvas.find_all() if canvas.itemcget(item, 'fill') == m.palette_187()['accent']]
    return str(caption.cget('text')), len(lit)


def test_the_cheques_card_shows_the_cashed_share_not_the_open_share(root):
    text, lit = _bar(root, '۴۰۰', '۱٬۰۰۰')  # 400 of 1000 still open: 60% cashed
    assert text.startswith('۶۰٪') and 'پاس‌شده' in text
    assert lit == 12  # one block per 5%


def test_all_cheques_cashed_fills_the_bar_and_none_cashed_leaves_it_empty(root):
    assert _bar(root, '۰', '۱٬۰۰۰')[1] == 20
    text, lit = _bar(root, '۱٬۰۰۰', '۱٬۰۰۰')
    assert text.startswith('۰٪') and lit == 0
