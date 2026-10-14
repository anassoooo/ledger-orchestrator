"""Synthetic public fixtures; no confidential PDF values are committed."""
import copy
import unittest
from types import SimpleNamespace

from ledger_orchestrator.extraction.adapters import get_extractor
from ledger_orchestrator.extraction.astree_candidate import (
    ASSET_CODES, LIABILITY_CODES, PREMIUM_LABELS, amount, extract_candidate)


def word(text, x, y):
    return dict(text=text, x0=x-2, x1=x+2, top=y, bottom=y+5)


def fixture(year=2025):
    pages = [dict(page=1, width=595.22, height=842, method='native',
                  text=f'ASTREE Etats financiers individuels {year}', words=[])]
    for page_no, codes, asset in ((2,ASSET_CODES,True),(3,LIABILITY_CODES,False)):
        words = [word(str(year),430,70),word(str(year-1),520,70)]
        if asset:
            words.append(word('Net',455,115 if year==2024 else 90))
        labels = dict(TOTAL_ASSET="Total de l'actif", EQUITY_BEFORE='Total capitaux propres avant résultat',
                      EQUITY='Total capitaux propres avant affectation',
                      TOTAL_EQUITY_LIABILITY='Total des capitaux propres et du passif')
        for i,code in enumerate(sorted(codes)):
            label = labels.get(code, code.replace('_',','))
            y = 120+i*12
            words.extend([word(label,100,y), word('0',465 if asset else 476,y),word('0',530,y)])
        title = 'Actif du bilan' if asset else 'Capitaux propres et passif du Bilan'
        pages.append(dict(page=page_no,width=595.22,height=842,method='native',
                          text=f'Chiffres en dinars tunisiens {title}',words=words))
    x = {2023:283,2024:305,2025:330}[year]
    words = [word('Branche',100,100),word(f'31/12/{year}',x,100),word(f'31/12/{year-1}',460,100)]
    labels = PREMIUM_LABELS + (['Primes acceptées'] if year==2025 else [])
    for i,label in enumerate(labels):
        words.extend([word(label,100,120+i*12),word('1',x,120+i*12)])
    words.append(word(str(len(labels)),x,120+len(labels)*12))
    basis = 'y compris acceptation' if year==2025 else 'hors acceptation'
    pages.append(dict(page=13 if year==2025 else 12,width=595.22,height=842,method='native',
                      text=f'Situation comparative des primes émises {year} en DT {basis}',words=words))
    return pages


class AstreeCandidateTests(unittest.TestCase):
    def extract(self,pages,year=2025):
        return extract_candidate(pages,year,f'sources/ASTREE/{year}.pdf')

    def test_three_layouts_keep_native_taxonomy_and_unapproved_evidence(self):
        for year in (2023,2024,2025):
            with self.subTest(year=year):
                data=self.extract(fixture(year),year)
                self.assertEqual(len(data['asset']),44)
                self.assertEqual(len(data['liability']),33)
                self.assertEqual(len(data['premiums']['rows']),17 if year==2025 else 16)
                self.assertFalse(data['production_enabled'])
                for row in data['asset']+data['liability']+data['premiums']['rows']:
                    self.assertFalse(row['approved'])
                    self.assertEqual(row['source'],f'sources/ASTREE/{year}.pdf')
                    self.assertEqual(len(row['bbox']),4)

    def test_published_zero_and_blank_are_distinct(self):
        pages=fixture()
        # AC550 has a known optional blank disclosure; no imputed zero.
        row=next(w for w in pages[1]['words'] if w['text']=='AC550')
        pages[1]['words']=[w for w in pages[1]['words'] if not(w['top']==row['top'] and 440<w['x0']<500)]
        data=self.extract(pages)
        self.assertIsNone(next(r['value'] for r in data['asset'] if r['code']=='AC550'))
        self.assertEqual(next(r['value'] for r in data['liability'] if r['code']=='PA360'),0)

    def test_rejects_unqualified_year_and_wrong_source(self):
        for year in (2011,2022,2026,True):
            with self.subTest(year=year),self.assertRaisesRegex(ValueError,'exercise'):
                self.extract(fixture(),year)
        with self.assertRaisesRegex(ValueError,'source'):
            extract_candidate(fixture(),2025,'sources/STAR/2025.pdf')

    def test_rejects_wrong_identity_consolidation_units_geometry_and_ocr(self):
        mutations=[lambda p:p[0].update(text='STAR 2025'),
                   lambda p:p[0].update(text='ASTREE 2025 comptes consolidés'),
                   lambda p:p[1].update(text=p[1]['text'].replace('dinars','milliers de dinars')),
                   lambda p:p[1].update(text=p[1]['text'].replace('tunisiens','autres')),
                   lambda p:p[-1].update(text=p[-1]['text']+' milliers de DT'),
                   lambda p:p[1].update(width=800),lambda p:p[1].update(method='ocr')]
        for mutate in mutations:
            pages=fixture();mutate(pages)
            with self.subTest(mutation=mutate),self.assertRaises(ValueError):self.extract(pages)

    def test_rejects_swapped_year_columns(self):
        for index in (1,2,3):
            pages=fixture()
            for w in pages[index]['words']:
                if '2025' in w['text']:w['text']=w['text'].replace('2025','2024')
                elif '2024' in w['text']:w['text']=w['text'].replace('2024','2025')
            with self.subTest(index=index),self.assertRaises(ValueError):self.extract(pages)

    def test_rejects_missing_net_header_rows_and_duplicate_codes(self):
        for mode in ('net','missing','duplicate'):
            pages=fixture();words=pages[1]['words']
            if mode=='net':words[:]=[w for w in words if w['text']!='Net']
            else:
                row=next(w for w in words if w['text']=='AC14')
                if mode=='missing':words[:]=[w for w in words if w['top']!=row['top']]
                else:
                    for w in copy.deepcopy([w for w in words if w['top']==row['top']]):
                        w['top']+=650;w['bottom']+=650;words.append(w)
            with self.subTest(mode=mode),self.assertRaises(ValueError):self.extract(pages)

    def test_rejects_changed_premium_basis_branch_or_total(self):
        for mode in ('basis','branch','total'):
            pages=fixture();page=pages[-1]
            if mode=='basis':page['text']=page['text'].replace('y compris','hors')
            elif mode=='branch':next(w for w in page['words'] if w['text']=='Maladie')['text']='Other'
            else:page['words'][-1]['text']='99'
            with self.subTest(mode=mode),self.assertRaises(ValueError):self.extract(pages)

    def test_ambiguous_amount_rejected(self):
        with self.assertRaises(ValueError):amount([word('?',465,120)],440,500)

    def test_production_registry_stays_closed_even_if_status_is_changed(self):
        profile=SimpleNamespace(config=dict(company='ASTREE',extractor='astree_individual_v1',status='validated'))
        with self.assertRaisesRegex(ValueError,'No qualified extractor'):
            get_extractor(profile,[2023,2024,2025])
