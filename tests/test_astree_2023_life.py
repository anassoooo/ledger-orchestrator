import unittest
from ledger_orchestrator.extraction.astree_2023_life import extract_2023_life


def word(t,x,y):return dict(text=t,x0=x-1,x1=x+1,top=y,bottom=y+3)


def fixture():
    pages=[dict(page=1,text='ASTREE 2023 individuel')]
    for n,code,x in ((4,'PRNV11',340),(5,'PRV11',375)):
        words=[word('Brutes',x,20),word('31/12/2023',x,30),word(code,80,60),word('100',x,60)]
        if n==5:words.extend([word('PRV1',80,45),word('100',x,45)])
        pages.append(dict(page=n,text='dinars tunisiens 31/12/2023 31/12/2022',method='native',width=595.22,height=842,words=words))
    return pages


class Life2023Tests(unittest.TestCase):
    def extract(self,p):return extract_2023_life(p,'sources/ASTREE/2023.pdf')

    def test_only_life_is_mapped(self):
        result=self.extract(fixture())
        self.assertEqual(result['mapped'],{'VIE':100})
        self.assertEqual(result['records'],[])
        self.assertIn('AUTOMOBILE',result['blocked'])
        self.assertFalse(result['production_enabled'])

    def test_rejects_ocr_units_dates_and_wrong_company(self):
        for mode in ('ocr','unit','date','identity'):
            p=fixture()
            if mode=='ocr':p[2]['method']='ocr'
            elif mode=='unit':p[2]['text']='milliers de dinars tunisiens 31/12/2023 31/12/2022'
            elif mode=='date':p[2]['words'][1]['text']='31/12/2022'
            else:p[0]['text']='OTHER 2023'
            with self.subTest(mode=mode),self.assertRaises(ValueError):self.extract(p)

    def test_rejects_total_mismatch(self):
        p=fixture();p[2]['words'][-1]['text']='101'
        with self.assertRaises(ValueError):self.extract(p)

    def test_published_life_zero_is_preserved(self):
        p=fixture()
        for w in p[2]['words']:
            if w['text']=='100':w['text']='0'
        self.assertEqual(self.extract(p)['mapped']['VIE'],0)
