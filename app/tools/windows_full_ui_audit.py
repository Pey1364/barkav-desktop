r"""Capture every dashboard tab and visible nested tab on real Windows Tk.

The audit always uses a disposable SQLite database.  It records widget fonts,
table alignment/styles, tab hierarchy, and button labels next to each current
Windows screenshot so visual standardisation is based on rendered evidence.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def _walk(root):
    yield root
    for child in root.winfo_children():
        yield from _walk(child)


def _text(widget) -> str:
    try:
        return str(widget.cget("text") or "")
    except Exception:
        return ""


def _font(widget) -> dict[str, Any] | None:
    import tkinter.font as tkfont

    try:
        if "font" not in widget.keys():
            return None
        value = str(widget.cget("font") or "")
        if not value:
            return None
        actual = tkfont.Font(root=widget, font=value).actual()
        return {
            "family": str(actual.get("family") or ""),
            "size": int(actual.get("size") or 0),
            "weight": str(actual.get("weight") or ""),
            "slant": str(actual.get("slant") or ""),
        }
    except Exception:
        return None


def _widget_path(widget, stop) -> str:
    parts: list[str] = []
    current = widget
    while current is not None and current is not stop:
        parts.append(str(current.winfo_name()))
        current = getattr(current, "master", None)
    return "/".join(reversed(parts))


def _table_snapshot(tree) -> dict[str, Any]:
    columns = list(tree.cget("columns"))
    display = list(tree.cget("displaycolumns"))
    return {
        "path": _widget_path(tree, tree.winfo_toplevel()),
        "style": str(tree.cget("style") or ""),
        "show": str(tree.cget("show") or ""),
        "columns": columns,
        "displaycolumns": display,
        "column_anchors": {name: str(tree.column(name, "anchor")) for name in columns},
        "heading_anchors": {name: str(tree.heading(name, "anchor")) for name in columns},
        "row_count": len(tree.get_children("")),
        "even_background": str(tree.tag_configure("even").get("background") or ""),
        "odd_background": str(tree.tag_configure("odd").get("background") or ""),
        "row_tags": [list(tree.item(item, "tags") or ()) for item in tree.get_children("")],
        "xscrollcommand": str(tree.cget("xscrollcommand") or ""),
        "yscrollcommand": str(tree.cget("yscrollcommand") or ""),
    }


def _notebook_snapshot(notebook) -> dict[str, Any]:
    strip = getattr(notebook, "_barkav_rtl_strip", None)
    return {
        "path": _widget_path(notebook, notebook.winfo_toplevel()),
        "style": str(notebook.cget("style") or ""),
        "tabs": [str(notebook.tab(tab_id, "text") or "") for tab_id in notebook.tabs()],
        "strip_class": type(strip).__name__ if strip is not None else "",
    }


def _screen_snapshot(app, path: list[str]) -> dict[str, Any]:
    import tkinter as tk
    from tkinter import ttk

    visible = [widget for widget in _walk(app) if widget.winfo_ismapped()]
    fonts: list[dict[str, Any]] = []
    buttons: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    notebooks: list[dict[str, Any]] = []
    for widget in visible:
        spec = _font(widget)
        if spec:
            fonts.append({
                "class": widget.winfo_class(),
                "text": _text(widget),
                "path": _widget_path(widget, app),
                **spec,
            })
        if isinstance(widget, (tk.Button, ttk.Button, tk.Menubutton, ttk.Menubutton)):
            try:
                command = str(widget.cget("command") or "")
            except tk.TclError:
                command = ""
            buttons.append({
                "text": _text(widget),
                "class": widget.winfo_class(),
                "path": _widget_path(widget, app),
                "command": command,
            })
        if isinstance(widget, ttk.Treeview):
            tables.append(_table_snapshot(widget))
        if isinstance(widget, ttk.Notebook):
            notebooks.append(_notebook_snapshot(widget))
    families = Counter(item["family"] for item in fonts if item["family"])
    return {
        "path": path,
        "font_families": dict(families),
        "fonts": fonts,
        "tables": tables,
        "notebooks": notebooks,
        "buttons": buttons,
    }


def _capture(app, destination: Path) -> None:
    from PIL import ImageGrab

    app.lift()
    try:
        app.focus_force()
    except Exception:
        pass
    app.update_idletasks()
    app.update()
    time.sleep(0.18)
    # Capture this Tk HWND directly. A screen-coordinate grab can silently
    # capture another BARKAV window that overlaps the audit fixture.
    ImageGrab.grab(window=int(app.winfo_id()), include_layered_windows=True).save(destination)


def _settle(app) -> None:
    app.update_idletasks()
    app.update()
    time.sleep(0.12)
    app.update_idletasks()
    app.update()


def _selected_page(notebook):
    selected = notebook.select()
    return notebook.nametowidget(selected) if selected else None


def _direct_nested_notebooks(page, ttk) -> list[Any]:
    if page is None:
        return []
    found: list[Any] = []
    stack = list(page.winfo_children())
    while stack:
        widget = stack.pop()
        if isinstance(widget, ttk.Notebook):
            if widget.winfo_ismapped() and widget.tabs():
                found.append(widget)
            continue
        stack.extend(widget.winfo_children())
    return found


def _run(output: Path) -> dict[str, Any]:
    from tkinter import ttk

    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("TELEGRAM_BOT_TOKEN", "full-ui-audit-token")
    os.environ.setdefault("GEMINI_API_KEY", "full-ui-audit-gemini")
    os.environ.setdefault("ADMIN_USER_ID", "187")
    os.environ.setdefault("GROUP_CHAT_ID", "-100187")

    with tempfile.TemporaryDirectory(prefix="barkav-full-ui-audit-") as directory:
        database = Path(directory) / "audit.sqlite3"
        os.environ["STAGE4_DB_PATH"] = str(database)

        import dashboard_stage18_7 as dashboard
        from tools.windows_gui_acceptance import _seed_sales

        dashboard.v186.v185.fetch_tgju_usd_toman = (
            lambda timeout=6.0: (70_000, "2026-09-02T00:00:00")
        )
        _seed_sales(dashboard.DB)
        app = dashboard.Stage187Dashboard()
        app.geometry("1366x768+0+0")
        try:
            app.state("zoomed")
        except Exception:
            pass
        _settle(app)
        app.unify_appearance_187()
        _settle(app)

        screens: list[dict[str, Any]] = []
        index = 0

        def save(path: list[str]) -> None:
            nonlocal index
            index += 1
            image = output / f"{index:02d}.png"
            _capture(app, image)
            snapshot = _screen_snapshot(app, path)
            snapshot["screenshot"] = str(image.resolve())
            screens.append(snapshot)

        def capture_nested(page, path: list[str]) -> None:
            for notebook in _direct_nested_notebooks(page, ttk):
                for tab_id in notebook.tabs():
                    notebook.select(tab_id)
                    _settle(app)
                    label = str(notebook.tab(tab_id, "text") or "زیرتب")
                    nested_path = [*path, label]
                    save(nested_path)
                    capture_nested(_selected_page(notebook), nested_path)

        main = app.notebook
        for main_tab in main.tabs():
            main.select(main_tab)
            _settle(app)
            main_label = str(main.tab(main_tab, "text") or f"main-{len(screens) + 1}")
            save([main_label])
            capture_nested(_selected_page(main), [main_label])

        report = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "title": app.title(),
            "screen_count": len(screens),
            "screens": screens,
        }
        app.destroy()
        return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output")
    args = parser.parse_args()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output = Path(args.output).resolve() if args.output else ROOT / "runtime" / "full_ui_audit" / stamp
    output.mkdir(parents=True, exist_ok=True)
    report = _run(output)
    report_path = output / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"FULL_UI_AUDIT_REPORT={report_path.resolve()}")
    print(f"SCREENS={report['screen_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
