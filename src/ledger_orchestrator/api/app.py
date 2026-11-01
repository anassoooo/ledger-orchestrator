"""Local API. Fixed input sources, one isolated worker process per request."""
import json
import os
import re
import subprocess
import sys
import threading
import uuid
from functools import lru_cache
from pathlib import Path
from fastapi import FastAPI,HTTPException
from fastapi.responses import FileResponse
from ledger_orchestrator.api.schemas import RunRequest, ReviewDecision, CopilotQuestion, ConsolidationRequest
from ledger_orchestrator.consolidate import FILENAME as CONSOLIDATED_WORKBOOK, profile_kind
from ledger_orchestrator.pipeline import save_json
from ledger_orchestrator.profiles import CompanyProfile, local_path
from ledger_orchestrator.extraction.adapters import get_extractor
from ledger_orchestrator.workbook.premium_writer import HistoryProfile
from ledger_orchestrator.review.graph import ReviewWorkflow
from ledger_orchestrator.review.copilot import ReadOnlyCopilot, LocalModelUnavailable, _evidence, status as copilot_status

app=FastAPI(title='LedgerOrchestrator local API',version='0.1.0',docs_url=None,redoc_url=None)
ROOT=Path(os.getenv('CMF_ROOT','/data'))
OUTPUT=Path(os.getenv('CMF_OUTPUT','/output'))
CONFIG=Path(os.getenv('CMF_CONFIG','/app/config/star.json'))
LOCK=threading.Lock()
COPILOT_LOCK=threading.Lock()
STATIC=Path(__file__).resolve().parent.parent/'ui'
RUN_ID=r'\d{8}T\d{6}_[a-f0-9]{8}'
CONSOLIDATION_ID=r'consolidated_'+RUN_ID


@lru_cache(maxsize=4)
def review_workflow(database: str):
    return ReviewWorkflow(Path(database))


def workflow():
    return review_workflow(str(OUTPUT/'review_graph.sqlite3'))


@lru_cache(maxsize=1)
def copilot_graph():
    return ReadOnlyCopilot()


@app.get('/health')
def health():
    return {'status':'ok','local_only':True}


def load_profile(path):
    """Statements profiles (config/*.json) and premium-history profiles (config/history/*.json)."""
    return HistoryProfile.load(path) if profile_kind(path)=='premium_history' else CompanyProfile.load(path)


def check_runnable(profile,years):
    """Raise ValueError when these years cannot run; history profiles need no extractor."""
    years=profile.select_years(years)
    if isinstance(profile,CompanyProfile):
        get_extractor(profile,years)
    return years


def required_inputs(profile,years):
    return [profile.config['workbook']['template'],*[profile.source_relative(y) for y in years]]


def configured_profiles():
    profiles={}
    for path in [*sorted(CONFIG.parent.glob('*.json')),*sorted((CONFIG.parent/'history').glob('*.json'))]:
        profile=load_profile(path)
        identifier=profile.config['profile_id']
        if identifier in profiles:
            raise ValueError('Duplicate profile identifier')
        profiles[identifier]=(path,profile)
    return profiles


@app.get('/profiles')
def list_profiles():
    try:
        profiles=configured_profiles()
        default=CompanyProfile.load(CONFIG).config['profile_id']
        rows=[]
        for identifier,(_,profile) in profiles.items():
            config=profile.config
            reason=None
            try:
                check_runnable(profile,None)
            except ValueError as exc:
                reason=str(exc)
            rows.append(dict(id=identifier,kind=config.get('kind','statements'),company=config['company'],
                             revision=config['revision'],status=config['status'],years=config['years'],
                             runnable=reason is None,reason=reason,available_years=[y for y in config['years']
                                 if local_path(ROOT,profile.source_relative(y)).is_file()]))
        return {'default_profile_id':default,'profiles':rows}
    except (ValueError,KeyError,TypeError,OSError) as exc:
        raise HTTPException(503,'Configuration des profils invalide ou inaccessible') from exc


@app.get('/copilot/status')
def local_copilot_status():
    return copilot_status()


@app.get('/review')
def review_page():
    return FileResponse(STATIC/'index.html',media_type='text/html')


@app.get('/review/{asset}')
def review_asset(asset:str):
    if asset not in ('app.js','style.css'):
        raise HTTPException(404,'Fichier inconnu')
    return FileResponse(STATIC/asset)


@app.get('/runs')
def list_runs():
    if not OUTPUT.is_dir():
        return {'runs':[]}
    folders=sorted((p for p in OUTPUT.iterdir() if p.is_dir() and re.fullmatch(RUN_ID,p.name)),
                   key=lambda p:p.name,reverse=True)
    runs=[]
    for folder in folders[:25]:
        path=folder/'report.json'
        if not path.is_file():
            continue
        report=json.loads(path.read_text(encoding='utf-8'))
        runs.append(dict(run_id=folder.name,kind=report.get('kind','statements'),company=report.get('company'),
                         years=report.get('years',[]),status=report.get('status'),
                         review_count=len(report.get('review',[]))))
    return {'runs':runs}


def resolve_profile(profile_id):
    if profile_id is None:
        return CONFIG,CompanyProfile.load(CONFIG)
    entry=configured_profiles().get(profile_id)
    if entry is None:
        raise HTTPException(422,'Profil inconnu')
    return entry


def final_json(text):
    """The CLI's result: the last top-level JSON object printed (one line or indented)."""
    lines=text.rstrip().splitlines()
    for index in range(len(lines)-1,-1,-1):
        if lines[index].startswith('{'):
            return json.loads('\n'.join(lines[index:]))
    raise ValueError('No JSON result in the worker output')


def launch(command,timeout):
    """Run one CLI command in an isolated process; one job at a time across runs and consolidations."""
    if not LOCK.acquire(blocking=False):
        raise HTTPException(409,'Un traitement est déjà en cours')
    try:
        OUTPUT.mkdir(parents=True,exist_ok=True)
        job=uuid.uuid4().hex
        jobpath=OUTPUT/f'job_{job}.json'
        save_json(jobpath,dict(job_id=job,status='running'))
    except Exception:
        LOCK.release()
        raise
    def worker():
        try:
            with (OUTPUT/f'job_{job}.log').open('w',encoding='utf-8') as log:
                proc=subprocess.run([sys.executable,'-m',command[0],'--root',str(ROOT),'--output',str(OUTPUT),*command[1:]],
                                    stdout=log,stderr=subprocess.STDOUT,timeout=timeout)
            text=(OUTPUT/f'job_{job}.log').read_text(encoding='utf-8')
            result=final_json(text) if proc.returncode==0 else {'status':'failed','message':'Consulter le journal local du traitement'}
            # A consolidation prints no run status; a successful exit means it finished.
            save_json(jobpath,dict(job_id=job,**{'status':'completed',**result}))
        except Exception as exc:
            save_json(jobpath,dict(job_id=job,status='failed',message=type(exc).__name__))
        finally:
            LOCK.release()
    try:
        threading.Thread(target=worker,daemon=True).start()
    except Exception:
        LOCK.release()
        save_json(jobpath,dict(job_id=job,status='failed',message='Worker unavailable'))
        raise
    return {'job_id':job,'status':'running','poll':f'/jobs/{job}'}


@app.post('/runs',status_code=202)
def start(body:RunRequest):
    try:
        config_path,profile=resolve_profile(body.profile_id)
        years=check_runnable(profile,body.years)
        if any(not local_path(ROOT,path).is_file() for path in required_inputs(profile,years)):
            raise HTTPException(422,'Un PDF demandé ou le modèle Excel est absent des données locales')
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc
    except (OSError,KeyError,TypeError) as exc:
        raise HTTPException(503,'Configuration du profil invalide ou inaccessible') from exc
    return launch(['ledger_orchestrator','--config',str(config_path),'--years',*[str(y) for y in years]],3600)


@app.post('/consolidations',status_code=202)
def start_consolidation(body:ConsolidationRequest):
    """Every profile runs on all its years, in the order given, into one copy of the template."""
    if len(set(body.profile_ids))!=len(body.profile_ids):
        raise HTTPException(422,'Un profil est demandé deux fois')
    try:
        profiles=configured_profiles()
        paths=[]
        for identifier in body.profile_ids:
            if identifier not in profiles:
                raise HTTPException(422,f'Profil inconnu : {identifier}')
            path,profile=profiles[identifier]
            years=check_runnable(profile,None)
            if any(not local_path(ROOT,p).is_file() for p in required_inputs(profile,years)):
                raise HTTPException(422,f'Un PDF ou le modèle Excel du profil {identifier} est absent des données locales')
            paths.append(str(path))
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc
    except (OSError,KeyError,TypeError) as exc:
        raise HTTPException(503,'Configuration des profils invalide ou inaccessible') from exc
    return launch(['ledger_orchestrator.consolidate','--configs',*paths],3600*len(paths))


def consolidation_folder(consolidation_id):
    if re.fullmatch(CONSOLIDATION_ID,consolidation_id) is None:
        raise HTTPException(404,'Identifiant inconnu')
    path=OUTPUT/consolidation_id
    if not (path/'consolidation.json').is_file():
        raise HTTPException(404,'Consolidation introuvable')
    return path


@app.get('/consolidations')
def list_consolidations():
    if not OUTPUT.is_dir():
        return {'consolidations':[]}
    rows=[]
    for folder in sorted((p for p in OUTPUT.iterdir() if p.is_dir() and re.fullmatch(CONSOLIDATION_ID,p.name)),
                         key=lambda p:p.name,reverse=True)[:25]:
        path=folder/'consolidation.json'
        if not path.is_file():
            continue
        data=json.loads(path.read_text(encoding='utf-8'))
        rows.append(dict(consolidation_id=folder.name,passed=data.get('passed'),
                         runs=[dict(run_id=r.get('run_id'),company=r.get('company'),kind=r.get('kind'),
                                    status=r.get('status'),writes=r.get('writes')) for r in data.get('runs',[])]))
    return {'consolidations':rows}


@app.get('/consolidations/{consolidation_id}')
def consolidation(consolidation_id:str):
    return json.loads((consolidation_folder(consolidation_id)/'consolidation.json').read_text(encoding='utf-8'))


@app.get('/consolidations/{consolidation_id}/workbook')
def consolidation_workbook(consolidation_id:str):
    folder=consolidation_folder(consolidation_id)
    data=json.loads((folder/'consolidation.json').read_text(encoding='utf-8'))
    if not data.get('passed'):
        raise HTTPException(409,'Classeur consolidé non vérifié')
    path=folder/CONSOLIDATED_WORKBOOK
    if not path.is_file():
        raise HTTPException(404,'Classeur introuvable')
    return FileResponse(path,filename=CONSOLIDATED_WORKBOOK)


@app.get('/jobs/{job_id}')
def job_status(job_id:str):
    if re.fullmatch('[a-f0-9]{32}',job_id) is None:
        raise HTTPException(404,'Identifiant inconnu')
    path=OUTPUT/f'job_{job_id}.json'
    if not path.exists():
        raise HTTPException(404,'Traitement introuvable')
    return json.loads(path.read_text(encoding='utf-8'))


def run_folder(run_id):
    if re.fullmatch(r'\d{8}T\d{6}_[a-f0-9]{8}',run_id) is None:
        raise HTTPException(404,'Identifiant inconnu')
    path=OUTPUT/run_id
    if not (path/'report.json').exists():
        raise HTTPException(404,'Traitement introuvable')
    return path


@app.get('/runs/{run_id}/report')
def report(run_id:str):
    return json.loads((run_folder(run_id)/'report.json').read_text(encoding='utf-8'))


@app.post('/runs/{run_id}/copilot')
def ask_copilot(run_id:str,body:CopilotQuestion):
    report_data=report(run_id)
    if report_data.get('status') not in ('completed','needs_review'):
        raise HTTPException(409,'Traitement non terminé')
    case=review_case(run_id,body.case_id) if body.case_id else None
    if not COPILOT_LOCK.acquire(blocking=False):
        raise HTTPException(409,'Le modèle local traite déjà une question')
    try:
        return copilot_graph().answer(report_data,body.question.strip(),case)
    except LocalModelUnavailable as exc:
        raise HTTPException(503,str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(503,'Configuration du modèle local invalide') from exc
    finally:
        COPILOT_LOCK.release()


def review_case(run_id:str,case_id:str):
    report_data=json.loads((run_folder(run_id)/'report.json').read_text(encoding='utf-8'))
    if report_data['status'] not in ('completed','needs_review'):
        raise HTTPException(409,'Revue indisponible avant la fin du traitement')
    for row in report_data.get('review',[]):
        if f"{row['sheet']}-{row['cell']}" == case_id:
            return case_from_row(run_id,case_id,row)
    raise HTTPException(404,'Cellule à revoir introuvable')


def case_from_row(run_id,case_id,row):
    """Statements review rows carry every field; premium-history rows only year/cell/code/status/reason."""
    history=row.get('status')=='missing_or_blocked' and 'category' not in row
    return dict(run_id=run_id,case_id=case_id,year=row['year'],sheet=row['sheet'],cell=row['cell'],code=row['code'],
                category=row.get('category',row.get('status')),
                reason=row.get('reason') or ('Primes de l’exercice non admises par les identités' if history else None),
                action=row.get('action',"Contrôler l'annexe 13 et l'état de résultat technique" if history else None),
                source=row.get('source'),page=row.get('page'),dependencies=row.get('dependencies',[]),
                issue_types=row.get('issue_types',[]))


def case_thread(run_id:str,case_id:str):
    return f'{run_id}:{case_id}'


@app.get('/runs/{run_id}/review')
def review_queue(run_id:str):
    report_data=json.loads((run_folder(run_id)/'report.json').read_text(encoding='utf-8'))
    if report_data['status'] not in ('completed','needs_review'):
        raise HTTPException(409,'Revue indisponible avant la fin du traitement')
    cases=[]
    for row in report_data.get('review',[]):
        case_id=f"{row['sheet']}-{row['cell']}"
        state=workflow().snapshot(case_thread(run_id,case_id))
        case=case_from_row(run_id,case_id,row)
        cases.append(dict({k:case[k] for k in ('case_id','year','sheet','cell','code','category','reason','page')},
                          decision=state['decision']))
    return {'run_id':run_id,'status':report_data['status'],'cases':cases}


@app.get('/runs/{run_id}/review/{case_id}')
def review_detail(run_id:str,case_id:str):
    case=review_case(run_id,case_id)
    facts=_evidence(report(run_id),case)
    return {'case':case,'evidence':[item for item in facts if item['kind'] in ('anomalie','extraction')],
            **workflow().snapshot(case_thread(run_id,case_id))}


@app.get('/runs/{run_id}/review/{case_id}/source')
def review_source(run_id:str,case_id:str):
    case=review_case(run_id,case_id)
    try:
        source=case['source']
        if not source.startswith('sources/') or not source.endswith('.pdf'):
            raise ValueError('Invalid source')
        path=local_path(ROOT,source)
    except (ValueError,TypeError,AttributeError) as exc:
        raise HTTPException(404,'Source locale invalide') from exc
    if not path.is_file():
        raise HTTPException(404,'PDF source introuvable')
    return FileResponse(path,media_type='application/pdf',filename=path.name,
                        content_disposition_type='inline')


@app.post('/runs/{run_id}/review/{case_id}/start')
def start_review(run_id:str,case_id:str):
    case=review_case(run_id,case_id)
    try:
        state=workflow().start(case_thread(run_id,case_id),case)
    except ValueError as exc:
        raise HTTPException(409,str(exc)) from exc
    return {'case':case,**state}


@app.post('/runs/{run_id}/review/{case_id}/decision')
def decide_review(run_id:str,case_id:str,body:ReviewDecision):
    review_case(run_id,case_id)
    if body.action not in ('documented','follow_up'):
        raise HTTPException(422,'Décision inconnue')
    if not 2 <= len(body.reviewer.strip()) <= 80 or not 3 <= len(body.note.strip()) <= 1000:
        raise HTTPException(422,'Nom ou note de revue invalide')
    try:
        state=workflow().decide(case_thread(run_id,case_id),body.model_dump())
    except ValueError as exc:
        raise HTTPException(409,str(exc)) from exc
    return state


@app.get('/runs/{run_id}/agents')
def agent_status(run_id:str):
    result=json.loads((run_folder(run_id)/'report.json').read_text(encoding='utf-8'))
    return dict(run_id=run_id,status=result['status'],orchestration_version=result.get('orchestration_version'),
                agents=result.get('agent_trace',[]))


@app.get('/runs/{run_id}/workbook')
def workbook(run_id:str):
    folder=run_folder(run_id)
    data=json.loads((folder/'report.json').read_text(encoding='utf-8'))
    if data['status'] not in ('completed','needs_review'):
        raise HTTPException(409,'Classeur indisponible')
    name=data.get('workbook','')
    if not isinstance(name,str) or re.fullmatch(r'[A-Za-z0-9_-]+\.xlsx',name) is None:
        raise HTTPException(404,'Classeur inconnu')
    try:
        path=local_path(folder,name)
    except ValueError as exc:
        raise HTTPException(404,'Classeur inconnu') from exc
    if not path.is_file():
        raise HTTPException(404,'Classeur introuvable')
    return FileResponse(path,filename=name)
