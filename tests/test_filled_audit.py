import json
from pathlib import Path
import tempfile
import unittest
import openpyxl
from ledger_orchestrator.workbook.filled_audit import audit,formula_refs


class FilledAuditTests(unittest.TestCase):
    def test_guard_and_duplicates_rejected(self):
        for f in ['=SUM(A1,A2)','=IF(COUNT(A1)=2,SUM(A1),"")',
                  '=IF(COUNT(A1,A1)=2,SUM(A1,A1),"")',
                  '=IF(COUNT(A1)=1,SUM(A2),"")']:
            with self.assertRaises(ValueError):
                formula_refs(f,'Sheet')

    def test_quoted_sheet_reference(self):
        self.assertEqual(formula_refs('=IF(COUNT(\'Details\'!A1)=1,SUM(\'Details\'!A1),"")','Sheet'),[('Details','A1')])

    def test_altered_value_and_unapproved_source_are_detected(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'book.xlsx'
            wb=openpyxl.Workbook()
            wb.active['A1']=11
            wb.save(path)
            report=dict(run_id='test',issues=[],config={'rounding_tolerance_tnd':3},
                writes=[dict(sheet='Sheet',cell='A1',year=2025,code='AC1',new=10,
                    sources=[dict(value=10,approved=False,unit='TND',conversion_factor=1,source='s.pdf',page=1)])])
            result=audit(path,report)
            self.assertEqual(result['integrity_errors'],1)
            errors=result['cells'][0]['errors']
            self.assertIn('workbook_report_mismatch',errors)
            self.assertIn('source_value_mismatch',errors)
            self.assertIn('unapproved_source',errors)

    def test_missing_formula_cache_and_warning_propagation(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'book.xlsx'
            wb=openpyxl.Workbook()
            wb.active['A1']=0
            formula='=IF(COUNT(A1)=1,SUM(A1),"")'
            wb.active['A2']=formula
            wb.save(path)
            source=dict(value=0,approved=True,unit='TND',conversion_factor=1,source='s.pdf',page=1)
            report=dict(run_id='test',config={'rounding_tolerance_tnd':3},
                issues=[dict(type='comparative_difference',year=2025,code='AC1')],
                writes=[dict(sheet='Sheet',cell='A1',year=2025,code='AC1',new=0,sources=[source]),
                        dict(sheet='Sheet',cell='A2',year=2025,code='TOTAL',new=formula,sources=[])])
            result=audit(path,report)
            self.assertIn('formula_cache_mismatch',result['cells'][1]['errors'])
            self.assertIn('dependency_requires_review',result['cells'][1]['warnings'])
