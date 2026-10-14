from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from finance_db import FinanceDB, _id, _now


class AttachmentService:
    def __init__(self, db: FinanceDB, base_dir: str | Path):
        self.db = db
        self.root = Path(base_dir) / 'data' / 'attachments'
        self.root.mkdir(parents=True, exist_ok=True)

    def add_local(self, *, entity_type: str, entity_id: str, source_path: str | Path, document_type: str = 'RECEIPT') -> dict[str, Any]:
        src = Path(source_path)
        if not src.exists(): raise FileNotFoundError(str(src))
        aid = _id('ATT'); folder = self.root / entity_type.upper(); folder.mkdir(parents=True, exist_ok=True)
        safe = ''.join(ch for ch in src.name if ch not in '<>:"/\\|?*')
        dst = folder / f'{aid}_{safe}'; shutil.copy2(src, dst)
        mime = {'.jpg':'image/jpeg','.jpeg':'image/jpeg','.png':'image/png','.pdf':'application/pdf'}.get(src.suffix.lower(),'application/octet-stream')
        with self.db.tx() as con:
            con.execute('''INSERT INTO attachments(attachment_id,entity_type,entity_id,document_type,local_path,mime_type,created_at)
                           VALUES(?,?,?,?,?,?,?)''', (aid,entity_type.upper(),entity_id,document_type,str(dst),mime,_now()))
        return self.get(aid)

    def get(self, attachment_id: str) -> dict[str, Any]:
        with self.db.read() as con:
            r=con.execute('SELECT * FROM attachments WHERE attachment_id=?',(attachment_id,)).fetchone()
        return dict(r) if r else {}

    def list_for_entities(self, entities: list[tuple[str,str]]) -> list[dict[str, Any]]:
        if not entities: return []
        out=[]
        with self.db.read() as con:
            for typ,eid in entities:
                rows=con.execute('SELECT * FROM attachments WHERE entity_type=? AND entity_id=? ORDER BY created_at DESC',(typ.upper(),eid)).fetchall()
                out.extend(dict(r) for r in rows)
        return out

    def count_for_entities(self, entities: list[tuple[str,str]]) -> int:
        return len(self.list_for_entities(entities))

    def open(self, attachment_id: str) -> None:
        d=self.get(attachment_id); p=Path(d.get('local_path') or '')
        if not p.exists(): raise FileNotFoundError(str(p))
        if os.name=='nt': os.startfile(str(p))  # type: ignore[attr-defined]
        else:
            import subprocess; subprocess.Popen(['xdg-open',str(p)])
