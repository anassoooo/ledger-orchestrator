"""Usage:
  python -m ledger_orchestrator.evaluation coverage --root data [--workbook out.xlsx]
  python -m ledger_orchestrator.evaluation benchmark --root data --run outputs/<run_id>
"""
import argparse
import json
from pathlib import Path

from ledger_orchestrator.evaluation.benchmark import benchmark
from ledger_orchestrator.evaluation.coverage_matrix import coverage_matrix

TEMPLATE = 'templates/TAF_G1_G2_G3_G4.xlsx'


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', choices=['coverage', 'benchmark'])
    parser.add_argument('--root', type=Path, default=Path('data'))
    parser.add_argument('--workbook', type=Path)
    parser.add_argument('--run', type=Path, help='Run folder containing report.json')
    parser.add_argument('--full', action='store_true', help='Print every row, not only summaries')
    args = parser.parse_args()
    template = args.root / TEMPLATE
    if args.command == 'coverage':
        result = coverage_matrix(template, args.root / 'sources', args.workbook)
        if not args.full:
            result = dict(summary=result['summary'], basis=result['basis'],
                          by_company=_by_company(result['rows']))
    else:
        if args.run is None:
            parser.error('benchmark requires --run')
        report = json.loads((args.run / 'report.json').read_text(encoding='utf-8'))
        result = benchmark(report, template)
        if args.run.is_dir():
            (args.run / 'benchmark.json').write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
        if not args.full:
            result = {k: v for k, v in result.items() if k not in ('template', 'cga')} | dict(
                template=result['template']['summary'], cga_defined=result['cga']['summary_defined'],
                cga_all=result['cga']['summary_all'],
                differences=[r for r in result['template']['rows'] + result['cga']['rows'] if r['status'] == 'differ'])
    print(json.dumps(result, indent=2, ensure_ascii=False))


def _by_company(rows):
    grouped = {}
    for r in rows:
        entry = grouped.setdefault(f"{r['sheet']} {r['company']}", dict(input_cells=0, filled=0, sourced_years=[]))
        entry['input_cells'] += r['input_cells']
        entry['filled'] += r['filled']
        if r['source']:
            entry['sourced_years'].append(r['year'])
    return grouped


if __name__ == '__main__':
    main()
