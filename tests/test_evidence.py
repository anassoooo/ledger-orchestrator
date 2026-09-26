import copy
import unittest
from ledger_orchestrator.extraction.notes import asset_notes,supplement
from ledger_orchestrator.validation.accounting import validate_balance
from ledger_orchestrator.validation.premium_evidence import corroborate_premiums,ORDER,ALIASES


def word(text,x,y):
    return dict(text=text,x0=x,x1=x+len(text)*2,top=y,bottom=y+5)


def page(rows,method='native',page_number=1):
    words=[word(text,x,y) for y,cells in rows for x,text in cells]
    return dict(page=page_number,width=1000,height=800,method=method,words=words,
                text='\n'.join(' '.join(t for x,t in cells) for y,cells in rows))


class NoteTests(unittest.TestCase):
    def test_mmb_alias_is_scoped_and_requires_net_check(self):
        p=page([(10,[(10,'NOTES SUR L’ACTIF DU BILAN Dinars Tunisiens')]),
                (20,[(10,'AC2 Actifs corporels')]),
                (30,[(600,'31/12/2025'),(800,'31/12/2024')]),
                (40,[(10,'MMB'),(400,'100'),(500,'30'),(600,'70'),(800,'60')])])
        records,_=asset_notes([p],2025,'s')
        self.assertEqual(records['AC22']['value'],70)
        self.assertIn('AC22',validate_balance(records,{},3)['eligible'])
        for w in p['words']:
            if w['text']=='70':
                w['text']='80'
        records,_=asset_notes([p],2025,'s')
        self.assertNotIn('AC22',validate_balance(records,{},3)['eligible'])
        for w in p['words']:
            if w['text']=='AC2 Actifs corporels':
                w['text']='AC1 Actifs incorporels'
        self.assertNotIn('AC22',asset_notes([p],2025,'s')[0])

    def fixture(self):
        return [page([(10,[(10,'NOTES SUR L’ACTIF DU BILAN Dinars Tunisiens')]),
                      (20,[(10,'AC 72 Charges reportées')]),
                      (30,[(400,'31/12/2025'),(700,'31/12/2024')]),
                      (40,[(10,"Frais d'acquisition reportés"),(400,'12'),(700,'10')]),
                      (50,[(10,'TOTAL'),(400,'12'),(700,'10')])])]

    def test_spaced_code_and_exact_section(self):
        records,issues=asset_notes(self.fixture(),2025,'source')
        self.assertEqual(records['AC72']['value'],12)
        self.assertEqual(records['AC721']['previous'],10)
        self.assertEqual(issues,[])

    def test_deposits_total_needs_two_distinct_disclosed_components(self):
        p=page([(10,[(10,'NOTES SUR L’ACTIF DU BILAN Dinars Tunisiens')]),
                (20,[(10,'AC34 Créances pour espèces déposées')]),
                (30,[(400,'31/12/2025'),(700,'31/12/2024')]),
                (40,[(10,'Dépôts en garantie des PPNA'),(400,'4'),(700,'3')]),
                (50,[(10,'Dépôts en garantie des PSAP'),(400,'6'),(700,'5')]),
                (60,[(10,'TOTAL'),(400,'10'),(700,'8')])])
        records,_=asset_notes([p],2025,'s')
        self.assertEqual(records['AC34']['note_checks'][0]['delta'],0)
        self.assertIn('AC34',validate_balance(records,{},3)['eligible'])
        p['words']=[w for w in p['words'] if w['top']!=50]
        records,_=asset_notes([p],2025,'s')
        self.assertNotIn('AC34',validate_balance(records,{},3)['eligible'])

    def test_wrong_year_or_unit_blocks(self):
        for old,new in [('31/12/2025','31/12/2022'),('Dinars Tunisiens','milliers de dinars')]:
            pages=self.fixture()
            pages[0]['text']=pages[0]['text'].replace(old,new)
            self.assertEqual(asset_notes(pages,2025,'s')[0],{})

    def test_conflict_preserves_and_blocks(self):
        balance={'AC12':dict(value=9,unit='TND')}
        issues=supplement(balance,{'AC12':dict(value=10,page=24)})
        self.assertEqual(balance['AC12']['value'],9)
        self.assertTrue(balance['AC12']['ambiguous'])
        self.assertEqual(issues[0]['type'],'balance_note_conflict')

    def test_failed_net_check_cannot_pass_through_parent(self):
        records={'AC12':dict(value=10,unit='TND',note_checks=[dict(status='blocked')]),
                 'AC1':dict(value=10,unit='TND')}
        result=validate_balance(records,{'AC1':['AC12']},3)
        self.assertNotIn('AC12',result['eligible'])
        self.assertNotIn('AC1',result['eligible'])

    def test_native_leaf_check_does_not_bypass_subtotal_children(self):
        records={k:dict(value=10,unit='TND',note_checks=[dict(status='passed')]) for k in ['AC1','AC331']}
        result=validate_balance(records,{'AC1':['AC12']},3)
        self.assertNotIn('AC1',result['eligible'])
        self.assertIn('AC331',result['eligible'])


class PremiumEvidenceTests(unittest.TestCase):
    def fixture(self):
        positions=[300+i*70 for i in range(9)]
        issued=[10]*8+[80]
        rows=[(10,[(10,'Non-Vie au 31/12/2025 en dinars')]),
              (30,[(x,aliases[0]) for x,aliases in zip(positions,ALIASES)]),
              (60,[(10,'PRIMES ACQUISES')]+[(x,str(v)) for x,v in zip(positions,[11]*8+[88])]),
              (100,[(10,'Primes émises')]+[(x,str(v)) for x,v in zip(positions,issued)]),
              (140,[(10,'Variation des primes non acquises')]+[(x,str(v)) for x,v in zip(positions,[1]*8+[8])])]
        ocr=page(rows,'ocr',2)
        native=page([(10,[(10,'Opérations brutes 31/12/2025 Dinars Tunisiens')]),
                     (30,[(10,'Primes émises non-vie PRNV1'),(400,'80'),(500,'5'),(600,'75'),(700,'60')])])
        records={k:dict(value=v,page=2,bbox=[x,100,x+4,105],method='ocr') for k,v,x in zip(ORDER,issued,positions)}
        return [native,ocr],records

    def test_all_independent_controls_required(self):
        pages,records=self.fixture()
        self.assertEqual(corroborate_premiums(pages,records,2025,'s',0),[])
        self.assertTrue(all(r.get('corroboration') for r in records.values()))

    def test_missing_native_proof_blocks(self):
        pages,records=self.fixture()
        self.assertTrue(corroborate_premiums(pages[1:],records,2025,'s'))
        self.assertFalse(any(r.get('corroboration') for r in records.values()))

    def test_compensating_branch_errors_block(self):
        pages,records=self.fixture()
        records['GROUPE']['value']+=100
        records['A_TRAVAIL']['value']-=100
        self.assertTrue(corroborate_premiums(pages,records,2025,'s'))
        self.assertFalse(any(r.get('corroboration') for r in records.values()))

    def test_swapped_headers_block(self):
        pages,records=self.fixture()
        headers=[w for w in pages[1]['words'] if w['top']==30]
        headers[0]['text'],headers[1]['text']=headers[1]['text'],headers[0]['text']
        self.assertTrue(corroborate_premiums(pages,records,2025,'s'))
