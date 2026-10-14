import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import openpyxl

from ledger_orchestrator.extraction import comar
from ledger_orchestrator.extraction.adapters import ComarIndividualExtractor, get_extractor
from ledger_orchestrator.profiles import CompanyProfile
from ledger_orchestrator.validation.accounting import validate_balance, validate_premiums
from ledger_orchestrator.workbook import writer

CONFIG = Path(__file__).resolve().parents[1] / 'config' / 'comar.json'


def comar_config():
    return json.loads(CONFIG.read_text(encoding='utf-8'))


def premium(categories, total, statement=None):
    """Synthetic reader output with the COMAR category order."""
    rows = [dict(category=c, value=v, raw='-' if v is None else str(v), source_state='numeric',
                 header_text=c, page=37, bbox=[1, 1, 2, 2], unit='TND', method='native')
            for c, v in categories.items()]
    rows.append(dict(category='TOTAL', value=total, raw=str(total), source_state='numeric',
                     header_text='TOTAL', page=37, bbox=[1, 1, 2, 2], unit='TND', method='native'))
    life = [dict(meaning='annex_total', value=10, page=36, bbox=[1, 1, 2, 2], unit='TND', method='native')]
    return dict(records=rows, statement_gross=statement or total, bridge_value=total, life=dict(records=life))


CATEGORIES = comar_config()['premium_mapping']['categories']


class PartitionProfileTests(unittest.TestCase):
    def test_comar_profile_is_a_complete_partition(self):
        profile = CompanyProfile.load(CONFIG)
        self.assertEqual(profile.config['status'], 'validated')
        self.assertIsInstance(get_extractor(profile, [2023, 2024, 2025]), ComarIndividualExtractor)
        for years in ([2022], [2023, 2026]):
            with self.assertRaises(ValueError):
                get_extractor(profile, years)

    def test_missing_duplicate_or_unknown_categories_are_rejected(self):
        broken = []
        config = comar_config()
        config['premium_mapping']['branches']['IRDS'].remove('CAUTION')
        broken.append(config)
        config = comar_config()
        config['premium_mapping']['branches']['IRDS'].append('AUTOMOBILE')
        broken.append(config)
        config = comar_config()
        config['premium_mapping']['excluded'] = []
        broken.append(config)
        config = comar_config()
        del config['premium_mapping']['branches']['GROUPE']
        broken.append(config)
        config = comar_config()
        config['premium_mapping']['life_total'] = 'AUTOMOBILE'
        broken.append(config)
        for config in broken:
            with self.subTest(mapping=config['premium_mapping']), self.assertRaises(ValueError):
                CompanyProfile.from_dict(config)


class PremiumTests(unittest.TestCase):
    def values(self):
        return {c: 100 for c in CATEGORIES}

    def test_dash_is_nil_only_when_the_published_total_proves_it(self):
        values = self.values()
        values['TRAVAIL'] = None
        total = 100 * (len(CATEGORIES) - 1) + 1          # one-dinar rounding difference
        raw, issues = comar.premium_records(premium(values, total), 2024, 'sources/COMAR/2024.pdf', 3)
        self.assertEqual(raw['TRAVAIL']['value'], 0)
        self.assertEqual(raw['TRAVAIL']['nil_proof']['delta'], -1)
        self.assertIn('premium_dash_admitted_as_nil', [i['type'] for i in issues])
        raw, issues = comar.premium_records(premium(values, total + 500), 2024, 'sources/COMAR/2024.pdf', 3)
        self.assertNotIn('TRAVAIL', raw)
        self.assertIn('premium_dash_unproven', [i['type'] for i in issues])

    def test_partition_branches_totals_and_acceptations(self):
        values = self.values()
        total = sum(values.values())
        raw, _ = comar.premium_records(premium(values, total), 2023, 'sources/COMAR/2023.pdf', 3)
        branches, issues = validate_premiums(raw, comar_config())
        self.assertEqual(branches['IRDS']['value'], 900)
        self.assertEqual(sum(branches[b]['value'] for b in ('AUTOMOBILE', 'INCENDIE', 'TRANSPORT', 'IRDS', 'GROUPE')),
                         total - values['ACCEPTATION'])
        self.assertEqual(branches['VIE']['value'], 10)
        self.assertIn('premium_unallocated', [i['type'] for i in issues])

    def test_unreconciled_or_incomplete_annex_admits_no_branch(self):
        values = self.values()
        raw, _ = comar.premium_records(premium(values, sum(values.values()) + 4), 2023, 's', 3)
        self.assertEqual(validate_premiums(raw, comar_config()),
                         ({}, [dict(type='premium_source_total_mismatch', delta=-4)]))
        del raw['RC']
        branches, issues = validate_premiums(raw, comar_config())
        self.assertEqual((branches, issues[0]['type']), ({}, 'premium_nonlife_incomplete'))


def reading(current, comparative, gross=None, provisions=None, raw_current=None):
    cells = dict(current=dict(value=current, raw=raw_current if raw_current is not None else str(current), bbox=[1, 1, 2, 2]),
                 comparative=dict(value=comparative, raw=str(comparative), bbox=[3, 1, 4, 2]))
    if gross is not None:
        cells.update(gross=dict(value=gross, raw=str(gross)), provisions=dict(value=provisions, raw=''))
    return dict(cells=cells, page=2, unit='TND', method='native', row_label='label')


class BalanceTests(unittest.TestCase):
    def test_dash_is_a_nil_candidate_and_needs_a_reconciled_parent(self):
        balance = dict(corroborations={}, records={
            'AC5': reading(100, 90), 'AC510': reading(100, 90), 'AC520': reading(None, None, raw_current='-'),
            'AC530': reading(None, 5, raw_current='')})
        records, issues = comar.balance_records(balance, {}, 2025, 's', 3)
        self.assertEqual(records['AC520']['value'], 0)
        self.assertNotIn('AC530', records)                      # a blank is never a zero
        self.assertIn('source_blank_not_admitted', [i['type'] for i in issues])
        children = {'AC5': ['AC510', 'AC520', 'AC530', 'AC531']}
        self.assertIn('AC520', validate_balance(records, children, 3)['eligible'])
        records['AC5']['value'] = 150                            # parent no longer reconciles
        self.assertNotIn('AC520', validate_balance(records, children, 3)['eligible'])

    def test_gross_minus_provisions_must_equal_net(self):
        balance = dict(corroborations={}, records={'AC11': reading(80, 70, gross=100, provisions=20),
                                                   'AC12': reading(80, 70, gross=100, provisions=10)})
        records, issues = comar.balance_records(balance, {}, 2025, 's', 3)
        self.assertEqual(records['AC11']['row_checks'][0]['status'], 'passed')
        self.assertTrue(records['AC12']['ambiguous'])
        self.assertNotIn('AC12', validate_balance(records, {}, 3)['eligible'] + list(
            validate_balance(records, {'AC1': ['AC11', 'AC12']}, 3)['dependencies']))

    def test_printed_pa2_subtotal_and_note_collisions(self):
        balance = dict(corroborations={'PA2_PUBLISHED_SUBTOTAL': reading(7, 6)}, records={'PA23': reading(7, 6)})
        records, _ = comar.balance_records(balance, {}, 2025, 's', 3)
        self.assertEqual(records['PA2']['value'], 7)
        with self.assertRaises(ValueError):
            comar.balance_records(balance, {'PA23': reading(1, 1)}, 2025, 's', 3)


class AdapterTests(unittest.TestCase):
    def test_readers_must_read_the_fingerprinted_document(self):
        extractor = ComarIndividualExtractor()
        with self.assertRaises(ValueError):
            extractor.extract([], 2024, 's', comar_config())
        with patch.object(comar, 'extract', return_value=dict(sha256='a' * 64)), \
             patch.object(comar, 'candidate', return_value=dict(source_sha256='b' * 64)):
            with self.assertRaises(ValueError):
                extractor.extract([], 2024, 's', comar_config(), path=Path('x.pdf'), digest='a' * 64)


class ConfirmationTests(unittest.TestCase):
    def test_existing_typed_total_equal_to_published_total_is_confirmed(self):
        config = comar_config()
        record = lambda code, value: dict(code=code, year=2025, value=value, unit='TND', approved=True)
        records = {'AC11': record('AC11', 1), 'AC12': record('AC12', 2), 'AC13': record('AC13', 3), 'AC1': record('AC1', 7)}
        validation = validate_balance(records, {'AC1': ['AC11', 'AC12', 'AC13']}, 3)  # computed 6, published 7
        annual = {2025: dict(records=records, branches={}, validation=validation)}
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            wb = openpyxl.Workbook()
            g1 = wb.active
            g1.title = 'TAF_G1'
            g3 = wb.create_sheet('TAF_G3')
            g1['A1'], g3['B14'] = 'COMAR', 'COMAR'
            g1['C6'] = 7                   # the supervisor typed the published total
            g1['C3'] = 1
            wb.save(path / 'template.xlsx')
            confirmations = []
            config = copy.deepcopy(config)
            config['extend_template'] = False
            with patch.object(writer, 'recalculate'):
                writes, issues = writer.write_workbook(path / 'template.xlsx', path / 'out.xlsx', config, annual,
                                                       confirmations)
            self.assertEqual({(c['cell'], c['code']) for c in confirmations}, {('C6', 'AC1'), ('C3', 'AC11')})
            self.assertNotIn('existing_cell_conflict', [i['type'] for i in issues])
            g1['C6'] = 9                   # a different typed total stays a conflict
            wb.save(path / 'template.xlsx')
            with patch.object(writer, 'recalculate'):
                _, issues = writer.write_workbook(path / 'template.xlsx', path / 'out.xlsx', config, annual, [])
            self.assertIn('existing_cell_conflict', [i['type'] for i in issues])


if __name__ == '__main__':
    unittest.main()
