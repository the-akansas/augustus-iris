import room_options
"""Cargo-backed transfers. Only paired SQLite commits publish worker results."""
import base64,uuid,subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import save_provenance
import joint_save,transport_snapshot,cargo_snapshot
from coordinator import sha

def initialize(db):
 db.executescript('''CREATE TABLE IF NOT EXISTS live_cargo(id INTEGER PRIMARY KEY,phase TEXT,cargo BLOB);
 CREATE TABLE IF NOT EXISTS live_cargo_ack(result INTEGER,city TEXT,PRIMARY KEY(result,city));''')
 if 'source_route' not in {r[1] for r in db.execute('PRAGMA table_info(live_cargo)')}:
  db.execute('ALTER TABLE live_cargo ADD COLUMN source_route INTEGER NOT NULL DEFAULT 0')
 db.execute('CREATE TABLE IF NOT EXISTS live_collection(id INTEGER PRIMARY KEY,building INTEGER)')
def get(db,tid):return db.execute('SELECT * FROM live_cargo WHERE id=?',(tid,)).fetchone()
def stop_job(room):
 job=getattr(room,'live_prepare_job',None)
 if job:
  for f in job['jobs'].values():f.cancel()
  job['pool'].shutdown(wait=False);room.live_prepare_job=None
def start_save(room,db,t,phase):
 if joint_save.pending(db):raise ValueError('save in progress')
 host=db.execute('SELECT city FROM lobby_invite ORDER BY rowid LIMIT 1').fetchone()[0]
 saved=joint_save.request(room,db,host,dict(op='save_begin',request_id=uuid.uuid4().hex))
 db.execute('UPDATE live_cargo SET phase=? WHERE id=?',(phase,t['id']))
 db.execute("UPDATE live_transfer SET state='saving',base=?,result=NULL WHERE id=?",(saved['id'],t['id']));db.commit()
def worker(phase,incoming,source,target,t):
 from city_client import Engine
 e=Engine();target.mkdir(parents=True,exist_ok=True)
 if phase=='load':
  if incoming:
   e.run('live-in',source,target,t['quantity'],-t['money'],t['resource'])
   return (source/'city.sav').read_bytes(),None # Validate buyer, never install dry-run goods/payment.
  e.run('cargo-load-caravan' if t.get('source_route') else 'cargo-load',source,target,t['quantity'],t['resource'],t['id'])
 elif phase=='depart':
  if incoming:return (source/'city.sav').read_bytes(),None
  e.run('cargo-depart',source,target,t['quantity'],t['resource'],t['id'])
 elif phase=='refund':
  if incoming:return (source/'city.sav').read_bytes(),None
  e.run('cargo-return-sea' if t.get('source_route')==3 else 'cargo-return',source,target,t['quantity'],t['resource'],t['id'])
 elif phase=='deliver':
  e.run('live-in-caravan' if incoming else 'live-out-cargo',source,target,t['quantity'], -t['money'] if incoming else t['money'],t['resource'])
 else:raise ValueError('cargo phase')
 return (target/'city.sav').read_bytes(),None if incoming else (target/'cargo.bin').read_bytes()

def validate_result(phase,before,after,t):
 """Validate ownership and phase before publishing either city's worker output."""
 old=cargo_snapshot.cargo(before);new=cargo_snapshot.cargo(after)
 if (new['contract'],new['resource'],new['total'])!=(t['id'],t['resource'],t['quantity']):
  raise ValueError('cargo ownership mismatch')
 if phase=='load':
  valid=not old['contract'] and new['state']==1 and new['remaining']==t['quantity']
 else:
  valid=(old['contract'],old['resource'],old['total'])==(t['id'],t['resource'],t['quantity'])
  if phase=='depart':valid=valid and old==new and old['state']==1
  elif phase=='deliver':valid=valid and old['state']==1 and new['state']==4 and not new['remaining']
  elif phase=='refund':valid=valid and old['state'] in (1,2) and new['state'] in (2,3) and new['remaining']<=old['remaining']
  else:valid=False
 if not valid:raise ValueError('cargo phase mismatch')
def prepare(room,db,t):
 c=get(db,t['id']);phase=c['phase']
 base=db.execute('SELECT * FROM joint_save WHERE id=?',(t['base'],)).fetchone()
 if not base or base['state']=='cancelled':
  state='rejected' if phase=='load' else 'returning'
  db.execute("UPDATE live_transfer SET state=?,error='저장 취소/누락: 화물은 보관됨, 반환 재시도 가능' WHERE id=?",(state,t['id']));db.commit();return
 if base['state']!='complete':return
 job=getattr(room,'live_prepare_job',None)
 try:
  if job is None:
   root=Path(room.coordinator.path).parent/('cargo-'+str(t['id'])+'-'+str(t['base'])+'-'+uuid.uuid4().hex)
   tasks=[]
   for city in (t['sender'],t['receiver']):
    source=root/(city+'-base');source.mkdir(parents=True)
    data=db.execute('SELECT save FROM joint_part WHERE id=? AND city=?',(t['base'],city)).fetchone()[0]
    from live_trade import ZERO
    (source/'city.sav').write_bytes(data);(source/'receipt.bin').write_bytes(ZERO)
    (source/'cargo.bin').write_bytes(c['cargo'])
    if phase=='load' and city==t['sender'] and c['source_route']:
     target=db.execute('SELECT building FROM live_collection WHERE id=?',(t['id'],)).fetchone()
     if not target:raise ValueError('missing source collection')
     (source/'transport.txt').write_text(f"{t['id']} {target[0]}")
    if phase=='deliver' and city==t['receiver']:
     target=db.execute('SELECT building FROM live_transport WHERE id=?',(t['id'],)).fetchone()
     if not target:raise ValueError('missing arrival')
     (source/'transport.txt').write_text(f"{t['id']} {target[0]}")
    tasks.append((city,source))
   pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix='cargo')
   jobs={city:pool.submit(worker,phase,city==t['receiver'],source,root/(city+'-result'),dict(t,source_route=c['source_route'])) for city,source in tasks}
   job=room.live_prepare_job=dict(id=t['id'],phase=phase,pool=pool,jobs=jobs)
  if job['id']!=t['id'] or job.get('phase')!=phase:raise RuntimeError('conflicting cargo job')
  if not all(f.done() for f in job['jobs'].values()):return
  prepared={city:f.result() for city,f in job['jobs'].items()}
  cargo=prepared[t['sender']][1];validate_result(phase,c['cargo'],cargo,t)
 except (RuntimeError,OSError,ValueError,subprocess.SubprocessError):
  stop_job(room)
  if phase in ('deliver','depart'):
   db.execute("UPDATE live_cargo SET phase='refund' WHERE id=?",(t['id'],))
   db.execute("UPDATE live_transfer SET error='운송 확인 실패: 선적 화물 반환 처리 중' WHERE id=?",(t['id'],))
  else:
   state='rejected' if phase=='load' else 'returning'
   db.execute("UPDATE live_transfer SET state=?,error=? WHERE id=?",(state,'출발 전 재고, 대금, 공간 검사 실패' if phase=='load' else '반환 처리 실패: 화물 보관 중, 재시도 가능',t['id']))
  db.commit();return
 db.execute('BEGIN IMMEDIATE')
 sid=db.execute("INSERT INTO joint_save(request,ticks,state,speed) VALUES(?,?,'complete',?)",('cargo-'+uuid.uuid4().hex,base['ticks'],base['speed'])).lastrowid
 room_options.capture(db,sid)
 for city,(sav,_) in prepared.items():db.execute('INSERT INTO joint_part VALUES(?,?,?,?)',(sid,city,sav,sha(sav)))
 db.execute('UPDATE live_cargo SET cargo=? WHERE id=?',(cargo,t['id']))
 for unchanged in db.execute('SELECT city,save,hash FROM joint_part WHERE id=?',(t['base'],)).fetchall():
  if unchanged['city'] not in prepared:db.execute('INSERT INTO joint_part VALUES(?,?,?,?)',(sid,unchanged['city'],unchanged['save'],unchanged['hash']))
 db.execute('INSERT INTO joint_provenance SELECT ?,city,ticks,source_id,mode FROM joint_provenance WHERE id=?',(sid,t['base']))
 save_provenance.capture_boundary(db,sid)
 db.execute("UPDATE live_transfer SET state='committed',result=? WHERE id=?",(sid,t['id']))
 if phase=='deliver':
  import delivery_goals
  delivery_goals.delivered(db,t)
 transport_snapshot.capture(db,sid);db.commit();stop_job(room)

def request(room,db,city,r,t):
 op=r['op'];c=get(db,t['id'])
 if op!='live_status' and r.get('id')!=t['id']:raise ValueError('stale cargo transfer')
 if op=='live_accept':
  if city!=t['receiver']:raise ValueError('recipient consent required')
  if t['state']=='offered':
   if c['source_route']:
    db.execute("UPDATE live_transfer SET state='collecting' WHERE id=?",(t['id'],));db.execute("UPDATE live_cargo SET phase='collect' WHERE id=?",(t['id'],));db.commit()
   else:start_save(room,db,t,'load')
  elif t['state']=='rejected':raise ValueError('not offered')
 elif op=='live_reject':
  if t['state']=='rejected':pass
  elif t['state'] in ('committed','finished'):raise ValueError('already committed')
  elif t['state'] in ('offered','collecting') or (t['state']=='saving' and c['phase']=='load'):
   if t['state']=='collecting' and joint_save.pending(db):raise ValueError('save in progress')
   stop_job(room)
   db.execute("UPDATE joint_save SET state='cancelled' WHERE id=? AND state='collecting'",(t['base'],))
   db.execute("UPDATE live_transfer SET state='rejected',error='선적 전 거래 취소: 재고 변경 없음' WHERE id=?",(t['id'],));db.commit()
  elif t['state']=='saving':
   stop_job(room);db.execute("UPDATE live_cargo SET phase='refund' WHERE id=?",(t['id'],));db.commit()
  elif t['state'] in ('departing','travelling','returning'):start_save(room,db,t,'refund')
  else:raise ValueError('invalid cargo cancellation')
 elif op in ('live_departed','live_departure_failed'):
  if city!=t['sender']:raise ValueError('wrong departure reporter')
  if t['state']=='departing' and not joint_save.pending(db):
   if op=='live_departed' and 'departure' in r:
    # The running engine performs the same exit/figure checks as cargo-depart.
    # No goods or money change here: keep the loaded cargo and last complete
    # checkpoint intact. A lost reply can safely repeat this transition.
    proof=r['departure'];cargo=cargo_snapshot.cargo(c['cargo'])
    if (not isinstance(proof,list) or len(proof)!=3 or any(type(v)!=int for v in proof)
        or proof!=[t['resource'],t['quantity'],c['source_route']]
        or c['source_route'] not in (2,3) or c['phase']!='depart'
        or (cargo['contract'],cargo['resource'],cargo['total'],cargo['remaining'],cargo['state'])
           !=(t['id'],t['resource'],t['quantity'],t['quantity'],1)):
     raise ValueError('invalid live departure confirmation')
    db.execute("UPDATE live_cargo SET phase='travel' WHERE id=?",(t['id'],))
    db.execute("UPDATE live_transfer SET state='travelling' WHERE id=?",(t['id'],));db.commit()
   else:
    # Older engines cannot attest their exit checks; keep their safe SAV path.
    start_save(room,db,t,'depart' if op=='live_departed' else 'refund')
 elif op in ('live_collected','live_collection_failed'):
  if city!=t['sender']:raise ValueError('wrong collection reporter')
  if t['state']=='collecting' and not joint_save.pending(db):
   if op=='live_collection_failed':
    reason='선적을 시작할 수 없습니다. 수로, 빈 선창, 인력, 물품 허용 및 저장소 연결을 확인하세요.' if c['source_route']==3 else '물품을 모을 수 없습니다. 길, 재고, 상인 출입 설정을 확인하세요.'
    db.execute("UPDATE live_transfer SET state='rejected',error=? WHERE id=?",(reason,t['id']));db.commit()
   else:
    building=r.get('building')
    if type(building)!=int or not 0<building<100000:raise ValueError('invalid collection target')
    start_save(room,db,t,'load');db.execute('INSERT OR REPLACE INTO live_collection VALUES(?,?)',(t['id'],building));db.commit()
 elif op in ('live_arrived','live_transport_failed'):
  if city!=t['receiver']:raise ValueError('wrong transport')
  if t['state']=='travelling' and not joint_save.pending(db):
   if op=='live_arrived':
    building=r.get('building')
    if type(building)!=int or not 0<building<100000:raise ValueError('invalid destination')
    start_save(room,db,t,'deliver')
    db.execute('INSERT OR REPLACE INTO live_transport VALUES(?,?)',(t['id'],building));db.commit()
   else:start_save(room,db,t,'refund')
 elif op=='live_ack':
  if t['state'] not in ('committed','finished','departing','travelling','returning','rejected') or not t['result']:raise ValueError('no commit')
  if r.get('result')!=t['result']:raise ValueError('stale cargo install')
  part=db.execute('SELECT hash FROM joint_part WHERE id=? AND city=?',(t['result'],city)).fetchone()
  if not part or part[0]!=r.get('hash'):raise ValueError('wrong installed snapshot')
  db.execute('INSERT OR IGNORE INTO live_cargo_ack VALUES(?,?)',(t['result'],city))
  if t['state']=='committed' and db.execute('SELECT count(*) FROM live_cargo_ack WHERE result=?',(t['result'],)).fetchone()[0]==2:
   state=('departing' if c['source_route']>=2 else 'travelling') if c['phase']=='load' else 'travelling' if c['phase']=='depart' else 'finished' if c['phase']=='deliver' else ('returning' if cargo_snapshot.cargo(c['cargo'])['remaining'] else 'rejected')
   db.execute('UPDATE live_transfer SET state=? WHERE id=?',(state,t['id']))
   if state=='travelling':db.execute("UPDATE live_cargo SET phase='travel' WHERE id=?",(t['id'],))
   if state=='departing':db.execute("UPDATE live_cargo SET phase='depart' WHERE id=?",(t['id'],))
   if state=='rejected':db.execute("UPDATE live_transfer SET error='화물 반환 완료: 거래 종료' WHERE id=?",(t['id'],))
  db.commit()
 elif op=='live_status':
  if t['state']=='saving':prepare(room,db,t)
 else:raise ValueError('unknown cargo operation')
 t=db.execute('SELECT * FROM live_transfer WHERE id=?',(t['id'],)).fetchone();c=get(db,t['id']);result=dict(t)
 result.update(phase=c['phase'],cargo_remaining=cargo_snapshot.cargo(c['cargo'])['remaining'],source_route=c['source_route'])
 if t['state']=='committed' and not db.execute('SELECT 1 FROM live_cargo_ack WHERE result=? AND city=?',(t['result'],city)).fetchone():
  part=db.execute('SELECT save,hash FROM joint_part WHERE id=? AND city=?',(t['result'],city)).fetchone()
  ticks=db.execute('SELECT ticks FROM joint_save WHERE id=?',(t['result'],)).fetchone()[0]
  result['install']=dict(save=base64.b64encode(part['save']).decode(),hash=part['hash'],ticks=ticks,serial=t['result'])
 return result
