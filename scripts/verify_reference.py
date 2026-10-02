"""Run a real extraction/export and compare it with a confidential local baseline.

The reference is never modified. Existing SHA-keyed PDF/OCR caches may be reused;
the workbook is always regenerated and recalculated through LibreOffice. This is
a regression check, not independent confirmation of the baseline's accounting
accuracy. Only pass/fail summaries are printed.
"""

import argparse
import json
from pathlib import Path

import openpyxl

from ledger_orchestrator.pipeline import execute, save_json


def ordered(items):
    return sorted(json.dumps(item, sort_keys=True, ensure_ascii=False) for item in items)


def normalize_legacy_source_paths(value):
    """One documented path migration from old STAR OCR caches; no numeric changes."""
    if isinstance(value, list):
        return [normalize_legacy_source_paths(item) for item in value]
    if isinstance(value, dict):
        return {key: ('sources/STAR/2025.pdf' if key == 'source' and item == 'STAR/2025.pdf'
                      else normalize_legacy_source_paths(item)) for key, item in value.items()}
    return value


def compare_reports(reference, actual):
    # Normalize integer year keys in in-memory reports to the saved JSON form.
    actual = json.loads(json.dumps(actual))
    reference = normalize_legacy_source_paths(reference)
    return {
        'scope': all(actual.get(k) == reference.get(k) for k in ('company', 'years', 'target_unit')),
        'source_documents': actual['documents'] == reference['documents'],
        'template_fingerprint': actual['template_sha256'] == reference['template_sha256'],
        'status': actual['status'] == reference['status'],
        'financial_records_and_controls': actual['data'] == reference['data'],
        'all_anomalies': ordered(actual['issues']) == ordered(reference['issues']),
        'all_writes_and_evidence': ordered(actual['writes']) == ordered(reference['writes']),
        'coverage': actual['coverage'] == reference['coverage'],
        'review_cases': ordered(actual['review']) == ordered(reference['review']),
        'comparative_events': ordered(actual.get('source_events', [])) == ordered(reference.get('source_events', [])),
        'agents_completed': [(e['agent'], e['state']) for e in actual['agent_trace']] == [
            (agent, state) for agent in ('documents', 'extraction', 'validation', 'workbook', 'review')
            for state in ('running', 'completed')],
    }


def compare_workbooks(reference_path, actual_path):
    checks = {}
    for data_only, name in ((False, 'workbook_values_and_formulas'), (True, 'workbook_recalculated_values')):
        reference = openpyxl.load_workbook(reference_path, data_only=data_only)
        actual = openpyxl.load_workbook(actual_path, data_only=data_only)
        try:
            same = reference.sheetnames == actual.sheetnames
            styles_same = same
            for sheet in reference:
                if sheet.title not in actual:
                    continue
                target = actual[sheet.title]
                if (sheet.max_row, sheet.max_column) != (target.max_row, target.max_column):
                    same = False
                for row in sheet:
                    for cell in row:
                        other = target[cell.coordinate]
                        same = same and cell.value == other.value
                        if not data_only:
                            styles_same = styles_same and cell._style == other._style
            checks[name] = same
            if not data_only:
                checks['workbook_cell_styles'] = styles_same
        finally:
            reference.close()
            actual.close()
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--root', type=Path, default=Path('data'))
    parser.add_argument('--config', type=Path, default=Path('config/star.json'))
    parser.add_argument('--output', type=Path, default=Path('outputs'))
    args = parser.parse_args()
    reference = json.loads((args.reference / 'report.json').read_text(encoding='utf-8'))
    actual = execute(args.root, args.output, args.config, reference['years'])
    folder = args.output / actual['run_id']
    checks = compare_reports(reference, actual)
    checks.update(compare_workbooks(args.reference / reference['workbook'], folder / actual['workbook']))
    result = dict(reference_run=reference['run_id'], actual_run=actual['run_id'],
                  passed=all(checks.values()), checks=checks,
                  allowed_metadata_migrations={'STAR/2025.pdf':'sources/STAR/2025.pdf'},
                  scope='Regression against the recorded reference; not a human accuracy certification')
    save_json(folder / 'reference_verification.json', result)
    print(json.dumps(result, ensure_ascii=False))
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
