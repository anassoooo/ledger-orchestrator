"""Bounded, read-only header triage; never admits a financial extraction profile.

Reuses the saved local inventory and verifies its source hashes. Only the first
four physical pages are inspected. Findings concern those pages, not the entire
document. Missing or damaged text is reported, never interpreted as zero.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import unicodedata

import pdfplumber


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text.upper())
                   if not unicodedata.combining(c))


def compact(text):
    return re.sub(r'[^A-Z0-9]', '', normalized(text))


ALIASES = {'ASTREE': 'ASTREE', 'COMAR': 'COMAR', 'STAR': 'STAR',
           'ZITOUNA TAKAFUL': 'ZITOUNATAKAFUL', 'CTAMA': 'CTAMA'}
DATE = r'31\s*(?:/\s*12\s*/|DECEMBRE\s+)\s*((?:19|20)\d{2})'


def header_years(text):
    # Older COMAR prints spaced year digits explicitly after EXERCICE.
    # Do not remove spaces from arbitrary numerical text or financial amounts.
    text = re.sub(r'(EXERCICE\s+)([12]\s+\d\s+\d\s+\d)\b(?!\s+\d)',
                  lambda m: m[1] + re.sub(r'\s', '', m[2]), normalized(text))
    return [int(y) for y in re.findall(r'\b((?:19|20)\d{2})\b', text)]


def observed_period_pair(page, year):
    years = page['header_year_occurrences']
    expected = {year, year - 1}
    paired_lines = [header_years(item['text']) for item in page.get('period_evidence', [])
                    if expected <= set(header_years(item['text']))]
    return (expected <= set(years) and set(years) <= expected
            and years.index(year) < years.index(year - 1)
            and all(line.index(year) < line.index(year - 1) for line in paired_lines))


def evidence(lines, page, predicate):
    return [{'page': page, 'text': line['text'],
             'bbox': [round(line[k], 3) for k in ('x0', 'top', 'x1', 'bottom')]}
            for line in lines if predicate(normalized(line['text']))]


def inspect_page(page, number):
    lines = page.extract_text_lines(return_chars=False)
    text = '\n'.join(line['text'] for line in lines)
    key = compact(text)
    ntext = normalized(text)
    upper = [line for line in lines if line['top'] < page.height * .45]
    header = '\n'.join(line['text'] for line in upper)
    # Stop at the first account row: numerical years below it are not headers.
    account_rows = [n for n, line in enumerate(lines)
                    if re.match(r'^\s*(?:AC\s*1\b|AC11\b|CP\s*1\b|AN\s*1\b|ACTIFS INCORPORELS)',
                                normalized(line['text']))]
    if account_rows:
        upper = lines[:account_rows[0]]
        header = '\n'.join(line['text'] for line in upper)
    hkey = compact(header)
    sides = []
    if ('AC1' in key or 'ACTIFSINCORPORELS' in key) and ('BILAN' in hkey or 'ACTIF' in hkey):
        sides.append('asset')
    if ('CP1' in key or 'CAPITALSOCIAL' in key) and 'CAPITAUXPROPRES' in key:
        sides.append('equity_liability')
    period_lines = evidence(upper, number, lambda t: bool(header_years(t))
                            and not re.search(r'\bBO\b|\bPAGE\b|ASSEMBLEE|COMMISSAIRE|ORDINAIRE', t))
    years = [y for item in period_lines for y in header_years(item['text'])]
    statement_dates = [int(y) for y in re.findall(DATE, normalized(header))]
    unit_lines = evidence(lines, number, lambda t: bool(re.search(
        r'(?:EXPRIM|CHIFFRES|MONTANTS|MILLIERS|EN DINAR|EN TND)', t)) and ('DINAR' in t or 'TND' in t))
    flags = []
    if len(text.strip()) < 80:
        flags.append('missing_or_sparse_native_text')
    elif number in (2, 3) and not sides:
        flags.append('balance_not_identified_in_native_text')
    if 'RETRAITE' in hkey and 'PUBLIE' in hkey:
        flags.append('distinct_restated_and_published_comparatives')
    if 'FONDSDES' in key and ('ADHERENT' in key or 'PARTICIPANT' in key):
        flags.append('takaful_fund_scope_requires_separate_adapter')
    if 'COMBINE' in hkey:
        flags.append('combined_balance_scope')
    if sides and re.search(r'\b\d{1,3}(?: \d{3})+,\d{3}\b', text):
        flags.append('three_decimal_amounts_observed')
    if 'PHASEDECREATION' in key:
        flags.append('creation_phase_statement')
    if re.search(r'ANNUL(?:E|ENT)ETREMPLAC(?:E|ENT)', key):
        flags.append('replacement_publication')
    # A coded vs uncoded observation is not a complete layout fingerprint.
    style = 'coded_accounts' if 'AC1' in key or 'CP1' in key else (
        'uncoded_labels' if sides else 'unidentified')
    return {'page': number, 'width': page.width, 'height': page.height,
            'native_characters': len(text), 'balance_sides_observed': sides,
            'account_label_style': style, 'header_year_occurrences': years,
            'header_date_years': statement_dates, 'period_evidence': period_lines,
            'unit_evidence': unit_lines, 'flags': flags}, lines, text


def inspect_document(source, item):
    if digest(source) != item['sha256']:
        raise ValueError(f"Source differs from inventory: {item['file']}")
    pages, first_text, first_lines = [], '', []
    with pdfplumber.open(source) as pdf:
        if len(pdf.pages) != item['page_count']:
            raise ValueError(f"Page count differs: {item['file']}")
        for index in range(min(4, len(pdf.pages))):
            result, lines, text = inspect_page(pdf.pages[index], index + 1)
            pages.append(result)
            if index == 0:
                first_text, first_lines = text, lines
    cover_key = compact(first_text)
    company = item['company']
    identity = evidence(first_lines, 1, lambda t: ALIASES[company] in compact(t))
    if company == 'CTAMA' and not identity:
        identity = evidence(first_lines, 1, lambda t: 'CAISSE' in t and 'AGRICOLES' in t)
    # Binding follows the notice's financial closing date, not publication/AGM.
    cover_normalized = normalized(first_text)
    matches = re.findall(r'ETATS\s+FINANCIERS.{0,90}?ARRETE.{0,40}?' + DATE,
                         cover_normalized, flags=re.DOTALL)
    closing_years = sorted(set(map(int, matches)))
    flags = sorted({flag for page in pages for flag in page['flags']})
    if not identity:
        flags.append('company_identity_unconfirmed')
    if closing_years != [item['filename_year']]:
        flags.append('notice_financial_year_unconfirmed_or_mismatched')
    side_results = {}
    for side in ('asset', 'equity_liability'):
        candidates = [page for page in pages if side in page['balance_sides_observed']]
        consistent = [page for page in candidates
                      if observed_period_pair(page, item['filename_year'])]
        side_results[side] = {'candidate_pages': [p['page'] for p in candidates],
                              'two_period_headers_observed_pages': [p['page'] for p in consistent]}
        if not consistent:
            flags.append(f'{side}_two_period_headers_unconfirmed')
    clear = bool(identity) and closing_years == [item['filename_year']] and all(
        value['two_period_headers_observed_pages'] for value in side_results.values())
    return {'company': company, 'file': item['file'], 'sha256': item['sha256'],
            'filename_year': item['filename_year'], 'page_count': item['page_count'],
            'identity_evidence': identity, 'notice_financial_years': closing_years,
            'notice_date_evidence': evidence(first_lines, 1, lambda t: bool(re.search(DATE, t))),
            'balance_header_observations': side_results, 'pages_inspected': pages,
            'status': 'native_identity_and_balance_periods_observed' if clear else 'needs_header_review',
            'flags': sorted(set(flags)), 'financial_values_extracted': 0,
            'approved': False, 'production_admitted': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Output must be a new directory')
    original_inventory_hash = digest(args.inventory)
    inventory = json.loads(args.inventory.read_text(encoding='utf-8'))
    source_root = (args.root / 'data/sources').resolve()
    seen = set()
    documents = []
    for item in inventory['documents']:
        source = (source_root / item['file']).resolve()
        if not source.is_relative_to(source_root) or source in seen:
            raise ValueError('Unsafe or duplicate inventory path')
        if item['company'] not in ALIASES:
            raise ValueError('Unconfigured company identity alias')
        seen.add(source)
        documents.append(inspect_document(source, item))
        print(item['file'], documents[-1]['status'], flush=True)
    # Recheck before publication; a partial/stale qualification must not be saved.
    if digest(args.inventory) != original_inventory_hash:
        raise ValueError('Inventory changed during qualification')
    for item in inventory['documents']:
        if digest(source_root / item['file']) != item['sha256']:
            raise ValueError('Source changed during qualification')
    report = {'schema_version': 1,
              'scope': 'Native header triage of first four physical pages only; not financial qualification',
              'inventory_sha256': original_inventory_hash,
              'source_hashes_verified': len(documents),
              'pages_inspected': sum(len(d['pages_inspected']) for d in documents),
              'status_counts': dict(Counter(d['status'] for d in documents)),
              'flag_counts': dict(Counter(f for d in documents for f in d['flags'])),
              'documents': documents, 'production_changes': 0, 'financial_values_extracted': 0}
    args.output.mkdir(parents=True)
    (args.output / 'qualification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'documents'}, indent=2))


if __name__ == '__main__':
    main()
