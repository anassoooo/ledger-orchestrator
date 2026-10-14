"""Discover company blocks and target cells directly from the CMF template.

The template, not the profiles, defines what "done" means: every input cell of
TAF_G1 (balance sheet), TAF_G2 and TAF_G3 (premiums) for every company block.
"""
from dataclasses import dataclass
import re

from openpyxl.utils import get_column_letter

# Template company names -> local source directories (data/sources/<dir>).
SOURCE_DIRECTORIES = {'ZITOUNA': 'ZITOUNA TAKAFUL', 'ZITOUNA TAKAFUL': 'ZITOUNA TAKAFUL'}
BALANCE_HEADINGS = {'CAPITAUX PROPRES', 'PASSIF', 'CAPITAUX PROPRES ET PASSIFS'}


@dataclass(frozen=True)
class TargetCell:
    sheet: str
    company: str
    year: int
    cell: str
    row: int
    section: str        # asset, liability or premium
    label: str
    derived: bool       # the template already holds a formula here


def _year(text):
    match = re.search(r'(20\d\d)', str(text or ''))
    return int(match[1]) if match else None


def _balance_blocks(sheet):
    for start in range(1, sheet.max_row + 1):
        if sheet.cell(start, 2).value != 'ACTIF':
            continue
        company = str(sheet.cell(start, 1).value).strip()
        header = start + 1
        asset_cols = [(c, _year(sheet.cell(header, c).value)) for c in range(3, 8)]
        liability_cols = [(c, _year(sheet.cell(header, c).value)) for c in range(11, 16)]
        end = next((r for r in range(start + 2, sheet.max_row + 1)
                    if str(sheet.cell(r, 1).value or '').upper().startswith('TOTAL ACTIF')), None)
        if end is None:
            raise ValueError(f'Unterminated balance block for {company}')
        for row in range(start + 2, end + 1):
            code = sheet.cell(row, 1).value
            if code:
                for col, year in asset_cols:
                    yield _target(sheet, company, year, col, row, 'asset', f'{code} {sheet.cell(row, 2).value or ""}')
            label = sheet.cell(row, 9).value
            if label and str(label).strip().upper() not in BALANCE_HEADINGS:
                for col, year in liability_cols:
                    yield _target(sheet, company, year, col, row, 'liability', str(label))


def _premium_blocks(sheet):
    years = {}
    year = sheet.cell(2, 2).value
    if type(year) is not int:
        raise ValueError(f'{sheet.title}: expected the first year in B2')
    for col in range(2, sheet.max_column + 1):
        years[col] = year + col - 2
    for start in range(1, sheet.max_row + 1):
        if not str(sheet.cell(start, 1).value or '').startswith('Source'):
            continue
        company = str(sheet.cell(start, 2).value).strip()
        for row in range(start + 3, start + 12):
            label = sheet.cell(row, 1).value
            if not label:
                continue
            for col, year in years.items():
                yield _target(sheet, company, year, col, row, 'premium', str(label))


def _target(sheet, company, year, col, row, section, label):
    if year is None:
        raise ValueError(f'{sheet.title}: no year for column {get_column_letter(col)}')
    cell = sheet.cell(row, col)
    return TargetCell(sheet.title, company, year, cell.coordinate, row, section,
                      label.strip(), cell.data_type == 'f')


def target_cells(workbook):
    cells = []
    for name, reader in (('TAF_G1', _balance_blocks), ('TAF_G2', _premium_blocks), ('TAF_G3', _premium_blocks)):
        if name in workbook.sheetnames:
            cells.extend(reader(workbook[name]))
    keys = [(c.sheet, c.cell) for c in cells]
    if len(keys) != len(set(keys)):
        raise ValueError('Two template blocks claim the same cell')
    return cells


def source_directory(company):
    return SOURCE_DIRECTORIES.get(company.upper(), company.upper())
