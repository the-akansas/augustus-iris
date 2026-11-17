"""Each authenticated city controls viewers of that city; no host override."""
import json
from coordinator import sha

def initialize(db):
 db.execute('CREATE TABLE IF NOT EXISTS observe_permission(owner TEXT,viewer TEXT,allowed INTEGER,revision INTEGER,PRIMARY KEY(owner,viewer))')
 db.execute('CREATE TABLE IF NOT EXISTS joint_observe(id INTEGER PRIMARY KEY,payload TEXT,hash TEXT)')

def state(db):
 return [dict(r) for r in db.execute('SELECT * FROM observe_permission ORDER BY owner,viewer')]

def allowed(db,owner,viewer):
 row=db.execute('SELECT allowed FROM observe_permission WHERE owner=? AND viewer=?',(owner,viewer)).fetchone()
 return row is None or bool(row[0]) # Preserve existing rooms; owners may opt out per viewer.

def request(room,db,city,r):
 target=r.get('target');value=r.get('allowed');revision=r.get('revision')
 spectators=target=='~spectator'   # every spectator of the room (spectate.py, Korean edition): one line for them all
 if spectators:
  if city not in room.active_cities(db):raise ValueError('관전 설정 대상이 변경되었습니다.')
 else:
  if not room.started or city not in room.active_cities(db) or target==city or target not in room.active_cities(db):raise ValueError('관전 설정 대상이 변경되었습니다.')
  row=db.execute('SELECT token FROM lobby_invite WHERE city=?',(target,)).fetchone()
  if not row or sha(row[0].encode())!=r.get('generation'):raise ValueError('participant changed')
 if type(value)is not bool or type(revision)is not int or revision<0:raise ValueError('잘못된 관전 설정입니다.')
 old=db.execute('SELECT allowed,revision FROM observe_permission WHERE owner=? AND viewer=?',(city,target)).fetchone()
 current,version=(bool(old[0]),old[1]) if old else (True,0)
 if current!=value:
  if revision!=version:raise ValueError('관전 설정이 변경되었습니다. 목록을 확인하고 다시 선택해 주세요.')
  version+=1;db.execute('INSERT OR REPLACE INTO observe_permission VALUES(?,?,?,?)',(city,target,int(value),version));db.commit()
 if not value:
  observers=getattr(room,'observers',{})
  if spectators:
   for key in [k for k,v in observers.items() if k.startswith('spectator:') and v.get('target')==city]:observers.pop(key,None)
  elif observers.get(target,{}).get('target')==city:observers.pop(target,None)
 return dict(allowed=value,revision=version)

def validate(rows,cities):
 if not isinstance(rows,list) or len(rows)>len(cities)**2+len(cities):raise ValueError('관전 저장 형식 오류')   # + one '~spectator' line per city
 seen=set()
 for r in rows:
  if not isinstance(r,dict) or set(r)!={'owner','viewer','allowed','revision'}:raise ValueError('관전 저장 형식 오류')
  key=(r['owner'],r['viewer'])
  if key[0] not in cities or (key[1] not in cities and key[1]!='~spectator') or key[0]==key[1] or key in seen or type(r['allowed'])is not int or r['allowed'] not in (0,1) or type(r['revision'])is not int or not 0<r['revision']<2**53:raise ValueError('관전 저장 값 오류')
  seen.add(key)
 return rows

def put(db,sid,rows,cities):
 payload=json.dumps(validate(rows,cities),sort_keys=True,separators=(',',':'))
 db.execute('INSERT INTO joint_observe VALUES(?,?,?)',(sid,payload,sha(payload.encode())))

def capture(db,sid):
 put(db,sid,state(db),[r[0] for r in db.execute('SELECT id FROM city')])

def read(db,sid,cities):
 if not db.execute("SELECT 1 FROM sqlite_master WHERE name='joint_observe'").fetchone():return []
 row=db.execute('SELECT payload,hash FROM joint_observe WHERE id=?',(sid,)).fetchone()
 if not row:return [] # Saves created before this feature retain old behavior.
 if sha(row[0].encode())!=row[1]:raise ValueError('관전 저장 해시 오류')
 return validate(json.loads(row[0]),cities)

def restore(db,rows,cities):
 initialize(db);validate(rows,cities)
 db.execute('DELETE FROM observe_permission')
 db.executemany('INSERT INTO observe_permission VALUES(?,?,?,?)',[(r['owner'],r['viewer'],r['allowed'],r['revision']) for r in rows])
