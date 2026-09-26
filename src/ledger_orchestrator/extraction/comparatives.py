"""Use explicitly published native N-1 cells, never inferred zeros."""
from copy import deepcopy


def supplement_comparatives(annual,children,tolerance):
    from ledger_orchestrator.validation.accounting import validate_balance
    events=[]
    for year,data in sorted(annual.items()):
        following=annual.get(year+1)
        if not following:
            continue
        for code,source in following['records'].items():
            if (code in data['records'] or source['method']!='native' or
                    source.get('source_kind') not in (None,'balance') or
                    source.get('ambiguous') or source.get('previous') is None or
                    code not in following['validation']['eligible']):
                continue
            record=deepcopy(source)
            record.update(year=year,value=source['previous'],previous=None,
                          source_kind='native_comparative',source_year=year+1,
                          source_column='previous',comparative_evidence=deepcopy(source))
            data['records'][code]=record
            events.append(dict(type='native_comparative_used',year=year,code=code,
                               source=source['source'],page=source['page'],value=record['value']))
        data['validation']=validate_balance(data['records'],children,tolerance)
    return events
