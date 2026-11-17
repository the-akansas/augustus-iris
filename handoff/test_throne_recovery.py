"""Lost personal throne record (policy 2026-11-12): recover from this PC's own records, otherwise stay 'restoring'.

Real throne_client / throne_events / throne_state on real SQLite files laid out like the game's rooms folder:
  rooms/network-play-<old>/throne-own/<commit>.json   (an earlier game session on this PC)
  rooms/network-play-<old>/host-<x>/room.sqlite        (a room this PC hosted)
  rooms/network-play-<new>/bridge                      (the current session)
No GUI, no network.
"""
import sys,tempfile,sqlite3,unittest
from contextlib import closing
from types import SimpleNamespace
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if not (ROOT/'Augustus').is_dir() and __import__('os').environ.get('AUGUSTUS_TEST_COPY'):ROOT=Path(__import__('os').environ['AUGUSTUS_TEST_COPY'])   # tests run from outside a test copy
sys.path[:0]=[str(ROOT/'Augustus'),str(ROOT/'handoff')]
import throne_client as tc,throne_state as ts,throne_events as te
from test_throne_events import B,CITIES,room,replica,restore,req,set_secret

def write_db(memory,path):
    path.parent.mkdir(parents=True,exist_ok=True)
    memory.commit()
    with closing(sqlite3.connect(path)) as target:memory.backup(target)

class Client:
    def __init__(self,active,city='player1'):self.active=active;self.city=city;self.calls=[]
    def call(self,op,**kw):
        self.calls.append(op);d=self.active[0]
        if op=='throne_mine':return te.own(d,B,self.city)
        if op=='throne_opening':return dict(opening=te.own_opening(d,B,self.city,kw['id']))
        if op=='throne_opening_stored':return te.confirm_stored(d,B,self.city,kw['id'],kw['commit'])
        if op=='throne_hand_in':return te.hand_in(d,B,self.city,kw['secret'],kw['nonce'],tick=kw.get('tick'))
        raise AssertionError(op)

def session(rooms,name,active,city='player1'):
    root=rooms/('network-play-'+name)/'bridge';root.mkdir(parents=True)
    return SimpleNamespace(root=root,config={'session':name},client=Client(active,city),joined=True,write_changed=lambda *a:None)

class LostRecord(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.rooms=Path(self.tmp.name)/'rooms'
        self.host=room();te.begin_attempt(self.host,B,'player3',req(),100);set_secret(self.host,'player1',paranoia=7,failures=2)
        self.host.execute("INSERT INTO joint_save(id,ticks,state) VALUES(1,800,'complete')");ts.capture(self.host,1,B,800)
        self.commit=ts.sealed_save(self.host,1,B,800)['players']['player1']['sealed']['commit']
        self.new=[restore(replica(self.host,1,800),1,800)]           # a new host restored from a replica: all pending
    def status(self):return {'throne':te.public_status(self.new[0],B)}
    def test_found_in_an_earlier_session_folder(self):
        old=session(self.rooms,'old',[self.host]);tc.sync(old,{'throne':te.public_status(self.host,B)})
        self.assertTrue((self.rooms/'network-play-old/throne-own'/(self.commit+'.json')).exists())
        now=session(self.rooms,'now',self.new);tc.sync(now,self.status())     # game started again: new folder
        mine=te.own(self.new[0],B,'player1')
        self.assertFalse(mine['restoring']);self.assertEqual((mine['paranoia'],mine['failures']),(7,2))
        self.assertTrue((self.rooms/'network-play-now/throne-own'/(self.commit+'.json')).exists())   # kept here now
    def test_found_in_a_room_this_pc_hosted(self):
        write_db(self.host,self.rooms/'network-play-old/host-abc/room.sqlite')
        now=session(self.rooms,'now',self.new);tc.sync(now,self.status())
        mine=te.own(self.new[0],B,'player1')
        self.assertFalse(mine['restoring']);self.assertEqual(mine['paranoia'],7)
        # the old host DB holds every player's record: only this city's was used, nothing else was handed in
        self.assertTrue(te.own(self.new[0],B,'player2')['restoring']);self.assertTrue(te.own(self.new[0],B,'player3')['restoring'])
    def test_old_game_folder_rooms_are_searched_too(self):
        write_db(self.host,self.rooms/'game-1/room.sqlite')
        now=session(self.rooms,'now',self.new);tc.sync(now,self.status())
        self.assertFalse(te.own(self.new[0],B,'player1')['restoring'])
    def test_another_players_record_is_never_used(self):
        # player2's real opening, saved under player1's commitment name: the commitment binds the city, so no match
        other=te.own_opening(self.host,B,'player2',1);other['commit']=self.commit
        folder=self.rooms/'network-play-old/throne-own';folder.mkdir(parents=True)
        (folder/(self.commit+'.json')).write_text(__import__('json').dumps(other),encoding='utf8')
        now=session(self.rooms,'now',self.new);tc.sync(now,self.status())
        self.assertTrue(te.own(self.new[0],B,'player1')['restoring'])
    def test_nothing_found_keeps_the_secret_state_and_limits_only_throne_actions(self):
        now=session(self.rooms,'now',self.new);before=ts.current(self.new[0],B)['players']['player1']
        tc.sync(now,self.status());tc.sync(now,self.status())
        after=ts.current(self.new[0],B)['players']['player1']
        self.assertEqual(before,after)                                # sealed record kept: no reset, no new key
        self.assertFalse(after['eliminated']);self.assertEqual(after['stage'],before['stage'])
        self.assertTrue(te.own(self.new[0],B,'player1')['restoring'])
        self.assertIn('player1',te.public_status(self.new[0],B)['restoring'])   # shown, not hidden
        with self.assertRaises(ValueError):te.begin_attempt(self.new[0],B,'player1',req(),900)
        # the record turns up later (e.g. copied back by the user): the next session hands it in
        old=session(self.rooms,'old',[self.host]);tc.sync(old,{'throne':te.public_status(self.host,B)})
        later=session(self.rooms,'later',self.new);tc.sync(later,self.status())
        self.assertFalse(te.own(self.new[0],B,'player1')['restoring'])
    def test_altered_or_broken_record_is_refused(self):
        # this city's own opening, but with the secret changed (or the file damaged): it no longer matches the seal
        mine=te.own_opening(self.host,B,'player1',1);mine['commit']=self.commit;mine['secret']=dict(mine['secret'],paranoia=0)
        folder=self.rooms/'network-play-old/throne-own';folder.mkdir(parents=True)
        (folder/(self.commit+'.json')).write_text(__import__('json').dumps(mine),encoding='utf8')
        (self.rooms/'network-play-older/throne-own').mkdir(parents=True)
        (self.rooms/'network-play-older/throne-own'/(self.commit+'.json')).write_text('{broken',encoding='utf8')
        now=session(self.rooms,'now',self.new);tc.sync(now,self.status())
        self.assertTrue(te.own(self.new[0],B,'player1')['restoring'])
        self.assertFalse((self.rooms/'network-play-now/throne-own'/(self.commit+'.json')).exists())   # nothing kept
    def test_records_outside_the_search_scope_are_not_read(self):
        # a correct record, but in places the search does not cover: another folder name, a copied database
        good=te.own_opening(self.host,B,'player1',1);good['commit']=self.commit
        for folder in (self.rooms/'backup/throne-own',self.rooms/'network-play-old/elsewhere',self.rooms.parent/'throne-own'):
            folder.mkdir(parents=True);(folder/(self.commit+'.json')).write_text(__import__('json').dumps(good),encoding='utf8')
        write_db(self.host,self.rooms/'copied/room.sqlite');write_db(self.host,self.rooms/'network-play-old/room.sqlite')
        now=session(self.rooms,'now',self.new);tc.sync(now,self.status())
        self.assertTrue(te.own(self.new[0],B,'player1')['restoring'])
    def test_searched_once_per_record_per_session(self):
        now=session(self.rooms,'now',self.new);seen=[]
        original=tc.recover_opening
        tc.recover_opening=lambda *a:seen.append(a) or None
        try:
            for _ in range(5):tc.sync(now,self.status())
        finally:tc.recover_opening=original
        self.assertEqual(len(seen),1)

class WaitingAndDeadlines(unittest.TestCase):
    def test_retries_and_new_hosts_do_not_restart_the_pending_clock(self):
        host=room();te.begin_attempt(host,B,'player3',req(),100);set_secret(host,'player1',next_attempt_tick=5000);set_secret(host,'player2',next_attempt_tick=5000)
        host.execute("INSERT INTO joint_save(id,ticks,state) VALUES(1,800,'complete')");ts.capture(host,1,B,800)
        record=te.own_opening(host,B,'player1',1)
        a=restore(replica(host,1,800),1,800)                          # pending since 800
        # more saves while still pending, then another host change from the newer save
        r2=te.own_opening(host,B,'player2',1);te.hand_in(a,B,'player2',r2['secret'],r2['nonce'],tick=1000)
        te.begin_attempt(a,B,'player2',req(),1200)                    # others play on while player1 waits
        p2=ts.current(a,B)['players']['player2']['secret']['next_attempt_tick']
        a.execute("INSERT INTO joint_save(id,ticks,state) VALUES(2,1600,'complete')");ts.capture(a,2,B,1600)
        self.assertEqual(ts.sealed_save(a,2,B,1600)['players']['player1']['sealed']['since'],800)
        b=restore(replica(a,2,1600),2,1600)
        self.assertEqual(ts.current(b,B)['players']['player1']['pending']['since'],800)   # not restarted at 1600
        self.assertTrue(te.hand_in(b,B,'player1',record['secret'],record['nonce'],tick=2000)['restored'])
        self.assertEqual(ts.current(b,B)['players']['player1']['secret']['next_attempt_tick'],5000+(2000-800))
        # the same record sent again (reconnect, resend): no second shift
        self.assertFalse(te.hand_in(b,B,'player1',record['secret'],record['nonce'],tick=2400)['restored'])
        self.assertEqual(ts.current(b,B)['players']['player1']['secret']['next_attempt_tick'],5000+(2000-800))
        # player1's wait never moved another player's deadline
        r2b=te.own_opening(a,B,'player2',2);te.hand_in(b,B,'player2',r2b['secret'],r2b['nonce'],tick=2000)
        self.assertEqual(ts.current(b,B)['players']['player2']['secret']['next_attempt_tick'],p2+(2000-1600))   # its own wait only

if __name__=='__main__':unittest.main()
