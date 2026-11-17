"""Bounded, best-effort telemetry. Game calls enqueue only; reports are on demand."""
from pathlib import Path
import itertools,atexit,collections,hashlib,json,math,queue,re,threading,time,uuid,zipfile
_LIMIT=512*1024
_FIELDS=set('event session attempt peer op outcome ms phase reason waiting bytes age_ms native_ms ticks grant run_ms credit_wait_ms stale_wait_ms pause_wait_ms barrier_wait_ms pace_ms simulation_us tick_gap_max_ms tick_gap_over100 tick_gap_over250 lock_wait_ms handler_ms connect_ms send_ms receive_ms decode_ms request_bytes response_bytes stage error_id stream sequence exit_code'.split())
_NUMERIC=_FIELDS-set('event session attempt peer op outcome phase reason stage error_id stream'.split())
_REASONS=set('connection ready left download changed snapshot network_timeout network_error invalid_frame invalid_json remote_rejection request_rejected host_fenced participant_timed_out room_closed'.split())|set('TimeoutError ConnectionResetError ConnectionRefusedError ConnectionAbortedError BrokenPipeError OSError PermissionError FileNotFoundError RuntimeError ValueError'.split())|set('credit stale pause barrier pacing save trade army objectives'.split())
_REASONS.update(('ceremony','host_pause','objective','peer_stale','none','unknown','start snapshot mismatch','stale start acknowledgement','invalid server frame','room closed','room left','participant timed out','host fenced'))
_Q=queue.Queue(maxsize=2048);_LOCK=threading.RLock();_START=threading.Lock();_THREAD=None
_DROPPED=0;_IO_ERRORS=0;_SEQUENCE=itertools.count(1);_STREAM=uuid.uuid4().hex[:16];_FAILURES=collections.OrderedDict()
def ident(value):return hashlib.sha256(str(value).encode()).hexdigest()[:16]
def clean(row):
 out={}
 for k,v in row.items():
  if k in _NUMERIC:
   if type(v) in (int,float) and math.isfinite(v) and 0<=v<2**63:out[k]=v
  elif k in ('session','attempt','peer','error_id','stream'):
   if isinstance(v,str) and re.fullmatch('[0-9a-f]{0,16}',v):out[k]=v
  elif k=='utc':
   if isinstance(v,str) and re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ',v):out[k]=v
  elif k=='reason':
   if v in _REASONS if isinstance(v,str) else False:out[k]=v
   elif isinstance(v,str):out[k]='other';out['error_id']=ident(v)
  elif k in ('event','op','outcome','phase','stage'):
   if isinstance(v,str) and re.fullmatch('[a-z][a-z_0-9]{0,47}',v):out[k]=v
 return out

def _write(root,row):
 global _IO_ERRORS
 try:
  p=Path(root)/'network-events.jsonl';data=(json.dumps(row,ensure_ascii=False)+'\n').encode('utf8')
  p.parent.mkdir(parents=True,exist_ok=True)
  with _LOCK:
   if p.exists() and p.stat().st_size+len(data)>_LIMIT:p.replace(p.with_suffix('.previous.jsonl'))
   with p.open('ab') as f:f.write(data)
   if row.get('outcome')=='failed':
    now=time.monotonic();key=str(p)
    if now-_FAILURES.get(key,-1e10)>=10:
     p.with_suffix('.failure.jsonl').write_bytes(p.read_bytes())
     _FAILURES[key]=now;_FAILURES.move_to_end(key)
     while len(_FAILURES)>64:_FAILURES.popitem(last=False)
 except OSError:_IO_ERRORS+=1

def _worker():
 while True:
  item=_Q.get()
  try:
   if isinstance(item,threading.Event):item.set()
   else:_write(*item)
  finally:_Q.task_done()

def _start():
 global _THREAD
 if _THREAD is None:
  with _START:
   if _THREAD is None:
    _THREAD=threading.Thread(target=_worker,name='mp-diagnostics',daemon=True);_THREAD.start()

def record(root,event,**fields):
 global _DROPPED,_SEQUENCE
 try:
  sequence=next(_SEQUENCE)
  row=clean(dict(utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),event=event,stream=_STREAM,sequence=sequence,**fields))
  _start();_Q.put_nowait((str(root),row))
 except queue.Full:_DROPPED+=1
 except (OSError,ValueError,TypeError):_DROPPED+=1

def flush(timeout=1):
 if _THREAD is None:return True
 marker=threading.Event()
 try:_Q.put_nowait(marker)
 except queue.Full:return False
 return marker.wait(timeout)
atexit.register(lambda:flush(.5))

def summarize(rows):
 # Rolling files overlap with failure windows. Do not mislabel the count as an exact session total.
 ops={};failures=[];sessions=set();attempts=set();phases=[]
 for r in rows:
  if r.get('session'):sessions.add(r['session'])
  if r.get('attempt'):attempts.add(r['attempt'])
  if r.get('outcome')=='failed':failures.append(r)
  if r.get('event','').startswith('start_'):phases.append(r)
  if r.get('event')=='rpc' and r.get('op'):
   a=ops.setdefault(r['op'],dict(samples=0,failed=0,ms=[],request_bytes=0,response_bytes=0))
   a['samples']+=1;a['failed']+=r.get('outcome')=='failed'
   if 'ms' in r:a['ms'].append(r['ms'])
   for k in ('request_bytes','response_bytes'):a[k]+=r.get(k,0)
 for a in ops.values():
  values=sorted(a.pop('ms'))
  for name,p in [('p50_ms',.5),('p95_ms',.95),('max_ms',1)]:a[name]=values[max(0,math.ceil(len(values)*p)-1)] if values else None
 return dict(sessions=sorted(sessions),attempts=sorted(attempts),operations=ops,recent_failures=failures[-20:],start_events=phases[-30:],count_scope='retained sampled logs; overlapping windows deduplicated, not whole-session totals')

def export(root,destination,install):
 root=Path(root).resolve();destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
 report_id=uuid.uuid4().hex[:12];target=destination/('Augustus-report-'+time.strftime('%Y%m%d-%H%M%S')+'-'+report_id+'.zip');stage=target.with_suffix('.tmp')
 flushed=flush();metadata=dict(schema=2,report_id=report_id,privacy='No payloads, chat, saves, addresses, names or credentials. No automatic upload.',queue_drained=flushed,dropped_records=_DROPPED,write_errors=_IO_ERRORS,files=[])
 rows=[];seen=set();paths=[];scanned=0
 # Export happens in a report worker, never in the game/control loop.
 import os
 for base,dirs,files in os.walk(root,followlinks=False):
  dirs[:]=[d for d in dirs if not (Path(base)/d).is_symlink()]
  if len(Path(base).relative_to(root).parts)>=6:dirs.clear()
  for name in files:
   scanned+=1
   if name.startswith('network-events') and name.endswith('.jsonl'):
    p=Path(base)/name
    if not p.is_symlink():
     try:paths.append((p.stat().st_mtime,p))
     except OSError:pass
   if scanned>=4096:break
  if scanned>=4096:break
 metadata['scan_truncated']=scanned>=4096
 try:
  with zipfile.ZipFile(stage,'w',zipfile.ZIP_DEFLATED) as z:
   for i,(_,p) in enumerate(sorted(paths,reverse=True)[:24]):
    if not p.resolve().is_relative_to(root):continue
    try:
     with _LOCK,p.open('rb') as f:
      f.seek(max(0,p.stat().st_size-_LIMIT));raw=f.read(_LIMIT)
    except OSError:continue
    batch=[]
    for line in raw.splitlines():
     try:r=json.loads(line)
     except (ValueError,UnicodeError):continue
     if not isinstance(r,dict):continue
     r=clean(r);key=json.dumps(r,sort_keys=True)
     if not r or key in seen:continue
     seen.add(key);batch.append(r);rows.append(r)
    name=f'trace-{i+1:02}.jsonl';z.writestr(name,'\n'.join(json.dumps(x,ensure_ascii=False) for x in batch));metadata['files'].append(name)
   release=Path(install)/'release.json'
   if release.is_file():
    try:
     v=json.loads(release.read_text(encoding='utf-8-sig'));metadata['version']={k:v[k] for k in ('version','internal_build','upstream_commit','diagnostics_revision','package_revision') if isinstance(v.get(k),str) and re.fullmatch('[a-zA-Z0-9._-]{1,100}',v[k])}
    except (OSError,ValueError):metadata['version_unavailable']=True
   metadata['executables']={}
   metadata['diagnostic_modules']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(install)/'network_diagnostics.py',Path(install)/'city_client.py',Path(install)/'network_play.py') if p.is_file()}
   for p in [Path(install)/'augustus-mp-ui.exe',Path(install)/'engine-city-test.exe']:
    if p.is_file():
     with p.open('rb') as f:metadata['executables'][p.name]=hashlib.file_digest(f,'sha256').hexdigest()
   summary=summarize(rows)
   z.writestr('summary.json',json.dumps(summary,ensure_ascii=False,indent=2));z.writestr('report.json',json.dumps(metadata,ensure_ascii=False,indent=2))
   text='보고서 번호: '+report_id+'\n\n이 ZIP을 전달해 주세요. 방장과 문제가 생긴 참가자 양쪽 자료가 필요합니다.\n함께 알려주실 내용: 방장/참가자, 발생 시각(시간대 포함), 직전 행동, 보인 증상, 재현 여부.\n채팅·저장·IP·아이디·인증 정보는 포함하지 않으며 자동 전송하지 않습니다.\n\n공통 세션: '+', '.join(summary['sessions'])+'\n시작 시도: '+', '.join(summary['attempts'])+'\n\n측정은 보관된 구간만 포함합니다. 실패 기록이 없어도 정상임을 뜻하지 않습니다.\nsummary.json의 실패 단계/connect/send/receive/decode 및 응답시간을 양쪽 보고서와 대조합니다.\n측정만으로 회선·VPN·상대 PC 중 원인을 확정하지 않습니다.\n'
   try:   # the reader's language first (ui_text.py), then the Korean original for the developer (2026-11-14)
    from ui_text import T
    shown=T(text,Path(__file__).resolve().parent)
   except Exception:
    shown=text
   if shown!=text:text=shown+'\n----- 한국어 원문 -----\n'+text
   z.writestr('전달 안내.txt',text)
  stage.replace(target)
 except BaseException:
  stage.unlink(missing_ok=True);raise
 return target

class ReportJob:
 def __init__(self):self.thread=None;self.result=None;self.error=None;self.done=threading.Event()
 def start(self,root,destination,install):
  if self.thread is not None:return False
  def work():
   try:self.result=export(root,destination,install)
   except Exception as error:self.error=type(error).__name__
   finally:self.done.set()
  self.thread=threading.Thread(target=work,name='mp-report',daemon=True);self.thread.start();return True


# Host lock timing uses wall time, never the game clock. No gameplay decisions
# depend on these best-effort measurements.
from contextlib import contextmanager
@contextmanager
def measured_room_lock(lock,root,session,peer,op):
 begin=time.monotonic();acquired=begin
 try:
  with lock:
   acquired=time.monotonic()
   try:yield
   finally:finished=time.monotonic()
 finally:
  try:
   record(root,'host_request',session=ident(session),peer=ident(peer),op=op,
          lock_wait_ms=round((acquired-begin)*1000,3),handler_ms=round((finished-acquired)*1000,3))
  except Exception:pass
