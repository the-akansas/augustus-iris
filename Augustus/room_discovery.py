"""Read-only room discovery. Does not issue invitations, heartbeats or city claims."""
import json,socket,time
from contextlib import closing
from connection_config import address,port,engine_hash
from coordinator import PROTOCOL,BUILD,sha
from network_preferences import display_line

def attach(server,room,manifest,configs,admitted,admission_time,host_seat=None):
 def public_info(request):
  if request!={'op':'public_info','version':1}:raise ValueError('invalid query')
  with room.lock,closing(room.coordinator.connect()) as db:
   closed=bool(db.execute('SELECT 1 FROM room_closed').fetchone())
   phase='closed' if closed else 'started' if room.started else 'preparing' if getattr(room,'roster_job',None) else 'countdown' if room.start_at is not None else 'lobby'
   first=db.execute('SELECT city FROM lobby_invite ORDER BY rowid LIMIT 1').fetchone()
   name=db.execute('SELECT name FROM player_name WHERE city=?',(first[0],)).fetchone() if first and first[0] else None
   occupied=1 if host_seat is None or host_seat['client'] is not None or (first and first[0]) else 0   # a dedicated room has nobody in the host's seat until the first player comes
   for index,cfg in enumerate(configs[1:]):
    key=sha(cfg['invite'].encode())
    row=db.execute('SELECT city FROM lobby_invite WHERE token=?',(key,)).fetchone()
    left=db.execute('SELECT 1 FROM departed_invite WHERE token=?',(key,)).fetchone()
    if row and not left and (row[0] is not None or index in admitted and time.monotonic()-max(admission_time[index],room.last_seen(key))<=30):occupied+=1
   from multiplayer_limits import MAX_ONLINE_PLAYERS
   maximum=min(len(configs),MAX_ONLINE_PLAYERS)   # 8 seats: at most 6 play, so at most 6 come in (room_host.public_join)
   return dict(version=1,session=room.coordinator.session,room=display_line(manifest['title'])+' 방',host=display_line(name[0]) if name else '방장 (도시 선택 전)',scenario=display_line(manifest['title']),players=min(occupied,maximum),maximum=maximum,phase=phase,joinable=phase=='lobby' and occupied<maximum,protocol=PROTOCOL,build=BUILD,engine_sha256=configs[0]['engine_sha256'])
 server.public_info=public_info

def probe(host,server_port=48921):
 host=address(host);port(server_port);start=time.monotonic()
 with socket.create_connection((host,server_port),timeout=3) as sock:
  sock.settimeout(3);sock.sendall(b'{"op":"public_info","version":1}\n')
  with sock.makefile('rb') as stream:raw=stream.readline(8193)
 if len(raw)>8192 or not raw.endswith(b'\n'):raise ValueError('invalid discovery response')
 response=json.loads(raw)
 if not isinstance(response,dict) or not response.get('ok'):raise ValueError('검색을 지원하지 않는 방이거나 응답을 읽을 수 없습니다.')
 r=response['result']
 if not isinstance(r,dict) or r.get('version')!=1:raise ValueError('invalid discovery version')
 for key in ('session','room','host','scenario','build','engine_sha256'):
  if not isinstance(r.get(key),str) or len(r[key])>450:raise ValueError('invalid discovery text')
 if r.get('phase') not in ('lobby','preparing','countdown','started','closed'):raise ValueError('invalid discovery phase')
 if type(r.get('players'))!=int or type(r.get('maximum'))!=int or not 0<=r['players']<=r['maximum']<=8 or type(r.get('joinable'))!=bool:raise ValueError('invalid discovery count')
 r['compatible']=r.get('protocol')==PROTOCOL and r['build']==BUILD and r['engine_sha256']==engine_hash()
 r['ping_ms']=max(0,round((time.monotonic()-start)*1000));r['address']=host;r['checked']=time.monotonic()
 return r

def summary(r):
 phases={'lobby':'대기 중','preparing':'시작 준비 중','countdown':'시작 준비 중','started':'게임 중','closed':'종료됨'}
 return '\n'.join([display_line(r['room']), '방장: '+display_line(r['host']), '시나리오: '+display_line(r['scenario']),f"참가 {r['players']} / {r['maximum']}명 / {phases[r['phase']]} / 핑 {r['ping_ms']}ms",'같은 게임 버전 / '+('입장 가능' if r['joinable'] else '현재 입장 불가') if r['compatible'] else '게임 버전이 다릅니다. 같은 배포본을 사용하세요.', '마지막 확인 '+time.strftime('%H:%M:%S')])

def refusal(r):
 """Why this room cannot be entered now (the search answer). Shown in red; one line."""
 if not r['compatible']:return '게임 버전이 다릅니다. 같은 배포본을 사용하세요.'
 if r['phase']=='closed':return '종료된 방입니다.'
 if r['phase']=='started':return '이미 게임을 시작한 방이라 입장할 수 없습니다.'
 if r['phase']!='lobby':return '게임 시작 준비 중이라 지금은 입장할 수 없습니다.'
 if r['players']>=r['maximum']:return f"방이 가득 찼습니다({r['players']}/{r['maximum']}명). 자리가 나면 다시 검색해 주세요."
 return '지금은 입장할 수 없는 방입니다. 잠시 후 다시 검색해 주세요.'
