from windows_paths import filesystem_path, launch_cwd, legacy_process_path
"""User-launched one-game network session manager. Never injects game input."""

from persistent_profile import prepare_profile
import argparse,json,os,shutil,subprocess,sys,threading,time,uuid,socket,traceback

from pathlib import Path

sys.path.insert(0,str(Path(__file__).parent))

from mailbox_io import publish_text,remove_file,read_command

from connection_config import decode,validate,address,port

from room_host import create_room

from game_bridge import Bridge

from city_client import HERE

from network_preferences import Preferences,display_line
from scenario_project import players_label

from creator_workspace import Workspace



class NameRefused(ValueError):

 """An ID the hall would refuse (game_hall.reserved_name): told to the player as it is."""



class Session:

 hall_port=48921   # where a game hall listens (the same port a room on a player's PC uses)

 def __init__(self,root,preferences_path=None):

  self.root=filesystem_path(root);self.root.mkdir(parents=True,exist_ok=True)

  self.mail=self.root/'bridge';self.mail.mkdir(exist_ok=True)

  self.server=None;self.thread=None;self.bridge=None;self.helper=None;self.response=None

  self.search_thread=None;self.search_result=None;self.search_error=None;self.found_room=None;self.search_host=None

  self.creator=None;self.importer=None;self.import_response=None

  from city_visit import Visits

  self.visits=Visits(self.root/'city-visits',self.visit_notice)

  self.preferences=Preferences(preferences_path if preferences_path is not None else HERE/'network-preferences.json')

  import previous_version

  self.publish('network-entry.txt','1');self.publish('network-status.txt',previous_version.announcement(HERE) or '방 만들기 또는 입장하기를 선택하세요.')

  self.publish_preferences()

 def publish(self,name,text):

  publish_text(self.mail/name,text)

 def publish_preferences(self):

  data=self.preferences.read()

  for key,listing,last in [('recent_ips','network-recent-ips.txt','network-last-ip.txt'),('player_names','network-player-names.txt','network-last-name.txt')]:

   self.publish(listing,'\n'.join(data[key]));self.publish(last,data[key][0] if data[key] else '')

 def remember_address(self,host):

  # Saving local conveniences must never turn a successful connection into an error.

  try:self.preferences.update('recent_ips',host);self.publish_preferences()

  except OSError:self.publish('network-profile-status.txt','접속은 완료했지만 최근 주소를 저장하지 못했습니다.')

 def update_check(self):

  """The "업데이트 확인" button on the first multiplayer screen (Korean edition: update_check.py; user 2026-11-16): the newest version on

  the server against this one, in update-check.txt (line 1: 0 up to date, 1 newer, 2 not checked; then the lines to show).

  Nothing is fetched or changed; updating is 업데이트확인.cmd with the game closed."""

  try:import update_check

  except ImportError:self.publish('update-check.txt','2\n이 판에는 업데이트 확인이 없습니다.');return

  if getattr(self,'update_thread',None) and self.update_thread.is_alive():return

  self.publish('update-check.txt','')

  def check():

   try:

    mine,newest=update_check.latest(HERE.parent)

    if mine==newest:text=f'0\n최신 버전입니다 ({mine}).'

    else:text=f'1\n새 버전이 있습니다: {newest}\n게임을 끄고 업데이트확인.cmd를 실행해 주세요.'

   except update_check.Failed as error:   # two lines: the reason, then what to do (one line is cut on the 512px screen)

    reason,sep,rest=str(error).partition('. ');text='2\n'+reason+('.' if sep else '')+('\n'+rest if rest else '')

   except (OSError,ValueError):text='2\n서버에서 버전을 확인하지 못했습니다. 잠시 뒤 다시 확인해 주세요.'

   self.publish('update-check.txt',text)

  self.update_thread=threading.Thread(target=check,daemon=True);self.update_thread.start()

 def profile_command(self,verb,payload):

  self.publish('network-name-saved.txt','')

  try:

   key='recent_ips' if verb=='network-forget-ip' else 'player_names'

   value=self.preferences.update(key,payload,forget=verb.startswith('network-forget-'))

   self.publish_preferences();self.publish('network-profile-status.txt','')

   if verb=='network-save-name':

    if self.bridge and not self.bridge.joined:self.bridge.client.call('lobby_arrive',invite=self.bridge.config['invite'],name=value)

    self.publish('network-name-saved.txt',value)

    self.publish('network-name-result.txt',payload+'\nok\n'+value)

   self.publish('network-profile-result.txt',verb+'\n'+payload+'\nok')

  except (OSError,ValueError) as error:

   from error_text import reason
   message=str(error) if isinstance(error,ValueError) else '기록을 저장하지 못했습니다('+reason(error.strerror or type(error).__name__,40)+'). 게임 폴더의 쓰기 권한을 확인해 주세요.'

   self.publish('network-profile-status.txt',message)

   self.publish('network-profile-result.txt',verb+'\n'+payload+'\n'+message)

   if verb=='network-save-name':self.publish('network-name-result.txt',payload+'\nerror\n'+message)

 def connect(self,request,name=None,new_room=False):

  if self.bridge or self.server:raise ValueError('already connected')

  if not isinstance(request,dict):raise ValueError('invalid connection request')

  self.publish('room-recovery-result.txt','')

  self.publish('room-exit.txt','')

  try:

   if request.get('mode')=='host':

    if set(request)-{'dev'} not in ({'mode','address','port','project'},{'mode','address','port','project','restore','save_id'}) or request.get('dev',True) is not True:raise ValueError('invalid connection request')

    address(request['address']);port(request['port'])

    room=self.root/('host-'+uuid.uuid4().hex)

    restore=request.get('restore');save_id=request.get('save_id')

    project=Path(restore).parent/'scenario-project.json' if restore else Path(request['project'])

    import maker_room
    dev=maker_room.check(request.get('dev') is True,restore)   # a maker room's save continues only in a maker room, and the other way round
    self.server=create_room(room,restore=restore,save_id=save_id,project=project,bind_host=request['address'],port=request['port'])
    maker_room.mark(self.server,room,dev)

    self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()

    config=json.loads((room/'player-1.json').read_text());self.publish('network-invitation.txt',(room/'guest-invitation.txt').read_text())

   elif request.get('mode')=='join':

    if set(request)!={'mode','code'}:raise ValueError('invalid connection request')

    config=decode(request['code'])

   else:raise ValueError('invalid connection request')

   validate(config);config_path=self.root/('connection-'+uuid.uuid4().hex+'.json');config_path.write_text(json.dumps(config),encoding='utf-8')

   bridge=Bridge(config_path,self.mail)

   if request['mode']=='host' and not request.get('restore'):
    import host_options_profile
    bridge.host_options_path=self.preferences.path.with_suffix('.host-options.json')
    saved_options=host_options_profile.load(bridge.host_options_path)
    if saved_options is not None:
     bridge.client.call('room_options_set',invite=config['invite'],revision=0,values=saved_options)

   state=bridge.client.call('lobby_view',invite=config['invite'])

   if request['mode']=='join' and state['start']['phase']!='lobby':raise ValueError('started room requires shared restore')

   if new_room and state.get('viewer_role')==1:

    # A room just opened in a game hall, this player in the host's seat (2026-11-15): the host's last room options are put

    # on it, and changes are kept for the next room - the same as a room on the player's own PC.

    import host_options_profile

    bridge.host_options_path=self.preferences.path.with_suffix('.host-options.json')

    saved_options=host_options_profile.load(bridge.host_options_path)

    current=state.get('room_options') or {}

    if saved_options is not None and type(current.get('revision'))==int:

     try:bridge.client.call('room_options_set',invite=config['invite'],revision=current['revision'],values=saved_options)

     except ValueError:pass   # somebody changed them first: the room keeps what it has

   bridge.tick() # authenticated reachability before entering the lobby
   if name is not None:
    # Register the name before the UI leaves the connect screen; otherwise the host
    # briefly (or, on failure, for good) lands on the ID prompt while guests join.
    bridge.client.call('lobby_arrive',invite=config['invite'],name=name)
    self.publish('network-joined-name.txt',name)

   self.bridge=bridge;self.publish('network-entry.txt','0');self.publish('network-status.txt','연결되었습니다.')

   if request['mode']=='join':self.remember_address(config['host'])

  except Exception:

   self.close_server();self.bridge=None

   try:self.publish('network-entry.txt','1')

   except OSError:pass

   raise

 @staticmethod

 def connection_error(error,hosting):

  if str(error)=='room changed':return '방이 바뀌었습니다. 다시 검색해 주세요.'

  if isinstance(error,PermissionError):return '게임 폴더의 연결 상태 파일을 갱신하지 못했습니다. 잠시 후 다시 시도해 주세요.'

  if isinstance(error,subprocess.TimeoutExpired):return '도시 지도 준비 시간이 초과되었습니다. connection-error.log를 확인해 주세요.'

  if getattr(error,'winerror',None)==10048:return '이 PC에서 같은 포트를 사용 중입니다. 실행 중인 다른 멀티플레이를 종료해 주세요.'

  if str(error).startswith('지형 편집'):return str(error)

  return ('방 생성 실패: ' if hosting else '방 접속 실패: ')+str(error)[:160]

 def close_server(self):

  if self.server:

   if self.thread:self.server.shutdown()

   self.server.server_close()

   if self.thread:self.thread.join(timeout=5)

  self.server=self.thread=None

 def leave_hall(self):

  hall=getattr(self,'hall',None);self.hall=None

  if hall:hall.stop()

 def local_scenarios(self):

  """This PC's own scenarios for the hall's 내 저장소 tab: [(title, seats, path)], read again each time the room window opens."""

  try:return [(entry['title'],entry['players'],entry['path']) for entry in Workspace(HERE).catalog()['entries']]

  except (OSError,ValueError):return []



 def enter_hall(self,host,name):

  """Into the game hall at `host` (game_hall.py): its lists are kept up to date for the hall screen from now on."""

  from network_preferences import player_name

  try:   # the game hall is the Korean edition's (EDITIONS.md); the Global edition plays over the LAN alone

   from hall_client import HallClient,local_country

   from game_hall import reserved_name

  except ImportError:raise ValueError('이 판에는 로비가 없습니다. 랜 플레이를 이용해 주세요.') from None

  host=address(host);name=player_name(name)

  if reserved_name(name):raise NameRefused('그 아이디는 쓸 수 없습니다. 다른 아이디를 정해 주세요.')   # checked before leaving the hall the player is in

  self.leave_hall()

  local=self.local_scenarios()

  client=self.root.name.rsplit('-',1)[-1]

  if len(client)!=32:client=uuid.uuid5(uuid.NAMESPACE_URL,str(self.root)).hex

  self.hall_host=host;self.hall_name=name;self.hall_return=None

  try:   # the country picker's list, in this edition's language (countries.tsv: code, Korean, English)

   rows=[line.split('\t') for line in (HERE/'countries.tsv').read_text(encoding='utf-8').splitlines() if line.count('\t')==2]

   self.publish('hall-countries.txt','\n'.join(code+'\t'+korean for code,korean,english in sorted(rows,key=lambda row:row[1])))

  except (OSError,UnicodeError):self.publish('hall-countries.txt','')

  def save(path):   # a scenario fetched from the hall's shared library: into this PC's own scenarios (LAN rooms offer it too)

   from scenario_import import import_scenario

   return import_scenario(HERE,path)['path']

  self.hall=HallClient(self.publish,client,host,self.hall_port,name,local_country(self.preferences.path.with_suffix('.country.txt')),local,save=save,
                      board_seen=self.preferences.path.with_suffix('.board-seen.txt'),patch_seen=self.preferences.path.with_suffix('.patch-seen.txt'))

  self.preferences.update('player_names',name);self.publish_preferences()

 def hall_join(self,room,mine=False):

  """Into a room of the hall the player is in (the hall is left: the room's own waiting room takes over)."""

  import re

  if not getattr(self,'hall',None) or not re.fullmatch('[0-9a-f]{32}',room):raise ValueError('먼저 로비에 들어가 주세요.')

  self.spectate_end()   # a spectator who enters a room stops watching

  host,name=self.hall_host,self.hall_name

  self.direct_join(host,server_port=self.hall_port,name=name,room=room,new_room=mine)   # mine: the room this player just opened

  hall,self.hall=self.hall,None;hall.finish_with_room(room)   # the room's scenario is kept on this PC too

  self.publish('hall-entry.txt','')

  self.hall_return=(host,name)   # back into the hall when this room is left or closed (reset)

  if not getattr(self,'hall_server',False):self.remember_address(host)   # a typed address; the edition's own server is not one

 def hall_spectate(self,room):
  """관전 (Korean edition, spectate_client.py): the hall hands out a spectator's token for `room`; the session then
  talks to the room as its spectator while the game shows the 관전 screen (the hall stays entered)."""
  import re
  if not getattr(self,'hall',None) or not re.fullmatch('[0-9a-f]{32}',room):raise ValueError('먼저 로비에 들어가 주세요.')
  try:import spectate_client
  except ImportError:raise ValueError('이 판에는 관전 기능이 없습니다.') from None
  self.spectate_end()   # an earlier look (and why it ended) is over: the screen waits for this one's state
  with socket.create_connection((address(self.hall_host),self.hall_port),timeout=8) as sock:
   sock.sendall((json.dumps(dict(op='hall_spectate',client_id=self.hall.client_id,room=room))+'\n').encode())
   answer=json.loads(sock.makefile('rb').readline(65536) or b'{}')
  if not answer.get('ok'):
   error=answer.get('error')
   raise ValueError(error if error and error not in ('invalid request','invalid_request','internal_error') else '서버가 이전 버전이라 관전할 수 없습니다. NAS를 업데이트해 주세요.')
  self.spectate_end()
  self.spectator=spectate_client.Session(self.mail,self.root,self.hall_host,self.hall_port,answer['result'],self.hall_name)
  self.publish('hall-status.txt','')
 def spectate_poll(self):
  s=getattr(self,'spectator',None)
  if s and s.ended is not None:self.publish('visit-denied.txt','1');self.visits.close();s.close();self.spectator=None   # an open city view closes; the screen reads why from spectate-state.txt
 def spectate_end(self):
  s=getattr(self,'spectator',None);self.spectator=None
  if s:
   self.visits.close();s.close()
  self.publish('spectate-state.txt','')
 def disconnect(self):

  self.spectate_end()

  self.leave_hall()

  self.visits.close()

  if self.bridge:

   self.bridge.close()

   try:self.bridge.client.call('lobby_leave',invite=self.bridge.config['invite'])

   except (OSError,ValueError):pass

  if self.server:time.sleep(1) # let the guest receive the explicit closed-room event

  self.close_server();self.bridge=None

 def reset(self):

  self.disconnect()

  archive=self.root/('ended-'+uuid.uuid4().hex);archive.mkdir()

  for p in self.mail.iterdir():

   if p.is_file():

    shutil.copy2(p,archive/p.name)

    if p.name!='menu-leave-request.txt':remove_file(p)

  self.publish('network-entry.txt','1');self.publish('network-status.txt','방 만들기 또는 입장하기를 선택하세요.')

  self.publish_preferences()

  if hasattr(self,'adapters'):self.publish_adapters()

  self.found_room=None

  self.prepare_starts()

  (self.mail/'menu-leave-request.txt').unlink(missing_ok=True)

  back,self.hall_return=getattr(self,'hall_return',None),None

  if back:   # the room was entered through a hall: the player is put back there

   try:self.enter_hall(*back);self.publish('hall-return.txt','1')

   except (OSError,ValueError,KeyError,RuntimeError) as e:self.publish('hall-status.txt',self.connection_error(e,False))

 def succeed(self,port=None):

  self.publish('room-recovery-result.txt','')

  old=self.bridge

  if old:old.close()

  # Back up the complete old mailbox before removing any state.

  try:

   self.visits.close()

   self.publish('auto-enter.txt','0')

   archive=self.root/('pre-succession-'+uuid.uuid4().hex);archive.mkdir()

   files=[p for p in self.mail.iterdir() if p.is_file()]

   for p in files:shutil.copy2(p,archive/p.name)

   for p in files:

    if p.name!='chat-events.txt':remove_file(p)

   self.bridge=None

   from migration import promote

   promote(self,old,port=port)

  except Exception as error:

   self.close_server();self.bridge=None

   (self.root/'succession-error.log').write_text(repr(error),encoding='utf-8')

   self.publish('network-entry.txt','1')

   self.publish('room-exit.txt','')

   self.publish('room-recovery-result.txt','failed')

   self.publish('network-status.txt','자동 복구에 실패했습니다. 보존된 공동 저장으로 방을 다시 만들 수 있습니다.')

   self.publish_preferences()

   if hasattr(self,'adapters'):self.publish_adapters()

   self.prepare_starts()

 def prepare_choices(self):

  subprocess.run([legacy_process_path(HERE/'Augustus-Network.exe'),'--adapter-probe'],cwd=launch_cwd(HERE),check=True,timeout=15)

  self.adapters=json.loads((HERE/'network-adapters.json').read_text(encoding='utf-8-sig'))

  self.adapters.append(dict(address='127.0.0.1',name='혼자 플레이 (이 PC 전용)'))

  self.publish_adapters()

  self.prepare_starts()

 def publish_adapters(self):

  self.publish('network-adapters.txt','\n'.join(x['address']+' / '+display_line(x['name']) for x in self.adapters))

 def prepare_starts(self):

  # default-scenarios.json names the bundled scenarios the list shows, in order (tools/make_default_scenarios.py).
  # Other folders under scenarios/ stay for tests and tools and are opened only through AUGUSTUS_MP_PROJECT.
  try:listed=[HERE/'scenarios'/str(n)/'scenario.json' for n in json.loads((HERE/'default-scenarios.json').read_text(encoding='utf-8-sig'))['scenarios']]
  except (OSError,ValueError,KeyError,TypeError):listed=None
  project=os.environ.get('AUGUSTUS_MP_PROJECT',str(listed[0] if listed else HERE/'scenarios/unified-sandbox/scenario.json'))

  self.starts=[]

  from scenario_project import load,require_runtime

  candidates=[Path(project),HERE/'scenarios/unified-sandbox/scenario.json',HERE/'scenarios/unified-cooperative/scenario.json',HERE/'scenarios/preset-sandbox/scenario.json',HERE/'scenarios/four-cities/scenario.json',HERE/'scenarios/capua-tarentum-sea/scenario.json',HERE/'scenarios/capua-tarentum/scenario.json']

  # Discover all scenario folders and nested creator projects, not only bundled examples.

  if listed is None:candidates+=sorted((HERE/'scenarios').rglob('scenario.json'))+sorted((HERE/'scenarios').glob('*.json'))
  else:candidates=[Path(project)]+listed
  shown=None if listed is None else {str(filesystem_path(p).resolve()) for p in candidates}

  try:candidates += [Path(entry['path']) for entry in Workspace(HERE).catalog()['entries']]

  except (OSError,ValueError):self.publish('menu-status.txt','작업 폴더를 읽지 못했습니다. 기본 시나리오는 사용할 수 있습니다.')

  seen=set();seen_projects=set()

  for path in candidates:

   path=filesystem_path(path)  # Unify ordinary and extended Windows paths before categorizing/deduplicating.
   if str(path.resolve()) in seen or not path.is_file():continue
   if shown is not None and str(path.resolve()) not in shown and path.resolve().is_relative_to((HERE/'scenarios').resolve()):continue

   seen.add(str(path.resolve()))

   try:

    data=load(path);require_runtime(data)
    # The struggle for the throne is a normal victory condition since 2026-11-14 (user): offered like any other scenario.

    category='기본 제공' if path.resolve().is_relative_to((HERE/'scenarios').resolve()) else '내 작업'

    canonical=(category,json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(',',':')))

    if canonical in seen_projects:continue

    seen_projects.add(canonical)

    category='기본 제공' if path.resolve().is_relative_to((HERE/'scenarios').resolve()) else '내 작업'

    self.starts.append(dict(label='['+category+'] '+display_line(data['title'])+' ('+players_label(data)+'인 / '+('협동' if data['rules'].get('mode')=='cooperative' else '경쟁 · 황위 쟁탈전' if data['rules'].get('mode')=='race-for-throne' else '경쟁 · 황제의 순행' if data['rules'].get('mode')=='imperial-progress' else '경쟁 · 기한 경쟁' if data['rules'].get('mode')=='deadline-race' else '자유 건설')+')',project=str(path)))

   except (OSError,ValueError):continue

  if not self.starts:raise ValueError('no playable scenarios')

  from save_catalog import catalog

  from scenario_pair import load_pair

  from city_client import game_data

  from start_catalog import save_choices

  binding=load_pair(game_data())[1]
  try:
   from save_catalog import prune
   prune(HERE/'rooms',binding,current=self.root)   # only the newest 8 games are kept (user 2026-11-15)
  except OSError:pass
  self.starts.extend(save_choices(catalog(HERE/'rooms',binding)['entries'],project))

  from scenario_overview import publish as publish_briefings
  publish_briefings(self)

  self.publish('network-starts.txt','\n'.join(x['label'] for x in self.starts))

 def start_search(self,host):

  from room_discovery import probe

  if self.bridge or (self.search_thread and self.search_thread.is_alive()):return

  host=address(host);self.search_host=host;self.search_result=self.search_error=None;self.search_hall=False

  self.publish('network-search-busy.txt','1')

  def search():

   try:self.search_result=probe(host)

   except (OSError,ValueError,KeyError,TypeError) as error:self.search_error=str(error)

   if not (HERE/'game_hall.py').is_file():return   # no game hall in this edition (Korean edition only, EDITIONS.md)

   try:   # is a game hall at this address (game_hall.py)? Then the screen offers "로비 입장" beside the room.

    with socket.create_connection((host,self.hall_port),timeout=3) as sock:

     sock.settimeout(3);sock.sendall(b'{"op":"hall_info"}\n')

     with sock.makefile('rb') as stream:answer=json.loads(stream.readline(8193))

    self.search_hall=bool(answer.get('ok') and isinstance(answer.get('result'),dict) and answer['result'].get('hall'))

   except (OSError,ValueError,AttributeError):self.search_hall=False

  self.search_thread=threading.Thread(target=search,daemon=True);self.search_thread.start()

 def finish_search(self):

  if not self.search_thread or self.search_thread.is_alive():return

  self.search_thread=None;self.publish('network-search-busy.txt','0')

  self.publish('network-hall.txt',self.search_host if getattr(self,'search_hall',False) else '')

  if self.bridge:return

  from room_discovery import summary

  if self.search_result:

   self.found_room=self.search_result

   allowed=self.found_room['compatible'] and self.found_room['joinable']

   from room_discovery import refusal

   # line 2: '1' joinable, or '0 <why>' (shown in red in the info box and when 입장 is pressed; user 2026-11-13)

   self.publish('network-room-info.txt',self.search_host+'\n'+('1' if allowed else '0 '+refusal(self.found_room))+'\n'+summary(self.found_room))

   self.publish('network-status.txt','아이디를 확인한 뒤 입장하세요.' if allowed else '방 상태 또는 버전을 확인하세요.')

  else:

   self.found_room=None

   # Retain prior details for reference while visibly invalidating admission.

   old=(self.mail/'network-room-info.txt').read_text(encoding='utf-8') if (self.mail/'network-room-info.txt').exists() else ''

   parts=old.split('\n',2);detail=parts[2] if len(parts)==3 and parts[0]==self.search_host else ''

   self.publish('network-room-info.txt',self.search_host+'\n2\n'+detail)   # '2': no answer (drawn in red inside the info box)

   self.publish('network-status.txt','응답 없음. 방장 IP와 연결을 확인하고 다시 검색해 주세요.')

 def join_found(self,host,name):

  from network_preferences import player_name

  from room_discovery import probe

  host=address(host);name=player_name(name)

  if not self.found_room or self.found_room['address']!=host:raise ValueError('먼저 방을 검색해 주세요.')

  latest=probe(host)

  if latest['session']!=self.found_room['session']:raise ValueError('방이 바뀌었습니다. 다시 검색해 주세요.')

  if not latest['compatible']:raise ValueError('같은 게임 버전을 사용해 주세요.')

  if not latest['joinable']:raise ValueError('지금은 입장할 수 없습니다. 새로고침해 주세요.')

  self.preferences.update('player_names',name);self.publish_preferences()

  self.direct_join(host,expected_session=latest['session'],name=name)

 def direct_join(self,host,server_port=48921,expected_session=None,name=None,room=None,new_room=False):

  from coordinator import PROTOCOL,BUILD

  from connection_config import engine_hash,encode

  request=dict(op='public_join',protocol=PROTOCOL,build=BUILD,engine_sha256=engine_hash(),client_id=self.root.name.rsplit('-',1)[-1])

  if expected_session is not None:request['expected_session']=expected_session

  if room is not None:request['room']=room   # a room of a game hall (many rooms behind one address)

  # The stable per-run ID permits retry after an admission reply was lost.

  if len(request['client_id'])!=32:request['client_id']=uuid.uuid5(uuid.NAMESPACE_URL,str(self.root)).hex

  with socket.create_connection((address(host),port(server_port)),timeout=5) as sock:

   sock.sendall((json.dumps(request)+'\n').encode())

   with sock.makefile('rb') as f:raw=f.readline(8193)

  if len(raw)>8192:raise ValueError('invalid response')

  response=json.loads(raw)

  if not response.get('ok'):raise ValueError(response.get('error','connection failed'))

  # The room is reached at the address the player typed: a room behind a router may name another one in its answer.
  result=dict(response['result']);result['host']=address(host);result['port']=port(server_port)
  self.connect(dict(mode='join',code=encode(result)),name=name,new_room=new_room)

 def launch_dialog(self,mode):

  if self.helper:return

  if mode=='invite':

   invitation=self.mail/'network-invitation.txt'

   if not invitation.exists():return

   args=['--invite',str(invitation)];self.response=None

  else:

   self.response=self.root/('request-'+uuid.uuid4().hex+'.json');args=['--dialog',mode,str(self.response)]

   self.publish('network-status.txt','연결 설정 창에서 선택해 주세요.')

  self.helper=subprocess.Popen([legacy_process_path(HERE/'Augustus-Network.exe'),*[legacy_process_path(a) for a in args]],cwd=launch_cwd(HERE))

 def step(self):

  job=getattr(self,'report_job',None)

  if job and job.done.is_set():

   self.report_job=None

   text='문제 보고 파일을 저장했습니다. 열린 폴더의 ZIP을 전달해 주세요.' if job.result else '문제 보고를 저장하지 못했습니다. 폴더 쓰기 권한을 확인하세요.'

   self.publish('network-status.txt',text)

   if self.bridge:self.bridge.notice_text=text;self.bridge.notice_until=time.monotonic()+12

   if job.result:

    self.publish('diagnostic-result.txt',job.result.name)

    try:

     if os.name=='nt':os.startfile(str(job.result.parent))

    except OSError:pass

  self.visits.poll(getattr(self,'spectator',None) or self.bridge)
  self.spectate_poll()

  self.finish_search()

  hall=getattr(self,'hall',None)

  if hall and hall.created and not self.bridge:   # the room this player just opened in the hall: go in (as its host)

   room,hall.created=hall.created,None

   try:self.hall_join(room,mine=True)

   except (OSError,ValueError,KeyError,RuntimeError) as e:self.publish('hall-status.txt',self.connection_error(e,False))

  if (self.mail/'menu-leave-request.txt').exists():

   self.reset();return

  command=self.mail/'command.txt'

  command_text=read_command(command)

  if command_text is not None:

   verb,_,payload=command_text.partition('\n')

   if verb=='network-report':

    remove_file(command)

    if not getattr(self,'report_job',None):

     from network_diagnostics import ReportJob

     self.report_job=ReportJob();self.report_job.start(self.root,HERE/'reports',HERE)

    self.publish('network-status.txt','문제 보고 파일을 준비하고 있습니다.')

    # Do not pause the bridge while collecting/compressing a report.

    return

   if verb=='network-visit-close':

    remove_file(command);self.visits.close();return

   if verb=='network-visit-city':

    remove_file(command)

    try:self.visits.request(getattr(self,'spectator',None) or self.bridge,int(payload))   # a spectator watches through its session

    except (OSError,ValueError) as e:self.publish('visit-status.txt',str(e));self.visit_notice(str(e))

   elif verb=='open-creator':

    remove_file(command)

    try:

     if self.bridge:raise ValueError('방에서 나온 뒤 제작기를 열어 주세요.')

     if self.creator is None or self.creator.poll() is not None:

      self.creator=subprocess.Popen([legacy_process_path(HERE/'Augustus-Scenario-Creator.exe')],cwd=launch_cwd(HERE))

     self.publish('menu-status.txt','제작기가 열렸습니다. 저장한 뒤 닫으면 목록에 반영됩니다.')

    except (OSError,ValueError) as error:self.publish('menu-status.txt',str(error) if isinstance(error,ValueError) else '제작기를 열지 못했습니다. 배포 파일을 확인해 주세요.')

   elif verb=='network-import-scenario':

    remove_file(command)

    if not self.bridge and self.importer is None:

     self.import_response=self.root/('scenario-import-'+uuid.uuid4().hex+'.json')

     self.importer=subprocess.Popen([legacy_process_path(HERE/'Augustus-Network.exe'),'--scenario-picker',legacy_process_path(self.import_response)],cwd=launch_cwd(HERE))

     self.publish('network-status.txt','파일 선택 창에서 시나리오 또는 공유 ZIP을 선택하세요.')

   elif verb=='network-refresh-starts':

    remove_file(command)

    if not self.bridge:

     try:self.prepare_starts();self.publish('network-status.txt','기본 제공 / 내 작업 / 공동 저장 목록을 새로 불러왔습니다.')

     except (OSError,ValueError):self.publish('network-status.txt','작업 시나리오를 읽지 못했습니다. 파일을 확인해 주세요.')

   elif verb=='update-check':

    remove_file(command);self.update_check()

   elif verb in ('network-save-name','network-forget-name','network-forget-ip'):

    remove_file(command);self.profile_command(verb,payload)

   elif verb in ('hall-enter','server-enter','hall-chat','hall-create','hall-join','hall-leave','hall-country','hall-upload','hall-download','hall-saves','hall-profile','hall-local','hall-briefing','hall-save-delete','hall-admin-login','hall-admin','hall-spectate','spectate-chat','spectate-leave','hall-patch',
                'hall-board','hall-board-post','hall-board-delete'):   # 알림판: missing here since rc6, so its first command stayed in the one mailbox and blocked every later one (user 2026-11-17)

    remove_file(command)

    try:

     if verb=='hall-enter':

      host,sep,name=payload.partition('\n')

      if not sep:raise ValueError('아이디를 입력해 주세요.')

      self.hall_port=type(self).hall_port;self.hall_server=False;self.enter_hall(host.strip(),name)

     elif verb=='server-enter':   # the Korean edition's own server (server_entry.py; the Global edition has no such file)

      try:import server_entry

      except ImportError:raise ValueError('이 판에는 서버 접속이 없습니다. 랜 플레이를 이용해 주세요.')

      if not payload.strip():raise ValueError('아이디를 입력해 주세요.')

      self.publish('hall-entry.txt','');self.publish('hall-status.txt','서버 주소를 확인하고 있습니다.')

      host,self.hall_port=server_entry.address(HERE);self.hall_server=True

      self.enter_hall(host,payload)

     elif verb=='hall-leave':self.leave_hall();self.hall_return=None

     elif verb=='hall-profile':   # 'CC\nname': country and ID together, from the hall's own line (user 2026-11-15)

      import re

      from network_preferences import player_name

      code,_,name=payload.partition('\n');code=code.strip().upper();name=player_name(name)

      if not re.fullmatch('[A-Z]{2}',code):raise ValueError('국가를 다시 골라 주세요.')

      if not getattr(self,'hall',None):raise ValueError('먼저 로비에 들어가 주세요.')

      self.preferences.path.with_suffix('.country.txt').write_text(code,encoding='ascii')

      self.enter_hall(self.hall_host,name);self.publish('network-joined-name.txt',name)

     elif verb=='hall-country':

      import re

      value=payload.strip().upper()

      if not re.fullmatch('[A-Z]{2}',value):raise ValueError('국가를 다시 골라 주세요.')

      self.preferences.path.with_suffix('.country.txt').write_text(value,encoding='ascii')

      if getattr(self,'hall',None):self.enter_hall(self.hall_host,self.hall_name)

     elif not getattr(self,'hall',None):raise ValueError('먼저 로비에 들어가 주세요.')

     elif verb=='hall-chat':self.hall.say(payload.strip())

     elif verb=='hall-create':   # 'scenario id[\nroom title[\nrecovery password[\n1 a developer room]]]'

      key,_,rest=payload.partition('\n');title,_,rest=rest.partition('\n');secret,_,dev=rest.partition('\n');self.hall.open(key.strip(),title.strip(),secret.strip(),dev=dev.strip()=='1')

     elif verb=='hall-saves':self.hall.saves(dev=payload.strip()=='1')   # '1': the 개발자 방 saves (user 2026-11-17)

     elif verb=='hall-briefing':self.hall.briefing(payload.strip())

     elif verb=='hall-save-delete':key,_,secret=payload.partition('\n');self.hall.delete_save(key.strip(),secret)   # the recovery password, if any: never kept

     elif verb=='hall-local':self.hall.set_local(self.local_scenarios())   # the room window opened: 내 저장소 as it is now

     elif verb=='hall-admin-login':self.hall.admin_login(payload)   # the administrator's password (Korean edition), never written anywhere

     elif verb=='hall-admin':parts=(payload.split('\n')+['','',''])[:4];self.hall.admin_command(*[x.strip() for x in parts])   # text, room, person, scenario

     elif verb=='hall-board':self.hall.board(seen=payload.strip()=='1')   # the 알림판 window: '1' open (posts read)
     elif verb=='hall-board-post':   # 'parent id (0 a new post)\npassword\ntext': the password only goes to the hall
      parent,_,rest=payload.partition('\n');password,_,text=rest.partition('\n')
      if not parent.strip().isdigit():raise ValueError('글을 다시 골라 주세요.')
      self.hall.board_post(int(parent),password.strip(),text.strip())
     elif verb=='hall-board-delete':item,_,password=payload.partition('\n');self.hall.board_delete(int(item) if item.strip().isdigit() else -1,password.strip())
     elif verb=='hall-patch':self.hall.patch_notes()   # 패치 기록 (user 2026-11-17)
     elif verb=='hall-upload':self.hall.upload(payload.strip())
     elif verb=='hall-spectate':   # 관전 (user 2026-11-17): a started room whose host allowed it
      self.publish('network-busy.txt','1')
      try:self.hall_spectate(payload.strip())
      finally:self.publish('network-busy.txt','0')
     elif verb=='spectate-chat':
      said=self.spectator.say(payload) if getattr(self,'spectator',None) else ''
      self.publish('spectate-said.txt',('0 '+said) if said else '1')
     elif verb=='spectate-leave':self.spectate_end()

     elif verb=='hall-download':self.hall.download(payload.strip())

     else:

      self.publish('network-busy.txt','1')

      try:self.hall_join(payload.strip())

      finally:self.publish('network-busy.txt','0')

    except (OSError,ValueError,KeyError,RuntimeError) as e:

     self.publish('hall-status.txt',str(e)[:160] if (verb=='server-enter' and isinstance(e,ValueError)) or isinstance(e,NameRefused) else self.connection_error(e,False))

     if verb in ('hall-enter','server-enter'):self.publish('hall-entry.txt','0')

   elif verb=='network-search':

    remove_file(command)

    try:self.start_search(payload.strip())

    except (OSError,ValueError):self.publish('network-status.txt','올바른 방장 IP를 입력해 주세요.')

   elif verb in ('network-host-ip','network-join-ip','network-join-found'):

    if self.bridge:

     remove_file(command);self.publish('network-entry.txt','0');self.publish('network-status.txt','이미 만든 방으로 이동합니다.');return

    self.publish('network-busy.txt','1')

    payload=payload.strip();remove_file(command)

    self.publish('network-status.txt','방을 만들고 있습니다.' if verb=='network-host-ip' else '방에 연결하고 있습니다.')

    try:

     if verb=='network-host-ip':

      if not hasattr(self,'adapters'):self.prepare_choices()

      selection,sep,name=payload.partition('\n')

      from network_preferences import player_name

      if not sep:raise ValueError('아이디를 입력해 주세요.')

      name=player_name(name)

      numbers=[int(x) for x in selection.split()]   # adapter, start, and 1 for a scenario maker's room (user 2026-11-17: both editions)
      if len(numbers) not in (2,3):raise ValueError('select scenario')
      selected,start=numbers[:2];maker=len(numbers)==3 and numbers[2]==1

      if not 0<=selected<len(self.adapters):raise ValueError('select adapter')

      if not 0<=start<len(self.starts):raise ValueError('select scenario')

      choice={k:v for k,v in self.starts[start].items() if k!='label'}

      self.connect(dict(mode='host',address=self.adapters[selected]['address'],port=48921,**choice,**({'dev':True} if maker else {})),name=name)
      self.preferences.update('player_names',name);self.publish_preferences()

     elif verb=='network-join-found':

      host,sep,name=payload.partition('\n')

      if not sep:raise ValueError('아이디를 입력해 주세요.')

      self.join_found(host,name)

     else:self.direct_join(payload)

    except (OSError,ValueError,KeyError,RuntimeError,subprocess.TimeoutExpired) as e:

     from network_diagnostics import record

     record(self.root,'connection_failure',op=verb,outcome='failed',reason=type(e).__name__)

     self.publish('network-status.txt',self.connection_error(e,verb=='network-host-ip'))

     (self.root/'connection-error.log').write_text(traceback.format_exc(),encoding='utf-8')

    finally:self.publish('network-busy.txt','0')

   elif verb in ('network-host','network-join','network-invite'):

    remove_file(command)

    if verb=='network-invite' or not self.bridge:self.launch_dialog(verb.split('-',1)[1])

   # In the hall nothing else reads the mailbox: a command no branch above took is dropped (and noted), never left to
   # block the chat, the 알림판 and every room request after it (rc7, user 2026-11-17).
   if getattr(self,'hall',None) is not None and not self.bridge and read_command(command)==command_text:
    remove_file(command)
    from network_diagnostics import record
    record(self.root,'unknown_command',op=verb[:40],outcome='dropped')

  if self.helper and self.helper.poll() is not None:

   code=self.helper.returncode;self.helper=None

   if code==0 and self.response and self.response.exists():

    try:self.publish('network-status.txt','방에 연결하고 있습니다.');self.connect(json.loads(self.response.read_text(encoding='utf-8-sig')))

    except Exception as error:

     from network_diagnostics import record

     record(self.root,'connection_failure',outcome='failed',reason=type(error).__name__)

     messages={'started room requires shared restore':'이미 시작한 방입니다. 방장이 공동 저장으로 새 방을 만든 뒤 입장해 주세요.','incompatible game executable':'게임 빌드가 다릅니다. 같은 배포본으로 실행해 주세요.','incompatible room version':'멀티플레이 버전이 다릅니다. 같은 배포본을 사용하세요.'}

     text=messages.get(str(error),'연결하지 못했습니다. 네트워크 연결, 방장 IP, 포트와 방화벽을 확인하세요.')

     self.publish('network-status.txt',text)

     (self.root/'connection-error.log').write_text(type(error).__name__+': '+str(error),encoding='utf-8')

   self.response=None

  if self.importer is not None and self.importer.poll() is not None:

   code=self.importer.returncode;self.importer=None

   try:

    if code==0 and self.import_response.exists():

     from scenario_import import import_scenario

     selected=Path(json.loads(self.import_response.read_text(encoding='utf-8-sig'))['path'])

     imported=import_scenario(HERE,selected)

     self.prepare_starts()

     self.publish('network-status.txt',imported['message'])

    else:self.publish('network-status.txt','시나리오 가져오기를 취소했습니다.')

   except (OSError,ValueError,KeyError) as error:self.publish('network-status.txt','가져오기 실패: '+str(error))

   finally:

    if self.import_response:self.import_response.unlink(missing_ok=True)

    self.import_response=None

  if self.creator is not None and self.creator.poll() is not None:

   self.creator=None

   try:

    if not self.bridge:self.prepare_starts()

    self.publish('menu-status.txt','제작기를 닫았습니다. 저장한 시나리오를 방 만들기에서 고르세요.')

   except (OSError,ValueError):self.publish('menu-status.txt','시나리오 목록을 읽지 못했습니다. 작업 파일을 확인해 주세요.')

  if self.bridge:

   self.bridge.step()

   if self.bridge.departed and (self.mail/'room-exit-seen.txt').exists():

    if self.bridge.migration_requested:self.succeed()

    else:self.reset()

 def visit_notice(self,text):

  if self.bridge:

   self.bridge.notice_text=text;self.bridge.notice_until=time.monotonic()+6

  else:self.publish('menu-status.txt',text)

 def run(self,game_data):

  self.prepare_choices()

  try:   # Korean edition: reports that could not be sent last time, and one line that a report went out

   import crash_report

   said=crash_report.announcement(HERE)

   if said:self.publish('network-status.txt',said)

   crash_report.retry_later(HERE)

  except ImportError:pass

  except Exception:pass

  env=os.environ.copy();env['AUGUSTUS_MP_BRIDGE']=str(self.mail);env['AUGUSTUS_KO_USER_PATH']=prepare_profile(HERE,game_data).as_posix()+'/';env['AUGUSTUS_I18N_DIR']=str(HERE/'i18n')  # multilingual catalogs: i18n/<code>.tsv

  (self.root/'user').mkdir(exist_ok=True)

  from network_diagnostics import record
  record(self.root,'native_process',stage='launch')
  try:game=subprocess.Popen([str(HERE/'augustus-mp-ui.exe'),'--windowed',str(game_data)],executable=str(HERE/'augustus-mp-ui.exe'),cwd=launch_cwd(HERE),env=env)
  except OSError as error:
   record(self.root,'native_process',stage='launch',outcome='failed',reason=type(error).__name__)
   raise
  record(self.root,'native_process',stage='running')

  try:

   while game.poll() is None:self.step();time.sleep(.05)

  finally:

   marker=self.mail/'native-start.txt'
   try:last_load=marker.read_text(encoding='ascii')[:64].strip()
   except (OSError,UnicodeError):last_load='unknown'
   if last_load in ('loading','loaded','load_failed'):record(self.root,'native_city_load',stage=last_load,outcome='failed' if last_load=='load_failed' else 'ok')
   code=game.poll()
   record(self.root,'native_process',stage='exit',outcome='ok' if code==0 else 'failed',exit_code=(code & 0xffffffff) if code is not None else 4294967295)
   room=self.bridge.config.get('session','') if self.bridge else ''
   self.disconnect()

   # A settings dialog belongs to this run; do not leave it running after game exit.

   if self.helper and self.helper.poll() is None:self.helper.terminate();self.helper.wait(timeout=5)
   try:   # the Korean edition sends what a crash left behind to the company's server (crash_report.py; not in the Global edition)
    import crash_report
    try:who=(self.mail/'network-joined-name.txt').read_text(encoding='utf-8').strip()
    except (OSError,UnicodeError):who=''
    crash_report.after_exit(HERE,self.root,self.mail,env['AUGUSTUS_KO_USER_PATH'],code,name=who or getattr(self,'hall_name',''),room=room)
   except ImportError:pass
   except Exception as error:record(self.root,'crash_report',outcome='failed',reason=type(error).__name__)



if __name__=='__main__':

 p=argparse.ArgumentParser();p.add_argument('--game-data',type=Path,required=True);a=p.parse_args()

 if not (a.game_data/'c3.sg2').is_file():raise ValueError('Caesar III data folder is missing c3.sg2')

 from prepare_network_data import prepare

 prepared=prepare(a.game_data,HERE/'private-game-data',HERE/'korean')

 try:   # flag cloth and post office roof in player colours, made from this player's own game when missing (caesar3_tints.py)

  import caesar3_tints;caesar3_tints.ensure(a.game_data)

 except Exception:pass   # never in the way of the game: the flags keep their original colours

 os.environ['AUGUSTUS_C3_DATA']=str(prepared)

 Session(HERE/'rooms'/('network-play-'+uuid.uuid4().hex)).run(prepared)

