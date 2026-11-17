"""황위 시험 규칙 v1: end of the trial, spends caught by it, refunds, and the 1,000,000 Dn payment limit.

Policy (approved 2026-11-12): spends settled before the end are kept. The first spend whose debit receipt the host
confirms and whose final-stage success it settles ends the trial; spends confirmed in the same pass go in acceptance
order. A spend not settled by then never takes effect: not taken -> cancelled without a charge; taken -> exactly the
taken amount is paid back to the same city by its own refund command, 'refunded' only after that receipt.

Two city backends run every money test:
  Model   the Python stand-in of post_book_apply (test_throne_trial.Cities);
  Native  the real C src/multiplayer/post_book.c (post_book_apply / encode / decode) built as a shared library
          (AUGUSTUS_POST_BOOK_LIB=<built library>, or built here with a C compiler; skipped with the reason if neither).
Both use the real host code: throne_play, throne_state, trade_post_ledger, post_recovery.reconcile, cash_snapshot.
Neither is the game process, a real joint-save file or the TCP flow. Fixture stages/paranoia/funds are TEST INPUTS."""
import ctypes,json,os,shutil,subprocess,sys,tempfile,time,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_throne_trial as T
from test_throne_trial import B,CITIES,MONTH,RULES,Base,Cities,Draws,Host,req,save,set_secret,restore_own,restore_replica,activate
import throne_state as ts,throne_events as te,throne_play as tp,throne_rules as tr,trade_post_ledger

ROOT=Path(__file__).resolve().parents[1]
FUNDS=200000

# ---------------------------------------------------------------- the real C book (optional, never faked)
class PostCommand(ctypes.Structure):_fields_=[('id',ctypes.c_char*96),('peer',ctypes.c_int32),('step',ctypes.c_int32),('resource',ctypes.c_int32),('amount',ctypes.c_int32)]
class PostReceipt(ctypes.Structure):_fields_=[('command',PostCommand),('applied',ctypes.c_int32)]
class PostBook(ctypes.Structure):_fields_=[('roster',ctypes.c_char*65),('site',ctypes.c_uint32*8),('generation',ctypes.c_uint32*8),('cargo',(ctypes.c_int32*64)*8),('count',ctypes.c_uint32),('receipts',PostReceipt*512)]
STEPS=('export','escrow','receive','pay','refund_goods','refund_money')
ROSTER=b'ab'*32
_lib=None;_why=''
def native():
    global _lib,_why
    if _lib or _why:return _lib
    path=os.environ.get('AUGUSTUS_POST_BOOK_LIB')
    if not path:
        cc=shutil.which('cc') or shutil.which('gcc')
        source=ROOT/'src/multiplayer/post_book.c'
        if not cc or not source.is_file():_why='no C compiler or post_book.c';return None
        out=Path(tempfile.mkdtemp())/'post_book.so'
        r=subprocess.run([cc,'-shared','-fPIC','-O1','-o',str(out),str(source)],capture_output=True,text=True)
        if r.returncode:_why='build failed: '+r.stderr[-300:];return None
        path=str(out)
    try:lib=ctypes.CDLL(path)
    except OSError as e:_why=str(e);return None
    lib.post_book_init.argtypes=[ctypes.POINTER(PostBook),ctypes.c_char_p]
    lib.post_book_apply.argtypes=[ctypes.POINTER(PostBook),ctypes.POINTER(ctypes.c_int32),ctypes.POINTER(PostCommand)]
    lib.post_book_encode.argtypes=[ctypes.POINTER(PostBook),ctypes.c_char_p,ctypes.c_size_t];lib.post_book_encode.restype=ctypes.c_size_t
    lib.post_book_decode.argtypes=[ctypes.POINTER(PostBook),ctypes.c_char_p,ctypes.c_char_p,ctypes.c_size_t]
    _lib=lib;return lib

class NativeCities(Cities):
    """Each city's treasury and receipt book live in the real C post_book; a city save is post_book_encode + treasury."""
    def __init__(s,funds):
        s.lib=native();s.treasury_c={c:ctypes.c_int32(v) for c,v in funds.items()};s.books={}
        for c in CITIES:b=PostBook();assert s.lib.post_book_init(ctypes.byref(b),ROSTER);s.books[c]=b
    @property
    def treasury(s):return {c:v.value for c,v in s.treasury_c.items()}
    def set_treasury(s,city,value):s.treasury_c[city].value=value
    def apply(s,city,c):
        cmd=PostCommand(c['id'].encode(),CITIES.index(c['peer']),STEPS.index(c['step'])+1,c['asset'],c['amount'])
        r=s.lib.post_book_apply(ctypes.byref(s.books[city]),ctypes.byref(s.treasury_c[city]),ctypes.byref(cmd))
        assert r in (0,1),r
        return bool(r)
    def receipts(s,city):
        b=s.books[city];out={}
        for i in range(b.count):
            r=b.receipts[i];out[r.command.id.decode()]=dict(peer=CITIES[r.command.peer],step=STEPS[r.command.step-1],asset=r.command.resource,amount=r.command.amount,applied=bool(r.applied))
        return out
    def snapshot(s):
        out={}
        for c,b in s.books.items():
            n=s.lib.post_book_encode(ctypes.byref(b),None,0);buf=ctypes.create_string_buffer(n)
            assert s.lib.post_book_encode(ctypes.byref(b),buf,n)==n;out[c]=(buf.raw,s.treasury_c[c].value)
        return out
    def load(s,snap):
        for c,(raw,money) in snap.items():
            b=PostBook();assert s.lib.post_book_decode(ctypes.byref(b),ROSTER,raw,len(raw));s.books[c]=b;s.treasury_c[c].value=money

class ModelCities(Cities):
    def set_treasury(s,city,value):s.treasury[city]=value

# ---------------------------------------------------------------- scenarios (run with both backends)
class EndScenarios:
    backend=ModelCities
    def setUp(self):
        super().setUp();self.cities=self.backend({c:FUNDS for c in CITIES})
        activate(self.host,'player3',cities=self.cities)   # paranoia on (player3 pays one failed 5,000 coup)
    def finalist(self,city,stage=4):set_secret(self.host,city,stage=stage,paranoia=50)
    def final(self,city,draw=0,tick=1600):
        self.draws.queue.append(draw);out=self.host.spend(city,'coup',80000,tick=tick);self.assertEqual(out['state'],'charging');return out['request']
    def spend_of(self,host,city,request):return next(e for e in host.state()['players'][city]['secret']['spends'] if e['request']==request)
    def refunds(self,host,request):
        return [dict(r) for r in host.db.execute("SELECT * FROM post_command WHERE contract=? AND step='pay'",(tp.contract_id(request),))]
    def invariant(self,host):
        """Per spend: an effect and a refund never both; refunds never above the taken amount; 'refunded' only with a
        paid receipt. Checked after every step."""
        for city,p in host.state()['players'].items():
            if 'secret' not in p:continue
            for e in p['secret']['spends']:
                row=host.db.execute('SELECT * FROM post_contract WHERE id=?',(tp.contract_id(e['request']),)).fetchone()
                pays=host.db.execute("SELECT count(*) FROM post_command WHERE contract=? AND step='pay' AND state='applied'",(tp.contract_id(e['request']),)).fetchone()[0]
                self.assertLessEqual(pays,1)
                if e['state']=='done':self.assertEqual(pays,0);self.assertFalse(row['paid'])
                if e['state']=='refunded':self.assertTrue(row['paid'] and row['exported'])
                if e['state'] in ('cancelled','void'):self.assertFalse(row and row['exported'] and not row['paid'] and e['state']!='void')
    def assertRefundedOnce(self,city,start=FUNDS):
        self.assertEqual(self.cities.treasury[city],start)

    def test_first_confirmed_final_success_wins(self):
        self.finalist('player1');self.finalist('player2')
        r1=self.final('player1');r2=self.final('player2')          # both requested (player1 first), both charging
        self.cities.run(self.host,'player1',ack=False)              # player1's money already left its city...
        self.cities.run(self.host,'player2');self.host.settle(1600)   # ...but player2's debit is confirmed first: it wins
        st=self.host.state();self.assertEqual((st['winner'],st['ended']),('player2',True))
        self.assertEqual(self.spend_of(self.host,'player1',r1)['state'],'charging')   # unknown here: waits for its receipt
        self.cities.report(self.host,'player1');self.host.settle(1600)   # player1's receipt confirmed after the end
        e=self.spend_of(self.host,'player1',r1);self.assertEqual((e['state'],e['result']),('refunding','ended'))
        self.assertEqual(self.host.state()['players']['player1']['stage'],4)   # no effect, no failure, no wait
        s=self.host.state()['players']['player1']['secret'];self.assertEqual((s['failures'],s['next_cost']),(0,80000))
        self.assertEqual(self.cities.treasury['player1'],FUNDS-80000);self.invariant(self.host)
        self.cities.run(self.host,'player1');self.host.settle(1600)
        self.assertEqual(self.spend_of(self.host,'player1',r1)['state'],'refunded');self.assertRefundedOnce('player1')
        self.assertEqual(self.cities.treasury['player2'],FUNDS-80000)          # the winning attempt is spent normally
        own=self.host.own('player1');self.assertEqual(own['last']['state'],'refunded');self.invariant(self.host)

    def same_pass(self,first,second):
        self.finalist('player1');self.finalist('player2')
        a=self.final(first);b=self.final(second)
        self.cities.run(self.host,'player1');self.cities.run(self.host,'player2')   # both receipts in before one settle
        self.host.settle(1600);return a,b
    def test_same_pass_goes_by_acceptance_order(self):
        a,b=self.same_pass('player2','player1')     # player2 accepted first; city order would say player1
        self.assertEqual(self.host.state()['winner'],'player2')
        self.assertEqual(self.spend_of(self.host,'player1',b)['state'],'refunding');self.invariant(self.host)
    def test_same_pass_other_order(self):
        a,b=self.same_pass('player1','player2')
        self.assertEqual(self.host.state()['winner'],'player1')
    def test_acceptance_order_survives_save_and_reload(self):
        self.finalist('player1');self.finalist('player2')
        a=self.final('player2');b=self.final('player1')
        saved=save(self.host,1,1600,self.cities)
        new=restore_own(self.tmp.name,saved,self.host);self.addCleanup(new.db.close);self.cities.load(saved['cities'])
        self.cities.run(new,'player1');self.cities.run(new,'player2');new.settle(1600)
        self.assertEqual(new.state()['winner'],'player2')

    def test_spends_settled_before_the_end_are_kept(self):
        set_secret(self.host,'player3',paranoia=40)
        g=self.host.spend('player3','gift',2000,tick=1600)['request'];self.cities.run(self.host,'player3');self.host.settle(1600)
        self.finalist('player1');self.final('player1');self.cities.run(self.host,'player1');self.host.settle(1600)
        self.assertTrue(self.host.state()['ended'])
        e=self.spend_of(self.host,'player3',g);self.assertEqual(e['state'],'done');self.assertEqual(self.refunds(self.host,g),[])
        failed=[e for e in self.host.state()['players']['player3']['secret']['spends'] if e['kind']=='coup'][0]
        self.assertEqual((failed['state'],failed['result']),('done','failure'));self.assertEqual(self.refunds(self.host,failed['request']),[])
        self.assertEqual(self.cities.treasury['player3'],FUNDS-5000-2000)

    def test_not_taken_yet_is_cancelled_without_a_charge(self):
        self.finalist('player1');set_secret(self.host,'player2',paranoia=40)
        g=self.host.spend('player2','gift',2000,tick=1600)['request']     # staged, never handed to the city
        self.final('player1');self.cities.run(self.host,'player1');self.host.settle(1600)
        e=self.spend_of(self.host,'player2',g);self.assertEqual((e['state'],e['result']),('cancelled','ended'))
        self.cities.run(self.host,'player2');self.cities.report(self.host,'player2');self.host.settle(1600)
        self.assertEqual(self.cities.treasury['player2'],FUNDS);self.assertEqual(self.refunds(self.host,g),[])
        self.assertEqual(self.host.own('player2')['last']['state'],'cancelled');self.invariant(self.host)

    def test_late_receipt_taken_is_refunded_exactly(self):
        self.finalist('player1');set_secret(self.host,'player2',paranoia=27)
        g=self.host.spend('player2','gift',3500,tick=1600)                   # limit 3,500, actual charge 3,400 (17 pts)
        self.assertEqual(g['quote']['charge'],3400)
        self.cities.run(self.host,'player2',ack=False)                         # handed over and applied; host not told
        self.final('player1');self.cities.run(self.host,'player1');self.host.settle(1600)
        e=self.spend_of(self.host,'player2',g['request']);self.assertEqual(e['state'],'charging')   # unknown: wait
        box=__import__('throne_client').box_file(self.host.own('player2'),{},{},0)
        self.assertIn('state\tended',box);self.assertIn('처리 중이던 지출은 취소되며, 이미 빠진 돈은 전액 돌려받습니다.',box)
        self.cities.report(self.host,'player2');self.host.settle(1600)      # the receipt arrives late
        self.assertEqual(self.spend_of(self.host,'player2',g['request'])['state'],'refunding')
        self.assertEqual(self.refunds(self.host,g['request'])[0]['amount'],3400)   # what was taken, not the limit
        self.cities.run(self.host,'player2');self.host.settle(1600)
        self.assertEqual(self.spend_of(self.host,'player2',g['request'])['state'],'refunded');self.assertRefundedOnce('player2')
        s=self.host.state()['players']['player2']['secret'];self.assertEqual((s['paranoia'],s['gift_total']),(27+4,0))   # no gift effect; +2 months x2
        self.invariant(self.host)

    def test_late_receipt_not_taken_is_cancelled(self):
        self.finalist('player1');set_secret(self.host,'player2',paranoia=40)
        self.cities.set_treasury('player2',100)
        g=self.host.spend('player2','gift',2000,tick=1600)['request'];self.cities.run(self.host,'player2',ack=False)
        self.final('player1');self.cities.run(self.host,'player1');self.host.settle(1600)
        self.cities.report(self.host,'player2');self.host.settle(1600)
        self.assertEqual(self.spend_of(self.host,'player2',g)['state'],'cancelled');self.assertEqual(self.refunds(self.host,g),[])
        self.assertEqual(self.cities.treasury['player2'],100)

    def ended_with_refund_due(self):
        self.finalist('player1');self.finalist('player2')
        self.final('player1');r=self.final('player2')
        self.cities.run(self.host,'player2',ack=False)                      # player2's debit taken, not confirmed yet
        self.cities.run(self.host,'player1');self.host.settle(1600)         # player1's confirmed first: the end
        self.cities.report(self.host,'player2');self.host.settle(1600)      # player2's receipt: taken -> refund
        self.assertEqual(self.spend_of(self.host,'player2',r)['state'],'refunding');return r

    def test_refund_resent_and_ack_lost(self):
        r=self.ended_with_refund_due()
        self.cities.run(self.host,'player2',ack=False);self.cities.run(self.host,'player2',ack=False)   # resent: same receipt
        self.host.settle(1600);self.assertEqual(self.spend_of(self.host,'player2',r)['state'],'refunding')   # no receipt seen yet
        host2=Host(self.tmp.name);self.addCleanup(host2.db.close)        # host restarts
        self.cities.report(host2,'player2');host2.settle(1600);host2.settle(1600)
        self.assertEqual(self.spend_of(host2,'player2',r)['state'],'refunded');self.assertRefundedOnce('player2')
        self.cities.run(host2,'player2');self.cities.report(host2,'player2');host2.settle(1600)
        self.assertRefundedOnce('player2');self.invariant(host2)

    def test_refund_the_city_cannot_take_stays_owed(self):
        r=self.ended_with_refund_due()
        self.cities.set_treasury('player2',2**31-1-1000)          # TEST INPUT: a treasury at the engine's limit
        self.cities.run(self.host,'player2');self.host.settle(1600)
        own=self.host.own('player2');busy=own['charging'][0]
        self.assertEqual((busy['state'],busy['refund_blocked']),('refunding',True))
        self.assertIn('도시가 지금 받을 수 없습니다. 권리는 유지되며 다시 시도합니다.',__import__('throne_client').box_file(dict(test=True,restoring=False,ended=True,active=True,stage=1,stages=5,paranoia=30,charging=[busy]),{},{},0))
        self.cities.set_treasury('player2',FUNDS-80000)           # the city spent money: it can take it now
        self.host.settle(1600);self.assertEqual(len(self.refunds(self.host,r)),1)   # no new attempt before the back-off
        self.host.db.execute('UPDATE cash_retry SET next_time=0');self.host.db.commit()   # TEST: the back-off time passes
        self.host.settle(1600);self.assertEqual(len(self.refunds(self.host,r)),2)
        self.cities.run(self.host,'player2');self.host.settle(1600);self.cities.run(self.host,'player2');self.host.settle(1600)
        self.assertEqual(self.spend_of(self.host,'player2',r)['state'],'refunded');self.assertRefundedOnce('player2');self.invariant(self.host)

    def test_new_requests_after_the_end_are_refused_while_refunds_go_on(self):
        r=self.ended_with_refund_due();before=len(self.host.debits())
        for kind,amount in (('coup',5000),('gift',2000)):
            out=self.host.spend('player3',kind,amount,tick=1600,expect=None);self.assertEqual(out['state'],'refused');self.assertIn('끝났습니다',out['quote']['reason'])
        self.assertEqual(len(self.host.debits()),before)
        self.cities.run(self.host,'player2');self.host.settle(1600);self.assertEqual(self.spend_of(self.host,'player2',r)['state'],'refunded')

    def test_departure_keeps_the_refund_owed(self):
        r=self.ended_with_refund_due()
        ledger=self.host.ledger()
        try:ledger.abandon({'player2'})
        finally:ledger.close()
        self.host.settle(1600);self.assertEqual(len(self.refunds(self.host,r)),1)
        self.assertEqual(self.refunds(self.host,r)[0]['state'],'pending')   # not waived, nobody else paid
        self.cities.run(self.host,'player2');self.host.settle(1600);self.assertRefundedOnce('player2')

    # -------- saves, reloads and host changes at each point
    def checkpoint(self,point):
        self.finalist('player1');self.finalist('player2')
        self.final('player1');r=self.final('player2')
        self.cities.run(self.host,'player2',ack=False)                     # handed over (taken), host not told yet
        self.cities.run(self.host,'player1');self.host.settle(1600)        # the trial ends (player1)
        if point=='after-debit':self.cities.report(self.host,'player2')   # debit confirmed, not settled yet
        if point in ('refund-issued','refund-applied'):self.cities.report(self.host,'player2');self.host.settle(1600)
        if point=='refund-applied':self.cities.run(self.host,'player2',ack=False)        # credited, host not told
        return r,save(self.host,1,1600,self.cities)
    def finish(self,host,r):
        for _ in range(3):
            self.cities.report(host,'player2');self.cities.run(host,'player2');host.settle(1600)
        self.assertEqual(self.spend_of(host,'player2',r)['state'],'refunded');self.assertRefundedOnce('player2');self.invariant(host)
        self.assertEqual(host.state()['winner'],'player1')
    def run_point(self,point,replica):
        r,saved=self.checkpoint(point)
        self.cities.load(saved['cities'])
        if replica:
            new=restore_replica(self.tmp.name,saved,self.host);self.addCleanup(new.db.close)
            for _ in range(2):self.cities.report(new,'player2');self.cities.run(new,'player2');new.settle(1600)   # pending: not settled
            self.assertEqual(new.state()['players']['player2'].keys(),{'stage','eliminated','pending'})
            for c in CITIES:o=saved['openings'][c];te.hand_in(new.db,B,c,o['secret'],o['nonce'],1600)
            new.db.commit()
        else:new=restore_own(self.tmp.name,saved,self.host);self.addCleanup(new.db.close)
        self.finish(new,r)
    def test_save_points_on_the_same_host(self):
        for point in ('before-debit','after-debit','refund-issued','refund-applied'):
            with self.subTest(point=point):
                self.tearDown();self.setUp();self.run_point(point,False)
    def test_save_points_with_host_change(self):
        for point in ('before-debit','after-debit','refund-issued','refund-applied'):
            with self.subTest(point=point):
                self.tearDown();self.setUp();self.run_point(point,True)

class EndModel(EndScenarios,Base):backend=ModelCities

class Orders(Base):
    """Bounded exhaustive check (a finite model, not a proof): two final-stage requests (player1 accepted first), then
    every order of six events, then the normal drain (receipts, deliveries, settles). After each step and at the end:
    one winner; the loser is cancelled or refunded; each city lost exactly what its outcome says; per spend never an
    effect and a refund together, never more than one applied refund.
      d1 d2  the city takes its debit command (no acknowledgement reaches the host)
      r1     player1's receipts reach the host (cash report)
      S      the host settles
      V      joint save
      C      host crash: back to the last save (cities too)"""
    EVENTS=('d1','d2','r1','S','V','C')
    def test_every_order(self):
        import itertools
        count=0
        for order in itertools.permutations(self.EVENTS):
            with self.subTest(order=order):self.one(order)
            count+=1
        self.assertEqual(count,720)
    def one(self,order):
        self.tearDown();self.setUp()
        cities=ModelCities({c:FUNDS for c in CITIES});self.cities=cities
        activate(self.host,'player3',cities=cities)
        for c in ('player1','player2'):set_secret(self.host,c,stage=4,paranoia=50)
        reqs={}
        for c in ('player1','player2'):
            self.draws.queue.append(0);reqs[c]=self.host.spend(c,'coup',80000,tick=1600)['request']
        host=self.host;sid=1;saved=save(host,sid,1600,cities)
        check=EndScenarios.invariant.__get__(self)
        for ev in order:
            if ev=='d1':cities.run(host,'player1',ack=False)
            elif ev=='d2':cities.run(host,'player2',ack=False)
            elif ev=='r1':cities.report(host,'player1')
            elif ev=='S':host.settle(1600)
            elif ev=='V':sid+=1;saved=save(host,sid,1600,cities)
            elif ev=='C':cities.load(saved['cities']);host=restore_own(self.tmp.name,saved,host);self.addCleanup(host.db.close)
            check(host)
        for _ in range(4):
            for c in ('player1','player2'):cities.report(host,c);cities.run(host,c);host.settle(1600)
            check(host)
        st=host.state();self.assertTrue(st['ended']);w=st['winner'];l='player2' if w=='player1' else 'player1'
        win=next(e for e in st['players'][w]['secret']['spends'] if e['request']==reqs[w])
        lose=next(e for e in st['players'][l]['secret']['spends'] if e['request']==reqs[l])
        self.assertEqual((win['state'],win['result']),('done','success'))
        self.assertIn(lose['state'],('cancelled','refunded'))
        self.assertEqual((cities.treasury[w],cities.treasury[l]),(FUNDS-80000,FUNDS))
        self.assertEqual(st['players'][l]['stage'],4)

@unittest.skipUnless(native(),'real post_book.c not available: '+_why)
class EndNative(EndScenarios,Base):backend=NativeCities

class Wording(unittest.TestCase):
    def test_ended_spends_are_never_shown_as_results(self):
        import throne_client as tc
        own=dict(test=True,restoring=False,ended=True,active=True,stage=1,stages=5,paranoia=30,charging=[])
        for state,word in (('cancelled','취소되었습니다. 차감된 돈은 없습니다.'),('refunding','돌려받는 중입니다.'),('refunded','80,000 Dn을 돌려받았습니다.')):
            for kind in ('coup','gift'):
                e=dict(kind=kind,amount=80000,state=state,result='ended',points=6 if kind=='gift' else 0,chance=5500,chance_text='55.00%',seq=1,request='a'*32)
                box=tc.box_file(dict(own,charging=[e]) if state=='refunding' else dict(own,last=e),{},{},0)
                line=next(l for l in box.splitlines() if l.startswith('note\t'));self.assertIn(word,line)
                for wrong in ('성공','실패','편집증 -','성공률'):self.assertNotIn(wrong,line)

# ---------------------------------------------------------------- the payment limit
class PaymentLimit(Base):
    def test_exact_cost_past_the_limit_is_shown_and_refused(self):
        activate(self.host,cities=self.cities)
        set_secret(self.host,'player1',stage=4,paranoia=50,failures=11)
        self.assertEqual(self.host.own('player1')['next_cost'],932400)
        set_secret(self.host,'player1',failures=12)
        own=self.host.own('player1');self.assertEqual((own['next_cost'],own['limit_reached']),(1165500,True))
        out=self.host.spend('player1','coup',1000000,tick=1600,expect=None)
        self.assertEqual(out['state'],'refused');self.assertIn('1,165,500',out['quote']['reason']);self.assertIn('1회 지출 한도',out['quote']['reason'])
        s=self.host.state()['players']['player1']['secret'];self.assertEqual((s['failures'],len(s['spends'])),(12,0))
        box=__import__('throne_client').box_file(own,{},{},0);self.assertIn('더 도전할 수 없습니다',box);self.assertIn('coup\t0',box)
    def test_unreachable_failure_counts_are_rejected_quickly(self):
        activate(self.host,cities=self.cities)
        for failures in (13,10000):
            started=time.time()
            with self.assertRaises(ValueError):set_secret(self.host,'player1',stage=4,paranoia=50,failures=failures)
            self.assertLess(time.time()-started,2)
        self.assertEqual(tr.min_cost(RULES,4,10000)>tr.BIG,True)
    def test_old_stand_in_value_is_made_exact_on_read(self):
        activate(self.host,cities=self.cities)
        set_secret(self.host,'player1',stage=4,paranoia=50,failures=12)
        state=self.host.state();state['players']['player1']['secret']['next_cost']=1000100   # written by the old rule code
        del state['players']['player1']['secret']['spends'][:]
        payload=ts.encode(state);self.host.db.execute('UPDATE throne_state SET payload=?,hash=? WHERE id=1',(payload,ts.sha(payload.encode())));self.host.db.commit()
        self.assertEqual(self.host.state()['players']['player1']['secret']['next_cost'],1165500)

# ---------------------------------------------------------------- a refund the city cannot take for a long time
class RetryGrowth:
    """A refund whose city's receipts keep saying 'not taken' (treasury at the engine limit: TEST INPUT) is tried again
    with a new command only after the spend's back-off (throne_play.refund_retry_wait, counted per spend in the ledger).
    Before this rule a new command followed every delivery back-off (~1 s): in a simulated day at one exchange per 5 s
    that was 8,641 commands and receipts and a 3,765,522-byte cash checkpoint (limit 4,000,000; the real C book holds
    512 receipts). Time is a simulated clock (time.time patched); exchanges every STEP seconds."""
    STEP=10
    def setUp(self):
        super().setUp();self.clock=[1_000_000.0]
        from unittest import mock
        p=mock.patch('time.time',lambda:self.clock[0]);p.start();self.addCleanup(p.stop)
    def blocked(self):
        r=self.ended_with_refund_due();self.cities.set_treasury('player2',2**31-1-1000);return r
    def exchange(self,host,seconds):
        for _ in range(int(seconds//self.STEP)):
            self.clock[0]+=self.STEP;self.cities.run(host,'player2');host.settle(1600)
    def test_a_day_blocked_stays_small_and_pays_once_when_possible(self):
        r=self.blocked();self.exchange(self.host,24*3600)
        tried=len(self.refunds(self.host,r))
        self.assertLessEqual(tried,32);self.assertGreaterEqual(tried,25)       # 30 expected: 30 s doubling to one per hour
        self.assertTrue(all(c['state']=='unapplied' for c in self.refunds(self.host,r)[:-1]))
        self.assertLess(len(self.cities.receipts('player2')),40)
        import cash_snapshot
        self.assertLess(len(json.dumps(cash_snapshot.current(self.host.db))),60000)
        self.assertEqual(self.spend_of(self.host,'player2',r)['state'],'refunding');self.invariant(self.host)
        self.cities.set_treasury('player2',FUNDS-80000)                      # the city can take it again
        self.exchange(self.host,tp.REFUND_RETRY_CAP+60)
        self.assertEqual(self.spend_of(self.host,'player2',r)['state'],'refunded');self.assertRefundedOnce('player2')
        self.exchange(self.host,2*tp.REFUND_RETRY_CAP);self.assertRefundedOnce('player2');self.invariant(self.host)
    def test_back_off_survives_host_restart_and_handover(self):
        r=self.blocked();self.exchange(self.host,3*3600)
        tried=len(self.refunds(self.host,r));wait=tp.refund_retry_wait(tried);self.assertGreaterEqual(wait,1800)
        host2=Host(self.tmp.name);self.addCleanup(host2.db.close)              # the host program restarts
        self.exchange(host2,60);self.assertEqual(len(self.refunds(host2,r)),tried)
        saved=save(host2,7,1600,self.cities);host3=restore_replica(self.tmp.name,saved,host2);self.addCleanup(host3.db.close)
        for c in CITIES:o=saved['openings'][c];te.hand_in(host3.db,B,c,o['secret'],o['nonce'],1600)
        host3.db.commit()
        self.exchange(host3,60);self.assertEqual(len(self.refunds(host3,r)),tried)    # another PC hosts: same count, same wait
        self.exchange(host3,wait+60);self.assertEqual(len(self.refunds(host3,r)),tried+1)
        self.assertEqual(tp.refund_retry_wait(tried+1),min(tp.REFUND_RETRY_CAP,2*wait));self.invariant(host3)

def _only_growth(cls):
    for name in dir(EndScenarios):
        if name.startswith('test_'):setattr(cls,name,None)    # the end scenarios run in EndModel/EndNative, not again here
    return cls
@_only_growth
class RetryGrowthModel(RetryGrowth,EndScenarios,Base):backend=ModelCities
@_only_growth
@unittest.skipUnless(native(),'real post_book.c not available: '+_why)
class RetryGrowthNative(RetryGrowth,EndScenarios,Base):backend=NativeCities

if __name__=='__main__':unittest.main()
