"""Scenario contract view and pre-export checks. Reads the existing scenario.json (schema 1..5); never rewrites it.

Contract. Four facts about a city are kept apart (scenario_cities.status):
  terrain    a city map belongs to it: in a player slot, kept on a neutral city (empire city 'map'), or offered by the preset catalog
  eligible   it may be chosen for play - exactly when it has terrain
  role       how this scenario uses it: player / neutral.  Rome (schema 5, empire.rome) is separate and never has a map
  slot       the player slot holding it (role player only)
A neutral city keeps its map when it has one; using a city as neutral never means "no terrain".
  map source none     no city map belongs to the city (plain neutral trade city, Rome)
             original slot or kept map with campaign_scenario (optionally terrain_edits), or only offered by the catalog
             external slot or kept map with terrain_asset (terrain taken from an imported map)
  trade      neutral: sea-only or land, cost, sells, buys, partners = trade_players (absent = every slot);
                      sea_mode 'manual' (the stored value was chosen) or 'auto' (follows the coast estimate)
             player : partners = the other player cities, always by land
Neutral trade is abstract: the engine never simulates a neutral city's own map (empire/city.c sends its traders into
the player's city), so no terrain check is applied to neutral cities, with or without a map.

Sea trade and fishing are different things:
  sea trade  an outside trade ship enters the player's map at the river entry and reaches a dock (BUILDING_DOCK).
  fishing    a boat from a shipyard (BUILDING_SHIPYARD) serves a wharf (BUILDING_WHARF) at the map's fishing points.
A lake with fishing points can fish without any sea trade; water without fishing points cannot fish at all.

Findings: dict(check, target, severity, reason). Severity:
  block       the engine or an existing rule provably refuses this scenario -> export is refused
  warn        playable, but something the author allowed can never work
  info        stated for the author, no judgement
  unverified  cannot be judged from the file alone (no engine terrain result for the current map)
An unverified finding is never treated as passed. It does not stop an export, with one exception that is
reported separately (result['export']['pending']): the entry-exit route of every player city must have been
verified by the engine for the current map before a shared ZIP is written.

Sources of truth
  entry-exit route, sea access : the engine itself (terrain.json fields 'entry_exit' and 'sea', written by
                                 mp-worker/creator_terrain.h). Python only reads the answer.
  building terrain needs       : coarse "does the map contain that terrain at all" - used for warnings only.
  engine rule tables           : scenario-rules.json, generated from the engine source (tools/gen_scenario_rules.py).
Engine results are cached per map identity (terrain_key) by creator_terrain.validate_project, so a result made
for an older map is never found for a changed one.

Supply assumptions (resources and food): a resource counts as obtainable only when some city can really
produce it (building allowed, terrain present, inputs obtainable) or an enabled neutral city sells it to a
city that can reach it. Players can always trade with each other by land (project rule), so such a supply
can be passed on - but trade alone never creates a supply. Whether players will cooperate is not judged.
"""
import argparse,hashlib,json,sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import trade_policy
LABEL=dict(block='막힘',warn='경고',info='정보',unverified='미검증')
ORDER=('block','warn','unverified','info')
# Severity per check. Raising a 'warn' to 'block' here is the only change needed to make it stop an export.
POLICY={'format':'block','preset':'block','throne':'block','entry-exit':'block',
        'resource':'warn','food':'warn','terrain-building':'warn','sea':'warn','fishing':'warn',
        'npc-partners':'warn','online-limit':'warn','throne-runtime':'warn','overlap':'warn','rome-position':'block','throne-favor':'block',
        'progress-goods':'warn','invasion-point':'block','race':'warn','map-file':'block'}
WATER,ROCK,TREE,SHRUB,MEADOW=4,2,1,16,2048
ROAD,ELEVATION=1<<6,1<<9
DOCK,WHARF,SHIPYARD,FISH=75,76,74,5
SEA_TRADE_BUILDINGS=[DOCK]   # empire/city.c: a trade ship is only sent when the city has a working dock
EVIDENCE=HERE/'creator-cache'/'terrain-evidence'

def rules():return json.loads((HERE/'scenario-rules.json').read_text(encoding='utf-8'))
def names():
    from scenario_overview import RES
    try:buildings={r['id']:r['name'] for r in json.loads((HERE/'building-catalog.json').read_text(encoding='utf-8-sig'))}
    except OSError:buildings={}
    try:cities={r['name_id']:r['name'] for r in json.loads((HERE/'creator-city-catalog.json').read_text(encoding='utf-8-sig'))}
    except OSError:cities={}
    return RES,buildings,cities

def city_model(data):
    """The contract view: one row per empire city (plus Rome), in file order."""
    import scenario_cities
    slots={s['name_id']:s for s in data['slots']};every=[s['id'] for s in data['slots']];rows=[]
    transport=data['rules'].get('player_transport','land') if isinstance(data['rules'],dict) else 'land'
    for c in data['empire']['cities']:
        slot=slots.get(c['name_id']) if c['role']=='player' else None
        state=scenario_cities.status(data,c['name_id'])
        if slot:
            rows.append(dict(kind='player',role='player',name_id=c['name_id'],slot=slot['id'],enabled=True,x=c.get('x'),y=c.get('y'),
                has_terrain=True,eligible=True,map=state['terrain'],
                funds=dict(amount=slot.get('starting_funds',data['rules'].get('starting_funds')) if isinstance(data['rules'],dict) else None,source='slot' if 'starting_funds' in slot else 'common'),
                role_hint=slot.get('role_hint'),
                trade=dict(transport=transport,partners=[i for i in every if i!=slot['id'] and trade_policy.allowed(data['rules'],slot['id'],i)],cost=0,sells={},buys={})))
        else:
            rows.append(dict(kind='neutral',role='neutral',name_id=c['name_id'],slot=None,enabled=c.get('enabled',True),reserved=bool(c.get('reserved')),x=c.get('x'),y=c.get('y'),
                has_terrain=state['has_terrain'],eligible=state['eligible'] and not c.get('reserved'),map=state['terrain'],
                trade=dict(transport='sea' if c['sea'] else 'land',sea_mode=state['sea_mode'],partners=list(c.get('trade_players',every)),cost=c['cost'],sells=dict(c['sells']),buys=dict(c['buys']))))
    rome=data['empire'].get('rome')
    if rome:rows.append(dict(kind='rome',role='rome',name_id=None,slot=None,enabled=True,x=rome['x'],y=rome['y'],has_terrain=False,eligible=False,map=dict(source='none'),trade=None))
    return rows

# ---- terrain facts (engine terrain.json) -------------------------------------------------------------------
def terrain_facts(t):
    """Reduce an engine terrain.json to the facts the checks use. Missing engine fields stay None (unknown)."""
    f=t['terrain_flags'];w,h=t['width'],t['height']
    def inside(x,y):return 0<=x<w and 0<=y<h
    facts=dict(meadow=any(v&MEADOW for v in f),rock=any(v&ROCK for v in f),tree=any(v&(TREE|SHRUB) for v in f),
               water=any(v&(WATER|1<<23) for v in f))
    facts['distant_water']=facts['water']
    facts['shore']=any(f[y*w+x]&WATER and any(inside(a,b) and not f[b*w+a]&(WATER|ROCK) for a,b in ((x+1,y),(x-1,y),(x,y+1),(x,y-1))) for y in range(h) for x in range(w))
    sea=t.get('sea');route=t.get('entry_exit')
    # Sea trade (outside trade ships -> dock). 'blocked' is the engine's confirmed "no"; 'candidate' means the engine's dock
    # placement rule passes somewhere with nothing unclearable under it - road access, money and labour are not checked.
    if isinstance(sea,dict):
        clear=sea.get('dock_sites_clear')
        if not sea['river_entry']:state,reason='blocked','맵에 뱃길 입구가 지정되어 있지 않아 무역선이 들어올 수 없습니다.'
        elif not sea['open_water']:state,reason='blocked','뱃길 입구가 배가 다닐 수 있는 물이 아닙니다.'
        elif not sea['dock_sites']:state,reason='blocked','무역선이 다니는 물길에 닿는 부두 자리가 없습니다.'
        elif clear is None or clear==0:state,reason='unknown','부두 자리 후보가 모두 바위·건물 등에 걸려 있어 확정하지 못했습니다.' if clear==0 else ''
        else:state,reason='candidate','부두 자리 후보 '+str(clear)+'곳(배치 규칙 통과. 도로 연결 등은 확인하지 않음)'
        facts['sea']=dict(state=state,reason=reason);facts['open_water']=sea['open_water']>0
    else:facts['sea']=None;facts['open_water']=None
    # Fishing (shipyard -> wharf -> fishing points). Independent of sea trade.
    fish=t.get('fishing')
    if isinstance(fish,dict):
        if not fish['points']:state,cause,reason='blocked','no-points','맵에 어장이 없습니다.'
        elif not fish['sites']:state,cause,reason='blocked','no-sites','어장은 있지만, 어선이 어장까지 갈 수 있는 물가에 선창·조선소를 놓을 자리가 없습니다.'
        elif not fish['two_sites']:state,cause,reason='blocked','one-site','어장은 있지만, 어장과 이어진 물가에 선창과 조선소를 함께 놓을 자리가 없습니다.'
        else:state,cause,reason='candidate','','어장 '+str(fish['points'])+'곳, 물가 자리 후보 '+str(fish['sites'])+'곳'
        facts['fishing']=dict(state=state,cause=cause,reason=reason)
    else:facts['fishing']=None
    # Enemy entry points (2026-11-15): usable as the city's game checks them (creator_city_invasions.h
    # creator_invasion_point_valid: on the map, not on high ground, rock or trees, water only under a road), and the exit
    # point, which an attack on the automatic point falls back to. None = an older engine result without them.
    def usable(p):
        if not isinstance(p,list) or len(p)!=2 or not inside(p[0],p[1]):return False
        v=f[p[1]*w+p[0]]
        return not v&(ELEVATION|ROCK|TREE) and not (v&WATER and not v&ROAD)
    points=t.get('invasion_points')
    facts['invasion_points']=[usable(p) for p in points] if isinstance(points,list) else None
    facts['exit_usable']=usable(t.get('exit')) if isinstance(points,list) else None
    if isinstance(route,dict) and -1 not in (route['now'],route['cleared'],route['bridged']):
        facts['road']='now' if route['now'] else 'cleared' if route['cleared'] else 'bridged' if route['bridged'] else 'cut'
    else:facts['road']=None
    return facts

# ---- engine results for the current map ----------------------------------------------------------------------
_worker=[]
def worker_hash():
    if not _worker:
        p=HERE/'engine-city-test.exe';_worker.append(hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else '')
    return _worker[0]
def terrain_key(slot):
    """Identity of one city's map as the engine builds it. Any change to the map or to the engine gives a new key."""
    asset=slot.get('terrain_asset')
    body=dict(preset=slot['campaign_scenario'],edits=slot.get('terrain_edits',[]),asset=asset['sha256'] if asset else None,
              setup=slot.get('starting_setup'),worker=worker_hash())
    return hashlib.sha256(json.dumps(body,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def salary_facts(governance):
    """Salary base and the engine's own monthly amount for ranks 0..10 (city_emperor_salary_for_rank), from the
    governance-audit.json of the same engine start. None when the worker did not report them (older worker)."""
    if not isinstance(governance,dict):return None
    base,table=governance.get('caesar_salary'),governance.get('salary_for_rank')
    if type(base)!=int or not isinstance(table,list) or len(table)!=11 or any(type(v)!=int for v in table):return None
    return dict(base=base,by_rank=table)
def store_evidence(slot,terrain,governance=None):
    """Called by the engine check (creator_terrain.validate_project) with the terrain.json it just produced and the
    governance-audit.json of the same start (salary base; it depends on the map and the start path, not on governance)."""
    EVIDENCE.mkdir(parents=True,exist_ok=True);key=terrain_key(slot)
    facts=terrain_facts(terrain);facts['salary']=salary_facts(governance)
    (EVIDENCE/(key+'.json')).write_text(json.dumps(dict(schema=3,key=key,facts=facts),ensure_ascii=False),encoding='utf-8')
    return key
def evidence(data):
    """{slot id: facts} for every slot whose current map already has an engine result."""
    found={}
    for slot in data['slots']:
        p=EVIDENCE/(terrain_key(slot)+'.json')
        try:
            row=json.loads(p.read_text(encoding='utf-8'))
            if row.get('schema')==3 and row.get('key')==p.stem:found[slot['id']]=row['facts']
        except (OSError,ValueError,KeyError):pass
    return found

def load_terrain(directory,slots):
    """directory/<slot id>/terrain.json, as written by creator_terrain.validate_project. Missing files stay unknown."""
    result={}
    for s in slots:
        p=Path(directory)/s/'terrain.json'
        if p.is_file():result[s]=json.loads(p.read_text(encoding='utf-8'))
    return result

# ---- checks ------------------------------------------------------------------------------------------------
def check(data,terrain=None,facts=None):
    """data must already have passed scenario_project.validate.
    terrain: {slot id: engine terrain.json}; facts: {slot id: terrain_facts} (e.g. from evidence()). Neither = nothing known."""
    R=rules();RES,BN,CN=names();out=[]
    def add(kind,target,reason,severity=None,**extra):out.append(dict(check=kind,target=target,severity=severity or POLICY[kind],reason=reason,**extra))
    def bname(b):return BN.get(b,'건물 #'+str(b))
    def rname(r):return RES.get(int(r),'자원 #'+str(r))
    model=city_model(data);players=[c for c in model if c['kind']=='player'];slots={s['id']:s for s in data['slots']}
    facts=dict(facts or {});facts.update({s:terrain_facts(t) for s,t in (terrain or {}).items()})
    facts={s:f for s,f in facts.items() if s in slots}
    title=lambda c:CN.get(c['name_id'],'도시 '+str(c['name_id']))+(' ('+c['slot']+')' if c['slot'] else '')

    # the original map file each seat is started from, on this PC (2026-11-15: a received scenario on a PC without a
    # .map file failed with 'engine operation rejected: 92' when the room was made)
    try:
        import creator_presets
        for slot,map_title,file in creator_presets.missing_maps(data):
            c=next((x for x in players if x['slot']==slot),None)
            add('map-file',title(c) if c else slot,f"이 도시가 시작하는 원본 지도 '{map_title}' ({file})가 이 PC의 시저 3 폴더에 없습니다. 이대로는 게임을 시작할 수 없습니다. 만든 사람에게 이 도시의 지형을 지도 파일로 넣어 달라고 하세요.")
    except (OSError,ValueError,KeyError):pass
    if data['schema'] in (3,4):   # presets the engine can lay out (existing rule: scenario_project.require_layout)
        import scenario_project
        try:scenario_project.require_layout(data)
        except ValueError as e:add('preset','시나리오',str(e))
    if data['schema']==5:
        add('throne','황위 규칙','수치와 로마 위치가 기존 범위 검사(throne_state.validate_spec)를 통과했습니다.','info')
        import throne_rules,scenario_project
        if throne_rules.is_test(data['rules']['throne']):
            spec=data['rules']['throne'];total=sum(s['cost'] for s in spec['stages']);months=(len(spec['stages'])-1)*spec['attempt_months']
            labels=dict(standard='표준',short='짧은 판',long='긴 판');preset=throne_rules.preset_of(spec)
            add('throne-runtime','시나리오',f"황위 쟁탈전 ({labels.get(preset,'사용자 설정')}): 5단계까지 최소 지원금 합계 {total:,} Dn, 한 번도 실패하지 않아도 최소 {months}개월이 걸립니다.",'info')
            funds=[s.get('starting_funds',data['rules']['starting_funds']) for s in data['slots']]
            if funds and max(funds)>=total:add('throne-runtime','시나리오',f'시작 자금({max(funds):,} Dn)만으로 5단계까지의 최소 지원금 합계({total:,} Dn)를 낼 수 있습니다. 너무 빨리 끝날 수 있습니다.')
            elif funds and spec['stages'][0]['cost']>20*max(1,min(funds)):add('throne-runtime','시나리오',f"첫 쿠데타의 최소 지원금({spec['stages'][0]['cost']:,} Dn)이 시작 자금({min(funds):,} Dn)의 20배를 넘습니다. 첫 쿠데타까지 오래 걸립니다.")
            try:scenario_project.require_layout(data)
            except ValueError as e:add('preset','시나리오',str(e))
        else:add('throne-runtime','시나리오','황위 쟁탈전은 아직 저장 단계라 게임에서 실행할 수 없습니다(기존 규칙).')
        # Paranoia (throne) and the original favour are separate; in this mode the original favour rules must run.
        # A slot whose governance pins favour ('fixed') would switch them off: reported, never changed silently.
        for s_ in data['slots']:
            g=s_.get('governance')
            if g and g.get('policy')=='fixed':
                c=next((m for m in model if m['slot']==s_['id']),None)
                add('throne-favor',title(c) if c else s_['id'],"황위 쟁탈전에서는 원본 황제 호감도 규칙(봉급·선물·공물·분노·황제군)이 작동해야 합니다. 이 자리의 '지지도 고정'을 '원본 규칙'으로 바꿔 주세요. 황제 편집증과는 별개입니다(값은 바꾸지 않았습니다).")
        add('rome','로마','맵 없는 도시로 기록되어 있습니다. 지형·연결 검사 대상이 아닙니다.','info')
    if len(data['slots'])>6:add('online-limit','시나리오',f"{len(data['slots'])}자리 중 최대 6명이 골라서 플레이합니다. 고르지 않은 자리는 중립 도시가 됩니다.",'info')
    seen={}
    for c in model:
        if c['enabled'] and c['x'] is not None:
            other=seen.setdefault((c['x'],c['y']),c)
            if other is not c:add('overlap',title(c) if c['kind']!='rome' else '로마','제국 지도에서 '+(title(other) if other['kind']!='rome' else '로마')+'와 같은 좌표입니다.')
    # Rome is shown in every mode at its fixed place; a city on top of it is reported, never moved.
    import rome_capital
    rome_x,rome_y,rome_source=rome_capital.position(data)
    for city,distance in rome_capital.conflicts(data):
        row=next(m for m in model if m['name_id']==city['name_id'])
        add('rome-position',title(row),f"로마(고정 수도) 자리와 겹칩니다(중심 사이 {distance}, {rome_capital.spec()['keep_clear']} 이상 떨어져야 함). 지도에서 이 도시를 옮겨 주세요. 도시와 로마 정보는 바꾸지 않았습니다.",
            None if row['kind']=='player' or row['enabled'] else 'info')
    for c in model:
        if c['kind']=='neutral' and c['enabled'] and not c.get('reserved') and (c['trade']['sells'] or c['trade']['buys']) and not c['trade']['partners']:
            add('npc-partners',title(c),'교역 품목은 있는데 교역을 허용한 플레이어가 없습니다.')

    # ---- per city abilities. Tri-state: True / None (no engine result) / False (confirmed) ----
    def allowed(c):return slots[c['slot']]['allowed_buildings']
    def terrain_ok(c,b):
        need=R['terrain_required'].get(str(b))
        if not need:return True
        f=facts.get(c['slot'])
        if f is None or f.get(need) is None:return None
        return bool(f[need])
    def can_build(c,b):return False if b not in allowed(c) else terrain_ok(c,b)
    tri=lambda part:None if part is None or part['state']=='unknown' else part['state']=='candidate'
    def sea_state(c):   # outside trade ships: True candidate / False confirmed impossible / None unknown
        f=facts.get(c['slot']);return None if f is None else tri(f.get('sea'))
    def fish_state(c):  # fishing: needs a wharf and a shipyard allowed, fishing points and shore next to them
        if WHARF not in allowed(c) or SHIPYARD not in allowed(c):return False
        f=facts.get(c['slot']);return None if f is None else tri(f.get('fishing'))
    def can_make(c,r,b):return fish_state(c) if r==FISH else can_build(c,b)
    def sea_trade(c):   # can this city actually trade by sea (map allows it and the author allows a dock)
        if not any(b in allowed(c) for b in SEA_TRADE_BUILDINGS):return False
        return sea_state(c)
    sea_ports=lambda c:[n for n in model if n['kind']=='neutral' and n['enabled'] and n['trade']['transport']=='sea' and c['slot'] in n['trade']['partners'] and (n['trade']['sells'] or n['trade']['buys'])]
    raws={};[raws.setdefault(x['good'],[]).append(x['raw']) for x in R['supply_chain']]
    def reach(optimistic):
        """Fixpoint from real sources only: neutral sellers and local production. Player trade passes supplies on, never creates them."""
        yes=lambda v:v is True or (optimistic and v is None)
        have={c['slot']:set() for c in players}
        for c in players:
            for n in model:
                if n['kind']=='neutral' and n['enabled'] and c['slot'] in n['trade']['partners'] and (n['trade']['transport']=='land' or yes(sea_trade(c))):
                    have[c['slot']].update(int(r) for r in n['trade']['sells'])
        changed=True
        while changed:
            changed=False
            for c in players:
                mine=have[c['slot']]
                for r,b in R['industry'].items():
                    r=int(r)
                    if r not in mine and yes(can_make(c,r,b)) and all(x in mine for x in raws.get(r,[])):mine.add(r);changed=True
                for o in players:   # players reach each other by land (project rule) unless the scenario forbids the pair
                    if o is not c and trade_policy.allowed(data['rules'],c['slot'],o['slot']) and have[o['slot']]-mine:mine.update(have[o['slot']]);changed=True
        return have
    sure,maybe=reach(False),reach(True)
    def why_missing(c,r):
        b=R['industry'][str(r)];parts=[]
        if r==FISH and fish_state(c) is False:
            f=facts.get(c['slot'])
            parts.append('선창 또는 조선소 미허용' if WHARF not in allowed(c) or SHIPYARD not in allowed(c) else f['fishing']['reason'])
        elif b not in allowed(c):parts.append(bname(b)+' 미허용')
        elif terrain_ok(c,b) is False:parts.append(bname(b)+'을(를) 지을 지형이 없음')
        else:
            lack=[rname(x) for x in raws.get(r,[]) if x not in maybe[c['slot']]]
            if lack:parts.append('원료('+', '.join(lack)+')가 없음')
        sellers=[n for n in model if n['kind']=='neutral' and n['enabled'] and str(r) in n['trade']['sells'] and c['slot'] in n['trade']['partners']]
        parts.append('파는 중립 도시가 해상뿐인데 이 도시는 해상 교역을 할 수 없음' if sellers else '이 도시에 파는 중립 도시 없음')
        parts.append('생산하거나 사 올 수 있는 다른 플레이어 도시 없음')
        return '; '.join(parts)

    limits=[]
    for c in players:
        f=facts.get(c['slot']);can=set(allowed(c));needs={}
        for b in can:
            for r in R['construction_resources'].get(str(b),{}):needs.setdefault(int(r),[]).append(b)
        for r,b in R['industry'].items():
            if b in can:
                for raw in raws.get(int(r),[]):needs.setdefault(raw,[]).append(b)
        if 185 in can:   # city mint turns gold into denarii (supply chain entry with no trade good)
            for raw in raws.get(22,[]):
                if 185 not in needs.setdefault(raw,[]):needs[raw].append(185)
        unknown=[]
        for r in sorted(needs):
            users=', '.join(bname(b) for b in sorted(set(needs[r]))[:6])+(' 외' if len(set(needs[r]))>6 else '')
            if r in sure[c['slot']]:continue
            if r in maybe[c['slot']]:unknown.append(rname(r))
            else:add('resource',title(c),f'{rname(r)}을(를) 얻을 방법이 없습니다({why_missing(c,r)}). 쓰는 건물: {users}')
        if unknown:add('resource',title(c),'현재 맵의 엔진 검사 결과가 없어 얻을 수 있는지 판정하지 못한 자원: '+', '.join(unknown),'unverified')
        food=set(R['food'])
        if not food&sure[c['slot']]:
            if food&maybe[c['slot']]:add('food',title(c),'현재 맵의 엔진 검사 결과가 없어 식량을 얻을 수 있는지 판정하지 못했습니다.','unverified')
            else:add('food',title(c),'식량을 얻을 방법이 없습니다(농장을 지을 수 없고 어업도 불가하며, 식량을 파는 중립 도시와 식량을 가진 다른 플레이어 도시도 없음).')
        # Fishing notice: only about the fishing wharf the author allowed in this player slot. Food supply is judged above, separately.
        fishing=None if f is None else f.get('fishing')
        if WHARF in can:
            if fishing is None:add('fishing',title(c),'어업용 선창을 허용했지만, 현재 맵의 엔진 검사 결과가 없어 어장이 있는지 확인하지 못했습니다.','unverified')
            elif fishing['cause']=='no-points':add('fishing',title(c),'어업용 선창을 허용했지만 이 도시에는 어장이 없습니다. 선창을 지어도 생선을 얻을 수 없습니다(선택값은 그대로 둠).')
            elif fishing['state']=='blocked':add('fishing',title(c),'어업용 선창을 허용했지만 어업을 할 수 없습니다: '+fishing['reason'])
            elif SHIPYARD not in can:add('fishing',title(c),'어업용 선창을 허용했지만 어선을 만드는 조선소가 허용되어 있지 않습니다. 어장은 있습니다.')
        # sea access of this city
        state=sea_state(c);ports=sea_ports(c);docks=[b for b in SEA_TRADE_BUILDINGS if b in can]
        limit=dict(slot=c['slot'],sea='unknown' if state is None else 'candidate' if state else 'blocked',reason='' if f is None or not f.get('sea') else f['sea']['reason'],buildings=[],sea_neutrals=[],
                   fishing='unknown' if f is None or not f.get('fishing') else f['fishing']['state'],
                   salary=None if f is None else f.get('salary'))   # engine salary amounts for this map; None = not checked yet
        if state is None:
            add('sea',title(c),'외부 해상 교역이 가능한지 판정하지 못했습니다'+('('+f['sea']['reason']+')' if f and f.get('sea') and f['sea']['reason'] else ': 현재 맵의 엔진 검사 결과가 없습니다')+'.','unverified')
        elif not state:
            limit.update(reason=f['sea']['reason'],buildings=list(SEA_TRADE_BUILDINGS),sea_neutrals=[n['name_id'] for n in ports])
            text='외부 해상 교역 불가: '+f['sea']['reason']+' 플레이어 간 육로 거래, 육로 중립 도시 거래, 어업(선창·조선소)은 이것과 무관합니다.'
            if docks:text+=' 허용 건물의 '+', '.join(bname(b) for b in docks)+'은(는) 이 도시에서 지을 수 없습니다(선택값은 지우지 않았습니다).'
            if ports:text+=' 해상 중립 도시('+', '.join(title(n) for n in ports)+')와의 거래는 이루어지지 않습니다(교역 허용 값은 지우지 않았습니다).'
            add('sea',title(c),text,'warn' if docks or ports else 'info')
        elif ports and not docks:
            add('sea',title(c),'해상 중립 도시('+', '.join(title(n) for n in ports)+')와 교역하려면 부두가 필요한데 허용 건물에 없습니다.')
        elif ports:
            add('sea',title(c),'외부 해상 교역 가능 후보: '+f['sea']['reason']+'. 확정이 아닙니다.','info')
        limits.append(limit)
        # buildings whose terrain the map lacks (coarse: the terrain does not exist anywhere on the map)
        if f is None:add('terrain-building',title(c),'현재 맵의 엔진 검사 결과가 없어 건물의 지형 조건을 판정하지 못했습니다.','unverified')
        else:
            lacking={}
            for b in sorted(can):
                need=R['terrain_required'].get(str(b))
                if need and f.get(need) is False and not (b in SEA_TRADE_BUILDINGS and state is False) and not (b in (WHARF,SHIPYARD) and fishing):lacking.setdefault(need,[]).append(b)
            words=dict(meadow='목초지',rock='바위',tree='나무',water='물',distant_water='물',shore='물가',open_water='배가 다니는 물길')
            for need,bs in lacking.items():add('terrain-building',title(c),f"맵에 {words[need]}이(가) 없어 지을 수 없습니다: "+', '.join(bname(b) for b in bs))
        # enemy entry points of this city's attacks: a point the map does not have stops the city from being made
        attacks=slots[c['slot']].get('invasions',[]);points=None if f is None else f.get('invasion_points')
        if attacks and points is not None:
            for k,e in enumerate(attacks,1):
                if e['point']>0 and not (e['point']<=len(points) and points[e['point']-1]):
                    add('invasion-point',title(c),f"침략 {k} ({e['month']}개월): 진입점 {e['point']}번이 이 지도에 없거나 적군이 설 수 없는 칸입니다. 게임을 시작할 수 없으니 침략 설정에서 다른 진입점(또는 자동)을 고르세요.")
                elif e['point']==0 and not any(points) and not f.get('exit_usable'):
                    add('invasion-point',title(c),f"침략 {k} ({e['month']}개월): 이 지도에는 적군이 들어올 진입점이 없습니다(출구도 쓸 수 없음). 게임을 시작할 수 없으니 이 침략을 지우세요.")
        # entry-exit route: the engine's answer only
        road=None if f is None else f['road']
        if road is None:add('entry-exit',title(c),'입구·출구 연결 검증 미완료: 현재 맵에 대한 엔진 검사 결과가 없습니다. 에디터의 "게임 적용 검사"를 실행하세요.','unverified',required=True)
        elif road=='cut':add('entry-exit',title(c),'입구·출구 단절 확정: 나무를 치우고 놓을 수 있는 다리를 모두 놓아도 입구에서 출구까지 갈 수 없습니다(엔진 판정).')
        elif road=='cleared':add('entry-exit',title(c),'입구에서 출구까지 가려면 나무를 치워야 합니다(엔진 판정: 연결 가능).','info')
        elif road=='bridged':add('entry-exit',title(c),'입구에서 출구까지 가려면 다리를 놓아야 합니다(엔진 판정: 연결 가능).','info')
    # 황제의 순행 goods (user 2026-11-15): each candidate good must be obtainable by every city in the same way as the
    # resources above: made in the city, bought from a neutral city that trades with it, or passed on by another player.
    if data['rules'].get('mode')=='imperial-progress' and isinstance(data['rules'].get('progress'),dict):
        goods=[int(g) for g in data['rules']['progress'].get('goods',[])];fine=True
        for r in goods:
            none=[c for c in players if r not in maybe[c['slot']]]
            unknown=[c for c in players if r not in sure[c['slot']] and r in maybe[c['slot']]]
            if none and len(none)==len(players):fine=False;add('progress-goods','황제의 순행',f'순행 물품 {rname(r)}: 어느 도시도 생산하거나 사 올 수 없습니다. 이 물품이 뽑히면 황제를 맞는 도시는 전부 부족분을 돈으로 냅니다.')
            elif none:fine=False;add('progress-goods','황제의 순행',f'순행 물품 {rname(r)}: 얻을 방법이 없는 도시가 있습니다: '+', '.join(title(c)+'('+why_missing(c,r)+')' for c in none))
            if unknown:fine=False;add('progress-goods','황제의 순행',f'순행 물품 {rname(r)}: 현재 맵의 엔진 검사 결과가 없어 얻을 수 있는지 판정하지 못한 도시: '+', '.join(title(c) for c in unknown),'unverified')
        if goods and fine:add('progress-goods','황제의 순행',f'순행 물품 {len(goods)}가지 모두 모든 도시가 얻을 수 있습니다(직접 생산, 중립 도시 구매, 다른 플레이어와의 교역 포함).','info')
    # 기한 경쟁 on the emperor's favour: a city whose favour is pinned (governance 'fixed') cannot move it (2026-11-15)
    race=data['rules'].get('race') if data['rules'].get('mode')=='deadline-race' else None
    if isinstance(race,dict) and race.get('stat')=='favor':
        pinned=[c for c in players if (slots[c['slot']].get('governance') or {}).get('policy')=='fixed']
        if pinned:add('race','기한 경쟁','비교 수치가 황제 지지도인데, 지지도를 고정한 도시가 있습니다: '+', '.join(title(c) for c in pinned)+'. 이 도시들의 지지도는 움직이지 않습니다. 3 플레이 자리 설정의 통치자·황제 지지도 탭에서 원본 규칙으로 바꾸거나 다른 수치를 고르세요.')
    if 'starting_funds' in data['rules']:add('funds','시나리오',f"도시별 시작 자금 {data['rules']['starting_funds']:,}",'info')
    # ---- trade links: one judgement for the editor map, the lobby and these checks ----
    # allowed  what the author set (neutral: trade_players; players: trade_policy)
    # state    whether the route works: ok (land), candidate (sea, engine placement rule passes), broken (confirmed impossible),
    #          unknown (no engine result). A link that is not allowed carries state 'off' and is hidden by default.
    # goods    what a neutral city sells/buys. No goods is reported apart from the route; it never makes a route broken.
    links=[]
    for c in players:
        rows=[]
        for o in players:
            if o is c:continue
            ok,source=trade_policy.decide(data['rules'],c['slot'],o['slot'])
            rows.append(dict(kind='player',slot=o['slot'],name_id=o['name_id'],transport='land',allowed=ok,allow_source=source,
                             state='ok' if ok else 'off',reason='플레이어 도시끼리는 육로로 교역합니다.' if ok else '시나리오 설정에서 두 도시의 교역을 막았습니다.',
                             approximate=True,sells=[],buys=[]))
        for n in model:
            if n['kind']!='neutral' or not n['enabled'] or n.get('reserved'):continue   # unused and reserved cities are not trade partners
            ok=c['slot'] in n['trade']['partners'];sea=n['trade']['transport']=='sea'
            if not ok:state,reason='off','이 중립 도시와의 교역을 허용하지 않았습니다.'
            elif not sea:state,reason='ok','육로 교역'
            else:
                v=sea_trade(c);f=facts.get(c['slot'])
                if v is True:state,reason='candidate','해상 교역 가능 후보: '+f['sea']['reason']
                elif v is None:state,reason='unknown','해상 교역 가능 여부 미확인'+(': '+f['sea']['reason'] if f and f.get('sea') and f['sea']['reason'] else ': 현재 맵의 엔진 검사 결과가 없습니다')
                elif not any(b in allowed(c) for b in SEA_TRADE_BUILDINGS):state,reason='broken','해상 교역 불가: 부두가 허용 건물에 없습니다.'
                else:state,reason='broken','해상 교역 불가: '+f['sea']['reason']
            rows.append(dict(kind='neutral',slot=None,name_id=n['name_id'],transport='sea' if sea else 'land',allowed=ok,allow_source='neutral',
                             state=state,reason=reason,approximate=True,sells=sorted(int(k) for k in n['trade']['sells']),buys=sorted(int(k) for k in n['trade']['buys'])))
        links.append(dict(slot=c['slot'],name_id=c['name_id'],links=rows))
    result=report(out);result['limits']=limits;result['links']=links
    result['rome']=dict(name=rome_capital.spec()['name'],x=rome_x,y=rome_y,source=rome_source,keep_clear=rome_capital.spec()['keep_clear'])
    return result

def report(findings):
    findings=sorted(findings,key=lambda f:ORDER.index(f['severity']))
    for f in findings:f['label']=LABEL[f['severity']]
    counts={k:sum(f['severity']==k for f in findings) for k in ORDER}
    blocks=[f for f in findings if f['severity']=='block'];pending=[f for f in findings if f.get('required') and f['severity']=='unverified']
    return dict(schema=2,blocked=bool(blocks),counts=counts,findings=findings,limits=[],
                export=dict(allowed=not blocks and not pending,blocks=blocks,pending=pending))

def check_file(path,terrain_dir=None):
    """Whole pipeline for a file on disk. A file the existing loader refuses is one 'format' block."""
    import scenario_project
    try:data=scenario_project.load(path)
    except (ValueError,KeyError,TypeError) as e:
        return report([dict(check='format',target='시나리오 파일',severity=POLICY['format'],reason=str(e) or type(e).__name__)])
    terrain=load_terrain(terrain_dir,[s['id'] for s in data['slots']]) if terrain_dir else None
    result=check(data,terrain,evidence(data));result['cities']=city_model(data);return result

def gate(data,terrain=None,facts=None):
    """Shared-ZIP contract. Refuses when a block exists, or when a player city's entry-exit route has no engine result
    for the current map. Other warnings and unverified items never stop an export. Saving a project does not come here."""
    result=check(data,terrain,evidence(data) if facts is None and terrain is None else facts);e=result['export']
    if not e['allowed']:
        lines=['내보낼 수 없습니다.']
        if e['blocks']:lines+=['[막힘] 먼저 고쳐야 할 항목:']+['- '+f['target']+': '+f['reason'] for f in e['blocks']]
        if e['pending']:lines+=['[검증 미완료] 내보내기 전에 검증이 필요한 항목:']+['- '+f['target']+': '+f['reason'] for f in e['pending']]
        raise ValueError('\n'.join(lines))
    return result

def text(result):
    lines=[f"막힘 {result['counts']['block']} · 경고 {result['counts']['warn']} · 미검증 {result['counts']['unverified']} · 정보 {result['counts']['info']}"
           +(' · 내보내기 가능' if result['export']['allowed'] else ' · 내보내기 불가')]
    lines+=[f"[{f['label']}] {f['target']}: {f['reason']}" for f in result['findings']]
    return '\n'.join(lines)

if __name__=='__main__':
    p=argparse.ArgumentParser(description='Scenario pre-export checks');p.add_argument('project',type=Path)
    p.add_argument('--terrain-dir',type=Path,help='folder with <slot id>/terrain.json from the engine check');p.add_argument('--text',action='store_true')
    p.add_argument('--limits',action='store_true',help='only the per-city limits the editor shows (never fails)')
    p.add_argument('--links',action='store_true',help='per-city limits and trade links for the editor map and the lobby (never fails)')
    a=p.parse_args();r=check_file(a.project,a.terrain_dir)
    if a.limits:print(json.dumps(dict(limits=r.get('limits',[])),ensure_ascii=False));sys.exit(0)
    if a.links:   # one call feeds the editor map, slot pages and the validation page
        print(json.dumps(dict(limits=r.get('limits',[]),links=r.get('links',[]),rome=r.get('rome'),blocked=r['blocked'],counts=r['counts'],findings=r['findings'],
            export=dict(allowed=r['export']['allowed'],blocks=len(r['export']['blocks']),pending=len(r['export']['pending']))),ensure_ascii=False));sys.exit(0)
    print(text(r) if a.text else json.dumps(r,ensure_ascii=False))
    sys.exit(1 if r['blocked'] else 0)
