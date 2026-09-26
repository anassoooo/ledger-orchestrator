import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ledger_orchestrator.copilot import ABSTENTION, LocalModelUnavailable, ReadOnlyCopilot, local_model_settings
from ledger_orchestrator.gateway import ALLOWED_PATH


def sample_report():
    return {
        'status': 'needs_review', 'company': 'STAR', 'years': [2025], 'target_unit': 'TND',
        'writes': [], 'issues': [{'type': 'not_found', 'year': 2025, 'code': 'AC11'}],
        'review': [{'code': 'AC11'}],
        'coverage': {'summary': [{'year': 2025, 'sheet': 'TAF_G1', 'expected_cells': 81,
                                  'counts': {'populated_this_run': 58}}]},
        'data': {'2025': {'records': {'AC11': {
            'code': 'AC11', 'year': 2025, 'value': 123, 'source': 'sources/STAR/2025.pdf',
            'page': 2, 'source_label': 'AC11 123', 'approved': False,
        }}, 'raw_branches': {}}},
    }


CASE = {'year': 2025, 'sheet': 'TAF_G1', 'cell': 'Q53', 'code': 'AC11',
        'category': 'preuve_insuffisante', 'reason': 'Contrôle insuffisant',
        'action': 'Vérifier le PDF', 'source': 'sources/STAR/2025.pdf',
        'page': 2, 'dependencies': [], 'issue_types': ['not_found']}


class CopilotTests(unittest.TestCase):
    def test_local_endpoint_only(self):
        with patch.dict('os.environ', {'CMF_LLM_MODEL': 'local-model',
                                       'CMF_LLM_URL': 'https://example.com'}, clear=False):
            with self.assertRaises(ValueError):
                local_model_settings()
        with patch.dict('os.environ', {'CMF_LLM_MODEL': 'local-model',
                                       'CMF_LLM_URL': 'http://ollama:11434'}, clear=False):
            self.assertEqual(local_model_settings(), ('local-model', 'http://ollama:11434'))
        with patch.dict('os.environ', {'CMF_LLM_MODEL': 'remote:cloud',
                                       'CMF_LLM_URL': 'http://ollama:11434'}, clear=False):
            with self.assertRaises(ValueError):
                local_model_settings()

    def test_grounded_answer_and_no_unrelated_pdf_content(self):
        seen = {}

        def fake_transport(url, payload):
            seen['url'], seen['payload'] = url, payload
            return {'answer': 'La preuve est insuffisante pour AC11.',
                    'citation_ids': ['case', 'record'], 'insufficient_evidence': False}

        with patch.dict('os.environ', {'CMF_LLM_MODEL': 'local-model',
                                       'CMF_LLM_URL': 'http://ollama:11434'}, clear=False):
            result = ReadOnlyCopilot(fake_transport).answer(sample_report(), 'Pourquoi AC11 ?', CASE)
        self.assertFalse(result['abstained'])
        self.assertEqual([c['id'] for c in result['citations']], ['case', 'record'])
        self.assertEqual(seen['url'], 'http://ollama:11434')
        self.assertNotIn('tools', seen['payload'])
        prompt = json.loads(seen['payload']['messages'][1]['content'])
        self.assertEqual(prompt['question'], 'Pourquoi AC11 ?')
        self.assertEqual({f['id'] for f in prompt['facts']},
                         {'run', 'coverage', 'issue_types', 'case', 'issue_1', 'record'})

    def test_invalid_citation_or_unstructured_output_is_rejected(self):
        with patch.dict('os.environ', {'CMF_LLM_MODEL': 'local-model'}, clear=False):
            for response in (
                {'answer': 'Fausse preuve', 'citation_ids': ['web'], 'insufficient_evidence': False},
                {'answer': 'Fausse preuve', 'citation_ids': 'run', 'insufficient_evidence': False},
            ):
                with self.subTest(response=response):
                    with self.assertRaises(LocalModelUnavailable):
                        ReadOnlyCopilot(lambda *_: response).answer(sample_report(), 'Question valide')

    def test_abstains_without_citation(self):
        with patch.dict('os.environ', {'CMF_LLM_MODEL': 'local-model'}, clear=False):
            result = ReadOnlyCopilot(lambda *_: {'answer': 'Une affirmation sans preuve',
                'citation_ids': [], 'insufficient_evidence': False}).answer(sample_report(), 'Question valide')
        self.assertTrue(result['abstained'])
        self.assertEqual(result['answer'], ABSTENTION)

    def test_local_ollama_transport_checks_installed_model_first(self):
        calls = []
        testcase = self

        class Response:
            def __init__(self, body):
                self.body = body

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self, _limit):
                return self.body

        class Opener:
            def open(self, request, timeout):
                calls.append((request.full_url, timeout))
                if request.full_url.endswith('/api/tags'):
                    return Response(b'{"models":[{"name":"local-model"}]}')
                self_payload = json.loads(request.data)
                testcase.assertEqual(self_payload['model'], 'local-model')
                return Response(json.dumps({'message': {'content': json.dumps({
                    'answer': 'Le run demande une revue.', 'citation_ids': ['run'],
                    'insufficient_evidence': False,
                })}}).encode('utf-8'))

        with patch.dict('os.environ', {'CMF_LLM_MODEL': 'local-model',
                                       'CMF_LLM_URL': 'http://ollama:11434'}, clear=False), \
             patch('ledger_orchestrator.copilot.build_opener', return_value=Opener()):
            result = ReadOnlyCopilot().answer(sample_report(), 'Quel est le statut ?')
        self.assertEqual(result['citations'][0]['id'], 'run')
        self.assertEqual([url.rsplit('/', 1)[-1] for url, _ in calls], ['tags', 'chat'])

    def test_gateway_routes(self):
        run = '/runs/20260924T074936_4a5f2ea5'
        self.assertIsNotNone(ALLOWED_PATH.fullmatch('/copilot/status'))
        self.assertIsNotNone(ALLOWED_PATH.fullmatch(run + '/copilot'))
        self.assertIsNone(ALLOWED_PATH.fullmatch(run + '/copilot/../../secrets'))

    def test_api_copilot_is_read_only(self):
        try:
            from fastapi.testclient import TestClient
            from ledger_orchestrator import api
        except ImportError:
            self.skipTest('FastAPI TestClient is unavailable')
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            run_id = '20260924T074936_4a5f2ea5'
            folder = output / run_id
            folder.mkdir()
            report = sample_report()
            report['review'] = [CASE]
            report_bytes = json.dumps(report).encode('utf-8')
            (folder / 'report.json').write_bytes(report_bytes)
            (folder / 'STAR_consolide.xlsx').write_bytes(b'unchanged workbook')
            with patch.object(api, 'OUTPUT', output), patch.dict('os.environ', {'CMF_LLM_MODEL': ''}, clear=False):
                with TestClient(api.app) as client:
                    self.assertFalse(client.get('/copilot/status').json()['enabled'])
                    detail = client.get(f'/runs/{run_id}/review/TAF_G1-Q53').json()
                    self.assertEqual({item['id'] for item in detail['evidence']}, {'issue_1', 'record'})
                    self.assertEqual(client.post(f'/runs/{run_id}/copilot', json={
                        'question': 'Pourquoi ce dossier ?', 'case_id': 'TAF_G1-Q53',
                    }).status_code, 503)
                    self.assertEqual(client.post(f'/runs/{run_id}/copilot', json={
                        'question': 'Pourquoi ce dossier ?', 'case_id': 'TAF_G1-Z999',
                    }).status_code, 404)
                    with api.COPILOT_LOCK:
                        self.assertEqual(client.post(f'/runs/{run_id}/copilot', json={
                            'question': 'Pourquoi ce dossier ?', 'case_id': 'TAF_G1-Q53',
                        }).status_code, 409)
                    with patch.object(api, 'copilot_graph') as copilot:
                        copilot.return_value.answer.return_value = {
                            'answer': 'Dossier bloqué.', 'citations': [], 'abstained': False}
                        response = client.post(f'/runs/{run_id}/copilot', json={
                            'question': 'Pourquoi ce dossier ?', 'case_id': 'TAF_G1-Q53',
                        })
                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(copilot.return_value.answer.call_args.args[2]['code'], 'AC11')
            self.assertEqual((folder / 'report.json').read_bytes(), report_bytes)
            self.assertEqual((folder / 'STAR_consolide.xlsx').read_bytes(), b'unchanged workbook')


if __name__ == '__main__':
    unittest.main()
