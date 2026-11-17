"""Paired live snapshots. Pending sets never replace the last complete set."""
from coordinator import blob,sha
import throne_state
import transport_snapshot
import save_provenance
import objectives
import expedition_snapshot

def initialize(db):
 import room_options
 import observe_permissions
 observe_permissions.initialize(db)
 room_options.initialize(db)
 db.executescript('''CREATE TABLE IF NOT EXISTS joint_save(id INTEGER PRIMARY KEY AUTOINCREMENT,request TEXT UNIQUE,ticks INTEGER,state TEXT,speed INTEGER);
 CREATE TABLE IF NOT EXISTS joint_part(id INTEGER,city TEXT,save BLOB,hash TEXT,PRIMARY KEY(id,city));''')

 # Older experimental sets have no recorded target speed; retain NULL rather than invent it.
 if 'speed' not in {r[1] for r in db.execute('PRAGMA table_info(joint_save)')}:db.execute('ALTER TABLE joint_save ADD COLUMN speed INTEGER')
 # 'manual' (the host's save command, the save before the host leaves) or 'auto' (timer, trade, cargo, army).
 # Recorded for the guests' copies (replica_worker.prune). Older rows: NULL.
 if 'kind' not in {r[1] for r in db.execute('PRAGMA table_info(joint_save)')}:db.execute('ALTER TABLE joint_save ADD COLUMN kind TEXT')

 transport_snapshot.initialize(db)
 save_provenance.initialize(db)
 objectives.initialize(db)
 expedition_snapshot.initialize(db)
 throne_state.initialize(db)

def finish_if_ready(room,db):
 saved=pending(db)
 if saved and db.execute('SELECT count(*) FROM joint_part WHERE id=?',(saved['id'],)).fetchone()[0]==len(room.coordinator.scenario['cities']) and objectives.ready_to_capture(room,db,saved['ticks']):
  prepared=expedition_snapshot.prepare_capture(room,db,saved['id'])
  if prepared is None:return
  military=expedition_snapshot.capture(room,db,saved['id'],prepared=prepared)
  db.execute("UPDATE joint_save SET state='complete' WHERE id=?",(saved['id'],))
  transport_snapshot.capture(db,saved['id'])
  throne_state.capture(db,saved['id'],room.coordinator.scenario,saved['ticks'],present=set(room.active_cities(db)))
  import observe_permissions
  observe_permissions.capture(db,saved['id'])
  import imperial_progress
  imperial_progress.capture(db,saved['id'],room.coordinator.scenario)
  save_provenance.capture_boundary(db,saved['id'])
  db.commit()
  prune(room,db)
  expedition_snapshot.notify_expired(room,db,military)

def prune(room,db):
 """One save per game (user 2026-11-15: "수동저장이든 자동저장이든 게임당 최신1개만"): the city files of older complete
 saves are dropped and the save marked 'pruned', except the saves something still stands on: a save being made,
 the base and result of a trade or cargo transfer that has not finished, an army order's save, and in a throne
 room the save a new host would restore (throne_state.handover_save). The file keeps its size; the freed space
 is used by the next saves."""
 newest=db.execute("SELECT max(id) FROM joint_save WHERE state='complete'").fetchone()[0]
 if newest is None:return
 keep={newest}|{r[0] for r in db.execute("SELECT id FROM joint_save WHERE state='collecting'")}
 tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
 if 'live_transfer' in tables:
  for r in db.execute("SELECT base,result FROM live_transfer WHERE state NOT IN ('finished','rejected')"):keep.update(r)
 if 'army_order' in tables:
  keep.update(r[0] for r in db.execute("SELECT save_id FROM army_order WHERE state NOT IN ('complete','failed')"))
 if throne_state.spec(room.coordinator.scenario) is not None:keep.add(throne_state.handover_save(db,room.coordinator.scenario))
 old=[r[0] for r in db.execute("SELECT id FROM joint_save WHERE state='complete' AND id<?",(newest,)) if r[0] not in keep]
 if not old:return
 marks=','.join('?'*len(old))
 db.execute('DELETE FROM joint_part WHERE id IN ('+marks+')',old)
 db.execute("UPDATE joint_save SET state='pruned' WHERE id IN ("+marks+")",old)
 db.commit()

def pending(db):return db.execute("SELECT * FROM joint_save WHERE state='collecting' ORDER BY id LIMIT 1").fetchone()
def status(db):
 p=pending(db);last=db.execute("SELECT id,ticks,speed FROM joint_save WHERE state='complete' ORDER BY id DESC LIMIT 1").fetchone()
 result=dict(pending=dict(p) if p else None,complete=dict(last) if last else None)
 if last:result['complete']['remaining']=bool(db.execute('SELECT 1 FROM joint_provenance WHERE id=?',(last['id'],)).fetchone())
 return result
def request(room,db,city,r):
 op=r['op'];p=pending(db)
 if op in ('save_replica_meta','save_replica_part'):
  from save_replica import export
  return export(room,db,r)
 if op in ('save_begin','save_cancel'):
  host=db.execute('SELECT city FROM lobby_invite ORDER BY rowid LIMIT 1').fetchone()
  if not host or host['city']!=city:raise ValueError('host only')
 if op=='save_begin':
  key=r.get('request_id')
  if not isinstance(key,str) or len(key)!=32 or any(c not in '0123456789abcdef' for c in key):raise ValueError('request id')
  old=db.execute('SELECT * FROM joint_save WHERE request=?',(key,)).fetchone()
  if old:return dict(old)
  if p:raise ValueError('save already pending')
  cities=room.coordinator.scenario['cities']
  active=room.active_cities(db)
  retained=save_provenance.retained_parts(room,db,active) if len(active)<len(cities) else []
  now=room.clock()
  if any(c not in room.progress or now-room.progress[c][1]>=1.5 for c in active):raise ValueError('both engines required')
  kind=r.get('kind','auto')
  if kind not in ('auto','manual'):raise ValueError('save kind')
  sid=db.execute("INSERT INTO joint_save(request,ticks,state,speed,kind) VALUES(?,?,'collecting',?,?)",(key,room.grant,db.execute('SELECT value FROM room_speed').fetchone()[0],kind)).lastrowid
  import room_options
  room_options.capture(db,sid)
  for peer,data,digest,ticks,source in retained:
   db.execute('INSERT INTO joint_part VALUES(?,?,?,?)',(sid,peer,data,digest))
   db.execute('INSERT INTO joint_provenance VALUES(?,?,?,?,?)',(sid,peer,ticks,source,'retained'))
  if retained:
   for peer in active:db.execute('INSERT INTO joint_provenance VALUES(?,?,?,?,?)',(sid,peer,room.grant,0,'current'))
  db.commit()
  return dict(pending(db))
 if op=='save_cancel':
  if p:db.execute("UPDATE joint_save SET state='cancelled' WHERE id=?",(p['id'],));db.commit()
  return status(db)
 if op=='save_part':
  sid=r.get('id');ticks=r.get('ticks');data=blob(r.get('save'))
  saved=db.execute('SELECT * FROM joint_save WHERE id=?',(sid,)).fetchone()
  old=db.execute('SELECT hash FROM joint_part WHERE id=? AND city=?',(sid,city)).fetchone()
  if old:
   if old['hash']!=sha(data):raise ValueError('conflicting duplicate')
   return status(db)
  if not saved or saved['state']!='collecting' or type(ticks)!=int or ticks!=saved['ticks'] or room.progress.get(city,(-1,0))[0]!=ticks:raise ValueError('wrong save barrier')
  db.execute('INSERT INTO joint_part VALUES(?,?,?,?)',(sid,city,data,sha(data)))
  finish_if_ready(room,db)
  db.commit();return status(db)
 if op=='save_status':
  finish_if_ready(room,db)
  return status(db)
 raise ValueError('unknown save op')
