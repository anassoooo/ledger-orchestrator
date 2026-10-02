"""Canonical, JSON-safe financial facts emitted at the validation boundary."""

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
import math
import re


def decimal_text(value):
    if isinstance(value, bool):
        raise ValueError('A boolean is not a financial amount')
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError('Invalid financial amount') from exc
    if not result.is_finite():
        raise ValueError('Financial amounts must be finite')
    return format(result, 'f')


@dataclass(frozen=True)
class SourceEvidence:
    source: str
    sha256: str
    document_year: int
    page: int
    method: str
    source_unit: str | None
    conversion_factor: str
    bbox: list[float] | None
    column: str


@dataclass(frozen=True)
class FinancialFact:
    schema_version: int
    company: str
    year: int
    statement: str
    code: str
    source_amount: str
    target_amount: str | None
    target_unit: str
    approved: bool
    evidence: SourceEvidence


def canonical_facts(annual, documents, profile):
    """Check provenance/amount contracts before the workbook agent can execute.

    Amounts are decimal strings in this interchange schema; existing extraction
    records remain available in report.data. This is not an independent accuracy
    assessment or a new approval path.
    """
    declared = {profile.source_relative(int(year)): (int(year), document)
                for year, document in documents.items()}
    facts = []
    for year, data in sorted(annual.items()):
        for statement, records in (('balance', data['records']), ('premiums', data['raw_branches'])):
            for code, record in sorted(records.items()):
                if record.get('year') != year or record.get('code') != code:
                    raise ValueError('Financial record identity does not match its container')
                source = record.get('source')
                if source not in declared:
                    raise ValueError('Financial evidence references an undeclared document')
                document_year, document = declared[source]
                if not re.fullmatch(r'[a-f0-9]{64}', document['sha256']):
                    raise ValueError('Financial evidence requires a SHA-256 fingerprint')
                page = record.get('page')
                if type(page) is not int or not 1 <= page <= document['pages']:
                    raise ValueError('Financial evidence page is outside the source document')
                if document_year != year and not (
                    document_year == year + 1 and record.get('source_year') == document_year
                    and record.get('source_column') == 'previous'
                    and record.get('source_kind') == 'native_comparative'
                ):
                    raise ValueError('Unverified comparative period')
                amount = decimal_text(record['value'])
                factor = decimal_text(record.get('conversion_factor', 1))
                if Decimal(factor) != 1:
                    raise ValueError('Non-unit currency conversion is not qualified yet')
                approved = record.get('approved', False)
                if type(approved) is not bool:
                    raise ValueError('Approval must be an explicit boolean')
                if approved and (record.get('unit') != profile.config['target_unit']
                                 or record.get('ambiguous')
                                 or any(c['status'] != 'passed' for c in record.get('note_checks', []))):
                    raise ValueError('Approved record violates the evidence contract')
                method = record.get('method')
                if method not in ('native', 'ocr', 'ocr_cells'):
                    raise ValueError('Unknown evidence extraction method')
                bbox = record.get('bbox')
                if bbox is not None and (len(bbox) != 4 or any(
                    type(v) not in (int, float) or not math.isfinite(v) for v in bbox
                ) or bbox[0] > bbox[2] or bbox[1] > bbox[3]):
                    raise ValueError('Invalid evidence bounding box')
                evidence = SourceEvidence(source, document['sha256'], document_year, page, method,
                                          record.get('unit'), factor, bbox,
                                          record.get('source_column', 'current'))
                target_amount=amount if record.get('unit')==profile.config['target_unit'] else None
                facts.append(asdict(FinancialFact(1, profile.config['company'], year, statement, code,
                                                 amount, target_amount, profile.config['target_unit'], approved, evidence)))
    return facts
