"""황위 시험 규칙 v1 (Race for the Throne, TEST rule set approved 2026-11-12 as a first trial; not a balanced or
measured rule set). Every number of the trial lives here; nothing else in the code holds one.

A scenario uses it only when its rules.throne is exactly TEST_RULES_V1 (rule format version 2). Older rule data
(format version 1, throne_state.DEFAULT_RULES) keeps its earlier meaning: stored only, never run.

Stage numbers: a player's public 'stage' counts COMPLETED coup stages (0..5). The stage it works on is stage+1, so
table row i (0-based) is "단계 i+1": the coup it attempts next, and the paranoia floors that apply while it is there.
After the fifth success the player holds stage 5 (final) and the last row's floors stay in force.

All amounts are fixed Dn. All probabilities are integers in basis points (1/100 of a percent): the value shown and the
value drawn are the same integer.

Revised 2026-11-13 (user): a failed coup raises every player's paranoia at once by failure_paranoia (5), naming no
one. Rooms and saves made with the set before this revision no longer match it and are refused like any other
changed set (only test rooms existed).

Revised 2026-11-14 (user): the emperor's punitive expedition ('expedition'). Paranoia 100 -> the emperor prepares for
preparation_months, then his legions (the original Caesar legions) arrive at the city's entry and attack at once.
Tribute may be paid at any time while they are there (they withdraw, paranoia -tribute_reduction); beating them
gives -victory_reduction; if neither happens within siege_months they sack the city and withdraw, paranoia unchanged.
After any of these no new expedition starts for cooldown_months. Each expedition against the same player is larger
(army_initial + army_increment per earlier one, at most army_cap). The numbers are the design document's interim
values (13장). As with the 2026-11-13 revision, rooms and saves made before it are refused as a changed set.

Confirmed plan 2026-11-14 (docs/황위-쟁탈전-확정안-20261114.md, replaces the numbers and the expedition flow above):
  * chance base/cap 50/70, 41/63, 33/55, 24/48, 15/40; paranoia +2 a month; a failed coup +5 for everyone.
  * expedition: at paranoia 100 the legions LEAVE ROME at once (no preparation). They march for march_months (3):
    only then can the withdrawal tribute be paid (they turn back, paranoia -80); its amount is the one of the stage
    held at departure and does not change on the way. On arrival they attack at once; no tribute any more.
    Beaten: -25. Not beaten within siege_months (2): they sack the city and withdraw, paranoia -50. Then
    cooldown_months (2) without a new one. Every reduction stops at the stage floor.
  * the numbers come from the scenario file (the scenario editor): validate() accepts any set inside the ranges
    below, STANDARD is the preset of the plan, preset() gives the editor's three presets. Stage names are fixed
    (translations)."""
import copy

TICKS_PER_MONTH=800
STAGE_NAMES=('비밀 조직 결성','원로원 매수','근위대 포섭','황궁 내부 장악','황제 폐위')   # existing names (DEFAULT_RULES)
TEST_RULES_V1=dict(version=2,label='황위 쟁탈전 규칙',
 stages=[dict(name=n,cost=c,chance=b,cap=cap,floor=f,gift_floor=g) for n,c,b,cap,f,g in zip(STAGE_NAMES,
  (5000,10000,20000,40000,80000),(50,41,33,24,15),(70,63,55,48,40),(10,20,30,40,50),(0,10,20,30,40))],
 failure_percent=25,cost_rounding=100,attempt_months=2,monthly_paranoia=2,failure_paranoia=5,paranoia_max=100,
 gift_price=200,gift_price_below=600,max_spend=1000000,
 expedition=dict(march_months=3,siege_months=2,cooldown_months=2,tribute_reduction=80,victory_reduction=25,sack_reduction=50,
                 tributes=[3000,5000,8000,12000,18000],army_initial=32,army_increment=16,army_cap=80))
FIELDS=('version','label','stages','failure_percent','cost_rounding','attempt_months','monthly_paranoia','failure_paranoia','paranoia_max',
        'gift_price','gift_price_below','max_spend','expedition')
STAGE_FIELDS=('name','cost','chance','cap','floor','gift_floor')

def test_rules():return copy.deepcopy(TEST_RULES_V1)
def is_test(rules):return isinstance(rules,dict) and rules.get('version')==2

STANDARD=TEST_RULES_V1
EXPEDITION_FIELDS=('march_months','siege_months','cooldown_months','tribute_reduction','victory_reduction','sack_reduction','tributes','army_initial','army_increment','army_cap')
PRESETS=('standard','short','long')
def preset(name):
    """The scenario editor's presets. short: funding and tribute x0.5, a coup every month. long: x1.5, every 3 months.
    Chances are the same in all three."""
    if name not in PRESETS:raise ValueError('황위 프리셋 이름 오류')
    rules=copy.deepcopy(STANDARD)
    if name=='standard':return rules
    half=name=='short'
    for s in rules['stages']:s['cost']=s['cost']//2 if half else s['cost']*3//2
    rules['expedition']['tributes']=[t//2 if half else t*3//2 for t in rules['expedition']['tributes']]
    rules['attempt_months']=1 if half else 3
    return rules
def preset_of(rules):return next((n for n in PRESETS if preset(n)==rules),None)

def _int(value,low,high,label):
    if type(value) is not int or not low<=value<=high:raise ValueError(f'황위 규칙 {label}: {low}~{high}의 정수여야 합니다.')
def validate(rules):
    """Format-2 rules from a scenario file: every number inside its range and the table consistent (the editor
    refuses the same things before export). Exactly five stages with the fixed names."""
    if not isinstance(rules,dict) or set(rules)!=set(FIELDS):raise ValueError('황위 규칙 필드 오류')
    if rules['version']!=2 or rules['label']!=STANDARD['label']:raise ValueError('황위 규칙 형식 오류')
    stages=rules['stages']
    if not isinstance(stages,list) or len(stages)!=len(STAGE_NAMES):raise ValueError('황위 규칙은 5단계여야 합니다.')
    floor=-1
    for i,s in enumerate(stages):
        if not isinstance(s,dict) or set(s)!=set(STAGE_FIELDS) or s['name']!=STAGE_NAMES[i]:raise ValueError('황위 단계 필드 오류')
        _int(s['cost'],100,1000000,'최소 지원금');_int(s['chance'],1,95,'성공률 기본');_int(s['cap'],s['chance'],95,'성공률 상한')
        _int(s['floor'],floor+1,99,'기준 하한(단계마다 커져야 합니다)');floor=s['floor'];_int(s['gift_floor'],0,s['floor'],'선물 최저치(기준 하한 이하)')
    _int(rules['failure_percent'],0,100,'실패 뒤 인상률');_int(rules['cost_rounding'],1,10000,'금액 단위');_int(rules['attempt_months'],1,24,'도전 간격')
    _int(rules['monthly_paranoia'],0,20,'매달 편집증');_int(rules['failure_paranoia'],0,50,'실패 시 편집증')
    if rules['paranoia_max']!=100:raise ValueError('황위 규칙 편집증 최대치는 100입니다.')
    _int(rules['gift_price'],1,100000,'선물 단가');_int(rules['gift_price_below'],1,100000,'하한 아래 선물 단가')
    _int(rules['max_spend'],max(s['cost'] for s in stages),100000000,'1회 지출 한도')
    x=rules['expedition']
    if not isinstance(x,dict) or set(x)!=set(EXPEDITION_FIELDS):raise ValueError('황위 원정 규칙 필드 오류')
    for k,label in (('march_months','행군 기간'),('siege_months','격퇴 기한'),('cooldown_months','유예 기간')):_int(x[k],1,24,label)
    for k,label in (('tribute_reduction','공물 감소'),('victory_reduction','격파 감소'),('sack_reduction','약탈 감소')):_int(x[k],0,100,label)
    if not isinstance(x['tributes'],list) or len(x['tributes'])!=len(stages):raise ValueError('황위 철수 공물은 단계마다 하나씩이어야 합니다.')
    for v in x['tributes']:_int(v,1,rules['max_spend'],'철수 공물')
    _int(x['army_initial'],1,400,'황제군 초기 규모');_int(x['army_increment'],0,400,'황제군 증가');_int(x['army_cap'],x['army_initial'],400,'황제군 최대 규모(초기 이상)')
    return rules

def row(rules,stage):
    """The table row in force for a player with `stage` completed stages."""
    stages=rules['stages'];return stages[min(stage,len(stages)-1)]
def base_floor(rules,stage):return row(rules,stage)['floor']
def gift_floor(rules,stage):return row(rules,stage)['gift_floor']
def months(origin,tick):return (tick-origin)//TICKS_PER_MONTH

BIG=10**12   # far above any reachable cost: stops the calculation for manipulated failure counts (never a rule value)

def min_cost(rules,stage,failures):
    """Minimum coup funding after `failures` failures at this stage: each failure x1.25, rounded UP to 100 Dn.
    Exact for every reachable record: the first value above max_spend is kept as it is (shown, and refused as a
    payment). Only an unreachable failure count can run past BIG; the calculation stops there (that record is invalid
    anyway, see reachable())."""
    if stage>=len(rules['stages']):return 0
    cost=rules['stages'][stage]['cost'];step=rules['cost_rounding']
    for _ in range(min(failures,10000)):
        cost=((cost*(100+rules['failure_percent'])+100*step-1)//(100*step))*step
        if cost>BIG:break
    return cost

def fundable(rules,cost):return cost<=rules['max_spend']

def reachable(rules,stage,failures):
    """A failure count can only grow through a funded attempt: the cost before the last failure was payable."""
    return failures==0 or (stage<len(rules['stages']) and fundable(rules,min_cost(rules,stage,failures-1)))

def chance_bp(rules,stage,minimum,amount):
    """P = B + (C-B)(A-M)/A, in basis points, rounded down. A=M gives B; A=2M gives the midpoint; never reaches C."""
    s=rules['stages'][stage];base=s['chance']*100;cap=s['cap']*100
    return base+((cap-base)*(amount-minimum))//amount

def percent(bp):return f'{bp//100}.{bp%100:02d}%'

def gift_plan(rules,stage,paranoia,limit):
    """Lower my own paranoia one point at a time from its current value, within `limit` Dn:
    200 Dn a point down to the stage floor, 600 Dn a point below it, never below the gift floor.
    Only what is used is charged; the rest stays in the treasury (nothing is kept for later)."""
    floor=base_floor(rules,stage);bottom=gift_floor(rules,stage)
    value=paranoia;charge=0
    while value>bottom:
        price=rules['gift_price'] if value>floor else rules['gift_price_below']
        if charge+price>limit:break
        charge+=price;value-=1
    return dict(points=paranoia-value,charge=charge,rest=limit-charge,after=value,floor=floor,bottom=bottom,
                next_price=(rules['gift_price'] if value>floor else rules['gift_price_below']) if value>bottom else 0)

# ---- the emperor's punitive expedition (2026-11-14) ----
def raid_size(rules,count):
    """Soldiers of this player's `count`-th expedition (1 = first): 32, 48, 64, 80, 80, ..."""
    x=rules['expedition'];return min(x['army_cap'],x['army_initial']+max(0,count-1)*x['army_increment'])
def raid_tribute(rules,stage):
    """Dn that makes the legions withdraw, by completed coup stages (0..4)."""
    t=rules['expedition']['tributes'];return t[min(stage,len(t)-1)]
def raid_stage(stage,secret):
    """Completed stages this player held when the current expedition left Rome (expedition id = that tick): the
    withdrawal tribute is fixed then and does not follow a stage won on the way."""
    left=secret['expedition']['id']
    return max(0,stage-sum(1 for e in secret.get('spends',()) if e['kind']=='coup' and e['state']=='done' and e['result']=='success' and e['done']>=left))
def raid_relief(rules,stage,paranoia,points):
    """Paranoia after an expedition is settled: never below the stage floor (design 7.5), never raised by it."""
    return min(paranoia,max(base_floor(rules,stage),paranoia-points))

def offset_cost(rules,stage):
    """Cost of buying back one month's paranoia rise (monthly_paranoia points) from just above the stage floor."""
    return rules['monthly_paranoia']*rules['gift_price']

if __name__=='__main__':
    # For the scenario editor (creator-src/CreatorThrone.cs): the presets, and the check of an edited set.
    import argparse,json,sys
    from pathlib import Path
    p=argparse.ArgumentParser(description='Race for the Throne rule sets');p.add_argument('--presets',action='store_true');p.add_argument('--validate',type=Path)
    a=p.parse_args();sys.stdout.reconfigure(encoding='utf-8')
    if a.presets:print(json.dumps({n:preset(n) for n in PRESETS},ensure_ascii=False))
    elif a.validate:
        try:
            rules=validate(json.loads(a.validate.read_text(encoding='utf-8-sig')))
            total=sum(s['cost'] for s in rules['stages']);months=(len(rules['stages'])-1)*rules['attempt_months']
            print(json.dumps(dict(valid=True,preset=preset_of(rules),summary=f'5단계까지 최소 지원금 합계 {total:,} Dn, 한 번도 실패하지 않아도 최소 {months}개월'),ensure_ascii=False))
        except (ValueError,KeyError,TypeError) as e:print(json.dumps(dict(valid=False,error=str(e) or type(e).__name__),ensure_ascii=False))
