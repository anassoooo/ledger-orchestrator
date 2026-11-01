"""Reader-independent identity gate for proposed premium readings (articles III, IV).

A reader (deterministic code, a local model, an API model) proposes amounts in
TND with the page it read them on. The gate never trusts the reader: it admits a
reading only when the published document itself proves it.

- Grounding: a non-zero amount must be printed on its cited page, in TND or in
  exact thousands (D-008). A zero is never "printed"; it is admitted only when
  an identity proves it, and several zeros only when they share one branch (D-002).
- Double printing: each total must be printed on at least two pages of the year's
  own document (annex and technical statement, D-007), the second one within the
  rounding tolerance (STAR 2011 prints 197 220 737 and 197 220 736).
- Identity: proposed categories must add up to their total (D-004 tolerance).
- Next year's report is recorded as evidence when available, never required:
  NC 26 technical statements print the N-1 column *net* of reinsurance only, so
  next year's report does not print year N's gross premium.

An amount is printed on a page when either of two conservative readings finds it:

- page geometry: words grouped into amounts by their horizontal gaps, the way the
  production readers separate columns (``numeric_groups``);
- page text, for annexes whose PDF glues adjacent columns into one word
  ("18 189,950" next to "845,246"): the amount needs digit boundaries and its
  printed sign, so 1 661 853 is not found inside 31 661 853 and (50) is not 50.
  A match that starts with a three-digit group right after other digits, or is
  followed by one, may be the middle of a larger amount and is not accepted.

Known blind spots, measured by the harness rather than hidden: two categories
whose values are swapped keep every amount printed and every sum intact, so the
gate admits them; only header-anchored column reading can prove an assignment.
A reader that copies the N-1 comparative column is caught only because the
category annex prints year N alone.
"""
from decimal import Decimal
from functools import lru_cache
import re

from ledger_orchestrator.extraction.core import lines, numeric_groups
from ledger_orchestrator.extraction.premium_annex import MINUS

LIFE_PREFIX = 'VIE_'
SEPARATOR = r'[   .]?'
MINUS_SIGNS = '-‐‑‒–−('


def _amount(value):
    return Decimal(str(value))


def _groups(integer):
    return f'{integer:,}'.split(',')


@lru_cache(maxsize=4096)
def amount_patterns(value):
    """Regexes for ``value`` (TND) printed in TND or in exact thousands (D-008)."""
    value = _amount(value)
    minus = re.escape(MINUS_SIGNS)
    magnitude = abs(value)

    def build(integer, decimals=''):
        groups = _groups(integer)
        # A thousands continuation group is exactly three digits. A match that starts
        # with one right after other digits, or whose integer part is followed by
        # one, may be the middle of a larger amount: ambiguous, so not matched.
        # After a decimal part (",871 ") no thousands group can follow, so the
        # next three digits necessarily start a new amount.
        lead = r'(?<![\d.,])' + (r'(?:(?<!\d[   .])|(?<=[,.]\d{3}[   ]))'
                                  if len(groups[0]) == 3 else '')
        sign = rf'[{minus}]\s?' if value < 0 else rf'(?<![{minus}])'
        tail = r'(?![\d]|[.,]\d)' + ('' if decimals else r'(?![   .]\d{3}(?!\d))')
        if value < 0:
            return rf'(?<![\d.,]){sign}' + SEPARATOR.join(groups) + decimals + tail
        return lead + sign + SEPARATOR.join(groups) + decimals + tail

    patterns = {}
    if magnitude == magnitude.to_integral_value():
        patterns['TND'] = build(int(magnitude))
    thousands = magnitude / 1000
    if thousands == thousands.quantize(Decimal('0.001')):
        integer = int(thousands)
        fraction = f'{int((thousands - integer) * 1000):03d}'
        decimals = rf'[,.](?:{fraction}|{fraction.rstrip("0")})' if fraction != '000' else ''
        patterns['kTND'] = build(integer, decimals)
        if fraction == '000':
            patterns['kTND'] = f"(?:{build(integer, r'[,.]0{1,3}')}|{patterns['kTND']})"
    return {unit: re.compile(p) for unit, p in patterns.items()}


def printed_amounts(page):
    """Amounts as the column geometry separates them, in the printed unit."""
    result = set()
    for row in lines(page.get('words', [])):
        row = [dict(w, text=MINUS.sub('-', w['text'])) for w in row]
        result.update(_amount(value) for value, _, _ in numeric_groups(row, page['width']))
    return result


class DocumentIndex:
    """Geometry-grouped amounts and text of each page of one document."""

    def __init__(self, pages):
        self.text = {p['page']: p.get('text', '') for p in pages}
        self.amounts = {p['page']: printed_amounts(p) for p in pages}

    def units_on(self, value, page):
        value = _amount(value)
        amounts, text = self.amounts.get(page, set()), self.text.get(page, '')
        patterns = amount_patterns(value)
        units = []
        if value in amounts or ('TND' in patterns and patterns['TND'].search(text)):
            units.append('TND')
        if value / 1000 in amounts or ('kTND' in patterns and patterns['kTND'].search(text)):
            units.append('kTND')
        return units

    def pages_printing(self, value, tolerance=0):
        """Pages printing ``value`` exactly, or within a whole-TND rounding tolerance (D-004)."""
        value = _amount(value)
        candidates = [value] + [value + d for k in range(1, int(tolerance) + 1) for d in (k, -k)]
        return sorted(p for p in self.text if any(self.units_on(c, p) for c in candidates))


def scopes(taxonomy):
    """Non-life categories (assigned to a branch or excluded) and life categories."""
    nonlife = {c: b for b, codes in taxonomy['branches'].items() for c in codes}
    nonlife.update({c: 'excluded' for c in taxonomy['excluded']})
    life = {LIFE_PREFIX + c: 'VIE' for c in taxonomy['life']['aliases'] if c != 'TOTAL'}
    return dict(nonlife=('TOTAL_NONVIE', nonlife), life=('TOTAL_VIE', life))


def verify_premiums(proposals, document, taxonomy, tolerance, next_document=None):
    """``proposals``: {code: dict(value=TND amount, page=int)}. Returns per-code decisions and checks."""
    tolerance = _amount(tolerance)
    decisions = {code: dict(admitted=False, reasons=[], units=[]) for code in proposals}
    checks = []
    known = set()
    for scope, (total_code, members) in scopes(taxonomy).items():
        known |= {total_code, *members}
        codes = [c for c in proposals if c in members]
        if total_code not in proposals:
            for code in codes:
                decisions[code]['reasons'].append(f'{total_code} not proposed')
            continue
        failures = []
        values = {c: _amount(proposals[c]['value']) for c in [total_code, *codes]}
        for code in [total_code, *codes]:
            if values[code] == 0:
                if code == total_code:
                    failures.append(f'{code} is zero')
                continue
            units = document.units_on(values[code], proposals[code].get('page'))
            decisions[code]['units'] = units
            if not units:
                failures.append(f'{code} not printed on cited page {proposals[code].get("page")}')
        # The second printing (statement vs annex) may differ by rounding, like D-007.
        printings = document.pages_printing(values[total_code], tolerance)
        checks.append(dict(scope=scope, identity='total printed on two pages', pages=printings,
                           exact_pages=document.pages_printing(values[total_code])))
        if len(printings) < 2:
            failures.append(f'{total_code} printed on {len(printings)} page(s), two required')
        if codes:
            delta = sum(values[c] for c in codes) - values[total_code]
            checks.append(dict(scope=scope, identity='categories = total', delta=str(delta)))
            if abs(delta) > tolerance:
                failures.append(f'categories differ from {total_code} by {delta}')
            zeros = [c for c in codes if values[c] == 0]
            if len({members[c] for c in zeros}) > 1:
                failures.append(f'zero categories {zeros} span several branches; not provable (D-002)')
        # Evidence only: next year's report prints the N-1 premium net of reinsurance.
        checks.append(dict(scope=scope, identity='printed in next year report (evidence, not required)',
                           pages=None if next_document is None else next_document.pages_printing(values[total_code])))
        for code in [total_code, *codes]:
            decisions[code]['reasons'] += failures
            decisions[code]['admitted'] = not failures
    for code in proposals:
        if code not in known:
            decisions[code]['reasons'].append('code outside the profile taxonomy')
    return dict(decisions=decisions, checks=checks)
