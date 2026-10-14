"""Publish management rules and the default D1 land price into a reference copy.

Edit OOXML directly: saving with openpyxl would discard cached formula values
which the application's lightweight Excel importer needs before Excel is opened.
No workbook instructions are executed. Existing styles, +/- outline controls,
formulas, cached values, signed numbers and unrelated sheets are retained.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path
import posixpath
import re
import sys
from zipfile import ZipFile
from lxml import etree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from openpyxl.formula.tokenizer import Tokenizer
from project_management_rules187 import MANAGEMENT_RULES, MANAGEMENT_RULE_HEADING

MAIN = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PKG = 'http://schemas.openxmlformats.org/package/2006/relationships'
TYPES = 'http://schemas.openxmlformats.org/package/2006/content-types'
Q = lambda name: f'{{{MAIN}}}{name}'


def parse_xml(content):
    # Excel's mc:Ignorable/Choice attributes name namespace prefixes as text.
    # ElementTree drops unused declarations and renames prefixes on save;
    # lxml retains their scope even when the prefix is only used in an attribute.
    return ET.fromstring(content, parser=ET.XMLParser(resolve_entities=False, no_network=True))


def validate_excel_package(files):
    """Check Excel compatibility bindings and part/relationship integrity.

    A ZIP test or openpyxl read alone accepts unresolved mc:Ignorable prefixes
    and dangling worksheet drawings, both of which can prevent Excel opening.
    """
    compatibility = 'http://schemas.openxmlformats.org/markup-compatibility/2006'
    for path, content in files.items():
        if not path.endswith(('.xml', '.rels', '.vml')):
            continue
        root = parse_xml(content)
        rel_path = posixpath.join(posixpath.dirname(path), '_rels',
                                 posixpath.basename(path) + '.rels')
        rel_ids = ({r.get('Id') for r in parse_xml(files[rel_path])}
                   if rel_path in files else set())
        for node in root.iter():
            for attribute in ('Ignorable', 'MustUnderstand', 'ProcessContent',
                              'PreserveAttributes', 'PreserveElements'):
                for token in node.get(f'{{{compatibility}}}{attribute}', '').split():
                    prefix = token.split(':')[0]
                    if prefix not in node.nsmap:
                        raise ValueError(f'{path}: undeclared Excel compatibility prefix {prefix}')
            if node.tag == f'{{{compatibility}}}Choice':
                for prefix in node.get('Requires', '').split():
                    if prefix not in node.nsmap:
                        raise ValueError(f'{path}: undeclared Excel Choice prefix {prefix}')
            for key, value in node.attrib.items():
                if key.startswith(f'{{{REL}}}') and value not in rel_ids:
                    raise ValueError(f'{path}: missing relationship {value}')
        if path.endswith('.rels'):
            base = posixpath.dirname(posixpath.dirname(path))
            for relationship in root:
                if relationship.get('TargetMode') == 'External':
                    continue
                target = relationship.get('Target', '')
                resolved = (target.lstrip('/') if target.startswith('/') else
                            posixpath.normpath(posixpath.join(base, target)))
                if resolved not in files:
                    raise ValueError(f'{path}: missing package part {resolved}')


def rebased_range(ref, first, delta):
    return re.sub(r'(\$?[A-Z]{1,3}\$?)(\d+)',
                  lambda m: m[1] + str(int(m[2]) + (delta if int(m[2]) >= first else 0)), ref)


def rebase_formula(formula, owner, target, first, delta):
    tokens = Tokenizer('=' + formula)
    for token in tokens.items:
        if token.subtype != 'RANGE':
            continue
        ref = token.value
        if '!' in ref:
            prefix, cells = ref.rsplit('!', 1)
            if prefix.strip("'").replace("''", "'") != target:
                continue
            token.value = prefix + '!' + rebased_range(cells, first, delta)
        elif owner == target:
            token.value = rebased_range(ref, first, delta)
    return ''.join(token.value for token in tokens.items)


def set_cell(row, address, value, *, style=None, cached=None):
    cell = next((c for c in row if c.get('r') == address), None)
    if cell is None:
        cell = ET.SubElement(row, Q('c'), {'r': address})
    if style is None:
        style = cell.get('s')
    cell.clear()
    cell.set('r', address)
    if style is not None:
        cell.set('s', str(style))
    if isinstance(value, str) and value.startswith('='):
        ET.SubElement(cell, Q('f')).text = value[1:]
        if cached is not None:
            ET.SubElement(cell, Q('v')).text = str(cached)
    elif isinstance(value, str):
        cell.set('t', 'inlineStr')
        ET.SubElement(ET.SubElement(cell, Q('is')), Q('t')).text = value
    elif value is not None:
        ET.SubElement(cell, Q('v')).text = str(value)
    row[:] = sorted(row, key=lambda c: (len(re.sub(r'\d', '', c.get('r', ''))),
                                       re.sub(r'\d', '', c.get('r', ''))))


def clone_row(sheet, source, number):
    data = sheet.find(Q('sheetData'))
    old = next(r for r in data if int(r.get('r')) == source)
    row = deepcopy(old)
    row.set('r', str(number))
    for cell in row:
        cell.set('r', re.sub(r'\d+$', str(number), cell.get('r')))
        style, address = cell.get('s'), cell.get('r')
        cell.clear()
        cell.set('r', address)
        if style is not None:
            cell.set('s', style)
    data.append(row)
    data[:] = sorted(data, key=lambda r: int(r.get('r')))
    return row


def update_reference(source: Path, destination: Path):
    if source.resolve() == destination.resolve() or destination.exists():
        raise ValueError('Choose a new output file; the original is never overwritten.')
    with ZipFile(source) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    workbook = parse_xml(files['xl/workbook.xml'])
    rels = parse_xml(files['xl/_rels/workbook.xml.rels'])
    paths = {r.get('Id'): ('xl/' + r.get('Target').lstrip('/'))
             if not r.get('Target').startswith('/') else r.get('Target').lstrip('/') for r in rels}
    sheets = {s.get('name'): paths[s.get(f'{{{REL}}}id')] for s in workbook.find(Q('sheets'))}
    required = {'براورد کلی', '01-خرید زمین', 'قیمت خدمات', 'قوانین محاسبه بروز'}
    if not required <= sheets.keys():
        raise ValueError('The source must have the original 32-phase reference layout.')
    if 'قیمت زمین' in sheets:
        raise ValueError('Land sheet already exists; refusing to add duplicate rows.')
    roots = {name: parse_xml(files[path]) for name, path in sheets.items()}
    changed = set()

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
        for defined in workbook.iter(Q('definedName')):
            before = defined.text or ''
            defined.text = rebase_formula(before, '', target, first, delta)

    insert_rows('براورد کلی', 10, 2)
    insert_rows('01-خرید زمین', 8, 1)
    phase = roots['01-خرید زمین']
    row = clone_row(phase, 7, 8)
    values = [4, 'خرید زمین', 'خرید زمین', 'خرید زمین', 'مترمربع', 0, '=F8', None,
              "='قیمت زمین'!D4", "='قیمت زمین'!E4", "='قیمت زمین'!F4", 1,
              '=F8*I8*L8', '=G8*J8*L8', '=H8*K8*L8']
    for col, value in zip('ABCDEFGHIJKLMNO', values):
        set_cell(row, f'{col}8', value, cached=0)
    total = next(r for r in phase.find(Q('sheetData')) if r.get('r') == '9')
    for col in 'MNO':
        set_cell(total, f'{col}9', f'=SUM({col}5:{col}8)', cached=0)

    overall = roots['براورد کلی']
    group = clone_row(overall, 6, 10)
    set_cell(group, 'B10', 'D. خرید زمین')
    group.set('outlineLevel', '1')
    row = clone_row(overall, 7, 11)
    row.set('outlineLevel', '2')
    for col, value in {'B': '01-4', 'C': 'خرید زمین', 'D': 1}.items():
        set_cell(row, f'{col}11', value)
    for col, source_col in zip('EFGHIJKLMN', 'EIJKFGHMNO'):
        set_cell(row, f'{col}11', f"='01-خرید زمین'!{source_col}8", cached=0 if col != 'E' else None)
    # A text cache is required for the land unit in a formula cell.
    unit = next(c for c in row if c.get('r') == 'E11')
    unit.set('t', 'str')
    ET.SubElement(unit, Q('v')).text = 'مترمربع'
    total = next(r for r in overall.find(Q('sheetData')) if r.get('r') == '12')
    for col in 'LMN':
        cell = next(c for c in total if c.get('r') == f'{col}12')
        cell.find(Q('f')).text = f'SUM({col}7:{col}11)'

    rules = roots['قوانین محاسبه بروز']
    data = rules.find(Q('sheetData'))
    last = max(int(r.get('r')) for r in data)
    row = clone_row(rules, 4, last + 1)
    set_cell(row, f'A{last+1}', MANAGEMENT_RULE_HEADING)
    for number, (topic, text) in enumerate(MANAGEMENT_RULES, last + 2):
        row = clone_row(rules, 5, number)
        set_cell(row, f'A{number}', topic)
        set_cell(row, f'B{number}', text)
        row.set('ht', str(min(409, max(60, 15 * (text.count('\n') + 1)))))
        row.set('customHeight', '1')
    rules.find(Q('dimension')).set('ref', f'A1:B{last+1+len(MANAGEMENT_RULES)}')
    changed.add('قوانین محاسبه بروز')

    # Same first seven columns as the app's price-land table: one default D1 row.
    land = deepcopy(roots['قیمت خدمات'])
    # A new sheet does not own the source sheet's comments/VML relationships.
    # Carrying legacyDrawing rId1 without a new .rels part makes Excel repair it.
    for child in list(land):
        if child.tag == Q('conditionalFormatting') or any(
                key.startswith(f'{{{REL}}}') for node in child.iter() for key in node.attrib):
            land.remove(child)
    for key in list(land.attrib):
        if key.endswith('}uid'):
            del land.attrib[key]
    data = land.find(Q('sheetData'))
    data[:] = [r for r in data if int(r.get('r')) <= 4]
    for row in data:
        row[:] = [c for c in row if re.match(r'^([A-I])\d+$', c.get('r', ''))]
    land.find(Q('dimension')).set('ref', 'A1:I4')
    merges = land.find(Q('mergeCells'))
    if merges is not None:
        merges[:] = [m for m in merges if m.get('ref') == 'D2:F2']
        ET.SubElement(merges, Q('mergeCell'), {'ref': 'A1:I1'})
        merges.set('count', str(len(merges)))
    rows = {int(r.get('r')): r for r in data}
    set_cell(rows[1], 'A1', 'کاتالوگ قیمت زمین (برآورد اولیه / برآورد بروز / واقعی)')
    header = ['ردیف', 'عنوان', 'واحد', 'برآورد اولیه', 'برآورد بروز', 'واقعی',
              'فازهای مورد استفاده', 'ضریب رشد بروز', 'روش محاسبه بروز']
    for col, value in zip('ABCDEFGHI', header):
        set_cell(rows[3], f'{col}3', value)
    for col, value in zip('ABCDEFGHI', [1, 'خرید زمین', 'مترمربع', 0, 0, 0, '01',
                                       '=IFERROR(E4/D4,0)', 'ثبت دستی']):
        set_cell(rows[4], f'{col}4', value, cached=0)
    land.find(Q('sheetViews')).find(Q('sheetView')).set('rightToLeft', '1')
    for selection in land.iter(Q('selection')):
        selection.set('activeCell', 'A4')
        selection.set('sqref', 'A4')
    sheet_id = max(int(s.get('sheetId')) for s in workbook.find(Q('sheets'))) + 1
    used_ids = {r.get('Id') for r in rels}
    rel_id = f'rId{sheet_id}'
    while rel_id in used_ids:
        rel_id += 'L'
    new_path = f'xl/worksheets/sheet{sheet_id}.xml'
    ET.SubElement(workbook.find(Q('sheets')), Q('sheet'),
                  {'name': 'قیمت زمین', 'sheetId': str(sheet_id), f'{{{REL}}}id': rel_id})
    ET.SubElement(rels, f'{{{PKG}}}Relationship',
                  {'Id': rel_id, 'Type': REL + '/worksheet', 'Target': new_path[3:]})
    types = parse_xml(files['[Content_Types].xml'])
    ET.SubElement(types, f'{{{TYPES}}}Override', {'PartName': '/' + new_path,
        'ContentType': 'application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml'})
    # Excel rebuilds calculation order after row movement; cached values remain.
    for rel in list(rels):
        if rel.get('Type', '').endswith('/calcChain'):
            rels.remove(rel)
    for entry in list(types):
        if entry.get('PartName', '').endswith('/calcChain.xml'):
            types.remove(entry)
    files.pop('xl/calcChain.xml', None)
    calc = workbook.find(Q('calcPr'))
    if calc is not None:
        calc.set('fullCalcOnLoad', '1')
    for name in changed:
        files[sheets[name]] = ET.tostring(roots[name], encoding='utf-8', xml_declaration=True)
    files[new_path] = ET.tostring(land, encoding='utf-8', xml_declaration=True)
    for path, root in [('xl/workbook.xml', workbook), ('xl/_rels/workbook.xml.rels', rels),
                       ('[Content_Types].xml', types)]:
        files[path] = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    if 'docProps/app.xml' in files:
        properties = parse_xml(files['docProps/app.xml'])
        extended = 'http://schemas.openxmlformats.org/officeDocument/2006/extended-properties'
        variants = 'http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes'
        pairs = properties.find(f'{{{extended}}}HeadingPairs/{{{variants}}}vector')
        titles = properties.find(f'{{{extended}}}TitlesOfParts/{{{variants}}}vector')
        if pairs is not None and titles is not None:
            offset = 0
            for index in range(0, len(pairs), 2):
                label = pairs[index].find(f'{{{variants}}}lpstr')
                count = pairs[index + 1].find(f'{{{variants}}}i4')
                if count is None:
                    continue
                original_count = int(count.text)
                if label is not None and label.text == 'Worksheets':
                    count.text = str(original_count + 1)
                    title = ET.Element(f'{{{variants}}}lpstr')
                    title.text = 'قیمت زمین'
                    titles.insert(offset + original_count, title)
                    titles.set('size', str(len(titles)))
                    break
                offset += original_count
            files['docProps/app.xml'] = ET.tostring(properties, encoding='utf-8', xml_declaration=True)
    validate_excel_package(files)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(destination, 'w') as archive:
        for path, content in files.items():
            archive.writestr(path, content, compress_type=8)
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    print(update_reference(args.source, args.destination))
