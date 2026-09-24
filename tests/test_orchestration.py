import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from cmf.orchestration import Agent, AgentResult, Orchestrator
from cmf import pipeline

try:
    from cmf import api
except ModuleNotFoundError as exc:
    if exc.name not in ('fastapi', 'pydantic'):
        raise
    api = None


class OrchestrationTests(unittest.TestCase):
    def test_agents_receive_predecessor_results_and_emit_trace(self):
        events = []

        agents = [
            Agent('documents', (), lambda _: AgentResult({'private_value': 7}, {'documents': 1})),
            Agent('validation', ('documents',),
                  lambda results: AgentResult(results['documents']['private_value'] + 1,
                                              {'approved': True})),
        ]
        results = Orchestrator(agents, events.append).execute()

        self.assertEqual(results['validation'], 8)
        self.assertEqual([(e['agent'], e['state']) for e in events], [
            ('documents', 'running'), ('documents', 'completed'),
            ('validation', 'running'), ('validation', 'completed'),
        ])
        self.assertEqual(events[-1]['metrics'], {'approved': True})
        self.assertNotIn('private_value', str(events))

    def test_invalid_dependency_is_rejected_before_execution(self):
        with self.assertRaisesRegex(ValueError, 'Unresolved dependencies'):
            Orchestrator([Agent('review', ('workbook',), lambda _: AgentResult(None))], lambda _: None)

    def test_agent_sees_only_declared_predecessors(self):
        observed = []

        def inspect(inputs):
            observed.extend(inputs)
            return AgentResult(None)

        agents = [
            Agent('documents', (), lambda _: AgentResult(1)),
            Agent('validation', ('documents',), lambda inputs: AgentResult(inputs['documents'] + 1)),
            Agent('review', ('validation',), inspect),
        ]
        Orchestrator(agents, lambda _: None).execute()
        self.assertEqual(observed, ['validation'])

    def test_failed_agent_stops_downstream_work(self):
        events = []
        called = []

        def fail(_):
            raise ValueError('invalid document')

        def downstream(_):
            called.append(True)
            return AgentResult(None)

        agents = [Agent('documents', (), fail), Agent('workbook', ('documents',), downstream)]
        with self.assertRaisesRegex(ValueError, 'invalid document'):
            Orchestrator(agents, events.append).execute()

        self.assertEqual(called, [])
        self.assertEqual([(e['agent'], e['state']) for e in events], [
            ('documents', 'running'), ('documents', 'failed'),
        ])
        self.assertEqual(events[-1]['error_type'], 'ValueError')

    @unittest.skipIf(api is None, 'FastAPI dependency is not installed locally')
    def test_agent_endpoint_returns_compact_trace(self):
        run_id = '20260924T090000_1234abcd'
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / run_id
            folder.mkdir()
            trace = [{'agent': 'documents', 'state': 'completed', 'metrics': {'documents': 1}}]
            (folder / 'report.json').write_text(json.dumps({
                'status': 'needs_review', 'orchestration_version': 1,
                'agent_trace': trace, 'data': {'private_value': 7},
            }), encoding='utf-8')
            with patch.object(api, 'OUTPUT', Path(temp)):
                result = api.agent_status(run_id)
        self.assertEqual(result['agents'], trace)
        self.assertEqual(result['status'], 'needs_review')
        self.assertNotIn('data', result)

    def test_pipeline_stops_before_workbook_for_wrong_document(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'data'
            (root / 'templates').mkdir(parents=True)
            (root / 'templates' / 'TAF_G1_G2_G3_G4.xlsx').write_bytes(b'template')
            output = Path(temp) / 'outputs'
            config = Path(__file__).resolve().parents[1] / 'config' / 'star.json'
            with patch.object(pipeline, 'read_pages', return_value=([{'text': 'OTHER 2024'}], 'digest')), \
                 patch.object(pipeline, 'write_workbook') as writer:
                with self.assertRaisesRegex(ValueError, 'Source identity/year not confirmed'):
                    pipeline.execute(root, output, config, [2024])
                writer.assert_not_called()
            folder = next(path for path in output.iterdir() if path.is_dir())
            report = json.loads((folder / 'report.json').read_text(encoding='utf-8'))
            self.assertEqual(report['status'], 'failed')
            self.assertEqual([item['state'] for item in report['agent_trace']], ['running', 'failed'])
            self.assertFalse((folder / 'STAR_consolide.xlsx').exists())


if __name__ == '__main__':
    unittest.main()
