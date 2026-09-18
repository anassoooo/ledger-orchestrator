import copy
import unittest
from cmf.diagnostics import diagnose_candidates


class DiagnosticTests(unittest.TestCase):
    def fixture(self):
        candidates={c:dict(value=v,previous=5,unit='TND') for c,v in [('A',10),('B',20)]}
        current={'P':dict(value=29,unit='TND',method='native')}
        prior={'A':dict(value=7,unit='TND',method='native')}
        return candidates,current,prior,{'P':['A','B']}

    def test_read_only_and_compares_both_years(self):
        args=self.fixture()
        before=copy.deepcopy(args)
        findings=diagnose_candidates(*args,tolerance=0)
        self.assertEqual(args,before)
        self.assertEqual([f['delta'] for f in findings],[-2,1])
        self.assertFalse(any('approved' in f for f in findings))

    def test_partial_family_cannot_establish_mismatch(self):
        args=self.fixture()
        args[3]['P'].append('C')
        self.assertFalse(any(f['kind']=='ocr_family_check' for f in diagnose_candidates(*args)))

    def test_ambiguous_or_non_native_reference_ignored(self):
        args=self.fixture()
        args[1]['P']['ambiguous']=True
        args[2]['A']['method']='ocr'
        self.assertEqual(diagnose_candidates(*args,tolerance=0),[])

    def test_matching_sum_is_diagnostic_not_approval(self):
        args=self.fixture()
        args[1]['P']['value']=30
        finding=diagnose_candidates(*args)[0]
        self.assertEqual(finding['status'],'matched')
        self.assertNotIn('approved',finding)
