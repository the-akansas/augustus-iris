"""Military room rules added 2026-11-13 (user: handle the military list in one go). The real army_live.request with a
small stand-in room (clock, active cities); the cities' engines are played by the test (it answers each command the
way the engine's receipt would). Not covered here: the game's own soldier behaviour and screens (user screen check).
  * one player never has support and attack forces at the same city at once; at most two attack forces per city;
  * the host city can send a stationed support legion home; only the host, only support;
  * a host city that leaves: its visitors go home with the troops they arrived with; if it comes back, its copy is
    tidied and its answers no longer move the expedition; nothing is paid back twice;
  * a sender that leaves: its expeditions are called back; the last step waits for it;
  * saves from before the new column still load."""
import sqlite3,sys,unittest,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Augustus'))
import army_live as A
import army_seal
# The dispatch is sealed in play (army_seal.py); these rules keep the sealed code checked for when it comes back.
army_seal.SEALED=False

CITIES=['player1','player2','player3']
class Room:
    started=True
    def __init__(s):
        s.db=sqlite3.connect(':memory:');s.db.row_factory=sqlite3.Row;s.active=set(CITIES);s.progress={c:(0,0) for c in CITIES}
        class Co:scenario=dict(cities=CITIES)
        s.coordinator=Co()
    def active_cities(s,db):return sorted(s.active)
    def tick(s,n):s.progress={c:(v[0]+n,0) for c,v in s.progress.items()}
    def call(s,city,op,**r):return A.request(s,s.db,city,dict(op=op,**r))

def manifest(token,n=3):return f'EX2 {token} 5 7 13 80 1 0 0 0 0 {n}\n'+''.join(f'{i+1} {i+1} 0 10 10 0 0\n' for i in range(n))

class Rules(unittest.TestCase):
    def setUp(self):self.room=Room();self.addCleanup(self.room.db.close)
    def order(self,city,dest,role,form):
        return self.room.call(city,'army_order',action_id=uuid.uuid4().hex,destination=dest,role=role,formation=form,expected=dict(fort=7,unit=13,identities=[[1,1],[2,2],[3,3]]))['id']
    def answer(self,city,applied=True,payload=None):
        """The city's engine takes its next command and reports the receipt. Returns the step, or None."""
        c=self.room.call(city,'army_live_poll')['command']
        if not c:return None
        self.room.call(city,'army_live_report',command=c['id'],applied=applied,payload=payload if payload is not None else manifest(c['token']) if applied else '')
        return c['step']
    def state(self,xid):return dict(self.room.db.execute('SELECT * FROM army_live WHERE id=?',(xid,)).fetchone())
    def station(self,city,dest,role,form):
        xid=self.order(city,dest,role,form);self.assertEqual(self.answer(city),1)
        self.room.tick(1600);self.room.call(city,'army_overview');self.assertEqual(self.answer(dest),2)
        self.assertEqual(self.state(xid)['state'],'stationed');return xid

    def test_no_support_and_attack_at_the_same_city(self):
        self.order('player1','player2',1,1)
        with self.assertRaises(ValueError) as e:self.order('player1','player2',2,2)
        self.assertEqual(str(e.exception),A.ROLE_CONFLICT)
        self.order('player1','player3',2,2)                       # another city: fine
        self.order('player3','player2',2,1)                       # another player attacks the city I support: fine
        self.assertEqual(self.room.db.execute('SELECT count(*) FROM army_live').fetchone()[0],3)
    def test_conflict_ends_when_the_first_force_is_home(self):
        xid=self.station('player1','player2',1,1)
        self.room.call('player2','army_send_home',expedition=xid);self.assertEqual(self.answer('player2'),3)
        with self.assertRaises(ValueError):self.order('player1','player2',2,2)     # still on its way home
        self.room.tick(1600);self.room.call('player1','army_overview');self.assertEqual(self.answer('player1'),4)
        self.assertEqual(self.state(xid)['state'],'returned');self.order('player1','player2',2,2)
    def test_attack_that_left_the_host_map_goes_home(self):
        """User 2026-11-13: an attack force looted, retreated off the host's map, and stayed 'stationed' at home."""
        xid=self.station('player1','player2',2,1)
        self.room.call('player2','army_wiped',expedition=xid)              # the host city: it is gone from my map
        self.assertEqual(self.state(xid)['state'],'recalling')
        self.room.call('player2','army_wiped',expedition=xid)              # said again: nothing more happens
        self.assertEqual(self.room.db.execute("SELECT count(*) FROM army_live_command WHERE expedition=? AND step=3",(xid,)).fetchone()[0],1)
        self.assertEqual(self.answer('player2',payload=manifest(self.state(xid)['token'],2)),3)   # two came back alive
        self.room.tick(1600);self.room.call('player1','army_overview');self.assertEqual(self.answer('player1'),4)
        self.assertEqual(self.state(xid)['state'],'returned')
        with self.assertRaises(ValueError):self.room.call('player3','army_wiped',expedition=xid)   # only the host city
    def test_two_attack_forces_per_city(self):
        self.order('player1','player2',2,1);self.order('player1','player2',2,2)
        with self.assertRaises(ValueError) as e:self.order('player1','player2',2,3)
        self.assertEqual(str(e.exception),A.ATTACK_FULL)
        self.order('player1','player3',2,3);self.order('player3','player2',2,1)   # per sender and per city
    def test_messages_reach_the_player(self):
        import coordinator,inspect
        source=inspect.getsource(coordinator.Handler.refusal)
        for text in (A.ROLE_CONFLICT,A.ATTACK_FULL,A.SUPPORT_FULL):self.assertIn(text,source)
    def test_host_sends_support_home(self):
        xid=self.station('player1','player2',1,1)
        with self.assertRaises(ValueError):self.room.call('player3','army_send_home',expedition=xid)   # not the host city
        attack=self.station('player3','player2',2,1)
        with self.assertRaises(ValueError):self.room.call('player2','army_send_home',expedition=attack)   # attackers cannot be sent away
        self.room.call('player2','army_send_home',expedition=xid);self.room.call('player2','army_send_home',expedition=xid)   # twice: once
        self.assertEqual(self.room.db.execute("SELECT count(*) FROM army_live_command WHERE expedition=? AND step=3",(xid,)).fetchone()[0],1)
        self.assertEqual(self.answer('player2',payload=manifest(self.state(xid)['token'],2)),3)          # two survivors
        self.room.tick(1600);self.room.call('player1','army_overview')
        c=self.room.call('player1','army_live_poll')['command'];self.assertEqual((c['step'],c['payload'].splitlines()[0].split()[-1]),(4,'2'))
    def test_host_city_leaves_visitors_go_home(self):
        xid=self.station('player1','player2',1,1);going=self.order('player3','player2',1,1);self.assertEqual(self.answer('player3'),1)
        self.room.tick(400);self.room.active.discard('player2');self.room.call('player1','army_overview')
        a,b=self.state(xid),self.state(going)
        self.assertEqual((a['released'],a['state'],a['transit_step'],a['ticks_left']),(1,'travelling',4,1600))
        self.assertEqual((b['released'],b['state'],b['transit_step'],b['ticks_left']),(1,'travelling',4,400))   # turned round where it was
        self.assertTrue(self.room.call('player1','army_overview')[0]['released'])
        self.room.tick(1600);self.room.call('player1','army_overview')
        c=self.room.call('player1','army_live_poll')['command'];self.assertEqual((c['step'],c['payload']),(4,manifest(a['token'])))   # as they arrived
        self.room.call('player1','army_live_report',command=c['id'],applied=True,payload=c['payload'])
        self.assertEqual(self.state(xid)['state'],'returned')
        # the city comes back later: its copy is removed, and that answer changes nothing
        self.room.active.add('player2')
        self.assertEqual(self.answer('player2',payload=manifest(a['token'],1)),3)
        self.assertEqual(self.state(xid)['state'],'returned');self.assertIsNone(self.answer('player2'))
        self.assertEqual(self.room.db.execute("SELECT count(*) FROM army_live_command WHERE expedition=? AND step=4",(xid,)).fetchone()[0],1)
    def test_host_city_leaves_while_arriving(self):
        xid=self.order('player1','player2',1,1);self.answer('player1');self.room.tick(1600);self.room.call('player1','army_overview')
        self.assertEqual(self.state(xid)['state'],'arriving')
        self.room.active.discard('player2');self.room.call('player1','army_overview')
        self.assertEqual((self.state(xid)['released'],self.state(xid)['state']),(1,'travelling'))
        self.room.active.add('player2')                           # back: arrival then tidy-up, neither moves the expedition
        self.assertEqual(self.answer('player2'),2);self.assertEqual(self.answer('player2'),3)
        self.assertEqual(self.state(xid)['state'],'travelling')
    def test_sender_leaves_expeditions_are_called_back(self):
        xid=self.station('player1','player2',1,1);going=self.order('player1','player3',2,2);self.answer('player1')
        self.room.tick(600);self.room.active.discard('player1');self.room.call('player2','army_overview')
        self.assertEqual(self.state(xid)['cancel'],1);self.assertEqual(self.answer('player2'),3)      # recalled from the host city
        b=self.state(going);self.assertEqual((b['cancel'],b['transit_step'],b['ticks_left']),(1,4,600))
        self.room.tick(1600);self.room.call('player2','army_overview')
        self.assertEqual(self.state(xid)['state'],'returning')    # the last step waits for the sender
        self.room.call('player2','army_overview');self.assertEqual(self.room.db.execute("SELECT count(*) FROM army_live_command WHERE step=3").fetchone()[0],1)
        self.room.active.add('player1');self.assertEqual(self.answer('player1'),4);self.assertEqual(self.answer('player1'),4)
        self.assertEqual({self.state(xid)['state'],self.state(going)['state']},{'returned'})
    def test_old_saves_without_the_new_column_load(self):
        xid=self.station('player1','player2',1,1)
        army=[dict(r) for r in self.room.db.execute('SELECT * FROM army_live')];commands=[dict(r) for r in self.room.db.execute('SELECT * FROM army_live_command')]
        A.validate_snapshot(dict(version=8,army=army,commands=commands),CITIES)
        for row in army:del row['released']
        A.validate_snapshot(dict(version=8,army=army,commands=commands),CITIES)

class SeveralSupportLegions(Rules):
    """User, 2026-11-13: one city must be able to send at least two support legions. The dispatch window waits only
    while the order status is 'preparing'; a legion on the road reports 'moving' and the next one can be ordered."""
    def status(self,city):return self.room.call(city,'army_order_status')[0]['state']
    def test_second_legion_can_be_ordered_while_the_first_is_on_the_road(self):
        a=self.order('player1','player2',1,3)
        self.assertEqual(self.status('player1'),'preparing')          # its own game has not confirmed the departure
        self.assertEqual(self.answer('player1'),1)
        self.assertEqual((self.state(a)['state'],self.status('player1')),('travelling','moving'))
        b=self.order('player1','player2',1,4)                         # second legion, same destination, first still travelling
        self.assertEqual(self.answer('player1'),1)
        self.room.tick(1600);self.room.call('player2','army_overview')
        self.assertEqual(self.answer('player2'),2);self.assertEqual(self.answer('player2'),2)
        self.assertEqual({self.state(a)['state'],self.state(b)['state']},{'stationed'})
        self.assertEqual(self.status('player1'),'complete')
        rows=[r for r in self.room.call('player2','army_overview') if r['incoming']]
        self.assertEqual(sorted(r['formation'] for r in rows),[3,4])
        self.assertEqual(len({r['token'] for r in rows}),2)
    def test_same_legion_is_not_sent_twice_and_six_is_the_limit(self):
        self.order('player1','player2',1,3);self.answer('player1')
        with self.assertRaises(ValueError):self.order('player1','player2',1,3)
        for form in (4,5,6,7,8):self.order('player1','player2',1,form);self.answer('player1')
        with self.assertRaises(ValueError) as e:self.order('player3','player2',1,9)
        self.assertEqual(str(e.exception),A.SUPPORT_FULL)
    def test_called_back_on_the_road_is_moving_not_blocking(self):
        a=self.order('player1','player2',1,3);self.answer('player1')
        self.room.call('player1','army_order_cancel',action_id=a)
        self.assertEqual((self.state(a)['transit_step'],self.status('player1')),(4,'moving'))
        self.order('player1','player3',1,4)                           # another legion may leave meanwhile


if __name__=='__main__':unittest.main()
