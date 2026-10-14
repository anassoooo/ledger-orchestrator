"""Destination checks for the inspected COMAR review template, not admission."""
import hashlib
import json
from pathlib import Path

CONTRACT_PATH = Path(__file__).resolve().parents[1] / 'config/qualification/comar_template_v1.json'


def validate_template(profile, workbook, contract_path=CONTRACT_PATH):
    payload = contract_path.read_bytes()
    contract = json.loads(payload)
    if (contract.get('schema_version') != 1 or contract.get('company') != 'COMAR'
            or contract.get('production_enabled') is not False):
        raise ValueError('Unsupported COMAR template contract')
    targets = [{'year': year, 'sheet': sheet, 'cell': cell, 'code': code}
               for year in profile.config['years'] for sheet, cell, code in profile.targets(year)]
    addresses = [(t['sheet'], t['cell']) for t in targets]
    if len(addresses) != len(set(addresses)):
        raise ValueError('Duplicate COMAR destination')
    key = lambda t: (t['year'], t['sheet'], t['cell'], t['code'])
    if sorted(targets, key=key) != sorted(contract['targets'], key=key):
        raise ValueError('COMAR target layout differs from the inspected contract')
    for spec in contract['cells']:
        if spec['sheet'] not in workbook.sheetnames:
            raise ValueError('Missing COMAR target sheet: ' + spec['sheet'])
        actual = workbook[spec['sheet']][spec['cell']].value
        if actual not in spec['allowed_values']:
            raise ValueError('Unconfirmed COMAR destination identity: '
                             + spec['sheet'] + '!' + spec['cell'])
    return {'contract': contract['contract_id'],
            'sha256': hashlib.sha256(payload).hexdigest(),
            'destinations_checked': len(targets), 'identity_cells_checked': len(contract['cells']),
            'status': 'passed'}
