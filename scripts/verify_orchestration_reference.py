"""Compare the orchestrated pipeline against a local reference run.

This diagnostic reuses the reference workbook because it intentionally does not
test LibreOffice. Run the normal Docker integration test separately.
"""

import argparse
import collections
import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

from cmf import pipeline
from cmf.cell_ocr import read_scanned_asset as original_scanned_asset
from cmf.extraction import read_pages as original_read_pages


def evidence_signature(report):
    return {
        str(year): {
            'records': {
                code: (record['value'], record.get('approved'), record.get('method'))
                for code, record in data['records'].items()
            },
            'branches': {
                code: item['value'] for code, item in data['branches'].items()
            },
        }
        for year, data in report['data'].items()
    }


def issue_counts(report):
    return collections.Counter(item['type'] for item in report['issues'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--root', type=Path, default=Path('data'))
    parser.add_argument('--config', type=Path, default=Path('config/star.json'))
    parser.add_argument('--cache', type=Path, default=Path('outputs/cache'))
    args = parser.parse_args()
    reference = json.loads((args.reference / 'report.json').read_text(encoding='utf-8'))
    reference_workbook = args.reference / reference['workbook']
    if not reference_workbook.is_file() or not args.cache.is_dir():
        parser.error('Reference workbook and extraction cache are required')

    def copy_reference(_template, destination, _config, _annual):
        shutil.copyfile(reference_workbook, destination)
        return reference['writes'], []

    with tempfile.TemporaryDirectory() as temp:
        with patch.object(pipeline, 'read_pages', side_effect=lambda source, _: original_read_pages(source, args.cache)), \
             patch.object(pipeline, 'read_scanned_asset', side_effect=lambda source, _: original_scanned_asset(source, args.cache)), \
             patch.object(pipeline, 'write_workbook', side_effect=copy_reference):
            actual = pipeline.execute(args.root, Path(temp), args.config, reference['years'])

    checks = {
        'status': actual['status'] == reference['status'],
        'documents': actual['documents'] == reference['documents'],
        'evidence_and_branch_values': evidence_signature(actual) == evidence_signature(reference),
        'issue_types': issue_counts(actual) == issue_counts(reference),
        'coverage': actual['coverage']['summary'] == reference['coverage']['summary'],
        'review_count': len(actual['review']) == len(reference['review']),
        'agent_trace': [event['state'] for event in actual['agent_trace']] ==
                       ['running', 'completed'] * 5,
    }
    for name, passed in checks.items():
        print(f'{name}: {"PASS" if passed else "FAIL"}')
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
