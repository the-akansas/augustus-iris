"""Live cargo on the native receipt channel; never enters a save barrier."""
import joint_save

def initialize(db):
    db.execute('CREATE TABLE IF NOT EXISTS goods_motion(id INTEGER PRIMARY KEY,accepted INTEGER NOT NULL DEFAULT 0,source INTEGER NOT NULL DEFAULT 0,departed INTEGER NOT NULL DEFAULT 0,destination INTEGER NOT NULL DEFAULT 0,route INTEGER NOT NULL,counted INTEGER NOT NULL DEFAULT 0)')
    columns={r[1] for r in db.execute('PRAGMA table_info(goods_motion)')}
    for column in ('source_ok','destination_ok','map_depart_tick','map_arrive_tick','map_progress'):
        if column not in columns:db.execute('ALTER TABLE goods_motion ADD COLUMN '+column+' INTEGER NOT NULL DEFAULT 0')

MAP_TRAVEL_TICKS=192

def shared_tick(room,t,db=None):
    progress=getattr(room,'progress',{})
    cities=[t['sender'],t['receiver']]
    if db is not None and getattr(room,'started',False):
        # A city whose player left no longer keeps time: the goods move on the other's clock.
        active=set(room.active_cities(db));cities=[c for c in cities if c in active] or cities
    return min(progress[c][0] for c in cities) if all(c in progress for c in cities) else None

def map_motion(room,db,t):
    m=db.execute('SELECT * FROM goods_motion WHERE id=?',(t['id'],)).fetchone()
    if not m or not m['departed']:return dict(map_progress=0,map_arrived=False)
    # Legacy saves already departed without a timeline: keep them at destination.
    start,end=m['map_depart_tick'],m['map_arrive_tick']
    now=shared_tick(room,t,db)
    progress=max(m['map_progress'],1000 if not end else 0 if now is None else max(0,min(1000,(now-start)*1000//(end-start))))
    if progress!=m['map_progress']:
        db.execute('UPDATE goods_motion SET map_progress=? WHERE id=?',(progress,t['id']));db.commit()
    return dict(map_progress=progress,map_arrived=progress>=1000)

def state(db,t,contract):
    m=db.execute('SELECT * FROM goods_motion WHERE id=?',(t['id'],)).fetchone()
    p=contract['phase']
    if p=='complete':return 'finished'
    if p=='cancelled':return 'rejected'
    if p.startswith('blocked:'):return 'deferred'
    if contract['cancel']:return 'returning'
    if p=='offered':
        if not m['accepted']:return 'offered'
        fleet=db.execute('SELECT assigned FROM fleet_order WHERE id=?',(t['id'],)).fetchone()
        if fleet and not fleet[0]:return 'queued' 
        if m['route']==3 and not (m['source_ok'] and m['destination_ok']):return 'preflight'
        return 'collecting'
    if p=='export':return 'collecting'
    if p in ('escrow','travel'):return 'travelling' if m['departed'] else 'departing'
    return 'travelling'

def trade(room,db,city,r,t,ledger):
    import cash_live
    m=db.execute('SELECT * FROM goods_motion WHERE id=?',(t['id'],)).fetchone()
    tid=t['request'];op=r['op']
    if op!='live_status' and joint_save.pending(db):raise ValueError('save in progress')
    if op=='live_preflight':
        if t['state']!='preflight':return trade(room,db,city,dict(op='live_status'),t,ledger)
        if type(r.get('available'))!=bool:raise ValueError('invalid preflight')
        if not r['available']:ledger.cancel(city,tid)
        else:
            column='source_ok' if city==t['sender'] else 'destination_ok'
            db.execute('UPDATE goods_motion SET '+column+'=1 WHERE id=?',(t['id'],));db.commit()
    elif op=='live_accept':
        if city!=t['receiver']:raise ValueError('recipient consent required')
        if t['state']=='rejected':raise ValueError('cancelled offer')
        if not cash_live.ready(room,(t['sender'],t['receiver'])):raise ValueError('both engines required')
        if t['state']=='offered':db.execute('UPDATE goods_motion SET accepted=1 WHERE id=?',(t['id'],));db.commit()
    elif op in ('live_reject','live_collection_failed','live_departure_failed','live_transport_failed'):
        expected=t['receiver'] if op=='live_transport_failed' else t['sender']
        if op!='live_reject' and city!=expected:raise ValueError('wrong transport reporter')
        if op=='live_reject' or not ledger._contract(city,tid)['received']:ledger.cancel(city,tid)
    elif op=='live_collected':
        if city!=t['sender']:raise ValueError('wrong collection reporter')
        target=r.get('building')
        if type(target)!=int or not 0<target<100000:raise ValueError('invalid collection target')
        if t['state']=='collecting':
            db.execute('UPDATE goods_motion SET source=? WHERE id=?',(target,t['id']));db.commit()
            ledger.accept(t['receiver'],tid,room.active_cities(db))
    elif op=='live_departed':
        if city!=t['sender']:raise ValueError('wrong departure reporter')
        proof=r.get('departure')
        if proof!=[t['resource'],t['quantity'],m['route']] or any(type(x)!=int for x in proof):raise ValueError('invalid departure')
        if t['state']=='departing' and not m['departed']:
            tick=shared_tick(room,t)
            if tick is None:raise ValueError('both city clocks required')
            db.execute('UPDATE goods_motion SET departed=1,map_depart_tick=?,map_arrive_tick=? WHERE id=?',(tick,tick+MAP_TRAVEL_TICKS,t['id']));db.commit()
    elif op=='live_arrived':
        if city!=t['receiver']:raise ValueError('wrong arrival reporter')
        target=r.get('building')
        if type(target)!=int or not 0<target<100000:raise ValueError('invalid destination')
        c=ledger._contract(city,tid)
        if t['state']=='travelling' and m['departed'] and c['phase']=='travel' and map_motion(room,db,t)['map_arrived']:
            db.execute('UPDATE goods_motion SET destination=? WHERE id=?',(target,t['id']));db.commit()
            ledger.arrived(city,tid)
    elif op!='live_status':raise ValueError('unsupported goods operation')
    import player_fleet
    player_fleet.advance(db,room)
    cash_live.sync(db,ledger,t['id'])
    out=dict(db.execute('SELECT * FROM live_transfer WHERE id=?',(t['id'],)).fetchone())
    out.update(cargo_delivered=bool(ledger._contract(city,tid)['received']),goods_live=True,source_route=m['route'],cargo_remaining=t['quantity'] if out['state']=='returning' else 0)
    out.update(map_motion(room,db,t))
    # A city whose player left does not come back this session: its trades are settled
    # by the room (live_trade.settle_departed), so they are never shown as waiting for it.
    return out

def decorate(db,command):
    if not command['asset']:return command
    t=db.execute('SELECT t.*,m.source,m.destination,m.route FROM live_transfer t JOIN goods_motion m ON t.id=m.id WHERE t.request=?',(command['contract'],)).fetchone()
    if not t:return None
    target=t['source'] if command['step']=='export' else t['destination'] if command['step']=='receive' else 0
    return dict(command,transport=[t['id'],target,t['route']])


def retry_confirmed_failures(ledger,city,now=None):
    import time
    now=time.time() if now is None else now
    # Only definitive unapplied receipts allow a NEW command identity. Missing
    # proof reuses the original ID and never causes an inferred refund.
    for row in ledger.db.execute("SELECT * FROM post_contract WHERE phase LIKE 'blocked:%' AND resource>0").fetchall():
        step=row['phase'].split(':',1)[1]
        owner=row['receiver'] if step in ('receive','escrow','refund_money') else row['sender']
        count=ledger.db.execute('SELECT count(*) FROM post_command WHERE contract=? AND step=?',(row['id'],step)).fetchone()[0]
        deliveries=ledger.db.execute('SELECT COALESCE(SUM(a.attempts),0) FROM post_command c JOIN cash_attempt a ON c.id=a.command WHERE c.contract=? AND c.step=?',(row['id'],step)).fetchone()[0]
        last=ledger.db.execute('SELECT id FROM post_command WHERE contract=? AND step=? ORDER BY attempt DESC LIMIT 1',(row['id'],step)).fetchone()
        due=ledger.db.execute('SELECT next_time FROM cash_retry WHERE command=?',(last[0],)).fetchone()
        if city==owner and (due is None or now>=due[0]) and not ledger.recovery_held(row):ledger.retry(city,row['id'])
