import observe_permissions
import throne_state
import joint_save
from clock_policy import CREDIT_TICKS, FRESH_SECONDS, credit_for_speed
import army_orders
import live_trade
import migration
import recovery_group
import objectives
import celebration
import room_roster
from city_labels import city_name
"""Local prototype lobby. Host issues invites; clients choose a single durable city slot.
No GUI or live simulation is enabled by readiness. Recovery RPCs remain usable offline.
"""
import hashlib,hmac,secrets,threading,time,unicodedata,math
from contextlib import closing
from pathlib import Path
from coordinator import PROTOCOL,BUILD,sha

class Lobby:
 def __init__(self,coordinator,clock=time.monotonic):
  if coordinator.scenario is None:raise ValueError('scenario required')
  import lobby_map
  self.empire_map=lobby_map.load(coordinator.path)
  self.lobby_overview=lobby_map.briefing(coordinator.path)
  try:   # display-only trade paths for the empire map; a failure only means the original route display
   import empire_route_display
   self.empire_routes=empire_route_display.host_routes(coordinator.path)
  except Exception:self.empire_routes=dict(version=None,data=None,routes=[])
  self.coordinator=coordinator;self.clock=clock;self.lock=threading.RLock();self.presence={};self.grant=0;self.progress={};self.last_grant=clock()
  with closing(coordinator.connect()) as db:
   import lobby_chat
   lobby_chat.initialize(db)
   import room_options
   room_options.initialize(db)
   migration.initialize(db)
   joint_save.initialize(db)
   observe_permissions.initialize(db)
   try:import spectate   # 관전 (Korean edition only, EDITIONS.md)
   except ImportError:spectate=None
   if spectate:spectate.initialize(db)
   army_orders.initialize(db)
   live_trade.initialize(db)
   db.execute('CREATE TABLE IF NOT EXISTS clock_origin(ticks INTEGER)')
   if not db.execute('SELECT 1 FROM clock_origin').fetchone():db.execute('INSERT INTO clock_origin VALUES(0)')
   self.start_at=None;self.start_step=None;self.started=False
   self.origin=db.execute('SELECT ticks FROM clock_origin').fetchone()[0];self.grant=self.origin
   objectives.configure(db,coordinator.scenario,self.origin)
   throne_state.configure(db,coordinator.scenario,self.origin)
   import throne_events;throne_events.initialize(db)
   import imperial_progress;imperial_progress.configure(db,coordinator.scenario,self.origin)
   db.execute('CREATE TABLE IF NOT EXISTS lobby_invite(token TEXT PRIMARY KEY,city TEXT UNIQUE)')
   db.execute('CREATE TABLE IF NOT EXISTS room_speed(value INTEGER)')
   if not db.execute('SELECT 1 FROM room_speed').fetchone():db.execute('INSERT INTO room_speed VALUES(80)')
   db.execute('CREATE TABLE IF NOT EXISTS play_session(city TEXT PRIMARY KEY)')
   db.execute('CREATE TABLE IF NOT EXISTS chat(id INTEGER PRIMARY KEY AUTOINCREMENT,city TEXT,message_id TEXT,text TEXT,UNIQUE(city,message_id))');db.commit()
   db.execute('CREATE TABLE IF NOT EXISTS dormant_city(city TEXT PRIMARY KEY)')
   db.execute('CREATE TABLE IF NOT EXISTS departed_invite(token TEXT PRIMARY KEY)')
   db.execute('CREATE TABLE IF NOT EXISTS notification_event(key TEXT PRIMARY KEY)')
   for column in ('audience_a','audience_b'):
    if column not in {r[1] for r in db.execute('PRAGMA table_info(chat)')}:db.execute('ALTER TABLE chat ADD COLUMN '+column+' TEXT')
   db.execute('CREATE TABLE IF NOT EXISTS room_closed(value INTEGER)')
   db.execute('CREATE TABLE IF NOT EXISTS disconnected_token(token TEXT PRIMARY KEY,reason TEXT)')
   db.execute('CREATE TABLE IF NOT EXISTS player_name(city TEXT PRIMARY KEY,name TEXT)')
   if 'player_color' not in {row[1] for row in db.execute('PRAGMA table_info(chat)')}:db.execute('ALTER TABLE chat ADD COLUMN player_color INTEGER DEFAULT -1')
   if 'sender' not in {row[1] for row in db.execute('PRAGMA table_info(chat)')}:db.execute("ALTER TABLE chat ADD COLUMN sender TEXT DEFAULT ''")
   db.commit()
 def invite(self):
  """Host-only local call; never an unauthenticated network operation."""
  token=secrets.token_hex(32)
  with self.lock,closing(self.coordinator.connect()) as db:
   db.execute('BEGIN IMMEDIATE')
   if db.execute('SELECT count(*) FROM lobby_invite').fetchone()[0]>=len(self.coordinator.scenario['cities']):
    raise ValueError('room full')
   db.execute('INSERT INTO lobby_invite VALUES(?,NULL)',(sha(token.encode()),));db.commit()
  return token
 def system_chat(self,db,text,targets=None,key=None):
  if key and db.execute('SELECT 1 FROM notification_event WHERE key=?',(key,)).fetchone():return
  a,b=(targets if targets else (None,None))
  db.execute("INSERT INTO chat(city,message_id,text,sender,audience_a,audience_b) VALUES('system',?,?,?,?,?)",(secrets.token_hex(16),text,'시스템',a,b))
  if key:db.execute('INSERT INTO notification_event VALUES(?)',(key,))
  db.commit()
 def depart(self,db,key,old,timed_out=False,removed=False):
  host=db.execute('SELECT token FROM lobby_invite ORDER BY rowid LIMIT 1').fetchone()[0]
  name=db.execute('SELECT name FROM player_name WHERE city=?',(old,)).fetchone()
  db.execute('INSERT INTO departed_invite VALUES(?)',(key,))
  if key==host:db.execute('INSERT INTO room_closed VALUES(1)')
  else:db.execute("UPDATE joint_save SET state='cancelled' WHERE state='collecting'")
  if old:
   self.presence.pop(old,None);self.progress.pop(old,None)
   credential=db.execute('SELECT token FROM city WHERE id=?',(old,)).fetchone()[0]
   db.execute('INSERT OR REPLACE INTO disconnected_token VALUES(?,?)',(credential,'removed by host' if removed else 'participant timed out' if timed_out else 'room left'))
   db.execute('UPDATE city SET token=? WHERE id=?',(sha(secrets.token_bytes(32)),old))
   if not self.started:
    db.execute('UPDATE lobby_invite SET city=NULL WHERE token=?',(key,))
    db.execute('DELETE FROM player_name WHERE city=?',(old,))
  db.commit()
  message='방장이 나가서 방이 종료되었습니다.' if key==host else (name[0] if name else '참가자')+('님의 연결을 방장이 해제했습니다.' if removed else '님의 연결이 30초 동안 끊겨 퇴장 처리했습니다.' if timed_out else '님이 방을 나갔습니다.')
  self.system_chat(db,message,key='depart:'+key)
 def expire_guests(self,db):
  # Only a live host clock request may evict a guest. A stalled server or a
  # guest's request cannot elect a new host or fence the existing one.
  if not self.started:return
  now=self.clock()
  rows=db.execute('SELECT token,city FROM lobby_invite ORDER BY rowid').fetchall()
  for row in rows[1:]:
   city=row['city']
   if city is None or db.execute('SELECT 1 FROM departed_invite WHERE token=?',(row['token'],)).fetchone():continue
   contact=lambda c:max(self.presence.get(c,(-1e30,False))[0],self.progress.get(c,(0,-1e30))[1])
   last=contact(city)
   if now-last>=30:
    armed=db.execute('SELECT 1 FROM succession WHERE city=?',(city,)).fetchone()
    # Another guest still talking to this host proves the host is not the one cut off:
    # only the silent player left. The host stops itself only when nobody answers.
    heard=any(r['city'] not in (None,city) and now-contact(r['city'])<10 and not db.execute('SELECT 1 FROM departed_invite WHERE token=?',(r['token'],)).fetchone() for r in rows[1:])
    if armed and not heard and (len(rows)==2 or recovery_group.plan(self,db,city)):
     migration.fence(self,db);raise ValueError('host fenced')
    self.depart(db,row['token'],city,timed_out=True)
 def active_cities(self,db):
  left={r[0] for r in db.execute('SELECT city FROM lobby_invite WHERE token IN (SELECT token FROM departed_invite)')}
  left.update(r[0] for r in db.execute('SELECT city FROM dormant_city'))
  return [c for c in self.coordinator.scenario['cities'] if c not in left]
 def start_state(self,db):
  room_roster.poll(self,db)
  if getattr(self,"roster_job",None):return dict(phase="preparing",remaining=0)
  import start_gate
  return start_gate.state(self,db)
 def status(self,db):
  start=self.start_state(db);now=self.clock();slots=[]
  for city in self.coordinator.scenario['cities']:
   claimed=db.execute('SELECT 1 FROM lobby_invite WHERE city=?',(city,)).fetchone() is not None
   seen,ready=self.presence.get(city,(-1e30,False));online=now-seen<30
   progress=self.progress.get(city)
   running=db.execute('SELECT 1 FROM play_session WHERE city=?',(city,)).fetchone() is not None
   engine_state=('active' if now-progress[1]<FRESH_SECONDS else 'stale') if progress else ('starting' if running else 'lobby')
   name=db.execute('SELECT name FROM player_name WHERE city=?',(city,)).fetchone()
   age_ms=max(0,int((now-progress[1])*1000)) if progress else None
   owner=db.execute('SELECT token FROM city WHERE id=?',(city,)).fetchone()[0]
   version=getattr(self,'client_versions',{}).get(owner) if claimed else None
   contact=max(seen,progress[1] if progress else -1e30)
   invitation=db.execute('SELECT token FROM lobby_invite WHERE city=?',(city,)).fetchone()
   contact_age_ms=max(0,int((now-contact)*1000)) if contact>-1e20 else None
   rtt=getattr(self,'peer_rtt',{}).get(owner)
   import lobby_chat
   player_color=lobby_chat.color(db,invitation[0]) if invitation else -1
   slots.append(dict(player_color=player_color,contact_age_ms=contact_age_ms,rtt_ms=rtt,generation=sha(invitation[0].encode()) if invitation else '',client_version=version,saved_city=city in getattr(self,'restored_cities',()),dormant=db.execute('SELECT 1 FROM dormant_city WHERE city=?',(city,)).fetchone() is not None,departed=db.execute('SELECT 1 FROM lobby_invite WHERE city=? AND token IN (SELECT token FROM departed_invite)',(city,)).fetchone() is not None,name_id=self.coordinator.scenario.get('city_name_ids',{}).get(city,{'capua':2,'tarentum':1}.get(city,0)),city_name=city_name(city,self.coordinator.scenario.get('city_names')),name=name[0] if name else city,player_name=name[0] if name else None,age_ms=age_ms,city=city,claimed=claimed,online=online,ready=online and ready,ticks=progress[0] if progress else None,engine_state=engine_state))
  playing=db.execute('SELECT 1 FROM play_session').fetchone() is not None
  import room_options
  import throne_events
  try:import diag_relay   # Korean edition test tool (EDITIONS.md); absent in the global edition
  except ImportError:diag_relay=None
  import lobby_counts
  first=db.execute('SELECT token FROM lobby_invite ORDER BY rowid LIMIT 1').fetchone()
  host_version=getattr(self,'invite_versions',{}).get(first[0]) if first else None   # registered on entry, city or not
  return dict(host_version=host_version,start_year=self.start_year(),**({'dev':True,'dev_tools':self.maker_tools()} if getattr(self,'dev_mode',False) else {}),**({'diag':True} if diag_relay and diag_relay.active(self) else {}),lobby_counts=lobby_counts.counts(self,db,slots),throne=throne_events.public_status(db,self.coordinator.scenario),**self.progress_public(db),**self.spectate_public(db),observe_permissions=observe_permissions.state(db),room_options=room_options.state(db),empire_map=self.empire_map,layout_version=self.coordinator.scenario["sha256"],start=start,slots=slots,objectives=objectives.status(self,db),can_trade=not playing and all(s['ready'] for s in slots),live_play=playing,target_speed=db.execute('SELECT value FROM room_speed').fetchone()[0],host_city=db.execute('SELECT city FROM lobby_invite ORDER BY rowid LIMIT 1').fetchone()[0])
 def start_year(self):
  """The scenario's first year (scenario_project.start_year), for the dates the room's screens work out from ticks."""
  if getattr(self,'_start_year',None) is None:
   import json,scenario_project
   try:self._start_year=scenario_project.start_year(json.loads((Path(self.coordinator.path).parent/'scenario-project.json').read_text(encoding='utf-8-sig')))
   except (OSError,ValueError):self._start_year=scenario_project.START_YEAR_DEFAULT
  return self._start_year
 def maker_tools(self):
  """The test keys the scenario's author left on for a maker room (scenario_project.maker_tools; user 2026-11-17)."""
  if getattr(self,'_maker_tools',None) is None:
   import json,scenario_project
   try:self._maker_tools=scenario_project.maker_tools(json.loads((Path(self.coordinator.path).parent/'scenario-project.json').read_text(encoding='utf-8-sig')))
   except (OSError,ValueError):self._maker_tools=[t for t in scenario_project.MAKER_TOOLS if t not in ('throne','progress')]
  return self._maker_tools
 def dev_tools(self,need=None):
  """The developer tools this room allows: a maker room (game_hall.py or maker_room.py sets dev_mode; dev_tools.py)
  or a room of the test launcher (mp_test_tools.py with AUGUSTUS_MP_TEST_TOOLS=1, in no release). Otherwise the
  request is refused as unknown, as a room without the tools would."""
  if getattr(self,'dev_mode',False):
   if need and need not in self.maker_tools():raise ValueError('이 시나리오는 이 시험 단추를 쓰지 않습니다.')
   try:import dev_tools;return dev_tools
   except ImportError:pass
  try:import mp_test_tools
  except ImportError:raise ValueError('unknown operation') from None
  mp_test_tools.require();return mp_test_tools
 def spectate_public(self,db):
  # 관전 (spectate.py, Korean edition): allowed, spectators now and the most, chat level. Absent without the file, and
  # in a LAN room (user 2026-11-17: spectators come only from the game hall, so a LAN room shows no 관전 part)
  if not getattr(self,'hall_room',False):return {}
  try:import spectate
  except ImportError:return {}
  return dict(spectate=spectate.public(self,db))
 def progress_public(self,db):
  # 황제의 순행 (imperial_progress.py): the public part only. Absent for every other scenario.
  import imperial_progress
  state=imperial_progress.current(db,self.coordinator.scenario)
  return {} if state is None else dict(progress=imperial_progress.public_view(state))
 def request(self,r):
  result=self.request_locked(r)
  # Observation uploads/downloads finish their heavy byte work outside the room lock.
  from live_observe import Deferred
  return result() if isinstance(result,Deferred) else result
 def seen_invite(self,key):
  # A guest sitting in the lobby (still choosing a city) keeps its seat; only an
  # admission nobody uses is handed to the next arrival (room_host.public_join).
  import time
  self.__dict__.setdefault('invite_seen',{})[key]=time.monotonic()
 def last_seen(self,key):
  return getattr(self,'invite_seen',{}).get(key,-1e30)
 def request_locked(self,r):
  co=self.coordinator
  if not isinstance(r,dict) or (r.get('protocol'),r.get('build'),r.get('session'),r.get('scenario'))!=(PROTOCOL,BUILD,co.session,co.wire_scenario):
   raise ValueError('incompatible room')
  from network_diagnostics import measured_room_lock
  with measured_room_lock(self.lock,Path(co.path).parent,co.session,r.get('city'),r.get('op')),closing(co.connect()) as db:
   op=r.get('op');city=r.get('city')
   if op=='lobby_leave':
    invite=r.get('invite');key=sha(invite.encode()) if isinstance(invite,str) else ''
    row=db.execute('SELECT city FROM lobby_invite WHERE token=?',(key,)).fetchone()
    if row is None:raise ValueError('invalid invitation')
    if db.execute('SELECT 1 FROM departed_invite WHERE token=?',(key,)).fetchone():return dict(left=True)
    self.depart(db,key,row['city'])
    return dict(left=True)
   if db.execute('SELECT 1 FROM authority_fenced').fetchone():raise ValueError('host fenced')
   if db.execute('SELECT 1 FROM room_closed').fetchone():raise ValueError('room closed')
   if city=='~spectator':   # a spectator from the game hall (spectate.py): its own token, a few read-only requests
    try:import spectate
    except ImportError:raise ValueError('unknown operation') from None
    return spectate.request(self,db,r)
   if op in ('lobby_view','lobby_preview','lobby_chat_send','lobby_color','room_options_set','room_options_ack','lobby_client_version'):
    invite=r.get('invite')
    if isinstance(invite,str) and db.execute('SELECT 1 FROM departed_invite WHERE token=?',(sha(invite.encode()),)).fetchone():raise ValueError('room left')
    if not isinstance(invite,str) or not db.execute('SELECT 1 FROM lobby_invite WHERE token=?',(sha(invite.encode()),)).fetchone():raise ValueError('invalid invitation')
    self.seen_invite(sha(invite.encode()))
    if op=='lobby_client_version':
     # Display only: each admitted player's version from the moment it enters the waiting room, before any city is
     # chosen (user 2026-11-13: the host's version line must not wait for the host's city). Keyed by the invitation.
     from client_version import validate_info
     self.__dict__.setdefault('invite_versions',{})[sha(invite.encode())]=validate_info(r.get('info'))
     return dict(registered=True)
    if op in ('room_options_set','room_options_ack'):
     import room_options
     return room_options.request(self,db,sha(invite.encode()),r)
    if op=='lobby_chat_send':
     import lobby_chat
     return lobby_chat.send(db,sha(invite.encode()),r)
    if op=='lobby_color':
     import lobby_chat
     return lobby_chat.choose(self,db,sha(invite.encode()),r)
    if op=='lobby_preview':
     from city_preview import request
     return request(self,db,r.get('preview_city'))
    state=self.status(db)
    host=db.execute('SELECT token FROM lobby_invite ORDER BY rowid LIMIT 1').fetchone()[0]
    state['lobby_overview']=self.lobby_overview
    state['viewer_role']=1 if host==sha(invite.encode()) else 2
    state['lobby_messages']=[dict(x) for x in db.execute("SELECT sender,text,player_color FROM chat WHERE audience_a IS NULL AND audience_b IS NULL ORDER BY id DESC LIMIT 100")][::-1]   # the waiting room scrolls back through these
    return state
   if op=='lobby_arrive':
    invite=r.get('invite');name=r.get('name')
    if not isinstance(invite,str):raise ValueError('invalid invitation')
    key=sha(invite.encode())
    if not db.execute('SELECT 1 FROM lobby_invite WHERE token=?',(key,)).fetchone():raise ValueError('invalid invitation')
    if db.execute('SELECT 1 FROM departed_invite WHERE token=?',(key,)).fetchone():raise ValueError('room left')
    if not isinstance(name,str) or not name.strip() or len(name)>24 or any(unicodedata.category(ch) in ('Cc','Cf','Cs') for ch in name):raise ValueError('invalid name')
    db.execute('INSERT OR REPLACE INTO lobby_display_name VALUES(?,?)',(key,name.strip()));db.commit()
    self.seen_invite(key)
    self.system_chat(db,name.strip()+'님이 접속했습니다.',key='join-invite:'+key)
    return dict(name=name.strip())
   if op=='lobby_join':
    if getattr(self,'roster_job',None) or (self.start_at is not None and not self.started):raise ValueError('start in progress')
    invite=r.get('invite')
    if not isinstance(invite,str) or len(invite)!=64:raise ValueError('invite required')
    db.execute('BEGIN IMMEDIATE')
    row=db.execute('SELECT city FROM lobby_invite WHERE token=?',(sha(invite.encode()),)).fetchone()
    if row is None or city not in co.scenario['cities']:raise ValueError('invalid invitation or city')
    if self.started and row['city']!=city:raise ValueError('game already started')
    if db.execute('SELECT 1 FROM departed_invite WHERE token=?',(sha(invite.encode()),)).fetchone():raise ValueError('room left')
    switching=row['city'] is not None and row['city']!=city
    if switching and self.started:raise ValueError('game already started')
    owner=db.execute('SELECT token FROM lobby_invite WHERE city=?',(city,)).fetchone()
    if owner and owner['token']!=sha(invite.encode()):raise ValueError('city occupied')
    c=db.execute('SELECT active FROM city WHERE id=?',(city,)).fetchone()
    if c is None:raise ValueError('city snapshot not initialized')
    if row['city'] is None and c['active']:raise ValueError('city transaction active')
    if switching:
     old=row['city']
     if db.execute('SELECT active FROM city WHERE id=?',(old,)).fetchone()[0] or c['active']:raise ValueError('transaction pending')
     name=db.execute('SELECT name FROM player_name WHERE city=?',(old,)).fetchone()
     db.execute('DELETE FROM player_name WHERE city=?',(old,))
     if name:db.execute('INSERT OR REPLACE INTO player_name VALUES(?,?)',(city,name[0]))
     db.execute('UPDATE city SET token=? WHERE id=?',(sha(secrets.token_bytes(32)),old))
     self.presence.pop(old,None);self.progress.pop(old,None)
     if self.start_at is not None:
      self.start_at=None;self.start_step=None;db.execute('DELETE FROM play_session')
    # Same invitation recovers the same credential after a lost join response.
    token=hmac.new(invite.encode(),(co.session+'|'+city).encode(),hashlib.sha256).hexdigest()
    db.execute('UPDATE lobby_invite SET city=? WHERE token=?',(city,sha(invite.encode())))
    db.execute('UPDATE city SET token=? WHERE id=?',(sha(token.encode()),city));db.commit()
    self.presence[city]=(self.clock(),False)
    return dict(city=city,token=token,scenario=co.scenario['sha256'])
   token=r.get('token');c=db.execute('SELECT token FROM city WHERE id=?',(city,)).fetchone()
   expired=db.execute('SELECT reason FROM disconnected_token WHERE token=?',(sha(token.encode()),)).fetchone() if isinstance(token,str) else None
   if expired:raise ValueError(expired[0])
   if not isinstance(token,str) or c is None or not secrets.compare_digest(c['token'],sha(token.encode())):
    raise ValueError('unauthorized')
   if op=='diag_report':   # developer diagnostics summary (diag_relay): kept only while the developer collects
    try:import diag_relay
    except ImportError:return dict(active=False)   # global edition: no diagnostics tool
    return diag_relay.report(self,city,r)
   if op.startswith('cash_'):
    import cash_live
    return cash_live.request(self,db,city,c['token'],r)
   if op.startswith('post_'):
    import post_service
    return post_service.request(self,db,city,c['token'],r)
   if op=='observe_permission_set':return observe_permissions.request(self,db,city,r)
   if op=='spectate_settings':   # the host only (spectate.py, Korean edition)
    try:import spectate
    except ImportError:raise ValueError('unknown operation') from None
    host=db.execute('SELECT city FROM lobby_invite ORDER BY rowid LIMIT 1').fetchone()
    return spectate.settings(self,db,bool(host) and host[0]==city,r)
   if op=='participant_remove':
    import participant_admin
    return participant_admin.request(self,db,city,r)
   if op=='lobby_heartbeat':
    rtt=r.get('rtt_ms')
    if type(rtt)==int and 0<=rtt<=120000:
     if not hasattr(self,'peer_rtt'):self.peer_rtt={}
     self.peer_rtt[c['token']]=rtt
   if op=='client_version':
    from client_version import validate_info
    info=validate_info(r.get('info'))
    if not hasattr(self,'client_versions'):self.client_versions={}
    # Key by authenticated credential, not caller-supplied player name.
    self.client_versions[c['token']]=info
    return dict(registered=True)
   # Any authenticated traffic proves contact; readiness is still explicit.
   if not self.started:
    seen,ready=self.presence.get(city,(-1e30,False))
    if self.clock()-seen>=30:ready=False
    self.presence[city]=(self.clock(),ready)
    from network_diagnostics import record,ident
    record(Path(co.path).parent,'host_contact',session=ident(co.session),peer=ident(city),op=op,age_ms=max(0,int((self.clock()-seen)*1000)) if seen>-1e20 else 0)
   if op=='start_loaded':
    import start_gate
    return start_gate.acknowledge(self,db,city,r)
   if op=='recovery_endpoint':return recovery_group.endpoint(db,city,r.get('host'),r.get('port'))
   if op=='victory_done':return celebration.finish(self,db,city,r.get('run'))
   # Race for the Throne (throne_events.py). The attempting city is kept server-side only; status carries the
   # anonymous notice. No player-facing button sends this yet: cost, chance and resolution are undecided.
   if op in ('progress_mine','progress_bid','progress_visit','progress_test'):
    # 황제의 순행 (imperial_progress.py). Every answer carries the caller's own view only.
    import imperial_progress as ip
    state=ip.current(db,co.scenario)
    if state is None:raise ValueError('황제의 순행 시나리오가 아닙니다.')
    if joint_save.pending(db):
     if op=='progress_mine':return dict(own=ip.view(state,city))
     raise ValueError('공동 저장 중입니다. 저장이 끝난 뒤 다시 시도해 주세요.')
    tick=max(self.progress.get(city,(self.origin,0))[0],state['last_tick']);active=self.active_cities(db) if self.started else []
    funds=r.get('funds') if type(r.get('funds'))==int else None
    def ensure_ledger():
     if not db.execute("SELECT 1 FROM sqlite_master WHERE name='post_meta'").fetchone():
      db.commit()
      from trade_post_ledger import Ledger;Ledger(co.path,co.scenario['cities'],transport=True).close()
     import cash_live;cash_live.scope(self,db)
    result={}
    if op=='progress_test':   # a developer room (dev_tools.py) or the test launcher (mp_test_tools.py); refused elsewhere
     self.dev_tools('progress').progress_adjust(db,co.scenario,r.get('action'))
    ip.advance(db,co.scenario,tick,active,ensure_ledger)
    if op=='progress_bid':result=ip.bid(db,co.scenario,city,r.get('request'),r.get('amount'),funds,tick,active)
    elif op=='progress_visit':
     if ip.visit_report(db,co.scenario,city,r.get('visit'),r.get('taken'),funds,tick,active,ensure_ledger):ip.advance(db,co.scenario,tick,active,ensure_ledger)
    db.commit();result['own']=ip.view(ip.current(db,co.scenario),city);return result
   if op in ('throne_quote','throne_spend'):
    # 황위 시험 규칙 v1 (throne_play.py): the caller's own quote, or its own spend (one-sided debit + private record).
    import throne_play
    state=throne_state.current(db,co.scenario)
    if state is None or not throne_play.is_test(co.scenario):raise ValueError('황위 쟁탈전 시나리오가 아닙니다.')
    tick=max(self.progress.get(city,(self.origin,0))[0],state['last_tick'])
    funds=r.get('funds') if type(r.get('funds'))==int else None
    def ensure_ledger():
     if not db.execute("SELECT 1 FROM sqlite_master WHERE name='post_meta'").fetchone():
      db.commit()   # the ledger opens its own connection to create its tables: nothing of ours may be pending
      from trade_post_ledger import Ledger;Ledger(co.path,co.scenario['cities'],transport=True).close()
     import cash_live;cash_live.scope(self,db)   # the cash checkpoint (joint save) needs its scope row
    if joint_save.pending(db):raise ValueError('공동 저장 중입니다. 저장이 끝난 뒤 다시 시도해 주세요.')
    throne_play.settle(db,co.scenario,tick,ensure_ledger);state=throne_state.current(db,co.scenario)
    if op=='throne_quote':
     db.commit();return dict(quote=throne_play.quote(state,city,r.get('kind'),r.get('amount'),funds,tick),own=throne_play.view(state,city,tick,db))
    result=throne_play.spend(db,co.scenario,city,r.get('request'),r.get('kind'),r.get('amount'),funds,r.get('expect'),tick,ensure_ledger)
    db.commit();result['own']=throne_play.view(throne_state.current(db,co.scenario),city,tick,db);return result
   if op=='throne_test':
    # The panel under the throne box (user 2026-11-14): a developer room (dev_tools.py, user 2026-11-17 "개발자 방에서만
    # 허용") or the test launcher (mp_test_tools.py); every other room refuses it like any unknown request.
    tools=self.dev_tools('throne')
    import throne_play
    state=throne_state.current(db,co.scenario)
    if state is None or not throne_play.is_test(co.scenario):raise ValueError('황위 쟁탈전 시나리오가 아닙니다.')
    if joint_save.pending(db):raise ValueError('공동 저장 중입니다. 저장이 끝난 뒤 다시 시도해 주세요.')
    tick=max(self.progress.get(city,(self.origin,0))[0],state['last_tick'])
    throne_play.settle(db,co.scenario,tick);tools.throne_adjust(db,co.scenario,city,r.get('action'),tick);db.commit()
    return dict(own=throne_play.view(throne_state.current(db,co.scenario),city,tick,db))
   if op=='throne_coup_begin':
    import throne_events,throne_play
    state=throne_state.current(db,co.scenario)
    if state is None:raise ValueError('황위 쟁탈전 시나리오가 아닙니다.')
    if throne_play.is_test(co.scenario):raise ValueError('시험 규칙에서는 쿠데타 지원(throne_spend)으로 시도합니다.')
    tick=max(self.progress.get(city,(self.origin,0))[0],state['last_tick'])
    result=throne_events.begin_attempt(db,co.scenario,city,r.get('request'),tick);db.commit();return result
   if op=='throne_mine':   # the caller's own private values only
    import throne_events,throne_play
    if throne_play.is_test(co.scenario) and not joint_save.pending(db):
     state=throne_state.current(db,co.scenario)
     tick=max(self.progress.get(city,(self.origin,0))[0],state['last_tick'])
     if throne_play.settle(db,co.scenario,tick):db.commit()
    return throne_events.own(db,co.scenario,city)
   if op=='throne_raid':   # the caller's own engine reports its punitive expedition (legions in the city / gone unbeaten-by-order)
    import throne_play
    state=throne_state.current(db,co.scenario)
    if state is None or not throne_play.is_test(co.scenario):raise ValueError('황위 쟁탈전 시나리오가 아닙니다.')
    if joint_save.pending(db):raise ValueError('공동 저장 중입니다. 저장이 끝난 뒤 다시 시도해 주세요.')
    tick=max(self.progress.get(city,(self.origin,0))[0],state['last_tick'])
    throne_play.settle(db,co.scenario,tick)   # a tribute whose debit is confirmed counts before the battle report
    throne_play.raid_report(db,co.scenario,city,r.get('count'),r.get('seen'),tick);db.commit()
    return dict(own=throne_play.view(throne_state.current(db,co.scenario),city,tick,db))
   if op=='throne_opening':   # the caller's own opening for one joint save, kept on the caller's PC for a later host
    import throne_events
    sid=r.get('id')
    if type(sid)!=int or sid<=0:raise ValueError('save id')
    return dict(opening=throne_events.own_opening(db,co.scenario,city,sid))
   if op=='throne_hand_in':   # after a restore from a backup: the caller's own record, checked against the sealed save
    import throne_events
    state=throne_state.current(db,co.scenario)
    if state is None:raise ValueError('황위 쟁탈전 시나리오가 아닙니다.')
    tick=max(self.progress.get(city,(self.origin,0))[0],state['last_tick'])
    result=throne_events.hand_in(db,co.scenario,city,r.get('secret'),r.get('nonce'),tick);db.commit();return result
   if op=='throne_opening_stored':   # sent by the player's PC only after its opening is on disk and read back
    import throne_events
    sid=r.get('id')
    if type(sid)!=int or sid<=0:raise ValueError('save id')
    result=throne_events.confirm_stored(db,co.scenario,city,sid,r.get('commit'));db.commit();return result
   if op=='objective_report':
    result=objectives.submit(self,db,city,r)
    joint_save.finish_if_ready(self,db)
    return result
   if op=='objective_status':return objectives.status(self,db)
   if op=='empire_routes':return self.empire_routes   # display only (empire_route_display.py)
   if op=='recovery_plan':return recovery_group.plan(self,db,city,private=True)
   if op=='replica_ack':return migration.acknowledge(self,db,city,r.get('id'))
   if op=='succession_status':return dict(replicas=[dict(x) for x in db.execute('SELECT city,save_id FROM succession')])
   if op.startswith('route_'):
    import city_trade_routes
    if op=='route_status':return city_trade_routes.snapshot(db)
    if city not in self.active_cities(db) or r.get('peer') not in self.active_cities(db):raise ValueError('상대 도시의 연결을 확인하세요.')
    if joint_save.pending(db):raise ValueError('공동 저장 중입니다. 잠시 후 다시 시도하세요.')
    return city_trade_routes.request(db,co.scenario['cities'],city,op,r.get('peer'),r.get('request_id'),r.get('revision'))
   if op.startswith('agreement_'):
    import trade_agreements
    return trade_agreements.request(self,db,city,r)
   if op=='fleet_catalog':
    import player_fleet
    return player_fleet.register(db,city,r.get('posts'))
   if op in ('observe_put','observe_get','observe_status','observe_leave'):
    import live_observe
    return live_observe.request(self,db,city,r)
   import army_install
   if op in ('army_order','army_order_cancel','army_order_status','army_overview','army_live_poll','army_live_report','army_wiped','army_send_home'):
    import army_live
    army_live.initialize(db)
    if op=='army_order' and r.get('expedition') and not db.execute('SELECT 1 FROM army_live WHERE id=?',(r['expedition'],)).fetchone():return army_orders.request(self,db,city,r)
    if op=='army_order_cancel' and not db.execute('SELECT 1 FROM army_live WHERE action=? AND origin=?',(r.get('action_id'),city)).fetchone() and db.execute('SELECT 1 FROM army_order WHERE id=? AND city=?',(r.get('action_id'),city)).fetchone():return army_orders.request(self,db,city,r)
    result=army_live.request(self,db,city,r)
    if op=='army_overview':return result+army_orders.request(self,db,city,r)
    if op=='army_order_status' and not result:return army_orders.request(self,db,city,r)
    return result
   if op.startswith('army_'):
    if army_orders.busy(db) and op not in ('army_install_status','army_install_ack'):raise ValueError('save busy')
    return army_install.request(self,db,city,r)
   if (army_install.pending(self) or army_orders.busy(db)) and (op in ('save_begin','save_cancel') or op.startswith('live_') and op not in ('live_status','live_history')):raise ValueError('save busy')
   if op.startswith('live_') and getattr(co,'post_protocol',0)==1:
    raise ValueError('legacy trade disabled in receipt protocol room')
   if op.startswith('live_'):
    before=live_trade.selected(db,city,r)
    harmless_cancel=op=='live_reject' and before and before['state']=='offered'
    active=self.active_cities(db)
    endpoints=(city,r.get('receiver')) if op=='live_offer' else (before['sender'],before['receiver']) if before else ()
    suspended=any(p is not None and p not in active for p in endpoints)
    if suspended and op not in ('live_status','live_history','live_ack','live_batch','live_sync','live_home','live_home_failed') and not harmless_cancel:raise ValueError('participant left; trade suspended')
    if suspended and op=='live_status' and before and before['state']!='committed':
     if city not in (before['sender'],before['receiver']):return None
     result=dict(before);result['suspended']=True;return result
    result=live_trade.request(self,db,city,r)
    if suspended and isinstance(result,dict):result['suspended']=True
    if op in ('live_accept','live_reject') and before and isinstance(result,dict) and result.get('state')!=before['state']:
     name=db.execute('SELECT name FROM player_name WHERE city=?',(city,)).fetchone()
     actor=name[0] if name else city
     action='수락했습니다.' if op=='live_accept' else '취소했습니다.' if city==before['sender'] else '거절했습니다.'
     self.system_chat(db,f"{actor}님이 거래 #{before['id']} 제안을 {action}",(before['sender'],before['receiver']),f"trade:{before['id']}:{op}:{city}")
    return result
   if op in ('save_begin','save_cancel'):
    import participant_admin
    if participant_admin.save_blocked(self,db):raise ValueError('transfer in progress')
   if op.startswith('save_'):return joint_save.request(self,db,city,r)
   if op=='player_name':
    name=r.get('name')
    if not isinstance(name,str) or not name.strip() or len(name)>24 or any(unicodedata.category(ch) in ('Cc','Cf','Cs') for ch in name):raise ValueError('invalid name')
    db.execute('INSERT OR REPLACE INTO player_name VALUES(?,?)',(city,name.strip()));db.commit()
    owner=db.execute('SELECT token FROM lobby_invite WHERE city=?',(city,)).fetchone()
    if owner:self.system_chat(db,name.strip()+'님이 접속했습니다.',key='join-invite:'+owner[0])
    return dict(name=name.strip())
   if op=='room_speed':
    host=db.execute('SELECT city FROM lobby_invite ORDER BY rowid LIMIT 1').fetchone()
    speed=r.get('speed')
    if not host or host['city']!=city:raise ValueError('host only')
    if type(speed)!=int or speed not in (0,10,20,30,40,50,60,70,80,90,100):raise ValueError('speed')
    db.execute('UPDATE room_speed SET value=?',(speed,));db.commit();self.last_grant=self.clock()
    return self.status(db)
   if op=='room_start_cancel':
    # The host stops a start under way (user 2026-11-14: only a guest taking back "ready" could). While the empty
    # seats are being turned neutral the request waits for that job and cancels as soon as the countdown would begin.
    host=db.execute('SELECT city FROM lobby_invite ORDER BY rowid LIMIT 1').fetchone()[0]
    if host!=city:raise ValueError('host only')
    if self.started:raise ValueError('start already finished')
    self.cancel_requested=True
    return self.status(db)
   if op=='room_start':
    host=db.execute('SELECT city FROM lobby_invite ORDER BY rowid LIMIT 1').fetchone()[0]
    if host!=city:raise ValueError('host only')
    state=self.status(db)
    if state['start']['phase']!='lobby':return state
    selected=[s for s in state['slots'] if s['claimed'] and not s.get('departed')]
    if not selected:raise ValueError('participant required')
    # Someone in the waiting room who has not chosen a city yet (seen within 30 s, the same rule that keeps their seat in
    # room_discovery/room_host) must not be left behind: the start used to go ahead and send them back to the main menu
    # (user report 2026-11-13). An admission nobody uses for 30 s does not block.
    import time as _time
    if any(_time.monotonic()-self.last_seen(k)<=30 for (k,) in db.execute('SELECT token FROM lobby_invite WHERE city IS NULL AND token NOT IN (SELECT token FROM departed_invite)')):
     raise ValueError('participants must choose cities')
    if not all(s['online'] and (s['city']==host or s['ready']) for s in selected):raise ValueError('participants must be ready')
    # A struggle for the throne can be played alone (user 2026-11-15: becoming emperor is the goal for some): its
    # payments are one-sided debits of the player's own city (trade_post_ledger.stage_debit).
    # The fewest players the scenario's author allows (scenario_project.min_players; 황제의 순행 always needs two).
    try:
     import json;from scenario_project import min_players
     need=min_players(json.loads((Path(co.path).parent/'scenario-project.json').read_text(encoding='utf-8')))
    except (OSError,ValueError,KeyError,TypeError):need=1
    if len(selected)<need and not getattr(self,'restored_cities',None):raise ValueError('needs players %d'%need)
    from multiplayer_limits import MAX_ONLINE_PLAYERS
    if len(selected)>MAX_ONLINE_PLAYERS:raise ValueError('too many players')   # up to 8 seats, at most 6 play (user 2026-11-15)
    import room_options
    for slot in selected:room_options.require_ack(self,db,slot['city'])
    if getattr(self,'restore_expansion',None):
     from restore_expansion import begin
     begin(self,db,[s['city'] for s in selected]);return self.status(db)
    if len(selected)<len(state['slots']):
     room_roster.begin(self,db,[s['city'] for s in selected]);return self.status(db)
    if db.execute('SELECT 1 FROM city WHERE active IS NOT NULL').fetchone():raise ValueError('transaction pending')
    if getattr(self,'restored_cities',None):room_roster.set_dormant(self,db,[s['city'] for s in selected])
    self.start_at=self.clock()+5;self.start_step=None
    return self.status(db)
   if op=='clock':
    ticks=r.get('ticks');now=self.clock()
    if not db.execute('SELECT 1 FROM play_session WHERE city=?',(city,)).fetchone():raise ValueError('not playing')
    if type(ticks)!=int or not 0<=ticks<=self.grant:raise ValueError('invalid ticks')
    # Concurrent authenticated RPCs can arrive after a newer progress report.
    # A stale report is read-only: never roll progress back or renew its lease.
    if ticks>=self.progress.get(city,(0,0))[0]:self.progress[city]=(ticks,now)
    host=db.execute('SELECT city FROM lobby_invite ORDER BY rowid LIMIT 1').fetchone()[0]
    if city==host:self.expire_guests(db)
    speed=db.execute('SELECT value FROM room_speed').fetchone()[0]
    active=self.active_cities(db)
    synced=bool(active) and all(c in self.progress and now-self.progress[c][1]<FRESH_SECONDS for c in active)
    # Rolling look-ahead keeps a bounded buffer without an eight-tick stop/start barrier.
    # Trusted engine clients pace each tick using the host's target speed.
    army_orders.poll(self,db)
    army_orders.retain_offline(self,db)
    saving=joint_save.pending(db)
    military_busy=bool(army_install.pending(self) or army_orders.busy(db))
    transfer=live_trade.busy(db)
    if transfer and any(p not in active for p in (transfer['sender'],transfer['receiver'])):
     # An already committed local snapshot must be installed once before resuming.
     # No new settlement is attempted without the departed city's live engine.
     if transfer and transfer['state']=='committed':
      if city not in (transfer['sender'],transfer['receiver']):transfer=None
     if transfer and transfer['state']=='committed':
      cargo=db.execute('SELECT 1 FROM live_cargo WHERE id=?',(transfer['id'],)).fetchone()
      installed=db.execute('SELECT 1 FROM live_cargo_ack WHERE result=? AND city=?',(transfer['result'],city)).fetchone() if cargo else db.execute('SELECT 1 FROM live_installed WHERE id=? AND city=?',(transfer['id'],city)).fetchone()
      if installed:transfer=None
     else:transfer=None
    ceremony=celebration.state(self,db)
    goal_tick=objectives.barrier(self,db)
    if self.start_state(db)['phase']=='started' and not saving and not transfer and not military_busy and not ceremony and speed and synced:
     proposed=max(self.grant,min(self.progress[c][0] for c in active)+credit_for_speed(speed))
     self.grant=proposed
    goal_state=objectives.state(db)
    requested=goal_tick if goal_state and city in objectives.required(goal_state['rules'],co.scenario['cities']) else None
    reason='save' if saving else 'trade' if transfer else 'army' if military_busy else 'ceremony' if ceremony else 'host_pause' if not speed else 'peer_stale' if not synced else 'none'
    return dict(grant=self.grant,wait_reason=reason,ceremony=ceremony,objective_tick=requested,speed=((speed or 80) if ticks<self.grant else 0) if saving or transfer or military_busy or ceremony else speed,waiting=not synced,save_id=saving['id'] if saving else 0,save_ticks=saving['ticks'] if saving else 0,trade_busy=bool(transfer or military_busy),army_token=army_install.expected(self,city))
   if op=='play_begin':
    if not db.execute('SELECT 1 FROM play_session WHERE city=?',(city,)).fetchone():
     if self.status(db)['start']['phase']=='lobby':raise ValueError('host must start first')
     if db.execute('SELECT 1 FROM city WHERE active IS NOT NULL').fetchone():raise ValueError('transaction pending')
     db.execute('INSERT INTO play_session VALUES(?)',(city,));db.commit()
    import scenario_briefing
    scenario_briefing.publish(self,db,city)
    return dict(city=city,start_ticks=self.origin,start_message=scenario_briefing.start_message_for(self,city))
   if op in ('offer','checkpoint') and db.execute('SELECT 1 FROM play_session').fetchone():
    raise ValueError('live city checkpoint integration pending; trade disabled')
   if op=='chat_send':
    mid=r.get('message_id');text=r.get('text')
    if not isinstance(mid,str) or len(mid)!=32 or any(x not in '0123456789abcdef' for x in mid):raise ValueError('message id')
    if not isinstance(text,str) or not text.strip() or len(text)>500 or len(text.encode('utf-8'))>2000:raise ValueError('message length')
    if any(unicodedata.category(ch) in ('Cc','Cf','Cs') for ch in text):raise ValueError('control character')
    # Whisper (user 2026-11-13): 'to' is another seated player's city; only the two of them read the line.
    to=r.get('to')
    if to is not None:
     seated={row[0] for row in db.execute('SELECT city FROM lobby_invite WHERE city IS NOT NULL')}
     if not isinstance(to,str) or to==city or to not in seated:raise ValueError('귓속말 받을 플레이어를 다시 골라 주세요.')
    old=db.execute('SELECT id,text,audience_b FROM chat WHERE city=? AND message_id=?',(city,mid)).fetchone()
    if old:
     if old['text']!=text or old['audience_b']!=to:raise ValueError('message id reused')
     return dict(id=old['id'])
    name=db.execute('SELECT name FROM player_name WHERE city=?',(city,)).fetchone()
    import lobby_chat
    invitation=db.execute('SELECT token FROM lobby_invite WHERE city=?',(city,)).fetchone()
    color=lobby_chat.color(db,invitation[0]) if invitation else -1
    result=db.execute('INSERT INTO chat(city,message_id,text,sender,player_color,audience_a,audience_b) VALUES(?,?,?,?,?,?,?)',(city,mid,text,name[0] if name else city,color,city if to else None,to));db.commit()
    return dict(id=result.lastrowid)
   if op=='chat_read':
    after=r.get('after',0)
    if type(after)!=int or not 0<=after<=9223372036854775807:raise ValueError('cursor')
    # whisper_to: the receiver's name on a player's whisper (system lines addressed to someone are not whispers)
    return dict(messages=[dict(row) for row in db.execute("SELECT id,city,text,sender,player_color,CASE WHEN city!='system' AND audience_b IS NOT NULL THEN COALESCE((SELECT name FROM player_name WHERE player_name.city=chat.audience_b),audience_b) END AS whisper_to FROM chat WHERE id>? AND (audience_a IS NULL OR audience_a=? OR audience_b=?) ORDER BY id LIMIT 100",(after,city,city))])
   if op=='lobby_ready' and (getattr(self,'roster_job',None) or self.start_at is not None) and r.get('ready') is not False:raise ValueError('start in progress')
   if op in ('lobby_status','lobby_ready','lobby_heartbeat'):
    if op!='lobby_status':
     now=self.clock();seen,ready=self.presence.get(city,(-1e30,False))
     if now-seen>=30:ready=False
     if op=='lobby_ready':
      if type(r.get('ready')) is not bool:raise ValueError('boolean required')
      if r['ready']:
       import room_options
       room_options.require_ack(self,db,city)
      if r['ready'] and not ready:
       import lobby_version
       lobby_version.warn(self,db,city)
      ready=r['ready']
      if not ready and self.started:raise ValueError('already playing')
     self.presence[city]=(now,ready)
     row=db.execute('SELECT token FROM lobby_invite WHERE city=?',(city,)).fetchone()
     if row:self.seen_invite(row[0])   # still in the room for the hall's people list (game_hall.member_state; user 2026-11-17: gone a minute after choosing a city)
    return self.status(db)
   if op=='offer' and not self.status(db)['can_trade']:raise ValueError('both cities must be online and ready')
   return co.request(r)
