"""Bilateral city-route permission, separate from individual cargo orders.

All writes run under the existing room lock and SQLite transaction. Building
identities include their native generation; changing a peer never reuses a
post's live reservations. This module does not debit inventory or cash.
"""
import re

CAPACITY=32

def initialize(db):
 db.executescript('''
 CREATE TABLE IF NOT EXISTS city_trade_link(
  a TEXT,b TEXT,proposer TEXT,state TEXT,request TEXT UNIQUE,revision INTEGER NOT NULL,
  PRIMARY KEY(a,b),CHECK(a<b),CHECK(state IN ('offered','active','rejected')));
 CREATE TABLE IF NOT EXISTS city_trade_request(request TEXT PRIMARY KEY,a TEXT,b TEXT,proposer TEXT,revision INTEGER);
 CREATE TABLE IF NOT EXISTS city_trade_post(
  city TEXT,peer TEXT,building INTEGER,generation INTEGER,active INTEGER,
  PRIMARY KEY(city,peer),UNIQUE(city,building,generation));
 INSERT OR IGNORE INTO city_trade_request SELECT request,a,b,proposer,revision FROM city_trade_link;
 ''')

def pair(cities,city,peer):
 if not isinstance(city,str) or not isinstance(peer,str) or city not in cities or peer not in cities or city==peer:raise ValueError('다른 참가 도시를 선택하세요.')
 return tuple(sorted((city,peer)))

def active(db,cities,city,peer):
 a,b=pair(cities,city,peer)
 return bool(db.execute("SELECT 1 FROM city_trade_link WHERE a=? AND b=? AND state='active'",(a,b)).fetchone())

def request(db,cities,city,op,peer,request_id=None,revision=None):
 a,b=pair(cities,city,peer)
 if op=='route_offer' and (not isinstance(request_id,str) or not re.fullmatch('[0-9a-f]{32}',request_id)):
  raise ValueError('계약 요청 번호 오류')
 with db:
  db.execute('BEGIN IMMEDIATE')
  row=db.execute('SELECT * FROM city_trade_link WHERE a=? AND b=?',(a,b)).fetchone()
  if op=='route_offer':
   old=db.execute('SELECT * FROM city_trade_request WHERE request=?',(request_id,)).fetchone()
   if old:
    if (old['a'],old['b'],old['proposer'])!=(a,b,city):raise ValueError('계약 요청 번호가 다른 요청에 사용됐습니다.')
    return dict(row)
   if db.execute('SELECT count(*) FROM city_trade_request').fetchone()[0]>=4096:raise ValueError('교역 계약 제안 기록 한도에 도달했습니다.')
   if row and row['state'] in ('active','offered'):
    db.execute('INSERT INTO city_trade_request VALUES(?,?,?,?,?)',(request_id,a,b,city,row['revision']))
    return dict(row)
   rev=(row['revision']+1) if row else 1
   db.execute('INSERT INTO city_trade_request VALUES(?,?,?,?,?)',(request_id,a,b,city,rev))
   db.execute("INSERT INTO city_trade_link VALUES(?,?,?,'offered',?,?) ON CONFLICT(a,b) DO UPDATE SET proposer=excluded.proposer,state=excluded.state,request=excluded.request,revision=excluded.revision",(a,b,city,request_id,rev))
  elif op in ('route_accept','route_reject'):
   if not row or type(revision) is not int or row['revision']!=revision:raise ValueError('계약 상태가 변경됐습니다. 다시 확인하세요.')
   target='active' if op=='route_accept' else 'rejected'
   if row['proposer']==city:raise ValueError('상대 도시가 계약을 수락해야 합니다.')
   if row['state']==target:return dict(row)
   if row['state']!='offered':raise ValueError('응답할 계약 제안이 없습니다.')
   db.execute('UPDATE city_trade_link SET state=? WHERE a=? AND b=?',(target,a,b))
  else:raise ValueError('지원하지 않는 교역 계약 요청입니다.')
  return dict(db.execute('SELECT * FROM city_trade_link WHERE a=? AND b=?',(a,b)).fetchone())

def bind(db,cities,city,peer,building,generation):
 if not active(db,cities,city,peer):raise ValueError('교역 계약 수락 후 전용 교역소를 건설하세요.')
 if type(building) is not int or type(generation) is not int or not 0<building<100000 or not 0<=generation<65536:raise ValueError('교역소 식별 오류')
 with db:
  row=db.execute('SELECT * FROM city_trade_post WHERE city=? AND peer=?',(city,peer)).fetchone()
  if row and row['active'] and (row['building'],row['generation'])!=(building,generation):raise ValueError('해당 도시 전용 교역소가 이미 있습니다.')
  db.execute('INSERT INTO city_trade_post VALUES(?,?,?,?,1) ON CONFLICT(city,peer) DO UPDATE SET building=excluded.building,generation=excluded.generation,active=1',(city,peer,building,generation))

def deactivate(db,city,building,generation):
 with db:db.execute('UPDATE city_trade_post SET active=0 WHERE city=? AND building=? AND generation=?',(city,building,generation))

def snapshot(db):
 return dict(requests=[dict(r) for r in db.execute('SELECT * FROM city_trade_request ORDER BY request')],links=[dict(r) for r in db.execute('SELECT * FROM city_trade_link ORDER BY a,b')],posts=[dict(r) for r in db.execute('SELECT * FROM city_trade_post ORDER BY city,peer')])

def validate(data,cities):
 if not isinstance(data,dict) or set(data)!= {'links','posts','requests'} or not isinstance(data['links'],list) or not isinstance(data['posts'],list) or not isinstance(data['requests'],list):raise ValueError('도시 교역 저장 형식 오류')
 if len(data['requests'])>4096:raise ValueError('계약 요청 기록 개수 오류')
 if len(data['links'])>len(cities)*(len(cities)-1)//2 or len(data['posts'])>len(cities)*(len(cities)-1):raise ValueError('도시 교역 저장 개수 오류')
 seen=set();requests=set();allowed=set()
 for row in data['links']:
  if not isinstance(row,dict) or set(row)!=set('a b proposer state request revision'.split()):raise ValueError('교역 계약 저장 오류')
  key=pair(cities,row['a'],row['b'])
  if key!=(row['a'],row['b']) or key in seen or row['proposer'] not in key or row['state'] not in ('offered','active','rejected') or type(row['revision']) is not int or row['revision']<1 or not isinstance(row['request'],str) or not re.fullmatch('[0-9a-f]{32}',row['request']) or row['request'] in requests:raise ValueError('교역 계약 저장 값 오류')
  seen.add(key);requests.add(row['request'])
  if row['state']=='active':allowed.add(key)
 history={}
 for row in data['requests']:
  if not isinstance(row,dict) or set(row)!=set('request a b proposer revision'.split()):raise ValueError('계약 요청 기록 오류')
  key=pair(cities,row['a'],row['b'])
  if key!=(row['a'],row['b']) or row['proposer'] not in key or type(row['revision']) is not int or row['revision']<1 or not isinstance(row['request'],str) or not re.fullmatch('[0-9a-f]{32}',row['request']) or row['request'] in history:raise ValueError('계약 요청 기록 값 오류')
  history[row['request']]=row
 for row in data['links']:
  if history.get(row['request'])!={k:row[k] for k in 'request a b proposer revision'.split()}:raise ValueError('계약 요청 기록 누락')
 for row in data['requests']:
  current=next((r for r in data['links'] if (r['a'],r['b'])==(row['a'],row['b'])),None)
  if current is None or row['revision']>current['revision']:raise ValueError('고아 계약 요청 기록')
 seen=set();buildings=set()
 for row in data['posts']:
  if not isinstance(row,dict) or set(row)!=set('city peer building generation active'.split()):raise ValueError('전용 교역소 저장 오류')
  key=pair(cities,row['city'],row['peer']);site=(row['city'],row['building'],row['generation']);owner=(row['city'],row['peer'])
  if key not in allowed or owner in seen or site in buildings or type(row['building']) is not int or not 0<row['building']<100000 or type(row['generation']) is not int or not 0<=row['generation']<65536 or type(row['active']) is not int or row['active'] not in (0,1):raise ValueError('전용 교역소 저장 값 오류')
  seen.add(owner);buildings.add(site)

def restore(db,data,cities):
 validate(data,cities)
 if db.execute('SELECT 1 FROM city_trade_link').fetchone() or db.execute('SELECT 1 FROM city_trade_post').fetchone():raise ValueError('교역 계약 복원 대상이 비어 있지 않습니다.')
 with db:
  for r in data['requests']:db.execute('INSERT INTO city_trade_request VALUES(?,?,?,?,?)',tuple(r[k] for k in 'request a b proposer revision'.split()))
  for r in data['links']:db.execute('INSERT INTO city_trade_link VALUES(?,?,?,?,?,?)',tuple(r[k] for k in 'a b proposer state request revision'.split()))
  for r in data['posts']:db.execute('INSERT INTO city_trade_post VALUES(?,?,?,?,?)',tuple(r[k] for k in 'city peer building generation active'.split()))

def register(db,cities,city,rows):
 """Replace one authenticated city's binding catalog, validating the whole batch."""
 if not isinstance(rows,list) or len(rows)>512:raise ValueError('전용 교역소 목록 오류')
 roster=sorted(cities);seen=set();sites=set();validated=[]
 for row in rows:
  if not isinstance(row,list) or len(row)!=3 or any(type(v) is not int for v in row):raise ValueError('전용 교역소 항목 오류')
  building,generation,slot=row
  if not 0<building<100000 or not 0<=generation<65536 or not 0<=slot<=len(roster) or building in sites:raise ValueError('전용 교역소 식별 오류')
  sites.add(building)
  if slot==0:continue # Legacy unassigned posts do not acquire a route implicitly.
  peer=roster[slot-1]
  if peer==city or peer in seen or not active(db,cities,city,peer):raise ValueError('교역 계약과 교역소가 일치하지 않습니다.')
  seen.add(peer);validated.append((city,peer,building,generation))
 with db:
  db.execute('UPDATE city_trade_post SET active=0 WHERE city=?',(city,))
  for row in validated:
   db.execute('INSERT INTO city_trade_post VALUES(?,?,?,?,1) ON CONFLICT(city,peer) DO UPDATE SET building=excluded.building,generation=excluded.generation,active=1',row)

def require_posts(db,cities,city,peer,selected=None):
 if not active(db,cities,city,peer):raise ValueError('먼저 도시 교역 계약을 체결하세요.')
 result=[]
 for owner,other in ((city,peer),(peer,city)):
  row=db.execute('SELECT building,generation FROM city_trade_post WHERE city=? AND peer=? AND active=1',(owner,other)).fetchone()
  if not row:raise ValueError('양쪽 도시에 상대 도시 전용 교역소가 필요합니다.')
  result.append(list(row))
 if selected is not None and selected!=result[0]:raise ValueError('선택한 상대의 전용 교역소를 이용하세요.')
 return result
