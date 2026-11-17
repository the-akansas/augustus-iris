"""Bounded presentation-only event journal. No economy or army authority."""
import json,time

# Kinds: 1 caravan, 2 expedition, 3 post to build, 4 offer to answer, 5 offer answered, 6 post holding goods,
# 7 Race for the Throne public line (failure, end): fanfare, no camera target (throne_client.fanfare).
# To-do notices (pending) stay until done. Everything else is shown briefly and
# then kept only in the log that the bell panel can open.
TRANSIENT_SECONDS=10
LOG_LIMIT=64

def state(b):
    if not hasattr(b,'city_notice_state'):
        try:
            s=json.loads((b.root/'city-notice-state.json').read_text(encoding='utf8'))
            if not isinstance(s,dict) or not {'sequence','seen','events'}<=set(s) or not set(s)<={'sequence','seen','events','read','pending','expire','log'} or type(s['sequence'])!=int or not 0<=s['sequence']<2**64 or not isinstance(s['seen'],list) or not isinstance(s['events'],list):raise ValueError('notice state')
            if len(s['seen'])>2048 or any(not isinstance(k,str) or len(k)>160 for k in s['seen']) or len(s['events'])>8:raise ValueError('notice bounds')
            prior=0
            for e in s['events']:
                if not isinstance(e,list) or len(e)!=7 or any(type(v)!=int for v in e[:6]) or not prior<e[0]<=s['sequence'] or e[1] not in (1,2,3,4,5,6,7) or not 0<e[2]<2**32 or (e[1]==3 and not 1<=e[2]<=8) or not 0<=e[3]<100000 or not 0<=e[4]<65536 or e[5] not in (0,1) or not isinstance(e[6],str) or len(e[6])>180 or any(c in e[6] for c in '\r\n\t\0'):raise ValueError('notice event')
                prior=e[0]
            ids={e[0] for e in s['events']}
            s.setdefault('read',[])
            s.setdefault('pending',[e[0] for e in s['events'] if e[1] in (3,4)])
            if any(not isinstance(s[k],list) or len(s[k])>8 or any(type(v)!=int or v not in ids for v in s[k]) for k in ('read','pending')):raise ValueError('notice read state')
            s.setdefault('expire',{});s.setdefault('log',[])
            if not isinstance(s['expire'],dict) or any(not isinstance(k,str) or type(v) not in (int,float) for k,v in s['expire'].items()):s['expire']={}
            if not isinstance(s['log'],list) or len(s['log'])>LOG_LIMIT or any(not isinstance(e,list) or len(e)!=4 or any(type(v)!=int for v in e[:3]) or not isinstance(e[3],str) for e in s['log']):s['log']=[]
        except (OSError,ValueError):s=dict(sequence=time.time_ns(),seen=[],events=[],read=[],pending=[],expire={},log=[])
        b.city_notice_state=s
    return b.city_notice_state

def drop(s,kind,target):
    """Remove notices that no longer ask anything of the player."""
    s['events']=[e for e in s['events'] if not (e[1]==kind and e[2]==target)]
    resolve(s,kind,target)

def add(s,key,kind,target,fallback,generation,source,text,silent=False,pending=False,replace=False):
    if key in s['seen']:return
    s['seen']=(s['seen']+[key])[-2048:]
    if silent:return
    resolve(s,kind,target)
    if replace:drop(s,kind,target) # One line per transfer: its latest stage.
    s['sequence']+=1
    event=[s['sequence'],kind,int(target),int(fallback),int(generation),int(source),text.replace('\n',' ').replace('\r',' ').replace('\t',' ')[:180]]
    s['events']=(s['events']+[event])[-8:]
    if pending:s['pending'].append(event[0])
    else:s.setdefault('expire',{})[str(event[0])]=time.time()+TRANSIENT_SECONDS
    s['log']=(s.get('log',[])+[[event[0],kind,int(time.time()),event[6]]])[-LOG_LIMIT:]

def resolve(s,kind,target):
    resolved={e[0] for e in s['events'] if e[1]==kind and e[2]==target}
    s['pending']=[v for v in s.get('pending',[]) if v not in resolved]

def publish(b,s):
    ids={e[0] for e in s['events']}
    read=set(s.get('read',[]))
    try:
        lines=(b.root/'city-notice-read.txt').read_text().split()
        if len(lines)<=64:
            read.update(int(v) for v in lines if v.isdecimal() and len(v)<=20 and int(v) in ids)
    except (OSError,ValueError):pass
    pending=set(s.get('pending',[]))
    now=time.time();expire=s.setdefault('expire',{})
    s['events']=[e for e in s['events'] if (e[0] not in read or e[0] in pending) and (e[0] in pending or expire.get(str(e[0]),now+1)>now)]
    s['expire']={k:v for k,v in expire.items() if v>now and int(k) in {e[0] for e in s['events']}}
    ids={e[0] for e in s['events']}
    s['read']=sorted(read & ids);s['pending']=sorted(pending & ids)
    b.write_changed('city-notice-state.json',json.dumps(s,ensure_ascii=False))
    lines=[str(len(s['events']))]
    for e in s['events']:lines.extend([' '.join(map(str,e[:6])),e[6]])
    b.write_changed('city-notices.txt','\n'.join(lines)+'\n')
    log=list(reversed(s.get('log',[])))
    b.write_changed('city-notice-log.txt',str(len(log))+'\n'+''.join(f'{e[0]} {e[1]} {e[2]}\n{e[3]}\n' for e in log))

def resource_name(resource):
    from pathlib import Path
    try:
        catalog=json.loads(Path(__file__).with_name('trade-catalog.json').read_text(encoding='utf-8'))
        return next((i['name'] for i in catalog if i['resource']==resource),'물품')
    except (OSError,ValueError):return '물품'

def settled_text(b,t,source):
    """One line saying the goods and money of a transfer are final."""
    from city_labels import city_name
    peer=city_name(t['receiver'] if source else t['sender'],getattr(b,'city_names',None))
    goods=f"{resource_name(t.get('resource',0))} {t.get('quantity',0)}포대"
    if t.get('money'):
        return f"정산 완료: {peer}에 {goods} 판매 · {t['money']:,} Dn 받음" if source else f"정산 완료: {peer}에서 {goods} 구매 · {t['money']:,} Dn 지급"
    return f"선물 전달 완료: {peer}에 {goods}" if source else f"선물 입고 완료: {peer}에서 {goods}"

def agreement_rounds(b):
    """Transfer id -> round number for rounds of my agreed contracts (the host issues and accepts these itself)."""
    return {a['transfer']:a.get('cycle',0) for a in getattr(b,'agreements',None) or [] if a.get('transfer')}

FAILED_TEXTS=('구매자의 자금이 모자라 거래가 취소되었습니다.','판매자 교역소에 물품이 모자라 거래가 취소되었습니다.')

def trade(b,rows):
    s=state(b);first=not getattr(b,'city_notice_trade_ready',False);rounds=agreement_rounds(b)
    for t in rows:
        f=t.get('fleet');source=t['sender']==b.client.city;phase=t['state'];key='trade:'+str(t['id'])
        if t.get('resource') and phase=='finished' and b.client.city in (t['sender'],t['receiver']):
            # Settlement is final for both sides: a result notice, nothing to locate.
            add(s,key+':settled',5,t['id'],0,0,int(source),settled_text(b,t,source),silent=first)
        if source and phase=='rejected' and not (f and f.get('assigned')) and t.get('resource'):
            # My offer was declined before any caravan moved: tell me once, with or without a fleet row.
            from city_labels import city_name
            left='방을 나가' in (t.get('error') or '')
            add(s,key+(':left' if left else ':declined'),5,t['id'],0,0,1,f"{'상대가 방을 나가 거래가 취소되었습니다' if left else '제안이 거절되었습니다'}: {city_name(t['receiver'],getattr(b,'city_names',None))}에 {resource_name(t['resource'])} {t.get('quantity',0)}포대",silent=first)
        left_on_road=t.get('error')=='상대가 방을 나가 거래를 취소했습니다.' and f and f.get('assigned')
        if t.get('resource') and phase=='rejected' and ((t.get('error') or '') in FAILED_TEXTS or left_on_road) and b.client.city in (t['sender'],t['receiver']):
            # An accepted deal fell through: both sides learn why, once.
            text='상대가 방을 나가 상단이 물품을 싣고 돌아옵니다.' if left_on_road else t['error']
            add(s,key+(':left' if left_on_road else ':failed'),5,t['id'],0,0,int(source),f"{text} ({resource_name(t['resource'])} {t.get('quantity',0)}포대)",silent=first)
        if not f:
            if source and t.get('resource')==0 and phase in ('finished','rejected'):
                # Kind 5: a result with nothing to locate on the map.
                add(s,key+':'+phase,5,t['id'],0,0,1,
                    '돈 선물 송금이 완료되었습니다.' if phase=='finished' else '돈 선물이 거절되거나 취소되었습니다.',silent=first)
            continue
        args=(1,t['id'],f['building'] if source else 0,f['generation'] if source else 0,source)
        if source and phase in ('queued','collecting','departing','travelling'):
            # A contract's later rounds were agreed once already: record the key, no card (first round keeps it).
            add(s,key+':accepted',*args,'거래 제안이 수락되었습니다. / 교역소 상단',silent=rounds.get(t['id'],0)>1,replace=True)
        if not source and (phase=='finished' or phase=='travelling' and t.get('map_arrived',False)):
            add(s,key+':arrival',*args,'플레이어 교역 상단이 도착했습니다.',silent=first and phase=='finished',replace=True)
        if source and f['home'] and f.get('assigned'):
            add(s,key+':home',*args,'교역이 종료되었습니다. 다음 거래를 준비할 수 있습니다.',silent=first,replace=True)
    b.city_notice_trade_ready=True;publish(b,s)

POST_FULL_TEXT='교역소에 있는 물품을 저장할 빈 저장소가 없습니다.'

def post_storage(b):
    """Kind 6: a to-do that stays until the native city can move the goods out.
    post-blocked.txt lines: building generation resource surplus. A missing or
    damaged file means unknown: keep the current notices unchanged."""
    try:lines=(b.root/'post-blocked.txt').read_text(encoding='utf8').splitlines()
    except OSError:return
    blocked={}
    for line in lines:
        parts=line.split()
        if len(parts)!=4 or not all(p.isdigit() for p in parts):return
        building,generation,resource,_=map(int,parts)
        if not 0<building<100000:return
        blocked.setdefault((building,generation),set()).add(resource)
    s=state(b);shown={e[2] for e in s['events'] if e[1]==6 and e[2]<ROAD_TARGET}
    for (building,generation),resources in sorted(blocked.items()):
        names='·'.join(resource_name(r) for r in sorted(resources))
        key=f"post-full:{building}:{generation}:{','.join(map(str,sorted(resources)))}"
        add(s,key,6,building,building,generation,1,f'{POST_FULL_TEXT} ({names})'[:180],pending=True,replace=True)
    for building in shown-{k[0] for k in blocked}:
        drop(s,6,building)
        # The same goods may block again later: let that be noticed afresh.
        s['seen']=[k for k in s['seen'] if not k.startswith(f'post-full:{building}:')]
    publish(b,s)

ROAD_TARGET=1000000 # keeps these apart from the post-full notices of the same building
ROAD_TEXT={2:'교역소가 길에 닿아 있지 않아 상단이 오갈 수 없습니다. 길을 이어 주세요.',
           4:'교역소에서 도시 출입구까지 길이 끊겨 상단이 오갈 수 없습니다.'}

def post_road(b,data):
    """Kind 6: my post cannot be reached while a deal with its partner is under way.
    post-readiness.txt lines: building generation workers reason (2 no road, 4 gates unreachable)."""
    try:lines=(b.root/'post-readiness.txt').read_text(encoding='utf8').splitlines()
    except OSError:return
    reason={}
    for line in lines:
        parts=line.split()
        if len(parts)!=4 or not all(p.isdigit() for p in parts):return
        reason[(int(parts[0]),int(parts[1]))]=int(parts[3])
    me=b.client.city;busy=set()
    for t in data.get('rows',[]):
        if t.get('resource') and t['state'] not in ('finished','rejected') and me in (t['sender'],t['receiver']):
            busy.add(t['receiver'] if t['sender']==me else t['sender'])
    for a in data.get('agreements',{}).get('agreements',[]):
        if a['state'] in ('offered','active') and me in (a['seller'],a['buyer']):
            busy.add(a['buyer'] if a['seller']==me else a['seller'])
    wanted={}
    for p in data.get('routes',{}).get('posts',[]):
        site=(p['building'],p['generation'])
        if p['city']==me and p['active'] and p['peer'] in busy and reason.get(site) in ROAD_TEXT:wanted[site]=reason[site]
    s=state(b);shown={e[2] for e in s['events'] if e[1]==6 and e[2]>=ROAD_TARGET}
    for (building,generation),why in sorted(wanted.items()):
        add(s,f'post-road:{building}:{generation}:{why}',6,ROAD_TARGET+building,building,generation,1,ROAD_TEXT[why],pending=True,replace=True)
    for target in shown-{ROAD_TARGET+k[0] for k in wanted}:
        drop(s,6,target)
        s['seen']=[k for k in s['seen'] if not k.startswith(f'post-road:{target-ROAD_TARGET}:')]
    publish(b,s)

def army(b,rows):
    s=state(b);first=not getattr(b,'city_notice_army_ready',False)
    for r in rows:
        if not r.get('token'):continue # Legacy expeditions have a separate native protocol.
        source=r['origin']==b.client.city;phase=r['phase'];key='army:'+r['id']
        args=(2,r['token'],r.get('formation',0) if source else 0,0,source)
        if source and phase in ('departing','travelling','arriving') and not r.get('returning'):
            add(s,key+':accepted',*args,'군단 파견 명령이 수락되었습니다.')
        if not source and phase=='travelling' and r['role']==1 and not r.get('returning') and not r.get('released'):
            name=getattr(b,'city_names',{}).get(r['origin'],r['origin'])
            add(s,key+':coming',*args,name+'에서 지원군이 오고 있습니다. 군사 탭에서 도착 예정을 볼 수 있습니다.',silent=first)
        if not source and phase=='stationed':
            add(s,key+':arrival',*args,('상대 공격군' if r['role']==2 else '지원군')+'이 도시에 도착했습니다.',silent=first)
        if r.get('wiped') and phase!='stationed':
            add(s,key+':wiped',*args,'보낸 지원군이 전멸했습니다. 요새는 남아 있어 다시 충원됩니다.' if source else '우리 도시를 지키던 지원군이 전멸했습니다.',silent=first)
        if source and r.get('released'):
            add(s,key+':released',*args,'상대 도시가 방을 나가 보낸 군단이 돌아옵니다.',silent=first)
        if source and phase=='returned' and not r.get('wiped'):
            add(s,key+':home',*args,'파견한 군단이 귀환했습니다.',silent=first)
    b.city_notice_army_ready=True;publish(b,s)
