from pathlib import Path
import tempfile
import unittest

import openpyxl

from ledger_orchestrator.consolidate import verify_union


def run(company, *writes, profile=None):
    return dict(company=company, profile=dict(id=profile or company.lower()),
                writes=[dict(sheet='TAF_G1', cell=c, new=v) for c, v in writes])


class ConsolidationTests(unittest.TestCase):
    def check(self, cells, runs):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'final.xlsx'
            wb = openpyxl.Workbook()
            wb.active.title = 'TAF_G1'
            for cell, value in cells.items():
                wb['TAF_G1'][cell] = value
            wb.save(path)
            return verify_union(path, runs)

    def test_union_of_disjoint_runs_passes(self):
        checks = self.check({'C3': 1, 'C53': '=SUM(C51:C52)'},
                            [run('COMAR', ('C3', 1)), run('STAR', ('C53', '=SUM(C51:C52)'))])
        self.assertTrue(all(checks.values()))

    def test_overwritten_or_doubly_written_cells_fail(self):
        checks = self.check({'C3': 2}, [run('COMAR', ('C3', 1))])
        self.assertFalse(checks['every_write_preserved'])
        checks = self.check({'C3': 1}, [run('COMAR', ('C3', 1)), run('STAR', ('C3', 1))])
        self.assertFalse(checks['no_cell_written_twice'])
        checks = self.check({'C3': 1}, [run('STAR', ('C3', 1)), run('STAR', ('C4', None))])
        self.assertFalse(checks['profiles_distinct'])
        checks = self.check({'C3': 1, 'C4': 2}, [run('STAR', ('C3', 1)),
                                                  run('STAR', ('C4', 2), profile='star_premium_history')])
        self.assertTrue(all(checks.values()))


if __name__ == '__main__':
    unittest.main()
