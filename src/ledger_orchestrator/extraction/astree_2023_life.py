"""Native 2023 life premiums only; scanned non-life branches stay unqualified."""
import re
from ledger_orchestrator.extraction.core import lines,normalize
from ledger_orchestrator.extraction.astree_accounting import record,unique_row


def extract_2023_life(pages,source):
    year=2023
    if source!='sources/ASTREE/2023.pdf':raise ValueError('Unexpected ASTREE 2023 source')
    by_page={p['page']:p for p in pages}
    if len(by_page)!=len(pages) or not {1,4,5}<=by_page.keys():raise ValueError('Missing or duplicate statement pages')
    front=normalize(by_page[1]['text'])
    if not re.search(r'\bASTREE\b',front) or '2023' not in front or 'CONSOLID' in front:
        raise ValueError('Wrong individual document identity')
    evidence=[]
    for n,code,lo,hi in ((4,'PRNV11',320,365),(5,'PRV11',350,400)):
        page=by_page[n];text=normalize(page['text'])
        if page['method']!='native' or abs(page['width']-595.22)>1 or abs(page['height']-842)>1:
            raise ValueError('Unsupported 2023 statement layout or method')
        if not re.search(r'DINARS? TUNISIEN',text) or 'MILLIER' in text or 'MILLION' in text:
            raise ValueError('Unconfirmed TND units')
        if '31/12/2023' not in text or '31/12/2022' not in text:
            raise ValueError('Unconfirmed 2023 period')
        row=unique_row(page,code)
        header=[w for w in page['words'] if w['top']<min(x['top'] for x in row) and lo<=(w['x0']+w['x1'])/2<hi]
        if not any('BRUT' in normalize(w['text']) for w in header) or not any(w['text']=='31/12/2023' for w in header):
            raise ValueError('Unconfirmed gross/current column')
        evidence.append(record(page,row,lo,hi,year,source,code,code+' opérations brutes'))
    page=by_page[5]
    rows=[r for r in lines(page['words']) if any(w['text']=='PRV1' for w in r)]
    if len(rows)!=1:raise ValueError('Unconfirmed life statement subtotal')
    subtotal=record(page,rows[0],350,400,year,source,'PRV1','Total primes Vie brut')
    if subtotal['value']!=evidence[1]['value']:raise ValueError('Life statement total mismatch')
    return dict(status='needs_review',year=year,records=[],life=evidence[1],
                corroboration=[evidence[0],subtotal],checks={'life_statement_delta':0},
                mapped={'VIE':evidence[1]['value']},
                blocked=['AUTOMOBILE','INCENDIE','TRANSPORT','IRDS','GROUPE','TOTAL_NONVIE_TARGET','TOTAL_TARGET'],
                issues=['scanned_nonlife_ocr_unreliable'],production_enabled=False)
