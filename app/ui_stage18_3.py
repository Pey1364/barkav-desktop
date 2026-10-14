from __future__ import annotations

import re
import threading
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Any
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

FA_DIGITS = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')
EN_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')


def fa(value: Any) -> str:
    return str(value if value is not None else '').translate(FA_DIGITS)


def en(value: Any) -> str:
    return str(value if value is not None else '').translate(EN_DIGITS)

def persianize_var(var: tk.StringVar) -> None:
    # ارقام ورودی در کنترل‌های ویزارد به شکل فارسی نمایش داده شوند.
    def _on_change(*_args) -> None:
        current = var.get()
        converted = fa(current)
        if converted != current:
            var.set(converted)
    _on_change()
    var.trace_add('write', _on_change)


def _clean_int(value: Any) -> str:
    s = en(value).replace(',', '').replace('٬', '').replace('،', '').strip()
    return re.sub(r'[^0-9\-]', '', s)


def parse_int(value: Any, default: int = 0) -> int:
    s = _clean_int(value)
    if s in ('', '-'): return default
    try: return int(s)
    except Exception: return default


def group_int_fa(value: Any, blank_zero: bool = False) -> str:
    try:
        raw = _clean_int(value)
        n = int(raw or 0)
        if blank_zero and n == 0: return ''
        return fa(f'{n:,}')
    except Exception:
        return fa(value)


def _clean_decimal(value: Any) -> str:
    s = en(value).replace(',', '').replace('٬', '').replace('،', '').replace('٫', '.').strip()
    s = re.sub(r'[^0-9.\-]', '', s)
    sign = '-' if s.startswith('-') else ''
    s = s.replace('-', '')
    if '.' in s:
        head, tail = s.split('.', 1)
        return sign + head + '.' + tail.replace('.', '')
    return sign + s


def parse_decimal(value: Any, default: float = 0.0) -> float:
    s = _clean_decimal(value)
    if s in ('', '-', '.', '-.'): return default
    try: return float(s)
    except Exception: return default


def group_decimal_fa(value: Any) -> str:
    raw = _clean_decimal(value)
    if raw in ('', '-', '.', '-.'):
        return fa(raw)
    neg = raw.startswith('-'); unsigned = raw[1:] if neg else raw
    if '.' in unsigned:
        whole, frac = unsigned.split('.', 1); dot = True
    else:
        whole, frac, dot = unsigned, '', False
    try: grouped = f'{int(whole or 0):,}'
    except Exception: return fa(value)
    out = ('-' if neg else '') + grouped + ('.' + frac if dot else '')
    return fa(out)


def _preserve_caret(entry: ttk.Entry, old: str, new: str) -> None:
    try: caret = int(entry.index(tk.INSERT))
    except Exception: caret = len(old)
    right_digits = sum(ch.isdigit() for ch in old[caret:])
    pos = len(new)
    if right_digits:
        seen = 0
        for idx in range(len(new)-1, -1, -1):
            if new[idx].isdigit():
                seen += 1
                if seen >= right_digits:
                    pos = idx
                    break
    try: entry.icursor(pos)
    except Exception: pass


def bind_grouped_number_fa(entry: ttk.Entry, var: tk.StringVar, *, allow_negative: bool = False) -> None:
    busy = {'v': False}
    def normalize(*_):
        if busy['v']: return
        raw = _clean_int(var.get())
        if not allow_negative: raw = raw.lstrip('-')
        if raw in ('', '-'):
            target = fa(raw)
        else:
            try: target = fa(f'{int(raw):,}')
            except Exception: return
        old = str(var.get() or '')
        if old == target: return
        busy['v'] = True
        try:
            var.set(target); _preserve_caret(entry, old, target)
        finally: busy['v'] = False
    try: var.trace_add('write', normalize)
    except Exception: entry.bind('<KeyRelease>', normalize, add='+')
    entry.bind('<FocusOut>', normalize, add='+'); entry.bind('<Return>', normalize, add='+')


def bind_grouped_decimal_fa(entry: ttk.Entry, var: tk.StringVar, *, allow_negative: bool = False) -> None:
    busy = {'v': False}
    def normalize(*_):
        if busy['v']: return
        raw = _clean_decimal(var.get())
        if not allow_negative: raw = raw.lstrip('-')
        if raw in ('', '-', '.', '-.'):
            target = fa(raw)
        else:
            target = group_decimal_fa(raw)
        old = str(var.get() or '')
        if old == target: return
        busy['v'] = True
        try:
            var.set(target); _preserve_caret(entry, old, target)
        finally: busy['v'] = False
    try: var.trace_add('write', normalize)
    except Exception: entry.bind('<KeyRelease>', normalize, add='+')
    entry.bind('<FocusOut>', normalize, add='+'); entry.bind('<Return>', normalize, add='+')


def widget_notebook_path(widget: tk.Misc) -> list[str]:
    """Return tab labels for notebook ancestors, inner to outer."""
    out=[]; w=widget
    while True:
        try: parent=w.master
        except Exception: break
        if parent is None: break
        if isinstance(parent, ttk.Notebook):
            try: out.append(str(parent.tab(w, 'text')))
            except Exception: pass
        w=parent
    return out


class RtlNotebookStrip:
    """Right-aligned themed button strip controlling an existing hidden Notebook."""
    def __init__(self, notebook: ttk.Notebook, *, bg: str, line: str, text: str, muted: str,
                 active_bg: str, active_fg: str, font=('Segoe UI', 10, 'bold')):
        self.notebook=notebook; self.buttons={}; self.colors=(bg,line,text,muted,active_bg,active_fg); self.font=font
        style=ttk.Style(notebook)
        style.configure('BarkavRtlHidden.TNotebook', background=bg, borderwidth=0, tabmargins=0)
        try: style.layout('BarkavRtlHidden.TNotebook.Tab', [])
        except Exception: pass
        notebook.configure(style='BarkavRtlHidden.TNotebook')
        self.bar=tk.Frame(notebook.master,bg=bg,highlightbackground=line,highlightthickness=1,height=48)
        try: self.bar.pack(fill='x',pady=(0,4),before=notebook)
        except Exception: self.bar.pack(fill='x',pady=(0,4))
        self.bar.pack_propagate(False)
        self.rebuild()
        notebook.bind('<<NotebookTabChanged>>',lambda e:self.sync(),add='+')

    def rebuild(self):
        bg,line,text,muted,active_bg,active_fg=self.colors
        for w in self.bar.winfo_children(): w.destroy()
        self.buttons.clear()
        # Existing logical order: first tab becomes right-most in RTL.
        for tid in self.notebook.tabs():
            label=str(self.notebook.tab(tid,'text'))
            b=tk.Button(self.bar,text=label,command=lambda t=tid:self.notebook.select(t),
                        bg=bg,fg=muted,activebackground=active_bg,activeforeground=active_fg,
                        relief='flat',bd=0,highlightbackground=line,highlightthickness=1,
                        font=self.font,padx=18,pady=7,cursor='hand2')
            b.pack(side='right',fill='y',padx=2,pady=4); self.buttons[str(tid)]=b
        self.sync()

    def sync(self):
        bg,line,text,muted,active_bg,active_fg=self.colors
        try: sel=str(self.notebook.select())
        except Exception: sel=''
        for tid,b in self.buttons.items():
            active=tid==sel
            try: b.configure(bg=active_bg if active else bg, fg=active_fg if active else muted,
                             relief='raised' if active else 'flat', bd=1 if active else 0)
            except Exception: pass


class TreeGridOverlay:
    """Visible cell grid for ttk.Treeview without replacing the Treeview data model.

    Vertical column separators are deliberately softer than horizontal row separators.
    """
    def __init__(self, tree: ttk.Treeview, *, column_color: str, row_color: str, header_color: str | None=None):
        self.tree=tree; self.column_color=column_color; self.row_color=row_color; self.header_color=header_color or row_color
        self.vlines=[]; self.hlines=[]; self._dead=False
        for ev in ('<Configure>','<MouseWheel>','<ButtonRelease-1>','<KeyRelease>','<<TreeviewSelect>>'):
            tree.bind(ev,lambda e:self.schedule(),add='+')
        self.schedule()

    def _line(self, pool, idx, color):
        while len(pool)<=idx:
            pool.append(tk.Frame(self.tree,bg=color,bd=0,highlightthickness=0))
        w=pool[idx]
        try: w.configure(bg=color)
        except Exception: pass
        return w

    def schedule(self):
        if self._dead: return
        try: self.tree.after_idle(self.update)
        except Exception: self._dead=True

    def update(self):
        try:
            if not self.tree.winfo_exists(): self._dead=True; return
            width=max(1,self.tree.winfo_width()); height=max(1,self.tree.winfo_height())
            display=self.tree.cget('displaycolumns')
            if display in ('#all', ('#all',), ''): display=list(self.tree.cget('columns'))
            else: display=list(display)
            kids=list(self.tree.get_children())
            visible=[]
            for iid in kids:
                try:
                    bb=self.tree.bbox(iid)
                    if bb and bb[1]+bb[3]>=0 and bb[1]<=height: visible.append(iid)
                except Exception: pass
            sample=visible[0] if visible else (kids[0] if kids else None)
            vused=0
            if sample:
                for col in display[:-1]:
                    try: bb=self.tree.bbox(sample,col)
                    except Exception: bb=''
                    if not bb: continue
                    x=bb[0]+bb[2]-1
                    if 0 < x < width:
                        ln=self._line(self.vlines,vused,self.column_color); ln.place(x=x,y=0,width=1,height=height); vused+=1
            for ln in self.vlines[vused:]: ln.place_forget()
            hused=0
            # Header/data boundary from first visible row's y position.
            if visible:
                try:
                    bb=self.tree.bbox(visible[0])
                    if bb and bb[1]>1:
                        ln=self._line(self.hlines,hused,self.header_color); ln.place(x=0,y=max(0,bb[1]-2),width=width,height=2); hused+=1
                except Exception: pass
            for iid in visible:
                try: bb=self.tree.bbox(iid)
                except Exception: bb=''
                if not bb: continue
                y=bb[1]+bb[3]-2
                if 0<y<height:
                    ln=self._line(self.hlines,hused,self.row_color); ln.place(x=0,y=y,width=width,height=2); hused+=1
            for ln in self.hlines[hused:]: ln.place_forget()
        except Exception:
            return
        try: self.tree.after(350,self.update)
        except Exception: self._dead=True


def attach_tree_grid(tree: ttk.Treeview, *, light: bool=False):
    if getattr(tree, '_barkav_line_free_187', False):
        old = getattr(tree, '_barkav_grid_overlay', None)
        if old is not None:
            old._dead = True
            for line in list(getattr(old, 'vlines', [])) + list(getattr(old, 'hlines', [])):
                line.destroy()
        tree._barkav_grid_overlay = None
        return None
    # A barkav_ui.table.DataTable already decided its own grid - see
    # barkav_ui/table.py. This is the oldest of five generations of the same
    # blanket pass (18.3 through 18.7), each written before that kit existed,
    # and each still walks every Treeview in the window on every refresh.
    if getattr(tree,'_barkav_kit_table_187',False): return getattr(tree,'_barkav_grid_overlay',None)
    old=getattr(tree,'_barkav_grid_overlay',None)
    if old: return old
    ov=TreeGridOverlay(tree,
        column_color='#D7DEE6' if light else '#29415A',
        row_color='#B8C5D2' if light else '#47617A',
        header_color='#9FB1C2' if light else '#587895')
    tree._barkav_grid_overlay=ov
    return ov


def attach_grids_recursive(root: tk.Misc, *, light: bool=False):
    stack=[root]
    while stack:
        w=stack.pop()
        try: stack.extend(w.winfo_children())
        except Exception: pass
        if isinstance(w,ttk.Treeview): attach_tree_grid(w,light=light)


def install_smarttable_export_dropdown(table, *, values=('انتخاب فرمت خروجی','پرینت','Excel','PDF')):
    """Replace the three legacy output icon buttons in one SmartTable toolbar."""
    if getattr(table,'_barkav_export_combo',None): return table._barkav_export_combo
    try: bar=table.winfo_children()[0]
    except Exception: return None
    for w in list(bar.winfo_children()):
        try:
            if isinstance(w,ttk.Button) and str(w.cget('text')) in {'📊','📄','🖨'}: w.destroy()
        except Exception: pass
    var=tk.StringVar(master=table,value=values[0])
    combo=ttk.Combobox(bar,textvariable=var,state='readonly',values=list(values),width=19,justify='right')
    combo.pack(side='left',padx=3)
    def chosen(_=None):
        val=var.get()
        try:
            if val=='Excel': table.export_excel()
            elif val=='PDF': table.export_pdf()
            elif val=='پرینت': table.print_report()
        finally:
            try: var.set(values[0])
            except Exception: pass
    combo.bind('<<ComboboxSelected>>',chosen,add='+')
    table._barkav_export_combo=combo; table._barkav_export_var=var
    return combo


def themed_brand_image(source: str | Path, *, fg: str, bg: str, size=(250,58)):
    """Return PIL RGBA image recolored to theme; caller creates ImageTk.PhotoImage."""
    from PIL import Image
    im=Image.open(source).convert('RGBA')
    # Convert original white background to transparent and dark logo pixels to requested foreground.
    fr,fgc,fb = tuple(int(fg[i:i+2],16) for i in (1,3,5))
    px=im.load()
    for y in range(im.height):
        for x in range(im.width):
            r,g,b,a=px[x,y]
            lum=(r+g+b)//3
            if lum>242:
                px[x,y]=(0,0,0,0)
            else:
                # preserve antialiasing using darkness as alpha
                alpha=max(0,min(255,255-lum))
                px[x,y]=(fr,fgc,fb,alpha)
    im.thumbnail(size,Image.Resampling.LANCZOS)
    return im


TGJU_DOLLAR_URL='https://www.tgju.org/profile/price_dollar_rl'


def fetch_tgju_usd_toman(timeout: float=8.0) -> tuple[int,str]:
    """Fetch free USD rate from TGJU. TGJU page states the value in IRR; return toman."""
    req=urllib.request.Request(TGJU_DOLLAR_URL,headers={
        'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 BARKAV/18.3',
        'Accept-Language':'fa-IR,fa;q=0.9,en;q=0.6',
    })
    with urllib.request.urlopen(req,timeout=timeout) as resp:
        html=resp.read().decode('utf-8','ignore')
    # Stable profile fragments seen on the official page. Try several forms so minor markup shifts don't break it.
    patterns=[
        r'نرخ\s*فعلی\s*</[^>]+>\s*<[^>]+>\s*([0-9۰-۹٠-٩,٬]+)',
        r'نرخ\s*فعلی\s*[:：]*\s*</?[^>]*>\s*([0-9۰-۹٠-٩,٬]{5,})',
        r'در\s*حال\s*حاضر\s*قیمت\s*هر\s*دلار\s*([0-9۰-۹٠-٩,٬]+)\s*ریال',
        r'نرخ\s*فعلی\s*[:：]+\s*([0-9۰-۹٠-٩,٬]{5,})',
    ]
    raw=''
    for pat in patterns:
        m=re.search(pat,html,re.I|re.S)
        if m: raw=m.group(1); break
    if not raw:
        # Extract text by stripping tags and use the same official wording.
        text=re.sub(r'<[^>]+>',' ',html); text=re.sub(r'\s+',' ',text)
        m=re.search(r'نرخ فعلی\s*[:：]*\s*([0-9۰-۹٠-٩,٬]{5,})',text)
        if not m: m=re.search(r'در حال حاضر قیمت هر دلار\s*([0-9۰-۹٠-٩,٬]+)\s*ریال',text)
        if m: raw=m.group(1)
    rial=parse_int(raw)
    if rial<=0: raise ValueError('نرخ فعلی دلار در صفحه TGJU پیدا نشد.')
    toman=round(rial/10)
    return toman, datetime.now().isoformat(timespec='seconds')
