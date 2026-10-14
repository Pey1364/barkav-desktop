from __future__ import annotations
import json,re,zipfile,uuid
from pathlib import Path
from typing import Any

DIG=str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩','01234567890123456789')
def norm(s):return re.sub(r'\s+',' ',str(s or '').translate(DIG).replace('ي','ی').replace('ك','ک').lower()).strip()
def toks(s):return {x for x in re.findall(r'[\wآ-ی]+',norm(s)) if len(x)>=3}
def _id():return 'HEX-'+uuid.uuid4().hex[:12].upper()

class HistoricalLearningV17:
    """Lightweight historical retrieval layer.

    Historical examples are references only. They never post to live accounting.
    The index can ingest Telegram JSON and WhatsApp text exports, and can later be
    enriched with verified phase/activity labels from user corrections.
    """
    def __init__(self,db):self.db=db;self._migrate()
    def _migrate(self):
        with self.db.tx() as con:con.executescript('''
        CREATE TABLE IF NOT EXISTS historical_examples_v17(
          example_id TEXT PRIMARY KEY,project_label TEXT,source_type TEXT,source_ref TEXT,event_date TEXT,
          text_content TEXT,vendor TEXT,item_text TEXT,phase_no INTEGER,phase_name TEXT,activity TEXT,
          verified INTEGER NOT NULL DEFAULT 0,notes TEXT,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_hist_v17_project ON historical_examples_v17(project_label,source_type);
        ''')
    def add(self,**d):
        with self.db.tx() as con:con.execute('''INSERT OR REPLACE INTO historical_examples_v17(example_id,project_label,source_type,source_ref,event_date,text_content,vendor,item_text,phase_no,phase_name,activity,verified,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',(_id(),d.get('project_label',''),d.get('source_type',''),d.get('source_ref',''),d.get('event_date',''),d.get('text_content',''),d.get('vendor',''),d.get('item_text',''),d.get('phase_no'),d.get('phase_name',''),d.get('activity',''),1 if d.get('verified') else 0,d.get('notes','')))
    def count(self):
        with self.db.read() as con:return int(con.execute('SELECT COUNT(*) FROM historical_examples_v17').fetchone()[0])
    def import_telegram_json(self,path,project_label='telegram_history'):
        obj=json.loads(Path(path).read_text(encoding='utf-8'));chats=[]
        if isinstance(obj,dict):
            root=obj.get('chats');chats=(root.get('list') if isinstance(root,dict) else root) or []
            if not chats and isinstance(obj.get('messages'),list):chats=[obj]
        n=0
        for ch in chats:
            for m in ch.get('messages') or []:
                text=m.get('text','')
                if isinstance(text,list):text=''.join(x if isinstance(x,str) else str(x.get('text') or '') for x in text)
                text=str(text or '').strip()
                if not text:continue
                self.add(project_label=project_label,source_type='TELEGRAM',source_ref=str(m.get('id') or ''),event_date=str(m.get('date') or ''),text_content=text);n+=1
        return n
    def import_whatsapp_zip(self,path,project_label='barkav0'):
        n=0
        with zipfile.ZipFile(path) as z:
            names=[x for x in z.namelist() if x.lower().endswith('.txt')]
            if not names:return 0
            raw=z.read(names[0])
        text=''
        for enc in ('utf-8-sig','utf-8','utf-16','cp1256'):
            try:text=raw.decode(enc);break
            except Exception:pass
        # Generic WhatsApp: date/time - sender: message. Continuations attach to last message.
        cur=None
        pat=re.compile(r'^(\d{1,4}[/.\-]\d{1,2}[/.\-]\d{1,4}),?\s+([^\-]+)\s+-\s+([^:]+):\s?(.*)$')
        for line in text.splitlines():
            m=pat.match(line)
            if m:
                cur={'date':m.group(1)+' '+m.group(2).strip(),'sender':m.group(3).strip(),'text':m.group(4).strip()}
                if cur['text']:
                    self.add(project_label=project_label,source_type='WHATSAPP',source_ref='',event_date=cur['date'],text_content=cur['text'],notes='sender='+cur['sender']);n+=1
            elif cur and line.strip():
                # Preserve continuation as a searchable context example.
                self.add(project_label=project_label,source_type='WHATSAPP_CONTEXT',source_ref='',event_date=cur['date'],text_content=line.strip(),notes='continuation');n+=1
        return n
    def suggestions(self,text,limit=5):
        q=toks(text)
        if not q:return []
        with self.db.read() as con:rows=[dict(r) for r in con.execute('SELECT * FROM historical_examples_v17 ORDER BY verified DESC,created_at DESC LIMIT 8000').fetchall()]
        scored=[]
        for r in rows:
            rt=toks(r.get('text_content'));inter=len(q & rt)
            if not inter:continue
            score=inter/max(1,len(q|rt));score+=0.15 if r.get('verified') else 0
            scored.append((score,r))
        scored.sort(key=lambda x:-x[0]);out=[]
        for score,r in scored[:limit]:r['similarity']=round(score,3);out.append(r)
        return out
