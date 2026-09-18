import contextlib
import csv
import hashlib
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from cmf.extraction import read_pages,balance,premiums
from cmf.validation import validate_balance,validate_premiums
from cmf.workbook import write_workbook
from cmf.notes import asset_notes,supplement
from cmf.premium_evidence import corroborate_premiums
from cmf.coverage import measure
from cmf.comparatives import supplement_comparatives
from cmf.review import build_review,export_review
from cmf.cell_ocr import read_scanned_asset
from cmf.subtotal_evidence import corroborate_subtotals
from cmf.presence import native_balance_presence


@contextlib.contextmanager
def exclusive_lock(output):
    handle=(output/'.pipeline.lock').open('a+b')
    try:
        if os.name=='nt':
            import msvcrt
            handle.seek(0)
            handle.write(b'0')
            handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        yield
    finally:
        handle.close()


def save_json(path,data):
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    temp.replace(path)


def execute(root,output,config_path,years=None):
    output.mkdir(parents=True,exist_ok=True)
    config=json.loads(config_path.read_text(encoding='utf-8'))
    years=sorted(set(years or config['years']))
    if not years or any(y not in [2023,2024,2025] for y in years):
        raise ValueError('MVP supports STAR 2023–2025 only')
    if config['target_unit']!='TND':
        raise ValueError('Only confirmed TND mapping is implemented')
    template=root/'templates'/'TAF_G1_G2_G3_G4.xlsx'
    template_digest=hashlib.sha256(template.read_bytes()).hexdigest()
    with exclusive_lock(output):
        run_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'_'+uuid.uuid4().hex[:8]
        folder=output/run_id
        folder.mkdir()
        report=dict(run_id=run_id,status='running',company='STAR',years=years,target_unit='TND',
                    conversion_factor=1,template_sha256=template_digest,config=config,documents={},issues=[],writes=[])
        save_json(folder/'report.json',report)
        try:
            annual={}
            for year in years:
                source=root/'sources'/'STAR'/f'{year}.pdf'
                print(f'STAR {year}: extraction',flush=True)
                pages,digest=read_pages(source,output/'cache')
                if 'STAR' not in pages[0]['text'].upper() or str(year) not in pages[0]['text']:
                    raise ValueError(f'Source identity/year not confirmed: {source.name}')
                records,issues=balance(pages,year,f'sources/STAR/{year}.pdf')
                notes,note_issues=asset_notes(pages,year,f'sources/STAR/{year}.pdf',config['rounding_tolerance_tnd'])
                issues+=note_issues+supplement(records,notes)
                raw=premiums(pages,year,f'sources/STAR/{year}.pdf')
                issues+=corroborate_premiums(pages,raw,year,f'sources/STAR/{year}.pdf',config['rounding_tolerance_tnd'])
                validation=validate_balance(records,config['children'],config['rounding_tolerance_tnd'])
                branches,branch_issues=validate_premiums(raw,config)
                annual[year]=dict(records=records,raw_branches=raw,branches=branches,validation=validation)
                annual[year]['presence']=native_balance_presence(pages,year,f'sources/STAR/{year}.pdf',
                                                                 set(config['asset_rows'])|set(config['liability_rows']))
                report['documents'][str(year)]=dict(sha256=digest,pages=len(pages),ocr_pages=[p['page'] for p in pages if p['method']=='ocr'],
                                                   balance_records=len(records),premium_records=len(raw))
                report['issues'] += [dict(year=year,**{k:v for k,v in i.items() if k!='year'}) for i in issues+branch_issues]
            if 2025 in annual and 2024 in annual and 'AC33' not in annual[2025]['records']:
                scanned=read_scanned_asset(root/'sources'/'STAR'/'2025.pdf',output/'cache')
                accepted=corroborate_subtotals(scanned.get('records',{}),annual[2025],annual[2024],config['children'])
                annual[2025]['records'].update(accepted)
                annual[2025]['validation']=validate_balance(annual[2025]['records'],config['children'],config['rounding_tolerance_tnd'])
            report['source_events']=supplement_comparatives(annual,config['children'],config['rounding_tolerance_tnd'])
            for year,data in annual.items():
                report['documents'][str(year)]['balance_records']=len(data['records'])
                next_records=annual.get(year+1,{}).get('records',{})
                for code,r in data['records'].items():
                    corroborated=(code in next_records and next_records[code]['previous']==r['value']
                                  and next_records[code]['method']=='native'
                                  and code in annual[year+1]['validation']['eligible'])
                    r['cross_year_match']=corroborated
                    # High is an evidence tier, not an invented probability of correctness.
                    r['approved']=code in data['validation']['eligible'] and (r['method']=='native' or corroborated or bool(r.get('subtotal_corroboration')))
                    r['confidence']='high' if r['approved'] else 'review'
                    r['conversion_factor']=1
                    if not r['approved']:
                        report['issues'].append(dict(type='balance_review_required',year=year,code=code,page=r['page']))
                    if code in next_records and next_records[code]['previous']!=r['value']:
                        report['issues'].append(dict(type='comparative_difference',year=year,code=code,current=r['value'],next_comparative=next_records[code]['previous']))
                for code,r in data['raw_branches'].items():
                    r['approved']=r['method']=='native' or bool(r.get('corroboration'))
                    r['conversion_factor']=1
                    if not r['approved']:
                        report['issues'].append(dict(type='premium_review_required',year=year,code=code,page=r['page']))
                for code in set(config['asset_rows'])|set(config['liability_rows']):
                    if code not in data['records']:
                        report['issues'].append(dict(type='not_found',year=year,code=code))
            path=folder/'STAR_consolide.xlsx'
            writes,issues=write_workbook(template,path,config,annual)
            report['writes']=writes
            report['issues']+=issues
            report['data']=annual
            report['coverage']=measure(path,config,years,writes,report['issues'])
            report['review']=build_review(report['coverage'],annual,config,report['issues'])
            export_review(folder/'cellules_a_revoir.csv',report['review'])
            report['status']='needs_review' if report['issues'] else 'completed'
            report['workbook']=path.name
            report['written_cells']=len(writes)
            if hashlib.sha256(template.read_bytes()).hexdigest()!=template_digest:
                raise RuntimeError('Source template changed during execution')
            save_json(folder/'report.json',report)
            with (folder/'anomalies.csv').open('w',encoding='utf-8-sig',newline='') as stream:
                writer=csv.writer(stream,delimiter=';')
                writer.writerow(['Type','Exercice','Code','Détail'])
                for issue in report['issues']:
                    writer.writerow([issue.get('type'),issue.get('year'),issue.get('code'),json.dumps(issue,ensure_ascii=False)])
            with sqlite3.connect(output/'audit.sqlite3') as db:
                db.execute('CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, status TEXT, report TEXT NOT NULL)')
                db.execute('INSERT INTO runs VALUES (?,?,?)',(run_id,report['status'],json.dumps(report,ensure_ascii=False)))
            return report
        except Exception as exc:
            report['status']='failed'
            report['error']=f'{type(exc).__name__}: {exc}'
            save_json(folder/'report.json',report)
            raise
