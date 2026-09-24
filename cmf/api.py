"""Local API. Fixed input sources, one isolated worker process per request."""
import json
import os
import re
import subprocess
import sys
import threading
import uuid
from pathlib import Path
from fastapi import FastAPI,HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel,Field
from cmf.pipeline import save_json

app=FastAPI(title='LedgerOrchestrator local API',version='0.1.0',docs_url=None,redoc_url=None)
ROOT=Path(os.getenv('CMF_ROOT','/data'))
OUTPUT=Path(os.getenv('CMF_OUTPUT','/output'))
CONFIG=Path(os.getenv('CMF_CONFIG','/app/config/star.json'))
LOCK=threading.Lock()


class RunRequest(BaseModel):
    years:list[int]=Field(default_factory=lambda:[2023,2024,2025],min_length=1,max_length=3)


@app.get('/health')
def health():
    return {'status':'ok','local_only':True}


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
                proc=subprocess.run([sys.executable,'-m','cmf','--root',str(ROOT),'--output',str(OUTPUT),
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
