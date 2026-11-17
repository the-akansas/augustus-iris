"""Race for the Throne under 황위 시험 규칙 v1 (throne_rules.py): coup funding, gifts to the emperor, monthly paranoia.
Host side only; every value here is the caller's own (private) or public. Numbers: throne_rules.TEST_RULES_V1.

Money: a spend is one one-sided debit of the player's city (trade_post_ledger.stage_debit), the same native command
and receipt the cash gifts use. The flow, each step durable in the room DB:
  1. request  the host checks the request against the CURRENT state (a changed quote is returned for the player to
              confirm again), then in ONE transaction records the spend as 'charging' in the player's private record
              (with the coup draw already made and kept) and stages the debit command. Same request id again: the
              same spend comes back, nothing new is charged or drawn.
  2. charge   the city's engine applies the command only if its treasury covers it and keeps the receipt in its own
              save; the host learns the outcome from that receipt (cash_live reports), never from a client's word.
  3. settle   applied -> the effect is applied once ('done'); not applied or the city left -> 'void', no effect.
A save, a restart, a resend or a host change keeps all of this: the private record is sealed with the save
(throne_state), the debit contract and its command are in the cash checkpoint, the receipt is in the city save.
A restore-pending player's record is settled after it is handed in. Nothing is charged twice and nothing is drawn
twice; nothing takes effect unless the money was taken.

End of the trial (policy approved 2026-11-12): the first spend whose debit receipt is confirmed and whose final-stage
success the host settles ends it; spends confirmed in the same pass are taken in acceptance order ('seq', kept in each
private record). Requesting first or a debit not yet confirmed reserves nothing. A spend whose effect was not settled
by then never takes effect: not taken -> 'cancelled' (a command never handed to the city is withdrawn; one that may
be in the city's hands waits for its receipt), taken -> 'refunding' then 'refunded' when the city's own refund
receipt confirms the same amount came back. Spends settled before the end are kept (no refund of a failed coup or
an applied gift). New spends after the end are refused before anything is charged.

The emperor's punitive expedition (2026-11-14, rules 'expedition'; throne_state.step_raids keeps its clock):
  paranoia 100 -> preparing -> the legions arrive in the player's own city (its engine lets the original Caesar legions
  in when the player's view says order 'attack', and reports what it sees: raid_report). They attack at once.
  * tribute: a spend of kind 'tribute' (the fixed amount of the player's stage), allowed while they are there. When
    its debit is confirmed the legions are called back and paranoia drops by tribute_reduction (not below the stage
    floor). A confirmed tribute always counts, also when the legions were beaten in the meantime.
  * beaten: the city's engine reports that the legions are gone without having been called back -> paranoia drops
    by victory_reduction. The battle happens only in that player's game, so this report is that game's own word
    (like the visiting-army reports); money never depends on it.
  * neither within siege_months: 'sacked', the legions are called back, paranoia unchanged (step_raids).
  Then cooldown_months without a new expedition. The player's values and the order for its engine are in view().

Not implemented here: a victory or defeat screen. The final stage's success is recorded (winner) and shown as the
end of the trial."""
import hashlib,secrets
import throne_state as ts,throne_rules as tr

MONTH=tr.TICKS_PER_MONTH

def contract_id(request):
    """Ledger id of a spend. Derived from the private request id: not linkable to the public coup notice id."""
    return hashlib.sha256(b'augustus-throne-spend\x00'+request.encode()).hexdigest()[:32]

def is_test(binding):
    spec=ts.spec(binding);return bool(spec) and tr.is_test(spec['rules'])

def _state(db,binding):
    state=ts.current(db,binding)
    if state is None or not tr.is_test(state['spec']['rules']):raise ValueError('황위 쟁탈전 시나리오가 아닙니다.')
    return state

def _wait_text(ticks):
    months,rest=divmod(max(0,ticks),MONTH);days=(rest+49)//50
    return (f'{months}개월 ' if months else '')+(f'{days}일' if days else '')or '0일'

def _charging(secret):return next((e for e in secret['spends'] if e['state']=='charging'),None)

def quote(state,city,kind,amount,funds,tick):
    """What this request would do now. Pure: nothing changes. `funds` is the treasury the player's game shows; it only
    refuses early (the city's engine decides the debit itself)."""
    rules=state['spec']['rules'];p=state['players'][city]
    if 'pending' in p:return dict(kind=kind,ok=False,reason='내 비공개 기록을 새 방장에게 확인받는 중입니다(복원 대기). 황위 행동은 기다립니다.')
    s=p['secret'];stage=p['stage'];n=len(rules['stages'])
    base=dict(kind=kind,ok=False,reason='',amount=amount,charge=0)
    if type(amount)!=int or amount<1:return dict(base,reason='금액을 정해 주세요.')
    if state['ended']:return dict(base,reason='황위 쟁탈전 시험이 끝났습니다.')
    if p['eliminated']:return dict(base,reason='탈락한 도시입니다.')
    if _charging(s):return dict(base,reason='앞선 황위 지출을 처리하는 중입니다.')
    if amount>rules['max_spend']:return dict(base,reason=f"한 번에 {rules['max_spend']:,} Dn까지 낼 수 있습니다.")
    if type(funds)==int and amount>funds:return dict(base,reason=f'보유 자금({funds:,} Dn)보다 큰 금액입니다.')
    if kind=='coup':
        if stage>=n:return dict(base,reason='이미 마지막 단계까지 성공했습니다.')
        row=rules['stages'][stage];minimum=s['next_cost']
        out=dict(base,stage=stage+1,stage_name=row['name'],minimum=minimum,failures=s['failures'],
                 fail_next=tr.min_cost(rules,stage,s['failures']+1),cap=row['cap']*100,base_chance=row['chance']*100)
        if s['next_attempt_tick']>tick:return dict(out,reason='다음 쿠데타 지원까지 '+_wait_text(s['next_attempt_tick']-tick)+' 남았습니다.')
        if not tr.fundable(rules,minimum):return dict(out,reason=f"최소 지원금 {minimum:,} Dn이 1회 지출 한도({rules['max_spend']:,} Dn)를 넘어 이 단계에 더 도전할 수 없습니다.")
        if amount<minimum:return dict(out,reason=f'최소 지원금은 {minimum:,} Dn입니다.')
        chance=tr.chance_bp(rules,stage,minimum,amount)
        return dict(out,ok=True,charge=amount,chance=chance,chance_text=tr.percent(chance))
    if kind=='gift':
        if state['activated_tick'] is None:return dict(base,reason='평화의 시대: 황제는 아직 총독들의 충성을 의심하지 않습니다. 선물은 받지 않습니다.')
        plan=tr.gift_plan(rules,stage,s['paranoia'],amount)
        out=dict(base,limit=amount,before=s['paranoia'],**plan)
        if not plan['points']:
            reason='편집증이 이미 선물로 낮출 수 있는 최저치입니다.' if s['paranoia']<=plan['bottom'] else f"1점을 낮추려면 {plan['next_price']:,} Dn이 필요합니다."
            return dict(out,charge=0,reason=reason)
        return dict(out,ok=True)
    if kind=='tribute':
        e=s['expedition']
        if 'expedition' not in rules or e['phase']!='preparing':return dict(base,reason='황제군이 도시에 도착했습니다. 이제 공물은 받지 않습니다.' if e['phase'] in ('arrived','fighting') else '황제군이 오고 있을 때만 공물을 바칠 수 있습니다.')
        due=tr.raid_tribute(rules,tr.raid_stage(stage,s));after=tr.raid_relief(rules,stage,s['paranoia'],rules['expedition']['tribute_reduction'])
        out=dict(base,amount=due,before=s['paranoia'],after=after,points=s['paranoia']-after,floor=tr.base_floor(rules,stage))
        if amount!=due:return dict(out,reason=f'철수 공물은 {due:,} Dn입니다.')
        if type(funds)==int and due>funds:return dict(out,reason=f'보유 자금({funds:,} Dn)이 철수 공물 {due:,} Dn보다 적습니다.')
        return dict(out,ok=True,charge=due)
    raise ValueError('지원하지 않는 황위 행동입니다.')

def _forced_roll(db,city):
    """A coup roll fixed by the developer panel (dev_tools.py: a developer room or the test launcher); None otherwise."""
    try:import dev_tools
    except ImportError:return None
    return dev_tools.forced_roll(db,city)

def fingerprint(q):
    """What the player saw and confirmed. A request carrying another fingerprint gets the new quote back."""
    if not q.get('ok'):return None
    return [q['kind'],q['amount'],q['charge'],q.get('chance',0),q.get('points',0),
            q.get('stage'),q.get('minimum'),q.get('fail_next'),q.get('before'),q.get('after'),
            q.get('floor'),q.get('bottom'),q.get('rest')]

def _spend_view(e):
    return {k:e[k] for k in ('request','kind','amount','state','result','points','seq')}|({'chance':e['chance'],'chance_text':tr.percent(e['chance'])} if e['kind']=='coup' else {})

def _next_seq(db,state,tick):
    """Global high-water mark travels with the cash checkpoint, even when sealed records are not handed in yet.
    The row contains no city, request, action, amount, chance or result. Legacy checkpoints without it can have
    hidden sequences up to the old validator's bound; allocate beyond that bound rather than guessing their order.
    Caller holds the room transaction and rolls back this reservation if the spend cannot be staged."""
    db.execute('CREATE TABLE IF NOT EXISTS post_sequence(id INTEGER PRIMARY KEY CHECK(id=1), value INTEGER NOT NULL)')
    row=db.execute('SELECT value FROM post_sequence WHERE id=1').fetchone()
    known=[e['seq'] for p in state['players'].values() if 'secret' in p for e in p['secret']['spends']]
    high=row[0] if row else -1
    if not row and any('pending' in p for p in state['players'].values()):
        high=max(high,ts.MAX_TICK*1000+999)
    seq=max([tick*1000,high+1]+[q+1 for q in known])
    if seq>=2**63:raise ValueError('황위 접수 순번 범위를 초과했습니다.')
    db.execute('INSERT OR REPLACE INTO post_sequence(id,value) VALUES(1,?)',(seq,))
    return seq


def spend(db,binding,city,request,kind,amount,funds,expect,tick,ensure_ledger=lambda:None):
    """Step 1. Caller commits. Returns {state: charging|done|void|refused|requote, ...} for the caller only."""
    ts.hex32(request,'요청 번호');state=_state(db,binding)
    if city not in state['players']:raise ValueError('참가 도시가 아닙니다.')
    ts.integer(tick,state['last_tick'],ts.MAX_TICK,'요청 시각')
    for c,p in state['players'].items():
        if 'secret' not in p:continue
        e=next((e for e in p['secret']['spends'] if e['request']==request),None)
        if e and c==city:return dict(_spend_view(e),duplicate=True)                       # resent: same spend, nothing new
        if e:raise ValueError('사용할 수 없는 요청 번호입니다.')
    if ts.notice_ids(request)&{n['id'] for n in state['notices']}:raise ValueError('사용할 수 없는 요청 번호입니다.')
    changed=ts.advance(state,tick)
    q=quote(state,city,kind,amount,funds,tick)
    if not q['ok'] or fingerprint(q)!=expect:
        if changed:ts.store(db,state,binding)
        return dict(state='refused' if not q['ok'] else 'requote',quote=q)
    rules=state['spec']['rules'];p=state['players'][city];s=p['secret']
    ensure_ledger()
    e=dict(request=request,kind=kind,tick=tick,amount=q['charge'],stage=p['stage'],chance=0,roll=0,points=0,state='charging',result=None,done=None,seq=_next_seq(db,state,tick))
    forced=_forced_roll(db,city)
    if kind=='coup':e.update(chance=q['chance'],roll=forced if forced is not None else secrets.randbelow(10000))     # drawn once, kept, never drawn again
    else:e['points']=q['points']
    s['spends'].append(e)
    import trade_post_ledger
    trade_post_ledger.stage_debit(db,list(binding['cities']),city,contract_id(request),e['amount'])
    ts.store(db,state,binding)
    return dict(_spend_view(e),duplicate=False,quote=q)

def _activate(state,tick):
    rules=state['spec']['rules']
    state['activated_tick']=state['period_start_tick']=tick
    for p in state['players'].values():   # every known record starts at its stage floor (restore-pending: when handed in)
        if 'secret' in p:p['secret']['paranoia']=max(p['secret']['paranoia'],tr.base_floor(rules,p['stage']))

def _apply(state,city,e,tick):
    rules=state['spec']['rules'];p=state['players'][city];s=p['secret'];n=len(rules['stages'])
    if e['kind']=='gift':
        s['paranoia']=max(tr.gift_floor(rules,p['stage']),s['paranoia']-e['points']);s['gift_total']+=e['amount']
        e.update(state='done',result='reduced',done=tick);return
    if e['kind']=='tribute':
        # Paid: the legions are called back (the engine's order follows the phase) and the emperor is appeased.
        # The reduction is taken from the value at this moment (design 7.5), so gifts made meanwhile are kept.
        x=rules['expedition'];raid=s['expedition'];after=tr.raid_relief(rules,p['stage'],s['paranoia'],x['tribute_reduction'])
        e.update(state='done',result='withdrawn',done=tick,points=s['paranoia']-after);s['paranoia']=after
        if raid['phase']=='preparing':   # on the march: they turn back
            raid.update(phase='cooldown',result='tribute',tribute_paid=True,deadline_tick=tick+x['cooldown_months']*MONTH)
        return
    def notice(kind):state['notices'].append(dict(id=ts.notice_id(e['request'],kind),tick=tick,kind=kind))
    first=state['activated_tick'] is None   # the first valid coup funding wakes the emperor up: announced (popup)
    if first:_activate(state,tick)
    success=e['roll']<e['chance']
    if first and success:notice('coup_first')   # a first coup that fails is announced once, below
    e.update(state='done',result='success' if success else 'failure',done=tick)
    s['next_attempt_tick']=tick+rules['attempt_months']*MONTH
    if success:
        p['stage']+=1;s['failures']=0;s['next_cost']=ts.expected_cost(rules,p['stage'],0)
        s['paranoia']=max(s['paranoia'],tr.base_floor(rules,p['stage']))
        if p['stage']==n:state['winner']=city;state['ended']=True;notice('throne_taken')   # the end (fanfare)
        elif p['stage']==n-1 and not any(x['kind']=='final_stage' for x in state['notices']):notice('final_stage')   # only the FIRST stage-4 success of the room (popup); other successes: no notice
    else:
        s['failures']+=1;s['next_cost']=ts.expected_cost(rules,p['stage'],s['failures'])
        notice('coup_first_failed' if first else 'coup_failed');ts.hear(state)                  # anonymous; every player's paranoia +5 at once

def _ledger_row(db,request):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='post_contract'").fetchone():return None
    return db.execute('SELECT phase,exported,paid FROM post_contract WHERE id=?',(contract_id(request),)).fetchone()

REFUND_RETRY_BASE=30       # seconds after the first refund the city could not take
REFUND_RETRY_CAP=3600      # at most one new refund command per hour per spend while the city still cannot take it

def refund_retry_wait(tried):
    """Wait before the next refund command, after `tried` refund commands the city's receipts said it could not take.
    Counted per spend from the ledger (post_command, part of the cash checkpoint), so a reconnect, a restart or a host
    change never resets it. Bounds the records a blocked refund adds (one command and one receipt per try)."""
    return min(REFUND_RETRY_CAP,REFUND_RETRY_BASE*2**min(max(tried,1)-1,16))

def _retry_due(db,request):
    """A refund the city could not take (definite unapplied receipt) is tried again with a new command only after the
    back-off of this spend: refund_retry_wait(number of refund commands so far), from its last delivery."""
    import time
    cid=contract_id(request)
    last=db.execute("SELECT id FROM post_command WHERE contract=? AND step='pay' ORDER BY attempt DESC LIMIT 1",(cid,)).fetchone()
    if not last:return True
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='cash_retry'").fetchone():return True
    due=db.execute('SELECT next_time FROM cash_retry WHERE command=?',(last[0],)).fetchone()
    if due is None:return False
    tried=db.execute("SELECT count(*) FROM post_command WHERE contract=? AND step='pay'",(cid,)).fetchone()[0]
    return time.time()>=due[0]+refund_retry_wait(tried)

def settle(db,binding,tick,ensure_ledger=lambda:None):
    """Steps 2-3 for every known record in acceptance order, refunds after the end, and the monthly rise up to `tick`.
    Idempotent. Caller commits. Returns True when the state changed."""
    if not is_test(binding):return False
    import trade_post_ledger
    state=ts.current(db,binding)
    changed=ts.advance(state,max(tick,state['last_tick']))
    changed|=ts.hear(state)   # a record handed in after a restore catches up on announced failures
    now=state['last_tick']
    ended=state['ended']
    for _ in range(2):   # a second pass when this pass ended the trial: earlier-accepted spends are then re-checked
        changed|=_settle_pass(db,binding,state,now,ensure_ledger)
        if state['ended']==ended:break
        ended=state['ended']
    changed|=ts.step_raids(state,now)   # paranoia that just reached 100, a tribute that was not taken, the end
    if changed:ts.store(db,state,binding)
    return changed

RAID_ATTACKING,RAID_WITHDRAWING,RAID_BEATEN,RAID_LEFT=1,2,3,4   # what a city's engine says of its expedition (emperor_raid.inc)

def raid_report(db,binding,city,count,seen,tick):
    """The city's own engine reports its expedition number `count`: the legions are in the city (attacking), or they
    are gone without having been called back (beaten or routed). Anything else, another number, or a record that
    is not waiting for it changes nothing; the same report again changes nothing. Caller commits."""
    state=_state(db,binding)
    if city not in state['players']:raise ValueError('참가 도시가 아닙니다.')
    ts.integer(count,1,1000000,'원정 번호');ts.integer(seen,0,4,'원정 상태');ts.integer(tick,0,ts.MAX_TICK,'보고 시각')
    changed=ts.advance(state,max(tick,state['last_tick']));now=state['last_tick']
    p=state['players'][city];rules=state['spec']['rules']
    if 'secret' in p and 'expedition' in rules and not state['ended'] and not p['eliminated']:
        s=p['secret'];e=s['expedition'];x=rules['expedition']
        paying=any(sp['kind']=='tribute' and sp['state']=='charging' for sp in s['spends'])
        if e['count']==count and e['phase'] in ('arrived','fighting'):
            if seen==RAID_ATTACKING and e['phase']=='arrived':
                e.update(phase='fighting',deadline_tick=now+x['siege_months']*MONTH);changed=True   # the siege time runs from here
            elif seen==RAID_BEATEN and not paying:   # a tribute under way is settled first (it counts if it was taken)
                s['paranoia']=tr.raid_relief(rules,p['stage'],s['paranoia'],x['victory_reduction'])
                e.update(phase='cooldown',result='defeated',deadline_tick=now+x['cooldown_months']*MONTH);changed=True
    if changed:ts.store(db,state,binding)
    return changed

def _settle_pass(db,binding,state,now,ensure_ledger):
    import trade_post_ledger
    changed=False
    work=sorted((e['seq'],e['request'],city,e) for city,p in state['players'].items() if 'secret' in p   # restore-pending: after hand-in
                for e in p['secret']['spends'] if e['state'] in ('charging','refunding'))
    for _,request,city,e in work:
        row=_ledger_row(db,request)
        if e['state']=='charging':
            if row is None:
                # The record says 'charging' but this ledger has no debit (e.g. restored from a copy without it): stage the
                # same command again. Same id and digest: a receipt the city already holds settles it, nothing is doubled.
                ensure_ledger()
                trade_post_ledger.stage_debit(db,list(binding['cities']),city,contract_id(request),e['amount']);changed=True;continue
            if row['phase']=='complete' and row['exported']:
                if state['ended']:                                    # taken, but the trial ended first: pay it back
                    trade_post_ledger.stage_refund(db,contract_id(request));e.update(state='refunding',result='ended',done=now)
                else:_apply(state,city,e,now)                        # may end the trial: later ones in this pass refund
                changed=True
            elif row['phase']=='cancelled':
                e.update(state='cancelled',result='ended',done=now) if state['ended'] else e.update(state='void',result='void',done=now);changed=True
            elif state['ended'] and trade_post_ledger.withdraw_debit(db,contract_id(request)):
                e.update(state='cancelled',result='ended',done=now);changed=True
            # otherwise the command may be in the city's hands: its receipt decides (shown as "차감 확인·취소 처리 중")
        elif row is not None:                                         # refunding
            if row['paid']:e.update(state='refunded',done=now);changed=True
            elif row['phase']=='blocked:pay' and _retry_due(db,request):trade_post_ledger.stage_refund(db,contract_id(request));changed=True
    return changed

def view(state,city,tick,db=None):
    """The player's own throne panel. Only this player's values; the rest is public (stage numbers) or rules."""
    rules=state['spec']['rules'];p=state['players'][city];n=len(rules['stages'])
    out=dict(rules=rules['label'],test=True,active=state['activated_tick'] is not None,ended=state['ended'],winner_is_me=state['winner']==city,
             stage=p['stage'],stages=n)
    if 'pending' in p:return dict(out,restoring=True)
    s=p['secret'];stage=p['stage']
    out.update(restoring=False,paranoia=s['paranoia'],floor=tr.base_floor(rules,stage),gift_floor=tr.gift_floor(rules,stage),
               failures=s['failures'],next_cost=s['next_cost'],stage_name=rules['stages'][stage]['name'] if stage<n else '',
               wait=_wait_text(s['next_attempt_tick']-tick) if s['next_attempt_tick']>tick else '',gift_total=s['gift_total'],
               expedition_due=s['paranoia']>=rules['paranoia_max'],gift_price=rules['gift_price'],gift_price_below=rules['gift_price_below'],max_spend=rules['max_spend'])
    if 'expedition' in rules:
        # The player's own expedition and what its engine must do about it: 'attack' while the legions belong in
        # the city, 'withdraw' once that expedition is over (paid, sacked, called off), nothing before the first.
        e=s['expedition'];x=rules['expedition']
        out['raid']=dict(phase=e['phase'],id=e['id'],count=e['count'],result=e['result'],size=tr.raid_size(rules,e['count']) if e['count'] else 0,
                         tribute=tr.raid_tribute(rules,tr.raid_stage(stage,s)),wait=_wait_text(e['deadline_tick']-tick).strip() if e['deadline_tick'] is not None and e['deadline_tick']>tick else '',
                         order='attack' if e['phase'] in ('arrived','fighting') else 'withdraw' if e['count'] and e['phase'] in ('resolved','cooldown','idle') else '',
                         after_tribute=tr.raid_relief(rules,stage,s['paranoia'],x['tribute_reduction']),after_victory=tr.raid_relief(rules,stage,s['paranoia'],x['victory_reduction']),
                         paying=any(sp['kind']=='tribute' and sp['state']=='charging' for sp in s['spends']))
    out['limit_reached']=stage<n and not tr.fundable(rules,s['next_cost'])
    # what the coup dialog shows before any quote (the bridge prepares it so a click opens it at once, 2026-11-15)
    if stage<n:out.update(next_chance=rules['stages'][stage]['chance']*100,next_cap=rules['stages'][stage]['cap']*100,
                           fail_next=tr.min_cost(rules,stage,s['failures']+1),eliminated=p['eliminated'])
    busy=[e for e in s['spends'] if e['state'] in ('charging','refunding')]
    out['charging']=[_spend_view(e)|({'refund_blocked':db is not None and _ledger_row(db,e['request']) is not None and _ledger_row(db,e['request'])['phase']=='blocked:pay'} if e['state']=='refunding' else {}) for e in busy]
    done=[e for e in s['spends'] if e['state'] not in ('charging','refunding')]
    out['last']=_spend_view(done[-1]) if done else None
    return out
