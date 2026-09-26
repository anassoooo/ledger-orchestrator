"""Combine explicit visual observations with the earlier source rereading audit."""
import argparse
import hashlib
import json
from pathlib import Path


def reconcile(audit,visual):
    if audit['source_run']!=visual['source_run']:
        raise ValueError('Run mismatch')
    records={(r['sheet'],r['cell'],r['source_index']):r for r in audit['sources']}
    seen=set()
    for v in visual['confirmed_references']:
        key=(v['sheet'],v['cell'],v['source_index'])
        if key in seen:
            raise ValueError('Duplicate visual reference')
        seen.add(key)
        r=records[key]
        if (v['year']!=r['year'] or v['page']!=r['page'] or
                str(v['pdf_year'])!=Path(r['source']).stem or v['printed_value']!=r['expected']):
            raise ValueError(f'Visual observation does not match recorded source: {key}')
    native=sum(r['status'] in ('native_column_match','native_cell_match') for r in audit['sources'])
    outstanding=[r for key,r in records.items() if r['status'] not in ('native_column_match','native_cell_match') and key not in seen]
    return dict(source_run=audit['source_run'],pdf_sha256=audit['pdf_sha256'],
                native_references=native,visual_references=len(seen),outstanding_references=outstanding,
                findings=visual['findings'],financial_writes=0,
                limitation='Numeric evidence reviewed, not a certification of all semantic mappings or source consistency.')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('folder',type=Path)
    p.add_argument('--root',type=Path,default=Path('data'))
    args=p.parse_args()
    source=json.loads((args.folder/'audit_sources.json').read_text(encoding='utf-8'))
    visual=json.loads((args.folder/'revue_visuelle.json').read_text(encoding='utf-8'))
    for year,digest in source['pdf_sha256'].items():
        if hashlib.sha256((args.root/'sources'/'STAR'/f'{year}.pdf').read_bytes()).hexdigest()!=digest:
            raise ValueError('PDF changed since audit')
    result=reconcile(source,visual)
    (args.folder/'audit_consolide.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('findings','pdf_sha256')}))


if __name__=='__main__':
    main()
