"""Mechanically flatten the active 18.7 Dashboard inheritance chain.

The generated module preserves every class body in dependency order.  Namespace
snapshots replace the former versioned module aliases (``v186``, ``v185``, ...),
so a later override keeps referring to exactly the same preceding class.
"""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PARTS = (
    ("dashboard_stage12.py", "d12"),
    ("dashboard_stage14.py", "d14"),
    ("dashboard_stage15.py", None),
    ("dashboard_stage16_3.py", "v16", "v163"),
    ("dashboard_stage17.py", "v174"),
    ("dashboard_stage17_5.py", "v175"),
    ("dashboard_stage18.py", "v18"),
    ("dashboard_stage18_1.py", "v181"),
    ("dashboard_stage18_2.py", "v182"),
    ("dashboard_stage18_3.py", "v183"),
    ("dashboard_stage18_4.py", "v184"),
    ("dashboard_stage18_5.py", "v185"),
    ("dashboard_stage18_6.py", "v186"),
    ("dashboard_stage18_7.py", None),
)
DEFERRED_IMPORTS = {
    "financial_calendar_stage18_7",
    "reports_stage18_7",
    "sales_claims_stage18_7",
}


def _remove_internal_imports(source: str) -> str:
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    drops: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name.startswith("dashboard_stage") for alias in node.names):
                drops.append((node.lineno, node.end_lineno or node.lineno))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.startswith("dashboard_stage") or module in DEFERRED_IMPORTS:
                drops.append((node.lineno, node.end_lineno or node.lineno))
    for start, end in sorted(drops, reverse=True):
        del lines[start - 1:end]
    return "".join(lines).replace("from __future__ import annotations\n", "")


def main() -> None:
    chunks = [
        '"""Consolidated active BARKAV 18.7 Dashboard runtime."""\n',
        "from __future__ import annotations\n\n",
        "import types as _types\n\n",
        "def _legacy_snapshot():\n"
        "    return _types.SimpleNamespace(**globals().copy())\n\n",
    ]
    for part in PARTS:
        file_name, *aliases = part
        source = _remove_internal_imports((ROOT / file_name).read_text(encoding="utf-8"))
        chunks.append(f"\n# ---- Extracted from {file_name} ----\n")
        chunks.append(source)
        chunks.append("\n")
        for alias in aliases:
            if alias:
                chunks.append(f"{alias} = _legacy_snapshot()\n")
    chunks.append(
        "\n# Deferred imports avoid a circular dependency while preserving runtime behaviour.\n"
        "from financial_calendar_stage18_7 import (\n"
        "    FinancialCalendarDialog187, FinancialMessagesDialog187, upcoming_events_187,\n"
        ")\n"
        "from sales_claims_stage18_7 import SalesClaimsPanel187, is_temporary_sales_finance_pending_187\n"
        "\n"
        "def install_report_controls_187(app):\n"
        "    from reports import install_report_controls_187 as implementation\n"
        "    return implementation(app)\n\n"
        "def PhaseDetailDialog187(*args, **kwargs):\n"
        "    from reports import PhaseDetailDialog187 as implementation\n"
        "    return implementation(*args, **kwargs)\n"
    )
    (ROOT / "dashboard.py").write_text("".join(chunks).rstrip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
