"""Army dispatch sealed (user 2026-11-13 23:32): the room refuses every support/attack order, both paths; the
room closes what an older room still had open and the game releases its side when a save is loaded (2026-11-14). The game side hides the button (src/multiplayer/army_seal.h)."""
import re,sqlite3,sys,unittest,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'Augustus'))
import army_seal,army_live

class Room:
    started=True
    def __init__(s):
        s.db=sqlite3.connect(':memory:');s.db.row_factory=sqlite3.Row;s.progress={'player1':(0,0),'player2':(0,0)}
        class Co:scenario=dict(cities=['player1','player2'])
        s.coordinator=Co()
    def active_cities(s,db):return ['player1','player2']

class Seal(unittest.TestCase):
    def test_switch_is_on_in_both_halves(self):
        self.assertRegex((ROOT/'Augustus/army_seal.py').read_text(encoding='utf-8'),r'\nSEALED=True')
        self.assertRegex((ROOT/'src/multiplayer/army_seal.h').read_text(encoding='utf-8'),r'#define MP_ARMY_DISPATCH_SEALED 1')
    def test_new_dispatch_refused(self):
        room=Room();self.addCleanup(room.db.close);old=army_seal.SEALED;army_seal.SEALED=True;self.addCleanup(setattr,army_seal,'SEALED',old)
        for role in (1,2):
            with self.assertRaises(ValueError) as e:
                army_live.request(room,room.db,'player1',dict(op='army_order',action_id=uuid.uuid4().hex,destination='player2',role=role,formation=3,expected=dict(fort=7,unit=13,identities=[[1,1]])))
            self.assertEqual(str(e.exception),army_seal.REASON)
        self.assertEqual(room.db.execute('SELECT count(*) FROM army_live').fetchone()[0],0)
    def test_open_expeditions_closed_and_nothing_to_apply(self):
        room=Room();self.addCleanup(room.db.close);old=army_seal.SEALED;army_seal.SEALED=True;self.addCleanup(setattr,army_seal,'SEALED',old)
        db=room.db;army_live.initialize(db)
        db.execute("INSERT INTO army_live(id,token,origin,destination,role,formation,state,manifest,action) VALUES('a',3,'player3','player1',1,3,'deferred','EX2 3','a')")
        db.execute("INSERT INTO army_live(id,token,origin,destination,role,formation,state,manifest,action) VALUES('b',5,'player4','player2',1,1,'returned','EX2 5','b')")
        db.execute("INSERT INTO army_live_command(id,expedition,city,step,payload,state) VALUES('c','a','player3',4,'EX2 3','pending')");db.commit()
        self.assertEqual(army_live.request(room,db,'player3',dict(op='army_live_poll')),dict(command=None))
        self.assertEqual(army_live.request(room,db,'player3',dict(op='army_overview')),[])
        self.assertEqual(army_live.request(room,db,'player3',dict(op='army_live_report',command='c',applied=True,payload='x')),dict(accepted=True))
        self.assertEqual([tuple(r) for r in db.execute('SELECT id,state,released FROM army_live ORDER BY id')],[('a','failed',1),('b','returned',0)])
        self.assertEqual(db.execute("SELECT state FROM army_live_command").fetchone()[0],'unapplied')
        for op in ('army_send_home','army_wiped','army_order_cancel'):
            with self.assertRaises(ValueError):army_live.request(room,db,'player1',dict(op=op,expedition='a',action_id='a'))
    def test_game_releases_leftovers_on_load(self):
        self.assertIn('mp_army_seal_release();',(ROOT/'src/game/file.c').read_text(encoding='utf-8'))
        self.assertIn('if(MP_ARMY_DISPATCH_SEALED)return;',(ROOT/'src/multiplayer/army_live.c').read_text(encoding='utf-8'))
        import json
        for target in json.loads((ROOT/'build/native-sources.json').read_text(encoding='utf-8'))['targets'].values():
            self.assertIn('src/multiplayer/army_seal.c',target['sources'])
    def test_planned_order_path_refused(self):
        src=(ROOT/'Augustus/army_orders.py').read_text(encoding='utf-8')
        self.assertIn('if exp is None and army_seal.SEALED:raise ValueError(army_seal.REASON)',src)

if __name__=='__main__':unittest.main()
