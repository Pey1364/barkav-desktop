"""The only object JavaScript can call (pywebview ``js_api``).

pywebview exposes every *public* attribute of this object to the page,
recursively (webview/util.py ``get_functions``): a public ``self.db`` would
hand the page ``FinanceDB.tx()``.  So the rule here is strict - the public
surface is exactly ``PUBLIC_METHODS`` and everything else starts with ``_``.
``tests/test_webui_bridge.py`` enforces it.

pywebview calls these methods on worker threads, possibly concurrently; the
lock serialises loads, and each load uses its own snapshot and connections.

Every method returns the envelope described in
docs/PYWEBVIEW_BRIDGE_CONTRACTS_19_1_1.md:
``{"ok": true, "data": ..., "meta": {...}}`` or
``{"ok": false, "error": {"code", "message", "retryable"}, "meta": {...}}``.
Messages are Persian and user-facing; no tracebacks or file paths.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from webui.snapshot import SnapshotError, read_only_snapshot, resolve_project
from webui.summary import build_dashboard_summary

API_VERSION = 1
PUBLIC_METHODS = ('get_app_info', 'get_dashboard_summary')
_LOG = logging.getLogger(__name__)


def _meta() -> dict[str, Any]:
    return {'api_version': API_VERSION, 'generated_at': datetime.now().isoformat(timespec='seconds')}


def _ok(data: Any) -> dict[str, Any]:
    return {'ok': True, 'data': data, 'meta': _meta()}


def _fail(code: str, message: str, *, retryable: bool) -> dict[str, Any]:
    return {'ok': False, 'error': {'code': code, 'message': message, 'retryable': retryable}, 'meta': _meta()}


def load_dashboard(app_dir: Path, project_id: str | None = None,
                   db_path: str | Path | None = None,
                   registry_path: str | Path | None = None) -> dict[str, Any]:
    """Snapshot the project's database and build the summary from it."""
    project = resolve_project(app_dir, project_id, registry_path) if db_path is None else None
    source = Path(db_path) if db_path is not None else project.db_path
    with read_only_snapshot(source) as snap:
        # Imported here: these modules are the existing 19.1.1 services and
        # must be importable from app/ (sys.path is set by webui.app).
        from dashboard_read_model import DashboardServiceStage12
        from finance_db import FinanceDB
        service = DashboardServiceStage12(FinanceDB(snap.db_path), snap.base_dir)
        summary = build_dashboard_summary(service, project_name=project.name if project else '',
                                          contracts=snap.contracts)
        summary['snapshot'] = {
            'taken_at': snap.taken_at.isoformat(timespec='seconds'),
            'source_modified_at': snap.source_modified_at.isoformat(timespec='seconds'),
            'read_only': True,
        }
    return summary


class DashboardBridge:
    def __init__(self, app_dir: str | Path, *, project_id: str | None = None,
                 db_path: str | Path | None = None,
                 registry_path: str | Path | None = None, cache_seconds: float = 5.0,
                 loader: Callable[..., dict[str, Any]] = load_dashboard):
        self._app_dir = Path(app_dir)
        self._project_id = project_id
        self._db_path = db_path
        self._registry_path = registry_path
        self._cache_seconds = cache_seconds
        self._loader = loader
        self._lock = threading.Lock()
        self._cached: tuple[float, dict[str, Any]] | None = None

    def get_app_info(self) -> dict[str, Any]:
        try:
            version = (self._app_dir / 'VERSION.txt').read_text(encoding='utf-8').strip()
        except OSError:
            version = ''
        return _ok({'app_version': version, 'mode': 'read_only_prototype',
                    'operations': list(PUBLIC_METHODS)})

    def get_dashboard_summary(self, force_refresh: bool = False) -> dict[str, Any]:
        with self._lock:
            now = time.monotonic()
            if (not force_refresh and self._cached is not None
                    and now - self._cached[0] < self._cache_seconds):
                return _ok(self._cached[1])
            try:
                data = self._loader(self._app_dir, self._project_id, self._db_path, self._registry_path)
            except SnapshotError as exc:
                return _fail(exc.code, str(exc), retryable=exc.code == 'DATABASE_UNREADABLE')
            except Exception:
                _LOG.exception('dashboard summary failed')
                return _fail('INTERNAL_ERROR', 'ساخت خلاصهٔ داشبورد با خطا روبه‌رو شد.', retryable=True)
            self._cached = (now, data)
            return _ok(data)
