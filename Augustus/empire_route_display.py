"""In-game empire map: display-only trade paths (window/empire_route_paths.inc draws them).

Host (Lobby, once per room): host_routes() reads the room's scenario-project.json and makes one display path per
real trade relation (empire_paths.display_routes). The result is kept beside the project (empire-routes-cache.json,
reused only while the project text and the passage data are the same) and handed to players by the 'empire_routes'
request. Nothing here is part of the simulation binding, the saves or the trade rules.

Player (game bridge): publish() asks for it once per scenario layout and writes empire-routes.txt for the game:
which relations are this city's own and, for player-player relations, whether the contract is in force (the same
route-state.txt the contract window reads). The game re-reads the file only when it changes.
A relation without a terrain path is written as a straight stand-in line between the two cities (shape 1), never
as a terrain path (shape 0). Any failure here leaves the file empty or unchanged: the game then draws the trade
routes it knows itself (empire_route_paths.inc) as the same plain dashed lines, and trade is never held up by it.
"""
import hashlib,json,time
from pathlib import Path

CACHE='empire-routes-cache.json'
MAX_ROUTES=320;MAX_POINTS=24000;MAX_PER_PATH=600   # route_display.h limits

def host_routes(room_path):
    """Routes for the room's project, or an empty answer when the room has no project (older scenarios)."""
    folder=Path(room_path).parent;project=folder/'scenario-project.json'
    if not project.is_file():return dict(version=None,data=None,routes=[])
    import empire_paths
    from scenario_project import load
    key='AUGROUTES2:'+hashlib.sha256(project.read_bytes()).hexdigest()+':'+str(empire_paths.data_id())
    try:
        cached=json.loads((folder/CACHE).read_text(encoding='utf8'))
        if cached.get('key')==key and isinstance(cached.get('answer'),dict):return cached['answer']
    except (OSError,ValueError):pass
    answer=empire_paths.display_routes(load(project))
    try:
        tmp=folder/(CACHE+'.tmp');tmp.write_text(json.dumps(dict(key=key,answer=answer),ensure_ascii=False),encoding='utf8');tmp.replace(folder/CACHE)
    except OSError:pass
    return answer

def _valid(answer):
    if not isinstance(answer,dict) or not isinstance(answer.get('routes'),list):return False
    for r in answer['routes']:
        if not isinstance(r,dict) or r.get('kind') not in ('player','neutral') or r.get('transport') not in ('land','sea'):return False
        if any(type(r.get(k)) is not int or not 1<=r[k]<=255 for k in ('a','b')) or r['a']==r['b']:return False
        for p in (r.get('points'),r.get('ends')):
            if p is None:continue
            if not isinstance(p,list) or not 2<=len(p)<=MAX_PER_PATH:return False
            for xy in p:
                if not isinstance(xy,list) or len(xy)!=2 or any(type(v) is not int for v in xy) or not 0<=xy[0]<=2000 or not 0<=xy[1]<=1000:return False
        if r.get('ends') is not None and len(r['ends'])!=2:return False
    return True

def contracts(root):
    """Contract state per partner city, from route-state.txt (route_bridge): 1 = in force."""
    try:lines=(Path(root)/'route-state.txt').read_text(encoding='utf8').splitlines()
    except OSError:return {}
    out={}
    for line in lines:
        parts=line.split()
        if len(parts)==4 and parts[2].isdigit():out[parts[1]]=int(parts[2])
    return out

def encode(answer,own_city,slots,contract):
    """The file text for one player (AUGROUTES2). shape 0 = terrain path, 1 = straight stand-in between the two
    cities (no terrain path). A relation whose cities have no position is left out: nothing is guessed."""
    names={s.get('city'):s.get('name_id') for s in slots}
    own=names.get(own_city);rows=[];points=0
    for r in answer['routes']:
        p,shape=(r['points'],0) if r['points'] else (r.get('ends'),1)
        if p is None or len(rows)>=MAX_ROUTES or points+len(p)>MAX_POINTS:continue
        mine=own in (r['a'],r['b'])
        active=-1
        if r['kind']=='player' and mine:
            other=r['slot_b'] if r['slot_a']==own_city else r['slot_a']
            active=1 if contract.get(other)==1 else 0
        rows.append(f"{0 if r['kind']=='player' else 1} {int(r['transport']=='sea')} {r['a']} {r['b']} {int(mine)} {active} {shape} {len(p)}\n"+' '.join(f'{x} {y}' for x,y in p))
        points+=len(p)
    return 'AUGROUTES2\n'+str(len(rows))+'\n'+''.join(row+'\n' for row in rows)

EMPTY='AUGROUTES2\n0\n'
def publish(b,state):
    """Called with every lobby state the bridge publishes. One request per room session and scenario layout;
    retries are spaced. Until the answer for the current room is in, the file holds no routes, so nothing from an
    earlier room or scenario is ever drawn."""
    if not getattr(b,'joined',False) or not getattr(b.client,'city',None):return
    key=(getattr(b.client,'session',None),state.get('layout_version'))
    if getattr(b,'route_display_for',None)!=key:
        b.write_changed('empire-routes.txt',EMPTY)
        if time.monotonic()<getattr(b,'route_display_retry',0):return
        try:
            answer=b.client.call('empire_routes')
            if not _valid(answer):raise ValueError('empire routes')
        except Exception:   # display only: never let it disturb the bridge
            b.route_display_retry=time.monotonic()+15;return
        b.route_display=answer;b.route_display_for=key;b.route_display_retry=0
    b.write_changed('empire-routes.txt',encode(b.route_display,b.client.city,state.get('slots',[]),contracts(b.root)))
