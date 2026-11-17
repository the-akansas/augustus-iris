"""Read-only lobby overview derived from the host's actual city snapshot."""
import hashlib,json,threading,uuid
from pathlib import Path
_workers=threading.Semaphore(1)

def terrain_grid(data):
    w,h=data['width'],data['height'];flags=data['terrain_flags']
    if type(w)!=int or type(h)!=int or not 1<=w<=160 or not 1<=h<=160 or len(flags)!=w*h:raise ValueError('invalid preview map')
    def tile(f):
        if type(f)!=int or not 0<=f<1<<24:raise ValueError('invalid terrain flag')
        if f & (8|16384|32768):return 'B'
        if f & (64|256|1966080):return 'D'
        if f & 4:return 'W'
        if f & (2|512):return 'R'
        if f & (1|16):return 'T'
        if f & (2048|32):return 'F'
        return 'L'
    return dict(width=w,height=h,grid=''.join(map(tile,flags)))

def request(room,db,city):
    if not isinstance(city,str) or city not in room.coordinator.scenario['cities']:raise ValueError('invalid city')
    if room.started or room.start_at is not None or getattr(room,'roster_job',None):return dict(city=city,status='unavailable')
    row=db.execute('SELECT save,receipt FROM city WHERE id=?',(city,)).fetchone()
    if not row:return dict(city=city,status='unavailable')
    sav,rec=bytes(row[0]),bytes(row[1]);key=hashlib.sha256(sav+rec).hexdigest()
    if not hasattr(room,'city_previews'):room.city_previews={}
    cached=room.city_previews.get(city)
    if cached and cached['key']==key and cached['result'].get('status')!='error':return dict(city=city,**cached['result'])   # a failed build is tried again
    cached=dict(key=key,result=dict(status='pending'));room.city_previews[city]=cached
    context=getattr(room,'restore_expansion',None)
    saved=city in context['restored']['parts'] if context else (Path(room.coordinator.path).parent/'restored-from.json').exists()
    def build():
        try:
            from city_client import Engine,HERE
            with _workers:
                stage=HERE/'lobby-preview-cache'/uuid.uuid4().hex;stage.mkdir(parents=True)
                (stage/'city.sav').write_bytes(sav);(stage/'receipt.bin').write_bytes(rec)
                Engine().run('inspect',stage,stage/'view')
                result=terrain_grid(json.loads((stage/'view/terrain.json').read_text()))
                audit=stage/'view/roster-audit.json'
                if audit.exists():
                    grid=list(result['grid']);w,h=result['width'],result['height']
                    for b in json.loads(audit.read_text())['buildings']:
                        if len(b)<8:continue
                        x,y,size=b[5:8]
                        if any(type(v)!=int for v in (x,y,size)) or not 0<=x<w or not 0<=y<h or not 1<=size<=16:continue
                        for dy in range(y,min(h,y+size)):
                            for dx in range(x,min(w,x+size)):grid[dy*w+dx]='B'
                    result['grid']=''.join(grid)
                result.update(status='ready',caption='공동 저장의 도시 모습' if saved else '시작할 때의 도시 모습')
            cached['result']=result
        except Exception:
            cached['result']=dict(status='error')
    thread=threading.Thread(target=build,daemon=True);cached['thread']=thread;thread.start()
    return dict(city=city,status='pending')

def ask(bridge,city):
    """Start showing `city`'s map: at once from this bridge's own copy, otherwise by asking the room."""
    if city not in getattr(bridge,'city_ids',set()):raise ValueError('invalid city')
    known=cached(bridge,city)
    if known:   # a city seen before in this room shows at once, no request
        bridge.preview_city=None;bridge.write_changed('city-preview.txt',known);bridge.write_changed('city-preview-status.txt','');bridge.write_changed('city-preview-busy.txt','0')
        return
    bridge.write_changed('city-preview-busy.txt','1')
    bridge.preview_city=city;bridge.preview_next=0
    bridge.write_changed('city-preview.txt','');bridge.write_changed('city-preview-status.txt','도시 지도를 불러오는 중입니다.')

def hover_request(bridge):
    """The waiting room's hover card asks through its own file (preview-request.txt: city id, then a counter), never through
    command.txt: a hover request there held the one command slot, and a city click right after it was dropped (user
    2026-11-13: 'clicks get eaten, it takes a double click')."""
    root=getattr(bridge,'root',None)
    if root is None:return
    try:text=(root/'preview-request.txt').read_text(encoding='utf-8')
    except (OSError,UnicodeDecodeError):return
    if not text or text==getattr(bridge,'preview_request_seen',None):return
    bridge.preview_request_seen=text
    city=text.split('\n',1)[0].strip()
    try:ask(bridge,city)
    except ValueError:pass

def poll_bridge(bridge):
    import time
    hover_request(bridge)
    city=getattr(bridge,'preview_city',None)
    if not city or time.monotonic()<getattr(bridge,'preview_next',0):return
    bridge.preview_next=time.monotonic()+.5
    result=bridge.client.call('lobby_preview',invite=bridge.config['invite'],preview_city=city)
    status=result.get('status')
    if result.get('city')!=city:raise ValueError('preview city mismatch')
    if status=='ready':
        w,h=result.get('width'),result.get('height');grid=result.get('grid')
        if type(w)!=int or type(h)!=int or not 1<=w<=160 or not 1<=h<=160 or not isinstance(grid,str) or len(grid)!=w*h or set(grid)-set('BDWRTFL'):raise ValueError('invalid city preview')
        payload=city+'\n'+str(w)+' '+str(h)+'\n'+grid+'\n'+str(result.get('caption',''))[:200]
        bridge.__dict__.setdefault('preview_cache',{})[(bridge.client.session,city)]=payload   # hover again: shown at once (cached())
        bridge.write_changed('city-preview.txt',payload)
        bridge.write_changed('city-preview-status.txt','')
        bridge.write_changed('city-preview-busy.txt','0')
        bridge.preview_next=time.monotonic()+3600
    else:
        bridge.write_changed('city-preview.txt','')
        bridge.write_changed('city-preview-status.txt','도시 지도를 불러오는 중입니다.' if status=='pending' else '미리보기를 불러오지 못했습니다. 잠시 후 다시 확인해 주세요.' if status=='error' else '게임 시작 준비 중에는 미리보기를 볼 수 없습니다.')
        bridge.write_changed('city-preview-busy.txt','1' if status=='pending' else '0')
        if status!='pending':bridge.preview_next=time.monotonic()+3600

def cached(bridge,city):
    """A city map this bridge already received in this room (the lobby city files do not change before the start)."""
    return getattr(bridge,'preview_cache',{}).get((bridge.client.session,city))
