"""Local lobby/chat host. Creates fresh real campaign snapshots; never starts live play."""
import sys,json,uuid,argparse
from contextlib import closing
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import transport_snapshot
import objectives
import expedition_snapshot
from coordinator import Coordinator,Server,PROTOCOL,BUILD
from lobby import Lobby
from city_client import Engine,HERE,game_data
from scenario_pair import load_pair,verify_city
from scenario_project import write_layout,load,layout,DEFAULT

def create_room(root,restore=None,save_id=None,project=DEFAULT,bind_host='127.0.0.1',port=0,expand_available=True,advertise_host=None,host_by_first_join=False,advertise_port=None):
 """advertise_host: the address written into invitations when the room listens on another one (a server behind a router:
 it listens on its own LAN address, players reach it at the public one). advertise_port: likewise the port, when
 players reach the room through another one (game_hall.py: many rooms behind one port). host_by_first_join: nobody
 plays on the machine that runs the room, so the first player who comes in gets the host's seat."""
 from connection_config import address,port as valid_port,engine_hash,encode
 bind_host=address(bind_host);valid_port(port,ephemeral=True);advertise_host=address(advertise_host) if advertise_host else bind_host
 if advertise_port is not None:valid_port(advertise_port)
 if restore and Path(project)==DEFAULT and (Path(restore).parent/'scenario-project.json').is_file():
  project=Path(restore).parent/'scenario-project.json'
 manifest=load(project)
 preset,binding=load_pair(game_data(),manifest)
 restored=None;expansion=None;original=None
 if restore:
  from restore_pair import read_pair
  restored=read_pair(restore,binding,save_id)
  binding=restored['binding']
  from restore_expansion import original_project
  original=original_project(Path(restore).parent,manifest)
  # A save whose records belong to the cities that played (throne, 황제의 순행, a dispatch, a finished transport) is
  # continued with the same cities: no empty seat is offered for new players. Before 2026-11-15 these raised here, so
  # such a game started with fewer players than seats could not be continued at all (network_play always offers
  # the expansion; the room has no other way in).
  fixed=restored.get('throne') is not None or restored['binding'].get('progress') is not None or bool(restored.get('expedition')) or bool(restored['transport'] and restored['transport'].get('transfer'))
  if expand_available and original and len(original['slots'])>len(manifest['slots']) and not fixed:
   expansion=dict(original=original,restored=restored)
   preset,binding=load_pair(game_data(),original)
   binding=dict(binding);binding.pop('objectives',None)
   if restored['binding'].get('objectives'):binding['objectives']=restored['binding']['objectives']
 # a seat this PC cannot start is named before the room folder or any engine run (2026-11-15: instead of 'engine operation rejected: 92')
 need=[s for s in (original if expansion else manifest)['slots'] if s['id'] in preset['cities'] and not (restored and s['id'] in restored['parts'])]
 if need:
  import creator_presets
  missing=creator_presets.missing_maps(dict(slots=need))
  if missing:raise ValueError(creator_presets.missing_maps_text(missing))
 root=Path(root);root.mkdir(parents=True,exist_ok=False)
 if restored:
  from mailbox_io import publish_text
  publish_text(root/'room-options-worker.txt',' '.join(map(str,restored['room_options']['values'])))
 (root/'scenario-project.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
 write_layout(original if expansion else manifest,root)
 if original:(root/'scenario-original.json').write_text(json.dumps(original,ensure_ascii=False),encoding='utf-8')
 session=uuid.uuid4().hex;co=Coordinator(root/'room.sqlite',session,binding)
 for city in preset['cities']:
  if restored and city in restored['parts']:sav,rec=restored['parts'][city]
  else:
   out=root/city;sav,rec=Engine().run('start-'+city,root,out);verify_city(out,city,preset)
  co.provision(city,sav,rec)
 room=Lobby(co)
 if expansion:room.restore_expansion=expansion
 if restored:
  expedition_snapshot.restore(root/'expedition.sqlite',restored.get('expedition'),binding['cities'],restored['parts'])
  if restored.get('expedition'):
   with closing(co.connect()) as db:db.execute('INSERT OR IGNORE INTO expedition_required VALUES(1)');db.commit()
  room.restored_cities=set(restored['parts'])
  with closing(co.connect()) as db:
   import room_options
   room_options.restore(db,restored['room_options'])
   import observe_permissions
   observe_permissions.restore(db,restored.get('observe_permissions',[]),list(restored['parts']))
   from mailbox_io import publish_text
   publish_text(root/'room-options-worker.txt',' '.join(map(str,restored['room_options']['values'])))
   db.execute('UPDATE clock_origin SET ticks=?',(restored['ticks'],))
   db.execute('UPDATE room_speed SET value=?',(restored['speed'],))
   transport_snapshot.restore(db,restored['transport'],binding['cities'])
   import post_recovery
   post_recovery.forgive(db,[x['city'] for x in restored.get('provenance',[]) if x.get('mode')=='retained'])
   objectives.restore(db,restored.get('objectives'),restored['binding'],restored['ticks'])
   import throne_state
   throne_state.restore(db,restored.get('throne'),restored['binding'],restored['ticks'])
   import imperial_progress;imperial_progress.restore(db,restored.get('progress'),restored['binding'],restored['ticks'])
   for item in restored.get('provenance',[]):db.execute('INSERT OR REPLACE INTO origin_provenance VALUES(?,?)',(item['city'],item['ticks']))
   db.commit()
  room.origin=room.grant=restored['ticks']
  (root/'restored-from.json').write_text(json.dumps({k:v for k,v in restored.items() if k not in ('parts','expedition')},ensure_ascii=False,indent=2),encoding='utf-8')
 import migration
 if not expansion:migration.baseline(room)
 server=Server(room,bind_host,port)
 configs=[]
 for i in range(len(binding['cities'])):
  config=dict(protocol=PROTOCOL,build=BUILD,session=session,scenario=binding['sha256'],host=advertise_host,port=advertise_port or server.server_address[1],invite=room.invite(),engine_sha256=engine_hash())
  (root/('player-'+str(i+1)+'.json')).write_text(json.dumps(config),encoding='utf-8');configs.append(config)
 (root/'guest-invitation.txt').write_text(encode(configs[-1]) if len(configs)>1 else '',encoding='ascii')
 # Admission remains internally authenticated; a user need only know the host IP.
 guest_configs=[dict(c) for c in configs[1:]];admitted={};admission_time={}
 host_seat=dict(client=None,time=0.0) if host_by_first_join else None   # the host's seat, while nobody holds it yet
 def public_join(request):
  import re,time
  if set(request) not in ({'op','protocol','build','engine_sha256','client_id'},{'op','protocol','build','engine_sha256','client_id','expected_session'}) or request['protocol']!=PROTOCOL or request['build']!=BUILD or request['engine_sha256']!=configs[0]['engine_sha256']:raise ValueError('incompatible room')
  client_id=request['client_id']
  if not isinstance(client_id,str) or not re.fullmatch('[0-9a-f]{32}',client_id):raise ValueError('invalid request')
  with room.lock,closing(co.connect()) as db:
   if request.get('expected_session',co.session)!=co.session:raise ValueError('room changed')
   if db.execute('SELECT 1 FROM room_closed').fetchone():raise ValueError('room closed')
   if room.start_state(db)['phase']!='lobby':raise ValueError('game already started')
   from coordinator import sha
   now=time.monotonic()
   if host_seat is not None:
    key=sha(configs[0]['invite'].encode())
    claimed=db.execute('SELECT city FROM lobby_invite WHERE token=?',(key,)).fetchone()
    if host_seat['client']==client_id:host_seat['time']=now;return configs[0]
    held=claimed and claimed[0] is not None
    if not held and (host_seat['client'] is None or now-max(host_seat['time'],room.last_seen(key))>30):
     host_seat.update(client=client_id,time=now);return configs[0]   # first in (or the first left before choosing a city)
   for index,cfg in enumerate(guest_configs):
    key=sha(cfg['invite'].encode())
    claimed=db.execute('SELECT city FROM lobby_invite WHERE token=?',(key,)).fetchone()
    departed=db.execute('SELECT 1 FROM departed_invite WHERE token=?',(key,)).fetchone()
    expired=index in admitted and claimed and claimed[0] is None and now-max(admission_time[index],room.last_seen(key))>30
    if departed or expired:
     db.execute('DELETE FROM lobby_invite WHERE token=?',(key,));db.commit()
     cfg['invite']=room.invite();admitted.pop(index,None)
    if admitted.get(index)==client_id:
     admission_time[index]=now;return cfg
   # Up to 8 seats, at most MAX_ONLINE_PLAYERS play (2026-11-15): the room takes no more people than can start;
   # before, 7 or 8 could come in and the start was then refused for everybody.
   from multiplayer_limits import MAX_ONLINE_PLAYERS
   present=1+sum(1 for index,cfg in enumerate(guest_configs) if index in admitted or db.execute('SELECT city FROM lobby_invite WHERE token=?',(sha(cfg['invite'].encode()),)).fetchone()[0] is not None)
   if present>=MAX_ONLINE_PLAYERS:raise ValueError('room full')
   for index,cfg in enumerate(guest_configs):
    if index not in admitted and db.execute('SELECT city FROM lobby_invite WHERE token=?',(sha(cfg['invite'].encode()),)).fetchone()[0] is None:
     admitted[index]=client_id;admission_time[index]=now;return cfg
   raise ValueError('room full')
 from room_discovery import attach
 attach(server,room,manifest,[configs[0],*guest_configs],admitted,admission_time,host_seat)
 # Developer diagnostics: a test tool of the Korean edition (EDITIONS.md), left out of the global edition. Without the
 # file the room has no diagnostics request at all.
 try:import diag_relay
 except ImportError:diag_relay=None
 if diag_relay:server.public_diag=lambda request:diag_relay.pull(room,request)   # developer key only
 server.public_join=public_join
 (root/'ready.txt').write_text('Scenario multiplayer development test.',encoding='utf-8')
 return server

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('directory');parser.add_argument('--project',type=Path,default=DEFAULT);args=parser.parse_args()
 server=create_room(args.directory,project=args.project)
 try:server.serve_forever()
 finally:server.server_close()
