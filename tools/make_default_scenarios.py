"""Builds the default ("기본 제공") scenario set (user decision 2026-11-13: the two Provincial scenarios become defaults,
the earlier defaults leave the list, and examples that show what the scenario editor can do are added).

  provincial-quartet, provincial-sextet   copied from scenario-drafts (tools/make_provincial_examples.py)
  freebuild-2p / -4p / -6p                the free-build drafts, without fishing buildings where the map has no fish
  feature-trade-goals                     editor feature example: delivery goals, per-seat funds and hints, trade rules,
                                          governance, city events, an invasion
  ../default-scenarios.json               the list and order the lobby shows; other folders under scenarios/ stay on disk
                                          for tests and tools and are opened only through AUGUSTUS_MP_PROJECT
The two older practice examples (city-events-example, city-invasions-example) are not listed: their prepared start town
did not pass the engine check in the Linux rig (2026-11-13), and feature-trade-goals shows events and an invasion.
Run from the package root:  python tools/make_default_scenarios.py"""
import json,copy,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];A=ROOT/'Augustus'
SHIPYARD,WHARF=74,76
NO_FISH={1,2,4,10,7}          # name_ids whose free-build map has no fishing grounds (engine check, 2026-11-13): 타렌툼 카푸아 메디올라눔 시라쿠세 타라코(80x80)
# Release list (user decision 2026-11-13, broadcast build): only the two Provincial scenarios ship. The free-build and
# feature examples are still made here (main --examples) for testing, but are no longer listed or shipped.
# 2026-11-14 (user): the defaults are the tutorials, one per victory condition, each for 6 players:
# free build, joint victory (the Provincial Sextet) and the struggle for the throne. The quartet stays on disk only.
# Later the same day (user): every default is a tutorial that ends in one to two hours of play. The Provincial
# scenarios are long games, so they stay on disk as examples and a short joint-victory tutorial takes that place.
DEFAULTS=['freebuild-6p','coop-6p','throne-6p','progress-6p']
TUTORIAL='이 시나리오는 튜토리얼입니다. 더 길고 어려운 판은 시나리오 제작기로 직접 만들 수 있습니다.'
COOP_POPULATION=1500

def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def write(folder,data):
    target=A/'scenarios'/folder;target.mkdir(parents=True,exist_ok=True)
    (target/'scenario.json').write_text(json.dumps(data,ensure_ascii=False,indent=1,sort_keys=True)+'\n',encoding='utf8')

def free_build(n):
    d=read(A/f'scenario-drafts/free-build-{n}/scenario.json')
    d['id']=f'freebuild-{n}p';d['title']=f'자유 건설 · {n}인';d['revision']=1
    for s in d['slots']:
        if s['name_id'] in NO_FISH:s['allowed_buildings']=[b for b in s['allowed_buildings'] if b not in (SHIPYARD,WHARF)]
    d['briefing']=(f'정해진 승리 조건 없이 {n}명이 각자 도시를 키웁니다. 도시끼리 물품과 돈을 주고받을 수 있습니다.\n'
                   '어장이 없는 도시에서는 선창과 조선소를 뺐습니다. 그 밖의 건물은 모두 지을 수 있습니다.')
    return d

def coop(n=6):
    """Joint-victory tutorial: a small population goal for every city, reachable in an hour or two."""
    d=free_build(n);d['id']=f'coop-{n}p';d['title']=f'공동 승리 · {n}인';ids=[s['id'] for s in d['slots']]
    d['rules'].update(mode='cooperative',objectives=dict(celebration='notice',population_total=COOP_POPULATION*n,treasury_total=0,deliveries=[],
        per_city={i:dict(population=COOP_POPULATION,culture=0,prosperity=0,peace=0,favor=0,treasury=0) for i in ids},
        by_players={str(k):dict(population_total=COOP_POPULATION*k) for k in range(1,n)}))
    d['briefing']=(f'모든 도시가 인구 {COOP_POPULATION:,}명을 달성하고, 전체 인구가 참가한 도시 수 x {COOP_POPULATION:,}명 이상이면 함께 승리합니다.\n'
                   '도시끼리 물품과 돈을 주고받을 수 있습니다. 뒤처진 도시를 도와야 함께 이길 수 있습니다.\n'
                   '어장이 없는 도시에서는 선창과 조선소를 뺐습니다. 그 밖의 건물은 모두 지을 수 있습니다.\n'+TUTORIAL)
    return with_start(d,f'공동 승리 시나리오입니다. 모든 도시가 인구 {COOP_POPULATION:,}명을 달성하고, 전체 인구가 참가한 도시 수 x {COOP_POPULATION:,}명 이상이면 함께 승리합니다.\n'
        '뒤처진 도시가 있으면 물품이나 돈을 보내 도와주세요.')

def tutorial_throne_rules():
    """Throne numbers for a game of one to two hours (user 2026-11-14). The confirmed presets are long games: with the
    standard one a win costs about 1,000,000 Dn at the median (20,000 simulated games, minimum payments).
    Here: five stages of 1,000 to 3,500 Dn (10,500 Dn in all, just above the 10,000 Dn a city starts with, so nobody
    wins on the starting money alone), better odds, a 5% rise after a failure and eight months between attempts.
    Whole games played by the real host code (handoff/sim_throne_tutorial.py, six cities, 300 games each, every game
    ended): with an ASSUMED income of 250 Dn a month the end comes after 41 months at the median (31 minutes at game
    speed 80%), with 100 Dn a month after 88 months (67 minutes; nine in ten within 104 minutes). City income was not
    measured, so these are a tutorial's numbers, not a balance. Those runs used a 10% rise; with two cities and
    100 Dn a month one game in 200 did not end within 50 years, so the rise was lowered to 5% (not simulated again). Paranoia rises slowly (six players fail often), the
    emperor's legions are small and the tribute is cheap."""
    sys.path.insert(0,str(A));import throne_rules
    r=throne_rules.preset('standard')
    for stage,(cost,chance,cap) in zip(r['stages'],[(1000,70,90),(1500,65,85),(2000,60,80),(2500,55,75),(3500,50,70)]):stage.update(cost=cost,chance=chance,cap=cap)
    r.update(failure_percent=5,attempt_months=8,monthly_paranoia=1,failure_paranoia=2,gift_price=50,gift_price_below=150)
    r['expedition'].update(tributes=[300,500,800,1200,1600],army_initial=16,army_increment=8,army_cap=48)
    return throne_rules.validate(r)

def with_start(d,text):
    d['schema']=max(d.get('schema',0),4);d['start_message']=dict(common=text)
    # every default starts its players as governor (rank 9, 총독), like the Provincial scenarios: the salary a player
    # pays himself then never lowers the emperor's favor
    for slot in d['slots']:slot.setdefault('governance',dict(favor=50,policy='original',rank=9,salary_rank=-1,savings=0))
    return d

def sextet():
    """The user's own design, plus what a tutorial needs: totals for a game started with fewer than six players
    (players x 25,000, the same rule as the full roster) and a start message."""
    d=read(A/'scenario-drafts/provincial-sextet/scenario.json');n=len(d['slots'])
    d['rules']['objectives']['by_players']={str(k):dict(population_total=25000*k) for k in range(1,n)}
    return with_start(d,'공동 승리 시나리오입니다. 모든 도시가 인구 25,000명과 번영 100을 달성하고, 전체 인구가 참가한 도시 수 x 25,000명 이상이면 함께 승리합니다.\n'
        '도시마다 만들 수 없는 물품이 있습니다. 다른 총독과 물품을 주고받아야 목표에 닿을 수 있습니다.')

def throne(n=6):
    """The free-build map for n players with the tutorial throne numbers, as the editor saves it."""
    d=free_build(n);d['id']=f'throne-{n}p';d['title']='Et tu, Brute?';d['schema']=5   # title: user 2026-11-15
    d['rules'].update(mode='race-for-throne',throne=tutorial_throne_rules());d['rules'].pop('objectives',None)
    rome=read(A/'rome-capital.json');d['empire']['rome']=dict(id='rome',x=rome['x'],y=rome['y'])
    d['briefing']=(f'{n}명의 총독이 황제 자리를 두고 겨룹니다. 5단계 쿠데타를 먼저 끝낸 총독이 황제가 되고 그 순간 게임이 끝납니다.\n'
                   '쿠데타는 익명입니다. 실패하면 모든 총독이 의심받고, 의심이 쌓이면 황제가 징벌 원정군을 보냅니다.\n'
                   '어장이 없는 도시에서는 선창과 조선소를 뺐습니다. 그 밖의 건물은 모두 지을 수 있습니다.\n'
                   '한두 시간에 끝나도록 쿠데타 지원금을 낮춘 튜토리얼입니다. 긴 판은 시나리오 제작기의 황위 쟁탈전 설정에서 프리셋을 골라 만드세요.')
    return with_start(d,'황위 쟁탈전입니다. 5단계 쿠데타를 먼저 끝낸 총독이 황제가 되고 그 순간 게임이 끝납니다.\n'
        '도시 화면 오른쪽 위의 상자를 누르면 쿠데타를 지원할 수 있습니다. 쿠데타는 익명이지만, 실패하면 모든 총독의 편집증이 오릅니다.\n'
        '편집증이 100이 되면 황제가 징벌 원정군을 보냅니다. 충성선물로 편집증을 낮추거나, 공물을 바치거나, 군대로 막으세요.')

def progress(n=6):
    """황제의 순행 (user 2026-11-15) on the free-build map: the editor's own numbers, with a smaller demand (8 to 16 loads,
    at most half a warehouse) so a first game can serve the emperor. Not a balance: nothing here was measured in play."""
    sys.path.insert(0,str(A));import imperial_progress
    d=free_build(n);d['id']=f'progress-{n}p';d['title']=f'황제의 순행 · {n}인'
    d['rules'].update(mode='imperial-progress',progress=dict(imperial_progress.defaults(),amount_min=8,amount_max=16),min_players=2);d['rules'].pop('objectives',None)
    d['briefing']=(f'{n}명의 총독이 황제의 총애를 두고 겨룹니다. 황제가 순행에 나설 때마다 모시고 싶은 총독이 비공개로 입찰하고, 가장 높은 금액을 쓴 총독의 도시로 황제가 갑니다.\n'
                   '황제는 예고한 세 가지 물품 가운데 한 가지만 찾습니다. 넉넉히 드리면 총애가 오르고, 모자라면 총애가 떨어지고 돈으로 메워야 합니다.\n'
                   '모든 순행이 끝났을 때 총애가 가장 높은 총독이 황제의 오른팔이 됩니다. 2명 이상이 있어야 시작할 수 있습니다.\n'
                   '어장이 없는 도시에서는 선창과 조선소를 뺐습니다. 그 밖의 건물은 모두 지을 수 있습니다.\n'+TUTORIAL)
    return with_start(d,'황제의 순행입니다. 2년 뒤부터 황제가 속주를 돌기 시작합니다.\n'
        '순행이 공고되면 도시 화면 오른쪽 위의 상자에서 입찰할 수 있습니다. 입찰은 한 번뿐이고 다른 총독은 볼 수 없습니다.\n'
        '황제를 모시게 되면 후보 물품 세 가지를 창고에 준비해 두세요. 황제는 그 가운데 한 가지만 찾습니다.')

def feature_example():
    d=free_build(4);ids=[s['id'] for s in d['slots']]                 # player1 카푸아, player2 타렌툼, player3 메디올라눔, player4 시라쿠세
    d['id']='feature-trade-goals';d['title']='기능 예제 · 납품 목표와 교역 규칙 (4인)'
    d['rules'].update(mode='cooperative',objectives=dict(celebration='notice',population_total=6000,treasury_total=0,
        per_city={i:dict(population=1500,culture=0,prosperity=0,peace=0,favor=0,treasury=0) for i in ids},
        deliveries=[dict(id='pottery-to-tarentum',sender='player1',receiver='player2',resource=15,quantity=20,kind='either'),
                    dict(id='timber-to-syracuse',sender='player3',receiver='player4',resource=7,quantity=20,kind='gift')]),
        player_trade=dict(exceptions=[dict(between=['player1','player4'],allow=False)]))
    slot={s['id']:s for s in d['slots']}
    slot['player1'].update(starting_funds=12000,role_hint='도기를 만들어 타렌툼에 보냅니다. 시라쿠세와는 거래할 수 없습니다.',
        governance=dict(favor=60,policy='fixed',rank=4,salary_rank=-1,savings=0))
    slot['player2'].update(starting_funds=8000,role_hint='카푸아에서 도기를 받습니다. 24개월째에 작은 침략이 있습니다.',
        governance=dict(favor=50,policy='original',rank=2,salary_rank=4,savings=500),
        invasions=[dict(amount=16,month=24,point=0,target=4)])
    slot['player3'].update(role_hint='목재를 시라쿠세에 선물합니다. 6개월째에 지원금을 받습니다.',
        events=[dict(kind='grant',month=6,amount=2000,resource=0,deadline=0)])
    slot['player4'].update(role_hint='메디올라눔에서 목재를 받습니다. 12개월째에 황제가 밀을 요청합니다.',
        events=[dict(kind='request',month=12,amount=8,resource=1,deadline=2)])
    for c in d['empire']['cities']:
        if c['role']=='npc' and c.get('enabled'):c['trade_players']=['player1','player2'] if c['name_id'] in (3,6) else ['player3','player4']
    d['briefing']=('시나리오 제작기로 정할 수 있는 것을 한 판에 모은 예제입니다. 제작기에서 이 파일을 열어 값을 바꿔 보세요.\n\n'
        '승리 조건(1번 탭): 도시마다 인구 1,500명, 전체 6,000명. 납품 과제 둘 — 카푸아가 타렌툼에 도기 20포대(선물 또는 판매), 메디올라눔이 시라쿠세에 목재 20포대(선물).\n'
        '중립 도시(2번 탭): 브룬디지움과 카르타고는 카푸아·타렌툼만, 렙티스 마그나와 마실리아는 메디올라눔·시라쿠세만 거래합니다.\n'
        '자리 설정(3번 탭): 카푸아 12,000 / 타렌툼 8,000 데나리로 시작합니다. 자리마다 추천 역할이 있습니다. 카푸아와 시라쿠세는 서로 거래할 수 없습니다.\n'
        '통치자: 카푸아는 지지도 60 고정(검찰관), 타렌툼은 기술관 직급에 검찰관 봉급과 개인 재산 500.\n'
        '이벤트와 침략: 메디올라눔 6개월째 지원금 2,000, 시라쿠세 12개월째 밀 8포대 요청, 타렌툼 24개월째 침략(규모 16).')
    return d

def main():
    write('provincial-quartet',read(A/'scenario-drafts/provincial-quartet/scenario.json'))
    write('provincial-sextet',sextet())
    free=free_build(6);free['briefing']+='\n'+TUTORIAL
    write('freebuild-6p',with_start(free,'자유 건설입니다. 정해진 승리 조건이 없습니다.\n각자 도시를 키우고, 다른 총독과 물품과 돈을 주고받으세요.'))
    write('coop-6p',coop(6))
    write('throne-6p',throne(6))
    write('progress-6p',progress(6))
    if '--examples' in sys.argv:   # examples on disk only, never listed (the release tool leaves unlisted folders out)
        for n in (2,4):write(f'freebuild-{n}p',free_build(n))
        write('feature-trade-goals',feature_example())
    (A/'default-scenarios.json').write_text(json.dumps(dict(schema=1,scenarios=DEFAULTS),ensure_ascii=False,indent=1)+'\n',encoding='utf8')
    print('written:',', '.join(DEFAULTS),'+ default-scenarios.json')
if __name__=='__main__':main()
