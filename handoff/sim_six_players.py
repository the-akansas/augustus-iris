"""6인 정상 플레이 압축 시뮬레이션 (교역 계약·교역소·선물·판매·구매 제안).

방 쪽 규칙은 실제 모듈을 그대로 쓴다: city_trade_routes, live_trade(제안·거절·정리),
trade_agreements(구매/판매 계약, 조정, 회차, 납기), player_fleet(상단 합승·출발).
게임 쪽(창고 일꾼, 상단 이동, 하역·정산)만 단순 모형이다.
보는 것: 예외, 물품·돈 보존, 상단 규칙, 그리고 '멈춰 버린 거래'(정상 플레이에서 풀리지 않는 상태).
"""
import collections,random,sqlite3,sys,time,traceback,uuid
from pathlib import Path;sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Augustus'))
import live_trade,player_fleet,trade_agreements,cash_live,joint_save,army_orders,army_install,city_trade_routes,trade_post_ledger,goods_live

CITIES=['c1','c2','c3','c4','c5','c6'];GOODS=sorted(live_trade.RESOURCES.values())[:6]
# The model replaces these room functions for the whole process. restore() puts the real ones back: a test that uses
# the model calls it when it ends, or the tests run after it in the same process use the model's stand-ins (2026-11-15).
_REPLACED=[(joint_save,'pending'),(army_orders,'busy'),(army_install,'pending'),(cash_live,'ready'),(cash_live,'scope'),(cash_live,'materialize'),
           (cash_live,'trade'),(trade_post_ledger,'stage_offer')]
_ORIGINAL=[(m,n,getattr(m,n)) for m,n in _REPLACED]
def restore():
    for m,n,v in _ORIGINAL:setattr(m,n,v)
def replace():
    joint_save.pending=lambda db:False;army_orders.busy=lambda db:False;army_install.pending=lambda room:False
    cash_live.ready=lambda room,c:all(x in room.active for x in c);cash_live.scope=lambda room,db:None;cash_live.materialize=lambda room,db:None
replace()

class Sim:
    def __init__(s,seed,leave=True):
        replace()   # again: a test before may have called restore()
        s.rng=random.Random(seed);s.seed=seed;s.allow_leave=leave
        s.db=sqlite3.connect(':memory:');s.db.row_factory=sqlite3.Row
        live_trade.initialize(s.db);joint_save.initialize(s.db)
        s.db.execute('CREATE TABLE IF NOT EXISTS lobby_invite(token TEXT,city TEXT)')
        for c in CITIES:s.db.execute('INSERT INTO lobby_invite VALUES(?,?)',(c,c))
        s.db.execute("CREATE TABLE IF NOT EXISTS post_contract(id TEXT PRIMARY KEY,phase TEXT,quantity INTEGER,money INTEGER,cancel INTEGER DEFAULT 0,received INTEGER DEFAULT 0,sender TEXT,receiver TEXT)")
        s.db.execute("CREATE TABLE IF NOT EXISTS post_meta(x)");s.db.commit()
        s.active=list(CITIES);s.tick=0;s.now=1000.0
        s.coordinator=type('C',(),{'scenario':{'cities':CITIES},'path':':memory:','post_protocol':2,'session':'s'})()
        s.started=True;s.progress={};s.post_load={};s.trade_stock={};s.trade_storage_stock={}
        s.store={c:{g:s.rng.choice([0,0,10,30,60]) for g in GOODS} for c in CITIES}
        s.money={c:5000 for c in CITIES};s.post={};s.posts={c:{} for c in CITIES};s.next_building={c:10 for c in CITIES}
        s.transit={};s.exiting={};s.noroad={};s.made=collections.Counter({g:sum(s.store[c][g] for c in CITIES) for g in GOODS})
        s.problems=[];s.log=collections.Counter();s.rejections=collections.Counter()
        cash_live.trade=s.native_trade;trade_post_ledger.stage_offer=s.stage
    # ---- room interface the modules expect
    def clock(s):return s.now
    def active_cities(s,db):return list(s.active)
    def stage(s,db,cities,sender,key,receiver,res,qty,money,route='land'):
        db.execute("INSERT OR REPLACE INTO post_contract(id,phase,quantity,money,sender,receiver) VALUES(?,?,?,?,?,?)",(key,'offered',qty,money,sender,receiver))
    # ---- the game side of one transfer (stands in for cash_live/goods_live + native receipts)
    def native_trade(s,room,db,city,r,t):
        t=dict(db.execute('SELECT * FROM live_transfer WHERE id=?',(t['id'],)).fetchone());op=r['op']
        if op=='live_status':return t
        if not db.execute('SELECT 1 FROM post_contract WHERE id=?',(t['request'],)).fetchone():s.stage(db,None,t['sender'],t['request'],t['receiver'],t['resource'],t['quantity'],t['money'])
        if op=='live_accept':
            if city!=t['receiver']:raise ValueError('recipient consent required')
            if t['state']=='rejected':raise ValueError('cancelled offer')
            if not {t['sender'],t['receiver']}<=set(s.active):raise ValueError('both engines required')
            if t['state']=='offered' and not t['resource']:      # money gift: paid at once
                if s.money[t['sender']]<t['money']:raise ValueError('자금이 부족합니다.')
                s.money[t['sender']]-=t['money'];s.money[t['receiver']]+=t['money'];db.execute("UPDATE live_transfer SET state='finished' WHERE id=?",(t['id'],))
            elif t['state']=='offered':
                db.execute('UPDATE goods_motion SET accepted=1 WHERE id=?',(t['id'],));db.execute("UPDATE live_transfer SET state='queued' WHERE id=?",(t['id'],))
        elif op=='live_reject':
            if t['state'] in ('finished',):raise ValueError('already received; settlement must finish')
            if t['state']!='rejected':
                if t['id'] in s.transit:                         # caravan turns back: goods return to the sender
                    s.store[t['sender']][t['resource']]+=t['quantity'];del s.transit[t['id']]
                db.execute("UPDATE live_transfer SET state='rejected' WHERE id=?",(t['id'],));db.execute("UPDATE post_contract SET phase='cancelled' WHERE id=?",(t['request'],))
        else:raise ValueError('unsupported')
        db.commit();player_fleet.advance(db,room)
        return dict(db.execute('SELECT * FROM live_transfer WHERE id=?',(t['id'],)).fetchone())
    # ---- helpers
    def call(s,what,fn,*a,**k):
        """A player's action: a Korean/English ValueError is a normal refusal, anything else is a bug."""
        try:out=fn(*a,**k);s.log[what]+=1;return out
        except ValueError as e:s.db.rollback();s.rejections[f'{what}: {e}']+=1;return None   # the room drops a refused request's connection
        except Exception:s.problems.append(f'[예외] {what} (seed {s.seed}, {s.tick//50}일)\n'+traceback.format_exc(limit=4));return None
    def engine(s,what,fn,*a,**k):
        """The game's own periodic calls: these must never fail."""
        try:return fn(*a,**k)
        except Exception as e:s.problems.append(f'[엔진 호출 실패] {what}: {type(e).__name__}: {e} (seed {s.seed}, {s.tick//50}일)\n'+traceback.format_exc(limit=4));return None
    def rows(s,q,*a):return [dict(r) for r in s.db.execute(q,a).fetchall()]
    def site(s,city,peer):return s.posts[city].get(peer)
    def register(s,city):
        roster=sorted(CITIES)
        s.engine('교역소 목록 보고',city_trade_routes.register,s.db,CITIES,city,[[b,g,roster.index(p)+1] for p,(b,g) in s.posts[city].items()])
        s.engine('상단 목록 보고',player_fleet.register,s.db,city,[[b,g,0 if s.noroad.get((city,b),0)>s.tick else 1] for p,(b,g) in s.posts[city].items()])
    # ---- one game day
    def day(s,acts=True):
        s.tick+=50;s.now+=1.0
        for c in s.active:
            s.progress[c]=(s.tick,s.now)
            if acts and s.rng.random()<0.25:g=s.rng.choice(GOODS);n=s.rng.randint(1,8);s.store[c][g]+=n;s.made[g]+=n   # production
        if acts:
            for c in list(s.active):
                for _ in range(s.rng.choice([0,0,1,1,2])):s.act(c)
        for (c,b),until in list(s.noroad.items()):
            if until<=s.tick:
                del s.noroad[(c,b)]
                if c in s.active:s.register(c)
        for c in s.active:s.haul(c)
        for c in s.active:
            s.engine('재고 보고',trade_agreements.request,s,s.db,c,dict(op='agreement_poll',stock=[[g,s.store[c][g]+sum(s.post.get((c,b,gen),{}).get(g,0) for b,gen in s.posts[c].values())] for g in GOODS],storage_stock=[[g,s.store[c][g]] for g in GOODS]))
            s.engine('운송 보고',live_trade.request,s,s.db,c,dict(op='live_batch'))
        s.depart();s.arrive();s.check()
    def haul(s,c):
        load=[]
        for peer,(b,g) in s.posts[c].items():
            box=s.post.setdefault((c,b,g),collections.Counter());need=collections.Counter();left=5
            for r in s.rows("SELECT t.id,t.resource,t.quantity FROM fleet_order f JOIN live_transfer t ON t.id=f.id JOIN goods_motion m ON m.id=f.id WHERE f.city=? AND f.building=? AND f.generation=? AND f.home=0 AND m.accepted=1 AND t.state NOT IN ('finished','rejected') ORDER BY f.id",c,b,g):
                if r['id'] not in s.transit:need[r['resource']]+=r['quantity']   # queued, or loaded and about to leave
            inbound=collections.Counter()
            for res,q in need.items():
                want=max(0,q-box[res]);step=min(want,left,s.store[c][res])
                box[res]+=step;s.store[c][res]-=step;left-=step
                if want-step>0 and s.store[c][res]>0:inbound[res]=min(want-step,4)
            for res in list(box):                                   # the post is kept empty: surplus goes back to storage
                extra=box[res]-need[res]
                if extra>0:box[res]-=extra;s.store[c][res]+=extra
            load+=[[b,g,res,box[res],inbound[res]] for res in set(box)|set(inbound) if box[res] or inbound[res]]
        s.engine('교역소 짐 보고',player_fleet.report_load,s,c,load)
    def depart(s):
        for r in s.rows("SELECT f.*,t.sender,t.receiver,t.resource,t.quantity,t.state FROM fleet_order f JOIN live_transfer t ON t.id=f.id WHERE f.assigned=1 AND f.home=0 AND t.state NOT IN ('finished','rejected')"):
            if r['id'] in s.transit or r['id'] in s.exiting or r['sender'] not in s.active:continue
            if r['receiver'] not in s.active:continue            # real room: 'participant unavailable' at collection
            box=s.post.get((r['sender'],r['building'],r['generation']),collections.Counter())
            if box[r['resource']]<r['quantity']:
                s.problems.append(f"[상단] 실리지 않은 짐이 출발 지시됨: 주문 #{r['id']} {r['quantity']}포대, 교역소에는 {box[r['resource']]} (seed {s.seed})");continue
            box[r['resource']]-=r['quantity'];s.transit[r['id']]=s.tick+4*50
            s.db.execute("UPDATE live_transfer SET state='travelling' WHERE id=?",(r['id'],));s.db.execute("UPDATE post_contract SET phase='travel' WHERE id=(SELECT request FROM live_transfer WHERE id=?)",(r['id'],));s.db.commit()
    def arrive(s):
        for tid,due in list(s.transit.items()):
            t=dict(s.db.execute('SELECT * FROM live_transfer WHERE id=?',(tid,)).fetchone())
            if s.tick<due or t['receiver'] not in s.active or t['sender'] not in s.active:continue
            there=s.posts[t['receiver']].get(t['sender'])
            if not there:                                        # the receiving post was demolished: the caravan turns back
                s.engine('운송 실패 보고',s.native_trade,s,s.db,t['receiver'],dict(op='live_reject'),t);s.log['받는 교역소 없음: 반환']+=1;continue
            if s.noroad.get((t['receiver'],there[0]),0)>s.tick:s.log['받는 교역소 길 없음: 대기(일)']+=1;continue
            s.store[t['receiver']][t['resource']]+=t['quantity'];s.money[t['receiver']]-=t['money'];s.money[t['sender']]+=t['money']
            s.db.execute("UPDATE live_transfer SET state='finished' WHERE id=?",(tid,));s.db.execute("UPDATE post_contract SET phase='complete',received=1 WHERE id=?",(t['request'],));s.db.commit()
            del s.transit[tid];s.exiting[tid]=s.tick+50;s.log['정산']+=1
        for r in s.rows("SELECT f.id,f.city,f.building,f.generation FROM fleet_order f JOIN live_transfer t ON t.id=f.id WHERE f.assigned=1 AND f.home=0 AND t.state='rejected'"):
            if r['city'] in s.active and r['id'] not in s.transit:s.engine('빈 상단 귀환 보고',player_fleet.returned,s.db,r['city'],r['id'],[r['building'],r['generation']])
        for tid,due in list(s.exiting.items()):
            t=dict(s.db.execute('SELECT t.*,f.building,f.generation FROM live_transfer t JOIN fleet_order f ON f.id=t.id WHERE t.id=?',(tid,)).fetchone())
            if s.tick<due or t['receiver'] not in s.active:continue
            s.engine('상단 퇴장 보고',player_fleet.receiver_exited,s.db,t['receiver'],tid,[t['building'],t['generation']],[t['resource'],t['quantity'],2]);del s.exiting[tid]
    # ---- what a normal player does
    def act(s,c):
        r=s.rng;peer=r.choice([x for x in CITIES if x!=c]);db=s.db;pair=tuple(sorted((c,peer)))
        link=db.execute('SELECT * FROM city_trade_link WHERE a=? AND b=?',pair).fetchone()
        choice=r.random()
        if not link or link['state']=='rejected':
            if choice<0.5 and peer in s.active:s.call('교역 계약 제안',city_trade_routes.request,db,CITIES,c,'route_offer',peer,request_id=uuid.uuid4().hex)
            return
        if link['state']=='offered':
            if link['proposer']!=c:s.call('교역 계약 수락' if choice<0.85 else '교역 계약 거절',city_trade_routes.request,db,CITIES,c,'route_accept' if choice<0.85 else 'route_reject',peer,revision=link['revision'])
            return
        if not s.site(c,peer):                                   # contract concluded: build my post
            if choice<0.7:b=s.next_building[c];s.next_building[c]+=1;s.posts[c][peer]=(b,b+100);s.register(c);s.log['교역소 건설']+=1
            return
        mine=list(s.site(c,peer))
        # answer what waits on me first (a normal player clears the inbox)
        for t in s.rows("SELECT * FROM live_transfer WHERE receiver=? AND sender=? AND state='offered'",c,peer):
            if db.execute('SELECT 1 FROM trade_agreement WHERE transfer=?',(t['id'],)).fetchone():continue
            s.call('제안 수락' if r.random()<0.8 else '제안 거절',live_trade.request,s,db,c,dict(op='live_accept' if r.random()<0.8 else 'live_reject',id=t['id']));return
        for a in s.rows("SELECT * FROM trade_agreement WHERE state='offered' AND proposer!=? AND (seller=? OR buyer=?) AND (seller=? OR buyer=?)",c,c,c,peer,peer):
            x=r.random();base=dict(id=a['id'],revision=a['revision'],request_id=uuid.uuid4().hex,post=mine if a['seller']==c else [0,0])
            if x<0.55:s.call('계약 제안 수락',trade_agreements.request,s,db,c,dict(op='agreement_accept',**base))
            elif x<0.8:s.call('거래 조정',trade_agreements.request,s,db,c,dict(op='agreement_counter',quantity=r.randint(1,32),money=r.randint(1,32)*r.randint(1,30),**base))
            else:s.call('계약 제안 거절',trade_agreements.request,s,db,c,dict(op='agreement_stop',**base))
            return
        if choice<0.22:
            g=r.choice(GOODS);s.call('선물 보내기',live_trade.request,s,db,c,dict(op='live_offer',request_id=uuid.uuid4().hex,kind='gift',receiver=peer,resource=g,quantity=r.randint(1,32),money=0,post=mine))
        elif choice<0.44:
            g=r.choice(GOODS);q=r.randint(1,32);s.call('판매 제안',live_trade.request,s,db,c,dict(op='live_offer',request_id=uuid.uuid4().hex,kind='sale',receiver=peer,resource=g,quantity=q,money=q*r.randint(1,30),post=mine))
        elif choice<0.52:
            s.call('돈 보내기',live_trade.request,s,db,c,dict(op='live_offer',request_id=uuid.uuid4().hex,kind='gift',receiver=peer,resource=0,quantity=0,money=r.choice([100,500,1000])))
        elif choice<0.72:
            g=r.choice(GOODS);q=r.randint(1,32);mode=r.choice(['buy','buy','sell'])
            s.call('구매 제안' if mode=='buy' else '지속 판매 제안',trade_agreements.request,s,db,c,dict(op='agreement_offer',request_id=uuid.uuid4().hex,mode=mode,peer=peer,resource=g,quantity=q,money=q*r.randint(1,30),repeat=r.choice([0,0,1]),post=mine if mode=='sell' else [0,0],allow_partial=r.choice([0,1]) if mode=='buy' else 0))
        elif choice<0.78:
            for t in s.rows("SELECT * FROM live_transfer WHERE sender=? AND state IN ('offered','queued') ORDER BY RANDOM() LIMIT 1",c):
                if not db.execute('SELECT 1 FROM trade_agreement WHERE transfer=?',(t['id'],)).fetchone():s.call('보낸 제안 취소',live_trade.request,s,db,c,dict(op='live_reject',id=t['id']))
        elif choice<0.82:
            for a in s.rows("SELECT * FROM trade_agreement WHERE state IN ('active','paused') AND (seller=? OR buyer=?) ORDER BY RANDOM() LIMIT 1",c,c):
                op='agreement_stop' if a['state']=='active' or r.random()<0.5 else 'agreement_resume'
                s.call('계약 중단' if op=='agreement_stop' else '계약 다시 제안',trade_agreements.request,s,db,c,dict(op=op,id=a['id'],revision=a['revision'],request_id=uuid.uuid4().hex,post=list(s.site(c,a['buyer'] if a['seller']==c else a['seller']) or [0,0])))
        elif choice<0.835:                                        # rebuild the post somewhere else (demolish, build again)
            del s.posts[c][peer];s.register(c);s.log['교역소 철거']+=1
        elif choice<0.86:                                         # re-laying roads: the post is cut off for a few days
            s.noroad[(c,mine[0])]=s.tick+50*r.randint(1,6);s.register(c);s.log['교역소 길 끊김']+=1
        elif choice<0.863 and s.allow_leave and len(s.active)>4 and s.tick>60*50:
            s.active.remove(c);s.progress.pop(c,None);s.log['플레이어 나감']+=1
    # ---- invariants
    def check(s):
        for g in GOODS:
            have=sum(s.store[c][g] for c in CITIES)+sum(box[g] for box in s.post.values())+sum(t['quantity'] for t in s.rows('SELECT resource,quantity FROM live_transfer WHERE id IN (%s)'%(','.join(map(str,s.transit)) or '0')) if t['resource']==g)
            if have!=s.made[g]:s.problems.append(f'[보존] 물품 {g}: 있어야 할 {s.made[g]}, 실제 {have} (seed {s.seed}, {s.tick//50}일)');s.made[g]=have
        if sum(s.money.values())!=5000*len(CITIES):s.problems.append(f'[보존] 돈 합계 {sum(s.money.values())} (seed {s.seed})');s.money[CITIES[0]]+=5000*len(CITIES)-sum(s.money.values())
        for r in s.rows("SELECT f.city,f.building,f.generation,count(DISTINCT f.shipment) n,sum(t.quantity) q FROM fleet_order f JOIN live_transfer t ON t.id=f.id WHERE f.assigned=1 AND f.home=0 GROUP BY 1,2,3"):
            if r['n']>1:s.problems.append(f"[상단] 한 교역소에서 운송편 {r['n']}개가 동시에 나가 있음 {r['city']} (seed {s.seed})")
        for r in s.rows("SELECT f.shipment,sum(t.quantity) q FROM fleet_order f JOIN live_transfer t ON t.id=f.id WHERE f.shipment>0 GROUP BY 1"):
            if r['q']>16:s.problems.append(f"[상단] 운송편 {r['shipment']}에 {r['q']}포대 (16 초과) (seed {s.seed})")
        for a in s.rows("SELECT * FROM trade_agreement WHERE transfer IS NOT NULL"):
            t=s.db.execute('SELECT * FROM live_transfer WHERE id=?',(a['transfer'],)).fetchone()
            if not t or (t['sender'],t['receiver'],t['resource'])!=(a['seller'],a['buyer'],a['resource']):s.problems.append(f"[계약] #{a['id']} 회차 주문이 계약과 다름 (seed {s.seed})")
    # ---- after the players stop: does everything come to rest?
    def settle(s):
        for c in s.active:
            for g in GOODS:s.store[c][g]+=200;s.made[g]+=200       # nobody is short of goods or money any more
        for _ in range(260):s.day(acts=False)
        stuck=collections.Counter();examples={}
        def note(kind,text):stuck[kind]+=1;examples.setdefault(kind,text)
        for t in s.rows("SELECT t.*,f.assigned,f.home,f.building,f.generation,m.accepted FROM live_transfer t LEFT JOIN fleet_order f ON f.id=t.id LEFT JOIN goods_motion m ON m.id=t.id WHERE t.state NOT IN ('finished','rejected')"):
            gone=[c for c in (t['sender'],t['receiver']) if c not in s.active]
            agreement=s.db.execute('SELECT id,state FROM trade_agreement WHERE transfer=?',(t['id'],)).fetchone()
            site=t['building'] and s.db.execute('SELECT active FROM fleet_site WHERE city=? AND building=? AND generation=?',(t['sender'],t['building'],t['generation'])).fetchone()
            where=f"#{t['id']} {t['kind']} {t['sender']}->{t['receiver']} 상태 {t['state']}"+(f" (계약 #{agreement['id']} {agreement['state']})" if agreement else '')
            if gone:note(('나간 플레이어와의 거래가 남음',t['state'],'계약 회차' if agreement else '일반'),where)
            elif t['state']=='offered':note(('받는 사람이 답하지 않은 제안',),where)       # players stopped acting: expected
            elif site is not None and not site[0]:note(('철거한 교역소에 묶인 주문',t['state']),where)
            elif agreement and agreement['state']=='active' and s.db.execute('SELECT repeat FROM trade_agreement WHERE id=?',(agreement['id'],)).fetchone()[0]:pass   # a repeating contract keeps running: expected
            else:
                there=s.posts[t['receiver']].get(t['sender'])
                note(('이유 없이 멈춘 주문',t['state'],'계약 회차' if agreement else '일반'),where+f" [배정 {t['assigned']} 귀환 {t['home']} 이동중 {t['id'] in s.transit} 퇴장중 {t['id'] in s.exiting} 받는교역소 {there} 길끊김 {bool(there) and s.noroad.get((t['receiver'],there[0]),0)>s.tick}]")
        for a in s.rows("SELECT * FROM trade_agreement WHERE state IN ('active','paused','offered')"):
            gone=[c for c in (a['seller'],a['buyer']) if c not in s.active]
            where=f"계약 #{a['id']} {a['seller']}->{a['buyer']} 상태 {a['state']} 반복 {a['repeat']} 회차 {a['cycle']}"
            if gone:note(('나간 플레이어와의 계약이 남음',a['state']),where)
            elif a['state']=='offered':note(('답하지 않은 계약 제안',),where)
            elif a['state']=='paused':note(('일시 중단된 계약(다시 제안 필요)',),where)
            elif a['state']=='active' and not a['repeat']:note(('한 번짜리 계약이 끝나지 않음',),where)
        return stuck,examples

def main(runs=40,days=420):
    problems=[];stuck=collections.Counter();examples={};log=collections.Counter();rejections=collections.Counter()
    for seed in range(runs):
        s=Sim(seed,leave=seed%2==0)
        for _ in range(days):s.day()
        st,ex=s.settle()
        problems+=s.problems;stuck.update(st);log.update(s.log);rejections.update(s.rejections)
        for k,v in ex.items():examples.setdefault(k,f'{v} (seed {seed})')
    print(f'== {runs}판 x {days}일, 6인');print('한 일:',dict(log.most_common()))
    print('\n== 문제(예외·보존·상단 규칙):',len(problems))
    seen=collections.Counter(p.split(' (seed')[0].split('\n')[0] for p in problems)
    for k,v in seen.most_common(20):print(f'  {v}회  {k}')
    for p in problems[:3]:print('---\n'+p)
    print('\n== 플레이어가 손을 뗀 뒤 260일이 지나도 남은 것')
    for k,v in sorted(stuck.items(),key=lambda x:-x[1]):print(f'  {v}건  {" / ".join(k)}\n        예: {examples[k]}')
    print('\n== 거절된 행동(상위)')
    for k,v in rejections.most_common(25):print(f'  {v}회  {k}')
    return problems,stuck
if __name__=='__main__':main(int(sys.argv[1]) if len(sys.argv)>1 else 40)
