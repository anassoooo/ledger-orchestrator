"""Cross-check OCR premiums against native gross totals and category identities."""
import re
from ledger_orchestrator.extraction.core import normalize,lines,numeric_groups

ORDER=['GROUPE','A_TRAVAIL','INCENDIE','RISQUES_DIVERS','TRANSPORT','AVIATION','AUTOMOBILE','ACCEPTATION','TOTAL_NONVIE']
ALIASES=[['GROUPE'],['A.TRAVAIL'],['INCENDIE'],['RISQUES','RISQUESDIVERS'],
         ['TRANSPORT'],['AVIATION'],['AUTO','AUTOMOBILE'],['ACCEPTATION'],['TOTAL']]


def evidence(row,page,source):
    return dict(source=source,page=page['page'],method=page['method'],
                source_label=' '.join(w['text'] for w in row),
                bbox=[row[0]['x0'],min(w['top'] for w in row),row[-1]['x1'],max(w['bottom'] for w in row)])


def corroborate_premiums(pages,records,year,source,tolerance=3):
    if any(k not in records for k in ORDER):
        return []
    page_ids={records[k]['page'] for k in ORDER}
    if len(page_ids)!=1:
        return [dict(type='premium_evidence_mixed_pages')]
    page=next(p for p in pages if p['page']==next(iter(page_ids)))
    if page['method']!='ocr':
        return []
    text=normalize(page['text'])
    if f'31/12/{year}' not in text or 'DINAR' not in text or 'MILLIER' in text:
        return [dict(type='premium_evidence_header_unverified')]
    vectors={}
    proofs=[]
    rowlist=lines(page['words'])
    for index,row in enumerate(rowlist):
        label=normalize(' '.join(w['text'] for w in row))
        key=next((key for key,prefix in [('acquired','PRIMES ACQUISES'),('variation','VARIATION DES PRIMES NON ACQUISES')]
                  if label.startswith(prefix)),None)
        if key is None:
            continue
        vals=numeric_groups([w for w in row if w['x0']>page['width']*.20],page['width'])
        numeric_row=row
        if not vals and index+1<len(rowlist) and rowlist[index+1][0]['top']-row[0]['top']<20:
            numeric_row=rowlist[index+1]
            vals=numeric_groups(numeric_row,page['width'])
        if len(vals)==9:
            if key in vectors:
                return [dict(type='premium_evidence_duplicate_row',code=key)]
            vectors[key]=[v[0] for v in vals]
            proofs.append(evidence(row+numeric_row,page,source))
    if set(vectors)!={'acquired','variation'}:
        return [dict(type='premium_evidence_rows_missing')]
    # Confirm category headers are in the expected horizontal order, not merely present.
    centers=[(records[k]['bbox'][0]+records[k]['bbox'][2])/2 for k in ORDER]
    if centers!=sorted(centers) or len(set(centers))!=9:
        return [dict(type='premium_evidence_column_order')]
    header_words=[w for w in page['words'] if w['bottom']<records['GROUPE']['bbox'][1]]
    for index,aliases in enumerate(ALIASES):
        left=(centers[index-1]+centers[index])/2 if index else page['width']*.2
        right=(centers[index]+centers[index+1])/2 if index<8 else page['width']
        if not any(normalize(w['text']).strip(' ., :|') in aliases and
                   left<=(w['x0']+w['x1'])/2<=right for w in header_words):
            return [dict(type='premium_evidence_column_header',code=ORDER[index])]
    native=[]
    for p in pages:
        t=normalize(p['text'])
        if p['method']!='native' or 'OPERATIONS' not in t or 'BRUTES' not in t or 'DINAR' not in t or 'MILLIER' in t:
            continue
        if f'31/12/{year}' not in t:
            continue
        for row in lines(p['words']):
            label=normalize(' '.join(w['text'] for w in row))
            if not re.search(r'\bPRNV1\b',label) or 'PRIMES EMISES' not in label:
                continue
            vals=numeric_groups(row,p['width'])
            if len(vals)==4 and abs(vals[0][0]-vals[1][0]-vals[2][0])<=tolerance:
                native.append(dict(value=vals[0][0],**evidence(row,p,source)))
    issued=[records[k]['value'] for k in ORDER]
    if not native or any(p['value']!=issued[-1] for p in native):
        return [dict(type='premium_evidence_native_total_unverified')]
    checks=[]
    for name,vector in [('issued',issued),*vectors.items()]:
        delta=sum(vector[:-1])-vector[-1]
        checks.append(dict(kind='row_total',row=name,delta=delta,status='passed' if abs(delta)<=tolerance else 'blocked'))
    for index,code in enumerate(ORDER):
        delta=issued[index]+vectors['variation'][index]-vectors['acquired'][index]
        checks.append(dict(kind='issued_plus_variation_equals_acquired',code=code,delta=delta,
                           status='passed' if abs(delta)<=tolerance else 'blocked'))
    if any(c['status']!='passed' for c in checks):
        return [dict(type='premium_evidence_reconciliation_failed',checks=checks)]
    for code in ORDER:
        records[code]['corroboration']=dict(rule='native_gross_total_and_category_identities_v1',
                                          native_sources=native,ocr_sources=proofs,checks=checks)
    return []
