import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from ledger_orchestrator.gateway import ALLOWED_PATH

try:
    from ledger_orchestrator.review_graph import ReviewWorkflow
except ImportError:
    ReviewWorkflow = None


class GatewayReviewRoutesTests(unittest.TestCase):
    def test_review_routes_are_scoped_to_known_run_and_cell_ids(self):
        prefix = '/runs/20260924T074936_4a5f2ea5/review'
        for path in ('/review', '/review/app.js', '/runs', prefix,
                     prefix + '/TAF_G1-E53', prefix + '/TAF_G1-E53/start',
                     prefix + '/TAF_G1-E53/decision', prefix + '/TAF_G1-E53/source'):
            self.assertIsNotNone(ALLOWED_PATH.fullmatch(path), path)
        for path in ('/review/../../data', prefix + '/../../2025.pdf',
                     prefix + '/TAF_G1-E53/extra', '/runs/invalid/review'):
            self.assertIsNone(ALLOWED_PATH.fullmatch(path), path)


@unittest.skipUnless(ReviewWorkflow, 'LangGraph dependencies are required')
class ReviewGraphTests(unittest.TestCase):
    def test_interrupt_resume_and_restart_preserve_history(self):
        case = {'run_id': 'run-1', 'case_id': 'TAF_G1-E53', 'reason': 'Source non détectée'}
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / 'review.sqlite3'
            graph = ReviewWorkflow(database)
            self.assertEqual(graph.snapshot('run-1:TAF_G1-E53')['history'], [])
            started = graph.start('run-1:TAF_G1-E53', case)
            self.assertTrue(started['waiting_for_human'])
            self.assertIsNone(started['decision'])
            first = graph.decide('run-1:TAF_G1-E53', {
                'action': 'follow_up', 'reviewer': 'Anas', 'note': 'Contrôler la note PDF.'
            })
            self.assertEqual(first['decision']['action'], 'follow_up')
            self.assertTrue(first['waiting_for_human'])
            graph.close()

            reopened = ReviewWorkflow(database)
            self.assertEqual(len(reopened.snapshot('run-1:TAF_G1-E53')['history']), 1)
            second = reopened.decide('run-1:TAF_G1-E53', {
                'action': 'documented', 'reviewer': 'Anas', 'note': 'Page vérifiée ; revue consignée.'
            })
            self.assertEqual([d['action'] for d in second['history']], ['follow_up', 'documented'])
            self.assertTrue(second['waiting_for_human'])
            reopened.close()

    def test_requires_start_and_rejects_changed_case(self):
        with tempfile.TemporaryDirectory() as temp:
            graph = ReviewWorkflow(Path(temp) / 'review.sqlite3')
            with self.assertRaises(ValueError):
                graph.decide('case', {'action': 'follow_up', 'reviewer': 'Anas', 'note': 'À revoir'})
            graph.start('case', {'reason': 'First'})
            with self.assertRaises(ValueError):
                graph.start('case', {'reason': 'Changed'})
            graph.close()


@unittest.skipUnless(ReviewWorkflow, 'LangGraph dependencies are required')
class ReviewApiTests(unittest.TestCase):
    def test_local_review_flow_does_not_edit_workbook(self):
        try:
            from fastapi.testclient import TestClient
            from ledger_orchestrator import api
        except ImportError:
            self.skipTest('FastAPI TestClient is unavailable')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / 'outputs'
            run_id = '20260924T074936_4a5f2ea5'
            folder = output / run_id
            folder.mkdir(parents=True)
            case = dict(year=2025, sheet='TAF_G1', cell='Q53', code='AC11',
                        category='non_detecte', reason='Aucun montant admissible détecté',
                        action='Vérifier le PDF', source='sources/STAR/2025.pdf', page=2,
                        dependencies=[], issue_types=['not_found'])
            (folder / 'report.json').write_text(json.dumps({
                'status': 'needs_review', 'company': 'STAR', 'years': [2025], 'review': [case]
            }), encoding='utf-8')
            workbook = folder / 'STAR_consolide.xlsx'
            workbook.write_bytes(b'unchanged workbook')
            pdf = root / 'sources' / 'STAR' / '2025.pdf'
            pdf.parent.mkdir(parents=True)
            pdf.write_bytes(b'%PDF-1.4\n')
            with patch.object(api, 'OUTPUT', output), patch.object(api, 'ROOT', root):
                with TestClient(api.app) as client:
                    self.assertEqual(client.get('/review').status_code, 200)
                    self.assertEqual(client.get('/review/app.js').status_code, 200)
                    self.assertEqual(client.get('/runs').json()['runs'][0]['run_id'], run_id)
                    base = f'/runs/{run_id}/review/TAF_G1-Q53'
                    self.assertFalse(client.get(base).json()['started'])
                    self.assertEqual(client.post(base + '/decision', json={
                        'action': 'follow_up', 'reviewer': 'Anas', 'note': 'À vérifier'
                    }).status_code, 409)
                    self.assertTrue(client.post(base + '/start').json()['waiting_for_human'])
                    source = client.get(base + '/source')
                    self.assertEqual(source.status_code, 200)
                    self.assertTrue(source.headers['content-disposition'].startswith('inline;'))
                    self.assertEqual(client.post(base + '/decision', json={
                        'action': 'approve_amount', 'reviewer': 'Anas', 'note': 'Montant approuvé'
                    }).status_code, 422)
                    result = client.post(base + '/decision', json={
                        'action': 'follow_up', 'reviewer': 'Anas', 'note': 'Contrôler la page PDF.'
                    })
                    self.assertEqual(result.status_code, 200)
                    self.assertEqual(result.json()['decision']['action'], 'follow_up')
                    self.assertEqual(len(client.get(base).json()['history']), 1)
                    self.assertEqual(client.get('/runs/' + run_id + '/review').json()['cases'][0]['decision']['action'], 'follow_up')
                    self.assertEqual(workbook.read_bytes(), b'unchanged workbook')
                api.review_workflow(str(output / 'review_graph.sqlite3')).close()
                api.review_workflow.cache_clear()
