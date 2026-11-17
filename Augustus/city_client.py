from windows_paths import filesystem_path, launch_cwd
"""Frozen-city integration driver for the headless prototype, not a GUI client."""
import base64,json,os,socket,subprocess,uuid,time
from network_diagnostics import record,ident
from pathlib import Path
from coordinator import PROTOCOL,BUILD,FRAME_LIMIT,sha,receipt
from checkpoints import Checkpoints,durable
HERE=filesystem_path(Path(__file__).parent)
def game_data():
 if os.environ.get('AUGUSTUS_C3_DATA'):
  data=filesystem_path(os.environ['AUGUSTUS_C3_DATA'])
  try:   # same pictures for a data folder given directly (the editor's prepared copy, tests); a no-op once made
   import caesar3_tints;caesar3_tints.ensure(data)
  except Exception:pass
  return data
 settings=HERE/'network-settings.json'
 if settings.exists() and (HERE/'korean').is_dir():
  from prepare_network_data import prepare
  source=json.loads(settings.read_text(encoding='utf-8-sig'))['game_data']
  try:   # the player-colour pictures the engine loads (caesar3_tints.py; not shipped in the Global edition). Never fatal.
   import caesar3_tints;caesar3_tints.ensure(source)
  except Exception:pass
  return prepare(source,HERE/'private-game-data',HERE/'korean')
 return HERE.parent/'engine-test-rc20/game-data' 
# A simulated ping of the test launcher (mp_test_tools.py, not in any release): 0 everywhere else. Looked up once.
try:from mp_test_tools import round_trip_delay as test_round_trip
except ImportError:
 def test_round_trip():return 0.0
class Engine:
 def run(self,mode,source,target,qty=0,money=0,seq=0):
  source,target=filesystem_path(source),filesystem_path(target);target.mkdir(parents=True,exist_ok=True)
  if mode in ('start-capua','start-tarentum','seed-capua','seed-tarentum') and not (source/'empire-layout.txt').exists():
   from scenario_project import load,layout
   source=target/'scenario-input';source.mkdir(exist_ok=True)
   (source/'empire-layout.txt').write_text(layout(load()),encoding='ascii')
  user=target/'user';user.mkdir(exist_ok=True)
  env=os.environ.copy();env['AUGUSTUS_KO_USER_PATH']=user.as_posix()+'/'
  env.pop('AUGUSTUS_ROOM_OPTIONS_FILE',None)
  # Frozen-city helpers must use the same locked rules as the live city.
  for base in [source,*source.parents,target,*target.parents]:
   candidate=base/'room-options-worker.txt'
   if candidate.is_file():env['AUGUSTUS_ROOM_OPTIONS_FILE']=str(candidate);break
  with (target/'engine.log').open('wb') as log:
   p=subprocess.run([str(HERE/'engine-city-test.exe'),str(game_data()),mode,str(source),str(target),str(qty),str(money),str(seq)],executable=str(HERE/'engine-city-test.exe'),cwd=launch_cwd(HERE),env=env,stdout=log,stderr=subprocess.STDOUT,timeout=90)
  log=(target/'engine.log').read_text(errors='replace')
  if p.returncode:
   if p.returncode==92:raise RuntimeError('시저 3 원본 지도 파일을 읽지 못해 도시를 만들 수 없습니다. 이 시나리오가 쓰는 원본 지도(.map)가 이 PC의 시저 3 폴더에 있는지 확인하세요.')   # engine_main.c: the mission template did not load
   if p.returncode==117:raise RuntimeError('연습 도시를 배치할 평지 또는 지도 진입로가 없습니다. 지형을 확인하거나 시작 도시 구성을 해제하세요.')
   if 'Roster expansion blocked: active NPC trader' in log:raise RuntimeError('새 참가 도시의 중립 상인이 이동 중입니다. 기존 방에서 교역을 멈추고 상인이 떠난 뒤 공동 저장해 주세요.')
   if 'Creator terrain rejected protected or invalid tile:' in log:
    detail=log.split('Creator terrain rejected protected or invalid tile:',1)[1].splitlines()[0].strip()
    raise RuntimeError('지형 편집 위치를 확인하세요. 보호된 건물 또는 잘못된 타일: '+detail)
   if 'Creator terrain rejected: existing entry/exit route was disconnected' in log:raise RuntimeError('지형 편집으로 입구와 출구 사이의 길이 끊겼습니다. 시나리오 편집기에서 연결을 복구하세요.')
   if 'Creator invasion rejected:' in log:raise RuntimeError('침략 진입점을 확인하세요. 지정 위치가 없거나 통과할 수 없는 지형입니다. 3 플레이 자리 설정의 침략 설정 탭에서 자동 선택하거나 정식 지형 편집기에서 진입점을 수정한 뒤 게임 적용 검사를 실행하세요.')
   raise RuntimeError('engine operation rejected: '+str(p.returncode))
  if not any(marker in log for marker in ('Using default audio driver: dummy','Audio output disabled: no playback device opened')) or 'ERROR:' in log:raise RuntimeError('engine validation log failed')
  # Terrain export produces a map and conversion report, not a multiplayer save/receipt.
  # Keep the same exit-code and strict engine-log validation above for both result types.
  if mode=='native-save-terrain':return (target/'terrain.mapx').read_bytes(),(target/'save-terrain.json').read_bytes()
  return (target/'city.sav').read_bytes(),(target/'receipt.bin').read_bytes()
class NetworkUnavailable(OSError):
 pass

class Client:
 def __init__(self,root,session,city,token,address,scenario=None):
  self.root=filesystem_path(root);self.root.mkdir(parents=True,exist_ok=True)
  self.city=city;self.session=session;self.token=token;self.address=address
  self.scenario=scenario
  self.checkpoints=Checkpoints(self.root/'checkpoints',session,city)
 # Each RPC used to open a new TCP connection: one extra round trip per call
 # (+400ms at a 400ms ping). Keep one connection per thread and reuse it while
 # it is fresh; the server closes idle sockets after 15s, we retire them at 8s.
 IDLE_SECONDS=8
 def pool(self):
  local=getattr(self,'_pool',None)
  if local is None:
   import threading
   local=self._pool=threading.local()
  return local
 def connection(self,timeout):
  p=self.pool();sock=getattr(p,'sock',None)
  if sock is not None and time.monotonic()-p.last<self.IDLE_SECONDS:
   sock.settimeout(timeout);return sock,p.reader,True
  self.disconnect()
  sock=socket.create_connection(self.address,timeout=timeout)
  p.sock=sock;p.reader=sock.makefile('rb');p.last=time.monotonic()
  return sock,p.reader,False
 def disconnect(self):
  p=self.pool();sock=getattr(p,'sock',None);p.sock=None
  if sock is not None:
   try:p.reader.close()
   except OSError:pass
   try:sock.close()
   except OSError:pass
 # ---- one round trip for the routine polls of a bridge round ----------------------------------------------------
 # A bridge round used to send about a dozen status requests one after another: a dozen round trips, ~5 s at a
 # 400 ms ping. begin_round() sends the polls the previous round made (only the operations below: reads and
 # idempotent heartbeats, safe to answer even if the answer ends up unused) in ONE 'batch' request; call() then hands
 # out those answers when the round asks the same question, and goes to the network for anything else. Nothing that
 # changes room state on purpose (offers, saves, reports, commands) is ever sent ahead.
 PREFETCH=frozenset(('lobby_heartbeat','play_begin','chat_read','save_status','lobby_status','recovery_plan',
                     'army_install_status','army_overview','army_order_status','throne_mine','progress_mine','clock'))
 @staticmethod
 def _key(op,fields):
  return (op,json.dumps({k:v for k,v in fields.items() if not (op=='lobby_heartbeat' and k=='rtt_ms')},sort_keys=True,default=str))
 def begin_round(self,clock_ticks=None):
  import threading
  plan=getattr(self,'_plan',[]);self._plan=[];self._ready=[];self._owner=threading.get_ident();self.last_cached=False
  # Polls the bridge makes only every second or so (army status, ...) were asked in some rounds and not in the round
  # just before, so they went out one by one: two more round trips in those rounds at a high ping (2026-11-15). The
  # batch now also carries what the last three rounds asked (the latest question per operation). At a low ping three
  # rounds are a fraction of a second, so nothing extra is asked for long.
  recent=self.__dict__.setdefault('_recent',[]);recent.append(plan);del recent[:-3]
  asked={op for op,_ in plan}
  for older in reversed(recent[:-1]):
   for op,fields in older:
    if op not in asked:asked.add(op);plan=plan+[(op,fields)]
  if getattr(self,'_no_batch',False) or len(plan)<2:return
  calls=[]
  for op,fields in plan[:32]:
   if op=='clock':
    if clock_ticks is None:continue
    fields=dict(ticks=clock_ticks)
   elif op=='lobby_heartbeat' and getattr(self,'prefetch_ms',None) is not None:fields=dict(fields,rtt_ms=self.prefetch_ms)
   calls.append(dict(op=op,**fields))
  if len(calls)<2:return
  begin=time.monotonic()
  try:replies=self.call('batch',calls=calls)
  except ValueError as error:
   if str(error)=='invalid_request':self._no_batch=True;return   # a host without 'batch': one request at a time, as before
   raise
  self.prefetch_ms=round((time.monotonic()-begin)*1000)
  if not isinstance(replies,list) or len(replies)!=len(calls) or any(not isinstance(x,dict) or type(x.get('ok')) is not bool for x in replies):raise ValueError('invalid server frame')
  for c,reply in zip(calls,replies):
   op=c['op'];fields={k:v for k,v in c.items() if k!='op'}
   self._ready.append((self._key(op,fields),fields,reply))
 def _take(self,op,fields,any_fields=False):
  import threading
  self.last_cached=False
  if op not in self.PREFETCH or getattr(self,'_owner',None)!=threading.get_ident():return None
  plan=self.__dict__.setdefault('_plan',[])
  if len(plan)<32:plan.append((op,dict(fields)))
  key=self._key(op,fields)
  for i,(k,f,reply) in enumerate(getattr(self,'_ready',[])):
   if k==key or (any_fields and k[0]==op):
    del self._ready[i];self.last_cached=True
    record(self.root,'rpc',session=ident(self.session),peer=ident(self.city),op=op,outcome='ok' if reply['ok'] else 'failed',stage='prefetched',ms=0)
    return f,reply
  return None
 def take_clock(self):
  """The clock report sent ahead in this round's batch: (ticks reported, reply), or None (then report as before)."""
  hit=self._take('clock',{},any_fields=True)
  if hit is None:return None
  if not hit[1]['ok']:raise ValueError(hit[1]['error'])
  return hit[0]['ticks'],hit[1]['result']
 def call(self,op,**fields):
  if op!='clock':
   # chat_read: the round's prefetched answer was asked after this round's command, from an older cursor, so it holds
   # every newer line too (the bridge skips the ones it has). Taking it saves the round trip after a chat line (2026-11-15).
   hit=self._take(op,fields,any_fields=op=='chat_read')
   if hit is not None:
    if not hit[1]['ok']:raise ValueError(hit[1]['error'])
    return hit[1]['result']
  r=dict(protocol=PROTOCOL,build=BUILD,session=self.session,scenario=self.scenario,city=self.city,token=self.token,op=op,**fields)
  if getattr(self,'chat_sink',None) and op!='chat_read':r['_chat_after']=getattr(self,'chat_after',0)
  engine=getattr(self,'engine_progress_file',None)
  if engine and getattr(self,'clock_enabled',False) and op!='clock':
   try:
    # A stale engine file must never count as a running game.
    if 0<=time.time()-engine.stat().st_mtime<1.0:r['_engine_ticks']=int(engine.read_text().strip())
   except (OSError,ValueError):pass
  begin=time.monotonic();stage='encode';timings={};sent=0;received=0
  def trace(outcome,reason=None,error=None):
   fields=dict(session=ident(self.session),peer=ident(self.city),op=op,outcome=outcome,stage=stage,ms=round((time.monotonic()-begin)*1000),request_bytes=sent,response_bytes=received,**timings)
   if reason:fields['reason']=reason
   if error:fields['error_id']=ident(error)
   record(self.root,'rpc',**fields)
  try:
   wire=(json.dumps(r)+'\n').encode();timeout=20 if op in ('save_part','save_replica_part','snapshot') else 8
   for attempt in (0,1):
    stage='connect';mark=time.monotonic()
    sock,reader,reused=self.connection(timeout)
    timings['connect_ms']=round((time.monotonic()-mark)*1000)
    try:
     self.local_address=sock.getsockname()[0];stage='send';mark=time.monotonic()
     lag=test_round_trip()
     if lag:time.sleep(lag/2)   # test tool: simulated ping (outbound half)
     sock.sendall(wire);sent=len(wire);timings['send_ms']=round((time.monotonic()-mark)*1000)
     stage='receive';mark=time.monotonic()
     data=reader.readline(FRAME_LIMIT+1);received=len(data)
     if lag:time.sleep(lag/2)   # test tool: simulated ping (return half)
     timings['receive_ms']=round((time.monotonic()-mark)*1000)
    except OSError:
     self.disconnect()
     # A kept-alive socket the server already closed (idle timeout) never saw
     # this request; retry once on a fresh connection. Fresh failures propagate.
     if reused and not received and not attempt:continue
     raise
    if not data and reused and not attempt:
     self.disconnect();continue
    if not data.endswith(b'\n'):self.disconnect()
    else:self.pool().last=time.monotonic()
    break
  except OSError as error:
   trace('failed','network_timeout' if isinstance(error,TimeoutError) else 'network_error',type(error).__name__)
   raise NetworkUnavailable(str(error)) from error
  if len(data)<=FRAME_LIMIT and not data.endswith(b'\n'):
   trace('failed','network_error')
   raise NetworkUnavailable('connection closed before complete response')
  if len(data)>FRAME_LIMIT:
   trace('failed','invalid_frame');raise ValueError('invalid server frame')
  stage='decode';mark=time.monotonic()
  try:
   response=json.loads(data)
   if not isinstance(response,dict) or type(response.get('ok')) is not bool:raise ValueError('invalid server frame')
  except ValueError:
   trace('failed','invalid_json');raise
  timings['decode_ms']=round((time.monotonic()-mark)*1000)
  stage='complete'
  trace('ok' if response['ok'] else 'failed',None if response['ok'] else 'remote_rejection',None if response['ok'] else str(response.get('error','')))
  if not response['ok']:raise ValueError(response['error'])
  if 'engine_clock' in response and getattr(self,'clock_sink',None):
   try:self.clock_sink(response['engine_clock'])
   except OSError as error:
    # The primary operation has already succeeded. A local mailbox failure must
    # not turn it into a failed/retried command. Native credit still expires.
    record(self.root,'clock_publish_failed',session=ident(self.session),peer=ident(self.city),op=op,outcome='failed',reason=type(error).__name__)
  if 'chat_messages' in response and getattr(self,'chat_sink',None):
   try:self.chat_sink(response['chat_messages'])
   except (OSError,ValueError,TypeError,KeyError):
    record(self.root,'chat_publish_failed',session=ident(self.session),op=op,outcome='failed',reason='local_delivery')
  return response['result']
 def remote_snapshot(self):
  r=self.call('snapshot');return base64.b64decode(r['save']),base64.b64decode(r['receipt']),r['active']
 def synchronize(self):
  sav,rec,active=self.remote_snapshot()
  if active:
   status=self.call('status',tx=active)
   if status['state'] in ('offered','preparing'):return False
  if self.checkpoints.load()!=(sav,rec):self.checkpoints.publish(sav,rec)
  if active:self.call('ack',tx=active,checkpoint=sha(sav+rec))
  # Do not simulate while counterpart has not acknowledged the same decision.
  return self.call('snapshot')['active'] is None
 def prepare(self,tx):
  status=self.call('status',tx=tx)
  if status['state']!='preparing':return status
  sav,rec,active=self.remote_snapshot()
  if active!=tx:raise ValueError('wrong active transaction')
  local=self.checkpoints.load()
  if local!=(sav,rec):raise ValueError('client must start from authoritative checkpoint')
  draft=self.root/('prepare-'+tx);draft.mkdir(exist_ok=True)
  ready=draft/'ready.json'
  if ready.exists():
   meta=json.loads(ready.read_text());prepared=((draft/'city.sav').read_bytes(),(draft/'receipt.bin').read_bytes())
   if meta!={'base':sha(sav+rec),'prepared':sha(b''.join(prepared))}:raise ValueError('draft mismatch')
  else:
   source=draft/'base';source.mkdir(exist_ok=True)
   (source/'city.sav').write_bytes(sav);(source/'receipt.bin').write_bytes(rec)
   money=status['qty']*status['price']*(-1 if self.city==status['buyer'] else 1)
   try:prepared=Engine().run('apply',source,draft,status['qty'],money,receipt(rec)['seq']+1)
   except RuntimeError:
    self.call('abort',tx=tx)
    raise
   # Checkpoint publication remains on the old state until server decision is durable.
   for name in ('city.sav','receipt.bin'):
    with (draft/name).open('r+b') as f:os.fsync(f.fileno())
   durable(ready,json.dumps({'base':sha(sav+rec),'prepared':sha(b''.join(prepared))}).encode())
  return self.call('prepare',tx=tx,base=sha(sav+rec),save=base64.b64encode(prepared[0]).decode(),receipt=base64.b64encode(prepared[1]).decode())


 def deliver(self):
  if not self.synchronize():raise ValueError('city remains frozen')
  sav,rec=self.checkpoints.load()
  draft=self.root/('delivery-'+uuid.uuid4().hex);source=draft/'base';source.mkdir(parents=True)
  (source/'city.sav').write_bytes(sav);(source/'receipt.bin').write_bytes(rec)
  prepared=Engine().run('deliver',source,draft)
  self.call('checkpoint',base=sha(sav+rec),save=base64.b64encode(prepared[0]).decode(),receipt=base64.b64encode(prepared[1]).decode())
  return self.synchronize()
