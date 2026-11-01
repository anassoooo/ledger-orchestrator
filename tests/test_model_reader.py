"""Model reader agent loop, recorder and provider client, with a scripted fake provider (no network)."""
import json
import re
from pathlib import Path
import tempfile
import unittest
import unittest.mock

from ledger_orchestrator.evaluation.model_reader import (CallRecorder, ChatClient, ModelReader, ProviderError,
                                                         ReplayMissing, ScopedModelReader, api_key, fit_context,
                                                         locate_annexes, page_rows)
from test_harness import NONLIFE, TAXONOMY, WIDTH, document, proposals, row_words

CONFIG = dict(taxonomy=TAXONOMY, rounding_tolerance_tnd=3)
TASK = dict(task_id='example:2020', profile_id='example', company='EXAMPLE', year=2020)
SECRET = 'gsk_secret_value_never_logged'


def tool_call(name, arguments, index):
    return dict(id=f'call_{index}', type='function', function=dict(name=name, arguments=json.dumps(arguments)))


def reply(*calls, content=None, prompt=100, completion=20):
    return dict(choices=[dict(message=dict(role='assistant', content=content, tool_calls=list(calls) or None))],
                usage=dict(prompt_tokens=prompt, completion_tokens=completion))


class ScriptedProvider:
    """Returns the scripted replies in order and keeps every request it received."""

    def __init__(self, replies, statuses=None):
        self.replies, self.statuses = list(replies), list(statuses or [])
        self.requests = []

    def __call__(self, url, payload, headers):
        # Snapshot: the agent keeps appending to the same message list.
        self.requests.append(json.loads(json.dumps(dict(url=url, payload=payload, headers=headers))))
        if self.statuses:
            status, extra = self.statuses.pop(0)
            return status, extra, b'{"error": "rate limited"}'
        return 200, {}, json.dumps(self.replies.pop(0)).encode('utf-8')


def good_conversation():
    answer = proposals()
    return [reply(tool_call('search_pages', dict(query='résultat technique catégorie'), 1)),
            reply(tool_call('read_page', dict(page=1), 2)),
            reply(tool_call('check', dict(proposals=answer), 3)),
            reply(tool_call('submit', dict(proposals=answer), 4))]


class ModelReaderTests(unittest.TestCase):
    def reader(self, transport, folder, mode='record'):
        client = ChatClient('groq', 'example-model', key=SECRET, transport=transport, sleep=lambda s: None)
        return ModelReader(client, CallRecorder(folder, mode))

    def test_agent_reads_checks_and_submits_then_replays_offline(self):
        with tempfile.TemporaryDirectory() as temp:
            provider = ScriptedProvider(good_conversation())
            reading = self.reader(provider, temp).read(TASK, document(), CONFIG)
            self.assertIsNone(reading.abstained)
            self.assertEqual(reading.proposals['AUTO'], dict(value=str(NONLIFE['AUTO']), page=1))
            self.assertEqual((reading.usage['calls'], reading.usage['recorded']), (4, 0))
            self.assertEqual(reading.usage['input_tokens'], 400)
            # Tool results reached the model: the page layout and the gate's verdict.
            last = provider.requests[-1]['payload']['messages']
            self.assertRegex(next(m['content'] for m in last if m.get('tool_call_id') == 'call_2'), r'Primes\s+émises')
            self.assertIn('"admitted": true', next(m['content'] for m in last if m.get('tool_call_id') == 'call_3'))
            recordings = list(Path(temp).glob('*.json'))
            self.assertEqual(len(recordings), 4)
            self.assertNotIn(SECRET, ''.join(p.read_text(encoding='utf-8') for p in recordings))

            def offline(*_):
                raise AssertionError('replay must not call the provider')
            replayed = self.reader(offline, temp, 'replay').read(TASK, document(), CONFIG)
            self.assertEqual(replayed.proposals, reading.proposals)
            self.assertEqual(replayed.usage['recorded'], 4)

    def test_replay_without_recording_fails_loudly(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ReplayMissing):
                self.reader(ScriptedProvider([]), temp, 'replay').read(TASK, document(), CONFIG)

    def test_check_tool_returns_the_gate_reasons(self):
        swapped = proposals()
        swapped['INC'], swapped['TR'] = swapped['TR'], swapped['INC']
        script = [reply(tool_call('check', dict(proposals=swapped), 1)),
                  reply(tool_call('abstain', dict(reason='headers disagree'), 2))]
        with tempfile.TemporaryDirectory() as temp:
            provider = ScriptedProvider(script)
            reading = self.reader(provider, temp).read(TASK, document(), CONFIG)
        verdict = json.loads(provider.requests[-1]['payload']['messages'][-1]['content'])
        self.assertFalse(verdict['decisions']['INC']['admitted'])
        self.assertIn('printed under TRANSPORT', ' '.join(verdict['decisions']['INC']['reasons']))
        self.assertEqual(reading.abstained, 'model: headers disagree')

    def test_malformed_proposals_are_dropped_not_guessed(self):
        submitted = dict(AUTO=dict(value='1 200 000', page=1), INVENTED=dict(value='5', page=1),
                         INC=dict(value='three hundred', page=1), TR=dict(value='150000', page='1'))
        with tempfile.TemporaryDirectory() as temp:
            reading = self.reader(ScriptedProvider([reply(tool_call('submit', dict(proposals=submitted), 1))]),
                                  temp).read(TASK, document(), CONFIG)
        self.assertEqual(reading.proposals, dict(AUTO=dict(value='1200000', page=1)))

    def test_text_answers_are_nudged_and_the_turn_budget_ends_in_abstention(self):
        with tempfile.TemporaryDirectory() as temp:
            client = ChatClient('groq', 'example-model', key=SECRET, sleep=lambda s: None,
                                transport=ScriptedProvider([reply(content=f'thinking {i}') for i in range(3)]))
            reading = ModelReader(client, CallRecorder(temp), max_turns=3).read(TASK, document(), CONFIG)
        self.assertEqual(reading.abstained, 'turn budget exhausted')
        self.assertEqual(reading.usage['calls'], 3)

    def test_rate_limits_wait_then_succeed_and_errors_never_echo_the_key(self):
        waits = []
        provider = ScriptedProvider([reply(tool_call('abstain', dict(reason='x'), 1))],
                                    statuses=[(429, {'Retry-After': '7'})])
        client = ChatClient('groq', 'example-model', key=SECRET, transport=provider, sleep=waits.append,
                            min_interval=0)
        self.assertIn('choices', client.complete(dict(model='example-model', messages=[])))
        self.assertEqual(waits, [7.0])
        failing = ChatClient('groq', 'example-model', key=SECRET, sleep=lambda s: None, min_interval=0,
                             transport=lambda url, payload, headers: (401, {}, b'{"error": "invalid api key"}'))
        with self.assertRaises(ProviderError) as caught:
            failing.complete(dict(model='example-model', messages=[]))
        self.assertIn('HTTP 401', str(caught.exception))
        self.assertNotIn(SECRET, str(caught.exception))
        with tempfile.TemporaryDirectory() as temp:
            reading = ModelReader(failing, CallRecorder(temp)).read(TASK, document(), CONFIG)
        self.assertTrue(reading.abstained.startswith('provider error: HTTP 401'))

    def test_key_comes_from_environment_or_ignored_env_file(self):
        with tempfile.TemporaryDirectory() as temp:
            env = Path(temp) / '.env'
            with unittest.mock.patch.dict('os.environ', {'GROQ_API_KEY': ''}):
                with self.assertRaises(ProviderError):
                    api_key('groq', env)
                env.write_text('OTHER=1\nGROQ_API_KEY="from-file"\n', encoding='utf-8')
                self.assertEqual(api_key('groq', env), 'from-file')
            with unittest.mock.patch.dict('os.environ', {'GROQ_API_KEY': 'from-env'}):
                self.assertEqual(api_key('groq', env), 'from-env')
        with self.assertRaises(ValueError):
            ChatClient('groq', 'bad model id;rm')

    def test_contents_and_ranked_search_guide_navigation(self):
        script = [reply(tool_call('search_pages', dict(query='Annexe 13 résultat technique catégorie'), 1)),
                  reply(tool_call('search_pages', dict(query='GRELE'), 2)),
                  reply(tool_call('find_rows', dict(page=1, words='automobile émises'), 3)),
                  reply(tool_call('abstain', dict(reason='x'), 4))]
        with tempfile.TemporaryDirectory() as temp:
            provider = ScriptedProvider(script)
            self.reader(provider, temp).read(TASK, document(), CONFIG)
        messages = provider.requests[-1]['payload']['messages']
        self.assertRegex(messages[1]['content'], r'p1: \S')
        ranked = json.loads(next(m['content'] for m in messages if m.get('tool_call_id') == 'call_1'))
        # "Annexe 13" is not printed, yet the annex page still ranks first on the words it shares.
        self.assertEqual(ranked[0]['page'], 1)
        self.assertEqual(next(m['content'] for m in messages if m.get('tool_call_id') == 'call_2'), 'no page matches')
        # find_rows keeps the header and the amount row, aligned as on the full page, and nothing else.
        found = next(m['content'] for m in messages if m.get('tool_call_id') == 'call_3').splitlines()[1:]
        full = page_rows(document()[0])
        self.assertTrue(found and all(line[4:] in full for line in found))
        self.assertTrue(any('AUTOMOBILE' in line for line in found) and any('émises' in line for line in found))
        self.assertFalse(any('acquises' in line for line in found))

    def test_context_budget_elides_oldest_page_reads_but_keeps_notes(self):
        messages = [dict(role='system', content='s' * 500), dict(role='user', content='u' * 500)]
        for i in range(4):
            messages.append(dict(role='assistant', tool_calls=[tool_call('read_page', dict(page=i), i)]))
            messages.append(dict(role='tool', tool_call_id=f'call_{i}', content='x' * 3000))
        messages.append(dict(role='assistant', tool_calls=[tool_call('check', dict(proposals=proposals()), 9)]))
        self.assertEqual(fit_context(messages, budget=9000, keep=2), 2)
        tools = [m['content'] for m in messages if m['role'] == 'tool']
        self.assertTrue(tools[0].startswith('[elided') and '"page": 0' in tools[0])
        self.assertEqual(tools[2:], ['x' * 3000] * 2)
        self.assertEqual(fit_context(messages, budget=9000, keep=2), 0)   # idempotent once it fits
        self.assertIn('AUTO', json.dumps(messages[-1]['tool_calls']))     # the model's notes survive
        verdict = '{"decisions": {"AUTO": {"admitted": false, "reasons": ["' + 'r' * 3000 + '"]}}}'
        messages.append(dict(role='tool', tool_call_id='call_9', content=verdict))
        messages += [dict(role='assistant', tool_calls=[tool_call('read_page', dict(page=5), 10 + i)]) for i in range(1)]
        messages += [dict(role='tool', tool_call_id='call_10', content='y' * 3000),
                     dict(role='assistant', tool_calls=[tool_call('read_page', dict(page=6), 11)]),
                     dict(role='tool', tool_call_id='call_11', content='z' * 3000)]
        fit_context(messages, budget=1000, keep=2)
        self.assertIn(verdict, [m.get('content') for m in messages])     # the gate's feedback is never elided

    def test_page_layout_keeps_columns_and_blanks_aligned(self):
        rows = page_rows(document()[0])
        header = rows[1]
        issued = next(r for r in rows if re.match(r'\s*Primes\s+émises', r))
        acquired = next(r for r in rows if re.match(r'\s*Primes\s+acquises', r))
        # Each amount ends at the same position on every row, under its header.
        self.assertEqual([m.end() for m in re.finditer(r'\d(?=\s{2,}|$)', issued)],
                         [m.end() for m in re.finditer(r'\d(?=\s{2,}|$)', acquired)])
        self.assertLessEqual(abs(header.index('AUTOMOBILE') - issued.index('1 200')), 3)
        self.assertLessEqual(abs(header.index('TRANSPORT') - issued.index('150')), 3)


def titled_statement(number, title, label, amounts):
    words = row_words(10, title, []) + row_words(25, label, [(300 + 80 * i, v) for i, v in enumerate(amounts)])
    return dict(page=number, width=WIDTH, height=800, method='native', words=words,
                text=title + '\n' + label + ' ' + ' '.join(f'{v:,}'.replace(',', ' ') for v in amounts))


class ScopedReaderTests(unittest.TestCase):
    def reader(self, transport, folder):
        client = ChatClient('groq', 'example-model', key=SECRET, transport=transport, sleep=lambda s: None)
        return ScopedModelReader(client, CallRecorder(folder))

    def test_locator_finds_annexes_statements_and_printing_variants(self):
        pages = document() + [
            titled_statement(5, "Etat de résultat technique vie", 'PRV11PRIMES émises et acceptées', [700, 9]),
            titled_statement(6, "Résultat technique par catégorie d'assurance non vie", '‐PRIMES EMISES', [5]),
            titled_statement(7, 'Ventilation des primes par zone', 'Primes émises', [5])]
        found = {page['page']: label for page, label, _, _ in locate_annexes(pages)}
        self.assertEqual(found, {1: 'category annex, non-life', 3: 'category annex, life',
                                 5: 'technical statement, life', 6: 'category annex, non-life'})

    def test_scoped_reader_reads_only_the_located_excerpts_then_checks_and_submits(self):
        answer = proposals()
        script = [reply(tool_call('check', dict(proposals=answer), 1)),
                  reply(tool_call('submit', dict(proposals=answer), 2))]
        with tempfile.TemporaryDirectory() as temp:
            provider = ScriptedProvider(script)
            reading = self.reader(provider, temp).read(TASK, document(), CONFIG)
        self.assertEqual(reading.proposals, answer)
        self.assertEqual(reading.usage['calls'], 2)
        payload = provider.requests[0]['payload']
        self.assertEqual({t['function']['name'] for t in payload['tools']}, {'read_page', 'check', 'submit', 'abstain'})
        opening = payload['messages'][1]['content']
        self.assertIn('page 1 (category annex, non-life', opening)
        self.assertRegex(opening, r'Primes\s+émises')
        # The excerpt stops at the "Primes émises" row: later rows are not sent.
        self.assertNotIn('Solde', opening)

    def test_nothing_located_abstains_without_calling_the_model(self):
        def offline(*_):
            raise AssertionError('no request expected')
        with tempfile.TemporaryDirectory() as temp:
            reading = self.reader(offline, temp).read(TASK, [document()[1]], CONFIG)
        self.assertTrue(reading.abstained.startswith('no premium page located'))
        self.assertEqual(reading.usage['calls'], 0)


if __name__ == '__main__':
    unittest.main()
