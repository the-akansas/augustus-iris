"""Race for the Throne: coup attempts, the public/private split of everything about them, and handing private records
back to a new host. State layout and the sealing scheme: throne_state.py.

Decided and implemented:
  * Paranoia is per player and private to that player. Failures, next cost and the attempts themselves are private too.
  * Every attempt is announced to everyone with the original confirm-and-close message, naming no one. The notice id is
    derived from the private request id, so a re-run of the same request (resend, restore, new host) is the same notice.
  * The first attempt switches the paranoia display on for everyone (public 'active'); it changes nobody's value.
  * 황위 시험 규칙 v1 (2026-11-13, user): only the first coup (popup), a stage-4 success (popup), every failure and the
    end (fanfare lines in the notice tab) are announced, all naming no one; other successes are not announced. A
    failure raises every player's paranoia by 5 at once (throne_state.hear). Format-1 rooms keep 'coup_attempt'.
  * The public coup rank (stage) is public; a success that raises it lets others infer who succeeded (allowed).
  * Host change, save and resume keep every private value (sealed commitments + each player's own opening).
  * The emperor's paranoia and the original favour are separate: nothing here reads or writes the original favour,
    the original emperor's army, salary, gifts or tribute.

Not decided, so not implemented: how paranoia changes, cost, chance, investment, resolution, gifts, victory, defeat,
the throne expedition's battle. begin_attempt records the start only and charges nothing; no player-facing button.

Decided for when ranking/victory is implemented (policy 2026-11-12, docs/개편-9단계-황위-복원정책.md):
  a restore-pending player is never treated as defeated, eliminated or zero; public scores stay and show 'restoring';
  a ranking or victory that depends on a still-sealed secret is provisional (no final result, no automatic winner);
  results that do not depend on it are final as usual.
"""
import throne_state

NOTICE={'coup_attempt':('쿠데타 시도 발생','누군가 황제를 몰아내려는 쿠데타를 시도했습니다. 누가 시도했는지는 알려지지 않았습니다.\n'
                        '황제의 편집증이 깨어났습니다. 각자 화면 오른쪽 위에서 자기 수치만 확인할 수 있습니다.\n'
                        '황제 호감도(원본 자문관)와는 별개의 수치입니다.'),
        # 황위 시험 규칙 v1 (2026-11-13): popup only for the first coup and a stage-4 success; the rest is a fanfare line
        'coup_first':('쿠데타 시도 발생','누군가 황제를 몰아내려는 쿠데타를 시도했습니다. 누가 시도했는지는 알려지지 않았습니다.\n'
                        '황제의 편집증이 깨어났습니다. 각자 화면 오른쪽 위에서 자기 수치만 확인할 수 있습니다.\n'
                        '이후의 쿠데타는 실패했을 때만 알려집니다. 실패할 때마다 모든 총독의 편집증이 오릅니다.\n'
                        '황제 호감도(원본 자문관)와는 별개의 수치입니다.'),
        'final_stage':('황궁 내부 장악','누군가 쿠데타 4단계 "황궁 내부 장악"에 성공했습니다. 누구인지는 알려지지 않았습니다.\n'
                        '이제 그 총독에게는 마지막 단계 "황제 폐위"만 남았습니다.'),
        'coup_failed':('쿠데타 실패','누군가의 쿠데타가 실패했습니다. 누구인지는 알려지지 않았습니다.\n황제의 의심이 커져 모든 총독의 편집증이 올랐습니다.'),
        'coup_first_failed':('쿠데타 시도 발생','누군가 황제를 몰아내려는 쿠데타를 시도했으나 실패했습니다. 누구인지는 알려지지 않았습니다.\n'
                        '황제의 편집증이 깨어났습니다. 각자 화면 오른쪽 위에서 자기 수치만 확인할 수 있습니다.\n'
                        '쿠데타가 실패할 때마다 모든 총독의 편집증이 오릅니다.'),
        'throne_taken':('황제 폐위','누군가 마지막 단계 "황제 폐위"에 성공해 황위 쟁탈전이 끝났습니다.')}
# Confirm-and-close message (2026-11-14: a failure too). The end is shown by the scoreboard, not by a message.
POPUP=('coup_attempt','coup_first','final_stage','coup_failed','coup_first_failed')
LINE={'throne_taken':'황제 폐위, 황위 쟁탈전 종료'}   # short: one card line
MOODS=('평온','불안','동요','위태로움','폭풍 전야')   # the leading plot's completed stages 0..4, in words

def scoreboard(value):
    """The end: every value is shown to everyone (the game is over). Rows best first: completed stages, then who
    reached that stage earlier. A restore-pending record has no known values (known=False). Only spends whose money
    was really taken and kept count (refunded and cancelled ones do not)."""
    rows=[]
    for city,p in value['players'].items():
        s=p.get('secret');row=dict(city=city,stage=p['stage'],winner=value['winner']==city,known=s is not None)
        if s is not None:
            done=[e for e in s.get('spends',()) if e['state']=='done']
            wins=[e for e in done if e['kind']=='coup' and e['result']=='success']
            row.update(successes=len(wins),failures=sum(1 for e in done if e['kind']=='coup' and e['result']=='failure'),
                       coup_total=sum(e['amount'] for e in done if e['kind']=='coup'),gift_total=sum(e['amount'] for e in done if e['kind']=='gift'),
                       raids=s['expedition']['count'],tributes=sum(1 for e in done if e['kind']=='tribute'),paranoia=s['paranoia'],
                       reached=max((e['done'] for e in wins),default=0))
        rows.append(row)
    rows.sort(key=lambda r:(-r['stage'],r.get('reached',0),r['city']))
    return rows

def initialize(db):throne_state.initialize(db)

def _state(db,binding):
    if throne_state.spec(binding) is None:raise ValueError('황위 쟁탈전 시나리오가 아닙니다.')
    return throne_state.current(db,binding)

def begin_attempt(db,binding,city,request,tick):
    """Record the start of one coup attempt by `city`. Returns only what the caller may see about its own request.
    Rule format 1 only; under the test rules an attempt is a spend (throne_play.spend)."""
    throne_state.hex32(request,'요청 번호');state=_state(db,binding)
    if throne_state.throne_rules.is_test(state['spec']['rules']):raise ValueError('시험 규칙에서는 쿠데타 지원(throne_spend)으로 시도합니다.')
    if city not in state['players']:raise ValueError('참가 도시가 아닙니다.')
    me=state['players'][city]
    if 'pending' in me:raise ValueError('이 도시의 비공개 기록이 아직 복원되지 않았습니다(복원 대기).')
    notice=throne_state.notice_id(request)
    if any(a['request']==request for a in me['secret']['attempts']):return dict(request=request,notice=notice,duplicate=True)   # resent
    if any(a['request']==request for c,p in state['players'].items() if c!=city and 'secret' in p for a in p['secret']['attempts']):raise ValueError('사용할 수 없는 요청 번호입니다.')
    if any(n['id']==notice for n in state['notices']):raise ValueError('사용할 수 없는 요청 번호입니다.')   # a pending record's attempt
    throne_state.integer(tick,state['last_tick'],throne_state.MAX_TICK,'시도 시각')
    if state['ended']:raise ValueError('황위 쟁탈전이 끝났습니다.')
    if me['eliminated']:raise ValueError('탈락한 도시입니다.')
    if state['activated_tick'] is None:state['activated_tick']=state['period_start_tick']=tick   # first attempt: display on for all
    state['last_tick']=tick
    me['secret']['attempts'].append(dict(request=request,notice=notice,tick=tick,state='started'))
    state['notices'].append(dict(id=notice,tick=tick,kind='coup_attempt'))
    throne_state.store(db,state,binding)
    return dict(request=request,notice=notice,duplicate=False)

def own(db,binding,city):
    """The caller's own private values (only ever returned to that city). Values stay whatever the undecided rules
    leave them (0 today); 'rules' says the paranoia rules are not connected yet."""
    state=_state(db,binding)
    if city not in state['players']:raise ValueError('참가 도시가 아닙니다.')
    p=state['players'][city]
    protected=set()
    for sid in {latest_sealed(db),throne_state.handover_save(db,binding)}-{None}:
        row=db.execute('SELECT ticks FROM joint_save WHERE id=?',(sid,)).fetchone()
        sealed=throne_state.sealed_save(db,sid,binding,row[0])
        protected.add(sealed['players'][city]['sealed']['commit'])
    if 'pending' in p:protected.add(p['pending']['commit'])
    protected=sorted(protected)
    import throne_play
    extra=throne_play.view(state,city,state['last_tick'],db) if throne_play.is_test(binding) else {}   # 황위 시험 규칙 v1
    if 'pending' in p:return dict(extra,active=state['activated_tick'] is not None,restoring=True,commit=p['pending']['commit'],protected_commits=protected)
    s=p['secret']
    return dict(extra,protected_commits=protected,active=state['activated_tick'] is not None,restoring=False,paranoia=s['paranoia'],failures=s['failures'],next_cost=s['next_cost'],
                attempts=[dict(request=a['request'],tick=a['tick'],state=a['state']) for a in s['attempts']],rules=extra.get('rules','undecided'))

def own_opening(db,binding,city,sid):
    """The caller's own opening for joint save `sid` (host DB). The player keeps it to hand back to a later host."""
    _state(db,binding)
    row=db.execute("SELECT ticks FROM joint_save WHERE id=? AND state='complete'",(sid,)).fetchone()
    if not row:raise ValueError('완료된 공동 저장이 아닙니다.')
    sealed=throne_state.sealed_save(db,sid,binding,row[0]);found=throne_state.opening(db,sid,city)
    if not sealed or not found:return None
    entry=sealed['players'][city]['sealed']
    return dict(save_id=sid,commit=entry['commit'],tick=entry['tick'],secret=found[0],nonce=found[1])

def hand_in(db,binding,city,secret,nonce,tick=None):
    """A restoring player's own opening. Stored only if it matches the commitment of the restored save; the player's
    personal deadlines are protected for the time it was pending (throne_state.protect_deadlines, once).
    A wrong record is refused with a reason; a record that has not arrived yet simply leaves the player pending."""
    state=_state(db,binding)
    changed=throne_state.reveal(state,binding,city,secret,nonce,None if tick is None else max(tick,state['last_tick']))
    if changed:throne_state.store(db,state,binding)
    return dict(restored=changed)

def confirm_stored(db,binding,city,sid,commit):
    """The player's PC wrote its opening for save `sid` to disk and read it back (sent only after that)."""
    _state(db,binding);return throne_state.confirm_custody(db,binding,sid,city,commit)

def latest_sealed(db):
    row=db.execute('SELECT max(id) FROM joint_save WHERE throne_version=?',(throne_state.VERSION,)).fetchone()
    return row[0] if row else None

def public_status(db,binding):
    """Everything every client may see. None outside the throne mode. Never a private value or an attempt's owner."""
    if throne_state.spec(binding) is None:return None
    view=throne_state.public_view(throne_state.current(db,binding))   # read only (tables are made at room setup)
    notices=[dict(id=n['id'],tick=n['tick'],title=NOTICE[n['kind']][0],body=NOTICE[n['kind']][1],popup=n['kind'] in POPUP,line=LINE.get(n['kind'],NOTICE[n['kind']][0])) for n in view['notices']]
    # Fully anonymous (2026-11-14): no per-city stage leaves the host while the race is on, only the leading plot's
    # stage. At the end the scoreboard shows everything.
    live=throne_state.current(db,binding);leading=max((p['stage'] for p in view['players'].values()),default=0)
    return dict(active=view['activated_tick'] is not None,activated_tick=view['activated_tick'],notices=notices,
                leading=leading,mood=MOODS[min(leading,len(MOODS)-1)],scoreboard=scoreboard(live) if view['ended'] else None,
                eliminated={c:p['eliminated'] for c,p in view['players'].items()},
                restoring=sorted(c for c,p in view['players'].items() if p['restoring']),sealed_save=latest_sealed(db),
                handover_save=throne_state.handover_save(db,binding),
                ended=view['ended'],winner=view['winner'])
