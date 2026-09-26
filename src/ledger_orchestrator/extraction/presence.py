"""Distinguish absence in verified native balance pages from OCR non-detection."""
import re
from ledger_orchestrator.extraction.core import lines,normalize


def native_balance_presence(pages,year,source,codes):
    groups={'asset':[],'liability':[]}
    for page in pages[:5]:
        if page['method']!='native':
            continue
        text=normalize(page['text'])
        dates=re.findall(r'31\s*/\s*12\s*/\s*(20\d\d)',text)
        if dates[-2:]!=[str(year),str(year-1)]:
            continue
        found={}
        for row in lines(page['words']):
            label=' '.join(w['text'] for w in row)
            match=re.match(r'^(AC|CP|PA)\s*(\d{1,3})\b',normalize(label))
            if match:
                found[match[1]+match[2]]=dict(label=label,bbox=[row[0]['x0'],row[0]['top'],row[-1]['x1'],max(w['bottom'] for w in row)])
        if len(found)<8:
            continue
        kind='asset' if sum(c.startswith('AC') for c in found)>sum(c.startswith('PA') for c in found) else 'liability'
        groups[kind].append(dict(source=source,page=page['page'],method='native',codes=found))
    result={}
    for code in codes:
        if not re.fullmatch(r'(AC|CP|PA)\d+',code):
            continue
        evidence=groups['asset' if code.startswith('AC') else 'liability']
        # A single unambiguous verified statement page, not partial multi-page coverage.
        if len(evidence)!=1:
            continue
        statement=evidence[0]
        result[code]=dict(status='present' if code in statement['codes'] else 'absent_on_native_balance_page',
                          source=source,page=statement['page'],method='native',
                          observed_codes=sorted(statement['codes']),row=statement['codes'].get(code))
    return result
