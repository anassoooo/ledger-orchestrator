"""Admit a scanned subtotal only with native children and a native comparative."""


def corroborate_subtotals(candidates,current,prior,children,tolerance=3):
    accepted={}
    for code,candidate in candidates.items():
        # Bounded reviewed profile: financial placements, not arbitrary OCR leaves.
        if code!='AC33' or code in current['records'] or candidate.get('ambiguous'):
            continue
        previous=prior.get('records',{}).get(code)
        if (not previous or previous.get('method')!='native' or
                code not in prior['validation']['eligible'] or
                candidate.get('previous')!=previous['value']):
            continue
        disclosed=[c for c in children[code] if c in current['records']]
        if not disclosed:
            continue
        details=[current['records'][c] for c in disclosed]
        if any(r['method']!='native' or r.get('ambiguous') or r['code'] not in current['validation']['eligible'] for r in details):
            continue
        total=sum(r['value'] for r in details)
        delta=total-candidate['value']
        # Exact match for this OCR proof, stricter than the ordinary rounding gate.
        if delta!=0 or candidate.get('unit')!='TND' or candidate.get('year')!=2025:
            continue
        record=dict(candidate)
        record['subtotal_corroboration']=dict(rule='native_children_and_native_prior_v1',
            children=details,computed=total,delta=delta,prior_source=previous,
            omitted_children=[c for c in children[code] if c not in disclosed])
        accepted[code]=record
    return accepted
