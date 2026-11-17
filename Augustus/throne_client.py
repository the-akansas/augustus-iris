from windows_paths import sqlite_readonly_uri
"""Race for the Throne on a player's PC (called by game_bridge with the public lobby status).

  * HUD ("황제 편집증"): built from the player's OWN values (op throne_mine), never from another player's.
  * After every sealed joint save the player fetches its own opening (op throne_opening) and keeps it on this PC
    (folder throne-own, one file per commitment). Only this player's own secret is in it. The file is written to a
    temporary name, flushed and fsync'ed, renamed in place, then READ BACK and checked against the commitment; only
    then is op throne_opening_stored sent. Receiving the opening is not the same as having stored it.
  * When a new host restored from a backup and this player is 'restoring', the matching opening is handed in
    (op throne_hand_in); the host accepts it only if it matches the sealed save. If this session's folder lacks it,
    the records this PC already keeps are searched once (recover_opening). Not found: the player stays 'restoring'
    with its secret state intact (no reset, no new key, no elimination); only throne actions wait.
Errors never stop the bridge: the next status poll retries.
"""
import json,os,sqlite3,hashlib
from contextlib import closing
from pathlib import Path
KEEP=40

def folder(bridge):
    path=Path(bridge.root).parent/'throne-own';path.mkdir(parents=True,exist_ok=True);return path

def keep_opening(path,city,opening):
    """Durably store one opening; True only when the stored copy reads back and matches its commitment."""
    if not opening or not isinstance(opening.get('commit'),str) or len(opening['commit'])!=64:return False
    import throne_state
    if throne_state.commit(city,opening['tick'],opening['secret'],opening['nonce'])!=opening['commit']:return False
    target=path/(opening['commit']+'.json');temporary=target.with_suffix('.tmp')
    with open(temporary,'w',encoding='utf-8') as f:
        f.write(json.dumps(opening,ensure_ascii=False));f.flush();os.fsync(f.fileno())
    os.replace(temporary,target)
    try:
        d=os.open(path,os.O_RDONLY);os.fsync(d);os.close(d)          # the rename itself (not available on Windows)
    except OSError:pass
    back=find_opening(path,opening['commit'])
    if not back or throne_state.commit(city,back['tick'],back['secret'],back['nonce'])!=opening['commit']:return False
    prune_openings(path,city,opening['commit'])
    return True

def valid_commit(value):
    return isinstance(value,str) and len(value)==64 and all(c in '0123456789abcdef' for c in value)

def protect_openings(path,session,city,commits):
    # Persist the server's current/hand-over/pending references BEFORE accepting any new record.
    if not isinstance(commits,list) or not all(valid_commit(c) for c in commits):raise ValueError('invalid recovery references')
    directory=path/'protected';directory.mkdir(exist_ok=True)
    key=hashlib.sha256(json.dumps([session,city]).encode()).hexdigest()
    target=directory/(key+'.json');temp=target.with_suffix('.tmp')
    try:
        if json.loads(target.read_text(encoding='utf8'))==commits:return
    except (OSError,ValueError):pass
    with open(temp,'w',encoding='utf8') as f:
        json.dump(commits,f);f.flush();os.fsync(f.fileno())
    os.replace(temp,target)

def prune_openings(path,city,current):
    # Forty recent records PLUS records referenced by retained backups or live recovery points.
    # Inaccessible/corrupt reference data is not permission to delete a possibly necessary record.
    try:
        pins={current}
        for p in (path/'protected').glob('*.json'):
            values=json.loads(p.read_text(encoding='utf8'))
            if not isinstance(values,list) or not all(valid_commit(c) for c in values):return
            pins.update(values)
        for p in path.parent.glob('host-backup-*/room.sqlite'):
            with closing(sqlite3.connect(sqlite_readonly_uri(p),uri=True)) as db:
                if not db.execute("SELECT 1 FROM sqlite_master WHERE name='joint_throne'").fetchone():continue
                for body,digest in db.execute('SELECT payload,hash FROM joint_throne'):
                    if hashlib.sha256(body.encode()).hexdigest()!=digest:return
                    data=json.loads(body)
                    # Pin every referenced commitment: this folder may contain this user's other city records.
                    for player in data['players'].values():
                        sealed=player.get('sealed')
                        if sealed:
                            if not valid_commit(sealed.get('commit')):return
                            pins.add(sealed['commit'])
        files=sorted((p for p in path.glob('*.json') if valid_commit(p.stem)),key=lambda p:(p.stat().st_mtime_ns,p.name))
        for old in files[:-KEEP]:
            if old.stem not in pins:old.unlink(missing_ok=True)
    except (OSError,ValueError,TypeError,KeyError,sqlite3.Error):return

def find_opening(path,commit):
    if not valid_commit(commit):return None
    try:return json.loads((path/(commit+'.json')).read_text(encoding='utf-8'))
    except (OSError,ValueError,TypeError):return None

def _matches(city,commit,record):
    import throne_state
    try:return throne_state.commit(city,record['tick'],record['secret'],record['nonce'])==commit
    except (KeyError,TypeError,ValueError,AttributeError):return False

def recover_opening(path,city,commit):
    """The player's own opening for `commit` when this session's folder does not have it (lost or never copied
    here, e.g. the game was started again and now runs in a new network-play-* folder). Looks only at records this
    PC already keeps, read-only:
      1. the throne-own folders of this PC's other sessions (rooms/network-play-*/throne-own);
      2. this PC's own host databases (rooms/network-play-*/host-*/room.sqlite, rooms/game-*/room.sqlite), which
         hold the openings of the saves this PC hosted - only this city's rows are read.
    A record counts only if it matches the commitment (which binds city, save tick, secret and nonce). The match is
    copied into this session's folder (keep_opening: durable, read back, protected) and returned. None if nothing
    matches: the player simply stays 'restoring'. Nothing is reset, replaced or sent anywhere else."""
    if not valid_commit(commit):return None
    rooms=path.parent.parent
    found=None
    try:candidates=sorted(rooms.glob('network-play-*/throne-own/'+commit+'.json'))
    except OSError:candidates=[]
    for other in candidates:
        if other.parent==path:continue
        record=find_opening(other.parent,commit)
        if record and _matches(city,commit,record):found=record;break
    if found is None:
        try:databases=sorted(rooms.glob('network-play-*/host-*/room.sqlite'))+sorted(rooms.glob('game-*/room.sqlite'))
        except OSError:databases=[]
        for database in databases:
            try:
                with closing(sqlite3.connect(sqlite_readonly_uri(database),uri=True)) as db:
                    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='joint_throne_secret'").fetchone():continue
                    for sid,payload,nonce,body in db.execute('SELECT s.id,s.payload,s.nonce,t.payload FROM joint_throne_secret s JOIN joint_throne t ON t.id=s.id WHERE s.city=? ORDER BY s.id DESC',(city,)):
                        sealed=json.loads(body)['players'][city]['sealed']
                        if sealed.get('commit')!=commit:continue
                        record=dict(save_id=sid,commit=commit,tick=sealed['tick'],secret=json.loads(payload),nonce=nonce)
                        if _matches(city,commit,record):found=record;break
            except (OSError,ValueError,TypeError,KeyError,sqlite3.Error):continue
            if found:break
    if found is None:return None
    return found if keep_opening(path,city,dict(found,commit=commit)) else None

def hud_lines(own,ui=None):
    """The old text box (throne-hud.txt) is gone: the game draws the box from throne-box.txt (2026-11-14)."""
    return []

# ---- confirmed plan 2026-11-14: the box, the dialogs, the march card and the scoreboard --------------------------------
# The game draws; every text and number is prepared here (window/multiplayer_throne.inc reads the three files).
#   throne-box.txt     key<TAB>value lines for the box in the city view, the Rome panel and the march card
#   throne-dialog.txt  the open dialog (coup / gift / tribute), empty when none
#   throne-score.txt   the scoreboard at the end, empty before
# No arrows, middle dots or other special signs in any text (they break in other languages' fonts).
COUP_TEXT=('황제에게 불만을 품은 원로원 의원과 장교들을 비밀리에 한데 모읍니다.',
           '원로원 의원들을 매수해 황제에게 등을 돌리게 합니다.',
           '황제의 근위대 지휘관들을 매수해 결정적인 순간에 황궁을 비우게 합니다.',
           '황궁의 시종과 관리들을 포섭해 황제를 고립시킵니다.',
           '준비한 모든 것을 걸고 황제를 끌어내립니다. 성공하면 황제가 됩니다.')
NOTE_SECONDS=8
def _line(*parts):return '\t'.join(str(p).replace('\t',' ').replace('\r',' ').replace('\n',' ') for p in parts)+'\n'
def _dn(v):return f'{v:,} Dn'

def box_file(own,public,ui,now):
    """The box. state: off (not a throne game) / restoring / peace / active / ended."""
    if not own or not own.get('test'):return ''
    public=public or {}
    state='restoring' if own.get('restoring') else 'ended' if own.get('ended') else 'active' if own.get('active') else 'peace'
    out=_line('state',state)+_line('stages',own.get('stages',5))+_line('leading',public.get('leading',0))+_line('mood','제국 정세: '+public.get('mood','평온'))
    if state=='restoring':return out+_line('note','내 기록을 새 방장에게 확인받는 중입니다. 황위 행동은 기다립니다.')
    busy=bool(own.get('charging'));open_stage=own['stage']<own['stages']
    out+=_line('paranoia',own['paranoia'])+_line('mine',own['stage'])
    out+=_line('coup',int(state in ('peace','active') and open_stage and not busy and not own.get('limit_reached')))+_line('gift',int(state=='active' and not busy))
    note=ui.get('note') if ui.get('note_until',0)>now else ''
    last=own.get('last') or {};charging=own.get('charging') or []
    if isinstance(charging,dict):charging=[charging]
    if state=='ended':   # what happens to my money that was under way when the race ended (never shown as a coup result)
        if any(e.get('refund_blocked') for e in charging):note='황위 쟁탈전이 끝나 취소된 지출을 돌려받을 차례지만 도시가 지금 받을 수 없습니다. 권리는 유지되며 다시 시도합니다.'
        elif any(e['state']=='refunding' for e in charging):note='황위 쟁탈전이 끝나 취소된 지출을 돌려받는 중입니다.'
        elif charging:note='황위 쟁탈전이 끝났습니다. 처리 중이던 지출은 취소되며, 이미 빠진 돈은 전액 돌려받습니다.'
        elif last.get('state')=='refunded':note=f"황위 쟁탈전이 끝나 취소된 지출 {last['amount']:,} Dn을 돌려받았습니다."
        elif last.get('state')=='cancelled':note='황위 쟁탈전이 끝나 처리 중이던 지출이 취소되었습니다. 차감된 돈은 없습니다.'
    elif not note and busy:note='황위 지출을 처리하는 중입니다. 도시 자금 차감을 확인하고 있습니다.'
    elif not note and own.get('limit_reached'):note=f"최소 지원금 {own['next_cost']:,} Dn이 1회 지출 한도를 넘어 이 단계에 더 도전할 수 없습니다."
    elif not note and last.get('state')=='void':note='지난 황위 지출은 도시 자금이 차감되지 않아 무효가 되었습니다.'
    if note:out+=_line('note',note)
    raid=own.get('raid') or {}
    if raid.get('phase')=='preparing' and state=='active':
        out+=_line('march','황제군이 오고 있습니다','도착까지 '+(raid.get('wait') or '0일'),int(not busy))
    return out

def _calc(own,q,mode):
    """The rule values the game calculates the amount's effect with (multiplayer_throne.inc th_local)."""
    if mode=='coup':return (q.get('minimum',own.get('next_cost',0)),q.get('base_chance',0),q.get('cap',0),q.get('fail_next',0),own.get('max_spend',1000000))
    return (own['paranoia'],own['floor'],own['gift_floor'],own.get('gift_price',200),own.get('gift_price_below',600),own.get('max_spend',1000000))

def dialog_file(own,ui):
    q=ui.get('quote');mode=ui.get('mode')
    if not mode or not q or not own or own.get('restoring'):return ''
    out=_line('kind',mode);amount=ui.get('amount',0)
    if mode=='coup':
        stage=q.get('stage',own['stage']+1)-1
        out+=_line('title','쿠데타 지원')+_line('subtitle',f"다음 쿠데타: {q.get('stage_name',own.get('stage_name',''))} (완료 {own['stage']}단계)")
        out+=_line('desc',COUP_TEXT[min(stage,len(COUP_TEXT)-1)])+_line('small',f"기본 성공률 {q.get('base_chance',0)//100}%, 상한 {q.get('cap',0)//100}%")
        lowest=q.get('minimum',own.get('next_cost',0))
        out+=_line('row','최소 지원금',_dn(lowest))+_line('amount','지원 금액',_dn(amount),amount,lowest,own.get('max_spend',1000000))
        # the rules for the game to calculate the amount's effect itself (user 2026-11-14): minimum, base chance, cap,
        # next minimum after a failure, highest spend; can a coup be funded now apart from the amount, and why not
        ready=bool(q.get('ok')) or q.get('reason','').startswith('보유 자금(')
        out+=_line('calc','coup',*_calc(own,q,'coup'),int(ready),'' if ready else q.get('reason',''))
        out+=_line('low','예상 성공률',q['chance_text'] if q.get('ok') else '-')+_line('low','실패 시 다음 최소 지원금',_dn(q['fail_next']) if 'fail_next' in q else '-')
        out+=_line('hint','처음 지원하면 편집증이 깨어납니다. 누가 했는지는 비밀입니다.' if not own.get('active') else '지원금은 성공, 실패와 관계없이 모두 사용됩니다.')
        go='쿠데타 지원'
    elif mode=='gift':
        out+=_line('title','충성선물')+_line('subtitle','황제에게 충성을 보여 의심을 누그러뜨립니다')
        if ui.get('funds') is not None:out+=_line('row','보유 자금',_dn(ui['funds']))
        out+=_line('bar','황제의 의심',f"{own['paranoia']} / 100",own['paranoia'])
        out+=_line('row',f"기준 하한 (1점 {own.get('gift_price',200):,} Dn)",own['floor'])+_line('row',f"선물 최저치 (1점 {own.get('gift_price_below',600):,} Dn)",own['gift_floor'])
        out+=_line('amount','선물 한도',_dn(amount),amount,0,own.get('max_spend',1000000))
        # the rules for the game's own calculation: paranoia, stage floor, gift floor, the two prices, highest spend
        why='' if own.get('active') else '평화의 시대: 황제는 아직 총독들의 충성을 의심하지 않습니다. 선물은 받지 않습니다.'
        if not why and own.get('ended'):why='황위 쟁탈전 시험이 끝났습니다.'
        if not why and own.get('charging'):why='앞선 황위 지출을 처리하는 중입니다.'
        out+=_line('calc','gift',*_calc(own,q,'gift'),int(not why),why)
        out+=_line('low','예상 감소','-'+str(q['points']) if q.get('points') else '-')+_line('low','선물 후 편집증',q['after'] if 'after' in q else own['paranoia'])+_line('low','실제 차감',_dn(q.get('charge',0)))
        out+=_line('hint','한도 안에서 실제로 낮춘 만큼만 차감합니다.')
        go='선물 보내기'
    else:
        raid=own.get('raid') or {}
        out+=_line('title','철수 공물')+_line('subtitle','황제에게 공물을 바쳐 군대를 돌려보냅니다')
        out+=_line('row','공물',_dn(q.get('amount',raid.get('tribute',0))))
        if ui.get('funds') is not None:out+=_line('row','보유 자금',_dn(ui['funds']))
        out+=_line('row','공물 후 편집증',f"{q.get('after',raid.get('after_tribute','-'))} (지금 {own['paranoia']})")+_line('row','황제군 도착까지',raid.get('wait') or '0일')
        out+=_line('hint','도착한 뒤에는 공물을 받지 않습니다.')
        go='공물 바치기'
    # coup and gift: the game explains the amount itself (calc line); only the room's own messages are passed on
    message=ui.get('message') or ('' if q.get('ok') or mode in ('coup','gift') else q.get('reason',''))
    if message:out+=_line('message',message)
    return out+_line('go',go,int(bool(q.get('ok')) and not own.get('charging')))

def score_file(public,names,me):
    """The end: everyone sees every value. names: city id -> shown name."""
    rows=(public or {}).get('scoreboard')
    if not rows:return ''
    winner=next((r for r in rows if r.get('winner')),None)
    out=_line('title','황위 쟁탈전 종료')
    if winner:out+=_line('subtitle',names.get(winner['city'],winner['city'])+' 총독이 황제를 폐위하고 로마의 새 황제가 되었습니다')
    for i,r in enumerate(rows):
        name=names.get(r['city'],r['city'])
        if r.get('known'):out+=_line('row',i+1,name,f"{r['stage']}/5",f"{r['successes']} / {r['failures']}",f"{r['coup_total']:,}",f"{r['gift_total']:,}",f"{r['raids']} / {r['tributes']}",r['paranoia'],int(bool(r.get('winner'))),int(r['city']==me))
        else:out+=_line('row',i+1,name,f"{r['stage']}/5",'-','-','-','-','-',int(bool(r.get('winner'))),int(r['city']==me))
    out+=_line('foot','순위: 완료 단계가 높은 순, 같으면 그 단계에 먼저 도달한 순. 금액은 Dn, 환불된 지출은 빼고 셉니다.')
    out+=_line('foot','게임이 끝났으므로 지원금, 실패, 선물, 원정, 편집증을 모두 공개합니다.')
    return out

def local_quote(own,kind):
    """The quote a click would get, from my own values alone (throne_play.quote for the amount the dialog starts with:
    the minimum for a coup, 0 for a gift). Only for opening the dialog at once: the bridge asks the room right after,
    and the room checks everything again before it charges."""
    base=dict(kind=kind,ok=False,reason='',charge=0)
    if not own or not own.get('test') or own.get('restoring'):return dict(base,reason='내 비공개 기록을 새 방장에게 확인받는 중입니다(복원 대기). 황위 행동은 기다립니다.')
    if own.get('ended'):return dict(base,reason='황위 쟁탈전 시험이 끝났습니다.')
    if own.get('eliminated'):return dict(base,reason='탈락한 도시입니다.')
    if own.get('charging'):return dict(base,reason='앞선 황위 지출을 처리하는 중입니다.')
    if kind=='coup':
        if own['stage']>=own['stages'] or 'next_chance' not in own:return dict(base,reason='이미 마지막 단계까지 성공했습니다.')
        minimum=own['next_cost']
        out=dict(base,amount=minimum,stage=own['stage']+1,stage_name=own.get('stage_name',''),minimum=minimum,failures=own.get('failures',0),
                 fail_next=own['fail_next'],cap=own['next_cap'],base_chance=own['next_chance'])
        if own.get('wait'):return dict(out,reason='다음 쿠데타 지원까지 '+own['wait']+' 남았습니다.')
        if own.get('limit_reached'):return dict(out,reason=f"최소 지원금 {minimum:,} Dn이 1회 지출 한도({own.get('max_spend',0):,} Dn)를 넘어 이 단계에 더 도전할 수 없습니다.")
        return dict(out,ok=True,charge=minimum,chance=own['next_chance'],chance_text=f"{own['next_chance']//100}.{own['next_chance']%100:02d}%")
    if not own.get('active'):return dict(base,amount=0,reason='평화의 시대: 황제는 아직 총독들의 충성을 의심하지 않습니다. 선물은 받지 않습니다.')
    return dict(base,amount=0,reason='금액을 정해 주세요.')

def prepared(own,kind):
    """throne-prep-<kind>.txt: the dialog a click on that button opens at once in the game (multiplayer_throne.inc
    th_open_local), or "refuse<TAB>why" when the click would open nothing (the same rule as command())."""
    if not own or not own.get('test') or own.get('restoring') or own.get('ended'):return ''
    q=local_quote(own,kind)
    if kind=='coup' and not q.get('ok') and ('minimum' not in q or q.get('reason','').startswith('다음 쿠데타 지원까지') or own.get('limit_reached')):return _line('refuse',q.get('reason',''))
    if kind=='gift' and not own.get('active'):return _line('refuse',q.get('reason',''))
    return dialog_file(own,dict(mode=kind,quote=q,amount=q.get('amount',0)))

def publish_panel(bridge,own):
    import time
    ui=getattr(bridge,'throne_ui',{});public=getattr(bridge,'throne_public',None);now=time.time()
    if own and own.get('test') and (own.get('ended') or own.get('restoring')):ui.update(mode=None,quote=None)
    bridge.write_changed('throne-hud.txt','')
    bridge.write_changed('throne-actions.txt','')
    bridge.write_changed('throne-box.txt',box_file(own,public,ui,now))
    bridge.write_changed('throne-dialog.txt',dialog_file(own,ui) if own and own.get('test') else '')
    for kind in ('coup','gift'):bridge.write_changed(f'throne-prep-{kind}.txt',prepared(own,kind))
    # what the game calculates with now: a confirm click checked against it (command, 'go')
    ui['shown']=_calc(own,ui['quote'],ui['mode']) if own and own.get('test') and not own.get('restoring') and ui.get('mode') in ('coup','gift') and ui.get('quote') else None
    bridge.write_changed('throne-score.txt',score_file(public,getattr(bridge,'throne_names',{}),bridge.client.city))

def _quote(bridge,funds):
    ui=bridge.throne_ui
    got=bridge.client.call('throne_quote',kind=ui['mode'],amount=ui['amount'],funds=funds)
    ui['quote']=got['quote'];ui['funds']=funds;return got['own']

ADD={'add1000':1000,'add5000':5000,'add10000':10000,'more':100,'less':-100}
def command(bridge,text,request):
    """A click in the throne box, the Rome panel, the march card or a dialog. 'coup' / 'gift' / 'tribute' open a
    dialog; the amount follows the trade window: 'less' 'more' (100), 'add1000' 'add5000' 'add10000', 'reset' (coup:
    the minimum, gift: 0), 'set' with the amount the game shows (the game edits it itself and sends 'set'); 'go' sends the confirmed quote as one spend (request id = this command's id: a resend is
    the same spend); 'close' closes. A coup asked for while it has to wait opens nothing: the wait is shown as a
    note under the box for a few seconds."""
    import time
    parts=text.split('\n');action=parts[0];funds=parts[1] if len(parts)>1 else ''
    funds=int(funds) if funds.strip().lstrip('-').isdigit() else None
    typed=parts[2] if len(parts)>2 else ''
    ui=bridge.throne_ui=getattr(bridge,'throne_ui',{});ui['message']=''
    own=bridge.client.call('throne_mine')
    def lowest():return (ui.get('quote') or {}).get('minimum',own.get('next_cost',0)) if ui.get('mode')=='coup' else 0
    if action=='coup':
        ui.update(mode='coup',amount=own.get('next_cost',0),quote=None);own=_quote(bridge,funds);q=ui['quote']
        if not q.get('ok') and ('minimum' not in q or q.get('reason','').startswith('다음 쿠데타 지원까지') or own.get('limit_reached')):   # nothing to choose: say why, open nothing
            ui.update(mode=None,quote=None,note=q.get('reason',''),note_until=time.time()+NOTE_SECONDS)
    elif action=='gift':
        ui.update(mode='gift',amount=0,quote=None);own=_quote(bridge,funds);q=ui['quote']
        if not own.get('active'):ui.update(mode=None,quote=None,note=q.get('reason',''),note_until=time.time()+NOTE_SECONDS)
    elif action=='tribute':
        ui.update(mode='tribute',amount=(own.get('raid') or {}).get('tribute',0),quote=None);own=_quote(bridge,funds)
        if (own.get('raid') or {}).get('phase')!='preparing':ui.update(mode=None,quote=None,note=ui['quote'].get('reason','') if ui.get('quote') else '',note_until=time.time()+NOTE_SECONDS)
    elif action in ADD and ui.get('mode') in ('coup','gift'):
        ui['amount']=max(lowest(),min(own.get('max_spend',1000000),ui['amount']+ADD[action]));own=_quote(bridge,funds)
    elif action=='set' and ui.get('mode') in ('coup','gift') and typed.strip().isdigit():
        # the amount as the game shows it (edited there at once, sent when it settles: user 2026-11-14, every click
        # used to wait for the room); the same bounds as the keys below
        ui['amount']=max(lowest(),min(own.get('max_spend',1000000),int(typed)));own=_quote(bridge,funds)
    elif action=='reset' and ui.get('mode') in ('coup','gift'):
        ui['amount']=lowest();own=_quote(bridge,funds)
    elif action=='go' and ui.get('mode') and ui.get('quote'):
        import throne_play
        if ui['mode'] in ('coup','gift') and typed.strip().isdigit():
            # the amount the game showed and calculated with: quoted here once, at the confirm click
            shown=ui.get('shown')
            ui['amount']=max(lowest(),min(own.get('max_spend',1000000),int(typed)));own=_quote(bridge,funds)
            if shown is not None and _calc(own,ui['quote'],ui['mode'])!=shown:   # the rules it showed no longer hold
                ui['message']='상태가 바뀌어 내용이 달라졌습니다. 다시 확인하고 눌러 주세요.';publish_panel(bridge,own);return
        result=bridge.client.call('throne_spend',request=request,kind=ui['mode'],amount=ui['amount'],funds=funds,expect=throne_play.fingerprint(ui['quote']))
        own=result.get('own',own)
        if result.get('state')=='requote':
            ui['quote']=result['quote'];ui['message']='상태가 바뀌어 내용이 달라졌습니다. 다시 확인하고 눌러 주세요.'
        elif result.get('state')=='refused':
            ui['quote']=result['quote'];ui['message']='실행하지 않았습니다. '+result['quote'].get('reason','')
        else:
            ui.update(mode=None,quote=None)
            if result.get('state')=='charging':bridge.throne_charging=True;bridge.cash_next=0   # hand the debit to the city now (cash_bridge)
            ui.update(note='요청을 받았습니다. 도시 자금 차감이 확인되면 결과가 나옵니다.' if result.get('state')=='charging' else '이미 처리한 요청입니다.',note_until=time.time()+NOTE_SECONDS)
    elif action=='close':ui.update(mode=None,quote=None)
    elif action.startswith('t-'):   # the developer panel (dev_tools.py; the room refuses it outside a developer room)
        try:import dev_tools
        except ImportError:dev_tools=None
        if dev_tools:own,note=dev_tools.throne_client_action(bridge,action,own);ui.update(note=note,note_until=time.time()+NOTE_SECONDS)
    publish_panel(bridge,own)

THRONE_NOTICE=7   # city_notices kind: fanfare line in the notice tab, no camera target

# ---- the emperor's punitive expedition against this player (2026-11-14; rules and clock: throne_play, throne_state)
RAID_RESULT={'tribute':'황제군 철수: 공물을 바쳐 황제의 의심을 달랬습니다.','defeated':'황제군 격파: 로마의 군대를 물리쳤습니다.',
             'sacked':'황제군이 도시를 약탈하고 물러났습니다. 황제의 분노가 조금 가라앉았습니다.','called_off':'황위 쟁탈전이 끝나 황제군이 물러납니다.'}

def _raid_id(bridge,raid,what):
    return hashlib.sha256(f"augustus-throne-raid\0{bridge.config.get('session','')}\0{bridge.client.city}\0{raid['id']}\0{raid['count']}\0{what}".encode()).hexdigest()[:32]

def raid_sync(bridge,own):
    """This player's own expedition, between the room and this PC's game:
      * emperor-raid-request.txt tells the game's engine to let expedition <count> in (1) or to call it back (2);
        the engine acts once per number and keeps that in the city save (src/multiplayer/emperor_raid.inc);
      * emperor-raid.txt is what the engine sees ("count state size killed alive"); 'attacking' and 'gone without
        being called back' are passed on to the room (op throne_raid), which decides what follows;
      * the warning (popup, while the emperor prepares) and the outcome (one fanfare line) are shown to this player
        only. Returns the player's values (fetched again when a report changed them)."""
    raid=own.get('raid') if own and not own.get('restoring') else None
    text=''
    if raid and raid.get('order'):
        try:scope,owner=(bridge.root/'post-identity.txt').read_text().split()
        except (OSError,ValueError):scope=None
        if scope:text=f"{scope} {owner} {raid['count']} {raid['size']} {1 if raid['order']=='attack' else 2}\n"
    bridge.write_changed('emperor-raid-request.txt',text)
    bridge.throne_private_events=''
    if not raid or not raid.get('count'):return own
    if raid['phase']=='preparing':
        bridge.throne_private_events=_raid_id(bridge,raid,'warning')+'\t황제의 징벌 원정\t'+(
            '황제께서 그대의 충성심을 의심하여 징벌 원정군을 보내셨습니다. 로마의 군대가 이미 출발했습니다. '
            f"황제군 {raid['size']}명, 도착까지 {raid.get('wait') or '0일'}, 철수 공물 {raid['tribute']:,} Dn. "
            '도착하기 전에 공물을 바치면 군대가 돌아갑니다. 도착하면 곧바로 공격하며, 그 뒤에는 공물을 받지 않습니다. 화면의 "황제군이 오고 있습니다" 알림에서 공물을 바칠 수 있습니다.')+'\n'
    if raid.get('result') in RAID_RESULT and getattr(bridge,'joined',False):
        import city_notices
        s=city_notices.state(bridge);key=_raid_id(bridge,raid,raid['result'])
        if 'throne:'+key not in s['seen']:
            city_notices.add(s,'throne:'+key,THRONE_NOTICE,int(key[:7],16)+1,0,0,0,RAID_RESULT[raid['result']]);city_notices.publish(bridge,s)
    if raid['phase'] in ('arrived','fighting'):
        try:count,seen,size,killed,alive=map(int,(bridge.root/'emperor-raid.txt').read_text().split())
        except (OSError,ValueError):return own
        if count==raid['count'] and ((seen==1 and raid['phase']=='arrived') or (seen==3 and not raid.get('paying'))):
            # the room's answer carries this player's values after the report (a batched throne_mine may be older)
            return dict(own,**bridge.client.call('throne_raid',count=count,seen=seen).get('own',{}))
    return own

def own_result(bridge,own):
    """My own coup or gift has been settled: a popup for me alone (user 2026-11-14: a success was only announced as
    "someone" to everybody, me included). Only a result that comes in while this game is running: the one already
    there when the game joins is the baseline, so a restart or another PC never replays it."""
    last=(own or {}).get('last') or {}
    if not hasattr(bridge,'throne_result_seen'):   # the first look of this game: whatever is there is old news
        bridge.throne_result_seen=last.get('request','') if last.get('state')=='done' else '';return ''
    if not last.get('request') or last.get('state')!='done' or last.get('kind') not in ('coup','gift'):return ''
    if bridge.throne_result_seen==last['request']:return getattr(bridge,'throne_result_line','')
    bridge.throne_result_seen=last['request']
    key=hashlib.sha256(f"augustus-throne-result\0{bridge.config.get('session','')}\0{last['request']}".encode()).hexdigest()[:32]
    # Plain story wording, no chance or amount (user 2026-11-14: the numbers made it read like a receipt).
    import throne_rules
    names=throne_rules.STAGE_NAMES;done=own.get('stage',0)
    if last['kind']=='gift':
        title='충성선물';body=f"황제가 당신의 충성선물을 받고 의심을 조금 거두었습니다. 편집증이 {last.get('points',0)} 낮아져 지금 {own.get('paranoia',0)}입니다."
    elif last.get('result')=='success':
        stage=names[max(0,min(done,len(names))-1)]
        title='쿠데타 성공'
        if done>=len(names):body=f"{stage}에 성공했습니다. 원로원과 군단이 당신을 새 황제로 맞이합니다. 이제 로마는 당신의 것입니다."
        else:body=f"{stage}에 성공했습니다. 당신을 따르는 세력이 제국 곳곳에서 커지고 있습니다. 다른 총독들은 누가 해냈는지 모릅니다. 황제의 의심이 커지기 전에 다음 단계를 준비하세요."
    else:
        stage=names[min(done,len(names)-1)]
        title='쿠데타 실패';body=f"{stage} 시도가 실패했습니다. 음모의 흔적이 드러나 황제가 모든 총독을 더 깊이 의심하게 되었습니다. 아직 아무도 당신이 꾸민 일인지 모릅니다. 다음 도전에는 더 많은 지원금이 필요합니다."
    bridge.throne_result_line=key+'\t'+title+'\t'+body+'\n'
    return bridge.throne_result_line

def end_popup(bridge,throne):
    """The struggle has ended: every other player gets a popup naming the new emperor (user 2026-11-15; the winner
    has its own popup from own_result, and everyone gets the scoreboard). Only an end that comes while this game is
    running: an end already there at the first look is old news (the scoreboard shows it)."""
    rows=(throne or {}).get('scoreboard') or []
    winner=next((r['city'] for r in rows if r.get('winner')),None)
    if not hasattr(bridge,'throne_end_seen'):bridge.throne_end_seen=winner;return ''
    if not winner or winner==bridge.client.city:return ''
    if bridge.throne_end_seen==winner:return getattr(bridge,'throne_end_line','')
    bridge.throne_end_seen=winner
    name=getattr(bridge,'throne_names',{}).get(winner,winner)
    key=hashlib.sha256(f"augustus-throne-end\0{bridge.config.get('session','')}\0{winner}".encode()).hexdigest()[:32]
    body=f"{name} 총독이 마지막 단계 황제 폐위에 성공해 로마의 새 황제가 되었습니다. 황위 쟁탈전이 끝났습니다. 모든 총독의 기록은 결과창에서 볼 수 있습니다."
    bridge.throne_end_line=key+'\t새 황제 즉위\t'+body+'\n'
    return bridge.throne_end_line

def fanfare(bridge,throne):
    """Public throne notices that are not popups (a failed coup, the end) become one fanfare line each in the notice
    tab, once per notice id. A notice record that has never seen throne notices (a new PC or folder for this room)
    takes the ones already there as read, so joining or restoring never replays the history."""
    import city_notices
    if not throne:
        # Not a throne room: a throne line left in this notice record (a folder kept from a throne game that ended
        # without the normal reset) is removed, from the cards and the log. Nothing is ever added here.
        s=getattr(bridge,'city_notice_state',None)
        if s is None and (bridge.root/'city-notice-state.json').exists():s=city_notices.state(bridge)
        if s and (any(e[1]==THRONE_NOTICE for e in s['events']) or any(e[1]==THRONE_NOTICE for e in s.get('log',[]))):
            s['events']=[e for e in s['events'] if e[1]!=THRONE_NOTICE];s['log']=[e for e in s.get('log',[]) if e[1]!=THRONE_NOTICE]
            city_notices.publish(bridge,s)
        return
    if not getattr(bridge,'joined',False):return
    lines=[n for n in throne.get('notices',[]) if not n.get('popup',True) and isinstance(n.get('id'),str) and len(n['id'])==32]
    s=city_notices.state(bridge);base='throne-baseline:'+str(bridge.config.get('session',''))
    quiet=base not in s['seen']
    if quiet:city_notices.add(s,base,THRONE_NOTICE,1,0,0,0,'',silent=True)
    for n in lines:
        city_notices.add(s,'throne:'+n['id'],THRONE_NOTICE,int(n['id'][:7],16)+1,0,0,0,n.get('line') or n['title'],silent=quiet)
    city_notices.publish(bridge,s)

def sync(bridge,state):
    import progress_client
    if progress_client.sync(bridge,state):return   # 황제의 순행: the box files are that mode's
    throne=state.get('throne')
    if not throne or not getattr(bridge,'joined',False):
        for name in ('throne-hud.txt','throne-actions.txt','throne-box.txt','throne-dialog.txt','throne-score.txt','emperor-raid-request.txt','throne-prep-coup.txt','throne-prep-gift.txt'):bridge.write_changed(name,'')
        bridge.throne_private_events='';return
    try:
        bridge.throne_public=throne;bridge.throne_names={x['city']:x.get('name') or x['city'] for x in state.get('slots',[])}
        own=bridge.client.call('throne_mine')
        ui=getattr(bridge,'throne_ui',{})
        if own.get('test') and ui.get('mode') and not own.get('restoring'):own=_quote(bridge,ui.get('funds'))   # keep the open quote current
        publish_panel(bridge,own)   # first: never held up by storage
        path=folder(bridge);sid=throne.get('sealed_save')
        if 'protected_commits' in own:
            protect_openings(path,bridge.config['session'],bridge.client.city,own['protected_commits'])
        if sid and getattr(bridge,'throne_opening_sid',None)!=sid and not own.get('restoring'):
            opening=bridge.client.call('throne_opening',id=sid).get('opening')
            if opening is None:bridge.throne_opening_sid=sid            # nothing of ours in this save (e.g. carried seal)
            elif keep_opening(path,bridge.client.city,opening):
                bridge.client.call('throne_opening_stored',id=sid,commit=opening['commit']);bridge.throne_opening_sid=sid
            # otherwise: not stored, not confirmed; the next status poll tries again
        if own.get('restoring'):
            found=find_opening(path,own.get('commit',''))
            if not found and getattr(bridge,'throne_recovery_tried',None)!=own.get('commit'):
                # once per pending record per session: a new record, a restart or a new host tries again
                bridge.throne_recovery_tried=own.get('commit');found=recover_opening(path,bridge.client.city,own.get('commit',''))
            if found:bridge.client.call('throne_hand_in',secret=found['secret'],nonce=found['nonce']);own=bridge.client.call('throne_mine')
        if own.get('test'):own=raid_sync(bridge,own);bridge.throne_private_events+=own_result(bridge,own)+end_popup(bridge,throne)
        busy=bool(own.get('charging')) or bool((own.get('raid') or {}).get('paying'))
        if busy and not getattr(bridge,'throne_charging',False):bridge.cash_next=0   # a spend appeared (e.g. a tribute): exchange now
        bridge.throne_charging=busy
        publish_panel(bridge,own)
    except (OSError,ValueError,KeyError,TypeError,AttributeError):pass
