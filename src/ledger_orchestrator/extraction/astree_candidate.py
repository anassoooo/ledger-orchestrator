"""Bounded ASTREE qualification candidate. Never selected by the production registry.

Only the inspected native 2023-2025 layouts are accepted. Premium disclosures stay
in their source taxonomy; they are not admitted as mapped accounting facts.
"""
import re

from ledger_orchestrator.extraction.core import lines, normalize

ASSET_CODES = {
    'AC1',
    'AC11_12_13',
    'AC14',
    'AC2',
    'AC21',
    'AC22',
    'AC23',
    'AC3',
    'AC31',
    'AC311',
    'AC312',
    'AC313',
    'AC32',
    'AC33',
    'AC331',
    'AC332',
    'AC333',
    'AC334',
    'AC335',
    'AC336',
    'AC34',
    'AC5',
    'AC510',
    'AC520',
    'AC530',
    'AC531',
    'AC550',
    'AC6',
    'AC61',
    'AC611',
    'AC612',
    'AC613',
    'AC62',
    'AC63',
    'AC631',
    'AC632',
    'AC633',
    'AC7',
    'AC71',
    'AC72',
    'AC73',
    'AC731',
    'AC733',
    'TOTAL_ASSET',
}
LIABILITY_CODES = {
    'CP1',
    'CP2',
    'CP4',
    'CP5',
    'CP6',
    'EQUITY',
    'EQUITY_BEFORE',
    'PA2',
    'PA23',
    'PA3',
    'PA310',
    'PA320',
    'PA330',
    'PA331',
    'PA340',
    'PA341',
    'PA350',
    'PA360',
    'PA361',
    'PA5',
    'PA6',
    'PA61',
    'PA611',
    'PA612',
    'PA62',
    'PA63',
    'PA631',
    'PA632',
    'PA633',
    'PA634',
    'PA7',
    'PA71',
    'TOTAL_EQUITY_LIABILITY',
}
PREMIUM_LABELS = [
    'Automobile',
    'Vie',
    'Maladie',
    'Transport et aviation',
    'Multirisques',
    'Incendie',
    'Individuelle',
    'Responsabilité Civile',
    'Risques Spéciaux',
    'Risques Agricoles',
    'Invalidité',
    'Assistance',
    'Assurance‐Crédit',
    'Vol',
    'Bris de glaces et dégâts des eaux',
    'Pertes pécuniaires',
]

def center(word):
    return (word['x0'] + word['x1']) / 2


def check_page(page):
    if page['method'] != 'native' or abs(page['width'] - 595.22) > 1 or abs(page['height'] - 842) > 1:
        raise ValueError('Unsupported ASTREE page geometry or extraction method')


def check_balance_header(page, year, asset):
    check_page(page)
    title = 'ACTIF DU BILAN' if asset else 'CAPITAUX PROPRES ET PASSIF DU BILAN'
    if title not in normalize(page['text']):
        raise ValueError('Unconfirmed balance statement')
    first_row = min((w['top'] for w in page['words']
                     if re.match(r'^(AC|CP|PA)(?:\d|ACTIFS|PART)', normalize(w['text']))), default=0)
    words = [w for w in page['words'] if w['top'] < first_row]
    # Asset headings use both textual and slash dates. Check positions, not just
    # the presence of two years somewhere on the page.
    current = [w for w in words if w['text'] in (str(year), f'31/12/{year}')]
    previous = [w for w in words if w['text'] in (str(year-1), f'31/12/{year-1}')]
    if len(current) != 1 or len(previous) != 1 or not 390 <= center(current[0]) < 480 or not 480 <= center(previous[0]) < 560:
        raise ValueError('Unconfirmed current/comparative columns')
    if asset and not any(normalize(w['text']) == 'NET' and 440 <= center(w) < 500 for w in words):
        raise ValueError('Unconfirmed net asset column')


def amount(words, lo, hi):
    selected = [w for w in words if lo <= (w['x0'] + w['x1']) / 2 < hi]
    raw = ''.join(w['text'] for w in selected).replace('\u00a0', '').replace(' ', '')
    if not raw:
        return None
    if not re.fullmatch(r'\d+', raw):
        raise ValueError(f'Unclear financial column: {raw!r}')
    return int(raw)


def balance_page(page, year, asset):
    check_balance_header(page, year, asset)
    text = normalize(page['text'])
    if not re.search(r'DINARS? TUNISIEN', text) or 'MILLIER' in text or 'MILLION' in text:
        raise ValueError('Unconfirmed TND units')
    records = []
    for row in lines(page['words']):
        label = ' '.join(w['text'] for w in row if w['x0'] < (310 if asset else 345))
        norm = normalize(label)
        match = re.match(r'^(AC|CP|PA)\s*(\d+(?:,\d+)*)', norm)
        code = match.group(1) + match.group(2).replace(',', '_') if match else None
        note = ''
        if asset and norm.startswith('ACACTIFS INCORPORELS'):
            code, note = 'AC1', 'Code tronqué; correspondance du libellé issue du pilote, à revoir.'
        if asset and norm.startswith('ACPART DES REASSUREURS'):
            code, note = 'AC5', 'Code tronqué; correspondance du libellé issue du pilote, à revoir.'
        if norm.startswith("TOTAL DE L'ACTIF"):
            code = 'TOTAL_ASSET'
        elif norm.startswith('TOTAL CAPITAUX PROPRES AVANT RESULTAT'):
            code = 'EQUITY_BEFORE'
        elif norm.startswith('TOTAL CAPITAUX PROPRES AVANT AFFECTATION'):
            code = 'EQUITY'
        elif norm.startswith('TOTAL DES CAPITAUX PROPRES ET DU PASSIF'):
            code = 'TOTAL_EQUITY_LIABILITY'
        if not code:
            continue
        current = amount(row, 440, 500) if asset else amount(row, 390, 480)
        previous = amount(row, 500, 560) if asset else amount(row, 480, 560)
        records.append(dict(code=code, label=label, value=current, previous=previous,
                            page=page['page'], year=year, unit='TND', note=note,
                            bbox=[min(w['x0'] for w in row), min(w['top'] for w in row),
                                  max(w['x1'] for w in row), max(w['bottom'] for w in row)]))
    expected = ASSET_CODES if asset else LIABILITY_CODES
    if {r['code'] for r in records} != expected:
        raise ValueError('Unsupported balance row layout')
    if any(r['value'] is None and r['code'] != 'AC550' for r in records):
        raise ValueError('Missing current balance amount')
    if len({r['code'] for r in records}) != len(records):
        raise ValueError('Duplicate account labels')
    return records


def premium_page(page, year):
    check_page(page)
    text = normalize(page['text'])
    if 'SITUATION COMPARATIVE DES PRIMES EMISES' not in text or str(year) not in text or not re.search(r'\bDT\b', text) or 'MILLIER' in text or 'MILLION' in text:
        raise ValueError('Unconfirmed premium table')
    lo, hi = (255, 325) if year == 2023 else ((275, 350) if year == 2024 else (300, 370))
    rows = []
    started = False
    basis = 'y compris acceptation' if year == 2025 else 'hors acceptation'
    if basis.upper() not in text:
        raise ValueError('Unconfirmed acceptance basis')
    header = next((r for r in lines(page['words']) if any(w['text'] == 'Branche' for w in r)), [])
    dates = [w for w in header if re.fullmatch(r'31/12/20[0-9]{2}', w['text'])]
    if [w['text'] for w in dates] != [f'31/12/{year}', f'31/12/{year-1}'] or not lo <= center(dates[0]) < hi:
        raise ValueError('Unconfirmed premium columns')
    for row in lines(page['words']):
        label = ' '.join(w['text'] for w in row if (w['x0'] + w['x1']) / 2 < lo)
        if label == 'Automobile':
            started = True
        if not started:
            continue
        value = amount(row, lo, hi)
        if value is None:
            continue
        if not label:
            total = value
            break
        rows.append(dict(label=label, value=value, page=page['page'], year=year, unit='TND',
                         bbox=[min(w['x0'] for w in row), min(w['top'] for w in row),
                               max(w['x1'] for w in row), max(w['bottom'] for w in row)]))
    else:
        raise ValueError('Published premium total not found')
    expected = PREMIUM_LABELS + (['Primes acceptées'] if year == 2025 else [])
    if [r['label'] for r in rows] != expected:
        raise ValueError('Unsupported premium branch layout')
    if sum(r['value'] for r in rows) != total:
        raise ValueError('Premium source total mismatch')
    return dict(rows=rows, published_total=total, sum=sum(r['value'] for r in rows),
                delta=sum(r['value'] for r in rows)-total,
                basis=basis)


def extract_candidate(pages, year, source):
    """Return review evidence only; blanks and published zeros remain distinct."""
    if type(year) is not int or year not in (2023, 2024, 2025):
        raise ValueError('Unsupported ASTREE exercise')
    if source != f'sources/ASTREE/{year}.pdf':
        raise ValueError('Unexpected ASTREE source path')
    by_page = {p['page']: p for p in pages}
    if len(by_page) != len(pages):
        raise ValueError('Duplicate page identifiers')
    premium_number = 13 if year == 2025 else 12
    if not {1, 2, 3, premium_number} <= by_page.keys():
        raise ValueError('Missing ASTREE evidence pages')
    front = normalize(by_page[1]['text'])
    if not re.search(r'\bASTREE\b', front) or not re.search(rf'\b{year}\b', front) or 'CONSOLID' in front:
        raise ValueError('Unconfirmed ASTREE individual document identity')
    assets = balance_page(by_page[2], year, True)
    liabilities = balance_page(by_page[3], year, False)
    premiums = premium_page(by_page[premium_number], year)
    for row in assets + liabilities + premiums['rows']:
        row.update(source=source, method='native', source_column='current', approved=False)
    a = {r['code']: r['value'] for r in assets}
    b = {r['code']: r['value'] for r in liabilities}
    checks = dict(
        balance_delta=a['TOTAL_ASSET']-b['TOTAL_EQUITY_LIABILITY'],
        asset_components_delta=sum(a[k] for k in ('AC1','AC2','AC3','AC5','AC6','AC7'))-a['TOTAL_ASSET'],
        liability_components_delta=sum(b[k] for k in ('EQUITY','PA2','PA3','PA5','PA6','PA7'))-b['TOTAL_EQUITY_LIABILITY'],
        premium_delta=premiums['delta'])
    return dict(asset=assets, liability=liabilities, premiums=premiums, checks=checks,
                status='qualification_candidate', production_enabled=False,
                unresolved=['premium_definition', 'branch_mapping', 'acceptance_scope', 'independent_review'])
