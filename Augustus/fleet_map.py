"""Read-only multiple caravan animation; no inventory or receipt authority."""
import time

def publish(b,rows):
    try:
        slots={}
        for line in (b.root/'empire-player-slots.txt').read_text(encoding='utf8').splitlines():
            name,city,label=line.split('\t',2);slots[city]=(int(name),label)
    except (OSError,ValueError):
        b.write_changed('empire-fleet.txt','0\n');return
    # Completed local return removes the icon. Never reinsert it on a later poll.
    visible=[t for t in rows if t.get('fleet') and t['fleet']['assigned'] and not t['fleet']['home']
             and t['sender'] in slots and t['receiver'] in slots]
    lines=[]
    for t in visible[:64]:
        s,d=slots[t['sender']],slots[t['receiver']]
        state=t['state']
        progress=t.get('map_progress',1000 if state=='finished' or t.get('cargo_delivered') else 0)
        motion=4 if t.get('suspended') else 3 if state in ('returning','rejected') else 2 if progress>=1000 else 1 if state=='travelling' else 0
        label={0:'출발 준비',1:'제국지도 이동 중',2:'도착 도시 하역 중',3:'거래 취소 처리 중',4:'연결 확인 대기'}[motion]
        # Goods already unloaded: the caravan is still in the destination city, but it carries
        # nothing. Show an empty marker (resource 0, quantity 0) until it leaves that city.
        delivered=motion==2 and (state=='finished' or t.get('cargo_delivered'))
        resource,quantity=(0,0) if delivered else (t['resource'],t['quantity'])
        if delivered:label='하역 완료 · 도착 도시를 떠나는 중'
        lines.extend([f"3 {s[0]} {d[0]} {resource} 0 {quantity} 0 {t['id']} {motion} {progress}",f"{s[1]} -> {d[1]}",f"육상 상단 · {label}",'빈 상단 / 클릭: 거래' if delivered else f"{t['quantity']}포대 / 클릭: 거래"])
    b.write_changed('empire-fleet.txt',str(len(lines)//4)+'\n'+'\n'.join(x.replace('\r',' ').replace('\n',' ') for x in lines)+'\n')
