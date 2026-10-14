"""Measure historical ASTREE compatibility with unchanged recent balance guards.

This deliberately does not call/relax the outer candidate admission gate, which
continues to reject historical years. Any extracted rows are unapproved probes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import pdfplumber


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--headers', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise ValueError('New output required')
    sys.path.insert(0, str(a.root / 'src'))
    from ledger_orchestrator.extraction.astree_candidate import balance_page
    header_hash = digest(a.headers)
    headers = json.loads(a.headers.read_text(encoding='utf-8'))
    results = []
    for item in headers['documents']:
        if item['company'] != 'ASTREE' or item['filename_year'] >= 2023:
            continue
        if item['status'] != 'native_identity_and_balance_periods_observed':
            raise ValueError('Unconfirmed historical ASTREE identity/periods')
        path = a.root / 'data/sources' / item['file']
        if digest(path) != item['sha256']:
            raise ValueError('Source differs from header evidence')
        result = {'file': item['file'], 'source_sha256': item['sha256'],
                  'year': item['filename_year'], 'approved': False,
                  'production_admitted': False, 'sections': {}}
        with pdfplumber.open(path) as pdf:
            for side, asset in [('asset', True), ('equity_liability', False)]:
                candidates = item['balance_header_observations'][side]['two_period_headers_observed_pages']
                if len(candidates) != 1:
                    result['sections'][side] = {'status': 'ambiguous_header_candidates'}
                    continue
                number = candidates[0]
                page = pdf.pages[number-1]
                data = {'page': number, 'width': page.width, 'height': page.height,
                        'method': 'native', 'text': page.extract_text(x_tolerance=2) or '',
                        'words': page.extract_words(x_tolerance=2)}
                try:
                    rows = balance_page(data, item['filename_year'], asset)
                except ValueError as exc:
                    result['sections'][side] = {'status': 'unchanged_guard_rejected',
                                                'reason': str(exc), 'page': number}
                else:
                    for row in rows:
                        row.update(approved=False, source=item['file'], source_sha256=item['sha256'],
                                   method='native', production_admitted=False)
                    result['sections'][side] = {'status': 'unchanged_guard_compatible_candidate',
                                                'page': number, 'rows': rows}
        if digest(path) != item['sha256']:
            raise ValueError('Source changed during compatibility probe')
        sections = result['sections']
        if all(s['status'] == 'unchanged_guard_compatible_candidate' for s in sections.values()):
            asset = {r['code']: r['value'] for r in sections['asset']['rows']}
            liability = {r['code']: r['value'] for r in sections['equity_liability']['rows']}
            result['current_controls'] = {
                'balance_delta': asset['TOTAL_ASSET']-liability['TOTAL_EQUITY_LIABILITY'],
                'asset_components_delta': sum(asset[k] for k in ('AC1','AC2','AC3','AC5','AC6','AC7'))-asset['TOTAL_ASSET'],
                'liability_components_delta': sum(liability[k] for k in ('EQUITY','PA2','PA3','PA5','PA6','PA7'))-liability['TOTAL_EQUITY_LIABILITY']}
        results.append(result)
        print(item['file'], {s: v['status'] for s, v in sections.items()}, flush=True)
    if digest(a.headers) != header_hash:
        raise ValueError('Header qualification changed during probe')
    report = {'scope': 'Historical compatibility probe of unchanged recent ASTREE balance guards; not production qualification',
              'header_evidence_sha256': header_hash,
              'extractor_sha256': digest(a.root/'src/ledger_orchestrator/extraction/astree_candidate.py'),
              'historical_documents': len(results), 'documents': results,
              'outer_year_admission_gate_unchanged': True, 'production_changes': 0}
    a.output.mkdir(parents=True)
    (a.output/'compatibility.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__ == '__main__':
    main()
