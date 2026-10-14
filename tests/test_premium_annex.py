import copy
import unittest

from ledger_orchestrator.extraction.premium_annex import AnnexError, annex_row, read_premiums, statement_unit

NONLIFE = {'GROUPE': ['GROUPE'], 'INCENDIE': ['INCENDIE'], 'RISQUES_DIVERS': ['RISQUES DIVERS'],
           'AUTOMOBILE': ['AUTOMOBILE', 'AUTOS'], 'ACCEPTATION': ['ACCEPTATION'], 'TOTAL': ['TOTAL']}
LIFE = {'VIE': ['VIE'], 'DECES': ['DECES'], 'TOTAL': ['TOTAL']}
TAXONOMY = dict(nonlife=dict(aliases=NONLIFE), life=dict(aliases=LIFE),
                branches=dict(GROUPE=['GROUPE'], INCENDIE=['INCENDIE'], IRDS=['RISQUES_DIVERS'],
                              AUTOMOBILE=['AUTOMOBILE']), excluded=['ACCEPTATION'])


def words(top, items):
    """items: (text, x1) pairs; each word is 30 points wide, right-aligned on x1."""
    return [dict(text=t, x0=x1 - 6 * len(t), x1=x1, top=top, bottom=top + 8) for t, x1 in items]


def row(top, label, amounts, columns):
    result = words(top, [(label, 120)])
    for amount, x1 in zip(amounts, columns):
        if amount is not None:
            result += words(top, [(part, x1 - 20 * i) for i, part in enumerate(reversed(amount.split()))])
    return result


def annex_page(page, header, amounts, title, columns):
    header_words = words(100, [('CATEGORIES', 120)])
    for text, x1 in zip(header, columns):
        parts = text.split()
        # Headers end about 10 points left of their right-aligned amounts (measured on STAR).
        header_words += words(100, [(p, x1 - 10 - 45 * (len(parts) - 1 - i)) for i, p in enumerate(parts)])
    body = header_words + row(120, 'Primes émises', amounts, columns)
    text = f'{title} 31/12/2020 CATEGORIES ' + ' '.join(header) + ' PRIMES EMISES ' + ' '.join(a or '' for a in amounts)
    return dict(page=page, width=842, height=595, method='native', text=text, words=body)


def statement_page(page, code, value, life):
    title = "Etat de résultat technique de l'assurance " + ('vie' if life else 'non-vie') + ' 31/12/2020 (en dinars)'
    body = words(120, [(code, 60)]) + words(120, [(part, 300 + 20 * i) for i, part in enumerate(value.split())])
    body += words(120, [('999', 500)])
    return dict(page=page, width=842, height=595, method='native', text=title, words=body)


COLUMNS = [200, 320, 440, 560, 680, 800]


def pages(nonlife=None, total='1 000 000', life_total='50 000'):
    nonlife = nonlife or ['400 000', '100 000', '200 000', '290 000', '10 000', '1 000 000']
    return [statement_page(4, 'PRNV11', total, False), statement_page(5, 'PRV11', life_total, True),
            annex_page(30, ['VIE', 'DECES', 'TOTAL'], ['20 000', '30 000', '50 000'],
                       'Résultat technique par catégorie Vie', COLUMNS[:3]),
            annex_page(31, ['GROUPE', 'INCENDIE', 'RISQUES DIVERS', 'AUTOMOBILE', 'ACCEPTATION', 'TOTAL'],
                       nonlife, 'Résultat technique par catégorie Non Vie', COLUMNS)]


class PremiumAnnexTests(unittest.TestCase):
    def test_reads_categories_and_proves_both_identities(self):
        records, checks = read_premiums(pages(), 2020, TAXONOMY, 3)
        self.assertEqual(records['AUTOMOBILE']['value'], 290000)
        self.assertEqual(records['TOTAL_NONVIE']['value'], 1000000)
        self.assertEqual(records['TOTAL_VIE']['value'], 50000)
        self.assertEqual(records['VIE_DECES']['value'], 30000)
        self.assertEqual({c['delta'] for c in checks}, {0})

    def test_single_blank_category_is_nil_only_by_identity(self):
        values = ['400 000', '100 000', None, '490 000', '10 000', '1 000 000']
        records, _ = read_premiums(pages(values), 2020, TAXONOMY, 3)
        self.assertEqual(records['RISQUES_DIVERS']['value'], 0)
        self.assertEqual(records['RISQUES_DIVERS']['nil_proof']['printed'], 'blank')
        values = ['400 000', None, None, '490 000', '10 000', '1 000 000']
        with self.assertRaises(AnnexError):
            read_premiums(pages(values), 2020, TAXONOMY, 3)

    def test_identity_failures_reject_the_year(self):
        cases = {
            'categories': pages(['400 000', '100 000', '200 000', '299 000', '10 000', '1 000 000']),
            'statement': pages(total='1 000 900'),
            'life statement': pages(life_total='51 000'),
        }
        for name, case in cases.items():
            with self.subTest(name), self.assertRaises(AnnexError):
                read_premiums(case, 2020, TAXONOMY, 3)

    def test_unknown_header_or_missing_unit_is_rejected(self):
        case = pages()
        case[3]['words'] = [dict(w, text='CREDIT') if w['text'] == 'INCENDIE' else w for w in case[3]['words']]
        with self.assertRaises(AnnexError):
            read_premiums(case, 2020, TAXONOMY, 3)
        case = pages()
        case[0]['text'] = case[0]['text'].replace('(en dinars)', '')     # no unit anywhere
        with self.assertRaises(AnnexError):
            read_premiums(case, 2020, TAXONOMY, 3)

    def test_thousands_convert_exactly_or_not_at_all(self):
        from ledger_orchestrator.extraction.premium_annex import exact_factor
        self.assertEqual(exact_factor('kTND', [31729.119, 10312.252]), 1000)
        with self.assertRaises(AnnexError):
            exact_factor('kTND', [31729.1195])
        case = pages()
        case[0]['text'] = case[0]['text'].replace('(en dinars)', '(en milliers de dinars)')
        records, _ = read_premiums(case, 2020, TAXONOMY, 3)
        self.assertEqual((records['TOTAL_NONVIE']['value'], records['TOTAL_NONVIE']['conversion_factor']),
                         (1000000000, 1000))

    def test_wrong_year_or_duplicate_annex_is_rejected(self):
        with self.assertRaises(AnnexError):
            read_premiums(pages(), 2021, TAXONOMY, 3)
        case = pages()
        case.append(copy.deepcopy(case[3]))
        with self.assertRaises(AnnexError):
            annex_row(case, 2020, dict(aliases=NONLIFE), life=False)

    def test_units(self):
        self.assertEqual(statement_unit('(chiffres arrondis en dinars)'), 'TND')
        self.assertEqual(statement_unit('Exprimé en milliers de dinars'), 'kTND')
        self.assertIsNone(statement_unit('no unit here'))


if __name__ == '__main__':
    unittest.main()


class LayoutVariantTests(unittest.TestCase):
    def test_typographic_minus_and_leading_dash_labels(self):
        from ledger_orchestrator.extraction.premium_annex import _row_label, _signed
        self.assertEqual([w['text'] for w in _signed([dict(text='‐50'), dict(text='‐')])], ['-50', '‐'])
        self.assertEqual(_row_label([dict(text='‐Primes'), dict(text='Emises')]), 'PRIMES EMISES')
        self.assertEqual(_row_label([dict(text='PRNV11'), dict(text='Primes')]), 'PRIMES')

    def test_note_reference_is_skipped_but_a_short_leading_group_is_kept(self):
        page = statement_page(4, 'PRNV11', '1 000 000', False)
        page['words'] += words(120, [('9.1', 200)])
        from ledger_orchestrator.extraction.premium_annex import statement_gross
        self.assertEqual(statement_gross([page], 'PRNV11', 2020)['value'], 1000000)

    def test_policy_unit_needs_no_thousands_anywhere(self):
        from ledger_orchestrator.extraction.premium_annex import _policy_unit
        policy = dict(page=9, text='Les positions comptables sont exprimées en dinar tunisien.')
        self.assertEqual(_policy_unit([policy]), ('TND', 9))
        thousands = dict(page=10, text='Tableau (en milliers de dinars)')
        self.assertEqual(_policy_unit([policy, thousands]), (None, None))

    def test_reconciliation_tables_are_not_category_annexes(self):
        case = pages()
        case[3]['text'] += ' TABLEAU DE RACCORDEMENT'
        with self.assertRaises(AnnexError):
            annex_row(case, 2020, dict(aliases=NONLIFE), life=False)


class FamilyAndUnitTests(unittest.TestCase):
    SPEC = dict(aliases={'AUTO': ['AUTO'], 'INCENDIE': ['INCENDIE'], 'RC': ['RC'], 'TOTAL': ['TOTAL']},
                families=[dict(name='f', columns=[dict(code='AUTO', expect='AUTO'), dict(code='INCENDIE', expect='INCENDIE'),
                                                  dict(code='RC', expect=None), dict(code='TOTAL', expect='TOTAL')])])

    def columns(self, texts):
        return [dict(left=100 * i, right=100 * i + 90, text=t) for i, t in enumerate(texts)]

    def test_interleaved_headers_need_one_family_with_checked_keys(self):
        from ledger_orchestrator.extraction.premium_annex import _band_labels
        labels = _band_labels(self.columns(['AUTO', 'REINCENDIE', 'SPONSABILITE', 'TOTAL']), self.SPEC)
        self.assertEqual([l['code'] for l in labels], ['AUTO', 'INCENDIE', 'RC', 'TOTAL'])
        # Interleaved texts: a swapped key column, or a wrong column count, fits no family.
        for texts in (['AUTO', 'SPONSABILITE', 'REINCENDIE', 'TOTAL'], ['AUTO', 'REINCENDIE', 'TOTAL']):
            with self.subTest(texts=texts), self.assertRaises(AnnexError):
                _band_labels(self.columns(texts), self.SPEC)

    def test_annex_unit_is_proven_by_the_statement_identity(self):
        from ledger_orchestrator.extraction.premium_annex import annex_factor
        annex = dict(unit=None, cells=dict(TOTAL=dict(value=84404.579)))
        self.assertEqual(annex_factor(annex, [84404.579], 84404579, 3), 1000)
        annex = dict(unit=None, cells=dict(TOTAL=dict(value=84404579)))
        self.assertEqual(annex_factor(annex, [84404579], 84404579, 3), 1)
        with self.assertRaises(AnnexError):        # matches in no unit
            annex_factor(dict(unit=None, cells=dict(TOTAL=dict(value=84404.0))), [84404.0], 84404579, 3)
        with self.assertRaises(AnnexError):        # a declared unit must agree
            annex_factor(dict(unit='TND', cells=dict(TOTAL=dict(value=84404.579))), [84404.579], 84404579, 3)
