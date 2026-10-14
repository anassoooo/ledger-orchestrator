"""Generic reader for the regulated premium disclosures of Tunisian insurers (NC 26).

Every annual report contains the same semantic objects, whatever its layout:

- the technical statements (non-life PRNV11, life PRV11), whose first amount on
  the "primes émises (et acceptées)" row is the gross issued premium of year N;
- annex 13 (non-life) and annex 12 (life): "Résultat technique par catégorie",
  with one column per category and a "Primes émises" row.

The reader anchors on those meanings rather than on page coordinates. Category
columns are identified from the header line through a per-company alias table;
an unknown header rejects the table instead of guessing. Admission is decided
by identities computed here and re-checked downstream:

1. categories (and any "total affaires directes" subtotal) sum to the annex total;
2. the annex total equals the statement's gross issued premium;
3. the statement declares its unit, which the identity transfers to the annex.
"""
import re

from decimal import Decimal

from ledger_orchestrator.extraction.core import lines, normalize, number, numeric_groups

DINAR_UNIT = re.compile(r'(EN|ARRONDIS EN|EXPRIMEE?S? EN)\s+(DINARS?|DT)\b')
# Accounting-policy declaration covering every statement of the document.
POLICY_UNIT = re.compile(r'(ETATS FINANCIERS|POSITIONS COMPTABLES|COMPTES)[^.]{0,80}EXPRIMEE?S?\s+EN\s+DINARS?\s+TUNISIENS?')
# "MD" means millions of dinars in Tunisian usage; it is never read as thousands.
THOUSAND_UNIT = re.compile(r'MILLIERS?\s+DE\s+DINARS|EN\s+MILLE\s+DINARS|\bEN\s+(KDT|MDT)\b')
YEARS = re.compile(r'\b(20\d\d)\b')
DASHES = {'-', '‐', '‑', '‒', '–', '—'}


class AnnexError(ValueError):
    """The disclosure does not match a qualified reading; nothing is admitted."""


MINUS = re.compile(r'^[‐‑‒–−](?=\d)')


def _signed(words):
    """Typographic minus signs before digits ("‐50") become ASCII; a lone dash stays a dash."""
    return [dict(w, text=MINUS.sub('-', w['text'])) for w in words]


def _key(text):
    return re.sub(r'[^A-Z0-9]', '', normalize(text))


def statement_unit(text):
    text = normalize(text)
    if THOUSAND_UNIT.search(text):
        return 'kTND'
    if DINAR_UNIT.search(text):
        return 'TND'
    return None


NONLIFE_PAGE = re.compile(r'NON[\s\-‐‑]*VIE')


def _is_nonlife(text):
    return bool(NONLIFE_PAGE.search(normalize(text)))


def _statement_row(row, code, life):
    tokens = [normalize(w['text']) for w in row]
    # The code may be glued to its label ("PRNV11Primes"), never to a digit.
    for i, token in enumerate(tokens):
        if re.fullmatch(code + r'([^0-9].*)?', token):
            return i + 1
    label = ' '.join(tokens)
    expected = 'PRIMES EMISES' if life else 'PRIMES EMISES ET ACCEPTE'
    if label.startswith(expected):
        return len(expected.split())
    return None


def statement_gross(pages, code, year):
    """First amount of the PRNV11 / PRV11 row on a technical statement of year N.

    The row is identified by its code or, in older reports, by its printed label.
    A note reference printed between the label and the amounts is skipped.
    """
    life = code == 'PRV11'
    found = []
    for page in pages:
        text = normalize(page['text'])
        if 'RESULTAT TECHNIQUE' not in text or 'CATEGORIE' in text or str(year) not in text:
            continue
        if _is_nonlife(page['text']) == life:
            continue
        for row in lines(page['words']):
            start = _statement_row(row, code, life)
            if start is None:
                continue
            amounts = [w for w in row[start:] if not re.search(r'[A-Za-z]', w['text'])]
            values = numeric_groups(_signed(amounts), page['width'])
            # A note reference ("9.1") is its own column group, never part of an
            # amount; a company's gross premium is never below 100 TND.
            if len(values) > 1 and abs(values[0][0]) < 100:
                values = values[1:]
            if values:
                value, x0, x1 = values[0]
                found.append(dict(code=code, value=value, page=page['page'], method=page['method'],
                                  unit=statement_unit(page['text']),
                                  bbox=[x0, min(w['top'] for w in row), x1, max(w['bottom'] for w in row)],
                                  source_label=' '.join(w['text'] for w in row)))
    if len({(f['value'], f['unit']) for f in found}) != 1:
        raise AnnexError(f'{code}: expected one statement reading, found {len(found)}')
    reading = found[0]
    if reading['unit'] is None:
        reading['unit'], reading['unit_page'] = _unit_by_amount(pages, reading['value'])
    if reading['unit'] is None:
        reading['unit'], reading['unit_page'] = _policy_unit(pages)
    return reading


def _policy_unit(pages):
    """A document-wide policy sentence, accepted only if no page declares thousands."""
    policy = [p['page'] for p in pages if POLICY_UNIT.search(' '.join(normalize(p['text']).split()))]
    if not policy or any(THOUSAND_UNIT.search(normalize(p['text'])) for p in pages):
        return None, None
    return 'TND', policy[0]


def _formatted(value):
    return f'{int(value):,}'.replace(',', ' ')


def _unit_by_amount(pages, value):
    """Unit of a page that declares one and prints the same amount (e.g. the notes)."""
    printed = _formatted(value)
    units = {(statement_unit(p['text']), p['page']) for p in pages
             if printed in p['text'] and statement_unit(p['text'])}
    if len({u for u, _ in units}) != 1:
        return None, None
    return sorted(units)[0]


def corroborated_life_total(pages, statement):
    """Without a life category annex, a second page must print the same life total."""
    printed = _formatted(statement['value'])
    others = [dict(page=p['page'], method=p['method']) for p in pages
              if p['page'] != statement['page'] and printed in p['text']
              and re.search(r'PRIMES EMISES (VIE|PRV1)|\bPRV11\b', normalize(p['text']))]
    if not others:
        raise AnnexError('No life category annex and no second reading of the life total')
    return others


def _header_labels(row, aliases):
    """Group header tokens into canonical categories, longest alias first."""
    keyed = sorted(((tuple(_key(t) for t in alias.split()), code)
                    for code, names in aliases.items() for alias in names),
                   key=lambda item: -len(item[0]))
    words = [w for w in row if _key(w['text'])]
    labels, i = [], 0
    while i < len(words):
        for tokens, code in keyed:
            window = [_key(w['text']) for w in words[i:i + len(tokens)]]
            if tuple(window) == tokens:
                group = words[i:i + len(tokens)]
                labels.append(dict(code=code, x0=group[0]['x0'], x1=group[-1]['x1'],
                                   text=' '.join(w['text'] for w in group)))
                i += len(tokens)
                break
        else:
            raise AnnexError(f"Unknown category header: {words[i]['text']!r}")
    codes = [l['code'] for l in labels]
    if len(codes) != len(set(codes)):
        raise AnnexError('Duplicate category header')
    return labels


def _row_label(row):
    """Row label without its code or a leading dash: "PRNV11 Primes", "-Primes"."""
    label = normalize(' '.join(w['text'] for w in row))
    return re.sub(r'^(PRNV11|PRV11)?[\s\-\u2010\u2011.]*', '', label)


LABEL_YEAR = re.compile(r'^\(?(19|20)\d\d\)?:?$')


def _digits(value):
    return len(re.sub(r'\D', '', format(Decimal(str(value)).normalize(), 'f')))


def _letters(text):
    return re.sub(r'[^A-Z]', '', normalize(text))


def _band_columns(rows, header_rows, first_data, width):
    """Column right edges and the header text rebuilt inside each band."""
    """Multi-line headers: columns from amount right edges, labels from header words above.

    Column right edges are clustered over every numeric row of the table, so a
    column that is blank on the "Primes émises" row is still located. Each
    column's label is the concatenation, line by line, of the header words whose
    centre falls in its band; it must equal one alias exactly (letters only).
    """
    # Only amounts of at least four digits locate columns (in TND or kTND): they
    # are right-aligned, while small values such as 0 are often centred. Years
    # printed in row labels, e.g. "Résultat technique (2016)", are not amounts.
    # Only the top of the table is used: lower provision sub-rows add extra columns.
    ends = sorted(x1 for r in rows[first_data:first_data + 15]
                  for value, _, x1 in numeric_groups(_signed([w for w in r if not re.search(r'[A-Za-z]', w['text'])
                                                              and not LABEL_YEAR.match(w['text'])]), width)
                  if _digits(value) >= 4)
    clusters = []
    for x in ends:
        # Right edges in one column vary by up to ~12 pt (centred amounts, minus
        # signs); columns are at least ~30 pt apart. A cluster spans at most 14 pt.
        if clusters and x - clusters[-1][0] <= 14:
            clusters[-1].append(x)
        else:
            clusters.append([x])
    rights = [max(c) for c in clusters if len(c) >= 3]
    if len(rights) < 2:
        raise AnnexError('Too few amount columns to locate category headers')
    words = [w for r in header_rows for w in r]
    columns, previous = [], None
    for right in rights:
        left = previous if previous is not None else right - 60
        band = [w for w in words if left + 2 < (w['x0'] + w['x1']) / 2 <= right + 8]
        by_line = {}
        for w in band:
            by_line.setdefault(round(w['top']), []).append(w)
        text = ''.join(_letters(''.join(x['text'] for x in sorted(ws, key=lambda w: w['x0'])))
                       for _, ws in sorted(by_line.items()))
        columns.append(dict(left=left, right=right, text=text))
        previous = right
    return columns


def _band_labels(columns, spec):
    """Name band columns by exact alias, or by one ordered layout family.

    A family lists every column in order; "expect" is a letter fragment its
    header must contain, null for columns whose identity cannot change a target
    value (all mapped to the same branch). Exactly one family must fit.
    """
    texts = [c['text'] for c in columns]
    index = {key: code for code, names in spec['aliases'].items() for key in (_letters(n) for n in names)}
    exact = [index.get(t) for t in texts]
    if None not in exact and len(set(exact)) == len(exact):
        codes = exact
        how = 'aliases'
    else:
        fits = [f for f in spec.get('families', []) if len(f['columns']) == len(columns) and all(
            col['expect'] is None or col['expect'] in text for col, text in zip(f['columns'], texts))]
        if len(fits) != 1:
            raise AnnexError(f'No unique layout family for headers {texts} ({len(fits)} fit)')
        codes = [col['code'] for col in fits[0]['columns']]
        how = 'family ' + fits[0]['name']
    if len(codes) != len(set(codes)):
        raise AnnexError('Duplicate category header')
    return [dict(code=code, x0=c['left'], x1=c['right'], text=c['text'], band=True, matched=how)
            for code, c in zip(codes, columns)]


def _by_bands(words, labels):
    """Join the tokens whose right edge falls in each column band, then parse."""
    values = []
    for label in labels:
        band = sorted((w for w in words if label['x0'] + 2 < w['x1'] <= label['x1'] + 8
                       and w['text'].strip() not in DASHES), key=lambda w: w['x0'])
        if not band:
            continue
        raw = ''.join(w['text'] for w in band)
        if raw[:1] in ',.' or raw[:2] in ('-,', '-.'):
            raw = raw.replace(',', '0,', 1) if ',' in raw[:2] else raw.replace('.', '0.', 1)   # ",000" is zero
        try:
            value = number(raw)
        except ValueError as exc:
            raise AnnexError(f'Unreadable amount {raw!r} in column {label["code"]}') from exc
        values.append((value, band[0]['x0'], band[-1]['x1']))
    return values


def _column(labels, x0, x1):
    """Assign an amount to its header column.

    Layouts right-align amounts just right of the header or centre them under
    it; both overlap the header span. The largest overlap wins and must be
    clearly larger than the next; otherwise the nearest right edge decides,
    with the same ambiguity guard. Ambiguity rejects the table.
    """
    overlaps = sorted(((min(x1, l['x1']) - max(x0, l['x0']), i) for i, l in enumerate(labels)), reverse=True)
    if overlaps[0][0] > 0:
        if len(overlaps) > 1 and overlaps[1][0] > 0.5 * overlaps[0][0]:
            raise AnnexError('Amount overlaps two category headers')
        return overlaps[0][1]
    distances = sorted((abs(x1 - l['x1']), i) for i, l in enumerate(labels))
    if len(distances) > 1 and distances[0][0] > 0.5 * distances[1][0]:
        raise AnnexError('Amount between two category columns')
    return distances[0][1]


def annex_row(pages, year, spec, life):
    """Locate annex 12/13 and read its "Primes émises" row by header columns."""
    candidates = []
    for page in pages:
        text = normalize(page['text'])
        # Reconciliation tables (annexes 15/16) repeat the total, not the categories.
        if 'CATEGORIE' not in text or 'PRIMES EMISES' not in text or 'RACCORDEMENT' in text:
            continue
        # The year is proven by the identity with the year-N statement; a page
        # printed for another year only is still rejected here.
        if YEARS.findall(text) and str(year) not in text:
            continue
        if _is_nonlife(page['text']) == life:
            continue
        rows = lines(page['words'])
        header_index = next((i for i, r in enumerate(rows) if _key(r[0]['text']) == 'CATEGORIES'), None)
        premium_index = [i for i, r in enumerate(rows) if _row_label(r).startswith('PRIMES EMISES')]
        if header_index is not None:
            labels = _header_labels(rows[header_index][1:], spec['aliases'])
            premium_index = [i for i in premium_index if i > header_index]
        else:
            # Multi-line headers: the block between the title and the first data row.
            title = next((i for i, r in enumerate(rows)
                          if 'PAR CATEGORIE' in normalize(' '.join(w['text'] for w in r))), None)
            first_data = next((i for i, r in enumerate(rows) if title is not None and i > title
                               and _row_label(r).startswith('PRIMES')), None)
            if title is None or first_data is None or not premium_index:
                continue
            labels = _band_labels(_band_columns(rows, rows[title + 1:first_data], first_data, page['width']), spec)
        if len(premium_index) != 1:
            raise AnnexError('Expected one "Primes émises" row in the category annex')
        candidates.append((page, labels, rows[premium_index[0]]))
    if len(candidates) != 1:
        raise AnnexError(f"Expected one {'life' if life else 'non-life'} category annex, found {len(candidates)}")
    page, labels, row = candidates[0]
    label_end = max(w['x1'] for w in row if re.search(r'[A-Za-z]', w['text']))
    amounts = _signed([w for w in row if w['x0'] > label_end])
    if labels[0].get('band'):
        values = _by_bands(amounts, labels)
    else:
        values = numeric_groups(amounts, page['width'])
    dashes = [w for w in row if w['text'].strip() in DASHES and w['x0'] > label_end]
    cells = {l['code']: None for l in labels}
    for value, x0, x1 in values:
        code = labels[_column(labels, x0, x1)]['code']
        if cells[code] is not None:
            raise AnnexError('Two amounts in one category column')
        cells[code] = dict(value=value, bbox=[x0, row[0]['top'], x1, max(w['bottom'] for w in row)])
    for dash in dashes:
        code = labels[_column(labels, dash['x0'], dash['x1'])]['code']
        if cells[code] is not None:
            raise AnnexError('A dash and an amount in one category column')
        cells[code] = dict(value=None, dash=True, bbox=[dash['x0'], dash['top'], dash['x1'], dash['bottom']])
    return dict(page=page['page'], method=page['method'], unit=statement_unit(page['text']),
                labels=[l['text'] for l in labels], cells=cells,
                source_label=' '.join(w['text'] for w in row))


def annex_factor(annex, printed, statement_tnd, tolerance):
    """The annex unit is proven by its total matching the statement in exactly one unit.

    Some reports print the statements in dinars and the category annex in
    thousands with three decimals; a declared annex unit must agree.
    """
    total = annex['cells'].get('TOTAL')
    if total is None or total['value'] is None:
        raise AnnexError('Missing annex total')
    fits = []
    for factor, unit in ((1, 'TND'), (1000, 'kTND')):
        if annex['unit'] not in (None, unit):
            continue
        try:
            exact_factor(unit, printed)
        except AnnexError:
            continue
        if abs(total['value'] * factor - statement_tnd) <= tolerance:
            fits.append(factor)
    if len(fits) != 1:
        raise AnnexError(f"Annex total {total['value']} matches the statement {statement_tnd} in {len(fits)} units")
    return fits[0]


def exact_factor(unit, values):
    """D-008: kTND is converted only when every amount has at most three decimals."""
    if unit == 'TND':
        return 1
    if unit != 'kTND':
        raise AnnexError(f'Statement unit not qualified: {unit}')
    for value in values:
        scaled = Decimal(str(value)) * 1000
        if scaled != scaled.to_integral_value():
            raise AnnexError(f'kTND amount {value} has more than three decimals: conversion inexact')
    return 1000


def _convert(record, factor):
    if factor != 1:
        record['source_value'] = record['value']
        record['source_unit'] = 'kTND'
        record['value'] = int(Decimal(str(record['value'])) * factor)
    record['conversion_factor'] = factor
    return record


def read_premiums(pages, year, taxonomy, tolerance):
    """Return admitted non-life categories, the non-life and life totals, and checks."""
    result, checks = {}, []
    for life in (False, True):
        spec = taxonomy['life' if life else 'nonlife']
        statement = statement_gross(pages, 'PRV11' if life else 'PRNV11', year)
        try:
            annex = annex_row(pages, year, spec, life)
        except AnnexError as exc:
            if 'found 0' not in str(exc):
                raise
            if not life:
                # Annex 13 not found (absent or unreadable): nothing non-life
                # is admitted, but the life total keeps its own evidence.
                checks.append(dict(identity='non-life category annex', status='not_found'))
                continue
            pages_seen = corroborated_life_total(pages, statement)
            factor = exact_factor(statement['unit'], [statement['value']])
            checks.append(dict(identity='life statement total printed again', pages=pages_seen, delta=0))
            result['TOTAL_VIE'] = _convert(dict(code='TOTAL_VIE', year=year, value=statement['value'], unit='TND',
                                       page=statement['page'], method=statement['method'], bbox=statement['bbox'],
                                       source_label=statement['source_label'], statement=statement,
                                       corroborating_pages=pages_seen), factor)
            continue
        statement_tnd = statement['value'] * exact_factor(statement['unit'], [statement['value']])
        printed = [c['value'] for c in annex['cells'].values() if c and c['value'] is not None]
        factor = annex_factor(annex, printed, statement_tnd, tolerance)
        # Identities are checked in the printed unit; tolerance is in TND.
        tolerance_printed = tolerance / factor
        cells = annex['cells']
        total = cells.get('TOTAL')
        if total is None or total['value'] is None:
            raise AnnexError('Missing annex total')
        if abs(total['value'] * factor - statement_tnd) > tolerance:
            raise AnnexError(f"Annex total differs from {statement['code']}: {total['value'] * factor - statement_tnd}")
        subtotals = spec.get('subtotals', {})
        categories = [c for c in cells if c != 'TOTAL' and c not in subtotals]
        unknown = [c for c in categories if cells[c] is None or cells[c]['value'] is None]
        known = sum(cells[c]['value'] for c in categories if c not in unknown)
        delta = known - total['value']
        if abs(delta) > tolerance_printed:
            raise AnnexError(f'Annex categories do not reconcile with the total: {delta}')
        # D-002: blanks/dashes are admitted only through the identity above. With
        # several, only their sum is proven, so they must share one target branch.
        if len(unknown) > 1 and not life:
            owners = {next((b for b, codes in taxonomy['branches'].items() if c in codes), 'excluded')
                      for c in unknown}
            if len(owners) != 1:
                raise AnnexError(f'Blank categories {unknown} span several branches; values not provable')
        for name, members in subtotals.items():
            if name not in cells:
                continue        # this layout family does not print the subtotal
            sub = cells[name]
            if sub is None or sub['value'] is None:
                raise AnnexError(f'Printed subtotal {name} has no amount')
            sub_delta = sum(cells[c]['value'] for c in members if c in cells and c not in unknown) - sub['value']
            if abs(sub_delta) > tolerance_printed:
                raise AnnexError(f'Subtotal {name} does not reconcile: {sub_delta}')
            checks.append(dict(identity=f'{name} = sum of members', delta=sub_delta))
        checks.append(dict(identity=f"{'life' if life else 'non-life'} categories = annex total", delta=delta))
        checks.append(dict(identity=f"annex total = {statement['code']} gross", delta=total['value'] * factor - statement_tnd,
                           annex_factor=factor))
        prefix = 'VIE_' if life else ''
        for code in categories:
            cell = cells[code]
            value = 0 if code in unknown else cell['value']
            record = dict(code=prefix + code, year=year, value=value, unit='TND', page=annex['page'],
                          method=annex['method'], bbox=cell['bbox'] if cell else None,
                          source_label=annex['source_label'])
            if code in unknown:
                record['nil_proof'] = dict(rule='D-002', printed='dash' if cell else 'blank', delta=delta,
                                           proven='value' if len(unknown) == 1 else 'sum', members=unknown)
            result[record['code']] = _convert(record, factor)
        total_code = 'TOTAL_VIE' if life else 'TOTAL_NONVIE'
        result[total_code] = _convert(dict(code=total_code, year=year, value=total['value'], unit='TND',
                                  page=annex['page'], method=annex['method'], bbox=total['bbox'],
                                  source_label=annex['source_label'], statement=statement), factor)
    return result, checks
