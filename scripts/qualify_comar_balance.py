"""Read-only detailed COMAR balance candidate for inspected 2023-2025 layouts."""
import argparse
import json
from pathlib import Path

# The readers live in the package; this script remains the standalone entry point.
from ledger_orchestrator.extraction.comar import (  # noqa: F401
    ASSET_BANDS,
    CHILDREN,
    MANIFEST_PATH,
    candidate,
    covered_rows,
    extract,
    headers,
    identify,
    in_band,
    label_key,
    normalize,
    read_amount,
    rows,
)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--sources',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('Use a new output directory')
    result=[extract(a.sources/f'{y}.pdf',y) for y in ASSET_BANDS]
    a.output.mkdir(parents=True);(a.output/'evidence.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps({r['year']:{'records':len(r['records']),'balance_equality':r['balance_equality'],'incomplete_hierarchies':[c['parent'] for c in r['hierarchy_checks'] if c['missing']],'nonzero_hierarchy_deltas':{c['parent']:c['delta'] for c in r['hierarchy_checks'] if c['delta'] not in (None,0)}} for r in result},indent=2))

if __name__=='__main__':main()
