import json
from pathlib import Path
import tempfile
import unittest

import openpyxl

from ledger_orchestrator.evaluation.benchmark import benchmark
from ledger_orchestrator.evaluation.coverage_matrix import coverage_matrix, source_availability
from ledger_orchestrator.evaluation.template_map import target_cells

STAR = json.loads((Path(__file__).resolve().parents[1] / 'config' / 'star.json').read_text(encoding='utf-8'))


def template():
    """A synthetic two-sheet template with the CMF block conventions."""
    wb = openpyxl.Workbook()
    g1 = wb.active
    g1.title = 'TAF_G1'
    g1['A1'], g1['B1'], g1['I1'] = 'EXAMPLE', 'ACTIF', 'CAPITAUX PROPRES ET PASSIFS'
    for col, year in zip('CDEFG', range(2025, 2020, -1)):
        g1[f'{col}2'] = f'Montant Net 31/12/{year}'
    for col, year in zip('KLMNO', range(2025, 2020, -1)):
        g1[f'{col}2'] = f'31/12/{year}\nMontant Net'
    g1['A3'], g1['I3'] = 'AC11', 'CAPITAUX PROPRES'      # heading on the liability side
    g1['A4'], g1['I4'] = 'AC1', 'CP1 Capital social'
    g1['A5'] = 'TOTAL ACTIF'
    g1['C3'] = 1000
    g3 = wb.create_sheet('TAF_G3')
    g3['A1'], g3['B1'], g3['B2'] = 'Source : CMF', 'EXAMPLE', 2010
    g3['C2'] = '=+B2+1'
    g3['A4'], g3['A5'] = 'Automobile', 'Emissions Non Vie'
    g3['B5'], g3['C5'] = '=+B4', '=+C4'
    return wb


class TemplateMapTests(unittest.TestCase):
    def test_blocks_years_headings_and_formulas(self):
        cells = target_cells(template())
        g1 = [c for c in cells if c.sheet == 'TAF_G1']
        # 3 asset rows x 5 years + 1 liability row x 5 years; the heading is skipped.
        self.assertEqual(len(g1), 20)
        self.assertEqual({c.year for c in g1 if c.cell.startswith('C')}, {2025})
        self.assertFalse(any('CAPITAUX PROPRES' == c.label for c in g1))
        g3 = {c.cell: c for c in cells if c.sheet == 'TAF_G3'}
        self.assertEqual((g3['B4'].year, g3['C4'].year), (2010, 2011))
        self.assertTrue(g3['B5'].derived)
        self.assertFalse(g3['B4'].derived)

    def test_unterminated_balance_block_is_rejected(self):
        wb = template()
        wb['TAF_G1']['A5'] = None
        with self.assertRaises(ValueError):
            target_cells(wb)


class CoverageTests(unittest.TestCase):
    def test_sources_comparatives_and_filled_values(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'sources' / 'EXAMPLE').mkdir(parents=True)
            (root / 'sources' / 'EXAMPLE' / '2024.pdf').write_bytes(b'%PDF')
            self.assertEqual(source_availability(root / 'sources', 'EXAMPLE', 2024), 'statement')
            self.assertEqual(source_availability(root / 'sources', 'EXAMPLE', 2023), 'comparative_only')
            self.assertIsNone(source_availability(root / 'sources', 'EXAMPLE', 2025))
            wb = template()
            wb.save(root / 'template.xlsx')
            wb['TAF_G1']['D3'] = 5            # 2024 value
            wb['TAF_G1']['E3'] = '=IF(FALSE,1,"")'  # unevaluated guarded formula: not filled
            wb.save(root / 'filled.xlsx')
            result = coverage_matrix(root / 'template.xlsx', root / 'sources', root / 'filled.xlsx')
            rows = {(r['sheet'], r['year']): r for r in result['rows']}
            self.assertEqual(rows['TAF_G1', 2025]['prefilled'], 1)
            self.assertEqual(rows['TAF_G1', 2025]['filled'], 1)
            self.assertEqual(rows['TAF_G1', 2024]['filled'], 1)
            self.assertEqual(rows['TAF_G1', 2023]['filled'], 0)
            self.assertEqual(rows['TAF_G3', 2010]['derived_cells'], 1)
            self.assertEqual(result['summary']['TAF_G1']['with_source'], 8)


def fact(year, statement, code, amount, document_year=None):
    return dict(year=year, statement=statement, code=code, source_amount=str(amount), approved=True,
                evidence=dict(document_year=document_year or year))


class BenchmarkTests(unittest.TestCase):
    def run_benchmark(self, wb, facts):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'template.xlsx'
            wb.save(path)
            return benchmark(dict(config=STAR, facts=facts, run_id='test'), path)

    def star_template(self):
        wb = openpyxl.Workbook()
        wb.active.title = 'TAF_G1'
        wb.create_sheet('TAF_G3')
        g4 = wb.create_sheet('TAF_G4')
        g4['A28'], g4['B28'] = 2024, 'PRIMES NETTES'
        g4['A29'], g4['B29'], g4['I29'] = 'STAR', 431210, 23077
        return wb

    def test_template_references_agree_differ_and_missing(self):
        wb = self.star_template()
        wb['TAF_G1']['C53'] = 100     # AC11 2025
        wb['TAF_G1']['C54'] = 200     # AC12 2025
        wb['TAF_G1']['C55'] = 300     # AC13 2025, nothing extracted
        wb['TAF_G3']['Q9'] = '=SUM(Q4:Q8)'   # formula, never a reference
        result = self.run_benchmark(wb, [fact(2025, 'balance', 'AC11', 100),
                                         fact(2025, 'balance', 'AC12', 201),
                                         fact(2025, 'balance', 'AC1', 999)])
        self.assertEqual(result['template']['summary']['counts'], {'agree': 1, 'differ': 1, 'no_extraction': 1})
        self.assertEqual(result['template']['summary']['agreement'], 0.5)

    def test_comparatives_are_not_used_as_current_readings(self):
        wb = self.star_template()
        wb['TAF_G1']['D53'] = 100     # AC11 2024
        result = self.run_benchmark(wb, [fact(2024, 'balance', 'AC11', 100, document_year=2025)])
        self.assertEqual(result['template']['summary']['counts'], {'no_extraction': 1})

    def test_cga_rounding_and_missing_parts(self):
        wb = self.star_template()
        facts = [fact(2024, 'premiums', 'TOTAL_NONVIE', 376775092), fact(2024, 'premiums', 'TOTAL_VIE', 54434452),
                 fact(2024, 'balance', 'CP1', 23078600)]
        rows = {r['metric']: r for r in self.run_benchmark(wb, facts)['cga']['rows']}
        self.assertEqual(rows['B']['status'], 'agree')        # 431,209.544 kTND rounds to 431,210
        self.assertEqual(rows['I']['status'], 'differ')       # 23,079 vs 23,077: beyond 1 kTND
        facts = facts[1:]
        rows = {r['metric']: r for r in self.run_benchmark(wb, facts)['cga']['rows']}
        self.assertEqual(rows['B']['status'], 'no_extraction')


if __name__ == '__main__':
    unittest.main()
