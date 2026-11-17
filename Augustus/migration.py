"""Two-player checkpoint succession, with the old authority fenced on partition.

Only the designated guest with an acknowledged, validated replica can succeed.
No live simulation state is inferred from silence. Recovery creates a new session.
"""
import json,uuid
from contextlib import closing
from pathlib import Path
from coordinator import sha

def initialize(db):
 db.execute('CREATE TABLE IF NOT EXISTS succession(city TEXT PRIMARY KEY,save_id INTEGER)')
 db.execute('CREATE TABLE IF NOT EXISTS authority_fenced(value INTEGER)')
 import recovery_group
 recovery_group.initialize(db)

def acknowledge(room,db,city,sid):
 rows=db.execute('SELECT city FROM lobby_invite ORDER BY rowid').fetchall()
 if len(rows)<2 or rows[0][0]==city:return dict(armed=False)
 saved=db.execute("SELECT id,state FROM joint_save WHERE id=?",(sid,)).fetchone()
 # A copy of a save the host has since dropped (one save per game, joint_save.prune): not armed, no error; the
 # guest's next copy is of the newest save (2026-11-15: the refusal aborted the guest's round and showed an error).
 if saved and saved[1]=='pruned':return dict(armed=False)
 if not saved or saved[1]!='complete':raise ValueError('save incomplete')
 if city not in room.active_cities(db):return dict(armed=False)
 # Race for the Throne: a complete save is used for a host change only when every player whose private record was
 # sealed fresh in it has confirmed holding its own opening (throne_state.custody). Until then the previous such save
 # stays the succession point; nothing is rolled back silently and no older save is chosen here.
 import throne_state
 hold=throne_state.custody(db,room.coordinator.scenario,sid)
 if not hold['ready']:
  prior=db.execute('SELECT save_id FROM succession WHERE city=?',(city,)).fetchone()
  # armed=False: the caller keeps the save it is already armed with (game_bridge never moves to a refused one)
  return dict(armed=False,city=city,save_id=sid,kept=prior[0] if prior else None,waiting='throne-custody',waiting_count=hold['waiting'])
 db.execute('INSERT INTO succession VALUES(?,?) ON CONFLICT(city) DO UPDATE SET save_id=max(save_id,excluded.save_id)',(city,sid));db.commit()
 if len(rows)>2:
  import recovery_group
  ready=recovery_group.plan(room,db,city,private=True)
  return dict(armed=bool(ready),city=city,save_id=sid)
 return dict(armed=True,city=city,save_id=sid)

def fence(room,db):
 db.execute('INSERT INTO authority_fenced VALUES(1)')
 db.execute("UPDATE joint_save SET state='cancelled' WHERE state='collecting'");db.commit()
 room.system_chat(db,'연결이 끊겨 기존 방장의 진행 권한을 중단했습니다. 지정된 참가자가 저장본에서 이어받습니다.',key='authority-fenced')

def baseline(room):
 """The initial/restored pair is a real recovery point even before first autosave."""
 import transport_snapshot,save_provenance
 with closing(room.coordinator.connect()) as db:
  import room_options
  options=room_options.state(db)
  if not options['initialized'] or not options['locked']:return
  sid=db.execute("INSERT INTO joint_save(request,ticks,state,speed) VALUES(?,?,'complete',?)",(uuid.uuid4().hex,room.origin,db.execute('SELECT value FROM room_speed').fetchone()[0])).lastrowid
  room_options.capture(db,sid)
  import throne_state
  throne_state.capture(db,sid,room.coordinator.scenario,room.origin)
  import observe_permissions
  observe_permissions.capture(db,sid)
  for r in db.execute('SELECT id,save FROM city').fetchall():db.execute('INSERT INTO joint_part VALUES(?,?,?,?)',(sid,r['id'],r['save'],sha(r['save'])))
  ages={r['city']:r['ticks'] for r in db.execute('SELECT city,ticks FROM origin_provenance')}
  if ages:
   for city in room.coordinator.scenario['cities']:
    tick=ages.get(city,room.origin)
    db.execute('INSERT INTO joint_provenance VALUES(?,?,?,?,?)',(sid,city,tick,0,'retained' if tick<room.origin else 'current'))
  import expedition_snapshot
  expedition_snapshot.capture(room,db,sid)
  transport_snapshot.capture(db,sid);save_provenance.capture_boundary(db,sid);db.commit()

def promote(session,old,port=48921):
 if getattr(old,'recovery_plan',None):
  plan=old.recovery_plan
  if plan['save_id']!=old.succession_id or plan['session']!=old.config['session']:raise ValueError('stale recovery plan; use verified shared save')
  from recovery_group import recover
  return recover(session,old,port=port)
 if port is None:port=48921
 from room_host import create_room
 from game_bridge import Bridge
 import threading
 sid=old.succession_id
 replica=old.root.parent/('host-backup-'+old.config['session']+'-'+str(sid))
 if not old.succession_armed or not sid or not replica.is_dir():raise ValueError('verified succession snapshot required')
 city=old.client.city
 bind=getattr(old.client,'local_address',None)
 if not bind:raise ValueError('local network address missing')
 # Stage/validate the new room before publishing any new engine mailbox state.
 target=session.root/('host-successor-'+uuid.uuid4().hex)
 server=create_room(target,restore=replica/'room.sqlite',save_id=sid,project=replica/'scenario-project.json',expand_available=False,bind_host=bind,port=port)
 room=server.coordinator;co=room.coordinator
 import maker_room;maker_room.mark(server,target,maker_room.is_maker(replica/'room.sqlite') or bool(getattr(old,'maker_room',False)))   # a maker room stays one on the new host
 try:
  config=json.loads((target/'player-1.json').read_text())
  config_path=session.root/('successor-'+uuid.uuid4().hex+'.json');config_path.write_text(json.dumps(config),encoding='utf-8')
  bridge=Bridge(config_path,session.mail)
  # Calls are local during setup; the new authority is not advertised yet.
  from coordinator import PROTOCOL,BUILD
  base=dict(protocol=PROTOCOL,build=BUILD,session=co.session,scenario=co.scenario['sha256'])
  joined=room.request(dict(base,op='lobby_join',city=city,invite=config['invite']))
  peer=next(c for c in co.scenario['cities'] if c!=city)
  guest=json.loads((target/'player-2.json').read_text())
  room.request(dict(base,op='lobby_join',city=peer,invite=guest['invite']))
  with closing(co.connect()) as db:
   db.execute('INSERT OR REPLACE INTO player_name VALUES(?,?)',(peer,getattr(old,'peer_name','이전 방장')));db.commit()
  room.started=True
  room.request(dict(base,op='lobby_leave',invite=guest['invite']))
  with closing(co.connect()) as db:
   db.execute('INSERT OR REPLACE INTO player_name VALUES(?,?)',(city,getattr(old,'own_name',city)))
   db.execute('INSERT OR IGNORE INTO play_session VALUES(?)',(city,));db.commit()
   room.system_chat(db,f'방장을 이어받았습니다. 공동 저장 #{sid}에서 복구했습니다. 저장 이후 진행은 되돌아갑니다.',key='succession-start')
  bridge.client.city=city;bridge.client.token=joined['token'];bridge.joined=True
  thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  session.server=server;session.thread=thread;session.bridge=bridge
  (session.root/'succession-result.json').write_text(json.dumps(dict(previous_session=old.config['session'],save_id=sid,city=city,new_session=co.session,address=bind,port=server.server_address[1])),encoding='utf-8')
  session.publish('network-entry.txt','0');session.publish('network-status.txt','방장을 이어받고 있습니다.')
  bridge.tick()
 except Exception:
  if session.server is server:session.close_server()
  else:server.server_close()
  raise
