"""Freeze a benchmark answer key from reference runs (TAF_G3 premium history).

A task is one company-year with its source document. Its expected answers are
the facts the reference run *admitted* from that year's own publication: values
that passed the identities of D-007. That makes them identity-verified answers
produced by the deterministic readers, not an independent human reference;
the key says so in its ``basis`` and each task keeps its run, page and SHA-256.

Years the readers rejected become *open* tasks: no expected answer, only the
rejection reason. They are where a new reader can gain coverage, and where it
is scored by the gate alone, never by agreement.

The key contains amounts read from public reports and nothing from the CMF
template, but it stays local like every other output (articles XI, D-010).
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

SCHEMA_VERSION = 1
BASIS = ('Expected answers are facts admitted by identity-verified deterministic reference runs '
         '(D-007), from the year\'s own publication. They are not an independent human reference.')


def _fingerprint(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


def build_answer_key(reports):
    """``reports``: report.json dicts of premium-history runs, one per profile."""
    profiles, tasks, runs = {}, [], []
    for report in reports:
        if report.get('kind') != 'premium_history':
            raise ValueError(f"Only premium-history runs are benchmarked in this version: {report.get('run_id')}")
        if report.get('status') not in ('completed', 'needs_review'):
            raise ValueError(f"Reference run did not finish: {report.get('run_id')}")
        config = report['config']
        identifier = config['profile_id']
        if identifier in profiles:
            raise ValueError(f'Two reference runs for profile {identifier}')
        profiles[identifier] = dict(sha256=report['profile']['sha256'], config=config)
        runs.append(dict(run_id=report['run_id'], profile_id=identifier))
        rejected = {i['year']: i['reason'] for i in report['issues'] if i['type'] == 'premium_history_rejected'}
        expected = {}
        # The history pipeline approves branch members only; the non-life total and
        # the excluded categories (acceptations) took part in the same partition
        # identity, so they are expected answers whenever that identity admitted the year.
        # Likewise the life categories took part in the annex 12 identity that admitted TOTAL_VIE.
        partition_codes = {'TOTAL_NONVIE', *config['taxonomy']['excluded']}
        current = [f for f in report['facts'] if f['evidence']['document_year'] == f['year']]
        partitioned = {f['year'] for f in current if f['approved'] and f['code'] != 'TOTAL_VIE'}
        life_admitted = {f['year'] for f in current if f['approved'] and f['code'] == 'TOTAL_VIE'}
        for fact in current:
            evidence = fact['evidence']
            implied = ((fact['code'] in partition_codes and fact['year'] in partitioned) or
                       (fact['code'].startswith('VIE_') and fact['year'] in life_admitted))
            if fact['approved'] or implied:
                expected.setdefault(fact['year'], {})[fact['code']] = dict(
                    amount=fact['target_amount'], page=evidence['page'], method=evidence['method'],
                    source_unit=evidence['source_unit'],
                    admitted_by='branch identity' if fact['approved'] else 'partition identity')
        for year in report['years']:
            document = report['documents'].get(str(year))
            if document is None:
                continue
            answers = expected.get(year, {})
            # partial: e.g. life total admitted, non-life annex not found (ASTREE 2022-2024).
            status = ('solved' if {'TOTAL_NONVIE', 'TOTAL_VIE'} <= answers.keys() else
                      'partial' if answers else 'open')
            tasks.append(dict(task_id=f'{identifier}:{year}', profile_id=identifier, company=config['company'],
                              year=year, source=f"{config['source_directory']}/{year}.pdf",
                              sha256=document['sha256'], pages=document['pages'], status=status,
                              reason=rejected.get(year), reference_run=report['run_id'],
                              issue_types=sorted({i['type'] for i in report['issues'] if i.get('year') == year}),
                              expected=dict(sorted(answers.items()))))
    tasks.sort(key=lambda t: (t['profile_id'], t['year']))
    body = dict(schema_version=SCHEMA_VERSION, basis=BASIS, runs=runs, profiles=profiles, tasks=tasks)
    return dict(body, created_at=datetime.now(timezone.utc).isoformat(), sha256=_fingerprint(body))


def load_answer_key(path):
    key = json.loads(Path(path).read_text(encoding='utf-8'))
    body = {k: v for k, v in key.items() if k not in ('created_at', 'sha256')}
    if key.get('schema_version') != SCHEMA_VERSION or _fingerprint(body) != key.get('sha256'):
        raise ValueError('Answer key is unknown or was modified after it was frozen')
    return key


def reports_from_consolidation(folder):
    """The premium-history runs of a consolidated reference (consolidation.json)."""
    summary = json.loads((Path(folder) / 'consolidation.json').read_text(encoding='utf-8'))
    output = Path(folder).parent
    return [json.loads((output / r['run_id'] / 'report.json').read_text(encoding='utf-8'))
            for r in summary['runs'] if r.get('kind') == 'premium_history']
