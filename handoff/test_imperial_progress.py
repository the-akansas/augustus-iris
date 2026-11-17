"""황제의 순행 (user 2026-11-15): host rules of Augustus/imperial_progress.py."""
import copy,json,sqlite3,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'Augustus'))
import imperial_progress as ip,trade_post_ledger as tpl

CITIES=['p1','p2','p3'];M=ip.MONTH
def binding(**over):return dict(sha256='0'*64,cities=list(CITIES),progress=dict(ip.defaults(),**dict(dict(start_months=1,amount_min=32,amount_max=32),**over)))
def rid(n):return '%032x'%n

class Room(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=str(Path(self.tmp.name)/'room.db')
        tpl.Ledger(self.path,CITIES,transport=True).close()
        self.db=sqlite3.connect(self.path);self.db.row_factory=sqlite3.Row
        self.b=binding();ip.configure(self.db,self.b,0);self.db.commit();self.active=list(CITIES)
    def tearDown(self):self.db.close();self.tmp.cleanup()
    def go(self,tick,active=None):ip.advance(self.db,self.b,tick,self.active if active is None else active);self.db.commit();return ip.current(self.db,self.b)
    def receipt(self,applied=True):
        s=ip.current(self.db,self.b);cid=s['charge']['id']
        self.db.execute("UPDATE post_contract SET phase=?,exported=? WHERE id=?",('complete' if applied else 'cancelled',1 if applied else 0,cid));self.db.commit()
    def bid(self,city,n,amount,tick,funds=None):
        r=ip.bid(self.db,self.b,city,rid(n),amount,funds,tick,self.active);self.db.commit();return r
    def to_arrival(self,s):
        return self.go(s['arrive_tick'])

    def test_nothing_before_the_start_period(self):
        s=self.go(M-1);self.assertEqual((s['phase'],s['round']),('idle',0))
        self.assertTrue(ip.public_view(s)['first'])
        s=self.go(M);self.assertEqual((s['phase'],s['round']),('bidding',1))
        self.assertEqual(len(set(s['goods'])),3);self.assertIn(s['good'],s['goods'])

    def test_public_view_hides_bids_good_and_arrival(self):
        self.go(M);self.bid('p1',1,900,M+1)
        s=ip.current(self.db,self.b);p=ip.public_view(s);text=json.dumps(p)
        for k in ('good','amount','bids','arrive_tick','close_tick','nonce','queue'):self.assertNotIn('"%s"'%k,text)
        self.assertEqual(ip.view(s,'p1')['bid'],900);self.assertEqual(ip.view(s,'p2')['bid'],0)

    def test_one_bid_each_minimum_and_funds(self):
        self.go(M)
        self.assertEqual(self.bid('p1',1,499,M+1)['state'],'refused')
        self.assertEqual(self.bid('p1',1,2000,M+1,funds=1500)['state'],'refused')
        self.assertEqual(self.bid('p1',1,700,M+1,funds=1500)['state'],'accepted')
        self.assertTrue(self.bid('p1',1,700,M+1)['duplicate'])                       # resent
        self.assertEqual(self.bid('p1',2,800,M+2)['state'],'refused')                # a second bid
        self.assertEqual(self.db.execute('SELECT count(*) FROM post_contract').fetchone()[0],0)   # nothing charged at the bid
        self.assertEqual(self.bid('p2',3,800,2*M)['state'],'refused')                # after the close

    def test_highest_wins_tie_goes_to_the_earlier_and_only_the_winner_pays(self):
        self.go(M);self.bid('p2',1,900,M+1);self.bid('p1',2,900,M+2);self.bid('p3',3,600,M+3)
        s=self.go(2*M);self.assertEqual((s['phase'],s['charge']['city'],s['charge']['amount']),('charging','p2',900))
        self.assertEqual(ip.public_view(s)['holder'],None)
        self.receipt();s=self.go(2*M)
        self.assertEqual((s['phase'],s['holder'],s['chosen'],s['paid']),('travel','p2','bid',900))
        rows=self.db.execute('SELECT sender,money FROM post_contract').fetchall()
        self.assertEqual([tuple(r) for r in rows],[('p2',900)])
        self.assertTrue(2*M+2*M<=s['arrive_tick']<=2*M+4*M)

    def test_a_winner_who_cannot_pay_gives_way_to_the_next_bidder(self):
        self.go(M);self.bid('p1',1,5000,M+1);self.bid('p3',2,700,M+2)
        self.go(2*M);self.receipt(False);s=self.go(2*M)
        self.assertEqual(s['charge']['city'],'p3');self.receipt();s=self.go(2*M)
        self.assertEqual((s['holder'],s['paid'],s['paid_total']),('p3',700,dict(p1=0,p2=0,p3=700)))

    def test_no_bid_sends_the_emperor_to_a_random_city_for_free(self):
        self.go(M);s=self.go(2*M)
        self.assertEqual((s['phase'],s['chosen'],s['paid']),('travel','random',0));self.assertIn(s['holder'],CITIES)
        self.assertEqual(self.db.execute('SELECT count(*) FROM post_contract').fetchone()[0],0)

    def visit(self,taken,funds=None):
        self.go(M);self.bid('p1',1,500,M+1);self.go(2*M);self.receipt();s=self.go(2*M);s=self.to_arrival(s)
        self.assertEqual(s['phase'],'arrived');order=ip.view(s,'p1')['order']
        self.assertEqual((order['resource'],order['amount']),(s['good'],32));self.assertIsNone(ip.view(s,'p2')['order'])
        self.assertTrue(ip.visit_report(self.db,self.b,'p1',order['id'],taken,funds,s['last_tick'],self.active));self.db.commit()
        return ip.current(self.db,self.b)

    def test_everything_served_gives_three(self):
        s=self.visit(40);self.assertEqual((s['phase'],s['favor']['p1']),('idle',3))
        r=s['results'][0];self.assertEqual((r['taken'],r['delta'],r['fine'],r['result']),(32,3,0,'full'))
        self.assertFalse(ip.visit_report(self.db,self.b,'p1',1,0,None,s['last_tick'],self.active))   # a second report changes nothing
    def test_half_gives_one(self):
        s=self.visit(16);self.assertEqual((s['favor']['p1'],s['results'][0]['fine']),(1,0))
    def test_less_than_half_costs_one_and_the_shortfall_in_money(self):
        s=self.visit(2,funds=100000);self.assertEqual((s['phase'],s['charge']['kind'],s['charge']['amount']),('fine','fine',30*100))
        self.receipt();s=self.go(s['last_tick'])
        self.assertEqual((s['phase'],s['favor']['p1'],s['results'][0]['fine']),('idle',-1,3000))
    def test_the_fine_is_at_most_what_the_city_has(self):
        s=self.visit(0,funds=450);self.assertEqual(s['charge']['amount'],450)
        self.receipt(False);s=self.go(s['last_tick']);self.assertEqual((s['favor']['p1'],s['results'][0]['fine']),(-1,0))
    def test_an_empty_treasury_is_not_fined(self):
        s=self.visit(0,funds=0);self.assertEqual((s['phase'],s['favor']['p1']),('idle',-1))
    def test_only_the_host_city_reports(self):
        self.go(M);s=self.go(2*M);s=self.to_arrival(s);other=next(c for c in CITIES if c!=s['holder'])
        self.assertFalse(ip.visit_report(self.db,self.b,other,1,32,None,s['last_tick'],self.active))

    def test_the_amount_is_drawn_for_each_progress_within_the_bounds(self):
        self.b=binding(amount_min=5,amount_max=9);self.db.execute('DELETE FROM progress_state');ip.configure(self.db,self.b,0)
        s=self.go(M);self.assertTrue(5<=s['amount']<=9)
        s=self.go(2*M);s=self.to_arrival(s);self.assertEqual(s['visit']['amount'],s['amount'])
        self.assertNotIn('amount',ip.public_view(s));self.assertEqual(ip.view(s,s['holder'])['order']['amount'],s['amount'])   # only the hosting game's engine

    def test_a_host_who_leaves_cancels_that_progress(self):
        self.go(M);self.bid('p1',1,500,M+1);self.go(2*M);self.receipt();s=self.go(2*M)
        s=self.go(2*M+1,active=['p2','p3'])
        self.assertEqual((s['phase'],s['results'][0]['result'],s['favor']['p1']),('idle','cancelled',0))

    def test_the_end_names_the_right_hand(self):
        self.b=binding(rounds=2,gap_months=0);self.db.execute('DELETE FROM progress_state');ip.configure(self.db,self.b,0)
        t=M
        for n,(city,taken) in enumerate([('p1',32),('p2',32)]):
            s=self.go(t);self.bid(city,10+n,500+n*100,s['last_tick']);s=self.go(s['close_tick']);self.receipt();s=self.go(s['last_tick']);s=self.to_arrival(s)
            ip.visit_report(self.db,self.b,city,s['visit']['id'],taken,None,s['last_tick'],self.active);self.db.commit();t=s['last_tick']
        s=ip.current(self.db,self.b)
        self.assertEqual((s['phase'],s['ended'],s['winners']),('ended',True,['p2']))   # equal favour: p2 paid the emperor more
        self.assertEqual(self.bid('p3',99,900,t+1)['state'],'refused')

    def test_a_joint_save_keeps_and_returns_the_state(self):
        self.go(M);self.bid('p1',1,900,M+1);ip.capture(self.db,7,self.b);self.db.commit()
        saved=ip.read(self.db,7,self.b);self.go(2*M)
        ip.restore(self.db,saved,self.b,M+1);self.assertEqual(ip.current(self.db,self.b),saved)
        self.db.execute("UPDATE joint_progress SET payload=replace(payload,'900','901')")
        with self.assertRaises(ValueError):ip.read(self.db,7,self.b)
        bad=copy.deepcopy(saved);bad['favor']['p9']=1
        with self.assertRaises(ValueError):ip.put(self.db,8,bad,self.b)

    def test_a_scenario_without_it_has_no_state(self):
        plain=dict(sha256='0'*64,cities=CITIES)
        self.assertIsNone(ip.current(self.db,plain));self.assertFalse(ip.advance(self.db,plain,5,CITIES));self.assertIsNone(ip.read(self.db,1,plain))

class Spec(unittest.TestCase):
    def test_limits(self):
        ip.validate_spec(ip.defaults())
        for k,v in dict(amount_max=33,amount_min=33,rounds=0,min_bid=0,goods=[1,2],prepare_min=5).items():
            with self.assertRaises(ValueError):ip.validate_spec(dict(ip.defaults(),**{k:v}))
    def test_project_mode_and_minimum_players(self):
        import scenario_project as sp
        d=json.loads((ROOT/'Augustus/scenarios/provincial-quartet/scenario.json').read_text(encoding='utf-8-sig'))
        self.assertEqual(sp.min_players(d),1)
        d['rules']['min_players']=3;sp.validate(d);self.assertEqual(sp.min_players(d),3)
        for bad in (0,5,'2'):
            x=copy.deepcopy(d);x['rules']['min_players']=bad
            with self.assertRaises(ValueError):sp.validate(x)
        x=copy.deepcopy(d);x['rules'].pop('min_players');x['rules'].pop('objectives',None);x['rules'].update(mode='imperial-progress',progress=ip.defaults());sp.validate(x)
        self.assertEqual(sp.min_players(x),2)
        x['rules']['progress']['amount_max']=99
        with self.assertRaises(ValueError):sp.validate(x)

if __name__=='__main__':unittest.main()
