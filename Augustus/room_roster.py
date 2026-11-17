"""Freeze a new room's roster, build verified native saves off-thread, then publish atomically."""
import copy,json,threading,uuid
from pathlib import Path
from coordinator import sha
from multiplayer_limits import MAX_ONLINE_PLAYERS

def effective_project(manifest,participants,legacy_neutral=False):
 from scenario_project import validate
 from creator_presets import catalog
 data=copy.deepcopy(manifest);keep=set(participants)
 if not 1<=len(keep)<=MAX_ONLINE_PLAYERS or not keep<={s['id'] for s in data['slots']}:raise ValueError('participant required')
 if len(keep)==1 and data['schema']==1:raise ValueError('legacy solo unsupported')
 from scenario_project import min_players
 if len(keep)<min_players(data):raise ValueError('needs players %d'%min_players(data))   # the author's minimum (lobby.py refuses the start first)
 endpoints={g[k] for g in data['rules'].get('objectives',{}).get('deliveries',[]) for k in ('sender','receiver')}
 if not endpoints<=keep:raise ValueError('납품 과제에 필요한 도시는 삭제할 수 없습니다. 담당자 대기 도시로 보존해야 합니다.')
 removed=[s for s in data['slots'] if s['id'] not in keep]
 data['slots']=[s for s in data['slots'] if s['id'] in keep]
 neutral={c['name_id']:c for c in catalog()['neutral']}
 for c in data['empire']['cities']:
  if any(s['name_id']==c['name_id'] for s in removed):
   c['role']='npc';preset=neutral.get(c['name_id'])
   for field in ('sea','cost','sells','buys'):c[field]=copy.deepcopy(preset[field] if preset else {} if field in ('sells','buys') else 0)
   if 'enabled' in c:c['enabled']=True
   c.pop('trade_players',None)
   # A player city keeps the neutral trade it had before a seat took it ('parked_trade', scenario editor). The city
   # is neutral now, and the file allows that record on player cities only: with it every scenario made from the
   # free-build map refused to start with fewer players than seats ('invalid_request', user 2026-11-14).
   c.pop('parked_trade',None)
   if not legacy_neutral and data['schema']>=4:
    c.update(reserved=True,sea=0,cost=0,sells={},buys={},trade_players=[])
  if 'trade_players' in c:c['trade_players']=[p for p in c['trade_players'] if p in keep]
 # Trade exceptions between two seats (rules.player_trade): one that names a seat nobody took goes with it (2026-11-15;
 # it made the file invalid, so such a scenario could not start with fewer players than seats).
 trade=data['rules'].get('player_trade')
 if trade:trade['exceptions']=[r for r in trade['exceptions'] if set(r['between'])<=keep]
 message=data.get('start_message')
 if message and 'per_city' in message:message['per_city']={c:v for c,v in message['per_city'].items() if c in keep}   # a city that left has no reader
 goals=data['rules'].get('objectives')
 if goals:
  goals['per_city']={c:g for c,g in goals['per_city'].items() if c in keep}
  # Totals the author set for this number of players (scenario_project.validate_objectives 'by_players'). The frozen
  # roster carries plain totals only, so the table leaves with the cities that left.
  table=goals.pop('by_players',None)
  if removed and table and str(len(keep)) in table:
   for key,value in table[str(len(keep))].items():goals[key]=value
  if not(goals.get('deliveries') or goals['population_total'] or goals.get('treasury_total',0) or any(any(g.values()) for g in goals['per_city'].values())):
   data['rules']['mode']='free-build';data['rules'].pop('objectives')
 return validate(data),removed

def begin(room,db,participants):
 if getattr(room,'roster_job',None):return
 root=Path(room.coordinator.path).parent
 manifest=json.loads((root/'scenario-project.json').read_text(encoding='utf8'))
 if (root/'restored-from.json').exists() or manifest['rules'].get('objectives',{}).get('deliveries'):
  # Keep every saved city and its original snapshot; only assigned cities tick.
  set_dormant(room,db,participants)
  room.start_at=room.clock()+5;room.start_step=None
  return
 if db.execute('SELECT 1 FROM live_transfer').fetchone():raise ValueError('transaction pending')
 manifest=json.loads((root/'scenario-project.json').read_text(encoding='utf8'))
 effective,removed=effective_project(manifest,participants)
 cache=Path(__file__).resolve().parent/'roster-cache';cache.mkdir(exist_ok=True)
 job=dict(participants=list(participants),project=effective,removed=removed,result=None,error=None,stage=str(cache/uuid.uuid4().hex))
 room.roster_job=job
 room.system_chat(db,'참가하지 않은 도시를 중립도시로 전환합니다. 지도를 준비하는 동안 잠시 기다려 주세요.')
 def build():
  try:
   from scenario_pair import load_pair,verify_city
   from scenario_project import write_layout
   from city_client import Engine,game_data
   stage=Path(job['stage']);stage.mkdir();write_layout(effective,stage)
   preset,binding=load_pair(game_data(),effective);parts={}
   for city in binding['cities']:
    out=stage/city;parts[city]=Engine().run('start-'+city,stage,out);verify_city(out,city,preset)
   job['result']=(binding,parts)
  except Exception as e:
   job['error']=str(e)
   (root/'roster-error.txt').write_text(str(e),encoding='utf8')
 thread=threading.Thread(target=build,daemon=True);job['thread']=thread;thread.start()

def poll(room,db):
 job=getattr(room,'roster_job',None)
 if not job:return
 if job['error']:
  room.roster_job=None;room.system_chat(db,'도시 준비를 마치지 못했습니다. 원본 저장은 유지됩니다. '+job['error']);return
 if job['result'] is None:return
 selected=job['participants'];now=room.clock();host=db.execute('SELECT city FROM lobby_invite ORDER BY rowid LIMIT 1').fetchone()[0]
 if db.execute('SELECT 1 FROM room_closed').fetchone() or any(now-room.presence.get(c,(-1e30,False))[0]>=30 for c in selected):
  room.roster_job=None;room.system_chat(db,'시작 취소: 참가자의 연결이 끊겼습니다. 다시 시작해 주세요.');return
 co=room.coordinator;binding,parts=job['result'];root=Path(co.path).parent
 source=root/'scenario-project.json';original=source.read_bytes();backup=root/'scenario-before-neutral.json'
 if not backup.exists():backup.write_bytes(original)
 if db.execute('SELECT 1 FROM expedition_required').fetchone():
  room.roster_job=None;room.system_chat(db,'파견 기록이 있는 방은 도시 구성을 변경할 수 없습니다.');return
 previous=co.scenario
 try:
  db.execute('BEGIN IMMEDIATE')
  # Before first play, only initial checkpoints exist. Replace them as one set.
  for table in ('joint_expedition','joint_part','joint_transport','joint_objectives','joint_provenance','joint_save','objective_report','objective_state','succession','play_session'):
   db.execute('DELETE FROM '+table)
  for c in previous['cities']:
   if c not in binding['cities']:db.execute('DELETE FROM city WHERE id=?',(c,))
  for c,(sav,rec) in parts.items():db.execute('UPDATE city SET save=?,receipt=?,active=NULL WHERE id=?',(sav,rec,c))
  db.execute('INSERT OR IGNORE INTO departed_invite SELECT token FROM lobby_invite WHERE city IS NULL')
  db.execute('DELETE FROM lobby_invite WHERE city IS NULL')
  db.execute('UPDATE scenario_binding SET value=?',(json.dumps(binding,sort_keys=True,separators=(',',':')),))
  # Race for the Throne with empty seats (2026-11-14; refused until then, so a six-seat throne scenario could only
  # start with six players). Nothing has been played yet: the record must be the untouched one made with the room.
  # It is made again for the cities that play. A record with any activity is never replaced.
  import throne_state
  if throne_state.spec(binding) is not None:
   throne_state.initialize(db);state=throne_state.current(db,previous)
   if state is None or state['activated_tick'] is not None or state['ended'] or state['notices'] or any(p['stage'] or p['eliminated'] for p in state['players'].values()):
    raise ValueError('황위 기록이 이미 진행된 방은 참가 도시를 바꿀 수 없습니다.')
   for table in ('joint_throne','joint_throne_secret','throne_custody'):db.execute('DELETE FROM '+table)
   throne_state.store(db,throne_state.initial(binding,state['origin_tick']),binding)
  # 황제의 순행: nothing has been played yet either; the record is made again for the cities that play.
  import imperial_progress
  if imperial_progress.spec(binding) is not None:
   imperial_progress.initialize(db);db.execute('DELETE FROM progress_state');db.execute('DELETE FROM joint_progress')
   imperial_progress.store(db,imperial_progress.initial(binding,room.origin),binding)
  # Project file is derived from this committed copy for checkpoint restoration.
  db.execute('CREATE TABLE IF NOT EXISTS runtime_project(value TEXT)');db.execute('DELETE FROM runtime_project');db.execute('INSERT INTO runtime_project VALUES(?)',(json.dumps(job['project'],ensure_ascii=False),))
  source.write_text(json.dumps(job['project'],ensure_ascii=False,indent=2),encoding='utf8')
  db.commit();co.scenario=binding
 except Exception:
  db.rollback();source.write_bytes(original);co.scenario=previous;room.roster_job=None;raise
 import objectives,migration
 if job.get('expansion'):
  from restore_expansion import restore_goals
  restore_goals(room,db,binding)
 else:objectives.configure(db,binding,room.origin)
 set_dormant(room,db,selected)
 migration.baseline(room)
 room.roster_job=None;room.roster_fixed=True
 if job.get('expansion'):room.restore_expansion=None
 names=[previous.get('city_names',{}).get(s['id'],s['id']) for s in job['removed']]
 room.system_chat(db,('저장 도시와 새 도시 준비 완료. ' if job.get('expansion') else '중립도시 전환 완료: '+', '.join(names)+'. ')+str(len(selected))+'명이 플레이합니다.')
 if not job.get('expansion'):
  before=(previous.get('objectives') or {});after=(binding.get('objectives') or {})
  changed=[(label,after.get(key,0)) for key,label in (('population_total','전체 인구'),('treasury_total','전체 도시 자금')) if before.get(key,0)!=after.get(key,0)]
  if changed:room.system_chat(db,'도시별 목표는 참가 도시만 적용합니다. '+str(len(selected))+'명 기준 목표로 조정했습니다: '+', '.join(label+' '+format(value,',') for label,value in changed)+'.')
  else:room.system_chat(db,'도시별 목표는 참가 도시만 적용합니다. 전체 인구·자금 합계 목표 수치는 유지됩니다.')
 room.start_at=room.clock()+5;room.start_step=None


def set_dormant(room,db,participants):
 selected=set(participants)
 dormant=[c for c in room.coordinator.scenario['cities'] if c not in selected]
 db.execute('DELETE FROM dormant_city')
 db.executemany('INSERT INTO dormant_city VALUES(?)',[(c,) for c in dormant]);db.commit()
 if dormant:
  room.system_chat(db,'담당자 없는 도시는 진행 상태를 보존합니다. 다음 이어하기에서 선택할 수 있습니다.')
