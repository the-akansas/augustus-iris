import room_options
"""Live transfers: frozen paired snapshot -> disposable workers -> atomic pair -> both install ACKs."""
import base64,uuid,struct,subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import save_provenance
import joint_save
import transport_snapshot
import live_cargo
from coordinator import sha
import json
TRADE_CATALOG=json.loads(Path(__file__).with_name('trade-catalog.json').read_text(encoding='utf-8'))
RESOURCES={item['name']:item['resource'] for item in TRADE_CATALOG if item['resource']}
ZERO=struct.pack('<4sQiiiii',b'MPC1',0,0,0,0,0,0)
def initialize(db):
 import player_fleet
 import trade_agreements
 trade_agreements.initialize(db)
 import city_trade_routes
 city_trade_routes.initialize(db)
 player_fleet.initialize(db)
 live_cargo.initialize(db)
 import cash_live
 cash_live.initialize(db)
 db.executescript('''CREATE TABLE IF NOT EXISTS live_transfer(id INTEGER PRIMARY KEY AUTOINCREMENT,request TEXT UNIQUE,sender TEXT,receiver TEXT,resource INTEGER,quantity INTEGER,money INTEGER,kind TEXT,state TEXT,base INTEGER,result INTEGER,error TEXT);
 CREATE TABLE IF NOT EXISTS live_transport(id INTEGER PRIMARY KEY,building INTEGER);
 CREATE TABLE IF NOT EXISTS live_preflight(id INTEGER PRIMARY KEY);
 CREATE TABLE IF NOT EXISTS live_installed(id INTEGER,city TEXT,PRIMARY KEY(id,city));''')
def selected(db,city,request=None):
 request=request or {}
 if request.get('id') is not None:
  row=db.execute('SELECT * FROM live_transfer WHERE id=?',(request['id'],)).fetchone()
  if not row or city not in (row['sender'],row['receiver']):raise ValueError('unknown or unauthorized transfer')
  return row
 return db.execute("SELECT * FROM live_transfer WHERE sender=? OR receiver=? ORDER BY CASE WHEN state IN ('finished','rejected') THEN 1 ELSE 0 END,CASE WHEN state IN ('finished','rejected') THEN -id ELSE id END ASC LIMIT 1",(city,city)).fetchone()

def latest(db):return db.execute('SELECT * FROM live_transfer ORDER BY id DESC LIMIT 1').fetchone()
def busy(db):
 return db.execute("SELECT * FROM live_transfer WHERE state IN ('saving','committed') ORDER BY id LIMIT 1").fetchone()

def prepare(room,db,t):
 preflight=bool(db.execute('SELECT 1 FROM live_preflight WHERE id=?',(t['id'],)).fetchone())
 base=db.execute('SELECT * FROM joint_save WHERE id=?',(t['base'],)).fetchone()
 if not base or base['state']=='cancelled':
  db.execute("UPDATE live_transfer SET state='rejected',error='거래 전 저장 취소 또는 누락' WHERE id=?",(t['id'],));db.commit();return
 if base['state']!='complete':return
 from city_client import Engine
 root=Path(room.coordinator.path).parent/('transfer-'+str(t['id']))
 # Only the room request thread touches SQLite. Engine workers receive immutable bytes.
 job=getattr(room,'live_prepare_job',None)
 try:
  if job is None:
   tasks=[]
   for city in (t['sender'],t['receiver']):
    data=db.execute('SELECT save FROM joint_part WHERE id=? AND city=?',(t['base'],city)).fetchone()[0]
    source=root/(city+'-base');source.mkdir(parents=True,exist_ok=True)
    (source/'city.sav').write_bytes(data);(source/'receipt.bin').write_bytes(ZERO)
    incoming=city==t['receiver']
    delta=t['money']*(1 if (incoming and t['kind']=='gift') or (not incoming and t['kind']=='sale') else -1)
    mode='live-in' if incoming else 'live-out'
    transport=db.execute('SELECT building FROM live_transport WHERE id=?',(t['id'],)).fetchone()
    if incoming and transport:
     (source/'transport.txt').write_text(str(t['id'])+' '+str(transport['building']))
     mode='live-in-caravan'
    tasks.append((city,mode,source,root/(city+'-result'),delta))
   pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix='augustus-trade')
   jobs={city:pool.submit(Engine().run,mode,source,target,t['quantity'],delta,t['resource']) for city,mode,source,target,delta in tasks}
   job=room.live_prepare_job=dict(id=t['id'],pool=pool,jobs=jobs)
  if job['id']!=t['id']:raise RuntimeError('conflicting preparation')
  if not all(f.done() for f in job['jobs'].values()):return
  prepared={city:f.result()[0] for city,f in job['jobs'].items()}
 except (RuntimeError,OSError,subprocess.SubprocessError):
  if job:job['pool'].shutdown(wait=False)
  room.live_prepare_job=None
  reason=('출발 전 검사 실패: ' if preflight else '')+'재고, 자금, 수용 공간 부족 또는 저장 처리 실패'
  db.execute("UPDATE live_transfer SET state='rejected',error=? WHERE id=?",(reason,t['id']));db.commit();return
 if preflight:
  # These are disposable dry-run results. Neither city installs them or pays yet.
  db.execute('BEGIN IMMEDIATE')
  db.execute("UPDATE live_transfer SET state='travelling',base=NULL WHERE id=?",(t['id'],))
  db.execute('DELETE FROM live_preflight WHERE id=?',(t['id'],));db.commit()
  job['pool'].shutdown(wait=False);room.live_prepare_job=None
  return
 # No engine has installed either result yet. Commit both snapshots and decision together.
 db.execute('BEGIN IMMEDIATE')
 sid=db.execute("INSERT INTO joint_save(request,ticks,state,speed) VALUES(?,?,'complete',?)",('trade-'+str(t['id']),base['ticks'],base['speed'])).lastrowid
 room_options.capture(db,sid)
 for city,sav in prepared.items():db.execute('INSERT INTO joint_part VALUES(?,?,?,?)',(sid,city,sav,sha(sav)))
 for unchanged in db.execute('SELECT city,save,hash FROM joint_part WHERE id=?',(t['base'],)).fetchall():
  if unchanged['city'] not in prepared:db.execute('INSERT INTO joint_part VALUES(?,?,?,?)',(sid,unchanged['city'],unchanged['save'],unchanged['hash']))
 db.execute('INSERT INTO joint_provenance SELECT ?,city,ticks,source_id,mode FROM joint_provenance WHERE id=?',(sid,t['base']))
 save_provenance.capture_boundary(db,sid)
 db.execute("UPDATE live_transfer SET state='committed',result=? WHERE id=?",(sid,t['id']));transport_snapshot.capture(db,sid);db.commit()
 job['pool'].shutdown(wait=False);room.live_prepare_job=None

LEFT_TEXT='상대가 방을 나가 거래를 취소했습니다.'

def settle_departed(room,db,gone):
 """Trades already under way with a city whose player left: goods heading there go
 back to the sender, goods coming from there still arrive, and nothing waits on it."""
 if not gone or joint_save.pending(db) or not db.execute("SELECT 1 FROM sqlite_master WHERE name='post_meta'").fetchone():return
 marks=','.join('?'*len(gone));pair=(*gone,*gone)
 # A caravan of the city that left can no longer report coming home.
 db.execute("UPDATE fleet_order SET home=1 WHERE assigned=1 AND home=0 AND city IN ("+marks+") AND id IN (SELECT id FROM live_transfer WHERE state='rejected')",tuple(gone))
 db.commit() # the ledger writes through its own connection
 open_trade="SELECT 1 FROM post_contract WHERE phase NOT IN ('complete','cancelled') AND (sender IN ("+marks+") OR receiver IN ("+marks+"))"
 if not db.execute(open_trade,pair).fetchone():return
 from trade_post_ledger import Ledger
 import cash_live
 ledger=Ledger(room.coordinator.path,room.coordinator.scenario['cities'],transport=True)
 try:
  # Goods still inside a city that left never set out: release the buyer's side.
  for t in db.execute('''SELECT t.request,t.receiver FROM live_transfer t JOIN goods_motion m ON m.id=t.id
   WHERE t.sender IN ('''+marks+''') AND m.departed=0 AND t.state NOT IN ('finished','rejected','offered')''',tuple(gone)).fetchall():
   c=ledger.db.execute('SELECT cancel,received FROM post_contract WHERE id=?',(t['request'],)).fetchone()
   if c and not c['cancel'] and not c['received']:
    try:ledger.cancel(t['receiver'],t['request'])
    except ValueError:pass
  ledger.abandon(gone)
  cash_live.sync(db,ledger)
  # Name the reason on everything this turned back, for both players' notices.
  db.execute("UPDATE live_transfer SET error=? WHERE error IS NULL AND state!='finished' AND (sender IN ("+marks+") OR receiver IN ("+marks+")) AND request IN (SELECT id FROM post_contract WHERE cancel=1)",(LEFT_TEXT,*pair))
  db.commit()
 finally:ledger.close()

def request(room,db,city,r):
 op=r['op']
 import player_fleet
 if op=='live_sync':
  import trade_agreements
  if 'route_posts' in r:
   import city_trade_routes
   city_trade_routes.register(db,room.coordinator.scenario['cities'],city,r['route_posts'])
  if 'posts' in r:player_fleet.register(db,city,r['posts'])
  if 'post_load' in r:player_fleet.report_load(room,city,r['post_load'])
  request(room,db,city,dict(op='live_batch',reports=r.get('reports',[])))
  args=dict(op='agreement_poll')
  if 'stock' in r:args['stock']=r['stock']
  if 'storage_stock' in r:args['storage_stock']=r['storage_stock']
  agreements=trade_agreements.request(room,db,city,args)
  rows=request(room,db,city,dict(op='live_batch'))
  history=request(room,db,city,dict(op='live_history'))
  return dict(rows=rows,agreements=agreements,history=history,routes=__import__('city_trade_routes').snapshot(db),route_roster=sorted(room.coordinator.scenario['cities']),post_status=player_fleet.post_status(db,city),
   trade_blocked=sorted(p for p in room.coordinator.scenario.get('player_trade_blocked',[]) if city in p))
 if op=='live_batch':
  reports=r.get('reports',[])
  if not isinstance(reports,list) or len(reports)>64:raise ValueError('invalid transport report batch')
  allowed={'live_collected','live_collection_failed','live_departed','live_departure_failed','live_arrived','live_transport_failed','live_home','live_home_failed','live_receiver_exit','live_receiver_exit_failed'}
  for report in reports:
   if not isinstance(report,dict) or report.get('op') not in allowed:continue
   try:request(room,db,city,report)
   except ValueError:continue # Reject this courier proof, continue the other couriers.
  # Unassigned couriers have never departed. Use the ordinary cancel/refund
  # path if their post no longer stands (a post that only lost its road keeps
  # its orders waiting); never manufacture settlement for assigned cargo.
  abandoned=db.execute('''SELECT f.id FROM fleet_order f JOIN live_transfer t ON t.id=f.id
   LEFT JOIN fleet_site s ON s.city=f.city AND s.building=f.building AND s.generation=f.generation
   WHERE f.city=? AND f.assigned=0 AND f.home=0 AND s.city IS NULL
   AND t.state NOT IN ('finished','rejected')''',(city,)).fetchall()
  for old in abandoned:
   request(room,db,city,dict(op='live_reject',id=old['id']))
  # A city whose player left stays empty for the rest of this session. What never
  # left my post (offers, queued orders) ends here instead of waiting forever.
  gone=set(room.coordinator.scenario['cities'])-set(room.active_cities(db)) if getattr(room,'started',False) else set()
  if gone:
   # ...and a caravan still loading at my post: nothing has been taken out or paid yet.
   loading="OR t.request IN (SELECT id FROM post_contract WHERE phase='offered')" if db.execute("SELECT 1 FROM sqlite_master WHERE name='post_contract'").fetchone() else ''
   for old in db.execute('''SELECT t.id,t.sender,t.receiver FROM live_transfer t LEFT JOIN fleet_order f ON f.id=t.id
    WHERE (t.sender=? OR t.receiver=?) AND t.state NOT IN ('finished','rejected') AND (COALESCE(f.assigned,0)=0 '''+loading+')',(city,city)).fetchall():
    if (old['receiver'] if old['sender']==city else old['sender']) not in gone:continue
    try:request(room,db,city,dict(op='live_reject',id=old['id']))
    except ValueError:continue
    db.execute("UPDATE live_transfer SET error=? WHERE id=? AND state='rejected'",(LEFT_TEXT,old['id']));db.commit()
   settle_departed(room,db,gone)
  player_fleet.advance(db,room)
  rows=db.execute("SELECT t.id FROM live_transfer t LEFT JOIN fleet_order f ON f.id=t.id WHERE (t.sender=? OR t.receiver=?) AND (t.state NOT IN ('finished','rejected') OR f.home=0) ORDER BY CASE WHEN f.assigned=1 AND f.home=0 THEN 0 WHEN t.receiver=? AND t.state='offered' THEN 1 ELSE 2 END,t.id LIMIT 64",(city,city,city)).fetchall()
  result=[player_fleet.decorate(db,request(room,db,city,dict(op='live_status',id=row[0]))) for row in rows]
  # A round of an agreed contract waits only for the host's own acceptance, not for the receiver: not an unanswered offer.
  if result:result[0]['inbox']=list(db.execute("SELECT count(*),COALESCE(min(id),0),COALESCE(max(id),0) FROM live_transfer WHERE receiver=? AND state='offered' AND id NOT IN (SELECT transfer FROM trade_agreement WHERE transfer IS NOT NULL)",(city,)).fetchone())
  return result
 if op in ('live_receiver_exit','live_receiver_exit_failed'):
  player_fleet.receiver_exited(db,city,r.get('id'),r.get('post'),r.get('exit'),recovered=op=='live_receiver_exit_failed');return dict(home=True)
 if op in ('live_home','live_home_failed'):
  player_fleet.returned(db,city,r.get('id'),r.get('post'),recovered=op=='live_home_failed');return dict(home=True)
 t=selected(db,city,r)
 import cash_live
 if op not in ('live_offer','live_history') and cash_live.mapped(db,t):
  if op=='live_status' and city not in (t['sender'],t['receiver']):return None
  return cash_live.trade(room,db,city,r,t)
 if t and op not in ('live_offer','live_history') and city not in (t['sender'],t['receiver']):
  if op=='live_status':return None
  raise ValueError('not a transfer participant')
 if t and op not in ('live_offer','live_history') and live_cargo.get(db,t['id']):return live_cargo.request(room,db,city,r,t)
 if op=='live_history':
  return [dict(row) for row in db.execute("SELECT id,sender,receiver,resource,quantity,money,kind,state,error FROM live_transfer WHERE sender=? OR receiver=? ORDER BY id DESC LIMIT 50",(city,city))]
 if op=='live_offer':
  key=r.get('request_id');kind=r.get('kind');res=r.get('resource');qty=r.get('quantity');money=r.get('money')
  if not isinstance(key,str) or len(key)!=32 or any(c not in '0123456789abcdef' for c in key):raise ValueError('request id')
  cities=room.coordinator.scenario['cities']
  peer=r.get('receiver')
  if peer is None and len(cities)==2:peer=next(c for c in cities if c!=city)
  if peer not in cities or peer==city:raise ValueError('invalid recipient')
  import trade_policy
  trade_policy.require(room.coordinator.scenario,city,peer)   # the scenario's player-to-player trade rule; no UI can lift it
  old=db.execute('SELECT * FROM live_transfer WHERE request=?',(key,)).fetchone()
  if old:
   f=db.execute('SELECT building,generation FROM fleet_order WHERE id=?',(old['id'],)).fetchone()
   if f and r.get('post')!=list(f):raise ValueError('conflicting caravan assignment')
   if (old['sender'],old['receiver'],old['kind'],old['resource'],old['quantity'],old['money'])!=(city,peer,kind,res,qty,money):raise ValueError('conflicting duplicate')
   return dict(old)
  if qty:
   import city_trade_routes
   city_trade_routes.require_posts(db,cities,city,peer,r.get('post'))
  if kind not in ('sale','gift') or type(qty)!=int or type(money)!=int or type(res)!=int:raise ValueError('fields')
  if not (0<=qty<=32 and 0<=money<=1000000) or (qty==0 and (res!=0 or money<=0 or kind!='gift')) or (qty>0 and res not in RESOURCES.values()) or (kind=='sale' and money<=0) or (kind=='gift' and qty>0 and money!=0):raise ValueError('amount')
  if db.execute("SELECT count(*) FROM live_transfer WHERE sender=? AND state NOT IN ('finished','rejected')",(city,)).fetchone()[0]>=64:raise ValueError('city order queue full')
  if joint_save.pending(db):raise ValueError('save busy')
  cities=room.active_cities(db)
  # Same freshness as the shared clock: at a 400ms ping a progress report can be ~1s old.
  from clock_policy import FRESH_SECONDS
  if any(c not in room.progress or room.clock()-room.progress[c][1]>=FRESH_SECONDS for c in cities):raise ValueError('both engines required')
  if not cash_live.ready(room,(city,peer)):raise ValueError('both engines required')
  if not db.execute('SELECT 1 FROM lobby_invite WHERE city=?',(peer,)).fetchone():raise ValueError('invalid recipient')
  tid=db.execute("INSERT INTO live_transfer(request,sender,receiver,resource,quantity,money,kind,state) VALUES(?,?,?,?,?,?,?,'offered')",(key,city,peer,res,qty,money,kind)).lastrowid
  db.execute('INSERT INTO cash_transfer VALUES(?,?)',(tid,key))
  if qty:
   player_fleet.reserve(db,city,tid,r.get('post'))
   db.execute('INSERT INTO goods_motion(id,route) VALUES(?,2)',(tid,))
  db.commit()
  cash_live.materialize(room,db)
  return dict(db.execute('SELECT * FROM live_transfer WHERE id=?',(tid,)).fetchone())
 if op in ('live_accept','live_reject'):
  if not t or r.get('id')!=t['id']:raise ValueError('stale offer')
  if op=='live_reject':
   if t['state']=='rejected':return dict(t)
   if t['state']=='travelling' and joint_save.pending(db):raise ValueError('save in progress')
   if t['state'] not in ('offered','travelling','saving'):raise ValueError('already committed')
   # Serialized by the lobby lock: either cancellation or paired commit wins.
   # Workers only write disposable directories; they never publish to SQLite.
   db.execute('BEGIN IMMEDIATE')
   if t['state']=='saving':
    db.execute("UPDATE joint_save SET state='cancelled' WHERE id=? AND state='collecting'",(t['base'],))
   subject='선물' if t['kind']=='gift' else '판매 제안'
   reason=('보낸 사람이 '+subject+'을 취소했습니다.') if city==t['sender'] else ('받는 사람이 '+subject+'을 거절했습니다.')
   db.execute("UPDATE live_transfer SET state='rejected',error=? WHERE id=?",(reason,t['id']));db.commit()
   job=getattr(room,'live_prepare_job',None)
   if job and job['id']==t['id']:
    for future in job['jobs'].values():future.cancel()
    job['pool'].shutdown(wait=False);room.live_prepare_job=None
  else:
   if city!=t['receiver']:raise ValueError('recipient consent required')
   if t['state'] in ('travelling','saving','committed','finished'):return dict(t)
   if t['state']!='offered':raise ValueError('not offered')
   if joint_save.pending(db):raise ValueError('save in progress')
   host=db.execute('SELECT city FROM lobby_invite ORDER BY rowid LIMIT 1').fetchone()[0]
   saved=joint_save.request(room,db,host,dict(op='save_begin',request_id=uuid.uuid4().hex))
   if t['quantity']:db.execute('INSERT INTO live_preflight VALUES(?)',(t['id'],))
   db.execute("UPDATE live_transfer SET state='saving',base=? WHERE id=?",(saved['id'],t['id']));db.commit()
  return dict(db.execute('SELECT * FROM live_transfer WHERE id=?',(t['id'],)).fetchone())
 if op in ('live_arrived','live_transport_failed'):
  if not t or r.get('id')!=t['id'] or city!=t['receiver']:raise ValueError('wrong transport')
  if t['state']!='travelling':return dict(t)
  if joint_save.pending(db):return dict(t) # Retry arrival/failure after the paired snapshot is complete.
  if op=='live_transport_failed':
   db.execute("UPDATE live_transfer SET state='rejected',error='육상 상단 이동 실패: 길, 수용 공간, 상인 생존 확인' WHERE id=?",(t['id'],));db.commit();return dict(db.execute('SELECT * FROM live_transfer WHERE id=?',(t['id'],)).fetchone())
  building=r.get('building')
  if type(building)!=int or not 0<building<100000:raise ValueError('invalid destination')
  host=db.execute('SELECT city FROM lobby_invite ORDER BY rowid LIMIT 1').fetchone()[0]
  saved=joint_save.request(room,db,host,dict(op='save_begin',request_id=uuid.uuid4().hex))
  db.execute('INSERT INTO live_transport VALUES(?,?)',(t['id'],building))
  db.execute("UPDATE live_transfer SET state='saving',base=? WHERE id=?",(saved['id'],t['id']));db.commit()
  return dict(db.execute('SELECT * FROM live_transfer WHERE id=?',(t['id'],)).fetchone())
 if op=='live_ack':
  if not t or r.get('id')!=t['id'] or t['state'] not in ('committed','finished'):raise ValueError('no commit')
  part=db.execute('SELECT hash FROM joint_part WHERE id=? AND city=?',(t['result'],city)).fetchone()
  if r.get('hash')!=part[0]:raise ValueError('wrong installed snapshot')
  db.execute('INSERT OR IGNORE INTO live_installed VALUES(?,?)',(t['id'],city))
  if db.execute('SELECT count(*) FROM live_installed WHERE id=?',(t['id'],)).fetchone()[0]==2:db.execute("UPDATE live_transfer SET state='finished' WHERE id=?",(t['id'],))
  db.commit();return dict(db.execute('SELECT * FROM live_transfer WHERE id=?',(t['id'],)).fetchone())
 if op!='live_status':raise ValueError('unknown transfer op')
 if t and t['state']=='saving':prepare(room,db,t);t=latest(db)
 result=dict(t) if t else None
 if t and t['state']=='saving' and db.execute('SELECT 1 FROM live_preflight WHERE id=?',(t['id'],)).fetchone():
  result['phase']='preflight'
 if t and t['state']=='committed' and not db.execute('SELECT 1 FROM live_installed WHERE id=? AND city=?',(t['id'],city)).fetchone():
  part=db.execute('SELECT save,hash FROM joint_part WHERE id=? AND city=?',(t['result'],city)).fetchone()
  ticks=db.execute('SELECT ticks FROM joint_save WHERE id=?',(t['result'],)).fetchone()[0]
  result['install']=dict(save=base64.b64encode(part['save']).decode(),hash=part['hash'],ticks=ticks,serial=t['result'])
 return result
