"""Compare COMAR accounting premiums with FTUSA statistical branches, read-only.

No branch crosswalk or reference value is admitted to a production workbook.
All computed alternatives retain missing observations rather than substituting zero.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

import pdfplumber

from ledger_orchestrator.profiles import local_path
from qualify_comar_premiums import normalize, read_amount, in_band


SPECS = {'AUTOMOBILE': (48, 'AUTOMOBILE'), 'GROUPE': (53, 'GROUPE MALADIE'),
         'TRANSPORT': (57, 'TRANSPORT'), 'INCENDIE': (61, 'INCENDIE'),
         'DIVERS_FTUSA': (65, 'RISQUES TECHNIQUES & DIVERS'),
         'CREDIT_FTUSA': (69, 'CREDIT'), 'AGRICOLES': (72, 'RISQUES AGRICOLES'),
         'VIE': (76, 'ASSURANCE VIE')}
OTHER_DIRECT = ['TRAVAIL', 'RC', 'BIENS', 'AGRICOLES', 'CONSTRUCTION',
                'PERTE_EXPLOITATION', 'CAUTION', 'ASSISTANCE', 'ACCIDENT_CORPOREL']


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reference_row(page, report_year, category, expected_title):
    words = page.extract_words()
    headers = [w for w in words if w['text'] == 'Intitulé']
    companies = [w for w in words if w['text'] == 'COMAR']
    if len(headers) != 1 or len(companies) != 1:
        raise ValueError('Missing or ambiguous FTUSA table/company identity')
    header = sorted([w for w in words if abs(w['top'] - headers[0]['top']) < 2],
                    key=lambda w: w['x0'])
    prefix = normalize(page.crop((0, 0, page.width, headers[0]['top'])).extract_text() or '')
    if (normalize(expected_title) not in prefix or not re.search(r'\d\. LES PRIMES', prefix)
            or 'PRIMES EMISES' not in prefix or 'LES SINISTRES' in prefix
            or str(report_year) not in prefix):
        raise ValueError('Unconfirmed FTUSA premium measure or branch')
    years = [w for w in header if re.fullmatch(r'20\d\d', w['text'])]
    if [int(w['text']) for w in years] != list(range(report_year - 2, report_year + 1)):
        raise ValueError('Unconfirmed FTUSA year headers')
    row = sorted([w for w in words if abs(w['top'] - companies[0]['top']) < 2],
                 key=lambda w: w['x0'])
    if companies[0]['top'] <= headers[0]['top']:
        raise ValueError('FTUSA company row is outside the table')
    result = []
    consumed = set()
    for year_word in years:
        index = header.index(year_word)
        following = header[index + 1:index + 3]
        if not following or normalize(following[0]['text']) not in ('EN', 'EN%'):
            raise ValueError('Unconfirmed FTUSA amount/percentage columns')
        band = (year_word['x0'] - 32, following[0]['x0'] - 3)
        cell = in_band(row, *band)
        raw, value, state = read_amount(cell)
        if state != 'numeric':
            raise ValueError('Missing numeric FTUSA comparison amount')
        for word in cell:
            if id(word) in consumed:
                raise ValueError('Overlapping FTUSA amount columns')
            consumed.add(id(word))
        result.append({'year': int(year_word['text']), 'category': category,
                       'published_category': expected_title, 'raw': raw, 'value': value,
                       'bbox': [min(w['x0'] for w in cell), min(w['top'] for w in cell),
                                max(w['x1'] for w in cell), max(w['bottom'] for w in cell)],
                       'method': 'native', 'approved': False})
    return result


def ftusa_readings(source, report_year, specifications):
    digest = fingerprint(source)
    result = []
    with pdfplumber.open(source) as document:
        front = normalize('\n'.join(page.extract_text() or '' for page in document.pages[:3]))
        if str(report_year) not in re.sub(r'\s', '', front) or 'INSURANCE' not in front:
            raise ValueError('Unconfirmed FTUSA report identity')
        for category, (page_number, title) in specifications.items():
            for reading in reference_row(document.pages[page_number - 1], report_year, category, title):
                reading.update(page=page_number, source=source.as_posix(), sha256=digest,
                               report_year=report_year, measure='statistical_issued_premiums')
                result.append(reading)
    if fingerprint(source) != digest:
        raise ValueError('FTUSA source changed during comparison')
    return result


def option_for_year(premium, specialized_separate):
    source = {r['category']: r for r in premium['records']}
    children = [c for c in OTHER_DIRECT if not specialized_separate or c not in ('AGRICOLES', 'CAUTION')]
    missing = [c for c in children if source[c]['value'] is None]
    known = sum(source[c]['value'] for c in children if source[c]['value'] is not None)
    return {'year': premium['year'], 'candidate_irds_components': children,
            'known_numeric_sum': known, 'missing_components': missing,
            'candidate_irds_value': None if missing else known,
            'separate_categories': ['AGRICOLES', 'CAUTION'] if specialized_separate else [],
            'excluded_acceptations': source['ACCEPTATION']['value'],
            'status': 'proposed_policy_not_admitted', 'approved': False}


def qualify(root, review_path, ftusa_2024, ftusa_2023, output):
    if output.exists():
        raise ValueError('Use a new output directory')
    review_hash = fingerprint(review_path)
    review = json.loads(review_path.read_text(encoding='utf8'))
    if (review['company'] != 'COMAR' or review['production_enabled'] is not False
            or any(f['approved'] for f in review['facts'])):
        raise ValueError('Expected unapproved COMAR review data')
    for premium in review['premium_candidates']:
        if fingerprint(local_path(root, premium['source'])) != premium['source_sha256']:
            raise ValueError('COMAR review source changed')
    references = ftusa_readings(ftusa_2024, 2024, SPECS)
    earlier = ftusa_readings(ftusa_2023, 2023, {'GROUPE': (51, 'GROUPE MALADIE')})
    index = {(r['year'], r['category']): r for r in references}
    totals = []
    comparisons = []
    categories = [c for c in SPECS if c != 'VIE']
    for year in (2023, 2024):
        premium = next(p for p in review['premium_candidates'] if p['year'] == year)
        source = {r['category']: r for r in premium['records']}
        reference_total = sum(index[year, c]['value'] for c in categories)
        direct_from_published = source['TOTAL']['value'] - source['ACCEPTATION']['value']
        totals.append({'year': year, 'ftusa_seven_branch_sum': reference_total,
                       'comar_published_nonlife': source['TOTAL']['value'],
                       'comar_published_acceptations': source['ACCEPTATION']['value'],
                       'comar_direct_derived_from_published': direct_from_published,
                       'delta': reference_total - direct_from_published,
                       'annex_category_sum_complete': premium['checks']['complete_category_sum_minus_total'] is not None,
                       'does_not_impute_missing_categories': True, 'approved': False})
        for category in ('AUTOMOBILE', 'INCENDIE', 'TRANSPORT', 'GROUPE', 'AGRICOLES', 'VIE'):
            native = (next(r for r in premium['life']['records'] if r['meaning'] == 'annex_total')
                      if category == 'VIE' else source[category])
            reference = index[year, category]
            comparisons.append({'year': year, 'category': category, 'comar_value': native['value'],
                                'comar_evidence': {'source': premium['source'], 'sha256': premium['source_sha256'],
                                                   'page': native['page'], 'bbox': native['bbox']},
                                'ftusa_value': reference['value'], 'ftusa_evidence': reference,
                                'ftusa_minus_comar': reference['value'] - native['value'],
                                'status': 'numeric_agreement' if reference['value'] == native['value']
                                          else 'branch_comparison_unresolved', 'approved': False})
    earlier_value = next(r for r in earlier if r['year'] == 2023)['value']
    persistence = {'year': 2023, 'category': 'GROUPE', 'ftusa_2023_current': earlier_value,
                   'ftusa_2024_comparative': index[2023, 'GROUPE']['value'],
                   'difference': index[2023, 'GROUPE']['value'] - earlier_value,
                   'cause_of_comar_difference': 'unproven; not explained by a later FTUSA revision'}
    options = {name: [option_for_year(p, separate) for p in review['premium_candidates']]
               for name, separate in [('separate_specialized_categories', True), ('five_branch_residual', False)]}
    if fingerprint(review_path) != review_hash:
        raise ValueError('COMAR review changed during comparison')
    for premium in review['premium_candidates']:
        if fingerprint(local_path(root, premium['source'])) != premium['source_sha256']:
            raise ValueError('COMAR source changed before comparison output')
    for path, digest in {r['source']: r['sha256'] for r in [*references, *earlier]}.items():
        if fingerprint(Path(path)) != digest:
            raise ValueError('FTUSA source changed before comparison output')
    report = {'schema_version': 1, 'company': 'COMAR', 'production_enabled': False,
              'status': 'premium_basis_review', 'review_sha256': review_hash,
              'basis': {'project_definition': 'Issued premiums net of cancellations, before reinsurance',
                        'project_authority': 'docs/LOGIQUE_METIER.md, TAF_G3 premium definition',
                        'source_measure': 'Accounting annex Primes Emises, reconciled to PRNV11/PRV11 gross columns',
                        'source_taxonomy': 'COMAR accounting annex categories',
                        'reference_taxonomy': 'FTUSA statistical branches',
                        'unit_comparison': 'Unscaled FTUSA table amounts agree with TND source totals; graph MD labels are not applied to table cells',
                        'standard_reference': {'url': 'https://www.finances.gov.tn/sites/default/files/NC28.pdf',
                                               'pdf_pages': [6, 7], 'paragraphs': [17, 18, 19, 20, 21, 22]},
                        'wording_issue': 'resolved for candidate basis; no after-reinsurance net substitution',
                        'qualification_limit': 'Accounting basis does not establish a company-specific target crosswalk'},
              'reference_readings': references, 'earlier_groupe_readings': earlier,
              'direct_total_comparisons': totals, 'branch_comparisons': comparisons,
              'groupe_reference_persistence': persistence, 'aggregation_options': options,
              'policy': {'ftusa_branch_values_must_not_overwrite_comar': True,
                         'caution_is_not_automatically_credit': True,
                         'irds_is_not_a_subtraction_plug': True,
                         'no_missing_to_zero_conversion': True,
                         'chosen_target_crosswalk': None},
              'unresolved': ['Explicit target taxonomy and treatment of Caution/Agricoles',
                             'Branch-level COMAR/FTUSA allocation difference',
                             'Missing Travail values and per-record production admission']}
    summary = {'reference_cells_read': len(references) + len(earlier),
               'direct_total_checks': len(totals), 'direct_total_deltas': [t['delta'] for t in totals],
               'branch_comparisons': len(comparisons),
               'branch_differences': sum(c['ftusa_minus_comar'] != 0 for c in comparisons),
               'groupe_ftusa_publication_delta': persistence['difference'],
               'numeric_policies_admitted': 0, 'production_enabled': False,
               'source_and_review_hashes_unchanged': True}
    output.mkdir(parents=True)
    (output / 'qualification.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf8')
    (output / 'verification.json').write_text(json.dumps(summary, indent=2), encoding='utf8')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--review', type=Path, required=True)
    parser.add_argument('--ftusa-2024', type=Path, required=True)
    parser.add_argument('--ftusa-2023', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(qualify(args.root, args.review, args.ftusa_2024, args.ftusa_2023, args.output), indent=2))


if __name__ == '__main__':
    main()
