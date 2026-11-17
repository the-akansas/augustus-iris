"""Authored one-shot city events. Execution/state live in the city's native SAV.

Each event happens once in its own city, the given number of months after the start (src: creator_city_events.h).
Every kind changes only that city, never the room's shared trade, prices or goals (user 2026-11-15):
  grant      city funds +amount
  favor      emperor's favour +-amount (needs the original favour rules)
  request    the emperor asks for amount loads of resource within deadline years (needs the original favour rules)
  building   building type `resource` becomes allowed (amount 1) or forbidden (amount 2); built ones stay
  god        god resource-1 (Ceres, Neptune, Mercury, Mars, Venus): blessing (1), small curse (2), great curse (3) -
             the game's own god effects and messages
  goods      amount loads of resource put into (amount > 0) or taken from (amount < 0) the city's warehouses/granaries
  health     city health +-amount
  migration  immigration at amount percent of normal for deadline months, then normal again
  revolt     a gladiator revolt (the game's own)
  message    the author's own message (text: title, a line break, then the body), shown in the city's message list
Two optional parts for every kind (2026-11-15):
  when       {"stat": population|prosperity|culture|health|money|favor, "at_least": n}: from its month on, the event
             waits until the city reaches n (the game's own event condition, checked by the city's game)
  repeat     {"every": months, "times": n}: n events, `every` months apart (the layout lists each one; the game sees
             ordinary one-shot events). With a condition as well, one event the game repeats `every` months after each
             time it happened, while the city still qualifies (EVENTREPEAT)
The game shows the kinds it has no message for (building, goods, health, migration, message) with a text written
here (layout: EVENTTEXT section, UTF-8 hex), so the game's C side carries no Korean wording of its own."""
KINDS=('grant','favor','request','building','god','goods','health','migration','revolt','message')
GODS=('케레스','넵튠','머큐리','마르스','비너스')
GOD_ACTS=('','축복','작은 저주','큰 저주')
MAX_TEXT=600   # UTF-8 bytes of one message (title and body)
STATS=('population','prosperity','culture','health','money','favor')   # EVENTCOND codes 1..6 (creator_city_events.h)
STAT_NAMES=dict(population='인구',prosperity='번영',culture='문화',health='건강',money='자금',favor='황제 지지도')
STAT_MAX=dict(population=1000000,prosperity=100,culture=100,health=100,money=1000000000,favor=100)
MAX_LAID_OUT=64   # events of one city after repeats (shared_empire.h)

def _names():
    import json
    from pathlib import Path
    here=Path(__file__).resolve().parent
    res={r['resource']:r['name'] for r in json.loads((here/'trade-catalog.json').read_text(encoding='utf-8-sig')) if r['resource']>0}
    bld={b['id']:b['name'] for b in json.loads((here/'building-catalog.json').read_text(encoding='utf-8-sig'))}
    return res,bld

def validate(slot):
    from scenario_project import integer,keys
    events=slot['events']
    if not isinstance(events,list) or len(events)>32:raise ValueError('도시별 이벤트는 최대 32개입니다.')
    res,bld=_names()
    for e in events:
        if not isinstance(e,dict) or e.get('kind') not in KINDS:raise ValueError('지원하지 않는 도시 이벤트입니다.')
        keys(e,'kind month amount resource deadline'+(' text' if e['kind']=='message' else '')+(' when' if 'when' in e else '')+(' repeat' if 'repeat' in e else ''),'city event')
        if 'when' in e:
            if e['kind']=='migration':raise ValueError('이민 증가·감소에는 조건을 붙일 수 없습니다(끝나는 달이 조건과 따로 움직입니다).')
            keys(e['when'],'stat at_least','event condition')
            if e['when']['stat'] not in STATS:raise ValueError('지원하지 않는 이벤트 조건입니다.')
            integer(e['when']['at_least'],1,STAT_MAX[e['when']['stat']],STAT_NAMES[e['when']['stat']]+' 조건')
        integer(e['month'],1,1200,'시작 후 개월')
        if 'repeat' in e:
            keys(e['repeat'],'every times','event repeat')
            integer(e['repeat']['every'],1,240,'반복 간격 (개월)');integer(e['repeat']['times'],2,24,'반복 횟수')
            if e['month']+e['repeat']['every']*(e['repeat']['times']-1)>1200:raise ValueError('반복하면 1200개월을 넘습니다.')
        k=e['kind']
        if k=='grant':integer(e['amount'],1,1000000,'지원금')
        elif k=='favor':
            integer(e['amount'],-100,100,'지지도 변화')
            if e['amount']==0:raise ValueError('지지도 변화는 0일 수 없습니다.')
        elif k=='request':
            integer(e['amount'],1,10000,'요청 포대');integer(e['resource'],1,21,'요청 물품');integer(e['deadline'],1,20,'기한 (년)')
        elif k=='building':
            integer(e['amount'],1,2,'허용 또는 금지');integer(e['resource'],1,300,'건물')
            if e['resource'] not in bld:raise ValueError('건설 허용 목록에 없는 건물입니다.')
        elif k=='god':integer(e['amount'],1,3,'축복 또는 저주');integer(e['resource'],1,5,'신')
        elif k=='goods':
            integer(e['amount'],-1000,1000,'물품 포대');integer(e['resource'],1,21,'물품')
            if e['amount']==0:raise ValueError('물품 포대는 0일 수 없습니다.')
            if e['resource'] not in res:raise ValueError('창고에 둘 수 없는 물품입니다.')
        elif k=='health':
            integer(e['amount'],-100,100,'건강 변화')
            if e['amount']==0:raise ValueError('건강 변화는 0일 수 없습니다.')
        elif k=='migration':
            integer(e['amount'],10,400,'이민 비율 (%)');integer(e['deadline'],1,120,'기간 (개월)')
            if e['amount']==100:raise ValueError('이민 비율 100%는 평소와 같습니다.')
        elif k=='revolt':integer(e['amount'],1,1,'검투사 반란')
        else:
            integer(e['amount'],1,1,'도시 소식')
            if not isinstance(e['text'],str) or not e['text'].strip():raise ValueError('도시 소식 내용을 쓰세요.')
            if len(message_text(e,res,bld).encode('utf-8'))>MAX_TEXT:raise ValueError('도시 소식이 너무 깁니다.')
        if k not in ('request','building','god','goods'):integer(e['resource'],0,0,'물품 없음')
        if k not in ('request','migration'):integer(e['deadline'],0,0,'기한 없음')
        if k in ('favor','request') and slot.get('governance',{}).get('policy')=='fixed':
            raise ValueError('지지도 변화·황제 물품 요청은 3 플레이 자리 설정의 통치자·황제 지지도 탭에서 황제 지지도를 원본 규칙으로 설정해야 합니다.')
    laid_out(slot)   # at most MAX_LAID_OUT once the repeats are counted

def message_text(e,res=None,bld=None):
    """The title and body (one line break between) the game shows for this event; '' = the game's own message."""
    if res is None:res,bld=_names()
    k=e['kind']
    if k=='building':
        name=bld.get(e['resource'],'건물')
        return '건설 허용 변경\n'+(f'이제 {name}을(를) 지을 수 있습니다.' if e['amount']==1 else f'이제 {name}을(를) 새로 지을 수 없습니다. 이미 지은 건물은 그대로 남습니다.')
    if k=='goods':
        name=res.get(e['resource'],'물품')
        return (f'보급품 도착\n{name} {e["amount"]}포대가 창고에 들어왔습니다. 창고 자리가 모자라면 들어갈 수 있는 만큼만 들어옵니다.' if e['amount']>0
                else f'물품 징발\n창고에서 {name} {-e["amount"]}포대를 가져갔습니다. 모자라면 있는 만큼만 가져갑니다.')
    if k=='health':return '도시 건강 변화\n'+(f'도시 건강이 {e["amount"]}만큼 좋아졌습니다.' if e['amount']>0 else f'도시 건강이 {-e["amount"]}만큼 나빠졌습니다.')
    if k=='migration':
        return ('이주민 증가\n' if e['amount']>100 else '이주민 감소\n')+f'앞으로 {e["deadline"]}개월 동안 이주민이 평소의 {e["amount"]}%만큼 들어옵니다.'
    if k=='message':   # the editor stores 'title\nbody'; a text without a line break is a body under the default title
        t=e['text'].strip().replace('\r\n','\n').replace('\r','\n')
        title,_,body=t.partition('\n')
        return (title.strip()+'\n'+body.strip()) if body.strip() else '도시 소식\n'+t
    return ''

def describe(e):
    """One line for the editor and the briefing."""
    res,bld=_names();k=e['kind']
    if k=='grant':return f"도시 지원금 {e['amount']:,} 데나리"
    if k=='favor':return f"황제 지지도 {e['amount']:+d}"
    if k=='request':return f"황제 요청: {res.get(e['resource'],'물품')} {e['amount']}포대 / 기한 {e['deadline']}년"
    if k=='building':return f"{bld.get(e['resource'],'건물')} "+('허용' if e['amount']==1 else '금지')
    if k=='god':return f"{GODS[e['resource']-1]}의 {GOD_ACTS[e['amount']]}"
    if k=='goods':return (f"보급품 {res.get(e['resource'],'물품')} {e['amount']}포대" if e['amount']>0 else f"징발 {res.get(e['resource'],'물품')} {-e['amount']}포대")
    if k=='health':return f"도시 건강 {e['amount']:+d}"
    if k=='migration':return f"이민 {e['amount']}% ({e['deadline']}개월)"
    if k=='revolt':return '검투사 반란'
    return '도시 소식: '+message_text(e,res,bld).split('\n',1)[0][:40]

def chained(e):
    """A repeat that also waits for the city (2026-11-15): laid out as copies, every copy whose month had passed fired
    at once when the city reached the value late. Such an event is one game event that the game itself repeats,
    `every` months after each time it happened (EVENTREPEAT). Repeats without a condition stay copies."""
    return 'repeat' in e and 'when' in e

def laid_out(slot):
    """The city's events as the game gets them: each repeat its own event, `every` months later."""
    out=[]
    for e in slot.get('events',[]):
        if chained(e):out.append(dict(e));continue   # one event; the game repeats it (EVENTREPEAT)
        r=e.get('repeat') or dict(every=0,times=1)
        for k in range(r['times']):out.append({**{x:v for x,v in e.items() if x!='repeat'},'month':e['month']+k*r['every']})
    if len(out)>MAX_LAID_OUT:raise ValueError(f'반복을 포함한 도시별 이벤트는 {MAX_LAID_OUT}개까지입니다.')
    # In month order (stable: the author's order within a month). The game installs them in this order, so the end
    # of one immigration change comes before a change that starts the same month.
    out.sort(key=lambda e:e['month'])
    # One immigration change at a time: the end of an earlier one would otherwise cut a later one short (2026-11-15).
    end=0
    for e in out:
        if e['kind']!='migration':continue
        if e['month']<end:raise ValueError(f"이민 증가·감소 기간이 겹칩니다({e['month']}개월). 앞의 변화가 끝난 뒤에 시작하도록 시작 개월이나 반복 간격을 바꾸세요.")
        end=e['month']+e['deadline']
    return out

def append_layout(data,rows):
    events=[(s['id'],e) for s in data['slots'] for e in laid_out(s)]
    if not events:return
    if not any(r.startswith('GOVERNANCE ') for r in rows):rows.append('GOVERNANCE 0')
    rows.append('EVENTS '+str(len(events)))
    for slot,e in events:rows.append(' '.join(map(str,[slot,KINDS.index(e['kind']),e['month'],e['amount'],e['resource'],e['deadline']])))

def texts(data):
    """The EVENTTEXT tail section: '<slot> <index of the event in its slot> <UTF-8 hex>' for events with a text."""
    res,bld=_names();out=[]
    for s in data['slots']:
        for i,e in enumerate(laid_out(s)):
            t=message_text(e,res,bld)
            if t:out.append(f"{s['id']} {i} {t.encode('utf-8').hex()}")
    return out

def repeats(data):
    """The EVENTREPEAT tail section (after EVENTCOND): '<slot> <index> <every> <times>' for the chained repeats."""
    return [f"{s['id']} {i} {e['repeat']['every']} {e['repeat']['times']}" for s in data['slots'] for i,e in enumerate(laid_out(s)) if 'repeat' in e]

def conditions(data):
    """The EVENTCOND tail section: '<slot> <index> <stat code> <value>' for events that wait for the city."""
    return [f"{s['id']} {i} {STATS.index(e['when']['stat'])+1} {e['when']['at_least']}" for s in data['slots'] for i,e in enumerate(laid_out(s)) if 'when' in e]
