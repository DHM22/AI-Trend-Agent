"""Local-only saved-report, default-status, HTTP rendering, offline replay checks."""
import os,sys,json,socket,subprocess,time,urllib.request
from pathlib import Path
from dataclasses import asdict
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'02_src')]
from schemas import VerifiedTrend,TrendCluster
from app.models import Report
from demo_snapshot import load_snapshot
out={'reports':[]}
for name in ['01_data/demo_snapshot.json','data/report.json']:
 raw=load_snapshot(str(ROOT/name));model=Report.model_validate(raw)
 statuses=[]
 for row in raw['recommendations']:
  kwargs={'cluster':TrendCluster(row['trend'],[]),'confidence':row['confidence'],'verification_note':row.get('verification_note','')}
  if 'status' in row:kwargs['status']=row['status']
  trend=VerifiedTrend(**kwargs);statuses.append(trend.status)
  assert trend.status=='unverified'
 out['reports'].append({'path':name,'loaded':len(model.recommendations),'missing_status_rows':sum('status' not in r for r in raw['recommendations']),'reconstructed_verified_trend_statuses':sorted(set(statuses)),'dashboard_model_missing_status_rows':sum('status' not in r.model_dump() for r in model.recommendations)})
assert VerifiedTrend(TrendCluster('compatibility',[]),1.0,'legacy').status=='unverified'
env=os.environ.copy();env.pop('OPENAI_API_KEY',None);env['TOOL_CACHE_ONLY']='1';env['PYTHONDONTWRITEBYTECODE']='1'
out['http']=[]
for name in ['01_data/demo_snapshot.json','data/report.json']:
 with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
 env['REPORT_PATH']=name
 log=ROOT/'review/verification/implementation'/('status_server_'+Path(name).stem+'.log')
 with log.open('w') as handle:
  proc=subprocess.Popen([str(ROOT/'.venv/bin/python'),'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(port)],cwd=ROOT,env=env,stdout=handle,stderr=subprocess.STDOUT)
  try:
   for i in range(100):
    try:
     with urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=1) as r:assert r.status==200
     break
    except OSError:
     if proc.poll() is not None:raise RuntimeError('server exited during startup')
     time.sleep(.1)
   else:raise RuntimeError('server startup timeout')
   for route in ['/health','/','/api/report']:
    with urllib.request.urlopen(f'http://127.0.0.1:{port}{route}',timeout=5) as r:
     body=r.read();assert r.status==200
     if route=='/':assert b'<html' in body.lower()
     out['http'].append({'report':name,'route':route,'status':r.status,'bytes':len(body)})
  finally:
   proc.terminate();proc.wait(timeout=10)
replay=subprocess.run([str(ROOT/'.venv/bin/python'),str(ROOT/'02_src/demo_snapshot.py'),'--replay'],cwd=ROOT,env=env,capture_output=True,text=True)
assert replay.returncode==0
out['offline_replay']={'exit_code':replay.returncode,'api_key_present':False,'TOOL_CACHE_ONLY':'1','summary':[line for line in replay.stdout.splitlines() if 'UPDATE EXISTING MATERIAL:' in line or 'signals ->' in line]}
out['limitations']='Saved reports contain Recommendation rows, not serialized VerifiedTrend. Existing dashboard and replay readers retain absent status; they do not synthesize verified or unverified. Reconstructing VerifiedTrend without status defaults to unverified. No consumer/gating change was made. Browser JavaScript NOT TESTED.'
path=ROOT/'review/verification/implementation/status_shipped_compatibility.json';path.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
