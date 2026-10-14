"""Preserve native Excel parts while publishing artifact-authored phase-04 edits.

prepare() creates a coordinate manifest and rebases existing formulas mechanically.
finish() takes authored cells from an artifact-tool XLSX, retaining original styles,
formula caches and all unrelated package parts. Never overwrite the source here.
"""
from copy import deepcopy
import json
from pathlib import Path
import re
import sys
from zipfile import ZipFile, ZIP_DEFLATED
from lxml import etree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.update_management_reference187 import (Q, REL, parse_xml, clone_row,
    rebase_formula, set_cell, validate_excel_package)
from engineering_phase187 import group_of, SUPERVISION, SUPERVISION_COST, SUPERVISION_TAX, PAIRS

PHASE = '04-نظام مهندسی'
OVERALL = 'براورد کلی'


def package(path):
    with ZipFile(path) as archive:
        files = {n: archive.read(n) for n in archive.namelist()}
    wb = parse_xml(files['xl/workbook.xml'])
    rels = parse_xml(files['xl/_rels/workbook.xml.rels'])
    paths = {r.get('Id'): r.get('Target').lstrip('/') if r.get('Target').startswith('/') else 'xl/' + r.get('Target') for r in rels}
    sheets = {s.get('name'): paths[s.get(f'{{{REL}}}id')] for s in wb.find(Q('sheets'))}
    return files, wb, sheets


def text(cell, strings):
    if cell is None:
        return ''
    if cell.get('t') == 's':
        return strings[int(cell.find(Q('v')).text)]
    return ''.join(cell.itertext()) if cell.get('t') == 'inlineStr' else (cell.findtext(Q('v')) or '')


def prepare(source, stage, manifest):
    files, wb, paths = package(source)
    roots = {name: parse_xml(files[path]) for name, path in paths.items()}
    strings = [''.join(n.itertext()) for n in parse_xml(files['xl/sharedStrings.xml'])] if 'xl/sharedStrings.xml' in files else []
    changed = set()
    edits = []

    def edit(name, row, col, value, cached=None):
        edits.append(dict(sheet=name, cell=f'{col}{row}', value=value, cached=cached))

    def insert(target, first, delta):
        from tools.update_management_reference187 import rebased_range
        root = roots[target]
        for node in root.iter():
            tag = node.tag.split('}')[-1]
            if tag == 'row' and int(node.get('r')) >= first:
                node.set('r', str(int(node.get('r')) + delta))
            elif tag == 'c':
                node.set('r', rebased_range(node.get('r'), first, delta))
            for attr in ('ref', 'sqref', 'topLeftCell', 'activeCell'):
                if attr in node.attrib:
                    node.set(attr, rebased_range(node.get(attr), first, delta))
        changed.add(target)
        for owner, root in roots.items():
            for f in root.iter(Q('f')):
                after = rebase_formula(f.text or '', owner, target, first, delta)
                if after != f.text:
                    f.text = after
                    changed.add(owner)
        for defined in wb.iter(Q('definedName')):
            defined.text = rebase_formula(defined.text or '', '', target, first, delta)

    phase = roots[PHASE]
    original = {int(r.get('r')): r for r in phase.find(Q('sheetData'))}
    descriptions = {r: text(next((c for c in row if c.get('r') == f'C{r}'), None), strings) for r, row in original.items()}
    if any(title == SUPERVISION_COST for title in descriptions.values()):
        raise ValueError('This reference already contains the requested supervision summaries.')
    insert(PHASE, 15, 2)
    for row, title in ((15, SUPERVISION_COST), (16, SUPERVISION_TAX)):
        clone_row(phase, 5, row)
        for col, value in zip('ABCDEFGHIJKLMNO',
            [34 if row == 15 else 35, SUPERVISION, title, 'خدمات', 'مترمربع', 0, 0, '=IF(O%d=0,0,$F$5)' % row, 0, 0,
             '=IF(H%d>0,O%d/H%d,0)' % (row, row, row), 1, 0, 0, None]):
            edit(PHASE, row, col, value, 0 if isinstance(value, str) and value.startswith('=') else None)
    phase_rows = {}
    for old in range(5, 38):
        number = old if old < 15 else old + 2
        title = descriptions[old]
        phase_rows[f'04-{old-4}'] = (number, title)
        group = group_of(dict(phase_no=4, description=title))
        if group:
            edit(PHASE, number, 'B', group)
        if title.startswith('مالیات'):
            for col in 'IJ':
                edit(PHASE, number, col, f'={col}{number-1}*10%')
            edit(PHASE, number, 'F', f'=F{number-1}')
            edit(PHASE, number, 'G', f'=G{number-1}')
        if group == SUPERVISION:
            for col in 'HKO':
                edit(PHASE, number, col, 0)
    phase_rows['04-34'] = (15, SUPERVISION_COST)
    phase_rows['04-35'] = (16, SUPERVISION_TAX)

    # Rebuild only this phase's overall block; other phases retain their IDs/data.
    overall = roots[OVERALL]
    data = overall.find(Q('sheetData'))
    leaves = {text(next((c for c in row if c.get('r') == f'B{row.get("r")}'), None), strings): deepcopy(row)
              for row in data if 47 <= int(row.get('r')) <= 79}
    order = [SUPERVISION] + [label for _, label in PAIRS] + ['سایر هزینه‌های نظام مهندسی']
    grouped = {label: [] for label in order}
    for ref, (p_row, title) in phase_rows.items():
        grouped[group_of(dict(phase_no=4, description=title)) or order[-1]].append((ref, p_row, title))
    count = sum(len(items) + 1 for items in grouped.values())
    insert(OVERALL, 80, count - 33)
    data[:] = [r for r in data if not 47 <= int(r.get('r')) <= 79]
    leaf_numbers = []
    headers = {}
    number = 47
    for label, items in grouped.items():
        headers[label] = number
        header = clone_row(overall, 45, number)
        header.set('outlineLevel', '2')
        edit(OVERALL, number, 'B', 'فاز فرعی')
        edit(OVERALL, number, 'C', label)
        edit(OVERALL, number, 'D', 4)
        header_number = number
        number += 1
        group_leaves = []
        for ref, p_row, title in items:
            row = clone_row(overall, 45, number)
            template = leaves.get(ref, next(iter(leaves.values())))
            template_styles = {re.sub(r'\d+$', '', c.get('r')): c.get('s') for c in template}
            for cell in row:
                style = template_styles.get(re.sub(r'\d+$', '', cell.get('r')))
                if style is None:
                    cell.attrib.pop('s', None)
                else:
                    cell.set('s', style)
            row.set('outlineLevel', '3')
            group_leaves.append(number)
            leaf_numbers.append(number)
            for col, value in {'B': ref, 'C': title, 'D': 4}.items():
                edit(OVERALL, number, col, value)
            for col, source_col in zip('EFGHIJKLMN', 'EIJKFGHMNO'):
                source_row = next(r for r in phase.find(Q('sheetData')) if int(r.get('r')) == p_row)
                source_cell = next((c for c in source_row if c.get('r') == f'{source_col}{p_row}'), None)
                cached = source_cell.findtext(Q('v')) if source_cell is not None and source_col != 'E' else None
                edit(OVERALL, number, col, f"='{PHASE}'!{source_col}{p_row}", cached or (0 if source_col != 'E' else None))
            number += 1
        for col in 'LM':
            cached = sum(float(e.get('cached') or 0) for e in edits if e['sheet'] == OVERALL and e['cell'] in {f'{col}{r}' for r in group_leaves})
            edit(OVERALL, header_number, col, '=SUM(' + ','.join(f'{col}{r}' for r in group_leaves) + ')', cached)
        if label == order[-1]:
            edit(OVERALL, header_number, 'N', '=SUM(' + ','.join(f'N{r}' for r in group_leaves) + ')')
    for label, items in grouped.items():
        if label == order[-1]:
            continue
        if label == SUPERVISION:
            targets = [(15, .9), (16, .1)]
        else:
            targets = [(p_row, .1 if title.startswith('مالیات') else .9) for _, p_row, title in items]
        for p_row, share in targets:
            edit(PHASE, p_row, 'O', f"='{OVERALL}'!N{headers[label]}*{share}", 0)
            edit(PHASE, p_row, 'H', f'=IF(O{p_row}=0,0,$F$5)', 0)
            edit(PHASE, p_row, 'K', f'=IF(H{p_row}>0,O{p_row}/H{p_row},0)', 0)
    total_row = number
    for col in 'LMN':
        edit(OVERALL, total_row, col, '=SUM(' + ','.join(f'{col}{r}' for r in leaf_numbers) + ')')
    for col in 'MNO':
        edit(PHASE, 40, col, f'=SUM({col}5:{col}39)')
    for row in overall.find(Q('sheetData')):
        if 45 <= int(row.get('r')) <= total_row:
            row.attrib.pop('hidden', None)
    for row in phase.find(Q('sheetData')):
        if int(row.get('r')) in (15, 16):
            row.attrib.pop('hidden', None)
    for name in changed:
        files[paths[name]] = ET.tostring(roots[name], encoding='UTF-8', xml_declaration=True)
    calc = wb.find(Q('calcPr'))
    if calc is not None:
        calc.set('fullCalcOnLoad', '1')
    files['xl/workbook.xml'] = ET.tostring(wb, encoding='UTF-8', xml_declaration=True)
    # Excel rebuilds this derived chain; its old coordinates are invalid after
    # structural row edits. Remove the chain and its package declarations.
    rel_path = 'xl/_rels/workbook.xml.rels'
    rels = parse_xml(files[rel_path])
    for rel in list(rels):
        if rel.get('Type', '').endswith('/calcChain'):
            target = rel.get('Target', '')
            files.pop(target.lstrip('/') if target.startswith('/') else 'xl/' + target, None)
            rels.remove(rel)
    files[rel_path] = ET.tostring(rels, encoding='UTF-8', xml_declaration=True)
    types = parse_xml(files['[Content_Types].xml'])
    for node in list(types):
        if node.get('ContentType', '').endswith('calcChain+xml'):
            types.remove(node)
    files['[Content_Types].xml'] = ET.tostring(types, encoding='UTF-8', xml_declaration=True)
    validate_excel_package(files)
    with ZipFile(stage, 'w', ZIP_DEFLATED) as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    Path(manifest).write_text(json.dumps(edits, ensure_ascii=False), encoding='utf-8')


def finish(stage, authored, manifest, destination):
    files, _, paths = package(stage)
    amendments, _, authored_paths = package(authored)
    originals = {name: parse_xml(files[paths[name]]) for name in (PHASE, OVERALL)}
    authored_roots = {name: parse_xml(amendments[authored_paths[name]]) for name in originals}
    authored_strings = [''.join(n.itertext()) for n in parse_xml(amendments['xl/sharedStrings.xml'])] if 'xl/sharedStrings.xml' in amendments else []
    for edit in json.loads(Path(manifest).read_text(encoding='utf-8')):
        name, address = edit['sheet'], edit['cell']
        root = originals[name]
        row = next(r for r in root.find(Q('sheetData')) if int(r.get('r')) == int(re.search(r'\d+', address)[0]))
        authored_cell = next((c for c in authored_roots[name].iter(Q('c')) if c.get('r') == address), None)
        if authored_cell is None and edit['value'] is not None:
            raise ValueError(f'Missing authored cell {name}!{address}')
        if edit['value'] is not None and not (isinstance(edit['value'], str) and edit['value'].startswith('=')):
            assert text(authored_cell, authored_strings) == str(edit['value']), f'Authored value mismatch {name}!{address}'
        # Values/formulas are verified against the authoring manifest. Native styles
        # and cache values are retained from the original, not the engine's roundtrip.
        cached = edit.get('cached')
        old = next((c for c in row if c.get('r') == address), None)
        if cached is None and old is not None and isinstance(edit['value'], str) and edit['value'].startswith('='):
            cached = old.findtext(Q('v'))
        set_cell(row, address, edit['value'], cached=cached)
        if edit['value'] is not None and isinstance(edit['value'], str) and edit['value'].startswith('='):
            assert authored_cell.findtext(Q('f')) == edit['value'][1:]
        # Overall unit links need a string cache for the application's fast reader.
        if name == OVERALL and address.startswith('E') and isinstance(edit['value'], str) and edit['value'].startswith('='):
            cell = next(c for c in row if c.get('r') == address)
            p_row = int(re.search(r'E(\d+)$', edit['value'])[1])
            phase_row = next(r for r in originals[PHASE].find(Q('sheetData')) if int(r.get('r')) == p_row)
            p_cell = next(c for c in phase_row if c.get('r') == f'E{p_row}')
            strings = [''.join(n.itertext()) for n in parse_xml(files['xl/sharedStrings.xml'])] if 'xl/sharedStrings.xml' in files else []
            unit = text(p_cell, strings)
            cell.set('t', 'str')
            if cell.find(Q('v')) is None:
                ET.SubElement(cell, Q('v'))
            cell.find(Q('v')).text = unit
    for name, root in originals.items():
        files[paths[name]] = ET.tostring(root, encoding='UTF-8', xml_declaration=True)
    validate_excel_package(files)
    with ZipFile(destination, 'w', ZIP_DEFLATED) as archive:
        for name, value in files.items():
            archive.writestr(name, value)
