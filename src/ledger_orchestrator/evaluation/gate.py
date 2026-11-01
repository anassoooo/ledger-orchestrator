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

- Column anchoring: each non-zero category must be printed on the "Primes émises"
  row of the category annex on its cited page, inside a column whose header names
  a category of the same template branch. Sums prove totals, not assignments: two
  categories of different branches swapped keep every amount printed and every
  sum intact, and only their headers tell them apart. The check is made at branch
  level because that is what the template stores; a swap inside IRDS changes no
  target value (the same reason ASTREE's layout families leave those columns
  positional). Requiring the "Primes émises" row also rejects a reader that took
  the "Primes acquises" row, whose categories add up to a total printed twice too.

Column geometry (right edges clustered over the table, header words per band,
glued amounts split per band) reuses the production reader's primitives, which
are qualified on every admitted layout. Naming is the gate's own and more
permissive: any header that names one branch is enough and no complete layout
family is needed, so readings of years the production reader rejects can still
be verified. A column whose header names no branch, or several, admits nothing.

A reader that copies the N-1 comparative column is caught only because the
category annex prints year N alone.
"""
from decimal import Decimal
from functools import lru_cache
import re

from ledger_orchestrator.extraction.core import lines, normalize, numeric_groups
from ledger_orchestrator.extraction.premium_annex import (MINUS, AnnexError, _band_columns, _by_bands, _letters,
                                                          _row_label, _signed)

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
        self.pages = {p['page']: p for p in pages}
        self.text = {p['page']: p.get('text', '') for p in pages}
        self.amounts = {p['page']: printed_amounts(p) for p in pages}
        self._columns = {}

    def premium_columns(self, page, aliases, branch_of):
        """Named columns of the category annex on ``page`` (cached), or the reason it cannot be read."""
        key = (page, tuple(sorted(aliases)))
        if key not in self._columns:
            try:
                self._columns[key] = annex_columns(self.pages[page], aliases, branch_of)
            except (AnnexError, KeyError) as exc:
                self._columns[key] = f'category annex not readable on page {page}: {exc}'
        return self._columns[key]

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


ANNEX_TITLE = re.compile(r'RESULTAT\s+TECHNIQUE\b.*\bCATEGORIE')
ALIAS_WORD = 5      # letters a distinctive alias word needs to name a column on its own


def name_band(header, aliases):
    """Codes named by a column header (letters only).

    A complete alias printed in the header names its code; an alias contained in
    a longer matched alias does not count ("AT" inside "PERTE D'EXPLOITATION",
    "AUTO" inside "AUTOMOBILE"). Only when no complete alias is printed, a
    distinctive alias word of at least five letters names its code: PDFs print
    "RESPOSABILITE DECENNALE" or interleave a neighbour's letters
    ("AUTRESDOMMAGESASSAUXBIENS"). The caller requires all names to share a branch.
    """
    matched = {}
    for code, names in aliases.items():
        keys = [k for k in (_letters(n) for n in names) if k and k in header]
        if keys:
            matched[code] = max(keys, key=len)
    if matched:
        return sorted(c for c, k in matched.items()
                      if not any(k != other and k in other for other in matched.values()))
    return sorted(code for code, names in aliases.items()
                  if any(len(w) >= ALIAS_WORD and w in header for n in names for w in map(_letters, n.split())))


def annex_columns(page, aliases, branch_of, row_label='PRIMES EMISES'):
    """Columns of the category annex on one page: header, branches named, amount on ``row_label``."""
    rows = lines(page['words'])
    premium = [i for i, r in enumerate(rows) if _row_label(r).startswith(row_label)]
    # The table starts after "Résultat technique par catégorie" / "... de la catégorie"
    # (STAR 2021-2022), or at a "CATEGORIES" header row when the title is on the
    # previous page (STAR 2021 life annex). ``title`` is the row before the header.
    titles = [i for i, r in enumerate(rows) if ANNEX_TITLE.search(normalize(' '.join(w['text'] for w in r)))]
    titles += [i - 1 for i, r in enumerate(rows) if _letters(r[0]['text']) == 'CATEGORIES']
    if not premium or not any(i < premium[0] for i in titles):
        raise AnnexError('no category annex with a "Primes émises" row')
    title = max(i for i in titles if i < premium[0])
    first_data = next(i for i in range(title + 1, len(rows)) if _row_label(rows[i]).startswith('PRIMES'))
    if len([i for i in premium if i > title]) != 1:
        raise AnnexError('expected one "Primes émises" row in the category annex')
    columns = _band_columns(rows, rows[title + 1:first_data], first_data, page['width'])
    row = rows[premium[0]]
    label_end = max(w['x1'] for w in row if re.search(r'[A-Za-z]', w['text']))
    bands = [dict(code=i, x0=c['left'], x1=c['right']) for i, c in enumerate(columns)]
    values = _by_bands(_signed([w for w in row if w['x0'] > label_end]), bands)
    result = []
    for column in columns:
        inside = [_amount(v) for v, _, x1 in values if column['left'] + 2 < x1 <= column['right'] + 8]
        codes = name_band(column['text'], aliases)
        result.append(dict(header=column['text'], codes=codes, branches=sorted({branch_of.get(c, 'total')
                                                                                 for c in codes}),
                           amounts=inside))
    return result


def anchor(document, code, value, page, aliases, branch_of):
    """None when ``value`` sits under a header of its branch; otherwise the reason."""
    columns = document.premium_columns(page, aliases, branch_of)
    if isinstance(columns, str):
        return columns
    holding = [c for c in columns if any(a == value or a * 1000 == value for a in c['amounts'])]
    if not holding:
        return f'{code} not on the "Primes émises" row of the category annex, page {page}'
    branch = branch_of[code]
    if any(c['branches'] == [branch] for c in holding):
        return None
    found = ' / '.join(f"{c['header'] or 'no header'} ({', '.join(c['branches']) or 'no branch'})" for c in holding)
    return f'{code} ({branch}) printed under {found}'


def scopes(taxonomy):
    """Non-life categories (assigned to a branch or excluded) and life categories."""
    nonlife = {c: b for b, codes in taxonomy['branches'].items() for c in codes}
    nonlife.update({c: 'excluded' for c in taxonomy['excluded']})
    life = {LIFE_PREFIX + c: 'VIE' for c in taxonomy['life']['aliases'] if c != 'TOTAL'}
    return dict(nonlife=('TOTAL_NONVIE', nonlife), life=('TOTAL_VIE', life))


def header_aliases(taxonomy, scope):
    """Header aliases of a scope keyed by proposal code (life codes carry the VIE_ prefix)."""
    if scope == 'nonlife':
        return taxonomy['nonlife']['aliases']
    return {(c if c == 'TOTAL' else LIFE_PREFIX + c): names for c, names in taxonomy['life']['aliases'].items()}


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
            aliases = header_aliases(taxonomy, scope)
            for code in codes:
                if values[code] != 0:
                    reason = anchor(document, code, values[code], proposals[code].get('page'), aliases, members)
                    checks.append(dict(scope=scope, identity=f'{code} under a header of its branch',
                                       status='ok' if reason is None else reason))
                    if reason is not None:
                        failures.append(reason)
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
