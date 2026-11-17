"""Paired native visitor transactions. Called only on a frozen private ledger.

The caller must publish this ledger and install both city snapshots before time
advances. Unit IDs are never reused across cities; arrival identities are bound
to their native generation and mapped back to the original soldier record.
"""
import copy,json,uuid
from pathlib import Path
from tempfile import TemporaryDirectory
from expedition_state import identifier,integer,encode
from expedition_adapter import inspect_bytes,select_army,sha
from expedition_draft import prepare_departure,transform
from city_client import Engine

def visit_transform(sav,receipt,native,role,scratch,remove=False):
 with TemporaryDirectory(prefix='visitor-',dir=scratch) as directory:
  root=Path(directory);source=root/'input';source.mkdir()
  (source/'city.sav').write_bytes(sav);(source/'receipt.bin').write_bytes(receipt)
  values=[native['vacancy_token'],role,native['unit_type'],native['morale'],native['trained'],native['months_from_home'],native['food_modifier'],len(native['soldiers'])]
  text='VIS1 '+' '.join(map(str,values))+'\n'
  text+=''.join(f"{s['damage']} {s['name']}\n" for s in native['soldiers'])
  (source/'visitor.txt').write_text(text,encoding='ascii')
  sav,rec=Engine().run('visit-remove' if remove else 'visit-arrive',source,root/'output')
  report=json.loads((root/'output/legions.json').read_text())
 return dict(save=sav,receipt=rec,hash=sha(sav),report=report)

def transfer(paired,action,actor,epoch,origin_revision,destination_revision,*,destination,formation=None,expedition=None,role=1,ticks=0,expected=None):
 """One SQLite transaction: both SAVs, identity mapping, phases, ACK queue.

 action replay is checked before the revisions, but after the room epoch.
 Client supplied casualty counts and survivor records are never accepted.
 """
 for value in (action,actor,destination):identifier(value)
 for value in (epoch,origin_revision,destination_revision,ticks):integer(value,0,2**53-1)
 if destination==actor or destination not in paired.store.cities:raise ValueError('destination')
 if role not in (1,2):raise ValueError('visitor role')
 if expedition is not None:identifier(expedition)
 else:integer(formation,1,2**31-1)
 fingerprint=sha(encode([actor,destination,origin_revision,destination_revision,formation,expedition,role,ticks,expected]).encode())
 with paired.store.connection() as db:
  db.execute('BEGIN IMMEDIATE')
  if db.execute('SELECT epoch FROM metadata').fetchone()[0]!=epoch:raise ValueError('stale epoch')
  old=db.execute('SELECT * FROM paired_action WHERE id=?',(action,)).fetchone()
  if old:
   if old['fingerprint']!=fingerprint:raise ValueError('conflicting paired replay')
   return json.loads(old['receipt'])
  if db.execute("SELECT 1 FROM army_install WHERE state='pending'").fetchone():raise ValueError('army install pending')
  source=db.execute('SELECT * FROM city_snapshot WHERE id=?',(actor,)).fetchone()
  target=db.execute('SELECT * FROM city_snapshot WHERE id=?',(destination,)).fetchone()
  if not source or not target or source['revision']!=origin_revision or target['revision']!=destination_revision:raise ValueError('stale city snapshot')
  remote=inspect_bytes(bytes(target['sav']),bytes(target['receipt']),paired.scratch)
  def phase(suffix,who,eid,revision,op,**kwargs):
   return paired.store._apply_in_transaction(db,action+'-'+suffix,who,epoch,eid,revision,op,**kwargs)
  if expedition is None:
   if any(m.get('visitor_role') for m in remote['report']['legions']):raise ValueError('destination already has visiting army')
   view=inspect_bytes(bytes(source['sav']),bytes(source['receipt']),paired.scratch)
   native=db.execute('SELECT id FROM native_army WHERE city=? AND formation=?',(actor,formation)).fetchone()
   army=native[0] if native else 'army-'+uuid.uuid4().hex
   if db.execute("SELECT 1 FROM expedition WHERE army_id=? AND phase IN ('reserved','outbound','stationed','returning')",(army,)).fetchone():raise ValueError('army already active')
   choice=select_army(view,formation,actor,army)
   if expected is not None:
    actual=dict(fort=choice['native']['fort_id'],unit=choice['native']['unit_type'],identities=[[v['local_id'],v['generation']] for v in choice['native']['soldiers']])
    if actual!=expected:raise ValueError('선택한 군단의 병력이 바뀌었습니다. 다시 선택하세요.')
   db.execute('INSERT OR REPLACE INTO army VALUES(?,?,?,NULL)',(army,actor,encode(choice['manifest'])))
   db.execute('INSERT OR REPLACE INTO army_source VALUES(?,?,?,?)',(army,view['source'],view['source_hash'],encode(choice)))
   if not native:db.execute('INSERT INTO native_army VALUES(?,?,?)',(army,actor,formation))
   expedition='exp-'+uuid.uuid4().hex
   phase('reserve',actor,expedition,0,'reserve',army_id=army,destination=destination)
   departure=prepare_departure(view,choice,paired.scratch)
   choice=departure['selection'];arrived=visit_transform(target['sav'],target['receipt'],choice['native'],role,paired.scratch)
   visitor=next(m for m in arrived['report']['legions'] if m['mp_expedition_id']==choice['native']['vacancy_token'] and m.get('visitor_role')==role)
   if len(visitor['soldiers'])!=len(choice['native']['soldiers']):raise ValueError('arrival count mismatch')
   choice['visitor']=dict(role=role,formation=visitor['formation_id'],identities=[[s['local_id'],s['generation']] for s in visitor['soldiers']])
   db.execute('INSERT INTO paired_binding VALUES(?,?)',(expedition,encode(choice)))
   phase('depart',actor,expedition,1,'depart')
   event=phase('arrive',destination,expedition,2,'arrive')
   updates=[(actor,departure),(destination,arrived)]
  else:
   event=db.execute('SELECT * FROM expedition WHERE id=?',(expedition,)).fetchone()
   if not event or event['origin']!=actor or event['destination']!=destination or event['phase']!='stationed':raise ValueError('not owner or not stationed')
   choice=json.loads(db.execute('SELECT selection FROM paired_binding WHERE id=?',(expedition,)).fetchone()[0])
   bound=choice.get('visitor')
   if not bound or bound['role']!=role:raise ValueError('visitor binding')
   native=choice['native'];matches=[m for m in remote['report']['legions'] if m['mp_expedition_id']==native['vacancy_token'] and m.get('visitor_role')==role]
   if len(matches)!=1 or matches[0]['formation_id']!=bound['formation']:raise ValueError('visitor identity changed')
   visitor=matches[0];identities={tuple(key):i for i,key in enumerate(bound['identities'])};survivors=[]
   for s in visitor['soldiers']:
    key=(s['local_id'],s['generation'])
    if key not in identities or s['type']!=native['unit_type']:raise ValueError('unbound visitor soldier')
    original=copy.deepcopy(native['soldiers'][identities.pop(key)]);original['damage']=s['damage'];survivors.append(original)
   returned=copy.deepcopy(native);returned['soldiers']=survivors;returned['morale']=visitor['morale']
   # Native surviving soldiers determine losses; no synthetic combat roll.
   event=phase('battle',destination,expedition,event['revision'],'battle',soldiers=len(survivors),morale=visitor['morale'],total_damage=sum(s['damage'] for s in survivors))
   removed=visit_transform(target['sav'],target['receipt'],native,role,paired.scratch,True)
   home=transform(source['sav'],source['receipt'],returned,paired.scratch,'expedition-restore')
   if survivors:
    event=phase('recall',actor,expedition,event['revision'],'recall')
    event=phase('home',actor,expedition,event['revision'],'home')
   choice['return_native']=returned
   db.execute('UPDATE paired_binding SET selection=? WHERE id=?',(encode(choice),expedition))
   updates=[(actor,home),(destination,removed)]
  paired._checkpoint('after_native')
  for city,draft in updates:
   db.execute('UPDATE city_snapshot SET revision=revision+1,sav=?,receipt=?,hash=? WHERE id=?',(draft['save'],draft['receipt'],draft['hash'],city))
   current=db.execute('SELECT revision,hash FROM city_snapshot WHERE id=?',(city,)).fetchone()
   db.execute("INSERT INTO army_install VALUES(?,?,?,?,?,'pending')",(action+'-'+city,city,current['revision'],current['hash'],ticks))
  paired._checkpoint('after_sav')
  result=dict(expedition=event,origin=actor,destination=destination)
  db.execute('INSERT INTO paired_action VALUES(?,?,?)',(action,fingerprint,encode(result)))
  paired._checkpoint('after_receipt')
  return result
