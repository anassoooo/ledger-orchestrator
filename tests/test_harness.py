"""Benchmark harness: answer key, identity gate, readers and scoring, on synthetic data only."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ledger_orchestrator.evaluation import harness
from ledger_orchestrator.evaluation.answer_key import build_answer_key, load_answer_key
from ledger_orchestrator.evaluation.gate import DocumentIndex, name_band, verify_premiums
from ledger_orchestrator.evaluation.readers import PERTURBATIONS, AbstainReader, PerturbedReader, Reading

TAXONOMY = dict(branches=dict(AUTOMOBILE=['AUTO'], INCENDIE=['INC'], TRANSPORT=['TR'], IRDS=['DIV'], GROUPE=['GRP']),
                excluded=['ACC'], life=dict(aliases=dict(VIE=['VIE'], TOTAL=['TOTAL'])),
                nonlife=dict(aliases=dict(AUTO=['AUTOMOBILE'], INC=['INCENDIE'], TR=['TRANSPORT'],
                                          DIV=['RISQUES DIVERS'], GRP=['GROUPE'], ACC=['ACCEPTATION'],
                                          TOTAL=['TOTAL'])))
HEADERS = dict(AUTO='AUTOMOBILE', INC='INCENDIE', TR='TRANSPORT', DIV='RISQUES DIVERS', GRP='GROUPE',
               ACC='ACCEPTATION', TOTAL='TOTAL', VIE='VIE')
NONLIFE = dict(AUTO=1_200_000, INC=300_000, TR=150_000, DIV=250_000, GRP=80_000, ACC=20_000)
TOTAL = sum(NONLIFE.values())          # 2 000 000
LIFE = 500_000
WIDTH = 600


def row_words(top, label, cells):
    """One PDF row: a label, then amounts right-aligned on column edges, split at thousands."""
    result, x = [], 10.0
    for token in label.split():
        result.append(dict(text=token, x0=x, x1=x + 5 * len(token), top=top, bottom=top + 8))
        x += 5 * len(token) + 3
    for right, value in cells:
        if value is None:
            continue
        parts = ['-'] if value == '-' else f'{value:,}'.split(',')
        x = right
        for part in reversed(parts):
            result.append(dict(text=part, x0=x - 5 * len(part), x1=x, top=top, bottom=top + 8))
            x -= 5 * len(part) + 2
    return result


def annex(number, title, columns, issued, earned):
    """Category annex: title, header row, then numeric rows (the gate clusters column edges over them)."""
    rights = [160 + 60 * i for i in range(len(columns))]
    words, lines_ = [], []
    words += row_words(20, title, [])
    for right, code in zip(rights, columns):
        for k, token in enumerate(HEADERS[code].split()):
            words.append(dict(text=token, x0=right - 40, x1=right - 40 + 5 * len(token), top=40 + 8 * k,
                              bottom=48 + 8 * k))
    rows = [('Primes acquises', earned), ('Primes émises', issued),
            ('Charges de prestations', [7_777] * len(columns)), ('Solde de souscription', [8_888] * len(columns))]
    for i, (label, values) in enumerate(rows):
        words += row_words(80 + 15 * i, label, list(zip(rights, values)))
    text = '\n'.join([title, ' '.join(HEADERS[c] for c in columns)] +
                     [label + ' ' + ' '.join('-' if v == '-' else f'{v:,}'.replace(',', ' ') for v in values)
                      for label, values in rows])
    return dict(page=number, width=WIDTH, height=800, words=words, text=text, method='native')


def statement(number, code, amounts):
    text = f'{code} Primes émises ' + ' '.join(f'{v:,}'.replace(',', ' ') for v in amounts)
    return dict(page=number, width=WIDTH, height=800, method='native', text=text,
                words=row_words(20, f'{code} Primes émises', [(300 + 80 * i, v) for i, v in enumerate(amounts)]))


def document(nonlife=NONLIFE, total=TOTAL, life=LIFE, earned=None):
    issued = ['-' if v == 0 else v for v in nonlife.values()] + [total]
    earned = earned or [v + 1_000 for v in [*nonlife.values(), total]]
    return [annex(1, 'Résultat technique par catégorie non vie', [*nonlife, 'TOTAL'], issued, earned),
            statement(2, 'PRNV11', [total, -100, total - 100]),
            annex(3, 'Résultat technique par catégorie vie', ['VIE', 'TOTAL'], [life, life], [life + 9, life + 9]),
            statement(4, 'PRV11', [life])]


def proposals(nonlife=NONLIFE, total=TOTAL, life=LIFE):
    result = {code: dict(value=str(v), page=1) for code, v in nonlife.items()}
    result['TOTAL_NONVIE'] = dict(value=str(total), page=1)
    result['VIE_VIE'] = dict(value=str(life), page=3)
    result['TOTAL_VIE'] = dict(value=str(life), page=3)
    return result


def verify(props, pages=None):
    return verify_premiums(props, DocumentIndex(pages or document()), TAXONOMY, 3)['decisions']


class AmountMatchingTests(unittest.TestCase):
    def test_amounts_need_boundaries_and_sign(self):
        index = DocumentIndex([dict(page=1, text='31 661 853 2 841 470 Total 84 404,579 (50) -12 net '
                                                 '792,871 873,860 51 708 692 5 452 061 344 074')])
        for value, units in [(31661853, ['TND']), (1661853, []), (661853, []), (2841470, ['TND']),
                             (84404579, ['kTND']), (84404, []), (-50, ['TND']), (50, []), (-12, ['TND']),
                             (12, []), (873860, ['kTND']), (871873, []),
                             # Ambiguous run-together amounts are not matched (safe direction).
                             (5452061, [])]:
            self.assertEqual(index.units_on(value, 1), units, value)

    def test_geometry_separates_columns_the_text_cannot(self):
        page = dict(page=1, width=WIDTH, text='Primes 1 996 280 298 820 201',
                    words=row_words(20, 'Primes', [(200, 1_996_280), (300, 298_820_201)]))
        index = DocumentIndex([page])
        self.assertEqual(index.units_on(298820201, 1), ['TND'])
        self.assertEqual(index.units_on(280298, 1), [])

    def test_headers_name_codes_by_alias_then_by_distinctive_word(self):
        aliases = dict(A_TRAVAIL=['A T'], PERTE=["PERTE D'EXPLOITATION"], AUTO=['AUTO'], AUTOMOBILE=['AUTOMOBILE'],
                       RC_DECENNALE=['RESPONSABILITE DECENNALE'], RC_CIVILE=['RESPONSABILITE CIVILE'])
        self.assertEqual(name_band('PERTEDEXPLOITATION', aliases), ['PERTE'])     # "AT" inside it does not count
        self.assertEqual(name_band('AUTOMOBILE', aliases), ['AUTOMOBILE'])
        self.assertEqual(name_band('RESPOSABILITEDECENNALE', aliases), ['RC_DECENNALE'])   # typo in the PDF
        self.assertEqual(name_band('RESPONSABILITERESP', aliases), ['RC_CIVILE', 'RC_DECENNALE'])
        self.assertEqual(name_band('ELEMENTS', aliases), [])


class GateTests(unittest.TestCase):
    def test_correct_reading_is_admitted(self):
        decisions = verify(proposals())
        self.assertTrue(all(d['admitted'] for d in decisions.values()), decisions)

    def test_wrong_amounts_are_rejected_with_reasons(self):
        for change in (dict(INC=300_010), dict(INC=300_000_000), dict(INC=0)):
            props = proposals()
            props.update({c: dict(value=str(v), page=1) for c, v in change.items()})
            decisions = verify(props)
            self.assertFalse(any(decisions[c]['admitted'] for c in [*NONLIFE, 'TOTAL_NONVIE']), change)
            self.assertTrue(decisions['TOTAL_VIE']['admitted'], 'the life scope is judged on its own')

    def test_total_must_be_printed_twice(self):
        pages = document()
        pages[1] = statement(2, 'PRNV11', [])
        decisions = verify(proposals(), pages)
        self.assertFalse(decisions['TOTAL_NONVIE']['admitted'])
        self.assertIn('two required', ' '.join(decisions['TOTAL_NONVIE']['reasons']))

    def test_second_printing_may_differ_by_rounding_only(self):
        pages = document()
        pages[1] = statement(2, 'PRNV11', [TOTAL - 1])
        self.assertTrue(verify(proposals(), pages)['TOTAL_NONVIE']['admitted'])
        pages[1] = statement(2, 'PRNV11', [TOTAL - 4])
        self.assertFalse(verify(proposals(), pages)['TOTAL_NONVIE']['admitted'])

    def test_zeros_are_proven_only_within_one_branch(self):
        nonlife = dict(NONLIFE, TR=0, DIV=400_000)          # Transport printed as a dash
        pages = document(nonlife)
        self.assertTrue(verify(proposals(nonlife), pages)['TR']['admitted'])
        nonlife = dict(NONLIFE, TR=0, GRP=0, DIV=480_000)   # two dashes in two branches
        decisions = verify(proposals(nonlife), document(nonlife))
        self.assertFalse(decisions['TR']['admitted'])
        self.assertIn('D-002', ' '.join(decisions['TR']['reasons']))

    def test_unknown_codes_and_missing_totals_are_never_admitted(self):
        props = proposals()
        props['MYSTERY'] = dict(value='300000', page=1)
        del props['TOTAL_NONVIE']
        decisions = verify(props)
        self.assertFalse(decisions['MYSTERY']['admitted'])
        self.assertFalse(decisions['AUTO']['admitted'])

    def test_category_swap_across_branches_is_rejected_by_column_headers(self):
        # Swapped columns keep every amount printed and every sum intact; only the
        # header above each amount tells them apart.
        props = proposals()
        props['INC'], props['TR'] = props['TR'], props['INC']
        decisions = verify(props)
        self.assertFalse(decisions['INC']['admitted'] or decisions['TR']['admitted'])
        self.assertIn('printed under TRANSPORT', ' '.join(decisions['INC']['reasons']))

    def test_swap_inside_one_branch_changes_no_target_and_is_not_judged(self):
        taxonomy = copy.deepcopy(TAXONOMY)
        taxonomy['branches']['IRDS'] = ['DIV', 'INC']          # both columns now feed IRDS
        del taxonomy['branches']['INCENDIE']
        props = proposals()
        props['INC'], props['DIV'] = props['DIV'], props['INC']
        decisions = verify_premiums(props, DocumentIndex(document()), taxonomy, 3)['decisions']
        self.assertTrue(decisions['INC']['admitted'] and decisions['DIV']['admitted'])

    def test_earned_premiums_row_is_not_issued_premiums(self):
        earned = [v + 1_000 for v in [*NONLIFE.values(), TOTAL]]
        earned[-1] = sum(earned[:-1])            # the earned row reconciles with its own total
        pages = document(earned=earned)
        pages[1] = statement(2, 'PRNV11', [TOTAL, earned[-1]])   # and that total is printed twice
        props = proposals(dict(zip(NONLIFE, earned)), earned[-1])
        decisions = verify(props, pages)
        self.assertFalse(decisions['AUTO']['admitted'])
        self.assertIn('not on the "Primes émises" row', ' '.join(decisions['AUTO']['reasons']))

    def test_a_category_must_be_read_on_the_category_annex(self):
        props = proposals()
        props['AUTO'] = dict(value=str(NONLIFE['AUTO']), page=2)
        pages = document()
        pages[1] = statement(2, 'PRNV11', [TOTAL, NONLIFE['AUTO']])
        decisions = verify(props, pages)
        self.assertFalse(decisions['AUTO']['admitted'])
        self.assertIn('category annex not readable on page 2', ' '.join(decisions['AUTO']['reasons']))


def history_report(run_id='20261014T030645_cc0159b6'):
    def fact(year, code, amount, approved):
        return dict(year=year, code=code, target_amount=str(amount), approved=approved,
                    evidence=dict(document_year=year, page=1, method='native', source_unit='TND'))
    facts = [fact(2020, c, v, c != 'ACC') for c, v in NONLIFE.items()]
    facts += [fact(2020, 'TOTAL_NONVIE', TOTAL, False), fact(2020, 'TOTAL_VIE', LIFE, True),
              fact(2020, 'VIE_VIE', LIFE, False), fact(2021, 'TOTAL_VIE', LIFE, True)]
    config = dict(profile_id='example_history', company='EXAMPLE', source_directory='sources/EXAMPLE',
                  taxonomy=TAXONOMY, rounding_tolerance_tnd=3)
    return dict(run_id=run_id, kind='premium_history', status='needs_review', config=config,
                profile=dict(id='example_history', sha256='0' * 64), years=[2019, 2020, 2021],
                documents={str(y): dict(sha256=str(y) * 16, pages=4) for y in (2019, 2020, 2021)},
                issues=[dict(type='premium_history_rejected', year=2019, reason='Annex total differs')],
                facts=facts)


class AnswerKeyTests(unittest.TestCase):
    def test_key_statuses_and_identity_implied_answers(self):
        key = build_answer_key([history_report()])
        tasks = {t['year']: t for t in key['tasks']}
        self.assertEqual((tasks[2019]['status'], tasks[2020]['status'], tasks[2021]['status']),
                         ('open', 'solved', 'partial'))
        self.assertEqual(tasks[2019]['reason'], 'Annex total differs')
        expected = tasks[2020]['expected']
        # Not "approved" by the pipeline, but part of the identity that admitted the year.
        self.assertEqual(expected['TOTAL_NONVIE']['admitted_by'], 'partition identity')
        self.assertEqual(expected['ACC']['admitted_by'], 'partition identity')
        self.assertEqual(expected['VIE_VIE']['admitted_by'], 'partition identity')
        self.assertEqual(expected['AUTO']['admitted_by'], 'branch identity')

    def test_frozen_key_rejects_tampering_and_other_runs(self):
        key = build_answer_key([history_report()])
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'key.json'
            path.write_text(json.dumps(key), encoding='utf-8')
            self.assertEqual(load_answer_key(path)['sha256'], key['sha256'])
            tampered = copy.deepcopy(key)
            tampered['tasks'][1]['expected']['AUTO']['amount'] = '1'
            path.write_text(json.dumps(tampered), encoding='utf-8')
            with self.assertRaises(ValueError):
                load_answer_key(path)
        with self.assertRaises(ValueError):
            build_answer_key([history_report(), history_report('20261014T030646_cc0159b7')])
        with self.assertRaises(ValueError):
            build_answer_key([dict(history_report(), kind='statements')])


class ExactReader:
    name = 'exact'

    def read(self, task, pages, config):
        if task['year'] != 2020:
            return Reading(abstained='only reads 2020')
        return Reading(proposals=proposals(), usage=dict(calls=1, input_tokens=10, output_tokens=5))


class HarnessTests(unittest.TestCase):
    def run_reader(self, reader):
        key = build_answer_key([history_report()])
        with patch.object(harness, '_load', side_effect=lambda root, cache, relative, sha=None:
                          document() if relative.endswith(('2019.pdf', '2020.pdf', '2021.pdf')) else None):
            return harness.run_reader(reader, key, Path('.'), Path('.'))

    def test_scoring_separates_correct_wrong_abstained_and_unconfirmed(self):
        result = self.run_reader(ExactReader())
        summary = result['summary']
        self.assertEqual(summary['silent_errors'], 0)
        self.assertEqual(summary['counts']['correct_admitted'], 9)
        self.assertEqual(summary['counts']['abstained'], 1)            # 2021 life total
        self.assertEqual(summary['admitted_precision'], 1.0)
        self.assertEqual(result['usage'], dict(calls=1, input_tokens=10, output_tokens=5))

    def test_abstaining_is_never_an_error(self):
        summary = self.run_reader(AbstainReader())['summary']
        self.assertEqual((summary['silent_errors'], summary['verified_recall']), (0, 0.0))

    def test_perturbations_are_injected_and_reported(self):
        for kind in PERTURBATIONS:
            if kind == 'previous_year':
                continue
            result = self.run_reader(PerturbedReader(ExactReader(), kind, seed=1))
            stats = result['perturbations'][kind]
            self.assertGreater(stats['injected'], 0, kind)
            self.assertEqual(stats['catch_rate'], 1.0, kind)
            self.assertEqual(result['summary']['silent_errors'], 0, kind)

    def test_previous_year_copy_needs_an_answer_to_copy(self):
        reading = PerturbedReader(ExactReader(), 'previous_year', {}).read(
            dict(task_id='x', profile_id='example_history', year=2020), document(), dict(taxonomy=TAXONOMY))
        self.assertEqual(reading.abstained, 'no previous-year answer to copy')
        with self.assertRaises(ValueError):
            PerturbedReader(ExactReader(), 'invented')


if __name__ == '__main__':
    unittest.main()
