"""Benchmark any premium reader against a frozen answer key, through the identity gate.

For every task the reader sees only the year's pages and the profile taxonomy,
never the answer key. Each proposed code is then classified:

- ``correct_admitted``: equals the expected answer and the gate admits it;
- ``correct_rejected``: right value the gate could not prove (lost coverage);
- ``wrong_admitted``: a **silent error**, the one outcome that must stay at zero;
- ``wrong_rejected``: a wrong value the gate caught;
- ``abstained``: an expected answer the reader did not propose;
- ``unconfirmed_admitted`` / ``unconfirmed_rejected``: proposals without an
  expected answer (open tasks). Admitted ones are candidate coverage gains that
  a human or an independent reference must still confirm; they are never
  counted as correct.
"""
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from time import monotonic

from ledger_orchestrator.evaluation.gate import DocumentIndex, verify_premiums
from ledger_orchestrator.extraction.core import read_pages
from ledger_orchestrator.profiles import local_path


def _load(root, cache, relative, expected_sha256=None):
    path = local_path(root, relative)
    if not path.is_file():
        return None
    pages, digest = read_pages(path, cache)
    if expected_sha256 and digest != expected_sha256:
        raise ValueError(f'{relative} changed since the answer key was frozen')
    return pages


def classify(expected, proposal, admitted):
    if expected is None:
        return 'unconfirmed_admitted' if admitted else 'unconfirmed_rejected'
    if proposal is None:
        return 'abstained'
    correct = Decimal(proposal['value']) == Decimal(expected['amount'])
    return ('correct' if correct else 'wrong') + ('_admitted' if admitted else '_rejected')


def summarize(rows):
    counts = Counter(r['status'] for r in rows)
    admitted_known = counts['correct_admitted'] + counts['wrong_admitted']
    expected = sum(counts[s] for s in ('correct_admitted', 'correct_rejected', 'wrong_admitted',
                                       'wrong_rejected', 'abstained'))
    return dict(counts=dict(sorted(counts.items())), expected_answers=expected,
                silent_errors=counts['wrong_admitted'],
                verified_recall=round(counts['correct_admitted'] / expected, 4) if expected else None,
                admitted_precision=round(counts['correct_admitted'] / admitted_known, 4) if admitted_known else None,
                unconfirmed_admitted=counts['unconfirmed_admitted'])


def run_reader(reader, key, root, cache):
    tasks, rows, seconds = [], [], 0.0
    usage = Counter()
    for task in key['tasks']:
        config = key['profiles'][task['profile_id']]['config']
        pages = _load(root, cache, task['source'], task['sha256'])
        if pages is None:
            tasks.append(dict(task_id=task['task_id'], status='source_missing'))
            continue
        following = f"{config['source_directory']}/{task['year'] + 1}.pdf"
        next_pages = _load(root, cache, following)
        start = monotonic()
        reading = reader.read(dict(task_id=task['task_id'], profile_id=task['profile_id'], year=task['year'],
                                   company=task['company']), pages, config)
        elapsed = monotonic() - start
        seconds += elapsed
        usage.update(reading.usage)
        verdict = verify_premiums(reading.proposals, DocumentIndex(pages), config['taxonomy'],
                                  config['rounding_tolerance_tnd'],
                                  DocumentIndex(next_pages) if next_pages else None)
        task_rows = []
        for code in sorted(set(task['expected']) | set(reading.proposals)):
            proposal = reading.proposals.get(code)
            decision = verdict['decisions'].get(code, dict(admitted=False, reasons=[]))
            status = classify(task['expected'].get(code), proposal, decision['admitted'])
            row = dict(task_id=task['task_id'], code=code, status=status,
                       expected=task['expected'].get(code, {}).get('amount'),
                       proposed=None if proposal is None else proposal['value'],
                       page=None if proposal is None else proposal.get('page'),
                       gate_reasons=decision['reasons'])
            if code in reading.perturbed:
                row['perturbation'] = reading.perturbed[code]
            task_rows.append(row)
        rows += task_rows
        tasks.append(dict(task_id=task['task_id'], task_status=task['status'], abstained=reading.abstained,
                          seconds=round(elapsed, 3), next_year_report=next_pages is not None,
                          checks=verdict['checks'], summary=summarize(task_rows)))
    perturbed = [r for r in rows if 'perturbation' in r]
    caught = Counter(r['perturbation'] for r in perturbed if not r['status'].endswith('_admitted'))
    injected = Counter(r['perturbation'] for r in perturbed)
    result = dict(reader=reader.name, summary=summarize(rows), seconds=round(seconds, 3), usage=dict(usage),
                  tasks=tasks, rows=rows)
    if perturbed:
        result['perturbations'] = {kind: dict(injected=n, caught=caught[kind], catch_rate=round(caught[kind] / n, 4))
                                   for kind, n in sorted(injected.items())}
    return result


def run_benchmark(key, readers, root, cache):
    return dict(answer_key=dict(sha256=key['sha256'], basis=key['basis'], tasks=len(key['tasks'])),
                created_at=datetime.now(timezone.utc).isoformat(),
                results=[run_reader(reader, key, Path(root), Path(cache)) for reader in readers])


def previous_answers(key):
    """(profile, year) -> expected answers, for the previous-year perturbation only."""
    return {(t['profile_id'], t['year']): t['expected'] for t in key['tasks']}
