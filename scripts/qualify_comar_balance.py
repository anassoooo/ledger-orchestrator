"""Read-only detailed COMAR balance candidate for inspected 2023-2025 layouts."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import pdfplumber
from qualify_comar_premiums import normalize, read_amount, in_band, candidate

ASSET_BANDS={2023:[(325,370),(370,415),(415,460),(460,505)],2024:[(320,370),(370,420),(420,475),(475,540)],2025:[(345,395),(395,445),(445,495),(495,550)]}
MANIFEST_PATH=Path(__file__).resolve().parents[1]/'config'/'qualification'/'comar_balance_v1.json'
CHILDREN={'AC1':['AC11','AC12','AC13'],'AC2':['AC21','AC22'],
 'AC31':['AC311','AC312'],'AC32':['AC321','AC322','AC323','AC324'],
 'AC33':['AC331','AC332','AC334','AC335','AC336'],'AC3':['AC31','AC32','AC33','AC34'],
 'AC5':['AC510','AC520','AC530','AC531'],'AC61':['AC611','AC612','AC613'],
 'AC63':['AC631','AC632','AC633'],'AC6':['AC61','AC62','AC63'],
 'AC73':['AC731','AC733'],'AC7':['AC71','AC72','AC73','AC75'],
 'TOTAL_ASSET':['AC1','AC2','AC3','AC5','AC6','AC7'],
 'EQUITY_BEFORE':['CP1','CP2','CP4'],'EQUITY':['EQUITY_BEFORE','CP6'],
 'PA3':['PA310','PA320','PA330','PA331','PA340','PA341','PA350','PA360','PA361'],
 'PA63':['PA631','PA632','PA633','PA634'],'PA6':['PA61','PA62','PA63'],
 'PA71':['PA710','PA712'],'PA7':['PA71','PA73'],
 'TOTAL_LIABILITY':['PA23','PA3','PA5','PA6','PA7'],
 'TOTAL_EQUITY_LIABILITY':['EQUITY','TOTAL_LIABILITY']}

def rows(words):
    result=[]
    for w in sorted(words,key=lambda x:(x['top'],x['x0'])):
        if not result or abs(w['top']-result[-1][0]['top'])>2:result.append([])
        result[-1].append(w)
    return [sorted(row,key=lambda x:x['x0']) for row in result]

def headers(words,year,side,bands):
    cutoff=min(w['top'] for w in words if w['text']==('AC1' if side=='asset' else 'CP1'))
    head=[w for w in words if w['top']<cutoff]
    expected=['BRUT','PROV','NET','NET'] if side=='asset' else ['NET','NET']
    for band,token in zip(bands,expected):
        if [normalize(w['text']) for w in in_band(head,*band)].count(token)!=1:
            raise ValueError('Unconfirmed balance column heading')
    lo,hi=({2023:(90,102),2024:(77,87),2025:(73,83)} if side=='asset' else {2023:(92,101),2024:(81,90),2025:(77,86)})[year]
    dates=[w for w in head if lo<w['top']<hi]
    date_bands=[(370,445),bands[-1]] if side=='asset' else bands
    for value,band in zip((year,year-1),date_bands):
        found=[w['text'] for w in in_band(dates,*band)]
        if found!=[str(value) if year<2025 else f'31/12/{value}']:
            raise ValueError('Unconfirmed balance period positions')

def identify(row):
    text=normalize(' '.join(w['text'] for w in row))
    if text.startswith("TOTAL DE L'ACTIF"):return 'TOTAL_ASSET'
    if text.startswith('TOTAL DES CAPITAUX PROPRES ET DU PASSIF'):return 'TOTAL_EQUITY_LIABILITY'
    if text.startswith('TOTAL DU PASSIF'):return 'TOTAL_LIABILITY'
    if text.startswith('TOTAL CAPITAUX PROPRES AVANT RESULTAT'):return 'EQUITY_BEFORE'
    if text.startswith('TOTAL CAPITAUX PROPRES AVANT AFFECTATION'):return 'EQUITY'
    return row[0]['text'] if re.fullmatch(r'(AC|CP|PA)\d+',row[0]['text']) else None

def label_key(text):
    return re.sub('[^A-Z0-9]','',normalize(text))

def covered_rows(words,year,side,bands,manifest):
    """Match all financial rows and section labels, including unlabeled subtotals.

    No numerical values live in the manifest. It freezes the inspected semantic
    row sequence and heading/reading distinction, not an accounting reference.
    """
    all_rows=rows(words)
    first='AC1' if side=='asset' else 'CP1'
    start=next((i for i,row in enumerate(all_rows) if row[0]['text']==first),None)
    total='TOTAL_ASSET' if side=='asset' else 'TOTAL_EQUITY_LIABILITY'
    ends=[i for i,row in enumerate(all_rows) if identify(row)==total]
    if start is None or len(ends)!=1 or ends[0]<start:
        raise ValueError('Unconfirmed balance body bounds')
    observed=[]
    for row in all_rows[start:ends[0]+1]:
        code=identify(row)
        financial=any(in_band(row,*band) for band in bands)
        if code is None and not financial:
            continue
        label=' '.join(w['text'] for w in row if (w['x0']+w['x1'])/2<bands[0][0])
        observed.append((row,code,financial,label))
    expected=manifest['layouts'][str(year)][side]
    if len(observed)!=len(expected):
        raise ValueError('Balance row coverage changed')
    result=[]
    for (row,code,financial,label),spec in zip(observed,expected):
        expected_code=None if spec['role']=='corroboration' else spec['code']
        if (code!=expected_code or financial!=(spec['role']!='heading')
                or label_key(label)!=spec['label_key']):
            raise ValueError('Unconfirmed balance row identity: '+spec['code'])
        result.append((row,spec,label))
    return result

def extract(source,year,manifest_path=MANIFEST_PATH):
    if year not in ASSET_BANDS:raise ValueError('Unsupported COMAR balance year')
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    # Reuse company/period/unit checks and independent premium controls.
    premium=candidate(source,year)
    manifest_bytes=manifest_path.read_bytes()
    manifest=json.loads(manifest_bytes)
    if (manifest.get('schema_version')!=1 or manifest.get('company')!='COMAR'
            or manifest.get('production_enabled') is not False):
        raise ValueError('Unsupported COMAR coverage manifest')
    records={};corroborations={};coverage={}
    with pdfplumber.open(source) as doc:
        for side,pn in [('asset',2),('liability',3)]:
            page=doc.pages[pn-1];words=page.extract_words()
            bands=ASSET_BANDS[year] if side=='asset' else ([(410,460),(460,505)] if year==2023 else [(420,485),(485,550)])
            headers(words,year,side,bands)
            names=['gross','provisions','current','comparative'] if side=='asset' else ['current','comparative']
            admitted_rows=covered_rows(words,year,side,bands,manifest)
            coverage[side]={'expected_rows':len(admitted_rows),'matched_rows':len(admitted_rows),
                            'headings':sum(s['role']=='heading' for _,s,_ in admitted_rows),
                            'corroborations':sum(s['role']=='corroboration' for _,s,_ in admitted_rows)}
            section_labels={}
            for row,spec,label in admitted_rows:
                code=spec['code']
                if spec['role']=='heading':
                    section_labels[code]=label
                    continue
                cells={}
                for name,band in zip(names,bands):
                    w=in_band(row,*band);raw,val,state=read_amount(w)
                    cells[name]={'value':val,'raw':raw,'state':state,'bbox':[min(x['x0'] for x in w),min(x['top'] for x in w),max(x['x1'] for x in w),max(x['bottom'] for x in w)] if w else None}
                destination=corroborations if spec['role']=='corroboration' else records
                if code in destination:raise ValueError('Duplicate balance code')
                destination[code]={'page':pn,'side':side,'cells':cells,'approved':False,
                                   'method':'native','unit':'TND','row_label':label,
                                   'section_label':section_labels.get(code),
                                   'row_bbox':[min(w['x0'] for w in row),min(w['top'] for w in row),
                                               max(w['x1'] for w in row),max(w['bottom'] for w in row)]}
    if not {'TOTAL_ASSET','TOTAL_EQUITY_LIABILITY','TOTAL_LIABILITY','EQUITY'}<=records.keys():raise ValueError('Missing balance controls')
    for code in ['TOTAL_ASSET','TOTAL_EQUITY_LIABILITY','TOTAL_LIABILITY','EQUITY']:
        if any(records[code]['cells'][column]['value'] is None for column in ['current','comparative']):
            raise ValueError('Missing numeric balance control: '+code)
    checks=[]
    for parent,children in CHILDREN.items():
        # 2024 publishes PA2 directly; 2023/2025 publish its only detail PA23.
        if parent=='TOTAL_LIABILITY' and year==2024:
            children=['PA2',*children[1:]]
        missing=[c for c in [parent,*children] if c not in records or records[c]['cells']['current']['value'] is None]
        checks.append({'parent':parent,'children':children,'missing':missing,'delta':None if missing else sum(records[c]['cells']['current']['value'] for c in children)-records[parent]['cells']['current']['value']})
    gross_checks=[]
    for code,r in records.items():
        if r['side']!='asset':continue
        v={k:r['cells'][k]['value'] for k in ['gross','provisions','current']}
        gross_checks.append({'code':code,'delta':None if any(x is None for x in v.values()) else v['gross']-v['provisions']-v['current'],'missing':[k for k,x in v.items() if x is None]})
    equality={col:records['TOTAL_ASSET']['cells'][col]['value']-records['TOTAL_EQUITY_LIABILITY']['cells'][col]['value'] for col in ['current','comparative']}
    subtotal_checks=[]
    for code,r in corroborations.items():
        detail='PA23' if code=='PA2_PUBLISHED_SUBTOTAL' else 'PA5'
        for column in ['current','comparative']:
            a=r['cells'][column]['value'];b=records[detail]['cells'][column]['value']
            if a is None or b is None or a!=b:
                raise ValueError('Contradictory published liability subtotal')
            subtotal_checks.append({'subtotal':code,'detail':detail,'column':column,'delta':a-b})
    if hashlib.sha256(source.read_bytes()).hexdigest()!=digest:raise ValueError('Source changed')
    return {'company':'COMAR','year':year,'source':str(source),'sha256':digest,'status':'candidate_needs_review','production_enabled':False,'records':records,'corroborations':corroborations,'coverage':coverage,'coverage_manifest':manifest['layout_id'],'coverage_manifest_sha256':hashlib.sha256(manifest_bytes).hexdigest(),'subtotal_checks':subtotal_checks,'hierarchy_checks':checks,'gross_checks':gross_checks,'balance_equality':equality,'unit_evidence_page':premium['unit_evidence_page']}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--sources',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('Use a new output directory')
    result=[extract(a.sources/f'{y}.pdf',y) for y in ASSET_BANDS]
    a.output.mkdir(parents=True);(a.output/'evidence.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps({r['year']:{'records':len(r['records']),'balance_equality':r['balance_equality'],'incomplete_hierarchies':[c['parent'] for c in r['hierarchy_checks'] if c['missing']],'nonzero_hierarchy_deltas':{c['parent']:c['delta'] for c in r['hierarchy_checks'] if c['delta'] not in (None,0)}} for r in result},indent=2))

if __name__=='__main__':main()
