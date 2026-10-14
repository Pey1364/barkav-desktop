"""Architecture guard: the core must not know Google Drive, the UI or the 19.1.1 app."""

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "barkav_field"
FORBIDDEN = ("google", "googleapiclient", "tkinter", "barkav", "finance_db", "telegram")
CORE = ["envelope.py", "store.py", "intake.py", "api.py"]


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
    return names


def test_core_modules_do_not_import_google_ui_or_the_legacy_app():
    for name in CORE:
        for module in _imports(PACKAGE / name):
            for bad in FORBIDDEN:
                assert not module.startswith(bad), f"{name} imports {module}"
