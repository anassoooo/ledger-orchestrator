import unittest
from ledger_orchestrator.presence import native_balance_presence
from ledger_orchestrator.review import build_review
from test_evidence import page


class PresenceTests(unittest.TestCase):
    def fixture(self):
        return [page([(10,[(300,'31/12/2024'),(600,'31/12/2023')])]+
                     [(30+i*10,[(10,'AC'+str(100+i)+' Rubrique'),(300,'10'),(600,'5')]) for i in range(8)])]

    def test_only_native_verified_page_proves_scoped_absence(self):
        pages=self.fixture()
        result=native_balance_presence(pages,2024,'s',['AC100','AC11'])
        self.assertEqual(result['AC100']['status'],'present')
        self.assertEqual(result['AC11']['status'],'absent_on_native_balance_page')
        pages[0]['method']='ocr'
        self.assertEqual(native_balance_presence(pages,2024,'s',['AC11']),{})

    def test_wrong_dates_or_multiple_pages_do_not_prove_absence(self):
        pages=self.fixture()
        self.assertEqual(native_balance_presence(pages,2025,'s',['AC11']),{})
        self.assertEqual(native_balance_presence(pages+pages,2024,'s',['AC11']),{})

    def test_absence_is_explained_without_inventing_zero(self):
        c=dict(year=2024,sheet='TAF_G1',cell='D53',code='AC11',status='missing_or_blocked')
        p=native_balance_presence(self.fixture(),2024,'s',['AC11'])
        result=build_review({'cells':[c]},{2024:dict(records={},presence=p)},{'children':{}},[])
        self.assertEqual(result[0]['category'],'absent_du_bilan_natif')
        self.assertIn('Conserver la cellule vide',result[0]['action'])
