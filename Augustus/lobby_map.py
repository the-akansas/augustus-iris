from windows_paths import sqlite_readonly_uri
"""Display-only room layout; never part of the simulation binding or saves."""
import json
from pathlib import Path

def room_project(room_path):
    """The project file that matches the cities this room offers. A room resumed from a joint save keeps the saved
    (smaller) roster in scenario-project.json, but offers every seat of the original scenario (restore_expansion,
    scenario-original.json) so that new players can join with fresh cities. The waiting room must show that original
    roster, or the free seats look like neutral cities (user report 2026-11-13). Once the game starts, room_roster
    writes the played roster back to scenario-project.json, and that file matches again."""
    folder=Path(room_path).parent;path=folder/'scenario-project.json';original=folder/'scenario-original.json'
    if not original.is_file():return path
    try:
        import sqlite3
        from contextlib import closing
        with closing(sqlite3.connect(sqlite_readonly_uri(room_path),uri=True)) as db:
            cities=json.loads(db.execute('SELECT value FROM scenario_binding').fetchone()[0])['cities']
        from scenario_project import load as load_project
        if sorted(s['id'] for s in load_project(original)['slots'])==sorted(cities):return original
    except (OSError,ValueError,KeyError,TypeError,ImportError):pass
    except Exception:pass   # sqlite3.Error and the like: keep the saved roster
    return path

def load(room_path):
    from city_client import HERE
    from scenario_project import load as load_project
    from scenario_overview import overview
    path=room_project(room_path)
    if not path.is_file():return []
    data=load_project(path)
    catalog=json.loads((HERE/'preset-catalog.json').read_text(encoding='utf-8-sig'))
    view=overview(data,catalog)
    cities=sorted([c for c in data['empire']['cities'] if c['role']=='player' or c.get('enabled',True)],key=lambda c:c['role']!='player')
    ids={s['name_id']:s['id'] for s in data['slots']}
    rows=[dict(id=ids.get(c['name_id'],''),name=v['name'],x=v['x'],y=v['y']) for c,v in zip(cities,view['cities'])]
    return rows+[dict(rome=True,name='로마',**view['rome'])]   # fixed capital, display only (rome_capital.py)

def encode(bridge,state):
    from scenario_overview import clean
    slots={s['city']:s for s in state['slots']}
    rows=[];number=0
    shown=[c for c in state.get('empire_map',[]) if isinstance(c,dict)]
    rome=next((c for c in shown if c.get('rome')),None)
    for city in [c for c in shown if not c.get('rome')][:40]:
        x,y=city.get('x'),city.get('y')
        if type(x)!=int or type(y)!=int or not 0<=x<=2000 or not 0<=y<=1000:continue
        slot=slots.get(city.get('id'))
        mine=bool(slot and bridge.joined and slot['city']==bridge.client.city)
        flag=3 if mine else 2 if slot and slot['claimed'] else 1 if slot else 0
        if slot:number+=1
        status=''
        if slot:
            status=slot['name'] if slot['claimed'] else '빈자리'
            status+=' · '+('방장' if slot['city']==state['host_city'] and slot['claimed'] else '준비' if slot['ready'] else '연결 끊김' if slot['claimed'] and not slot['online'] else '대기' if slot['claimed'] else '시작 시 중립')
            if slot['claimed'] and slot['online'] and slot['city']!=state['host_city'] and not mine:
                from status_display import lobby_ping
                status+=lobby_ping(slot)   # e.g. '플레이어2 · 대기 400ms': that player's ping to the host; never on one's own row (user 2026-11-13)
            elif slot['claimed'] and slot['city']==state['host_city'] and bridge.joined and bridge.client.city!=slot['city']:
                # on a guest's screen the host row carries the guest's own ping to the host: '플레이어1 · 방장 400ms'
                from status_display import lobby_ping
                own=slots.get(bridge.client.city)
                if own and own.get('online'):status+=lobby_ping(own)
        rows += [f'{flag} {x} {y} {number if slot else 0} {slot.get('player_color',-1) if slot else -1}',clean(city.get('name','')),clean(status),clean(city.get('id',''))]
    tail=f"ROME {rome['x']} {rome['y']}\n" if rome and type(rome.get('x'))==int and type(rome.get('y'))==int and 0<=rome['x']<=2000 and 0<=rome['y']<=1000 else ''
    return 'AUGLOBBYMAP3\n'+str(len(rows)//4)+'\n'+'\n'.join(rows)+'\n'+tail   # optional last line; older readers ignore it


def briefing(room_path):
    from city_client import HERE
    from scenario_project import load as load_project
    from scenario_overview import overview,encode
    path=room_project(room_path)
    if not path.is_file():return ''
    data=load_project(path)
    catalog=json.loads((HERE/'preset-catalog.json').read_text(encoding='utf-8-sig'))
    return encode('ROOM',overview(data,catalog))
