"""Player colours in the waiting room (user, 2026-11-13: a player picks its own colour after choosing a city; eight
pastel presets). The real lobby_chat colour code on a small stand-in of the room tables.
  * without a pick everyone has its joining order's colour, never two alike;
  * a pick is kept; a colour a seated player holds is refused; picking needs a city; not after the start;
  * a pick that takes another (unpicked) player's default moves that player to the next free colour."""
import sqlite3,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Augustus'))
import lobby_chat as L

class Room:started=False;roster_job=None;start_at=None

class Colors(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row;self.addCleanup(self.db.close)
        self.db.execute('CREATE TABLE lobby_invite(token TEXT PRIMARY KEY,city TEXT UNIQUE)');L.initialize(self.db)
        for i in range(8):self.db.execute('INSERT INTO lobby_invite VALUES(?,?)',(f'k{i}',f'player{i+1}' if i<4 else None))
        self.room=Room()
    def pick(self,key,color):return L.choose(self.room,self.db,key,dict(color=color))
    def test_defaults_follow_joining_order(self):
        self.assertEqual([L.color(self.db,f'k{i}') for i in range(8)],list(range(8)))
        self.assertEqual(L.color(self.db,'nobody'),-1)
    def test_seated_players_never_share_a_colour_however_many_invitations_exist(self):
        # user report 2026-11-13: two trade posts of the same colour in a game. People who join and leave (or rejoin)
        # leave invitations behind; with more than eight of them the ninth got the first one's colour again.
        self.db.execute('DELETE FROM lobby_invite')
        for i in range(20):self.db.execute('INSERT INTO lobby_invite VALUES(?,?)',(f'k{i}',None))
        seats={0:'player1',8:'player2',9:'player3',16:'player4',17:'player5',19:'player6'}
        for i,city in seats.items():self.db.execute('UPDATE lobby_invite SET city=? WHERE token=?',(city,f'k{i}'))
        got=L.colors(self.db);seated=[got[f'k{i}'] for i in seats]
        self.assertEqual(len(set(seated)),6);self.assertTrue(all(0<=c<8 for c in got.values()))
        self.assertEqual(got['k0'],0);self.assertEqual(got['k8'],1);self.assertEqual(got['k9'],2)   # joining order's colour, or the next free one (8%8=0 is taken)
        self.pick('k19',0+5)                                                  # a pick among them still works and keeps all six apart
        got=L.colors(self.db);self.assertEqual(got['k19'],5);self.assertEqual(len({got[f'k{i}'] for i in seats}),6)
        for extra in range(20,40):self.db.execute('INSERT INTO lobby_invite VALUES(?,?)',(f'k{extra}',None))   # more visitors change nothing for the seated
        again=L.colors(self.db);self.assertEqual({k:again[k] for k in (f'k{i}' for i in seats)},{k:got[k] for k in (f'k{i}' for i in seats)})
    def test_pick_is_kept_and_all_stay_different(self):
        self.pick('k0',6)
        got=L.colors(self.db);self.assertEqual(got['k0'],6);self.assertEqual(len(set(got.values())),8)
        self.assertEqual(got['k1'],1)                       # untouched players keep theirs
        self.assertNotEqual(got['k6'],6)                    # the unseated holder of 6 by default moved on
        self.pick('k0',6);self.assertEqual(L.color(self.db,'k0'),6)
    def test_colour_of_a_seated_player_is_refused(self):
        with self.assertRaises(ValueError) as e:self.pick('k0',1)       # player2's default
        self.assertEqual(str(e.exception),L.COLOR_TAKEN)
        self.pick('k1',5)
        with self.assertRaises(ValueError):self.pick('k0',5)
        self.pick('k0',1);self.assertEqual((L.color(self.db,'k0'),L.color(self.db,'k1')),(1,5))   # 1 is free now
    def test_needs_a_city_and_a_valid_colour(self):
        with self.assertRaises(ValueError):self.pick('k5',7)
        for bad in (-1,8,'3',None,True):
            with self.assertRaises(ValueError):self.pick('k0',bad)
    def test_not_after_the_start(self):
        for field,value in (('started',True),('start_at',12.5),('roster_job',object())):
            room=Room();setattr(room,field,value)
            with self.assertRaises(ValueError) as e:L.choose(room,self.db,'k0',dict(color=6))
            self.assertEqual(str(e.exception),L.COLOR_LOCKED)
    def test_old_room_record_without_the_table(self):
        self.db.execute('DROP TABLE lobby_color');self.assertEqual(L.color(self.db,'k2'),2)


# ---- the same through a real room (room server, TCP, game_bridge.Bridge and the files the game reads) ----
import test_throne_room_flow as F
from unittest.mock import patch
FREE=F.ROOT/'Augustus/scenarios/unified-sandbox/scenario.json'

@unittest.skipUnless(F.DATA and FREE.is_file() and F.native_library(1),'needs AUGUSTUS_C3_DATA and the real post_* C library: '+F._why)
class RoomColors(F.RoomFlow):
    def setUp(self):
        super().setUp()
        p=patch.object(F,'PROJECT',FREE);p.start();self.addCleanup(p.stop)
    def press(self,b,color):
        (b.root/'command.txt').write_text('color\n'+str(color),encoding='utf8')
        for _ in range(3):b.step()
    def lobby_map(self,b):
        lines=(b.root/'lobby-map.txt').read_text(encoding='utf8').splitlines();count=int(lines[1]);out={}
        for i in range(count):
            head=lines[2+i*4].split();cid=lines[5+i*4]
            if cid:out[cid]=(int(head[4]),lines[4+i*4])
        return out
    def test_pick_reaches_every_screen_file_and_is_locked_after_the_start(self):
        a=self.make_room('colors');names=['player1','player2','player3','player4']
        bridges={c:self.bridge(a,i,c) for i,c in enumerate(names)}
        for b in bridges.values():b.step()
        self.assertEqual([self.lobby_map(bridges['player1'])[c][0] for c in names],[0,1,2,3])
        self.press(bridges['player2'],6)
        for b in bridges.values():b.step()
        for viewer in bridges.values():self.assertEqual([self.lobby_map(viewer)[c][0] for c in names],[0,6,2,3])
        self.press(bridges['player3'],6)                                   # held by player2: refused, shown in Korean
        self.assertEqual(self.lobby_map(bridges['player1'])['player3'][0],2)
        self.assertIn('다른 플레이어가 쓰고 있는 색',(bridges['player3'].root/'lobby-error.txt').read_text(encoding='utf8'))
        self.start(a,bridges)
        for b in bridges.values():b.step()
        host=bridges['player1']
        self.assertEqual(host.route_player_colors,dict(player1=0,player2=6,player3=2,player4=3))
        with self.assertRaises(ValueError) as e:host.client.call('lobby_color',invite=host.config['invite'],color=5)
        self.assertEqual(str(e.exception),'게임 시작 준비 중이거나 시작한 뒤에는 색을 바꿀 수 없습니다.')
    def test_host_row_text_is_the_one_the_lobby_paints_ready(self):
        a=self.make_room('hostrow');bridges={c:self.bridge(a,i,c) for i,c in enumerate(['player1','player2'])}
        for b in bridges.values():b.step()
        rows=self.lobby_map(bridges['player2'])
        self.assertTrue(rows['player1'][1].split(' · ')[-1].startswith('방장'))   # multiplayer_lobby_map.inc: 방장 = ready colour
        self.assertTrue(rows['player2'][1].split(' · ')[-1].startswith('대기'))

for _name in [n for n in dir(F.RoomFlow) if n.startswith('test_')]:setattr(RoomColors,_name,None)

if __name__=='__main__':unittest.main()
