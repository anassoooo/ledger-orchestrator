"""Premium history (TAF_G3, years without a TAF_G1 column): one company per profile.

Same five agents, same evidence contract and the same writer guards as the main
pipeline, restricted to the premium sheet. A year whose disclosures fail an
identity is reported with its reason and left blank; it never stops the others.

Usage: python -m ledger_orchestrator.history --config config/history/star_premiums.json
"""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import uuid

from ledger_orchestrator.extraction.core import normalize, read_pages
from ledger_orchestrator.extraction.premium_annex import AnnexError, read_premiums
from ledger_orchestrator.orchestration import Agent, AgentResult, Orchestrator
from ledger_orchestrator.pipeline import exclusive_lock, save_json
from ledger_orchestrator.profiles import local_path
from ledger_orchestrator.records import FinancialFact, SourceEvidence, decimal_text
from ledger_orchestrator.workbook.premium_writer import HistoryProfile, write_premium_history


def execute_history(root, output, config_path, years=None, base_workbook=None):
    profile = HistoryProfile.load(config_path)
    config = profile.config
    years = profile.select_years(years)
    output.mkdir(parents=True, exist_ok=True)
    original = local_path(root, config['workbook']['template'])
    template = Path(base_workbook) if base_workbook else original
    template_digest = hashlib.sha256(original.read_bytes()).hexdigest()
    base_digest = hashlib.sha256(template.read_bytes()).hexdigest()
    tolerance = config['rounding_tolerance_tnd']
    with exclusive_lock(output):
        run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '_' + uuid.uuid4().hex[:8]
        folder = output / run_id
        folder.mkdir()
        report = dict(run_id=run_id, kind='premium_history', status='running', company=config['company'],
                      years=years, target_unit='TND', template_sha256=template_digest, config=config,
                      profile=dict(id=config['profile_id'], revision=config['revision'], sha256=profile.fingerprint),
                      documents={}, issues=[], writes=[], confirmations=[], agent_trace=[], schema_version=2)
        if base_workbook:
            report['base_workbook'] = dict(path=str(template), sha256=base_digest)
        save_json(folder / 'report.json', report)

        def event(item):
            report['agent_trace'].append(item)
            save_json(folder / 'report.json', report)

        def documents(_):
            result = {}
            for year in years:
                relative = profile.source_relative(year)
                pages, digest = read_pages(local_path(root, relative), output / 'cache')
                front = normalize(' '.join(p['text'] for p in pages[:3]))
                if not any(re.search(r'\b' + re.escape(normalize(t)) + r'\b', front) for t in config['identity_terms']):
                    raise ValueError(f'Source identity not confirmed: {relative}')
                result[year] = dict(pages=pages, digest=digest, source=relative)
                report['documents'][str(year)] = dict(sha256=digest, pages=len(pages),
                                                      ocr_pages=[p['page'] for p in pages if p['method'] == 'ocr'])
            return AgentResult(result, dict(documents=len(result)))

        def extraction(results):
            annual = {}
            for year, document in results['documents'].items():
                try:
                    records, checks = read_premiums(document['pages'], year, config['taxonomy'], tolerance)
                except AnnexError as exc:
                    report['issues'].append(dict(type='premium_history_rejected', year=year, reason=str(exc)))
                    continue
                for record in records.values():
                    record['source'] = document['source']
                    if record['method'] != 'native':
                        report['issues'].append(dict(type='premium_ocr_reading', year=year, code=record['code'],
                                                     corroborating_pages=record.get('corroborating_pages', [])))
                annual[year] = dict(records=records, checks=checks)
            return AgentResult(annual, dict(admitted_years=len(annual), rejected_years=len(years) - len(annual)))

        def validation(results):
            taxonomy = config['taxonomy']
            for year, data in results['extraction'].items():
                records = data['records']
                branches = {}
                for branch, codes in taxonomy['branches'].items():
                    present = [records[c] for c in codes if c in records]
                    if present:
                        branches[branch] = dict(value=sum(r['value'] for r in present), sources=present)
                excluded = sum(records[c]['value'] for c in taxonomy['excluded'] if c in records)
                if 'TOTAL_NONVIE' not in records:
                    report['issues'].append(dict(type='premium_nonlife_annex_not_published', year=year))
                    branches = {}
                else:
                    partition = sum(b['value'] for b in branches.values()) + excluded - records['TOTAL_NONVIE']['value']
                    if abs(partition) > tolerance or set(branches) != set(taxonomy['branches']):
                        report['issues'].append(dict(type='premium_partition_failed', year=year, delta=partition))
                        branches = {}
                    elif excluded:
                        report['issues'].append(dict(type='premium_unallocated', year=year, amount=excluded,
                                                     codes=taxonomy['excluded']))
                if 'TOTAL_VIE' in records:
                    branches['VIE'] = dict(value=records['TOTAL_VIE']['value'], sources=[records['TOTAL_VIE']])
                admitted = {id(s) for b in branches.values() for s in b['sources']}
                for record in records.values():
                    # OCR is admitted only when a native page prints the same amount.
                    corroborated = any(p['method'] == 'native' for p in record.get('corroborating_pages', []))
                    record['approved'] = id(record) in admitted and (record['method'] == 'native' or corroborated)
                for branch in branches.values():
                    if not all(s['approved'] for s in branch['sources']):
                        report['issues'].append(dict(type='premium_review_required', year=year))
                data['branches'] = branches
            report['facts'] = facts(results['extraction'], report['documents'], config)
            return AgentResult(results['extraction'], dict(years_with_branches=sum(
                bool(d['branches']) for d in results['extraction'].values())))

        def workbook(results):
            path = folder / config['workbook']['filename']
            writes, issues = write_premium_history(template, path, profile, results['validation'],
                                                   report['confirmations'])
            report['writes'] = writes
            report['issues'] += issues
            return AgentResult(path, dict(written_cells=len(writes)))

        def review(results):
            report['data'] = results['validation']
            report['coverage'] = profile.coverage(results['workbook'], years, report['writes'], report['issues'])
            report['review'] = [c for c in report['coverage']['cells'] if c['status'] == 'missing_or_blocked']
            return AgentResult(None, dict(review_cells=len(report['review'])))

        try:
            Orchestrator([Agent('documents', (), documents), Agent('extraction', ('documents',), extraction),
                          Agent('validation', ('extraction',), validation),
                          Agent('workbook', ('validation',), workbook),
                          Agent('review', ('validation', 'workbook'), review)], event).execute()
            if (hashlib.sha256(original.read_bytes()).hexdigest() != template_digest or
                    hashlib.sha256(template.read_bytes()).hexdigest() != base_digest):
                raise RuntimeError('Source template changed during execution')
            report['status'] = 'needs_review' if report['issues'] else 'completed'
            report['workbook'] = config['workbook']['filename']
            save_json(folder / 'report.json', report)
            return report
        except Exception as exc:
            report['status'] = 'failed'
            report['error'] = f'{type(exc).__name__}: {exc}'
            save_json(folder / 'report.json', report)
            raise


def facts(annual, documents, config):
    """The same canonical contract as the main pipeline, for premium readings."""
    result = []
    for year, data in sorted(annual.items()):
        document = documents[str(year)]
        for code, record in sorted(data['records'].items()):
            if record['year'] != year or record['code'] != code or not 1 <= record['page'] <= document['pages']:
                raise ValueError('Premium record identity or page is invalid')
            evidence = SourceEvidence(record['source'], document['sha256'], year, record['page'], record['method'],
                                      record['unit'], '1', record['bbox'], 'current')
            amount = decimal_text(record['value'])
            result.append(asdict(FinancialFact(1, config['company'], year, 'premiums', code, amount, amount,
                                               'TND', record.get('approved', False), evidence)))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--root', type=Path, default=Path(os.getenv('CMF_ROOT', 'data')))
    parser.add_argument('--output', type=Path, default=Path(os.getenv('CMF_OUTPUT', 'outputs')))
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--years', nargs='+', type=int)
    args = parser.parse_args()
    report = execute_history(args.root, args.output, args.config, args.years)
    print(json.dumps(dict(run_id=report['run_id'], status=report['status'], written_cells=len(report['writes']),
                          rejected={i['year']: i['reason'] for i in report['issues']
                                    if i['type'] == 'premium_history_rejected'}), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
