import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import openpyxl

from ledger_orchestrator.workbook import premium_writer
from ledger_orchestrator.workbook.premium_writer import HistoryProfile, write_premium_history

CONFIG = Path(__file__).resolve().parents[1] / 'config' / 'history' / 'star_premiums.json'


def star_history():
    return json.loads(CONFIG.read_text(encoding='utf-8'))


def template(path):
    wb = openpyxl.Workbook()
    sheet = wb.active
    sheet.title = 'TAF_G3'
    sheet['B1'], sheet['B2'] = 'STAR', 2010
    for col in range(3, 18):
        sheet.cell(2, col, f'=+{openpyxl.utils.get_column_letter(col - 1)}2+1')
    sheet['M9'] = '=+M8+M7+M6+M5+M4'           # the template's own total formula for 2021
    wb.save(path)


def branches(values, approved=True):
    source = dict(approved=approved)
    result = {code: dict(value=v, sources=[source]) for code, v in values.items()}
    return {2021: dict(branches=result)}


VALUES = dict(AUTOMOBILE=100, INCENDIE=20, TRANSPORT=10, IRDS=5, GROUPE=50, VIE=7)


class HistoryProfileTests(unittest.TestCase):
    def test_star_profile_columns_and_partition(self):
        profile = HistoryProfile.load(CONFIG)
        self.assertEqual(profile.column(2010), 'B')
        self.assertEqual(profile.address(2022, 'AUTOMOBILE'), 'N4')
        self.assertEqual(profile.address(2021, 'TOTAL_12'), 'M12')

    def test_incomplete_or_overlapping_partitions_are_rejected(self):
        broken = []
        config = star_history()
        config['taxonomy']['branches']['IRDS'].remove('VOL')
        broken.append(config)
        config = star_history()
        config['taxonomy']['branches']['GROUPE'].append('VOL')
        broken.append(config)
        config = star_history()
        config['taxonomy']['nonlife']['subtotals']['TOTAL_DIRECT'].append('ACCEPTATION')
        broken.append(config)
        config = star_history()
        config['premium_basis'] = 'net_of_reinsurance'
        broken.append(config)
        config = star_history()
        config['years'] = [2009]
        broken.append(config)
        for config in broken:
            with self.subTest(config=config['taxonomy']['branches']), self.assertRaises(ValueError):
                HistoryProfile.from_dict(config)


class PremiumWriterTests(unittest.TestCase):
    def write(self, annual, prepare=None):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            template(path / 'template.xlsx')
            if prepare:
                wb = openpyxl.load_workbook(path / 'template.xlsx')
                prepare(wb['TAF_G3'])
                wb.save(path / 'template.xlsx')
            with patch.object(premium_writer, 'recalculate'):
                writes, issues = write_premium_history(path / 'template.xlsx', path / 'out.xlsx',
                                                       HistoryProfile.load(CONFIG), annual, [])
            return writes, issues, openpyxl.load_workbook(path / 'out.xlsx')['TAF_G3']

    def test_branches_and_guarded_totals(self):
        writes, issues, sheet = self.write(branches(VALUES))
        self.assertEqual(sheet['M4'].value, 100)
        self.assertEqual(sheet['M10'].value, 7)
        self.assertTrue(sheet['M9'].value.startswith('=IF(COUNT(M4,M5,M6,M7,M8)=5'))
        self.assertEqual(issues, [])
        self.assertEqual(len(writes), 9)

    def test_unapproved_branch_blocks_its_totals(self):
        annual = branches(VALUES)
        annual[2021]['branches']['IRDS']['sources'] = [dict(approved=False)]
        _, _, sheet = self.write(annual)
        self.assertIsNone(sheet['M7'].value)
        self.assertIn('AND(FALSE', sheet['M9'].value)

    def test_existing_value_conflict_is_preserved(self):
        def prepare(sheet):
            sheet['M4'] = 99
        _, issues, sheet = self.write(branches(VALUES), prepare)
        self.assertEqual(sheet['M4'].value, 99)
        self.assertEqual(issues[0]['type'], 'existing_cell_conflict')

    def test_wrong_anchor_or_broken_year_chain_is_rejected(self):
        for prepare in (lambda s: s.__setitem__('B1', 'COMAR'), lambda s: s.__setitem__('M2', 2021)):
            with self.subTest(), self.assertRaises(ValueError):
                self.write(branches(VALUES), prepare)


if __name__ == '__main__':
    unittest.main()
