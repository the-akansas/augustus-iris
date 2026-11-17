"""Read-only player logistics cards. Never reserves cargo or changes a contract."""
import time
from city_labels import city_name
from live_trade import RESOURCES

NAMES={v:k for k,v in RESOURCES.items()}

def clean(value):
    return str(value).replace('\n',' ').replace('\r',' ').replace('\t',' ').encode('utf8')[:480].decode('utf8','ignore')

def cards(city,rows,agreements,stocks,names=None,maps=None):
    def name(c):return '내 도시' if c==city else clean(city_name(c,names))
    def goods(a):return f"{NAMES.get(a['resource'],'물품')} {a['quantity']}포대"
    def site(a):return (a['seller'],a['post'],a['generation'])
    def order(a):return (a.get('transfer') or 0,a['id'])
    active=sorted((a for a in agreements if a['state']=='active'),key=order)
    out=[];represented=set()
    for t in rows:
        f=t.get('fleet')
        if not f or f['home'] or not t['resource']:continue
        key=(t['sender'],f['building'],f['generation'])
        represented.update(a['id'] for a in agreements if a.get('transfer')==t['id'])
        state=t['state'];cargo=goods(t)
        title=f"[플레이어 · 육상] {'입고' if t['receiver']==city else '출고'} #{t['id']} · 교역소 #{f['building']}"
        route=f"{name(t['sender'])} -> {name(t['receiver'])}"
        if state in ('finished','rejected'):
            stage='하역 완료 · 도착 도시 퇴장 중' if state=='finished' else '거래 종료 · 상단 정리 중'
            route=f"적재 없음 · {name(t['receiver'])}에서 퇴장" if state=='finished' else '정산 종료 · 상단 배정 해제 대기'
        else:
            stage={'offered':'상대 수락 대기','queued':'상단에 실을 물품을 모으는 중','collecting':'창고에서 물품 수거 중',
                   'departing':'적재 완료 · 도시 출구로 이동','travelling':'도착 도시 운송·하역 준비',
                   'returning':'물품 반환·환불 확인 중','deferred':'처리 확인 대기'}.get(state,'운송 처리 중')
            if state=='travelling' and t.get('cargo_delivered'):stage='하역 완료 · 정산 확인 중'
            route=f"{cargo} · {route}"
        if t.get('suspended'):stage='상대 도시 연결 복구 대기 · 상태 보존'
        pending=next((q for q in rows if q['id']!=t['id'] and q.get('fleet') and
            (q['sender'],q['fleet']['building'],q['fleet']['generation'])==key and q['state']=='queued'),None)
        candidates=[a for a in active if site(a)==key and (a.get('transfer')!=t['id'] or a['repeat'])]
        ready=[a for a in candidates if stocks.get(a['seller'],{}).get(str(a['resource']),stocks.get(a['seller'],{}).get(a['resource'],0))>=a['quantity']]
        candidate=ready[0] if ready else candidates[0] if candidates else None
        if pending:following=f"다음 대기: {goods(pending)} -> {name(pending['receiver'])}"
        elif candidate:
            following=f"다음 후보: {goods(candidate)} -> {name(candidate['buyer'])}"
            if not ready:following+=' · 재고 대기' if candidate['seller']==city else ' · 상대 준비 대기'
            if t['sender']!=city:following+=' (우리 거래 기준)'
        else:following='다음 주문 없음'
        out.append([title,route,stage,following])
        if maps is not None:
            phase=4 if state in ('finished','rejected') else 1 if state=='collecting' else 2 if state=='departing' else 3 if state=='travelling' else 0
            if t.get('suspended'):phase=0
            maps.append([f'{phase} 0',name(t['sender']),name(t['receiver'])])
    for a in sorted(agreements,key=lambda a:(a['state'] not in ('active','offered','paused'),*order(a))):
        if a['id'] in represented or a['state'] not in ('active','offered','paused'):continue
        amount=stocks.get(a['seller'],{}).get(str(a['resource']),stocks.get(a['seller'],{}).get(a['resource'],0))
        stage='동의 대기' if a['state']=='offered' else '일시중단 · 교역소 확인 후 재제안' if a['state']=='paused' else '상대 준비 대기' if a['seller']!=city else '재고 대기' if amount<a['quantity'] else '상단 퇴장·배정 대기'
        out.append([f"[플레이어 · {'지속' if a['repeat'] else '일회'} 주문] 계약 #{a['id']}",
            f"{goods(a)} · {name(a['seller'])} -> {name(a['buyer'])}",stage,
            f"회차당 {a['money']:,} Dn · 완료/진행 회차 {a['cycle']}"])
        if maps is not None:maps.append(['0 0',name(a['seller']),name(a['buyer'])])
    if len(out)>127:
        out=out[:127]+[['표시 한도','128개 항목까지 표시합니다.','계약 관리에서 나머지 주문을 확인하세요.','']]
        if maps is not None:maps[:]=maps[:127]+[['0 0','판매 도시','구매 도시']]
    return out

def publish(b,data):
    a=data['agreements']
    maps=[]
    rows=cards(b.client.city,data['rows'],a['agreements'],a['stocks'],getattr(b,'city_names',None),maps)
    text=f"2 {int(time.time())} {len(rows)}\n"+''.join('\n'.join(clean(s) for s in [*meta,*row])+'\n' for meta,row in zip(maps,rows))
    b.write_changed('trade-board.txt',text)
