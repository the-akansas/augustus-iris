"""Read-only transport animation. Movement is illustrative, never a receipt."""
import time
from live_trade import TRADE_CATALOG

def motion(t):
    """0 source, 1 outbound, 2 arrival confirmed, 3 return, 4 hold."""
    if t.get('suspended'):return 4
    if t.get('phase')=='refund' or t['state']=='returning':return 3
    if t['state']=='finished' or t.get('phase')=='deliver':return 2
    if t['state']=='travelling':return 1
    return 0

def publish(bridge, trade):
    if not trade or bridge.client.city not in (trade['sender'], trade['receiver']):
        bridge.write_changed('empire-transport.txt', '')
        return
    t = trade
    key = (t['id'], t['state'], t.get('phase'), t.get('error'), bool(t.get('suspended')))
    now = time.monotonic()
    if getattr(bridge, '_empire_transport_key', None) != key:
        bridge._empire_transport_key = key
        bridge._empire_transport_since = now
    if t['state'] == 'finished' and now - bridge._empire_transport_since > 15:
        bridge.write_changed('empire-transport.txt', '')
        return
    slots = {}
    try:
        for line in (bridge.root / 'empire-player-slots.txt').read_text(encoding='utf8').splitlines():
            name_id, city, label = line.split('\t', 2)
            slots[city] = (int(name_id), label)
    except (OSError, ValueError):
        bridge.write_changed('empire-transport.txt', '')
        return
    if t['sender'] not in slots or t['receiver'] not in slots:
        bridge.write_changed('empire-transport.txt', '')
        return
    labels = {'offered':'수락 대기', 'collecting':'저장소에서 수거 중',
              'departing':'도시 출구로 이동 중', 'travelling':'운송 중, 입고 확인 대기',
              'saving':'저장 및 정산 중', 'committed':'게임에 반영 중',
              'returning':'화물 반환 대기', 'finished':'입고 완료',
              'rejected':'거래 거절 또는 검사 실패', 'cancelled':'거래 취소'}
    state = '참가자 연결 대기' if t.get('suspended') else labels.get(t['state'], '거래 확인 중')
    phase = t.get('phase')
    if not t.get('suspended') and t['state'] in ('saving','committed'):
        state = {'load':'출발 검사 및 선적 중', 'depart':'출발 처리 중',
                 'deliver':'입고 및 대금 반영 중', 'refund':'반환 처리 중'}.get(phase,state)
    res = next((x['name'] for x in TRADE_CATALOG if x['resource']==t['resource']), '돈')
    amount = f"{res} {t['quantity']}포대" if t['resource'] else f"{t['money']}데나리"
    mode = ('해상' if t.get('source_route')==3 else '육상') if t['resource'] else '송금'
    # v2 animates between cities, stopping short until actual arrival is reported.
    # This is a schematic relationship, not geography or an ETA.
    destination = t['state']=='travelling' or phase=='deliver' or t['state']=='finished'
    source, target = slots[t['sender']], slots[t['receiver']]
    warning = bool(t.get('error') or t.get('suspended') or t['state'] in ('rejected','cancelled','returning'))
    tone = 2 if warning else 3 if t['state']=='finished' else 1 if t['state']=='offered' else 0
    lines = [f"2 {source[0]} {target[0]} {t['resource']} {int(destination)} {t['quantity']} {tone} {t['id']} {motion(t)}",
             f"{source[1]} -> {target[1]}", f"{mode} / {amount} / {state}",
             t.get('error') or f"이동은 운송 연출 / 화물 {t.get('cargo_remaining',0)}포대 / 클릭: 상세"]
    bridge.write_changed('empire-transport.txt', '\n'.join(s.replace('\n',' ').replace('\r',' ') for s in lines))
