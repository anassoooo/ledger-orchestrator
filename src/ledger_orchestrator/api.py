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
from pydantic import BaseModel,Field
from ledger_orchestrator.pipeline import save_json
from ledger_orchestrator.review_graph import ReviewWorkflow
from ledger_orchestrator.copilot import ReadOnlyCopilot, LocalModelUnavailable, _evidence, status as copilot_status

app=FastAPI(title='LedgerOrchestrator local API',version='0.1.0',docs_url=None,redoc_url=None)
ROOT=Path(os.getenv('CMF_ROOT','/data'))
OUTPUT=Path(os.getenv('CMF_OUTPUT','/output'))
CONFIG=Path(os.getenv('CMF_CONFIG','/app/config/star.json'))
LOCK=threading.Lock()
COPILOT_LOCK=threading.Lock()
STATIC=Path(__file__).parent/'ui'


class RunRequest(BaseModel):
    years:list[int]=Field(default_factory=lambda:[2023,2024,2025],min_length=1,max_length=3)


class ReviewDecision(BaseModel):
    action:str
    reviewer:str=Field(min_length=2,max_length=80)
    note:str=Field(min_length=3,max_length=1000)


class CopilotQuestion(BaseModel):
    question:str=Field(min_length=5,max_length=600)
    case_id:str|None=None


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
    folders=sorted((p for p in OUTPUT.iterdir() if p.is_dir() and
                    re.fullmatch(r'\d{8}T\d{6}_[a-f0-9]{8}',p.name)),
                   key=lambda p:p.name,reverse=True)
    runs=[]
    for folder in folders[:25]:
        path=folder/'report.json'
        if not path.is_file():
            continue
        report=json.loads(path.read_text(encoding='utf-8'))
        runs.append(dict(run_id=folder.name,company=report.get('company'),
                         years=report.get('years',[]),status=report.get('status'),
                         review_count=len(report.get('review',[]))))
    return {'runs':runs}


@app.post('/runs',status_code=202)
def start(body:RunRequest):
    if any(y not in (2023,2024,2025) for y in body.years):
        raise HTTPException(422,'Exercices autorisés : 2023, 2024, 2025')
    if not LOCK.acquire(blocking=False):
        raise HTTPException(409,'Un traitement est déjà en cours')
    OUTPUT.mkdir(parents=True,exist_ok=True)
    job=uuid.uuid4().hex
    jobpath=OUTPUT/f'job_{job}.json'
    save_json(jobpath,dict(job_id=job,status='running'))
    def worker():
        try:
            with (OUTPUT/f'job_{job}.log').open('w',encoding='utf-8') as log:
                proc=subprocess.run([sys.executable,'-m','ledger_orchestrator','--root',str(ROOT),'--output',str(OUTPUT),
                                     '--config',str(CONFIG),'--years',*[str(y) for y in body.years]],
                                    stdout=log,stderr=subprocess.STDOUT,timeout=3600)
            text=(OUTPUT/f'job_{job}.log').read_text(encoding='utf-8')
            last=text.strip().splitlines()[-1] if text.strip() else ''
            result=json.loads(last) if proc.returncode==0 else {'status':'failed','message':'Consulter le journal local du traitement'}
            save_json(jobpath,dict(job_id=job,**result))
        except Exception as exc:
            save_json(jobpath,dict(job_id=job,status='failed',message=type(exc).__name__))
        finally:
            LOCK.release()
    threading.Thread(target=worker,daemon=True).start()
    return {'job_id':job,'status':'running','poll':f'/jobs/{job}'}


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
            return dict(run_id=run_id,case_id=case_id,year=row['year'],sheet=row['sheet'],
                        cell=row['cell'],code=row['code'],category=row['category'],
                        reason=row['reason'],action=row['action'],source=row['source'],
                        page=row['page'],dependencies=row['dependencies'],
                        issue_types=row['issue_types'])
    raise HTTPException(404,'Cellule à revoir introuvable')


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
        cases.append(dict(case_id=case_id,year=row['year'],sheet=row['sheet'],cell=row['cell'],
                          code=row['code'],category=row['category'],reason=row['reason'],
                          page=row['page'],decision=state['decision']))
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
    path=ROOT/'sources'/'STAR'/f"{case['year']}.pdf"
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
    status=json.loads((folder/'report.json').read_text(encoding='utf-8'))['status']
    if status not in ('completed','needs_review'):
        raise HTTPException(409,'Classeur indisponible')
    return FileResponse(folder/'STAR_consolide.xlsx',filename='STAR_consolide.xlsx')
