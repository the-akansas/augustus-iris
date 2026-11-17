"""City roles in a scenario project. Pure data edits on the scenario.json dict; nothing is ever dropped silently.

Four separate facts about an empire city:
  terrain    does a city map belong to it?   in a slot (player), kept on the city ('map'), or offered by the preset catalog
  eligible   may it be chosen for play?      exactly when it has terrain
  role       how this scenario uses it       'player' or 'neutral' (Rome is separate and has no map)
  slot       which player slot holds it      only for role 'player'

What belongs to whom:
  city   its terrain (preset number, tile edits, external map), its neutral trade setup, its position and identity
  slot   allowed buildings, governance, starting funds, role hint, player-to-player trade exceptions and the other play settings

  swap_city           the slot stays and plays another city: the old city keeps its terrain, the slot uses the new city's
                      terrain, and the slot's own settings are untouched.
  to_neutral          the slot is deleted (existing editor behaviour: its settings go with it); the city keeps its terrain
                      and gets back the neutral trade setup it had.
  to_player           a new slot is created for the city with default settings and the city's terrain.
  detach_terrain      what the city keeps (an attached map, the terrain of an earlier seat) leaves the scenario.
  reset_to_c3         a neutral city as a new scenario has it from Caesar III (the unified empire of creator_presets.py):
                      place, trade, route, who may trade, switched off; its kept terrain leaves the scenario.
Everything that can be put in can be taken out again (2026-11-15); to_neutral can take the goals that name the slot
with it (drop_goals), else it refuses as before.
A city without terrain cannot become a player city.
A 'map' written by the first draft of this field may also carry slot settings. They are never applied over an existing
slot (the slot's values win and the caller is told); a newly created slot, which has no values of its own, takes them.

Sea-only trade of a neutral city ('sea'): a value set by hand always wins. Only cities marked 'sea_auto' follow the
coast estimate, and only they are re-evaluated when moved. The estimate reads empire-coast.json when that file exists;
it is a guess from the empire picture and says nothing about a city map's real sea access.
"""
import argparse,copy,json,sys,uuid
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
TERRAIN=('campaign_scenario','terrain_edits','terrain_asset')          # belongs to the city
SETTINGS=('allowed_buildings','governance','starting_setup','events','invasions','invasion_enemy','starting_funds','role_hint')   # belongs to the slot
TRADE=('sea','cost','sells','buys')

_catalog={}
def catalog():
    path=Path(__file__).resolve().parent/'preset-catalog.json'
    if path not in _catalog:
        try:_catalog[path]=json.loads(path.read_text(encoding='utf-8-sig'))
        except OSError:_catalog[path]=dict(terrain=[],empire=[],neutral=[])
    return _catalog[path]
def preset_terrains(name_id,presets=None):
    return [t['id'] for t in (presets or catalog())['terrain'] if t.get('name_id')==name_id]
def find(data,name_id):
    city=next((c for c in data['empire']['cities'] if c['name_id']==name_id),None)
    if city is None:raise ValueError('시나리오에 없는 도시입니다.')
    return city
def slot_of(data,name_id):return next((s for s in data['slots'] if s['name_id']==name_id),None)

def status(data,name_id,presets=None):
    city=find(data,name_id);slot=slot_of(data,name_id) if city['role']=='player' else None
    held='slot' if slot else 'parked' if 'map' in city else None
    body=slot or city.get('map');offered=preset_terrains(name_id,presets)
    if body:terrain=dict(source='external' if 'terrain_asset' in body else 'original',preset=body['campaign_scenario'],edits=len(body.get('terrain_edits',[])),held=held)
    elif offered:terrain=dict(source='original',preset=None,edits=0,held=None,offered=offered)
    else:terrain=dict(source='none')
    return dict(name_id=name_id,role='player' if city['role']=='player' else 'neutral',slot=slot['id'] if slot else None,
                has_terrain=terrain['source']!='none',eligible=terrain['source']!='none',terrain=terrain,
                sea_only=None if city['role']=='player' else bool(city['sea']),sea_mode=None if city['role']=='player' else 'auto' if city.get('sea_auto') else 'manual')

def _all_buildings():
    try:return [r['id'] for r in json.loads((Path(__file__).resolve().parent/'building-catalog.json').read_text(encoding='utf-8-sig'))]
    except OSError:return []
def _goals_using(data,slot_id):
    goals=data['rules'].get('objectives') if isinstance(data['rules'],dict) else None
    if not goals:return False
    if any(goals.get('per_city',{}).get(slot_id,{}).values()):return True
    return any(slot_id in (g.get('sender'),g.get('receiver')) for g in goals.get('deliveries',[]))

def _terrain_of(slot):
    kept={k:copy.deepcopy(slot[k]) for k in TERRAIN if k in slot}
    kept.setdefault('terrain_edits',[]);return kept
def _default_settings():
    return dict(allowed_buildings=_all_buildings(),governance=dict(rank=0,salary_rank=-1,savings=0,favor=50,policy='fixed'))
def _release(data,city,slot_ids):
    """A player city becomes neutral again: bring back the neutral trade setup kept on it."""
    kept=city.pop('parked_trade',None);city['role']='npc'
    if kept:
        city.update({k:kept[k] for k in TRADE})
        if 'trade_players' in kept:city['trade_players']=[i for i in kept['trade_players'] if i in slot_ids]
        if kept.get('sea_auto'):city['sea_auto']=True
def _occupy(city):
    """A neutral city becomes a player city: keep its neutral trade setup on it."""
    parked={k:city[k] for k in TRADE}
    if 'trade_players' in city:parked['trade_players']=city.pop('trade_players')
    if city.pop('sea_auto',None):parked['sea_auto']=True
    city['parked_trade']=parked
    city.update(role='player',enabled=True,sea=0,cost=0,sells={},buys={})
def _city_terrain(data,city,presets):
    """(terrain fields, settings found in an older 'map') for a neutral city, or refuse when it has no terrain."""
    state=status(data,city['name_id'],presets)
    if not state['eligible']:raise ValueError('지형이 없는 도시는 플레이 도시로 선택할 수 없습니다. 먼저 도시 지형을 연결하세요.')
    body=city.pop('map',None)
    if body is None:
        offered=state['terrain']['offered'];return dict(campaign_scenario=next((i for i in offered if 2<=i<100),offered[0]),terrain_edits=[]),{}
    return _terrain_of(body),{k:body[k] for k in SETTINGS if k in body}

def to_neutral(data,name_id,enabled=False,drop_goals=False):
    """Delete the player slot of a city and use the city as a neutral trade city. The city keeps its terrain.
    The slot's own settings (allowed buildings, governance, ...) are deleted with the slot, as the editor always did.
    Goals naming the slot refuse it, unless drop_goals: then its city numbers and its deliveries leave with it."""
    data=copy.deepcopy(data);city=find(data,name_id);slot=slot_of(data,name_id)
    if city['role']!='player' or slot is None:raise ValueError('플레이 도시가 아닙니다.')
    if _goals_using(data,slot['id']) and not drop_goals:raise ValueError('이 도시를 쓰는 공동 목표가 있습니다. 목표에서 먼저 빼 주세요.')
    goals=data['rules'].get('objectives') if isinstance(data['rules'],dict) else None
    if goals:goals.get('per_city',{}).pop(slot['id'],None)   # all-zero, or dropped on purpose
    if goals and drop_goals and 'deliveries' in goals:goals['deliveries']=[g for g in goals['deliveries'] if slot['id'] not in (g.get('sender'),g.get('receiver'))]
    data['slots']=[s for s in data['slots'] if s is not slot]
    if isinstance(data.get('start_message'),dict):data['start_message'].get('per_city',{}).pop(slot['id'],None)   # the city's own start text leaves with its player
    import trade_policy
    trade_policy.forget_slot(data['rules'],slot['id'])   # player-to-player exceptions name slots and leave with them
    for other in data['empire']['cities']:
        if 'trade_players' in other:other['trade_players']=[i for i in other['trade_players'] if i!=slot['id']]
        if 'parked_trade' in other and 'trade_players' in other['parked_trade']:
            other['parked_trade']['trade_players']=[i for i in other['parked_trade']['trade_players'] if i!=slot['id']]
    city['map']=_terrain_of(slot);_release(data,city,{s['id'] for s in data['slots']});city['enabled']=bool(enabled)
    return data

def to_player(data,name_id,slot_id=None,presets=None):
    """Create a new player slot for a city. Refused when no city map belongs to it."""
    data=copy.deepcopy(data);city=find(data,name_id)
    if city['role']=='player':raise ValueError('이미 플레이 도시입니다.')
    if city.get('reserved'):raise ValueError('비워 둔 플레이어 자리 도시는 역할을 바꿀 수 없습니다.')
    terrain,older=_city_terrain(data,city,presets)
    used={s['id'] for s in data['slots']}
    if slot_id is None:
        n=len(data['slots'])+1
        while 'player'+str(n) in used:n+=1
        slot_id='player'+str(n)
    if slot_id in used:raise ValueError('이미 쓰는 자리 이름입니다.')
    _occupy(city)
    data['slots'].append(dict(_default_settings(),**older,**terrain,id=slot_id,name_id=name_id))   # a new slot has no values of its own
    return data

def swap_city(data,slot_id,name_id,presets=None,notes=None):
    """Keep the slot and let it play another city. Returns the new project; reasons worth telling the author go to notes."""
    data=copy.deepcopy(data);slot=next((s for s in data['slots'] if s['id']==slot_id),None)
    if slot is None:raise ValueError('없는 플레이어 자리입니다.')
    if slot['name_id']==name_id:return data
    new=find(data,name_id);old=find(data,slot['name_id'])
    if new['role']=='player':raise ValueError('이미 다른 플레이어 자리에서 사용하는 도시입니다.')
    if new.get('reserved'):raise ValueError('비워 둔 플레이어 자리 도시는 배정할 수 없습니다.')
    terrain,older=_city_terrain(data,new,presets)
    old['map']=_terrain_of(slot);_release(data,old,{s['id'] for s in data['slots']});old['enabled']=False
    _occupy(new)
    for key in TERRAIN:slot.pop(key,None)
    slot.update(terrain,name_id=name_id)
    differing=[k for k in older if older[k]!=slot.get(k)]
    if differing and notes is not None:
        notes.append('이 도시에 예전 형식으로 함께 보관돼 있던 설정('+', '.join(differing)+')은 적용하지 않고 자리의 현재 설정을 유지했습니다.')
    return data

def attach_terrain(data,name_id,asset,base=None,presets=None):
    """Give a neutral city a map from another file. Earlier tile edits belong to the old map and are refused rather than dropped."""
    data=copy.deepcopy(data);city=find(data,name_id)
    if city['role']=='player':raise ValueError('플레이 도시의 지형은 지형 탭에서 바꿉니다.')
    body=city.get('map')
    if body and body.get('terrain_edits'):raise ValueError('이 도시에는 이전 지형에 그린 수정이 남아 있습니다. 먼저 수정 내용을 정리하세요.')
    if body is None:
        offered=preset_terrains(name_id,presets)
        if base is None:base=next((i for i in offered if 2<=i<100),offered[0] if offered else 2)   # format needs a preset number; the engine takes the map from the asset
        body=dict(campaign_scenario=base,terrain_edits=[])
    city['map']=dict(body,terrain_asset=asset)
    return data

def detach_terrain(data,name_id):
    """A neutral city's kept terrain (an attached map, or the terrain and edits of an earlier seat) leaves the scenario:
    edits belong to the map they were painted on and go with it."""
    data=copy.deepcopy(data);city=find(data,name_id)
    if city['role']=='player':raise ValueError('플레이 도시의 지형은 지형 탭에서 바꿉니다.')
    city.pop('map',None);return data

def reset_to_c3(data,name_id,c3=None):
    """A neutral city back to Caesar III: the values a new scenario starts with (creator_presets.merged_empire)."""
    data=copy.deepcopy(data);city=find(data,name_id)
    if city['role']=='player':raise ValueError('플레이어 도시는 먼저 플레이어 자리에서 빼 주세요.')
    if c3 is None:
        from creator_presets import merged_empire
        c3=next((c for c in merged_empire()['cities'] if c['name_id']==name_id),None)
    if c3 is None:raise ValueError('C3 자료에서 이 도시를 찾지 못했습니다.')
    for key in ('map','parked_trade','trade_players','sea_auto','reserved'):city.pop(key,None)
    city.update({k:copy.deepcopy(c3[k]) for k in ('x','y','sea','cost','sells','buys','enabled')},role='npc')
    return data

# ---- sea-only trade of neutral cities ------------------------------------------------------------------------
def coast_estimate(template,x,y):
    """Guess from empire-coast.json (cells of the empire picture marked sea/land). No file or no data = no estimate."""
    try:grid=json.loads((HERE/'empire-coast.json').read_text(encoding='utf-8'))['templates'][str(template)]
    except (OSError,ValueError,KeyError):return dict(estimate=None,basis='제국지도 해안 자료(empire-coast.json)가 없어 추정하지 않았습니다.')
    cell=grid['cell'];rows=grid['rows'];cx,cy=x//cell,y//cell;reach=grid.get('reach',1)
    near=[rows[b][a] for b in range(cy-reach,cy+reach+1) for a in range(cx-reach,cx+reach+1) if 0<=b<len(rows) and 0<=a<len(rows[b])]
    if not near:return dict(estimate=None,basis='해안 자료 범위 밖입니다.')
    sea='1' in near
    return dict(estimate=int(sea),basis='제국지도 그림 기준 추정: 주변 '+str(len(near))+'칸 중 바다 '+str(near.count('1'))+'칸. 도시 맵의 실제 해상 연결과는 무관합니다.')

def _neutral(data,name_id):
    city=find(data,name_id)
    if city['role']!='npc':raise ValueError('중립 도시에만 설정할 수 있습니다.')
    return city
def set_sea(data,name_id,sea_only):
    """The author's own choice (checked or unchecked). Ends automatic mode."""
    data=copy.deepcopy(data);city=_neutral(data,name_id);city['sea']=int(bool(sea_only));city.pop('sea_auto',None);return data
def set_sea_auto(data,name_id):
    data=copy.deepcopy(data);city=_neutral(data,name_id);city['sea_auto']=True
    guess=coast_estimate(data['empire']['template'],city.get('x',0),city.get('y',0))
    if guess['estimate'] is not None:city['sea']=guess['estimate']
    return data
def move(data,name_id,x,y):
    """Move a city. Only a city in automatic mode has its sea-only value estimated again."""
    data=copy.deepcopy(data);city=find(data,name_id);city['x'],city['y']=x,y
    if city['role']=='npc' and city.get('sea_auto'):
        guess=coast_estimate(data['empire']['template'],x,y)
        if guess['estimate'] is not None:city['sea']=guess['estimate']
    return data

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__.splitlines()[0]);sub=p.add_subparsers(dest='op',required=True)
    a=sub.add_parser('coast');a.add_argument('template',type=int);a.add_argument('x',type=int);a.add_argument('y',type=int)
    a=sub.add_parser('asset');a.add_argument('map',type=Path)
    a=sub.add_parser('status');a.add_argument('project',type=Path)
    for name in ('to-neutral','to-player'):
        a=sub.add_parser(name);a.add_argument('project',type=Path);a.add_argument('name_id',type=int)
    a=sub.add_parser('swap');a.add_argument('project',type=Path);a.add_argument('slot');a.add_argument('name_id',type=int)
    args=p.parse_args()
    try:
        if args.op=='coast':result=coast_estimate(args.template,args.x,args.y)
        elif args.op=='asset':
            from creator_native_editor import inspect_terrain_file,CACHE
            result=dict(terrain_asset=inspect_terrain_file(args.map,CACHE/'attach'/uuid.uuid4().hex)[0])   # .mapx or .svx
        else:
            import scenario_project
            data=scenario_project.load(args.project)
            if args.op=='status':result=dict(cities=[status(data,c['name_id']) for c in data['empire']['cities']])
            elif args.op=='swap':result=scenario_project.validate(swap_city(data,args.slot,args.name_id))
            else:result=scenario_project.validate(to_neutral(data,args.name_id) if args.op=='to-neutral' else to_player(data,args.name_id))
        print(json.dumps(result,ensure_ascii=False))
    except (ValueError,OSError,RuntimeError) as e:p.exit(1,str(e)+'\n')
