"""A regression verifier must reject changes even when aggregate counts match."""

import copy
from pathlib import Path
import tempfile
import unittest

import openpyxl

from scripts.verify_reference import compare_reports, compare_workbooks


def reference():
    return dict(company='STAR', years=[2025], target_unit='TND', status='needs_review',
                documents={'2025': dict(sha256='a' * 64)}, template_sha256='b' * 64,
                data={'2025': {'records': {'AC11': dict(value=10, source='STAR/2025.pdf')}}},
                issues=[dict(type='difference', delta=1)],
                writes=[dict(sheet='Sheet', cell='A1', new=10)], coverage={}, review=[], source_events=[],
                agent_trace=[dict(agent=agent, state=state)
                             for agent in ('documents', 'extraction', 'validation', 'workbook', 'review')
                             for state in ('running', 'completed')])


class ReferenceVerificationTests(unittest.TestCase):
    def test_only_documented_legacy_path_migration_is_equivalent(self):
        baseline = reference()
        actual = copy.deepcopy(baseline)
        actual['data']['2025']['records']['AC11']['source'] = 'sources/STAR/2025.pdf'
        self.assertTrue(all(compare_reports(baseline, actual).values()))
        self.assertEqual(baseline['data']['2025']['records']['AC11']['source'], 'STAR/2025.pdf')
        actual['data']['2025']['records']['AC11']['source'] = 'sources/OTHER/2025.pdf'
        self.assertFalse(compare_reports(baseline, actual)['financial_records_and_controls'])

    def test_equal_counts_do_not_hide_changed_values_or_evidence(self):
        baseline = reference()
        changes = [
            ('financial_records_and_controls', lambda r: r['data']['2025']['records']['AC11'].update(value=11)),
            ('all_anomalies', lambda r: r['issues'][0].update(delta=900)),
            ('all_writes_and_evidence', lambda r: r['writes'][0].update(new=11)),
            ('source_documents', lambda r: r['documents']['2025'].update(sha256='c' * 64)),
        ]
        for check, mutate in changes:
            actual = copy.deepcopy(baseline)
            mutate(actual)
            with self.subTest(check=check):
                self.assertFalse(compare_reports(baseline, actual)[check])

    def test_workbook_formula_changes_are_detected_without_cached_values(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            book = openpyxl.Workbook()
            book.active['A1'] = '=SUM(B1,B2)'
            baseline, actual = root / 'baseline.xlsx', root / 'actual.xlsx'
            book.save(baseline)
            book.active['A1'] = '=SUM(B1,B3)'
            book.save(actual)
            self.assertFalse(compare_workbooks(baseline, actual)['workbook_values_and_formulas'])
