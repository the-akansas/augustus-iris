"""24차 구매 계약 시뮬레이션: 실제 trade_agreements.advance + player_fleet.schedule,
게임 쪽(창고 일꾼, 상단 이동, 정산)만 단순 모형으로 흉내 낸다."""
import sqlite3,sys,time,uuid
from pathlib import Path;sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Augustus'))
import live_trade,player_fleet,trade_agreements,cash_live,joint_save,army_orders,army_install,city_trade_routes,trade_post_ledger
NAMES={1:'밀',15:'도자기',6:'점토'}
# 게임·네트워크 쪽은 막아 둔다(이 시뮬레이션은 출발 판단과 계약 회차만 본다).
# 이 파일은 불러오는 순간 실행된다(전체 시험이 모듈로 불러옴). 막아 둔 함수는 끝에서 되돌린다: 되돌리지 않으면 같은
# 프로세스의 다른 시험(구매 협상, 떠난 도시 교역, 캐러밴 기록)이 가짜 함수로 돌아 실패한다 (2026-11-15).
_STUBBED=[(joint_save,'pending'),(army_orders,'busy'),(army_install,'pending'),(cash_live,'ready'),(cash_live,'scope'),(cash_live,'trade'),
          (city_trade_routes,'require_posts'),(trade_agreements,'post'),(trade_post_ledger,'stage_offer')]
_ORIGINAL=[(m,n,getattr(m,n)) for m,n in _STUBBED]
joint_save.pending=lambda db:False;army_orders.busy=lambda db:False;army_install.pending=lambda room:False
cash_live.ready=lambda room,c:True;cash_live.scope=lambda room,db:None
city_trade_routes.require_posts=lambda *a,**k:None;trade_agreements.post=lambda db,s,v,ready=True:v
def stage_offer(db,cities,sender,key,receiver,res,qty,money):
    db.execute("INSERT OR REPLACE INTO post_contract(id,phase,quantity,money) VALUES(?,?,?,?)",(key,'offered',qty,money))
trade_post_ledger.stage_offer=stage_offer
def accept(room,db,city,r,t):
    db.execute("UPDATE goods_motion SET accepted=1 WHERE id=?",(t['id'],));db.execute("UPDATE live_transfer SET state='queued' WHERE id=?",(t['id'],));db.commit()
cash_live.trade=accept
class Room:
    started=True
    def __init__(s):s.coordinator=type('C',(),{'scenario':{'cities':['a','b']},'path':':memory:','post_protocol':2})();s.tick=0;s.post_load={};s.progress={};s.trade_stock={}
    def clock(s):return 1000.0
    def active_cities(s,db):return ['a','b']
db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
live_trade.initialize(db);cash_live.initialize(db);trade_agreements.initialize(db)
import goods_live;goods_live.initialize(db) if hasattr(goods_live,'initialize') else None
db.execute("CREATE TABLE IF NOT EXISTS post_contract(id TEXT PRIMARY KEY,phase TEXT,quantity INTEGER,money INTEGER)")
db.execute("CREATE TABLE IF NOT EXISTS post_meta(x)")
player_fleet.register(db,'a',[[59,58,1]]);db.commit()
room=Room()
store={1:40,15:21}          # 카푸아 창고(교역소 밖)
post={}                      # 카푸아 교역소 안
HAUL=3                       # 창고 일꾼이 하루에 교역소로 옮기는 포대
travel={}                    # 운송편 -> 돌아오는 틱
def day():
    room.tick+=50;t=room.tick
    # 창고 -> 교역소: 대기열 주문 순서대로 필요한 만큼만 옮긴다(교역소는 비워 두는 규칙).
    need={}
    for r in db.execute("SELECT t.resource,t.quantity FROM fleet_order f JOIN live_transfer t ON t.id=f.id JOIN goods_motion m ON m.id=f.id WHERE f.assigned=0 AND f.home=0 AND m.accepted=1 ORDER BY f.id"):
        need[r[0]]=need.get(r[0],0)+r[1]
    moved=globals()['HAUL'];inbound={}
    for res,q in need.items():
        want=max(0,q-post.get(res,0));step=min(want,moved,store.get(res,0))
        if step:post[res]=post.get(res,0)+step;store[res]-=step;moved-=step
        if want-step>0 and store.get(res,0)>0:inbound[res]=min(want-step,4)
    room.post_load={'a':(time.monotonic(),{(59,58):{r:(post.get(r,0),inbound.get(r,0)) for r in set(post)|set(inbound)}})}
    room.progress={'a':(t,)};room.trade_stock={'a':(1000.0,dict(store))}
    a0=db.execute('SELECT state,cycle FROM trade_agreement').fetchone()
    trade_agreements.advance(room,db)
    a1=db.execute('SELECT state,cycle FROM trade_agreement').fetchone()
    if a0 and tuple(a0)!=tuple(a1):print(f'  {t//50:>3}일: 계약 {a1[0]} · 회차 {a1[1]} 발행' if a1[1]!=a0[1] else f'  {t//50:>3}일: 계약 상태 {a1[0]}')
    before={r[0] for r in db.execute('SELECT DISTINCT shipment FROM fleet_order WHERE assigned=1')}
    player_fleet.schedule(room,db)
    for sid in {r[0] for r in db.execute('SELECT DISTINCT shipment FROM fleet_order WHERE assigned=1 AND home=0')}-before-set(travel):
        rows=db.execute('SELECT t.* FROM fleet_order f JOIN live_transfer t ON t.id=f.id WHERE f.shipment=?',(sid,)).fetchall()
        for x in rows:post[x['resource']]-=x['quantity']
        travel[sid]=t+20*50
        print(f'  {t//50:>3}일: 운송편 {sid} 출발 = '+' + '.join(f"#{x["id"]} {NAMES[x["resource"]]} {x["quantity"]}" for x in rows)+f" (합 {sum(x['quantity'] for x in rows)}포대)")
    for sid,back in list(travel.items()):
        if t>=back:
            ids=[r[0] for r in db.execute('SELECT id FROM fleet_order WHERE shipment=?',(sid,))]
            for i in ids:db.execute("UPDATE live_transfer SET state='finished' WHERE id=?",(i,));db.execute('UPDATE fleet_order SET home=1 WHERE id=?',(i,))
            db.commit();del travel[sid];print(f'  {t//50:>3}일: 운송편 {sid} 정산·귀환 ({", ".join("#"+str(i) for i in ids)})')
def order(kind,res,qty,money):
    key=uuid.uuid4().hex
    tid=db.execute("INSERT INTO live_transfer(request,sender,receiver,resource,quantity,money,kind,state) VALUES(?,?,?,?,?,?,?,'queued')",(key,'a','b',res,qty,money,kind)).lastrowid
    db.execute('INSERT INTO cash_transfer VALUES(?,?)',(tid,key));stage_offer(db,None,'a',key,'b',res,qty,money)
    player_fleet.reserve(db,'a',tid,[59,58]);db.execute('INSERT INTO goods_motion(id,route,accepted) VALUES(?,2,1)',(tid,));db.commit();return tid
def agreement(qty,money,repeat):
    db.execute("INSERT INTO trade_agreement(request,proposer,seller,buyer,resource,quantity,money,repeat,state,post,generation) VALUES(?,?,?,?,?,?,?,?,'active',59,58)",(uuid.uuid4().hex,'b','a','b',1,qty,money,repeat));db.commit()
def contract_state():
    a=db.execute('SELECT * FROM trade_agreement').fetchone()
    return f"계약 {a['state']} · 회차 {a['cycle']}"
print("[시나리오] 카푸아(판매자) -> 타렌툼(구매자)")
print('1) 일반 판매 #1 도자기 5포대가 먼저 대기 중일 때, 구매 계약(밀 20포대, 1회)이 체결된다')
order('sale',15,5,100);agreement(20,200,0)
for _ in range(70):
    day()
    if not travel and db.execute("SELECT state FROM trade_agreement").fetchone()[0]=='complete':break
print('  ->',contract_state())
for r in db.execute('SELECT t.id,t.resource,t.quantity,t.money,f.shipment,f.origin FROM live_transfer t JOIN fleet_order f ON f.id=t.id ORDER BY t.id'):
    print(f"     #{r['id']} {NAMES[r['resource']]} {r['quantity']}포대 {r['money']} Dn · 운송편 {r['shipment']}"+(f" · #{r['origin']}에서 나뉨" if r['origin'] else ''))

print()
print('2) 지속 구매 계약: 밀 32포대씩(320 Dn), 매 회차 16+16으로 나뉘어 가고, 두 짐이 모두 돌아와야 다음 회차가 나온다')
db.execute('DELETE FROM trade_agreement');db.commit()
store[1]=80;HAUL=16
agreement(32,320,1)
for _ in range(110):day()
print('  ->',contract_state())
# 결과 확인: 판매와 계약이 한 상단(16포대)에 합승, 32포대는 16+16, 두 짐이 다 돌아온 뒤에만 다음 회차.
rows={r['id']:dict(r) for r in db.execute('SELECT t.id,t.resource,t.quantity,f.shipment,f.origin FROM live_transfer t JOIN fleet_order f ON f.id=t.id')}
assert rows[1]['shipment']==rows[2]['shipment']==1 and rows[1]['quantity']+rows[2]['quantity']==16,rows
assert rows[3]['origin']==2 and rows[3]['shipment']==2,rows
assert [rows[i]['quantity'] for i in (4,5,6,7)]==[16,16,16,16] and rows[5]['origin']==4 and rows[7]['origin']==6,rows
assert db.execute('SELECT cycle FROM trade_agreement').fetchone()[0]==2
print('ok contract simulation')
for _m,_n,_v in _ORIGINAL:setattr(_m,_n,_v)   # back to the real functions for the other tests
