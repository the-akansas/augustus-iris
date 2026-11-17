"""Host-decided cooperative goals, sampled at a shared tick without stopping city simulation.

This is a trusted-community protocol, not an anti-cheat authority. Completion is
durable once and never ends play. No stale/offline SAV contributes live metrics.
"""
from clock_policy import FRESH_SECONDS
import json
import secrets
import celebration
import delivery_goals
from coordinator import sha

INTERVAL = 400
METRICS = ('population','culture','prosperity','peace','favor','treasury')
LABELS = dict(population='인구',culture='문화',prosperity='번영',peace='평화',favor='지지도',treasury='자금')
MONTH = 800   # game ticks per month (throne_rules.TICKS_PER_MONTH)
# 기한 경쟁 (2026-11-15): rules {'population_total':0,'per_city':{},'race':{'stat','months'}} (scenario_pair). The same
# shared samples as the cooperative goals; the first complete sample at or after the deadline decides the winner
# (the most of 'stat'; a tie shares the win). Play goes on.
def race_deadline(rules):return rules['race']['months']*MONTH if rules.get('race') else None
def race_ranking(rules,reports):
 stat=rules['race']['stat'];return sorted(reports,key=lambda c:(-reports[c][stat],c))

def encode(value):
 return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))

def validate_rules(rules,cities):
 if rules is None:return
 if not isinstance(rules,dict) or (set(rules)-{'celebration','treasury_total','deliveries','race'})!={'population_total','per_city'}:raise ValueError('invalid objective rules')
 race=rules.get('race')
 if race is not None and (not isinstance(race,dict) or set(race)!={'stat','months'} or race['stat'] not in METRICS or type(race['months'])!=int or not 6<=race['months']<=600):raise ValueError('invalid race')
 if rules.get('celebration','notice') not in ('notice','video'):raise ValueError('invalid celebration')
 total=rules['population_total'];per=rules['per_city']
 money=rules.get('treasury_total',0)
 if type(money)!=int or not 0<=money<=1000000000:raise ValueError('invalid total treasury')
 if type(total)!=int or not 0<=total<=10000000 or not isinstance(per,dict) or not set(per)<=set(cities):raise ValueError('invalid objective targets')
 delivery_goals.validate(rules.get('deliveries',[]),cities)
 positive=bool(total or money or rules.get('deliveries') or race)
 for values in per.values():
  if not isinstance(values,dict) or not set(values)<=set(METRICS):raise ValueError('invalid city objectives')
  for key,value in values.items():
   maximum=1000000 if key=='population' else 1000000000 if key=='treasury' else 100
   if type(value)!=int or not 0<=value<=maximum:raise ValueError('invalid objective threshold')
   positive|=value>0
 if not positive:raise ValueError('empty cooperative objectives')

def initialize(db):
 celebration.initialize(db)
 delivery_goals.initialize(db)
 db.execute('CREATE TABLE IF NOT EXISTS objective_state(id INTEGER PRIMARY KEY,rules TEXT,run_id TEXT,completed_tick INTEGER,next_tick INTEGER,last_tick INTEGER,last_stats TEXT)')
 db.execute('CREATE TABLE IF NOT EXISTS objective_report(city TEXT PRIMARY KEY,ticks INTEGER,stats TEXT)')
 db.execute('CREATE TABLE IF NOT EXISTS joint_objectives(id INTEGER PRIMARY KEY,payload TEXT,hash TEXT)')
 if 'objective_version' not in {r[1] for r in db.execute('PRAGMA table_info(joint_save)')}:
  db.execute('ALTER TABLE joint_save ADD COLUMN objective_version INTEGER')

def configure(db,binding,origin=0):
 rules=binding.get('objectives');validate_rules(rules,binding['cities'])
 row=db.execute('SELECT rules FROM objective_state WHERE id=1').fetchone()
 if row:
  if json.loads(row[0])!=rules:raise ValueError('objective rules changed')
 elif rules is not None:
  db.execute('INSERT INTO objective_state VALUES(1,?,?,NULL,?,NULL,?)',(encode(rules),secrets.token_hex(16),origin,'{}'))
 db.commit()

def state(db):
 row=db.execute('SELECT * FROM objective_state WHERE id=1').fetchone()
 if not row:return None
 data=dict(version=1,rules=json.loads(row['rules']),run_id=row['run_id'],completed_tick=row['completed_tick'],next_tick=row['next_tick'],last_tick=row['last_tick'],last_stats=json.loads(row['last_stats']))
 if data['rules'].get('deliveries'):data.update(version=2,deliveries=delivery_goals.snapshot(db,data['rules']['deliveries']))
 return data

def required(rules,cities,left=()):
 """The cities a shared check needs. `left`: cities whose player left the room for good (departed): they are not
 waited for and not judged (user 2026-11-15: "나간도시를 빼고 판정해줘"). A delivery's two cities are still needed."""
 endpoints={g[k] for g in rules.get('deliveries',[]) for k in ('sender','receiver')}
 cities=[c for c in cities if c not in left or c in endpoints]
 return list(cities) if rules['population_total'] or rules.get('treasury_total',0) or rules.get('race') else [c for c in cities if c in endpoints or any(rules['per_city'].get(c,{}).values())]

def departed(room,db):
 """Cities whose player left the room (lobby_leave) and nobody has taken since. Not the seats nobody chose
 (dormant): those wait for a player as before."""
 import sqlite3
 try:
  left={r[0] for r in db.execute('SELECT city FROM lobby_invite WHERE city IS NOT NULL AND token IN (SELECT token FROM departed_invite)')}
  held={r[0] for r in db.execute('SELECT city FROM lobby_invite WHERE city IS NOT NULL AND token NOT IN (SELECT token FROM departed_invite)')}
 except sqlite3.OperationalError:return set()
 return left-held

def barrier(room,db):
 data=state(db)
 if not data or data['completed_tick'] is not None:return None
 needs=required(data['rules'],room.coordinator.scenario['cities'],departed(room,db))
 if not needs or not set(needs)<=set(room.active_cities(db)):
  # An absent required city suspends evaluation, not everybody else's game.
  if data['next_tick']<=room.grant:
   db.execute('UPDATE objective_state SET next_tick=? WHERE id=1',((room.grant//INTERVAL+1)*INTERVAL,));db.execute('DELETE FROM objective_report');db.commit()
  return None
 if data['next_tick']+INTERVAL<room.grant:
  db.execute('UPDATE objective_state SET next_tick=? WHERE id=1',((room.grant//INTERVAL+1)*INTERVAL,));db.execute('DELETE FROM objective_report');db.commit()
  return (room.grant//INTERVAL+1)*INTERVAL
 return data['next_tick']

def validate_stats(stats):
 if not isinstance(stats,dict) or set(stats)!=set(METRICS):raise ValueError('invalid objective stats')
 for key,value in stats.items():
  minimum=-2147483648 if key=='treasury' else 0
  maximum=100 if key in ('culture','prosperity','peace','favor') else 2147483647
  if type(value)!=int or not minimum<=value<=maximum:raise ValueError('invalid objective metric')

def submit(room,db,city,r):
 data=state(db)
 if not data:raise ValueError('objectives disabled')
 tick=r.get('ticks');stats=r.get('stats');validate_stats(stats)
 if type(tick)!=int or tick<0 or tick>=2**53:raise ValueError('invalid objective tick')
 if data['last_tick']==tick:
  # A city the check did not need (no goal of its own, or it came after a player left) reports the same sample
  # after the check is done: nothing to compare. It was refused as a conflicting retry (2026-11-15).
  if city in data['last_stats'] and data['last_stats'][city]!=stats:raise ValueError('conflicting objective retry')
  return status(room,db)
 if data['completed_tick'] is not None:return status(room,db)
 target=barrier(room,db)
 if not room.started or target is None or tick!=target or not tick<=room.progress.get(city,(-1,0))[0]<=room.grant:raise ValueError('wrong objective sample')
 needs=required(data['rules'],room.coordinator.scenario['cities'],departed(room,db))
 if city not in needs:return status(room,db)
 previous=db.execute('SELECT ticks,stats FROM objective_report WHERE city=?',(city,)).fetchone()
 if previous and (previous['ticks']!=tick or json.loads(previous['stats'])!=stats):raise ValueError('conflicting objective retry')
 db.execute('INSERT OR IGNORE INTO objective_report VALUES(?,?,?)',(city,tick,encode(stats)))
 reports={row['city']:json.loads(row['stats']) for row in db.execute('SELECT * FROM objective_report WHERE ticks=?',(tick,))}
 if set(reports)==set(needs) and all(tick<=room.progress.get(c,(-1,0))[0]<=room.grant and room.clock()-room.progress[c][1]<FRESH_SECONDS for c in needs):
  rules=data['rules'];met=not rules['population_total'] or sum(s['population'] for s in reports.values())>=rules['population_total']
  if rules.get('race'):met=tick>=race_deadline(rules)
  if rules.get('treasury_total',0) and sum(s['treasury'] for s in reports.values())<rules['treasury_total']:met=False
  for c,goals in rules['per_city'].items():
   if c not in reports:continue   # a city whose player left: not judged
   for metric,target in goals.items():
    if target and reports[c][metric]<target:met=False
  if rules.get('deliveries') and not delivery_goals.met(data['deliveries'],rules['deliveries']):met=False
  db.execute('UPDATE objective_state SET completed_tick=?,next_tick=?,last_tick=?,last_stats=? WHERE id=1',(tick if met else None,tick+INTERVAL,tick,encode(reports)))
  db.execute('DELETE FROM objective_report')
  if met:
   celebration.begin(room,db,data,room.grant)
   # State and all-player message become durable in the same SQLite commit.
   key='objective-complete:'+data['run_id']
   if not db.execute('SELECT 1 FROM notification_event WHERE key=?',(key,)).fetchone():
    if rules.get('race'):
     order=race_ranking(rules,reports);stat=rules['race']['stat'];best=reports[order[0]][stat]
     winners=[c for c in order if reports[c][stat]==best];names=room.coordinator.scenario.get('city_names',{})
     text='기한 경쟁이 끝났습니다. 승리: '+', '.join(names.get(c,c) for c in winners)+' ('+LABELS[stat]+' '+format(best,',')+'). 계속 도시를 건설할 수 있습니다.'
    else:text='공동 목표를 모두 달성했습니다! 계속 도시를 건설할 수 있습니다.'
    db.execute("INSERT INTO chat(city,message_id,text,sender) VALUES('system',?,?,?)",(key,text,'시스템'))
    db.execute('INSERT INTO notification_event VALUES(?)',(key,))
 db.commit()
 return status(room,db)

def status(room,db):
 data=state(db)
 if not data:return dict(mode='free-build')
 left=sorted(departed(room,db))
 missing=[] if data['completed_tick'] is not None else [c for c in required(data['rules'],room.coordinator.scenario['cities'],left) if c not in room.active_cities(db)]
 result=dict(mode='race' if data['rules'].get('race') else 'cooperative',run_id=data['run_id'],rules=data['rules'],completed_tick=data['completed_tick'],last_tick=data['last_tick'],stats=data['last_stats'],missing=missing,next_tick=data['next_tick'],left=left)
 if data['version']==2:result.update(deliveries=data['deliveries'],delivery_in_transit=delivery_goals.in_transit(db,data['rules']['deliveries']) if data['completed_tick'] is None else {})
 return result

def ready_to_capture(room,db,ticks):
 # Pending statistical samples never delay an explicit checkpoint.
 return True

def capture(db,sid):
 if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='objective_state'").fetchone():return
 data=state(db)
 if data is None:return
 # In-flight reports are not part of a checkpoint. Schedule a fresh round
 # after restore; completed metrics and delivery counters remain unchanged.
 saved_tick=db.execute('SELECT ticks FROM joint_save WHERE id=?',(sid,)).fetchone()[0]
 if data['completed_tick'] is None:
  data['next_tick']=max(data['next_tick'],saved_tick+INTERVAL)
 payload=encode(data)
 db.execute('INSERT INTO joint_objectives VALUES(?,?,?)',(sid,payload,sha(payload.encode())))
 db.execute('UPDATE joint_save SET objective_version=? WHERE id=?',(data['version'],sid))

def validate_snapshot(data,binding,ticks):
 rules=binding.get('objectives')
 if data is None:
  if rules is not None:raise ValueError('목표 진행 저장 정보가 누락되었습니다.')
  return
 if rules is None or not isinstance(data,dict) or set(data)!=({'version','rules','run_id','completed_tick','next_tick','last_tick','last_stats'} | ({'deliveries'} if rules.get('deliveries') else set())) or type(data['version'])!=int or data['version']!=(2 if rules.get('deliveries') else 1) or data['rules']!=rules:raise ValueError('목표 저장 규칙이 다릅니다.')
 validate_rules(data['rules'],binding['cities'])
 if rules.get('deliveries'):delivery_goals.validate_snapshot(data['deliveries'],rules['deliveries'])
 if not isinstance(data['run_id'],str) or len(data['run_id'])!=32 or any(c not in '0123456789abcdef' for c in data['run_id']):raise ValueError('목표 실행 식별자 오류')
 for key in ('completed_tick','last_tick'):
  value=data[key]
  if value is not None and (type(value)!=int or not 0<=value<=ticks):raise ValueError('목표 저장 시각 오류')
 if type(data['next_tick'])!=int or not 0<=data['next_tick']<2**53:raise ValueError('목표 검사 시각 오류')
 if data['next_tick']<ticks:
  # Completed goals never sample again; their old next_tick is harmless.
  if data['completed_tick'] is None:raise ValueError('목표 검사 시각 오류')
 stats=data['last_stats']
 if not isinstance(stats,dict) or not set(stats)<=set(binding['cities']):raise ValueError('목표 도시 정보 오류')
 if data['last_tick'] is None and stats:raise ValueError('검사하지 않은 목표 통계')
 for values in stats.values():validate_stats(values)
 # A check after a player left has no line for that city (required(..., left)); the delivery cities are always there.
 endpoints={g[k] for g in rules.get('deliveries',[]) for k in ('sender','receiver')}
 if data['last_tick'] is not None and (not stats or not set(stats)<=set(required(rules,binding['cities'])) or not endpoints<=set(stats)):raise ValueError('목표 통계 도시 누락')
 if data['completed_tick'] is not None and data['completed_tick']!=data['last_tick']:raise ValueError('목표 완료 시각 불일치')
 if data['completed_tick'] is not None:
  if rules.get('deliveries') and not delivery_goals.met(data['deliveries'],rules['deliveries']):raise ValueError('미완료 납품 목표의 완료 기록')
  if rules['population_total'] and sum(v['population'] for v in stats.values())<rules['population_total']:raise ValueError('완료 목표 통계 불일치')
  if rules.get('treasury_total',0) and sum(v['treasury'] for v in stats.values())<rules['treasury_total']:raise ValueError('완료 자금 목표 통계 불일치')
  if any(value and c in stats and stats[c][k]<value for c,values in rules['per_city'].items() for k,value in values.items()):raise ValueError('완료 도시 목표 통계 불일치')

def read(db,sid,binding):
 columns={r[1] for r in db.execute('PRAGMA table_info(joint_save)')}
 row=db.execute('SELECT ticks'+(',objective_version' if 'objective_version' in columns else '')+' FROM joint_save WHERE id=?',(sid,)).fetchone()
 version=row['objective_version'] if 'objective_version' in columns else None
 if version is None:
  validate_snapshot(None,binding,row['ticks']);return None
 if version not in (1,2):raise ValueError('지원하지 않는 목표 저장 버전입니다.')
 payload=db.execute('SELECT payload,hash FROM joint_objectives WHERE id=?',(sid,)).fetchone()
 if not payload or len(payload[0])>32768 or sha(payload[0].encode())!=payload[1]:raise ValueError('목표 저장 정보 검증 실패')
 data=json.loads(payload[0]);validate_snapshot(data,binding,row['ticks'])
 if data['version']!=version:raise ValueError('목표 저장 버전 불일치')
 return data

def restore(db,data,binding,ticks):
 validate_snapshot(data,binding,ticks)
 if data is None:return
 db.execute('DELETE FROM objective_state');db.execute('DELETE FROM objective_report');db.execute('DELETE FROM objective_delivery')
 if data['version']==2:delivery_goals.restore(db,data['deliveries'],data['rules']['deliveries'])
 db.execute('INSERT INTO objective_state VALUES(1,?,?,?,?,?,?)',(encode(data['rules']),data['run_id'],data['completed_tick'],data['next_tick'],data['last_tick'],encode(data['last_stats'])))
 if data['completed_tick'] is not None:
  db.execute('INSERT OR IGNORE INTO notification_event VALUES(?)',('objective-complete:'+data['run_id'],))

def lines(value,names,own_city=None,view='all'):
 if view not in ('all','mine','others','shared'):raise ValueError('invalid goal view')
 if value['mode']=='free-build':return '자유 건설: 승리 조건 없이 계속 플레이합니다.\n도시 수치와 납품 조건은 모두 비활성 상태입니다. 승리 판정을 하지 않습니다.'
 complete=value['completed_tick'] is not None
 rules=value['rules'];stats=value['stats'];missing=set(value.get('missing',[])) if not complete else set()
 if rules.get('race'):return race_lines(value,names,own_city)
 result=['공동 승리! 아래는 달성 당시의 기록입니다.' if complete else '도시 수치와 누적 납품 조건을 모두 충족하면 함께 승리합니다.']
 left=set(value.get('left',[])) if not complete else set()
 if left:result.append('나간 도시는 판정에서 뺍니다: '+', '.join(names.get(c,c) for c in sorted(left)))
 if missing:
  result.append('목표 판정 대기: '+', '.join(names.get(c,c) for c in sorted(missing)))
  result.append('담당자가 없는 필수 도시가 있습니다. 다른 도시는 계속 플레이할 수 있습니다.')
 if not complete and (rules.get('population_total') or rules.get('treasury_total') or any(any(g.values()) for g in rules['per_city'].values())):
  result.append('표시값은 최근 공동 검사 기록입니다. 실시간 수치와 차이가 있을 수 있습니다.' if stats else '첫 공동 검사를 기다리고 있습니다. 아직 수치가 없는 것은 0이 아닙니다.')
 def current_text(current):return format(current,',') if current is not None else '미확인'
 def progress(current,target,waiting=False):
  mark='담당자 대기' if waiting else '확인 중' if current is None else '조건 충족' if current>=target else '진행 중'
  return '['+mark+'] '+current_text(current)+' / '+format(target,',')
 if view in ('all','shared'):
  result.append('');result.append('[함께 달성할 목표]')
  count=0
  for key,metric,label,unit in [('population_total','population','참가 도시 인구 합계','명'),('treasury_total','treasury','참가 도시 현재 자금 합계',' 데나리')]:
   target=rules.get(key,0)
   if not target:continue
   count+=1;current=sum(s[metric] for s in stats.values()) if stats else None
   result.append(label+': '+progress(current,target,bool(missing))+unit)
   if missing and current is not None:result.append('이전 공동 검사 합계입니다. 담당자가 없는 도시의 저장 수치로 새로 판정하지 않습니다.')
  if not count:result.append('합계 목표는 없습니다. 아래 도시별 조건과 납품 과제를 확인하세요.')
 per=rules['per_city'];cities=list(per)
 if own_city in cities:cities.remove(own_city);cities.insert(0,own_city)
 selected=[c for c in cities if (view=='all' or view=='mine' and c==own_city or view=='others' and c!=own_city) and any(per[c].values())]
 if view in ('all','mine') and own_city and not any(per.get(own_city,{}).values()):
  result.extend(['','[내 도시: '+names.get(own_city,own_city)+']','이 도시에 별도로 지정된 수치 조건은 없습니다. 납품 역할과 전체 합계 목표를 확인하세요.'])
 for city in selected:
  result.extend(['','['+('내 도시: ' if city==own_city else '다른 도시: ')+names.get(city,city)+']'])
  waiting=city in missing
  if city in left:result.append('플레이어가 나가서 이 도시의 조건은 판정하지 않습니다.');continue
  for metric in METRICS:
   target=per[city].get(metric,0)
   if not target:continue
   current=stats.get(city,{}).get(metric);unit='명' if metric=='population' else ' 데나리' if metric=='treasury' else ''
   result.append(LABELS[metric]+': '+progress(current,target,waiting)+unit)
  if waiting:result.append('담당자 참여 후 판정을 재개합니다. 표시된 수치는 이전 검사 기록입니다.')
 if view=='others' and not selected:result.append('다른 도시에 별도로 지정된 수치 조건은 없습니다.')
 result.extend(delivery_goals.lines(value,names,own_city,view))
 if not complete:
  result.extend(['','도시 수치는 검사 시점의 현재 값입니다. 납품은 배송 완료량을 누적하며 소비해도 유지됩니다.','필수 도시 담당자가 모두 참여하고 전체 조건이 충족된 공동 검사 시점에 승리가 확정됩니다.'])
 return '\n'.join(result)

def race_lines(value,names,own_city=None):
 """The in-game goal text of a 기한 경쟁: the deadline, then the standing at the latest shared check."""
 rules=value['rules'];stat=rules['race']['stat'];stats=value['stats'];complete=value['completed_tick'] is not None
 result=['기한 경쟁 결과입니다. 아래는 마감 때의 기록입니다.' if complete else f"기한 경쟁: {rules['race']['months']}개월이 지났을 때 {LABELS[stat]} 값이 가장 높은 도시가 승리합니다."]
 missing=set(value.get('missing',[])) if not complete else set()
 if missing:result.append('판정 대기: '+', '.join(names.get(c,c) for c in sorted(missing))+' (담당자가 없는 도시)')
 left=set(value.get('left',[])) if not complete else set()
 if left:
  result.append('나간 도시는 판정에서 뺍니다: '+', '.join(names.get(c,c) for c in sorted(left)))
  stats={c:v for c,v in stats.items() if c not in left}
 if not stats:result.append('첫 공동 검사를 기다리고 있습니다.')
 else:
  order=race_ranking(rules,stats);unit='명' if stat=='population' else ' 데나리' if stat=='treasury' else ''
  result.append('');result.append('[순위 · 최근 공동 검사]' if not complete else '[최종 순위]')
  for i,c in enumerate(order):result.append(f"{i+1}위 {names.get(c,c)}{' (내 도시)' if c==own_city else ''}: {format(stats[c][stat],',')}{unit}")
 if not complete:result.extend(['','수치는 검사 시점의 현재 값입니다. 마감 뒤 첫 공동 검사에서 승리가 정해지고, 그 뒤에도 계속 플레이합니다.'])
 return '\n'.join(result)

def publish(bridge,value):
 own=bridge.client.city
 for view,suffix in [('all',''),('mine','-mine'),('others','-others'),('shared','-shared')]:
  bridge.write_changed('objective-status'+suffix+'.txt',lines(value,bridge.city_names,own,view))

def poll_bridge(bridge,clock,reported_ticks):
 target=clock.get('objective_tick')
 request=sha((bridge.config['session']+'|'+bridge.client.city+'|'+str(target)).encode()) if target is not None else ''
 bridge.write_changed('objective-snapshot.txt','' if target is None else str(target)+' '+request+'\n')
 path=bridge.root/'objective-stats.json'
 if target is None or reported_ticks<target or not path.is_file():return
 try:
  value=json.loads(path.read_text(encoding='utf8'))
 except (OSError,json.JSONDecodeError):return
 if isinstance(value,dict) and value.get('ticks')==target and value.get('request')==request:
  import time
  if time.monotonic()<getattr(bridge,'objective_retry_at',0):return
  try:result=bridge.client.call('objective_report',ticks=target,stats=value.get('stats'))
  except ValueError as error:
   # An automatic report, not something the player asked for. Right after the start (or while a required city is
   # still loading or away) the host has not opened this check yet and answers 'wrong objective sample'; the next
   # check point is used instead. Retry quietly after 2 s instead of showing "요청을 처리하지 못했습니다"
   # (user report 2026-11-13). Any other rejection is still shown.
   if str(error)!='wrong objective sample':raise
   bridge.objective_retry_at=time.monotonic()+2
   from network_diagnostics import record,ident
   record(bridge.root,'objective_sample_waiting',session=ident(bridge.config['session']),ticks=target,outcome='retry',reason='wrong objective sample')
   return
  bridge.objective_retry_at=0
  publish(bridge,result)
