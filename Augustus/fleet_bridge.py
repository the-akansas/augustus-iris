"""Publish all native couriers atomically; one failing courier cannot erase another."""
from city_labels import city_name

def reports(rows,states,city):
    result=[]
    for t in rows:
        f=t.get('fleet');v=states.get(t['id'])
        if not f or not v or t.get('suspended') or v[3:6]!=[t['resource'],t['quantity'],2]:continue
        source=t['sender']==city;state=t['state'];item=None
        if source and state=='collecting' and v[1] in (3,4):item=dict(op='live_collected' if v[1]==3 else 'live_collection_failed',building=v[2])
        elif source and state=='departing' and v[1]==4:item=dict(op='live_departure_failed')
        elif source and state=='departing' and v[1]==5 and v[6]==1:item=dict(op='live_departed',departure=v[3:6])
        elif not source and state=='travelling' and not t.get('cargo_delivered') and v[1] in (3,4):item=dict(op='live_arrived' if v[1]==3 else 'live_transport_failed',building=v[2])
        elif source and state=='rejected' and v[1] in (8,9):item=dict(op='live_home' if v[1]==8 else 'live_home_failed',post=[f['building'],f['generation']])
        elif not source and state=='finished' and v[1] in (10,11):item=dict(op='live_receiver_exit' if v[1]==10 else 'live_receiver_exit_failed',post=[f['building'],f['generation']],exit=v[3:6])
        if item:result.append(dict(item,id=t['id']))
    return result

def incoming_offers(b,rows):
    """Goods offers that wait for my answer. A contract round is accepted by the host itself, so it asks nothing."""
    from city_notices import agreement_rounds
    rounds=agreement_rounds(b)
    return [r['id'] for r in rows if r['receiver']==b.client.city and r['state']=='offered' and r.get('resource') and r['id'] not in rounds]

def receiver_visible(t):
    return t['state'] not in ('offered','queued','collecting','departing') and (t['state']!='travelling' or t.get('map_arrived',False))

def poll(b):
    try:catalog=[list(map(int,line.split())) for line in (b.root/'fleet-posts.txt').read_text().splitlines()]
    except (OSError,ValueError):catalog=None
    args={}
    try:args['route_posts']=[list(map(int,line.split())) for line in (b.root/'route-posts.txt').read_text().splitlines()]
    except (OSError,ValueError):pass
    if catalog is not None and catalog!=getattr(b,'fleet_catalog',None):args['posts']=catalog
    # Post contents and goods on their way: the host decides when a shared caravan leaves.
    try:
        import time
        p=b.root/'post-load.txt'
        # The game rewrites this only when it changes, so an old file can still be current.
        if p.exists():args['post_load']=[list(map(int,line.split())) for line in p.read_text().splitlines() if line.strip()]
    except (OSError,ValueError):pass
    try:states={v[0]:v for line in (b.root/'transport-states.txt').read_text().splitlines() if len(v:=list(map(int,line.split())))==7}
    except (OSError,ValueError):states={}
    import agreement_bridge
    args.update(agreement_bridge.stock_args(b))
    previous=getattr(b,'fleet_rows',[])
    proofs=reports(previous,states,b.client.city)
    data=b.client.call('live_sync',reports=proofs,**args)
    if 'posts' in args:b.fleet_catalog=catalog
    rows=data['rows'];b.fleet_rows=rows;b.client.fleet_rows=rows
    from route_bridge import publish as publish_routes
    publish_routes(b,data['routes'],data['route_roster'])
    b.agreements=data['agreements']['agreements'];b.client.agreements=b.agreements
    try:agreement_bridge.publish(b,data['agreements'])
    except OSError:pass
    if any(p['op']=='live_home_failed' for p in proofs):
        try:b.write_changed('trade-hint.txt','빈 상단 귀환 실패: 정산 유지, 점유 해제. 교역소 확인 후 계약을 재제안하세요.')
        except OSError:pass
    try:side_trade(b,data)
    except (OSError,ValueError,KeyError,TypeError):pass # Side panel is presentation only.
    import trade_board
    try:trade_board.publish(b,data)
    except (OSError,ValueError):pass
    import trade_partner_bridge
    try:trade_partner_bridge.publish(b,data)
    except (OSError,ValueError,KeyError):pass # Presentation tables must not hold native transport.
    from fleet_map import publish
    try:publish(b,rows)
    except (OSError,ValueError):pass # A map presentation failure must not hold native transport.
    from post_logistics_bridge import publish as publish_post_logistics
    local_posts=publish_post_logistics(b,data)
    manifest=[]
    for t in rows:
        if not t.get('goods_live'):continue
        fleet=t.get('fleet');source=t['sender']==b.client.city
        if not fleet or not fleet['assigned'] or fleet['home']:continue
        post=[fleet['building'],fleet['generation']] if source else local_posts.get(t['sender'],[0,0])
        state=t['state'];stage=2
        if source:
            stage=4 if state=='collecting' else 5 if state=='departing' else 8 if state=='rejected' else 2
        else:
            if not receiver_visible(t):continue
            stage=1 if state=='travelling' and not t.get('cargo_delivered') else 9 if state=='finished' else 3 if state in ('rejected','returning') else 2
        manifest.append(f"{t['id']} {t['resource']} {t['quantity']} {stage} 0 {post[0]} {post[1]}")
    b.write_changed('transport-list.txt',str(len(manifest))+'\n'+'\n'.join(manifest)+'\n')
    try:
        import city_notices
        # Terminal home rows leave the active list. Preserve the actual native
        # return proof for presentation; this is not an economic receipt.
        returned={p['id'] for p in proofs if p['op']=='live_home'}
        notices=rows+[dict(t,fleet=dict(t['fleet'],home=1)) for t in previous if t['id'] in returned]
        # History also carries finished goods whose caravan already left (settlement notice).
        notices += [t for t in data['history'] if t['state'] in ('finished','rejected') and t['id'] not in {r['id'] for r in rows}]
        city_notices.trade(b,notices)
        city_notices.post_storage(b) # Keep the post-full warning up until the goods can leave.
        try:city_notices.post_road(b,data) # A post no caravan can reach, while a deal depends on it.
        except (KeyError,TypeError):pass
    except (OSError,ValueError):pass
    b.transfer_busy=False
    selected=getattr(b.client,'fleet_focus',0)
    t=next((r for r in rows if r['id']==selected),None)
    if t is None:
        from city_notices import agreement_rounds;rounds=agreement_rounds(b) # contract rounds ask nothing: not opened as an offer to answer
        t=next((r for r in rows if r['receiver']==b.client.city and r['state']=='offered' and r['id'] not in rounds),rows[0] if rows else None)
    inbox=rows[0].get('inbox',[0,0,0]) if rows else [0,0,0]
    goods=incoming_offers(b,rows)
    b.incoming_trade=min(goods) if goods else 0 # Money gifts answer in their own top-right card.
    b.client.fleet_inbox=b.incoming_trade
    b.write_changed('trade-alert.txt',f"미확인 거래 제안 {inbox[0]}건 / 눌러서 확인" if inbox[0] else '')
    b.write_changed('trade-notify.txt',f'{inbox[2]} {inbox[0]}')
    names=getattr(b,'city_names',None)
    signature=tuple((r['id'],r['state']) for r in rows)
    if signature!=getattr(b,'fleet_history',None):
        records=data['history']
        from trade_bridge import history_line
        b.write_changed('trade-history.txt','\n'.join(history_line(r,names) for r in records));b.fleet_history=signature
    if t is None:
        b.write_changed('trade-view.txt','0 0\n진행 중인 거래가 없습니다.')
        b.write_changed('trade-hint.txt','')
        return []
    labels={'offered':'수락 대기','queued':'상단에 실을 물품을 모으는 중','collecting':'물품 수집 중','departing':'도시 출구로 이동 중','travelling':'상대 도시 운송 중','returning':'물품 반환 확인 중','deferred':'전달 확인 대기','finished':'하역 완료, 도착 도시 퇴장 중','rejected':'거래 종료, 상단 귀환 중','preflight':'운송 경로 확인 중'}
    mask=(3 if t['receiver']==b.client.city else 2) if t['state']=='offered' else 2 if t['state'] not in ('finished','rejected') else 0
    if t['sender']==b.client.city:mask|=8
    cash=t['resource']==0 and t['quantity']==0
    if cash:mask|=16
    label=labels.get(t['state'],t['state']);names=getattr(b,'city_names',None)
    from trade_bridge import RESOURCES
    resource=next((name for name,value in RESOURCES.items() if value==t['resource']),'돈')
    amount=f"{resource} {t['quantity']}포대 / 합계 {t['money']}데나리" if t['quantity'] else f"{t['money']}데나리"
    if cash:label={'offered':'돈 선물 수락 대기','finished':'돈 선물 완료','rejected':'돈 선물 거절'}.get(t['state'],'돈 선물 처리 중')
    if t.get('suspended'):label='상대 도시 재접속 대기'
    text=f"[플레이어 · 육상] 거래 #{t['id']}: {city_name(t['sender'],names)} -> {city_name(t['receiver'],names)}\n{amount}\n{label} / 진행 중인 주문 {len(rows)}건"
    if cash:text=f"[돈 선물] {city_name(t['sender'],names)} -> {city_name(t['receiver'],names)}\n{amount}\n{label}"
    if t.get('fleet') and not cash:text+=f"\n출발 교역소 #{t['fleet']['building']}"
    b.write_changed('trade-view.txt',f"{t['id']} {mask}\n"+text)
    b.write_changed('trade-hint.txt',label)
    return text.splitlines()

def side_trade(b,data):
    """Left side panel (trade tab): my posts, their queue, caravans on the road, standing contracts."""
    me=b.client.city;lines=[]
    for p in data.get('post_status',[]):
        lines.append(f"P {p['building']} {p['generation']} {p['loaded']} {p['inbound']} {p['leave']} {p['away']}")
        for q in p['queue']:lines.append(f"Q {q['id']} {1 if q['kind']=='gift' else 0} {q['resource']} {q['quantity']}")
    road=sum(1 for t in data.get('rows',[]) if t.get('resource') and t['state'] in ('collecting','departing','travelling') and me in (t['sender'],t['receiver']) and (t.get('fleet') or {}).get('assigned'))
    standing=sum(1 for a in data.get('agreements',{}).get('agreements',[]) if a['state'] in ('active','paused') and me in (a['seller'],a['buyer']))
    lines.append(f"C {road} {standing}")
    b.write_changed('side-trade.txt','\n'.join(lines)+'\n')
