import unittest
from cmf.annual_compare import extract_asset


class Page:
    width=1000
    def extract_words(self):
        result=[]
        for i in range(36):
            for x,text in [(240,'AC'+str(100+i)),(400,'Rubrique'),(600,'100'),(680,'-'),(755,'70'),(830,'60')]:
                result.append(dict(text=text,x0=x,x1=x+len(text)*2,top=20+i*12,bottom=26+i*12))
        return result


class AnnualCompareTests(unittest.TestCase):
    header='31/12/2025 31/12/2024 dinar AC613 AC541'
    def test_blank_provision_is_not_zero(self):
        rows=extract_asset(Page(),'états financiers individuels 2025',self.header)
        self.assertEqual(rows['AC100']['value'],70)
        self.assertEqual(rows['AC100']['previous'],60)
        self.assertIsNone(rows['AC100']['provision'])
        self.assertIsNone(rows['AC100']['net_delta'])

    def test_consolidated_wrong_year_or_unverified_unit_rejected(self):
        for section,header in [('consolidés 2025',self.header),
                               ('individuels 2025',self.header+' consolidé'),
                               ('individuels 2025',self.header.replace('2024','2023')),
                               ('individuels 2025',self.header.replace('dinar',''))]:
            with self.assertRaises(ValueError):
                extract_asset(Page(),section,header)
