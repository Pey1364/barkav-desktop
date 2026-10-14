from __future__ import annotations

import json
import sys
from pathlib import Path


def frozen() -> bool:
    """True inside a PyInstaller-built exe, False running from source."""
    return bool(getattr(sys, 'frozen', False))


def resolve_base(dev_file: str) -> Path:
    """App-relative base directory (secrets.local.json, data/, runtime/, .brk).

    In dev, every entrypoint (launcher, project runner, telegram bot) is its
    own .py file and resolves relative to itself, same as always. Once
    packaged, all three are bundled into one exe - there is no separate
    ``project_runner_stage18_7.py`` sitting on disk to resolve relative to
    any more, so every entrypoint must agree on one shared location instead:
    the exe's own folder.
    """
    if frozen():
        return Path(sys.executable).resolve().parent
    return Path(dev_file).resolve().parent


def local_secrets_path(base_dir: str | Path) -> Path | None:
    """Find local credentials beside the runtime or its enclosing install.

    Installed builds keep private files beside ``app/`` while the executable
    runs from ``app/`` itself. Source checkouts also support the historical
    sibling ``data/`` location.
    """
    base = Path(base_dir)
    for candidate in (
        base / "secrets.local.json",
        base.parent / "secrets.local.json",
        base.parent / "data" / "secrets.local.json",
    ):
        if candidate.is_file():
            return candidate
    return None


def load_local_secrets(base_dir: str | Path) -> dict:
    path = local_secrets_path(base_dir)
    if path is None:
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def self_reexec_args(dev_script: Path, *args: str) -> list[str]:
    """Argv for spawning another BARKAV entrypoint as a subprocess.

    In dev this is unchanged: ``[python, dev_script.py, *args]``. Frozen,
    there is no interpreter to hand a loose script to - ``sys.executable``
    *is* the one exe - so instead this re-launches the same exe with a
    ``--run-project``/``--run-bot``-style internal flag that main() dispatches
    on (see launcher_stage18_7.main).
    """
    if frozen():
        return [sys.executable, *args]
    return [sys.executable, str(dev_script), *args]
