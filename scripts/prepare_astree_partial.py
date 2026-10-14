"""Prepare supported ASTREE accounting mappings; never activate production."""
import argparse
import hashlib
import json
from pathlib import Path
from qualify_astree import read_document
from ledger_orchestrator.extraction.astree_accounting import extract_accounting
from ledger_orchestrator.extraction.astree_2023_life import extract_2023_life


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('Use a new output directory')
    result=dict(status='needs_review',production_enabled=False,years={},documents={},unqualified_scopes=["2023 non-life branches"])
    for year in (2023,2024,2025):
        source=f'sources/ASTREE/{year}.pdf';path=args.root/source
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        pages=read_document(path)
        result['years'][str(year)]=(extract_2023_life(pages,source) if year==2023 else extract_accounting(pages,year,source))
        if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError('Source changed during extraction')
        result['documents'][str(year)]=dict(source=source,sha256=digest,pages=len(pages))
    args.output.mkdir(parents=True)
    (args.output/'accounting.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({y:d['checks'] for y,d in result['years'].items()}))


if __name__=='__main__':main()
