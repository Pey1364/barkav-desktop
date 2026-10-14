from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from pathlib import Path

from ui_stage18_3 import *  # re-export stable 18.3 helpers
import ui_stage18_3 as v183ui


def attach_tree_grid_184(tree: ttk.Treeview, *, light: bool=False):
    """18.4 grid: horizontal row separators remain readable; verticals are intentionally very faint."""
    # A barkav_ui.table.DataTable already decided its own grid, its own
    # row colours and its own headings - see barkav_ui/table.py. This is
    # one of four generations of the same blanket pass (18.4/18.5/18.6),
    # each written before that kit existed, and each still walks every
    # Treeview in the window. The flag is the one thing they all check.
    if getattr(tree,'_barkav_kit_table_187',False): return getattr(tree,'_barkav_grid_overlay',None)
    old=getattr(tree,'_barkav_grid_overlay',None)
    column='#EEF1F4' if light else '#122436'
    row='#BAC6D2' if light else '#47617A'
    header='#9FAFBD' if light else '#587895'
    if old:
        try:
            old.column_color=column; old.row_color=row; old.header_color=header; old.schedule()
        except Exception: pass
        return old
    ov=v183ui.TreeGridOverlay(tree,column_color=column,row_color=row,header_color=header)
    tree._barkav_grid_overlay=ov
    return ov


def enable_tree_checkboxes(tree: ttk.Treeview):
    """Give any Treeview a Data-Entry-like checkbox selection column without touching its values tuple.

    Uses ttk's #0 tree column, so existing code that indexes item(values) remains 100% compatible.
    """
    if getattr(tree,'_barkav_checkboxes_184',False): return tree
    if getattr(tree,'_barkav_kit_table_187',False): return tree
    # PendingTable already owns a dedicated checkbox/value column and click behavior.
    parent=getattr(tree,'master',None)
    if parent is not None and hasattr(parent,'toggle_all') and hasattr(parent,'_sync_checks'):
        return tree
    try:
        show=str(tree.cget('show') or '')
        tokens=set(show.split())
        tokens.update(('tree','headings'))
        tree.configure(show='tree headings')
        tree.heading('#0',text='☐',anchor='center')
        tree.column('#0',width=46,minwidth=42,stretch=False,anchor='center')
    except Exception:
        return tree

    def sync(*_):
        try:
            selected=set(tree.selection()); kids=tree.get_children('')
            for iid in kids: tree.item(iid,text='☑' if iid in selected else '☐')
            tree.heading('#0',text='☑' if kids and len(selected)==len(kids) else '☐')
        except Exception: pass

    def toggle_all():
        try:
            kids=tree.get_children(''); sel=tree.selection()
            if kids and len(sel)==len(kids): tree.selection_remove(sel)
            else: tree.selection_set(kids)
            sync()
        except Exception: pass

    def click(ev):
        try:
            if tree.identify_column(ev.x)!='#0':
                tree.after_idle(sync); return None
            iid=tree.identify_row(ev.y)
            if not iid: return 'break'
            sel=set(tree.selection())
            if iid in sel: tree.selection_remove(iid)
            else: tree.selection_add(iid)
            tree.focus(iid); sync(); return 'break'
        except Exception:
            return None

    try: tree.heading('#0',command=toggle_all)
    except Exception: pass
    tree.bind('<Button-1>',click,add='+')
    tree.bind('<<TreeviewSelect>>',lambda e:sync(),add='+')
    tree.bind('<Configure>',lambda e:tree.after_idle(sync),add='+')
    tree._barkav_checkboxes_184=True; tree._barkav_checkbox_sync=sync
    tree.after_idle(sync)
    return tree


def attach_table_visuals_recursive(root: tk.Misc, *, light: bool=False):
    stack=[root]
    while stack:
        w=stack.pop()
        try: stack.extend(w.winfo_children())
        except Exception: pass
        if isinstance(w,ttk.Treeview):
            attach_tree_grid_184(w,light=light)
            enable_tree_checkboxes(w)


def retarget_smarttable_instance_184(table, *, font_size: int=11, light: bool=False):
    """Keep legacy SmartTable behavior but make its font/numbers/check selection match 18.4."""
    if getattr(table,'_barkav_184_upgraded',False):
        try:
            attach_tree_grid_184(table.tree,light=light); enable_tree_checkboxes(table.tree)
        except Exception: pass
        return table
    tree=getattr(table,'tree',None)
    if not isinstance(tree,ttk.Treeview): return table
    try:
        st=ttk.Style(table)
        if getattr(table,'style_name',None): st.configure(table.style_name,font=('Segoe UI',font_size),rowheight=max(34,int(getattr(table,'row_height',34))))
        if getattr(table,'heading_style_name',None): st.configure(table.heading_style_name,font=('Segoe UI',max(9,font_size-1),'bold'))
    except Exception: pass

    # Wrap per-instance methods. This avoids changing any business/service code.
    orig_update=getattr(table,'_update_total',None)
    if callable(orig_update):
        def update_total_184(*a,**kw):
            res=orig_update(*a,**kw)
            try: table.total.set(fa(table.total.get()))
            except Exception: pass
            try:
                for iid in tree.get_children(''):
                    vals=list(tree.item(iid,'values') or ())
                    if vals: tree.item(iid,values=[fa(v) for v in vals])
            except Exception: pass
            try: tree.after_idle(tree._barkav_checkbox_sync)
            except Exception: pass
            return res
        table._update_total=update_total_184

    orig_apply=getattr(table,'apply_filter',None)
    if callable(orig_apply):
        def apply_filter_184(*a,**kw):
            res=orig_apply(*a,**kw)
            try:
                for iid in tree.get_children(''):
                    vals=list(tree.item(iid,'values') or ())
                    if vals: tree.item(iid,values=[fa(v) for v in vals])
            except Exception: pass
            try: table.total.set(fa(table.total.get()))
            except Exception: pass
            try: tree.after_idle(tree._barkav_checkbox_sync)
            except Exception: pass
            return res
        table.apply_filter=apply_filter_184

    orig_height=getattr(table,'change_row_height',None)
    if callable(orig_height):
        def change_row_height_184(delta):
            res=orig_height(delta)
            try:
                st=ttk.Style(table)
                if getattr(table,'style_name',None): st.configure(table.style_name,font=('Segoe UI',font_size))
                if getattr(table,'heading_style_name',None): st.configure(table.heading_style_name,font=('Segoe UI',max(9,font_size-1),'bold'))
            except Exception: pass
            return res
        table.change_row_height=change_row_height_184

    attach_tree_grid_184(tree,light=light); enable_tree_checkboxes(tree)
    table._barkav_184_upgraded=True
    try: table._update_total()
    except Exception: pass
    return table


def upgrade_smarttables_recursive_184(root: tk.Misc, *, font_size: int=11, light: bool=False):
    stack=[root]
    while stack:
        w=stack.pop()
        try: stack.extend(w.winfo_children())
        except Exception: pass
        if hasattr(w,'tree') and hasattr(w,'set_rows'):
            try: retarget_smarttable_instance_184(w,font_size=font_size,light=light)
            except Exception: pass


def build_brand_widget_184(parent, source: str|Path, *, bg: str, fg: str, compact: bool=False):
    """Theme-blended BARKAV brand with a larger readable Engineering & Construction line."""
    host=tk.Frame(parent,bg=bg,bd=0,highlightthickness=0)
    try:
        from PIL import Image, ImageTk
        im=Image.open(source).convert('RGBA')
        # Crop away the tiny source tagline; render it ourselves at a readable size.
        crop_h=max(1,int(im.height*0.82)); im=im.crop((0,0,im.width,crop_h))
        # Theme recolor, preserving antialiasing.
        fr,fgc,fb=tuple(int(fg[i:i+2],16) for i in (1,3,5)); px=im.load()
        for y in range(im.height):
            for x in range(im.width):
                r,g,b,a=px[x,y]; lum=(r+g+b)//3
                if lum>242: px[x,y]=(0,0,0,0)
                else: px[x,y]=(fr,fgc,fb,max(0,min(255,255-lum)))
        im.thumbnail((220 if compact else 245,43 if compact else 49),Image.Resampling.LANCZOS)
        photo=ImageTk.PhotoImage(im,master=parent);host._brand_photo=photo
        tk.Label(host,image=photo,bg=bg,bd=0).pack(anchor='w')
    except Exception:
        tk.Label(host,text='BARKAV',bg=bg,fg=fg,font=('Segoe UI',15,'bold')).pack(anchor='w')
    tk.Label(host,text='Engineering & Construction',bg=bg,fg=fg,
             font=('Segoe UI',9 if compact else 10,'bold')).pack(anchor='w',pady=(0,1))
    return host
