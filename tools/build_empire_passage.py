"""Build Augustus/empire-passage.json: where an empire-map trade path may run (land / sea), plus the original routes.

Inputs (all from the owner's own game data, read locally, never shipped as pictures):
  --image   empire.bmp exported by the engine (creator 'inventory-<id>' output; one picture for c3.emp and c32.emp)
  --routes  routes.json files written for every template by the development aid tools/empire_routes_export.h (see
            there; 'inventory-<id>' runs): the original trade route dots (object x,y,w,h) and cities
Output: cell classes on a 10 px grid (L land, S sea, B both: opened by an original route of the other kind) and the original route pieces (centres), with a validation summary:
  every original sea piece must lie in a sea cell, every original land piece in a land cell. The build fails if the
  picture classification disagrees with the original routes beyond the stated tolerance, so the colour rule is not
  trusted on its own: it is accepted only where the game's own routes confirm it.
"""
import argparse,hashlib,json,sys
from pathlib import Path
from PIL import Image

CELL=10
def sea_pixel(r,g,b):return b>=80 and b-r>=25 and b-g>=15      # the rule of empire-coast.json (Codex), re-checked below

def classify(image):
    im=Image.open(image).convert('RGB');w,h=im.size;px=im.load();rows=[]
    for cy in range(h//CELL):
        row=[]
        for cx in range(w//CELL):
            sea=sum(1 for y in range(cy*CELL,(cy+1)*CELL) for x in range(cx*CELL,(cx+1)*CELL) if sea_pixel(*px[x,y]))
            row.append('S' if sea*2>=CELL*CELL else 'L')
        rows.append(''.join(row))
    return w,h,rows

GAP=45      # px: two pieces of one original route this close are consecutive dots of that route
def pieces(paths):
    land=set();sea=set();cities={};routes={}
    for p in paths:
        for o in json.loads(Path(p).read_text(encoding='utf8')):
            if o['type'] in (4,5):
                c=(round(o['x']+o['w']/2),round(o['y']+o['h']/2));(sea if o['type']==5 else land).add(c)
                routes.setdefault((str(p),o['route'],o['type']),set()).add(c)
            elif o['type']==1:cities.setdefault(o['name'],set()).add((o['x']+25,o['y']+25))
    return sorted(land),sorted(sea),cities,routes

def links(pts):
    """Minimum spanning tree of one route's dots (edges up to GAP): the original route drawn dot to dot."""
    pts=sorted(pts);
    if len(pts)<2:return []
    inside={pts[0]};out=[]
    while len(inside)<len(pts):
        best=min(((a[0]-b[0])**2+(a[1]-b[1])**2,a,b) for a in inside for b in pts if b not in inside)
        inside.add(best[2])
        if best[0]<=GAP*GAP:out.append((best[1],best[2]))
    return out

def corridor(a,b):
    (x1,y1),(x2,y2)=a,b;n=max(1,int(max(abs(x2-x1),abs(y2-y1))/(CELL/4)));seen=[]
    for i in range(n+1):
        c=(int(x1+(x2-x1)*i/n)//CELL,int(y1+(y2-y1)*i/n)//CELL)
        if seen and c[0]!=seen[-1][0] and c[1]!=seen[-1][1]:
            seen.append((c[0],seen[-1][1]))      # side-connected corridor: no passing through a corner point
        if c not in seen:seen.append(c)
    return seen

def main():
    a=argparse.ArgumentParser();a.add_argument('--image',required=True);a.add_argument('--routes',nargs='+',required=True)
    a.add_argument('--out',default=str(Path(__file__).resolve().parents[1]/'wip-24/Augustus/empire-passage.json'));a=a.parse_args()
    w,h,rows=classify(a.image);land,sea,_,routes=pieces(a.routes)
    cell=lambda x,y:rows[min(h//CELL-1,int(y)//CELL)][min(w//CELL-1,int(x)//CELL)]
    bad_sea=[p for p in sea if cell(*p)!='S'];bad_land=[p for p in land if cell(*p)!='L']
    # Original pieces override the picture where they disagree: they are the game's own routes.
    rows=[list(r) for r in rows]
    # 'B' = open to both: the picture says one kind, an original route of the other kind runs there (a river port,
    # a strait, a coast road). Original routes only ever open cells, never close them for the other kind.
    for x,y in bad_sea+bad_land:rows[int(y)//CELL][int(x)//CELL]='B'
    # Between consecutive dots of one original route the route itself is the passage (straits, narrow coasts the
    # 10 px picture cells miss). Counted separately and bounded like the pieces.
    fixed=set()
    for (_,_,kind),pts in sorted(routes.items()):
        want='S' if kind==5 else 'L'
        for p,q in links(pts):
            for cx,cy in corridor(p,q):
                if 0<=cy<len(rows) and 0<=cx<len(rows[0]) and rows[cy][cx] not in (want,'B'):rows[cy][cx]='B';fixed.add((cx,cy))
    rows=[''.join(r) for r in rows]
    summary=dict(sea_pieces=len(sea),land_pieces=len(land),sea_pieces_on_land_cells=len(bad_sea),land_pieces_on_sea_cells=len(bad_land),
                 corridor_cells_set_by_original_routes=len(fixed),cells=len(rows)*len(rows[0]))
    if (len(bad_sea)+len(bad_land))>0.05*(len(sea)+len(land)) or len(fixed)>0.01*summary['cells']:sys.exit('picture classification disagrees with the original routes: '+json.dumps(summary))
    out=dict(schema=1,cell=CELL,width=w,height=h,image_sha256=hashlib.sha256(Path(a.image).read_bytes()).hexdigest(),
             rows=rows,lanes=dict(land=[list(p) for p in land],sea=[list(p) for p in sea]),validation=summary)
    Path(a.out).write_text(json.dumps(out,separators=(',',':')),encoding='utf8');print(json.dumps(summary))
if __name__=='__main__':main()
