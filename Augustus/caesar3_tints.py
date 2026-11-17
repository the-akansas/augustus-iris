"""The player-colour cloth of flags and the post office roof, made on the player's own PC from the player's own
Caesar III graphics (user 2026-11-16: the Global edition's source does not carry pictures made from the original game).

Each picture is the brightness of the original sprite where its cloth (or roof tiles) is, and transparent elsewhere;
the game multiplies it by a player's colour (assets/Graphics/mp_flags.xml, admin_logistics.xml). The cloth is chosen by
colour rules only (no hand-drawn outline):
  empire map flags  C3.sg2 groups 175 (red cloth), 176 (teal), 223 (ochre), frames 1..6; group 174 (golden eagle,
                    no cloth): its black outline
  legion standards  group 126 frames 0..26: the red cloth, without the stick, the metal bars and small patches inside
                    the golden emblem
  post office roof  group 82 image 17: the roof tiles and the joints between them
then the brightness is spread over 0.45..1.2 of white (clipped), the same for every picture.
Pictures already in assets are kept (the Korean edition ships them); a missing one is made. Never fatal: without the
pictures the flags keep their original colours.

  python caesar3_tints.py <Caesar III folder> [assets folder]"""
import colorsys,struct,sys,zlib
from pathlib import Path
HERE=Path(__file__).resolve().parent

def _find(folder,name):
    folder=Path(folder);exact=folder/name
    if exact.is_file():return exact
    low=name.lower()
    for p in folder.iterdir() if folder.is_dir() else []:
        if p.name.lower()==low and p.is_file():return p
    return None

class Sprites:
    """C3.sg2 / C3.555: the sprites of the main graphics file, decoded to RGBA rows."""
    def __init__(self,folder):
        sg=_find(folder,'C3.sg2');px=_find(folder,'C3.555')
        if not sg or not px:raise FileNotFoundError('C3.sg2 or C3.555 not found in '+str(folder))
        self.folder=Path(folder);self.sg=sg.read_bytes();self.pix=px.read_bytes()
        self.groups=struct.unpack_from('<300H',self.sg,80)
        self.entries=[];offset=4
        for i in range(10000):
            b=self.sg[20680+64*i:20680+64*(i+1)]
            if len(b)<64:break
            o,l,u=struct.unpack_from('<3I',b);w,h=struct.unpack_from('<2H',b,20)
            e=dict(offset=offset,length=l,unc=u,w=w,h=h,iso=b[50]==30,compressed=b[51],external=b[52],top=b[53],bitmap=b[56],stored=o)
            self.entries.append(e)
            if i and not e['external']:offset+=l
    @staticmethod
    def rgba(c):return tuple(((c>>s)&31)*8+(((c>>s)&31)>>2) for s in (10,5,0))+(255,)
    def decode(self,index):
        e=self.entries[index];w,h=e['w'],e['h'];img=[[(0,0,0,0)]*w for _ in range(h)]
        data=self.pix;start=e['offset']
        if e['external']:raise ValueError('external sprite not needed here')
        end=start+e['length']
        def put(k,c):img[k//w][k%w]=c
        if e['compressed']:
            pos=start;k=0
            while pos<end and k<w*h:
                n=data[pos];pos+=1
                if n==255:k+=data[pos];pos+=1
                else:
                    for _ in range(n):
                        if k>=w*h:break
                        put(k,self.rgba(struct.unpack_from('<H',data,pos)[0]));pos+=2;k+=1
        elif e['iso']:raise ValueError('isometric sprite not needed here')
        else:
            for k in range(w*h):
                c=self.rgba(struct.unpack_from('<H',data,start+k*2)[0])
                put(k,(0,0,0,0) if c==(247,0,255,255) else c)
        return img
    def sprite(self,group,frame):return self.decode(self.groups[group]+frame)

def _hsv(c):h,s,v=colorsys.rgb_to_hsv(c[0]/255,c[1]/255,c[2]/255);return h*360,s,v
def _gray(c):return int(0.299*c[0]+0.587*c[1]+0.114*c[2]+0.5)
def _components(cells):
    cells=set(cells);seen=set();out=[]
    for s in cells:
        if s in seen:continue
        stack=[s];seen.add(s);comp=[]
        while stack:
            x,y=stack.pop();comp.append((x,y))
            for n in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
                if n in cells and n not in seen:seen.add(n);stack.append(n)
        out.append(comp)
    return out

def empire_cloth(img,group):
    sel=[]
    for y,row in enumerate(img):
        for x,(r,g,b,a) in enumerate(row):
            if a!=255:continue
            if group==174 and (r,g,b)==(0,0,0):sel.append((x,y))
            elif group==175 and r>=24 and g<=8 and b<=8:sel.append((x,y))
            elif group==176 and r<=8 and abs(g-b)<=9 and g>=24:sel.append((x,y))
            elif group==223 and r>=41 and g>=24 and b<=8 and 1<=r/g<=2:sel.append((x,y))
    return sel

def standard_cloth(img):
    sel=[]
    for y in range(2,min(27,len(img))):
        for x in range(3,min(29,len(img[y]))):
            c=img[y][x]
            if c[3]!=255:continue
            h,s,v=_hsv(c)
            if (h<=18 or h>=350) and s>=0.60 and v>=0.08:sel.append((x,y))
    if sum(1 for _,y in sel if y==2)<8:sel=[p for p in sel if p[1]!=2]   # the stick's top, not the cloth's top edge
    return [p for comp in _components(sel) if len(comp)>=8 for p in comp]   # small red patches inside the emblem stay

def roof_tiles(img):
    h=len(img);w=len(img[0]) if h else 0;sel=set()
    def allowed(x,y):return y<=34 and (y<27 or y-1<=x<=66-y)
    for y in range(min(h,35)):
        for x in range(w):
            c=img[y][x]
            if c[3]!=255 or not allowed(x,y):continue
            hh,s,v=_hsv(c)
            if (hh<=35 or hh>=350) and s>=0.38 and v>=0.12:sel.add((x,y))
    dark=lambda c:c[3]==255 and max(c[:3])<=90
    for y in range(min(h,35)):   # joints of 1..2 pixels between tiles of a row
        xs=sorted(x for x,yy in sel if yy==y)
        for a,b in zip(xs,xs[1:]):
            if 2<=b-a<=3 and all(dark(img[y][x]) and img[y][x][0]>=img[y][x][1]>=img[y][x][2] for x in range(a+1,b)):
                sel.update((x,y) for x in range(a+1,b))
    rest={(x,y) for y in range(h) for x in range(w)}-sel   # dark holes enclosed by tiles
    for comp in _components(rest):
        if any(x in (0,w-1) or y in (0,h-1) for x,y in comp):continue
        if all(dark(img[y][x]) for x,y in comp):sel.update(comp)
    return sorted(sel)

def shade(img,cells):
    """The cells' brightness spread over 0.45..1.2 of white (clipped at 255); everything else transparent."""
    h=len(img);w=len(img[0]) if h else 0;out=[[(0,0,0,0)]*w for _ in range(h)]
    values=[_gray(img[y][x]) for x,y in cells]
    if not values:return out
    m,M=min(values),max(values)
    for x,y in cells:
        g=_gray(img[y][x]);v=min(255,round(255*(1 if M==m else 0.45+0.75*(g-m)/(M-m))))
        out[y][x]=(v,v,v,img[y][x][3])
    return out

def png(rows,path):
    h=len(rows);w=len(rows[0]) if h else 0
    raw=b''.join(b'\0'+bytes(v for px in row for v in px) for row in rows)
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    data=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(raw,9))+chunk(b'IEND',b'')
    tmp=Path(str(path)+'.tmp');tmp.parent.mkdir(parents=True,exist_ok=True);tmp.write_bytes(data);tmp.replace(path)

def pictures():
    """(file under assets/Graphics, how to make it)"""
    out=[]
    for g in (174,175,176,223):
        for k in range(1,7):out.append((f'MP_Flags/E{g}_{k}.png',lambda s,g=g,k=k:(lambda img:shade(img,empire_cloth(img,g)))(s.sprite(g,k))))
    for k in range(27):out.append((f'MP_Flags/S_{k}.png',lambda s,k=k:(lambda img:shade(img,standard_cloth(img)))(s.sprite(126,k))))
    out.append(('Admin_Logistics/Player_Trade_Roof_Shade.png',lambda s:(lambda img:shade(img,roof_tiles(img)))(s.sprite(82,17))))
    return out

def ensure(game_data,assets=None,force=False):
    """Make the pictures that are missing. Returns how many were made; 0 when nothing was missing or the game data
    cannot be read (the game then shows the original colours)."""
    graphics=Path(assets or HERE/'assets')/'Graphics'
    wanted=[(rel,make) for rel,make in pictures() if force or not (graphics/rel).is_file()]
    if not wanted:return 0
    try:sprites=Sprites(game_data)
    except (OSError,ValueError,struct.error):return 0
    made=0
    for rel,make in wanted:
        try:png(make(sprites),graphics/rel);made+=1
        except (OSError,ValueError,IndexError,struct.error):continue
    return made

if __name__=='__main__':
    if len(sys.argv) not in (2,3):raise SystemExit(__doc__)
    print(ensure(sys.argv[1],sys.argv[2] if len(sys.argv)==3 else None),'pictures made')
