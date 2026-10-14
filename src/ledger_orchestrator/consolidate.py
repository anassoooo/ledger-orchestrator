"""Fill one copy of the template with several companies, one profile at a time.

Each profile runs the full five-agent pipeline on the workbook produced by the
previous one. Isolation does not rely on trust: the writer refuses to change any
cell outside the profile's own targets, and this module then checks that the
final workbook contains every run's writes unchanged and that no two runs wrote
the same cell (constitution, articles VIII and IX).

Usage: python -m ledger_orchestrator.consolidate --configs config/star.json config/comar.json
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import uuid

import openpyxl

from ledger_orchestrator.pipeline import execute, save_json

FILENAME = 'TAF_consolide.xlsx'


def consolidate(root, output, config_paths):
    if not config_paths:
        raise ValueError('At least one profile is required')
    folder = output / ('consolidated_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '_' + uuid.uuid4().hex[:8])
    folder.mkdir(parents=True)
    runs, base = [], None
    for config_path in config_paths:
        report = execute(root, output, Path(config_path), base_workbook=base)
        base = output / report['run_id'] / report['workbook']
        runs.append(dict(run_id=report['run_id'], company=report['company'], status=report['status'],
                         profile=report['profile'], workbook=str(base), writes=report['writes'],
                         confirmations=len(report.get('confirmations', [])),
                         conflicts=sum(i['type'] == 'existing_cell_conflict' for i in report['issues'])))
    final = folder / FILENAME
    shutil.copyfile(base, final)
    checks = verify_union(final, runs)
    result = dict(workbook=FILENAME, sha256=hashlib.sha256(final.read_bytes()).hexdigest(),
                  runs=[{k: v for k, v in r.items() if k != 'writes'} | dict(writes=len(r['writes'])) for r in runs],
                  checks=checks, passed=all(checks.values()))
    save_json(folder / 'consolidation.json', result)
    if not result['passed']:
        raise RuntimeError(f'Consolidation checks failed: {checks}')
    return folder, result


def verify_union(final, runs):
    workbook = openpyxl.load_workbook(final)
    owners, preserved, disjoint = {}, True, True
    for run in runs:
        for write in run['writes']:
            key = (write['sheet'], write['cell'])
            if key in owners:
                disjoint = False
            owners[key] = run['company']
            if workbook[write['sheet']][write['cell']].value != write['new']:
                preserved = False
    return dict(every_write_preserved=preserved, no_cell_written_twice=disjoint,
                companies_distinct=len({r['company'] for r in runs}) == len(runs))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--root', type=Path, default=Path(os.getenv('CMF_ROOT', 'data')))
    parser.add_argument('--output', type=Path, default=Path(os.getenv('CMF_OUTPUT', 'outputs')))
    parser.add_argument('--configs', nargs='+', required=True)
    args = parser.parse_args()
    folder, result = consolidate(args.root, args.output, args.configs)
    print(json.dumps(dict(folder=folder.name, **{k: result[k] for k in ('passed', 'checks', 'runs')}),
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
