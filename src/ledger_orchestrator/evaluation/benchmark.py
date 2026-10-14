"""Measure extracted facts against independent references (constitution, metric 2).

References used:
- values already present in the template at the profile's target cells
  (for example the COMAR 2024/2025 balance sheet);
- CGA aggregates in TAF_G4, published in thousands of TND.

An absent reference is "not comparable", never agreement. Results describe only
the compared cells and are not extrapolated.
"""
from collections import Counter
from decimal import Decimal, ROUND_HALF_UP

import openpyxl

from ledger_orchestrator.profiles import CompanyProfile

# TAF_G4 company row labels when they differ from the profile company name.
CGA_NAMES = {'ZITOUNA': 'ZITOUNA TAKAFUL'}

# TAF_G4 column -> (description, fact codes summed, definition status).
# confirmed: backed by a decision (DECISIONS.md D-001/D-006);
# corroborated: matched exactly on at least one company-year, still to recheck;
# indicative: CGA definition unknown; a difference is not an accuracy finding.
CGA_METRICS = {
    'B': ('Primes nettes = non-life total incl. acceptations + life total',
          [('premiums', 'TOTAL_NONVIE'), ('premiums', 'TOTAL_VIE')], 'confirmed'),
    'I': ('Capital social = CP1', [('balance', 'CP1')], 'confirmed'),
    'H': ('Résultat comptable = CP6', [('balance', 'CP6')], 'corroborated'),
    'J': ('Fonds propres = equity before the result of the year', [('balance', 'EQUITY_BEFORE')], 'corroborated'),
    'K': ('Placements nets = AC3 investments + AC71 bank and cash', [('balance', 'AC3'), ('balance', 'AC71')], 'corroborated'),
    'E': ('Provisions techniques vs PA3 gross (CGA basis unknown)', [('balance', 'PA3')], 'indicative'),
}


def _number(value):
    return Decimal(str(value)) if type(value) in (int, float) else None


def _current_facts(facts):
    """Facts read from the year's own statement (not a later comparative)."""
    result = {}
    for fact in facts:
        if fact['year'] == fact['evidence']['document_year']:
            result[fact['year'], fact['statement'], fact['code']] = fact
    return result


def template_reference(profile: CompanyProfile, template, facts):
    current = _current_facts(facts)
    rows = []
    for year in profile.config['years']:
        for sheet, address, code in profile.targets(year):
            reference = _number(template[sheet][address].value)
            if reference is None:
                continue
            statement = 'balance' if sheet == profile.workbook['balance_sheet'] else 'premiums'
            fact = current.get((year, statement, code))
            if fact is None:
                status, value, delta = 'no_extraction', None, None
            else:
                value = Decimal(fact['source_amount'])
                delta = value - reference
                status = 'agree' if delta == 0 else 'differ'
            rows.append(dict(reference='template', year=year, sheet=sheet, cell=address, code=code,
                             reference_value=str(reference), extracted=None if value is None else str(value),
                             delta=None if delta is None else str(delta), status=status,
                             approved=None if fact is None else fact['approved']))
    return rows


def _cga_rows(sheet):
    """Map (year, company) -> row from the yearly blocks of TAF_G4."""
    rows, year = {}, None
    for r in range(1, sheet.max_row + 1):
        first = sheet.cell(r, 1).value
        if type(first) is int and sheet.cell(r, 2).value == 'PRIMES NETTES':
            year = first
        elif year is not None and isinstance(first, str):
            rows[year, first.strip().upper()] = r
    return rows


def cga_reference(profile: CompanyProfile, template, facts, tolerance_ktnd=1):
    if 'TAF_G4' not in template.sheetnames:
        return []
    sheet = template['TAF_G4']
    locations = _cga_rows(sheet)
    company = profile.config['company'].upper()
    company = CGA_NAMES.get(company, company)
    current = _current_facts(facts)
    rows = []
    for year in profile.config['years']:
        row = locations.get((year, company))
        if row is None:
            continue
        for column, (meaning, codes, definition) in CGA_METRICS.items():
            reference = _number(sheet[f'{column}{row}'].value)
            if reference is None:
                continue
            parts = [current.get((year, statement, code)) for statement, code in codes]
            if any(p is None for p in parts):
                status, value, delta = 'no_extraction', None, None
            else:
                total = sum(Decimal(p['source_amount']) for p in parts)
                value = (total / 1000).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
                delta = value - reference
                status = 'agree' if abs(delta) <= tolerance_ktnd else 'differ'
            rows.append(dict(reference='cga_taf_g4', year=year, metric=column, meaning=meaning,
                             definition=definition, reference_value_ktnd=str(reference),
                             extracted_ktnd=None if value is None else str(value),
                             delta_ktnd=None if delta is None else str(delta), status=status))
    return rows


def benchmark(report, template_path):
    profile = CompanyProfile.from_dict(report['config'])
    # Formulas are not references (their cached value may be a stale 0); only
    # constants typed into the template count.
    template = openpyxl.load_workbook(template_path)
    template_rows = template_reference(profile, template, report['facts'])
    cga_rows = cga_reference(profile, template, report['facts'])
    def summarize(rows):
        counts = Counter(r['status'] for r in rows)
        compared = counts['agree'] + counts['differ']
        return dict(counts=dict(counts), compared=compared,
                    agreement=round(counts['agree'] / compared, 4) if compared else None)
    confirmed = [r for r in cga_rows if r['definition'] in ('confirmed', 'corroborated')]
    return dict(company=profile.config['company'], run_id=report.get('run_id'),
                template=dict(summary=summarize(template_rows), rows=template_rows),
                cga=dict(summary_defined=summarize(confirmed), summary_all=summarize(cga_rows), rows=cga_rows),
                scope='Agreement on compared cells only; not a certification of untested cells.')
