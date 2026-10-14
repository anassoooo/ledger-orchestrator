"""Stage guarded COMAR candidates as canonical facts and an explicit mapping review.

Uses the application contracts without admitting a draft profile for execution.
Never writes Excel, changes source PDFs, or enables a production extractor.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

import openpyxl
import pdfplumber

from ledger_orchestrator.profiles import CompanyProfile, local_path
from ledger_orchestrator.records import canonical_facts
from qualify_comar_balance import extract
from qualify_comar_premiums import candidate
from qualify_comar_notes import extract_notes
from comar_review_guards import validate_template


def source_record(code, cell, reading, year, source, column):
    record={'code':code,'year':year,'value':cell['value'],'source':source,
            'page':reading['page'],'method':reading['method'],'unit':reading['unit'],
            'bbox':cell['bbox'],'approved':False,'source_column':column}
    if column=='previous':
        record.update(source_year=year+1,source_kind='native_comparative')
    return record


def facts_for_document(balance, premiums, profile, document, notes=None):
    year=balance['year'];source=profile.source_relative(year)
    annual={y:{'records':{},'raw_branches':{}} for y in [year-1,year]}
    readings={**balance['records']}
    # These are directly printed group totals, not inferred from a sole child.
    if 'PA2_PUBLISHED_SUBTOTAL' in balance['corroborations']:
        readings['PA2']=balance['corroborations']['PA2_PUBLISHED_SUBTOTAL']
    for code,reading in (notes or {}).items():
        if code in readings:raise ValueError('Note would overwrite a balance-page reading')
        readings[code]=reading
    for code,reading in readings.items():
        for column,target_year in [('current',year),('comparative',year-1)]:
            cell=reading['cells'][column]
            if cell['value'] is None:continue
            name='current' if column=='current' else 'previous'
            annual[target_year]['records'][code]=source_record(code,cell,reading,target_year,source,name)
    for reading in premiums['records']:
        if reading['value'] is None:continue
        code='TOTAL_NONVIE_PUBLISHED' if reading['category']=='TOTAL' else reading['category']
        annual[year]['raw_branches'][code]=source_record(code,reading,reading,year,source,'current')
    life=next(r for r in premiums['life']['records'] if r['meaning']=='annex_total')
    annual[year]['raw_branches']['VIE']=source_record('VIE',life,life,year,source,'current')
    return canonical_facts(annual,{year:document},profile)


def direct_mapping(profile, workbook, facts):
    validate_template(profile,workbook)
    current={(f['year'],f['statement'],f['code']):f for f in facts
             if f['year']==f['evidence']['document_year']}
    mappings=[]
    for year in profile.config['years']:
        for sheet,address,code in profile.targets(year):
            statement='balance' if sheet==profile.workbook['balance_sheet'] else 'premiums'
            fact=current.get((year,statement,code))
            existing=workbook[sheet][address].value
            proposal=int(fact['target_amount']) if fact else None
            if fact is None:
                reason='mapping_unresolved' if code=='IRDS' else ('dependent_total_unadmitted' if code.startswith('TOTAL_') and statement=='premiums' else 'source_missing_or_dash')
                status='existing_value_unsupported' if existing is not None and not isinstance(existing,str) else 'no_candidate'
            else:
                reason='candidate_pending_review'
                if existing is None:status='empty_target'
                elif existing==proposal:status='existing_numeric_agrees'
                else:status='existing_conflict'
            mappings.append({'year':year,'sheet':sheet,'cell':address,'statement':statement,
                             'code':code,'existing':existing,'proposed':proposal,
                             'status':status,'reason':reason,'approved':False,
                             'evidence':fact['evidence'] if fact else None,
                             'corroborating_evidence':[f['evidence'] for f in facts
                                 if fact and f is not fact and f['year']==year and f['statement']==statement
                                 and f['code']==code and f['source_amount']==fact['source_amount']]})
    return mappings


def comparative_conflicts(facts):
    grouped=defaultdict(list)
    for f in facts:
        if f['statement']=='balance':grouped[f['year'],f['code']].append(f)
    result=[]
    for (year,code),group in sorted(grouped.items()):
        direct=next((f for f in group if f['evidence']['document_year']==year),None)
        later=next((f for f in group if f['evidence']['document_year']==year+1),None)
        if direct and later and direct['source_amount']!=later['source_amount']:
            result.append({'year':year,'code':code,'current':direct,'later_comparative':later,
                           'later_minus_current':int(later['source_amount'])-int(direct['source_amount']),
                           'resolution':None})
    return result


def prepare(root, profile_path, output):
    if output.exists():raise ValueError('Use a new output directory')
    profile=CompanyProfile.load(profile_path)
    if profile.config['profile_id']!='comar':
        raise ValueError('This command requires the COMAR profile')
    template=local_path(root,profile.workbook['template'])
    template_hash=hashlib.sha256(template.read_bytes()).hexdigest()
    workbook=openpyxl.load_workbook(template,data_only=False)
    template_validation=validate_template(profile,workbook)
    balances=[];premiums=[];notes=[];facts=[];documents={}
    for year in profile.config['years']:
        source=local_path(root,profile.source_relative(year))
        balance=extract(source,year);premium=candidate(source,year)
        if balance['sha256']!=premium['source_sha256']:raise ValueError('Source changed between candidates')
        with pdfplumber.open(source) as doc:pages=len(doc.pages)
        document={'sha256':balance['sha256'],'pages':pages}
        documents[year]=document
        note=extract_notes(source,year,balance)
        facts.extend(facts_for_document(balance,premium,profile,document,note))
        if note:notes.append({'year':year,'source':profile.source_relative(year),
                              'sha256':balance['sha256'],'records':note})
        # Store reproducible paths relative to the application's data root.
        balance['source']=premium['source']=profile.source_relative(year)
        balances.append(balance);premiums.append(premium)
    keys=[(f['year'],f['statement'],f['code'],f['evidence']['source'],f['evidence']['column']) for f in facts]
    if len(keys)!=len(set(keys)):raise ValueError('Duplicate canonical evidence')
    if any(f['approved'] for f in facts):raise ValueError('Candidate was unexpectedly admitted')
    mapping=direct_mapping(profile,workbook,facts)
    conflicts=comparative_conflicts(facts)
    corrections=[{**item,'existing':workbook[item['sheet']][item['cell']].value,'applied':False}
                 for item in profile.workbook['label_overrides']]
    labels={}
    for section in ['asset','liability']:
        for code,row in profile.config[section+'_rows'].items():
            labels[code]=workbook[profile.workbook['balance_sheet']][f'{"B" if section=="asset" else "I"}{row}'].value
    for correction in corrections:
        code=correction['value'].split()[0]
        labels[code]=correction['value']
    for year,document in documents.items():
        if hashlib.sha256(local_path(root,profile.source_relative(year)).read_bytes()).hexdigest()!=document['sha256']:
            raise ValueError('Source changed before output')
    if hashlib.sha256(template.read_bytes()).hexdigest()!=template_hash:raise ValueError('Template changed')
    review={'schema_version':3,'company':'COMAR','status':'candidate_needs_review','production_enabled':False,
            'profile_id':profile.config['profile_id'],'profile_revision':profile.config['revision'],
            'profile_sha256':profile.fingerprint,'template_sha256':template_hash,
            'template_validation':template_validation,'note_candidates':notes,
            'documents':documents,'facts':facts,'balance_candidates':balances,'premium_candidates':premiums,
            'mapping':mapping,'balance_labels':labels,'comparative_conflicts':conflicts,'label_corrections':corrections,
            'unresolved':['Independent accounting reference review','IRDS composition and treatment of Caution/Agricoles',
                          'Missing/dash details cannot be treated as zero','Published subtotal/comparative differences',
                          'COMAR/FTUSA Groupe 2023 reference discrepancy',
                          'Template premium nettes terminology versus source before-reinsurance basis',
                          'Canonical production adapter and workbook admission']}
    summary={'template_validation':template_validation,'note_readings':sum(len(n['records']) for n in notes),
             'facts':len(facts),'approved_facts':0,'mapping_targets':len(mapping),
             'mapping_statuses':dict(Counter(m['status'] for m in mapping)),
             'comparative_conflicts':len(conflicts),'label_corrections':len(corrections),
             'production_enabled':False,'source_and_template_hashes_unchanged':True}
    output.mkdir(parents=True)
    (output/'review.json').write_text(json.dumps(review,indent=2,ensure_ascii=False),encoding='utf8')
    (output/'verification.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--profile',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    print(json.dumps(prepare(a.root,a.profile,a.output),indent=2))


if __name__=='__main__':main()
