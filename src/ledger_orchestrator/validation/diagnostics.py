"""Read-only triage of OCR candidates. Never approve or write financial values."""
import argparse
import hashlib
import json
from pathlib import Path


def diagnose_candidates(candidates, current, prior, children, tolerance=3):
    findings=[]
    for code, candidate in sorted(candidates.items()):
        for column, reference in [('value',current.get(code)),('previous',prior.get(code))]:
            if (not reference or reference.get('method')!='native' or
                    reference.get('ambiguous') or candidate.get(column) is None or
                    candidate.get('unit')!='TND' or reference.get('unit')!='TND'):
                continue
            delta=candidate[column]-reference['value']
            if abs(delta)>tolerance:
                findings.append(dict(kind='ocr_native_disagreement',code=code,column=column,
                    candidate=candidate[column],reference=reference['value'],delta=delta,
                    candidate_evidence=candidate,reference_evidence=reference,
                    conclusion='Lecture OCR à vérifier ; aucune correction ni qualification automatique d’erreur source.'))
    for parent, codes in children.items():
        reference=current.get(parent)
        if not reference or reference.get('method')!='native' or reference.get('ambiguous') or reference.get('unit')!='TND':
            continue
        present=[code for code in codes if code in candidates]
        # An incomplete subset cannot establish a mismatch of the full family.
        if len(present)!=len(codes) or not present:
            continue
        if any(candidates[c].get('unit')!='TND' or candidates[c].get('value') is None for c in present):
            continue
        total=sum(candidates[c]['value'] for c in present)
        delta=total-reference['value']
        findings.append(dict(kind='ocr_family_check',code=parent,column='value',
            candidate=total,reference=reference['value'],delta=delta,
            status='matched' if abs(delta)<=tolerance else 'blocked',
            candidate_evidence={c:candidates[c] for c in present},reference_evidence=reference,
            conclusion='Une concordance de somme ne valide pas les détails OCR individuellement.'))
    return findings


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report',type=Path)
    parser.add_argument('cache',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    report=json.loads(args.report.read_text(encoding='utf-8'))
    digest=report['documents']['2025']['sha256']
    cache=args.cache/f'{digest}-cell-v1.json'
    candidates=json.loads(cache.read_text(encoding='utf-8'))['records']
    findings=diagnose_candidates(candidates,report['data']['2025']['records'],
        report['data']['2024']['records'],report['config']['children'])
    args.output.mkdir(parents=True,exist_ok=True)
    result=dict(source_run=report['run_id'],source_sha256=digest,
        report_sha256=hashlib.sha256(args.report.read_bytes()).hexdigest(),
        financial_writes=0,findings=findings)
    (args.output/'diagnostic_ocr.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# Diagnostic des lectures OCR STAR 2025','',
        'Diagnostic uniquement : aucun montant ajouté au classeur. Les candidats OCR ne sont pas des montants validés.',
        '',f"Exécution examinée : {report['run_id']}",'',
        '| Rubrique | Contrôle | Candidat OCR | Référence native | Écart (TND) |',
        '| --- | --- | ---: | ---: | ---: |']
    for f in findings:
        label='Somme des détails' if f['kind']=='ocr_family_check' else ('Comparatif 2024' if f['column']=='previous' else 'Montant 2025')
        lines.append(f"| {f['code']} | {label} | {f['candidate']:,.0f} | {f['reference']:,.0f} | {f['delta']:+,.0f} |")
    lines+=['','Les écarts peuvent provenir de l’OCR ou du document. Comparer les pages avant arbitrage.',
        'Une somme concordante ne suffit pas à admettre les détails. Les preuves et coordonnées sont dans diagnostic_ocr.json.','']
    (args.output/'DIAGNOSTIC_OCR.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps(dict(findings=len(findings),financial_writes=0,output=str(args.output))))


if __name__=='__main__':
    main()
