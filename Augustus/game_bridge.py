"""UI-only mailbox: no city mutation, engine memory access or GUI automation."""
import sys,json,time,uuid,os,base64,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from city_client import Client,NetworkUnavailable
from status_display import status_lines
from mailbox_io import publish_text,read_command,read_live_text,remove_file
import trade_bridge
import command_feedback
from chat_presentation import journal_line,journal_key,key_base
from city_labels import city_name

def side_players(state,me,own,names):
 """Left side panel (players tab), one line per claimed city:
 state(0 ok, 1 late, 2 reconnecting, 3 left/neutral) colour host me name city date ping city-id."""
 from status_display import date_label,ping_label
 out=[]
 for slot in state['slots']:
  if not slot['claimed'] and not slot.get('departed'):continue
  ticks=slot['ticks'];lag=0 if own is None or ticks is None else ticks-own
  if slot.get('departed') or slot.get('dormant'):code=3
  elif not slot['online']:code=2
  elif slot['engine_state']=='stale' or abs(lag)>150 or (slot['age_ms'] or 0)>=3000:code=1
  else:code=0
  color=slot.get('player_color',-1);color=color if type(color)==int and 0<=color<8 else -1
  clean=lambda v:str(v).replace('\t',' ').replace('\n',' ')[:60]
  date=date_label(ticks,state.get('start_year')) if ticks is not None else '입장 전'
  out.append('\t'.join(map(str,[code,color,int(slot['city']==state['host_city']),int(slot['city']==me),clean(slot['name']),clean(city_name(slot['city'],names)),date,ping_label(slot),slot['city']])))
 return '\n'.join(out)+'\n'

class Bridge:
 def __init__(self,config,directory):
  self.config=json.loads(Path(config).read_text());self.root=Path(directory);self.root.mkdir(parents=True,exist_ok=True)
  try:publish_text(self.root/'room-dev.txt','')   # a new room says again whether it is a developer room
  except OSError:pass
  c=self.config
  from connection_config import validate,address,port
  if 'engine_sha256' in c:validate(c)
  elif c['host']!='127.0.0.1':raise ValueError('remote invitation required')
  address(c['host']);port(c['port'])
  self.chat_session=hashlib.sha256(str(c['session']).encode()).hexdigest()[:32]
  self.journal=self.root/'chat-events.txt'
  self.journal_ids=set()
  if self.journal.exists():
   raw=self.journal.read_bytes()
   if raw and not raw.endswith(b'\n'):
    self.journal.with_suffix('.partial-backup').write_bytes(raw)
    self.journal.write_bytes(raw[:raw.rfind(b'\n')+1])
   self.journal_ids={key_base(line.split('\t',1)[0]) for line in self.journal.read_text(encoding='utf-8').splitlines() if '\t' in line}
  self.client=Client(self.root/'client',c['session'],'capua','',(c['host'],c['port']),c['scenario'])
  self.client.engine_progress_file=self.root/'engine.txt'
  self.client.clock_sink=self.accept_clock
  self.succession_armed=False;self.succession_id=None;self.migration_requested=False;self.was_started=False;self.last_autosave=0;self.manual_save_id=None
  self.recovery_plan=None;self.recovery_port=48921;self.endpoint_registered=None
  self.leave_started=None;self.leave_save_id=None;self.is_host=False
  self.departed=False;self.chat_incoming=[];self.chat_seen=0;self.incoming_trade=0;self.joined=False;self.ready=False;self.cursor=0;self.lines=[];self.chat_rows=[];self.pending_id=None;self.serial=0;self.uploaded=set();self.status_lines=[];self.published={};self.failure_since=None;self.notice_until=0;self.notice_text=""
  self.client.chat_after=self.cursor;self.client.chat_sink=self.accept_chat
  import threading;self.clock_lock=threading.Lock();self.clock_grant=-1
 def accept_chat(self,messages):
  for m in messages:
   if m['id']<=self.cursor:continue
   key=journal_key(self.chat_session,m)
   sender=m.get('sender') or city_name(m['city'],getattr(self,'city_names',{}))
   if m.get('whisper_to'):sender=sender+' · 귓속말 ('+str(m['whisper_to'])+'에게)'   # only these two see the line (words, no arrow glyph)
   if key_base(key) not in self.journal_ids:
    with self.journal.open('a',encoding='utf-8',newline='') as f:
     f.write(journal_line(key,sender,m,getattr(self,'chat_phase','lobby')));f.flush();os.fsync(f.fileno())
    self.journal_ids.add(key_base(key))
   if m['city']!=self.client.city:self.chat_incoming.append(m['id'])
   self.lines.append(sender+': '+m['text']);self.chat_rows.append((m.get('player_color',-1),sender,m['text']));self.chat_rows=self.chat_rows[-100:];self.cursor=m['id']
  self.client.chat_after=self.cursor
  self.publish_lobby_chat()
  self.write_changed('chat-cursor.txt',str(self.cursor))
 def close(self):
  try:publish_text(self.root/'room-dev.txt','')   # out of the room: no developer panel in the next game
  except OSError:pass
  if getattr(self,"clock_pump",None):self.clock_pump.close()
  if getattr(self,"observe_task",None):self.observe_task.close()
  if hasattr(self,'replicas'):self.replicas.close()
  if hasattr(self,'upload'):self.upload.close()
 def accept_clock(self,clock):
  """RPC replies (bridge loop and clock pump) publish the native clock mailbox."""
  with self.clock_lock:
   # Two threads may deliver replies out of order; a grant never moves back.
   if clock['grant']<self.clock_grant:return
   self.clock_grant=clock['grant'];self.serial+=1
   publish_text(self.root/'clock.txt',str(self.serial)+' '+str(clock['grant'])+' '+str(clock['speed'])+' '+str(clock.get('save_id',0))+' '+str(int(clock.get('trade_busy',False)))+' '+clock.get('army_token','-'))
  reason=clock.get('wait_reason','unknown')
  if reason not in ('save','trade','army','ceremony','host_pause','objective','peer_stale','none'):reason='unknown'
  if reason!=getattr(self,'clock_reason',None):
   from network_diagnostics import record,ident
   record(self.root,'clock_reason',session=ident(self.client.session),reason=reason,grant=clock['grant'])
   self.clock_reason=reason
 def write_changed(self,name,text):
  if self.published.get(name)==text:return
  publish_text(self.root/name,text)
  self.published[name]=text
  return True
 def publish_spectate(self,state,mine=True):
  """관전 (spectate.py, Korean edition): room-spectate.txt for the waiting room and the 멀티플레이 tab:
  allowed now, allowed at the start, closed, chat level, spectators, the most, then their names (tab separated);
  spectate-mine.txt: whether spectators may watch this player's city, and its revision. Empty without the feature."""
  s=state.get('spectate')
  if not s:self.write_changed('room-spectate.txt','');self.write_changed('spectate-mine.txt','');return
  head=' '.join(str(int(v)) for v in (s['allowed'],s['was_allowed'],s['closed'],s['chat'],s['count'],s['maximum']))
  self.write_changed('room-spectate.txt','\t'.join([head]+[' '.join(str(n).replace('\t',' ').split()) for n in s.get('names',[])]))
  if not mine:return
  me=getattr(self.client,'city',None)
  row=next((r for r in state.get('observe_permissions',[]) if r['owner']==me and r['viewer']=='~spectator'),None)
  self.write_changed('spectate-mine.txt','%d %d'%((row['allowed'],row['revision']) if row else (1,0)))
 def publish_lobby_chat(self):
  host,port=self.client.address
  self.write_changed('lobby-chat.txt','\n'.join([f'방장 IP: {host} / 포트: {port}']+self.lines[-12:]))
  # The address sits in the waiting-room header so it never scrolls out of the chat.
  self.write_changed('room-address.txt',f'{host}:{port}')
  rows=getattr(self,'chat_rows',[])[-100:]   # the waiting room chat scrolls (five lines show)
  clean=lambda value:str(value).replace('\t',' ').replace('\r',' ').replace('\n',' ')
  self.write_changed('lobby-chat-colors.txt','AUGCHAT1\n'+'\n'.join(str(c if type(c)==int and -1<=c<8 else -1)+'\t'+clean(n)+'\t'+clean(t) for c,n,t in rows))
 def publish_slots(self,state):
  self.route_player_colors={s['city']:s.get('player_color',-1) for s in state['slots']}
  empire_colors=[]
  for slot in state['slots']:
   name_id=slot.get('name_id',0);color=slot.get('player_color',-1)
   if not slot.get('claimed') or slot.get('departed'):color=-1   # nobody plays this city (never taken, or its player left): white flag
   if type(name_id)==int and name_id>0:
    empire_colors.append(f"{name_id} {color if type(color)==int and 0<=color<8 else -1}")
  self.write_changed('empire-player-colors.txt','\n'.join(empire_colors)+'\n')
  try:   # display-only empire map trade paths; never holds up the bridge
   import empire_route_display
   empire_route_display.publish(self,state)
  except (OSError,ValueError,KeyError,TypeError):pass
  import autosave_policy
  if state.get('host_city')==self.client.city:
   enabled,seconds=autosave_policy.read_preferences(Path(__file__).parent)
   self.write_changed('joint-save-options.txt',f'{int(enabled)} {seconds}')
  if 'room_options' in state:
   options=state['room_options'];self.room_options=options
   locked=options['locked'] or state.get('start',{}).get('phase','lobby')!='lobby'
   body='AUGROOM2\n'+self.config['session']+'\n'+str(options['revision'])+' '+str(int(locked))+' '+str(int(options['initialized']))+'\n'+' '.join(map(str,options['values']))+'\n'
   self.write_changed('room-options.txt',body)
   if options['initialized']:self.write_changed('room-options-worker.txt',' '.join(map(str,options['values'])))
   try:ack=(self.root/'room-options-ack.txt').read_text(encoding='ascii').split()
   except OSError:ack=[]
   identity=(self.config['session'],str(options['revision']))
   if ack==list(identity) and getattr(self,'options_ack_sent',None)!=identity and options['initialized']:
    self.client.call('room_options_ack',invite=self.config['invite'],revision=options['revision']);self.options_ack_sent=identity

  if 'lobby_overview' in state:self.write_changed('lobby-overview.txt',state['lobby_overview'])
  # Race for the Throne public feed (throne_events.public_status): anonymous coup notices for the original message
  # inbox (the game keys each by its id, so a resend or a reload never shows it twice). The paranoia display is the
  # player's own value only (throne_client).
  throne=state.get('throne') or {}
  from scenario_overview import clean
  # Popup notices only (first coup, stage-4 success); failures and the end are fanfare lines (throne_client.fanfare).
  self.write_changed('throne-events.txt',''.join(f"{n['id']}\t{clean(n['title'])}\t{n['body'].replace(chr(9),' ').replace(chr(13),'').replace(chr(10),' ')}\n" for n in throne.get('notices',[]) if len(n['id'])==32 and n.get('popup',True))
   +(getattr(self,'throne_private_events','') if throne or state.get('progress') else ''))   # + this player's own expedition warning (throne_client.raid_sync)
  import throne_client;throne_client.fanfare(self,throne);throne_client.sync(self,state)   # own paranoia display, own openings, hand-in after a restore
  import participant_admin
  participant_admin.publish(self,state)
  host=next((s for s in state['slots'] if s['city']==state['host_city']),None)
  version=host.get('client_version') if host else None
  def short(v):return 'v'+v['upstream'].split('-')[0]+' / '+v['package']
  # Both lines in every window, the host's too, from the moment each enters the room: the room learns versions on entry
  # (lobby_client_version), not when a city is chosen (user 2026-11-13).
  if isinstance(state.get('host_version'),dict):version=state['host_version']
  host_label='방장 버전: '+short(version) if version else '방장 버전: 확인 중'
  self.write_changed('lobby-host-version.txt',host_label)
  try:
   from client_version import local_info
   own=local_info()
   # second line of the waiting room header; '!' in front asks the game to draw it in red (differs from the host)
   differs=bool(version) and own!=version
   own_label=('!' if differs else '')+'내 버전: '+short(own)+((' (방장과 다름)' if short(own)!=short(version) else ' (실행 파일 다름)') if differs else '')
  except (OSError,ValueError,KeyError):own_label='내 버전: 확인하지 못했습니다'
  self.write_changed('lobby-own-version.txt',own_label)
  import lobby_map
  self.write_changed('lobby-map.txt',lobby_map.encode(self,state))
  lines=[];roster=[];choices=[]
  self.city_names={x['city']:x.get('city_name',city_name(x['city'])) for x in state['slots']}
  self.city_ids={x['city'] for x in state['slots']}
  import affiliation;affiliation.publish(self,state)   # trade post partner / soldier owner hover text
  self.write_changed('empire-dormant-cities.txt','\n'.join(str(x.get('name_id',0)) for x in state['slots'] if x.get('dormant') or x.get('departed')))
  rome=next((c for c in state.get('empire_map',[]) if isinstance(c,dict) and c.get('rome')),None)   # fixed capital, display only (rome_capital.py)
  rome_ok=rome and type(rome.get('x'))==int and type(rome.get('y'))==int and 0<=rome['x']<=2000 and 0<=rome['y']<=1000
  if rome_ok:   # line 1 place, then name, then the description split into two lines at a sentence end (user 2026-11-13)
   import rome_capital
   one=lambda value:' '.join(str(value or '').split())[:300]
   words=one(rome_capital.texts().get('description')).split(' ')
   ends=[i+1 for i,w in enumerate(words[:-1]) if w.endswith(('.','!','?'))]   # sentence ends; the most even split wins
   cut=min(ends,key=lambda i:abs(len(' '.join(words[:i]))-len(' '.join(words[i:]))),default=len(words))
   rome_text='\n'.join([f"{rome['x']} {rome['y']}",one(rome_capital.spec().get('name','로마')),' '.join(words[:cut]),' '.join(words[cut:])])+'\n'
  self.write_changed('empire-rome.txt',rome_text if rome_ok else '')
  # whose city (user 2026-11-17: the ID beside the city, on the empire map and over a watched city): name id, player
  self.player_names={x['city']:x['player_name'] for x in state['slots'] if x.get('player_name') and x.get('claimed') and not x.get('departed')}
  self.write_changed('empire-player-names.txt','\n'.join(str(x.get('name_id',0))+'\t'+' '.join(str(self.player_names[x['city']]).split()) for x in state['slots'] if x['city'] in self.player_names))
  self.write_changed('empire-player-slots.txt','\n'.join(str(x.get('name_id',0))+'\t'+x['city']+'\t'+self.city_names[x['city']] for x in state['slots']))
  for slot in state['slots']:
   label=self.city_names[slot['city']]+(' [저장 도시]' if slot.get('saved_city') else '')
   mine=self.joined and slot['city']==self.client.city
   available=not slot['claimed'] or mine
   choices.append(str(int(available))+'\t'+slot['city']+'\t'+label+' / '+('선택 가능' if not slot['claimed'] else slot['name']))
   state_label='방장' if slot['city']==state['host_city'] else '준비 완료' if slot['ready'] else '준비 중'
   if not slot['online']:state_label='연결 대기'
   elif slot['city']!=state['host_city'] and not mine:   # one's own ping is not shown on one's own row (user 2026-11-13)
    from status_display import lobby_ping
    state_label+=lobby_ping(slot)
   roster.append(label+' / '+(slot['name']+' / '+state_label if slot['claimed'] else '빈 자리 · 저장된 진행 보존' if slot.get('saved_city') else '빈 자리 · 시작하면 중립도시'))
   if not slot['claimed']:lines.append('선택 가능');continue
   owner='나' if self.joined and slot['city']==self.client.city else '상대'
   suffix='준비' if slot['ready'] else '선택됨'
   if not slot['online']:suffix='연결 없음'
   lines.append(owner+' / '+suffix)
  self.write_changed('slots.txt','\n'.join(lines)+'\n')
  order=sorted(range(len(state['slots'])),key=lambda i:state['slots'][i]['city']!=state['host_city'])
  self.write_changed('lobby-roster.txt','\n'.join(roster[i] for i in order))
  import lobby_counts
  self.write_changed('lobby-counts.txt',lobby_counts.lines(state))   # '참가 6 · 도시 선택 5 · 준비 3' beside the roster title
  self.write_changed('city-choices.txt','\n'.join(choices))
  if self.joined:
   own=next(x for x in state['slots'] if x['city']==self.client.city)
   self.write_changed('own-city.txt',self.city_names[self.client.city])
   self.write_changed('ready.txt','1' if own['ready'] else '0')
 def publish(self,status):
  if time.monotonic()<self.notice_until:status=self.notice_text
  self.write_changed('lobby-error.txt',self.notice_text if time.monotonic()<self.notice_until else '')
  summary=status.split(' / ',1)[0]
  self.write_changed('ingame-status.txt','' if (summary in ('공동 저장 없음','도시를 선택하세요.') or summary.startswith(('공동 저장 중 #','공동 저장 완료 #','남은 도시 저장 완료 #'))) and time.monotonic()>=self.notice_until else summary)
  text=status+'\n'+'\n'.join(self.status_lines+self.lines[-max(1,12-len(self.status_lines)):])
  self.write_changed('state.txt',text)
 def tick(self):
  if self.departed:return
  self.handling_command=None
  command=self.root/'command.txt'
  command_text=read_command(command)
  if command_text is not None:
   verb,_,text=command_text.partition('\n')
   # Session owns these commands; leave them in place but keep ticking.
   # Returning here stopped clock reports and froze every city (shared clock).
   if verb.startswith('network-') or verb=='open-creator':command_text=None
  if command_text is not None:
   command_feedback.begin(self,command_text);self.handling_command=command_text
   defer_leave=False
   if verb=='leave' and self.is_host and self.was_started and getattr(self,'has_peer',True):
    if self.leave_started is None:self.leave_started=time.monotonic()
    if time.monotonic()-self.leave_started<20:
     if self.leave_save_id is None:
      try:self.leave_save_id=self.client.call('save_begin',request_id=uuid.uuid4().hex,kind='manual')['id']
      except ValueError:pass # an active trade/save may briefly prevent a new barrier
     replicas=self.client.call('succession_status')['replicas']
     if not self.leave_save_id or not all(any(r['city']==peer and r['save_id']>=self.leave_save_id for r in replicas) for peer in getattr(self,'active_peer_ids',[])):
      defer_leave=True;verb='refresh'
      self.notice_text='나가기 전 공동 저장을 참가자에게 전달하고 있습니다.';self.notice_until=time.monotonic()+2
   if verb=='leave':
    try:self.client.call('lobby_leave',invite=self.config['invite'])
    except OSError:pass # Leaving locally must remain possible during a lost VPN connection.
    self.close();self.departed=True;self.write_changed('auto-enter.txt','0');self.write_changed('room-exit.txt','left');remove_file(command);return
   elif verb=='observe-permission':
    target,generation,revision,allowed=text.strip().split('\n')
    if allowed not in ('0','1'):raise ValueError('잘못된 관전 설정입니다.')
    result=self.client.call('observe_permission_set',target=target,generation=generation,revision=int(revision),allowed=allowed=='1')
    import participant_admin
    participant_admin.apply_local(self,target,result['allowed'],result['revision'])
    if target=='~spectator':   # every spectator (spectate.py): the 관전 part of the 멀티플레이 tab
     self.write_changed('spectate-mine.txt','%d %d'%(int(result['allowed']),result['revision']))
     self.write_changed('admin-result.txt','관전자가 내 도시를 볼 수 있습니다.' if result['allowed'] else '관전자가 내 도시를 볼 수 없습니다.')
    else:
     who=getattr(self,'city_names',{}).get(target,target)
     self.write_changed('admin-result.txt',f"{who}: 내 도시 관람을 {'허용합니다' if result['allowed'] else '막았습니다. 관람 중이었다면 바로 끝납니다'}.")
   elif verb=='spectate-set':   # the host's 관전 settings (spectate.py): 'allowed 0|1', 'chat 0|1|2' or 'kick'
    key,_,value=text.strip().partition(' ')
    if key=='allowed' and value in ('0','1'):fields=dict(allowed=value=='1')
    elif key=='chat' and value in ('0','1','2'):fields=dict(chat=int(value))
    elif key=='kick':fields=dict(kick=True)
    else:raise ValueError('잘못된 관전 설정입니다.')
    view=self.client.call('spectate_settings',**fields)
    self.publish_spectate(dict(spectate=view),mine=False)   # at once; the player's own line is not part of this answer
    self.write_changed('admin-result.txt','관전 설정을 바꿨습니다.')
   elif verb=='participant-remove':
    target,sep,generation=text.strip().partition('\n')
    if not sep:raise ValueError('participant changed')
    self.client.call('participant_remove',target=target,generation=generation)
    self.write_changed('admin-result.txt','선택한 참가자의 연결을 해제했습니다.')
   elif verb=='preview-city':
    from city_preview import ask
    ask(self,text)
   elif verb=='choose-city' or verb in getattr(self,'city_ids',{'capua','tarentum'}):
    if verb=='choose-city':verb,_,text=text.partition('\n')
    if verb not in getattr(self,'city_ids',{'capua','tarentum'}):raise ValueError('invalid city')
    previous=self.client.city
    self.client.city=verb
    try:joined=self.client.call('lobby_join',invite=self.config['invite'])
    except Exception:self.client.city=previous;raise
    if not self.joined:self.lines=[];self.chat_rows=[]
    self.client.token=joined['token'];self.joined=True
    if previous!=verb:
     (self.root/'play.sav').unlink(missing_ok=True)
     self.write_changed('auto-enter.txt','0')
    if text.strip():self.client.call('player_name',name=text.strip()[:24])
   elif verb in ('play','start'):
    if not self.joined:raise ValueError('먼저 도시를 선택하세요.')
    self.client.call('room_start')
   elif verb=='start-cancel':   # the host stops the start under way (waiting room, button 3 while starting)
    if not self.joined:raise ValueError('먼저 도시를 선택하세요.')
    self.client.call('room_start_cancel')
   elif verb=='joint-save-settings':
    state=self.client.call('lobby_status')
    if state['host_city']!=self.client.city:raise ValueError('host only')
    import autosave_policy
    fields=text.split()
    if len(fields)!=2 or fields[0] not in ('0','1'):raise ValueError('invalid joint save toggle')
    autosave_policy.set_interval(Path(__file__).parent,int(fields[1]),fields[0]=='1')
    self.autosave_settings_checked=float('-inf')
    self.write_changed('joint-save-result.txt','자동 공동 저장 설정을 보관했습니다.')
   elif verb=='save':
    if self.pending_id is None:self.pending_id=uuid.uuid4().hex
    self.manual_save_id=self.client.call('save_begin',request_id=self.pending_id,kind='manual')['id']
   elif verb=='cancel_save':
    self.client.call('save_cancel')
   elif verb.startswith('speed'):
    self.client.call('room_speed',speed=int(verb[5:]))
   elif verb=='color':
    # waiting room: my player colour (0..7), after a city is chosen
    if not self.joined:raise ValueError('먼저 도시를 선택하세요.')
    self.client.call('lobby_color',invite=self.config['invite'],color=int(text))
   elif verb=='ready':
    if not self.joined:raise ValueError('먼저 도시를 선택하세요.')
    self.client.call('lobby_ready',ready=not self.ready)
   elif verb=='army':
    if not self.joined:raise ValueError('먼저 도시를 선택하세요.')
    if self.pending_id is None:self.pending_id=uuid.uuid4().hex
    from army_bridge import command as army_command
    army_command(self,text,self.pending_id)
   elif verb=='trade':
    if not self.joined:raise ValueError('먼저 도시 선택')
    if self.pending_id is None:self.pending_id=uuid.uuid4().hex
    trade_bridge.ui_command(self.client,text,self.pending_id)
   elif verb=='throne':   # 황위 시험 규칙 v1 panel (throne_client.command); the command id is the spend's request id
    if not self.joined:raise ValueError('먼저 도시를 선택하세요.')
    if self.pending_id is None:self.pending_id=uuid.uuid4().hex
    if getattr(self,'progress_own',None) is not None:
     import progress_client;progress_client.command(self,text,self.pending_id)
    else:
     import throne_client;throne_client.command(self,text,self.pending_id)
   elif verb=='room-options-set':
    import room_options
    parts=list(map(int,text.split()))
    if len(parts)!=1+len(room_options.SCHEMA):raise ValueError('방 옵션 개수 오류')
    accepted=self.client.call('room_options_set',invite=self.config['invite'],revision=parts[0],values=parts[1:])
    if getattr(self,'host_options_path',None) is not None:
     import host_options_profile
     try:host_options_profile.save(self.host_options_path,accepted['values'])
     except OSError:
      self.notice_text='방 옵션은 적용됐지만 다음 방에 쓸 설정을 저장하지 못했습니다. 다시 적용해 주세요.';self.notice_until=time.monotonic()+10
   elif verb=='send':
    if self.pending_id is None:self.pending_id=uuid.uuid4().hex
    if self.joined:self.client.call('chat_send',message_id=self.pending_id,text=text)
    else:self.client.call('lobby_chat_send',invite=self.config['invite'],message_id=self.pending_id,text=text)
    self.write_changed('chat-sent.txt',self.pending_id+'\n'+text)
   elif verb=='whisper':   # 'city\ntext' from the in-game chat bar (user 2026-11-13)
    if not self.joined:raise ValueError('먼저 도시를 선택하세요.')
    to,_,body=text.partition('\n')
    if self.pending_id is None:self.pending_id=uuid.uuid4().hex
    self.client.call('chat_send',message_id=self.pending_id,text=body,to=to)
    self.write_changed('chat-sent.txt',self.pending_id+'\n'+body)
   elif verb!='refresh':raise ValueError('지원하지 않는 명령')
   if not defer_leave:
    command_feedback.finish(self)
    remove_file(command);self.pending_id=None
   self.handling_command=None;self.command_faults=0
  if self.joined:
   # The round's routine polls in one round trip (city_client.Client.begin_round). After the command above, so the
   # answers already show what that command changed. The engine's progress is sampled here, as the clock report
   # further down used to sample it.
   sample_ticks=None
   try:
    progress=self.root/'engine.txt'
    if progress.exists() and time.time()-progress.stat().st_mtime<1.0:
     sample=read_live_text(progress);sample_ticks=int(sample.strip()) if sample is not None else None
   except (OSError,ValueError):sample_ticks=None
   self.client.begin_round(sample_ticks)
  from city_preview import poll_bridge
  poll_bridge(self)
  entry=(self.client.session,self.config.get('invite'))
  if getattr(self,'version_entered',None)!=entry:   # own version on entering the waiting room, before choosing a city
   from client_version import local_info
   try:self.client.call('lobby_client_version',invite=self.config['invite'],info=local_info())
   except (ValueError,OSError,KeyError):pass   # display only: never stops the waiting room
   self.version_entered=entry
  if not self.joined:
   state=self.client.call('lobby_view',invite=self.config['invite']);self.publish_slots(state);self.write_changed('role.txt',str(state['viewer_role']))
   self.lines=[(m.get('sender') or '시스템')+': '+m['text'] for m in state.get('lobby_messages',[])]
   self.chat_rows=[(m.get('player_color',-1),m.get('sender') or '시스템',m['text']) for m in state.get('lobby_messages',[])]
   self.publish_lobby_chat();self.publish('도시를 선택하세요.');return
  identity=(self.client.session,self.client.city,self.client.token)
  if getattr(self,'version_registered',None)!=identity:
   from client_version import local_info
   self.client.call('client_version',info=local_info());self.version_registered=identity
  ping_start=time.monotonic();state=self.client.call('lobby_heartbeat',rtt_ms=getattr(self,'rtt_ms',0));self.rtt_ms=self.client.prefetch_ms if getattr(self.client,'last_cached',False) and getattr(self.client,'prefetch_ms',None) is not None else round((time.monotonic()-ping_start)*1000);self.publish_slots(state);parts=[]
  try:import diag_relay   # Korean edition test tool (EDITIONS.md); absent in the global edition
  except ImportError:diag_relay=None
  if diag_relay:diag_relay.poll_bridge(self,state)   # only while the developer collects (state['diag']); never raises
  self.maker_room=bool(state.get('dev'))   # kept for a new host (migration.py, recovery_group.py: maker_room.mark)
  self.write_changed('room-dev.txt','1 '+(','.join(state.get('dev_tools') or []) or '-') if state.get('dev') else '')   # a maker room: '1' and the keys its scenario allows ('-' none); the game shows its panel (multiplayer_dev.inc)
  self.publish_spectate(state)
  from army_bridge import poll as army_poll
  if state['start']['phase']=='started':
   import affiliation
   recorder=affiliation.Recorder(self.client);self.client=recorder   # keeps the overview army_poll already asks for
   try:army_poll(self)
   finally:self.client=recorder.client
   if recorder.army_rows is not None:affiliation.publish(self,rows=recorder.army_rows)
  import objectives
  objectives.publish(self,state.get('objectives',{'mode':'free-build'}))
  goals=state.get('objectives',{})
  completed=goals.get('completed_tick') is not None
  self.write_changed('objective-completed.txt',goals['run_id']+'\n'+objectives.lines(goals,self.city_names,self.client.city) if completed else '')
  endpoint=(self.client.local_address,self.recovery_port)
  if self.endpoint_registered!=endpoint:
   self.client.call('recovery_endpoint',host=endpoint[0],port=endpoint[1]);self.endpoint_registered=endpoint
  version=state.get('layout_version')
  if version and getattr(self,'layout_version',None)!=version:
   (self.root/'play.sav').unlink(missing_ok=True);self.layout_version=version
   # Roster replacement invalidates all earlier checkpoint/election authority.
   self.succession_armed=False;self.succession_id=None;self.recovery_plan=None
  native=self.root/'native-start.txt'
  if native.exists():
   value=native.read_text(encoding='ascii')[:64].strip()
   if value in ('loading','loaded','load_failed') and value!=getattr(self,'native_start_trace',None):
    from network_diagnostics import record,ident
    record(self.root,'native_city_load',session=ident(self.client.session),stage=value,outcome='failed' if value=='load_failed' else 'ok');self.native_start_trace=value
  phase=state['start']['phase'];self.was_started=phase=='started';self.chat_phase=phase
  self.client.clock_enabled=phase=='started'
  if phase!='started':self.clock_grant=-1
  import clock_pump
  clock_pump.poll(self)
  trace=(phase,state['start'].get('attempt',''))
  if getattr(self,'start_trace',None)!=trace:
   from network_diagnostics import record,ident
   record(self.root,'start_phase',session=ident(self.client.session),attempt=ident(trace[1]),phase=phase)
   self.start_trace=trace
  self.active_peer_ids=[x['city'] for x in state['slots'] if x['city']!=self.client.city and x['claimed'] and not x.get('departed',False)]
  self.has_peer=any(x['city']!=self.client.city and x['online'] and x['claimed'] for x in state['slots'])
  self.own_name=next(x['name'] for x in state['slots'] if x['city']==self.client.city)
  self.peer_name=next((x['name'] for x in state['slots'] if x['city']!=self.client.city),'이전 방장')
  self.write_changed('start-state.txt',phase+' '+str(state['start']['remaining']))
  if phase in ('loading','countdown','started'):
   begin=self.client.call('play_begin')
   self.write_changed('origin.txt',str(begin['start_ticks']))
   import scenario_briefing;self.write_changed('start-message.txt',scenario_briefing.start_message_file(begin.get('start_message')))   # authored start message: one confirm window, once
   target=self.root/'play.sav'
   expected=state['start'].get('hashes',{}).get(self.client.city)
   if not target.exists() or (expected and hashlib.sha256(target.read_bytes()).hexdigest()!=expected):
    from network_diagnostics import record,ident
    record(self.root,'start_download',session=ident(self.client.session),stage='begin')
    sav,rec,active=self.client.remote_snapshot()
    if active:raise ValueError('거래 처리 중')
    if expected and hashlib.sha256(sav).hexdigest()!=expected:raise ValueError('start snapshot mismatch')
    tmp=self.root/'play.tmp';tmp.write_bytes(sav);os.replace(tmp,target)
    record(self.root,'start_download',session=ident(self.client.session),stage='verified',bytes=len(sav))
   if phase=='loading':
    gate=state['start'];self.client.call('start_loaded',attempt=gate['attempt'],layout=gate['layout'],save_hash=hashlib.sha256(target.read_bytes()).hexdigest())
  self.write_changed('auto-enter.txt','1' if phase=='started' else '0')
  role='1' if state['host_city']==self.client.city else '2'
  self.is_host=role=='1'
  target=self.root/'role.txt'
  if not target.exists() or target.read_text()!=role:
   tmp=self.root/'role.tmp';tmp.write_text(role);os.replace(tmp,target)
  for s in state['slots']:
   if s['city']==self.client.city:self.ready=s['ready']
   parts.append(city_name(s['city'],self.city_names)+(' [방장]' if s['city']==state['host_city'] else '')+': '+('준비' if s['ready'] else '접속' if s['online'] else '대기'))
  self.accept_chat(self.client.call('chat_read',after=self.cursor)['messages'])
  self.publish_lobby_chat()
  if phase!='started':
   # Avoid serial trade/save/military polling before play (many transoceanic RTTs).
   detail=state['start'].get('detail','')
   self.write_changed('start-detail.txt',detail)
   self.write_changed('debug-status.txt',f"서버 왕복 {self.rtt_ms}ms / 시작 단계 {phase}")
   self.is_host=state['host_city']==self.client.city
   self.publish(detail if detail else '곧 게임을 시작합니다.' if phase=='countdown' else '참가자 준비를 기다립니다.')
   return
  reported_ticks=None
  engine=self.root/'engine.txt'
  if engine.exists() and time.time()-engine.stat().st_mtime<1.0:
   sample=read_live_text(engine)
   ticks=int(sample.strip()) if sample is not None else None
   if ticks is not None:
    ahead=self.client.take_clock() if hasattr(self.client,'take_clock') else None   # sent with this round's batch
    if ahead is not None:ticks,clock=ahead
    else:clock=self.client.call('clock',ticks=ticks)
    reported_ticks=ticks
    if getattr(self,'first_progress_trace',None)!=trace:
     from network_diagnostics import record,ident
     record(self.root,'start_first_progress',session=ident(self.client.session),attempt=ident(trace[1]),ticks=ticks);self.first_progress_trace=trace
    self.accept_clock(clock)
    objectives.poll_bridge(self,clock,reported_ticks)
    self.diag_clock=(clock,reported_ticks)   # for developer diagnostics summaries (diag_relay)
    import celebration
    celebration.poll_bridge(self,clock,reported_ticks)
  import army_live_bridge
  try:army_live_bridge.poll(self)
  except (OSError,ValueError):pass
  import observe_bridge
  observe_bridge.poll(self)
  saved=self.client.call('save_status')
  import cash_bridge
  try:cash_bridge.poll(self,bool(saved['pending']))
  except (OSError,ValueError) as error:
   self.cash_exchange=None;self.cash_next=time.monotonic()+10
   if time.monotonic()>=getattr(self,'cash_error_next',0):
    from network_diagnostics import record
    record(self.root,'cash_exchange_failed',reason=type(error).__name__)
    self.cash_error_next=time.monotonic()+60
  if not hasattr(self,'upload'):
   from save_upload import Upload
   self.upload=Upload()
  self.upload.poll(self,saved['pending'],reported_ticks)
  # Upload is asynchronous; refresh completion on the next poll, not a second RTT now.
  if not hasattr(self,'replicas'):
   from replica_worker import Replicas
   self.replicas=Replicas()
  from replica_worker import recovery_save
  self.last_throne_recovery=state.get('throne')
  self.replicas.poll(self,recovery_save(state,saved))
  replica=getattr(self,'replicated_id',None)
  # A save the room has not armed yet is asked about again every 2 s, not every round: one round trip less per
  # round at a high ping (2026-11-15). A new save is acknowledged at once.
  if replica and role=='2' and self.succession_id!=replica and (replica!=getattr(self,'replica_asked',None) or time.monotonic()>=getattr(self,'replica_ask_next',0)):
   self.replica_asked=replica;self.replica_ask_next=time.monotonic()+2
   ack=self.client.call('replica_ack',id=replica)
   if ack['armed']:
    self.succession_armed=True;self.succession_id=replica
  # Always discard a previous group plan when the roster becomes two-player.
  # Otherwise promote() prefers that stale plan over the latest acknowledged save.
  plan=self.client.call('recovery_plan') if len(state['slots'])>2 else None
  self.recovery_plan=plan if plan and self.client.city in plan['guests'] else None
  if self.recovery_plan:
   self.succession_armed=True;self.succession_id=plan['save_id']
  elif len(state['slots'])>2:
   self.succession_armed=False;self.succession_id=None
  # Optional host recovery save; disabled by default. Manual/transaction saves unchanged.
  import autosave_policy
  autosave_policy.poll(self,Path(__file__).parent,role,phase,reported_ticks,saved['pending'],complete=saved['complete'])
  if self.manual_save_id is not None and saved['complete'] and saved['complete']['id']==self.manual_save_id:
   self.notice_text='직접 요청한 공동 저장을 완료했습니다.';self.notice_until=time.monotonic()+4;self.manual_save_id=None
  label=('공동 저장 중입니다. 완료 후 자동으로 계속됩니다. #'+str(saved['pending']['id'])) if saved['pending'] else (('남은 도시 저장 완료 #' if saved['complete'].get('remaining') else '공동 저장 완료 #')+str(saved['complete']['id'])) if saved['complete'] else '공동 저장 없음'
  import army_install
  army_install.poll(self)
  state=self.client.call('lobby_status');self.status_lines=status_lines(state,saved)+trade_bridge.poll(self)
  if self.transfer_busy:self.status_lines[len(state['slots'])]='거래 처리 중 - 저장 확정, 당사자 반영 대기'
  seen=self.root/'chat-seen.txt'
  try:
   value=int(seen.read_text().strip()) if seen.exists() else 0
   self.chat_seen=max(self.chat_seen,min(value,self.cursor))
  except (OSError,ValueError):pass
  self.chat_incoming=[i for i in self.chat_incoming if i>self.chat_seen]
  self.write_changed('chat-cursor.txt',str(self.cursor))
  self.write_changed('alerts.txt',f"{len(self.chat_incoming)} {self.incoming_trade}")
  from status_display import date_label,ping_label
  own=next((x['ticks'] for x in state['slots'] if x['city']==self.client.city),None)
  debug=['플레이어 / 방장 RTT / 도시 / 날짜 / 진행 차이 / 마지막 보고']
  for slot in state['slots']:
   city=city_name(slot['city'],self.city_names)
   ticks=slot['ticks'];delta='대기' if own is None or ticks is None else f'{ticks-own:+d}틱'
   age='미수신' if slot['age_ms'] is None else str(slot['age_ms']//1000)+'초 전'
   name=slot['name']+(' [방장]' if slot['city']==state['host_city'] else '')
   debug.append(f"{name} / {ping_label(slot)} / {city} / {date_label(ticks,state.get('start_year')) if ticks is not None else '입장 전'} / {delta} / {age}")
  debug.append(f"방장 목표 {state['target_speed']}% / 서버 왕복 {self.rtt_ms}ms / 내 실행 {own if own is not None else '-'}틱")
  interval=getattr(self,'autosave_interval',0)
  setting=('끄기' if not interval else str(interval)+'초') if role=='1' else '방장 설정에 따름'
  debug.append(label+' / 자동 저장: '+setting)
  self.write_changed('debug-status.txt','\n'.join(debug))
  self.write_changed('side-players.txt',side_players(state,self.client.city,own,self.city_names))
  peer=next((x for x in state['slots'] if x['city']!=self.client.city),None)
  if peer:self.write_changed('trade-peer.txt',peer['name']+' ('+city_name(peer['city'],self.city_names)+')')
  recipients=[x for x in state['slots'] if x['city']!=self.client.city and x['claimed']]
  self.write_changed('trade-recipients.txt','\n'.join(x['city']+'\t'+str(int(x['online']))+'\t'+x['name']+' / '+city_name(x['city'],self.city_names) for x in recipients))
  host=city_name(state['host_city'],self.city_names) if state['host_city'] is not None else '도시 선택 대기'
  self.lines=self.lines[-100:];self.publish(label+' / 방장 '+host+' / 목표 '+str(state['target_speed'])+'%')
 def connection_exit(self,event,message):
  self.close()
  throne=getattr(self,'last_throne_recovery',None)
  older=bool(throne and throne.get('sealed_save') and getattr(self,'succession_id',None) and throne['sealed_save']>self.succession_id)
  if older and event in ('closed','disconnected','fenced'):
   # A fallback to an older throne save loses progress. Leave the choice to the host's explicit restore flow.
   # Do not auto-promote first and disclose the rollback afterwards.
   self.departed=True;self.migration_requested=False
   self.write_changed('auto-enter.txt','0')
   self.write_changed('room-exit-detail.txt',message+' 최신 공동 저장 #'+str(throne['sealed_save'])+'은 개인 자료 보관 확인이 끝나지 않았습니다. 인계 가능한 이전 저장 #'+str(self.succession_id)+'을 보존했습니다. 방 만들기에서 해당 저장을 선택해 이어할 수 있습니다. 선택한 저장 이후의 진행은 되돌아갑니다. 자동으로 되돌리지 않았습니다.')
   self.write_changed('room-exit.txt',event);return
  if getattr(self,'was_started',False) and getattr(self,'succession_armed',False) and event in ('closed','disconnected','fenced'):
   self.migration_requested=True;self.departed=True
   self.write_changed('auto-enter.txt','0');self.write_changed('room-exit.txt','migrate');return
  self.close();self.departed=True;self.write_changed('auto-enter.txt','0')
  replica=getattr(self,'replicated_id',None)
  recovery=('방 만들기에서 저장 #'+str(replica)+'으로 이어할 수 있습니다. 저장 이후 진행은 제외됩니다.') if replica else '이 PC에 확인된 복제 저장본이 없습니다. 방장 PC의 저장본이 필요합니다.'
  self.write_changed('room-exit-detail.txt',message+' '+recovery)
  self.write_changed('room-exit.txt',event)
 @staticmethod
 def error_message(error):
  messages={'start snapshot mismatch':'도시 파일 검증에 실패했습니다. 다시 시도해 주세요.','stale start acknowledgement':'시작 시도가 변경되었습니다. 새 시작 준비를 기다립니다.','start in progress':'시작 준비 중입니다. 잠시 기다려 주세요.',
   'participant required':'플레이할 도시를 선택해 주세요.',
   'select player trading post':'출발할 플레이어 교역소를 선택해 주세요.',
   'player trading post unavailable':'교역소와 도시 출입구까지 이어지는 길을 확인해 주세요.',
   'player trading post order queue full':'교역소 주문 대기열이 가득 찼습니다. 일부 주문을 마친 뒤 보내 주세요.',
   'city order queue full':'도시의 주문 대기열이 가득 찼습니다. 일부 주문을 마친 뒤 보내 주세요.',
   'legacy solo unsupported':'이전 2인 예제는 혼자 시작할 수 없습니다. 제작기의 새 시나리오를 선택해 주세요.',
   'restore requires assigned cities':'이어하기는 저장된 모든 도시의 담당자를 선택해 주세요. 빈 도시 전환은 새 게임에서 지원합니다.',
   'transfer busy':'다른 거래를 운송 또는 처리하고 있습니다. 완료 후 새 제안을 보내세요.',
   'save busy':'공동 저장 중입니다. 저장 완료 후 거래를 보내세요.',
   'save in progress':'공동 저장 중입니다. 잠시 후 다시 시도하세요.',
   'room full':'방의 참가 자리가 모두 찼습니다.',
   'participants must choose cities':'도시를 고르지 않은 참가자가 있습니다. 모두 도시를 고른 뒤 시작해 주세요.',
   'throne needs two players':'황위 쟁탈전은 두 명 이상이 있어야 시작할 수 있습니다.',
   **{'needs players %d'%n:'이 시나리오는 %d명 이상이 있어야 시작할 수 있습니다.'%n for n in range(2,7)},
   'too many players':'한 번에 플레이할 수 있는 인원은 최대 6명입니다. 도시를 고른 사람이 6명 이하가 되게 해 주세요.',
   'participants must be ready':'모든 참가자가 도시를 선택하고 준비를 마쳐야 시작할 수 있습니다.',
   'remaining save blocked by trade':'교역 변경 또는 미완료 운송이 있어 남은 도시 저장을 만들 수 없습니다. 마지막 공동 저장은 보존됩니다.',
   'participant left; paired save unavailable':'참가자가 나가 공동 저장할 수 없습니다. 마지막 공동 저장으로 이어 주세요.',
   'participant left; trade suspended':'참가자가 나가 교역이 대기 중입니다.',
   'host only':'방장만 게임을 시작하거나 속도를 변경할 수 있습니다.',
   'city occupied':'다른 플레이어가 선택한 도시입니다.',
   'game already started':'진행 중인 방에는 새로 참가하거나 도시를 변경할 수 없습니다.',
   'start already finished':'게임이 이미 시작되어 취소할 수 없습니다.',
   'transaction pending':'진행 중인 거래를 마친 뒤 다시 시도해 주세요.',
   'invalid name':'아이디는 공백이 아닌 24자 이내로 입력해 주세요.',
   'host fenced':'이전 방장의 진행 권한을 중단했습니다. 참가자가 저장본에서 이어받습니다.',
   'removed by host':'방장이 연결을 해제했습니다. 진행 중인 방에는 바로 재입장할 수 없습니다.',
   'participant changed':'참가자가 변경되었습니다. 목록에서 다시 선택해 주세요.',
   'cannot remove host':'방장 자신의 연결은 해제할 수 없습니다.',
   'host required':'방장만 사용할 수 있습니다.',
   'both engines required':'상대 도시의 응답을 기다리고 있습니다. 잠시 후 다시 보내 주세요.',
   'participant unavailable':'상대 플레이어의 연결을 기다리고 있습니다. 잠시 후 다시 시도해 주세요.',
   'amount':'수량과 금액을 확인해 주세요. 물품은 1~32포대, 금액은 1~1,000,000 데나리입니다.',
   'fields':'수량과 금액을 확인해 주세요.',
   'invalid recipient':'받는 사람을 다시 선택해 주세요.',
   'stale offer':'이미 처리된 제안입니다. 목록을 다시 확인해 주세요.',
   'already committed':'이미 확정된 거래라 취소할 수 없습니다.',
   'recipient consent required':'받는 사람만 수락할 수 있습니다.',
   'cancelled offer':'취소된 제안입니다.',
   'both trading posts required':'양쪽 도시에 상대 도시 전용 교역소가 필요합니다.',
   'conflicting duplicate':'같은 요청이 다른 내용으로 이미 처리되었습니다. 다시 작성해 주세요.',
   'participant timed out':'연결이 오래 끊겨 방에서 퇴장 처리되었습니다.',
   'room closed':'방장이 나가서 방이 종료되었습니다.', 'room left':'방에서 나왔습니다.'}
  if error in messages:return messages[error]
  # Room rules already explain themselves in Korean (e.g. '판매자의 보유 물품을 선택하세요.'): show them as they are.
  if any('\uac00'<=ch<='\ud7a3' for ch in error) and len(error)<=160:return error
  from error_text import reason   # the cause in a few words, so a report says which rule refused (user 2026-11-13)
  return '요청을 처리하지 못했습니다(원인: '+reason(error,70)+'). 잠시 후 다시 시도해 주세요.'
 def step(self):
  from clock_metrics import poll
  poll(self)
  attempted_at=time.monotonic()
  try:self.tick();self.failure_since=None
  except ValueError as error:
   from network_diagnostics import record,ident
   # The exact rejection text, kept on this PC only (the shared diagnostics keep 'request_rejected'): without it a
   # "요청을 처리하지 못했습니다" notice cannot be traced back to its cause (user report 2026-11-13).
   try:
    log=self.root/'rejections.log'
    if log.is_file() and log.stat().st_size>65536:log.replace(self.root/'rejections.previous.log')
    with log.open('a',encoding='utf-8') as out:out.write(time.strftime('%Y-%m-%d %H:%M:%S')+'\t'+' '.join(str(error).split())[:300]+'\t'+self.error_message(str(error))+'\n')
   except OSError:pass
   reason=str(error) if str(error) in ('start snapshot mismatch','stale start acknowledgement','invalid server frame','room closed','room left','participant timed out','host fenced','removed by host') else 'request_rejected'
   record(self.root,'bridge_validation',session=ident(self.client.session),peer=ident(self.client.city),outcome='failed',reason=reason)
   self.failure_since=None
   failed=self.root/'command.txt'
   if failed.exists() and failed.read_text(encoding='utf-8').startswith(('participant-remove\n','observe-permission\n')):
    self.write_changed('admin-result.txt',self.error_message(str(error)))
   if failed.exists() and failed.read_text(encoding='utf-8').startswith('send\n'):
    self.write_changed('chat-failed.txt',failed.read_text(encoding='utf-8').partition('\n')[2])
   if failed.exists() and failed.read_text(encoding='utf-8').startswith('whisper\n'):   # give back the words, not the receiver line
    self.write_changed('chat-failed.txt',failed.read_text(encoding='utf-8').partition('\n')[2].partition('\n')[2])
   if str(error) in ('room closed','room left','participant timed out','host fenced','removed by host'):
    if str(error) in ('participant timed out','removed by host'):self.succession_armed=False
    self.connection_exit('removed' if str(error)=='removed by host' else 'fenced' if str(error)=='host fenced' else 'closed' if str(error)=='room closed' else 'disconnected' if str(error)=='participant timed out' else 'left',self.error_message(str(error)))
   command_feedback.finish(self,self.error_message(str(error)));self.command_faults=0
   (self.root/'command.txt').unlink(missing_ok=True);self.pending_id=None;self.notice_text=self.error_message(str(error));self.notice_until=time.monotonic()+5;self.publish(self.notice_text)
  except NetworkUnavailable:
   if self.failure_since is None:self.failure_since=attempted_at
   elapsed=time.monotonic()-self.failure_since
   if elapsed>=30:
    self.connection_exit('disconnected','서버 연결을 30초 동안 복구하지 못했습니다.')
   elif elapsed>=2:
    try:self.publish('서버 재연결 대기 중입니다. 입력 내용은 보존됩니다.')
    except OSError:pass
  except Exception as error:   # any local fault (disk, engine, or a plain bug): say which, keep the session running
   from network_diagnostics import record,ident
   record(self.root,'local_failure',session=ident(self.client.session),outcome='failed',reason=type(error).__name__)
   # Local-only traceback: identify the file/operation instead of guessing disk space.
   # Kept outside exported diagnostic reports; exception text can contain local paths.
   import traceback
   if time.monotonic()>=getattr(self,'local_error_log_next',0):
    self.local_error_log_next=time.monotonic()+5
    try:(self.root/'local-last-error.log').write_text(time.strftime('%Y-%m-%d %H:%M:%S')+'\n'+traceback.format_exc(),encoding='utf-8')
    except OSError:pass
   # A local disk/engine failure is not evidence that the host disappeared.
   from error_text import where
   self.notice_text='로컬 처리 오류: '+where(error)+' / local-last-error.log';self.notice_until=time.monotonic()+8
   try:self.publish(self.notice_text)
   except OSError:pass
   # A command whose own handling keeps failing locally was tried again every round, and the game waited for its
   # answer for good (2026-11-15). After three tries in a row it is given up, with the reason, like a refusal.
   failed=getattr(self,'handling_command',None)
   if failed is not None:
    self.command_faults=getattr(self,'command_faults',0)+1
    if self.command_faults>=3:
     try:command_feedback.finish(self,self.notice_text);remove_file(self.root/'command.txt')
     except OSError:pass
     self.handling_command=None;self.command_faults=0;self.pending_id=None
 def run(self):
  try:
   while not (self.root/'stop').exists():
    self.step();time.sleep(0.05)
  finally:self.close()

if __name__=='__main__':Bridge(sys.argv[1],sys.argv[2]).run()
