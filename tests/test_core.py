import unittest
from ledger_orchestrator.extraction import number, normalize
from ledger_orchestrator.validation import validate_balance,validate_premiums
from ledger_orchestrator.workbook import guarded_sum


class ExtractionTests(unittest.TestCase):
    def test_numbers_and_missing_are_distinct(self):
        self.assertEqual(number('1 234 567'), 1234567)
        self.assertEqual(number('(1 234)'), -1234)
        self.assertEqual(number('0'), 0)
        for s in ['-', '', 'n.a.', '1O0']:
            with self.assertRaises(ValueError):
                number(s)

    def test_normalize(self):
        self.assertEqual(normalize('Primes émises'), 'PRIMES EMISES')

    def test_parent_disagreement_blocks_total(self):
        records={k:dict(value=v,unit='TND') for k,v in {'AC12':10,'AC13':2,'AC1':20}.items()}
        v=validate_balance(records,{'AC1':['AC12','AC13']},0)
        self.assertNotIn('AC1',v['eligible'])

    def test_reconciled_disclosed_children_do_not_invent_zero(self):
        records={k:dict(value=v,unit='TND') for k,v in {'AC12':10,'AC13':0,'AC1':10}.items()}
        v=validate_balance(records,{'AC1':['AC11','AC12','AC13']},0)
        self.assertIn('AC1',v['eligible'])
        self.assertNotIn('AC11',v['computed'])
        self.assertEqual(v['dependencies']['AC1'],['AC12','AC13'])

    def test_formula_requires_every_input(self):
        self.assertEqual(guarded_sum(['O4','O5']),'=IF(COUNT(O4,O5)=2,SUM(O4,O5),"")')

    def test_premium_policy_cannot_be_guessed(self):
        result,issues=validate_premiums({},dict(premium_basis='pending',branch_policy='pending'))
        self.assertEqual(result,{})
        self.assertEqual(issues[0]['type'],'premium_policy_unresolved')

    def test_confirmed_branch_grouping_excludes_acceptations(self):
        amounts=dict(GROUPE=10,A_TRAVAIL=20,INCENDIE=30,RISQUES_DIVERS=40,
                     TRANSPORT=50,AVIATION=60,AUTOMOBILE=70,ACCEPTATION=8,
                     TOTAL_NONVIE=288,VIE_EPARGNE=3,DECES=4,MIXTE=5,TOTAL_VIE=12)
        records={k:dict(value=v) for k,v in amounts.items()}
        config=dict(premium_basis='before_reinsurance',branch_policy='grouped',rounding_tolerance_tnd=0)
        result,issues=validate_premiums(records,config)
        self.assertEqual(result['TRANSPORT']['value'],110)
        self.assertEqual(result['IRDS']['value'],60)
        self.assertEqual(result['VIE']['value'],12)
        self.assertEqual(sum(r['value'] for k,r in result.items() if k!='VIE'),280)
        self.assertEqual(issues[0]['type'],'premium_unallocated')
        self.assertEqual(issues[0]['amount'],8)

    def test_wrong_published_premiums_total_blocks_writes(self):
        keys=['GROUPE','A_TRAVAIL','INCENDIE','RISQUES_DIVERS','TRANSPORT','AVIATION','AUTOMOBILE','ACCEPTATION']
        records={k:dict(value=10) for k in keys}
        records['TOTAL_NONVIE']=dict(value=90)
        result,issues=validate_premiums(records,dict(premium_basis='before_reinsurance',branch_policy='grouped',rounding_tolerance_tnd=3))
        self.assertEqual(result,{})
        self.assertEqual(issues[0]['type'],'premium_source_total_mismatch')
