"""Usage:
  python -m ledger_orchestrator.evaluation coverage --root data [--workbook out.xlsx]
  python -m ledger_orchestrator.evaluation benchmark --root data --run outputs/<run_id>
  python -m ledger_orchestrator.evaluation answer-key --consolidation outputs/consolidated_<id> [--key KEY]
  python -m ledger_orchestrator.evaluation harness [--key KEY] [--readers deterministic abstain perturbed]
  python -m ledger_orchestrator.evaluation models                      (Groq models available to your key)
  python -m ledger_orchestrator.evaluation harness --readers groq --model <id> [--tasks star_] [--replay]
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from ledger_orchestrator.evaluation.answer_key import build_answer_key, load_answer_key, reports_from_consolidation
from ledger_orchestrator.evaluation.benchmark import benchmark
from ledger_orchestrator.evaluation.coverage_matrix import coverage_matrix
from ledger_orchestrator.evaluation.harness import previous_answers, run_benchmark
from ledger_orchestrator.evaluation.model_reader import CallRecorder, ChatClient, ModelReader
from ledger_orchestrator.evaluation.readers import (PERTURBATIONS, AbstainReader, DeterministicReader,
                                                    PerturbedReader)

TEMPLATE = 'templates/TAF_G1_G2_G3_G4.xlsx'
KEY = Path('outputs/benchmark/answer_key_premiums.json')


def readers(names, key, args=None):
    result = []
    for name in names:
        if name == 'groq':
            recorder = CallRecorder(args.key.parent / 'calls', 'replay' if args.replay else 'record')
            result.append(ModelReader(ChatClient('groq', args.model), recorder))
        elif name == 'deterministic':
            result.append(DeterministicReader())
        elif name == 'abstain':
            result.append(AbstainReader())
        elif name == 'perturbed':
            result += [PerturbedReader(DeterministicReader(), kind, previous_answers(key)) for kind in PERTURBATIONS]
        else:
            raise ValueError(f'Unknown reader: {name}')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', choices=['coverage', 'benchmark', 'answer-key', 'harness', 'models'])
    parser.add_argument('--model', help='Provider model identifier for a model reader (harness)')
    parser.add_argument('--replay', action='store_true', help='Replay recorded model calls only; no network')
    parser.add_argument('--tasks', nargs='+', help='Only tasks whose identifier contains one of these strings')
    parser.add_argument('--root', type=Path, default=Path('data'))
    parser.add_argument('--workbook', type=Path)
    parser.add_argument('--run', type=Path, help='Run folder containing report.json')
    parser.add_argument('--consolidation', type=Path, help='Consolidated reference folder (answer-key)')
    parser.add_argument('--key', type=Path, default=KEY, help='Frozen answer key (answer-key, harness)')
    parser.add_argument('--cache', type=Path, default=Path('outputs/cache'), help='Page cache (harness)')
    parser.add_argument('--readers', nargs='+', default=['deterministic', 'abstain', 'perturbed'])
    parser.add_argument('--full', action='store_true', help='Print every row, not only summaries')
    args = parser.parse_args()
    template = args.root / TEMPLATE
    if args.command == 'answer-key':
        if args.consolidation is None:
            parser.error('answer-key requires --consolidation')
        key = build_answer_key(reports_from_consolidation(args.consolidation))
        args.key.parent.mkdir(parents=True, exist_ok=True)
        args.key.write_text(json.dumps(key, indent=2, ensure_ascii=False), encoding='utf-8')
        statuses = {}
        for task in key['tasks']:
            statuses[task['status']] = statuses.get(task['status'], 0) + 1
        result = dict(key=str(args.key), sha256=key['sha256'], tasks=len(key['tasks']), by_status=statuses,
                      expected_answers=sum(len(t['expected']) for t in key['tasks']))
    elif args.command == 'models':
        result = dict(provider='groq', models=ChatClient('groq', 'listing').models())
    elif args.command == 'harness':
        key = load_answer_key(args.key)
        if 'groq' in args.readers and not args.model:
            parser.error('the groq reader needs --model (list them with: evaluation models)')
        if args.tasks:
            # A subset run reports its scope; the key itself stays frozen and complete.
            key = dict(key, tasks=[t for t in key['tasks'] if any(s in t['task_id'] for s in args.tasks)])
        result = run_benchmark(key, readers(args.readers, key, args), args.root, args.cache)
        folder = args.key.parent / ('harness_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S'))
        folder.mkdir(parents=True)
        (folder / 'results.json').write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
        if not args.full:
            result = dict(folder=str(folder), answer_key=result['answer_key'], results=[
                {k: r[k] for k in ('reader', 'summary', 'seconds', 'usage', 'perturbations') if k in r}
                | dict(abstentions={t['task_id']: t['abstained'] for t in r.get('tasks', []) if t.get('abstained')})
                for r in result['results']])
    elif args.command == 'coverage':
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
