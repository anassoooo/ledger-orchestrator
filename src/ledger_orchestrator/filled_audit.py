"""Audit saved writes and formula caches without changing the workbook.

This checks internal integrity, not independent correctness of PDF transcription.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import openpyxl


def formula_refs(formula,sheet):
    match=re.fullmatch(r'=IF\(COUNT\((.+)\)=(\d+),SUM\((.+)\),""\)',formula)
    if not match or match[1]!=match[3]:
        raise ValueError('Unsupported formula or different COUNT/SUM inputs')
    refs=[]
    for token in match[1].split(','):
        m=re.fullmatch(r"(?:'([^']+)'!)?([A-Z]+[1-9][0-9]*)",token)
        if not m:
            raise ValueError('Unsupported reference')
        refs.append((m[1] or sheet,m[2]))
    if len(refs)!=int(match[2]) or len(set(refs))!=len(refs):
        raise ValueError('Wrong COUNT guard or duplicate reference')
    return refs


def audit(workbook,report,diagnostics=None):
    before=hashlib.sha256(workbook.read_bytes()).hexdigest()
    formulas=openpyxl.load_workbook(workbook,data_only=False)
    values=openpyxl.load_workbook(workbook,data_only=True)
    rows=[]
    index={}
    def evaluate(key,stack=()):
        if key in stack:
            raise ValueError('Circular reference')
        value=formulas[key[0]][key[1]].value
        if isinstance(value,str) and value.startswith('='):
            numbers=[evaluate(ref,(*stack,key)) for ref in formula_refs(value,key[0])]
            return sum(numbers) if all(type(n) in (int,float) for n in numbers) else None
        return value
    for w in report['writes']:
        key=(w['sheet'],w['cell'])
        actual=formulas[key[0]][key[1]].value
        cached=values[key[0]][key[1]].value
        errors=[]
        warnings=[]
        refs=[]
        if key in index:
            errors.append('duplicate_write')
        if actual!=w['new']:
            errors.append('workbook_report_mismatch')
        is_formula=isinstance(actual,str) and actual.startswith('=')
        expected=None
        if is_formula:
            try:
                refs=formula_refs(actual,key[0])
                expected=evaluate(key)
                if (cached or None)!=(expected or None) or (cached==0)!=(expected==0):
                    errors.append('formula_cache_mismatch')
            except ValueError as exc:
                errors.append(str(exc))
        sources=w.get('sources',[])
        if not is_formula:
            if not sources:
                errors.append('missing_provenance')
            else:
                expected=sum(s['value'] for s in sources)
                if actual!=expected:
                    errors.append('source_value_mismatch')
        for source in sources:
            if not source.get('approved'):
                errors.append('unapproved_source')
            if source.get('ambiguous'):
                errors.append('ambiguous_source')
            if source.get('unit')!='TND' or source.get('conversion_factor')!=1:
                errors.append('unit_or_conversion_unverified')
            if not source.get('page') or not source.get('source'):
                errors.append('missing_source_location')
            if any(c.get('status')!='passed' for c in source.get('note_checks',[])):
                errors.append('failed_source_check')
        if is_formula and sources and expected is not None:
            if abs(expected-sources[0]['value'])>report['config']['rounding_tolerance_tnd']:
                errors.append('published_total_mismatch')
        for issue in report['issues']:
            if issue.get('year')==w['year'] and issue.get('code')==w['code'] and issue['type']=='comparative_difference':
                warnings.append('comparative_difference')
        for finding in (diagnostics or {}).get('findings',[]):
            year=2024 if finding.get('column')=='previous' else 2025
            if finding['kind']=='ocr_native_disagreement' and w['year']==year and w['code']==finding['code'] and w['sheet']!='TAF_G3':
                warnings.append('ocr_native_disagreement_not_confirmed')
        row=dict(sheet=w['sheet'],cell=w['cell'],year=w['year'],code=w['code'],
                 value=cached,formula=actual if is_formula else None,
                 errors=errors,warnings=warnings,dependencies=[list(r) for r in refs],
                 source_locations=[dict(file=s.get('source'),page=s.get('page'),method=s.get('method')) for s in sources],
                 independent_pdf_review='pending')
        rows.append(row)
        index[key]=row
    # A flagged input affects its totals even if the arithmetic itself is correct.
    changed=True
    while changed:
        changed=False
        for row in rows:
            if any(index.get(tuple(k),{}).get('warnings') or index.get(tuple(k),{}).get('errors') for k in row['dependencies']):
                if 'dependency_requires_review' not in row['warnings']:
                    row['warnings'].append('dependency_requires_review')
                    changed=True
    formulas.close()
    values.close()
    if hashlib.sha256(workbook.read_bytes()).hexdigest()!=before:
        raise RuntimeError('Workbook changed during read-only audit')
    return dict(workbook_sha256=before,source_run=report['run_id'],
                scope='Recorded writes including STAR_Details; not a PDF accuracy certificate',
                audited_writes=len(rows),integrity_errors=sum(bool(r['errors']) for r in rows),
                review_flags=sum(bool(r['warnings']) for r in rows),
                formulas=sum(bool(r['formula']) for r in rows),cells=rows)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('run',type=Path)
    p.add_argument('--diagnostic',type=Path)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    report=json.loads((args.run/'report.json').read_text(encoding='utf-8'))
    diagnostic=json.loads(args.diagnostic.read_text(encoding='utf-8')) if args.diagnostic else None
    if diagnostic and diagnostic['source_run']!=report['run_id']:
        raise ValueError('Diagnostic belongs to another run')
    result=audit(args.run/report['workbook'],report,diagnostic)
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'audit_cellules.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# Audit des cellules remplies','',
           f"Écritures contrôlées : {result['audited_writes']} (détails complémentaires inclus).",
           f"Formules recalculées séparément : {result['formulas']}.",
           f"Cellules avec erreurs de transfert, de preuve ou de calcul : {result['integrity_errors']}.",
           f"Cellules avec alertes de revue, dépendances incluses : {result['review_flags']}.",'',
           'Ce passage contrôle la cohérence interne. La vérification indépendante des PDF reste à effectuer.',
           'Les alertes OCR ne sont pas des erreurs comptables confirmées. Le classeur est inchangé.','',
           '| Exercice | Feuille | Cellule | Rubrique | Alertes |','| --- | --- | --- | --- | --- |']
    for r in result['cells']:
        if r['errors'] or r['warnings']:
            lines.append(f"| {r['year']} | {r['sheet']} | {r['cell']} | {r['code']} | {', '.join(r['errors']+r['warnings'])} |")
    lines+=['','Les 255 écritures ne sont pas 255 montants indépendants. Les 233 cellules cibles remplies excluent STAR_Details.',
            'Détail de chaque écriture et des références sources : audit_cellules.json.','']
    (args.output/'AUDIT_CELLULES.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='cells'}))


if __name__=='__main__':
    main()
