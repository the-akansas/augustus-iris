"""Bilateral standing orders above the existing native receipt settlement engine.

One linked delivery at a time. Creating its transfer, fleet reservation and link
is one SQLite transaction. Stopping a contract never discards in-flight cargo.
Stock reports are discovery hints, never authority to debit goods or money.
"""
import json,uuid
import cash_live,joint_save,player_fleet
import agreement_negotiation as negotiation

LEGACY_FIELDS=('id','request','proposer','seller','buyer','resource','quantity','money','repeat','state','post','generation','cycle','transfer')
FIELDS=LEGACY_FIELDS+tuple(negotiation.DEFAULTS)
STATES=('offered','active','paused','stopped','complete')
DUE_TICKS=3*800 # a waiting round must leave within three game months, or the contract expires
def initialize(db):
 db.execute('''CREATE TABLE IF NOT EXISTS trade_agreement(
 id INTEGER PRIMARY KEY AUTOINCREMENT,request TEXT UNIQUE,proposer TEXT,seller TEXT,buyer TEXT,
 resource INTEGER,quantity INTEGER,money INTEGER,repeat INTEGER,state TEXT,post INTEGER,generation INTEGER,
 cycle INTEGER NOT NULL DEFAULT 0,transfer INTEGER)''')
 negotiation.initialize(db)

def stock(room,city):
 row=getattr(room,'trade_stock',{}).get(city)
 return row[1] if row and 0<=room.clock()-row[0]<10 else {}

def purchase_catalog(db,room,buyer,seller):
 row=getattr(room,'trade_storage_stock',{}).get(seller)
 available={res for res,qty in row[1].items() if qty>0} if row and 0<=room.clock()-row[0]<10 else set()
 history={x[0] for x in db.execute("SELECT DISTINCT resource FROM live_transfer WHERE ((sender=? AND receiver=?) OR (sender=? AND receiver=?)) AND state='finished' AND resource>0",(buyer,seller,seller,buyer))}
 return sorted(available|history)

def report_stock(room,city,values,storage=False):
 from live_trade import RESOURCES
 if not isinstance(values,list) or len(values)>len(RESOURCES):raise ValueError('재고 목록 형식 오류')
 result={}
 for row in values:
  if not isinstance(row,list) or len(row)!=2 or any(type(x)!=int for x in row):raise ValueError('재고 항목 오류')
  resource,amount=row
  if resource not in RESOURCES.values() or resource in result or not 0<=amount<=10000000:raise ValueError('재고 범위 오류')
  result[resource]=amount
 name='trade_storage_stock' if storage else 'trade_stock'
 if not hasattr(room,name):setattr(room,name,{})
 getattr(room,name)[city]=(room.clock(),result)

def item(db,city,ident):
 if type(ident)!=int:raise ValueError('계약 번호 오류')
 row=db.execute('SELECT * FROM trade_agreement WHERE id=?',(ident,)).fetchone()
 if not row or city not in (row['seller'],row['buyer']):raise ValueError('계약 당사자만 변경할 수 있습니다.')
 return dict(row)

def post(db,seller,value,ready=True):
 if not isinstance(value,list) or len(value)!=2 or any(type(v)!=int for v in value):raise ValueError('판매자 교역소를 선택하세요.')
 if not db.execute('SELECT 1 FROM city_trade_post WHERE city=? AND building=? AND generation=? AND active=1',(seller,*value)).fetchone():raise ValueError('판매자 교역소가 없거나 변경되었습니다. 교역소를 다시 확인하세요.')
 if ready and not db.execute('SELECT 1 FROM fleet_site WHERE city=? AND building=? AND generation=? AND active=1',(seller,*value)).fetchone():raise ValueError('판매자 교역소의 출입구 연결을 확인하세요.')
 return value

def snapshot(db):return [dict(r) for r in db.execute('SELECT * FROM trade_agreement ORDER BY id')]

def request(room,db,city,r):
 op=r['op']
 if not room.started:raise ValueError('게임 시작 후 거래할 수 있습니다.')
 if op=='agreement_poll':
  if 'stock' in r:report_stock(room,city,r['stock'])
  if 'storage_stock' in r:report_stock(room,city,r['storage_stock'],storage=True)
  advance(room,db)
  active=set(room.active_cities(db))
  catalogs={}
  for p in (city,):
   catalog={x[0]:0 for x in db.execute("SELECT DISTINCT resource FROM live_transfer WHERE (sender=? OR receiver=?) AND state='finished' AND resource>0",(p,p))}
   if p in active:catalog.update({k:v for k,v in stock(room,p).items() if v>0})
   catalogs[p]=catalog
  rows=[dict(x) for x in db.execute("SELECT * FROM trade_agreement WHERE seller=? OR buyer=? ORDER BY CASE WHEN state IN ('offered','active','paused') THEN 0 ELSE 1 END,id DESC LIMIT 128",(city,city))]
  for a in rows: # game ticks left before a waiting round expires (seller's clock), shown to both sides
   tick=(getattr(room,'progress',{}).get(a['seller']) or (None,))[0]
   a['due_left']=max(0,a['due_tick']-tick) if a['state']=='active' and a['due_tick'] and type(tick)==int else None
  return dict(agreements=rows,stocks=catalogs,purchase_catalogs={p:purchase_catalog(db,room,city,p) for p in room.coordinator.scenario['cities'] if p!=city})
 if op=='agreement_offer':
  key=r.get('request_id');peer=r.get('peer');mode=r.get('mode');res=r.get('resource');qty=r.get('quantity');money=r.get('money');repeat=r.get('repeat')
  from live_trade import RESOURCES
  if not isinstance(key,str) or len(key)!=32 or any(c not in '0123456789abcdef' for c in key):raise ValueError('거래 요청 번호 오류')
  if peer==city or peer not in room.coordinator.scenario['cities'] or mode not in ('buy','sell'):raise ValueError('거래 상대 오류')
  import trade_policy
  trade_policy.require(room.coordinator.scenario,city,peer)
  if any(type(x)!=int for x in (res,qty,money,repeat)) or res not in RESOURCES.values() or not 1<=qty<=32 or not 1<=money<=1000000 or repeat not in (0,1):raise ValueError('거래 수량/금액 오류')
  seller,buyer=(city,peer) if mode=='sell' else (peer,city)
  partial=r.get('allow_partial',0)
  if type(partial)!=int or partial not in (0,1) or (partial and mode!='buy'):raise ValueError('일부 수량 허용 설정 오류')
  selected=r.get('post') if seller==city else [0,0]
  original=negotiation.payload(city,seller,buyer,res,qty,money,repeat,selected,partial)
  old=db.execute('SELECT * FROM trade_agreement WHERE request=?',(key,)).fetchone()
  if old:
   if old['offer_payload']:
    # After a counter the record carries the newer terms; a late replay just reads it back.
    if old['offer_payload']!=original and not old['revision']:raise ValueError('중복 요청 내용이 다릅니다.')
    return dict(old)
   if tuple(old[k] for k in ('proposer','seller','buyer','resource','quantity','money','repeat'))!=(city,seller,buyer,res,qty,money,repeat) or (seller==city and selected!=[old['post'],old['generation']]):raise ValueError('중복 요청 내용이 다릅니다.')
   return dict(old)
  import city_trade_routes
  city_trade_routes.require_posts(db,room.coordinator.scenario['cities'],seller,buyer,selected if seller==city else None)
  if peer not in room.active_cities(db):raise ValueError('상대 도시 연결을 기다려 주세요.')
  if mode=='buy' and res not in purchase_catalog(db,room,buyer,seller):raise ValueError('상대가 보유 중이거나 두 도시가 거래한 물품을 선택하세요.')
  if mode=='sell' and stock(room,seller).get(res,0)<=0:raise ValueError('판매자의 보유 물품을 선택하세요.')
  if seller==city:selected=post(db,seller,selected)
  if db.execute("SELECT count(*) FROM trade_agreement WHERE (seller=? OR buyer=?) AND state IN ('offered','active','paused')",(city,city)).fetchone()[0]>=32:raise ValueError('진행 중인 계약은 도시당 32개까지 가능합니다.')
  with db:
   ident=db.execute("INSERT INTO trade_agreement(request,proposer,seller,buyer,resource,quantity,money,repeat,state,post,generation,allow_partial,offer_payload) VALUES(?,?,?,?,?,?,?,?,'offered',?,?,?,?)",(key,city,seller,buyer,res,qty,money,repeat,*selected,partial,original)).lastrowid
  return item(db,city,ident)
 a=item(db,city,r.get('id'))
 key,body,replayed=negotiation.check(a,city,r)
 if replayed:return a
 if op=='agreement_counter':
  import trade_policy
  trade_policy.require(room.coordinator.scenario,a['seller'],a['buyer'])
  with db:
   negotiation.counter(db,room,city,a,r)
   db.execute('UPDATE trade_agreement SET revision=revision+1,action_key=?,action_payload=? WHERE id=?',(key,body,a['id']))
  return item(db,city,a['id'])
 if op=='agreement_accept':
  if city==a['proposer']:raise ValueError('상대방의 동의가 필요합니다.')
  if a['state']=='active':return a
  if a['state']!='offered':raise ValueError('이미 처리된 제안입니다.')
  import trade_policy
  trade_policy.require(room.coordinator.scenario,a['seller'],a['buyer'])
  import city_trade_routes
  city_trade_routes.require_posts(db,room.coordinator.scenario['cities'],a['seller'],a['buyer'])
  selected=post(db,a['seller'],r.get('post') if city==a['seller'] else [a['post'],a['generation']],ready=False)
  city_trade_routes.require_posts(db,room.coordinator.scenario['cities'],a['seller'],a['buyer'],selected)
  if (json.loads(a['offer_payload'])[0] if a['offer_payload'] else a['proposer'])==a['seller'] and stock(room,a['seller']).get(a['resource'],0)<=0:raise ValueError('판매자의 현재 재고를 확인해 주세요.')
  with db:db.execute("UPDATE trade_agreement SET state='active',post=?,generation=?,due_tick=0,revision=revision+1,action_key=?,action_payload=? WHERE id=?",(*selected,key,body,a['id']))
 elif op=='agreement_stop':
  if a['state'] not in ('complete','stopped'):
   with db:db.execute("UPDATE trade_agreement SET state='stopped',revision=revision+1,action_key=?,action_payload=? WHERE id=?",(key,body,a['id']))
   if a['transfer']:
    t=db.execute('SELECT * FROM live_transfer WHERE id=?',(a['transfer'],)).fetchone()
    m=db.execute('SELECT accepted FROM goods_motion WHERE id=?',(a['transfer'],)).fetchone()
    if t and t['state']=='offered' and m and not m[0]:cash_live.trade(room,db,city,dict(op='live_reject',id=t['id']),t)
 elif op=='agreement_resume':
  # Both parties must consent again; one party cannot reinstate standing consent.
  if a['state']=='offered' and a['proposer']==city:return a
  if a['state']!='paused':raise ValueError('일시정지 계약만 재제안할 수 있습니다.')
  import trade_policy
  trade_policy.require(room.coordinator.scenario,a['seller'],a['buyer'])
  if not settled(db,a):raise ValueError('진행 중인 회차의 정산·귀환을 기다려 주세요.')
  selected=post(db,city,r['post']) if city==a['seller'] and r.get('post') else [a['post'],a['generation']]
  with db:db.execute("UPDATE trade_agreement SET state='offered',proposer=?,transfer=NULL,post=?,generation=?,revision=revision+1,action_key=?,action_payload=? WHERE id=?",(city,*selected,key,body,a['id']))
 else:raise ValueError('지원하지 않는 계약 명령')
 return item(db,city,a['id'])

def settled(db,a):
 if not a['transfer']:return True
 t=db.execute('SELECT state FROM live_transfer WHERE id=?',(a['transfer'],)).fetchone()
 f=db.execute('SELECT home FROM fleet_order WHERE id=?',(a['transfer'],)).fetchone()
 if not (t and t[0] in ('finished','rejected') and f and f[0]):return False
 # A 32-sack delivery travels as 16+16: the round ends when every part is settled and home.
 return not db.execute("""SELECT 1 FROM fleet_order f JOIN live_transfer t ON t.id=f.id
  WHERE f.origin=? AND (f.home=0 OR t.state NOT IN ('finished','rejected'))""",(a['transfer'],)).fetchone()

def advance(room,db):
 import army_orders,army_install
 if joint_save.pending(db) or army_orders.busy(db) or army_install.pending(room) or getattr(room.coordinator,'post_protocol',0)==1:return
 active=set(room.active_cities(db))
 if getattr(room,'started',False):
  # A contract with a city whose player left cannot run again in this session.
  for row in db.execute("SELECT * FROM trade_agreement WHERE state IN ('offered','active','paused')").fetchall():
   if {row['seller'],row['buyer']}<=active:continue
   t=db.execute('SELECT state FROM live_transfer WHERE id=?',(row['transfer'],)).fetchone() if row['transfer'] else None
   if t and t[0] not in ('finished','rejected'):continue # a round still on its way keeps its record
   with db:db.execute("UPDATE trade_agreement SET state='stopped',due_tick=0,revision=revision+1 WHERE id=?",(row['id'],))
 active=set(room.active_cities(db))
 for row in db.execute("SELECT * FROM trade_agreement WHERE state='active' ORDER BY COALESCE(transfer,0),id").fetchall():
  a=dict(row)
  if a['seller'] not in active or a['buyer'] not in active or not cash_live.ready(room,(a['seller'],a['buyer'])):continue
  if a['transfer']:
   t=db.execute('SELECT * FROM live_transfer WHERE id=?',(a['transfer'],)).fetchone()
   if not t:
    with db:db.execute("UPDATE trade_agreement SET state='paused' WHERE id=?",(a['id'],))
    continue
   if t['state']=='offered':
    # Durable standing consent survives a restart between issue and acceptance.
    cash_live.trade(room,db,a['buyer'],dict(op='live_accept',id=t['id']),t)
    continue
   if t['state']=='rejected':
    with db:db.execute("UPDATE trade_agreement SET state='paused' WHERE id=?",(a['id'],))
    continue
   if not settled(db,a):continue
   if not a['repeat']:
    with db:db.execute("UPDATE trade_agreement SET state='complete' WHERE id=?",(a['id'],))
    continue
  # Delivery deadline: counted in the seller's game time from when this round started waiting.
  tick=(getattr(room,'progress',{}).get(a['seller']) or (None,))[0]
  if type(tick)==int and not a['due_tick']:
   a['due_tick']=tick+DUE_TICKS
   with db:db.execute('UPDATE trade_agreement SET due_tick=? WHERE id=?',(a['due_tick'],a['id']))
  late=type(tick)==int and a['due_tick'] and tick>=a['due_tick']
  def expire():
   with db:db.execute("UPDATE trade_agreement SET state='stopped',expired=1,due_tick=0,revision=revision+1 WHERE id=?",(a['id'],))
  site=db.execute('SELECT active FROM fleet_site WHERE city=? AND building=? AND generation=?',(a['seller'],a['post'],a['generation'])).fetchone()
  if not site or not site[0]:
   if late:expire();continue # the seller's post never got ready to leave in time
   # Consent survives temporary staffing/path updates. Departure still requires readiness.
   if not db.execute('SELECT 1 FROM city_trade_post WHERE city=? AND building=? AND generation=? AND active=1',(a['seller'],a['post'],a['generation'])).fetchone():
    with db:db.execute("UPDATE trade_agreement SET state='paused' WHERE id=?",(a['id'],))
   continue
  import city_trade_routes
  try:city_trade_routes.require_posts(db,room.coordinator.scenario['cities'],a['seller'],a['buyer'],[a['post'],a['generation']])
  except ValueError:continue
  if stock(room,a['seller']).get(a['resource'],0)<a['quantity']:
   reported=getattr(room,'trade_stock',{}).get(a['seller'])
   if late and reported and 0<=room.clock()-reported[0]<10:expire() # goods never came within the deadline (fresh report only)
   continue
  # Shared caravans (24차): the round joins the post's queue like any other order.
  if db.execute("SELECT count(*) FROM live_transfer WHERE sender=? AND state NOT IN ('finished','rejected')",(a['seller'],)).fetchone()[0]>=64:continue
  try:post(db,a['seller'],[a['post'],a['generation']])
  except ValueError:
   with db:db.execute("UPDATE trade_agreement SET state='paused' WHERE id=?",(a['id'],))
   continue
  cycle=a['cycle']+1;key=uuid.uuid5(uuid.UUID(a['request']),str(cycle)).hex
  from trade_post_ledger import Ledger,stage_offer
  if not db.execute("SELECT 1 FROM sqlite_master WHERE name='post_meta'").fetchone():Ledger(room.coordinator.path,room.coordinator.scenario['cities'],transport=True).close()
  cash_live.scope(room,db)
  with db:
   tid=db.execute("INSERT INTO live_transfer(request,sender,receiver,resource,quantity,money,kind,state) VALUES(?,?,?,?,?,?,'sale','offered')",(key,a['seller'],a['buyer'],a['resource'],a['quantity'],a['money'])).lastrowid
   db.execute('INSERT INTO cash_transfer VALUES(?,?)',(tid,key))
   player_fleet.reserve(db,a['seller'],tid,[a['post'],a['generation']])
   db.execute('INSERT INTO goods_motion(id,route) VALUES(?,2)',(tid,))
   stage_offer(db,room.coordinator.scenario['cities'],a['seller'],key,a['buyer'],a['resource'],a['quantity'],a['money'])
   db.execute('UPDATE trade_agreement SET cycle=?,transfer=?,due_tick=0 WHERE id=?',(cycle,tid,a['id']))

def validate(rows,cities,transport):
 if not isinstance(rows,list) or len(rows)>10000:raise ValueError('계약 저장 크기 오류')
 seen=set();requests=set();linked=set()
 payload=transport
 if payload.get('version') in (7,8):payload=payload['transport']
 transfers={t['id']:t for t in payload['cash']['transfers']} if payload.get('version')==6 and payload['cash'] else {}
 from live_trade import RESOURCES
 for a in rows:
  # Saves from before a later field (e.g. the delivery deadline) carry a subset; defaults fill the rest.
  if not isinstance(a,dict) or not set(LEGACY_FIELDS)<=set(a)<=set(FIELDS):raise ValueError('계약 저장 형식 오류')
  a=negotiation.normalized(a);negotiation.validate(a,cities)
  if any(type(a[k])!=int for k in ('id','resource','quantity','money','repeat','post','generation','cycle')):raise ValueError('계약 숫자 오류')
  if a['id']<=0 or a['id'] in seen or a['seller'] not in cities or a['buyer'] not in cities or a['seller']==a['buyer'] or a['proposer'] not in (a['seller'],a['buyer']):raise ValueError('계약 식별 오류')
  if not isinstance(a['request'],str) or len(a['request'])!=32 or any(c not in '0123456789abcdef' for c in a['request']) or a['request'] in requests:raise ValueError('계약 요청 오류')
  if a['resource'] not in RESOURCES.values() or not 1<=a['quantity']<=32 or not 1<=a['money']<=1000000 or a['repeat'] not in (0,1) or a['state'] not in STATES or not 0<=a['post']<100000 or not 0<=a['generation']<65536 or a['cycle']<0:raise ValueError('계약 조건 오류')
  if a['state'] in ('active','paused','complete') and not a['post']:raise ValueError('계약 교역소 누락')
  if a['transfer'] is not None:
   if type(a['transfer'])!=int or a['transfer'] in linked or a['cycle']<1:raise ValueError('계약 회차 오류')
   t=transfers.get(a['transfer'])
   if not t or (t['sender'],t['receiver'],t['resource'],t['quantity'],t['money'],t['kind'],t['request'])!=(a['seller'],a['buyer'],a['resource'],a['quantity'],a['money'],'sale',uuid.uuid5(uuid.UUID(a['request']),str(a['cycle'])).hex):raise ValueError('계약 정산 연결 오류')
   linked.add(a['transfer'])
  elif a['state']=='complete':raise ValueError('완료 회차 누락')
  seen.add(a['id']);requests.add(a['request'])

def restore(db,rows):
 initialize(db)
 if db.execute('SELECT 1 FROM trade_agreement').fetchone():raise ValueError('계약 복원 대상이 비어 있지 않습니다.')
 for row in rows:
  a=negotiation.normalized(row)
  db.execute('INSERT INTO trade_agreement('+','.join(FIELDS)+') VALUES('+','.join('?' for _ in FIELDS)+')',tuple(a[k] for k in FIELDS))
