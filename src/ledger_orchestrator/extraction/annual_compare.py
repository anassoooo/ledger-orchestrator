"""Bounded, read-only comparison with STAR annual report's individual asset table."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import pdfplumber
import pypdfium2
from ledger_orchestrator.extraction.core import lines,normalize,number


def extract_asset(page,section_text,header_text):
    text=normalize(header_text)
    section=normalize(section_text)
    if ('INDIVIDUELS 2025' not in section or 'CONSOLIDE' in text or
            not all(s in text for s in ['31/12/2025','31/12/2024','DINAR','AC613','AC541'])):
        raise ValueError('Annual report individual asset profile not verified')
    # Geometry of the reviewed page 26; missing signs remain None, never zero.
    bounds=[(.587,.665),(.665,.740),(.740,.813),(.813,.890)]
    records={}
    for row in lines([w for w in page.extract_words() if .235*page.width<=w['x0']<.890*page.width]):
        label=' '.join(w['text'] for w in row)
        match=re.match(r'^(AC\d{1,3})\b',normalize(label))
        if not match:
            continue
        vals=[]
        raw=[]
        for left,right in bounds:
            cell=' '.join(w['text'] for w in row if left*page.width<=(w['x0']+w['x1'])/2<right*page.width)
            raw.append(cell)
            try:
                vals.append(number(cell))
            except ValueError:
                vals.append(None)
        records[match[1]]=dict(code=match[1],page=26,label=label,
            gross=vals[0],provision=vals[1],value=vals[2],previous=vals[3],raw_columns=raw,
            net_delta=vals[0]-vals[1]-vals[2] if all(v is not None for v in vals[:3]) else None)
    if len(records)<35:
        raise ValueError('Incomplete annual report table')
    return records


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder',type=Path)
    parser.add_argument('report',type=Path)
    args=parser.parse_args()
    source=args.folder/'star_rapport_annuel_2025.pdf'
    doc=pypdfium2.PdfDocument(source)
    page=doc[25]
    textpage=page.get_textpage()
    header_text=textpage.get_text_bounded()
    textpage.close()
    page.close()
    doc.close()
    with pdfplumber.open(source) as pdf:
        records=extract_asset(pdf.pages[25],pdf.pages[24].extract_text() or '',header_text)
    report=json.loads(args.report.read_text(encoding='utf-8'))
    existing=report['data']['2025']['records']
    for code,r in records.items():
        old=existing.get(code)
        r['pipeline_value']=old['value'] if old else None
        r['pipeline_approved']=bool(old and old.get('approved'))
        r['difference']=r['value']-old['value'] if old and r['value'] is not None else None
    result=dict(source_url='https://www.cmf.tn/sites/default/files/pdfs/emetteurs/informations/rapports-societes/star_rapport_annuel_2025.pdf',
        sha256=hashlib.sha256(source.read_bytes()).hexdigest(),source_run=report['run_id'],
        scope='STAR individual accounts; annual report PDF page 26, not consolidated page 74',
        financial_writes=0,records=records)
    (args.folder/'comparison.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps([r for r in records.values() if r['difference'] or r['pipeline_value'] is None or abs(r['net_delta'] or 0)>3],ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
