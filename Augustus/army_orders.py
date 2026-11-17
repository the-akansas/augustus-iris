import room_options
"""Bounded asynchronous army orders; engine work never holds the room lock.

Preparation owns an unpublished SQLite copy. A cancelled/disconnected/stale job
cannot replace the active ledger. Publication and clock grants share room.lock.
"""
import json,sqlite3,uuid,time,os,hashlib,shutil
from pathlib import Path
from threading import Thread,Event
from contextlib import closing
import joint_save,army_install,live_trade
from expedition_state import identifier,integer,encode
from expedition_commit import PairedExpeditions

def initialize(db):
 db.execute('CREATE TABLE IF NOT EXISTS army_order(id TEXT PRIMARY KEY,city TEXT,payload TEXT,state TEXT,save_id INTEGER,result TEXT)')

def busy(db):
 return db.execute("SELECT * FROM army_order WHERE state IN ('saving','preparing') LIMIT 1").fetchone()

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None

def retain_offline(room,db):
 """An absent engine cannot ACK. Its already checkpointed city remains retained,
 not falsely acknowledged. A later owner loads that same complete native SAV.
 """
 if busy(db):return
 path=army_install.path(room)
 if not path.exists():return
 latest=joint_save.status(db)['complete']
 if not latest:return
 active=room.active_cities(db)
 with closing(sqlite3.connect(path)) as military:
  for action,city,digest_value in military.execute("SELECT id,city,hash FROM army_install WHERE state='pending'").fetchall():
   if city in active:continue
   part=db.execute('SELECT hash FROM joint_part WHERE id=? AND city=?',(latest['id'],city)).fetchone()
   if part and part[0]==digest_value:military.execute("UPDATE army_install SET state='retained' WHERE id=?",(action,))
  military.commit()

def checkpoint_install(room,db,row):
 """Publish a complete recovery point at the same frozen tick as both installs."""
 key=hashlib.sha256(('army-installed:'+row['id']).encode()).hexdigest()[:32]
 old=db.execute('SELECT id,state FROM joint_save WHERE request=?',(key,)).fetchone()
 if old and old['state']=='complete':return
 if old:sid=old['id']
 else:
  base=db.execute('SELECT ticks,speed FROM joint_save WHERE id=?',(row['save_id'],)).fetchone()
  sid=db.execute("INSERT INTO joint_save(request,ticks,state,speed) VALUES(?,?,'collecting',?)",(key,base['ticks'],base['speed'])).lastrowid
  room_options.capture(db,sid)
  db.execute('INSERT INTO joint_part SELECT ?,city,save,hash FROM joint_part WHERE id=?',(sid,row['save_id']))
  db.execute('INSERT INTO joint_provenance SELECT ?,city,ticks,source_id,mode FROM joint_provenance WHERE id=?',(sid,row['save_id']))
  with closing(sqlite3.connect(army_install.path(room))) as military:
   for city,sav,digest_value in military.execute('SELECT id,sav,hash FROM city_snapshot'):
    db.execute('UPDATE joint_part SET save=?,hash=? WHERE id=? AND city=?',(sav,digest_value,sid,city))
  db.commit()
 joint_save.finish_if_ready(room,db)
 state=db.execute('SELECT state FROM joint_save WHERE id=?',(sid,)).fetchone()[0]
 if state!='complete':raise RuntimeError('military recovery checkpoint pending')

def request(room,db,city,r):
 import army_seal
 if army_seal.SEALED:   # sealed (army_seal.py): an order of an older room ends at the next poll
  if r['op']=='army_order_status':poll(room,db)
  if r['op'] in ('army_overview','army_order_status'):return []
  raise ValueError(army_seal.REASON)
 if r['op']=='army_order_status':
  poll(room,db)
  rows=db.execute('SELECT * FROM army_order WHERE city=? ORDER BY rowid DESC LIMIT 1',(city,)).fetchall()
  return [dict(id=x['id'],state=x['state'],result=json.loads(x['result']) if x['result'] else None) for x in rows]
 if r['op']=='army_overview':
  p=army_install.path(room)
  if not p.exists():return []
  with closing(sqlite3.connect(p)) as military:
   military.row_factory=sqlite3.Row
   rows=[dict(x) for x in military.execute("SELECT id,origin,destination,phase,current,losses FROM expedition WHERE origin=? ORDER BY rowid DESC LIMIT 12",(city,))]
   for x in rows:
    b=military.execute('SELECT selection FROM paired_binding WHERE id=?',(x['id'],)).fetchone()
    x['role']=json.loads(b[0]).get('visitor',{}).get('role',1) if b else 1
   return rows
 action=r.get('action_id');identifier(action)
 if len(action)>32:raise ValueError('action id too long')
 if r['op']=='army_order_cancel':
  row=db.execute('SELECT * FROM army_order WHERE id=? AND city=?',(action,city)).fetchone()
  if not row:raise ValueError('unknown army order')
  if row['state'] in ('saving','preparing'):
   db.execute("UPDATE army_order SET state='cancelled',result=? WHERE id=?",(encode({'message':'파견 요청을 취소했습니다.'}),action));db.commit()
   task=getattr(room,'_army_order_task',None)
   if task and task['id']==action:task['cancelled']=True
   p=joint_save.pending(db)
   if p and p['id']==row['save_id']:db.execute("UPDATE joint_save SET state='cancelled' WHERE id=?",(p['id'],));db.commit()
  return {'accepted':True}
 destination=r.get('destination');identifier(destination)
 role=r.get('role');integer(role,1,2)
 form=r.get('formation');exp=r.get('expedition')
 if exp is None:integer(form,1,2**31-1)
 else:identifier(exp)
 expected=r.get('expected')
 if exp is None and (not isinstance(expected,dict) or set(expected)!= {'fort','unit','identities'}):raise ValueError('army selection identity required')
 payload=encode(dict(destination=destination,formation=form,expedition=exp,role=role,expected=expected))
 old=db.execute('SELECT * FROM army_order WHERE id=?',(action,)).fetchone()
 if old:
  if old['city']!=city or old['payload']!=payload:raise ValueError('conflicting army order')
  return {'accepted':True,'id':action,'state':old['state']}
 import army_seal
 if exp is None and army_seal.SEALED:raise ValueError(army_seal.REASON)   # new dispatch sealed; a returning expedition still passes
 if destination==city or destination not in room.active_cities(db):raise ValueError('상대 도시가 접속 중이어야 합니다.')
 if room.start_state(db)['phase']!='started':raise ValueError('게임 시작 후 파견할 수 있습니다.')
 task=getattr(room,'_army_order_task',None)
 if busy(db) or task and not task['done'].is_set() or army_install.pending(room) or joint_save.pending(db) or live_trade.busy(db):raise ValueError('저장 또는 교역을 처리 중입니다. 잠시 후 다시 시도하세요.')
 host=db.execute('SELECT city FROM lobby_invite ORDER BY rowid LIMIT 1').fetchone()[0]
 saved=joint_save.request(room,db,host,dict(op='save_begin',request_id=uuid.uuid4().hex))
 db.execute("INSERT INTO army_order VALUES(?,?,?,'saving',?,NULL)",(action,city,payload,saved['id']));db.commit()
 return {'accepted':True,'id':action,'state':'saving'}

def poll(room,db):
 row=busy(db)
 task=getattr(room,'_army_order_task',None)
 if task and task['done'].is_set() and (not row or row['id']!=task['id']):
  folder=task['path'].parent.resolve();parent=army_install.path(room).parent.resolve()
  if folder.parent==parent and folder.name.startswith('army-preparation-'):
   try:shutil.rmtree(folder)
   except OSError:pass
   else:room._army_order_task=None
 if not row:return
 payload=json.loads(row['payload']);target=payload['destination'];source=row['city'];path=army_install.path(room)
 def fail(message):
  db.execute("UPDATE army_order SET state='failed',result=? WHERE id=?",(encode({'message':message}),row['id']));db.commit()
  p=joint_save.pending(db)
  if p and p['id']==row['save_id']:db.execute("UPDATE joint_save SET state='cancelled' WHERE id=?",(p['id'],));db.commit()
  room.system_chat(db,message,(source,source),'army-failed:'+row['id'])
 import army_seal
 if army_seal.SEALED:fail(army_seal.REASON);return
 saved=db.execute('SELECT state,ticks FROM joint_save WHERE id=?',(row['save_id'],)).fetchone()
 if not saved or saved['state']=='cancelled':fail('저장이 취소되어 파견 요청도 취소했습니다.');return
 if saved['state']!='complete':return
 # Restart after atomic replacement but before the order's completion commit.
 if path.exists():
  with closing(sqlite3.connect(path)) as military:
   prior=military.execute('SELECT receipt FROM paired_action WHERE id=?',(row['id'],)).fetchone()
  if prior:
   checkpoint_install(room,db,row)
   db.execute("UPDATE army_order SET state='complete',result=? WHERE id=?",(prior[0],row['id']));db.commit();return
 if source not in room.active_cities(db) or target not in room.active_cities(db):
  fail('참가자의 연결이 끊겨 파견 요청을 취소했습니다. 병력은 변경하지 않았습니다.');return
 task=getattr(room,'_army_order_task',None)
 if task and not task['done'].is_set():return
 if task and task['id']==row['id']:
  if task.get('error'):
   detail=str(task['error'])
   (path.parent/'army-last-error.txt').write_text(detail,encoding='utf8')
   reason={'destination already has visiting army':'상대 도시에 파견군이 있습니다. 먼저 귀환시켜 주세요.',
           'army already active':'이미 파견 중인 군단입니다.',
           'not owner or not stationed':'귀환할 수 있는 파견군이 아닙니다.'}.get(detail)
   if not reason and any('가'<=c<='힣' for c in detail):reason=detail[:160]
   from error_text import reason as short
   fail((reason or '파견을 처리하지 못했습니다(원인: '+short(detail,90)+').')+' 병력은 변경하지 않았습니다.');return
  receipts_unchanged=all(bytes(db.execute('SELECT receipt FROM city WHERE id=?',(c,)).fetchone()[0])==rec for c,(_,rec) in task['parts'].items())
  if task.get('cancelled') or digest(path)!=task['base'] or room.grant!=saved['ticks'] or not receipts_unchanged:
   fail('도시 상태가 변경되어 파견 요청을 취소했습니다.');return
  os.replace(task['path'],path)
  checkpoint_install(room,db,row)
  db.execute("UPDATE army_order SET state='complete',result=? WHERE id=?",(encode(task['result']),row['id']));db.commit()
  text='파견군이 귀환했습니다.' if payload['expedition'] else '지원군이 도착했습니다.' if payload['role']==1 else '다른 플레이어의 공격군이 도착했습니다.'
  room.system_chat(db,text,(source,target),'army-complete:'+row['id'])
  return
 staging=path.parent/('army-preparation-'+uuid.uuid4().hex);staging.mkdir()
 candidate=staging/'expedition.sqlite';before=digest(path)
 if path.exists():
  with closing(sqlite3.connect(path)) as src,closing(sqlite3.connect(candidate)) as dst:src.backup(dst)
 parts={}
 for c in (source,target):
  part=db.execute('SELECT save FROM joint_part WHERE id=? AND city=?',(row['save_id'],c)).fetchone()
  rec=db.execute('SELECT receipt FROM city WHERE id=?',(c,)).fetchone()
  if not part or not rec:fail('파견에 필요한 도시 저장이 없습니다.');return
  parts[c]=(bytes(part[0]),bytes(rec[0]))
 cities=list(room.coordinator.scenario['cities']);ticks=saved['ticks'];action=row['id']
 task=dict(id=action,path=candidate,base=before,parts=parts,done=Event(),cancelled=False)
 room._army_order_task=task
 def prepare():
  try:
   from expedition_adapter import inspect_bytes
   from expedition_visit import transfer
   paired=PairedExpeditions(candidate,cities,staging/'drafts')
   with paired.store.connection() as military:
    epoch=military.execute('SELECT epoch FROM metadata').fetchone()[0]
    revisions={r['id']:r['revision'] for r in military.execute('SELECT id,revision FROM city_snapshot')}
   for c,(sav,rec) in parts.items():
    adopted=paired.adopt_inspected(c,inspect_bytes(sav,rec,paired.scratch),epoch,revisions.get(c))
    revisions[c]=adopted['city_revision']
   task['result']=transfer(paired,action,source,epoch,revisions[source],revisions[target],ticks=ticks,**payload)
  except BaseException as error:task['error']=error
  finally:task['done'].set()
 db.execute("UPDATE army_order SET state='preparing' WHERE id=?",(action,));db.commit()
 Thread(target=prepare,name='army-order',daemon=True).start()
