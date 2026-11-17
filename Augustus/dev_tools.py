"""시나리오 제작자 방의 시험 도구 (user 2026-11-17: "개발자 방에서만 허용"). Both editions since 2026-11-17.

A room is a maker room when its creator ticked 시나리오 제작자 모드 in the game hall (game_hall.py: the room's `dev_mode`,
kept in its note so a continued game stays one) or in the LAN's 방 만들기 (maker_room.py: a file in the room's folder). Only such a room answers throne_test / progress_test (lobby.py);
every other room refuses them like an unknown request. A developer room's saves are offered only to developer rooms,
so nothing changed here reaches a normal game.
  * progress_adjust(): 황제의 순행, the waiting time of the current step is over ('t-next' of the panel)
  * throne_adjust(), forced_roll(): 황위 쟁탈전 test situations ('t-...' keys of the panel)
  * throne_client_action(), progress_client_action(): the game side of the two panels
The test launcher (mp_test_tools.py, in no release) reaches the same functions with AUGUSTUS_MP_TEST_TOOLS=1."""

# ---- 황제의 순행
def progress_adjust(db,binding,action):
    """'next': the waiting time of the current step is over. The room allows it only in a developer room (lobby.py)."""
    import imperial_progress as ip
    state=ip.current(db,binding)
    if state is None or action!='next':raise ValueError('시험 도구 동작 오류')
    now=state['last_tick']
    if state['phase']=='idle':state['next_tick']=now
    elif state['phase']=='bidding':state['close_tick']=now
    elif state['phase']=='travel':state['arrive_tick']=now
    ip.store(db,state,binding)

# ---- 황위 쟁탈전
TEST_ROLL={}
TEST_ACTIONS=('t-p+10','t-p-10','t-p100','t-wait','t-s+1','t-s-1','t-win','t-lose','t-rival')
def roll_key(db,city):
    """One room's city: the hall runs many rooms in one process, so a roll fixed in a developer room is kept under that
    room's database file and never reaches a city of the same name in another room."""
    row=next((r for r in db.execute('PRAGMA database_list') if r[1]=='main'),None)
    return (row[2] if row else '',city)

def forced_roll(db,city):
    """The coup roll a test key fixed for `city` of this room ('t-win' / 't-lose'), taken once; None otherwise."""
    return TEST_ROLL.pop(roll_key(db,city),None)   # filled only by throne_adjust, which only a developer room (or the test launcher) allows

def throne_adjust(db,binding,city,action,tick):
    """One test situation for `city` (its own record; 't-rival': the most advanced other player). Caller commits;
    only a developer room (or the test launcher) gets here (lobby.py)."""
    import throne_play as tp,throne_state as ts,throne_rules as tr
    if action not in TEST_ACTIONS:raise ValueError('지원하지 않는 시험 명령입니다.')
    state=tp._state(db,binding);rules=state['spec']['rules'];n=len(rules['stages'])
    if city not in state['players'] or 'secret' not in state['players'][city]:raise ValueError('참가 도시가 아닙니다.')
    if state['ended']:raise ValueError('황위 쟁탈전 시험이 끝났습니다.')
    ts.advance(state,max(tick,state['last_tick']));now=state['last_tick']
    if action in ('t-win','t-lose'):TEST_ROLL[roll_key(db,city)]=0 if action=='t-win' else 9999;return dict(ok=True)
    if action!='t-wait' and state['activated_tick'] is None:tp._activate(state,now)
    def restage(p,stage):
        s=p['secret'];p['stage']=stage;s['failures']=0;s['next_cost']=ts.expected_cost(rules,stage,0)
        s['paranoia']=max(s['paranoia'],tr.base_floor(rules,stage))
    p=state['players'][city];s=p['secret']
    if action=='t-p+10':s['paranoia']=min(rules['paranoia_max'],s['paranoia']+10)
    elif action=='t-p-10':s['paranoia']=max(tr.gift_floor(rules,p['stage']),s['paranoia']-10)
    elif action=='t-p100':s['paranoia']=rules['paranoia_max']
    elif action=='t-wait':s['next_attempt_tick']=now
    elif action=='t-s+1':
        if p['stage']<n-1:restage(p,p['stage']+1)
    elif action=='t-s-1':
        if p['stage']>0:restage(p,p['stage']-1)
    else:
        others=sorted((q['stage'],c) for c,q in state['players'].items() if c!=city and 'secret' in q and q['stage']<n-1)
        if others:restage(state['players'][others[-1][1]],others[-1][0]+1)
    ts.store(db,state,binding)
    return dict(ok=True)

# ---- the game side of the panels (multiplayer_dev.inc, shown in a developer room)
def throne_client_action(bridge,action,own):
    own=bridge.client.call('throne_test',action=action).get('own',own)
    notes={'t-win':'제작: 다음 쿠데타는 성공합니다.','t-lose':'제작: 다음 쿠데타는 실패합니다.'}   # whole lines: each is translated
    return own,notes.get(action,'제작: 적용했습니다.')

def progress_client_action(bridge,own):
    return bridge.client.call('progress_test',action='next').get('own',own),'제작: 다음 단계로 넘겼습니다.'
