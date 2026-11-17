"""Race for the Throne persistence. No economy, emperor or battle mutations (those rules are undecided).

All times are absolute executed game ticks (800 per month). SQL transactions are
owned by the existing lobby/save caller. Missing enabled-mode data fails closed.

State format 2. Every per-player value is either public or private to that player:

  public (everyone: status, joint save, host-backup replica)
      rules/spec, ticks, activated_tick (the paranoia display is on), notices (anonymous coup notices),
      per player: stage (the public coup rank), eliminated, winner/ended
  private (only that player and the host that judges)
      per player 'secret': paranoia, failures, next_cost, next_attempt_tick, gift_total, gift_bonus,
      the throne expedition (the emperor's punitive expedition against this player: phase, number, deadline,
      result; step_raids), attempts (request id, notice id, tick, state)

  live state (host room DB, table throne_state): players hold 'secret', or 'pending' when a restore from a
      backup has not yet received that player's own record (see below).
  joint save (host room DB): joint_throne holds the SEALED form - public values plus, per player, a hash
      commitment 'sealed' = {commit, tick}; joint_throne_secret (host DB only) holds each secret and its nonce.
  host-backup replica (other players' PCs): the sealed form only. No secret, no nonce.
  each player's own PC: its own opening (secret + nonce) for each joint save, fetched from the host.

  commit = SHA-256(domain, nonce (32 random bytes, new at every save for every player), city, tick, secret).
  Without the nonce the commitment says nothing about the secret; with a different secret it does not match.
  A restore from the host's own room DB is complete at once. A restore from a replica marks every player
  'pending' until that player hands in its own opening; it is accepted only if it matches the commitment.

Trust: the host process judges and sees every secret (as it does every city's save). A participant who is not
the host never receives another player's secret. A new host sees the secrets that are handed to it.
"""
import copy,json,hashlib,secrets as _random
from coordinator import sha
import throne_rules

MAX_TICK=2**53-1
VERSION=2
PHASES=('idle','preparing','arrived','fighting','resolved','cooldown')
# How an expedition ended. 'tribute': paid, the legions withdrew. 'defeated': the player beat or routed them.
# 'sacked' (2026-11-14): neither within the siege time; they plundered and withdrew, paranoia unchanged.
# 'called_off': the trial ended while it was under way. 'city_lost': kept from the first format, never produced.
RAID_RESULTS=(None,'tribute','defeated','city_lost','sacked','called_off')
DEFAULT_RULES=dict(version=1,stages=[
 dict(name='비밀 조직 결성',cost=5000,chance=70,cap=90,floor=15,tribute=5000),
 dict(name='원로원 매수',cost=10000,chance=60,cap=90,floor=30,tribute=8000),
 dict(name='근위대 포섭',cost=20000,chance=50,cap=90,floor=45,tribute=12000),
 dict(name='황궁 내부 장악',cost=40000,chance=40,cap=90,floor=65,tribute=18000),
 dict(name='황제 폐위',cost=80000,chance=30,cap=90,floor=65,tribute=18000)],
 attempt_months=2,failure_percent=25,failure_cap_multiplier=3,cost_rounding=100,
 monthly_paranoia=5,gift_per_point=200,gift_step=200,ranking_months=2,ranking_bonuses=[20,8],
 preparation_months=3,response_months=1,cooldown_months=2,tribute_reduction=80,victory_reduction=25,
 initial_tribute=3000,army_initial=64,army_increment=16,army_cap=128)
PUBLIC_PLAYER=('stage','eliminated')
SECRET_FIELDS=('paranoia','failures','next_cost','next_attempt_tick','gift_total','gift_bonus','expedition','attempts')
# 황위 시험 규칙 v1 (rule format 2, throne_rules.py): each player's own spends (coup funding, gifts) are private too.
SPEND_FIELDS=('request','kind','tick','amount','stage','chance','roll','points','state','result','done','seq')
# Spend states. 'charging': the debit is staged/under way, nothing else changed. 'done': taken, effect applied once.
# 'void': not taken, no effect. After the trial ended (someone's final success was settled first), a spend whose
# effect was not settled yet never takes effect: 'cancelled' (not taken), 'refunding' (taken; the same amount is
# being paid back by the city's own refund command), 'refunded' (the refund receipt confirmed it).
SPEND_STATES=('charging','done','void','cancelled','refunding','refunded')
ENDED_STATES=('cancelled','refunding','refunded')
# 'heard' (test rules): how many public 'coup_failed' notices this record has already taken its +failure_paranoia from.
# A record the host could not see (restore-pending) takes the ones it missed when it is handed in (hear()).
def secret_fields(rules):return SECRET_FIELDS+(('spends','heard') if throne_rules.is_test(rules) else ())
ATTEMPT_STATES=('started',)
COMMIT_DOMAIN=b'augustus-throne-secret-v2\x00'

def defaults():return copy.deepcopy(DEFAULT_RULES)
def encode(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def exact(value,fields,label):
 if not isinstance(value,dict) or set(value)!=set(fields):raise ValueError('황위 '+label+' 필드 오류')
def integer(value,low,high,label):
 if type(value)is not int or not low<=value<=high:raise ValueError('황위 '+label+' 범위 오류')
def boolean(value,label):
 if type(value)is not bool:raise ValueError('황위 '+label+' 형식 오류')
def hex32(value,label):
 if not isinstance(value,str) or len(value)!=32 or any(c not in '0123456789abcdef' for c in value):raise ValueError('황위 '+label+' 형식 오류')
# Public notices. 'coup_attempt': rule format 1 (every attempt). Test rules (2026-11-13, user): the first coup ever
# ('coup_first', popup) and a stage-4 success ('final_stage', popup) are announced with the confirm-and-close message;
# a failure ('coup_failed') and the end ('throne_taken') only as a fanfare line in the notice tab; any other success
# is not announced. None names a player.
# 2026-11-14 (confirmed plan): when the very first coup fails, one notice says both ('coup_first_failed').
NOTICE_KINDS=('coup_attempt','coup_first','coup_failed','final_stage','throne_taken','coup_first_failed')
FAILURE_KINDS=('coup_failed','coup_first_failed')
def notice_id(request,kind='coup_attempt'):
 """Public id of one notice about one attempt. Derived from the private request id (random, known only to the
 attempting player and the host): a re-run of the same request after a restore gives the same notice."""
 if kind=='coup_attempt':return hashlib.sha256(b'augustus-throne-notice\x00'+request.encode()).hexdigest()[:32]
 return hashlib.sha256(b'augustus-throne-notice\x00'+request.encode()+b'\x00'+kind.encode()).hexdigest()[:32]
def notice_ids(request):return {notice_id(request,k) for k in NOTICE_KINDS}
def failures_announced(value):return sum(1 for n in value['notices'] if n['kind'] in FAILURE_KINDS)

def hear(value):
 """Test rules: every known record takes +failure_paranoia (up to the maximum) for each announced failure it has not
 taken yet. Restore-pending records are skipped and catch up when handed in. Returns True when anything changed."""
 if value is None or not throne_rules.is_test(value['spec']['rules']):return False
 rules=value['spec']['rules'];total=failures_announced(value);changed=False
 for p in value['players'].values():
  s=p.get('secret')
  if s is not None and s['heard']<total:
   s['paranoia']=min(rules['paranoia_max'],s['paranoia']+(total-s['heard'])*rules['failure_paranoia']);s['heard']=total;changed=True
 return changed

def validate_rules(rules):
 if throne_rules.is_test(rules):return throne_rules.validate(rules)
 exact(rules,DEFAULT_RULES,'규칙')
 integer(rules['version'],1,1,'규칙 버전')
 stages=rules['stages']
 if not isinstance(stages,list) or not 1<=len(stages)<=20:raise ValueError('황위 단계 수 오류')
 floor=0
 for s in stages:
  exact(s,DEFAULT_RULES['stages'][0],'단계')
  if not isinstance(s['name'],str) or not 1<=len(s['name'])<=80 or any(ord(c)<32 for c in s['name']):raise ValueError('황위 단계 이름 오류')
  integer(s['cost'],100,100000000,'지원금');integer(s['chance'],1,100,'성공률');integer(s['cap'],s['chance'],100,'상한')
  integer(s['floor'],floor,99,'최소 의심');floor=s['floor'];integer(s['tribute'],1,100000000,'공물')
 for k in ('attempt_months','ranking_months','preparation_months','response_months','cooldown_months'):integer(rules[k],1,120,k)
 for k in ('monthly_paranoia','tribute_reduction','victory_reduction'):integer(rules[k],1,100,k)
 for k in ('gift_per_point','gift_step','initial_tribute'):integer(rules[k],1,100000000,k)
 integer(rules['failure_percent'],0,100,'실패 인상률');integer(rules['failure_cap_multiplier'],1,10,'실패 상한');integer(rules['cost_rounding'],1,10000,'금액 단위')
 for k in ('army_initial','army_increment','army_cap'):integer(rules[k],1,10000,k)
 if rules['army_cap']<rules['army_initial']:raise ValueError('황위 병력 상한 오류')
 if not isinstance(rules['ranking_bonuses'],list) or len(rules['ranking_bonuses'])!=2:raise ValueError('황위 순위 보너스 오류')
 for v in rules['ranking_bonuses']:integer(v,0,99,'순위 보너스')
 if rules['ranking_bonuses'][0]<rules['ranking_bonuses'][1]:raise ValueError('황위 순위 보너스 순서 오류')
 return rules

def validate_spec(spec,cities):
 if not isinstance(cities,list) or not cities or any(not isinstance(c,str) or not c for c in cities) or len(set(cities))!=len(cities):raise ValueError('황위 참가 도시 목록 오류')
 exact(spec,('rules','rome'),'시나리오')
 validate_rules(spec['rules']);rome=spec['rome'];exact(rome,('id','x','y'),'로마')
 if rome['id']!='rome' or 'rome' in cities:raise ValueError('로마는 참가 슬롯과 별개여야 합니다.')
 integer(rome['x'],16,1984,'로마 x');integer(rome['y'],16,984,'로마 y')
 return spec

def spec(binding):
 value=binding.get('throne')
 if value is not None:validate_spec(value,binding['cities'])
 return value

def fresh_secret(rules,tick):
 s=dict(paranoia=0,failures=0,next_cost=rules['stages'][0]['cost'],next_attempt_tick=tick,gift_total=0,gift_bonus=0,
  expedition=dict(phase='idle',id=0,count=0,deadline_tick=None,tribute_paid=False,result=None),attempts=[])
 if throne_rules.is_test(rules):s['spends']=[];s['heard']=0
 return s

def initial(binding,tick=0):
 rules=spec(binding)
 if rules is None:return None
 integer(tick,0,MAX_TICK,'시작 틱')
 return dict(version=VERSION,spec=copy.deepcopy(rules),spec_hash=sha(encode(rules).encode()),origin_tick=tick,last_tick=tick,
  activated_tick=None,period_start_tick=None,winner=None,ended=False,notices=[],
  players={c:dict(stage=0,eliminated=False,secret=fresh_secret(rules['rules'],tick)) for c in sorted(binding['cities'])})

def expected_cost(rules,stage,failures):
 if throne_rules.is_test(rules):return throne_rules.min_cost(rules,stage,failures)
 if stage==len(rules['stages']):return 0
 cost=rules['stages'][stage]['cost'];cap=cost*rules['failure_cap_multiplier'];step=rules['cost_rounding']
 for _ in range(min(failures,10000)):
  updated=min(cap,((cost*(100+rules['failure_percent'])+100*step-1)//(100*step))*step)
  if updated==cost:break
  cost=updated
 return cost

# ---- commitments ------------------------------------------------------------------------------------------
def commit(city,tick,secret,nonce):
 if not isinstance(nonce,str) or len(nonce)!=64 or any(c not in '0123456789abcdef' for c in nonce):raise ValueError('황위 봉인값 형식 오류')
 body=encode(dict(city=city,tick=tick,secret=secret)).encode()
 return hashlib.sha256(COMMIT_DOMAIN+bytes.fromhex(nonce)+body).hexdigest()

# ---- validation ---------------------------------------------------------------------------------------------
def _validate_spends(s,rules,stage,origin,last,active):
 """A player's own coup funding and gifts (test rules). 'charging': the city's funds are being taken by the host's
 one-sided debit command; nothing else has changed yet. 'done': taken, effect applied once. 'void': not taken
 (not enough funds, or the city left before it happened), no effect."""
 spends=s['spends']
 if not isinstance(spends,list) or len(spends)>100000:raise ValueError('황위 지출 기록 오류')
 seen=set();seqs=set();charging=0;n=len(rules['stages'])
 for e in spends:
  exact(e,SPEND_FIELDS,'지출');hex32(e['request'],'지출 요청 번호')
  if e['request'] in seen:raise ValueError('황위 지출 요청 중복')
  seen.add(e['request'])
  integer(e['seq'],0,2**63-1,'지출 접수 순번')
  if e['seq'] in seqs:raise ValueError('황위 지출 접수 순번 중복')
  seqs.add(e['seq'])
  if e['kind'] not in ('coup','gift','tribute') or e['state'] not in SPEND_STATES:raise ValueError('황위 지출 종류 오류')
  integer(e['tick'],origin,last,'지출 시각');integer(e['amount'],1,rules['max_spend'],'지출 금액');integer(e['stage'],0,n-1 if e['kind']=='coup' else n,'지출 단계')
  integer(e['chance'],0,10000,'성공률');integer(e['roll'],0,9999,'추첨');integer(e['points'],0,rules['paranoia_max'],'감소량')
  if e['kind']=='gift' and (e['chance'] or e['roll'] or not e['points']):raise ValueError('황위 선물 기록 오류')
  if e['kind']=='tribute' and (e['chance'] or e['roll'] or 'expedition' not in rules):raise ValueError('황위 공물 기록 오류')
  if e['kind']=='coup' and (e['points'] or not e['chance']):raise ValueError('황위 쿠데타 기록 오류')
  if e['state']=='charging':
   charging+=1
   if e['result'] is not None or e['done'] is not None:raise ValueError('황위 처리 중 지출 오류')
  elif e['state']=='void':
   if e['result']!='void':raise ValueError('황위 무효 지출 오류')
   integer(e['done'],e['tick'],last,'무효 시각')
  elif e['state'] in ENDED_STATES:
   # The kept draw (audit, resend protection) is never applied: no result, stage, paranoia, failure or wait from it.
   if e['result']!='ended':raise ValueError('황위 종료 취소 지출 오류')
   integer(e['done'],e['tick'],last,'취소 시각')
  else:
   integer(e['done'],e['tick'],last,'처리 시각')
   want=('success' if e['roll']<e['chance'] else 'failure') if e['kind']=='coup' else 'withdrawn' if e['kind']=='tribute' else 'reduced'
   if e['result']!=want:raise ValueError('황위 지출 결과 불일치')
 if charging>1:raise ValueError('황위 지출은 한 번에 하나만 처리합니다.')
 if not active and any(e['state']=='done' for e in spends):raise ValueError('평화 시기 황위 지출 오류')

def _validate_secret(city,s,rules,stage,origin,last,active=None):
 exact(s,secret_fields(rules),'비공개 상태')
 test=throne_rules.is_test(rules)
 integer(s['paranoia'],0,100,'의심');integer(s['failures'],0,10000,'실패 수')
 integer(s['gift_total'],0,2**63-1,'회유금');integer(s['gift_bonus'],0,0 if test else max(rules['ranking_bonuses']),'보너스')
 integer(s['next_attempt_tick'],origin,MAX_TICK,'다음 도전');integer(s['next_cost'],0,1000000000,'다음 비용')
 if test and not throne_rules.reachable(rules,stage,s['failures']):raise ValueError('황위 실패 횟수 오류(지원금 한도를 넘은 뒤에는 실패가 늘 수 없습니다)')
 if s['next_cost']!=expected_cost(rules,stage,s['failures']):raise ValueError('황위 다음 도전 비용 불일치')
 if test:
  # gift_bonus (old rank bonus) stays in the record for compatibility and is always 0 here.
  if active and s['paranoia']<throne_rules.gift_floor(rules,stage):raise ValueError('황위 최소 의심 위반')
  if s['attempts']:raise ValueError('시험 규칙은 지출 기록(spends)만 씁니다.')
  integer(s['heard'],0,100000,'실패 알림 반영 수')
  _validate_spends(s,rules,stage,origin,last,active)
 minimum=0 if test else max(0,(rules['stages'][stage-1]['floor'] if stage else 0)-s['gift_bonus'])
 if s['paranoia']<minimum:raise ValueError('황위 최소 의심 위반')
 e=s['expedition'];exact(e,('phase','id','count','deadline_tick','tribute_paid','result'),'원정')
 if e['phase'] not in PHASES:raise ValueError('황위 원정 단계 오류')
 integer(e['id'],0,MAX_TICK,'원정 ID');integer(e['count'],0,1000000,'원정 횟수');boolean(e['tribute_paid'],'공물 지급')
 if e['result'] not in RAID_RESULTS:raise ValueError('황위 원정 결과 오류')
 if e['deadline_tick'] is not None:integer(e['deadline_tick'],origin,MAX_TICK,'원정 시각')
 if e['phase'] in ('preparing','arrived','cooldown') and e['deadline_tick'] is None:raise ValueError('황위 원정 기한 누락')
 if e['phase']!='idle' and (not e['id'] or not e['count']):raise ValueError('황위 원정 식별 누락')
 if e['tribute_paid']!=(e['result']=='tribute'):raise ValueError('황위 공물 결과 불일치')
 if e['phase'] in ('resolved','cooldown') and e['result'] is None:raise ValueError('황위 해결 결과 누락')
 if e['phase'] in ('preparing','arrived','fighting') and e['result'] is not None:raise ValueError('미해결 원정의 결과 오류')
 if test and e['phase']=='fighting' and e['deadline_tick'] is None:raise ValueError('황위 원정 기한 누락')
 if test and e['phase']!='idle' and 'expedition' not in rules:raise ValueError('원정 규칙이 없는 황위 원정 기록')
 if not isinstance(s['attempts'],list) or len(s['attempts'])>100000:raise ValueError('황위 시도 기록 오류')
 for a in s['attempts']:
  exact(a,('request','notice','tick','state'),'시도');hex32(a['request'],'요청 번호');integer(a['tick'],origin,last,'시도 시각')
  if a['notice']!=notice_id(a['request']) or a['state'] not in ATTEMPT_STATES:raise ValueError('황위 시도 기록 오류')

def _validate_globals(value,binding,players_shape):
 authored=spec(binding)
 exact(value,('version','spec','spec_hash','origin_tick','last_tick','activated_tick','period_start_tick','winner','ended','notices','players'),'상태')
 if value['version']!=VERSION:raise ValueError('지원하지 않는 황위 상태 형식입니다.')
 validate_spec(value['spec'],binding['cities'])
 if value['spec']!=authored or value['spec_hash']!=sha(encode(authored).encode()):raise ValueError('황위 규칙/로마가 저장본과 다릅니다.')
 integer(value['origin_tick'],0,MAX_TICK,'시작 틱');integer(value['last_tick'],value['origin_tick'],MAX_TICK,'마지막 틱')
 for k in ('activated_tick','period_start_tick'):
  if value[k] is not None:integer(value[k],value['origin_tick'],value['last_tick'],k)
 if (value['activated_tick'] is None)!=(value['period_start_tick'] is None):raise ValueError('황위 활성화/집계 시각 오류')
 if value['activated_tick'] is not None and value['period_start_tick']<value['activated_tick']:raise ValueError('황위 집계 시작 오류')
 boolean(value['ended'],'종료')
 if value['ended']!=(value['winner'] is not None):raise ValueError('황위 승리자/종료 불일치')
 if value['winner'] is not None and value['winner'] not in binding['cities']:raise ValueError('황위 승리 도시 오류')
 if not isinstance(value['players'],dict) or set(value['players'])!=set(binding['cities']):raise ValueError('황위 참가 도시 필드 오류')
 rules=authored['rules'];winners=[]
 for city,p in value['players'].items():
  if not isinstance(p,dict) or not set(PUBLIC_PLAYER)<=set(p) or len(p)!=3 or not set(p)-set(PUBLIC_PLAYER) <= set(players_shape):raise ValueError('황위 도시 상태 필드 오류')
  integer(p['stage'],0,len(rules['stages']),'완료 단계');boolean(p['eliminated'],'탈락')
  if p['stage']==len(rules['stages']):winners.append(city)
  if value['activated_tick'] is None and p['stage']:raise ValueError('평화 시기 황위 진행 오류')
 if winners!=([value['winner']] if value['winner'] else []) or (value['winner'] and value['players'][value['winner']]['eliminated']):raise ValueError('황위 최종 단계/승리자 불일치')
 notices=value['notices']
 if not isinstance(notices,list) or len(notices)>100000:raise ValueError('황위 알림 목록 오류')
 last=None;ids=set()
 for n in notices:
  exact(n,('id','tick','kind'),'알림');hex32(n['id'],'알림 번호')
  if n['id'] in ids:raise ValueError('황위 알림 번호 오류')
  ids.add(n['id']);integer(n['tick'],value['origin_tick'],value['last_tick'],'알림 시각')
  if n['kind'] not in (('coup_first','coup_failed','final_stage','throne_taken','coup_first_failed') if throne_rules.is_test(rules) else ('coup_attempt',)) or (last is not None and n['tick']<last):raise ValueError('황위 알림 순서 오류')
  last=n['tick']
 if notices and (value['activated_tick'] is None or value['activated_tick']!=notices[0]['tick']):raise ValueError('황위 알림/편집증 활성화 불일치')
 return rules,ids

def _validate_sealed(entry,origin,last,pending=False):
 # 'since': the tick a restore-pending period began (public: pending itself is public). Required while pending.
 if pending or 'since' in entry:exact(entry,('commit','tick','since'),'봉인');integer(entry['since'],entry['tick'] if type(entry['tick'])is int else 0,last,'복원 대기 시작')
 else:exact(entry,('commit','tick'),'봉인')
 integer(entry['tick'],origin,last,'봉인 시각')
 if not isinstance(entry['commit'],str) or len(entry['commit'])!=64 or any(c not in '0123456789abcdef' for c in entry['commit']):raise ValueError('황위 봉인 형식 오류')

def validate(value,binding,saved_tick=None):
 """Live state (host DB): every player has 'secret' or 'pending'."""
 authored=spec(binding)
 if authored is None:
  if value is not None:raise ValueError('일반 시나리오에 황위 상태가 있습니다.')
  return None
 if value is None:raise ValueError('황위 쟁탈전 저장 상태가 누락되었습니다.')
 rules,ids=_validate_globals(value,binding,('secret','pending'))
 if saved_tick is not None and value['last_tick']!=saved_tick:raise ValueError('황위 상태와 공동 저장 시각이 다릅니다.')
 requests=set()
 for city,p in value['players'].items():
  if 'pending' in p:_validate_sealed(p['pending'],value['origin_tick'],value['last_tick'],pending=True);continue
  s=p['secret'];active=value['activated_tick'] is not None
  _validate_secret(city,s,rules,p['stage'],value['origin_tick'],value['last_tick'],active)
  if not active and (s['failures'] or s['paranoia'] or s['gift_total'] or s['gift_bonus'] or s['attempts'] or s['expedition']!=fresh_secret(rules,0)['expedition']):raise ValueError('평화 시기 황위 진행 오류')
  for a in s['attempts']:
   if a['request'] in requests or a['notice'] not in ids:raise ValueError('황위 시도/알림 불일치')
   requests.add(a['request'])
  if not value['ended'] and any(e['state'] in ENDED_STATES for e in s.get('spends',())):raise ValueError('황위 시험이 끝나지 않았는데 종료 취소 지출이 있습니다.')
  for e in s.get('spends',()):
   if e['request'] in requests:raise ValueError('황위 지출 요청 중복')
   requests.add(e['request'])
   if e['kind']=='coup' and e['state']=='done' and e['result']=='failure' and not ids&{notice_id(e['request'],k) for k in FAILURE_KINDS}:raise ValueError('황위 실패/알림 불일치')
  if 'heard' in s and s['heard']>failures_announced(value):raise ValueError('황위 실패 알림 반영 수 오류')
 return value

def validate_sealed(value,binding,saved_tick=None):
 """Joint save / replica form: public values and one commitment per player, nothing private."""
 if spec(binding) is None:
  if value is not None:raise ValueError('일반 시나리오에 황위 상태가 있습니다.')
  return None
 if value is None:raise ValueError('황위 쟁탈전 저장 상태가 누락되었습니다.')
 _validate_globals(value,binding,('sealed',))
 if saved_tick is not None and value['last_tick']!=saved_tick:raise ValueError('황위 상태와 공동 저장 시각이 다릅니다.')
 for p in value['players'].values():_validate_sealed(p['sealed'],value['origin_tick'],value['last_tick'])
 return value

def upgrade(value,binding):
 """Format-1 states (before the secret split) become format 2; their notices predate recorded attempts."""
 if not isinstance(value,dict) or value.get('version')!=1:return value
 old=copy.deepcopy(value);players={}
 for city,p in old.get('players',{}).items():
  if not isinstance(p,dict):raise ValueError('황위 도시 상태 필드 오류')
  secret={k:p.get(k) for k in SECRET_FIELDS if k!='attempts'};secret['attempts']=[]
  players[city]=dict(stage=p.get('stage'),eliminated=p.get('eliminated'),secret=secret)
 old['players']=players;old['version']=VERSION;old.setdefault('notices',[])
 return old

def public_view(value):
 """What every client may receive about the live state."""
 if value is None:return None
 out={k:copy.deepcopy(value[k]) for k in ('version','spec','spec_hash','origin_tick','last_tick','activated_tick','period_start_tick','winner','ended','notices')}
 out['players']={c:dict(stage=p['stage'],eliminated=p['eliminated'],restoring='pending' in p) for c,p in value['players'].items()}
 return out

# ---- sealing and opening ------------------------------------------------------------------------------------
def seal(value,tick,present=None,confirmed=None):
 """Live state -> (sealed form, {city: (secret, nonce)} for players whose secret is known).
   fresh   a new 256-bit nonce for every player whose secret is known (so 'whose commitment changed' says nothing);
           the player must store the new opening before the save can be used for a host change (custody).
   carried a pending player keeps its earlier commitment and 'since' (its secret is not known here);
           a player absent at this save (not in `present`) whose secret is exactly its last CONFIRMED sealed secret
           keeps that confirmed seal: it could not act while away, and the opening it already holds still matches.
 present=None means everyone is treated as present (all fresh)."""
 sealed={k:copy.deepcopy(v) for k,v in value.items() if k!='players'};sealed['players']={};openings={}
 for city,p in value['players'].items():
  entry=dict(stage=p['stage'],eliminated=p['eliminated'])
  last=(confirmed or {}).get(city)
  if 'pending' in p:entry['sealed']=copy.deepcopy(p['pending'])
  elif present is not None and city not in present and last and last['secret']==p['secret']:
   entry['sealed']=dict(commit=last['commit'],tick=last['tick']);openings[city]=(copy.deepcopy(last['secret']),last['nonce'])
  else:
   nonce=_random.token_hex(32);entry['sealed']=dict(commit=commit(city,tick,p['secret'],nonce),tick=tick)
   openings[city]=(copy.deepcopy(p['secret']),nonce)
  sealed['players'][city]=entry
 return sealed,openings

def open_sealed(sealed,openings,restore_tick):
 """Sealed form + verified openings -> live state; players without a matching opening become 'pending' from
 restore_tick (or from the earlier 'since' they already carried)."""
 live={k:copy.deepcopy(v) for k,v in sealed.items() if k!='players'};live['players']={}
 for city,p in sealed['players'].items():
  entry=dict(stage=p['stage'],eliminated=p['eliminated']);o=openings.get(city)
  if o and commit(city,p['sealed']['tick'],o[0],o[1])==p['sealed']['commit']:entry['secret']=copy.deepcopy(o[0])
  else:entry['pending']=dict(commit=p['sealed']['commit'],tick=p['sealed']['tick'],since=p['sealed'].get('since',restore_tick))
  live['players'][city]=entry
 return live

def protect_deadlines(secret,since,now):
 """Personal throne deadlines still ahead when the pending period began move forward by its length, once.
 Deadlines already passed before it, and the attempt history, are left as they were."""
 shift=max(0,now-since);s=copy.deepcopy(secret)
 if s['next_attempt_tick']>since:s['next_attempt_tick']+=shift
 e=s['expedition']
 if e['deadline_tick'] is not None and e['deadline_tick']>since:e['deadline_tick']+=shift
 return s

def reveal(value,binding,city,secret,nonce,now=None):
 """A pending player hands in its own opening. Accepted only if it matches the commitment (owner, save, values).
 Its personal deadlines are protected for the pending time (protect_deadlines). Nothing else changes."""
 if city not in value['players']:raise ValueError('참가 도시가 아닙니다.')
 p=value['players'][city]
 if 'pending' not in p:return False                                     # already known: a resend changes nothing
 try:ok=commit(city,p['pending']['tick'],secret,nonce)==p['pending']['commit']
 except (ValueError,TypeError,AttributeError):ok=False
 if not ok:raise ValueError('비공개 기록이 저장본의 봉인과 맞지 않습니다.')
 now=value['last_tick'] if now is None else now
 integer(now,value['last_tick'],MAX_TICK,'제출 시각')
 changed=copy.deepcopy(value);changed['last_tick']=now
 revealed=protect_deadlines(secret,p['pending']['since'],now)
 normalize_secret(value['spec']['rules'],p['stage'],revealed)   # after the commitment check above
 rules=value['spec']['rules']
 # Test rules: the monthly rise does not run on a record the host cannot see (treated like a personal deadline:
 # no growth while restore-pending). A record sealed before activation joins at its stage floor, once.
 if throne_rules.is_test(rules) and value['activated_tick'] is not None and p['pending']['tick']<value['activated_tick']:
  revealed['paranoia']=max(revealed['paranoia'],throne_rules.base_floor(rules,p['stage']))
 changed['players'][city]=dict(stage=p['stage'],eliminated=p['eliminated'],secret=revealed)
 hear(changed)   # failures announced while this record was pending: everyone took +5 at once, so does it now
 validate(changed,binding)                                               # a matching record must also be a valid one
 value.clear();value.update(changed);return True

# ---- test rules: time -----------------------------------------------------------------------------------------
def advance(value,tick):
 """Bring the live state to `tick`. Test rules only: while active, every known record rises by monthly_paranoia
 for each game month boundary (every 800 executed ticks from the room origin) passed since last_tick, up to 100.
 last_tick only moves forward, so a month is never counted twice (resends, polls, saves). Restore-pending records
 are skipped (no growth while the host cannot see them). Returns True when anything changed."""
 if value is None or tick<=value['last_tick']:return False
 rules=value['spec']['rules']
 if throne_rules.is_test(rules) and value['activated_tick'] is not None:
  passed=throne_rules.months(value['origin_tick'],tick)-throne_rules.months(value['origin_tick'],value['last_tick'])
  if passed>0:
   for p in value['players'].values():
    if 'secret' in p:p['secret']['paranoia']=min(rules['paranoia_max'],p['secret']['paranoia']+passed*rules['monthly_paranoia'])
 value['last_tick']=tick;step_raids(value,tick);return True

def step_raids(value,tick):
 """The emperor's punitive expedition of every known record, brought to `tick` (test rules with 'expedition').
   idle       paranoia at the maximum -> 'preparing' = THE MARCH (count+1): the legions left Rome and arrive when
              deadline_tick is reached. Only now can the withdrawal tribute be paid (throne_play: they turn back).
   preparing  deadline reached -> 'arrived': the player's city is told to let the legions in (throne_play.view).
              Held while a tribute payment is being charged.
   arrived    waits for that city's engine to say they are there (throne_play.raid_report -> 'fighting')
   fighting   the legions beaten: throne_play. Not by deadline_tick -> 'cooldown', result 'sacked': they are
              called back and paranoia drops by sack_reduction (never below the stage floor). No tribute here.
   cooldown   deadline reached -> 'idle' (and at once 'preparing' again if paranoia is still at the maximum)
 After the trial ended an unfinished expedition is 'resolved' / 'called_off'. Restore-pending and eliminated
 records are left alone (their deadlines are protected, protect_deadlines). Only deadlines and the record's own
 values decide, so a resend, a poll or a save never moves anything twice. Returns True when anything changed."""
 rules=value['spec']['rules']
 if not throne_rules.is_test(rules) or 'expedition' not in rules or value['activated_tick'] is None:return False
 x=rules['expedition'];month=throne_rules.TICKS_PER_MONTH;changed=False
 for p in value['players'].values():
  if 'secret' not in p or p['eliminated']:continue
  s=p['secret'];e=s['expedition']
  if value['ended']:
   if e['phase'] in ('preparing','arrived','fighting'):e.update(phase='resolved',result='called_off',deadline_tick=None);changed=True
   continue
  paying=any(sp['kind']=='tribute' and sp['state']=='charging' for sp in s['spends'])
  for _ in range(4):
   if e['phase']=='idle':
    if s['paranoia']<rules['paranoia_max']:break
    e.update(phase='preparing',id=max(1,tick),count=e['count']+1,deadline_tick=tick+x['march_months']*month,tribute_paid=False,result=None)
   elif e['phase']=='preparing':   # the march: a tribute being charged holds the arrival (it turns them back if taken)
    if tick<e['deadline_tick'] or paying:break
    e.update(phase='arrived',deadline_tick=tick+x['siege_months']*month)
   elif e['phase']=='fighting':
    if tick<e['deadline_tick']:break
    s['paranoia']=throne_rules.raid_relief(rules,p['stage'],s['paranoia'],x['sack_reduction'])   # sacked: the emperor's anger is spent
    e.update(phase='cooldown',result='sacked',deadline_tick=tick+x['cooldown_months']*month)
   elif e['phase']=='cooldown':
    if tick<e['deadline_tick']:break
    e.update(phase='idle',deadline_tick=None,tribute_paid=False,result=None)
   else:break
   changed=True
 return changed

# ---- storage -------------------------------------------------------------------------------------------------
def initialize(db):
 db.execute('CREATE TABLE IF NOT EXISTS throne_state(id INTEGER PRIMARY KEY CHECK(id=1),payload TEXT NOT NULL,hash TEXT NOT NULL)')
 db.execute('CREATE TABLE IF NOT EXISTS joint_throne(id INTEGER PRIMARY KEY,payload TEXT NOT NULL,hash TEXT NOT NULL)')
 db.execute('CREATE TABLE IF NOT EXISTS joint_throne_secret(id INTEGER NOT NULL,city TEXT NOT NULL,payload TEXT NOT NULL,nonce TEXT NOT NULL,PRIMARY KEY(id,city))')
 # custody: a player confirmed that its opening for save `id` is stored on its PC (host DB only)
 db.execute('CREATE TABLE IF NOT EXISTS throne_custody(id INTEGER NOT NULL,city TEXT NOT NULL,commit_hash TEXT NOT NULL,PRIMARY KEY(id,city))')
 db.execute('CREATE TABLE IF NOT EXISTS throne_required(id INTEGER PRIMARY KEY CHECK(id=1))')
 if 'throne_version' not in {r[1] for r in db.execute('PRAGMA table_info(joint_save)')}:db.execute('ALTER TABLE joint_save ADD COLUMN throne_version INTEGER')

def unpack(row):
 if sha(row[0].encode())!=row[1]:raise ValueError('황위 저장 해시 오류')
 try:return json.loads(row[0])
 except (ValueError,TypeError):raise ValueError('황위 저장 JSON 오류')

def normalize_secret(rules,stage,secret):
 """Test-rule records written before 2026-11-12 late night, made current on read (never by editing a save file):
   * spends without 'seq' get seq = tick*1000 + position (their acceptance order; nothing was ever ordered by it);
   * next_cost 1,000,100 was the old stand-in for "above the 1,000,000 Dn payment limit": replaced by the exact cost
     from the rules and the failure count, only when that exact cost is indeed above the limit.
 Applied after any commitment check (openings are verified on the stored form). Returns True when it changed."""
 if not throne_rules.is_test(rules) or not isinstance(secret,dict):return False
 changed=False
 for i,e in enumerate(secret.get('spends',[])):
  if isinstance(e,dict) and 'seq' not in e and type(e.get('tick'))==int:e['seq']=e['tick']*1000+i;changed=True
 if 'heard' not in secret:secret['heard']=0;changed=True   # before 2026-11-13 no failure was announced
 legacy=rules['max_spend']+rules['cost_rounding'];exact_cost=expected_cost(rules,stage,secret.get('failures',0)) if type(secret.get('failures'))==int and secret['failures']<=10000 else None
 if secret.get('next_cost')==legacy and exact_cost is not None and exact_cost!=legacy and not throne_rules.fundable(rules,exact_cost):
  secret['next_cost']=exact_cost;changed=True
 return changed

def normalize(value):
 if not isinstance(value,dict) or not isinstance(value.get('spec'),dict):return value
 rules=value['spec'].get('rules')
 for p in (value.get('players') or {}).values():
  if isinstance(p,dict) and 'secret' in p:normalize_secret(rules,p.get('stage',0),p['secret'])
 return value

def current(db,binding):
 row=db.execute('SELECT payload,hash FROM throne_state WHERE id=1').fetchone()
 return validate(normalize(upgrade(unpack(row),binding)) if row else None,binding)

def store(db,value,binding):
 validate(value,binding)
 if value is None:
  if db.execute('SELECT 1 FROM throne_required').fetchone():raise ValueError('황위 상태를 일반 모드로 초기화할 수 없습니다.')
  db.execute('DELETE FROM throne_state');return
 payload=encode(value);db.execute('INSERT OR REPLACE INTO throne_state VALUES(1,?,?)',(payload,sha(payload.encode())))
 db.execute('INSERT OR IGNORE INTO throne_required VALUES(1)')

def configure(db,binding,tick=0):
 initialize(db)
 row=db.execute('SELECT payload,hash FROM throne_state WHERE id=1').fetchone()
 if row:validate(upgrade(unpack(row),binding),binding)
 elif spec(binding) is not None:
  if db.execute('SELECT 1 FROM throne_required').fetchone():raise ValueError('황위 현재 상태가 누락되었습니다.')
  store(db,initial(binding,tick),binding)
 if spec(binding) is not None:db.execute('INSERT OR IGNORE INTO throne_required VALUES(1)')
 elif db.execute('SELECT 1 FROM throne_required').fetchone():raise ValueError('황위 모드 규칙이 누락되었습니다.')

def put(db,sid,sealed,binding,tick,openings=None):
 """Write one joint save: the sealed form (format 2) and, on the host only, the openings."""
 validate_sealed(sealed,binding,tick)
 if sealed is None:return
 payload=encode(sealed)
 db.execute('INSERT INTO joint_throne VALUES(?,?,?)',(sid,payload,sha(payload.encode())))
 for city,(secret,nonce) in (openings or {}).items():
  if commit(city,sealed['players'][city]['sealed']['tick'],secret,nonce)!=sealed['players'][city]['sealed']['commit']:raise ValueError('황위 봉인 생성 오류')
  db.execute('INSERT INTO joint_throne_secret VALUES(?,?,?,?)',(sid,city,encode(secret),nonce))
 db.execute('UPDATE joint_save SET throne_version=? WHERE id=?',(VERSION,sid))

def _confirmed(db,binding):
 """Per player, the newest seal whose opening that player confirmed holding (host DB only)."""
 out={}
 for city in binding['cities']:
  row=db.execute('SELECT c.id,c.commit_hash,s.payload,s.nonce FROM throne_custody c JOIN joint_throne_secret s ON s.id=c.id AND s.city=c.city WHERE c.city=? ORDER BY c.id DESC LIMIT 1',(city,)).fetchone()
  if not row:continue
  sealed=json.loads(db.execute('SELECT payload FROM joint_throne WHERE id=?',(row[0],)).fetchone()[0])['players'][city]['sealed']
  if sealed['commit']==row[1]:out[city]=dict(commit=row[1],tick=sealed['tick'],secret=json.loads(row[2]),nonce=row[3])
 return out

def capture(db,sid,binding,tick,present=None):
 value=current(db,binding)
 # Rule format 1 has no monthly rule: the state at the barrier is the state after its last event.
 # Test rules (format 2): the monthly paranoia rise is brought up to the barrier first and kept in the live state too,
 # so the sealed copy and the live state agree (advance() counts each game month once).
 if value:
  if tick<value['last_tick']:raise ValueError('황위 저장 시각 역행')
  if throne_rules.is_test(value['spec']['rules']):advance(value,tick);store(db,value,binding)
  value['last_tick']=tick
  sealed,openings=seal(value,tick,present,_confirmed(db,binding) if present is not None else None)
  put(db,sid,sealed,binding,tick,openings)
 else:put(db,sid,None,binding,tick)

def _rows(db,sid):
 columns={r[1] for r in db.execute('PRAGMA table_info(joint_save)')}
 marker=db.execute('SELECT throne_version FROM joint_save WHERE id=?',(sid,)).fetchone()[0] if 'throne_version' in columns else None
 exists=db.execute("SELECT 1 FROM sqlite_master WHERE name='joint_throne'").fetchone()
 row=db.execute('SELECT payload,hash FROM joint_throne WHERE id=?',(sid,)).fetchone() if exists else None
 return marker,row

def sealed_save(db,sid,binding,tick):
 """The sealed form of one joint save: all a host-backup replica may carry."""
 marker,row=_rows(db,sid)
 if marker is None and row is None:return validate_sealed(None,binding,tick)
 if row is None:raise ValueError('황위 저장 본문 누락')
 if marker==VERSION:return validate_sealed(unpack(row),binding,tick)
 if marker==1:   # an old save holds secrets in its body: seal it, never pass the body on
  live=validate(upgrade(unpack(row),binding),binding,tick);return seal(live,tick)[0]
 raise ValueError('지원하지 않는 황위 저장 형식입니다.')

def opening(db,sid,city):
 """One player's own opening for a joint save (host DB only). None when this DB has no secrets (a replica)."""
 exists=db.execute("SELECT 1 FROM sqlite_master WHERE name='joint_throne_secret'").fetchone()
 row=db.execute('SELECT payload,nonce FROM joint_throne_secret WHERE id=? AND city=?',(sid,city)).fetchone() if exists else None
 return (json.loads(row[0]),row[1]) if row else None

def read(db,sid,binding,tick):
 """Live state to restore from a joint save. From the host's own DB every secret is there and verified against
 its commitment; from a replica every player is 'pending' until it hands in its opening."""
 marker,row=_rows(db,sid)
 if marker is None and row is None:return validate(None,binding,tick)
 if row is None:raise ValueError('황위 저장 버전/본문 오류')
 if marker==1:return validate(upgrade(unpack(row),binding),binding,tick)
 if marker!=VERSION:raise ValueError('지원하지 않는 황위 저장 형식입니다.')
 sealed=validate_sealed(unpack(row),binding,tick)
 openings={c:o for c in binding['cities'] if (o:=opening(db,sid,c))}
 live=open_sealed(sealed,openings,tick)
 bad=[c for c in openings if 'pending' in live['players'][c]]
 if bad:raise ValueError('황위 비공개 저장이 봉인과 맞지 않습니다: '+', '.join(bad))
 return validate(normalize(live),binding,tick)

def restore(db,value,binding,tick):
 validate(value,binding,tick);store(db,value,binding)

# ---- custody: when a complete save may be used for a host change -------------------------------------------------
def confirm_custody(db,binding,sid,city,commit_hash):
 """`city` says its opening for save `sid` is written to its disk and read back. Accepted only for that player's
 commitment in that very save; a confirmation for another save or another commitment changes nothing."""
 row=db.execute("SELECT ticks FROM joint_save WHERE id=? AND state='complete'",(sid,)).fetchone()
 if not row:raise ValueError('완료된 공동 저장이 아닙니다.')
 sealed=sealed_save(db,sid,binding,row[0])
 if not sealed or city not in sealed['players'] or sealed['players'][city]['sealed']['commit']!=commit_hash:raise ValueError('이 저장의 봉인과 맞지 않는 확인입니다.')
 if not opening(db,sid,city):raise ValueError('이 방장에게 없는 저장 자료입니다.')
 db.execute('INSERT OR IGNORE INTO throne_custody VALUES(?,?,?)',(sid,city,commit_hash))
 return custody(db,binding,sid)

def custody(db,binding,sid):
 """ready: every player whose commitment was made fresh at this save has confirmed holding its opening.
 Carried commitments (restore-pending players, or players away and unchanged) need no new confirmation;
 pending players stay pending in the save (that is reported, never hidden)."""
 if spec(binding) is None:return dict(ready=True,waiting=0,pending=[])
 row=db.execute("SELECT ticks FROM joint_save WHERE id=? AND state='complete'",(sid,)).fetchone()
 if not row:return dict(ready=False,waiting=None,pending=[],reason='incomplete')
 sealed=sealed_save(db,sid,binding,row[0])
 have={r[0]:r[1] for r in db.execute('SELECT city,commit_hash FROM throne_custody WHERE id=?',(sid,))}
 fresh=[c for c,p in sealed['players'].items() if p['sealed']['tick']==row[0] and 'since' not in p['sealed']]
 # A carried, already acknowledged seal can have exactly the same tick after paused saves.
 # Compare the commitment, not elapsed game time, to identify acknowledged carried records.
 waiting=[c for c in fresh if have.get(c)!=sealed['players'][c]['sealed']['commit'] and not db.execute(
  'SELECT 1 FROM throne_custody WHERE city=? AND commit_hash=? AND id<?',
  (c,sealed['players'][c]['sealed']['commit'],sid)).fetchone()]
 pending=sorted(c for c,p in sealed['players'].items() if 'since' in p['sealed'])
 return dict(ready=not waiting,waiting=len(waiting),pending=pending)

def handover_save(db,binding):
 """The newest complete save that a new host could restore with every confirmed record (None if none yet)."""
 for (sid,) in db.execute("SELECT id FROM joint_save WHERE state='complete' ORDER BY id DESC").fetchall():
  if custody(db,binding,sid)['ready']:return sid
 return None
