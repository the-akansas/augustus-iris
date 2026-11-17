"""Pictures of the buildings and of the game's build-menu buttons for the scenario editor's build list (user 2026-11-15:
"like the game's build panel on the right, friendlier"). The engine worker draws them from the owner's own game files
(engine_worker.c building-pictures, building_pictures.h) into the editor's private cache; nothing is shipped or
exported. A missing picture only leaves that building without one."""
import hashlib,json,os,shutil,struct,subprocess,sys,uuid
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from creator_enemy_images import png

VERSION='v4'   # v3: the granary's and the triumphal arch's upper picture (2026-11-15); v4: warehouse hut, standing wall (2026-11-17)
OVERLAY={71:(-32,-64),56:(4,-51),72:(-4,-42)}   # type: where the game draws its second picture (widget/city/building_ghost.c)
SILENT=('Using default audio driver: dummy','Audio output disabled: no playback device opened')

def _rgba(raw):
    """Engine pixels (color_t ARGB, little endian: B G R A) to RGBA."""
    out=bytearray(len(raw))
    out[0::4]=raw[2::4];out[1::4]=raw[1::4];out[2::4]=raw[0::4];out[3::4]=raw[3::4]
    return out

def _paste(canvas,cw,ch,rgba,w,h,x,y):
    for row in range(h):
        ty=y+row
        if ty<0 or ty>=ch:continue
        for col in range(w):
            tx=x+col
            if tx<0 or tx>=cw:continue
            s=(row*w+col)*4
            if rgba[s+3]==0:continue
            d=(ty*cw+tx)*4;canvas[d:d+4]=rgba[s:s+4]

def _crop(canvas,cw,ch):
    rows=[y for y in range(ch) if any(canvas[(y*cw+x)*4+3] for x in range(cw))]
    if not rows:return None
    cols=[x for x in range(cw) if any(canvas[(y*cw+x)*4+3] for y in rows)]
    x0,x1,y0,y1=cols[0],cols[-1]+1,rows[0],rows[-1]+1
    out=bytearray()
    for y in range(y0,y1):out+=canvas[(y*cw+x0)*4:(y*cw+x1)*4]
    return x1-x0,y1-y0,out

def compose(folder,kind,key,planes):
    """planes: {part: (width,height,x_offset,y_offset,original_width,original_height,isometric)} -> (w,h,rgba)."""
    def load(part):
        w,h=planes[part][0],planes[part][1]
        raw=(Path(folder)/f'{kind}-{key}-{part}.bgra').read_bytes()
        if len(raw)!=w*h*4:raise ValueError('picture size')
        return _rgba(raw)
    if 2 in planes:   # one whole picture
        w,h=planes[2][:2];return _crop(load(2),w,h)
    w,h,x,y,ow,oh,iso=planes[0]
    if not iso:
        cw,ch=max(ow,w+x),max(oh,h+y);canvas=bytearray(cw*ch*4);_paste(canvas,cw,ch,load(0),w,h,x,y);return _crop(canvas,cw,ch)
    tiles=max(1,(w+2)//60)
    top=planes.get(1)
    top_height=top[5] if top else 0
    foot_y=max(0,top_height-15*tiles)
    # every part at its place, footprint at (0,foot_y); the drawing area grows to hold an overlay above or beside it
    parts=[(load(0),w,h,0,foot_y)]
    if top:parts.append((load(1),top[0],top[1],top[2],top[3]))
    extra=planes.get(3)
    if extra and int(key) in OVERLAY:   # ghost origin = footprint x + 30*(tiles-1) (graphics/image.c), the renderer adds the offsets
        dx,dy=OVERLAY[int(key)];parts.append((load(3),extra[0],extra[1],30*(tiles-1)+dx+extra[2],foot_y+dy+extra[3]))
    x0=min(0,min(p[3] for p in parts));y0=min(0,min(p[4] for p in parts))
    cw=max(p[3]+p[1] for p in parts)-x0;ch=max(max(p[4]+p[2] for p in parts),top_height)-y0;canvas=bytearray(cw*ch*4)
    for rgba,pw,ph,px,py in parts:_paste(canvas,cw,ch,rgba,pw,ph,px-x0,py-y0)
    return _crop(canvas,cw,ch)

def read_list(folder):
    found={}
    for line in (Path(folder)/'pictures.txt').read_text().splitlines():
        p=line.split()
        if len(p)!=10:continue
        found.setdefault((p[0],int(p[1])),{})[int(p[2])]=tuple(int(v) for v in p[3:])
    return found

def prepare(target=None):
    from city_client import game_data,launch_cwd
    data=game_data();exe=HERE/'engine-city-test.exe'
    catalog=json.loads((HERE/'building-catalog.json').read_text(encoding='utf-8-sig'))
    types=','.join(str(b['id']) for b in catalog)
    key=hashlib.sha256((str(Path(data).resolve())+'\n'+types+'\n'+VERSION).encode()+hashlib.sha256(exe.read_bytes()).digest()).hexdigest()[:20]
    root=Path(target or HERE/'creator-cache'/'building-pictures')
    done=root/key/'pictures.json'
    if done.is_file():return json.loads(done.read_text(encoding='utf8'))
    work=root/('work-'+uuid.uuid4().hex);work.mkdir(parents=True)
    try:
        user=work/'user';user.mkdir()
        env=os.environ.copy();env['AUGUSTUS_KO_USER_PATH']=user.as_posix()+'/';env.pop('AUGUSTUS_ROOM_OPTIONS_FILE',None)
        with (work/'engine.log').open('wb') as log:
            p=subprocess.run([str(exe),str(data),'building-pictures',types,str(work),'0','0','0'],executable=str(exe),cwd=launch_cwd(HERE),env=env,stdout=log,stderr=subprocess.STDOUT,timeout=90)
        text=(work/'engine.log').read_text(errors='replace')
        # Only pictures: the worker must have run silent and finished; a picture it could not draw is simply absent.
        if p.returncode or not any(m in text for m in SILENT):raise RuntimeError('건물 그림을 만들지 못했습니다. 로그: '+str(work/'engine.log'))
        out=root/key;out.mkdir(parents=True,exist_ok=True)
        result=dict(buildings={},menu={})
        for (kind,number),planes in read_list(work).items():
            try:
                picture=compose(work,kind,number,planes)
                if not picture:continue
                path=out/f'{kind}-{number}.png';png(path,*picture)
                result['buildings' if kind=='building' else 'menu'][str(number)]=str(path)
            except (OSError,ValueError,KeyError):pass
        done.write_text(json.dumps(result,ensure_ascii=False),encoding='utf8')
        return result
    finally:
        shutil.rmtree(work,ignore_errors=True)

if __name__=='__main__':
    try:print(json.dumps(prepare(),ensure_ascii=False))
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as error:print(json.dumps(dict(buildings={},menu={},error=str(error)),ensure_ascii=False))
