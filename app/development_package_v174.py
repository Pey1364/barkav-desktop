from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

SAFE_SOURCE_FILES = [
    'dashboard_stage18_3.py',
    'ui_stage18_3.py',
    'launcher_stage18_3.py',
    'project_center_stage18_3.py',
    'project_runner_stage18_3.py',
    'tests/test_stage18_3_regression.py',
    'tests/test_stage18_3_ui.py',
    'tests/test_stage18_3_24_point_acceptance.py',
    'attachment_service.py',
    'project_registry.py',
    'project_center_stage15.py',
    'unit_service.py',
    'BARKAV_18.3.bat',
    'CREATE_SHORTCUT.bat',
    'README_18.3_TEST.txt',
    'README_18.3_FINAL.txt',
    'TEST_PLAN_18.3.txt',
    'TEST_RESULTS_18.3_FINAL.txt',
    'BARKAV_V18.3_24_POINT_CHECKLIST_COMPLETED_2026-08-19.txt',
    'VERSION.txt',
    'assets/BARKAV.ico',
    'assets/BARKAV_shortcut.png',
    'assets/barkav_brand_header.png',
    'dashboard_stage18_2.py',
    'approval_service.py',
    'ui_stage10.py',
    'dashboard_stage16_3.py',
    'requirements_stage9.txt',
    'tests/test_stage18_2_regression.py',
    'launcher_stage18_2.py',
    'dashboard_stage18_1.py',
    'launcher_stage18_1.py',
    'dashboard_stage18.py',
    'launcher_stage18.py',
    'v18_store.py',
    'receipt_intelligence.py',
    'receipt_ai_provider.py',
    'telegram_stage15.py',
    'phase04_v18.py',
    'dashboard_stage17.py',
    'dashboard_stage17_5.py',
    'phase_intelligence_v175.py',
    'market_service_v17.py',
    'historical_learning_v17.py',
    'budget_rich_v163.py',
    'finance_db.py',
    'ai_parser.py',
    'local_fallback_parser.py',
    'requirements_stage15.txt',
    'phase_master.json',
    'launcher_stage17.py',
    'development_package_v174.py',
    'tests/test_v175_regression.py',
    'tests/test_v175_multi_cheque.py',
    'tests/test_v175_ui_smoke.py',
    'tests/test_v18_core.py',
    'tests/test_v18_ui_smoke.py',
    'tests/test_stage18_1_receipt.py',
    'tests/test_stage18_2_ui.py',
    'pytest.ini',
]

SENSITIVE_NAMES = {
    'secrets.local.json', 'secrets.json', '.env', 'token.txt',
}

def _is_sensitive(path: Path) -> bool:
    name = path.name.lower()
    if name in {x.lower() for x in SENSITIVE_NAMES}:
        return True
    parts = {p.lower() for p in path.parts}
    if 'data' in parts or 'runtime' in parts or '__pycache__' in parts:
        return True
    if path.suffix.lower() in {'.sqlite', '.sqlite3', '.db'}:
        return True
    return False

def build_development_package(base_dir: Path, dest: Path, version: str) -> dict:
    base_dir = Path(base_dir).resolve()
    dest = Path(dest).resolve()
    docs = base_dir / 'docs' / 'handoff'
    if not docs.exists():
        raise FileNotFoundError('پوشه docs/handoff پیدا نشد.')

    temp = Path(tempfile.mkdtemp(prefix='barkav_dev_'))
    try:
        out_handoff = temp / 'handoff'
        # Handoff/checkpoints are development context. Raw historical chat/example
        # corpora are user data and are deliberately excluded from this safe package.
        shutil.copytree(
            docs, out_handoff, dirs_exist_ok=True,
            ignore=shutil.ignore_patterns('historical_seed_*.jsonl','*.sqlite','*.sqlite3','*.db','*.log')
        )
        (temp / 'ACTIVE_VERSION.txt').write_text(str(version), encoding='utf-8')
        (temp / 'PACKAGE_CREATED_AT.txt').write_text(datetime.now().isoformat(timespec='seconds'), encoding='utf-8')

        copied=[]
        for rel in SAFE_SOURCE_FILES:
            src = base_dir / rel
            if src.exists() and src.is_file() and not _is_sensitive(src.relative_to(base_dir)):
                dst = temp / 'source' / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                copied.append(rel)

        manifest = {
            'product': 'BARKAV — Engineering & Construction',
            'version': str(version),
            'created_at': datetime.now().isoformat(timespec='seconds'),
            'contains_live_database': False,
            'contains_secrets': False,
            'handoff': 'handoff/BARKAV_PROJECT_HANDOFF.md',
            'checkpoints_dir': 'handoff/checkpoints',
            'included_source_files': copied,
            'note_fa': 'این بسته برای ادامه توسعه در چت جدید است و عمداً دیتابیس زنده، پوشه data، runtime و secrets.local.json را شامل نمی‌شود.',
        }
        (temp / 'DEVELOPMENT_PACKAGE_MANIFEST.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        (temp / 'START_HERE_FA.txt').write_text(
            'برای ادامه پروژه در چت جدید:\n'
            '1) این ZIP را همراه آخرین ZIP برنامه ارسال کن.\n'
            '2) بگو فایل handoff/BARKAV_PROJECT_HANDOFF.md ابتدا کامل خوانده شود.\n'
            '3) سپس تغییر موردنظر را روی معماری موجود اعمال کن؛ از صفر بازطراحی نشود.\n'
            '4) برای حفظ حریم خصوصی، این بسته دیتابیس زنده و secrets.local.json ندارد.\n',
            encoding='utf-8'
        )

        dest.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(dest, 'w', zipfile.ZIP_DEFLATED) as z:
            for file in sorted(temp.rglob('*')):
                if file.is_file():
                    z.write(file, file.relative_to(temp))

        with zipfile.ZipFile(dest) as z:
            names=z.namelist()
            forbidden=[n for n in names if n.lower().endswith(('secrets.local.json','.sqlite3','.sqlite','.db','.log')) or n.lower().startswith('data/') or '/data/' in n.lower() or 'historical_seed_' in n.lower()]
            if forbidden:
                raise RuntimeError('بسته توسعه شامل فایل حساس شد: ' + ', '.join(forbidden[:5]))
        return {'path': str(dest), 'file_count': len(names), 'manifest': manifest}
    finally:
        shutil.rmtree(temp, ignore_errors=True)
