"""Read-only partner/deal tables for the 800x600 trade screens.

Presentation only: derives rows from the same live_sync packet as the other
bridges. Never calls the server, reserves cargo or changes a contract.
"""
import time

# Deal kinds: 0 needs my answer, 1 running, 2 waiting for the peer, 3 paused.
# Action bits: 1 accept, 2 reject/cancel/stop, 4 counter terms (quantity and price), 8 resume.
PHASE={'queued':0,'collecting':0,'preflight':0,'departing':1,'travelling':2,'finished':4}
STATUS={'offered':'상대의 수락을 기다리는 중','queued':'상단에 싣는 중','collecting':'교역소에 물품을 모으는 중',
        'preflight':'운송 경로 확인 중','departing':'도시 출구로 이동 중','travelling':'제국지도 이동 중',
        'returning':'거래 취소 · 물품 반환 확인 중','deferred':'전달 확인을 기다리는 중',
        'finished':'하역 완료 · 상단이 도착 도시를 떠나는 중','rejected':'거래 종료 · 상단 정리 중'}

def clean(value):
    return str(value).replace('\n',' ').replace('\r',' ').replace('\t',' ').encode('utf8')[:200].decode('utf8','ignore')

def transfer_deal(city,t,agreement):
    out=t['sender']==city;peer=t['receiver'] if out else t['sender'];state=t['state']
    cash=not t['resource']
    phase=-1 if cash else PHASE.get(state,-1)
    text=STATUS.get(state,'처리 중')
    if not cash and state=='travelling' and (t.get('map_arrived') or t.get('cargo_delivered')):
        phase=3;text='정산 확인 중' if t.get('cargo_delivered') else ('내 교역소에 내리는 중' if not out else '상대 교역소에 내리는 중')
    if cash:text={'offered':'상대의 수락을 기다리는 중' if out else '돈 선물이 도착했습니다','finished':'송금 완료','rejected':'거절 또는 취소됨'}.get(state,'송금 처리 중')
    if not cash and t.get('dest_ready') is False and state in ('queued','collecting','preflight','travelling'):
        # The receiving post stands but no caravan can reach it: say whose move it is.
        text='상대 교역소의 길 연결을 기다리는 중' if out else '내 교역소에 길을 이어야 받을 수 있습니다'
    if t.get('suspended'):text='상대 도시 재접속 대기 · 상태 보존'
    kind=1;actions=0
    if state=='offered':
        if agreement:kind=1;text='계약 체결 · 운송 준비 중'
        elif out:kind=2;actions=2
        else:kind=0;actions=3;text='수락 또는 거절해 주세요' if not cash else text
    elif not agreement and out and state in ('queued','collecting'):actions=2
    if agreement:
        actions=2 if agreement['state'] in ('offered','active','paused') else 0
        return [peer,kind,1,agreement['id'],t['resource'],t['quantity'],t['money'],int(out),phase,actions,agreement.get('revision',0),agreement['cycle'],agreement['repeat'],text]
    return [peer,kind,0,t['id'],t['resource'],t['quantity'],t['money'],int(out),phase,actions,0,0,0,text]

def agreement_deal(city,a):
    out=a['seller']==city;peer=a['buyer'] if out else a['seller'];state=a['state'];mine=a['proposer']==city
    if state=='offered':
        if mine:kind=2;actions=2;text='상대의 동의를 기다리는 중'
        else:
            kind=0;actions=3|4;text='조건 조정 제안 · 수락 또는 거절해 주세요' if a.get('revision',0) else '수락 또는 거절해 주세요'
            if a.get('allow_partial'):actions|=32 # a reduced quantity is accepted at once
    elif state=='paused':kind=3;actions=10;text='일시 중단 · 교역소 확인 후 다시 제안'
    else:
        kind=1;actions=2;text='재고와 상단 차례를 기다리는 중' if out else '상대 도시의 준비를 기다리는 중'
        left=a.get('due_left')
        if type(left)==int:text+=f' · 납기까지 {left//800}개월 {(left%800)//50}일' # not sent by then: the contract expires
    return [peer,kind,1,a['id'],a['resource'],a['quantity'],a['money'],int(out),-1,actions,a.get('revision',0),a['cycle'],a['repeat'],text]

def deals(city,rows,agreements):
    linked={a['transfer']:a for a in agreements if a.get('transfer')}
    out=[];shown=set()
    for t in rows:
        if city not in (t['sender'],t['receiver']):continue
        fleet=t.get('fleet')
        if t['state'] in ('finished','rejected') and (not fleet or fleet['home'] or not fleet.get('assigned')):continue
        a=linked.get(t['id'])
        if a:shown.add(a['id'])
        out.append(transfer_deal(city,t,a))
    for a in agreements:
        if a['id'] in shown or a['state'] not in ('offered','active','paused') or city not in (a['seller'],a['buyer']):continue
        out.append(agreement_deal(city,a))
    out.sort(key=lambda d:(d[0],d[1],d[2],d[3]))
    return out[:128]

def partners(city,roster,routes,table,blocked=()):
    """Partner rows for the trade window. A pair the scenario forbids is not offered at all (the server refuses it too)."""
    barred={b if a==city else a for a,b in blocked}
    links={r['b'] if r['a']==city else r['a']:r for r in routes['links'] if city in (r['a'],r['b'])}
    posts={(p['city'],p['peer']) for p in routes['posts'] if p['active']}
    out=[]
    for slot,peer in enumerate(sorted(roster),1):
        if peer==city or peer in barred:continue
        r=links.get(peer)
        state=0 if not r else 1 if r['state']=='active' else 2 if r['state']=='offered' and r['proposer']!=city else 3 if r['state']=='offered' else 0
        mine=[d for d in table if d[0]==peer]
        running=sum(1 for d in mine if d[1]==1 and (d[2]==0 or d[8]>=0))
        standing=sum(1 for d in mine if d[2]==1 and d[1] in (1,3))
        inbox=sum(1 for d in mine if d[1]==0 and d[4])+(1 if state==2 else 0) # money gifts have their own card
        out.append([slot,peer,state,int((city,peer) in posts),int((peer,city) in posts),running,standing,inbox,r['revision'] if r else 0])
    return out

def publish(b,data):
    city=b.client.city
    table=deals(city,data['rows'],data['agreements']['agreements'])
    stamp=int(time.time())
    text=f'1 {stamp} {len(table)}\n'+''.join(' '.join(str(v) for v in d[:13])+'\n'+clean(d[13])+'\n' for d in table)
    b.write_changed('trade-deals.txt',text)
    people=partners(city,data['route_roster'],data['routes'],table,data.get('trade_blocked',()))
    b.write_changed('trade-partners.txt',f'1 {stamp} {len(people)}\n'+''.join(' '.join(str(v) for v in p)+'\n' for p in people))
