from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class ProjectEntry:
    project_id: str
    name: str
    db_path: str
    group_chat_id: int | None = None
    # فهرست همهٔ گروه‌های تلگرام این پروژه، شاملِ خودِ group_chat_id هم -
    # آن فیلد برای سازگاری با کد قدیمی (که همه‌جا فقط یک گروه می‌شناسد)
    # همچنان اولین گروه را نگه می‌دارد؛ این فیلد جدید و اختیاری است، پس
    # پروژه‌های ثبت‌شدهٔ قبلی (بدون این کلید در JSON) هم مشکلی پیدا نمی‌کنند.
    group_chat_ids: list[int] = field(default_factory=list)
    spreadsheet_name: str = ""
    address: str = ""
    postal_code: str = ""
    registration_plate: str = ""
    municipal_file_no: str = ""
    telegram_verified: bool = False
    created_at: str = ""


class ProjectRegistry:
    """Small pre-launch project registry.

    Stage 15 keeps each project's financial SQLite isolated while the program is
    in active-project mode. This makes the pre-launch selector safe for existing
    Stage 14 data and avoids invasive ledger migration before receipt accuracy is
    proven. The Telegram bot receives the selected project's DB/group through
    environment overrides.
    """
    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir)
        # Source checkouts keep Python entrypoints in ``app/`` while the live
        # project data sits beside it in the release root.  Preserve the
        # historical ``base/data`` layout for tests and older portable bundles,
        # but prefer the sibling data directory when it owns the registry.
        local_data = self.base_dir / "data"
        sibling_data = self.base_dir.parent / "data"
        self.data_root = (
            sibling_data
            if (sibling_data / "project_registry.json").is_file()
            and not (local_data / "project_registry.json").is_file()
            else local_data
        )
        self.path = self.data_root / "project_registry.json"
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

    def ensure_legacy_project(self, secrets: dict[str, Any]) -> ProjectEntry:
        rows=self.list()
        if rows:
            return rows[0]
        db_raw=str(os.getenv("STAGE4_DB_PATH") or secrets.get("STAGE4_DB_PATH") or self.data_root / "stage4_test.sqlite3")
        db=Path(db_raw)
        if not db.is_absolute(): db=self.data_root/db
        group=secrets.get("GROUP_CHAT_ID")
        try: group=int(group) if group not in (None,"",0,"0") else None
        except Exception: group=None
        name="پروژه فعلی"
        try:
            from finance_db import FinanceDB
            from project_service import ProjectService
            svc=ProjectService(FinanceDB(db),self.base_dir)
            meta=svc.get_project()
            if str(meta.get("name") or "").strip(): name=str(meta["name"]).strip()
        except Exception:
            pass
        p=ProjectEntry(
            project_id="PRJ-001",name=name,db_path=str(db),group_chat_id=group,
            spreadsheet_name=str(secrets.get("SPREADSHEET_NAME") or "BARKAV1405"),
            telegram_verified=bool(group),created_at=datetime.now().isoformat(timespec="seconds"),
        )
        self.data["projects"]=[asdict(p)];self.data["active_project_id"]=p.project_id;self.save();return p

    def create(self, *, name: str, group_chat_id: int | None, spreadsheet_name: str,
               address: str="", postal_code: str="", registration_plate: str="",
               municipal_file_no: str="", telegram_verified: bool=False,
               group_chat_ids: list[int] | None = None) -> ProjectEntry:
        # group_chat_ids اختیاری و اضافه است - همهٔ فراخوان‌های قدیمی که
        # فقط group_chat_id تکی می‌دهند دقیقاً مثل قبل کار می‌کنند
        # (group_chat_ids خودش را از همان یکی می‌سازد). ویزارد جدید هر دو
        # را می‌دهد: group_chat_id اولین گروه برای سازگاری، group_chat_ids
        # کل فهرست.
        ids: list[int] = list(dict.fromkeys(group_chat_ids)) if group_chat_ids else (
            [group_chat_id] if group_chat_id is not None else [])
        if group_chat_id is None and ids:
            group_chat_id = ids[0]
        for gid in ids:
            for p in self.list():
                if p.group_chat_id == gid or gid in (p.group_chat_ids or []):
                    raise ValueError(f"این Group ID قبلاً به پروژه «{p.name}» متصل شده است.")
        pid=self._next_id()
        folder=self.data_root/"projects"/pid
        folder.mkdir(parents=True,exist_ok=True)
        db=folder/"finance.sqlite3"
        p=ProjectEntry(
            project_id=pid,name=name.strip() or pid,db_path=str(db),group_chat_id=group_chat_id,
            group_chat_ids=ids,
            spreadsheet_name=spreadsheet_name.strip() or f"PEYMAAN-{pid}",address=address.strip(),
            postal_code=postal_code.strip(),registration_plate=registration_plate.strip(),
            municipal_file_no=municipal_file_no.strip(),telegram_verified=telegram_verified,
            created_at=datetime.now().isoformat(timespec="seconds"),
        )
        # Initialize the project's independent ledger and project profile now,
        # before the user can enter it.
        from finance_db import FinanceDB
        from project_service import ProjectService
        svc=ProjectService(FinanceDB(db),self.base_dir)
        svc.save_project(name=p.name,address=p.address,postal_code=p.postal_code,
                         registration_plate=p.registration_plate,municipal_file_no=p.municipal_file_no)
        rows=[asdict(x) for x in self.list()];rows.append(asdict(p));self.data["projects"]=rows;self.save();return p
    def update(self, project_id: str, *, name: str, group_chat_id: int | None,
               spreadsheet_name: str, address: str = "", postal_code: str = "",
               registration_plate: str = "", municipal_file_no: str = "",
               telegram_verified: bool = False,
               group_chat_ids: list[int] | None = None) -> ProjectEntry:
        current = self.get(project_id)
        if current is None:
            raise KeyError(project_id)
        ids: list[int] = list(dict.fromkeys(group_chat_ids)) if group_chat_ids else (
            [group_chat_id] if group_chat_id is not None else [])
        if group_chat_id is None and ids:
            group_chat_id = ids[0]
        if len(ids) != len(set(ids)):
            raise ValueError("شناسه‌های گروه تلگرام تکراری هستند.")
        for project in self.list():
            if project.project_id == project_id:
                continue
            for gid in ids:
                if project.group_chat_id == gid or gid in (project.group_chat_ids or []):
                    raise ValueError(f"این Group ID قبلاً به پروژه «{project.name}» متصل است.")
        updated = ProjectEntry(
            project_id=current.project_id,
            name=name.strip() or current.name,
            db_path=current.db_path,
            group_chat_id=group_chat_id,
            group_chat_ids=ids,
            spreadsheet_name=spreadsheet_name.strip() or current.spreadsheet_name,
            address=address.strip(),
            postal_code=postal_code.strip(),
            registration_plate=registration_plate.strip(),
            municipal_file_no=municipal_file_no.strip(),
            telegram_verified=telegram_verified,
            created_at=current.created_at,
        )
        self.data["projects"] = [
            asdict(updated) if item.project_id == project_id else asdict(item)
            for item in self.list()
        ]
        self.save()
        return updated

    def set_active(self, project_id: str) -> ProjectEntry:
        p=self.get(project_id)
        if not p: raise KeyError(project_id)
        self.data["active_project_id"]=project_id;self.save();return p


def apply_project_environment(project: ProjectEntry) -> None:
    os.environ["PEYMAAN_ACTIVE_PROJECT_ID"]=project.project_id
    os.environ["PEYMAAN_ACTIVE_PROJECT_NAME"]=project.name
    os.environ["STAGE4_DB_PATH"]=project.db_path
    if project.group_chat_id is not None:
        os.environ["GROUP_CHAT_ID"]=str(project.group_chat_id)
    else:
        os.environ.pop("GROUP_CHAT_ID",None)
    ids=project.group_chat_ids or ([project.group_chat_id] if project.group_chat_id is not None else [])
    if ids:
        os.environ["GROUP_CHAT_IDS"]=",".join(str(g) for g in ids)
    else:
        os.environ.pop("GROUP_CHAT_IDS",None)
    os.environ["SPREADSHEET_NAME"]=project.spreadsheet_name
