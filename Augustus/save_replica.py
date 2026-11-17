"""Replicate completed city pairs only; never export live credentials or SQL."""
import base64,json,os,uuid,shutil
from pathlib import Path
from contextlib import closing
from coordinator import Coordinator,blob,sha
import joint_save,transport_snapshot,save_provenance
import objectives
import expedition_snapshot
import throne_state
import room_options
import observe_permissions

def export(room,db,r):
 sid=r.get('id')
 if type(sid)!=int or sid<=0:raise ValueError('save id')
 saved=db.execute("SELECT * FROM joint_save WHERE id=? AND state='complete'",(sid,)).fetchone()
 if not saved:raise ValueError('save incomplete')
 if r['op']=='save_replica_meta':
  project=json.loads((Path(room.coordinator.path).parent/'scenario-project.json').read_text(encoding='utf-8'))
  from restore_expansion import original_project
  original=original_project(Path(room.coordinator.path).parent,project)
  import imperial_progress
  return dict(progress=imperial_progress.read(db,sid,room.coordinator.scenario),throne=throne_state.sealed_save(db,sid,room.coordinator.scenario,saved['ticks']),observe_permissions=observe_permissions.read(db,sid,room.coordinator.scenario['cities']),room_options=room_options.read(db,sid),expedition_version=saved['expedition_version'] if 'expedition_version' in saved.keys() else None,kind=saved['kind'] if 'kind' in saved.keys() else None,expedition=expedition_snapshot.read(db,sid,room.coordinator.scenario['cities']),original_project=original,objectives=objectives.read(db,sid,room.coordinator.scenario),provenance=save_provenance.read(db,sid,room.coordinator.scenario['cities']),id=sid,ticks=saved['ticks'],speed=saved['speed'],binding=room.coordinator.scenario,project=project,transport=transport_snapshot.read(db,sid,room.coordinator.scenario['cities']))
 city=r.get('part')
 if city not in room.coordinator.scenario['cities']:raise ValueError('city')
 row=db.execute('SELECT save,hash FROM joint_part WHERE id=? AND city=?',(sid,city)).fetchone()
 rec=db.execute('SELECT receipt FROM city WHERE id=?',(city,)).fetchone()[0]
 return dict(save=base64.b64encode(row['save']).decode(),hash=row['hash'],receipt=base64.b64encode(rec).decode())

def download(bridge,sid,check=lambda:None):
 check()
 root=bridge.root.parent;final=root/('host-backup-'+bridge.config['session']+'-'+str(sid))
 meta=bridge.client.call('save_replica_meta',id=sid)
 check()
 if meta['id']!=sid:raise ValueError('save mismatch')
 if final.exists():
  from restore_pair import read_pair
  read_pair(final/'room.sqlite',meta['binding'],sid)
  check()
  return
 stage=root/('backup-preparing-'+uuid.uuid4().hex);stage.mkdir()
 try:
  co=Coordinator(stage/'room.sqlite',uuid.uuid4().hex,meta['binding'])
  parts=[]
  for city in meta['binding']['cities']:
   check()
   part=bridge.client.call('save_replica_part',id=sid,part=city)
   check()
   data=blob(part['save'])
   if sha(data)!=part['hash']:raise ValueError('replica hash mismatch')
   rec=base64.b64decode(part['receipt'],validate=True);co.provision(city,data,rec);parts.append((sid,city,data,part['hash']))
  with closing(co.connect()) as db:
   joint_save.initialize(db)
   tr=meta['transport'];version=tr['version'] if tr else None
   db.execute("INSERT INTO joint_save(id,request,ticks,state,speed,transport_version) VALUES(?,?,?,'complete',?,?)",(sid,uuid.uuid4().hex,meta['ticks'],meta['speed'],version))
   room_options.put(db,sid,meta.get('room_options'))
   throne_state.put(db,sid,meta.get('throne'),meta['binding'],meta['ticks'])
   import imperial_progress;imperial_progress.put(db,sid,meta.get('progress'),meta['binding'])
   observe_permissions.put(db,sid,meta.get('observe_permissions',[]),meta['binding']['cities'])
   db.executemany('INSERT INTO joint_part VALUES(?,?,?,?)',parts)
   if meta.get('expedition_version') not in (None,1,2) or (meta.get('expedition_version') in (1,2) and not meta.get('expedition')):raise ValueError('military replica incomplete')
   expedition_snapshot.put(db,sid,meta.get('expedition'),meta['binding']['cities'])
   goal=meta.get('objectives');objectives.validate_snapshot(goal,meta['binding'],meta['ticks'])
   if goal:
    payload=objectives.encode(goal)
    db.execute('INSERT INTO joint_objectives VALUES(?,?,?)',(sid,payload,sha(payload.encode())))
    db.execute('UPDATE joint_save SET objective_version=? WHERE id=?',(goal['version'],sid))
   for item in meta.get('provenance',[]):db.execute('INSERT INTO joint_provenance VALUES(?,?,?,?,?)',(sid,item['city'],item['ticks'],item['source_id'],item['mode']))
   if tr:
    transport_snapshot.validate(tr,meta['binding']['cities']);payload=json.dumps(tr,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    db.execute('INSERT INTO joint_transport VALUES(?,?,?)',(sid,payload,sha(payload.encode())))
   db.commit()
  (stage/'scenario-project.json').write_text(json.dumps(meta['project'],ensure_ascii=False),encoding='utf-8')
  if meta.get('kind') in ('auto','manual'):(stage/'save-kind.txt').write_text(meta['kind'],encoding='ascii')   # prune(): manual copies stay
  if meta.get('original_project'):
   (stage/'scenario-original.json').write_text(json.dumps(meta['original_project'],ensure_ascii=False),encoding='utf-8')
   from restore_expansion import original_project
   original_project(stage,meta['project'])
  from restore_pair import read_pair
  read_pair(stage/'room.sqlite',meta['binding'],sid)
  check()
  stage.rename(final)
 except Exception:
  # Preserve diagnostic staging, but never list it as a completed restore point.
  raise
