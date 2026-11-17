from windows_paths import filesystem_path, launch_cwd
"""Latest-only read-only live replica. Worker owns channels and network lifecycle."""
import os,subprocess,threading,time,uuid
from pathlib import Path
from city_client import HERE,game_data
from mailbox_io import publish_text
from observe_codec import decode,digest,to_initial_save
from observe_channel import Channel,FRAME_CAP
from observe_bridge import clone

# The city-view renderer runs without the multiplayer bridge (no AUGUSTUS_MP_*), so it would draw every player colour
# (trade post roofs, pennants, soldiers) as the neutral grey. It gets copies of the observer's own colour tables in
# its visit folder instead (route_post.c reads them there only when no bridge is set). Display only.
COLOR_FILES=('route-player-colors.txt','army-colors.txt','empire-player-colors.txt')
def share_colors(bridge,folder,seen):
 for name in COLOR_FILES:
  try:text=(bridge.root/name).read_text(encoding='utf8')
  except OSError:continue
  if seen.get(name)!=text:publish_text(folder/name,text);seen[name]=text

class Visits:
 def __init__(self,root,notify):
  self.root=Path(root);self.notify=notify;self.process=None;self.thread=None;self.directory=None;self.bridge=None
  self.lock=threading.Lock();self.desired=None;self.generation=0;self.completed=0;self.errors=[];self.applied=0;self.deltas=0;self.full=0
 def request(self,bridge,name_id):
  if not bridge or not getattr(bridge,'joined',False) or not getattr(bridge,'was_started',False):raise ValueError('게임 시작 후 관전할 수 있습니다.')
  rows=(bridge.root/'empire-player-slots.txt').read_text(encoding='utf8').splitlines()
  target=next((r.split('\t')[1] for r in rows if r.split('\t')[0]==str(name_id)),None)
  if not target or target==bridge.client.city:raise ValueError('다른 플레이어 도시를 선택해 주세요.')
  with self.lock:
   if self.desired and self.desired[1]==target and self.bridge is bridge:
    # Re-publish after a repeated native click clears the ready marker.
    if self.directory and self.process and self.process.poll() is None:
     marker=bridge.root/'visit-ready.txt'
     try:ready=marker.read_text(encoding='utf8')
     except FileNotFoundError:ready=''
     except OSError:return  # Retry on the next poll if a reader holds the marker.
     if ready!=str(self.directory):publish_text(marker,str(self.directory))
    return
   self.generation=max(self.generation+1,time.time_ns());self.bridge=bridge
   label=bridge.city_names.get(target,target);player=getattr(bridge,'player_names',{}).get(target)   # the city and whose it is
   self.desired=(self.generation,target,label+' · '+player if player else label,bridge)
   publish_text(bridge.root/'visit-ready.txt','');publish_text(bridge.root/'visit-status.txt','실시간 도시 연결 중입니다.')
   if not self.thread or not self.thread.is_alive():
    self.thread=threading.Thread(target=self._run,daemon=True,name='city-state-viewer');self.thread.start()
 def _current(self,g):
  with self.lock:return self.desired is not None and self.desired[0]==g
 def _run(self):
  while True:
   with self.lock:
    job=self.desired
    if job is None:self.thread=None;return
   generation,target,label,bridge=job
   folder=self.root/('visit-'+uuid.uuid4().hex);folder.mkdir(parents=True)
   state=Channel(folder,'view-state');frames=Channel(folder,'view-frame',FRAME_CAP);process=None
   client=clone(bridge.client,folder/'network');data=None;epoch=seq=local=0;colors={}
   waiting_since=time.monotonic()
   try:
    while self._current(generation):
     try:
      refresh=folder/'visit-refresh.txt'
      if refresh.exists():refresh.unlink();epoch=seq=0
      part=client.call('observe_get',target=target,watch=generation,epoch=epoch,after=seq,hash=digest(data) if data else '')
      if not self._current(generation):break
      if part.get('denied'):
       with self.lock:
        if self._current_unlocked(generation):
         self.desired=None
         publish_text(bridge.root/'visit-ready.txt','')
         publish_text(bridge.root/'visit-denied.txt','1')
         publish_text(bridge.root/'visit-status.txt','이 플레이어가 자기 도시 관전을 허용하지 않았습니다.')
         self.notify('상대 플레이어가 관전을 허용하지 않아 내 도시로 돌아갑니다.')
       break
      if not part.get('available'):
       if time.monotonic()-waiting_since>=20:
        raise RuntimeError('상대 도시 상태를 20초 동안 받지 못했습니다. 내 도시로 돌아가 다시 시도해 주세요.')
       time.sleep(.1);continue
      if part['epoch']<epoch or (part['epoch']==epoch and part['sequence']<seq):raise ValueError('관전 상태 순서가 잘못되었습니다.')
      if part['epoch']!=epoch or part['sequence']!=seq:
       try:new=decode(data,part['delta'])
       except ValueError:
        data=None;epoch=seq=0;raise
       data=new;epoch=part['epoch'];seq=part['sequence'];local+=1
       if not process:
        (folder/'initial.sav').write_bytes(to_initial_save(data))
        publish_text(folder/'visit-meta.txt','initial.sav\n'+' '.join(str(label).split())[:100]+'\n')
       state.write(data,local,part['ticks']);self.applied+=1;self.deltas+=bool(part['delta']['base']);self.full+=not bool(part['delta']['base'])
      status='연결 지연: 마지막으로 받은 상태를 표시합니다.' if part.get('stale') else '관전 화면을 지연 재생하고 있습니다.'
      share_colors(bridge,folder,colors)
      publish_text(folder/'visit-status.txt',status)
      if not process:
       env={k:v for k,v in os.environ.items() if not k.startswith('AUGUSTUS_MP_') and k!='AUGUSTUS_CITY_VISIT'}
       user=folder/'user';user.mkdir();env.update(AUGUSTUS_CITY_VISIT=str(folder),AUGUSTUS_KO_USER_PATH=user.as_posix()+'/',SDL_AUDIODRIVER='dummy',SDL_VIDEODRIVER='dummy',SDL_RENDER_DRIVER='software')
       exe=Path(os.environ.get('AUGUSTUS_VIEWER_EXE',str(HERE/'augustus-mp-ui.exe')))
       with (folder/'renderer.log').open('wb') as log:process=subprocess.Popen([str(filesystem_path(exe)),'--windowed',str(game_data())],executable=str(filesystem_path(exe)),cwd=launch_cwd(exe.parent),env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
       with self.lock:
        if self._current_unlocked(generation):
         self.process=process;self.directory=folder;publish_text(bridge.root/'visit-ready.txt',str(folder))
      if process.poll() is not None:raise RuntimeError('관전 렌더가 종료되었습니다.')
      if self._current(generation):publish_text(bridge.root/'visit-status.txt',status)
      time.sleep(.08)
     except (OSError,ValueError) as e:
      self.errors.append(str(e));self.errors=self.errors[-20:]
      if self._current(generation):publish_text(bridge.root/'visit-status.txt','도시 연결 복구 중: '+str(e))
      time.sleep(.2)
   except Exception as e:
    self.errors.append(str(e))
    with self.lock:
     if self._current_unlocked(generation):publish_text(bridge.root/'visit-status.txt','관전을 준비하지 못했습니다. '+str(e));publish_text(bridge.root/'visit-denied.txt','1');self.notify('관전 연결 실패: '+str(e));self.desired=None
   finally:
    if process and process.poll() is None:
     process.terminate()
     try:process.wait(timeout=3)
     except subprocess.TimeoutExpired:process.kill();process.wait(timeout=3)
    state.close();frames.close()
    with self.lock:
     if self.process is process:self.process=None;self.directory=None
    try:client.call('observe_leave',watch=generation)
    except (OSError,ValueError):pass
    self.completed+=1
 def _current_unlocked(self,g):return self.desired is not None and self.desired[0]==g
 def poll(self,bridge):
  if self.bridge and (bridge is not self.bridge or getattr(bridge,'departed',False)):self.close()
 def close(self):
  with self.lock:
   self.desired=None;self.generation+=1
   if self.process and self.process.poll() is None:self.process.terminate()
   if self.bridge:publish_text(self.bridge.root/'visit-ready.txt','')
   self.bridge=None
