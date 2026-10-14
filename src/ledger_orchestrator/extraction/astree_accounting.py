"""ASTREE 2024-2025 accounting premiums for a partial, review-only export."""
import re
from ledger_orchestrator.extraction.core import lines, normalize
from ledger_orchestrator.extraction.astree_candidate import amount

CATEGORIES = [
    ('AUTO','Auto'), ('TRANSPORT','Transport'), ('AVIATION','Aviation'),
    ('INCENDIE','Incendie'), ('DECENNALE','Responsabilité décennale'),
    ('CIVILE','Responsabilité civile'), ('AGRICOLES','Risques agricoles'),
    ('BIENS','Autres dommages aux biens'), ('ASSISTANCE','Assistance A.E.A'),
    ('CREDIT','Assurance crédit'), ('MALADIE','Maladie'), ('INVALIDITE','Invalidité'),
    ('INDIVIDUELLE','Individuelle'), ('LOI','Loi'), ('PECUNIAIRES','Pertes pécuniaires'),
    ('TOTAL_DIRECT','Total direct publié'), ('ACCEPTATIONS','Acceptations'),
    ('TOTAL_NONVIE','Total non-vie publié')]
EDGES = {
    2024: [222,258.65,289.15,317.65,350.35,381.3,412.25,449.75,488.15,514.8,544.35,576.65,605.15,633.65,662.05,699.65,734.25,763.8,803.15],
    2025: [229,259.65,288.3,317.05,346.1,378.1,410,448.65,487.25,516,544.5,573.55,602.25,630.9,659.6,697.45,728.5,757.2,791.15]}


def bbox(words):
    return [min(w['x0'] for w in words), min(w['top'] for w in words),
            max(w['x1'] for w in words), max(w['bottom'] for w in words)]


def record(page, row, lo, hi, year, source, code, label):
    words = [w for w in row if lo <= (w['x0']+w['x1'])/2 < hi]
    value = amount(words, lo, hi)
    if value is None:
        raise ValueError('Missing accounting premium amount')
    return dict(code=code, label=label, year=year, value=value, unit='TND', source=source,
                page=page['page'], bbox=bbox(words), method='native', source_label=' '.join(w['text'] for w in row),
                source_column='current_gross', conversion_factor=1)


def unique_row(page, code, top=None):
    rows = [r for r in lines(page['words']) if any(w['text'].startswith(code) for w in r)
            and (top is None or r[0]['top'] < top)]
    if len(rows) != 1:
        raise ValueError('Missing or duplicate accounting premium row')
    return rows[0]


def extract_accounting(pages, year, source):
    if type(year) is not int or year not in EDGES:
        raise ValueError('Only native ASTREE accounting annexes 2024-2025 are supported')
    if source != f'sources/ASTREE/{year}.pdf':
        raise ValueError('Unexpected ASTREE source')
    by_page = {p['page']:p for p in pages}
    if len(by_page) != len(pages):
        raise ValueError('Duplicate page identifiers')
    annex_n, bridge_n, note_n = (39,42,29) if year==2024 else (42,45,30)
    if not {1,4,5,annex_n,bridge_n,note_n} <= by_page.keys():
        raise ValueError('Missing accounting evidence pages')
    front=normalize(by_page[1]['text'])
    if not re.search(r'\bASTREE\b',front) or str(year) not in front or 'CONSOLID' in front:
        raise ValueError('Wrong individual document identity')
    for n in (4,5,annex_n,bridge_n,note_n):
        if by_page[n]['method']!='native':raise ValueError('Native accounting evidence required')
    totals=[]
    for n,code in ((4,'PRNV11'),(5,'PRV11')):
        page=by_page[n];text=normalize(page['text'])
        if not re.search(r'DINARS? TUNISIEN',text) or 'MILLIER' in text or 'MILLION' in text:
            raise ValueError('Unconfirmed accounting units')
        if f'31/12/{year}' not in text or f'31/12/{year-1}' not in text:
            raise ValueError('Unconfirmed accounting period')
        row=unique_row(page,code)
        header=[w for w in page['words'] if w['top']<min(x['top'] for x in row) and 330<=(w['x0']+w['x1'])/2<380]
        if not any('BRUT' in normalize(w['text']) for w in header) or not any(f'31/12/{year}' in w['text'] for w in header):
            raise ValueError('Unconfirmed gross/current column')
        totals.append(record(page,row,330,380,year,source,code,code+' opérations brutes'))
    page=by_page[annex_n];text=normalize(page['text'])
    if abs(page['width']-842)>1 or abs(page['height']-595.22)>1 or f'31/12/{year}' not in text or 'NON VIE' not in text:
        raise ValueError('Unsupported accounting annex layout')
    row=unique_row(page,'PRNV11',160)
    row_top=min(w['top'] for w in row)
    source_label=normalize(' '.join(w['text'] for w in row if w['x0']<220))
    expected_label='PRIMES ACQUISES' if year==2024 else 'PRIMES EMISES'
    if expected_label not in source_label:raise ValueError('Unrecognized PRNV11 label')
    records=[]
    for i,(code,label) in enumerate(CATEGORIES):
        lo,hi=EDGES[year][i:i+2]
        header_words=[w for w in page['words'] if row_top-40<w['top']<row_top-3 and lo<=(w['x0']+w['x1'])/2<hi]
        header=''.join(normalize(w['text']) for line in lines(header_words) for w in line)
        header=re.sub(r'[^A-Z]','',header)
        token='TOTAL' if code in ('TOTAL_DIRECT','TOTAL_NONVIE') else code
        if token not in header:raise ValueError('Unconfirmed category column: '+code)
        records.append(record(page,row,lo,hi,year,source,code,label))
    bridge=by_page[bridge_n]
    bridge_rows=[r for r in lines(bridge['words']) if any(w['text']=='PRNV11' for w in r) and 'PRIMES EMISES' in normalize(' '.join(w['text'] for w in r))]
    if len(bridge_rows)!=1 or f'31/12/{year}' not in normalize(bridge['text']):
        raise ValueError('Unconfirmed PRNV11 reconciliation')
    corroboration=record(bridge,bridge_rows[0],490,565,year,source,'PRNV11_BRIDGE','Primes émises - raccordement')
    note=by_page[note_n]
    note_rows=[r for r in lines(note['words']) if 'PRIMES EMISES ET ACCEPTEES' in normalize(' '.join(w['text'] for w in r))]
    note_row=note_rows[-1] if note_rows else []
    # Independently read the note's final accounting line, not initial emissions.
    note_values=[]
    for lo,hi,code in ((340,425,'PRNV11_NOTE'),(425,530,'PRV11_NOTE')):
        note_values.append(record(note,note_row,lo,hi,year,source,code,'Note 6.1 après ajustements'))
    values={r['code']:r['value'] for r in records}
    checks=dict(branch_delta=sum(r['value'] for r in records[:15])-values['TOTAL_DIRECT'],
                total_delta=values['TOTAL_DIRECT']+values['ACCEPTATIONS']-values['TOTAL_NONVIE'],
                statement_delta=values['TOTAL_NONVIE']-totals[0]['value'],
                bridge_delta=corroboration['value']-totals[0]['value'],
                note_nonlife_delta=note_values[0]['value']-totals[0]['value'],
                note_life_delta=note_values[1]['value']-totals[1]['value'])
    if any(abs(v)>(1 if k in ('branch_delta','total_delta') else 0) for k,v in checks.items()):
        raise ValueError('Accounting premium reconciliation failed')
    mapped=dict(AUTOMOBILE=values['AUTO'],INCENDIE=values['INCENDIE'],
                TRANSPORT=values['TRANSPORT']+values['AVIATION'],VIE=totals[1]['value'])
    return dict(status='needs_review',year=year,records=records,life=totals[1],
                corroboration=[totals[0],corroboration,*note_values],checks=checks,mapped=mapped,
                blocked=['IRDS','GROUPE','TOTAL_NONVIE_TARGET','TOTAL_TARGET'],
                label_exception='PRNV11 labelled Primes acquises; corroborated as issued premiums' if year==2024 else None)
