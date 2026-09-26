import unittest
from ledger_orchestrator.validation.source_audit import positioned_numbers,printed_numbers


class TextPage:
    def __init__(self,chars):
        self.chars=chars
    def count_chars(self):
        return len(self.chars)
    def get_text_range(self,i,count):
        return self.chars[i][0]
    def get_charbox(self,i):
        return self.chars[i][1]


class SourceAuditTests(unittest.TestCase):
    def test_geometry_separates_columns(self):
        page=TextPage([('1',(0,0,2,5)),('0',(3,0,5,5)),
                       ('2',(20,0,22,5)),('0',(23,0,25,5))])
        self.assertEqual(positioned_numbers(page,(-1,-1,30,6)),[10,20])

    def test_rotated_geometry(self):
        page=TextPage([('1',(0,0,5,2)),('0',(0,3,5,5)),
                       ('2',(0,20,5,22)),('0',(0,23,5,25))])
        self.assertEqual(positioned_numbers(page,(-1,-1,6,30),90),[10,20])

    def test_blank_and_zero_are_distinct(self):
        self.assertEqual(positioned_numbers(TextPage([]),(0,0,10,10)),[])
        self.assertEqual(positioned_numbers(TextPage([('0',(1,1,3,5))]),(0,0,10,10)),[0])

    def test_parentheses_and_negative(self):
        self.assertEqual(printed_numbers('(1 234) -567'),[-1234,-567])
