"""Inspect local documents without changing the workbook."""
import argparse
import json
from pathlib import Path
from ledger_orchestrator.extraction.core import read_pages, balance, premiums


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,default=Path('/data'))
    parser.add_argument('--output',type=Path,default=Path('/output'))
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    report={}
    for year in [2023,2024,2025]:
        path=args.root/'sources'/'STAR'/f'{year}.pdf'
        print(f'Extracting STAR {year}',flush=True)
        pages,digest=read_pages(path,args.output/'cache')
        records,issues=balance(pages,year,str(path))
        branches=premiums(pages,year,str(path))
        report[year]=dict(sha256=digest,balance=records,premiums=branches,issues=issues)
        (args.output/f'extraction_{year}.json').write_text(json.dumps(report[year],ensure_ascii=False,indent=2),encoding='utf-8')
        print(f'{year}: {len(records)} balance records, {len(branches)} premium records; {sum(p["method"]=="ocr" for p in pages)} OCR pages',flush=True)
    (args.output/'audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':
    main()
