"""Versioned company/template contracts shared by CLI, API and workbook code."""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

from openpyxl.utils import column_index_from_string


def local_path(root: Path, relative: str) -> Path:
    """Resolve a declared input under its root, including symlink containment."""
    if not isinstance(relative, str) or not relative or '\\' in relative or ':' in relative:
        raise ValueError('Expected a relative local path')
    parts = PurePosixPath(relative)
    if parts.is_absolute() or any(p in ('.', '..') for p in relative.split('/')):
        raise ValueError('Expected a relative local path without traversal')
    target = (root / relative).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError('Declared path escapes its local root')
    return target


def _cell(address):
    if not isinstance(address, str) or not re.fullmatch(r'[A-Z]{1,3}[1-9][0-9]{0,6}', address):
        raise ValueError(f'Invalid Excel cell: {address!r}')
    letters = re.match(r'[A-Z]+', address)[0]
    if column_index_from_string(letters) > 16384 or int(address[len(letters):]) > 1048576:
        raise ValueError(f'Excel cell out of bounds: {address}')


@dataclass(frozen=True)
class CompanyProfile:
    config: dict

    @classmethod
    def load(cls, path: Path):
        return cls.from_dict(json.loads(path.read_text(encoding='utf-8')))

    @classmethod
    def from_dict(cls, config: dict):
        if not isinstance(config, dict):
            raise ValueError('Profile must be a JSON object')
        required = {'schema_version', 'profile_id', 'revision', 'status', 'company',
                    'extractor', 'identity_terms', 'source_directory', 'target_unit',
                    'years', 'workbook', 'asset_rows', 'liability_rows', 'branch_rows',
                    'children', 'extend_template', 'rounding_tolerance_tnd',
                    'premium_basis', 'branch_policy'}
        missing = required - config.keys()
        if missing:
            raise ValueError(f'Missing profile fields: {sorted(missing)}')
        if type(config['schema_version']) is not int or config['schema_version'] != 1:
            raise ValueError('Unsupported profile schema version')
        if not isinstance(config['profile_id'], str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', config['profile_id']):
            raise ValueError('Invalid profile identifier')
        if type(config['revision']) is not int or config['revision'] < 1:
            raise ValueError('Profile revision must be a positive integer')
        if config['status'] not in ('draft', 'validated'):
            raise ValueError('Profile status must be draft or validated')
        if not isinstance(config['company'], str) or not config['company'].strip():
            raise ValueError('Company is required')
        if not isinstance(config['extractor'], str) or not config['extractor']:
            raise ValueError('Extractor identifier is required')
        if not isinstance(config['identity_terms'], list) or not config['identity_terms'] or any(not isinstance(s, str) or not s.strip() for s in config['identity_terms']):
            raise ValueError('Document identity terms are required')
        years = config['years']
        if not isinstance(years, list) or not years or any(type(y) is not int or not 1900 <= y <= 2100 for y in years):
            raise ValueError('Profile years must be explicit integers')
        if len(years) != len(set(years)):
            raise ValueError('Duplicate profile years')
        if config['target_unit'] != 'TND':
            raise ValueError('Only confirmed TND mapping is implemented')
        if type(config['extend_template']) is not bool:
            raise ValueError('extend_template must be a boolean')
        tolerance = config['rounding_tolerance_tnd']
        if type(tolerance) not in (int, float) or not 0 <= tolerance < float('inf'):
            raise ValueError('Rounding tolerance must be finite and nonnegative')
        workbook = config['workbook']
        if not isinstance(workbook, dict):
            raise ValueError('Workbook profile must be an object')
        for key in ('template', 'filename', 'balance_sheet', 'premium_sheet', 'anchors',
                    'columns', 'details_sheet', 'details_title', 'premium_totals',
                    'label_overrides', 'extension_only', 'column_widths'):
            if key not in workbook:
                raise ValueError(f'Missing workbook field: {key}')
        for key, expected in (('anchors', list), ('columns', dict), ('premium_totals', dict),
                              ('label_overrides', list), ('extension_only', dict), ('column_widths', dict)):
            if not isinstance(workbook[key], expected):
                raise ValueError(f'Invalid workbook field: {key}')
        if not isinstance(config['children'], dict):
            raise ValueError('Balance dependencies must be an object')
        for relative in (config['source_directory'], workbook['template']):
            local_path(Path.cwd(), relative)
        if PurePosixPath(config['source_directory']).parts[0] != 'sources':
            raise ValueError('Source directory must be below sources/')
        if PurePosixPath(workbook['template']).parts[0] != 'templates':
            raise ValueError('Template must be below templates/')
        if not isinstance(workbook['filename'], str) or not re.fullmatch(r'[A-Za-z0-9_-]+\.xlsx', workbook['filename']):
            raise ValueError('Workbook filename must be a simple .xlsx name')
        sheets = [workbook[k] for k in ('balance_sheet', 'premium_sheet', 'details_sheet')]
        if any(not isinstance(s, str) or not 1 <= len(s) <= 31 or
               re.search(r'[\\/*?:\[\]]', s) or "'" in s for s in sheets) or len(set(sheets)) != 3:
            raise ValueError('Workbook sheets must be distinct, safe Excel names')
        if any(re.fullmatch(r'[A-Za-z0-9_]{1,31}', s) is None for s in sheets[:2]):
            raise ValueError('Target sheet names must be compatible with review identifiers')
        for section in ('asset', 'liability', 'branch'):
            mapping = config[f'{section}_rows']
            if not isinstance(mapping, dict) or any(type(row) is not int or not 1 <= row <= 1048576 for row in mapping.values()):
                raise ValueError(f'Invalid {section} rows')
            if any(not isinstance(code, str) or not code for code in mapping):
                raise ValueError(f'Invalid {section} code')
        if set(config['asset_rows']) & set(config['liability_rows']):
            raise ValueError('Balance code appears in both asset and liability mappings')
        if set(workbook['columns']) != {str(y) for y in years}:
            raise ValueError('Every profile year must have explicit Excel columns')
        for year in years:
            columns = workbook['columns'][str(year)]
            if not isinstance(columns, dict) or set(columns) != {'asset', 'liability', 'premium', 'details'}:
                raise ValueError('Expected asset, liability, premium and details columns')
            for column in columns.values():
                _cell(f'{column}1')
        if len({workbook['columns'][str(y)]['details'] for y in years}) != len(years):
            raise ValueError('Details columns must be unique per year')
        if any(column_index_from_string(workbook['columns'][str(y)]['details']) < 3 for y in years):
            raise ValueError('Details columns must follow the code and label columns')
        totals = workbook['premium_totals']
        for code, total in totals.items():
            if not isinstance(total, dict) or code in config['branch_rows'] or type(total.get('row')) is not int or not 1 <= total['row'] <= 1048576:
                raise ValueError('Invalid premium total row/code')
            if not isinstance(total.get('children'), list) or not total['children'] or any(
                not isinstance(c, str) or c not in set(config['branch_rows']) | set(totals) for c in total['children']
            ):
                raise ValueError('Unknown or missing premium total dependencies')
        for dependencies in (config['children'], {k: v['children'] for k, v in totals.items()}):
            def visit(code, stack):
                if code in stack:
                    raise ValueError(f'Cyclic total dependency: {code}')
                children = dependencies.get(code, [])
                if not isinstance(children, list) or any(not isinstance(c, str) for c in children) or len(children) != len(set(children)):
                    raise ValueError('Total dependencies must be unique lists')
                for child in children:
                    visit(child, stack | {code})
            for code in dependencies:
                visit(code, set())
        if set(workbook['column_widths']) - {'asset', 'liability', 'premium'}:
            raise ValueError('Unknown column width section')
        for width in workbook['column_widths'].values():
            if type(width) not in (int, float) or not 0 < width <= 255:
                raise ValueError('Invalid column width')
        if not workbook['anchors']:
            raise ValueError('Template identity anchors are required')
        for item in workbook['anchors'] + workbook['label_overrides'] + list(workbook['extension_only'].values()):
            if not isinstance(item, dict) or item.get('sheet') not in sheets[:2]:
                raise ValueError('Anchor or label targets an unknown sheet')
            _cell(item.get('cell'))
        if any('value' not in item for item in workbook['anchors'] + workbook['label_overrides']):
            raise ValueError('Anchor and label values are required')
        if any(code not in config['liability_rows'] or 'expected' not in item
               for code, item in workbook['extension_only'].items()):
            raise ValueError('Extension-only labels must identify liability codes and expected labels')
        profile = cls(config)
        destinations = [(s, c) for y in years for s, c, _ in profile.targets(y)]
        if len(destinations) != len(set(destinations)):
            raise ValueError('Two configured targets share an Excel cell')
        for item in workbook['anchors'] + workbook['label_overrides']:
            if (item['sheet'], item['cell']) in destinations:
                raise ValueError('A label/anchor overlaps a financial target')
        return profile

    @property
    def workbook(self):
        return self.config['workbook']

    @property
    def fingerprint(self):
        payload = json.dumps(self.config, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()

    def select_years(self, years=None):
        selected = self.config['years'] if years is None else years
        if not selected or any(type(y) is not int or y not in self.config['years'] for y in selected):
            raise ValueError(f"Exercices validés pour {self.config['company']} : {self.config['years']}")
        if self.config['status'] != 'validated':
            raise ValueError('A draft profile cannot execute an extraction')
        return sorted(set(selected))

    def source_relative(self, year):
        return f"{self.config['source_directory']}/{year}.pdf"

    def column(self, year, section):
        return self.workbook['columns'][str(year)][section]

    def targets(self, year):
        for section in ('asset', 'liability'):
            for code, row in self.config[f'{section}_rows'].items():
                yield self.workbook['balance_sheet'], f'{self.column(year, section)}{row}', code
        for code, row in self.config['branch_rows'].items():
            yield self.workbook['premium_sheet'], f'{self.column(year, "premium")}{row}', code
        for code, total in self.workbook['premium_totals'].items():
            yield self.workbook['premium_sheet'], f'{self.column(year, "premium")}{total["row"]}', code
