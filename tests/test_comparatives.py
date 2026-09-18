import unittest
from cmf.comparatives import supplement_comparatives
from cmf.review import build_review


class ComparativeTests(unittest.TestCase):
    def fixture(self):
        return {2023:dict(records={}),2024:dict(records={'PA350':dict(value=20,previous=0,method='native',unit='TND',source='s',page=3)},validation={'eligible':['PA350']})}

    def test_published_zero_and_source_period_preserved(self):
        data=self.fixture()
        events=supplement_comparatives(data,{},3)
        r=data[2023]['records']['PA350']
        self.assertEqual(r['value'],0)
        self.assertEqual(r['year'],2023)
        self.assertEqual(r['source_year'],2024)
        self.assertEqual(r['source_column'],'previous')
        self.assertEqual(data[2024]['records']['PA350']['value'],20)
        self.assertEqual(len(events),1)

    def test_missing_comparative_not_zero(self):
        data=self.fixture()
        data[2024]['records']['PA350']['previous']=None
        self.assertEqual(supplement_comparatives(data,{},3),[])
        self.assertEqual(data[2023]['records'],{})

    def test_existing_value_never_replaced(self):
        data=self.fixture()
        data[2023]['records']['PA350']=dict(value=5,unit='TND')
        supplement_comparatives(data,{},3)
        self.assertEqual(data[2023]['records']['PA350']['value'],5)

    def test_ocr_or_notes_not_admitted_as_comparative_fallback(self):
        for field,value in [('method','ocr'),('source_kind','asset_note'),('ambiguous',True)]:
            data=self.fixture()
            data[2024]['records']['PA350'][field]=value
            self.assertEqual(supplement_comparatives(data,{},3),[])

    def test_review_does_not_call_undetected_value_zero(self):
        c=dict(year=2025,sheet='TAF_G1',cell='C53',code='AC11',status='missing_or_blocked')
        rows=build_review({'cells':[c]},{2025:{'records':{}}},{'children':{}},[])
        self.assertEqual(rows[0]['category'],'non_detecte')
        self.assertIn('ne signifie pas zéro',rows[0]['action'])
