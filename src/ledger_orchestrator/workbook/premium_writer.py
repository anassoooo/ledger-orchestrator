"""Premium-history profile contract and guarded TAF_G3 writer.

The guards mirror workbook/writer.py: template anchors, never overwrite a
different existing value (conflicts are reported), totals are COUNT-guarded
formulas, every other cell must be unchanged before and after LibreOffice.
"""
import copy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

import openpyxl
from openpyxl.utils import column_index_from_string, get_column_letter

from ledger_orchestrator.profiles import _cell, local_path
from ledger_orchestrator.workbook.recalculation import recalculate
from ledger_orchestrator.workbook.writer import guarded_sum


@dataclass(frozen=True)
class HistoryProfile:
    config: dict

    @classmethod
    def load(cls, path: Path):
        return cls.from_dict(json.loads(Path(path).read_text(encoding='utf-8')))

    @classmethod
    def from_dict(cls, config):
        required = {'schema_version', 'profile_id', 'kind', 'revision', 'status', 'company', 'identity_terms',
                    'source_directory', 'years', 'target_unit', 'rounding_tolerance_tnd', 'premium_basis',
                    'taxonomy', 'workbook'}
        if not isinstance(config, dict) or required - config.keys():
            raise ValueError(f'Missing history profile fields: {sorted(required - set(config or {}))}')
        if config['schema_version'] != 1 or config['kind'] != 'premium_history':
            raise ValueError('Unsupported history profile')
        if config['status'] not in ('draft', 'validated') or config['target_unit'] != 'TND':
            raise ValueError('Invalid history profile status or unit')
        if config['premium_basis'] != 'before_reinsurance':
            raise ValueError('Only the D-001 premium basis is qualified')
        if not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', str(config['profile_id'])):
            raise ValueError('Invalid profile identifier')
        years = config['years']
        if not isinstance(years, list) or not years or len(set(years)) != len(years) or any(
                type(y) is not int or not 1990 <= y <= 2100 for y in years):
            raise ValueError('History years must be explicit unique integers')
        tolerance = config['rounding_tolerance_tnd']
        if type(tolerance) not in (int, float) or not 0 <= tolerance <= 10:
            raise ValueError('Rounding tolerance must be small and nonnegative')
        local_path(Path.cwd(), config['source_directory'])
        workbook = config['workbook']
        for key in ('template', 'filename', 'sheet', 'anchor', 'year_row', 'first_year', 'first_year_column',
                    'branch_rows', 'totals'):
            if key not in workbook:
                raise ValueError(f'Missing workbook field: {key}')
        local_path(Path.cwd(), workbook['template'])
        if not re.fullmatch(r'[A-Za-z0-9_-]+\.xlsx', workbook['filename']):
            raise ValueError('Workbook filename must be a simple .xlsx name')
        _cell(workbook['anchor']['cell'])
        if min(years) < workbook['first_year']:
            raise ValueError('A history year precedes the template columns')
        rows = workbook['branch_rows']
        if set(rows) != {'AUTOMOBILE', 'INCENDIE', 'TRANSPORT', 'IRDS', 'GROUPE', 'VIE'}:
            raise ValueError('Expected the five non-life branches and VIE')
        taxonomy = config['taxonomy']
        aliases = taxonomy['nonlife']['aliases']
        subtotals = taxonomy['nonlife'].get('subtotals', {})
        categories = sorted(set(aliases) - {'TOTAL'} - set(subtotals))
        assigned = sorted([c for codes in taxonomy['branches'].values() for c in codes] + taxonomy['excluded'])
        if set(taxonomy['branches']) != set(rows) - {'VIE'} or assigned != categories:
            raise ValueError('Every non-life category must be assigned to exactly one branch or excluded (D-003)')
        if 'TOTAL' not in aliases or 'TOTAL' not in taxonomy['life']['aliases']:
            raise ValueError('Both annexes need a TOTAL column alias')
        for name, members in subtotals.items():
            if set(members) - set(categories) or set(members) & set(taxonomy['excluded']):
                raise ValueError(f'Subtotal {name} must list direct categories only')
        targets = [cls(config).address(y, code) for y in years for code in rows]
        if len(targets) != len(set(targets)):
            raise ValueError('Two targets share a cell')
        return cls(config)

    @property
    def fingerprint(self):
        payload = json.dumps(self.config, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()

    def select_years(self, years=None):
        selected = self.config['years'] if years is None else years
        if not selected or any(y not in self.config['years'] for y in selected):
            raise ValueError(f"Exercices validés pour {self.config['company']} : {self.config['years']}")
        if self.config['status'] != 'validated':
            raise ValueError('A draft profile cannot execute an extraction')
        return sorted(set(selected))

    def source_relative(self, year):
        return f"{self.config['source_directory']}/{year}.pdf"

    def column(self, year):
        workbook = self.config['workbook']
        return get_column_letter(column_index_from_string(workbook['first_year_column']) + year - workbook['first_year'])

    def address(self, year, code):
        workbook = self.config['workbook']
        row = workbook['branch_rows'].get(code) or workbook['totals'][code]['row']
        return f'{self.column(year)}{row}'

    def targets(self, year):
        workbook = self.config['workbook']
        for code in list(workbook['branch_rows']) + list(workbook['totals']):
            yield workbook['sheet'], self.address(year, code), code

    def coverage(self, path, years, writes, issues):
        workbook = openpyxl.load_workbook(path, data_only=True)
        written = {(w['sheet'], w['cell']) for w in writes}
        conflicts = {(i['sheet'], i['cell']) for i in issues if i['type'] == 'existing_cell_conflict'}
        rejected = {i['year']: i['reason'] for i in issues if i['type'] == 'premium_history_rejected'}
        cells = []
        for year in years:
            for sheet, cell, code in self.targets(year):
                value = workbook[sheet][cell].value
                status = ('conflict' if (sheet, cell) in conflicts else
                          'missing_or_blocked' if value in (None, '') else
                          'populated_this_run' if (sheet, cell) in written else 'existing_not_revalidated')
                cells.append(dict(year=year, sheet=sheet, cell=cell, code=code, status=status,
                                  reason=rejected.get(year)))
        return dict(basis='Configured TAF_G3 target cells including totals.', cells=cells)


def write_premium_history(template, path, profile, annual, confirmations=None):
    config = profile.config
    layout = config['workbook']
    sheet_name = layout['sheet']
    wb = openpyxl.load_workbook(template)
    if sheet_name not in wb or wb[sheet_name][layout['anchor']['cell']].value != layout['anchor']['value']:
        raise ValueError(f"Unrecognized template anchor: {sheet_name}!{layout['anchor']['cell']}")
    sheet = wb[sheet_name]
    first = sheet[f"{layout['first_year_column']}{layout['year_row']}"].value
    if first != layout['first_year']:
        raise ValueError('Template year row does not start at the configured first year')
    for year in annual:
        # Each year column must continue the template's +1 chain from the first year.
        column, previous = profile.column(year), profile.column(year - 1)
        if year > layout['first_year'] and sheet[f"{column}{layout['year_row']}"].value != f"=+{previous}{layout['year_row']}+1":
            raise ValueError(f'Template year chain broken at column {column}')
    original = {(s.title, c.coordinate): (c.value, copy.copy(c._style)) for s in wb for row in s for c in row}
    writes, issues, allowed = [], [], set()

    def put(coord, value, year, code, sources=(), replace_formula=False):
        cell = sheet[coord]
        old = cell.value
        if old == value or (type(old) in (int, float) and old == value):
            if confirmations is not None and old is not None:
                confirmations.append(dict(sheet=sheet_name, cell=coord, year=year, code=code, value=old))
            return True
        if old is not None and not (replace_formula and cell.data_type == 'f'):
            issues.append(dict(type='existing_cell_conflict', sheet=sheet_name, cell=coord, year=year, code=code,
                               existing=old, proposed=value))
            return False
        cell.value = value
        cell.number_format = '#,##0;[Red](#,##0);0'
        allowed.add((sheet_name, coord))
        writes.append(dict(sheet=sheet_name, cell=coord, year=year, code=code, old=old, new=value,
                           sources=list(sources)))
        return True

    for year, data in sorted(annual.items()):
        admitted = set()
        for code, branch in data.get('branches', {}).items():
            if branch['sources'] and all(s.get('approved') for s in branch['sources']):
                if put(profile.address(year, code), branch['value'], year, code, branch['sources']):
                    admitted.add(code)
        results = {}

        def total(code):
            if code in admitted:
                return True
            if code in results:
                return results[code]
            spec = layout['totals'].get(code)
            if spec is None:
                return False
            ok = all([total(child) for child in spec['children']])
            refs = [profile.address(year, child) for child in spec['children']]
            success = put(profile.address(year, code), guarded_sum(refs, ok), year, code, replace_formula=True)
            results[code] = ok and success
            return results[code]
        for code in layout['totals']:
            total(code)
    for (name, coord), (value, style) in original.items():
        if (name, coord) not in allowed and (wb[name][coord].value != value or wb[name][coord]._style != style):
            raise RuntimeError(f'Unexpected modification: {name}!{coord}')
    wb.save(path)
    recalculate(path)
    reopened = openpyxl.load_workbook(path)
    for (name, coord), (value, _) in original.items():
        if (name, coord) not in allowed and reopened[name][coord].value != value:
            raise RuntimeError(f'Export changed {name}!{coord}')
    return writes, issues
