"""Race for the Throne: when a complete joint save may be used for a host change ('custody'), restore-pending players,
their personal deadlines, and fault injection around saving, storing, confirming and host loss.

Three different things, never mixed up here:
  file created   joint_save state 'complete' (public form, seals and the host's private table written together)
  usable for a host change   complete AND every player sealed fresh in it confirmed (after writing and reading back)
                             that its own opening is on its PC  (throne_state.custody / handover_save)
  every private record restored   a new host received each player's matching opening (no player 'restoring')
Values such as next_attempt_tick=1500 are TEST INPUTS, not game rules. The fault-injection walk is a bounded
exhaustive test of a small model, not a proof (no formal-verification tool is available here)."""
import copy,itertools,json,sqlite3,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/'Augustus'
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(Path(__file__).resolve().parent))
import throne_state as ts,throne_events as te
from test_throne_events import B,CITIES,new_db,room,replica,restore,set_secret,req

def save(db,sid,tick,present=None,state='complete'):
    db.execute("INSERT INTO joint_save(id,ticks,state) VALUES(?,?,?)",(sid,tick,state))
    if state=='complete':ts.capture(db,sid,B,tick,present=present)
def store_and_confirm(db,city,sid,files):
    """What throne_client does: fetch own opening, store it (here: a dict), then confirm."""
    o=te.own_opening(db,B,city,sid)
    if o is None:return None
    files.setdefault(city,{})[o['commit']]=o
    return te.confirm_stored(db,B,city,sid,o['commit'])
def hand_in_from(db,city,files,tick=None):
    own=te.own(db,B,city)
    if not own.get('restoring'):return 'known'
    o=files.get(city,{}).get(own['commit'])
    if not o:return 'missing'
    te.hand_in(db,B,city,o['secret'],o['nonce'],tick);return 'restored'

class Custody(unittest.TestCase):
    def test_complete_is_not_yet_usable_for_a_host_change(self):
        db=room();files={};save(db,1,800)
        for c in CITIES:store_and_confirm(db,c,1,files)
        self.assertEqual(ts.handover_save(db,B),1)
        te.begin_attempt(db,B,'player1',req(),900);save(db,2,1600)
        self.assertEqual((ts.custody(db,B,2)['ready'],ts.custody(db,B,2)['waiting']),(False,3))
        self.assertEqual(ts.handover_save(db,B),1)                                       # the previous usable save stays
        store_and_confirm(db,'player1',2,files);store_and_confirm(db,'player2',2,files)
        self.assertEqual(ts.handover_save(db,B),1)
        store_and_confirm(db,'player3',2,files);self.assertEqual(ts.handover_save(db,B),2)
    def test_wrong_late_and_repeated_confirmations(self):
        db=room();files={};save(db,1,800);save(db,2,1600)
        o1=te.own_opening(db,B,'player1',1)
        with self.assertRaises(ValueError):te.confirm_stored(db,B,'player1',2,o1['commit'])   # last save's confirmation
        with self.assertRaises(ValueError):te.confirm_stored(db,B,'player2',1,o1['commit'])   # someone else's commitment
        with self.assertRaises(ValueError):te.confirm_stored(db,B,'player1',3,o1['commit'])   # no such save
        te.confirm_stored(db,B,'player1',1,o1['commit']);te.confirm_stored(db,B,'player1',1,o1['commit'])   # repeat: same result
        self.assertEqual(ts.custody(db,B,2)['waiting'],3)                                # an old save's confirmation completes nothing new
    def test_unfinished_save_is_never_chosen(self):
        db=room();files={};save(db,1,800)
        for c in CITIES:store_and_confirm(db,c,1,files)
        save(db,2,1600,state='collecting')                                               # host lost while collecting
        self.assertEqual(ts.handover_save(db,B),1);self.assertFalse(ts.custody(db,B,2)['ready'])
    def test_absent_unchanged_player_keeps_its_confirmed_seal(self):
        db=room();files={};te.begin_attempt(db,B,'player1',req(),100);save(db,1,800)   # active: paranoia may differ from 0
        for c in CITIES:store_and_confirm(db,c,1,files)
        save(db,2,1600,present={'player1','player2'})
        s1=ts.sealed_save(db,1,B,800);s2=ts.sealed_save(db,2,B,1600)
        self.assertEqual(s2['players']['player3']['sealed'],s1['players']['player3']['sealed'])   # carried, not re-sealed
        self.assertNotEqual(s2['players']['player1']['sealed'],s1['players']['player1']['sealed'])
        for c in ('player1','player2'):store_and_confirm(db,c,2,files)
        self.assertEqual(ts.handover_save(db,B),2)                                       # no need to wait for the absent player
        set_secret(db,'player3',paranoia=33)                                             # TEST INPUT: its record changed meanwhile
        save(db,3,2400,present={'player1','player2'})
        for c in ('player1','player2'):store_and_confirm(db,c,3,files)
        self.assertEqual((ts.handover_save(db,B),ts.custody(db,B,3)['waiting']),(2,1))   # a new record must reach its owner first
    def test_successor_is_armed_only_with_a_usable_save(self):
        import migration
        db=room();migration.initialize(db);db.execute('CREATE TABLE lobby_invite(token TEXT,city TEXT)')
        db.executemany('INSERT INTO lobby_invite VALUES(?,?)',[('a','player1'),('b','player2'),('c','player3')])
        class Room:
            class coordinator:scenario=B
            def active_cities(self,db):return list(CITIES)
        files={};save(db,1,800)
        import recovery_group;recovery_group.plan=lambda room,db,city,private=True:dict(save_id=1)   # >2 players: plan not under test
        self.assertFalse(migration.acknowledge(Room(),db,'player2',1)['armed'])           # nobody confirmed yet
        for c in CITIES:store_and_confirm(db,c,1,files)
        self.assertTrue(migration.acknowledge(Room(),db,'player2',1)['armed'])
        save(db,2,1600);r=migration.acknowledge(Room(),db,'player2',2)
        self.assertEqual((r['armed'],r['waiting'],r['kept']),(False,'throne-custody',1))
        self.assertEqual(db.execute("SELECT save_id FROM succession WHERE city='player2'").fetchone()[0],1)

class Pending(unittest.TestCase):
    def setUp(self):
        self.db=room();self.files={}
        set_secret(self.db,'player1',next_attempt_tick=1500)                             # TEST INPUT: a personal deadline ahead
        te.begin_attempt(self.db,B,'player2',req(),100);save(self.db,1,800)
        for c in CITIES:store_and_confirm(self.db,c,1,self.files)
    def test_deadline_protected_once_for_the_pending_time(self):
        new=restore(replica(self.db,1,800),1,800)
        self.assertEqual(hand_in_from(new,'player1',self.files,2000),'restored')
        self.assertEqual(ts.current(new,B)['players']['player1']['secret']['next_attempt_tick'],1500+(2000-800))
        self.assertEqual(hand_in_from(new,'player1',self.files,9000),'known')          # reconnecting again adds nothing
        self.assertEqual(ts.current(new,B)['players']['player1']['secret']['next_attempt_tick'],2700)
    def test_simple_disconnect_is_not_pending_and_gets_no_extra_time(self):
        back=restore(self.db,1,800)                                                      # same host, own DB
        self.assertEqual(te.public_status(back,B)['restoring'],[]);self.assertEqual(ts.current(back,B)['players']['player1']['secret']['next_attempt_tick'],1500)
    def test_pending_survives_save_and_another_host_change_with_its_start(self):
        new=restore(replica(self.db,1,800),1,800)
        for c in ('player2','player3'):hand_in_from(new,c,self.files,900)
        save(new,2,1600,present={'player2','player3'})
        self.assertEqual(ts.custody(new,B,2)['pending'],['player1'])
        for c in ('player2','player3'):store_and_confirm(new,c,2,self.files)
        self.assertEqual(ts.handover_save(new,B),2)                                      # pending players do not block it
        later=restore(replica(new,2,1600),2,1600)
        self.assertEqual(ts.current(later,B)['players']['player1']['pending']['since'],800)   # pending began at the first restore
        self.assertEqual(hand_in_from(later,'player1',self.files,3000),'restored')
        self.assertEqual(ts.current(later,B)['players']['player1']['secret']['next_attempt_tick'],1500+(3000-800))
    def test_lost_file_stays_pending_with_a_reason(self):
        new=restore(replica(self.db,1,800),1,800);del self.files['player1']
        self.assertEqual(hand_in_from(new,'player1',self.files),'missing')
        self.assertTrue(te.own(new,B,'player1')['restoring']);self.assertEqual(te.public_status(new,B)['restoring'],CITIES)
        with self.assertRaises(ValueError):te.begin_attempt(new,B,'player1',req(),900)   # no throne move on a missing record
        self.assertTrue(te.own(new,B,'player1')['restoring'])   # the box shows it only in a game with the current rules (throne_client.box_file: state restoring)
    def test_host_and_a_player_lost_together(self):
        # the save players hold (#1) is the usable one; the newer #2 never got player1's confirmation
        te.begin_attempt(self.db,B,'player3',req(),900);save(self.db,2,1600)
        for c in ('player2','player3'):store_and_confirm(self.db,c,2,self.files)
        hs=ts.handover_save(self.db,B);self.assertEqual(hs,1)
        new=restore(replica(self.db,hs,800),hs,800)
        for c in ('player2','player3'):self.assertEqual(hand_in_from(new,c,self.files),'restored')
        self.assertEqual(te.public_status(new,B)['restoring'],['player1'])               # until it comes back with its file
        self.assertEqual(ts.current(new,B)['notices'],ts.read(self.db,1,B,800)['notices'])   # public and private both from #1
        self.assertEqual(hand_in_from(new,'player1',self.files),'restored')
        self.assertEqual(ts.current(new,B)['players'],ts.read(self.db,1,B,800)['players'] | {'player1':ts.current(new,B)['players']['player1']})

class ClientStorage(unittest.TestCase):
    def test_no_confirmation_without_a_stored_copy(self):
        import throne_client
        with tempfile.TemporaryDirectory() as d:
            db=room();save(db,1,800);o=te.own_opening(db,B,'player1',1)
            real=throne_client.find_opening
            throne_client.find_opening=lambda path,commit:None                        # the write did not survive the read-back
            try:self.assertFalse(throne_client.keep_opening(Path(d),'player1',o))
            finally:throne_client.find_opening=real
            bad=dict(o,nonce='0'*64);self.assertFalse(throne_client.keep_opening(Path(d),'player1',bad))   # not this save's
            self.assertFalse(throne_client.keep_opening(Path(d),'player2',o))         # not this player's
            self.assertTrue(throne_client.keep_opening(Path(d),'player1',o))
            self.assertEqual(json.loads((Path(d)/(o['commit']+'.json')).read_text(encoding='utf-8')),o)

class FaultInjection(unittest.TestCase):
    """Steps: tryA (player1 attempt), save (a complete joint save), fetchA/fetchB (opening received, not stored),
    storeA/storeB (written, read back, confirmed), crash (host lost: a successor restores from handover_save, then
    each player hands in what it holds). Checked after every step and after every crash:
      C1 handover_save only ever names a complete save whose fresh seals were all confirmed;
      C2 after a crash every player not pending in that save is restored, exactly to that save's values, public and
         private from the same save; nothing is filled with defaults;
      C3 a request is applied at most once; notice ids unique;
      C4 nothing a non-host client gets holds a private field."""
    STEPS=('tryA','save','fetchA','storeA','storeB','crash')
    def walk(self,seq,check=True):
        db=room();files={};fetched={};sid,tick=0,0
        save(db,1,0);sid=1
        for c in CITIES:store_and_confirm(db,c,1,files)                                  # a usable baseline (migration.baseline)
        for step in seq:
            tick+=100
            if step=='tryA':
                if 'pending' not in ts.current(db,B)['players']['player1']:te.begin_attempt(db,B,'player1','1'*32,tick)
            elif step=='save':sid+=1;save(db,sid,tick)
            elif step=='fetchA':fetched['player1']=te.own_opening(db,B,'player1',sid)  # received only: no confirmation
            elif step in ('storeA','storeB'):
                c='player1' if step=='storeA' else 'player2'
                if 'secret' in ts.current(db,B)['players'][c]:store_and_confirm(db,c,sid,files)
            elif step=='crash':
                hs=ts.handover_save(db,B)
                at=db.execute('SELECT ticks FROM joint_save WHERE id=?',(hs,)).fetchone()[0]
                expected=ts.read(db,hs,B,at);sealed=ts.sealed_save(db,hs,B,at)
                db=restore(replica(db,hs,at),hs,at);sid+=1;save(db,sid,at,present=set())   # new room's baseline save
                for c in CITIES:hand_in_from(db,c,files)
                if check:
                    state=ts.current(db,B)
                    for c in CITIES:
                        if 'since' in sealed['players'][c]['sealed']:continue
                        self.assertIn('secret',state['players'][c],(seq,c,'C2: confirmed player not restorable'))
                        self.assertEqual(state['players'][c]['secret'],expected['players'][c]['secret'],(seq,c))
                    self.assertEqual(state['notices'],expected['notices'],seq)
                for c in CITIES:
                    if 'secret' in ts.current(db,B)['players'][c]:store_and_confirm(db,c,sid,files)
            if check:
                hs=ts.handover_save(db,B)
                if hs:self.assertTrue(ts.custody(db,B,hs)['ready'],seq)                  # C1
                state=ts.current(db,B);known=[a['request'] for p in state['players'].values() if 'secret' in p for a in p['secret']['attempts']]
                self.assertEqual(len(known),len(set(known)),seq);ids=[n['id'] for n in state['notices']];self.assertEqual(len(ids),len(set(ids)),seq)
                if hs:
                    at=db.execute('SELECT ticks FROM joint_save WHERE id=?',(hs,)).fetchone()[0]
                    rep=ts.sealed_save(db,hs,B,at);rep.pop('spec');text=json.dumps([rep,te.public_status(db,B)])
                    for word in ('paranoia','failures','nonce','secret','attempts','request'):self.assertNotIn(word,text,seq)   # C4
        return db
    def test_all_orders(self):
        count=0
        for n in range(1,6):
            for seq in itertools.product(self.STEPS,repeat=n):self.walk(seq);count+=1
        self.assertEqual(count,sum(6**n for n in range(1,6)))
    def test_the_walk_catches_a_broken_custody_rule(self):
        """Deliberate fault: treat every complete save as usable. Some order must then break C2."""
        real=ts.custody
        ts.custody=lambda db,binding,sid:dict(ready=db.execute("SELECT 1 FROM joint_save WHERE id=? AND state='complete'",(sid,)).fetchone() is not None,waiting=0,pending=[])
        try:
            caught=0
            for n in range(1,5):
                for seq in itertools.product(self.STEPS,repeat=n):
                    try:self.walk(seq)
                    except AssertionError:caught+=1
            self.assertGreater(caught,0)
        finally:ts.custody=real

if __name__=='__main__':unittest.main()
