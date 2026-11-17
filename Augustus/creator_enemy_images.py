"""Small pictures of the 20 enemy peoples for the scenario editor (user 2026-11-15), read from the owner's own
Caesar 3 files (the enemy .sg2 index and .555 pixels, as src/core/image.c reads them). Written to the editor's
private cache only; never shipped or exported.

Each picture shows the people's two kinds of soldier, walking towards the viewer: the first kind is the image the
game draws for its main soldier (297 for barbarians, 449 for the others), the second (601) for the peoples that have
one (src/scenario/invasion.c ENEMY_PROPERTIES, src/figuretype/enemy.c)."""
import json,struct,sys,zlib
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))

# image.c ENEMY_GRAPHICS_SG2 / _555 (index = enemy id, the order of the editor's list)
FILES=['goths','Etruscan','Etruscan','carthage','Greek','Greek','egyptians','Persians','Phoenician','celts','celts','celts',
       'Gaul','Gaul','goths','goths','goths','Phoenician','North African','Phoenician']
BARBARIAN_ID=0   # id 0 uses goths files with the barbarian pictures
HEADER=20680;ENTRY=64;ENTRIES=801
TOWARDS_VIEWER=3  # direction offset: facing down the screen

def _find(folder,name):
    for p in Path(folder).iterdir():
        if p.name.lower()==name.lower():return p
    raise FileNotFoundError(name)

def _rgb(c):
    r=(c>>10)&31;g=(c>>5)&31;b=c&31
    return (r<<3)|(r>>2),(g<<3)|(g>>2),(b<<3)|(b>>2)

def sprite(index,pixels,number):
    """One image: (width, height, rows of RGBA bytes)."""
    offset,length,_=struct.unpack_from('<iii',index,HEADER+ENTRY*number)
    width,height=struct.unpack_from('<HH',index,HEADER+ENTRY*number+20)
    compressed=index[HEADER+ENTRY*number+51]
    if not 0<width<=256 or not 0<height<=256 or offset<0 or offset+length>len(pixels):raise ValueError('그림 정보가 올바르지 않습니다.')
    out=bytearray(width*height*4);p=offset;end=offset+length;x=y=0
    if compressed:
        while p<end and y<height:
            control=pixels[p];p+=1
            if control==255:
                skip=pixels[p];p+=1;y+=(x+skip)//width;x=(x+skip)%width
            else:
                for _ in range(control):
                    if y>=height:break
                    c=struct.unpack_from('<H',pixels,p)[0];p+=2;r,g,b=_rgb(c);i=(y*width+x)*4;out[i:i+4]=bytes((r,g,b,255))
                    x+=1
                    if x>=width:x=0;y+=1
    else:
        for y in range(height):
            for x in range(width):
                c=struct.unpack_from('<H',pixels,p)[0];p+=2
                if c!=0xf81f:   # the original transparent colour
                    r,g,b=_rgb(c);i=(y*width+x)*4;out[i:i+4]=bytes((r,g,b,255))
    return width,height,out

def png(path,width,height,rgba):
    raw=b''.join(b'\0'+bytes(rgba[y*width*4:(y+1)*width*4]) for y in range(height))
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    Path(path).write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(raw,9))+chunk(b'IEND',b''))

SHOWN_HEIGHT=72   # about an elephant (user 2026-11-15: "not too small, as big as the elephant")
def enlarge(width,height,rgba):
    """Soldiers are about a third of an elephant: enlarged by a whole factor, pixel by pixel (no blur)."""
    k=max(1,round(SHOWN_HEIGHT/height))
    if k==1:return width,height,rgba
    out=bytearray(width*k*height*k*4)
    for y in range(height):
        row=b''.join(bytes(rgba[(y*width+x)*4:(y*width+x)*4+4])*k for x in range(width))
        for j in range(k):out[((y*k+j)*width*k)*4:((y*k+j+1)*width*k)*4]=row
    return width*k,height*k,out

def picture(folder,enemy):
    base=FILES[enemy]
    index=_find(folder,base+'.sg2').read_bytes();pixels=_find(folder,base+'.555').read_bytes()
    if len(index)<HEADER+ENTRY*ENTRIES:raise ValueError('적군 그림 목록이 짧습니다: '+base)
    numbers=[(297 if enemy==BARBARIAN_ID else 449)+TOWARDS_VIEWER]
    if enemy!=BARBARIAN_ID and enemy not in (18,):numbers.append(601+TOWARDS_VIEWER)   # 18: numidians (one picture)
    parts=[enlarge(*sprite(index,pixels,n)) for n in numbers]
    gap=6;width=sum(w for w,_,_ in parts)+gap*(len(parts)-1);height=max(h for _,h,_ in parts)
    out=bytearray(width*height*4);left=0
    for w,h,rgba in parts:
        top=height-h   # feet on one line
        for y in range(h):out[((top+y)*width+left)*4:((top+y)*width+left+w)*4]=rgba[y*w*4:(y+1)*w*4]
        left+=w+gap
    return width,height,out

def prepare(target=None):
    from city_client import game_data
    folder=game_data();target=Path(target or HERE/'creator-cache'/'enemy-pictures');target.mkdir(parents=True,exist_ok=True)
    result={}
    for enemy in range(20):
        path=target/f'enemy-{enemy}-v2.png'   # v2: enlarged
        try:
            if not path.is_file():png(path,*picture(folder,enemy))
            result[str(enemy)]=str(path)
        except (OSError,ValueError,struct.error):pass   # a missing file: no picture for that people
    return dict(pictures=result)

if __name__=='__main__':
    try:print(json.dumps(prepare(),ensure_ascii=False))
    except (OSError,ValueError) as error:print(json.dumps(dict(pictures={},error=str(error)),ensure_ascii=False))
