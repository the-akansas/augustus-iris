"""Deterministic group recovery. One designated candidate; no unsafe fallback election."""
import json,socket,threading,time,uuid,secrets
from pathlib import Path
from contextlib import closing
from coordinator import sha,PROTOCOL,BUILD

def initialize(db):
 db.execute('CREATE TABLE IF NOT EXISTS recovery_endpoint(city TEXT PRIMARY KEY,host TEXT,port INTEGER)')

def endpoint(db,city,host,port):
 from connection_config import address,port as checked_port
 db.execute('INSERT OR REPLACE INTO recovery_endpoint VALUES(?,?,?)',(city,address(host),checked_port(port)));db.commit()
 return dict(registered=True)

def plan(room,db,viewer,private=False):
 rows=db.execute('SELECT city FROM lobby_invite ORDER BY rowid').fetchall()
 if len(rows)<=2:return None
 host=rows[0][0];active=room.active_cities(db)
 guests=[r[0] for r in rows[1:] if r[0] in active]
 if not guests or any(c is None for c in guests):return None
 records={r['city']:r['save_id'] for r in db.execute('SELECT city,save_id FROM succession')}
 candidate=guests[0]
 # Only the candidate needs a copy (see sid below). Before, every guest had to have acknowledged one: a single
 # guest whose copy was still on its way left the whole group without a plan, and a lost host ended everybody's
 # game (2026-11-15). A guest without a copy rejoins with its credentials like the others.
 if candidate not in records:return None
 address=db.execute('SELECT host,port FROM recovery_endpoint WHERE city=?',(candidate,)).fetchone()
 if not address:return None
 # The candidate builds the new room from its OWN copy, so the plan names the save it acknowledged. The oldest save of
 # all guests was named before; a guest that copied only an earlier save (saves can come faster than one copy) then
 # named a save the candidate never copied, and the takeover failed ('checkpoint missing', 2026-11-15). The other
 # guests need no copy: they rejoin the new room with their credentials.
 sid=records[candidate]
 result=dict(candidate=candidate,host=address['host'],port=address['port'],save_id=sid,
             session=room.coordinator.session,guests=guests,departed=[c for c in room.coordinator.scenario['cities'] if c not in guests],
             names={r['city']:r['name'] for r in db.execute('SELECT city,name FROM player_name')})
 if private and viewer==candidate:
  result['credentials']={r['id']:r['token'] for r in db.execute('SELECT id,token FROM city') if r['id'] in guests}
 return result

def attach_bridge(session,config,city,name):
 from game_bridge import Bridge
 path=session.root/('recovered-'+uuid.uuid4().hex+'.json');path.write_text(json.dumps(config),encoding='utf-8')
 bridge=Bridge(path,session.mail)
 bridge.client.city=city;joined=bridge.client.call('lobby_join',invite=config['invite'])
 bridge.client.city=city;bridge.client.token=joined['token'];bridge.joined=True
 bridge.client.call('player_name',name=name)
 session.bridge=bridge;session.publish('network-entry.txt','0');bridge.tick()
 return bridge

def recover(session,old,port=None):
 from room_host import create_room
 from connection_config import validate
 plan=old.recovery_plan;city=old.client.city
 if city not in plan['guests']:raise ValueError('not a recovery member')
 if city!=plan['candidate']:
  identity=dict(session=plan['session'],city=city,token=old.client.token,build=BUILD)
  def exchange(request):
   with socket.create_connection((plan['host'],plan['port']),timeout=1) as sock:
    sock.settimeout(2);sock.sendall((json.dumps(request)+'\n').encode())
    raw=sock.makefile('rb').readline(16385)
   if len(raw)>16384:raise ValueError('recovery response too large')
   response=json.loads(raw)
   if not response.get('ok'):raise ValueError('recovery authentication rejected')
   return response['result']
  last=None
  for _ in range(20):
   try:
    # Fetch a nonce bound to the candidate's checkpoint. Cached lobby plans may
    # differ by one save at disconnect; joining still requires an exact ID AND
    # the authenticated candidate-issued nonce. Wrong-ID replay stays rejected.
    offer=exchange(dict(identity,op='recovery_offer'))
    if not isinstance(offer,dict) or set(offer)!={'session','candidate','save_id','challenge'} or offer['session']!=plan['session'] or offer['candidate']!=plan['candidate'] or type(offer['save_id'])!=int or offer['save_id']<=0 or not isinstance(offer['challenge'],str) or len(offer['challenge'])!=64:raise ValueError('invalid recovery offer')
    config=validate(exchange(dict(identity,op='recovery_join',save_id=offer['save_id'],challenge=offer['challenge'])));break
   except (OSError,ValueError) as error:last=error;time.sleep(.5)
  else:raise ValueError('designated recovery host unavailable') from last
  attach_bridge(session,config,city,getattr(old,'own_name',city));return
 sid=plan['save_id'];replica=old.root.parent/('host-backup-'+old.config['session']+'-'+str(sid))
 if not replica.is_dir():raise ValueError('designated recovery checkpoint missing')
 target=session.root/('host-successor-'+uuid.uuid4().hex)
 server=create_room(target,restore=replica/'room.sqlite',save_id=sid,project=replica/'scenario-project.json',expand_available=False,bind_host=plan['host'],port=port if port is not None else plan['port'])
 room=server.coordinator;co=room.coordinator;configs={}
 import maker_room;maker_room.mark(server,target,maker_room.is_maker(replica/'room.sqlite') or bool(getattr(old,'maker_room',False)))   # a maker room stays one on the new host
 try:
  # The designated candidate receives host invite #1; other members keep city IDs.
  order=[city]+[c for c in co.scenario['cities'] if c!=city]
  base=dict(protocol=PROTOCOL,build=BUILD,session=co.session,scenario=co.scenario['sha256'])
  for i,member in enumerate(order):
   config=json.loads((target/('player-'+str(i+1)+'.json')).read_text());configs[member]=config
   room.request(dict(base,op='lobby_join',city=member,invite=config['invite']))
  with closing(co.connect()) as db:
   for member,name in plan['names'].items():db.execute('INSERT OR REPLACE INTO player_name VALUES(?,?)',(member,name))
   db.commit()
  room.started=True
  for member in plan['departed']:room.request(dict(base,op='lobby_leave',invite=configs[member]['invite']))
  challenges={}
  def authenticated(request,fields):
   if not isinstance(request,dict) or set(request)!=fields:raise ValueError('invalid recovery request')
   member=request['city'];token=request['token']
   if request['session']!=plan['session'] or request['build']!=BUILD or member not in plan['guests'] or not isinstance(token,str) or sha(token.encode())!=plan['credentials'].get(member):raise ValueError('invalid recovery request')
   return member
  def recovery_offer(request):
   member=authenticated(request,{'op','session','city','token','build'})
   challenge=secrets.token_hex(32);challenges[member]=challenge
   return dict(session=plan['session'],candidate=city,save_id=sid,challenge=challenge)
  def recovery_join(request):
   member=authenticated(request,{'op','session','save_id','city','token','build','challenge'})
   if type(request['save_id'])!=int or request['save_id']!=sid or not isinstance(request['challenge'],str) or len(request['challenge'])!=64 or not secrets.compare_digest(challenges.get(member,''),request['challenge']):raise ValueError('invalid recovery checkpoint')
   return configs[member]
  server.recovery_offer=recovery_offer;server.recovery_join=recovery_join
  thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();session.server=server;session.thread=thread
  with closing(co.connect()) as db:room.system_chat(db,f"새 방장이 공동 저장 #{sid}에서 방을 복구했습니다. 참가자들이 같은 도시로 돌아오고 있습니다.",key='group-recovery')
  attach_bridge(session,configs[city],city,getattr(old,'own_name',city))
  (session.root/'succession-result.json').write_text(json.dumps(dict(previous_session=plan['session'],save_id=sid,city=city,new_session=co.session,mode='group',candidate=city)),encoding='utf-8')
 except Exception:
  if session.server is server:session.close_server()
  else:server.server_close()
  raise
