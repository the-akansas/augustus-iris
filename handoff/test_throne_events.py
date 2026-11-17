"""Race for the Throne: per-player private state, anonymous attempts, host change / save / resume with sealed records.

Decided rules under test: paranoia (and failures, next cost, attempts) are per player and private; failed attempts are
anonymous; host change, save and resume keep every private value; paranoia and the original favour are separate.
Values such as failures=2 or paranoia=37 below are TEST INPUTS to make secrets differ (set_secret), not game rules.
The last class walks every order of a small set of events (attempt, resend, save, host crash, hand-in) and checks the
invariants after each step; it is an exhaustive test of a bounded model, not a proof."""
import copy,itertools,json,sqlite3,sys,unittest,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/'Augustus'
sys.path.insert(0,str(ROOT))
import throne_state as ts,throne_events as te,scenario_check as sc,scenario_project as sp,creator_presets

CITIES=['player1','player2','player3']
def binding():return dict(cities=list(CITIES),throne=dict(rules=ts.defaults(),rome=dict(id='rome',x=768,y=496)))
B=binding()
def new_db():
    db=sqlite3.connect(':memory:');db.execute('CREATE TABLE joint_save(id INTEGER PRIMARY KEY,ticks INTEGER,state TEXT)');return db
def room():
    db=new_db();ts.configure(db,B,0);te.initialize(db);return db
def save(db,sid,tick):
    db.execute("INSERT INTO joint_save(id,ticks,state) VALUES(?,?,'complete')",(sid,tick));ts.capture(db,sid,B,tick)
def replica(db,sid,tick):
    """What another player's PC keeps (save_replica.export -> download -> put): the sealed form only."""
    other=new_db();ts.initialize(other);other.execute("INSERT INTO joint_save(id,ticks,state) VALUES(?,?,'complete')",(sid,tick))
    ts.put(other,sid,ts.sealed_save(db,sid,B,tick),B,tick);return other
def restore(src,sid,tick):
    """room_host.create_room(restore=...): read_pair -> throne_state.restore into the new room."""
    db=new_db();ts.initialize(db);ts.restore(db,ts.read(src,sid,B,tick),B,tick);return db
def set_secret(db,city,**values):   # TEST ONLY: make secrets differ; keeps the existing validity rules
    s=ts.current(db,B);p=s['players'][city]['secret'];p.update(values)
    p['next_cost']=ts.expected_cost(s['spec']['rules'],s['players'][city]['stage'],p['failures']);ts.store(db,s,B)
def req():return uuid.uuid4().hex
def no_commits(sealed):
    s=copy.deepcopy(sealed)
    for p in s['players'].values():p['sealed']['commit']='-'
    return s
def everything_public(db):
    """Every byte a non-host client can get about the throne: status and the backup replica of the latest save."""
    out=dict(status=te.public_status(db,B))
    sid=te.latest_sealed(db)
    if sid:out['replica']=ts.sealed_save(db,sid,B,db.execute('SELECT ticks FROM joint_save WHERE id=?',(sid,)).fetchone()[0])
    return out
def scan_text(public):   # the public rule set itself names 'monthly_paranoia': leave it out of the leak scan
    p=copy.deepcopy(public)
    if p.get('replica'):p['replica'].pop('spec')
    return json.dumps(p)

class PerPlayer(unittest.TestCase):
    def test_one_players_change_leaves_the_others(self):
        db=room();te.begin_attempt(db,B,'player1',req(),100);before=ts.current(db,B)['players']
        set_secret(db,'player1',paranoia=37,failures=2);after=ts.current(db,B)['players']
        self.assertEqual(after['player2'],before['player2']);self.assertEqual(after['player3'],before['player3'])
        self.assertEqual((after['player1']['secret']['paranoia'],after['player1']['secret']['failures']),(37,2))
    def test_each_player_gets_only_its_own(self):
        db=room();te.begin_attempt(db,B,'player1',req(),100);set_secret(db,'player1',paranoia=37,failures=2);set_secret(db,'player2',paranoia=15)
        a=te.own(db,B,'player1');b=te.own(db,B,'player2')
        self.assertEqual((a['paranoia'],a['failures'],len(a['attempts'])),(37,2,1));self.assertEqual((b['paranoia'],b['failures'],b['attempts']),(15,0,[]))
        status=te.public_status(db,B)
        self.assertEqual(set(status),{'active','activated_tick','notices','leading','mood','scoreboard','eliminated','restoring','sealed_save','handover_save','ended','winner'})
        self.assertNotIn('paranoia',json.dumps(status));self.assertNotIn('failures',json.dumps(status));self.assertNotIn('request',json.dumps(status))
    def test_first_attempt_turns_the_display_on_for_all_without_raising_values(self):
        db=room()
        for c in CITIES:self.assertFalse(te.own(db,B,c)['active'])
        te.begin_attempt(db,B,'player2',req(),100)
        for c in CITIES:o=te.own(db,B,c);self.assertTrue(o['active']);self.assertEqual(o['paranoia'],0)
        self.assertTrue(te.public_status(db,B)['active'])

class Anonymous(unittest.TestCase):
    def world(self,who):
        """`who` tried twice and failed (test input: failures=2, paranoia=40); the others did nothing."""
        db=room();te.begin_attempt(db,B,who,'a'*32,100);te.begin_attempt(db,B,who,'b'*32,200)
        set_secret(db,who,failures=2,paranoia=40);save(db,1,800);return db
    def test_failed_attempts_look_the_same_whoever_made_them(self):
        x=self.world('player1');y=self.world('player3')
        px,py=everything_public(x),everything_public(y)
        self.assertEqual(px['status'],py['status'])
        self.assertEqual(no_commits(px['replica']),no_commits(py['replica']))          # only random commitments differ
        self.assertNotEqual(ts.current(x,B)['players'],ts.current(y,B)['players'])     # the secrets really differ
        rep=scan_text(px)
        for word in ('paranoia','failures','next_cost','attempts','request','nonce','secret'):self.assertNotIn(word,rep)
    def test_every_commitment_changes_at_every_save(self):
        db=room();save(db,1,800);first=ts.sealed_save(db,1,B,800);save(db,2,1600);second=ts.sealed_save(db,2,B,1600)
        for c in CITIES:self.assertNotEqual(first['players'][c]['sealed']['commit'],second['players'][c]['sealed']['commit'])
    def test_a_success_shows_only_the_public_rank(self):
        db=room();te.begin_attempt(db,B,'player2',req(),100)
        s=ts.current(db,B);s['players']['player2']['stage']=1;p=s['players']['player2']['secret']     # test input: a success
        p['next_cost']=ts.expected_cost(s['spec']['rules'],1,0);p['paranoia']=s['spec']['rules']['stages'][0]['floor'];ts.store(db,s,B)
        status=te.public_status(db,B);self.assertNotIn('stages',status);self.assertEqual((status['leading'],status['mood']),(1,'불안'))   # 2026-11-14: no per-city stage, only the leading plot
    def test_notice_text_names_no_one(self):
        db=room();te.begin_attempt(db,B,'player1',req(),100);n=te.public_status(db,B)['notices'][0]
        for who in CITIES+['P1','카푸아','플레이어']:self.assertNotIn(who,n['title']+n['body'])

class HostChange(unittest.TestCase):
    def setUp(self):
        self.db=room();self.r=req();te.begin_attempt(self.db,B,'player1',self.r,100);set_secret(self.db,'player1',failures=1,paranoia=20)
        set_secret(self.db,'player2',paranoia=33);save(self.db,1,800)
        self.openings={c:te.own_opening(self.db,B,c,1) for c in CITIES}
    def test_same_host_resumes_with_everything(self):
        back=restore(self.db,1,800)
        self.assertEqual(ts.current(back,B)['players'],ts.current(self.db,B)['players']);self.assertEqual(te.public_status(back,B)['restoring'],[])
    def test_new_host_from_a_backup_waits_for_each_player(self):
        new=restore(replica(self.db,1,800),1,800)
        self.assertEqual(te.public_status(new,B)['restoring'],CITIES)
        self.assertTrue(te.own(new,B,'player1')['restoring']);self.assertEqual(te.public_status(new,B)['leading'],te.public_status(self.db,B)['leading'])
        with self.assertRaises(ValueError):te.begin_attempt(new,B,'player1',req(),900)          # no move on a missing record
        o=self.openings['player1'];self.assertTrue(te.hand_in(new,B,'player1',o['secret'],o['nonce'])['restored'])
        self.assertFalse(te.hand_in(new,B,'player1',o['secret'],o['nonce'])['restored'])     # resent: nothing changes
        self.assertEqual(te.own(new,B,'player1')['paranoia'],20);self.assertEqual(te.own(new,B,'player1')['failures'],1)
        self.assertEqual(te.public_status(new,B)['restoring'],['player2','player3'])
        for c in ('player2','player3'):o=self.openings[c];te.hand_in(new,B,c,o['secret'],o['nonce'])
        self.assertEqual(ts.current(new,B)['players'],ts.current(self.db,B)['players'])
    def test_forged_stale_and_borrowed_records_are_refused(self):
        new=restore(replica(self.db,1,800),1,800);o=self.openings['player1']
        forged=copy.deepcopy(o['secret']);forged['paranoia']=0
        with self.assertRaises(ValueError):te.hand_in(new,B,'player1',forged,o['nonce'])
        with self.assertRaises(ValueError):te.hand_in(new,B,'player2',o['secret'],o['nonce'])   # someone else's record
        save(self.db,2,1600);newer=te.own_opening(self.db,B,'player1',2)
        with self.assertRaises(ValueError):te.hand_in(new,B,'player1',newer['secret'],newer['nonce'])   # not this save's
        self.assertTrue(te.own(new,B,'player1')['restoring'])
    def test_absent_player_stays_pending_through_later_saves(self):
        new=restore(replica(self.db,1,800),1,800)
        for c in ('player2','player3'):o=self.openings[c];te.hand_in(new,B,c,o['secret'],o['nonce'])
        te.begin_attempt(new,B,'player2',req(),900)                                   # the others play on
        new.execute("INSERT INTO joint_save(id,ticks,state) VALUES(2,1600,'complete')");ts.capture(new,2,B,1600)
        later=restore(replica(new,2,1600),2,1600)                                       # another host change
        for c in ('player2','player3'):o=te.own_opening(new,B,c,2);te.hand_in(later,B,c,o['secret'],o['nonce'])
        o=self.openings['player1'];te.hand_in(later,B,'player1',o['secret'],o['nonce'])   # player1 returns with its old record
        self.assertEqual(te.own(later,B,'player1')['paranoia'],20);self.assertEqual(te.public_status(later,B)['restoring'],[])
    def test_resent_attempt_is_not_applied_twice_across_a_host_change(self):
        new=restore(replica(self.db,1,800),1,800);o=self.openings['player1'];te.hand_in(new,B,'player1',o['secret'],o['nonce'])
        again=te.begin_attempt(new,B,'player1',self.r,900)
        self.assertTrue(again['duplicate']);self.assertEqual(len(te.public_status(new,B)['notices']),1)
    def test_attempt_after_the_save_reruns_with_the_same_notice(self):
        r=req();first=te.begin_attempt(self.db,B,'player2',r,900)                      # not in save 1
        new=restore(replica(self.db,1,800),1,800);o=self.openings['player2'];te.hand_in(new,B,'player2',o['secret'],o['nonce'])
        rerun=te.begin_attempt(new,B,'player2',r,900)
        self.assertFalse(rerun['duplicate']);self.assertEqual(rerun['notice'],first['notice'])   # clients already showing it skip it

class ClientSide(unittest.TestCase):
    """throne_client on a player's PC, against the real host functions (a fake transport, no network)."""
    def bridge(self,city,host,folder):
        import throne_client,tempfile
        class Client:
            def __init__(c):c.db=host;c.city=city
            def call(c,op,**kw):
                if op=='throne_mine':return te.own(c.db,B,city)
                if op=='throne_opening':return dict(opening=te.own_opening(c.db,B,city,kw['id']))
                if op=='throne_hand_in':return te.hand_in(c.db,B,city,kw['secret'],kw['nonce'])
                if op=='throne_opening_stored':return te.confirm_stored(c.db,B,city,kw['id'],kw['commit'])
                raise ValueError(op)
        class Bridge:
            joined=True
            def __init__(b):b.root=Path(folder)/city/'bridge';b.root.mkdir(parents=True,exist_ok=True);b.client=Client();b.config={'session':'client-side-test'};b.files={}
            def write_changed(b,name,text):b.files[name]=text
        return Bridge()
    def test_hud_openings_and_hand_in(self):
        import throne_client,tempfile
        with tempfile.TemporaryDirectory() as d:
            host=room();te.begin_attempt(host,B,'player1',req(),100);set_secret(host,'player1',paranoia=37);save(host,1,800)
            mine={c:self.bridge(c,host,d) for c in CITIES}
            for c,b in mine.items():throne_client.sync(b,dict(throne=te.public_status(host,B)))
            self.assertTrue(ts.custody(host,B,1)['ready'])                               # each PC stored and confirmed its own
            # 2026-11-14: the old text box is gone; a format-1 room (stored only, never run) shows no box at all
            self.assertEqual((mine['player1'].files['throne-hud.txt'],mine['player1'].files['throne-box.txt']),('',''))
            self.assertEqual(te.own(host,B,'player1')['paranoia'],37);self.assertEqual(te.own(host,B,'player2')['paranoia'],0)   # each player's own value only
            for c,b in mine.items():   # each PC holds exactly its own opening, never another player's
                kept=[json.loads(f.read_text(encoding='utf-8')) for f in throne_client.folder(b).glob('*.json')]
                self.assertEqual(len(kept),1);self.assertEqual(kept[0]['secret'],ts.current(host,B)['players'][c]['secret'])
            new=restore(replica(host,1,800),1,800)
            for b in mine.values():b.client.db=new
            throne_client.sync(mine['player1'],dict(throne=te.public_status(new,B)))
            self.assertEqual(te.public_status(new,B)['restoring'],['player2','player3'])
            self.assertEqual(te.own(new,B,'player1')['paranoia'],37)
            throne_client.sync(mine['player2'],dict(throne=te.public_status(new,B)))
            self.assertEqual(te.own(new,B,'player2')['paranoia'],0)
            self.assertTrue(te.own(new,B,'player3')['restoring'])

class Formats(unittest.TestCase):
    def test_format_1_saves_still_load_and_are_sealed_for_backups(self):
        db=room();old=ts.current(db,B);v1=copy.deepcopy(old);v1['version']=1;v1.pop('notices')
        v1['players']={c:dict(stage=0,eliminated=False,**{k:v for k,v in p['secret'].items() if k!='attempts'}) for c,p in old['players'].items()}
        db.execute("INSERT INTO joint_save(id,ticks,state,throne_version) VALUES(1,0,'complete',1)")
        payload=ts.encode(v1);db.execute('INSERT INTO joint_throne VALUES(1,?,?)',(payload,ts.sha(payload.encode())))
        live=ts.read(db,1,B,0);self.assertEqual(live['version'],2);self.assertEqual(live['players']['player1']['secret']['attempts'],[])
        sealed=ts.sealed_save(db,1,B,0);self.assertNotIn('secret',json.dumps(sealed))
    def test_unknown_format_is_refused(self):
        db=room();save(db,1,800);db.execute('UPDATE joint_save SET throne_version=3 WHERE id=1')
        for f in (ts.read,ts.sealed_save):
            with self.assertRaisesRegex(ValueError,'지원하지 않는'):f(db,1,B,800)
    def test_host_db_with_a_changed_secret_is_refused(self):
        db=room();save(db,1,800);row=db.execute("SELECT payload FROM joint_throne_secret WHERE id=1 AND city='player1'").fetchone()[0]
        s=json.loads(row);s['paranoia']=99;db.execute("UPDATE joint_throne_secret SET payload=? WHERE id=1 AND city='player1'",(ts.encode(s),))
        with self.assertRaises(ValueError):ts.read(db,1,B,800)

class Separate(unittest.TestCase):
    def test_paranoia_is_not_the_original_favour(self):
        db=room();before=ts.current(db,B);te.begin_attempt(db,B,'player1',req(),100);after=ts.current(db,B)
        for c in CITIES:
            a=copy.deepcopy(after['players'][c]['secret']);b=copy.deepcopy(before['players'][c]['secret']);a.pop('attempts');b.pop('attempts')
            self.assertEqual(a,b)                                                       # paranoia, costs, throne expedition untouched
        self.assertNotIn('favor',json.dumps(after));self.assertNotIn('favour',json.dumps(after))
    def test_fixed_favour_is_reported_in_throne_mode_only(self):
        data=creator_presets.default_project(3)
        for s in data['slots']:s['governance']=dict(rank=0,salary_rank=-1,savings=0,favor=50,policy='fixed')
        self.assertFalse([f for f in sc.check(data)['findings'] if f['check']=='throne-favor'])
        data['schema']=5;data['rules']['mode']='race-for-throne';data['rules']['throne']=ts.defaults()
        data['empire']['rome']=dict(id='rome',x=768,y=496);sp.validate(data);before=copy.deepcopy(data)
        found=[f for f in sc.check(data)['findings'] if f['check']=='throne-favor']
        self.assertEqual(len(found),3);self.assertTrue(all(f['severity']=='block' for f in found));self.assertEqual(data,before)

class EventOrders(unittest.TestCase):
    """Every sequence (length 1..4) of: A tries r1, A resends r1, B tries r2, save, host crash (new host from the
    latest backup), A hands in, B hands in. Invariants after each step:
      I1 a request is applied at most once; I2 notice ids are unique and each known attempt has its notice;
      I3 nothing a non-host client can get contains a private field; I4 after a crash and both hand-ins the private
      values equal those of the restored save; I5 a pending player can make no attempt."""
    EVENTS=('tryA','resendA','tryB','save','crash','handA','handB')
    def run_sequence(self,seq):
        db=room();save(db,1,0);sid,tick=1,0;saved={1:copy.deepcopy(ts.current(db,B)['players'])};openings={c:te.own_opening(db,B,c,1) for c in CITIES}
        R={'tryA':('player1','1'*32),'resendA':('player1','1'*32),'tryB':('player2','2'*32)}
        for e in seq:
            tick+=100
            if e in R:
                city,r=R[e]
                if 'pending' in ts.current(db,B)['players'][city]:
                    with self.assertRaises(ValueError):te.begin_attempt(db,B,city,r,tick)            # I5
                else:te.begin_attempt(db,B,city,r,tick)
            elif e=='save':
                sid+=1;save(db,sid,tick);saved[sid]=copy.deepcopy(ts.current(db,B)['players'])
                openings={c:(te.own_opening(db,B,c,sid) or openings[c]) for c in CITIES}
            elif e=='crash':
                at=db.execute('SELECT ticks FROM joint_save WHERE id=?',(sid,)).fetchone()[0];db=restore(replica(db,sid,at),sid,at)
                sid+=1;save(db,sid,at)            # the new room's baseline save (migration.baseline); pending records keep their seal
                tick=max(tick,ts.current(db,B)['last_tick'])
            else:
                city='player1' if e=='handA' else 'player2';o=openings[city]
                try:te.hand_in(db,B,city,o['secret'],o['nonce'])
                except ValueError:pass                                                      # an opening of another save
            state=ts.current(db,B);known=[a for p in state['players'].values() if 'secret' in p for a in p['secret']['attempts']]
            reqs=[a['request'] for a in known];ids=[n['id'] for n in state['notices']]
            self.assertEqual(len(reqs),len(set(reqs)),seq);self.assertEqual(len(ids),len(set(ids)),seq)                 # I1, I2
            self.assertTrue(all(a['notice'] in ids for a in known),seq)
            text=scan_text(everything_public(db))
            for word in ('paranoia','failures','request','nonce','secret','attempts'):self.assertNotIn(word,text,seq)      # I3
        return db
    def test_all_orders(self):
        count=0
        for n in range(1,5):
            for seq in itertools.product(self.EVENTS,repeat=n):
                self.run_sequence(seq);count+=1
        self.assertEqual(count,7+49+343+2401)
    def test_restore_returns_the_saved_private_values(self):   # I4 on the orders that end with a crash and both hand-ins
        for pre in itertools.product(('tryA','tryB','save','resendA'),repeat=3):
            db=room();save(db,1,0);sid,tick=1,0
            for e in pre:
                tick+=100
                if e=='save':sid+=1;save(db,sid,tick)
                else:te.begin_attempt(db,B,'player1' if e!='tryB' else 'player2',('2' if e=='tryB' else '1')*32,tick)
            at=db.execute('SELECT ticks FROM joint_save WHERE id=?',(sid,)).fetchone()[0]
            expected=ts.read(db,sid,B,at)['players']
            new=restore(replica(db,sid,at),sid,at)
            for c in CITIES:o=te.own_opening(db,B,c,sid);te.hand_in(new,B,c,o['secret'],o['nonce'])
            self.assertEqual(ts.current(new,B)['players'],expected,pre)

if __name__=='__main__':unittest.main()
