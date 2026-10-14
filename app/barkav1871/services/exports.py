from __future__ import annotations

import html
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Iterable
from xml.sax.saxutils import escape


def _col_letter(n:int)->str:
    s=''
    while n:
        n,rem=divmod(n-1,26); s=chr(65+rem)+s
    return s


def export_xlsx(path:str|Path, headers:list[str], rows:list[list[Any]], title:str='گزارش') -> Path:
    """Create a minimal standards-compliant XLSX with no third-party spreadsheet dependency."""
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    all_rows=[headers]+rows
    def cell_xml(r:int,c:int,v:Any)->str:
        ref=f'{_col_letter(c)}{r}'
        if v is None: return f'<c r="{ref}"/>'
        if isinstance(v,bool): return f'<c r="{ref}" t="b"><v>{1 if v else 0}</v></c>'
        if isinstance(v,(int,float)) and not isinstance(v,bool): return f'<c r="{ref}"><v>{v}</v></c>'
        text=escape(str(v))
        return f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'
    sheet_rows=[]
    for ri,row in enumerate(all_rows,1):
        cells=''.join(cell_xml(ri,ci,v) for ci,v in enumerate(row,1))
        sheet_rows.append(f'<row r="{ri}">{cells}</row>')
    widths=''.join(f'<col min="{i}" max="{i}" width="{18 if i>1 else 14}" customWidth="1"/>' for i in range(1,max(1,len(headers))+1))
    sheet=f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetViews><sheetView workbookViewId="0" rightToLeft="1"/></sheetViews><cols>{widths}</cols><sheetData>{''.join(sheet_rows)}</sheetData></worksheet>'''
    content='''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>'''
    rels='''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'''
    wb=f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="{escape(title[:31] or 'Report')}" sheetId="1" r:id="rId1"/></sheets></workbook>'''
    wb_rels='''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'''
    styles='''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="1"><font><sz val="11"/><name val="Tahoma"/></font></fonts><fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs></styleSheet>'''
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml',content); z.writestr('_rels/.rels',rels); z.writestr('xl/workbook.xml',wb); z.writestr('xl/_rels/workbook.xml.rels',wb_rels); z.writestr('xl/worksheets/sheet1.xml',sheet); z.writestr('xl/styles.xml',styles)
    return path


def _pdf_font():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    candidates=[r'C:\Windows\Fonts\tahoma.ttf',r'C:\Windows\Fonts\arial.ttf','/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']
    for p in candidates:
        if Path(p).exists():
            try: pdfmetrics.registerFont(TTFont('PeymaanFont',p)); return 'PeymaanFont'
            except Exception: pass
    return 'Helvetica'


def _rtl(s:Any)->str:
    text=str(s if s is not None else '')
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
    except ImportError as exc:
        raise RuntimeError(
            'برای خروجی PDF فارسی، وابستگی‌های arabic-reshaper و python-bidi لازم هستند. '
            'وابستگی‌های لازم برای خروجی PDF نصب نشده‌اند.'
        ) from exc
    return get_display(arabic_reshaper.reshape(text))


def export_pdf(path:str|Path,headers:list[str],rows:list[list[Any]],title:str='گزارش',summary_lines:list[str]|None=None)->Path:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True); font=_pdf_font()
    doc=SimpleDocTemplate(str(path),pagesize=landscape(A4),rightMargin=24,leftMargin=24,topMargin=24,bottomMargin=24)
    story=[]; style=ParagraphStyle('rtl',fontName=font,fontSize=10,alignment=TA_RIGHT,leading=14)
    title_style=ParagraphStyle('title',fontName=font,fontSize=15,alignment=TA_RIGHT,leading=20)
    story.append(Paragraph(_rtl(title),title_style)); story.append(Spacer(1,8))
    for line in summary_lines or []: story.append(Paragraph(_rtl(line),style))
    if summary_lines: story.append(Spacer(1,10))
    data=[[_rtl(h) for h in headers]]+[[_rtl(v) for v in row] for row in rows]
    if not data: data=[[_rtl('بدون داده')]]
    table=Table(data,repeatRows=1)
    table.setStyle(TableStyle([('FONTNAME',(0,0),(-1,-1),font),('FONTSIZE',(0,0),(-1,-1),8),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#153B5B')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('GRID',(0,0),(-1,-1),0.4,colors.HexColor('#B8C2CC')),('ALIGN',(0,0),(-1,-1),'RIGHT'),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F5F8FA')])]))
    story.append(table); doc.build(story); return path


def print_file(path:str|Path)->None:
    p=str(Path(path))
    if os.name=='nt': os.startfile(p,'print')  # type: ignore[attr-defined]
    else:
        import subprocess; subprocess.Popen(['lp',p])
