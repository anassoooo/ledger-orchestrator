import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import openpyxl
from fastapi.testclient import TestClient

from ledger_orchestrator import pipeline
from ledger_orchestrator.api import app as api
from ledger_orchestrator.extraction.adapters import get_extractor
from ledger_orchestrator.profiles import CompanyProfile, local_path
from ledger_orchestrator.records import canonical_facts
from ledger_orchestrator.validation.coverage import measure
from ledger_orchestrator.workbook.writer import write_workbook


CONFIG = Path(__file__).resolve().parents[1] / 'config' / 'star.json'


def star():
    return json.loads(CONFIG.read_text(encoding='utf-8'))


def synthetic():
    """A synthetic workbook profile, not an extraction qualification for a real insurer."""
    config = star()
    config.update(profile_id='example', company='EXAMPLE', extractor='unqualified',
                  identity_terms=['EXAMPLE'], source_directory='sources/EXAMPLE', years=[2018, 2020],
                  asset_rows={'AC11': 4}, liability_rows={'CP1': 6}, branch_rows={'VIE': 2}, children={})
    config['workbook'] = dict(template='templates/example.xlsx', filename='example_result.xlsx',
        balance_sheet='Balance', premium_sheet='Premiums', details_sheet='Details', details_title='Details TND',
        anchors=[dict(sheet='Balance', cell='A1', value='EXAMPLE'),
                 dict(sheet='Premiums', cell='A1', value='EXAMPLE')],
        columns={'2018': dict(asset='B', liability='C', premium='B', details='C'),
                 '2020': dict(asset='F', liability='G', premium='D', details='E')},
        column_widths={'asset': 20, 'premium': 18},
        premium_totals={'LIFE_TOTAL': dict(row=3, children=['VIE'])},
        label_overrides=[], extension_only={})
    return config


class ProfileTests(unittest.TestCase):
    def test_legacy_scanned_source_alias_is_bound_to_declared_document(self):
        profile = CompanyProfile.load(CONFIG)
        current = dict(records={}, validation={'eligible': []})
        annual = {2024: dict(records={}), 2025: current}
        with patch('ledger_orchestrator.extraction.adapters.read_scanned_asset', return_value={
            'records': {'AC33': dict(source='STAR/2025.pdf')}}), \
             patch('ledger_orchestrator.extraction.adapters.corroborate_subtotals', return_value={}) as corroborate:
            get_extractor(profile, [2024, 2025]).refine(annual, Path.cwd(), Path('outputs/cache'), profile)
            self.assertEqual(corroborate.call_args.args[0]['AC33']['source'], 'sources/STAR/2025.pdf')

    def test_explicit_years_and_columns_preserve_star_mapping(self):
        profile = CompanyProfile.load(CONFIG)
        self.assertEqual(profile.select_years(), [2023, 2024, 2025])
        self.assertIn(('TAF_G1', 'C53', 'AC11'), list(profile.targets(2025)))
        self.assertIn(('TAF_G3', 'O12', 'TOTAL_12'), list(profile.targets(2023)))
        self.assertEqual(len(list(profile.targets(2025))), 90)
        self.assertEqual(profile.fingerprint, CompanyProfile.from_dict(star()).fingerprint)
        for years in ([], [True], [2022]):
            with self.subTest(years=years), self.assertRaises(ValueError):
                profile.select_years(years)

    def test_rejects_collisions_and_invalid_dependencies_before_writing(self):
        mutations = [
            lambda c: c['workbook']['columns']['2024'].update(asset='C'),
            lambda c: c['asset_rows'].update(AC12=53),
            lambda c: c['workbook']['columns'].pop('2024'),
            lambda c: c['children'].update(AC11=['AC1']),
            lambda c: c['workbook']['premium_totals']['TOTAL_9'].update(children=['UNKNOWN']),
            lambda c: c['workbook']['premium_totals']['TOTAL_9'].update(children=['TOTAL_12']),
            lambda c: c['workbook']['anchors'][0].update(cell='C53'),
            lambda c: c.update(source_directory='../secrets'),
            lambda c: c['workbook'].update(filename='../output.xlsx'),
            lambda c: c.update(rounding_tolerance_tnd=float('nan')),
        ]
        for mutate in mutations:
            config = star()
            mutate(config)
            with self.subTest(config=config), self.assertRaises(ValueError):
                CompanyProfile.from_dict(config)

    def test_malformed_contracts_raise_profile_errors(self):
        for change in (dict(schema_version=True), dict(profile_id=None), dict(identity_terms='STAR'),
                       dict(workbook=[]), dict(children=[]), dict(years=['2025'])):
            with self.subTest(change=change), self.assertRaises(ValueError):
                CompanyProfile.from_dict(dict(star(), **change))
        with self.assertRaises(ValueError):
            CompanyProfile.from_dict([])

    def test_unqualified_company_and_draft_profile_are_not_executable(self):
        profile = CompanyProfile.from_dict(synthetic())
        with self.assertRaisesRegex(ValueError, 'No qualified extractor'):
            get_extractor(profile, profile.select_years())
        config = star()
        config['status'] = 'draft'
        with self.assertRaisesRegex(ValueError, 'draft'):
            CompanyProfile.from_dict(config).select_years()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'profile.json'
            path.write_text(json.dumps(synthetic()), encoding='utf-8')
            output = Path(temp) / 'output'
            with self.assertRaisesRegex(ValueError, 'No qualified extractor'):
                pipeline.execute(Path(temp), output, path)
            self.assertFalse(output.exists())

    def test_local_paths_reject_traversal_and_absolute_paths(self):
        for path in ('../private.pdf', '/private.pdf', 'C:/private.pdf', 'sources/../../private.pdf',
                     'sources\\private.pdf', ''):
            with self.subTest(path=path), self.assertRaises(ValueError):
                local_path(Path.cwd(), path)

    def test_workbook_and_coverage_follow_synthetic_profile_for_nonconsecutive_years(self):
        config = synthetic()
        annual = {}
        for year, value in ((2018, 100), (2020, 0)):
            records = {code: dict(value=amount, approved=True, source_label=code)
                       for code, amount in [('AC11', value), ('CP1', 90), ('EXTRA', 5)]}
            annual[year] = dict(records=records, validation=dict(eligible=list(records), dependencies={}),
                                branches={'VIE': dict(value=40, sources=[dict(approved=True)])})
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            wb = openpyxl.Workbook()
            wb.active.title = 'Balance'
            wb.create_sheet('Premiums')
            wb['Balance']['A1'] = wb['Premiums']['A1'] = 'EXAMPLE'
            wb['Balance']['B4'] = 77
            wb.create_sheet('Untouched')['Z9'] = 'keep'
            source, result = root / 'source.xlsx', root / 'result.xlsx'
            wb.save(source)
            source_bytes = source.read_bytes()
            with patch('ledger_orchestrator.workbook.writer.recalculate'):
                writes, issues = write_workbook(source, result, config, annual)
            actual = openpyxl.load_workbook(result)
            self.assertEqual(actual['Balance']['B4'].value, 77)
            self.assertEqual(actual['Balance']['F4'].value, 0)
            self.assertEqual(actual['Balance']['G6'].value, 90)
            self.assertEqual(actual['Premiums']['D3'].value, '=IF(COUNT(D2)=1,SUM(D2),"")')
            self.assertEqual(actual['Details']['E2'].value, 5)
            self.assertEqual(actual['Details']['E1'].value, 2020)
            self.assertIsNone(actual['Details']['D1'].value)
            self.assertEqual(actual['Untouched']['Z9'].value, 'keep')
            self.assertEqual(source.read_bytes(), source_bytes)
            coverage = measure(result, config, [2018, 2020], writes, issues)
            cells = {(c['year'], c['code']): c for c in coverage['cells']}
            self.assertEqual(cells[2018, 'AC11']['status'], 'conflict')
            self.assertEqual(cells[2020, 'AC11']['cell'], 'F4')
            self.assertEqual(cells[2020, 'AC11']['status'], 'populated_this_run')


class FinancialFactTests(unittest.TestCase):
    def setUp(self):
        self.profile = CompanyProfile.load(CONFIG)
        self.documents = {'2025': dict(sha256='a' * 64, pages=10)}
        self.record = dict(code='AC11', year=2025, value=0, source='sources/STAR/2025.pdf',
                           page=2, method='native', unit='TND', approved=True, bbox=[1, 2, 3, 4])

    def facts(self, record=None, year=2025):
        return canonical_facts({year: dict(records={'AC11': record or self.record}, raw_branches={})},
                               self.documents, self.profile)

    def test_zero_and_provenance_are_preserved(self):
        fact = self.facts()[0]
        self.assertEqual(fact['target_amount'], '0')
        self.assertEqual(fact['source_amount'], '0')
        self.assertEqual(fact['evidence']['sha256'], 'a' * 64)
        self.assertEqual(fact['evidence']['conversion_factor'], '1')

    def test_unverified_unit_has_no_target_amount(self):
        fact = self.facts(dict(self.record, unit=None, approved=False))[0]
        self.assertIsNone(fact['target_amount'])
        self.assertEqual(fact['source_amount'], '0')

    def test_invalid_approved_records_fail_before_workbook(self):
        for change in (dict(value=float('nan')), dict(value=True), dict(page=11), dict(ambiguous=True),
                       dict(unit=None), dict(conversion_factor=1000), dict(source='sources/OTHER/2025.pdf'),
                       dict(bbox=[3, 2, 1, 4]), dict(approved='yes'), dict(year=2024)):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.facts(dict(self.record, **change))

    def test_comparative_uses_actual_document_year_and_fingerprint(self):
        record = dict(self.record, year=2024, source_year=2025,
                      source_column='previous', source_kind='native_comparative')
        fact = self.facts(record, 2024)[0]
        self.assertEqual(fact['year'], 2024)
        self.assertEqual(fact['evidence']['document_year'], 2025)
        del record['source_column']
        with self.assertRaises(ValueError):
            self.facts(record, 2024)


class ProfileApiTests(unittest.TestCase):
    def test_start_passes_profile_defaults_to_worker(self):
        from types import SimpleNamespace

        class ImmediateThread:
            def __init__(self, target, daemon):
                self.target = target

            def start(self):
                self.target()

        def execute_stub(command, **kwargs):
            kwargs['stdout'].write(json.dumps(dict(run_id='20261002T120000_1234abcd', status='needs_review')))
            return SimpleNamespace(returncode=0)

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for relative in ['templates/TAF_G1_G2_G3_G4.xlsx', *[f'sources/STAR/{y}.pdf' for y in (2023, 2024, 2025)]]:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'fixture')
            with patch.object(api, 'CONFIG', CONFIG), patch.object(api, 'ROOT', root), \
                 patch.object(api, 'OUTPUT', root / 'outputs'), patch.object(api.threading, 'Thread', ImmediateThread), \
                 patch.object(api.subprocess, 'run', side_effect=execute_stub) as worker, TestClient(api.app) as client:
                started = client.post('/runs', json={'profile_id': 'star'})
                self.assertEqual(started.status_code, 202)
                self.assertEqual(client.get(started.json()['poll']).json()['status'], 'needs_review')
                command = worker.call_args.args[0]
                self.assertEqual(command[command.index('--config') + 1], str(CONFIG))
                self.assertEqual(command[command.index('--years') + 1:], ['2023', '2024', '2025'])
                self.assertFalse(api.LOCK.locked())

    def test_catalog_and_invalid_runs_do_not_start_worker(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(api, 'CONFIG', CONFIG), \
             patch.object(api, 'ROOT', Path(temp)), patch.object(api.threading, 'Thread') as worker:
            with TestClient(api.app) as client:
                catalog = client.get('/profiles').json()
                self.assertEqual(catalog['default_profile_id'], 'star')
                self.assertEqual(catalog['profiles'][0]['available_years'], [])
                self.assertTrue(catalog['profiles'][0]['runnable'])
                for body in ({'profile_id': 'unknown'}, {'years': [2018]}, {'years': []},
                             {'profile_id': '../star'}, {'years': [2025]}):
                    self.assertEqual(client.post('/runs', json=body).status_code, 422)
            worker.assert_not_called()

    def test_source_and_download_use_report_locations(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / 'outputs' / '20261002T120000_1234abcd'
            folder.mkdir(parents=True)
            source = root / 'sources' / 'EXAMPLE' / '2020.pdf'
            source.parent.mkdir(parents=True)
            source.write_bytes(b'%PDF synthetic')
            (folder / 'example_result.xlsx').write_bytes(b'synthetic workbook')
            case = dict(year=2018, sheet='Balance', cell='B4', code='AC11', category='review',
                        reason='test', action='review', source='sources/EXAMPLE/2020.pdf', page=1,
                        dependencies=[], issue_types=[])
            report = dict(status='needs_review', company='EXAMPLE', review=[case], workbook='example_result.xlsx')
            path = folder / 'report.json'
            path.write_text(json.dumps(report), encoding='utf-8')
            with patch.object(api, 'ROOT', root), patch.object(api, 'OUTPUT', folder.parent), TestClient(api.app) as client:
                base = f'/runs/{folder.name}'
                self.assertEqual(client.get(base + '/review/Balance-B4/source').content, b'%PDF synthetic')
                self.assertEqual(client.get(base + '/workbook').content, b'synthetic workbook')
                case['source'] = 'sources/../../secret.pdf'
                report['workbook'] = '../secret.xlsx'
                path.write_text(json.dumps(report), encoding='utf-8')
                self.assertEqual(client.get(base + '/review/Balance-B4/source').status_code, 404)
                self.assertEqual(client.get(base + '/workbook').status_code, 404)
