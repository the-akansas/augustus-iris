"""Receipt-confirmed live military transfers; no room save/clock barrier."""
import json,uuid,time

SUPPORT_LIMIT=6 # support legions one city may host at a time (its own limit is six forts)
SUPPORT_FULL='이 도시는 이미 지원군 여섯 군단을 받고 있습니다. 한 군단이 돌아간 뒤 보내 주세요.'
ATTACK_LIMIT=2 # attack forces one player may have at (or on the way to) one city at a time (user, 2026-11-12: a trial)
ATTACK_FULL='이 도시에는 공격군을 두 부대까지만 보낼 수 있습니다. 한 부대가 돌아온 뒤 보내 주세요.'
# One player never has support and attack forces at the same city at once: in the host city they are on opposite
# sides (support fights for the city, attackers against it) and would fight each other.
ROLE_CONFLICT='같은 도시에 지원군과 공격군을 함께 둘 수 없습니다. 먼저 보낸 군단이 돌아온 뒤 보내 주세요.'
OPEN="state NOT IN ('returned','failed')"

def initialize(db):
 db.execute('CREATE TABLE IF NOT EXISTS army_live(id TEXT PRIMARY KEY,token INTEGER UNIQUE,origin TEXT,destination TEXT,role INTEGER,formation INTEGER,state TEXT,manifest TEXT,cancel INTEGER NOT NULL DEFAULT 0,action TEXT,failed INTEGER NOT NULL DEFAULT 0)')
 db.execute('CREATE TABLE IF NOT EXISTS army_live_command(id TEXT PRIMARY KEY,expedition TEXT,city TEXT,step INTEGER,payload TEXT,state TEXT,attempts INTEGER NOT NULL DEFAULT 0,result TEXT)')
 for name in ('transit_step','ticks_left','transit_seen','wiped','released'):
  if name not in {r[1] for r in db.execute('PRAGMA table_info(army_live)')}:db.execute('ALTER TABLE army_live ADD COLUMN '+name+' INTEGER NOT NULL DEFAULT 0')

def clock_tick(room):
 room.army_tick=max(getattr(room,'army_tick',0),max((p[0] for p in room.progress.values()),default=0))
 return room.army_tick

def transit(room,db,row,step,payload,ticks=1600):
 # Two native game months. No destination ownership before an arrival receipt.
 db.execute("UPDATE army_live SET state='travelling',manifest=?,transit_step=?,ticks_left=?,transit_seen=? WHERE id=?",(payload,step,ticks,clock_tick(room),row['id']))

def advance(room,db):
 now=clock_tick(room)
 for row in db.execute("SELECT * FROM army_live WHERE state='travelling'").fetchall():
  left=max(0,row['ticks_left']-max(0,now-row['transit_seen'])) if row['transit_seen']>=0 else row['ticks_left']
  db.execute('UPDATE army_live SET ticks_left=?,transit_seen=? WHERE id=?',(left,now,row['id']))
  if not left:enqueue(db,row,row['destination'] if row['transit_step']==2 else row['origin'],row['transit_step'],row['manifest'])
 settle_departed(room,db)
 db.commit()

def settle_departed(room,db):
 """A player left the room (its city no longer takes part). Nothing waits on that city and no soldier is lost to it.
 Host city left ('released'): its visitors go home with the troops they arrived with (the last state the room
   knows; what happened in a city that is gone cannot be asked). Its own copy is removed if it ever comes back:
   a clean-up command stays queued for it and its answers no longer move the expedition.
 Sender left: its expeditions are called back like an order cancel; the last step (back into its fort) waits for it."""
 if not getattr(room,'started',False):return
 active=set(room.active_cities(db));gone=set(room.coordinator.scenario['cities'])-active
 if not gone:return
 for row in db.execute('SELECT * FROM army_live WHERE released=0 AND '+OPEN).fetchall():
  if row['destination'] in gone:
   state=row['state'];waiting=db.execute("SELECT 1 FROM army_live_command WHERE expedition=? AND city=? AND state='pending'",(row['id'],row['destination'])).fetchone()
   if state=='travelling' and row['transit_step']==2:
    db.execute('UPDATE army_live SET released=1 WHERE id=?',(row['id'],));transit(room,db,row,4,row['manifest'],max(50,1600-row['ticks_left']))
   elif state in ('arriving','stationed','recalling') or (state=='deferred' and waiting):
    db.execute('UPDATE army_live SET released=1 WHERE id=?',(row['id'],))
    if not db.execute("SELECT 1 FROM army_live_command WHERE expedition=? AND city=? AND step=3 AND state='pending'",(row['id'],row['destination'])).fetchone():
     db.execute("INSERT INTO army_live_command(id,expedition,city,step,payload,state) VALUES(?,?,?,3,?,'pending')",(uuid.uuid4().hex,row['id'],row['destination'],row['manifest']))
    transit(room,db,row,4,row['manifest'])
  elif row['origin'] in gone and not row['cancel']:
   db.execute('UPDATE army_live SET cancel=1 WHERE id=?',(row['id'],))
   if row['state']=='travelling' and row['transit_step']==2:transit(room,db,row,4,row['manifest'],max(50,1600-row['ticks_left']))
   elif row['state']=='stationed':enqueue(db,row,row['destination'],3,row['manifest'])

def overview(row,city):
 return dict(id=row['id'],action=row['action'],token=row['token'],formation=row['formation'],origin=row['origin'],destination=row['destination'],phase=row['state'],current='{}',losses=0,role=row['role'],incoming=row['destination']==city,wiped=bool(row['wiped']),released=bool(row['released']),remaining_ticks=row['ticks_left'] if row['state']=='travelling' else None,returning=row['transit_step']==4)

def enqueue(db,row,city,step,payload):
 key=uuid.uuid4().hex
 db.execute("INSERT INTO army_live_command(id,expedition,city,step,payload,state) VALUES(?,?,?,?,?,'pending')",(key,row['id'],city,step,payload))
 db.execute("UPDATE army_live SET state=? WHERE id=?",({1:'departing',2:'arriving',3:'recalling',4:'returning'}[step],row['id']))

def seal_close(db):
 """Army dispatch sealed (army_seal.py): expeditions left open by an older room end here, without moving anybody.
 The games release their side when the save is loaded (src/multiplayer/army_seal.c)."""
 if not db.execute('SELECT 1 FROM army_live WHERE '+OPEN+" UNION SELECT 1 FROM army_live_command WHERE state='pending' LIMIT 1").fetchone():return
 db.execute("UPDATE army_live SET state='failed',released=1 WHERE "+OPEN)
 db.execute("UPDATE army_live_command SET state='unapplied',result=? WHERE state='pending'",(json.dumps([False,'sealed']),))
 db.commit()

def request(room,db,city,r):
 import army_seal
 if army_seal.SEALED:
  # Sealed: nothing to list, nothing for a game to apply, every order refused (user 2026-11-14: no effect in the game).
  initialize(db);seal_close(db);op=r['op']
  if op in ('army_overview','army_order_status'):return []
  if op=='army_live_poll':return dict(command=None)
  if op=='army_live_report':return dict(accepted=True)
  raise ValueError(army_seal.REASON)
 initialize(db);advance(room,db);op=r['op']
 if op=='army_overview':
  return [overview(x,city) for x in db.execute('SELECT * FROM army_live WHERE origin=? OR destination=?',(city,city))]
 if op=='army_order_status':
  # 'preparing' (the dispatch window waits) only until the sender's own game has confirmed the departure; a legion
  # on its way ('moving') no longer blocks the next order, so one city can send several legions (user, 2026-11-13).
  return [dict(id=x['action'],state='complete' if x['state'] in ('stationed','returned') else 'failed' if x['state']=='failed' else 'preparing' if x['state'] in ('departing','deferred') else 'moving',result=dict(message='군단 확인 대기' if x['state']=='deferred' else '군단을 이동하고 있습니다.' if x['state'] not in ('stationed','returned','failed') else '군단을 보내지 못했습니다. 병사들이 모두 요새에 모여 쉬고 있는지 확인한 뒤 다시 보내 주세요.' if x['state']=='failed' else '군단 처리를 마쳤습니다.')) for x in db.execute('SELECT * FROM army_live WHERE origin=? ORDER BY rowid DESC LIMIT 1',(city,))]
 if op=='army_live_poll':
  row=db.execute("SELECT c.*,a.token,a.role,a.formation FROM army_live_command c JOIN army_live a ON c.expedition=a.id WHERE c.city=? AND c.state='pending' AND c.attempts<6 AND (? IS NULL OR c.id=?) ORDER BY c.rowid LIMIT 1",(city,r.get('command'),r.get('command'))).fetchone()
  if not row:return dict(command=None)
  db.execute('UPDATE army_live_command SET attempts=attempts+1 WHERE id=?',(row['id'],))
  if row['attempts']+1==6:db.execute("UPDATE army_live SET state='deferred' WHERE id=?",(row['expedition'],))
  db.commit();return dict(command=dict(row))
 if op=='army_live_report':
  command=db.execute('SELECT * FROM army_live_command WHERE id=? AND city=?',(r.get('command'),city)).fetchone()
  if not command:raise ValueError('unknown military command')
  applied=r.get('applied');payload=r.get('payload')
  if type(applied)!=bool or not isinstance(payload,str) or len(payload)>4095:raise ValueError('military receipt')
  encoded=json.dumps([applied,payload])
  if command['state']!='pending':
   if command['result']!=encoded:raise ValueError('conflicting military receipt')
   return dict(accepted=True)
  row=db.execute('SELECT * FROM army_live WHERE id=?',(command['expedition'],)).fetchone();step=command['step']
  if applied and (not payload.startswith('EX2 '+str(row['token'])+' ') or len(payload.splitlines())<1):raise ValueError('military manifest')
  db.execute('UPDATE army_live_command SET state=?,result=? WHERE id=?',('applied' if applied else 'unapplied',encoded,command['id']))
  if row['released'] and command['city']==row['destination']:
   # The host city left and came back: this only tidies its own map; the troops already went home (settle_departed).
   db.commit();return dict(accepted=True)
  if not applied:
   if step==1:db.execute("UPDATE army_live SET state='failed' WHERE id=?",(row['id'],))
   elif step==2:
    db.execute('UPDATE army_live SET failed=1 WHERE id=?',(row['id'],));transit(room,db,row,4,row['manifest'])
   else:db.execute("UPDATE army_live SET state='deferred' WHERE id=?",(row['id'],))
  elif step==1:
   db.execute('UPDATE army_live SET manifest=? WHERE id=?',(payload,row['id']))
   transit(room,db,row,4 if row['cancel'] else 2,payload)
  elif step==2:
   if row['cancel']:enqueue(db,row,row['destination'],3,row['manifest'])
   else:db.execute("UPDATE army_live SET state='stationed' WHERE id=?",(row['id'],))
  elif step==3:transit(room,db,row,4,payload)
  else:db.execute('UPDATE army_live SET state=? WHERE id=?',('failed' if row['failed'] else 'returned',row['id']))
  db.commit();return dict(accepted=True)
 if op=='army_wiped':
  # The host city reports a support legion with nobody left, or an attack force that left its map (retreated after
  # looting, or wiped out): it goes home by itself with whoever is left (the host's step 3 knows who that is).
  row=db.execute("SELECT * FROM army_live WHERE id=? AND destination=? AND role IN (1,2)",(r.get('expedition'),city)).fetchone()
  if not row:raise ValueError('unknown military order')
  if row['state']=='stationed' and not row['wiped']:
   db.execute('UPDATE army_live SET wiped=1 WHERE id=?',(row['id'],));enqueue(db,row,row['destination'],3,row['manifest']);db.commit()
  return dict(accepted=True)
 if op=='army_send_home':
  # The host city sends a stationed support legion back to its owner (survivors as they are now).
  row=db.execute("SELECT * FROM army_live WHERE id=? AND destination=? AND role=1",(r.get('expedition'),city)).fetchone()
  if not row:raise ValueError('unknown military order')
  if row['state']=='stationed' and not row['released']:
   enqueue(db,row,row['destination'],3,row['manifest']);db.commit()
  return dict(accepted=True)
 if op=='army_order_cancel':
  row=db.execute('SELECT * FROM army_live WHERE action=? AND origin=?',(r.get('action_id'),city)).fetchone()
  if not row:raise ValueError('unknown military order')
  db.execute('UPDATE army_live SET cancel=1 WHERE id=?',(row['id'],))
  if row['state']=='travelling' and row['transit_step']==2:transit(room,db,row,4,row['manifest'],max(50,1600-row['ticks_left']))
  if row['state']=='stationed':enqueue(db,row,row['destination'],3,row['manifest'])
  db.commit();return dict(accepted=True)
 if op!='army_order':raise ValueError('unknown military operation')
 if not room.started or city not in room.active_cities(db):raise ValueError('game not running')
 action=r.get('action_id');destination=r.get('destination');role=r.get('role')
 if not isinstance(action,str) or len(action)!=32 or any(x not in '0123456789abcdef' for x in action):raise ValueError('action id')
 if destination==city or destination not in room.active_cities(db) or role not in (1,2):raise ValueError('military destination')
 prior=db.execute('SELECT * FROM army_live WHERE action=?',(action,)).fetchone()
 if prior:
  if r.get('expedition') and r['expedition']!=prior['id']:raise ValueError('conflicting expedition replay')
  if not r.get('expedition'):
   expected=r.get('expected')
   if not isinstance(expected,dict) or set(expected)!={'fort','unit','identities'}:raise ValueError('army selection')
   try:payload=' '.join(map(str,[expected['fort'],expected['unit'],len(expected['identities']),*[x for v in expected['identities'] for x in v]]))
   except (TypeError,KeyError):raise ValueError('army selection')
   original=db.execute('SELECT payload FROM army_live_command WHERE expedition=? AND step=1',(prior['id'],)).fetchone()
   if not original or original[0]!=payload:raise ValueError('conflicting army identity')
  if not r.get('expedition') and prior['formation']!=r.get('formation'):raise ValueError('conflicting army selection')
  if prior['origin']!=city or prior['destination']!=destination or prior['role']!=role:raise ValueError('conflicting army replay')
  return dict(accepted=True,id=action,state=prior['state'])
 if r.get('expedition'):
  row=db.execute("SELECT * FROM army_live WHERE id=? AND origin=? AND destination=? AND role=?",(r['expedition'],city,destination,role)).fetchone()
  if not row or row['state']!='stationed':raise ValueError('not stationed')
  db.execute('UPDATE army_live SET action=? WHERE id=?',(action,row['id']));enqueue(db,row,destination,3,row['manifest']);db.commit();return dict(accepted=True,id=action)
 import army_seal
 if army_seal.SEALED:raise ValueError(army_seal.REASON)   # new dispatch sealed (support and attack); stationed armies above can still return
 form=r.get('formation');expected=r.get('expected')
 if type(form)!=int or form<=0 or not isinstance(expected,dict) or set(expected)!={'fort','unit','identities'}:raise ValueError('army selection')
 identities=expected['identities']
 if not isinstance(identities,list) or not 1<=len(identities)<=16 or any(not isinstance(v,list) or len(v)!=2 or any(type(x)!=int or x<0 for x in v) for v in identities):raise ValueError('army identities')
 if type(expected['fort'])!=int or type(expected['unit'])!=int:raise ValueError('army identity fields')
 if db.execute("SELECT 1 FROM army_live WHERE state NOT IN ('returned','failed') AND origin=? AND formation=?",(city,form)).fetchone():raise ValueError('army already dispatched')
 if role==1 and db.execute("SELECT count(*) FROM army_live WHERE destination=? AND role=1 AND state NOT IN ('returned','failed')",(destination,)).fetchone()[0]>=SUPPORT_LIMIT:raise ValueError(SUPPORT_FULL)
 if db.execute('SELECT 1 FROM army_live WHERE origin=? AND destination=? AND role!=? AND '+OPEN,(city,destination,role)).fetchone():raise ValueError(ROLE_CONFLICT)
 if role==2 and db.execute('SELECT count(*) FROM army_live WHERE origin=? AND destination=? AND role=2 AND '+OPEN,(city,destination)).fetchone()[0]>=ATTACK_LIMIT:raise ValueError(ATTACK_FULL)
 token=db.execute('SELECT COALESCE(MAX(token),0)+1 FROM army_live').fetchone()[0]
 if token>=2**31:raise ValueError('army identity capacity')
 db.execute("INSERT INTO army_live(id,token,origin,destination,role,formation,state,manifest,action) VALUES(?,?,?,?,?,?,'departing','',?)",(action,token,city,destination,role,form,action))
 row=db.execute('SELECT * FROM army_live WHERE id=?',(action,)).fetchone()
 payload=' '.join(map(str,[expected['fort'],expected['unit'],len(identities),*[x for v in identities for x in v]]))
 enqueue(db,row,city,1,payload);db.commit();return dict(accepted=True,id=action,state='preparing')

def validate_snapshot(data,cities):
 import sqlite3
 db=sqlite3.connect(':memory:');initialize(db)
 try:
  for table,rows in [('army_live',data['army']),('army_live_command',data['commands'])]:
   columns={r[1] for r in db.execute('PRAGMA table_info('+table+')')}
   if not isinstance(rows,list) or len(rows)>10000:raise ValueError('military snapshot size')
   for row in rows:
    if table=='army_live' and isinstance(row,dict) and data.get('version')==7:
     for name in ('transit_step','ticks_left','transit_seen'):row.setdefault(name,0)
    if table=='army_live' and isinstance(row,dict):row.setdefault('wiped',0);row.setdefault('released',0) # saves from before these were tracked
    if not isinstance(row,dict) or set(row)!=columns:raise ValueError('military snapshot columns')
    keys=list(row);db.execute('INSERT INTO '+table+'('+','.join(keys)+') VALUES('+','.join('?' for _ in keys)+')',[row[k] for k in keys])
  ids={row['id'] for row in data['army']}
  for row in data['army']:
   if row['origin'] not in cities or row['destination'] not in cities or row['origin']==row['destination'] or row['role'] not in (1,2) or row['state'] not in ('departing','arriving','stationed','recalling','returning','returned','failed','deferred','travelling') or not 0<row['token']<2**31:raise ValueError('military snapshot identity')
  for row in data['army']:
   if any(type(row[k])!=int for k in ('transit_step','ticks_left','transit_seen')) or row['transit_step'] not in (0,2,4) or not 0<=row['ticks_left']<=1600 or row['transit_seen']< -1 or (row['state']=='travelling' and row['transit_step'] not in (2,4)):raise ValueError('military transit snapshot')
  for row in data['commands']:
   if row['expedition'] not in ids or row['city'] not in cities or row['step'] not in (1,2,3,4) or row['state'] not in ('pending','applied','unapplied') or not 0<=row['attempts']<=6 or len(row['payload'])>4095:raise ValueError('military snapshot command')
 finally:db.close()
