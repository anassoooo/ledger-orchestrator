import argparse
import json
import os
from pathlib import Path
from cmf.pipeline import execute


def main():
    parser=argparse.ArgumentParser(description='LedgerOrchestrator — extraction financière locale et contrôlée')
    parser.add_argument('--root',type=Path,default=Path(os.getenv('CMF_ROOT','data')))
    parser.add_argument('--output',type=Path,default=Path(os.getenv('CMF_OUTPUT','outputs')))
    parser.add_argument('--config',type=Path,default=Path(os.getenv('CMF_CONFIG','config/star.json')))
    parser.add_argument('--years',nargs='+',type=int,default=[2023,2024,2025])
    args=parser.parse_args()
    result=execute(args.root,args.output,args.config,args.years)
    print(json.dumps({k:result[k] for k in ('run_id','status','written_cells','workbook')},ensure_ascii=False))


if __name__=='__main__':
    main()
