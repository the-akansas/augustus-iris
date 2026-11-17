"""Enemy attacks inside a single city's simulation (not player attacks).

An attack may come again (user 2026-11-15): 'repeat' {every: months 1..240, times: 2..24} (attacks in all, the first
included); the game repeats the attack's own event (INVREPEAT tail section, creator_city_invasions.h).

Each attack may name its enemy people ('enemy', 0..19, the original game's list; absent = the city's people:
slot 'invasion_enemy', else the map's own). The game shows the pictures of one people at a time, so (user
2026-11-15) two attacks with different pictures may not come in the same month, and when other pictures arrive the
soldiers of the earlier people still in the city leave the map first (src/scenario/invasion.c)."""
def validate(slot):
    from scenario_project import integer,keys
    rows=slot['invasions']
    if not isinstance(rows,list) or len(rows)>16:raise ValueError('침략은 도시마다 최대 16회입니다.')
    for e in rows:
        keys(e,'month amount point target'+(' enemy' if 'enemy' in e else '')+(' repeat' if 'repeat' in e else ''),'invasion')
        integer(e['month'],1,1200,'침략 시작 후 개월')
        integer(e['amount'],5,150,'침략 기본 병력')
        integer(e['point'],0,8,'진입점 (0: 자동, 1~8: 지도 진입점)')
        integer(e['target'],0,4,'공격 목표')
        if 'enemy' in e:integer(e['enemy'],0,19,'침략 적군 종류')
        if 'repeat' in e:
            r=e['repeat']
            if not isinstance(r,dict):raise ValueError('침략 반복 설정 형식 오류')
            keys(r,'every times','invasion repeat')
            integer(r['every'],1,240,'침략 반복 간격(개월)');integer(r['times'],2,24,'침략 횟수')
            if e['month']+r['every']*(r['times']-1)>1200:raise ValueError(f"시작 후 {e['month']}개월 침략의 반복이 1200개월을 넘습니다. 간격이나 횟수를 줄이세요.")
    month={}
    for e in rows:
        people=people_of(slot,e);pictures='map' if people=='map' else PICTURE_FILE[people]
        for m in months(e):
            if month.setdefault(m,pictures)!=pictures:
                raise ValueError(f"시작 후 {m}개월에 서로 다른 적군이 들어옵니다(반복 포함). 같은 달의 침략은 같은 적군으로 정하세요(한 도시에는 한 종류의 그림만 보입니다).")

def months(e):
    """Every month the attack comes (the repeats included)."""
    r=e.get('repeat')
    return [e['month']+i*r['every'] for i in range(r['times'])] if r else [e['month']]

def repeats(data):
    """The INVREPEAT tail section (the last one): '<slot> <index> <every> <times>' for attacks that come again."""
    return [f"{s['id']} {i} {e['repeat']['every']} {e['repeat']['times']}" for s in data['slots'] for i,e in enumerate(s.get('invasions',[])) if 'repeat' in e]

# The picture file of each people (scenario/invasion.c ENEMY_PICTURE_FILE): peoples that share one look alike.
PICTURE_FILE=(0,1,1,2,3,3,4,5,6,7,7,7,8,8,0,0,0,6,9,6)

def people_of(slot,e):
    """The people of one attack: its own, else the city's, else 'map' (the map's own, not known here)."""
    return e.get('enemy',slot.get('invasion_enemy','map'))

def append_layout(data,rows):
    attacks=[(s['id'],e) for s in data['slots'] for e in s.get('invasions',[])]
    if not attacks:return
    if not any(x.startswith('GOVERNANCE ') for x in rows):rows.append('GOVERNANCE 0')
    if not any(x.startswith('EVENTS ') for x in rows):rows.append('EVENTS 0')
    rows.append('INVASIONS '+str(len(attacks)))
    for slot,e in attacks:rows.append(' '.join(map(str,[slot,e['month'],e['amount'],e['point'],e['target']])))

def raiders(data):
    """The optional RAIDERS section (after FUNDS and ENEMIES): '<slot> <index> <people>' for each attack that names
    its own people; index = its place among that slot's attacks."""
    return [f"{s['id']} {i} {e['enemy']}" for s in data['slots'] for i,e in enumerate(s.get('invasions',[])) if 'enemy' in e]
