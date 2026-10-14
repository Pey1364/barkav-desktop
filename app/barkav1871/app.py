"""18.7.1 entry point with no imports from historical versioned modules."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from tkinter import messagebox

from .core import APP_IDENTITY, ProjectEntry, ProjectRegistry
from .features import ProjectCenter
from .shell import ApplicationShell


BASE_DIR = Path(__file__).resolve().parent.parent


def preflight_report() -> list[str]:
    errors: list[str] = []
    if sys.version_info < (3, 10):
        errors.append("Python 3.10 یا جدیدتر لازم است.")
    if importlib.util.find_spec("jdatetime") is None:
        errors.append("بستهٔ jdatetime نصب نشده است. ابتدا requirements_18_7_1.txt را نصب کنید.")
    return errors


def open_project_center(base_dir: str | Path = BASE_DIR) -> None:
    base = Path(base_dir)
    center = ProjectCenter(base, on_project_opened=lambda project: _open_project(center, base, project))
    center.mainloop()


def _open_project(center: ProjectCenter, base_dir: Path, project: ProjectEntry) -> None:
    center.destroy()
    ApplicationShell(base_dir, project).mainloop()


def main() -> int:
    errors = preflight_report()
    if errors:
        messagebox.showerror(f"BARKAV {APP_IDENTITY.version}", "\n\n".join(errors))
        return 1
    registry = ProjectRegistry(BASE_DIR)
    if not registry.list():
        registry.ensure_default_project({})
    open_project_center(BASE_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
