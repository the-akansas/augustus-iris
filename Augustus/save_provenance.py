"""Explicit snapshot ages for a remaining-player save; no fabricated peer progress."""
from coordinator import sha
import transport_snapshot

def unchanged_loaded_transport(db,snapshot,cities,active):
 """Allow a frozen cargo ledger, never a refund or a fabricated delivery.

 The same complete checkpoint owns both city SAVs and the external cargo.
 Offline cities retain exactly those SAV bytes; live partners must have
 acknowledged any published install before supplying their newer SAV.
 Called under Lobby.lock, as is the snapshot capture which follows it.
 """
 if not snapshot or snapshot.get('version',0)<2 or not snapshot.get('transfer'):return False
 import cargo_snapshot
 if not cargo_snapshot.cargo(bytes.fromhex(snapshot['cargo']))['remaining']:return False
 now=transport_snapshot.current(db);transport_snapshot.validate(now,cities)
 if now!=snapshot:return False
 t=db.execute('SELECT * FROM live_transfer WHERE id=?',(snapshot['transfer']['id'],)).fetchone()
 if not t or t['state'] not in ('committed','departing','travelling','returning','saving'):return False
 if t['state']=='saving':
  # A departed city cancels the collector. A live settlement must not race this save.
  base=db.execute('SELECT state FROM joint_save WHERE id=?',(t['base'],)).fetchone()
  if not base or base[0]!='cancelled':return False
 if t['state']=='committed':
  for city in (t['sender'],t['receiver']):
   if city in active and not db.execute('SELECT 1 FROM live_cargo_ack WHERE result=? AND city=?',(t['result'],city)).fetchone():return False
 return True

def initialize(db):
 db.execute('CREATE TABLE IF NOT EXISTS joint_provenance(id INTEGER,city TEXT,ticks INTEGER,source_id INTEGER,mode TEXT,PRIMARY KEY(id,city))')
 db.execute('CREATE TABLE IF NOT EXISTS origin_provenance(city TEXT PRIMARY KEY,ticks INTEGER)')
 db.execute('CREATE TABLE IF NOT EXISTS joint_trade_boundary(id INTEGER PRIMARY KEY,transfer_id INTEGER)')

def capture_boundary(db,sid):
 # Even a completed transfer after the baseline changed both cities. Retaining
 # the older peer would duplicate or lose funds/goods, so record the boundary.
 row=db.execute("SELECT max(id) FROM live_transfer WHERE state!='rejected'").fetchone()
 db.execute('INSERT OR REPLACE INTO joint_trade_boundary VALUES(?,?)',(sid,row[0] or 0))

def read(db,sid,cities):
 if not db.execute("SELECT 1 FROM sqlite_master WHERE name='joint_provenance'").fetchone():return []
 rows=[dict(r) for r in db.execute('SELECT city,ticks,source_id,mode FROM joint_provenance WHERE id=? ORDER BY city',(sid,))]
 if not rows:return []
 saved=db.execute('SELECT ticks FROM joint_save WHERE id=?',(sid,)).fetchone()
 if sorted(x['city'] for x in rows)!=sorted(cities):raise ValueError('snapshot provenance cities')
 for x in rows:
  if type(x['ticks'])!=int or not 0<=x['ticks']<=saved[0] or type(x['source_id'])!=int or x['source_id']<0 or x['mode'] not in ('current','retained'):raise ValueError('snapshot provenance')
 return rows

def retained_parts(room,db,active):
 cities=room.coordinator.scenario['cities']
 offline=set(cities)-set(active)
 saved=db.execute("SELECT id,ticks FROM joint_save WHERE state='complete' ORDER BY id DESC LIMIT 1").fetchone()
 boundary=db.execute('SELECT transfer_id FROM joint_trade_boundary WHERE id=?',(saved['id'],)).fetchone() if saved else None
 # A city whose player left stays at its retained checkpoint. Its trades after
 # that point were settled for the remaining cities (trade_post_ledger.abandon)
 # and are forgiven when it is restored (post_recovery.forgive); they no longer
 # block the remaining players' saves. Only an unsettled step of its own does.
 if db.execute("SELECT 1 FROM sqlite_master WHERE name='post_command'").fetchone() and offline:
  marks=','.join('?'*len(offline))
  if db.execute("SELECT 1 FROM post_command WHERE state='pending' AND city IN ("+marks+")",tuple(offline)).fetchone():raise ValueError('remaining save blocked by trade')
 # Older paired-save transfers (not on the post ledger) keep the strict rule.
 legacy=" AND id NOT IN (SELECT id FROM cash_transfer)" if db.execute("SELECT 1 FROM sqlite_master WHERE name='cash_transfer'").fetchone() else ''
 for t in db.execute("SELECT sender,receiver FROM live_transfer WHERE id>? AND state!='rejected'"+legacy,(boundary[0] if boundary else 0,)):
  if offline.intersection((t['sender'],t['receiver'])):raise ValueError('remaining save blocked by trade')
 ages={}
 if saved:
  tr=transport_snapshot.read(db,saved['id'],cities)
  moving=transport_snapshot.transfer_of(tr)
  if moving and offline.intersection((moving['sender'],moving['receiver'])):
   if not unchanged_loaded_transport(db,tr,cities,active):raise ValueError('remaining save blocked by trade')
  ages={x['city']:x['ticks'] for x in read(db,saved['id'],cities)}
 result=[]
 for city in cities:
  if city in active:continue
  if saved:
   row=db.execute('SELECT save,hash FROM joint_part WHERE id=? AND city=?',(saved['id'],city)).fetchone()
   if row is None or sha(row[0])!=row[1]:raise ValueError('retained snapshot hash')
   data,digest=row;tick=ages.get(city,saved['ticks']);source=saved['id']
  else:
   data=db.execute('SELECT save FROM city WHERE id=?',(city,)).fetchone()[0];digest=sha(data);source=0
   origin=db.execute('SELECT ticks FROM origin_provenance WHERE city=?',(city,)).fetchone();tick=origin[0] if origin else room.origin
  result.append((city,data,digest,tick,source))
 return result
