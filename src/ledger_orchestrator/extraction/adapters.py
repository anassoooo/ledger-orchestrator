"""Explicitly qualified extraction strategies; layouts are never enabled by name alone."""

import openpyxl

from ledger_orchestrator.extraction import comar
from ledger_orchestrator.extraction.core import balance, premiums
from ledger_orchestrator.extraction.notes import asset_notes, supplement
from ledger_orchestrator.extraction.presence import native_balance_presence
from ledger_orchestrator.extraction.cell_ocr import read_scanned_asset
from ledger_orchestrator.profiles import local_path
from ledger_orchestrator.validation.accounting import validate_balance, validate_premiums
from ledger_orchestrator.validation.premium_evidence import corroborate_premiums
from ledger_orchestrator.validation.subtotal_evidence import corroborate_subtotals


class StarIndividualExtractor:
    """The existing STAR rules, qualified only for individual accounts 2023–2025."""

    def extract(self, pages, year, source, config, **_):
        tolerance = config['rounding_tolerance_tnd']
        records, issues = balance(pages, year, source)
        notes, note_issues = asset_notes(pages, year, source, tolerance)
        issues += note_issues + supplement(records, notes)
        raw = premiums(pages, year, source)
        issues += corroborate_premiums(pages, raw, year, source, tolerance)
        validation = validate_balance(records, config['children'], tolerance)
        branches, branch_issues = validate_premiums(raw, config)
        presence = native_balance_presence(pages, year, source,
                                          set(config['asset_rows']) | set(config['liability_rows']))
        return dict(records=records, raw_branches=raw, branches=branches,
                    validation=validation, presence=presence), issues + branch_issues

    def refine(self, annual, root, cache, profile):
        if 2025 in annual and 2024 in annual and 'AC33' not in annual[2025]['records']:
            scanned = read_scanned_asset(local_path(root, profile.source_relative(2025)), cache)
            config = profile.config
            # Old SHA-keyed OCR caches predate the sources/ directory layout.
            # Rebind only that exact legacy alias to the file just fingerprinted.
            source = profile.source_relative(2025)
            for candidate in scanned.get('records', {}).values():
                if candidate.get('source') not in (source, 'STAR/2025.pdf'):
                    raise ValueError('Scanned evidence references an unexpected document')
                candidate['source'] = source
            accepted = corroborate_subtotals(scanned.get('records', {}), annual[2025],
                                            annual[2024], config['children'])
            annual[2025]['records'].update(accepted)
            annual[2025]['validation'] = validate_balance(annual[2025]['records'], config['children'],
                                                         config['rounding_tolerance_tnd'])


class ComarIndividualExtractor:
    """Guarded native COMAR readers, qualified for individual accounts 2023–2025."""

    def extract(self, pages, year, source, config, path=None, digest=None):
        if path is None or digest is None:
            raise ValueError('COMAR extraction requires the fingerprinted source document')
        tolerance = config['rounding_tolerance_tnd']
        balance = comar.extract(path, year)
        premium = comar.candidate(path, year)
        if balance['sha256'] != digest or premium['source_sha256'] != digest:
            raise ValueError('COMAR readers did not read the fingerprinted document')
        notes = comar.extract_notes(path, year, balance)
        records, issues = comar.balance_records(balance, notes, year, source, tolerance)
        raw, premium_issues = comar.premium_records(premium, year, source, tolerance)
        validation = validate_balance(records, config['children'], tolerance)
        branches, branch_issues = validate_premiums(raw, config)
        presence = native_balance_presence(pages, year, source,
                                          set(config['asset_rows']) | set(config['liability_rows']))
        return dict(records=records, raw_branches=raw, branches=branches,
                    validation=validation, presence=presence), issues + premium_issues + branch_issues

    def refine(self, annual, root, cache, profile):
        # The inspected destination contract: every target address and the
        # labels around it must be exactly those reviewed for this template.
        workbook = openpyxl.load_workbook(local_path(root, profile.workbook['template']))
        comar.validate_template(profile, workbook)


QUALIFIED = {
    ('star_individual_v1', 'STAR'): (StarIndividualExtractor, {2023, 2024, 2025}),
    ('comar_individual_v1', 'COMAR'): (ComarIndividualExtractor, {2023, 2024, 2025}),
}


def get_extractor(profile, years):
    config = profile.config
    entry = QUALIFIED.get((config['extractor'], config['company']))
    if entry and set(years) <= entry[1]:
        return entry[0]()
    raise ValueError('No qualified extractor for this company and these years')
