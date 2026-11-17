"""Creator v1..v4 runtime, v5 Throne data authoring. No game graphics embedded."""
import argparse
import base64
import binascii
import hashlib
import json
import re
import zipfile
from pathlib import Path

from multiplayer_limits import MAX_ONLINE_PLAYERS

HERE = Path(__file__).resolve().parent
DEFAULT = HERE / 'scenarios/capua-tarentum/scenario.json'

def integer(value, low, high, field):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{field}: integer {low}..{high} required')

def keys(obj, expected, field):
    if not isinstance(obj, dict) or set(obj) != set(expected.split()):
        raise ValueError(f'{field}: invalid or unsupported fields')


def decode_terrain_asset(asset):
    keys(asset,'format sha256 data','terrain asset')
    if asset['format']!='augustus-mapx':raise ValueError('지원하지 않는 지도 형식입니다.')
    if not isinstance(asset['sha256'],str) or not re.fullmatch('[0-9a-f]{64}',asset['sha256']):raise ValueError('지도 해시가 올바르지 않습니다.')
    if not isinstance(asset['data'],str) or len(asset['data'])>11184812:raise ValueError('지도 자료가 너무 큽니다.')
    try:raw=base64.b64decode(asset['data'],validate=True)
    except (ValueError,binascii.Error):raise ValueError('지도 자료의 인코딩이 올바르지 않습니다.')
    if not 1<=len(raw)<=8388608 or hashlib.sha256(raw).hexdigest()!=asset['sha256']:raise ValueError('지도 자료 해시가 일치하지 않습니다.')
    return raw

RACE_STATS=('population','culture','prosperity','peace','favor','treasury')   # objectives.METRICS
def validate_race(race):
    """기한 경쟁 (2026-11-15): after `months` months the city with the most of `stat` wins (objectives.py)."""
    keys(race,'stat months','race')
    if race['stat'] not in RACE_STATS:raise ValueError('기한 경쟁의 비교 수치가 올바르지 않습니다.')
    integer(race['months'],6,600,'기한 경쟁 기간 (개월)')

def validate_objectives(obj,slot_ids):
    keys(obj,'population_total per_city'+(' celebration' if 'celebration' in obj else '')+(' treasury_total' if 'treasury_total' in obj else '')+(' deliveries' if 'deliveries' in obj else '')+(' by_players' if 'by_players' in obj else ''),'objectives')
    if 'by_players' in obj:
        # Totals for a game started with fewer players than cities: {'<players>': {population_total, treasury_total}}.
        # The values above are for the full roster. A count without an entry keeps the full-roster totals.
        table=obj['by_players']
        if not isinstance(table,dict) or not all(isinstance(k,str) and k.isdigit() and str(int(k))==k and 1<=int(k)<len(slot_ids) for k in table):raise ValueError('인원별 목표의 인원 수가 올바르지 않습니다. 1명부터 전체 도시 수보다 적은 인원까지 적을 수 있습니다.')
        for row in table.values():
            if not isinstance(row,dict) or not row or not set(row)<={'population_total','treasury_total'}:raise ValueError('인원별 목표 형식이 올바르지 않습니다.')
            integer(row.get('population_total',0),0,10000000,'인원별 전체 인구 목표');integer(row.get('treasury_total',0),0,1000000000,'인원별 전체 도시 자금 목표')
    if obj.get('celebration','notice') not in ('notice','video'):raise ValueError('목표 달성 연출 오류')
    integer(obj['population_total'],0,10000000,'전체 인구 목표')
    if not isinstance(obj['per_city'],dict) or not set(obj['per_city'])<=slot_ids:raise ValueError('목표 도시가 시나리오에 없습니다.')
    integer(obj.get('treasury_total',0),0,1000000000,'전체 도시 자금 목표')
    import delivery_goals
    delivery_goals.validate(obj.get('deliveries',[]),slot_ids)
    active=obj['population_total']>0 or obj.get('treasury_total',0)>0 or bool(obj.get('deliveries'))
    for slot,values in obj['per_city'].items():
        keys(values,'population culture prosperity peace favor treasury','city objectives')
        for name,limit in [('population',1000000),('culture',100),('prosperity',100),('peace',100),('favor',100),('treasury',1000000000)]:
            integer(values[name],0,limit,'목표 '+name);active|=values[name]>0
    if not active:raise ValueError('목표를 하나 이상 입력하세요. 0은 목표 없음입니다.')

def write_layout(data,directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    body=layout(data)
    setups={'event-town':1,'defense-town':2}
    (directory/'starting-setup.txt').write_text(''.join(s['id']+' '+str(setups[s['starting_setup']])+'\n' for s in data['slots'] if s.get('starting_setup')),encoding='ascii')
    for slot in data['slots']:
        if 'terrain_asset' not in slot:continue
        maps=directory/'maps';maps.mkdir(exist_ok=True)
        (maps/(slot['id']+'.mapx')).write_bytes(decode_terrain_asset(slot['terrain_asset']))
    (directory/'empire-layout.txt').write_text(body,encoding='ascii')
    return directory/'empire-layout.txt'

ROUTE_KEY=re.compile(r'([1-9][0-9]?)-([1-9][0-9]?)-(land|sea)')
def validate_route_paths(paths):
    """Drawn trade paths on the empire map (authoring/display only; the engine layout and trade never read them).
    key 'a-b-land|sea' (city name ids, a<b) -> points from a to b in map pixels, the endpoints they were made for and
    the passage data id. Paths of cities that no longer exist may stay: they are kept, never used."""
    if not isinstance(paths,dict) or len(paths)>800:raise ValueError('교역 경로 자료가 올바르지 않습니다.')
    for key,rec in paths.items():
        m=ROUTE_KEY.fullmatch(key) if isinstance(key,str) else None
        if not m or int(m.group(1))>=int(m.group(2)) or int(m.group(2))>39:raise ValueError('교역 경로 이름이 올바르지 않습니다.')
        if not isinstance(rec,dict):raise ValueError('교역 경로 자료가 올바르지 않습니다.')
        keys(rec,'points from to'+(' data' if 'data' in rec else ''),'route path')
        pts=rec['points']
        if not isinstance(pts,list) or not 2<=len(pts)<=600:raise ValueError('교역 경로 점 개수가 올바르지 않습니다.')
        for p in pts+[rec['from'],rec['to']]:
            if not isinstance(p,list) or len(p)!=2:raise ValueError('교역 경로 점이 올바르지 않습니다.')
            integer(p[0],0,2000,'route x');integer(p[1],0,1000,'route y')
        if pts[0]!=rec['from'] or pts[-1]!=rec['to']:raise ValueError('교역 경로의 양 끝이 도시 위치와 맞지 않습니다.')
        if 'data' in rec and rec['data'] is not None and (not isinstance(rec['data'],str) or not re.fullmatch(r'[0-9a-f]{16}',rec['data'])):raise ValueError('교역 경로 자료 표시가 올바르지 않습니다.')

START_MESSAGE_MAX=1500
def validate_start_message(data):
    """Text shown once to every player when the game starts (a confirm window): 'common' for all, then the player's
    own city text from 'per_city' (slot id -> text). Either part may be absent or empty; plain text only."""
    m=data['start_message']
    if data.get('schema',0)<4 or not isinstance(m,dict) or not set(m)<={'common','per_city'}:raise ValueError('게임 시작 메시지 형식이 올바르지 않습니다.')
    def plain(v):return isinstance(v,str) and len(v)<=START_MESSAGE_MAX and not any(ord(ch)<32 and ch not in '\r\n\t' for ch in v)
    if 'common' in m and not plain(m['common']):raise ValueError(f'게임 시작 메시지는 {START_MESSAGE_MAX}자 이내의 일반 텍스트로 입력하세요.')
    per=m.get('per_city',{})
    ids={s.get('id') for s in data['slots'] if isinstance(s,dict)} if isinstance(data.get('slots'),list) else set()
    if not isinstance(per,dict) or not set(per)<=ids:raise ValueError('게임 시작 메시지의 도시가 시나리오에 없습니다.')
    if not all(plain(v) for v in per.values()):raise ValueError(f'게임 시작 메시지는 {START_MESSAGE_MAX}자 이내의 일반 텍스트로 입력하세요.')

def city_label(slot):
    """The city's name for a message (creator-city-catalog.json), else its seat id."""
    try:names={r['name_id']:r['name'] for r in json.loads((HERE/'creator-city-catalog.json').read_text(encoding='utf-8-sig'))}
    except (OSError,ValueError):names={}
    return names.get(slot.get('name_id'),str(slot.get('id')))

def validate(data):
    """The project checked; a malformed file (wrong types where a number, list or table belongs) is refused with
    ValueError like any other mistake, never with a Python error (2026-11-15: shared ZIPs come from other people)."""
    try:return _validate(data)
    except (TypeError,AttributeError,KeyError,IndexError) as e:raise ValueError('시나리오 파일 형식이 올바르지 않습니다. 제작기에서 다시 저장해 보세요.') from e

def _validate(data):
    keys(data, 'schema id title revision rules slots empire'+(' briefing' if 'briefing' in data else '')+(' start_message' if 'start_message' in data else ''), 'project')
    if 'start_message' in data:validate_start_message(data)
    if 'briefing' in data and (not isinstance(data['briefing'],str) or len(data['briefing'])>4000 or any(ord(ch)<32 and ch not in '\r\n\t' for ch in data['briefing'])):
        raise ValueError('브리핑은 4000자 이내의 일반 텍스트로 입력하세요.')
    integer(data['schema'], 1, 5, 'schema')
    version = data['schema']
    if not isinstance(data['id'], str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,63}', data['id']):
        raise ValueError('id: use lowercase letters, digits and hyphens')
    if not isinstance(data['title'], str) or not 1 <= len(data['title']) <= 100:
        raise ValueError('title: 1..100 characters required')
    integer(data['revision'], 1, 1000000, 'revision')
    if version>=3:
        keys(data['rules'],'mode player_transport starting_funds'+(' start_year' if version>=4 and 'start_year' in data['rules'] else '')+(' maker_tools' if version>=4 and 'maker_tools' in data['rules'] else '')+(' player_trade' if version>=4 and 'player_trade' in data['rules'] else '')+(' throne' if version==5 else '')+(' objectives' if version>=4 and data['rules'].get('mode')=='cooperative' else '')+(' progress' if version==4 and data['rules'].get('mode')=='imperial-progress' else '')+(' race' if version==4 and data['rules'].get('mode')=='deadline-race' else '')+(' min_players' if version>=4 and 'min_players' in data['rules'] else ''),'rules')
        integer(data['rules']['starting_funds'],0,1000000,'starting funds')
        # start_year (user 2026-11-17): the first year of every city, BC negative; absent = -350. There is no year 0.
        if 'start_year' in data['rules']:
            integer(data['rules']['start_year'],START_YEAR_MIN,START_YEAR_MAX,'start year')
            if data['rules']['start_year']==0:raise ValueError('시작 연도에 0년은 없습니다.')
        # maker_tools (user 2026-11-17): the test keys a 시나리오 제작자 방 of this scenario offers; absent = every key of its mode
        if 'maker_tools' in data['rules']:
            tools=data['rules']['maker_tools']
            if not isinstance(tools,list) or any(t not in MAKER_TOOLS for t in tools) or len(set(tools))!=len(tools):raise ValueError('제작자 모드 시험 단추 목록이 잘못되었습니다.')
            wrong=[t for t in tools if t not in maker_tools_of_mode(data)]
            if wrong:raise ValueError('이 시나리오의 방식에는 없는 시험 단추입니다: '+', '.join(MAKER_TOOL_NAMES[t] for t in wrong))
        if data['rules']['mode'] not in (('race-for-throne',) if version==5 else ('free-build','cooperative','imperial-progress','deadline-race') if version>=4 else ('free-build',)) or data['rules']['player_transport'] not in ('land','sea'):
            raise ValueError('시나리오 형식에 맞는 게임 모드와 육상/해상 교역을 지정하세요. 황위 데이터는 v5 전용입니다.')
    elif data['rules'] not in ({'mode': 'free-build', 'player_transport': 'land'}, {'mode': 'free-build', 'player_transport': 'sea'}):
        raise ValueError('unsupported rules; only free-build and land/sea player transport supported')
    slots = data['slots']
    if not isinstance(slots, list) or not (2 if version==1 else 1) <= len(slots) <= (8 if version>=3 else 4):
        raise ValueError('제작은 최대 8개 도시, 온라인 실행은 최대 6명을 지원합니다. 이전 형식의 도시 수 제한도 확인하세요.')
    ids, names = set(), set()
    def slot_fields(slot):
        # One city map with its play settings. Also used for a map kept on a neutral city (empire city 'map').
            keys(slot, 'id name_id campaign_scenario' + (' allowed_buildings' if version>=2 else '') + (' terrain_edits' if version>=2 and 'terrain_edits' in slot else '') + (' terrain_asset' if version>=4 and 'terrain_asset' in slot else '') + (' starting_setup' if version>=4 and 'starting_setup' in slot else '') + (' governance' if version>=4 and 'governance' in slot else '') + (' events' if version>=4 and 'events' in slot else '') + (' invasions' if version>=4 and 'invasions' in slot else '') + (' invasion_enemy' if version>=4 and 'invasion_enemy' in slot else '') + (' starting_funds' if version>=4 and 'starting_funds' in slot else '') + (' role_hint' if version>=4 and 'role_hint' in slot else ''), 'slot')
            # starting_funds: this slot's own amount (0 allowed). Absent = rules.starting_funds. Same range as the common value.
            if 'starting_funds' in slot:integer(slot['starting_funds'],0,1000000,'slot starting funds')
            # role_hint: the author's suggestion for this city (shown in the lobby as a suggestion, never enforced).
            if 'role_hint' in slot and (not isinstance(slot['role_hint'],str) or not 1<=len(slot['role_hint'])<=300 or any(ord(ch)<32 for ch in slot['role_hint'])):raise ValueError('도시 추천 역할은 300자 이내의 한 줄로 입력하세요.')
            integer(slot['name_id'], 1, 39 if version>=2 else 255, 'name_id')
            integer(slot['campaign_scenario'], 0, 111 if version>=3 else 99, 'campaign_scenario')
            if version>=3 and slot['campaign_scenario'] not in (*range(20),*range(100,112)):
                raise ValueError('지원하는 미션/자유 건설 프리셋 번호가 아닙니다.')
            if version>=2:
                allowed=slot['allowed_buildings']
                if not isinstance(allowed,list) or len(allowed)>512:raise ValueError('allowed_buildings: unique list required')
                for value in allowed:integer(value,1,511,'building id')
                if len(set(allowed))!=len(allowed):raise ValueError('allowed_buildings: unique list required')
                catalog=HERE/'building-catalog.json'
                if catalog.exists() and not set(allowed)<={r['id'] for r in json.loads(catalog.read_text(encoding='utf-8-sig'))}:raise ValueError('unsupported building id')
            if version>=2:
                edits=slot.get('terrain_edits',[])
                if not isinstance(edits,list) or len(edits)>25600:raise ValueError('terrain_edits: at most 25600 tiles')
                positions=set()
                for edit in edits:
                    keys(edit,'x y kind','terrain edit')
                    integer(edit['x'],0,159,'terrain x');integer(edit['y'],0,159,'terrain y')
                    if edit['kind'] not in ('land','water','rock'):raise ValueError('unsupported terrain brush')
                    xy=(edit['x'],edit['y'])
                    if xy in positions:raise ValueError('duplicate terrain tile')
                    positions.add(xy)
            if slot.get('starting_setup') not in (None,'event-town','defense-town'):raise ValueError('지원하지 않는 시작 도시 구성입니다.')
            if 'governance' in slot:
                g=slot['governance'];keys(g,'rank salary_rank savings favor policy','governance')
                integer(g['rank'],0,10,'통치자 직급');integer(g['salary_rank'],-1,10,'봉급 직급')
                integer(g['savings'],0,1000000,'개인 재산');integer(g['favor'],0,100,'황제 지지도')
                if g['policy'] not in ('fixed','original'):raise ValueError('황제 지지도 운영 방식 오류')
            if 'invasion_enemy' in slot:   # the enemy people of this city's invasions (2026-11-14); absent = the map's own
                integer(slot['invasion_enemy'],0,19,'침략 적군 종류')
            if 'invasions' in slot:
                import city_invasions
                try:city_invasions.validate(slot)
                except ValueError as e:raise ValueError(f'{city_label(slot)}: {e}') from e   # which city (copied to all, 2026-11-15)
            if 'events' in slot:
                import city_events
                try:city_events.validate(slot)
                except ValueError as e:raise ValueError(f'{city_label(slot)}: {e}') from e
            if 'terrain_asset' in slot:decode_terrain_asset(slot['terrain_asset'])
    for slot in slots:
        if not isinstance(slot, dict) or 'id' not in slot: raise ValueError('slot: invalid or unsupported fields')
        if not isinstance(slot['id'], str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,31}', slot['id']) or slot['id'] in ids:
            raise ValueError('duplicate or invalid slot id')
        slot_fields(slot)
        if slot['name_id'] in names: raise ValueError('duplicate player city')
        ids.add(slot['id']); names.add(slot['name_id'])
    if version>=4 and data['rules']['mode']=='cooperative':validate_objectives(data['rules']['objectives'],ids)
    if version>=4 and data['rules']['mode']=='imperial-progress':
        import imperial_progress
        imperial_progress.validate_spec(data['rules']['progress'])
    if version>=4 and data['rules']['mode']=='deadline-race':validate_race(data['rules']['race'])
    if version>=4 and 'min_players' in data['rules']:integer(data['rules']['min_players'],1,min(len(slots),MAX_ONLINE_PLAYERS),'최소 인원')
    if min_players(data)>len(slots):raise ValueError(f'이 게임 방식은 {min_players(data)}명 이상이 필요합니다. 플레이 도시를 {min_players(data)}곳 이상 두세요.')   # 2026-11-15: else no room could start
    if 'player_trade' in data['rules']:
        import trade_policy
        trade_policy.validate(data['rules']['player_trade'],ids)
    empire = data['empire']
    keys(empire, 'template cities'+(' rome' if version==5 else '')+(' route_paths' if version>=4 and 'route_paths' in empire else ''), 'empire')
    if 'route_paths' in empire:validate_route_paths(empire['route_paths'])
    if version==5:
        import throne_state
        throne_state.validate_spec(dict(rules=data['rules']['throne'],rome=empire['rome']),[s['id'] for s in slots])
        if any((c.get('x'),c.get('y'))==(empire['rome']['x'],empire['rome']['y']) for c in empire['cities']):raise ValueError('로마를 다른 도시와 같은 좌표에 배치할 수 없습니다.')
    integer(empire['template'], 0, 1098 if version>=3 else 100, 'template')
    cities = empire['cities']
    maximum=39 if version>=3 else 32
    if not isinstance(cities, list) or not len(slots) <= len(cities) <= maximum:
        raise ValueError(f'empire: {len(slots)}..{maximum} cities required')
    seen, players = set(), set()
    for city in cities:
        keys(city, 'name_id role sea cost sells buys' + (' x y' if version>=2 else '') + (' enabled' if version>=3 else '') + (' trade_players' if 'trade_players' in city else '') + (' reserved' if 'reserved' in city else '') + (' map' if 'map' in city else '') + (' sea_auto' if 'sea_auto' in city else '') + (' parked_trade' if 'parked_trade' in city else ''), 'empire city')
        # Authoring-only fields (schema 4+). They keep what a role change would otherwise lose; the engine layout ignores them.
        #   map          neutral city: the city map that belongs to it (campaign_scenario, optional terrain_edits/terrain_asset).
        #                Makes the city selectable for play. Slot settings (allowed buildings, governance, ...) belong to the slot,
        #                not here; files from the first draft of this field may still carry them and stay valid.
        #   parked_trade player city: the neutral trade setup it had (sea, cost, sells, buys, optional trade_players/sea_auto).
        #   sea_auto     neutral city: 'sea' follows the automatic coast estimate. Absent = the stored value was set by hand.
        if ('map' in city or 'sea_auto' in city or 'parked_trade' in city) and version<4:raise ValueError('도시 지형 보관·자동 해상 설정은 형식 4 이상에서만 쓸 수 있습니다.')
        if 'map' in city:
            if city['role']!='npc' or not isinstance(city['map'],dict) or 'id' in city['map'] or 'name_id' in city['map']:raise ValueError('중립 도시의 지형 보관 정보가 올바르지 않습니다.')
            slot_fields(dict(dict(allowed_buildings=[]),**city['map'],id='parked',name_id=city['name_id']))
        if 'sea_auto' in city and (city['sea_auto'] is not True or city['role']!='npc'):raise ValueError('자동 해상 설정은 중립 도시에만, 켜짐으로만 기록합니다.')
        if 'parked_trade' in city:
            t=city['parked_trade']
            if city['role']!='player':raise ValueError('보관한 교역 설정은 플레이 도시에만 둡니다.')
            keys(t,'sea cost sells buys'+(' trade_players' if isinstance(t,dict) and 'trade_players' in t else '')+(' sea_auto' if isinstance(t,dict) and 'sea_auto' in t else ''),'parked trade')
            integer(t['sea'],0,1,'sea');integer(t['cost'],0,1000000,'cost')
            if 'sea_auto' in t and t['sea_auto'] is not True:raise ValueError('자동 해상 설정은 켜짐으로만 기록합니다.')
            if 'trade_players' in t and (not isinstance(t['trade_players'],list) or any(not isinstance(v,str) for v in t['trade_players'])):raise ValueError('교역 허용 플레이어 오류')
            for field in ('sells','buys'):
                if not isinstance(t[field],dict):raise ValueError('resource map required')
                for resource,amount in t[field].items():
                    if resource not in [str(i) for i in range(1,22)]:raise ValueError('unsupported resource')
                    integer(amount,1,10000,'annual trade limit')
            if set(t['sells'])&set(t['buys']):raise ValueError('NPC cannot buy and sell the same resource in this engine')
        if 'reserved' in city and (version<4 or city['reserved'] is not True or city['role']!='npc' or city['cost'] or city['sells'] or city['buys'] or city.get('trade_players')!=[]):raise ValueError('invalid reserved player city')
        if 'trade_players' in city and (not isinstance(city['trade_players'],list) or len(city['trade_players'])!=len(set(city['trade_players'])) or not set(city['trade_players'])<=ids):raise ValueError('교역 허용 플레이어 오류')
        integer(city['name_id'], 1, 39 if version>=2 else 255, 'city name_id')
        if version>=3 and type(city['enabled']) is not bool:raise ValueError('도시 사용 여부는 참/거짓이어야 합니다.')
        if version>=2:
            integer(city['x'],16,1984,'city x');integer(city['y'],16,984,'city y')
        if city['name_id'] in seen: raise ValueError('duplicate empire city')
        seen.add(city['name_id'])
        if city['role'] not in ('player', 'npc'): raise ValueError('invalid city role')
        integer(city['sea'], 0, 1, 'sea'); integer(city['cost'], 0, 1000000, 'cost')
        for field in ('sells', 'buys'):
            resources = city[field]
            if not isinstance(resources, dict): raise ValueError('resource map required')
            for resource, amount in resources.items():
                if resource not in [str(i) for i in range(1, 22)]: raise ValueError('unsupported resource')
                integer(amount, 1, 10000, 'annual trade limit')
        if set(city['sells']) & set(city['buys']):
            raise ValueError('NPC cannot buy and sell the same resource in this engine')
        if city['role'] == 'player':
            if version>=3 and not city['enabled']:raise ValueError('플레이어 도시는 사용 상태여야 합니다.')
            players.add(city['name_id'])
            if city['sea'] or city['cost'] or city['sells'] or city['buys']:
                raise ValueError('player trade uses live contracts, not NPC policy')
    if version>=4 and data['rules']['mode']=='cooperative':
        goals=data['rules']['objectives']['per_city']
        for slot in slots:
            g=slot.get('governance')
            if g and g['policy']=='fixed' and goals.get(slot['id'],{}).get('favor',0)>g['favor']:
                raise ValueError(slot['id']+': 황제 지지도 목표가 고정값보다 높습니다. 목표나 지지도 운영 방식을 바꾸세요.')
    if players != names: raise ValueError('every slot must have exactly one matching player empire city')
    # Players always trade with each other overland (user decision 2026-11-13). Older files may still say 'sea': a lake
    # city without a dock site could then trade with nobody. The value is read as 'land' everywhere from here on.
    data['rules']['player_transport']='land'
    return data

def load(path=DEFAULT):
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj: raise ValueError('duplicate JSON key: ' + key)
            obj[key] = value
        return obj
    raw = Path(path).read_bytes()
    if len(raw) > 16777216: raise ValueError('project too large')
    return validate(json.loads(raw.decode('utf-8-sig'), object_pairs_hook=unique))

def canonical(data):
    raw=json.dumps(validate(data), ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    if len(raw)>16777216:raise ValueError('project too large')
    return raw

def min_players(data):
    """The fewest players this scenario starts with (user 2026-11-15). Absent = 1; 황제의 순행 and 기한 경쟁 need two."""
    rules=data['rules'] if isinstance(data.get('rules'),dict) else {}
    return max(rules.get('min_players',1),2 if rules.get('mode') in ('imperial-progress','deadline-race') else 1)

def players_label(data):
    """'6', or '2~6' when the scenario needs more than one player (scenario list: "2~6인", user 2026-11-15)."""
    seats=min(len(data['slots']),MAX_ONLINE_PLAYERS);low=min(min_players(data),seats)   # 8 seats: at most 6 play (2026-11-15)
    return f'{low}~{seats}' if 1<low<seats else str(seats)

def digest(data): return hashlib.sha256(canonical(data)).hexdigest()

def throne_test(data):
    """A v5 project that selects 황위 시험 규칙 v1 (throne_rules.py): the only throne rule set that runs in a game."""
    import throne_rules
    return data.get('schema')==5 and throne_rules.is_test(data['rules'].get('throne'))

def require_runtime(data):
    validate(data)
    if data['schema']==5 and not throne_test(data):raise ValueError('황위 쟁탈전은 상태·저장 단계입니다. 실제 게임 실행은 아직 지원하지 않습니다(황위 시험 규칙 v1을 고른 시나리오만 실행).')
    if data['schema']>=3:
        require_layout(data)
        # Up to 8 seats, of which at most MAX_ONLINE_PLAYERS play (user 2026-11-15: more cities to choose from). The
        # seats nobody takes become neutral when the room starts (room_roster.effective_project); more players than
        # MAX_ONLINE_PLAYERS are refused there and by lobby.py.
        return
    if data['schema']==2:
        if not 1<=len(data['slots'])<=4:raise ValueError('이전 형식의 실행 지원은 1~4인입니다.')
        if data['empire']['template']!=25:raise ValueError('현재 제국 배경은 25번을 지원합니다.')
        if any(s['campaign_scenario'] not in range(2,6) for s in data['slots']):raise ValueError('현재 지형 템플릿은 캠페인 2~5번을 지원합니다.')
        return
    expected = [('capua', 2, 2), ('tarentum', 1, 3)]
    if sorted((s['id'], s['name_id'], s['campaign_scenario']) for s in data['slots']) != expected:
        raise ValueError('현재 엔진은 카푸아·타렌툼 2인만 실행할 수 있습니다. 4/8인 슬롯은 제작 형식만 지원합니다.')
    # Existing empire templates provide coordinates/artwork. Arbitrary maps are a later importer stage.
    if data['empire']['template'] != 25 or {c['name_id'] for c in data['empire']['cities']} != {2,1,3,10,4,6,13}:
        raise ValueError('현재 엔진은 예제 제국 지도 25번의 7개 도시를 지원합니다.')

START_YEAR_MIN=-500;START_YEAR_MAX=300;START_YEAR_DEFAULT=-350
# 시나리오 제작자 방의 시험 단추 (user 2026-11-17: the author picks them; dev_tools.py, multiplayer_dev.inc). The first four
# work in every mode; 황위 쟁탈전 and 황제의 순행 keys only in their own mode.
MAKER_TOOLS=('money','invade','favor','goods','throne','progress')   # goods: 물자를 창고에 (user 2026-11-17)
MAKER_TOOL_NAMES=dict(money='자금 +10,000',invade='침략군 부르기',favor='호의 +10',goods='물자 넣기',throne='황위 쟁탈전 시험',progress='황제의 순행 다음 단계')
def maker_tools_of_mode(data):
    """The keys this scenario's mode can have."""
    mode=(data.get('rules') or {}).get('mode') if isinstance(data,dict) else None
    return [t for t in MAKER_TOOLS if t not in ('throne','progress') or (t=='throne' and data.get('schema')==5) or (t=='progress' and mode=='imperial-progress')]
def maker_tools(data):
    """The keys a maker room of this scenario offers: the author's choice, else every key of its mode."""
    allowed=maker_tools_of_mode(data)
    chosen=(data.get('rules') or {}).get('maker_tools') if isinstance(data,dict) else None
    return [t for t in allowed if t in chosen] if isinstance(chosen,list) else allowed
def start_year(data):
    """The first year of the scenario's cities (rules.start_year, else -350)."""
    try:
        year=data['rules'].get('start_year',START_YEAR_DEFAULT)
        return year if type(year)==int and START_YEAR_MIN<=year<=START_YEAR_MAX and year else START_YEAR_DEFAULT
    except (AttributeError,KeyError,TypeError):return START_YEAR_DEFAULT

def require_layout(data):
    """Author/native preview supports eight slots; online admission is separate."""
    validate(data)
    if data['schema']<3:return require_runtime(data)
    catalog=HERE/'preset-catalog.json'
    if not catalog.is_file():raise ValueError('preset-catalog.json 프리셋 목록을 찾지 못했습니다.')
    presets=json.loads(catalog.read_text(encoding='utf-8-sig'))
    if data['empire']['template'] not in {x['id'] for x in presets['empire']}:raise ValueError('지원하는 제국지도 프리셋이 아닙니다.')
    if not {s['campaign_scenario'] for s in data['slots']}<={x['id'] for x in presets['terrain']}:raise ValueError('지원하는 도시 지형 프리셋이 아닙니다.')

def layout(data):
    require_layout(data)
    if data['schema']==5 and not throne_test(data):raise ValueError('황위 로마의 엔진 지도 배치는 후속 단계입니다. 프로젝트 저장은 가능합니다.')
    # Test rules: Rome has no city map and is not an engine city (drawn from the ROME line); the engine lays the
    # project out exactly like format 4.
    version=4 if data['schema']==5 else data['schema']
    cities=[c for c in data['empire']['cities'] if c.get('enabled',True)]
    rows = [f"{version} {data['empire']['template']} {len(cities)}"]
    for c in cities:
        values = [c['name_id'], 2 if c.get('reserved') else int(c['role']=='player'), int(data['rules']['player_transport']=='sea') if c['role']=='player' else c['sea'], c['cost']]
        if version>=2:values += [c['x'],c['y']]
        values += [c['sells'].get(str(i),0) for i in range(1,22)]
        values += [c['buys'].get(str(i),0) for i in range(1,22)]
        rows.append(' '.join(map(str, values)))
    if version>=2:
        rows.append(str(len(data['slots'])))
        for slot in data['slots']:
            allowed=slot['allowed_buildings']
            rows.append(' '.join(map(str,[slot['id'],slot['name_id'],slot['campaign_scenario'],len(allowed),*allowed])))
        if version>=3:rows.append('START '+str(data['rules']['starting_funds']))
        rows.append('TERRAIN '+str(len(data['slots'])))
        for slot in data['slots']:
            edits=slot.get('terrain_edits',[])
            rows.append(slot['id']+' '+str(len(edits)))
            rows.extend(f"{e['x']} {e['y']} {('land','water','rock').index(e['kind'])}" for e in edits)
    if version>=4:
        assets=[s for s in data['slots'] if 'terrain_asset' in s]
        rows.append('MAPS '+str(len(assets)))
        rows.extend(s['id'] for s in assets)
    if version>=4:
        rows.append('ACCESS '+str(len(cities)))
        for c in cities:
            allowed=c.get('trade_players',[s['id'] for s in data['slots']])
            mask=sum(1<<i for i,s in enumerate(data['slots']) if s['id'] in allowed)
            rows.append(str(c['name_id'])+' '+str(mask))
    configured=[s for s in data['slots'] if 'governance' in s]
    if configured:
        rows.append('GOVERNANCE '+str(len(configured)))
        for s in configured:
            g=s['governance'];rows.append(f"{s['id']} {g['rank']} {g['salary_rank']} {g['savings']} {g['favor']} {int(g['policy']=='fixed')}")
    if version>=4:
        import city_events
        city_events.append_layout(data,rows)
        import city_invasions
        city_invasions.append_layout(data,rows)
        if 'start_year' in data['rules']:   # first tail section; a layout without it starts in -350 as before
            for tag in ('GOVERNANCE','EVENTS','INVASIONS'):
                if not any(x.startswith(tag+' ') for x in rows):rows.append(tag+' 0')
            rows.append('YEAR '+str(data['rules']['start_year']))
        own=[s for s in data['slots'] if 'starting_funds' in s]
        if own:   # per-slot starting funds; slots not listed use START. Earlier sections are positional, so fill them.
            for tag in ('GOVERNANCE','EVENTS','INVASIONS'):
                if not any(x.startswith(tag+' ') for x in rows):rows.append(tag+' 0')
            rows.append('FUNDS '+str(len(own)))
            rows.extend(s['id']+' '+str(s['starting_funds']) for s in own)
        enemy=[s for s in data['slots'] if 'invasion_enemy' in s]
        if enemy:   # after FUNDS (optional, then left out); the earlier positional sections are filled
            for tag in ('GOVERNANCE','EVENTS','INVASIONS'):
                if not any(x.startswith(tag+' ') for x in rows):rows.append(tag+' 0')
            rows.append('ENEMIES '+str(len(enemy)))
            rows.extend(s['id']+' '+str(s['invasion_enemy']) for s in enemy)
        raid=city_invasions.raiders(data)
        if raid:   # attacks with their own people (2026-11-15): last tail section
            for tag in ('GOVERNANCE','EVENTS','INVASIONS'):
                if not any(x.startswith(tag+' ') for x in rows):rows.append(tag+' 0')
            rows.append('RAIDERS '+str(len(raid)));rows.extend(raid)
        notes=city_events.texts(data)
        if notes:  # the messages of city events (2026-11-15): after RAIDERS, the last tail section
            for tag in ('GOVERNANCE','EVENTS','INVASIONS'):
                if not any(x.startswith(tag+' ') for x in rows):rows.append(tag+' 0')
            rows.append('EVENTTEXT '+str(len(notes)));rows.extend(notes)
        waits=city_events.conditions(data)
        if waits:  # events that wait for the city to reach a value (2026-11-15): after EVENTTEXT, the last tail section
            for tag in ('GOVERNANCE','EVENTS','INVASIONS'):
                if not any(x.startswith(tag+' ') for x in rows):rows.append(tag+' 0')
            rows.append('EVENTCOND '+str(len(waits)));rows.extend(waits)
            again=city_events.repeats(data)
            if again:rows.append('EVENTREPEAT '+str(len(again)));rows.extend(again)   # waiting events that repeat (2026-11-15)
        twice=city_invasions.repeats(data)
        if twice:rows.append('INVREPEAT '+str(len(twice)));rows.extend(twice)   # attacks that come again (2026-11-15): last tail section
    return '\n'.join(rows)+'\n'

def export(data, target):
    """Exclusive creation: never overwrite someone else's package. No input paths are copied."""
    body = canonical(data)
    with zipfile.ZipFile(target, 'x', zipfile.ZIP_DEFLATED) as z:
        z.writestr('scenario.json', body)
        z.writestr('checksums.json', json.dumps({'scenario.json': hashlib.sha256(body).hexdigest()}))
        z.writestr('README.txt', 'Creator format v1/v2/v3/v4. Requires Augustus Korean multiplayer and legally installed Caesar III.\n'
                   f'Authoring: up to 8 cities. Online schema3/4: up to {MAX_ONLINE_PLAYERS} players; schema2: up to 4; schema1: legacy two cities.\n'
                   'No original game graphics included. Authored map data may be embedded. This package does not claim map/engine validation.\n')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', type=Path)
    parser.add_argument('--export', type=Path)
    parser.add_argument('--runtime', action='store_true')
    args = parser.parse_args()
    try:
        data = load(args.project)
        if args.runtime: require_runtime(data)
        if args.export:
            # A scenario with a blocking finding is not packaged. Warnings and unverified items do not stop it.
            import scenario_check
            scenario_check.gate(data)
            export(data, args.export)
        print('VALID', digest(data))
        print('Format slots:', len(data['slots']), f'| Authoring up to 8; online schema3/4 up to {MAX_ONLINE_PLAYERS}; schema2 up to 4; schema1 legacy two-city')
    except (ValueError, OSError, zipfile.BadZipFile) as error:
        parser.exit(1, str(error)+'\n')
