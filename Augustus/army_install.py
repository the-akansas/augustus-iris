"""Authenticated room bridge for durable native army installation acknowledgements."""
from pathlib import Path
from contextlib import closing
import sqlite3,base64
from coordinator import sha
from expedition_commit import PairedExpeditions

def path(room):return Path(room.coordinator.path).parent/'expedition.sqlite'
def pending(room,city=None):
 p=path(room)
 if not p.is_file():return None
 with closing(sqlite3.connect(p)) as db:
  db.row_factory=sqlite3.Row
  if not db.execute("SELECT 1 FROM sqlite_master WHERE name='army_install'").fetchone():return None
  sql="SELECT * FROM army_install WHERE state='pending'";params=()
  if city is not None:sql+=' AND city=?';params=(city,)
  row=db.execute(sql,params).fetchone();return dict(row) if row else None

def token(room,epoch,row):return sha((room.coordinator.session+':'+str(epoch)+':'+row['id']+':'+row['hash']).encode())

def frozen_part(room,db,city):
 import live_trade,joint_save
 if live_trade.busy(db) or joint_save.pending(db) or pending(room):raise ValueError('save busy')
 latest=db.execute("SELECT id,ticks FROM joint_save WHERE state='complete' ORDER BY id DESC LIMIT 1").fetchone()
 if not latest or latest['ticks']!=room.grant or room.progress.get(city,(-1,0))[0]!=room.grant:raise ValueError('fresh frozen checkpoint required')
 part=db.execute('SELECT save,hash FROM joint_part WHERE id=? AND city=?',(latest['id'],city)).fetchone()
 receipt=db.execute('SELECT receipt FROM city WHERE id=?',(city,)).fetchone()
 if not part or not receipt or sha(part['save'])!=part['hash']:raise ValueError('checkpoint missing or corrupt')
 return bytes(part['save']),bytes(receipt[0])
def request(room,db,city,r):
 p=path(room)
 if r['op'] in ('army_list','army_select'):
  from expedition_adapter import inspect_bytes,select_army
  from expedition_state import integer
  import uuid
  sav,receipt=frozen_part(room,db,city)
  # Inspection is read-only. Opening a selection list must not activate a ledger.
  scratch=p.parent/'expedition-drafts'
  epoch=1;revision=None;active=set()
  if p.exists():
   with closing(sqlite3.connect(p)) as military:
    epoch=military.execute('SELECT epoch FROM metadata').fetchone()[0]
    row=military.execute('SELECT revision FROM city_snapshot WHERE id=?',(city,)).fetchone();revision=row[0] if row else None
    active={v[0] for v in military.execute("SELECT n.formation FROM native_army n JOIN expedition e ON e.army_id=n.id WHERE n.city=? AND e.phase IN ('reserved','outbound','stationed','returning')",(city,))}
  if r['op']=='army_list':
   view=inspect_bytes(sav,receipt,scratch);result=[]
   for row in view['report']['legions']:
    try:select_army(view,row['formation_id'],city,'preview');available=True
    except ValueError:available=False
    result.append(dict(formation=row['formation_id'],fort=row['fort_id'],unit_type=row['unit_type'],soldiers=len(row['soldiers']),morale=row['morale'],available=available and row['formation_id'] not in active))
   return dict(epoch=epoch,city_revision=revision,save_hash=sha(sav),legions=result)
  integer(r.get('formation'),1,2**31-1)
  integer(r.get('epoch'),1,2**53-2)
  if r.get('city_revision') is not None:integer(r['city_revision'],0,2**53-1)
  if r.get('epoch')!=epoch or r.get('city_revision')!=revision or r.get('save_hash')!=sha(sav):raise ValueError('stale army selection')
  paired=PairedExpeditions(p,room.coordinator.scenario['cities'],p.parent/'expedition-drafts')
  return paired.adopt_inspected(city,inspect_bytes(sav,receipt,scratch),epoch,revision,r['formation'])
 if not p.is_file():
  if r['op']=='army_install_status':return None
  raise ValueError('military ledger unavailable')
 paired=PairedExpeditions(p,room.coordinator.scenario['cities'],p.parent/'expedition-drafts')
 if r['op'] in ('army_install_status','army_install_ack'):
  with paired.store.connection() as military:
   military.execute('BEGIN IMMEDIATE')
   epoch=military.execute('SELECT epoch FROM metadata').fetchone()[0]
   row=military.execute("SELECT * FROM army_install WHERE city=? ORDER BY revision DESC LIMIT 1",(city,)).fetchone()
   if r['op']=='army_install_ack':
    if not row or r.get('install_token')!=token(room,epoch,row) or r.get('hash')!=row['hash']:raise ValueError('stale army acknowledgement')
    military.execute("UPDATE army_install SET state='installed' WHERE id=?",(row['id'],));return {'installed':True}
   if not row or row['state']!='pending':return None
   current=military.execute('SELECT * FROM city_snapshot WHERE id=?',(city,)).fetchone()
   if current['revision']!=row['revision'] or sha(current['sav'])!=row['hash']:raise ValueError('army install snapshot mismatch')
   return dict(token=token(room,epoch,row),hash=row['hash'],ticks=row['ticks'],save=base64.b64encode(current['sav']).decode())
 if r['op']=='army_cancel':
  import joint_save
  if joint_save.pending(db):raise ValueError('save busy')
  return paired.apply(r.get('action_id'),city,r.get('epoch'),r.get('expedition'),r.get('revision'),r.get('city_revision'),'cancel')
 if r['op'] not in ('army_depart','army_home'):raise ValueError('army operation')
 with paired.store.connection() as military:
  old=military.execute("SELECT ticks FROM army_install WHERE id=?",(r.get("action_id"),)).fetchone()
 if old:
  return paired.apply(r.get("action_id"),city,r.get("epoch"),r.get("expedition"),r.get("revision"),r.get("city_revision"),
                      "depart" if r["op"]=="army_depart" else "home",install_ticks=old[0])
 import live_trade,joint_save
 if live_trade.busy(db) or joint_save.pending(db):raise ValueError('save busy')
 latest=db.execute("SELECT id,ticks FROM joint_save WHERE state='complete' ORDER BY id DESC LIMIT 1").fetchone()
 if not latest or latest['ticks']!=room.grant or room.progress.get(city,(-1,0))[0]!=room.grant:raise ValueError('fresh frozen checkpoint required')
 current=paired.snapshot(city);part=db.execute('SELECT hash FROM joint_part WHERE id=? AND city=?',(latest['id'],city)).fetchone()
 if not part or part[0]!=current['hash']:raise ValueError('military SAV boundary mismatch')
 return paired.apply(r.get('action_id'),city,r.get('epoch'),r.get('expedition'),r.get('revision'),r.get('city_revision'),
                     'depart' if r['op']=='army_depart' else 'home',install_ticks=room.grant)

def poll(bridge):
 import os
 value=bridge.client.call('army_install_status')
 if not value:return
 key=value['token']
 if len(key)!=64 or any(c not in '0123456789abcdef' for c in key):raise ValueError('army install token')
 data=base64.b64decode(value['save'],validate=True)
 if sha(data)!=value['hash']:raise ValueError('army install hash')
 ack=bridge.root/'army-installed.txt'
 if ack.exists() and ack.read_text().strip()==key:
  bridge.client.call('army_install_ack',install_token=key,hash=value['hash']);return
 target=bridge.root/('army-install-'+key+'.sav')
 if not target.exists() or sha(target.read_bytes())!=value['hash']:
  stage=target.with_suffix('.tmp');stage.write_bytes(data);os.replace(stage,target)
 marker=bridge.root/'army-install.txt';text=key+' '+str(value['ticks'])
 if not marker.exists() or marker.read_text()!=text:
  stage=marker.with_suffix('.tmp');stage.write_text(text);os.replace(stage,marker)


def expected(room,city):
 row=pending(room,city)
 if not row:return 'hold' if pending(room) else '-'
 with closing(sqlite3.connect(path(room))) as db:epoch=db.execute('SELECT epoch FROM metadata').fetchone()[0]
 return token(room,epoch,row)
