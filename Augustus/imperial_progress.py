"""황제의 순행 (competition mode, user 2026-11-15). Host side only.

The emperor tours the provinces. Each progress:
  1. announce   three candidate goods are made public. One of them was already drawn and is kept on the host only.
  2. bidding    one in-game month. Each city may hand in ONE sealed bid (at least the minimum). Nothing is charged.
  3. close      the highest bid hosts the emperor; a tie goes to the earlier bid. Only the winner pays: a one-sided debit
                of its own city (trade_post_ledger.stage_debit, the same command and receipt as the throne spends). If
                its treasury does not cover the bid when the command arrives, the next bidder is tried. No valid bid:
                a random city of the room is chosen and pays nothing. Nobody can pass the visit on.
  4. travel     the arrival day is drawn at the close and never shown.
  5. arrival    the host tells the hosting city's game which ONE of the three goods the court uses, and how much (the
                amount is drawn with the good, between the scenario's two bounds, and is as secret as the good). That
                game takes what it has from its warehouses and granaries, up to the amount, once (kept in the city
                save: src/multiplayer/emperor_visit.inc) and says how much it took. That is this game's own word,
                like the army reports; money never depends on a client's word.
  6. score      all of it: favour +3. Half or more: +1. Less: -1, and the missing goods are paid in money at the
                scenario's price, at most what the city's game shows as its treasury (one debit; if the engine cannot
                take it, nothing more is asked).
After the last progress the city with the highest favour is the emperor's right hand. A tie: the one that paid the
emperor more in bids; still a tie: they share the title.

A hosting city that leaves the room cancels that progress (a bid already taken is not returned: it left) and the
next one follows. State: one row in the room DB; a joint save keeps a copy (capture/read/put/restore) next to the
cash checkpoint that holds the debits. The sealed bids of an open auction are part of that copy."""
import copy,hashlib,json,secrets
from coordinator import sha

MONTH=800                  # game ticks per month (throne_rules.TICKS_PER_MONTH)
DAY=50
MAX_TICK=2**40
VERSION=1
GOODS=(1,2,3,4,5,15,16,17,18,19)                 # food and finished goods (engine resource ids)
DEFAULT=dict(version=1,rounds=6,min_bid=500,start_months=24,gap_months=3,prepare_min=2,prepare_max=4,amount_min=16,amount_max=32,
             shortfall_price=100,goods=[1,2,3,4,15,16,17,18])
WAREHOUSE=32               # one warehouse holds 32 loads: the most a visit may ask for (user 2026-11-15)
FULL,PART,POOR=3,1,-1

def defaults():return copy.deepcopy(DEFAULT)
def encode(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))

def _int(value,low,high,label):
    if type(value)!=int or not low<=value<=high:raise ValueError(f'{label}: {low}~{high} 범위의 정수여야 합니다.')
    return value

def validate_spec(spec):
    if not isinstance(spec,dict) or set(spec)!=set(DEFAULT):raise ValueError('황제의 순행 설정 형식 오류')
    if spec['version']!=1:raise ValueError('지원하지 않는 황제의 순행 설정입니다.')
    _int(spec['rounds'],1,20,'순행 횟수');_int(spec['min_bid'],1,1000000,'최저 입찰가');_int(spec['start_months'],0,600,'첫 순행까지의 기간')
    _int(spec['gap_months'],0,120,'순행 사이 기간');_int(spec['prepare_min'],1,24,'준비 기간(최소)');_int(spec['prepare_max'],1,24,'준비 기간(최대)')
    if spec['prepare_min']>spec['prepare_max']:raise ValueError('준비 기간의 최소가 최대보다 큽니다.')
    _int(spec['amount_min'],1,WAREHOUSE,'요구량(최소)');_int(spec['amount_max'],1,WAREHOUSE,'요구량(최대)')
    if spec['amount_min']>spec['amount_max']:raise ValueError('요구량의 최소가 최대보다 큽니다.')
    _int(spec['shortfall_price'],0,10000,'부족분 가격')
    goods=spec['goods']
    if not isinstance(goods,list) or len(goods)<3 or len(set(goods))!=len(goods) or any(type(g)!=int or g not in GOODS for g in goods) or goods!=sorted(goods):
        raise ValueError('순행 물품은 서로 다른 세 가지 이상을 골라야 합니다.')
    return spec

def spec(binding):
    value=binding.get('progress')
    if value is not None:validate_spec(value)
    return value

def initial(binding,tick=0):
    rules=spec(binding)
    if rules is None:return None
    return dict(version=VERSION,spec=copy.deepcopy(rules),nonce=secrets.token_hex(16),origin_tick=tick,last_tick=tick,round=0,phase='idle',
                next_tick=tick+rules['start_months']*MONTH,goods=[],good=0,amount=0,close_tick=None,arrive_tick=None,bids={},seq=0,queue=[],charge=None,
                holder=None,chosen=None,paid=0,visit=None,favor={c:0 for c in sorted(binding['cities'])},paid_total={c:0 for c in sorted(binding['cities'])},
                results=[],winners=[],ended=False)

# ---- storage -------------------------------------------------------------------------------------------------------
def initialize(db):
    db.execute('CREATE TABLE IF NOT EXISTS progress_state(id INTEGER PRIMARY KEY CHECK(id=1),payload TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS joint_progress(id INTEGER PRIMARY KEY,payload TEXT,hash TEXT)')

PHASES=('idle','bidding','charging','travel','arrived','fine','ended')
def validate(value,binding):
    """Shape and ranges of a stored or received state. Raises ValueError."""
    rules=spec(binding)
    if rules is None or not isinstance(value,dict) or value.get('version')!=VERSION or value.get('spec')!=rules:raise ValueError('순행 저장 형식 오류')
    cities=sorted(binding['cities'])
    if set(value)!=set(initial(binding)):raise ValueError('순행 저장 형식 오류')
    if value['phase'] not in PHASES or type(value['ended'])!=bool or (value['phase']=='ended')!=value['ended']:raise ValueError('순행 저장 값 오류')
    for k in ('origin_tick','last_tick'):_int(value[k],0,MAX_TICK,'순행 시각')
    _int(value['round'],0,rules['rounds'],'순행 번호');_int(value['amount'],0,WAREHOUSE,'순행 요구량');_int(value['seq'],0,2**40,'순행 순번');_int(value['paid'],0,1000000,'순행 낙찰가')
    for k in ('next_tick','close_tick','arrive_tick'):
        if value[k] is not None:_int(value[k],0,MAX_TICK,'순행 시각')
    if not isinstance(value['nonce'],str) or len(value['nonce'])!=32 or any(c not in '0123456789abcdef' for c in value['nonce']):raise ValueError('순행 저장 값 오류')
    for k in ('favor','paid_total'):
        if not isinstance(value[k],dict) or sorted(value[k])!=cities or any(type(v)!=int or abs(v)>10**9 for v in value[k].values()):raise ValueError('순행 저장 값 오류')
    if value['goods'] and (len(value['goods'])!=3 or any(g not in rules['goods'] for g in value['goods']) or value['good'] not in value['goods']):raise ValueError('순행 물품 오류')
    if value['holder'] is not None and value['holder'] not in cities:raise ValueError('순행 도시 오류')
    if value['chosen'] not in (None,'bid','random'):raise ValueError('순행 저장 값 오류')
    if not isinstance(value['bids'],dict) or not set(value['bids'])<=set(cities):raise ValueError('순행 입찰 오류')
    for b in value['bids'].values():
        if not isinstance(b,dict) or set(b)!={'amount','seq','request'} or type(b['amount'])!=int or not 1<=b['amount']<=1000000 or type(b['seq'])!=int or not isinstance(b['request'],str) or len(b['request'])!=32:raise ValueError('순행 입찰 오류')
    if not isinstance(value['queue'],list) or any(c not in value['bids'] for c in value['queue']):raise ValueError('순행 입찰 오류')
    c=value['charge']
    if c is not None and (not isinstance(c,dict) or set(c)!={'city','amount','id','kind'} or c['city'] not in cities or c['kind'] not in ('bid','fine') or type(c['amount'])!=int or not 1<=c['amount']<=1000000 or not isinstance(c['id'],str) or len(c['id'])!=32):raise ValueError('순행 차감 오류')
    v=value['visit']
    if v is not None and (not isinstance(v,dict) or set(v)!={'id','resource','amount','taken','fine'} or v['resource'] not in rules['goods'] or type(v['amount'])!=int or (v['taken'] is not None and type(v['taken'])!=int)):raise ValueError('순행 접대 오류')
    if not isinstance(value['results'],list) or len(value['results'])>rules['rounds'] or not isinstance(value['winners'],list) or not set(value['winners'])<=set(cities):raise ValueError('순행 결과 오류')
    for r in value['results']:
        if not isinstance(r,dict) or set(r)!={'round','holder','chosen','paid','good','amount','taken','delta','fine','result'}:raise ValueError('순행 결과 오류')
    return value

def current(db,binding):
    if spec(binding) is None:return None
    row=db.execute('SELECT payload FROM progress_state WHERE id=1').fetchone()
    return validate(json.loads(row[0]),binding) if row else None

def store(db,value,binding):
    db.execute('INSERT OR REPLACE INTO progress_state VALUES(1,?)',(encode(validate(value,binding)),))

def configure(db,binding,tick=0):
    initialize(db)
    if spec(binding) is not None and not db.execute('SELECT 1 FROM progress_state').fetchone():store(db,initial(binding,tick),binding)

def put(db,sid,value,binding):
    """A joint save's copy (also received from another PC: save_replica)."""
    initialize(db)
    if value is None:return   # a save made before the first clock tick (the start saves) has no copy: read as "not begun"
    payload=encode(validate(value,binding))
    db.execute('INSERT OR REPLACE INTO joint_progress VALUES(?,?,?)',(sid,payload,sha(payload.encode())))

def capture(db,sid,binding):
    put(db,sid,current(db,binding),binding)

def read(db,sid,binding):
    if spec(binding) is None:return None
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='joint_progress'").fetchone():return None
    row=db.execute('SELECT payload,hash FROM joint_progress WHERE id=?',(sid,)).fetchone()
    if not row:return None   # the start saves: nothing had begun
    if sha(row[0].encode())!=row[1]:raise ValueError('순행 저장 해시 오류')
    return validate(json.loads(row[0]),binding)

def restore(db,value,binding,tick):
    initialize(db)
    if spec(binding) is None:return
    db.execute('DELETE FROM progress_state')
    store(db,initial(binding,tick or 0) if value is None else validate(value,binding),binding)

# ---- rules ---------------------------------------------------------------------------------------------------------
def contract_id(state,kind,city):
    return hashlib.sha256(('augustus-progress\x00%s\x00%d\x00%s\x00%s'%(state['nonce'],state['round'],kind,city)).encode()).hexdigest()[:32]

def _ledger_row(db,cid):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='post_contract'").fetchone():return None
    return db.execute('SELECT phase,exported FROM post_contract WHERE id=?',(cid,)).fetchone()

def _stage(db,binding,state,kind,city,amount,ensure_ledger):
    import trade_post_ledger
    ensure_ledger();cid=contract_id(state,kind,city)
    trade_post_ledger.stage_debit(db,list(binding['cities']),city,cid,amount)
    state['charge']=dict(city=city,amount=amount,id=cid,kind=kind)

def _announce(state,now):
    rules=state['spec'];state['round']+=1
    goods=sorted(secrets.SystemRandom().sample(rules['goods'],3))
    # which good and how much: drawn now, kept on the host, shown to nobody before the arrival (user 2026-11-15)
    state.update(phase='bidding',goods=goods,good=secrets.choice(goods),amount=rules['amount_min']+secrets.randbelow(rules['amount_max']-rules['amount_min']+1),close_tick=now+MONTH,arrive_tick=None,bids={},queue=[],charge=None,
                 holder=None,chosen=None,paid=0,visit=None,next_tick=None)

def _depart(state,now,city,chosen,paid):
    rules=state['spec']
    wait=secrets.randbelow((rules['prepare_max']-rules['prepare_min'])*MONTH+1)+rules['prepare_min']*MONTH
    state.update(phase='travel',holder=city,chosen=chosen,paid=paid,arrive_tick=now+wait,charge=None,queue=[])
    if paid:state['paid_total'][city]+=paid

def _finish(state,now,result,taken=None,delta=0,fine=0):
    rules=state['spec']
    state['results'].append(dict(round=state['round'],holder=state['holder'],chosen=state['chosen'],paid=state['paid'],good=state['good'] if result!='cancelled' else 0,
                                 amount=state['amount'] if result!='cancelled' else 0,taken=taken,delta=delta,fine=fine,result=result))
    if state['holder'] is not None:state['favor'][state['holder']]+=delta
    state.update(charge=None,visit=None,queue=[],bids={})
    if state['round']>=rules['rounds']:
        best=max(state['favor'].values());top=[c for c in sorted(state['favor']) if state['favor'][c]==best]
        most=max(state['paid_total'][c] for c in top)
        state.update(phase='ended',ended=True,winners=[c for c in top if state['paid_total'][c]==most],next_tick=None)
    else:state.update(phase='idle',next_tick=now+rules['gap_months']*MONTH)

def score(amount,taken):
    return FULL if taken>=amount else PART if taken*2>=amount else POOR

def advance(db,binding,tick,active,ensure_ledger=lambda:None):
    """Everything the clock and the debit receipts decide, up to `tick`. Idempotent; the caller commits.
    `active`: the cities still in the room. Returns True when the state changed."""
    state=current(db,binding)
    if state is None:return False
    active=[c for c in sorted(binding['cities']) if c in set(active)]
    changed=False
    if tick>state['last_tick']:state['last_tick']=tick;changed=True
    now=state['last_tick']
    for _ in range(64):   # bounded: each pass moves one step or stops
        phase=state['phase']
        if phase=='ended':break
        if phase=='idle':
            if now<state['next_tick'] or not active:break
            _announce(state,now)
        elif phase=='bidding':
            if now<state['close_tick']:break
            state['queue']=[c for c in sorted(state['bids'],key=lambda c:(-state['bids'][c]['amount'],state['bids'][c]['seq'])) if c in active]
            state['phase']='charging'
        elif phase=='charging':
            c=state['charge']
            if c is None:
                state['queue']=[x for x in state['queue'] if x in active]
                if state['queue']:
                    city=state['queue'].pop(0);_stage(db,binding,state,'bid',city,state['bids'][city]['amount'],ensure_ledger)
                elif active:_depart(state,now,secrets.choice(active),'random',0)
                else:break
            else:
                row=_ledger_row(db,c['id'])
                if row is None:_stage(db,binding,state,'bid',c['city'],c['amount'],ensure_ledger)   # a copy without the debit: same id again
                elif row['phase']=='complete' and row['exported']:_depart(state,now,c['city'],'bid',c['amount'])
                elif row['phase']=='cancelled':state['charge']=None                                 # could not pay: the next bidder
                else:
                    import trade_post_ledger
                    if c['city'] not in active and trade_post_ledger.withdraw_debit(db,c['id']):state['charge']=None
                    else:break                                                                      # the city's receipt decides
        elif phase=='travel':
            if state['holder'] not in active:_finish(state,now,'cancelled')
            elif now<state['arrive_tick']:break
            else:state.update(phase='arrived',visit=dict(id=state['round'],resource=state['good'],amount=state['amount'],taken=None,fine=0))
        elif phase=='arrived':
            if state['holder'] not in active:_finish(state,now,'cancelled')
            else:break                                                                              # the hosting game's report (visit_report)
        elif phase=='fine':
            c=state['charge'];v=state['visit'];row=_ledger_row(db,c['id'])
            if row is None:_stage(db,binding,state,'fine',c['city'],c['amount'],ensure_ledger)
            elif row['phase']=='complete' and row['exported']:_finish(state,now,'poor',v['taken'],POOR,c['amount'])
            elif row['phase']=='cancelled':_finish(state,now,'poor',v['taken'],POOR,0)
            else:
                import trade_post_ledger
                if c['city'] not in active and trade_post_ledger.withdraw_debit(db,c['id']):_finish(state,now,'poor',v['taken'],POOR,0)
                else:break
        changed=True
    if changed:store(db,state,binding)
    return changed

def bid(db,binding,city,request,amount,funds,tick,active):
    """One sealed bid. Nothing is charged here. Returns {state: accepted|refused, reason?}; the caller commits."""
    state=current(db,binding)
    if state is None:raise ValueError('황제의 순행 시나리오가 아닙니다.')
    if not isinstance(request,str) or len(request)!=32 or any(c not in '0123456789abcdef' for c in request):raise ValueError('요청 번호')
    if city not in state['favor']:raise ValueError('참가 도시가 아닙니다.')
    def no(reason):return dict(state='refused',reason=reason)
    old=state['bids'].get(city)
    if old and old['request']==request:return dict(state='accepted',amount=old['amount'],duplicate=True)
    if state['phase']!='bidding' or tick>=state['close_tick']:return no('지금은 입찰을 받지 않습니다.')
    if city not in active:return no('참가 도시가 아닙니다.')
    if old:return no('이미 입찰했습니다. 입찰은 한 번만 할 수 있습니다.')
    if type(amount)!=int or amount<1:return no('금액을 정해 주세요.')
    low=state['spec']['min_bid']
    if amount<low:return no(f'최저 입찰가는 {low:,} Dn입니다.')
    if amount>1000000:return no('한 번에 1,000,000 Dn까지 낼 수 있습니다.')
    if type(funds)==int and amount>funds:return no(f'보유 자금({funds:,} Dn)보다 큰 금액입니다.')
    if any(b['request']==request for b in state['bids'].values()):raise ValueError('사용할 수 없는 요청 번호입니다.')
    state['seq']+=1;state['bids'][city]=dict(amount=amount,seq=state['seq'],request=request)
    store(db,state,binding);return dict(state='accepted',amount=amount,duplicate=False)

def visit_report(db,binding,city,visit,taken,funds,tick,active,ensure_ledger=lambda:None):
    """The hosting city's own game says how much of the good it handed over for visit number `visit`. Anything else,
    another number or a second report changes nothing. The caller commits."""
    state=current(db,binding)
    if state is None:raise ValueError('황제의 순행 시나리오가 아닙니다.')
    _int(visit,1,1000,'순행 번호');_int(taken,0,100000,'접대 수량')
    v=state['visit']
    if state['phase']!='arrived' or state['holder']!=city or v is None or v['id']!=visit or v['taken'] is not None:return False
    rules=state['spec'];taken=min(taken,v['amount']);v['taken']=taken;delta=score(v['amount'],taken);now=max(tick,state['last_tick'])
    fine=(v['amount']-taken)*rules['shortfall_price'] if delta==POOR else 0
    if type(funds)==int:fine=min(fine,max(0,funds))
    fine=min(fine,1000000)
    if fine>0:
        state['phase']='fine';v['fine']=fine;_stage(db,binding,state,'fine',city,fine,ensure_ledger)
    else:_finish(state,now,{FULL:'full',PART:'part',POOR:'poor'}[delta],taken,delta,0)
    store(db,state,binding);return True

# ---- views ---------------------------------------------------------------------------------------------------------
def _days(ticks):return max(0,(ticks+DAY-1)//DAY)

def public_view(state):
    """What every player may see. No bids, no drawn good or amount before the arrival, no arrival day."""
    rules=state['spec'];phase=state['phase']
    out=dict(mode='progress',round=state['round'],rounds=rules['rounds'],phase='bidding' if phase=='bidding' else 'closing' if phase=='charging' else
             'travel' if phase=='travel' else 'visit' if phase in ('arrived','fine') else phase,
             goods=list(state['goods']) if phase in ('bidding','charging','travel','arrived','fine') else [],min_bid=rules['min_bid'],
             holder=state['holder'] if phase in ('travel','arrived','fine') else None,chosen=state['chosen'] if phase in ('travel','arrived','fine') else None,
             paid=state['paid'] if phase in ('travel','arrived','fine') else 0,favor=dict(state['favor']),results=copy.deepcopy(state['results']),
             winners=list(state['winners']),ended=state['ended'],price=rules['shortfall_price'])
    if phase=='bidding':out['close_days']=_days(state['close_tick']-state['last_tick'])
    if phase=='idle':out['first']=state['round']==0
    return out

def view(state,city):
    """The player's own values, with the public ones."""
    out=public_view(state);b=state['bids'].get(city)
    out['bid']=b['amount'] if b and state['phase'] in ('bidding','charging') else 0
    c=state['charge'];out['charging']=bool(c and c['city']==city)
    v=state['visit']
    out['order']=dict(id=v['id'],resource=v['resource'],amount=v['amount']) if v and state['holder']==city and state['phase']=='arrived' else None
    return out
