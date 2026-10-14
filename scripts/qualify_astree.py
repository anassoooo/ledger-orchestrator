"""Repeat the ASTREE candidate extraction locally, without enabling production."""
import argparse
import hashlib
import json
from pathlib import Path

import pdfplumber

from ledger_orchestrator.extraction.astree_candidate import extract_candidate


def read_document(path):
    with pdfplumber.open(path) as pdf:
        return [dict(page=i+1, width=p.width, height=p.height, method='native',
                     text=p.extract_text(x_tolerance=2) or '',
                     words=p.extract_words(x_tolerance=2)) for i,p in enumerate(pdf.pages)]


def compare(reference, actual):
    mismatches = []
    for year, data in actual['years'].items():
        expected = reference['years'][year]
        if reference['documents'][year] != actual['documents'][year]:
            mismatches.append(dict(year=year, section='document_fingerprint'))
        for section in ('asset', 'liability'):
            fields = ('code', 'value', 'previous', 'page', 'year', 'unit', 'bbox')
            if [{k:r[k] for k in fields} for r in data[section]] != [{k:r[k] for k in fields} for r in expected[section]]:
                mismatches.append(dict(year=year, section=section))
        fields = ('label', 'value', 'page', 'year', 'unit', 'bbox')
        if [{k:r[k] for k in fields} for r in data['premiums']['rows']] != [{k:r[k] for k in fields} for r in expected['premiums']['rows']]:
            mismatches.append(dict(year=year, section='premiums'))
        for field in ('basis', 'published_total', 'sum', 'delta'):
            if data['premiums'][field] != expected['premiums'][field]:
                mismatches.append(dict(year=year, section='premiums', field=field))
        if data['checks'] != expected['checks']:
            mismatches.append(dict(year=year, section='checks'))
    return mismatches


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True,
                        help='Previous qualification evidence.json, not an independent accounting reference')
    parser.add_argument('--output', type=Path, required=True, help='New output directory')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output already exists; use a new directory')
    result = dict(status='qualification_candidate', production_enabled=False, documents={}, years={})
    for year in (2023, 2024, 2025):
        relative = f'sources/ASTREE/{year}.pdf'
        path = args.root / relative
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        pages = read_document(path)
        result['documents'][str(year)] = dict(source=relative, sha256=digest, pages=len(pages))
        result['years'][str(year)] = extract_candidate(pages, year, relative)
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('Source changed during extraction')
    mismatches = compare(json.loads(args.reference.read_text(encoding='utf-8')), result)
    # Exercise availability does not imply layout qualification.
    old = args.root / 'sources/ASTREE/2011.pdf'
    historical = 'not_available'
    if old.exists():
        try:
            extract_candidate(read_document(old), 2011, 'sources/ASTREE/2011.pdf')
        except ValueError as exc:
            historical = 'rejected' if str(exc) == 'Unsupported ASTREE exercise' else 'unexpected_failure'
        else:
            historical = 'incorrectly_admitted'
    summary = dict(reference_kind='prior_probe_not_independent_accounting_review',
                   reference_sha256=hashlib.sha256(args.reference.read_bytes()).hexdigest(),
                   compared_balance_positions=231, compared_premium_rows=49,
                   mismatches=mismatches, historical_2011=historical,
                   production_enabled=False, checks={y:d['checks'] for y,d in result['years'].items()})
    args.output.mkdir(parents=True)
    for name, data in (('evidence.json',result), ('verification.json',summary)):
        (args.output/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary))
    return 1 if mismatches or historical in ('incorrectly_admitted','unexpected_failure') else 0


if __name__ == '__main__':
    raise SystemExit(main())
