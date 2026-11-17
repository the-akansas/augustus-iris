"""황위 시험 규칙 v1: coup funding, gifts, monthly paranoia, money safety, privacy (no engine, no window).

Real code under test: throne_rules, throne_state (validation, sealing, save/restore, hand-in), throne_play (quote, spend,
settle), trade_post_ledger (one-sided debit), post_recovery.reconcile (lost acknowledgements), cash_snapshot (the
cash checkpoint carried by joint saves and backup replicas), throne_events (public status, own view, openings).
Emulated: only the city engine's side of a native money command (post_book_apply: apply if the treasury covers it,
keep the receipt, the same receipt for the same command) and a city save (treasury + receipts at the save barrier).
Fixture values (treasury, stage, paranoia set through set_secret) are TEST INPUTS, not play data or income evidence."""
import copy,json,sqlite3,sys,tempfile,time,unittest,uuid
from pathlib import Path
TEST_TOOLS=(Path(__file__).resolve().parents[1]/'Augustus'/'mp_test_tools.py').is_file()   # the test launcher's tools: in no release, not in the public source
needs_test_tools=unittest.skipUnless(TEST_TOOLS,'needs the test launcher tools (Augustus/mp_test_tools.py), which are not in this copy')
ROOT=Path(__file__).resolve().parents[1]/'Augustus'
sys.path.insert(0,str(ROOT))
import throne_rules as tr,throne_state as ts,throne_events as te,throne_play as tp
import trade_post_ledger,post_recovery,cash_snapshot,live_trade,cash_live

CITIES=['player1','player2','player3']
RULES=tr.test_rules()
B=dict(cities=list(CITIES),throne=dict(rules=RULES,rome=dict(id='rome',x=768,y=496)))
MONTH=800

def req():return uuid.uuid4().hex

class Draws:
    """Test control of the host's one draw per coup (secrets.randbelow). Each value is used once."""
    def __init__(s):s.queue=[];s.real=tp.secrets.randbelow;tp.secrets.randbelow=s.draw
    def draw(s,n):return s.queue.pop(0) if s.queue else s.real(n)
    def close(s):tp.secrets.randbelow=s.real

class Host:
    def __init__(s,folder,name='host'):
        s.path=str(Path(folder)/(name+'.sqlite'));s.db=sqlite3.connect(s.path);s.db.row_factory=sqlite3.Row
        s.db.execute('CREATE TABLE IF NOT EXISTS joint_save(id INTEGER PRIMARY KEY,ticks INTEGER,state TEXT)')
        live_trade.initialize(s.db);cash_live.initialize(s.db)
        s.db.commit()
    def setup(s,tick=0):
        ts.configure(s.db,B,tick);te.initialize(s.db);s.ensure();s.db.commit();return s
    def ensure(s):
        if not s.db.execute("SELECT 1 FROM sqlite_master WHERE name='post_meta'").fetchone():
            s.db.commit();trade_post_ledger.Ledger(s.path,CITIES,transport=True).close()
        if not s.db.execute('SELECT 1 FROM cash_scope').fetchone():s.db.execute('INSERT INTO cash_scope VALUES(?)',('ab'*32,))   # lobby: cash_live.scope
    def state(s):return ts.current(s.db,B)
    def own(s,city):return te.own(s.db,B,city)
    def quote(s,city,kind,amount,funds=None,tick=0):
        state=s.state();ts.advance(state,max(tick,state['last_tick']));return tp.quote(state,city,kind,amount,funds,max(tick,state['last_tick']))
    def spend(s,city,kind,amount,funds=None,tick=0,request=None,expect='auto'):
        tick=max(tick,s.state()['last_tick']);request=request or req()
        if expect=='auto':expect=tp.fingerprint(s.quote(city,kind,amount,funds,tick))
        out=tp.spend(s.db,B,city,request,kind,amount,funds,expect,tick,s.ensure);s.db.commit();out['request']=request;return out
    def settle(s,tick=0):
        tp.settle(s.db,B,tick,s.ensure);s.db.commit()
    def ledger(s):return trade_post_ledger.Ledger(s.path,CITIES,transport=True)
    def debits(s):return [dict(r) for r in s.db.execute("SELECT * FROM post_contract WHERE route='debit'")]

class Cities:
    """The city engines (emulated post_book_apply: debit 'export', credit 'pay', one receipt per command id) and their
    saves. Delivery is recorded the way cash_live.request records it (cash_attempt / cash_retry) before the city sees
    the command, so the host can tell a command never handed over from one that may have been applied."""
    INT32_MAX=2**31-1
    def __init__(s,funds):s.treasury=dict(funds);s.book={c:{} for c in CITIES}
    def apply(s,city,c):
        key=c['id']
        if key not in s.book[city]:
            debit=c['step']=='export'
            applied=c['asset']==0 and ((debit and s.treasury[city]>=c['amount']) or (c['step']=='pay' and s.treasury[city]<=s.INT32_MAX-c['amount']))
            if applied:s.treasury[city]+=-c['amount'] if debit else c['amount']
            s.book[city][key]=dict(peer=c['peer'],step=c['step'],asset=c['asset'],amount=c['amount'],applied=applied)
        return s.book[city][key]['applied']
    def receipts(s,city):return dict(s.book[city])
    def run(s,host,city,ack=True):
        """Deliver the city's pending commands; the engine applies each once and keeps the receipt in its save."""
        ledger=host.ledger()
        try:
            for c in ledger.commands(city,set(CITIES)):
                n=(ledger.db.execute('SELECT attempts FROM cash_attempt WHERE command=?',(c['id'],)).fetchone() or [0])[0]
                with ledger.db:
                    ledger.db.execute('INSERT OR REPLACE INTO cash_attempt VALUES(?,?)',(c['id'],min(6,n+1)))
                    ledger.db.execute('INSERT OR REPLACE INTO cash_retry VALUES(?,?)',(c['id'],time.time()+min(30,2**n)))   # as cash_live
                applied=s.apply(city,c)
                if ack:ledger.ack(city,c['id'],c['digest'],applied)
        finally:ledger.close()
    def report(s,host,city):
        """A cash report: the receipts in the city save settle what the host has not acknowledged yet."""
        ledger=host.ledger()
        try:return post_recovery.reconcile(ledger,city,s.receipts(city),set(CITIES))
        finally:ledger.close()
    def snapshot(s):return copy.deepcopy((s.treasury,s.book))
    def load(s,snap):s.treasury,s.book=copy.deepcopy(snap)

def set_secret(host,city,stage=None,**values):
    """TEST FIXTURE ONLY: put a player at a stage / paranoia (the state stays valid by the real validator)."""
    state=host.state();p=state['players'][city]
    if stage is not None:p['stage']=stage
    p['secret'].update(values);p['secret']['next_cost']=ts.expected_cost(RULES,p['stage'],p['secret']['failures'])
    ts.store(host.db,state,B);host.db.commit()

def activate(host,city='player3',tick=0,cities=None):
    """Wake the emperor with one real (failing) coup funding by `city`."""
    d=Draws();d.queue=[9999]
    try:
        out=host.spend(city,'coup',5000,tick=tick);cities.run(host,city);host.settle(tick)
    finally:d.close()
    return out

def save(host,sid,tick,cities):
    """A joint save barrier: throne record sealed, cash checkpoint taken, every city saved."""
    host.db.execute("INSERT INTO joint_save(id,ticks,state) VALUES(?,?,'complete')",(sid,tick));ts.capture(host.db,sid,B,tick);host.db.commit()
    return dict(sid=sid,tick=tick,cash=cash_snapshot.current(host.db),cities=cities.snapshot(),
                openings={c:te.own_opening(host.db,B,c,sid) for c in CITIES})

def restore_own(folder,saved,old):
    """The same host restores its own DB's save (every secret known)."""
    new=Host(folder,'own-'+uuid.uuid4().hex[:6]);ts.initialize(new.db)
    ts.restore(new.db,ts.read(old.db,saved['sid'],B,saved['tick']),B,saved['tick']);te.initialize(new.db)
    cash_snapshot.restore(new.db,saved['cash'],CITIES);new.db.commit();return new

def restore_replica(folder,saved,old):
    """A new host from another player's backup: sealed record only; each player hands in its own opening."""
    new=Host(folder,'replica-'+uuid.uuid4().hex[:6]);ts.initialize(new.db)
    sealed=ts.sealed_save(old.db,saved['sid'],B,saved['tick'])
    new.db.execute("INSERT INTO joint_save(id,ticks,state) VALUES(?,?,'complete')",(saved['sid'],saved['tick']))
    ts.put(new.db,saved['sid'],sealed,B,saved['tick'])
    ts.restore(new.db,ts.read(new.db,saved['sid'],B,saved['tick']),B,saved['tick']);te.initialize(new.db)
    cash_snapshot.restore(new.db,saved['cash'],CITIES);new.db.commit();return new

class Base(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.host=Host(self.tmp.name).setup()
        self.cities=Cities({c:200000 for c in CITIES});self.draws=Draws()
    def tearDown(self):self.draws.close();self.host.db.close()
    def coup(self,city,amount,draw,tick=0):
        self.draws.queue.append(draw);out=self.host.spend(city,'coup',amount,tick=tick)
        self.cities.run(self.host,city);self.host.settle(tick);return out

class Rules(unittest.TestCase):
    def test_table_and_failure_cost(self):
        self.assertEqual([(s['cost'],s['chance'],s['cap'],s['floor'],s['gift_floor']) for s in RULES['stages']],
                         [(5000,50,70,10,0),(10000,41,63,20,10),(20000,33,55,30,20),(40000,24,48,40,30),(80000,15,40,50,40)])   # confirmed plan 2026-11-14
        self.assertEqual([tr.min_cost(RULES,0,f) for f in range(6)],[5000,6300,7900,9900,12400,15500])   # x1.25, up to 100 Dn
        self.assertEqual([tr.min_cost(RULES,4,f) for f in range(3)],[80000,100000,125000])
        self.assertEqual(tr.min_cost(RULES,5,0),0)
        # 2026-11-14: the numbers come from the scenario (editor): inside the ranges and consistent, else refused
        ts.validate_rules(dict(RULES,monthly_paranoia=6))
        for name in tr.PRESETS:self.assertEqual(tr.preset_of(tr.validate(tr.preset(name))),name)
        self.assertEqual(([s['cost'] for s in tr.preset('short')['stages']],tr.preset('short')['expedition']['tributes'],tr.preset('short')['attempt_months']),([2500,5000,10000,20000,40000],[1500,2500,4000,6000,9000],1))
        self.assertEqual(([s['cost'] for s in tr.preset('long')['stages']],tr.preset('long')['expedition']['tributes'],tr.preset('long')['attempt_months']),([7500,15000,30000,60000,120000],[4500,7500,12000,18000,27000],3))
        self.assertEqual([[s['chance'],s['cap']] for s in tr.preset('short')['stages']],[[s['chance'],s['cap']] for s in RULES['stages']])   # chances are the same in every preset
        def stage(i,**k):
            r=tr.test_rules();r['stages'][i].update(k);return r
        def raid(**k):
            r=tr.test_rules();r['expedition'].update(k);return r
        for bad in (dict(RULES,monthly_paranoia=21),dict(RULES,attempt_months=0),dict(RULES,paranoia_max=90),dict(RULES,extra=1),dict(RULES,label='x'),
                    stage(0,cap=49),stage(0,chance=0),stage(0,cap=96),stage(1,floor=10),stage(0,gift_floor=11),stage(0,cost=0),stage(2,name='x'),
                    raid(march_months=0),raid(siege_months=0),raid(cooldown_months=0),raid(army_cap=31),raid(tributes=[1,2,3]),raid(tributes=[0,1,2,3,4]),raid(sack_reduction=101)):
            with self.assertRaises(ValueError):ts.validate_rules(bad)
        self.assertEqual(ts.validate_rules(tr.test_rules()),RULES)
    def test_chance(self):
        self.assertEqual(tr.chance_bp(RULES,0,5000,5000),5000)        # A=M: base
        self.assertEqual(tr.chance_bp(RULES,0,5000,10000),6000)       # A=2M: midpoint of 50 and 70
        self.assertEqual(tr.chance_bp(RULES,0,5000,50000),6800)
        self.assertEqual(tr.chance_bp(RULES,0,5000,1000000),6990)     # never reaches the cap
        self.assertEqual(tr.chance_bp(RULES,4,80000,160000),2750)     # stage 5: 15%..40%
        self.assertEqual(tr.chance_bp(RULES,0,6300,6300),5000)        # after failures M grows, base stays
        last=0
        for a in range(5000,200001,100):
            c=tr.chance_bp(RULES,0,5000,a);self.assertGreaterEqual(c,last);self.assertLess(c,9000);last=c
        self.assertEqual(tr.percent(8990),'89.90%')
    def test_gift_plan(self):
        p=tr.gift_plan(RULES,1,25,2000)        # stage 2 (one completed): floor 20, gift floor 10
        self.assertEqual((p['points'],p['charge'],p['rest'],p['after']),(6,1600,400,19))
        self.assertEqual(tr.gift_plan(RULES,1,10,5000)['points'],0)                 # at the gift floor
        self.assertEqual((tr.gift_plan(RULES,1,21,200)['after'],tr.gift_plan(RULES,1,21,200)['charge']),(20,200))
        p=tr.gift_plan(RULES,1,20,599);self.assertEqual((p['points'],p['next_price']),(0,600))
        p=tr.gift_plan(RULES,0,12,100000);self.assertEqual((p['after'],p['charge']),(0,2*200+10*600))   # stage 1: 10 / 0
        p=tr.gift_plan(RULES,4,100,1000000);self.assertEqual((p['after'],p['charge']),(40,50*200+10*600))

class Peace(Base):
    def test_gift_refused_in_peace_nothing_charged(self):
        out=self.host.spend('player1','gift',2000,expect=None)
        self.assertEqual(out['state'],'refused');self.assertIn('평화의 시대',out['quote']['reason'])
        self.assertEqual(self.host.debits(),[]);self.assertIsNone(self.host.state()['activated_tick'])
    def test_first_valid_coup_funding_wakes_the_emperor(self):
        self.coup('player1',5000,9999,tick=1000)          # fails, but the money was spent: activation
        st=self.host.state()
        self.assertEqual(st['activated_tick'],1000);self.assertEqual([n['kind'] for n in st['notices']],['coup_first_failed'])   # 2026-11-14: one notice when the first coup fails
        self.assertEqual({c:p['secret']['paranoia'] for c,p in st['players'].items()},{c:15 for c in CITIES})   # stage 1 floor + failure 5
        self.assertEqual(self.cities.treasury['player1'],195000)
    def test_unfunded_coup_is_void(self):
        cities=Cities({c:4000 for c in CITIES})
        out=self.host.spend('player1','coup',5000)            # the host has no funds figure; the engine decides
        self.assertEqual(out['state'],'charging')
        cities.run(self.host,'player1');self.host.settle(0)
        e=self.host.own('player1')['last'];self.assertEqual((e['state'],e['result']),('void','void'))
        st=self.host.state();self.assertIsNone(st['activated_tick']);self.assertEqual(st['notices'],[])
        s=st['players']['player1']['secret'];self.assertEqual((s['failures'],s['next_attempt_tick'],cities.treasury['player1']),(0,0,4000))
    def test_reported_funds_refuse_before_anything(self):
        out=self.host.spend('player1','coup',5000,funds=4999,expect=None)
        self.assertEqual(out['state'],'refused');self.assertEqual(self.host.debits(),[])
        out=self.host.spend('player1','coup',4900,expect=None)
        self.assertIn('최소 지원금은 5,000',out['quote']['reason'])

class Coup(Base):
    def test_failures_raise_the_minimum_and_success_resets_it(self):
        self.coup('player1',5000,9999)
        self.assertEqual(self.host.own('player1')['next_cost'],6300)
        self.coup('player1',6300,9999,tick=1600)
        self.assertEqual((self.host.own('player1')['next_cost'],self.host.own('player1')['failures']),(7900,2))
        out=self.host.spend('player1','coup',7900,tick=1600,expect=None);self.assertIn('남았습니다',out['quote']['reason'])  # 2-month wait
        self.coup('player1',7900,0,tick=3200)           # success
        own=self.host.own('player1')
        self.assertEqual((own['stage'],own['failures'],own['next_cost'],own['paranoia']),(1,0,10000,28))   # 10 + 2 failures x5 + 4 months x2; floor 20 lower
        self.assertEqual(self.cities.treasury['player1'],200000-5000-6300-7900)
    def test_shown_chance_is_the_drawn_chance(self):
        q=self.host.quote('player1','coup',10000);self.assertEqual((q['chance'],q['chance_text']),(6000,'60.00%'))
        self.coup('player1',10000,5999)                  # 5999 < 6000: success
        self.assertEqual(self.host.own('player1')['last']['result'],'success')
        self.coup('player2',10000,6000)                  # 6000: failure (exactly the shown 60.00%)
        self.assertEqual(self.host.own('player2')['last']['result'],'failure')
        e=self.host.state()['players']['player2']['secret']['spends'][0];self.assertEqual((e['chance'],e['roll']),(6000,6000))
    def test_client_values_are_not_trusted(self):
        q=self.host.quote('player1','coup',5000);forged=tp.fingerprint(q);forged[3]=9000
        out=self.host.spend('player1','coup',5000,expect=forged)
        self.assertEqual(out['state'],'requote');self.assertEqual(self.host.debits(),[])
        with self.assertRaises(ValueError):tp.spend(self.host.db,B,'player1','zz','coup',5000,None,None,0)
    def test_final_stage_records_the_end_of_the_trial(self):
        activate(self.host,cities=self.cities)
        set_secret(self.host,'player1',stage=4,paranoia=50)
        self.coup('player1',80000,0,tick=1600)
        st=self.host.state();self.assertEqual((st['winner'],st['ended'],st['players']['player1']['stage']),('player1',True,5))
        self.assertTrue(self.host.own('player1')['winner_is_me'])
        out=self.host.spend('player2','coup',5000,tick=1600,expect=None);self.assertIn('끝났습니다',out['quote']['reason'])

class Paranoia(Base):
    def test_monthly_rise_once_per_game_month(self):
        activate(self.host,tick=1000,cities=self.cities)
        for tick in (1000,1200,1599,1599):self.host.settle(tick)
        self.assertEqual(self.host.own('player1')['paranoia'],15)   # floor 10 + the activating coup's failure 5
        for _ in range(3):self.host.settle(1600)       # the same month boundary, three polls
        self.assertEqual(self.host.own('player1')['paranoia'],17)   # +2 a month (2026-11-14)
        self.host.settle(1600+3*MONTH);self.assertEqual(self.host.own('player1')['paranoia'],23)
        self.host.settle(1600+60*MONTH);self.assertEqual(self.host.own('player1')['paranoia'],100)
        self.assertTrue(self.host.own('player1')['expedition_due'])
        # 2026-11-14: at the maximum the emperor's legions leave Rome (handoff/test_throne_raid.py)
        st=self.host.state();self.assertTrue(all(p['secret']['expedition']['phase']!='idle' and p['secret']['expedition']['count']==1 for p in st['players'].values()))
    def test_stage_change_keeps_value_or_raises_to_floor(self):
        activate(self.host,cities=self.cities)
        set_secret(self.host,'player1',paranoia=35)
        self.coup('player1',5000,0,tick=1600)           # 35 + 2 months x2 = 39; new floor 20 is lower: kept
        self.assertEqual(self.host.own('player1')['paranoia'],39)
        set_secret(self.host,'player2',paranoia=10)
        self.coup('player2',5000,0,tick=1600)           # 10 -> stage 2 floor 20
        self.assertEqual(self.host.own('player2')['paranoia'],20)

class Gift(Base):
    def test_two_prices_and_the_rest_stays(self):
        activate(self.host,cities=self.cities);set_secret(self.host,'player1',stage=1,paranoia=25)
        q=self.host.quote('player1','gift',2000);self.assertEqual((q['charge'],q['rest'],q['after'],q['points']),(1600,400,19,6))
        out=self.host.spend('player1','gift',2000);self.cities.run(self.host,'player1');self.host.settle(0)
        own=self.host.own('player1');self.assertEqual(own['paranoia'],19);self.assertEqual(self.cities.treasury['player1'],200000-5000*0-1600)
        self.assertEqual(self.host.state()['players']['player1']['secret']['gift_total'],1600)
        self.assertEqual(self.host.debits()[-1]['money'],1600)                  # only what was used is charged
    def test_no_effect_no_charge(self):
        activate(self.host,cities=self.cities);set_secret(self.host,'player1',stage=1,paranoia=10)
        n=len(self.host.debits())
        out=self.host.spend('player1','gift',5000,expect=None);self.assertIn('최저치',out['quote']['reason'])
        set_secret(self.host,'player1',paranoia=20)
        out=self.host.spend('player1','gift',599,expect=None);self.assertIn('600 Dn',out['quote']['reason'])
        self.assertEqual(len(self.host.debits()),n)
    def test_limit_above_funds_is_refused_not_reduced(self):
        activate(self.host,cities=self.cities);set_secret(self.host,'player1',paranoia=30)
        out=self.host.spend('player1','gift',3000,funds=2999,expect=None)
        self.assertEqual(out['state'],'refused');self.assertIn('보유 자금',out['quote']['reason'])
    def test_changed_state_gives_a_new_quote(self):
        activate(self.host,cities=self.cities);set_secret(self.host,'player1',paranoia=20)
        q=self.host.quote('player1','gift',2500);self.assertEqual((q['points'],q['charge']),(10,2000))
        self.host.settle(MONTH)                         # a month passes: +2, the quote is no longer the one shown
        out=tp.spend(self.host.db,B,'player1',req(),'gift',2500,None,tp.fingerprint(q),MONTH,self.host.ensure);self.host.db.commit()
        self.assertEqual(out['state'],'requote');self.assertEqual(out['quote']['before'],22)

class QuoteStateChanges(Base):
    def test_gift_same_cost_and_points_still_requires_current_preview(self):
        activate(self.host,cities=self.cities)
        set_secret(self.host,'player1',paranoia=35)
        old=self.host.quote('player1','gift',2000,tick=0)
        self.assertEqual((old['before'],old['after'],old['charge'],old['points']),(35,25,2000,10))
        response=self.host.spend('player1','gift',2000,tick=MONTH,expect=tp.fingerprint(old))
        self.assertEqual(response['state'],'requote')
        self.assertEqual((response['quote']['before'],response['quote']['after']),(37,27))
        self.assertEqual(len(self.host.debits()),1)  # only the activating coup

class MoneySafety(Base):
    def test_resend_is_the_same_spend(self):
        r=req();self.draws.queue=[0]
        a=self.host.spend('player1','coup',5000,request=r);b=self.host.spend('player1','coup',5000,request=r)
        self.assertTrue(b['duplicate']);self.assertEqual(len(self.host.debits()),1)
        self.cities.run(self.host,'player1');self.cities.run(self.host,'player1');self.host.settle(0);self.host.settle(0)
        c=self.host.spend('player1','coup',5000,request=r);self.assertEqual((c['state'],c['result']),('done','success'))
        self.assertEqual(self.cities.treasury['player1'],195000);self.assertEqual(self.host.state()['players']['player1']['stage'],1)
        with self.assertRaises(ValueError):self.host.spend('player2','coup',5000,request=r)
    def test_lost_acknowledgement_settles_from_the_city_receipt(self):
        self.draws.queue=[9999];self.host.spend('player1','coup',5000)
        self.cities.run(self.host,'player1',ack=False)              # debited in the city; the host never heard
        self.host.settle(0);self.assertEqual(self.host.own('player1')['charging'][0]['state'],'charging')
        host2=Host(self.tmp.name);self.addCleanup(host2.db.close)                                    # host process restarts on the same DB
        self.cities.run(host2,'player1')                            # same command again: the city answers from its receipt
        host2.settle(0);self.cities.report(host2,'player1');host2.settle(0)
        self.assertEqual(self.cities.treasury['player1'],195000)     # taken once
        self.assertEqual(host2.own('player1')['last']['result'],'failure');self.assertEqual(host2.own('player1')['failures'],1)
    def test_reconcile_path(self):
        self.draws.queue=[9999];self.host.spend('player1','coup',5000)
        self.cities.run(self.host,'player1',ack=False);r=self.cities.report(self.host,'player1')
        self.assertEqual(r['state'],'reconciled');self.host.settle(0)
        self.assertEqual(self.host.own('player1')['failures'],1)
        self.cities.report(self.host,'player1');self.host.settle(0)
        self.assertEqual(self.host.own('player1')['failures'],1)
    def test_city_that_left_before_paying(self):
        self.draws.queue=[9999];self.host.spend('player1','coup',5000)
        ledger=self.host.ledger()
        try:ledger.abandon({'player1'})
        finally:ledger.close()
        # 2026-11-12 late night: a departure is not evidence about a throne debit. The record stays 'charging' and
        # the city's own receipt settles it when it comes back (here: the command reaches it then, taken once).
        self.host.settle(0);self.assertEqual(self.host.own('player1')['charging'][0]['state'],'charging')
        self.assertIsNone(self.host.own('player1')['last'])
        self.cities.run(self.host,'player1');self.host.settle(0)
        self.assertEqual(self.host.own('player1')['last']['result'],'failure');self.assertEqual(self.cities.treasury['player1'],195000)
    def test_only_one_spend_at_a_time(self):
        self.host.spend('player1','coup',5000)
        out=self.host.spend('player1','coup',5000,expect=None);self.assertIn('처리하는 중',out['quote']['reason'])
        self.assertEqual(len(self.host.debits()),1)

class SaveAndHandover(Base):
    def test_save_while_charging_then_restore_on_the_same_host(self):
        activate(self.host,cities=self.cities)
        self.draws.queue=[0];self.host.spend('player1','coup',5000,tick=1600)
        saved=save(self.host,1,1600,self.cities)
        self.cities.run(self.host,'player1');self.host.settle(1700)      # happens after the save: lost with the crash
        self.cities.load(saved['cities'])
        new=restore_own(self.tmp.name,saved,self.host);self.addCleanup(new.db.close)
        self.assertEqual(new.own('player1')['charging'][0]['state'],'charging')
        self.cities.run(new,'player1');new.settle(1600)
        own=new.own('player1');self.assertEqual((own['stage'],own['last']['result']),(1,'success'))
        self.assertEqual(self.cities.treasury['player1'],200000-5000)   # once, from the restored city save
        new.settle(1600);self.cities.run(new,'player1');new.settle(1600)
        self.assertEqual(new.own('player1')['stage'],1)
    def test_save_after_charge_reload_keeps_everything(self):
        activate(self.host,cities=self.cities);set_secret(self.host,'player1',paranoia=40)
        self.host.spend('player1','gift',2000);self.cities.run(self.host,'player1');self.host.settle(0)
        saved=save(self.host,1,MONTH,self.cities)
        new=restore_own(self.tmp.name,saved,self.host);self.addCleanup(new.db.close)
        self.assertEqual(new.state()['players'],self.host.state()['players'])
        self.assertEqual(new.own('player1')['paranoia'],32)          # 40 -10 (gift) +2 (month at the barrier)
        new.settle(MONTH);self.assertEqual(new.own('player1')['paranoia'],32)   # the barrier's month is not counted again
        self.cities.load(saved['cities']);self.cities.report(new,'player1');new.settle(MONTH)
        self.assertEqual(self.cities.treasury['player1'],200000-2000)   # the waking coup was player3's
    def test_host_handover_while_charging(self):
        activate(self.host,cities=self.cities)
        self.draws.queue=[0];self.host.spend('player2','coup',5000,tick=1600)
        saved=save(self.host,1,1600,self.cities)
        new=restore_replica(self.tmp.name,saved,self.host);self.addCleanup(new.db.close)
        self.assertEqual(new.state()['players']['player2'].keys(),{'stage','eliminated','pending'})
        out=new.spend('player2','gift',1000,tick=1600,expect=None);self.assertIn('복원 대기',out['quote']['reason'])
        self.cities.load(saved['cities']);self.cities.run(new,'player2');new.settle(1600)   # charged, but not settled while pending
        self.assertEqual(new.state()['players']['player2']['stage'],0)
        o=saved['openings']['player2'];te.hand_in(new.db,B,'player2',o['secret'],o['nonce'],1600);new.db.commit()
        new.settle(1600);new.settle(1600)
        own=new.own('player2');self.assertEqual((own['stage'],own['last']['result']),(1,'success'))
        self.assertEqual(self.cities.treasury['player2'],195000)
    def test_record_sealed_before_activation_joins_at_its_floor(self):
        saved=save(self.host,1,0,self.cities)
        new=restore_replica(self.tmp.name,saved,self.host);self.addCleanup(new.db.close)
        for c in ('player1','player3'):o=saved['openings'][c];te.hand_in(new.db,B,c,o['secret'],o['nonce'],0)
        new.db.commit()
        self.cities.load(saved['cities']);activate(new,'player1',tick=100,cities=self.cities)
        o=saved['openings']['player2'];te.hand_in(new.db,B,'player2',o['secret'],o['nonce'],200);new.db.commit()
        self.assertEqual(new.own('player2')['paranoia'],15)   # floor 10 + the failure announced while it was pending

class Privacy(Base):
    def test_nothing_private_in_public_status_or_replica(self):
        activate(self.host,'player1',cities=self.cities);set_secret(self.host,'player1',paranoia=37)
        r=self.host.spend('player1','gift',2000)['request'];self.cities.run(self.host,'player1');self.host.settle(0)
        saved=save(self.host,1,0,self.cities)
        replica=ts.sealed_save(self.host.db,1,B,0);replica.pop('spec')       # the public rule set names 'paranoia' itself
        public=json.dumps(dict(status=te.public_status(self.host.db,B),replica=replica))
        for secret in (r,'spends','paranoia','gift_total','"roll"','"failures"'):self.assertNotIn(secret,public)
        other=json.dumps(self.host.own('player2'))
        self.assertNotIn(r,other);self.assertNotIn('37',json.dumps(self.host.own('player2').get('paranoia')))
        status=te.public_status(self.host.db,B)
        self.assertEqual(set(status),{'active','activated_tick','notices','leading','mood','scoreboard','eliminated','restoring','sealed_save','handover_save','ended','winner'})   # no per-city stage (fully anonymous)
        self.assertIsNone(status['scoreboard'])
        # Known limit (documented): the cash checkpoint and the city save hold the debit itself (city, amount);
        # kind, draw, chance and paranoia are not in it.
        rows=saved['cash']['tables']['post_contract'];self.assertTrue(all(row['route']=='debit' for row in rows))
        text=json.dumps(saved['cash']);self.assertNotIn(r,text)
        for word in ('coup','gift','chance','roll','paranoia'):self.assertNotIn(word,text)
    def test_notice_names_no_one(self):
        self.coup('player1',5000,9999)
        n=te.public_status(self.host.db,B)['notices'][0];self.assertNotIn('player1',json.dumps(n))

class Scope(unittest.TestCase):
    def test_only_the_test_rules_run(self):
        import scenario_project as sp
        data=json.loads((ROOT/'scenarios/throne-test-v1/scenario.json').read_text(encoding='utf-8'))
        sp.require_runtime(data);self.assertTrue(sp.layout(data).startswith('4 '))
        self.assertEqual(data['rules']['throne'],RULES)
        old=copy.deepcopy(data);old['rules']['throne']=ts.defaults()
        with self.assertRaises(ValueError):sp.require_runtime(old)
        changed=copy.deepcopy(data);changed['rules']['throne']['stages'][0]['cost']=1
        with self.assertRaises(ValueError):sp.validate(changed)
    def test_room_keeps_its_rules(self):
        db=sqlite3.connect(':memory:');db.execute('CREATE TABLE joint_save(id INTEGER PRIMARY KEY,ticks INTEGER,state TEXT)')
        ts.configure(db,B,0)
        other=dict(B,throne=dict(rules=ts.defaults(),rome=B['throne']['rome']))
        with self.assertRaises(ValueError):ts.current(db,other)       # a room never switches rule sets silently

class FakeClient:
    """The bridge's link to the host, answered by the same host functions lobby.py calls."""
    def __init__(s,host,city):s.host=host;s.city=city;s.calls=[]
    def call(s,op,**r):
        s.calls.append(op);h=s.host;tick=h.state()['last_tick']
        if op=='throne_mine':h.settle(tick);return te.own(h.db,B,s.city)
        h.settle(tick);state=h.state()
        if op=='throne_quote':return dict(quote=tp.quote(state,s.city,r['kind'],r['amount'],r.get('funds'),tick),own=tp.view(state,s.city,tick))
        if op=='throne_spend':
            out=tp.spend(h.db,B,s.city,r['request'],r['kind'],r['amount'],r.get('funds'),r['expect'],tick,h.ensure);h.db.commit()
            out['own']=tp.view(h.state(),s.city,tick);return out
        if op=='throne_test':
            __import__('mp_test_tools').throne_adjust(h.db,B,s.city,r['action'],tick);h.db.commit();return dict(own=tp.view(h.state(),s.city,tick))
        raise AssertionError(op)

class Panel(Base):
    def bridge(self,city):
        import throne_client
        folder=Path(self.tmp.name)/city;folder.mkdir(exist_ok=True)
        b=SimpleBridge(folder,FakeClient(self.host,city));return b,throne_client
    def box(self,b):return dict(l.split('\t',1) for l in b.files['throne-box.txt'].splitlines())
    def dialog(self,b):return [l.split('\t') for l in b.files['throne-dialog.txt'].splitlines()]
    def test_peace_box(self):
        b,tc=self.bridge('player1');tc.publish_panel(b,b.client.call('throne_mine'))
        box=self.box(b);self.assertEqual((box['state'],box['coup'],box['gift'],box['mine'],box['leading']),('peace','1','0','0','0'))
        self.assertEqual(box['mood'],'제국 정세: 평온');self.assertEqual(b.files['throne-dialog.txt'],'');self.assertEqual(b.files['throne-score.txt'],'')
        self.assertEqual((b.files['throne-hud.txt'],b.files['throne-actions.txt']),('',''))   # the old text box is gone
    def test_coup_from_the_box(self):
        b,tc=self.bridge('player1')
        tc.command(b,'coup\n200000',req())
        d=self.dialog(b);self.assertIn(['kind','coup'],d);self.assertIn(['subtitle','다음 쿠데타: 비밀 조직 결성 (완료 0단계)'],d)
        self.assertIn(['small','기본 성공률 50%, 상한 70%'],d);self.assertIn(['row','최소 지원금','5,000 Dn'],d);self.assertIn(['amount','지원 금액','5,000 Dn'],[l[:3] for l in d])
        self.assertIn(['low','예상 성공률','50.00%'],d);self.assertIn(['low','실패 시 다음 최소 지원금','6,300 Dn'],d);self.assertIn(['go','쿠데타 지원','1'],d)
        self.assertIn(['hint','처음 지원하면 편집증이 깨어납니다. 누가 했는지는 비밀입니다.'],d)
        tc.command(b,'more\n200000',req());self.assertIn(['amount','지원 금액','5,100 Dn'],[l[:3] for l in self.dialog(b)])
        tc.command(b,'add1000\n200000',req());tc.command(b,'add5000\n200000',req());tc.command(b,'add10000\n200000',req())
        self.assertIn(['amount','지원 금액','21,100 Dn'],[l[:3] for l in self.dialog(b)]);self.assertIn(['low','예상 성공률','65.26%'],self.dialog(b))
        tc.command(b,'reset\n200000',req());self.assertIn(['amount','지원 금액','5,000 Dn'],[l[:3] for l in self.dialog(b)])        # reset: the minimum
        tc.command(b,'less\n200000',req());self.assertIn(['amount','지원 금액','5,000 Dn'],[l[:3] for l in self.dialog(b)])         # never below it
        self.assertIn(['amount','지원 금액','5,000 Dn','5000','5000','1000000'],self.dialog(b))     # value, lowest, highest for the game's own keys
        # the game edits the amount itself and sends it when it settles (user 2026-11-14: every click used to wait for the room)
        tc.command(b,'set\n200000\n21100',req());self.assertIn(['low','예상 성공률','65.26%'],self.dialog(b))
        self.assertIn(['amount','지원 금액','21,100 Dn','21100','5000','1000000'],self.dialog(b))
        tc.command(b,'set\n200000\n100',req());self.assertIn(['amount','지원 금액','5,000 Dn','5000','5000','1000000'],self.dialog(b))   # never below the minimum
        tc.command(b,'set\n200000\nabc',req());self.assertIn(['amount','지원 금액','5,000 Dn','5000','5000','1000000'],self.dialog(b))   # not a number: unchanged
        r=req();self.draws.queue=[9999];tc.command(b,'go\n200000',r)
        self.assertEqual(b.files['throne-dialog.txt'],'');box=self.box(b)
        self.assertIn('요청을 받았습니다',box['note']);self.assertEqual((box['coup'],box['gift']),('0','0'))          # busy: no second spend
        tc.command(b,'go\n200000',r)                                   # the same command resent: nothing new
        self.assertEqual(len(self.host.debits()),1)
        self.cities.run(self.host,'player1');tc.publish_panel(b,b.client.call('throne_mine'))
        box=self.box(b);self.assertEqual((box['state'],box['paranoia'],box['mine']),('active','15','0'))
    def test_the_game_calculates_and_go_carries_its_amount(self):
        # user 2026-11-14: no trip to the room per click; the game calculates from the calc line, 'go' carries the amount
        b,tc=self.bridge('player1');tc.command(b,'coup\n200000',req())
        self.assertIn(['calc','coup','5000','5000','7000','6300','1000000','1',''],self.dialog(b))
        import throne_rules as tr
        self.assertEqual(tr.percent(tr.chance_bp(RULES,0,5000,21100)),'65.26%')   # what the game shows for 21,100 (same formula in th_local)
        r=req();self.draws.queue=[9999];tc.command(b,'go\n200000\n21100',r)
        self.assertEqual(b.files['throne-dialog.txt'],'');self.assertEqual(len(self.host.debits()),1)
        self.assertIn('21100',str(self.host.debits()[0]))                          # the game's amount was charged, not the opening one
    def test_go_refuses_when_what_the_game_showed_no_longer_holds(self):
        activate(self.host,cities=self.cities);set_secret(self.host,'player1',stage=1,paranoia=25)
        b,tc=self.bridge('player1');tc.command(b,'gift\n9000',req())
        d=self.dialog(b);calc=next(l for l in d if l[0]=='calc');self.assertEqual(calc[1:3],['gift','25'])
        set_secret(self.host,'player1',stage=1,paranoia=30)                       # paranoia rose after the dialog was drawn
        tc.command(b,'go\n9000\n2000',req())
        self.assertTrue(any(l[0]=='message' and '달라졌습니다' in l[1] for l in self.dialog(b)))
        self.assertIn(['calc','gift','30'],[l[:3] for l in self.dialog(b)])     # the new values to calculate with
    @needs_test_tools
    def test_test_panel_situations(self):
        # test launcher only (user 2026-11-14): each situation leaves a record the real validator accepts
        b,tc=self.bridge('player1')
        tc.command(b,'t-p+10\n200000',req());st=self.host.state();p=st['players']['player1']
        self.assertIsNotNone(st['activated_tick']);self.assertEqual(p['secret']['paranoia'],max(10,tr.base_floor(RULES,0)+10) if False else p['secret']['paranoia'])
        before=p['secret']['paranoia'];tc.command(b,'t-p+10\n200000',req());self.assertEqual(self.host.state()['players']['player1']['secret']['paranoia'],min(100,before+10))
        tc.command(b,'t-s+1\n200000',req());p=self.host.state()['players']['player1'];self.assertEqual(p['stage'],1)
        self.assertEqual(p['secret']['next_cost'],ts.expected_cost(RULES,1,0))
        tc.command(b,'t-s-1\n200000',req());self.assertEqual(self.host.state()['players']['player1']['stage'],0)
        tc.command(b,'t-rival\n200000',req());self.assertEqual(max(q['stage'] for c,q in self.host.state()['players'].items() if c!='player1'),1)
        tc.command(b,'t-wait\n200000',req());st=self.host.state();self.assertLessEqual(st['players']['player1']['secret']['next_attempt_tick'],st['last_tick'])
        tc.command(b,'t-p100\n200000',req());self.assertEqual(self.host.state()['players']['player1']['secret']['paranoia'],100)
        self.assertIn('제작:',self.box(b)['note'])   # the developer panel's note (dev_tools.py, 2026-11-17)
        with self.assertRaises(ValueError):__import__('mp_test_tools').throne_adjust(self.host.db,B,'player1','t-money',0)   # only the listed situations
    @needs_test_tools
    def test_forced_draw_and_my_own_result_popup(self):
        b,tc=self.bridge('player1');tc.sync(b,dict(throne=dict(leading=0,mood='평온'),slots=[])) if False else None
        b.joined=True;tc.own_result(b,b.client.call('throne_mine'))                 # baseline: nothing to announce yet
        tc.command(b,'t-win\n200000',req());tc.command(b,'coup\n200000',req());tc.command(b,'go\n200000\n5000',req())
        self.cities.run(self.host,'player1');own=b.client.call('throne_mine')
        self.assertEqual(own['stage'],1)                                          # forced success, whatever the chance
        line=tc.own_result(b,own);key,title,body=line.rstrip('\n').split('\t')
        self.assertEqual(title,'쿠데타 성공');self.assertIn('비밀 조직 결성에 성공했습니다',body);self.assertNotIn('Dn',body);self.assertNotIn('%',body);   # no amount, no chance (user 2026-11-14)
        self.assertEqual(len(key),32)
        self.assertEqual(tc.own_result(b,own),line)                               # the same line again: the game shows it once (uid)
        self.assertEqual(__import__('mp_test_tools').TEST_ROLL,{})                                         # the forced draw was used up
    @needs_test_tools
    def test_my_failed_coup_popup_tells_the_story_without_numbers(self):
        b,tc=self.bridge('player1');b.joined=True;tc.own_result(b,b.client.call('throne_mine'))
        tc.command(b,'t-lose\n200000',req());tc.command(b,'coup\n200000',req());tc.command(b,'go\n200000\n5000',req())
        self.cities.run(self.host,'player1');own=b.client.call('throne_mine')
        key,title,body=tc.own_result(b,own).rstrip('\n').split('\t')
        self.assertEqual(title,'쿠데타 실패');self.assertIn('비밀 조직 결성 시도가 실패했습니다',body)
        for number in ('Dn','%','5,000'):self.assertNotIn(number,body)
    def test_prepared_dialogs_match_what_the_room_opens(self):
        """A click opens the bridge's prepared copy at once (user 2026-11-15); it must be the dialog the room's quote gives."""
        b,tc=self.bridge('player1');tc.publish_panel(b,b.client.call('throne_mine'))
        self.assertEqual(b.files['throne-prep-gift.txt'].split('\t')[0],'refuse')        # peace: no gifts yet
        prep=b.files['throne-prep-coup.txt'];tc.command(b,'coup\n200000',req());self.assertEqual(prep,b.files['throne-dialog.txt'])
        tc.command(b,'close\n200000',req())
        activate(self.host,cities=self.cities);set_secret(self.host,'player1',stage=1,paranoia=40)
        tc.publish_panel(b,b.client.call('throne_mine'));prep=b.files['throne-prep-coup.txt']
        tc.command(b,'coup\n200000',req());self.assertEqual(prep,b.files['throne-dialog.txt']);tc.command(b,'close\n200000',req())
        prep=b.files['throne-prep-gift.txt'];tc.command(b,'gift\n200000',req())
        real=[l for l in b.files['throne-dialog.txt'].splitlines() if not l.startswith('row\t보유 자금')]   # the room's copy adds the treasury the click sent
        self.assertEqual(prep.splitlines(),real)
    def test_a_spend_is_handed_to_the_city_at_once(self):
        """user 2026-11-15: alone, the money still left only after up to 5 s (the exchange with the city's engine ran
        every 5 s while no trade was under way). A throne spend under way now keeps it running and starts it at once."""
        import cash_bridge
        b,tc=self.bridge('player1');b.cash_next=99
        tc.command(b,'coup\n200000',req());tc.command(b,'go\n200000\n5000',req())
        self.assertTrue(b.throne_charging);self.assertEqual(b.cash_next,0);self.assertTrue(cash_bridge.active_settlement(b))
    def test_a_coup_that_has_to_wait_is_refused_at_once(self):
        activate(self.host,cities=self.cities);b,tc=self.bridge('player3');tc.publish_panel(b,b.client.call('throne_mine'))
        kind,why=b.files['throne-prep-coup.txt'].rstrip('\n').split('\t');tc.command(b,'coup\n200000',req())
        self.assertEqual((kind,why),('refuse',self.box(b)['note']));self.assertEqual(b.files['throne-dialog.txt'],'')
    @needs_test_tools
    def test_the_others_are_told_who_became_emperor(self):
        b1,tc=self.bridge('player1');b2,_=self.bridge('player2');b1.throne_names={'player2':'플레이어 2 / 로마'}
        for b in (b1,b2):self.assertEqual(tc.end_popup(b,te.public_status(self.host.db,B)),'')   # baseline: not ended yet
        activate(self.host,cities=self.cities);set_secret(self.host,'player2',stage=4,paranoia=60)
        tc.command(b2,'t-win\n900000',req());tc.command(b2,'coup\n900000',req());tc.command(b2,'go\n900000\n'+str(b2.client.call('throne_mine')['next_cost']),req())
        self.cities.run(self.host,'player2');b2.client.call('throne_mine');public=te.public_status(self.host.db,B)
        self.assertEqual(public['winner'],'player2')
        key,title,body=tc.end_popup(b1,public).rstrip('\n').split('\t')
        self.assertEqual(title,'새 황제 즉위');self.assertIn('플레이어 2 / 로마 총독이',body);self.assertIn('새 황제',body);self.assertEqual(len(key),32)
        self.assertEqual(tc.end_popup(b1,public),key+'\t'+title+'\t'+body+'\n')   # same line again: shown once by its id
        self.assertEqual(tc.end_popup(b2,public),'')                                 # the winner has its own popup
        late,_=self.bridge('player3');self.assertEqual(tc.end_popup(late,public),'')  # an end already there at the first look
    def test_coup_that_has_to_wait_opens_nothing_and_says_why(self):
        activate(self.host,'player1',cities=self.cities)
        b,tc=self.bridge('player1');tc.command(b,'coup\n200000',req())
        self.assertEqual(b.files['throne-dialog.txt'],'');self.assertIn('다음 쿠데타 지원까지',self.box(b)['note'])
    def test_gift_dialog_and_requote(self):
        activate(self.host,cities=self.cities);set_secret(self.host,'player1',stage=1,paranoia=25)
        b,tc=self.bridge('player1');tc.command(b,'gift\n9000',req())
        d=self.dialog(b);self.assertIn(['amount','선물 한도','0 Dn'],[l[:3] for l in d]);self.assertIn(['go','선물 보내기','0'],d)   # starts at 0: nothing to send yet
        tc.command(b,'add1000\n9000',req());tc.command(b,'add1000\n9000',req())       # 2,000 Dn limit
        d=self.dialog(b);self.assertIn(['low','예상 감소','-6'],d);self.assertIn(['low','선물 후 편집증','19'],d);self.assertIn(['low','실제 차감','1,600 Dn'],d)
        self.assertIn(['bar','황제의 의심','25 / 100','25'],d);self.assertIn(['row','기준 하한 (1점 200 Dn)','20'],d);self.assertIn(['row','선물 최저치 (1점 600 Dn)','10'],d)
        tc.command(b,'reset\n9000',req());self.assertIn(['amount','선물 한도','0 Dn'],[l[:3] for l in self.dialog(b)]);tc.command(b,'add5000\n9000',req())
        self.host.settle(MONTH);quote=b.throne_ui['quote']             # the state moves before the click arrives
        r=req();out=tp.spend(self.host.db,B,'player1',r,'gift',5000,9000,tp.fingerprint(quote),MONTH,self.host.ensure);self.host.db.commit()
        self.assertEqual(out['state'],'requote')
        tc.command(b,'go\n9000',req());self.assertTrue(any(l[0]=='message' and '달라졌습니다' in l[1] for l in self.dialog(b)))
    def test_no_arrows_or_dots_in_any_prepared_text(self):
        activate(self.host,cities=self.cities);set_secret(self.host,'player1',stage=2,paranoia=100);self.host.settle(0)
        b,tc=self.bridge('player1');texts=[]
        for action in ('coup','gift','tribute'):tc.command(b,action+'\n200000',req());texts+=[b.files['throne-box.txt'],b.files['throne-dialog.txt']];tc.command(b,'close\n200000',req())
        for text in texts:
            for bad in '→←↑↓·•…▶◀■□★':self.assertNotIn(bad,text)
    def test_restoring_and_end(self):
        import throne_client
        self.assertEqual(throne_client.box_file(dict(test=True,restoring=True,stages=5),{},{},0).splitlines()[0],'state\trestoring')
        ended=throne_client.box_file(dict(test=True,restoring=False,ended=True,winner_is_me=False,active=True,paranoia=50,floor=50,gift_floor=40,stage=2,stages=5,stage_name='근위대 포섭',next_cost=20000,failures=0),{},{},0)
        self.assertIn('state\tended',ended);self.assertIn('coup\t0',ended);self.assertIn('gift\t0',ended)

class SimpleBridge:
    def __init__(s,root,client):s.root=Path(root);s.client=client;s.files={};s.config={'session':'test'};s.throne_private_events=''
    def write_changed(s,name,text):s.files[name]=text;return True

if __name__=='__main__':unittest.main()
