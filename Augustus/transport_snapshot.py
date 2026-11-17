"""Contract metadata captured in the same transaction as a complete city pair."""
import json
from coordinator import sha
FIELDS=('id','request','sender','receiver','resource','quantity','money','kind','state')
def initialize(db):
 db.execute('CREATE TABLE IF NOT EXISTS joint_transport(id INTEGER PRIMARY KEY,payload TEXT,hash TEXT)')
 if 'transport_version' not in {r[1] for r in db.execute('PRAGMA table_info(joint_save)')}:
  db.execute('ALTER TABLE joint_save ADD COLUMN transport_version INTEGER')

def legacy_current(db):
 """Pure projection shared by capture and offline-retention validation."""
 t=db.execute('SELECT * FROM live_transfer ORDER BY id DESC LIMIT 1').fetchone() if db.execute("SELECT 1 FROM sqlite_master WHERE name='live_transfer'").fetchone() else None
 transfer=None
 cargo_row=db.execute('SELECT * FROM live_cargo WHERE id=?',(t['id'],)).fetchone() if t and db.execute("SELECT 1 FROM sqlite_master WHERE name='live_cargo'").fetchone() else None
 if t and (t['state']=='travelling' or (t['state']=='saving' and db.execute('SELECT 1 FROM live_transport WHERE id=?',(t['id'],)).fetchone())):
  transfer={k:t[k] for k in FIELDS};transfer['state']='travelling'
 sequence=db.execute("SELECT seq FROM sqlite_sequence WHERE name='live_transfer'").fetchone()
 last_id=max(t['id'] if t else 0,sequence[0] if sequence else 0)
 data=dict(version=1,last_id=last_id,transfer=transfer)
 if cargo_row:
  import cargo_snapshot
  c=cargo_snapshot.cargo(cargo_row['cargo']);transfer=None
  if c['remaining']:
   transfer={k:t[k] for k in FIELDS}
   transfer['state']='returning' if cargo_row['phase']=='refund' or t['state']=='returning' else 'travelling'
  source_route=cargo_row['source_route'] if 'source_route' in cargo_row.keys() else 0
  if transfer and source_route>=2 and transfer['state']=='travelling' and (cargo_row['phase']=='load' or (cargo_row['phase']=='depart' and t['state']!='committed')):
   transfer['state']='departing'
  if source_route and (t['state']=='collecting' or (t['state']=='saving' and cargo_row['phase']=='load')) and not c['remaining']:
   transfer={k:t[k] for k in FIELDS};transfer['state']='collecting'
  data=dict(version=2,last_id=last_id,transfer=transfer,cargo=cargo_row['cargo'].hex() if transfer else None)
  if source_route:data.update(version=source_route+2,source_route=source_route)
 return data

def base_current(db):
 import cash_snapshot
 data=legacy_current(db);cash=cash_snapshot.current(db)
 if cash is None:return data
 if data['transfer'] and db.execute('SELECT 1 FROM cash_transfer WHERE id=?',(data['transfer']['id'],)).fetchone():data['transfer']=None
 return dict(version=6,legacy=data,cash=cash)

def without_agreements(db):
 data=base_current(db)
 if not db.execute("SELECT 1 FROM sqlite_master WHERE name='army_live'").fetchone():return data
 import army_live
 army_live.initialize(db)
 rows=[dict(r) for r in db.execute('SELECT * FROM army_live')]
 if not rows:return data
 return dict(version=8,transport=data,army=rows,commands=[dict(r) for r in db.execute('SELECT * FROM army_live_command')])

def without_routes(db):
 data=without_agreements(db)
 if not db.execute("SELECT 1 FROM sqlite_master WHERE name='trade_agreement'").fetchone():return data
 import trade_agreements
 rows=trade_agreements.snapshot(db)
 return dict(version=9,transport=data,agreements=rows) if rows else data

def current(db):
 data=without_routes(db)
 if not db.execute("SELECT 1 FROM sqlite_master WHERE name='city_trade_link'").fetchone():return data
 import city_trade_routes
 routes=city_trade_routes.snapshot(db)
 return dict(version=10,transport=data,routes=routes) if routes['links'] or routes['posts'] else data

def capture(db,sid):
 import objectives
 objectives.capture(db,sid)
 data=current(db)
 payload=json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(',',':'))
 db.execute('INSERT INTO joint_transport VALUES(?,?,?)',(sid,payload,sha(payload.encode())))
 db.execute('UPDATE joint_save SET transport_version=? WHERE id=?',(data['version'],sid))

def transfer_of(data):
 """The cargo transfer of a checkpoint, whatever envelope holds it: versions 8-10 wrap the transport record
 ({'version','transport',...}), older ones carry 'transfer' at the top. None when nothing is travelling."""
 while isinstance(data,dict) and 'transfer' not in data and isinstance(data.get('transport'),dict):data=data['transport']
 return data.get('transfer') if isinstance(data,dict) else None

def read(db,sid,cities):
 columns={r[1] for r in db.execute('PRAGMA table_info(joint_save)')}
 if 'transport_version' not in columns:return None
 version=db.execute('SELECT transport_version FROM joint_save WHERE id=?',(sid,)).fetchone()[0]
 if version is None:return None # Exact legacy saves, before the extension.
 if version not in (1,2,3,4,5,6,7,8,9,10):raise ValueError('지원하지 않는 운송 저장 버전입니다.')
 if not db.execute("SELECT 1 FROM sqlite_master WHERE name='joint_transport'").fetchone():raise ValueError('운송 저장 정보가 누락되었습니다.')
 row=db.execute('SELECT payload,hash FROM joint_transport WHERE id=?',(sid,)).fetchone()
 if not row or not isinstance(row[0],str) or len(row[0])>4000000 or sha(row[0].encode())!=row[1]:raise ValueError('운송 저장 정보 검증 실패')
 try:data=json.loads(row[0])
 except (ValueError,TypeError):raise ValueError('잘못된 운송 저장 정보')
 validate(data,cities)
 if data['version']!=version:raise ValueError('운송 저장 버전 불일치')
 return data

def validate(data,cities):
 if isinstance(data,dict) and type(data.get('version')) is int and data['version']==10:
  if set(data)!={'version','transport','routes'} or not isinstance(data['transport'],dict) or type(data['transport'].get('version')) is not int or data['transport']['version'] not in range(1,10):raise ValueError('route checkpoint envelope')
  validate(data['transport'],cities)
  import city_trade_routes
  city_trade_routes.validate(data['routes'],cities);return
 if isinstance(data,dict) and type(data.get('version')) is int and data['version']==9:
  if set(data)!={'version','transport','agreements'} or not isinstance(data['transport'],dict) or data['transport'].get('version') not in range(1,9):raise ValueError('contract checkpoint envelope')
  validate(data['transport'],cities)
  import trade_agreements
  trade_agreements.validate(data['agreements'],cities,data['transport']);return
 if isinstance(data,dict) and data.get('version') in (7,8):
  if set(data)!={'version','transport','army','commands'} or data['transport'].get('version') in (7,8):raise ValueError('military checkpoint envelope')
  validate(data['transport'],cities)
  import army_live
  army_live.validate_snapshot(data,cities)
  return
 if isinstance(data,dict) and type(data.get('version')) is int and data['version']==6:
  if set(data)!={'version','legacy','cash'} or data['legacy'].get('version')==6:raise ValueError('cash transport envelope')
  import cash_snapshot
  validate(data['legacy'],cities);cash_snapshot.validate(data['cash'],cities);return

 if not isinstance(data,dict) or type(data.get('version'))!=int or data['version'] not in (1,2,3,4,5):raise ValueError('잘못된 운송 저장 버전')
 keys={'version','last_id','transfer'} | ({'cargo'} if data['version']>=2 else set()) | ({'source_route'} if data['version']>=3 else set())
 if set(data)!=keys or type(data['last_id'])!=int or not 0<=data['last_id']<2**32:raise ValueError('잘못된 운송 저장 정보')
 if data['version']>=3 and (type(data['source_route'])!=int or data['source_route']!=data['version']-2):raise ValueError('수집 운송 버전 오류')
 t=data['transfer']
 if t is None:
  if data['version']>=2 and data['cargo'] is not None:raise ValueError('고아 화물 정보')
  return
 if not isinstance(t,dict) or set(t)!=set(FIELDS):raise ValueError('잘못된 운송 계약')
 states=('travelling','returning','collecting','departing') if data['version']>=4 else ('travelling','returning','collecting') if data['version']==3 else ('travelling','returning') if data['version']==2 else ('travelling',)
 if type(t['id'])!=int or not 0<t['id']<=data['last_id'] or t['state'] not in states or t['sender'] not in cities or t['receiver'] not in cities or t['sender']==t['receiver']:raise ValueError('운송 계약 식별자 오류')
 if not isinstance(t['request'],str) or len(t['request'])!=32 or any(c not in '0123456789abcdef' for c in t['request']):raise ValueError('운송 요청 식별자 오류')
 from live_trade import RESOURCES
 if type(t['resource'])!=int or t['resource'] not in RESOURCES.values() or type(t['quantity'])!=int or not 1<=t['quantity']<=32 or type(t['money'])!=int:raise ValueError('운송 품목/수량 오류')
 if not ((t['kind']=='sale' and 0<t['money']<=1000000) or (t['kind']=='gift' and t['money']==0)):raise ValueError('운송 금액 오류')
 if data['version']>=2:
  import cargo_snapshot
  if not isinstance(data['cargo'],str) or len(data['cargo'])!=56:raise ValueError('화물 정보 누락')
  c=cargo_snapshot.cargo(bytes.fromhex(data['cargo']))
  if t['state']=='collecting':
   if c['contract']:raise ValueError('수집 전 선적 화물 존재')
   return
  if c['contract']!=t['id'] or c['resource']!=t['resource'] or c['total']!=t['quantity'] or not c['remaining'] or (t['state'] in ('travelling','departing') and c['state']!=1):raise ValueError('화물 계약 불일치')

def restore(db,data,cities):
 if data is None:return
 if data.get('version')==10:
  validate(data,cities);restore(db,data['transport'],cities)
  import city_trade_routes
  city_trade_routes.restore(db,data['routes'],cities);return
 if data.get('version')==9:
  validate(data,cities);restore(db,data['transport'],cities)
  import trade_agreements
  trade_agreements.restore(db,data['agreements']);return
 if data.get('version') in (7,8):
  validate(data,cities);restore(db,data['transport'],cities)
  import army_live
  army_live.initialize(db)
  for table,rows in [('army_live',data['army']),('army_live_command',data['commands'])]:
   for row in rows:
    if table=='army_live':row=dict(row,transit_seen=-1)
    columns=list(row);db.execute('INSERT INTO '+table+'('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+')',[row[k] for k in columns])
  return
 if data.get('version')==6:
  validate(data,cities);restore(db,data['legacy'],cities)
  import cash_snapshot
  cash_snapshot.restore(db,data['cash'],cities);return
 validate(data,cities)
 if db.execute('SELECT 1 FROM live_transfer').fetchone():raise ValueError('복원 대상 방이 비어 있지 않습니다.')
 t=data['transfer']
 if t:db.execute('INSERT INTO live_transfer('+','.join(FIELDS)+') VALUES('+','.join('?' for _ in FIELDS)+')',tuple(t[k] for k in FIELDS))
 if t and data['version']>=2:
  db.execute('INSERT INTO live_cargo(id,phase,cargo,source_route) VALUES(?,?,?,?)',(t['id'],'collect' if t['state']=='collecting' else 'depart' if t['state']=='departing' else 'refund' if t['state']=='returning' else 'travel',bytes.fromhex(data['cargo']),data.get('source_route',0)))
 # Keep old completed/cancelled IDs reserved too: old figures/files cannot match a new contract.
 db.execute("DELETE FROM sqlite_sequence WHERE name='live_transfer'")
 db.execute("INSERT INTO sqlite_sequence(name,seq) VALUES('live_transfer',?)",(data['last_id'],))
