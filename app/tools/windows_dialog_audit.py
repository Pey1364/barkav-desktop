r"""Open and visually audit every distinct app-owned dialog family on Windows.

The fixture uses a disposable SQLite database and never presses a dialog's
Save/Delete/Export actions.  Each opened window is captured by its own HWND,
measured against the live 18.7.1 font/table/tab contract, then destroyed.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]


def _walk(root):
    yield root
    for child in root.winfo_children():
        yield from _walk(child)


def _settle(root) -> None:
    for _ in range(3):
        root.update_idletasks()
        root.update()
        time.sleep(0.08)


def _capture(window, destination: Path) -> None:
    from PIL import ImageGrab

    window.deiconify()
    window.lift()
    try:
        window.focus_force()
    except Exception:
        pass
    _settle(window)
    ImageGrab.grab(window=int(window.winfo_id()), include_layered_windows=True).save(destination)


def _snapshot(window, expected_family: str) -> dict[str, Any]:
    import tkinter.font as tkfont
    from tkinter import ttk
    from barkav_ui.tabs import TabStrip

    fonts: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    notebooks: list[dict[str, Any]] = []
    issues: list[str] = []
    for widget in _walk(window):
        try:
            if "font" in widget.keys() and str(widget.cget("font") or ""):
                actual = tkfont.Font(root=window, font=widget.cget("font")).actual()
                fonts.append({
                    "class": widget.winfo_class(),
                    "text": str(widget.cget("text") or "") if "text" in widget.keys() else "",
                    "family": str(actual.get("family") or ""),
                    "size": int(actual.get("size") or 0),
                })
        except Exception:
            pass
        if isinstance(widget, ttk.Treeview):
            columns = tuple(widget.cget("columns") or ())
            anchors = {
                column: {
                    "heading": str(widget.heading(column, "anchor")),
                    "cell": str(widget.column(column, "anchor")),
                }
                for column in columns
            }
            rows = tuple(widget.get_children(""))
            row_tags = [list(widget.item(item, "tags") or ()) for item in rows]
            table = {
                "style": str(widget.cget("style") or ""),
                "anchors": anchors,
                "row_tags": row_tags,
                "xscrollcommand": str(widget.cget("xscrollcommand") or ""),
                "yscrollcommand": str(widget.cget("yscrollcommand") or ""),
            }
            tables.append(table)
            if table["style"] != "Barkav.Data.Treeview":
                issues.append("table style")
            if any(pair[axis] != "e" for pair in anchors.values() for axis in ("heading", "cell")):
                issues.append("table alignment")
            if not table["xscrollcommand"] or not table["yscrollcommand"]:
                issues.append("table scrollbars")
            if any(not ({"even", "odd", "pending", "approved", "rejected"} & set(tags))
                   for tags in row_tags):
                issues.append("row stripes")
        if isinstance(widget, ttk.Notebook) and len(widget.tabs()) >= 2:
            strip = getattr(widget, "_barkav_rtl_strip", None)
            notebooks.append({
                "tabs": [str(widget.tab(tab, "text") or "") for tab in widget.tabs()],
                "strip_class": type(strip).__name__ if strip is not None else "",
            })
            if not isinstance(strip, TabStrip):
                issues.append("tab strip")
    wrong_fonts = sorted({item["family"] for item in fonts if item["family"] != expected_family})
    if wrong_fonts:
        issues.append("font family")
    if re.search(r"BARKAV\s+18\.(?:6|7)(?!\.)", window.title()):
        issues.append("stale window version")
    return {
        "title": window.title(),
        "normalised": bool(getattr(window, "_barkav_normalised187", False)),
        "font_families": sorted({item["family"] for item in fonts}),
        "wrong_font_families": wrong_fonts,
        "tables": tables,
        "notebooks": notebooks,
        "issues": sorted(set(issues)),
    }


def _run(output: Path) -> dict[str, Any]:
    import tkinter as tk

    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("TELEGRAM_BOT_TOKEN", "dialog-audit-token")
    os.environ.setdefault("GEMINI_API_KEY", "dialog-audit-gemini")
    os.environ.setdefault("ADMIN_USER_ID", "187")
    os.environ.setdefault("GROUP_CHAT_ID", "-100187")

    with tempfile.TemporaryDirectory(prefix="barkav-dialog-audit-") as directory:
        os.environ["STAGE4_DB_PATH"] = str(Path(directory) / "audit.sqlite3")

        import dashboard_stage18_7 as dashboard
        from barkav.features.dashboard import (
            ExpenseClassifyDialog, LoanDialog, ReceiptDialog, SimpleFormDialog,
            TransactionEditDialog,
        )
        from contractors_stage18_7 import ContractorWizard187
        from financial_calendar_stage18_7 import FinancialCalendarDialog187, FinancialMessagesDialog187
        from project_plan_stage18_7 import PlanRowWindow187
        from reports_stage18_7 import PhaseDetailDialog187, PriceCatalogDialog187, PriceEditor187
        from sales_claims_stage18_7 import (
            ContractDetails187, ContractExportPreview187, ContractWizard187,
            PaymentDocuments187, SalesRecord187, ShamsiDatePicker187,
        )
        from tools.windows_gui_acceptance import _seed_sales
        from ui_stage18_7 import resolve_font_family_187
        from v18_store import load_ui

        dashboard.v186.v185.fetch_tgju_usd_toman = (
            lambda timeout=6.0: (70_000, "2026-09-02T00:00:00")
        )
        _seed_sales(dashboard.DB)
        app = dashboard.Stage187Dashboard()
        app.geometry("1366x768+0+0")
        _settle(app)
        app.unify_appearance_187()
        _settle(app)
        expected_family = resolve_font_family_187(app, load_ui().get("font_family"))

        sales = app.sales_claims187
        sale_id = str(sales.contract_tree.get_children("")[0])
        market = next((widget for widget in _walk(app) if widget.__class__.__name__ == "MarketTab17"), None)
        plan = next((widget for widget in _walk(app) if widget.__class__.__name__ == "ProjectPlanPanel187"), None)

        scenarios: list[tuple[str, Callable[[], Any]]] = [
            ("project-settings", lambda: app.edit_project_settings()),
            ("manual-transaction", lambda: app.approval_center.manual_transaction()),
            ("new-loan", lambda: LoanDialog(app, lambda _data: None)),
            ("transaction-edit", lambda: TransactionEditDialog(app, {
                "amount": 1_000_000, "shamsi_date": "1405/06/01",
                "payer_name": "پرداخت‌کننده", "receiver_name": "دریافت‌کننده",
                "description": "نمونه ممیزی",
            }, lambda _data: None)),
            ("expense-classification", lambda: ExpenseClassifyDialog(app, {}, lambda *_args: None)),
            ("transaction-receipts", lambda: ReceiptDialog(app, [], lambda _path: None, lambda: None)),
            ("sales-contract-new", lambda: ContractWizard187(
                app, db=dashboard.DB, base_dir=dashboard.BASE_DIR,
                on_saved=lambda *_args: None, record_opener=None)),
            ("sales-contract-edit", lambda: ContractWizard187(
                app, db=dashboard.DB, base_dir=dashboard.BASE_DIR,
                on_saved=lambda *_args: None, record_opener=None,
                initial={"buyer_name": "نمونه", "contract_number": "AUDIT"}, sale_id=sale_id)),
            ("sales-record", lambda: SalesRecord187(
                app, db=dashboard.DB, base_dir=dashboard.BASE_DIR,
                sale_id=sale_id, on_saved=lambda *_args: None)),
            ("sales-contract-details", lambda: ContractDetails187(
                app, db=dashboard.DB, base_dir=dashboard.BASE_DIR, sale_id=sale_id)),
            ("sales-payment-documents", lambda: PaymentDocuments187(
                app, db=dashboard.DB, base_dir=dashboard.BASE_DIR,
                payments=[], contract_total=900_000_000)),
            ("sales-export-preview", lambda: ContractExportPreview187(
                app, export_format="PDF", headers=["عنوان", "مبلغ"],
                payload=[["نمونه", "۱٬۰۰۰"]], specs=[("قرارداد", "خریدار", "نمونه")],
                on_confirm=lambda *_args: None)),
            ("shamsi-date-picker", lambda: ShamsiDatePicker187(app, tk.StringVar(value="1405/06/01"))),
            ("contractor-wizard", lambda: ContractorWizard187(app, "قرارداد جدید", on_saved=lambda *_args: None)),
            ("project-plan-row", lambda: PlanRowWindow187(app, rich=app.rich, on_saved=lambda: None)),
            ("price-editor", lambda: PriceEditor187(app, app.rich, None, lambda: None)),
            ("price-catalog", lambda: PriceCatalogDialog187(app, app.rich, app.refresh_reports)),
            ("phase-detail", lambda: PhaseDetailDialog187(app, app.rich, 1, "فاز نمونه", app.refresh_reports)),
            ("financial-calendar", lambda: FinancialCalendarDialog187(app, dashboard.SERVICE)),
            ("financial-messages", lambda: FinancialMessagesDialog187(app, dashboard.SERVICE)),
            ("chart-cost", lambda: dashboard.ChartDetailDialog187(app, "donut")),
            ("chart-cashflow", lambda: dashboard.ChartDetailDialog187(app, "line")),
            ("chart-phases", lambda: dashboard.ChartDetailDialog187(app, "bar")),
        ]
        if market is not None:
            scenarios.extend([
                ("market-contractor", lambda: SimpleFormDialog(
                    app, "پیمانکار جدید", [("name", "نام", "entry")], {}, lambda _data: None)),
                ("market-supplier", lambda: SimpleFormDialog(
                    app, "تأمین‌کننده جدید", [("name", "نام", "entry")], {}, lambda _data: None)),
                ("market-contract", lambda: SimpleFormDialog(
                    app, "قرارداد پیمانکار", [("subject", "موضوع", "entry"),
                    ("amount", "مبلغ", "num")], {}, lambda _data: None)),
                ("market-rating", lambda: SimpleFormDialog(
                    app, "امتیازدهی", [("quality", "کیفیت", "entry"),
                    ("notes", "توضیحات", "entry")], {}, lambda _data: None)),
            ])
        if plan is None:
            raise RuntimeError("ProjectPlanPanel187 was not found")

        records: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        for index, (name, opener) in enumerate(scenarios, 1):
            before = {id(widget) for widget in _walk(app) if isinstance(widget, tk.Toplevel)}
            try:
                result = opener()
                _settle(app)
                candidates = [
                    widget for widget in _walk(app)
                    if isinstance(widget, tk.Toplevel) and id(widget) not in before and widget.winfo_exists()
                ]
                window = result if isinstance(result, tk.Toplevel) else (candidates[-1] if candidates else None)
                if window is None:
                    raise RuntimeError("opener did not create a Toplevel")
                _settle(window)
                image = output / f"{index:02d}-{name}.png"
                _capture(window, image)
                record = _snapshot(window, expected_family)
                record.update({"name": name, "screenshot": str(image.resolve())})
                records.append(record)
            except Exception as exc:
                errors.append({"name": name, "error": f"{type(exc).__name__}: {exc}"})
            finally:
                for widget in reversed(list(_walk(app))):
                    if isinstance(widget, tk.Toplevel) and id(widget) not in before:
                        try:
                            widget.destroy()
                        except Exception:
                            pass
                _settle(app)

        report = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "expected_font_family": expected_family,
            "dialog_count": len(records),
            "error_count": len(errors),
            "issue_count": sum(bool(record["issues"]) for record in records),
            "dialogs": records,
            "errors": errors,
        }
        app.destroy()
        return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output")
    args = parser.parse_args()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output = Path(args.output).resolve() if args.output else ROOT / "runtime" / "dialog_audit" / stamp
    output.mkdir(parents=True, exist_ok=True)
    report = _run(output)
    report_path = output / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"DIALOG_AUDIT_REPORT={report_path.resolve()}")
    print(f"DIALOGS={report['dialog_count']}")
    print(f"ERRORS={report['error_count']}")
    print(f"ISSUES={report['issue_count']}")
    return 1 if report["errors"] or report["issue_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
