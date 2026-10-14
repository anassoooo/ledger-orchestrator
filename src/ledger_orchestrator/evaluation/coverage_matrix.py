"""Template-wide coverage: what is asked, what has a source, what is filled.

This is the project's north-star view (constitution, metric 1). It counts
template *input* cells; cells that already hold a formula in the template are
reported as derived and excluded from the denominators.
"""
from collections import defaultdict
from pathlib import Path

import openpyxl

from ledger_orchestrator.evaluation.template_map import source_directory, target_cells


def source_availability(sources_root: Path, company: str, year: int):
    """A year is covered by its own statement, or by the N-1 column of the next one."""
    folder = sources_root / source_directory(company)
    if (folder / f'{year}.pdf').is_file():
        return 'statement'
    if (folder / f'{year + 1}.pdf').is_file():
        return 'comparative_only'
    return None


def _filled(cell):
    # Workbooks are read with cached values: a guarded total that evaluates to
    # "" is not filled. Pipeline outputs are recalculated by LibreOffice.
    return type(cell.value) in (int, float) and type(cell.value) is not bool


def coverage_matrix(template: Path, sources_root: Path, workbook: Path | None = None):
    template_book = openpyxl.load_workbook(template)
    targets = target_cells(template_book)
    filled_book = openpyxl.load_workbook(workbook, data_only=True) if workbook else template_book
    groups = defaultdict(lambda: dict(input_cells=0, derived_cells=0, filled=0, prefilled=0))
    for target in targets:
        key = (target.sheet, target.company, target.year)
        group = groups[key]
        if target.derived:
            group['derived_cells'] += 1
            continue
        group['input_cells'] += 1
        if type(template_book[target.sheet][target.cell].value) in (int, float):
            group['prefilled'] += 1
        if _filled(filled_book[target.sheet][target.cell]):
            group['filled'] += 1
    rows = []
    for (sheet, company, year), group in sorted(groups.items()):
        rows.append(dict(sheet=sheet, company=company, year=year,
                         source=source_availability(sources_root, company, year), **group))
    return dict(rows=rows, summary=_summary(rows),
                basis='Template input cells of TAF_G1/G2/G3; formula cells excluded; '
                      'a filled cell is not necessarily a verified cell.')


def _summary(rows):
    summary = {}
    for row in rows:
        entry = summary.setdefault(row['sheet'], dict(input_cells=0, with_source=0, filled=0,
                                                      filled_with_source=0, prefilled=0))
        entry['input_cells'] += row['input_cells']
        entry['prefilled'] += row['prefilled']
        entry['filled'] += row['filled']
        if row['source']:
            entry['with_source'] += row['input_cells']
            entry['filled_with_source'] += row['filled']
    for entry in summary.values():
        entry['coverage_of_sourced'] = (round(entry['filled_with_source'] / entry['with_source'], 4)
                                        if entry['with_source'] else None)
    return summary
