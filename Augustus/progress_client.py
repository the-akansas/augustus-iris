"""황제의 순행 on a player's PC (user 2026-11-15; host rules: imperial_progress.py).

The game draws; every text and number is prepared here. The files are the throne box's own (the two modes never run
together; window/multiplayer_throne.inc):
  throne-box.txt        "state<TAB>progress" and the box: pg_small, pg_title, pg_row, pg_favor, bid, note
  throne-prep-bid.txt   the bid dialog, opened by the game at the click (nothing is asked of the room for that)
  throne-dialog.txt     the same dialog while the bridge holds it open (after a refusal, with the room's message)
  throne-events.txt     popups: the announcement, where the emperor goes, the outcome of a visit, the end
  emperor-visit-request.txt / emperor-visit.txt   the arrival, between the room and this city's engine
                        (src/multiplayer/emperor_visit.inc: taken once per visit number, kept in the city save)
The amount is edited in the game with the trade window's controls and the number pad, and checked there against the
minimum and the treasury (calc line 'bid'). The room hears of it only at the confirm click ("go"): one request."""
import hashlib,time
from scenario_overview import RES
from throne_client import _line,_dn,NOTE_SECONDS

FILES=('throne-hud.txt','throne-actions.txt','throne-score.txt','throne-prep-coup.txt','throne-prep-gift.txt','emperor-raid-request.txt')
PHASE={'idle':'다음 순행을 기다리는 중','bidding':'입찰 중','closing':'낙찰 확인 중','travel':'황제 이동 중','visit':'황제 도착','ended':'순행 종료'}

NAMES=dict(RES);NAMES[15]='도자기'   # as the game's own goods list says it
def goods_text(ids):return ', '.join(NAMES.get(g,str(g)) for g in ids)
def goods_mark(ids):return '@goods '+' '.join(str(g) for g in ids)   # the game draws each with its icon and its own name
def _signed(v):return ('+' if v>0 else '')+str(v)
def _key(bridge,*parts):
    return hashlib.sha256('\0'.join(['augustus-progress',str(bridge.config.get('session',''))]+[str(p) for p in parts]).encode()).hexdigest()[:32]
def _name(bridge,city):return getattr(bridge,'throne_names',{}).get(city,city)

def can_bid(own):return bool(own) and own.get('phase')=='bidding' and not own.get('bid') and own.get('close_days',0)>0

def box_file(bridge,own,ui,now):
    if not own:return ''
    out=_line('state','progress')+_line('pg_small','순행',f"{own['round']}/{own['rounds']}")+_line('pg_title',f"황제의 순행 {own['round']}/{own['rounds']}")
    phase=own['phase']
    if phase=='idle':out+=_line('pg_row','상태','첫 순행을 기다리는 중' if own.get('first') else PHASE['idle'])
    elif phase=='bidding':out+=_line('pg_row','상태',f"입찰 중 (마감까지 {own.get('close_days',0)}일)")
    else:out+=_line('pg_row','상태',PHASE.get(phase,phase))
    if own.get('goods'):
        out+=_line('pg_row','후보 물품',goods_mark(own['goods']))+_line('pg_row','요구량 (한 가지만)','비밀')
    if phase in ('bidding','closing'):
        out+=_line('pg_row','최저 입찰가',_dn(own['min_bid']))+_line('pg_row','내 입찰',_dn(own['bid']) if own.get('bid') else '없음')
    if own.get('holder'):
        out+=_line('pg_row','행선지',_name(bridge,own['holder']))+_line('pg_row','선정','낙찰 '+_dn(own['paid']) if own.get('chosen')=='bid' else '황제의 선택')
    me=bridge.client.city
    for city in sorted(own['favor'],key=lambda c:(-own['favor'][c],c)):
        out+=_line('pg_favor',_name(bridge,city),_signed(own['favor'][city]),int(city==me),int(city in own.get('winners',[])))
    out+=_line('bid',int(can_bid(own)))
    note=ui.get('note') if ui.get('note_until',0)>now else ''
    if not note and own.get('charging'):note='순행 관련 지출을 처리하는 중입니다. 도시 자금 차감을 확인하고 있습니다.'
    if not note and phase in ('travel','visit') and own.get('holder')==me:note='황제께서 우리 도시로 오십니다. 도착일은 알 수 없습니다. 후보 물품을 창고에 준비해 두십시오.'
    if note:out+=_line('note',note)
    return out

def dialog_file(own,ui=None):
    """The bid dialog. '' when no bid can be made now."""
    if not can_bid(own):return ''
    low=own['min_bid'];amount=max(low,(ui or {}).get('amount',low))
    out=_line('kind','bid')+_line('title','순행 입찰')+_line('subtitle',f"황제의 순행 {own['round']}/{own['rounds']}")
    out+=_line('desc','가장 높은 금액을 쓴 총독의 도시로 황제께서 가십니다. 금액이 같으면 먼저 낸 총독입니다. 낙찰된 총독만 돈을 냅니다.')
    out+=_line('row','후보 물품',goods_mark(own['goods']))+_line('row','요구량 (한 가지만)','비밀')
    out+=_line('row','입찰 마감까지',f"{own.get('close_days',0)}일")+_line('row','최저 입찰가',_dn(low))
    out+=_line('amount','입찰 금액',_dn(amount),amount,low,1000000)+_line('calc','bid',low,1000000,1,'')
    out+=_line('hint','입찰은 한 번만 할 수 있고 바꿀 수 없습니다. 다른 총독의 입찰은 볼 수 없습니다.')
    message=(ui or {}).get('message')
    if message:out+=_line('message',message)
    return out+_line('go','입찰하기',1)

def popups(bridge,own):
    """Popup lines (id, title, body) for what is current: the game shows each id once and keeps it in the city save."""
    if not own or not own.get('round'):return ''
    n=own['round'];head=f"황제의 순행 {n}/{own['rounds']}";me=bridge.client.city;out=''
    def add(kind,title,body):
        nonlocal out;out+=_line(_key(bridge,n,kind),title,body)
    if own.get('goods'):
        add('announce',head,f"황제께서 속주 순행에 나서십니다. 접대에는 다음 가운데 한 가지만 쓰십니다: {goods_text(own['goods'])}. 무엇을 얼마나 쓰실지는 도착하셔야 알 수 있습니다. "
            f"황제를 모시려는 총독은 한 달 안에 입찰하십시오. 최저 입찰가는 {own['min_bid']:,} Dn입니다. 가장 높은 금액을 쓴 총독의 도시로 가시며, 아무도 입찰하지 않으면 황제께서 직접 도시를 고르십니다.")
    if own.get('holder'):
        name=_name(bridge,own['holder'])
        body=(f"황제의 행선지: {name}. 낙찰가 {own['paid']:,} Dn." if own.get('chosen')=='bid' else f"입찰한 총독이 없어 황제께서 직접 고르셨습니다. 황제의 행선지: {name}.")
        if own['holder']==me:body+=' 도착일은 알 수 없습니다. 후보 물품을 창고에 넉넉히 준비해 두십시오. 모두 드리면 총애 +3, 절반 이상이면 +1, 그보다 적으면 -1이며 부족분은 돈으로 냅니다.'
        add('holder',head,body)
    for r in own.get('results',[])[-1:]:
        name=_name(bridge,r['holder']) if r.get('holder') else '';head=f"황제의 순행 {r['round']}/{own['rounds']}"
        if r['result']=='cancelled':body='접대할 총독이 자리를 비워 이번 순행은 취소되었습니다.'
        else:
            body=f"{name}: 황제께서 찾으신 물품은 {NAMES.get(r['good'],r['good'])} {r['amount']}, 받으신 양은 {r['taken']}입니다. 총애 {_signed(r['delta'])}."
            if r.get('fine'):body+=f" 부족분으로 {r['fine']:,} Dn을 냈습니다."
        out+=_line(_key(bridge,r['round'],'result'),head+' 결과',body)
    if own.get('ended') and own.get('winners'):
        names=', '.join(_name(bridge,c) for c in own['winners'])
        table=', '.join(f"{_name(bridge,c)} {_signed(v)}" for c,v in sorted(own['favor'].items(),key=lambda kv:(-kv[1],kv[0])))
        out+=_line(_key(bridge,'end'),'황제의 오른팔',f"모든 순행이 끝났습니다. {names} 총독이 황제의 총애를 가장 많이 얻어 황제의 오른팔, 제국의 2인자가 되었습니다. 총애: {table}.")
    return out

def visit_sync(bridge,own):
    """The arrival: the order for this city's engine, and its answer passed on to the room once."""
    order=(own or {}).get('order');text=''
    if order:
        try:scope,owner=(bridge.root/'post-identity.txt').read_text().split()
        except (OSError,ValueError):scope=None
        if scope:text=f"{scope} {owner} {order['id']} {order['resource']} {order['amount']}\n"
    if text or not own:bridge.write_changed('emperor-visit-request.txt',text)   # kept after the report: the engine only answers a number it knows
    if not order:return own
    try:visit,resource,amount,taken,funds=map(int,(bridge.root/'emperor-visit.txt').read_text().split())   # funds: the treasury the engine shows
    except (OSError,ValueError):return own
    if visit!=order['id'] or resource!=order['resource']:return own
    return bridge.client.call('progress_visit',visit=visit,taken=taken,funds=funds).get('own',own)

def publish(bridge,own):
    ui=bridge.progress_ui=getattr(bridge,'progress_ui',{})
    if not can_bid(own):ui.pop('open',None)
    for name in FILES:bridge.write_changed(name,'')
    bridge.write_changed('throne-box.txt',box_file(bridge,own,ui,time.time()))
    bridge.write_changed('throne-prep-bid.txt',dialog_file(own) or (_line('refuse','이미 입찰했습니다. 입찰은 한 번만 할 수 있습니다.' if own and own.get('bid') else '지금은 입찰을 받지 않습니다.') if own else ''))
    bridge.write_changed('throne-dialog.txt',dialog_file(own,ui) if ui.get('open') else '')

def command(bridge,text,request):
    """A click in the box or the bid dialog. 'bid' opens the dialog (the game already shows its prepared copy);
    'go' with the amount the game shows sends the one bid (request id = this command's id: a resend is the same
    bid); 'close' closes. The amount keys never come here: the game edits the amount itself."""
    parts=text.split('\n');action=parts[0];funds=parts[1] if len(parts)>1 else '';typed=parts[2] if len(parts)>2 else ''
    funds=int(funds) if funds.strip().lstrip('-').isdigit() else None
    if funds is not None:bridge.progress_funds=funds
    ui=bridge.progress_ui=getattr(bridge,'progress_ui',{});ui['message']=''
    own=getattr(bridge,'progress_own',None)
    if action=='bid':
        if can_bid(own):ui.update(open=True,amount=own['min_bid'])
    elif action=='go' and typed.strip().isdigit():
        ui['amount']=int(typed)
        result=bridge.client.call('progress_bid',request=request,amount=int(typed),**({'funds':funds} if funds is not None else {}))
        own=bridge.progress_own=result.get('own',own)
        if result.get('state')=='accepted':
            ui.update(open=False,note=f"입찰했습니다: {result['amount']:,} Dn. 마감 뒤에 결과가 나옵니다.",note_until=time.time()+NOTE_SECONDS)
        else:ui.update(open=True,message='입찰하지 않았습니다. '+result.get('reason',''))
    elif action=='close':ui['open']=False
    elif action=='t-next':   # the developer panel (dev_tools.py; the room refuses it outside a developer room)
        try:import dev_tools
        except ImportError:dev_tools=None
        if dev_tools:
            own,note=dev_tools.progress_client_action(bridge,own);bridge.progress_own=own;ui.update(note=note,note_until=time.time()+NOTE_SECONDS)
    publish(bridge,own)

def sync(bridge,state):
    """Called every bridge round. Returns True when this is a 황제의 순행 room (the throne files are ours then)."""
    if not state.get('progress'):
        if getattr(bridge,'progress_own',None) is not None:
            bridge.progress_own=None;bridge.write_changed('emperor-visit-request.txt','');bridge.write_changed('throne-prep-bid.txt','')
        return False
    if not getattr(bridge,'joined',False):
        for name in FILES+('throne-box.txt','throne-dialog.txt','throne-prep-bid.txt'):bridge.write_changed(name,'')
        bridge.throne_private_events='';return True
    try:
        bridge.throne_names={x['city']:x.get('name') or x['city'] for x in state.get('slots',[])}
        own=bridge.client.call('progress_mine').get('own')
        own=visit_sync(bridge,own);bridge.progress_own=own
        bridge.throne_private_events=popups(bridge,own)
        busy=bool(own and own.get('charging'))
        if busy and not getattr(bridge,'throne_charging',False):bridge.cash_next=0   # hand the debit to the city now (cash_bridge)
        bridge.throne_charging=busy
        publish(bridge,own)
    except (OSError,ValueError,KeyError,TypeError,AttributeError):pass
    return True
