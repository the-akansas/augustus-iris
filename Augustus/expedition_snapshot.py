from windows_paths import sqlite_readonly_uri
"""Versioned military checkpoint attached to the existing joint-save boundary.
No SQL/schema/credentials from a peer are executed. SAVs travel as normal parts.
"""
import base64,json,sqlite3
from pathlib import Path
from contextlib import closing
from expedition_state import encode,identifier,integer,ExpeditionStore
from expedition_commit import PairedExpeditions
from coordinator import sha,receipt

COLUMNS={
 'army_install':('id','city','revision','hash','ticks','state'),
 'metadata':('id','version','cities','epoch'),
 'army':('id','city','payload','reservation'),
 'expedition':('id','origin','destination','army_id','phase','revision','initial','current','losses'),
 'action':('id','fingerprint','receipt'),
 'native_army':('id','city','formation'),
 'paired_binding':('id','selection'),
 'paired_action':('id','fingerprint','receipt'),
 'city_snapshot':('id','revision','receipt','hash'),
}
LIMIT=4*1024*1024

def initialize(db):
 db.execute('CREATE TABLE IF NOT EXISTS joint_expedition(id INTEGER PRIMARY KEY,payload TEXT NOT NULL,hash TEXT NOT NULL)')
 db.execute('CREATE TABLE IF NOT EXISTS expedition_required(id INTEGER PRIMARY KEY CHECK(id=1))')
 if 'expedition_version' not in {r[1] for r in db.execute('PRAGMA table_info(joint_save)')}:db.execute('ALTER TABLE joint_save ADD COLUMN expedition_version INTEGER')

def parts(db,sid):return {r['city']:bytes(r['save']) for r in db.execute('SELECT city,save FROM joint_part WHERE id=?',(sid,))}

def validate(data,cities,saves):
 if data is None:return
 if not isinstance(data,dict) or set(data)!={'version','tables'} or data['version'] not in (1,2) or set(data['tables'])!=(set(COLUMNS)-({'army_install'} if data['version']==1 else set())):raise ValueError('military checkpoint format')
 if len(encode(data).encode())>LIMIT:raise ValueError('military checkpoint too large')
 tables=data['tables']
 for table,columns in COLUMNS.items():
  rows=tables.get(table,[])
  if not isinstance(rows,list) or len(rows)>10000:raise ValueError('military row count')
  seen=set()
  for row in rows:
   if not isinstance(row,dict) or set(row)!=set(columns):raise ValueError('military row shape')
   if any(type(v) not in (str,int,type(None)) for v in row.values()):raise ValueError('military scalar')
   key=row['id']
   if key in seen:raise ValueError('military duplicate row')
   seen.add(key)
   if table!='metadata':identifier(key)
 if len(tables['metadata'])!=1:raise ValueError('military metadata')
 meta=tables['metadata'][0]
 if meta['id']!=1 or meta['version']!=2 or json.loads(meta['cities'])!=sorted(cities):raise ValueError('military city binding')
 integer(meta['epoch'],1,2**53-2)
 city_rows={r['id']:r for r in tables['city_snapshot']}
 for c,r in city_rows.items():
  if c not in cities or c not in saves or sha(saves[c])!=r['hash']:raise ValueError('military SAV boundary mismatch')
  integer(r['revision'],0,2**53-1);receipt(base64.b64decode(r['receipt'],validate=True))
 armies={r['id']:r for r in tables['native_army']}
 for r in armies.values():
  if r['city'] not in city_rows:raise ValueError('native army city')
  integer(r['formation'],1,2**31-1)
 exp={r['id']:r for r in tables['expedition']};bindings={r['id']:r for r in tables['paired_binding']}
 for e in exp.values():
  if e['army_id'] not in armies or e['origin']!=armies[e['army_id']]['city'] or e['destination'] not in cities:raise ValueError('expedition identity')
  if e['phase'] not in ('reserved','cancelled','outbound','stationed','returning','returned','lost'):raise ValueError('unsupported native expedition phase')
  integer(e['revision'],1,2**53-1)
  if e['phase'] in ('outbound','stationed','returning','returned','lost') and e['id'] not in bindings:raise ValueError('missing native departure')
 for r in bindings.values():
  if r['id'] not in exp:raise ValueError('orphan departure')
  selection=json.loads(r['selection']);e=exp[r['id']]
  if selection['native']['formation_id']!=armies[e['army_id']]['formation']:raise ValueError('native departure mismatch')
  if 'visitor' not in selection:
   if encode(selection['manifest'])!=e['current']:raise ValueError('native departure mismatch')
  else:
   visitor=selection['visitor'];integer(visitor['role'],1,2);integer(visitor['formation'],1,2**31-1)
   if encode(selection['manifest'])!=e['initial']:raise ValueError('visitor original manifest')
   if len(visitor['identities'])!=selection['manifest']['soldiers'] or len({tuple(v) for v in visitor['identities']})!=len(visitor['identities']):raise ValueError('visitor identities')
   for a,b in visitor['identities']:integer(a,1,2**31-1);integer(b,0,65535)
   if e['phase'] in ('returned','lost'):
    returned=selection.get('return_native',{});current=json.loads(e['current'])
    if len(returned.get('soldiers',[]))!=current['soldiers'] or returned.get('morale')!=current['morale'] or sum(s['damage'] for s in returned['soldiers'])!=current['total_damage']:raise ValueError('survivor mismatch')
  integer(selection['native']['vacancy_token'],1,2**32-1)
 pending=[r for r in tables.get('army_install',[]) if r['state']=='pending']
 if len(pending)>2 or len({r['city'] for r in pending})!=len(pending) or len({r['ticks'] for r in pending})>1:raise ValueError('incompatible pending army installs')
 for r in tables.get('army_install',[]):
  if r['city'] not in city_rows or r['state'] not in ('pending','installed','retained'):raise ValueError('army installation binding')
  integer(r['ticks'],0,2**53-1);integer(r['revision'],1,2**53-1)
  if r['state']=='pending' and (r['revision']!=city_rows[r['city']]['revision'] or r['hash']!=city_rows[r['city']]['hash']):raise ValueError('pending army SAV mismatch')
 # Reuse the actual ledger invariant checker without accepting external SQL.
 with closing(sqlite3.connect(':memory:')) as check:
  check.row_factory=sqlite3.Row
  for table in ('army','expedition'):
   check.execute('CREATE TABLE '+table+'('+','.join(COLUMNS[table])+')')
   for r in tables[table]:check.execute('INSERT INTO '+table+' VALUES('+','.join('?' for _ in r)+')',tuple(r[k] for k in COLUMNS[table]))
  ExpeditionStore._check(None,check)
 for table in ('action','paired_action'):
  for r in tables[table]:
   if len(r['fingerprint'])!=64 or any(c not in '0123456789abcdef' for c in r['fingerprint']):raise ValueError('action fingerprint')
   if not isinstance(json.loads(r['receipt']),dict):raise ValueError('action receipt')

def inspection_plan(room,db,sid):
 """Called under the room lock. Copy bytes, never pass connections to workers."""
 path=Path(room.coordinator.path).parent/'expedition.sqlite'
 if not path.is_file():return (sid,None,()),[]
 with closing(sqlite3.connect(path)) as military:
  military.row_factory=sqlite3.Row
  epoch=military.execute('SELECT epoch FROM metadata').fetchone()[0]
  rows=military.execute('SELECT * FROM city_snapshot ORDER BY id').fetchall()
 jobs=[];keys=[]
 for row in rows:
  part=db.execute('SELECT save,hash FROM joint_part WHERE id=? AND city=?',(sid,row['id'])).fetchone()
  rec=db.execute('SELECT receipt FROM city WHERE id=?',(row['id'],)).fetchone()
  if not part or not rec or sha(part['save'])!=part['hash']:raise ValueError('military checkpoint part missing or corrupt')
  keys.append((row['id'],row['revision'],row['hash'],sha(row['receipt']),part['hash'],sha(rec[0])))
  if part['hash']!=row['hash'] or bytes(rec[0])!=bytes(row['receipt']):
   jobs.append((row['id'],bytes(part['save']),bytes(rec[0]),bytes(row['sav']),bytes(row['receipt'])))
 return (sid,epoch,tuple(keys)),jobs

def prepare_capture(room,db,sid):
 """Poll one bounded background inspection job; it cannot publish or mutate DBs.

 Cancellation/new saves/epoch or revision changes invalidate the fingerprint.
 Old work may finish but cannot be committed by a new request.
 """
 from threading import Thread,Event
 from expedition_adapter import inspect_bytes
 key,jobs=inspection_plan(room,db,sid)
 task=getattr(room,'_military_inspection',None)
 if task and not task['done'].is_set():return None
 if task and task['key']==key:
  if task.get('error'):raise RuntimeError('military checkpoint inspection failed') from task['error']
  return task['views']
 if not jobs:
  room._military_inspection=None
  return {}
 task={'key':key,'done':Event(),'views':{}}
 scratch=Path(room.coordinator.path).parent/'expedition-drafts'
 def inspect():
  try:
   for city,sav,rec,old,oldrec in jobs:
    task['views'][city]=(inspect_bytes(sav,rec,scratch),inspect_bytes(old,oldrec,scratch))
  except BaseException as error:task['error']=error
  finally:task['done'].set()
 room._military_inspection=task
 Thread(target=inspect,name='military-checkpoint',daemon=True).start()
 return None

def capture(room,db,sid,prepared=None):
 path=Path(room.coordinator.path).parent/'expedition.sqlite'
 if not path.is_file():
  if db.execute('SELECT 1 FROM expedition_required').fetchone():raise ValueError('required military ledger missing')
  return
 # A live city advances independently of the detached army. Reconcile its
 # actual collected save before binding this joint checkpoint. No old SAV is
 # installed into the game. If publication fails, retrying identical bytes is
 # idempotent; recovery still uses only the last COMPLETE paired checkpoint.
 paired=PairedExpeditions(path,room.coordinator.scenario['cities'],path.parent/'expedition-drafts')
 with paired.store.connection() as military:
  epoch=military.execute('SELECT epoch FROM metadata').fetchone()[0]
  current=[dict(r) for r in military.execute('SELECT * FROM city_snapshot')]
 for row in current:
  part=db.execute('SELECT save,hash FROM joint_part WHERE id=? AND city=?',(sid,row['id'])).fetchone()
  rec=db.execute('SELECT receipt FROM city WHERE id=?',(row['id'],)).fetchone()
  if not part or not rec or sha(part['save'])!=part['hash']:raise ValueError('military checkpoint part missing or corrupt')
  if part['hash']!=row['hash'] or bytes(rec[0])!=bytes(row['receipt']):
   if prepared is None:
    from expedition_adapter import inspect_bytes
    view=inspect_bytes(bytes(part['save']),bytes(rec[0]),paired.scratch)
    prior=inspect_bytes(bytes(row['sav']),bytes(row['receipt']),paired.scratch)
   else:
    if row['id'] not in prepared:raise ValueError('stale checkpoint preparation')
    view,prior=prepared[row['id']]
   if view['source']!=bytes(part['save']) or view['receipt']!=bytes(rec[0]):raise ValueError('stale checkpoint preparation')
   paired.adopt_inspected(row['id'],view,epoch,row['revision'],prior=prior)
 with closing(sqlite3.connect(sqlite_readonly_uri(path),uri=True)) as src:
  src.row_factory=sqlite3.Row;src.execute('BEGIN')
  tables={name:([dict(r) for r in src.execute('SELECT '+','.join(cols)+' FROM '+name+' ORDER BY id')] if src.execute('SELECT 1 FROM sqlite_master WHERE name=?',(name,)).fetchone() else []) for name,cols in COLUMNS.items()}
  for r in tables['city_snapshot']:r['receipt']=base64.b64encode(r['receipt']).decode('ascii')
 data={'version':2,'tables':tables}
 put(db,sid,data,room.coordinator.scenario['cities'])
 return data

def notify_expired(room,db,data):
 if not data:return
 for action in data['tables']['action']:
  if action['id'].startswith('expire-'):
   event=json.loads(action['receipt'])
   room.system_chat(db,'군단의 상태가 변경되어 파견 준비를 취소했습니다. 다시 선택하세요.',
                    targets=(event['origin'],event['origin']),key='army:'+action['id'])

def check_receipts(db,data):
 for r in data['tables']['city_snapshot']:
  stored=db.execute('SELECT receipt FROM city WHERE id=?',(r['id'],)).fetchone()
  if not stored or bytes(stored[0])!=base64.b64decode(r['receipt'],validate=True):raise ValueError('military receipt boundary mismatch')

def put(db,sid,data,cities):
 if data is None:return
 validate(data,cities,parts(db,sid));check_receipts(db,data);payload=encode(data)
 db.execute('INSERT INTO joint_expedition VALUES(?,?,?)',(sid,payload,sha(payload.encode())))
 db.execute('UPDATE joint_save SET expedition_version=? WHERE id=?',(data['version'],sid))
 db.execute('INSERT OR IGNORE INTO expedition_required VALUES(1)')

def read(db,sid,cities):
 if 'expedition_version' not in {r[1] for r in db.execute('PRAGMA table_info(joint_save)')}:return None
 version=db.execute('SELECT expedition_version FROM joint_save WHERE id=?',(sid,)).fetchone()[0]
 if version is None:
  if db.execute("SELECT 1 FROM sqlite_master WHERE name='joint_expedition'").fetchone() and db.execute('SELECT 1 FROM joint_expedition WHERE id=?',(sid,)).fetchone():raise ValueError('military version marker missing')
  return None
 if version not in (1,2):raise ValueError('unsupported military checkpoint')
 row=db.execute('SELECT payload,hash FROM joint_expedition WHERE id=?',(sid,)).fetchone()
 if not row or sha(row['payload'].encode())!=row['hash']:raise ValueError('military checkpoint missing or corrupt')
 data=json.loads(row['payload'])
 if data.get('version')!=version:raise ValueError('military version marker mismatch')
 validate(data,cities,parts(db,sid));check_receipts(db,data);return data

def restore(path,data,cities,saves):
 if data is None:return
 validate(data,cities,{c:v[0] for c,v in saves.items()})
 for r in data['tables']['city_snapshot']:
  if saves[r['id']][1]!=base64.b64decode(r['receipt'],validate=True):raise ValueError('military restore receipt mismatch')
 path=Path(path)
 if path.exists():raise FileExistsError(path)
 # New room is not published until this completes. Never rewrite original DB.
 paired=PairedExpeditions(path,cities,path.parent/'expedition-drafts')
 try:
  with paired.store.connection() as db:
   db.execute('BEGIN IMMEDIATE');db.execute('DELETE FROM metadata')
   for name,columns in COLUMNS.items():
    for original in data['tables'].get(name,[]):
     r=dict(original)
     if name=='metadata':r['epoch']+=1
     if name=='city_snapshot':
      r['sav']=saves[r['id']][0];r['receipt']=base64.b64decode(r['receipt'],validate=True)
     cols=tuple(r)
     db.execute('INSERT INTO '+name+'('+','.join(cols)+') VALUES('+','.join('?' for _ in cols)+')',tuple(r[k] for k in cols))
   paired.store._check(db)
 except BaseException:
  # A partial staging room must never be advertised as resumable.
  raise
 return paired
