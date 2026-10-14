from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, Optional

from finance_db import FinanceDB, _id, _now


class ProjectService:
    def __init__(self, db: FinanceDB, base_dir: str | Path):
        self.db = db
        self.base_dir = Path(base_dir)
        active_project = os.getenv('PEYMAAN_ACTIVE_PROJECT_ID','').strip()
        self.documents_dir = (self.base_dir / 'data' / 'projects' / active_project / 'project_documents') if active_project else (self.base_dir / 'data' / 'project_documents')
        self.documents_dir.mkdir(parents=True, exist_ok=True)
        self._migrate()

    def _migrate(self) -> None:
        with self.db.tx() as con:
            con.executescript('''
                CREATE TABLE IF NOT EXISTS projects (
                    project_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL DEFAULT '',
                    address TEXT NOT NULL DEFAULT '',
                    postal_code TEXT NOT NULL DEFAULT '',
                    registration_plate TEXT NOT NULL DEFAULT '',
                    municipal_file_no TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS project_documents (
                    document_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(project_id),
                    document_type TEXT NOT NULL DEFAULT 'OTHER',
                    title TEXT NOT NULL DEFAULT '',
                    local_path TEXT NOT NULL,
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    deleted_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_project_docs_project ON project_documents(project_id, deleted_at);
            ''')
            cols = {r[1] for r in con.execute('PRAGMA table_info(projects)').fetchall()}
            if 'registration_plate' not in cols:
                con.execute("ALTER TABLE projects ADD COLUMN registration_plate TEXT NOT NULL DEFAULT ''")
            if 'municipal_file_no' not in cols:
                con.execute("ALTER TABLE projects ADD COLUMN municipal_file_no TEXT NOT NULL DEFAULT ''")
            row = con.execute('SELECT project_id FROM projects ORDER BY created_at LIMIT 1').fetchone()
            if not row:
                now = _now()
                con.execute('INSERT INTO projects(project_id,name,address,postal_code,registration_plate,municipal_file_no,description,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',
                            ('PROJECT-MAIN','', '', '', '', '', '', now, now))

    def get_project(self) -> dict[str, Any]:
        with self.db.read() as con:
            row = con.execute('SELECT * FROM projects ORDER BY created_at LIMIT 1').fetchone()
        return dict(row) if row else {}

    def save_project(self, *, name: str, address: str, postal_code: str, registration_plate: str = '',
                     municipal_file_no: str = '', description: str = '') -> dict[str, Any]:
        p = self.get_project(); pid = p.get('project_id') or 'PROJECT-MAIN'; now = _now()
        with self.db.tx() as con:
            con.execute('''INSERT INTO projects(project_id,name,address,postal_code,registration_plate,municipal_file_no,description,created_at,updated_at)
                           VALUES(?,?,?,?,?,?,?,?,?)
                           ON CONFLICT(project_id) DO UPDATE SET name=excluded.name,address=excluded.address,
                           postal_code=excluded.postal_code,registration_plate=excluded.registration_plate,
                           municipal_file_no=excluded.municipal_file_no,description=excluded.description,updated_at=excluded.updated_at''',
                        (pid, name.strip(), address.strip(), postal_code.strip(), registration_plate.strip(),
                         municipal_file_no.strip(), description.strip(), p.get('created_at') or now, now))
        return self.get_project()

    def list_documents(self) -> list[dict[str, Any]]:
        p = self.get_project(); pid = p.get('project_id') or 'PROJECT-MAIN'
        with self.db.read() as con:
            rows = con.execute('SELECT * FROM project_documents WHERE project_id=? AND deleted_at IS NULL ORDER BY created_at DESC', (pid,)).fetchall()
        return [dict(r) for r in rows]

    def add_document(self, source_path: str | Path, *, document_type: str, title: str = '', notes: str = '') -> dict[str, Any]:
        src = Path(source_path)
        if not src.exists() or not src.is_file():
            raise FileNotFoundError(str(src))
        p = self.get_project(); pid = p.get('project_id') or 'PROJECT-MAIN'
        did = _id('DOC'); folder = self.documents_dir / pid; folder.mkdir(parents=True, exist_ok=True)
        safe_name = ''.join(ch for ch in src.name if ch not in '<>:"/\\|?*')
        dest = folder / f'{did}_{safe_name}'
        shutil.copy2(src, dest)
        now = _now()
        with self.db.tx() as con:
            con.execute('''INSERT INTO project_documents(document_id,project_id,document_type,title,local_path,notes,created_at,updated_at)
                           VALUES(?,?,?,?,?,?,?,?)''',
                        (did,pid,document_type.strip() or 'OTHER',title.strip() or src.stem,str(dest),notes.strip(),now,now))
        return self.get_document(did) or {}

    def get_document(self, document_id: str) -> Optional[dict[str, Any]]:
        with self.db.read() as con:
            r = con.execute('SELECT * FROM project_documents WHERE document_id=?', (document_id,)).fetchone()
        return dict(r) if r else None

    def delete_document(self, document_id: str) -> None:
        with self.db.tx() as con:
            con.execute('UPDATE project_documents SET deleted_at=?,updated_at=? WHERE document_id=?', (_now(),_now(),document_id))

    def open_document(self, document_id: str) -> None:
        d = self.get_document(document_id)
        if not d or d.get('deleted_at'):
            raise ValueError('سند پیدا نشد.')
        path = Path(d['local_path'])
        if not path.exists():
            raise FileNotFoundError(str(path))
        if os.name == 'nt':
            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            import subprocess
            subprocess.Popen(['xdg-open', str(path)])

    def print_document(self, document_id: str) -> None:
        d = self.get_document(document_id)
        if not d or d.get('deleted_at'):
            raise ValueError('سند پیدا نشد.')
        path = Path(d['local_path'])
        if not path.exists():
            raise FileNotFoundError(str(path))
        if os.name == 'nt':
            os.startfile(str(path), 'print')  # type: ignore[attr-defined]
        else:
            import subprocess
            subprocess.Popen(['lp', str(path)])
