"""27차: a post that only lost its road keeps its orders; a caravan is not sent to a post it cannot reach."""
import sqlite3,sys,tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Augustus'))
import live_trade,player_fleet,city_trade_routes,city_notices,trade_partner_bridge
class Room:
 def __init__(self):
  self.coordinator=type('C',(),{'scenario':{'cities':['a','b']}})();self.post_load={};self.progress={}
class RoadTests(unittest.TestCase):
 def setUp(self):
  self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row;live_trade.initialize(self.db)
  city_trade_routes.initialize(self.db)
  self.db.execute("INSERT INTO city_trade_post VALUES('b','a',22,3,1)")
  player_fleet.register(self.db,'a',[[11,2,1]]);player_fleet.register(self.db,'b',[[22,3,1]]);self.room=Room()
  self.db.execute("INSERT INTO live_transfer(id,request,sender,receiver,resource,quantity,money,kind,state) VALUES(1,?,'a','b',1,5,0,'gift','queued')",('1'*32,))
  self.db.execute('INSERT INTO goods_motion(id,route,accepted) VALUES(1,2,1)');player_fleet.reserve(self.db,'a',1,[11,2]);self.db.commit()
 def tearDown(self):self.db.close()
 def at(self,tick):
  self.room.post_load={'a':(time.monotonic(),{(11,2):{1:(5,0)}})};self.room.progress={'a':(tick,)}
  player_fleet.schedule(self.room,self.db)
  return [r[0] for r in self.db.execute('SELECT id FROM fleet_order WHERE assigned=1')]
 def test_post_without_road_stays_listed(self):
  player_fleet.register(self.db,'a',[[11,2,0]])
  self.assertEqual(self.db.execute("SELECT active FROM fleet_site WHERE city='a'").fetchone()[0],0)
  player_fleet.register(self.db,'a',[])
  self.assertIsNone(self.db.execute("SELECT 1 FROM fleet_site WHERE city='a'").fetchone())
 def test_caravan_waits_for_the_receiving_post(self):
  player_fleet.register(self.db,'b',[[22,3,0]])
  self.assertIs(player_fleet.destination_ready(self.db,'a','b'),False)
  self.at(1000);self.assertEqual(self.at(5000),[])
  self.assertIs(player_fleet.decorate(self.db,dict(id=1,sender='a',receiver='b',resource=1,state='queued')).get('dest_ready'),False)
  player_fleet.register(self.db,'b',[[22,3,1]])
  self.at(5050);self.assertEqual(self.at(5200),[1])
 def test_unknown_receiving_post_does_not_hold(self):
  self.db.execute('DELETE FROM fleet_site WHERE city=?',('b',))
  self.assertIsNone(player_fleet.destination_ready(self.db,'a','b'))
  self.at(1000);self.assertEqual(self.at(1100),[1])
 def test_deal_text_says_whose_move(self):
  t=dict(id=1,sender='a',receiver='b',resource=1,quantity=5,money=0,state='queued',dest_ready=False)
  self.assertIn('상대 교역소',trade_partner_bridge.transfer_deal('a',t,None)[-1])
  self.assertIn('내 교역소',trade_partner_bridge.transfer_deal('b',t,None)[-1])
class NoticeTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent);self.root=Path(self.tmp.name)
  self.b=SimpleNamespace(root=self.root,client=SimpleNamespace(city='b'),write_changed=lambda n,t:(self.root/n).write_text(t,encoding='utf8'))
  self.data=dict(rows=[dict(id=1,sender='a',receiver='b',resource=1,quantity=5,state='queued')],agreements=dict(agreements=[]),
   routes=dict(posts=[dict(city='b',peer='a',building=22,generation=3,active=1)]))
 def tearDown(self):self.tmp.cleanup()
 def notices(self):return [e for e in city_notices.state(self.b)['events'] if e[1]==6]
 def test_cut_off_post_asks_for_a_road_until_connected(self):
  (self.root/'post-readiness.txt').write_text('22 3 0 2\n')
  for _ in range(3):city_notices.post_road(self.b,self.data)
  n=self.notices();self.assertEqual(len(n),1);self.assertIn('길',n[0][6]);self.assertEqual(n[0][3:5],[22,3])
  self.assertIn(n[0][0],city_notices.state(self.b)['pending'])
  (self.root/'post-blocked.txt').write_text('');city_notices.post_storage(self.b) # the post-full sweep leaves it alone
  self.assertEqual(len(self.notices()),1)
  (self.root/'post-readiness.txt').write_text('22 3 0 0\n');city_notices.post_road(self.b,self.data)
  self.assertEqual(self.notices(),[])
  (self.root/'post-readiness.txt').write_text('22 3 0 2\n');city_notices.post_road(self.b,self.data)
  self.assertEqual(len(self.notices()),1) # cut off again later: asked again
 def test_no_notice_without_a_deal(self):
  (self.root/'post-readiness.txt').write_text('22 3 0 2\n');self.data['rows']=[]
  city_notices.post_road(self.b,self.data);self.assertEqual(self.notices(),[])
 def test_failed_deal_tells_both_sides_why(self):
  import cash_live
  row=dict(id=7,sender='a',receiver='b',resource=1,quantity=5,money=500,state='rejected',error=cash_live.FAILED_TEXT['escrow'],fleet=dict(building=11,generation=2,assigned=1,home=0))
  for city in ('a','b'):
   root=self.root/city;root.mkdir()
   b=SimpleNamespace(root=root,client=SimpleNamespace(city=city),write_changed=lambda n,t,root=root:(root/n).write_text(t,encoding='utf8'))
   city_notices.trade(b,[]);city_notices.trade(b,[row])
   self.assertTrue(any('자금' in e[6] for e in city_notices.state(b)['events']),city)
 def test_left_player_cancellation_is_named(self):
  row=dict(id=8,sender='b',receiver='a',resource=1,quantity=5,money=0,state='rejected',error=live_trade.LEFT_TEXT)
  city_notices.trade(self.b,[]);city_notices.trade(self.b,[row])
  self.assertTrue(any('방을 나가' in e[6] for e in city_notices.state(self.b)['events']))
if __name__=='__main__':unittest.main()
