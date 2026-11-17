"""Natural trade paths on the empire map (display only).

Where a path may run comes from empire-passage.json (tools/build_empire_passage.py): a 10 px grid of land (L),
sea (S) and both (B: a river port, strait or coast road where an original route of the other kind runs) cells made from the empire picture and confirmed against the game's own original trade routes, plus the
centres of those original route pieces ('lanes').

  * a land path runs over land cells only, a sea path over sea cells only (both cells of every step; a diagonal step
    also needs one of the two side cells, so a path never slips through the point where two forbidden cells touch);
  * a path leaves a city from a gate: a cell of an original route of its kind near the city (a harbour, a road),
    or an allowed cell near the city; the gates are chosen together with the path (cheapest whole path, legs
    included). A sea path's harbour leg (city -> harbour) is the only part allowed on land; a land leg must be on
    land outside the city icon;
  * steps near an original route of the same kind are cheaper, so paths follow the old routes where they exist;
  * straightening (line of sight) and rounding (Chaikin) keep every segment inside the allowed cells; a rounded
    corner that would cut across forbidden cells is not rounded;
  * same map + same endpoints + same kind -> the same path (no randomness, fixed tie-breaking);
  * no allowed path -> None ('경로 미확정'). Never a straight line drawn over the terrain instead.

Nothing here changes trade rules, travel time or arrival: the path is drawn, not used for movement.
"""
import hashlib,heapq,json,math
from pathlib import Path
HERE=Path(__file__).resolve().parent
DATA=HERE/'empire-passage.json'
LANE_REACH=80        # px: a path may leave a city from an original route of its kind this close (a harbour, a road)
CELL_REACH=60        # px: or from any allowed cell this close
CITY_ICON=25         # px: half the city icon; a land leg must be on land outside it
LANE_BONUS=0.4       # step cost factor next to an original route of the same kind (display preference only)
SHORTCUT=160         # px: longest straightened segment, so a path keeps following the old route it found

_cache={}
def load(path=DATA):
    path=Path(path)
    if path not in _cache:
        d=json.loads(path.read_text(encoding='utf8'))
        if d.get('schema')!=1:raise ValueError('지원하지 않는 제국지도 통행 자료입니다.')
        cell=d['cell'];w,h=d['width']//cell,d['height']//cell
        if len(d['rows'])!=h or any(len(r)!=w or set(r)-{'L','S','B'} for r in d['rows']):raise ValueError('제국지도 통행 자료가 손상되었습니다.')
        near={}
        for kind,key in (('land','L'),('sea','S')):
            s=set()
            for x,y in d['lanes'][kind]:
                cx,cy=int(x)//cell,int(y)//cell
                for dy in (-1,0,1):
                    for dx in (-1,0,1):s.add((cx+dx,cy+dy))
            near[key]=s
        d['_near']=near;d['_w']=w;d['_h']=h;d['_part']={}
        d['_hash']=hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        _cache[path]=d
    return _cache[path]

def data_id(path=DATA):
    try:return load(path)['_hash']
    except (OSError,ValueError,KeyError):return None

def _cell(d,x,y):
    c=d['cell'];return min(d['_w']-1,max(0,int(x)//c)),min(d['_h']-1,max(0,int(y)//c))
def _cls(d,cx,cy):return d['rows'][cy][cx] if 0<=cx<d['_w'] and 0<=cy<d['_h'] else None
def _ok(d,cx,cy,key):c=_cls(d,cx,cy);return c==key or c=='B'
def _centre(d,cx,cy):c=d['cell'];return (cx*c+c//2,cy*c+c//2)

def _leg_clear(d,city,cell,key):
    """The leg from a city to its first cell: the part outside the city's own icon (CITY_ICON px) must be allowed
    terrain, except a sea route's harbour leg, which is the road from the city down to its harbour. A city that stands
    on a land cell leaves over land all the way (no hop over a strait hidden under the icon)."""
    if key=='S':return True
    (x1,y1),(x2,y2)=city,_centre(d,*cell);dist=math.hypot(x2-x1,y2-y1)
    if _ok(d,*_cell(d,x1,y1),key):return _clear(d,city,(x2,y2),key)   # a city on land leaves over land all the way
    if dist<=CITY_ICON:return True
    t0=CITY_ICON/dist;return _clear(d,(x1+(x2-x1)*t0,y1+(y2-y1)*t0),(x2,y2),key)

def _gates(d,x,y,key):
    """Cells where a path may leave a city, with the length of the leg (cells): cells on an original route of the
    same kind within LANE_REACH, and allowed cells within CELL_REACH. Sorted, so the result never depends on order."""
    c=d['cell'];out={}
    for px,py in d['lanes']['sea' if key=='S' else 'land']:
        dist=math.hypot(px-x,py-y)
        if dist<=LANE_REACH:
            cc=_cell(d,px,py)
            if _ok(d,*cc,key):out[cc]=min(out.get(cc,math.inf),math.hypot(_centre(d,*cc)[0]-x,_centre(d,*cc)[1]-y)/c)
    cx,cy=_cell(d,x,y);r=CELL_REACH//c+1
    for yy in range(cy-r,cy+r+1):
        for xx in range(cx-r,cx+r+1):
            if not _ok(d,xx,yy,key):continue
            px,py=_centre(d,xx,yy);dist=math.hypot(px-x,py-y)
            if dist<=CELL_REACH:out[(xx,yy)]=min(out.get((xx,yy),math.inf),dist/c)
    return {k:v for k,v in sorted(out.items()) if _leg_clear(d,(x,y),k,key)}

def _parts(d,key):
    """Connected areas of one kind (same step rule as the search), so an impossible link is answered without a search."""
    if key in d['_part']:return d['_part'][key]
    part={};n=0
    for y in range(d['_h']):
        for x in range(d['_w']):
            if (x,y) in part or not _ok(d,x,y,key):continue
            n+=1;part[(x,y)]=n;todo=[(x,y)]
            while todo:
                cx,cy=todo.pop()
                for dx in (-1,0,1):
                    for dy in (-1,0,1):
                        q=(cx+dx,cy+dy)
                        if q in part or not _ok(d,*q,key):continue
                        if dx and dy and not _ok(d,cx+dx,cy,key) and not _ok(d,cx,cy+dy,key):continue
                        part[q]=n;todo.append(q)
    d['_part'][key]=part;return part

def _graph(d,key):
    """Steps of one kind, computed once per data file: cell -> [(next cell, step cost)] in a fixed order."""
    g=d.setdefault('_graph',{})
    if key in g:return g[key]
    near=d['_near'][key];r2=math.sqrt(2);out={}
    for y in range(d['_h']):
        for x in range(d['_w']):
            if not _ok(d,x,y,key):continue
            steps=[]
            for dx,dy,cost in ((1,0,1),(-1,0,1),(0,1,1),(0,-1,1),(1,1,r2),(1,-1,r2),(-1,1,r2),(-1,-1,r2)):
                n=(x+dx,y+dy)
                if not _ok(d,*n,key):continue
                if dx and dy and not _ok(d,x+dx,y,key) and not _ok(d,x,y+dy,key):continue   # never slip between two corners
                steps.append((n,cost*(LANE_BONUS if n in near else 1.0)))
            out[(x,y)]=steps
    g[key]=out;return out

def _search(d,starts,goals,key):
    """Cheapest cell path from any start to any goal (A*), legs included in the cost. Ties: lower row, then lower
    column first, so equal inputs always give the same path."""
    if not starts or not goals:return None
    part=_parts(d,key);shared={part[c] for c in starts}&{part[c] for c in goals}
    if not shared:return None
    starts={c:v for c,v in starts.items() if part[c] in shared};goals={c:v for c,v in goals.items() if part[c] in shared}
    graph=_graph(d,key);x0=min(c[0] for c in goals);x1=max(c[0] for c in goals);y0=min(c[1] for c in goals);y1=max(c[1] for c in goals)
    def h(c):   # distance to the goals' bounding box at the cheapest step rate: never more than the true cost
        dx=max(x0-c[0],0,c[0]-x1);dy=max(y0-c[1],0,c[1]-y1);return math.hypot(dx,dy)*LANE_BONUS
    best={};came={};heap=[]
    for c,leg in sorted(starts.items()):
        if leg<best.get(c,math.inf):best[c]=leg;heapq.heappush(heap,(leg+h(c),leg,c[1],c[0],0))
    done=None
    while heap:
        f,g,cy,cx,fin=heapq.heappop(heap)
        if fin:done=(cx,cy);break
        c=(cx,cy)
        if g>best.get(c,math.inf)+1e-9:continue
        if c in goals:heapq.heappush(heap,(g+goals[c],g+goals[c],cy,cx,1))
        for n,cost in graph[c]:
            ng=g+cost
            if ng<best.get(n,math.inf)-1e-9:
                best[n]=ng;came[n]=c;heapq.heappush(heap,(ng+h(n),ng,n[1],n[0],0))
    if done is None:return None
    path=[done]
    while path[-1] in came:path.append(came[path[-1]])
    return path[::-1]

def _clear(d,a,b,key):
    """Every cell the segment a-b passes over is of the kind (exact grid walk). Where the segment runs exactly through
    a cell corner, one of the two side cells must be of the kind as well (the search's own diagonal rule)."""
    c=d['cell'];x,y=a[0]/c,a[1]/c;X,Y=b[0]/c,b[1]/c
    cx,cy=_cell(d,a[0],a[1])
    if not _ok(d,cx,cy,key):return False
    dx,dy=X-x,Y-y;sx=1 if dx>0 else -1;sy=1 if dy>0 else -1
    tdx=abs(1/dx) if dx else math.inf;tdy=abs(1/dy) if dy else math.inf
    tx=((cx+1-x) if dx>0 else (x-cx))*tdx if dx else math.inf
    ty=((cy+1-y) if dy>0 else (y-cy))*tdy if dy else math.inf
    while min(tx,ty)<=1:
        if abs(tx-ty)<1e-12:
            if not (_ok(d,cx+sx,cy,key) or _ok(d,cx,cy+sy,key)):return False
            cx+=sx;cy+=sy;tx+=tdx;ty+=tdy
        elif tx<ty:cx+=sx;tx+=tdx
        else:cy+=sy;ty+=tdy
        if not _ok(d,cx,cy,key):return False
    return True

def _straighten(d,pts,key):
    """Greedy line of sight: from each kept point go as far along the path as a straight, allowed segment of at most
    SHORTCUT px reaches."""
    out=[pts[0]];i=0
    while i<len(pts)-1:
        j=i+1
        while j+1<len(pts) and math.dist(pts[i],pts[j+1])<=SHORTCUT and _clear(d,pts[i],pts[j+1],key):j+=1
        out.append(pts[j]);i=j
    return out

def _round(d,pts,key,passes=2):
    for _ in range(passes):
        if len(pts)<3:break
        new=[pts[0]]
        for i in range(1,len(pts)-1):
            a,b,c=pts[i-1],pts[i],pts[i+1]
            q=(round(a[0]*0.25+b[0]*0.75),round(a[1]*0.25+b[1]*0.75));r=(round(b[0]*0.75+c[0]*0.25),round(b[1]*0.75+c[1]*0.25))   # whole pixels, checked as stored
            if _clear(d,new[-1],q,key) and _clear(d,q,r,key) and _clear(d,r,c,key):new+=[q,r]
            else:new.append(b)
        new.append(pts[-1]);pts=new
    return pts

def find(a,b,transport,path=DATA):
    """Points [[x,y],...] from city a to city b (map pixels), or None when no allowed path exists."""
    d=load(path);key='S' if transport=='sea' else 'L'
    cells=_search(d,_gates(d,a[0],a[1],key),_gates(d,b[0],b[1],key),key)
    if cells is None:return None
    pts=_round(d,_straighten(d,[_centre(d,*c) for c in cells],key),key)
    pts=[tuple(a)]+pts+[tuple(b)]
    out=[]
    for x,y in pts:
        p=[int(round(x)),int(round(y))]
        if not out or out[-1]!=p:out.append(p)
    return out

def check(points,transport,path=DATA):
    """True when every segment except the two harbour/approach legs stays on the allowed kind (used by tests and
    when a stored path is reloaded with different map data)."""
    d=load(path);key='S' if transport=='sea' else 'L'
    inner=points[1:-1]
    return len(points)>=2 and all(_clear(d,inner[i],inner[i+1],key) for i in range(len(inner)-1))

def key_for(a_id,b_id,transport):
    a,b=sorted((int(a_id),int(b_id)));return f'{a}-{b}-{transport}'

def resolve(stored,a_id,a_xy,b_id,b_xy,transport,regenerate=False,path=DATA):
    """The path for one link: a stored one is kept while its endpoints and kind still match (it is never replaced
    behind the user's back); otherwise a new one is made. Returns (record or None, state, reason)."""
    k=key_for(a_id,b_id,transport);lo,hi=sorted(((int(a_id),list(a_xy)),(int(b_id),list(b_xy))))
    rec=(stored or {}).get(k)
    if rec and not regenerate and rec.get('from')==lo[1] and rec.get('to')==hi[1]:
        return rec,'stored','저장된 경로'
    pts=find(lo[1],hi[1],transport,path)
    if pts is None:return None,'none','경로 미확정: 지도에서 '+('바닷길을' if transport=='sea' else '육로를')+' 찾지 못했습니다.'
    return dict(points=pts,**{'from':lo[1],'to':hi[1]},data=data_id(path)),'auto','지형에 맞춘 자동 경로'

def relations(data):
    """Every real trade relation of a scenario, as the game builds it (shared_empire / trade_policy):
      player-player  every pair trade_policy allows; transport = rules.player_transport (land unless set to sea)
      player-neutral an enabled, non-reserved neutral city and each player it lets trade (trade_players, default all);
                     transport = that neutral city's own sea flag
    Nothing is added for show. Returns [(kind, transport, name a, name b, slot a, slot b)], a < b by name id."""
    import trade_policy
    rules=data['rules'] if isinstance(data.get('rules'),dict) else {}
    slots=data['slots'];by_name={s['name_id']:s['id'] for s in slots};every=[s['id'] for s in slots]
    player_transport='sea' if rules.get('player_transport')=='sea' else 'land'
    out=[]
    for i,s in enumerate(slots):
        for o in slots[i+1:]:
            if trade_policy.allowed(rules,s['id'],o['id']):
                a,b=sorted(((s['name_id'],s['id']),(o['name_id'],o['id'])))
                out.append(('player',player_transport,a[0],b[0],a[1],b[1]))
    for c in data['empire']['cities']:
        if c['role']!='npc' or not c.get('enabled',True) or c.get('reserved'):continue
        for slot in c.get('trade_players',every):
            if slot not in every:continue
            name=next(s['name_id'] for s in slots if s['id']==slot)
            a,b=sorted(((name,slot),(c['name_id'],None)),key=lambda v:v[0])
            out.append(('neutral','sea' if c['sea'] else 'land',a[0],b[0],a[1],b[1]))
    return sorted(out,key=lambda r:(r[2],r[3],r[1]))

def display_routes(data,path=DATA):
    """Display paths for the in-game empire map: one per relation, from the project's stored path when it still
    fits the two cities (empire.route_paths), else made here. points None = no terrain path (none found, or the
    passage data could not be read); the game then draws the relation as a plain straight line between 'ends' (the
    two city positions), marked as a stand-in, not as a terrain path. ends None = a city has no position: nothing is
    drawn for it and nothing is guessed. Display only: nothing in trade reads it."""
    stored=data['empire'].get('route_paths') or {}
    pos={c['name_id']:(c.get('x'),c.get('y')) for c in data['empire']['cities']}
    try:load(path);ready=True
    except (OSError,ValueError,KeyError):ready=False
    out=[]
    for kind,transport,a,b,slot_a,slot_b in relations(data):
        pa,pb=pos.get(a),pos.get(b);points=None
        ends=[list(pa),list(pb)] if pa and pb and None not in pa+pb else None
        if ready and ends:
            rec,state,_=resolve(stored,a,pa,b,pb,transport,path=path)
            points=rec['points'] if rec else None
        out.append(dict(kind=kind,transport=transport,a=a,b=b,slot_a=slot_a,slot_b=slot_b,points=points,ends=ends))
    return dict(version=hashlib.sha256(json.dumps(out,sort_keys=True).encode()).hexdigest()[:16],data=data_id(path) if ready else None,routes=out)
