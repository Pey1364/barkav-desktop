from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
from typing import Any

_NS = {
    'm': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
}
_REL_NS = {'pr': 'http://schemas.openxmlformats.org/package/2006/relationships'}


def _col_to_index(col: str) -> int:
    n = 0
    for ch in col:
        if 'A' <= ch <= 'Z':
            n = n * 26 + (ord(ch) - 64)
    return n - 1


def _shared_strings(zf: zipfile.ZipFile) -> list[str]:
    shared: list[str] = []
    if 'xl/sharedStrings.xml' not in zf.namelist():
        return shared
    root = ET.fromstring(zf.read('xl/sharedStrings.xml'))
    for si in root.findall('m:si', _NS):
        texts = [t.text or '' for t in si.findall('.//m:t', _NS)]
        shared.append(''.join(texts))
    return shared


def _sheet_targets(zf: zipfile.ZipFile) -> list[tuple[str, str]]:
    wb_root = ET.fromstring(zf.read('xl/workbook.xml'))
    rel_root = ET.fromstring(zf.read('xl/_rels/workbook.xml.rels'))
    rels = {rel.attrib.get('Id'): rel.attrib.get('Target') for rel in rel_root.findall('pr:Relationship', _REL_NS)}
    out: list[tuple[str, str]] = []
    for sheet in wb_root.findall('m:sheets/m:sheet', _NS):
        name = str(sheet.attrib.get('name') or '')
        rel_id = sheet.attrib.get('{%s}id' % _NS['r'])
        target = rels.get(rel_id)
        if not target:
            continue
        if target.startswith('/'):
            target = target.lstrip('/')
        elif not target.startswith('xl/'):
            target = 'xl/' + target
        out.append((name, target))
    return out


def _read_sheet_xml(zf: zipfile.ZipFile, target: str, shared: list[str]) -> list[list[Any]]:
    root = ET.fromstring(zf.read(target))
    cells: dict[tuple[int, int], Any] = {}
    max_row = max_col = -1
    for c in root.findall('.//m:sheetData/m:row/m:c', _NS):
        ref = c.attrib.get('r', '')
        m = re.match(r'([A-Z]+)(\d+)', ref)
        if not m:
            continue
        col = _col_to_index(m.group(1)); row = int(m.group(2)) - 1
        typ = c.attrib.get('t')
        value: Any = None
        if typ == 'inlineStr':
            value = ''.join(t.text or '' for t in c.findall('.//m:is/m:t', _NS))
        else:
            v = c.find('m:v', _NS)
            raw = v.text if v is not None else None
            if raw is not None:
                if typ == 's':
                    try: value = shared[int(raw)]
                    except Exception: value = raw
                elif typ == 'b':
                    value = raw == '1'
                elif typ in ('str', 'e'):
                    value = raw
                else:
                    try:
                        num = float(raw)
                        value = int(num) if num.is_integer() else num
                    except Exception:
                        value = raw
        cells[(row, col)] = value
        max_row = max(max_row, row); max_col = max(max_col, col)
    if max_row < 0:
        return []
    rows = [[None] * (max_col + 1) for _ in range(max_row + 1)]
    for (r, c), v in cells.items():
        rows[r][c] = v
    return rows


def read_sheet(path: str | Path, *, name: str | None = None, index: int = 0) -> list[list[Any]]:
    """Read one worksheet using only the Python stdlib.

    Formula cells are read from the cached value stored in the xlsx.  This keeps
    Peymaan independent from Excel/openpyxl while allowing the budget workbook to
    remain formula-driven.
    """
    path = Path(path)
    with zipfile.ZipFile(path, 'r') as zf:
        shared = _shared_strings(zf)
        targets = _sheet_targets(zf)
        if name is not None:
            chosen = next((t for n, t in targets if n == name), None)
            if chosen is None:
                return []
        else:
            if index < 0 or index >= len(targets):
                return []
            chosen = targets[index][1]
        return _read_sheet_xml(zf, chosen, shared)


def read_first_sheet(path: str | Path) -> list[list[Any]]:
    return read_sheet(path, index=0)


def list_sheet_names(path: str | Path) -> list[str]:
    path = Path(path)
    with zipfile.ZipFile(path, 'r') as zf:
        return [name for name, _ in _sheet_targets(zf)]


def _to_amount(value: Any) -> int:
    try:
        n = int(round(float(value or 0)))
        return max(0, n)
    except Exception:
        return 0


def _parse_peymaan_32_phase_workbook(path: str | Path) -> list[dict[str, Any]]:
    """Parse the current Peymaan workbook: روکش + شیت اصلی + 32 phase sheets.

    - Phase order/name comes from روکش rows 4..35.
    - Activity estimate comes from column I (قیمت کل) of each phase sheet.
    - Duplicate activity titles inside one phase are disambiguated with the section
      name so they stay compatible with UNIQUE(phase_id,name) in SQLite.
    - Land purchase price is intentionally outside the phase-01 construction total;
      it is imported from the side block in the phase-01 sheet as a separate activity.
    """
    names = list_sheet_names(path)
    if 'روکش' not in names or 'شیت اصلی' not in names:
        return []
    cover = read_sheet(path, name='روکش')
    if len(cover) < 4:
        return []
    header = cover[2] if len(cover) > 2 else []
    if len(header) < 6 or str(header[0] or '').strip() != 'ردیف' or str(header[1] or '').strip() != 'شرح':
        return []

    phases: list[dict[str, Any]] = []
    for row in cover[3:]:
        if len(row) < 2:
            continue
        try:
            phase_no = int(float(row[0]))
        except Exception:
            continue
        if phase_no < 1 or phase_no > 32:
            continue
        phase_name = str(row[1] or '').strip()
        if not phase_name:
            continue
        prefix = f'{phase_no:02d}-'
        sheet_name = next((n for n in names if n.startswith(prefix)), None)
        if not sheet_name:
            # Keep the phase visible even when a future workbook temporarily lacks
            # its detail sheet. The estimate remains zero until the sheet returns.
            phases.append({'phase': phase_name, 'activities': []})
            continue

        rows = read_sheet(path, name=sheet_name)
        raw_acts: list[dict[str, Any]] = []
        for r in rows[3:]:  # row 4 onward; row 3 is the detail header
            if len(r) < 9:
                continue
            desc = str(r[2] or '').strip()
            if not desc:
                continue
            if desc == 'شرح' or str(r[0] or '').strip() == 'جمع کل فاز':
                continue
            section = str(r[1] or '').strip()
            estimate = _to_amount(r[8])
            raw_acts.append({'name': desc, 'section': section, 'estimate': estimate})

        # Phase 01: import land cost from the side information block (M/N).
        if phase_no == 1:
            for r in rows:
                if len(r) >= 14 and str(r[12] or '').strip() == 'بهای خرید زمین (تومان)':
                    land = _to_amount(r[13])
                    if land > 0:
                        raw_acts.insert(0, {'name': 'بهای خرید زمین', 'section': 'زمین', 'estimate': land})
                    break

        phases.append({'phase': phase_name, 'activities': _name_activities(raw_acts)})

    return phases if len(phases) >= 30 else []


def _parse_legacy_pair_template(path: str | Path) -> list[dict[str, Any]]:
    rows = read_first_sheet(path)
    if len(rows) < 5:
        raise ValueError('فایل اکسل برآورد خالی یا نامعتبر است.')
    width = max(len(r) for r in rows)
    for r in rows:
        if len(r) < width:
            r.extend([None] * (width - len(r)))
    phases: list[dict[str, Any]] = []
    for col in range(1, width, 2):
        phase = rows[2][col] if col < width else None
        if phase is None or not str(phase).strip():
            continue
        acts = []
        for rr in range(4, min(len(rows), 39)):
            name = rows[rr][col] if col < width else None
            estimate = rows[rr][col + 1] if col + 1 < width else None
            if name is None or not str(name).strip():
                continue
            acts.append({'name': str(name).strip(), 'estimate': _to_amount(estimate)})
        phases.append({'phase': str(phase).strip(), 'activities': acts})
    if not phases:
        raise ValueError('فاز ساخت در قالب اکسل پیدا نشد.')
    return phases


def _name_activities(raw_acts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Make activity names unique within a phase.

    SQLite holds UNIQUE(phase_id, name), and a workbook may well list the same
    description twice under different sections, so the section disambiguates
    first and a counter only if that is not enough.
    """

    counts: dict[str, int] = {}
    for a in raw_acts:
        counts[a['name']] = counts.get(a['name'], 0) + 1
    acts: list[dict[str, Any]] = []
    used: set[str] = set()
    for a in raw_acts:
        name = a['name']
        if counts.get(name, 0) > 1 and a['section']:
            name = f"{a['section']} — {name}"
        base = name
        suffix = 2
        while name in used:
            name = f'{base} ({suffix})'; suffix += 1
        used.add(name)
        acts.append({'name': name, 'estimate': int(a['estimate'])})
    return acts


def _parse_peymaan_v2_workbook(path: str | Path) -> list[dict[str, Any]]:
    """Parse the rebuilt reference workbook: روکش مالی + three price sheets.

    The phase sheets gained اولیه/بروز/واقعی columns for both quantity and
    rate, which pushed قیمت کل from column I to column M, and lost وضعیت and
    منبع. The estimate still comes from the first of the three - what the
    project was budgeted at - so a version imported from either layout means
    the same thing.
    """

    names = list_sheet_names(path)
    if 'روکش مالی' not in names:
        return []
    cover = read_sheet(path, name='روکش مالی')
    phases: list[dict[str, Any]] = []
    for row in cover[3:]:
        if len(row) < 3:
            continue
        try:
            phase_no = int(float(str(row[1]).strip()))
        except (TypeError, ValueError):
            continue
        if not 1 <= phase_no <= 32:
            continue
        phase_name = str(row[2] or '').strip()
        if not phase_name:
            continue
        sheet_name = next((n for n in names if n.startswith(f'{phase_no:02d}-')), None)
        if not sheet_name:
            phases.append({'phase': phase_name, 'activities': []})
            continue
        raw_acts: list[dict[str, Any]] = []
        for r in read_sheet(path, name=sheet_name)[4:]:
            if len(r) < 13:
                continue
            desc = str(r[2] or '').strip()
            if not desc or desc == 'شرح' or str(r[0] or '').strip() == 'جمع کل فاز':
                continue
            raw_acts.append({'name': desc, 'section': str(r[1] or '').strip(),
                             'estimate': _to_amount(r[12])})
        phases.append({'phase': phase_name, 'activities': _name_activities(raw_acts)})
    return phases if len(phases) >= 30 else []


def parse_phase_budget(path: str | Path) -> list[dict[str, Any]]:
    """Parse either Peymaan 32-phase workbook layout, or the old pair template."""
    phases = _parse_peymaan_32_phase_workbook(path)
    if phases:
        return phases
    phases = _parse_peymaan_v2_workbook(path)
    if phases:
        return phases
    return _parse_legacy_pair_template(path)
