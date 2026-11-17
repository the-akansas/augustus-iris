"""Local prototype: durable two-city commit over authenticated loopback requests.
The coordinator stores engine-produced snapshots, never invents game inventory.
Clients must remain frozen from accept/prepare until decision + checkpoint install.
"""
import base64, hashlib, json, secrets, sqlite3, struct, uuid
from contextlib import closing
from ledger import encode
PROTOCOL=2
BUILD='c0b2a5aefcd8f12331aad028002f101bf8c22417-mp2-network65-r102-state'
MAX_SAVE=8*1024*1024

def sha(data):return hashlib.sha256(data).hexdigest()
def receipt(data):
 if len(data)!=32:raise ValueError('receipt size')
 magic,seq,w,q,m,incoming,pending=struct.unpack('<4sQiiiii',data)
 if magic!=b'MPC1' or w<0 or q<0 or q>32 or incoming not in (0,1) or not 0<=pending<=32:raise ValueError('receipt fields')
 return dict(seq=seq,warehouse=w,quantity=q,money=m,incoming=incoming,pending=pending)
def blob(text):
 if not isinstance(text,str) or len(text)>MAX_SAVE*4//3+4:raise ValueError('snapshot size')
 data=base64.b64decode(text,validate=True)
 if not data or len(data)>MAX_SAVE:raise ValueError('snapshot size')
 return data

class Coordinator:
 def __init__(self,path,session,scenario=None):
  self.path=str(path);self.session=session;self.scenario=scenario;self.wire_scenario=scenario["sha256"] if scenario else None
  with closing(self.connect()) as db:
   db.executescript('''CREATE TABLE IF NOT EXISTS identity(session TEXT PRIMARY KEY);
   CREATE TABLE IF NOT EXISTS city(id TEXT PRIMARY KEY,token TEXT,save BLOB,receipt BLOB,active TEXT);
   CREATE TABLE IF NOT EXISTS tx(id TEXT PRIMARY KEY,seller TEXT,buyer TEXT,qty INTEGER,price INTEGER,state TEXT);
   CREATE TABLE IF NOT EXISTS prepared(tx TEXT,city TEXT,save BLOB,receipt BLOB,PRIMARY KEY(tx,city));
   CREATE TABLE IF NOT EXISTS ack(tx TEXT,city TEXT,PRIMARY KEY(tx,city));''')
   db.execute('CREATE TABLE IF NOT EXISTS scenario_binding(value TEXT NOT NULL)')
   binding=json.dumps(scenario,sort_keys=True,separators=(',',':'))
   previous=db.execute('SELECT value FROM scenario_binding').fetchone()
   if previous and previous[0]!=binding:raise ValueError('wrong scenario database')
   if not previous:
    if scenario is not None and db.execute('SELECT count(*) FROM city').fetchone()[0]:raise ValueError('cannot bind existing cities')
    db.execute('INSERT INTO scenario_binding VALUES(?)',(binding,))
   rows=db.execute('SELECT session FROM identity').fetchall()
   if rows and rows[0][0]!=session:raise ValueError('wrong session database')
   if not rows:db.execute('INSERT INTO identity VALUES(?)',(session,))
   db.commit()
 def connect(self):
  db=sqlite3.connect(self.path,timeout=10);db.row_factory=sqlite3.Row;db.execute('PRAGMA synchronous=FULL');return db
 def provision(self,city,save,rec):
  if self.scenario is not None and city not in self.scenario['cities']:raise ValueError('city outside scenario')
  receipt(rec);token=secrets.token_hex(32)
  with closing(self.connect()) as db:
   try:db.execute('INSERT INTO city VALUES(?,?,?,?,NULL)',(city,sha(token.encode()),save,rec));db.commit()
   except sqlite3.IntegrityError as exc:raise ValueError('city already assigned') from exc
  return token
 def request(self,r):
  if not isinstance(r,dict) or r.get('protocol')!=PROTOCOL or r.get('build')!=BUILD or r.get('session')!=self.session:raise ValueError('incompatible session')
  if r.get('scenario')!=self.wire_scenario:raise ValueError('incompatible scenario')
  city=r.get('city');token=r.get('token')
  if not isinstance(city,str) or not isinstance(token,str):raise ValueError('unauthorized')
  with closing(self.connect()) as db:
   try:
    db.execute('BEGIN IMMEDIATE')
    c=db.execute('SELECT * FROM city WHERE id=?',(city,)).fetchone()
    if c is None or not secrets.compare_digest(c['token'],sha(token.encode())):raise ValueError('unauthorized')
    op=r.get('op')
    if op=='snapshot':
     result={'save':base64.b64encode(c['save']).decode(),'receipt':base64.b64encode(c['receipt']).decode(),'active':c['active']}
    elif op=='checkpoint':
     sav=blob(r.get('save'));rec=blob(r.get('receipt'));state=receipt(rec);previous=receipt(c['receipt'])
     if c['active']:raise ValueError('city frozen for transaction')
     if (sav,rec)!=(c['save'],c['receipt']):
      if r.get('base')!=sha(c['save']+c['receipt']):raise ValueError('stale checkpoint')
      if any(state[k]!=previous[k] for k in previous if k!='pending') or state['pending']>previous['pending']:raise ValueError('receipt changed outside transaction')
      db.execute('UPDATE city SET save=?,receipt=? WHERE id=?',(sav,rec,city))
     result={'checkpoint':sha(sav+rec)}
    elif op=='offer':
     tid=r.get('tx');buyer=r.get('buyer');qty=r.get('quantity');price=r.get('price')
     if not isinstance(tid,str) or len(tid)!=32 or any(ch not in '0123456789abcdef' for ch in tid):raise ValueError('transaction id')
     if type(qty)!=int or not 1<=qty<=32 or type(price)!=int or not 1<=price<=1000000:raise ValueError('amount')
     other=db.execute('SELECT * FROM city WHERE id=?',(buyer,)).fetchone()
     if buyer==city or other is None:raise ValueError('buyer')
     old=db.execute('SELECT * FROM tx WHERE id=?',(tid,)).fetchone()
     if old:
      if (old['seller'],old['buyer'],old['qty'],old['price'])!=(city,buyer,qty,price):raise ValueError('transaction id reused')
     else:
      if c['active'] or other['active']:raise ValueError('city busy')
      db.execute('INSERT INTO tx VALUES(?,?,?,?,?,?)',(tid,city,buyer,qty,price,'offered'))
      db.execute('UPDATE city SET active=? WHERE id IN (?,?)',(tid,city,buyer))
     result={'tx':tid}
    else:
     tid=r.get('tx');t=db.execute('SELECT * FROM tx WHERE id=?',(tid,)).fetchone()
     if t is None or city not in (t['seller'],t['buyer']):raise ValueError('not a participant')
     if op=='accept':
      if city!=t['buyer']:raise ValueError('buyer consent required')
      if t['state']=='offered':db.execute("UPDATE tx SET state='preparing' WHERE id=?",(tid,))
      elif t['state'] not in ('preparing','committed'):raise ValueError('already aborted')
     elif op=='prepare':
      if t['state'] not in ('preparing','committed'):raise ValueError('not preparing')
      sav=blob(r.get('save'));rec=blob(r.get('receipt'));state=receipt(rec)
      old=db.execute('SELECT * FROM prepared WHERE tx=? AND city=?',(tid,city)).fetchone()
      if old:
       if old['save']!=sav or old['receipt']!=rec:raise ValueError('conflicting preparation')
      else:
       if t['state']!='preparing' or c['active']!=tid:raise ValueError('stale prepare')
       if r.get('base')!=sha(c['save']+c['receipt']):raise ValueError('stale checkpoint')
       previous=receipt(c['receipt']);incoming=int(city==t['buyer']);money=t['qty']*t['price']*(-1 if incoming else 1)
       if state['seq']!=previous['seq']+1 or state['quantity']!=t['qty'] or state['money']!=money or state['incoming']!=incoming or state['pending']!=(t['qty'] if incoming else 0):raise ValueError('wrong receipt')
       db.execute('INSERT INTO prepared VALUES(?,?,?,?)',(tid,city,sav,rec))
       prepared=db.execute('SELECT * FROM prepared WHERE tx=?',(tid,)).fetchall()
       if len(prepared)==2:
        # Both snapshots and the decision become visible in ONE SQLite commit.
        for p in prepared:db.execute('UPDATE city SET save=?,receipt=? WHERE id=?',(p['save'],p['receipt'],p['city']))
        db.execute("UPDATE tx SET state='committed' WHERE id=?",(tid,))
     elif op=='abort':
      if t['state']=='committed':raise ValueError('commit cannot be undone')
      db.execute("UPDATE tx SET state='aborted' WHERE id=?",(tid,))
     elif op=='ack':
      if t['state'] not in ('committed','aborted'):raise ValueError('no decision')
      if r.get('checkpoint')!=sha(c['save']+c['receipt']):raise ValueError('wrong installed checkpoint')
      db.execute('INSERT OR IGNORE INTO ack VALUES(?,?)',(tid,city))
      if db.execute('SELECT count(*) FROM ack WHERE tx=?',(tid,)).fetchone()[0]==2:
       db.execute('UPDATE city SET active=NULL WHERE active=?',(tid,))
     elif op!='status':raise ValueError('unknown operation')
     result=dict(db.execute('SELECT * FROM tx WHERE id=?',(tid,)).fetchone())
     result['ready']=[x[0] for x in db.execute('SELECT city FROM prepared WHERE tx=?',(tid,))]
    db.commit();return result
   except BaseException:db.rollback();raise

# Kept separate from the small chat-only prototype frame limit: saves are bounded at 8 MiB.
import socketserver
FRAME_LIMIT=12*1024*1024
class Handler(socketserver.StreamRequestHandler):
 # Clients keep one connection open and send one request line at a time; an
 # older one-request client simply closes after the first reply.
 def handle(self):
  self.connection.settimeout(15)
  while True:
   try:data=self.rfile.readline(FRAME_LIMIT+1)
   except (TimeoutError,ConnectionError,OSError):return
   if not data:return
   if not self.answer(data):return
 def answer(self,data):
  try:
   if len(data)>FRAME_LIMIT or not data.endswith(b'\n'):raise ValueError('frame size')
   request=json.loads(data)
   if isinstance(request,dict) and request.get('op')=='batch':
    # One round trip for a client's routine polls (city_client.Client.begin_round). Each entry is an ordinary
    # request with the caller's own credentials, answered one after another exactly as if sent alone; a failing
    # entry fails alone. No nesting, no unauthenticated (public/recovery) operations.
    calls=request.get('calls')
    if not isinstance(calls,list) or not 1<=len(calls)<=32 or any(not isinstance(c,dict) or not isinstance(c.get('op'),str) or c['op']=='batch' or c['op'].startswith(('public_','recovery_offer','recovery_join')) for c in calls):raise ValueError('batch')
    base={k:v for k,v in request.items() if k not in ('op','calls','_chat_after','_engine_ticks')}
    response={'ok':True,'result':[self.one(dict(base,**{k:v for k,v in c.items() if k not in ('_chat_after','_engine_ticks')})) for c in calls]}
   else:response={'ok':True,'result':self.server.public_diag(request) if isinstance(request,dict) and request.get('op')=='public_diag' and hasattr(self.server,'public_diag') else self.server.public_info(request) if isinstance(request,dict) and request.get('op')=='public_info' and hasattr(self.server,'public_info') else self.server.recovery_offer(request) if isinstance(request,dict) and request.get('op')=='recovery_offer' and hasattr(self.server,'recovery_offer') else self.server.recovery_join(request) if isinstance(request,dict) and request.get('op')=='recovery_join' and hasattr(self.server,'recovery_join') else self.server.public_join(request) if isinstance(request,dict) and request.get('op')=='public_join' and hasattr(self.server,'public_join') else self.server.coordinator.request(request)}
  except (ValueError,TypeError,KeyError) as error:response=self.refusal(error)
  except (TimeoutError,ConnectionError):return False
  except Exception:response={'ok':False,'error':'internal_error'}
  if isinstance(locals().get('request'),dict):
   from network_tick import attach
   response=attach(self.server.coordinator,request,response)
   from chat_delivery import attach as attach_chat
   response=attach_chat(self.server.coordinator,request,response)
  try:self.wfile.write((encode(response)+'\n').encode())
  except (TimeoutError,ConnectionError,OSError):return False
  # An oversized or unterminated frame leaves the stream unsynchronised.
  return len(data)<=FRAME_LIMIT and data.endswith(b'\n')
 def one(self,request):
  """One entry of a batch: the same answer the request would get alone (no piggyback; the batch frame carries it)."""
  try:return {'ok':True,'result':self.server.coordinator.request(request)}
  except (ValueError,TypeError,KeyError) as error:return self.refusal(error)
  except (TimeoutError,ConnectionError):raise
  except Exception:return {'ok':False,'error':'internal_error'}
 def refusal(self,error):
   # Expose only fixed public status codes, never arbitrary exception details.
   public={'다른 플레이어가 쓰고 있는 색입니다.','게임 시작 준비 중이거나 시작한 뒤에는 색을 바꿀 수 없습니다.','이 도시는 이미 지원군 여섯 군단을 받고 있습니다. 한 군단이 돌아간 뒤 보내 주세요.','이 도시에는 공격군을 두 부대까지만 보낼 수 있습니다. 한 부대가 돌아온 뒤 보내 주세요.','같은 도시에 지원군과 공격군을 함께 둘 수 없습니다. 먼저 보낸 군단이 돌아온 뒤 보내 주세요.','상대가 보유 중이거나 두 도시가 거래한 물품을 선택하세요.','판매자 교역소를 선택하세요.','판매자 교역소가 없거나 변경되었습니다. 교역소를 다시 확인하세요.','판매자 교역소의 도로와 인력을 확인하세요.','판매자 교역소의 출입구 연결을 확인하세요.','양쪽 도시에 상대 도시 전용 교역소가 필요합니다.','선택한 상대의 전용 교역소를 이용하세요.','제안이 변경되었습니다. 최신 내용을 확인하세요.','상대방의 동의가 필요합니다.','이미 처리된 제안입니다.','원래 제안보다 적은 수량을 입력하세요.','받은 구매 제안만 수량을 수정할 수 있습니다.','select player trading post','player trading post unavailable','player trading post order queue full','city order queue full','removed by host','host required','cannot remove host','participant changed','room changed','participants must be ready','host only','city occupied','game already started',
    'start in progress','start snapshot mismatch','stale start acknowledgement',
    'remaining save blocked by trade','both engines required','participant left; trade suspended','transaction pending','invalid name','room closed','room left','participant timed out','host fenced','room full','transfer busy','save busy','save in progress',
    'wrong objective sample','participants must choose cities','throne needs two players','needs players 2','needs players 3','needs players 4','needs players 5','needs players 6','too many players','start already finished'}   # fixed status codes (2026-11-13: quiet goal-report retry; start blocked while someone has no city)
   return {'ok':False,'error':str(error) if isinstance(error,ValueError) and str(error) in public else 'invalid_request'}
class Server(socketserver.ThreadingTCPServer):
 daemon_threads=True
 def __init__(self,coordinator,host='127.0.0.1',port=0):
  from connection_config import address,port as valid_port
  self.coordinator=coordinator
  super().__init__((address(host),valid_port(port,ephemeral=True)),Handler)
