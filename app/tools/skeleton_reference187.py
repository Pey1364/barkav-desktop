"""Publish the phase 08 groups (میلگرد، آزمایشگاه) into a copy of the reference workbook: python tools/skeleton_reference187.py SOURCE NEW_FILE (never overwrites; OOXML edit keeps caches)."""
import re
import sys
from copy import deepcopy
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
from lxml import etree as ET
from tools.update_management_reference187 import (Q, REL, parse_xml, clone_row, rebase_formula, rebased_range,
                                                  set_cell, validate_excel_package)

SOURCE, DEST = Path(sys.argv[1]), Path(sys.argv[2])
PHASE, OVERALL, PRICE = '08-اسکلت', 'براورد کلی', 'قیمت خدمات'
LAB = (('آزمایشگاه بتن', 29), ('آزمایشگاه میلگرد', 28))  # title, row of its price in «قیمت خدمات»

with ZipFile(SOURCE) as archive:
    files = {n: archive.read(n) for n in archive.namelist()}
wb = parse_xml(files['xl/workbook.xml'])
rels = parse_xml(files['xl/_rels/workbook.xml.rels'])
rel_paths = {r.get('Id'): r.get('Target').lstrip('/') if r.get('Target').startswith('/') else 'xl/' + r.get('Target')
             for r in rels}
sheets = {s.get('name'): rel_paths[s.get(f'{{{REL}}}id')] for s in wb.find(Q('sheets'))}
roots = {name: parse_xml(files[path]) for name, path in sheets.items()}
strings = [''.join(n.itertext()) for n in parse_xml(files['xl/sharedStrings.xml'])] if 'xl/sharedStrings.xml' in files else []
changed = set()


def text(cell):
    if cell is None:
        return ''
    if cell.get('t') == 's':
        return strings[int(cell.find(Q('v')).text)]
    if cell.get('t') == 'inlineStr':
        return ''.join(cell.itertext())
    return cell.findtext(Q('v')) or ''


def rows_of(name):
    return {int(r.get('r')): r for r in roots[name].find(Q('sheetData'))}


def cell_of(name, address):
    row = rows_of(name)[int(re.search(r'\d+', address)[0])]
    return next((c for c in row if c.get('r') == address), None)


def insert_rows(target, first, delta):
    sheet = roots[target]
    for element in sheet.iter():
        local = element.tag.split('}')[-1]
        if local == 'row' and int(element.get('r')) >= first:
            element.set('r', str(int(element.get('r')) + delta))
        elif local == 'c':
            element.set('r', rebased_range(element.get('r'), first, delta))
        for attr in ('ref', 'sqref', 'topLeftCell', 'activeCell'):
            if attr in element.attrib:
                element.set(attr, rebased_range(element.get(attr), first, delta))
    changed.add(target)
    for owner, root in roots.items():
        for formula in root.iter(Q('f')):
            before = formula.text or ''
            after = rebase_formula(before, owner, target, first, delta)
            if after != before:
                formula.text = after
                changed.add(owner)
    for defined in wb.iter(Q('definedName')):
        defined.text = rebase_formula(defined.text or '', '', target, first, delta)


def find_row(name, column, value, start=1):
    for number, row in sorted(rows_of(name).items()):
        if number >= start and text(next((c for c in row if c.get('r') == f'{column}{number}'), None)) == value:
            return number
    raise ValueError(f'{name}: {value} not found')


# ---- the original layout, before anything moves
if any(text(c) == 'آزمایشگاه بتن' for r in rows_of(PHASE).values() for c in r):
    raise ValueError('The reference already has the laboratory lines.')
head = find_row(OVERALL, 'B', 'فاز 08 — اسکلت')
first_leaf = find_row(OVERALL, 'B', '08-1', head)
contractor = find_row(OVERALL, 'B', 'B. پیمانکار', head)
total = find_row(OVERALL, 'B', 'جمع فاز 08', head)
last_leaf = total - 1
while text(cell_of(OVERALL, f'B{last_leaf}')) == '':
    last_leaf -= 1
old_total = find_row(PHASE, 'A', 'جمع کل فاز')

# ---- phase sheet: two lines before the total, the rebar sizes named as a section
insert_rows(PHASE, old_total, 2)
phase_rows = rows_of(PHASE)
for number in range(5, 9):
    set_cell(phase_rows[number], f'B{number}', 'میلگرد')
new_phase_rows = {}
for index, (title, price_row) in enumerate(LAB):
    number = old_total + index
    row = clone_row(roots[PHASE], old_total - 1, number)
    prices = [text(cell_of(PRICE, f'{col}{price_row}')) for col in 'DEF']
    # cached values of the price links come from the price sheet's own caches
    values = [(21 + index), 'آزمایشگاه', title, 'خدمات', 'مورد', 0, f'=F{number}', None,
              f"='{PRICE}'!$D${price_row}", f"='{PRICE}'!$E${price_row}", f"='{PRICE}'!$F${price_row}", 1,
              f'=F{number}*I{number}*L{number}', f'=G{number}*J{number}*L{number}', f'=H{number}*K{number}*L{number}']
    caches = [None, None, None, None, None, None, 0, None, prices[0] or 0, prices[1] or 0, prices[2] or 0, None, 0, 0, 0]
    for col, value, cached in zip('ABCDEFGHIJKLMNO', values, caches):
        set_cell(row, f'{col}{number}', value, cached=cached)
    new_phase_rows[title] = number
total_row = old_total + 2
for col in 'MNO':
    cell = cell_of(PHASE, f'{col}{total_row}')
    cell.find(Q('f')).text = f'SUM({col}5:{col}{total_row - 1})'

# ---- overall sheet: a «C. خدمات» block for the lab lines, then a sub-phase header over the rebar sizes
insert_rows(OVERALL, total, 4)
insert_rows(OVERALL, first_leaf, 1)
shift = 1
c_row, lab_header = total + shift, total + shift + 1
lab_rows = [lab_header + 1, lab_header + 2]
total_now = total + 4 + shift
contractor_now = contractor + shift
sample_header = find_row(OVERALL, 'B', 'فاز فرعی')
sample_leaf = sample_header + 1


def styled_clone(source, number, level):
    row = clone_row(roots[OVERALL], source, number)
    row.set('outlineLevel', str(level))
    return row


rebar_header = first_leaf
row = styled_clone(sample_header, rebar_header, 2)
set_cell(row, f'B{rebar_header}', 'فاز فرعی')
set_cell(row, f'C{rebar_header}', 'میلگرد')
set_cell(row, f'D{rebar_header}', 8)
leaf_rows = rows_of(OVERALL)
for number in range(rebar_header + 1, rebar_header + 5):
    leaf_rows[number].set('outlineLevel', '3')
cached_sums = {}
for col in 'LMN':
    cached = sum(float(text(cell_of(OVERALL, f'{col}{n}')) or 0) for n in range(rebar_header + 1, rebar_header + 5))
    set_cell(row, f'{col}{rebar_header}', f'=SUM({col}{rebar_header + 1}:{col}{rebar_header + 4})', cached=cached)

row = styled_clone(contractor_now, c_row, int(rows_of(OVERALL)[contractor_now].get('outlineLevel') or 1))
set_cell(row, f'B{c_row}', 'C. خدمات')
row = styled_clone(sample_header, lab_header, 2)
set_cell(row, f'B{lab_header}', 'فاز فرعی')
set_cell(row, f'C{lab_header}', 'آزمایشگاه')
set_cell(row, f'D{lab_header}', 8)
for col in 'LMN':
    set_cell(row, f'{col}{lab_header}', f'=SUM({col}{lab_rows[0]}:{col}{lab_rows[1]})', cached=0)
for (title, _), number in zip(LAB, lab_rows):
    row = styled_clone(sample_leaf, number, 3)
    p_row = new_phase_rows[title]
    ref = f'08-{21 + [t for t, _ in LAB].index(title)}'
    set_cell(row, f'B{number}', ref)
    set_cell(row, f'C{number}', title)
    set_cell(row, f'D{number}', 8)
    for col, source_col in zip('EFGHIJKLMN', 'EIJKFGHMNO'):
        cell_value = f"='{PHASE}'!{source_col}{p_row}"
        source = cell_of(PHASE, f'{source_col}{p_row}')
        cached = (source.findtext(Q('v')) if source is not None and source_col != 'E' else None)
        set_cell(row, f'{col}{number}', cell_value, cached=cached or (0 if col != 'E' else None))
    unit = next(c for c in row if c.get('r') == f'E{number}')
    unit.set('t', 'str')
    if unit.find(Q('v')) is None:
        ET.SubElement(unit, Q('v'))
    unit.find(Q('v')).text = 'مورد'
total_cells = rows_of(OVERALL)[total_now]
for col in 'LMN':
    cell = next(c for c in total_cells if c.get('r') == f'{col}{total_now}')
    cell.find(Q('f')).text = cell.find(Q('f')).text + f'+SUM({col}{lab_rows[0]}:{col}{lab_rows[1]})'
changed.update({PHASE, OVERALL})

for name in changed:
    files[sheets[name]] = ET.tostring(roots[name], encoding='UTF-8', xml_declaration=True)
calc = wb.find(Q('calcPr'))
if calc is not None:
    calc.set('fullCalcOnLoad', '1')
files['xl/workbook.xml'] = ET.tostring(wb, encoding='UTF-8', xml_declaration=True)
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
with ZipFile(DEST, 'w', ZIP_DEFLATED) as archive:
    for name, value in files.items():
        archive.writestr(name, value)
print('written', DEST, 'overall rows', rebar_header, c_row, lab_header, lab_rows, total_now, 'phase rows', new_phase_rows, total_row)
