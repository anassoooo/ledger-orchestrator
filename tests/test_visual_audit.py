import copy
import unittest
from cmf.reconcile_visual_audit import reconcile


class VisualAuditTests(unittest.TestCase):
    def fixture(self):
        source=dict(source_run='r',pdf_sha256={},sources=[dict(sheet='S',cell='A1',source_index=0,
            year=2025,page=2,source='sources/STAR/2025.pdf',expected=12,status='visual_review_required')])
        visual=dict(source_run='r',findings=[],confirmed_references=[dict(sheet='S',cell='A1',source_index=0,
            year=2025,page=2,pdf_year=2025,printed_value=12)])
        return source,visual

    def test_reconcile_without_mutation(self):
        args=self.fixture()
        original=copy.deepcopy(args)
        self.assertEqual(reconcile(*args)['outstanding_references'],[])
        self.assertEqual(args,original)

    def test_wrong_value_year_page_and_document_rejected(self):
        for field,value in [('printed_value',13),('year',2024),('page',3),('pdf_year',2024)]:
            args=self.fixture()
            args[1]['confirmed_references'][0][field]=value
            with self.assertRaises(ValueError):
                reconcile(*args)

    def test_duplicate_observation_rejected(self):
        args=self.fixture()
        args[1]['confirmed_references']*=2
        with self.assertRaises(ValueError):
            reconcile(*args)

    def test_unreviewed_source_stays_pending(self):
        args=self.fixture()
        args[1]['confirmed_references']=[]
        self.assertEqual(len(reconcile(*args)['outstanding_references']),1)
