"""Display only: dates derive from reported executed ticks, never drive the clock."""
import json
from city_labels import city_name
from pathlib import Path
START_YEAR=json.loads(Path(__file__).with_name('capua-tarentum.json').read_text())['start_year']
NAMES={'capua':'카푸아','tarentum':'타렌툼'}
def ping_label(slot):
 age=slot.get('contact_age_ms');rtt=slot.get('rtt_ms')
 if not slot.get('online') or slot.get('departed') or type(age)is not int or age>5000:return '연결 확인 중'
 return f'{rtt}ms' if type(rtt)is int and 0<=rtt<=120000 else '측정 중'

def lobby_ping(slot):
 """' 400ms' after a chosen city's state in the lobby (that player's round trip to the host), '' when there is no
 fresh measurement (offline, contact older than 5 s, not measured yet)."""
 label=ping_label(slot)
 return ' '+label if label.endswith('ms') else ''

def date_label(ticks,start=None):
 """`start`: the scenario's first year (rules.start_year; lobby_status 'start_year'), else -350."""
 months=ticks//800;year=(start if type(start)==int else START_YEAR)+months//12
 era='기원전' if year<0 else '서기'
 return f'{era} {abs(year)}년 {months%12+1}월'
def status_lines(state,saved):
 rows=[]
 labels={'active':'진행 응답 정상','stale':'게임 응답 없음','starting':'도시 입장 대기','lobby':'로비'}
 for slot in state['slots']:
  name=slot.get('city_name',city_name(slot['city']))+(' [방장]' if slot['city']==state['host_city'] else '')
  ticks=slot['ticks'];date=date_label(ticks,state.get('start_year')) if ticks is not None else '날짜 미수신'
  status=labels[slot['engine_state']]
  if slot.get('departed'):status='퇴장 / 저장 도시 보관'
  elif not slot['online']:status+=' / 연결 없음'
  rows.append(f'{name}: {date} / {status}')
 waiting=[s.get('city_name',city_name(s['city'])) for s in state['slots'] if not s.get('departed') and s['engine_state']!='active']
 if saved['pending']:reason='공동 저장 중 - 참가 도시 저장 완료 대기'
 elif not state['live_play']:reason='모든 참가자가 준비하면 시작할 수 있습니다.'
 elif waiting:reason='진행 대기: '+', '.join(waiting)+' 응답 대기'
 elif not state['target_speed']:reason='방장이 전체 정지 중입니다.'
 else:reason=f"{sum(not s.get('departed',False) for s in state['slots'])}개 도시 진행 중 / 방장 목표 {state['target_speed']}%"
 return [*rows,reason]
