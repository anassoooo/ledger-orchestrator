"""API reach for premium-history profiles, consolidation jobs and history review rows."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
import unittest.mock
from unittest.mock import patch

from fastapi.testclient import TestClient

from ledger_orchestrator import __main__ as cli
from ledger_orchestrator.api import app as api
from ledger_orchestrator.api.gateway import ALLOWED_PATH

CONFIG = Path(__file__).resolve().parents[1] / 'config' / 'star.json'
HISTORY = CONFIG.parent / 'history' / 'star_premiums.json'
STAR_HISTORY_YEARS = json.loads(HISTORY.read_text(encoding='utf-8'))['years']
CONSOLIDATION_ID = 'consolidated_20261014T030624_f62518e3'


class ImmediateThread:
    def __init__(self, target, daemon):
        self.target = target

    def start(self):
        self.target()


def worker_printing(result, progress='STAR 2024: extraction\n', indent=None):
    def run(command, **kwargs):
        kwargs['stdout'].write(progress + json.dumps(result, indent=indent))
        return SimpleNamespace(returncode=0)
    return run


def local_inputs(root, years_by_company):
    for relative in ['templates/TAF_G1_G2_G3_G4.xlsx',
                     *[f'sources/{c}/{y}.pdf' for c, years in years_by_company.items() for y in years]]:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'fixture')


class HistoryProfileApiTests(unittest.TestCase):
    def test_catalog_lists_history_profiles_as_runnable(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(api, 'CONFIG', CONFIG), \
             patch.object(api, 'ROOT', Path(temp)), TestClient(api.app) as client:
            catalog = {p['id']: p for p in client.get('/profiles').json()['profiles']}
        self.assertEqual(catalog['star']['kind'], 'statements')
        for identifier in ('star_premium_history', 'comar_premium_history', 'astree_premium_history'):
            self.assertIn(identifier, catalog)
            self.assertEqual(catalog[identifier]['kind'], 'premium_history')
            self.assertTrue(catalog[identifier]['runnable'], catalog[identifier]['reason'])

    def test_history_run_goes_through_the_cli_with_its_own_profile(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            local_inputs(root, {'STAR': STAR_HISTORY_YEARS})
            result = dict(run_id='20261014T030638_ed88e4e6', kind='premium_history', status='needs_review')
            with patch.object(api, 'CONFIG', CONFIG), patch.object(api, 'ROOT', root), \
                 patch.object(api, 'OUTPUT', root / 'outputs'), patch.object(api, 'threading', SimpleNamespace(Thread=ImmediateThread)), \
                 patch.object(api.subprocess, 'run', side_effect=worker_printing(result)) as worker, \
                 TestClient(api.app) as client:
                started = client.post('/runs', json={'profile_id': 'star_premium_history', 'years': [2012, 2011]})
                self.assertEqual(started.status_code, 202)
                self.assertEqual(client.get(started.json()['poll']).json()['kind'], 'premium_history')
                command = worker.call_args.args[0]
                self.assertEqual(command[2], 'ledger_orchestrator')
                self.assertEqual(command[command.index('--config') + 1], str(HISTORY))
                self.assertEqual(command[command.index('--years') + 1:], ['2011', '2012'])
                # 2013 has no STAR source document and is not a profile year.
                self.assertEqual(client.post('/runs', json={'profile_id': 'star_premium_history',
                                                            'years': [2013]}).status_code, 422)
                self.assertFalse(api.LOCK.locked())

    def test_cli_dispatches_by_profile_kind(self):
        report = dict(run_id='20261014T030638_ed88e4e6', kind='premium_history', status='completed',
                      writes=[{}, {}], workbook='STAR_historique.xlsx')
        argv = ['ledger_orchestrator', '--config', str(HISTORY), '--years', '2011']
        with patch.object(sys, 'argv', argv), patch.object(cli, 'run_profile', return_value=report) as run, \
             patch('builtins.print') as printed:
            cli.main()
        self.assertEqual(run.call_args.args[2], HISTORY)
        self.assertEqual(run.call_args.kwargs['years'], [2011])
        self.assertEqual(json.loads(printed.call_args.args[0]),
                         dict(run_id=report['run_id'], kind='premium_history', status='completed',
                              written_cells=2, workbook='STAR_historique.xlsx'))

    def test_history_review_rows_open_as_cases(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            run_id = '20261014T030638_ed88e4e6'
            (output / run_id).mkdir()
            row = dict(year=2016, sheet='TAF_G3', cell='H40', code='AUTOMOBILE', status='missing_or_blocked',
                       reason=None)
            (output / run_id / 'report.json').write_text(json.dumps(dict(
                kind='premium_history', status='needs_review', company='ASTREE', years=[2016],
                issues=[], review=[row], data={})), encoding='utf-8')
            try:
                with patch.object(api, 'OUTPUT', output), TestClient(api.app) as client:
                    self.assertEqual(client.get('/runs').json()['runs'][0]['kind'], 'premium_history')
                    cases = client.get(f'/runs/{run_id}/review').json()['cases']
                    self.assertEqual(cases[0]['case_id'], 'TAF_G3-H40')
                    self.assertEqual(cases[0]['category'], 'missing_or_blocked')
                    self.assertTrue(cases[0]['reason'])
                    detail = client.get(f'/runs/{run_id}/review/TAF_G3-H40')
                    self.assertEqual(detail.status_code, 200)
                    self.assertIsNone(detail.json()['case']['source'])
                    self.assertEqual(client.get(f'/runs/{run_id}/review/TAF_G3-H40/source').status_code, 404)
            finally:
                api.review_workflow(str(output / 'review_graph.sqlite3')).close()
                api.review_workflow.cache_clear()


class ConsolidationApiTests(unittest.TestCase):
    def test_consolidation_job_runs_profiles_in_order(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            local_inputs(root, {'STAR': sorted({2023, 2024, 2025, *STAR_HISTORY_YEARS})})
            # consolidate prints an indented document after progress lines.
            result = dict(folder=CONSOLIDATION_ID, passed=True, checks={}, runs=[])
            with patch.object(api, 'CONFIG', CONFIG), patch.object(api, 'ROOT', root), \
                 patch.object(api, 'OUTPUT', root / 'outputs'), patch.object(api, 'threading', SimpleNamespace(Thread=ImmediateThread)), \
                 patch.object(api.subprocess, 'run', side_effect=worker_printing(result, indent=2)) as worker, \
                 TestClient(api.app) as client:
                started = client.post('/consolidations', json={'profile_ids': ['star_premium_history', 'star']})
                self.assertEqual(started.status_code, 202)
                job = client.get(started.json()['poll']).json()
                self.assertEqual((job['status'], job['folder'], job['passed']), ('completed', CONSOLIDATION_ID, True))
                command = worker.call_args.args[0]
                self.assertEqual(command[2], 'ledger_orchestrator.consolidate')
                self.assertEqual(command[command.index('--configs') + 1:], [str(HISTORY), str(CONFIG)])
                self.assertFalse(api.LOCK.locked())

    def test_invalid_consolidations_do_not_start_worker(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            local_inputs(root, {'STAR': [2023, 2024, 2025]})
            with patch.object(api, 'CONFIG', CONFIG), patch.object(api, 'ROOT', root), \
                 patch.object(api, 'threading', SimpleNamespace(Thread=unittest.mock.Mock())) as threads, TestClient(api.app) as client:
                for body in ({'profile_ids': []}, {'profile_ids': ['star', 'star']}, {'profile_ids': ['unknown']},
                             # COMAR sources are absent from this fixture.
                             {'profile_ids': ['star', 'comar']}):
                    self.assertEqual(client.post('/consolidations', json=body).status_code, 422, body)
            threads.Thread.assert_not_called()

    def test_consolidation_listing_detail_and_verified_download(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            folder = output / CONSOLIDATION_ID
            folder.mkdir()
            summary = dict(workbook='TAF_consolide.xlsx', passed=True, checks={'every_write_preserved': True},
                           runs=[dict(run_id='20261014T030624_2dc79e88', company='STAR', kind='statements',
                                      status='needs_review', writes=255)])
            (folder / 'consolidation.json').write_text(json.dumps(summary), encoding='utf-8')
            (folder / 'TAF_consolide.xlsx').write_bytes(b'consolidated workbook')
            (output / 'consolidated_not-an-id').mkdir()
            with patch.object(api, 'OUTPUT', output), TestClient(api.app) as client:
                listing = client.get('/consolidations').json()['consolidations']
                self.assertEqual([c['consolidation_id'] for c in listing], [CONSOLIDATION_ID])
                self.assertEqual(listing[0]['runs'][0]['writes'], 255)
                base = f'/consolidations/{CONSOLIDATION_ID}'
                self.assertTrue(client.get(base).json()['passed'])
                self.assertEqual(client.get(base + '/workbook').content, b'consolidated workbook')
                self.assertEqual(client.get('/consolidations/consolidated_not-an-id').status_code, 404)
                summary['passed'] = False
                (folder / 'consolidation.json').write_text(json.dumps(summary), encoding='utf-8')
                self.assertEqual(client.get(base + '/workbook').status_code, 409)


class WorkerOutputTests(unittest.TestCase):
    def test_final_json_reads_one_line_and_indented_results(self):
        self.assertEqual(api.final_json('STAR 2024: extraction\n{"run_id": "x"}\n'), {'run_id': 'x'})
        self.assertEqual(api.final_json('progress\n' + json.dumps({'a': {'b': [1]}}, indent=2)), {'a': {'b': [1]}})
        with self.assertRaises(ValueError):
            api.final_json('no result here')

    def test_gateway_allows_only_scoped_consolidation_routes(self):
        for path in ('/consolidations', f'/consolidations/{CONSOLIDATION_ID}',
                     f'/consolidations/{CONSOLIDATION_ID}/workbook'):
            self.assertIsNotNone(ALLOWED_PATH.fullmatch(path), path)
        for path in ('/consolidations/../outputs', f'/consolidations/{CONSOLIDATION_ID}/report',
                     '/consolidations/consolidated_x', f'/consolidations/{CONSOLIDATION_ID}/../../data'):
            self.assertIsNone(ALLOWED_PATH.fullmatch(path), path)


if __name__ == '__main__':
    unittest.main()
