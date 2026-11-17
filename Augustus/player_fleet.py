"""One caravan per native player post, shared by several orders (a shipment).

The post's caravan carries at most CARAVAN_LOAD sacks, of any mix of goods,
taken from the post's order queue in order. It leaves when it is full, when
every queued order is loaded and nothing is on its way for GRACE_TICKS (so
orders accepted one after another still share it), when no goods have been on their way to the post
for IDLE_TICKS (waiting on production), or IDLE_TICKS*3 after its first sack.
A partly loaded order ships what is loaded (money pro rata) and the rest stays
queued as its own order. Incoming visitors own no local slot; the source slot
is released when every order of the shipment is home."""
import sqlite3,uuid
CARAVAN_LOAD=16
IDLE_TICKS=800          # one game month: 16 days x 50 ticks
MAX_WAIT_TICKS=IDLE_TICKS*3
GRACE_TICKS=100         # two game days after the last change before a not-full caravan leaves
LOAD_FRESH_SECONDS=10

def initialize(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS fleet_site(city TEXT,building INTEGER,generation INTEGER,active INTEGER,
        PRIMARY KEY(city,building,generation));
    CREATE TABLE IF NOT EXISTS fleet_order(id INTEGER PRIMARY KEY,city TEXT,building INTEGER,generation INTEGER,
        assigned INTEGER NOT NULL DEFAULT 0,home INTEGER NOT NULL DEFAULT 0);
    ''')
    # Several orders now share one caravan: the one-owner index is replaced by shipments.
    db.execute('DROP INDEX IF EXISTS fleet_one_owner')
    db.execute('CREATE TABLE IF NOT EXISTS fleet_timer(city TEXT,building INTEGER,generation INTEGER,now INTEGER,first INTEGER,idle INTEGER,loaded INTEGER,inbound INTEGER,settled INTEGER,PRIMARY KEY(city,building,generation))')
    if 'settled' not in {r[1] for r in db.execute('PRAGMA table_info(fleet_timer)')}:db.execute('ALTER TABLE fleet_timer ADD COLUMN settled INTEGER')
    if 'shipment' not in {r[1] for r in db.execute('PRAGMA table_info(fleet_order)')}:
        db.execute('ALTER TABLE fleet_order ADD COLUMN shipment INTEGER NOT NULL DEFAULT 0')
    # A split remainder remembers the order it was cut from (0: an original order).
    if 'origin' not in {r[1] for r in db.execute('PRAGMA table_info(fleet_order)')}:
        db.execute('ALTER TABLE fleet_order ADD COLUMN origin INTEGER NOT NULL DEFAULT 0')

def register(db,city,rows):
    if not isinstance(rows,list) or len(rows)>512:raise ValueError('invalid post inventory')
    seen=set()
    for row in rows:
        if not isinstance(row,list) or len(row)!=3 or any(type(v)!=int for v in row):raise ValueError('invalid native post')
        b,g,active=row
        if not 0<b<100000 or not 0<=g<65536 or active not in (0,1) or b in seen:raise ValueError('invalid native post')
        seen.add(b)
    # A post that no longer stands leaves the list. One that only lost its road stays,
    # inactive: its waiting orders wait with it instead of being cancelled.
    db.execute('DELETE FROM fleet_site WHERE city=?',(city,))
    for b,g,active in rows:
        db.execute('INSERT INTO fleet_site VALUES(?,?,?,?) ON CONFLICT(city,building,generation) DO UPDATE SET active=excluded.active',(city,b,g,active))
    db.commit()
    return [dict(r) for r in db.execute('SELECT * FROM fleet_site WHERE city=? AND active=1',(city,))]

def destination_ready(db,sender,receiver):
    """False only when the receiver's post for this sender stands but cannot take a caravan
    (no road to the city gates). None: not known, treated as ready."""
    try:p=db.execute('SELECT building,generation FROM city_trade_post WHERE city=? AND peer=? AND active=1',(receiver,sender)).fetchone()
    except sqlite3.OperationalError:return None
    if not p:return None
    site=db.execute('SELECT active FROM fleet_site WHERE city=? AND building=? AND generation=?',(receiver,p[0],p[1])).fetchone()
    return None if not site else bool(site[0])

def reserve(db,city,tid,post):
    if not isinstance(post,list) or len(post)!=2 or any(type(v)!=int for v in post):raise ValueError('select player trading post')
    if not db.execute('SELECT 1 FROM fleet_site WHERE city=? AND building=? AND generation=? AND active=1',(city,*post)).fetchone():raise ValueError('player trading post unavailable')
    if db.execute('SELECT count(*) FROM fleet_order WHERE city=? AND home=0',(city,)).fetchone()[0]>=64:raise ValueError('player trading post order queue full')
    db.execute('INSERT INTO fleet_order(id,city,building,generation) VALUES(?,?,?,?)',(tid,city,*post))

def report_load(room,city,rows):
    """Native post contents and goods already on their way to each post."""
    import time
    if not isinstance(rows,list) or len(rows)>2048:raise ValueError('invalid post load')
    load={}
    for row in rows:
        if not isinstance(row,list) or len(row)!=5 or any(type(v)!=int for v in row):raise ValueError('invalid post load')
        b,g,res,held,inbound=row
        if not 0<b<100000 or not 0<=g<65536 or not 0<res<64 or not 0<=held<=10000 or not 0<=inbound<=10000:raise ValueError('invalid post load')
        load.setdefault((b,g),{})[res]=(held,inbound)
    if not hasattr(room,'post_load'):room.post_load={}
    room.post_load[city]=(time.monotonic(),load)

def split(db,cities,t,keep,post):
    """Ship `keep` sacks of an unexported order now; the rest becomes a queued order."""
    from trade_post_ledger import stage_offer
    rest=t['quantity']-keep
    money_keep=t['money']*keep//t['quantity'];money_rest=t['money']-money_keep
    if keep<1 or rest<1 or (t['kind']=='sale' and (money_keep<1 or money_rest<1)):return None
    c=db.execute('SELECT phase FROM post_contract WHERE id=?',(t['request'],)).fetchone()
    if not c or c[0]!='offered':return None
    part=db.execute('SELECT count(*) FROM live_transfer WHERE request LIKE ?',(t['request'][:8]+'%',)).fetchone()[0]
    key=uuid.uuid5(uuid.UUID(t['request']),'part-'+str(part)).hex
    db.execute('UPDATE live_transfer SET quantity=?,money=? WHERE id=?',(keep,money_keep,t['id']))
    db.execute('UPDATE post_contract SET quantity=?,money=? WHERE id=?',(keep,money_keep,t['request']))
    tid=db.execute("INSERT INTO live_transfer(request,sender,receiver,resource,quantity,money,kind,state) VALUES(?,?,?,?,?,?,?,'offered')",
        (key,t['sender'],t['receiver'],t['resource'],rest,money_rest,t['kind'])).lastrowid
    db.execute('INSERT INTO cash_transfer VALUES(?,?)',(tid,key))
    row=db.execute('SELECT origin FROM fleet_order WHERE id=?',(t['id'],)).fetchone()
    db.execute('INSERT INTO fleet_order(id,city,building,generation,origin) VALUES(?,?,?,?,?)',(tid,t['sender'],*post,(row[0] if row and row[0] else t['id'])))
    db.execute('INSERT INTO goods_motion(id,route,accepted) VALUES(?,2,1)',(tid,))
    stage_offer(db,cities,t['sender'],key,t['receiver'],t['resource'],rest,money_rest)
    return tid

def schedule(room,db):
    """Load each post's caravan from its queue and decide when it leaves."""
    import time
    co=getattr(room,'coordinator',None) # test rooms may carry only active_cities
    cities=co.scenario['cities'] if co else room.active_cities(db)
    timers=room.__dict__.setdefault('caravan_timers',{})
    for site in db.execute('SELECT * FROM fleet_site WHERE active=1').fetchall():
        city,b,g=site['city'],site['building'],site['generation'];key=(city,b,g)
        if db.execute('SELECT 1 FROM fleet_order WHERE city=? AND building=? AND generation=? AND assigned=1 AND home=0',key).fetchone():
            timers.pop(key,None);continue
        lines=[dict(r) for r in db.execute('''SELECT t.*,f.building,f.generation FROM fleet_order f
            JOIN goods_motion m ON f.id=m.id JOIN live_transfer t ON t.id=f.id
            WHERE f.city=? AND f.building=? AND f.generation=? AND f.assigned=0 AND f.home=0 AND m.accepted=1 AND m.route=2
            AND t.state NOT IN ('finished','rejected') ORDER BY f.id''',key)]
        # Goods stay in my post while the other city's post cannot take a caravan:
        # they are not sent to wait at its gates, and the order can still be cancelled.
        lines=[t for t in lines if destination_ready(db,t['sender'],t['receiver']) is not False]
        if not lines:timers.pop(key,None);continue
        if db.execute('''SELECT count(*) FROM fleet_order f JOIN live_transfer t ON f.id=t.id
            WHERE f.assigned=1 AND f.home=0 AND (t.sender=? OR t.receiver=?)''',(city,city)).fetchone()[0]>=48:continue
        report=getattr(room,'post_load',{}).get(city)
        progress=getattr(room,'progress',{}).get(city)
        if not report or time.monotonic()-report[0]>LOAD_FRESH_SECONDS or not progress:
            continue # No fresh native load report: never guess what is in the post.
        stock={r:v[0] for r,v in report[1].get((b,g),{}).items()}
        inbound=sum(v[1] for v in report[1].get((b,g),{}).values())
        tick=progress[0]
        # Plan the caravan: queue order, at most CARAVAN_LOAD sacks in total.
        plan=[];room_left=CARAVAN_LOAD
        for t in lines:
            if room_left<=0:break
            want=min(t['quantity'],room_left);room_left-=want
            loaded=min(want,stock.get(t['resource'],0));stock[t['resource']]=stock.get(t['resource'],0)-loaded
            plan.append((t,want,loaded))
        total=sum(p[2] for p in plan)
        full=room_left<=0 and all(p[1]==p[2] for p in plan)
        complete=all(p[1]==p[2] for p in plan) and len(plan)==len(lines)
        state=timers.setdefault(key,{'first':None,'idle':None})
        # Everything loaded but not full: wait GRACE_TICKS with nothing on the way and no new order.
        mark=(len(lines),total)
        if not complete or inbound:state['settled']=None
        elif state.get('mark')!=mark or state.get('settled') is None:state['settled']=tick
        state['mark']=mark
        settled=full or (state.get('settled') is not None and tick-state['settled']>=GRACE_TICKS)
        if total and state['first'] is None:state['first']=tick
        if inbound:state['idle']=None
        elif state['idle'] is None:state['idle']=tick
        waited_idle=state['idle'] is not None and tick-state['idle']>=IDLE_TICKS
        waited_long=state['first'] is not None and tick-state['first']>=MAX_WAIT_TICKS
        # Visible to the test monitor: when this post's caravan may leave.
        db.execute('INSERT OR REPLACE INTO fleet_timer VALUES(?,?,?,?,?,?,?,?,?)',(city,b,g,tick,state['first'],state['idle'],total,inbound,state.get('settled')))
        db.commit()
        if not total or not (settled or waited_idle or waited_long):continue
        sid=(db.execute('SELECT COALESCE(MAX(shipment),0) FROM fleet_order').fetchone()[0] or 0)+1
        with db:
            for t,want,loaded in plan:
                if not loaded:continue
                if loaded<t['quantity'] and split(db,cities,t,loaded,[b,g]) is None and loaded<t['quantity']:continue
                db.execute('UPDATE fleet_order SET assigned=1,shipment=? WHERE id=?',(sid,t['id']))
        timers.pop(key,None)
        db.execute('DELETE FROM fleet_timer WHERE city=? AND building=? AND generation=?',key);db.commit()

def legacy_assign(db,cities_with_load):
    """Bridges that do not report post loads (and sea orders) keep one whole order per caravan."""
    rows=db.execute('''SELECT f.*,m.route FROM fleet_order f JOIN goods_motion m ON f.id=m.id
        JOIN live_transfer t ON t.id=f.id JOIN fleet_site s
        ON s.city=f.city AND s.building=f.building AND s.generation=f.generation
        WHERE f.assigned=0 AND f.home=0 AND m.accepted=1 AND s.active=1
        AND t.state NOT IN ('finished','rejected') ORDER BY f.id''').fetchall()
    for row in rows:
        if row['city'] in cities_with_load and row['route']==2:continue
        if db.execute('SELECT 1 FROM fleet_order WHERE city=? AND building=? AND generation=? AND assigned=1 AND home=0',(row['city'],row['building'],row['generation'])).fetchone():continue
        # Keep the bounded native manifest below its maximum even when many
        # foreign cities send to the same destination.
        t=db.execute('SELECT receiver FROM live_transfer WHERE id=?',(row['id'],)).fetchone()
        if any(db.execute('''SELECT count(*) FROM fleet_order f JOIN live_transfer t ON f.id=t.id
            WHERE f.assigned=1 AND f.home=0 AND (t.sender=? OR t.receiver=?)''',(city,city)).fetchone()[0]>=48 for city in (row['city'],t[0])):continue
        db.execute('UPDATE fleet_order SET assigned=1 WHERE id=?',(row['id'],))
    db.commit()

def advance(db,room=None):
    # Terminal goods/cash receipts alone do not free a caravan. The native
    # receiver must report exit after settled delivery; rejected orders use source cleanup.
    db.execute("UPDATE fleet_order SET home=1 WHERE assigned=0 AND id IN (SELECT id FROM live_transfer WHERE state IN ('finished','rejected'))")
    db.commit()
    if room is None:return # Loading decisions need the room's native load reports and clock.
    legacy_assign(db,set(getattr(room,'post_load',{})))
    schedule(room,db)

def post_status(db,city):
    """Side-panel summary for one city's posts: load, when the caravan may leave, its queue."""
    out=[]
    for site in db.execute('SELECT building,generation FROM fleet_site WHERE city=? AND active=1 ORDER BY building',(city,)).fetchall():
        b,g=site[0],site[1]
        away=db.execute('SELECT count(*) FROM fleet_order WHERE city=? AND building=? AND generation=? AND assigned=1 AND home=0',(city,b,g)).fetchone()[0]
        t=db.execute('SELECT * FROM fleet_timer WHERE city=? AND building=? AND generation=?',(city,b,g)).fetchone()
        queue=[dict(id=r[0],kind=r[1],resource=r[2],quantity=r[3]) for r in db.execute('''SELECT t.id,t.kind,t.resource,t.quantity FROM fleet_order f
            JOIN live_transfer t ON t.id=f.id WHERE f.city=? AND f.building=? AND f.generation=? AND f.assigned=0 AND f.home=0
            AND t.state NOT IN ('finished','rejected') ORDER BY f.id LIMIT 8''',(city,b,g))]
        leave=-1;loaded=inbound=0
        if t:
            loaded,inbound=t['loaded'] or 0,t['inbound'] or 0;now=t['now'];left=[]
            if loaded>=CARAVAN_LOAD:left.append(0)
            if t['idle'] is not None:left.append(IDLE_TICKS-(now-t['idle']))
            if t['first'] is not None:left.append(MAX_WAIT_TICKS-(now-t['first']))
            if t['settled'] is not None:left.append(GRACE_TICKS-(now-t['settled']))
            if left:leave=max(0,min(left))
        out.append(dict(building=b,generation=g,away=1 if away else 0,loaded=loaded,inbound=inbound,leave=leave,queue=queue))
    return out

def decorate(db,t):
    row=db.execute('SELECT * FROM fleet_order WHERE id=?',(t['id'],)).fetchone()
    if row:t=dict(t,fleet=dict(row))
    if t.get('resource') and t.get('state') not in ('finished','rejected') and destination_ready(db,t['sender'],t['receiver']) is False:t=dict(t,dest_ready=False)
    return t

def returned(db,city,tid,post,recovered=False):
    row=db.execute('SELECT f.*,t.state FROM fleet_order f JOIN live_transfer t ON t.id=f.id WHERE f.id=?',(tid,)).fetchone()
    if not row or row['city']!=city or post!=[row['building'],row['generation']]:raise ValueError('wrong caravan return')
    if row['state']!='rejected' or not row['assigned']:raise ValueError('caravan cargo not settled')
    with db:
        db.execute('UPDATE fleet_order SET home=1 WHERE id=?',(tid,))
        if recovered:
            db.execute("UPDATE trade_agreement SET state='paused' WHERE transfer=? AND state='active'",(tid,))
    advance(db)


def receiver_exited(db,city,tid,post,proof,recovered=False):
    """Release the source slot only after settled delivery and receiver exit."""
    if type(tid)!=int or any(not isinstance(v,list) or any(type(n)!=int for n in v) for v in (post,proof)):raise ValueError('invalid caravan exit proof')
    row=db.execute('SELECT f.*,t.receiver,t.resource,t.quantity,t.state FROM fleet_order f JOIN live_transfer t ON t.id=f.id WHERE f.id=?',(tid,)).fetchone()
    if not row or row['receiver']!=city or post!=[row['building'],row['generation']]:raise ValueError('wrong caravan exit')
    if row['state']!='finished' or not row['assigned'] or proof!=[row['resource'],row['quantity'],2]:raise ValueError('caravan delivery not settled')
    with db:
        db.execute('UPDATE fleet_order SET home=1 WHERE id=?',(tid,))
        if recovered:db.execute("UPDATE trade_agreement SET state='paused' WHERE transfer=? AND state='active'",(tid,))
    advance(db)
