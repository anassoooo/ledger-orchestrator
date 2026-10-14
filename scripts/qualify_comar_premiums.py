"""Read-only COMAR premium candidate. Never admits values or writes Excel."""
import argparse
import hashlib
import json
import re
import unicodedata
from decimal import Decimal
from pathlib import Path

import pdfplumber

LAYOUTS = {
    2023: (35, [220,257,294,331,368,404,440,476,513,550,587,623,659,695,732,768], 9, (300,350)),
    2024: (37, [195,233,272,310,349,387,425,464,502,540,579,618,657,694,733,774], 9, (315,365)),
    2025: (39, [220,258,296,333,371,409,447,485,522,560,598,636,674,711,749,788], 12, (320,367)),
}
CATEGORIES = ['INCENDIE','TRAVAIL','RC','AUTOMOBILE','TRANSPORT','GROUPE',
              'BIENS','AGRICOLES','CONSTRUCTION','PERTE_EXPLOITATION','CAUTION',
              'ASSISTANCE','ACCIDENT_CORPOREL','ACCEPTATION','TOTAL']
HEADERS = ['INCENDIE','ACCIDENTTRAVAIL','RC','AUTOMOBILE','TRANSPORT','GROUPE',
           'DOMMAGESAUXBIENS','RISQUESAGRICOLES','CONSTRUCTION','PERTEDEPLOITATION',
           'CAUTION','ASSISTANCE','ACCIDENTCORPOREL','ACCEPTATION','TOTAL']


def normalize(text):
    return ''.join(c for c in unicodedata.normalize('NFKD',text.upper()) if not unicodedata.combining(c))


def read_amount(words):
    raw=' '.join(w['text'] for w in sorted(words,key=lambda w:w['x0']))
    if not raw.strip() or raw.strip() in ('-','‐','–','—'):
        return raw,None,'missing_or_dash'
    compact=re.sub(r'\s','',raw).replace(',','.')
    if not re.fullmatch(r'\d+(?:\.0+)?',compact):
        raise ValueError('Unsupported premium number syntax')
    return raw,int(Decimal(compact)),'numeric'


def row_at(page,token):
    words=page.extract_words()
    matches=[w for w in words if normalize(w['text'])==token]
    if len(matches)!=1:
        raise ValueError('Missing or ambiguous premium row: '+token)
    return [w for w in words if abs(w['top']-matches[0]['top'])<2]


def in_band(words,lo,hi):
    return [w for w in words if lo <= (w['x0']+w['x1'])/2 < hi]


def header_text(words):
    lines=[]
    for word in sorted(words,key=lambda w:(w['top'],w['x0'])):
        if not lines or abs(word['top']-lines[-1][0]['top'])>1:
            lines.append([])
        lines[-1].append(word)
    return ' '.join(''.join(w['text'] for w in sorted(line,key=lambda w:w['x0'])) for line in lines)


def category_headers(words,top,edges):
    # Include both header lines, including the upper 2025 labels.
    header_words=[w for w in words if top-40<w['top']<top-8 and w['x0']>190]
    result=[]
    for code,expected,lo,hi in zip(CATEGORIES,HEADERS,edges,edges[1:]):
        text=header_text(in_band(header_words,lo,hi))
        if re.sub('[^A-Z]','',normalize(text))!=expected:
            raise ValueError('Unconfirmed category identity: '+code)
        result.append(text)
    return result


def gross_header(words,year,band,row_top,date_bounds=None):
    header=[w for w in in_band(words,*band) if row_top-60<w['top']<row_top]
    tokens=[normalize(w['text']) for w in header]
    if tokens.count('BRUTES')!=1 or 'NETTES' in tokens or 'CESSIONS' in tokens:
        raise ValueError('Unconfirmed gross column')
    lo,hi=date_bounds or {2023:(90,102),2024:(96,106),2025:(79,90)}[year]
    date_words=[w for w in words if lo<w['top']<hi]
    for expected,band in ((year,(350,435)),(year-1,(455,550))):
        date=[w['text'] for w in in_band(date_words,*band)]
        if date != [str(expected) if year<2025 else f'31/12/{expected}']:
            raise ValueError('Unconfirmed current/comparative period column')


def life_candidate(doc,year,annex):
    readings=[]
    specifications=[(5,'PRV11',(320,373),'statement_gross'),
                    (annex-1,'EMISES',(460,520) if year!=2024 else (430,490),'annex_total'),
                    (annex+1,'EMISES',(425,525),'bridge')]
    for pn,token,band,meaning in specifications:
        page=doc.pages[pn-1];text=normalize(page.extract_text() or '')
        title=' '.join(text.splitlines()[:4])
        if str(year) not in title or 'VIE' not in title or 'NON VIE' in title:
            raise ValueError('Unconfirmed life statement identity')
        if pn!=5 and f'ANNEXE {12 if meaning=="annex_total" else 15}' not in title:
            raise ValueError('Unconfirmed life annex')
        row=row_at(page,token);top=min(w['top'] for w in row)
        if pn==5:
            gross_header(page.extract_words(),year,band,top,(90,102) if year==2023 else (79,90))
        elif meaning=='annex_total':
            heading=[w for w in in_band(page.extract_words(),*band) if top-50<w['top']<top]
            if [normalize(w['text']) for w in heading]!=['TOTAL']:
                raise ValueError('Unconfirmed life total column')
        words=in_band(row,*band);raw,value,state=read_amount(words)
        if value is None:raise ValueError('Missing life premium control')
        readings.append({'meaning':meaning,'page':pn,'raw':raw,'value':value,
                         'bbox':[min(w['x0'] for w in words),min(w['top'] for w in words),
                                 max(w['x1'] for w in words),max(w['bottom'] for w in words)],
                         'method':'native','unit':'TND','approved':False})
    if len({r['value'] for r in readings})!=1:
        raise ValueError('Contradictory life premium controls')
    return {'records':readings,'annex_minus_statement':0,'bridge_minus_statement':0,
            'status':'candidate_needs_review'}


def candidate(source,year):
    if type(year) is not int or year not in LAYOUTS:
        raise ValueError('Unsupported COMAR year')
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    annex,edges,unit_page,gross_band=LAYOUTS[year]
    with pdfplumber.open(source) as doc:
        front=normalize(doc.pages[0].extract_text() or '')
        if 'COMAR' not in front or str(year) not in front or 'CONSOLID' in front:
            raise ValueError('Unconfirmed individual company/year identity')
        unit_text=normalize(doc.pages[unit_page-1].extract_text() or '')
        if not re.search(r'POSITIONS COMPTABLES SONT EXPRIME[S]? EN DINAR TUNISIEN',unit_text):
            raise ValueError('Unconfirmed statement unit')
        page=doc.pages[annex-1]
        title=normalize(page.extract_text() or '')
        if not all(t in title for t in ('ANNEXE 13','NON VIE',str(year))) or abs(page.width-842)>1 or abs(page.height-595.4)>1:
            raise ValueError('Unsupported annex identity or geometry')
        row=row_at(page,'EMISES');top=min(w['top'] for w in row)
        headers=category_headers(page.extract_words(),top,edges)
        records=[]
        for code,lo,hi,header in zip(CATEGORIES,edges,edges[1:],headers):
            cell=in_band(row,lo,hi)
            raw,value,state=read_amount(cell)
            records.append({'category':code,'value':value,'raw':raw,'source_state':state,
                'header_text':header,'page':annex,
                'bbox':[min(w['x0'] for w in cell),min(w['top'] for w in cell),max(w['x1'] for w in cell),max(w['bottom'] for w in cell)] if cell else None,
                'unit':'TND','method':'native','approved':False})
        statement=doc.pages[3];statement_text=normalize(statement.extract_text() or '')
        if not all(x in statement_text for x in (str(year),str(year-1),'BRUTES')):
            raise ValueError('Missing statement period or gross heading')
        statement_row=row_at(statement,'PRNV11')
        gross_header(statement.extract_words(),year,gross_band,min(w['top'] for w in statement_row))
        statement_value=read_amount(in_band(statement_row,*gross_band))[1]
        bridge=doc.pages[annex+1]
        bridge_text=normalize(bridge.extract_text() or '')
        if not all(x in bridge_text for x in ('ANNEXE 16',str(year),'NON VIE')):
            raise ValueError('Unconfirmed reconciliation table')
        bridge_row=row_at(bridge,'EMISES')
        bridge_value=read_amount([w for w in bridge_row if re.fullmatch(r'[\d,.]+',w['text'])])[1]
        values=[r['value'] for r in records[:-1]]
        total=records[-1]['value']
        if any(v is None for v in (total,statement_value,bridge_value)):
            raise ValueError('Missing independent premium control')
        if total!=statement_value or total!=bridge_value:
            raise ValueError('Contradictory premium controls')
        checks={'annex_minus_statement':total-statement_value,
                'annex_minus_bridge':total-bridge_value,
                'known_numeric_sum_minus_total':sum(v for v in values if v is not None)-total,
                'complete_category_sum_minus_total':sum(values)-total if all(v is not None for v in values) else None,
                'missing_categories':[r['category'] for r in records[:-1] if r['value'] is None]}
        life=life_candidate(doc,year,annex)
        if hashlib.sha256(source.read_bytes()).hexdigest()!=digest:
            raise ValueError('Source changed during extraction')
        return {'company':'COMAR','year':year,'source':str(source),'source_sha256':digest,
                'status':'candidate_needs_review','production_enabled':False,'header_identities_checked':True,
                'unit_evidence_page':unit_page,'statement_page':4,'statement_gross':statement_value,
                'bridge_page':annex+2,'bridge_value':bridge_value,'records':records,'checks':checks,'life':life}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise SystemExit('Output already exists; choose a new directory')
    results=[candidate(args.sources/f'{year}.pdf',year) for year in LAYOUTS]
    args.output.mkdir(parents=True)
    (args.output/'evidence.json').write_text(json.dumps(results,indent=2,ensure_ascii=False),encoding='utf8')
    print(json.dumps({r['year']:r['checks'] for r in results},indent=2))


if __name__=='__main__':main()
