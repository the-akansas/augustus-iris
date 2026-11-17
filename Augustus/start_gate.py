"""Server-owned download acknowledgement barrier before the five-second start."""
import secrets
from pathlib import Path
from coordinator import sha
from network_diagnostics import record,ident
CONTACT_TIMEOUT=30
DOWNLOAD_TIMEOUT=120

def event(room,kind,**fields):
 record(Path(room.coordinator.path).parent,kind,session=ident(room.coordinator.session),attempt=(getattr(room,'start_gate',None) or {}).get('id',''),**fields)
def cancel(room,db,reason,city=None):
 name=db.execute('SELECT name FROM player_name WHERE city=?',(city,)).fetchone() if city else None
 label=(name[0] if name else city or '참가자')
 messages={'connection':label+'님의 연결 응답이 늦습니다. 다시 시도해 주세요.','ready':label+'님이 준비를 취소했습니다.','host':'방장이 시작을 취소했습니다.','left':label+'님이 방을 나갔습니다.','download':label+'님의 도시 파일 준비 시간이 초과되었습니다.','changed':'도시 구성이 변경되었습니다. 다시 시작해 주세요.','snapshot':'도시 저장이 변경되었습니다. 다시 시작해 주세요.'}
 event(room,'start_cancel',outcome='failed',reason=reason,peer=ident(city) if city else '')
 room.start_failure='시작 취소: '+messages[reason];room.start_at=None;room.start_step=None;room.start_gate=None
 db.execute('DELETE FROM play_session');db.commit();room.system_chat(db,room.start_failure)
def state(room,db):
 if room.started:room.cancel_requested=False;return dict(phase='started',remaining=0)
 if getattr(room,'cancel_requested',False) and room.start_at is not None:   # the host's 시작 취소 (lobby room_start_cancel)
  room.cancel_requested=False;cancel(room,db,'host');return state(room,db)
 if room.start_at is None:
  if not getattr(room,'roster_job',None):room.cancel_requested=False   # nothing under way: a late request is dropped
  room.start_gate=None
  return dict(phase='lobby',remaining=0,detail=getattr(room,'start_failure',''))
 now=room.clock();g=getattr(room,'start_gate',None)
 if g is None:
  members=room.active_cities(db)
  g=room.start_gate={'id':secrets.token_hex(8),'layout':room.coordinator.scenario['sha256'],'members':members,'acks':set(),'deadline':now+DOWNLOAD_TIMEOUT,'counting':False,'hashes':{c:sha(db.execute('SELECT save FROM city WHERE id=?',(c,)).fetchone()[0]) for c in members}}
  room.start_failure='';event(room,'start_prepare',phase='loading',waiting=len(members));room.system_chat(db,'도시 파일을 준비합니다. 모든 참가자의 확인 후 카운트다운을 시작합니다.')
 if set(room.active_cities(db))!=set(g['members']):
  cancel(room,db,'left');return state(room,db)
 if g['layout']!=room.coordinator.scenario['sha256']:
  cancel(room,db,'changed');return state(room,db)
 host=db.execute('SELECT city FROM lobby_invite ORDER BY rowid LIMIT 1').fetchone()[0]
 for c in g['members']:
  seen,ready=room.presence.get(c,(-1e30,False))
  if now-seen>=CONTACT_TIMEOUT:
   cancel(room,db,'connection',c);return state(room,db)
  if c!=host and not ready:
   cancel(room,db,'ready',c);return state(room,db)
 waiting=[c for c in g['members'] if c not in g['acks']]
 if waiting:
  if now>=g['deadline']:
   cancel(room,db,'download',waiting[0]);return state(room,db)
  names=[(db.execute('SELECT name FROM player_name WHERE city=?',(c,)).fetchone() or [c])[0] for c in waiting]
  return dict(phase='loading',remaining=0,attempt=g['id'],layout=g['layout'],hashes=g['hashes'],detail=', '.join(names)+' 도시 파일 준비 중 ('+str(len(g['acks']))+'/'+str(len(g['members']))+')')
 if not g['counting']:
  g['counting']=True;room.start_at=now+5;room.start_step=None;event(room,'start_countdown',phase='countdown')
 import math
 remaining=max(0,math.ceil(room.start_at-now))
 if remaining!=room.start_step:
  room.start_step=remaining;room.system_chat(db,f'{remaining}초 후 게임을 시작합니다.' if remaining else '게임을 시작합니다.')
 if remaining==0:
  if any(sha(db.execute('SELECT save FROM city WHERE id=?',(c,)).fetchone()[0])!=g['hashes'][c] for c in g['members']):
   cancel(room,db,'snapshot');return state(room,db)
  import room_options
  for city in g['members']:room_options.require_ack(room,db,city)
  room_options.lock(db)
  if not db.execute("SELECT 1 FROM joint_save WHERE state='complete'").fetchone():
   import migration
   migration.baseline(room)
  room.started=True;event(room,'start_complete',phase='started')
 return dict(phase='started' if room.started else 'countdown',remaining=remaining,attempt=g['id'])
def acknowledge(room,db,city,r):
 current=state(room,db);g=getattr(room,'start_gate',None)
 if g is None or r.get('attempt')!=g['id'] or r.get('layout')!=g['layout'] or city not in g['members']:raise ValueError('stale start acknowledgement')
 expected=sha(db.execute('SELECT save FROM city WHERE id=?',(city,)).fetchone()[0])
 if expected!=g['hashes'][city]:
  cancel(room,db,'snapshot',city);raise ValueError('stale start acknowledgement')
 if r.get('save_hash')!=expected:raise ValueError('start snapshot mismatch')
 if city not in g['acks']:event(room,'start_download_ok',peer=ident(city),phase='loading')
 g['acks'].add(city)
 return state(room,db)
