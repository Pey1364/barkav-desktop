r"""Capture and validate the real Windows rendering of BARKAV sales tabs.

The public runner starts a disposable BARKAV dashboard process backed by a
temporary SQLite database, connects to that exact process with pywinauto, and
captures the Contracts and Finance tabs.  The fixture mode runs inside the
same Python installation as the application so the test exercises real Tk on
Windows instead of treating source inspection as visual acceptance.

Typical use from the release root::

    .venv-gui\Scripts\python.exe tools\windows_gui_acceptance.py

Generated screenshots and JSON reports are written below ``runtime/`` and are
therefore excluded from Git and from release packages.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TITLE_SUFFIX = "Version 19.1.1"
EXPECTED_FINANCE_ALL_ROWS = 9
SCENARIOS = ("contracts", "finance")


def _geometry(widget) -> dict[str, Any]:
    """Return screen and parent-relative geometry for one rendered widget."""
    return {
        "x": int(widget.winfo_x()),
        "y": int(widget.winfo_y()),
        "root_x": int(widget.winfo_rootx()),
        "root_y": int(widget.winfo_rooty()),
        "width": int(widget.winfo_width()),
        "height": int(widget.winfo_height()),
        "mapped": bool(widget.winfo_ismapped()),
        "manager": str(widget.winfo_manager()),
    }


def evaluate_snapshot(snapshot: dict[str, Any]) -> dict[str, bool]:
    """Evaluate measurable acceptance rules from a rendered Tk snapshot."""
    tree = snapshot.get("tree", {})
    xscroll = snapshot.get("xscroll", {})
    yscroll = snapshot.get("yscroll", {})
    checks = {
        "version_18_7_1": str(snapshot.get("title", "")).endswith(EXPECTED_TITLE_SUFFIX),
        "horizontal_scrollbar_visible": bool(xscroll.get("mapped"))
        and xscroll.get("manager") == "grid"
        and int(xscroll.get("width", 0)) >= 120
        and int(xscroll.get("height", 0)) >= 8,
        "vertical_scrollbar_visible": bool(yscroll.get("mapped"))
        and yscroll.get("manager") == "grid"
        and int(yscroll.get("height", 0)) >= 120
        and int(yscroll.get("width", 0)) >= 8,
        "table_uses_standard_background": str(tree.get("style", ""))
        == "Barkav.Data.Treeview",
    }
    if snapshot.get("scenario") == "finance":
        toolbar_y = [int(value) for value in snapshot.get("finance_toolbar_root_y", [])]
        checks["finance_toolbar_one_row"] = len(toolbar_y) == 3 and max(toolbar_y) - min(toolbar_y) <= 4
        checks["finance_refresh_button_absent"] = not any(
            "بروزرسانی" in str(text) for text in snapshot.get("finance_button_texts", [])
        )
        checks["finance_name_all_shows_all_rows"] = (
            snapshot.get("finance_search_kind") == "نام خریدار"
            and snapshot.get("finance_search_value") == "همه"
            and int(snapshot.get("finance_row_count", 0)) == EXPECTED_FINANCE_ALL_ROWS
        )
    return checks


def _walk(widget):
    yield widget
    for child in widget.winfo_children():
        yield from _walk(child)


def _seed_sales(database) -> None:
    """Create synthetic rows only in the disposable acceptance database."""
    from revenue_service import RevenueService

    service = RevenueService(database)
    for index, buyer in enumerate(("خریدار نمونه یک", "خریدار نمونه دو", "خریدار نمونه سه"), start=1):
        installments = [
            {
                "sequence_no": number,
                "amount": 300_000_000,
                "due_date_shamsi": f"1405/{6 + number:02d}/20",
                "description": f"مرحله پرداخت {number}",
            }
            for number in range(1, 4)
        ]
        service.create_sale_bundle(
            project_name="پروژه آزمایشی پذیرش تصویری",
            block_name="A",
            unit_number=str(100 + index),
            floor=str(index),
            area=85 + index,
            buyer_name=buyer,
            contract_number=f"GUI-{index:02d}",
            contract_date_shamsi="1405/06/01",
            contract_amount=900_000_000,
            installments=installments,
            notes=json.dumps(
                {
                    "contract_v": 1,
                    "contract_area": str(85 + index),
                    "sale_kind": "پیش‌فروش",
                    "delivery_date": "1406/06/01",
                },
                ensure_ascii=False,
            ),
            source="GUI_ACCEPTANCE_FIXTURE",
        )


def _fixture_snapshot(app, scenario: str) -> dict[str, Any]:
    import tkinter as tk
    from tkinter import ttk

    panel = app.sales_claims187
    tree = panel.contract_tree if scenario == "contracts" else panel.finance_tree
    xscroll = tree._barkav_xscroll187
    yscroll = tree._barkav_yscroll187
    button_texts: list[str] = []
    for widget in _walk(panel.finance):
        if isinstance(widget, (tk.Button, ttk.Button)):
            try:
                button_texts.append(str(widget.cget("text")))
            except tk.TclError:
                continue
    toolbar_groups = (
        panel.finance_actions187,
        panel.finance_filters187,
        panel.finance_output187,
    )
    snapshot = {
        "scenario": scenario,
        "pid": os.getpid(),
        "title": app.title(),
        "window_handle": int(app.winfo_id()),
        "window": _geometry(app),
        "tree": {
            **_geometry(tree),
            "xview": list(tree.xview()),
            "yview": list(tree.yview()),
            "style": str(tree.cget("style")),
        },
        "xscroll": _geometry(xscroll),
        "yscroll": _geometry(yscroll),
        "finance_toolbar_root_y": [group.winfo_rooty() for group in toolbar_groups],
        "finance_button_texts": button_texts,
        "finance_search_kind": panel.finance_search_kind.get(),
        "finance_search_value": panel.finance_search_value.get(),
        "finance_row_count": len(panel.finance_tree.get_children()),
    }
    snapshot["checks"] = evaluate_snapshot(snapshot)
    snapshot["passed"] = all(snapshot["checks"].values())
    return snapshot


def _run_fixture(args: argparse.Namespace) -> int:
    """Run one real Tk window for the outer pywinauto controller."""
    os.environ["STAGE4_DB_PATH"] = str(Path(args.database).resolve())
    os.environ.setdefault("TELEGRAM_BOT_TOKEN", "gui-acceptance-token")
    os.environ.setdefault("GEMINI_API_KEY", "gui-acceptance-gemini")
    os.environ.setdefault("ADMIN_USER_ID", "187")
    os.environ.setdefault("GROUP_CHAT_ID", "-100187")
    sys.path.insert(0, str(ROOT))

    import dashboard_stage18_7 as dashboard

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

    def prepare() -> None:
        panel = app.sales_claims187
        app.notebook.select(app.sales_root)
        panel.refresh()
        first = panel.contract_tree.get_children()[0]
        panel.contract_tree.selection_set(first)
        panel._select_contract()
        if args.fixture == "finance":
            panel.finance_search_kind.set("نام خریدار")
            panel._refresh_finance_search_values()
        panel.nb.select(panel.contracts if args.fixture == "contracts" else panel.finance)
        app.update_idletasks()
        app.update()
        app.update_idletasks()
        app.update()
        snapshot = _fixture_snapshot(app, args.fixture)
        ready = Path(args.ready_file)
        ready.parent.mkdir(parents=True, exist_ok=True)
        temporary = ready.with_suffix(ready.suffix + ".tmp")
        temporary.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(ready)

    app.after(1200, prepare)
    app.after(45_000, app.destroy)
    app.mainloop()
    return 0


def _registry_python() -> Path | None:
    if platform.system() != "Windows":
        return None
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Python\PythonCore") as root:
            versions: list[str] = []
            index = 0
            while True:
                try:
                    versions.append(winreg.EnumKey(root, index))
                    index += 1
                except OSError:
                    break
        for version in reversed(sorted(versions)):
            try:
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    rf"Software\Python\PythonCore\{version}\InstallPath",
                ) as key:
                    executable, _kind = winreg.QueryValueEx(key, "ExecutablePath")
            except OSError:
                continue
            candidate = Path(executable)
            if candidate.is_file():
                return candidate
        return None
    except (OSError, ImportError):
        return None


def _wait_for_snapshot(ready_file: Path, process: subprocess.Popen, timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if ready_file.is_file():
            return json.loads(ready_file.read_text(encoding="utf-8"))
        return_code = process.poll()
        if return_code is not None:
            raise RuntimeError(f"GUI fixture exited before it was ready (exit {return_code}).")
        time.sleep(0.1)
    raise TimeoutError(f"GUI fixture was not ready within {timeout:g} seconds.")


def _capture_nonblank(window, destination: Path) -> bool:
    image = window.capture_as_image()
    image.save(destination)
    extrema = image.convert("L").getextrema()
    return image.width >= 800 and image.height >= 500 and extrema[1] - extrema[0] >= 20


def _run_scenario(
    scenario: str,
    *,
    app_python: Path,
    output_dir: Path,
    scratch: Path,
) -> dict[str, Any]:
    from pywinauto import Desktop

    ready_file = scratch / f"{scenario}.json"
    database = scratch / f"{scenario}.sqlite3"
    log_path = output_dir / f"{scenario}.log"
    screenshot = output_dir / f"{scenario}.png"
    command = [
        str(app_python),
        str(Path(__file__).resolve()),
        "--fixture",
        scenario,
        "--ready-file",
        str(ready_file),
        "--database",
        str(database),
    ]
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        window = None
        try:
            snapshot = _wait_for_snapshot(ready_file, process, timeout=35)
            window = Desktop(backend="win32").window(
                title=snapshot["title"], process=process.pid
            )
            window.wait("visible enabled ready", timeout=15)
            # Dismiss any transient ttk combobox popdown that inherited
            # startup focus may have left open before capturing evidence. A
            # locked/non-interactive desktop cannot move the real mouse, so
            # focus and keyboard cleanup are strictly best-effort.
            try:
                window.set_focus()
                window.type_keys("{ESC}")
            except Exception:
                pass
            time.sleep(0.25)
            snapshot["checks"]["screenshot_nonblank"] = _capture_nonblank(window, screenshot)
            snapshot["screenshot"] = str(screenshot.resolve())
            snapshot["passed"] = all(snapshot["checks"].values())
            return snapshot
        finally:
            if window is not None:
                try:
                    window.close()
                except Exception:
                    pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


def _run_acceptance(args: argparse.Namespace) -> int:
    if platform.system() != "Windows":
        raise SystemExit("Windows GUI acceptance can only run on Windows.")
    try:
        import pywinauto  # noqa: F401
        import PIL  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "Missing GUI acceptance dependency. Run: "
            r".venv-gui\Scripts\python.exe -m pip install -r requirements_gui_acceptance.txt"
        ) from exc

    app_python = Path(args.app_python).resolve() if args.app_python else _registry_python()
    if app_python is None or not app_python.is_file():
        raise SystemExit("The real application Python could not be found; pass --app-python explicitly.")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir = Path(args.output).resolve() if args.output else ROOT / "runtime" / "gui_acceptance" / stamp
    output_dir.mkdir(parents=True, exist_ok=True)
    scenarios = SCENARIOS if args.scenario == "both" else (args.scenario,)

    with tempfile.TemporaryDirectory(prefix="barkav-gui-acceptance-") as directory:
        scratch = Path(directory)
        results = [
            _run_scenario(
                scenario,
                app_python=app_python,
                output_dir=output_dir,
                scratch=scratch,
            )
            for scenario in scenarios
        ]
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "app_python": str(app_python),
        "controller_python": sys.executable,
        "results": results,
        "passed": all(item["passed"] for item in results),
    }
    report_path = output_dir / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"GUI_ACCEPTANCE_REPORT={report_path}")
    for item in results:
        state = "PASS" if item["passed"] else "FAIL"
        failed = [name for name, value in item["checks"].items() if not value]
        print(f"{item['scenario'].upper()}={state}" + (f" failed={','.join(failed)}" if failed else ""))
    return 0 if report["passed"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=("both", *SCENARIOS), default="both")
    parser.add_argument("--output", help="Artifact directory; defaults below runtime/gui_acceptance.")
    parser.add_argument("--app-python", help="Python executable used by the real BARKAV application.")
    parser.add_argument("--fixture", choices=SCENARIOS, help=argparse.SUPPRESS)
    parser.add_argument("--ready-file", help=argparse.SUPPRESS)
    parser.add_argument("--database", help=argparse.SUPPRESS)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.fixture:
        if not args.ready_file or not args.database:
            raise SystemExit("Fixture mode requires --ready-file and --database.")
        return _run_fixture(args)
    return _run_acceptance(args)


if __name__ == "__main__":
    raise SystemExit(main())
