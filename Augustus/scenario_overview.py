"""Read-only scenario overview. Uses authored coordinates and verified preset metadata."""
import json,unicodedata
from pathlib import Path

RES=dict(enumerate(['없음','밀','채소','과일','육류','생선','점토','목재','올리브','포도','철','대리석','금','모래','석재','도기','가구','기름','포도주','무기','콘크리트','벽돌','데나리우스','병력']))
# Same IDs as game/resource.h; unknown entries retain their numeric ID.
GOALS={'population':'인구','culture':'문화','prosperity':'번영','peace':'평화','favor':'황제 지지도','treasury':'자금'}
# What the scenario window says (user 2026-11-16): where the scenario is going, enough to choose a room; the detailed
# rules (the throne box, the progress' bids, events, governance) are met in the game.
THRONE_PRESETS={'standard':'표준','short':'짧은 판','long':'긴 판'}
def throne_preset(rules):
    import throne_rules
    return next((THRONE_PRESETS[p] for p in throne_rules.PRESETS if throne_rules.preset(p)==rules),'사용자 설정')
def clean(value):return ' '.join(str(value).replace('\x00','').split())[:600]
def wrap(text,width=168):
    lines=[];line='';used=0
    for ch in ' '.join(str(text).split()):
        advance=16 if unicodedata.east_asian_width(ch) in 'WF' else 8
        if used+advance>width and line:lines.append(line.rstrip());line='';used=0
        line+=ch;used+=advance
    if line:lines.append(line.rstrip())
    return lines or ['']
def lines(paragraphs):
    result=[]
    for text in paragraphs:
        if result:result.append('')
        result.extend(wrap(text))
    return result
# Tagged lines for the lobby's scenario window (multiplayer_scenario.inc). A line is "<kind>\t<text>":
#   H heading · F fact · R the author's suggestion (not a rule) · W warning · C continuation of the line above
#   T trade link: "T\t<state>\t<transport>\t<city index>\t<text>"  (state ok|candidate|unknown|broken, transport land|sea)
#   L the same link drawn on the map only (no text line), for the many plain land links summarised in one F line
# Untagged lines (older files) are drawn as plain text. 'C' lines are made by the game when it wraps a long line.
def tagged(kind,text,extra=''):
    """One logical line. The game wraps it to its own text column with the real font width."""
    return [kind+'\t'+extra+' '.join(str(text).replace('\t',' ').split())[:400]]
MODES={'imperial-progress':('경쟁 · 황제의 순행','황제가 순행할 때마다 비공개 입찰로 모실 도시를 정합니다. 황제가 찾는 물품을 넉넉히 드려 총애를 쌓으세요. 모든 순행이 끝났을 때 총애가 가장 높은 총독이 황제의 오른팔이 됩니다.'),
       'cooperative':('협동','공동 목표를 모두 달성하면 함께 승리합니다.'),
       'deadline-race':('경쟁 · 기한 경쟁','정해진 기간이 끝났을 때 정해진 수치가 가장 높은 도시가 승리합니다. 그 뒤에도 계속 플레이합니다.'),
       'race-for-throne':('경쟁 · 황위 쟁탈전','쿠데타 5단계를 먼저 끝낸 총독이 황제가 되고 그 순간 판이 끝납니다. 쿠데타는 익명이며, 실패할 때마다 모든 총독이 의심받습니다.'),
       'free-build':('자유 건설','정해진 승리 조건이 없습니다. 원하는 방향으로 도시를 키우세요.')}
# The game font has no em dash; keep to characters it draws.
STATE={'ok':'가능','candidate':'가능 후보','unknown':'미확인','broken':'불가'}
def overview(data,catalog,restore=False):
    from multiplayer_limits import MAX_ONLINE_PLAYERS
    presets={x['name_id']:x for x in catalog['neutral']}
    template=next((x for x in catalog['empire'] if x['id']==data['empire']['template']),None)
    coords={x['name_id']:x for x in template['cities']} if template else {}
    terrain={x['id']:x for x in catalog['terrain']};slots={x['name_id']:x for x in data['slots']}
    mode=data['rules'].get('mode','free-build');obj=data['rules'].get('objectives',{})
    mode_name,mode_goal=MODES.get(mode,MODES['free-build'])
    out=[]
    if restore:out+=tagged('W','공동 저장의 초기 시나리오 구성입니다. 저장 시점의 도시 상태는 방 입장 후 확인하세요.')
    authored=data.get('briefing','').strip()
    if authored:
        out+=tagged('H','소개 (제작자 글)')
        for p in authored.splitlines():
            if p.strip():out+=tagged('F',p)
    out+=tagged('H','모드와 승리 조건');out+=tagged('F',mode_name+': '+mode_goal)
    if mode=='deadline-race':
        import objectives
        race=data['rules']['race'];out+=tagged('F',f"{race['months']}개월이 지났을 때 {objectives.LABELS[race['stat']]} 값이 가장 높은 도시가 승리합니다.")
    if obj.get('population_total'):out+=tagged('F','공동 인구 목표: '+format(obj['population_total'],',')+'명')
    if obj.get('treasury_total'):out+=tagged('F','공동 자금 목표: '+format(obj['treasury_total'],','))
    if obj.get('deliveries'):
        import delivery_goals
        city_names={s['id']:presets.get(s['name_id'],{}).get('name',s['id']) for s in data['slots']}
        for g in obj['deliveries']:
            out+=tagged('F',f"납품 목표: {city_names.get(g['sender'],g['sender'])}에서 {city_names.get(g['receiver'],g['receiver'])}(으)로 {delivery_goals.CATALOG.get(g['resource'],g['resource'])} {g['quantity']:,}포대")
    if obj.get('by_players'):out+=tagged('F','적은 인원으로 시작하면 공동 목표가 줄어듭니다.')
    if mode=='imperial-progress':
        p=data['rules']['progress'];out+=tagged('F',f"순행 {p['rounds']}회 · 첫 순행 {p['start_months']}개월 뒤")
    if mode=='race-for-throne' and isinstance(data['rules'].get('throne'),dict):out+=tagged('F','황위 쟁탈전 프리셋: '+throne_preset(data['rules']['throne']))
    out+=tagged('H','인원');out+=tagged('F',f"플레이 도시 {len(data['slots'])}개 · 온라인 최대 {MAX_ONLINE_PLAYERS}명")
    from scenario_project import min_players
    if min_players(data)>1:out+=tagged('F',f"최소 인원 {min_players(data)}명: 그보다 적으면 시작할 수 없습니다.")
    if len(data['slots'])>MAX_ONLINE_PLAYERS:out+=tagged('F',f'{len(data["slots"])}자리 중 최대 {MAX_ONLINE_PLAYERS}명이 골라서 플레이합니다. 고르지 않은 자리는 중립 도시가 됩니다.')
    out+=tagged('H','공통 규칙')
    out+=tagged('F','플레이어 간 교역은 육로로 합니다.')
    barred=[r['between'] for r in (data['rules'].get('player_trade') or {}).get('exceptions',[]) if not r['allow']]
    if barred:
        slot_names={s['id']:presets.get(s['name_id'],{}).get('name',s['id']) for s in data['slots']}
        out+=tagged('W','교역 금지: '+', '.join(f'{slot_names.get(a,a)} - {slot_names.get(b,b)}' for a,b in barred))
    if 'starting_funds' in data['rules']:
        own=[s for s in data['slots'] if 'starting_funds' in s]
        out+=tagged('F','기본 시작 자금: '+format(data['rules']['starting_funds'],',')+' 데나리'+(' (일부 도시는 따로 정해져 있습니다)' if own else ''))
    else:out+=tagged('F','시작 조건은 각 도시 원본 설정을 사용합니다.')
    if 'start_year' in data['rules']:   # the author's first year (user 2026-11-17); the usual -350 is not announced
        year=data['rules']['start_year']
        out+=tagged('F',f'시작 연도: 기원전 {-year}년' if year<0 else f'시작 연도: 서기 {year}년')
    out+=tagged('F','바다 무역선이 못 들어오는 도시도 어장이 있으면 고기잡이는 할 수 있습니다.')
    common=(data.get('start_message') or {}).get('common','').strip()   # each city's own text is that player's (user 2026-11-16)
    if common:
        out+=tagged('H','게임 시작 메시지 (모두에게)')
        for p in common.replace('\r\n','\n').replace('\r','\n').split('\n'):
            if p.strip():out+=tagged('F',p)
    paragraphs=out
    try:
        import scenario_check
        result=scenario_check.check(data,None,scenario_check.evidence(data))
        links={x['slot']:x['links'] for x in result['links']};limits={x['slot']:x for x in result['limits']}
        warns={}
        for f in result['findings']:
            if f['severity'] in ('warn','block'):warns.setdefault(f['target'],[]).append(f['reason'])
    except Exception:links,limits,warns={},{},{}   # an overview never fails because of the checks
    names={x['name_id']:x['name'] for x in catalog['neutral']}
    order=[c for c in sorted(data['empire']['cities'],key=lambda c:c['role']!='player') if c['role']=='player' or c.get('enabled',True)]
    index={c['name_id']:i for i,c in enumerate(order)};by_slot={s['id']:s['name_id'] for s in data['slots']}
    rows=[]
    for c in order:
        base=coords.get(c['name_id'],{});name=presets.get(c['name_id'],{}).get('name','도시 '+str(c['name_id']))
        x,y=c.get('x',base.get('x')),c.get('y',base.get('y'))
        if x is None or y is None:raise ValueError('도시의 원본 좌표를 확인할 수 없습니다.')
        detail=[];slot=slots.get(c['name_id'])
        if slot:
            number=[s['id'] for s in data['slots']].index(slot['id'])+1
            detail+=tagged('H','플레이 도시 P'+str(number))
            if 'starting_funds' in data['rules']:
                detail+=tagged('F','시작 자금: '+format(slot.get('starting_funds',data['rules']['starting_funds']),',')+(' (이 도시 전용)' if 'starting_funds' in slot else ' (기본값)'))
            source=terrain.get(slot['campaign_scenario'],{}).get('title')
            detail+=tagged('F','지형: '+('외부 지도' if slot.get('terrain_asset') else '원작 '+(source or '지도'))+(' · 제작자 수정' if slot.get('terrain_edits') else ''))
            goals=obj.get('per_city',{}).get(slot['id'],{})
            active=[GOALS[k]+' '+format(v,',') for k,v in goals.items() if v and k in GOALS]
            if active:detail+=tagged('F','도시 목표: '+', '.join(active))
            for key,label in [('events','예정 이벤트'),('invasions','침공 일정')]:   # how many; what they are, the game tells
                if slot.get(key):
                    extra=sum(e['repeat']['times']-1 for e in slot[key] if 'repeat' in e)
                    detail+=tagged('F',label+': '+str(len(slot[key]))+'개'+(f' (반복 포함 {len(slot[key])+extra}회)' if extra else ''))
            if slot.get('role_hint'):detail+=tagged('H','제작자 추천');detail+=tagged('R','제작자 추천(규칙 아님): '+slot['role_hint'])
            limit=limits.get(slot['id'])
            if limit:
                detail+=tagged('H','확인된 조건')
                detail+=tagged('F','외부 해상 교역: '+{'candidate':'가능 후보','blocked':'불가','unknown':'미확인'}[limit['sea']]+(' ('+limit['reason']+')' if limit['sea']=='blocked' and limit['reason'] else ''))
                detail+=tagged('F','고기잡이: '+{'candidate':'가능 후보','blocked':'불가','unknown':'미확인'}.get(limit.get('fishing','unknown'),'미확인'))
            mine=[l for l in links.get(slot['id'],[]) if l['allowed']]
            if links:
                detail+=tagged('H','교역 상대')
                players=[names.get(by_slot.get(l['slot']),l['slot']) for l in mine if l['kind']=='player']
                detail+=tagged('F','교역 상대 플레이어: '+(', '.join(players) or '없음'))
                # Short first: players and every link that is not plainly working get a line each (problems first);
                # plainly working land links to neutral cities are one summary line, still drawn on the map.
                plain=[l for l in mine if l['kind']=='neutral' and l['state']=='ok']
                for l in sorted([l for l in mine if l not in plain],key=lambda l:(l['kind']!='player',['broken','unknown','candidate','ok'].index(l['state']))):
                    target=by_slot.get(l['slot']) if l['kind']=='player' else l['name_id']
                    if target not in index:continue
                    text=names.get(target,'도시 '+str(target))+' · '+('해로' if l['transport']=='sea' else '육로')+' · '+STATE[l['state']]+('' if l['state']=='ok' else ': '+l['reason'].split(': ',1)[-1])
                    detail+=tagged('T',text,extra=f"{l['state']}\t{l['transport']}\t{index[target]}\t")
                if plain:
                    detail+=tagged('F',f'육로 중립 도시 {len(plain)}곳과 교역 가능: '+', '.join(names.get(l['name_id'],str(l['name_id'])) for l in plain)+' (품목은 각 도시 설명)')
                    detail+=[f"L\t{l['state']}\t{l['transport']}\t{index[l['name_id']]}\t" for l in plain if l['name_id'] in index]
                barred=[l for l in links.get(slot['id'],[]) if not l['allowed'] and l['kind']=='player']
                if barred:detail+=tagged('W','교역 금지(시나리오 설정): '+', '.join(names.get(by_slot.get(l['slot']),l['slot']) for l in barred))
            for reason in warns.get(f"{name} ({slot['id']})",[])[:4]:detail+=tagged('W',reason)
        elif c.get('reserved'):
            detail+=tagged('H','플레이어 자리로 비워 둔 도시');detail+=tagged('F','교역하지 않습니다.')
        else:
            detail+=tagged('H','중립 교역 도시')
            detail+=tagged('F','교역 방식: '+('해상만' if c.get('sea') else '육로')+' · 개설 비용 '+str(c.get('cost',0)))
            # Names come from the original runtime's resource IDs (not UI order).
            for key,label in [('sells','판매 품목'),('buys','구매 품목')]:
                detail+=tagged('F',label+': '+(', '.join(RES.get(int(k),'자원 #'+str(k)) for k,v in c.get(key,{}).items() if v) or '없음'))
            partners=c.get('trade_players',[s['id'] for s in data['slots']])
            detail+=tagged('F','교역 허용 플레이어: '+(', '.join(names.get(by_slot[p],p) for p in partners if p in by_slot) or '없음'))
        rows.append(dict(name=name,player=bool(slot),x=x,y=y,detail=detail))
    over=len(slots)>MAX_ONLINE_PLAYERS
    import rome_capital
    rome_x,rome_y,_=rome_capital.position(data)   # fixed capital: shown on the map, never a player or trade city
    return dict(title=data['title'],subtitle=f"{mode_name} · 플레이 도시 {len(slots)}개 · 중립 도시 {len(rows)-len(slots)}개"+(f' · {len(slots)}자리 중 최대 {MAX_ONLINE_PLAYERS}명' if over else ''),briefing=paragraphs,cities=rows,rome=dict(x=rome_x,y=rome_y,**rome_capital.texts()))
def encode(label,view):
    result=['AUGSCENARIO1',clean(label),clean(view['title']),clean(view['subtitle']),str(len(view['briefing'])),*view['briefing'],str(len(view['cities']))]
    for c in view['cities']:
        result += [f"{int(c['player'])} {c['x']} {c['y']}",clean(c['name']),str(len(c['detail'])),*c['detail']]
    if view.get('rome'):   # optional last lines; older readers stop before them. Texts come from rome-capital.json only.
        r=view['rome'];result.append(f"ROME {r['x']} {r['y']}")
        for key,tag in (('title','ROMETITLE'),('description','ROMETEXT'),('facts','ROMEFACT'),('facts_detail','ROMEFACT')):
            if r.get(key):result.append(tag+'\t'+clean(r[key]))
    return '\n'.join(result)+'\n'
def publish(session):
    from scenario_project import load
    from city_client import HERE
    catalog=json.loads((HERE/'preset-catalog.json').read_text(encoding='utf-8-sig'))
    for index,entry in enumerate(session.starts):
        try:body=encode(entry['label'],overview(load(entry['project']),catalog,bool(entry.get('restore'))))
        except (OSError,ValueError,KeyError,TypeError):body=''
        session.publish(f'scenario-overview-{index}.txt',body)
