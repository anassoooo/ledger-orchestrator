"""Evidence gates, independent published totals, and explicit coverage."""


def validate_balance(records, children, tolerance):
    checks=[]
    valid=set()
    dependencies={}
    computed={}
    for code, record in records.items():
        if (record.get('unit')=='TND' and not record.get('ambiguous') and
                all(c['status']=='passed' for c in record.get('note_checks',[]))):
            valid.add(code)
    def visit(code, stack=()):
        if code in computed:
            return computed[code]
        if code not in valid or code in stack:
            return None
        if code not in children:
            computed[code]=records[code]['value']
            return computed[code]
        # Only explicitly published child rows are included. An omitted row stays
        # missing, and the published parent independently proves numeric coverage.
        present=[c for c in children[code] if c in records]
        vals=[visit(c,(*stack,code)) for c in present]
        ok=bool(present) and all(v is not None for v in vals)
        total=sum(vals) if ok else None
        delta=total-records[code]['value'] if total is not None else None
        ok=ok and abs(delta)<=tolerance
        checks.append(dict(code=code,published=records[code]['value'],computed=total,delta=delta,
                           status='passed' if ok else 'blocked',children=present,
                           not_published=[c for c in children[code] if c not in records]))
        if ok:
            dependencies[code]=present
            computed[code]=total
            return total
        valid.discard(code)
        return None
    for code in list(records):
        visit(code)
    a,b=computed.get('TOTAL_ASSET'),computed.get('TOTAL_EQUITY_LIABILITY')
    balanced=a is not None and b is not None and abs(a-b)<=tolerance
    checks.append(dict(code='BALANCE',computed_asset=a,computed_equity_liability=b,status='passed' if balanced else 'blocked'))
    # Each detail needs a successfully reconciled parent, or the final balance.
    covered={c for kids in dependencies.values() for c in kids}
    eligible=(valid & covered) | set(dependencies)
    # Independently reconciled native-note leaves need not wait for an unreadable
    # parent. This does not bypass the required children of a configured subtotal.
    eligible.update(code for code in valid if code not in children and
                    records[code].get('note_checks') and
                    all(c['status']=='passed' for c in records[code]['note_checks']))
    return dict(checks=checks,computed=computed,dependencies=dependencies,eligible=sorted(eligible),balanced=balanced)


def validate_premiums(records, config):
    issues=[]
    if config['premium_basis']!='before_reinsurance' or config['branch_policy'] not in ('grouped','exact'):
        return {},[dict(type='premium_policy_unresolved')]
    expected=['GROUPE','A_TRAVAIL','INCENDIE','RISQUES_DIVERS','TRANSPORT','AVIATION','AUTOMOBILE','ACCEPTATION']
    total=records.get('TOTAL_NONVIE',{}).get('value')
    if total is None or any(k not in records for k in expected):
        issues.append(dict(type='premium_nonlife_incomplete'))
        return {},issues
    delta=sum(records[k]['value'] for k in expected)-total
    if abs(delta)>config['rounding_tolerance_tnd']:
        return {},[dict(type='premium_source_total_mismatch',delta=delta)]
    mapping={'AUTOMOBILE':['AUTOMOBILE'],'INCENDIE':['INCENDIE'],'TRANSPORT':['TRANSPORT'],
             'IRDS':['RISQUES_DIVERS'],'GROUPE':['GROUPE'],'VIE':['TOTAL_VIE']}
    if config['branch_policy']=='grouped':
        mapping['TRANSPORT'].append('AVIATION')
        mapping['IRDS'].append('A_TRAVAIL')
    out={}
    for key,codes in mapping.items():
        if all(c in records for c in codes):
            if key=='VIE':
                life=['VIE_EPARGNE','DECES','MIXTE']
                if 'ACCEPTATION_VIE' in records:
                    life.append('ACCEPTATION_VIE')
                if any(c not in records for c in life) or abs(sum(records[c]['value'] for c in life)-records['TOTAL_VIE']['value'])>config['rounding_tolerance_tnd']:
                    issues.append(dict(type='premium_life_total_mismatch'))
                    continue
            out[key]=dict(value=sum(records[c]['value'] for c in codes),sources=[records[c] for c in codes])
        else:
            issues.append(dict(type='premium_missing',code=key))
    excluded=[c for c in expected if not any(c in v for v in mapping.values())]
    if any(records[c]['value'] for c in excluded):
        issues.append(dict(type='premium_unallocated',amount=sum(records[c]['value'] for c in excluded),codes=excluded,
                           message='Le total des cinq branches exclut ces montants et ne représente pas le total publié.'))
    return out,issues
