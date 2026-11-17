"""Explain the shipped exercises using their actual starting setup and schedule."""
import json
from pathlib import Path

def lines(project, city):
    if project.get('id') not in ('city-events-example','city-invasions-example'):
        return []
    slot=next((s for s in project['slots'] if s['id']==city),None)
    if not slot:return []
    prepared=bool(slot.get('starting_setup'))
    result=['연습 안내: 주택 32채, 주민 160명, 도로와 저장 시설이 준비되어 있습니다. 밀 32포대와 도자기 20포대로 시작합니다. 승리 목표는 없습니다.' if prepared else '연습 안내: 빈 도시에서 시작합니다. 도로, 주택과 식량 공급부터 준비하세요. 승리 목표는 없습니다.']
    if prepared:
        result.append('도자기 공방과 광장 동상을 배치했습니다. 저장소에는 점토 8포대, 공방에는 점토 2포대가 있습니다. 건물을 오른쪽 클릭해 재고와 생산을 확인하세요.')
    if slot.get('events'):
        result.append('첫 납품 요청이 오면 황제 자문관에서 도자기를 보내세요. 준비된 재고는 연습용이므로 이후 식량과 물품 공급을 이어가세요.' if prepared else '도자기 요청에 대비해 점토 채취장, 도자기 공방과 저장소를 운영하세요.')
        for e in slot['events']:
            prefix=f"시작 후 {e['month']}개월: "
            if e['kind']=='grant':text=f"도시 자금 {e['amount']:,}데나리 지원."
            elif e['kind']=='favor':text=f"황제 지지도 {e['amount']:+d} 변동."
            elif e['kind']=='request':
                resource='도자기' if e['resource']==15 else f"물품 번호 {e['resource']}"
                text=f"{resource} {e['amount']}포대 납품 요청. 기한은 {e['deadline']}년입니다. 황제 자문관에서 요청을 확인하고 보내세요."
            else:continue
            result.append(prefix+text)
    if slot.get('invasions'):
        result.append('시작 화면의 두 요새에 투창병 16명과 군단병 16명이 정렬되어 있습니다. 군인 식당에는 밀 8포대를 준비했습니다. 요새를 선택해 부대를 이동하고 침략군을 막아 보세요. 병영과 군인 식당도 배치되어 있습니다.' if prepared else '병영과 요새를 지어 병사를 모집한 뒤 침략에 대비하세요.')
        for e in slot['invasions']:
            result.append(f"시작 후 {e['month']}개월에 규모 {e['amount']}의 침략이 설정되어 있습니다. 실제 적 수는 난이도에 따라 달라집니다. 준비한 부대로 방어하세요.")
    if slot.get('starting_setup')=='defense-town':
        result.append('군단 파견: 제국지도에서 상대 도시를 누른 뒤 군단 파견을 선택하세요. 요새에서 대기 중인 군단과 지원군 또는 공격군을 고르고 파견 확인을 누릅니다. 지원군은 적을 방어하고, 공격군은 상대 도시를 공격합니다.')
        result.append('파견 중인 군단 목록을 누르면 생존 병력이 귀환합니다. 이동 시 두 도시의 저장을 준비하며 잠시 기다립니다. 상대 도시에 방문군이 있으면 먼저 귀환시켜야 합니다.')
    result.append('이 안내는 메시지함의 채팅 기록에서 다시 볼 수 있습니다. 제작기에서 이 시나리오를 열면 도시별 이벤트와 침략 시점을 바꿀 수 있습니다.')
    return result

def publish(room,db,city):
    path=Path(room.coordinator.path).parent/'scenario-project.json'
    if not path.is_file():return
    project=json.loads(path.read_text(encoding='utf8'))
    for i,text in enumerate(lines(project,city)):
        room.system_chat(db,text,targets=(city,city),key=f'briefing:{city}:{i}')

def start_message(project, city):
    """The authored start message for `city`: the common text, then the city's own text (scenario_project
    validate_start_message). None when there is nothing to show. The id changes with the text, the scenario and the
    city, so the game shows each text once (custom message uid 'mpstart:<id>', kept in the save)."""
    import hashlib
    m=project.get('start_message') or {}
    parts=[v.replace('\r\n','\n').replace('\r','\n').strip() for v in (m.get('common',''),(m.get('per_city') or {}).get(city,''))]
    body='\n\n'.join(p for p in parts if p)
    if not body:return None
    ident=hashlib.sha256(json.dumps([project.get('id'),project.get('revision'),city,body],ensure_ascii=False).encode('utf8')).hexdigest()[:32]
    return dict(id=ident,title=project.get('title',''),body=body)

def start_message_for(room, city):
    path=Path(room.coordinator.path).parent/'scenario-project.json'
    try:return start_message(json.loads(path.read_text(encoding='utf8')),city)
    except (OSError,ValueError):return None

def start_message_file(message):
    """Bridge file start-message.txt: one line 'id<TAB>title<TAB>body'. The body is the game's rich text: an author's
    '@' cannot start a command (it is dropped), a line break is '@L', an empty line a paragraph '@P'."""
    if not isinstance(message,dict) or not isinstance(message.get('id'),str) or len(message['id'])!=32:return ''
    def one(v):return ' '.join(str(v).replace('@',' ').replace('\t',' ').split())
    paragraphs=[p for p in str(message.get('body','')).replace('\r','').split('\n\n') if p.strip()]
    body='@P'.join('@L'.join(one(l) for l in p.split('\n') if l.strip()) for p in paragraphs)
    return f"{message['id']}\t{one(message.get('title',''))}\t{body}\n" if body else ''
