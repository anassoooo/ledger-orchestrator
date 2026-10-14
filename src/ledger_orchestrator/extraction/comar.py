"""COMAR individual statements, 2023-2025: guarded native readers.

Moved unchanged from the qualification scripts (scripts/qualify_comar_*.py,
scripts/comar_review_guards.py), which now import from here. Each reader checks
company, period, unit, column headings and the frozen row manifest, and raises
on any deviation instead of guessing. Admission is decided downstream by the
accounting identities and the profile registry (constitution, articles III, XII).
"""
import hashlib
import json
import re
import unicodedata
from decimal import Decimal
from pathlib import Path

import pdfplumber

QUALIFICATION = Path(__file__).resolve().parents[3] / 'config' / 'qualification'


# --- Premium annexes and life statement -------------------------------------

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


# --- Balance sheet -----------------------------------------------------------

ASSET_BANDS={2023:[(325,370),(370,415),(415,460),(460,505)],2024:[(320,370),(370,420),(420,475),(475,540)],2025:[(345,395),(395,445),(445,495),(495,550)]}
MANIFEST_PATH=QUALIFICATION/'comar_balance_v1.json'
CHILDREN={'AC1':['AC11','AC12','AC13'],'AC2':['AC21','AC22'],
 'AC31':['AC311','AC312'],'AC32':['AC321','AC322','AC323','AC324'],
 'AC33':['AC331','AC332','AC334','AC335','AC336'],'AC3':['AC31','AC32','AC33','AC34'],
 'AC5':['AC510','AC520','AC530','AC531'],'AC61':['AC611','AC612','AC613'],
 'AC63':['AC631','AC632','AC633'],'AC6':['AC61','AC62','AC63'],
 'AC73':['AC731','AC733'],'AC7':['AC71','AC72','AC73','AC75'],
 'TOTAL_ASSET':['AC1','AC2','AC3','AC5','AC6','AC7'],
 'EQUITY_BEFORE':['CP1','CP2','CP4'],'EQUITY':['EQUITY_BEFORE','CP6'],
 'PA3':['PA310','PA320','PA330','PA331','PA340','PA341','PA350','PA360','PA361'],
 'PA63':['PA631','PA632','PA633','PA634'],'PA6':['PA61','PA62','PA63'],
 'PA71':['PA710','PA712'],'PA7':['PA71','PA73'],
 'TOTAL_LIABILITY':['PA23','PA3','PA5','PA6','PA7'],
 'TOTAL_EQUITY_LIABILITY':['EQUITY','TOTAL_LIABILITY']}

def rows(words):
    result=[]
    for w in sorted(words,key=lambda x:(x['top'],x['x0'])):
        if not result or abs(w['top']-result[-1][0]['top'])>2:result.append([])
        result[-1].append(w)
    return [sorted(row,key=lambda x:x['x0']) for row in result]

def headers(words,year,side,bands):
    cutoff=min(w['top'] for w in words if w['text']==('AC1' if side=='asset' else 'CP1'))
    head=[w for w in words if w['top']<cutoff]
    expected=['BRUT','PROV','NET','NET'] if side=='asset' else ['NET','NET']
    for band,token in zip(bands,expected):
        if [normalize(w['text']) for w in in_band(head,*band)].count(token)!=1:
            raise ValueError('Unconfirmed balance column heading')
    lo,hi=({2023:(90,102),2024:(77,87),2025:(73,83)} if side=='asset' else {2023:(92,101),2024:(81,90),2025:(77,86)})[year]
    dates=[w for w in head if lo<w['top']<hi]
    date_bands=[(370,445),bands[-1]] if side=='asset' else bands
    for value,band in zip((year,year-1),date_bands):
        found=[w['text'] for w in in_band(dates,*band)]
        if found!=[str(value) if year<2025 else f'31/12/{value}']:
            raise ValueError('Unconfirmed balance period positions')

def identify(row):
    text=normalize(' '.join(w['text'] for w in row))
    if text.startswith("TOTAL DE L'ACTIF"):return 'TOTAL_ASSET'
    if text.startswith('TOTAL DES CAPITAUX PROPRES ET DU PASSIF'):return 'TOTAL_EQUITY_LIABILITY'
    if text.startswith('TOTAL DU PASSIF'):return 'TOTAL_LIABILITY'
    if text.startswith('TOTAL CAPITAUX PROPRES AVANT RESULTAT'):return 'EQUITY_BEFORE'
    if text.startswith('TOTAL CAPITAUX PROPRES AVANT AFFECTATION'):return 'EQUITY'
    return row[0]['text'] if re.fullmatch(r'(AC|CP|PA)\d+',row[0]['text']) else None

def label_key(text):
    return re.sub('[^A-Z0-9]','',normalize(text))

def covered_rows(words,year,side,bands,manifest):
    """Match all financial rows and section labels, including unlabeled subtotals.

    No numerical values live in the manifest. It freezes the inspected semantic
    row sequence and heading/reading distinction, not an accounting reference.
    """
    all_rows=rows(words)
    first='AC1' if side=='asset' else 'CP1'
    start=next((i for i,row in enumerate(all_rows) if row[0]['text']==first),None)
    total='TOTAL_ASSET' if side=='asset' else 'TOTAL_EQUITY_LIABILITY'
    ends=[i for i,row in enumerate(all_rows) if identify(row)==total]
    if start is None or len(ends)!=1 or ends[0]<start:
        raise ValueError('Unconfirmed balance body bounds')
    observed=[]
    for row in all_rows[start:ends[0]+1]:
        code=identify(row)
        financial=any(in_band(row,*band) for band in bands)
        if code is None and not financial:
            continue
        label=' '.join(w['text'] for w in row if (w['x0']+w['x1'])/2<bands[0][0])
        observed.append((row,code,financial,label))
    expected=manifest['layouts'][str(year)][side]
    if len(observed)!=len(expected):
        raise ValueError('Balance row coverage changed')
    result=[]
    for (row,code,financial,label),spec in zip(observed,expected):
        expected_code=None if spec['role']=='corroboration' else spec['code']
        if (code!=expected_code or financial!=(spec['role']!='heading')
                or label_key(label)!=spec['label_key']):
            raise ValueError('Unconfirmed balance row identity: '+spec['code'])
        result.append((row,spec,label))
    return result

def extract(source,year,manifest_path=MANIFEST_PATH):
    if year not in ASSET_BANDS:raise ValueError('Unsupported COMAR balance year')
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    # Reuse company/period/unit checks and independent premium controls.
    premium=candidate(source,year)
    manifest_bytes=manifest_path.read_bytes()
    manifest=json.loads(manifest_bytes)
    if (manifest.get('schema_version')!=1 or manifest.get('company')!='COMAR'
            or type(manifest.get('production_enabled')) is not bool):
        raise ValueError('Unsupported COMAR coverage manifest')
    records={};corroborations={};coverage={}
    with pdfplumber.open(source) as doc:
        for side,pn in [('asset',2),('liability',3)]:
            page=doc.pages[pn-1];words=page.extract_words()
            bands=ASSET_BANDS[year] if side=='asset' else ([(410,460),(460,505)] if year==2023 else [(420,485),(485,550)])
            headers(words,year,side,bands)
            names=['gross','provisions','current','comparative'] if side=='asset' else ['current','comparative']
            admitted_rows=covered_rows(words,year,side,bands,manifest)
            coverage[side]={'expected_rows':len(admitted_rows),'matched_rows':len(admitted_rows),
                            'headings':sum(s['role']=='heading' for _,s,_ in admitted_rows),
                            'corroborations':sum(s['role']=='corroboration' for _,s,_ in admitted_rows)}
            section_labels={}
            for row,spec,label in admitted_rows:
                code=spec['code']
                if spec['role']=='heading':
                    section_labels[code]=label
                    continue
                cells={}
                for name,band in zip(names,bands):
                    w=in_band(row,*band);raw,val,state=read_amount(w)
                    cells[name]={'value':val,'raw':raw,'state':state,'bbox':[min(x['x0'] for x in w),min(x['top'] for x in w),max(x['x1'] for x in w),max(x['bottom'] for x in w)] if w else None}
                destination=corroborations if spec['role']=='corroboration' else records
                if code in destination:raise ValueError('Duplicate balance code')
                destination[code]={'page':pn,'side':side,'cells':cells,'approved':False,
                                   'method':'native','unit':'TND','row_label':label,
                                   'section_label':section_labels.get(code),
                                   'row_bbox':[min(w['x0'] for w in row),min(w['top'] for w in row),
                                               max(w['x1'] for w in row),max(w['bottom'] for w in row)]}
    if not {'TOTAL_ASSET','TOTAL_EQUITY_LIABILITY','TOTAL_LIABILITY','EQUITY'}<=records.keys():raise ValueError('Missing balance controls')
    for code in ['TOTAL_ASSET','TOTAL_EQUITY_LIABILITY','TOTAL_LIABILITY','EQUITY']:
        if any(records[code]['cells'][column]['value'] is None for column in ['current','comparative']):
            raise ValueError('Missing numeric balance control: '+code)
    checks=[]
    for parent,children in CHILDREN.items():
        # 2024 publishes PA2 directly; 2023/2025 publish its only detail PA23.
        if parent=='TOTAL_LIABILITY' and year==2024:
            children=['PA2',*children[1:]]
        missing=[c for c in [parent,*children] if c not in records or records[c]['cells']['current']['value'] is None]
        checks.append({'parent':parent,'children':children,'missing':missing,'delta':None if missing else sum(records[c]['cells']['current']['value'] for c in children)-records[parent]['cells']['current']['value']})
    gross_checks=[]
    for code,r in records.items():
        if r['side']!='asset':continue
        v={k:r['cells'][k]['value'] for k in ['gross','provisions','current']}
        gross_checks.append({'code':code,'delta':None if any(x is None for x in v.values()) else v['gross']-v['provisions']-v['current'],'missing':[k for k,x in v.items() if x is None]})
    equality={col:records['TOTAL_ASSET']['cells'][col]['value']-records['TOTAL_EQUITY_LIABILITY']['cells'][col]['value'] for col in ['current','comparative']}
    subtotal_checks=[]
    for code,r in corroborations.items():
        detail='PA23' if code=='PA2_PUBLISHED_SUBTOTAL' else 'PA5'
        for column in ['current','comparative']:
            a=r['cells'][column]['value'];b=records[detail]['cells'][column]['value']
            if a is None or b is None or a!=b:
                raise ValueError('Contradictory published liability subtotal')
            subtotal_checks.append({'subtotal':code,'detail':detail,'column':column,'delta':a-b})
    if hashlib.sha256(source.read_bytes()).hexdigest()!=digest:raise ValueError('Source changed')
    return {'company':'COMAR','year':year,'source':str(source),'sha256':digest,'status':'candidate_needs_review','production_enabled':False,'records':records,'corroborations':corroborations,'coverage':coverage,'coverage_manifest':manifest['layout_id'],'coverage_manifest_sha256':hashlib.sha256(manifest_bytes).hexdigest(),'subtotal_checks':subtotal_checks,'hierarchy_checks':checks,'gross_checks':gross_checks,'balance_equality':equality,'unit_evidence_page':premium['unit_evidence_page']}


# --- Notes ---------------------------------------------------------------------

def note_reading(page, year):
    if year != 2024 or abs(page.width - 595.22) > 1 or abs(page.height - 842) > 1:
        raise ValueError('Unsupported COMAR note layout')
    words = page.extract_words()
    section = [w for w in words if 190 < w['top'] < 210 and w['x0'] >= 95]
    if label_key(' '.join(w['text'] for w in section)) != 'AC7AUTRESELEMENTSDACTIF':
        raise ValueError('Unconfirmed COMAR AC7 note identity')
    bands = [(60, 220), (220, 305), (305, 385)]
    heading = [w for w in words if 260 < w['top'] < 278]
    for expected, band in zip(('LIBELLE', '2024', '2023'), bands):
        if label_key(' '.join(w['text'] for w in in_band(heading, *band))) != expected:
            raise ValueError('Unconfirmed COMAR note period columns')
    matches = []
    for row in rows([w for w in words if 278 < w['top'] < 450]):
        label = ' '.join(w['text'] for w in in_band(row, *bands[0]))
        if label_key(label) == 'FRAISDACQUISITIONREPORTES':
            matches.append((row, label))
    if len(matches) != 1:
        raise ValueError('Missing or ambiguous COMAR acquisition-cost note')
    row, label = matches[0]
    if any((w['x0'] + w['x1']) / 2 >= bands[-1][1] for w in row):
        raise ValueError('Unexpected COMAR note value column')
    cells = {}
    for column, band in zip(('current', 'comparative'), bands[1:]):
        cell = in_band(row, *band)
        raw, value, state = read_amount(cell)
        if value is None:
            raise ValueError('Missing numeric COMAR acquisition-cost note')
        cells[column] = {'value': value, 'raw': raw, 'state': state,
                         'bbox': [min(w['x0'] for w in cell), min(w['top'] for w in cell),
                                  max(w['x1'] for w in cell), max(w['bottom'] for w in cell)]}
    return {'code': 'AC721', 'page': 21, 'side': 'asset', 'cells': cells,
            'row_label': label, 'method': 'native', 'unit': 'TND', 'approved': False,
            'source_kind': 'note', 'mapping_basis': 'Explicit deferred acquisition costs in AC7 note',
            'period_headers': [2024, 2023]}


def extract_notes(source, year, balance):
    if year != 2024:
        return {}
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if balance['year'] != year or digest != balance['sha256']:
        raise ValueError('COMAR note and balance document differ')
    with pdfplumber.open(source) as document:
        reading = note_reading(document.pages[20], year)
    # Compare directly printed amounts, without deriving the child from its parent.
    controls = []
    for column in ('current', 'comparative'):
        value = reading['cells'][column]['value']
        parent = balance['records']['AC72']['cells'][column]['value']
        if parent is None or parent != value:
            raise ValueError('COMAR note differs from printed charges reportées')
        controls.append({'code': 'AC72', 'column': column, 'delta': value - parent})
    if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
        raise ValueError('COMAR source changed during note extraction')
    reading['printed_parent_checks'] = controls
    return {'AC721': reading}


# --- Template destination contract ---------------------------------------------

CONTRACT_PATH = QUALIFICATION / 'comar_template_v1.json'


def validate_template(profile, workbook, contract_path=CONTRACT_PATH):
    payload = contract_path.read_bytes()
    contract = json.loads(payload)
    if (contract.get('schema_version') != 1 or contract.get('company') != 'COMAR'
            or type(contract.get('production_enabled')) is not bool):
        raise ValueError('Unsupported COMAR template contract')
    targets = [{'year': year, 'sheet': sheet, 'cell': cell, 'code': code}
               for year in profile.config['years'] for sheet, cell, code in profile.targets(year)]
    addresses = [(t['sheet'], t['cell']) for t in targets]
    if len(addresses) != len(set(addresses)):
        raise ValueError('Duplicate COMAR destination')
    key = lambda t: (t['year'], t['sheet'], t['cell'], t['code'])
    if sorted(targets, key=key) != sorted(contract['targets'], key=key):
        raise ValueError('COMAR target layout differs from the inspected contract')
    for spec in contract['cells']:
        if spec['sheet'] not in workbook.sheetnames:
            raise ValueError('Missing COMAR target sheet: ' + spec['sheet'])
        actual = workbook[spec['sheet']][spec['cell']].value
        if actual not in spec['allowed_values']:
            raise ValueError('Unconfirmed COMAR destination identity: '
                             + spec['sheet'] + '!' + spec['cell'])
    return {'contract': contract['contract_id'],
            'sha256': hashlib.sha256(payload).hexdigest(),
            'destinations_checked': len(targets), 'identity_cells_checked': len(contract['cells']),
            'status': 'passed'}


# --- Pipeline records ------------------------------------------------------------

def _bbox_or_none(cell):
    return [float(v) for v in cell['bbox']] if cell.get('bbox') else None


DASHES = {'-', '‐', '‑', '‒', '–', '—'}


def _printed_dash(cell):
    return cell['value'] is None and (cell.get('raw') or '').strip() in DASHES


def balance_records(balance, notes, year, source, tolerance):
    """Convert guarded readings into pipeline records.

    A printed dash becomes a nil *candidate* (D-002): it is written only if its
    parent total reconciles with it, which validate_balance enforces because a
    detail is eligible only under a reconciled parent. A blank stays absent.
    Asset rows also carry gross - provisions = net; a failed identity marks the
    row ambiguous, which blocks it and its totals (constitution, articles II-III).
    """
    readings = dict(balance['records'])
    # A directly printed, unlabeled subtotal, checked against its only detail.
    if 'PA2_PUBLISHED_SUBTOTAL' in balance['corroborations']:
        readings['PA2'] = dict(balance['corroborations']['PA2_PUBLISHED_SUBTOTAL'],
                               row_label='Sous-total imprimé PA2 (non libellé)')
    for code, reading in notes.items():
        if code in readings:
            raise ValueError('A note would overwrite a balance-page reading')
        readings[code] = reading
    records, issues = {}, []
    for code, reading in readings.items():
        cells = reading['cells']
        current, comparative = cells['current'], cells['comparative']
        if current['value'] is None and not _printed_dash(current):
            issues.append(dict(type='source_blank_not_admitted', code=code, page=reading['page'],
                               raw=current.get('raw')))
            continue
        value = 0 if _printed_dash(current) else current['value']
        previous = 0 if _printed_dash(comparative) else comparative['value']
        record = dict(code=code, year=year, value=value, previous=previous, unit=reading['unit'],
                      source=source, page=reading['page'], method=reading['method'],
                      source_label=f"{code} {reading.get('row_label') or ''}".strip(),
                      bbox=_bbox_or_none(current), source_kind=reading.get('source_kind', 'balance'))
        if _printed_dash(current) or _printed_dash(comparative):
            record['nil_proof'] = dict(rule='D-002', proof='parent total reconciliation',
                                       dash_columns=[c for c, cell in (('current', current), ('comparative', comparative))
                                                     if _printed_dash(cell)])
            issues.append(dict(type='balance_dash_nil_candidate', code=code, page=reading['page'],
                               columns=record['nil_proof']['dash_columns']))
        if 'gross' in cells:
            gross, provisions = cells['gross']['value'], cells['provisions']['value']
            record.update(gross=gross, provisions=provisions)
            if gross is not None:
                delta = gross - (provisions or 0) - value
                passed = abs(delta) <= tolerance
                record['row_checks'] = [dict(kind='gross_minus_provisions_equals_net', delta=delta,
                                             provisions_blank=provisions is None,
                                             status='passed' if passed else 'blocked')]
                if not passed:
                    record['ambiguous'] = True
                    issues.append(dict(type='gross_net_mismatch', code=code, page=reading['page'], delta=delta))
        if reading.get('printed_parent_checks'):
            record['printed_parent_checks'] = reading['printed_parent_checks']
        records[code] = record
    return records, issues


def premium_records(premium, year, source, tolerance):
    """Issued-premium categories, the published non-life total and the life total.

    The reader already enforces annex total = statement gross = reconciliation
    table. A dash is admitted as nil only when the published total proves it
    (D-002); otherwise the category stays missing and blocks the partition.
    """
    rows = premium['records']
    *categories, total = rows
    if total['category'] != 'TOTAL':
        raise ValueError('Unexpected premium annex layout')
    known = sum(r['value'] for r in categories if r['value'] is not None)
    dashes = [r for r in categories if r['value'] is None]
    delta = known - total['value']
    proven_nil = bool(dashes) and abs(delta) <= tolerance
    raw, issues = {}, []
    for row in rows:
        code = 'TOTAL_NONVIE' if row['category'] == 'TOTAL' else row['category']
        value = row['value']
        record = dict(code=code, year=year, value=value, unit=row['unit'], source=source,
                      page=row['page'], method=row['method'], bbox=_bbox_or_none(row),
                      source_label=f"Primes émises — {row['header_text']}", source_state=row['source_state'])
        if value is None:
            if not proven_nil:
                issues.append(dict(type='premium_dash_unproven', code=code, page=row['page'], delta=delta))
                continue
            record.update(value=0, nil_proof=dict(rule='D-002', published_total=total['value'],
                                                  other_categories_sum=known, delta=delta,
                                                  dashes=[r['category'] for r in dashes]))
            issues.append(dict(type='premium_dash_admitted_as_nil', code=code, page=row['page'], delta=delta))
        record['controls'] = dict(statement_gross=premium['statement_gross'], bridge=premium['bridge_value']) \
            if code == 'TOTAL_NONVIE' else None
        raw[code] = record
    life = next(r for r in premium['life']['records'] if r['meaning'] == 'annex_total')
    raw['TOTAL_VIE'] = dict(code='TOTAL_VIE', year=year, value=life['value'], unit=life['unit'],
                            source=source, page=life['page'], method=life['method'], bbox=_bbox_or_none(life),
                            source_label='Primes émises vie — total annexe',
                            controls={r['meaning']: r['value'] for r in premium['life']['records']})
    return raw, issues
