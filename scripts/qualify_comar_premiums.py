"""Read-only COMAR premium candidate. Never admits values or writes Excel."""
import argparse
import json
from pathlib import Path

# The readers live in the package; this script remains the standalone entry point.
from ledger_orchestrator.extraction.comar import (  # noqa: F401
    CATEGORIES,
    HEADERS,
    LAYOUTS,
    candidate,
    category_headers,
    gross_header,
    header_text,
    in_band,
    life_candidate,
    normalize,
    read_amount,
    row_at,
)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise SystemExit('Output already exists; choose a new directory')
    results=[candidate(args.sources/f'{year}.pdf',year) for year in LAYOUTS]
    args.output.mkdir(parents=True)
    (args.output/'evidence.json').write_text(json.dumps(results,indent=2,ensure_ascii=False),encoding='utf8')
    print(json.dumps({r['year']:r['checks'] for r in results},indent=2))


if __name__=='__main__':main()
