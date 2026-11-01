import argparse
import json
import os
from pathlib import Path
from ledger_orchestrator.consolidate import run_profile


def main():
    parser=argparse.ArgumentParser(description='LedgerOrchestrator — extraction financière locale et contrôlée')
    parser.add_argument('--root',type=Path,default=Path(os.getenv('CMF_ROOT','data')))
    parser.add_argument('--output',type=Path,default=Path(os.getenv('CMF_OUTPUT','outputs')))
    parser.add_argument('--config',type=Path,default=Path(os.getenv('CMF_CONFIG','config/star.json')))
    parser.add_argument('--years',nargs='+',type=int,help='Exercices du profil ; tous par défaut')
    args=parser.parse_args()
    # Statements and premium-history profiles share one entry point (and the API worker).
    result=run_profile(args.root,args.output,args.config,years=args.years)
    print(json.dumps(dict(run_id=result['run_id'],kind=result.get('kind','statements'),status=result['status'],
                          written_cells=len(result['writes']),workbook=result['workbook']),ensure_ascii=False))


if __name__=='__main__':
    main()
