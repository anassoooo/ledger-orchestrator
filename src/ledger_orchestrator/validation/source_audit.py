"""Fresh PDFium text read, independent of pdfplumber and extraction caches.

Reuses recorded source locations, so this is not independent semantic mapping.
Scanned sources are explicitly left for visual review.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import pypdfium2


def printed_numbers(text):
    # Integer TND profile. Do not silently accept decimal or malformed numbers.
    text=text.replace('\u00a0',' ').replace('\u202f',' ').replace('−','-')
    tokens=re.findall(r'(?<![\w.,])\(?-?\d+(?: +\d{3})*(?:[.,]\d+)?\)?(?![\w.,])',text)
    result=[]
    for token in tokens:
        if '.' in token or ',' in token:
            continue
        negative=token.startswith('(') or token.startswith('-')
        result.append((-1 if negative else 1)*int(re.sub(r'\D','',token)))
    return result


def positioned_numbers(textpage,box,rotation=0):
    """Separate columns by glyph geometry, not by spaces between thousands."""
    left,bottom,right,top=box
    glyphs=[]
    for i in range(textpage.count_chars()):
        ch=textpage.get_text_range(i,1)
        if ch not in '0123456789-()' or len(ch)!=1:
            continue
        x0,y0,x1,y1=textpage.get_charbox(i)
        if left<=(x0+x1)/2<=right and bottom<=(y0+y1)/2<=top:
            glyphs.append((y0,x0,y1,x1,ch) if rotation==90 else (x0,y0,x1,y1,ch))
    glyphs.sort(key=lambda g:g[0])
    groups=[]
    for g in glyphs:
        if not groups or g[0]-groups[-1][-1][2]>8 or abs(g[1]-groups[-1][-1][1])>4:
            groups.append([g])
        else:
            groups[-1].append(g)
    values=[]
    for group in groups:
        text=''.join(g[4] for g in group)
        if re.fullmatch(r'-?\d+|\(\d+\)',text):
            values.append(-int(text[1:-1]) if text.startswith('(') else int(text))
    return values


def audit_sources(report,root):
    docs={}
    hashes={}
    results=[]
    try:
        for year,info in report['documents'].items():
            path=root/'sources'/'STAR'/f'{year}.pdf'
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            if digest!=info['sha256']:
                raise ValueError(f'Source PDF changed: {year}')
            hashes[year]=digest
            docs[year]=pypdfium2.PdfDocument(path)
        for write in report['writes']:
            for position,original in enumerate(write.get('sources',[])):
                source=original
                route='direct'
                selected='current'
                if original.get('source_kind')=='native_comparative':
                    source=original['comparative_evidence']
                    route='native_comparative'
                    selected='previous'
                elif original.get('method')!='native' and original.get('cross_year_match'):
                    source=report['data'][str(write['year']+1)]['records'][original['code']]
                    route='next_year_native_comparative'
                    selected='previous'
                result=dict(sheet=write['sheet'],cell=write['cell'],year=write['year'],
                            code=write['code'],source_index=position,route=route,
                            expected=original['value'],source=source['source'],page=source['page'],
                            status='visual_review_required',selected_column=selected,
                            semantic_mapping_review='pending',text='',numbers=[])
                if source.get('method')!='native':
                    results.append(result)
                    continue
                year=Path(source['source']).stem
                page=docs[year][source['page']-1]
                textpage=page.get_textpage()
                try:
                    x0,y0,x1,y1=source['bbox']
                    rotation=page.get_rotation()
                    if rotation not in (0,90):
                        raise ValueError('Unsupported source page rotation')
                    box=(y0-1,x0-1,y1+1,x1+1) if rotation==90 else (x0-1,page.get_height()-y1-1,x1+1,page.get_height()-y0+1)
                    text=textpage.get_text_bounded(*box)
                    nums=positioned_numbers(textpage,box,rotation)
                finally:
                    textpage.close()
                    page.close()
                result.update(text=text,numbers=nums,bbox=source['bbox'])
                if source.get('previous') is not None:
                    # Balance/native note profiles place current and prior net last.
                    pair=[source['value'],source['previous']]
                    if len(nums)>=2 and nums[-2:]==pair:
                        read=nums[-1] if selected=='previous' else nums[-2]
                        result['status']='native_column_match' if read==original['value'] else 'amount_mismatch'
                    else:
                        result['status']='native_row_not_confirmed'
                else:
                    # Premium evidence bbox encloses a single numeric table cell.
                    result['status']='native_cell_match' if nums==[original['value']] else 'native_cell_not_confirmed'
                results.append(result)
    finally:
        for doc in docs.values():
            doc.close()
    return dict(source_run=report['run_id'],pdf_sha256=hashes,
                reader='PDFium; fresh native text; recorded coordinates reused',
                limitation='Numeric re-reading only; semantic mapping and scanned PDF review remain open.',
                counts=dict(Counter(r['status'] for r in results)),sources=results)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('report',type=Path)
    p.add_argument('--root',type=Path,default=Path('data'))
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    report=json.loads(args.report.read_text(encoding='utf-8'))
    result=audit_sources(report,args.root)
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'audit_sources.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# Relecture numérique des sources PDF','',
           'Nouvelle lecture PDFium, sans cache OCR et sans modification du classeur.',
           'Les coordonnées proviennent du rapport initial : la correspondance sémantique reste à auditer.',
           'Un montant confirmé ici peut encore être contesté par une autre page du document.','',
           '| Résultat | Nombre de références |','| --- | ---: |']
    labels={'native_column_match':'Montant et comparatif relus dans le texte natif',
            'native_cell_match':'Montant relu dans une cellule native',
            'visual_review_required':'Source scannée : contrôle visuel restant',
            'native_row_not_confirmed':'Ligne native non confirmée par ce lecteur',
            'native_cell_not_confirmed':'Cellule native non confirmée par ce lecteur',
            'amount_mismatch':'Montant divergent'}
    for status,count in result['counts'].items():
        lines.append(f'| {labels[status]} | {count} |')
    lines+=['','Les références ne sont pas des cellules distinctes : les regroupements de branches ont plusieurs sources.',
            'Les textes relus, colonnes et pages sont conservés dans audit_sources.json.','']
    (args.output/'AUDIT_SOURCES.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps(result['counts']))


if __name__=='__main__':
    main()
