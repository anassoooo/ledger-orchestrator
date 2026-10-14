import unittest
from ledger_orchestrator.extraction.astree_accounting import CATEGORIES, EDGES, extract_accounting


def word(text,x,y):return dict(text=text,x0=x-1,x1=x+1,top=y,bottom=y+3)


def page(n,text,words,landscape=False):
    return dict(page=n,text=text,words=words,method='native',width=842 if landscape else 595.22,height=595.22 if landscape else 842)


def fixture(year):
    annex,bridge,note=(39,42,29) if year==2024 else (42,45,30)
    pages=[page(1,f'ASTREE individuel {year}',[])]
    for n,code,value in ((4,'PRNV11',17),(5,'PRV11',7)):
        pages.append(page(n,f'Chiffres en dinars tunisiens 31/12/{year} 31/12/{year-1}',
            [word('Brutes',350,15),word(f'31/12/{year}',350,25),word(code,40,55),word(str(value),350,55)]))
    words=[word('PRNV11',40,120),word('Primes acquises' if year==2024 else 'Primes émises',110,120)]
    for i,(code,label) in enumerate(CATEGORIES):
        x=sum(EDGES[year][i:i+2])/2
        words.extend([word('TOTAL' if code.startswith('TOTAL') else code,x,100),word(str(1 if i<15 else (15,2,17)[i-15]),x,120)])
    pages.append(page(annex,f'Non Vie 31/12/{year}',words,True))
    pages.append(page(bridge,f'31/12/{year}',[word('Primes émises',120,150),word('PRNV11',450,150),word('17',530,150)]))
    pages.append(page(note,'Note 6.1',[word('Primes émises et acceptées',170,170),word('17',400,170),word('7',480,170)]))
    return pages


class AccountingTests(unittest.TestCase):
    def extract(self,pages,year=2025):return extract_accounting(pages,year,f'sources/ASTREE/{year}.pdf')

    def test_supported_layouts_and_partial_mapping(self):
        for year in (2024,2025):
            data=self.extract(fixture(year),year)
            self.assertEqual(data['mapped'],dict(AUTOMOBILE=1,INCENDIE=1,TRANSPORT=2,VIE=7))
            self.assertEqual(data['status'],'needs_review')
            self.assertNotIn('IRDS',data['mapped'])
            self.assertNotIn('GROUPE',data['mapped'])
            self.assertEqual(len(data['records']),18)
            self.assertTrue(all(v==0 for v in data['checks'].values()))
            self.assertEqual(bool(data['label_exception']),year==2024)

    def test_wrong_year_identity_and_unit_are_rejected(self):
        with self.assertRaises(ValueError):self.extract(fixture(2025),2023)
        for index,text in ((0,'STAR 2025'),(0,'ASTREE 2025 consolidés'),(1,'milliers de dinars tunisiens 31/12/2025 31/12/2024')):
            pages=fixture(2025);pages[index]['text']=text
            with self.assertRaises(ValueError):self.extract(pages)

    def test_missing_zero_duplicate_or_reordered_category_is_not_silently_admitted(self):
        for mode in ('missing','duplicate','reordered'):
            pages=fixture(2025);words=pages[3]['words']
            if mode=='missing':words.pop(3)
            elif mode=='duplicate':words.extend([word('PRNV11',40,140)])
            else:words[2]['text']='INCENDIE'
            with self.assertRaises(ValueError):self.extract(pages)

    def test_changed_gross_header_or_reconciliation_blocks_output(self):
        for index,text in ((1,'Nettes'),(4,'999'),(5,'999')):
            pages=fixture(2025)
            if index==1:pages[index]['words'][0]['text']=text
            else:pages[index]['words'][-1]['text']=text
            with self.assertRaises(ValueError):self.extract(pages)

    def test_unit_scaled_or_ocr_source_is_rejected(self):
        pages=fixture(2025);pages[3]['method']='ocr'
        with self.assertRaises(ValueError):self.extract(pages)

    def test_published_zero_is_retained_with_reconciled_totals(self):
        pages=fixture(2025)
        # Automobile zero; reduce the independently published direct/overall totals.
        pages[3]['words'][3]['text']='0'
        pages[3]['words'][2+15*2+1]['text']='14'
        pages[3]['words'][2+17*2+1]['text']='16'
        pages[1]['words'][-1]['text']='16';pages[4]['words'][-1]['text']='16';pages[5]['words'][-2]['text']='16'
        self.assertEqual(self.extract(pages)['mapped']['AUTOMOBILE'],0)
