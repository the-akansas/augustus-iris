"""Repeating contracts: a round the host issues and accepts by itself must not raise contract alarms.
Bug 2026-11-12: with "repeat" checked, every round showed up as a new trade offer to the buyer
(fanfare via trade-notify.txt, "미확인 거래 제안" banner, offer button) and the seller got
"거래 제안이 수락되었습니다" again.

Room side is the real code (trade_agreements, live_trade, player_fleet, city_trade_routes); the game side
(warehouse workers, caravans, settlement) is the simple model of sim_six_players. Client side is the real
agreement_bridge.publish / city_notices.trade / fleet_bridge offer selection on a stand-in bridge folder."""
import sys,tempfile,unittest,uuid
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Augustus'));sys.path.insert(0,str(ROOT/'handoff'))
import sim_six_players as sim
def tearDownModule():sim.restore()   # the real room functions for the tests after this one
import live_trade,trade_agreements,city_trade_routes,agreement_bridge,city_notices,fleet_bridge

SELLER,BUYER,OTHER='c1','c2','c3'

class Bridge:
    """The parts of game_bridge the presentation code touches."""
    def __init__(s,root,city):
        s.root=Path(root);s.root.mkdir(parents=True,exist_ok=True);s.client=SimpleNamespace(city=city,session='s1');s.city_names=None
        s.files={};s.fanfares=0;s.seen_offer=0
    def write_changed(s,name,text):s.files[name]=text;(s.root/name).write_text(text,encoding='utf8');return True
    def events(s):return [e[3] for e in city_notices.state(s)['log']]

class World:
    def __init__(s,tmp):
        s.s=sim.Sim(7,leave=False);w=s.s
        for c in sim.CITIES:w.store[c]={g:0 for g in sim.GOODS}
        s.good=sim.GOODS[0];w.store[SELLER][s.good]=200
        db=w.db
        for a,b in ((SELLER,BUYER),(SELLER,OTHER)):
            city_trade_routes.request(db,sim.CITIES,a,'route_offer',b,request_id=uuid.uuid4().hex)
            link=db.execute('SELECT * FROM city_trade_link WHERE a=? AND b=?',tuple(sorted((a,b)))).fetchone()
            city_trade_routes.request(db,sim.CITIES,b,'route_accept',a,revision=link['revision'])
        for c,peers in ((SELLER,(BUYER,OTHER)),(BUYER,(SELLER,)),(OTHER,(SELLER,))):
            for p in peers:n=w.next_building[c];w.next_building[c]+=1;w.posts[c][p]=(n,n+100)
            w.register(c)
        s.bridges={c:Bridge(Path(tmp)/c,c) for c in (SELLER,BUYER,OTHER)}
        s.rounds_seen=0
    def poll(s,city,bridge=None):
        """One client poll: the same server calls as live_sync, then the client's presentation code."""
        w=s.s;db=w.db;b=bridge or s.bridges[city]
        stock=[[g,w.store[city][g]+sum(w.post.get((city,x,gen),{}).get(g,0) for x,gen in w.posts[city].values())] for g in sim.GOODS]
        ag=trade_agreements.request(w,db,city,dict(op='agreement_poll',stock=stock,storage_stock=[[g,w.store[city][g]] for g in sim.GOODS]))
        rows=live_trade.request(w,db,city,dict(op='live_batch'));history=live_trade.request(w,db,city,dict(op='live_history'))
        b.agreements=ag['agreements']
        agreement_bridge.publish(b,ag)
        city_notices.trade(b,rows+[t for t in history if t['state'] in ('finished','rejected') and t['id'] not in {r['id'] for r in rows}])
        inbox=rows[0].get('inbox',[0,0,0]) if rows else [0,0,0]
        # trade-notify.txt drives the fanfare: a larger latest id with a non-zero count plays it (multiplayer_lobby.c).
        if inbox[0] and inbox[2]>b.seen_offer:b.fanfares+=1
        if inbox[2]>b.seen_offer:b.seen_offer=inbox[2]
        b.offers=fleet_bridge.incoming_offers(b,rows)
        b.inbox=inbox[0]
        return rows
    def day(s,order=(BUYER,SELLER,OTHER)):
        for c in order:s.poll(c);s.check(c)
        s.s.day(acts=False)
    def check(s,c):
        b=s.bridges[c];linked={a['transfer'] for a in b.agreements if a.get('transfer')}
        s.max_inbox=max(getattr(s,'max_inbox',0),b.inbox)
        s.linked_offer=getattr(s,'linked_offer',False) or bool(set(b.offers)&linked)
    def agreement(s,i):return dict(s.s.db.execute('SELECT * FROM trade_agreement WHERE id=?',(i,)).fetchone())
    def offer(s,repeat,buyer=BUYER,qty=4,money=40):
        s.poll(SELLER)                                                # the seller's stock report comes first
        a=trade_agreements.request(s.s,s.s.db,SELLER,dict(op='agreement_offer',request_id=uuid.uuid4().hex,mode='sell',peer=buyer,resource=s.good,quantity=qty,money=money,repeat=repeat,post=list(s.s.posts[SELLER][buyer]),allow_partial=0))
        return a['id']
    def accept(s,i,city=BUYER):
        a=s.agreement(i);trade_agreements.request(s.s,s.s.db,city,dict(op='agreement_accept',id=i,revision=a['revision'],request_id=uuid.uuid4().hex,post=[0,0]))

def count(events,text):return sum(1 for e in events if text in e)

class RepeatContractNotices(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.w=World(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()

    def run_until(self,i,rounds,days=200):
        for _ in range(days):
            self.w.day()
            done=self.w.s.db.execute("SELECT count(*) FROM live_transfer WHERE state='finished' AND sender=? AND receiver=?",(SELLER,BUYER)).fetchone()[0]
            if done>=rounds and self.w.agreement(i)['cycle']>rounds:return done
        self.fail(f'rounds did not finish: {self.w.agreement(i)}')

    def test_repeat_rounds_raise_no_contract_alarms(self):
        w=self.w;i=w.offer(repeat=1)
        w.day()                                                       # the buyer sees the proposal
        buyer,seller=w.bridges[BUYER],w.bridges[SELLER]
        self.assertEqual(count(buyer.events(),'거래 제안이 왔습니다'),1)
        w.accept(i)
        money0=dict(w.s.money)
        finished=self.run_until(i,3)
        self.assertGreaterEqual(finished,3)
        self.assertGreaterEqual(w.agreement(i)['cycle'],4)           # rounds keep coming
        self.assertEqual(w.agreement(i)['state'],'active')
        self.assertGreater(w.s.money[SELLER],money0[SELLER]);self.assertLess(w.s.money[BUYER],money0[BUYER])
        # Decision notices: exactly once.
        self.assertEqual(count(buyer.events(),'거래 제안이 왔습니다'),1)
        self.assertEqual(count(seller.events(),'거래 제안을 수락했습니다'),1)
        # Rounds: no offer banner/fanfare/offer button on the buyer, no "accepted" card per round on the seller.
        self.assertEqual(w.max_inbox,0)
        self.assertEqual(buyer.fanfares,0)
        self.assertFalse(w.linked_offer)
        self.assertLessEqual(count(seller.events(),'거래 제안이 수락되었습니다'),1)  # first round only (existing behaviour)
        # Trade progress notices are not contract alarms and stay.
        self.assertGreaterEqual(count(seller.events(),'정산 완료'),3);self.assertGreaterEqual(count(buyer.events(),'정산 완료'),3)

    def test_round_issued_by_the_sellers_poll_is_quiet_too(self):
        w=self.w;i=w.offer(repeat=1);w.day();w.accept(i)
        for _ in range(200):
            for c in (SELLER,BUYER,OTHER):w.poll(c);w.check(c)
            w.s.day(acts=False)
            if w.agreement(i)['cycle']>3:break
        self.assertGreater(w.agreement(i)['cycle'],3)
        self.assertEqual(w.max_inbox,0);self.assertEqual(w.bridges[BUYER].fanfares,0);self.assertFalse(w.linked_offer)

    def test_counter_offer_and_plain_offer_still_alert(self):
        w=self.w;s=w.s;db=s.db
        i=w.offer(repeat=1);w.day()
        a=w.agreement(i)
        trade_agreements.request(s,db,BUYER,dict(op='agreement_counter',id=i,revision=a['revision'],request_id=uuid.uuid4().hex,quantity=3,money=36,post=[0,0]))
        w.day()
        self.assertEqual(count(w.bridges[SELLER].events(),'조건 조정 제안이 왔습니다'),1)   # a changed condition asks again
        # A plain sale offer (no contract) still asks the receiver, with the fanfare.
        live_trade.request(s,db,SELLER,dict(op='live_offer',request_id=uuid.uuid4().hex,kind='sale',receiver=OTHER,resource=w.good,quantity=2,money=20,post=list(s.posts[SELLER][OTHER])))
        w.poll(OTHER)
        other=w.bridges[OTHER]
        self.assertEqual(other.inbox,1);self.assertEqual(other.fanfares,1);self.assertEqual(len(other.offers),1)

    def test_refused_offer_and_expiry_still_notify(self):
        w=self.w;s=w.s;db=s.db
        i=w.offer(repeat=1);w.day();a=w.agreement(i)
        trade_agreements.request(s,db,BUYER,dict(op='agreement_stop',id=i,revision=a['revision'],request_id=uuid.uuid4().hex,post=[0,0]))
        w.day()
        self.assertEqual(count(w.bridges[SELLER].events(),'거래 제안을 거절했습니다'),1)
        # Expiry of an agreed contract: the seller has nothing to send for three months.
        s.store[SELLER][w.good]=4                                     # exactly one round of goods; the next round never gets any
        j=w.offer(repeat=1);w.day();w.accept(j)
        for _ in range(200):
            w.day()
            if w.agreement(j)['state']=='stopped':break
        self.assertEqual(w.agreement(j)['state'],'stopped');self.assertEqual(w.agreement(j)['expired'],1)
        w.day()
        self.assertEqual(count(w.bridges[SELLER].events(),'계약이 만료되었습니다'),1)
        self.assertEqual(count(w.bridges[BUYER].events(),'계약이 만료되었습니다'),1)

    def test_reconnect_and_repeated_replies_do_not_repeat_notices(self):
        w=self.w;i=w.offer(repeat=1);w.day();w.accept(i)
        self.run_until(i,3)
        before={c:list(b.events()) for c,b in w.bridges.items()}
        for c in (BUYER,SELLER):
            w.poll(c);w.poll(c)                                       # the same reply twice
            fresh=Bridge(w.bridges[c].root,c)                         # bridge restart: state comes back from its file
            fresh.agreement_previous=getattr(w.bridges[c],'agreement_previous',{})
            w.poll(c,fresh)
            self.assertEqual(fresh.events(),before[c]+[e for e in fresh.events()[len(before[c]):] if '정산 완료' in e or '도착' in e or '종료' in e])
            self.assertEqual(count(fresh.events(),'거래 제안이 왔습니다'),count(before[c],'거래 제안이 왔습니다'))
            self.assertEqual(count(fresh.events(),'거래 제안을 수락했습니다'),count(before[c],'거래 제안을 수락했습니다'))

if __name__=='__main__':unittest.main()
