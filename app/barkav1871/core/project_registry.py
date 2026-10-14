from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class ProjectEntry:
    project_id: str
    name: str
    db_path: str
    group_chat_id: int | None = None
    spreadsheet_name: str = ""
    address: str = ""
    postal_code: str = ""
    registration_plate: str = ""
    municipal_file_no: str = ""
    telegram_verified: bool = False
    created_at: str = ""


class ProjectRegistry:
    """Small pre-launch project registry with isolated project databases."""
    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir)
        # A copied historical registry can point at a database in another
        # release.  18.7.1 owns a separate registry and never follows that
        # external database path implicitly.
        self.path = self.base_dir / "data" / "project_registry_18_7_1.json"
        self._historical_path = self.base_dir / "data" / "project_registry.json"
        self._historical_metadata: dict[str, Any] = {}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data: dict[str, Any] = {"active_project_id": "", "projects": []}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self.data.update(raw)
            except Exception:
                pass
        elif self._historical_path.exists():
            # Metadata is safe to carry forward, but the historical db_path is
            # deliberately excluded.  Finance data needs an explicit migration.
            try:
                raw = json.loads(self._historical_path.read_text(encoding="utf-8"))
                projects = raw.get("projects") if isinstance(raw, dict) else None
                if isinstance(projects, list) and projects and isinstance(projects[0], dict):
                    self._historical_metadata = dict(projects[0])
            except Exception:
                pass

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def list(self) -> list[ProjectEntry]:
        return [ProjectEntry(**p) for p in self.data.get("projects", [])]

    def get(self, project_id: str) -> ProjectEntry | None:
        return next((p for p in self.list() if p.project_id == project_id), None)

    def _next_id(self) -> str:
        nums=[]
        for p in self.list():
            m=re.fullmatch(r"PRJ-(\d+)",p.project_id)
            if m: nums.append(int(m.group(1)))
        return f"PRJ-{max(nums or [0])+1:03d}"

    def ensure_default_project(self, secrets: dict[str, Any]) -> ProjectEntry:
        rows=self.list()
        if rows:
            return rows[0]
        db_raw=str(os.getenv("BARKAV_DB_PATH") or secrets.get("BARKAV_DB_PATH") or self.base_dir / "data" / "projects" / "PRJ-001" / "finance.sqlite3")
        db=Path(db_raw)
        if not db.is_absolute():
            db=self.base_dir/db
        else:
            try:
                db.relative_to(self.base_dir)
            except ValueError:
                db=self.base_dir / "data" / "projects" / "PRJ-001" / "finance.sqlite3"
        historical = self._historical_metadata
        group=secrets.get("GROUP_CHAT_ID", historical.get("group_chat_id"))
        try: group=int(group) if group not in (None,"",0,"0") else None
        except Exception: group=None
        name=str(historical.get("name") or "پروژه فعلی").strip()
        try:
            from barkav1871.services import FinanceDB, ProjectService
            svc=ProjectService(FinanceDB(db),self.base_dir)
            meta=svc.get_project()
            if str(meta.get("name") or "").strip(): name=str(meta["name"]).strip()
        except Exception:
            pass
        p=ProjectEntry(
            project_id="PRJ-001",name=name,db_path=str(db),group_chat_id=group,
            spreadsheet_name=str(secrets.get("SPREADSHEET_NAME") or historical.get("spreadsheet_name") or "BARKAV1405"),
            address=str(historical.get("address") or ""),postal_code=str(historical.get("postal_code") or ""),
            registration_plate=str(historical.get("registration_plate") or ""),municipal_file_no=str(historical.get("municipal_file_no") or ""),
            telegram_verified=bool(group),created_at=datetime.now().isoformat(timespec="seconds"),
        )
        self.data["projects"]=[asdict(p)];self.data["active_project_id"]=p.project_id;self.save();return p

    def create(self, *, name: str, group_chat_id: int | None, spreadsheet_name: str,
               address: str="", postal_code: str="", registration_plate: str="",
               municipal_file_no: str="", telegram_verified: bool=False) -> ProjectEntry:
        if group_chat_id is not None:
            for p in self.list():
                if p.group_chat_id == group_chat_id:
                    raise ValueError(f"این Group ID قبلاً به پروژه «{p.name}» متصل شده است.")
        pid=self._next_id()
        folder=self.base_dir/"data"/"projects"/pid
        folder.mkdir(parents=True,exist_ok=True)
        db=folder/"finance.sqlite3"
        p=ProjectEntry(
            project_id=pid,name=name.strip() or pid,db_path=str(db),group_chat_id=group_chat_id,
            spreadsheet_name=spreadsheet_name.strip() or f"PEYMAAN-{pid}",address=address.strip(),
            postal_code=postal_code.strip(),registration_plate=registration_plate.strip(),
            municipal_file_no=municipal_file_no.strip(),telegram_verified=telegram_verified,
            created_at=datetime.now().isoformat(timespec="seconds"),
        )
        # Initialize the project's independent ledger and project profile now,
        # before the user can enter it.
        from barkav1871.services import FinanceDB, ProjectService
        svc=ProjectService(FinanceDB(db),self.base_dir)
        svc.save_project(name=p.name,address=p.address,postal_code=p.postal_code,
                         registration_plate=p.registration_plate,municipal_file_no=p.municipal_file_no)
        rows=[asdict(x) for x in self.list()];rows.append(asdict(p));self.data["projects"]=rows;self.save();return p

    def set_active(self, project_id: str) -> ProjectEntry:
        p=self.get(project_id)
        if not p: raise KeyError(project_id)
        self.data["active_project_id"]=project_id;self.save();return p


def apply_project_environment(project: ProjectEntry) -> None:
    os.environ["PEYMAAN_ACTIVE_PROJECT_ID"]=project.project_id
    os.environ["PEYMAAN_ACTIVE_PROJECT_NAME"]=project.name
    os.environ["BARKAV_DB_PATH"]=project.db_path
    if project.group_chat_id is not None:
        os.environ["GROUP_CHAT_ID"]=str(project.group_chat_id)
    else:
        os.environ.pop("GROUP_CHAT_ID",None)
    os.environ["SPREADSHEET_NAME"]=project.spreadsheet_name
