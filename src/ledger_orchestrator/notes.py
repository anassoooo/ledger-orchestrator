"""Conservative native-note supplement; never infer a missing balance amount."""
import re
from ledger_orchestrator.extraction import normalize, lines, numeric_groups


# Exact labels scoped to their note. No amounts or balancing plugs in the dictionary.
LABELS={
    'AC1':{'LOGICIELS':'AC12'},
    'AC2':{'MMB':'AC22'},
    'AC5':{'PROVISION POUR PRIMES NON ACQUISES':'AC510',
           'PROVISION POUR SINISTRES VIE':'AC530','PROVISION POUR SINISTRES NON-VIE':'AC531',
           'PROV. POUR PART. DES ASSURES AUX BENEFICES':'AC541'},
    'AC63':{'PERSONNEL':'AC631','ETAT, ORGA,SECURITE SOCIALE':'AC632',
            'AUTRES DEBITEURS DIVERS':'AC633'},
    'AC72':{"FRAIS D'ACQUISITION REPORTES":'AC721'},
}
SECTIONS={'AC1','AC2','AC31','AC32','AC331','AC332','AC334','AC336','AC34',
          'AC5','AC6','AC61','AC62','AC63','AC71','AC72','AC73'}


def asset_notes(pages,year,source,tolerance=3):
    """Read only the bounded asset-notes section with explicit units and dates.

    Native gross-minus-depreciation/provision is a local independent check for a
    disclosed net leaf. Configured subtotal dependencies are still mandatory.
    """
    if year!=2025:
        return {},[]  # This profile has not been verified on other layouts.
    active=False
    section=None
    pending=None
    records={}
    issues=[]
    gross={}
    deductions={}
    component_evidence=[]
    for page in pages:
        text=normalize(page['text'])
        if 'NOTES SUR' in text and 'ACTIF DU BILAN' in text:
            active='DINARS TUNISIENS' in text and 'MILLIER' not in text
        if active and 'NOTES SUR LES CAPITAUX' in text:
            break
        if not active or page['method']!='native':
            continue
        dates=re.findall(r'31\s*/\s*12\s*/\s*(20\d\d)',text)
        if dates[-2:]!=[str(year),str(year-1)]:
            issues.append(dict(type='notes_header_unverified',page=page['page']))
            continue
        for row in lines(page['words']):
            label=' '.join(w['text'] for w in row)
            norm=normalize(label).lstrip(' ').replace('’',"'")
            match=re.match(r'^AC\s*(\d+)\b',norm)
            code='AC'+match[1] if match else None
            vals=numeric_groups([w for w in row if w['x0']>page['width']*.30],page['width'])
            # Plain narrative sentences never qualify as a table value.
            if code in SECTIONS and not vals:
                section=code
                pending=None
                component_evidence=[]
                continue
            if code and not vals:
                pending=(code,row[0]['top'],label)
                continue
            if pending and not code:
                if 0<row[0]['top']-pending[1]<12 and len(vals)==4:
                    code=pending[0]
                    label=pending[2]
                pending=None
            prefix=normalize(' '.join(w['text'] for w in row if not vals or w['x1']<=vals[0][1])).strip().replace('’',"'")
            code=code or LABELS.get(section,{}).get(prefix)
            if section=='AC34' and prefix in ('DEPOTS EN GARANTIE DES PPNA','DEPOTS EN GARANTIE DES PSAP') and len(vals)==2:
                component_evidence.append(dict(label=prefix,value=vals[0][0],previous=vals[1][0],
                                               page=page['page'],bbox=[row[0]['x0'],row[0]['top'],row[-1]['x1'],max(w['bottom'] for w in row)]))
            if prefix=='VALEUR BRUTE' and len(vals)==2:
                gross[section]=[v[0] for v in vals]
            if prefix.startswith('PROVISIONS') and len(vals)==2:
                deductions[section]=[v[0] for v in vals]
            if prefix in ('TOTAL','VALEUR NETTE'):
                code=section
                # Bank TOTAL is gross, not the net balance amount.
                if section=='AC71' and prefix=='TOTAL':
                    gross[section]=[v[0] for v in vals]
                    continue
                if section in {'AC32','AC331','AC332','AC334','AC336'} and prefix!='VALEUR NETTE':
                    continue
            if prefix=='TOTAL GENERAL':
                code='AC6'
            if not code or len(vals) not in (2,4):
                continue
            value,previous=vals[-2][0],vals[-1][0]
            checks=[]
            if code=='AC34' and prefix=='TOTAL' and len(component_evidence)==2 and len({c['label'] for c in component_evidence})==2:
                delta=sum(c['value'] for c in component_evidence)-value
                checks.append(dict(kind='disclosed_components',components=list(component_evidence),delta=delta,
                                   status='passed' if abs(delta)<=tolerance else 'blocked'))
            if len(vals)==4:
                delta=vals[0][0]-vals[1][0]-value
                checks.append(dict(kind='gross_minus_provision',gross=vals[0][0],provision=vals[1][0],net=value,
                                   delta=delta,status='passed' if abs(delta)<=tolerance else 'blocked'))
            elif prefix=='VALEUR NETTE' and section in gross and section in deductions:
                delta=gross[section][0]-deductions[section][0]-value
                checks.append(dict(kind='gross_minus_provision',gross=gross[section][0],provision=deductions[section][0],net=value,
                                   delta=delta,status='passed' if abs(delta)<=tolerance else 'blocked'))
            for check in checks:
                if check['status']=='blocked':
                    issues.append(dict(type='notes_arithmetic_mismatch',code=code,page=page['page'],check=check))
            evidence=dict(code=code,year=year,value=value,previous=previous,unit='TND',source=source,
                          page=page['page'],method='native',source_kind='asset_note',source_label=label,
                          bbox=[row[0]['x0'],min(w['top'] for w in row),row[-1]['x1'],max(w['bottom'] for w in row)],
                          note_checks=checks)
            if code in records and records[code]['value']!=value:
                records[code]['ambiguous']=True
                issues.append(dict(type='notes_duplicate_conflict',code=code,values=[records[code]['value'],value]))
            else:
                records[code]=evidence
    return records,issues


def supplement(records,notes):
    issues=[]
    for code,note in notes.items():
        if code not in records:
            records[code]=note
        elif records[code]['value']!=note['value']:
            records[code]['ambiguous']=True
            issues.append(dict(type='balance_note_conflict',code=code,balance=records[code]['value'],note=note['value'],page=note['page']))
        else:
            records[code]['note_evidence']=note
    return issues
