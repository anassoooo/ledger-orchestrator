import unittest
from cmf.subtotal_evidence import corroborate_subtotals


class SubtotalTests(unittest.TestCase):
    def fixture(self):
        candidate={'AC33':dict(year=2025,unit='TND',value=30,previous=25)}
        current=dict(records={c:dict(code=c,value=v,method='native') for c,v in [('AC331',10),('AC332',20)]},validation={'eligible':['AC331','AC332']})
        prior=dict(records={'AC33':dict(value=25,method='native')},validation={'eligible':['AC33']})
        return candidate,current,prior,{'AC33':['AC331','AC332','AC335']}

    def test_requires_exact_native_children_and_prior(self):
        args=self.fixture()
        self.assertIn('AC33',corroborate_subtotals(*args))
        args[0]['AC33']['value']=31
        self.assertEqual(corroborate_subtotals(*args),{})

    def test_ocr_child_cannot_corroborate_ocr_total(self):
        args=self.fixture()
        args[1]['records']['AC331']['method']='ocr'
        self.assertEqual(corroborate_subtotals(*args),{})

    def test_wrong_prior_or_existing_total_not_overridden(self):
        args=self.fixture()
        args[0]['AC33']['previous']=24
        self.assertEqual(corroborate_subtotals(*args),{})
        args=self.fixture()
        args[1]['records']['AC33']={'value':99}
        self.assertEqual(corroborate_subtotals(*args),{})
