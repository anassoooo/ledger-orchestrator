"""Read the inspected 2024 AC7 note without inventing a balance-page row."""
import hashlib

import pdfplumber

from qualify_comar_balance import rows, label_key
from qualify_comar_premiums import in_band, read_amount


def note_reading(page, year):
    if year != 2024 or abs(page.width - 595.22) > 1 or abs(page.height - 842) > 1:
        raise ValueError('Unsupported COMAR note layout')
    words = page.extract_words()
    section = [w for w in words if 190 < w['top'] < 210 and w['x0'] >= 95]
    if label_key(' '.join(w['text'] for w in section)) != 'AC7AUTRESELEMENTSDACTIF':
        raise ValueError('Unconfirmed COMAR AC7 note identity')
    bands = [(60, 220), (220, 305), (305, 385)]
    heading = [w for w in words if 260 < w['top'] < 278]
    for expected, band in zip(('LIBELLE', '2024', '2023'), bands):
        if label_key(' '.join(w['text'] for w in in_band(heading, *band))) != expected:
            raise ValueError('Unconfirmed COMAR note period columns')
    matches = []
    for row in rows([w for w in words if 278 < w['top'] < 450]):
        label = ' '.join(w['text'] for w in in_band(row, *bands[0]))
        if label_key(label) == 'FRAISDACQUISITIONREPORTES':
            matches.append((row, label))
    if len(matches) != 1:
        raise ValueError('Missing or ambiguous COMAR acquisition-cost note')
    row, label = matches[0]
    if any((w['x0'] + w['x1']) / 2 >= bands[-1][1] for w in row):
        raise ValueError('Unexpected COMAR note value column')
    cells = {}
    for column, band in zip(('current', 'comparative'), bands[1:]):
        cell = in_band(row, *band)
        raw, value, state = read_amount(cell)
        if value is None:
            raise ValueError('Missing numeric COMAR acquisition-cost note')
        cells[column] = {'value': value, 'raw': raw, 'state': state,
                         'bbox': [min(w['x0'] for w in cell), min(w['top'] for w in cell),
                                  max(w['x1'] for w in cell), max(w['bottom'] for w in cell)]}
    return {'code': 'AC721', 'page': 21, 'side': 'asset', 'cells': cells,
            'row_label': label, 'method': 'native', 'unit': 'TND', 'approved': False,
            'source_kind': 'note', 'mapping_basis': 'Explicit deferred acquisition costs in AC7 note',
            'period_headers': [2024, 2023]}


def extract_notes(source, year, balance):
    if year != 2024:
        return {}
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if balance['year'] != year or digest != balance['sha256']:
        raise ValueError('COMAR note and balance document differ')
    with pdfplumber.open(source) as document:
        reading = note_reading(document.pages[20], year)
    # Compare directly printed amounts, without deriving the child from its parent.
    controls = []
    for column in ('current', 'comparative'):
        value = reading['cells'][column]['value']
        parent = balance['records']['AC72']['cells'][column]['value']
        if parent is None or parent != value:
            raise ValueError('COMAR note differs from printed charges reportées')
        controls.append({'code': 'AC72', 'column': column, 'delta': value - parent})
    if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
        raise ValueError('COMAR source changed during note extraction')
    reading['printed_parent_checks'] = controls
    return {'AC721': reading}
