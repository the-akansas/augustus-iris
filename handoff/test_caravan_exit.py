import sqlite3,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Augustus'))
import live_trade,player_fleet
from fleet_bridge import reports
class ExitTests(unittest.TestCase):
 def setUp(self):
  self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row;live_trade.initialize(self.db)
  player_fleet.register(self.db,'a',[[11,2,1]])
  for ident,state in [(1,'finished'),(2,'queued')]:
   self.db.execute('INSERT INTO live_transfer(id,request,sender,receiver,resource,quantity,money,kind,state) VALUES(?,?,?,?,?,?,?,?,?)',(ident,str(ident)*32,'a','b',11,5,50,'sale',state))
   self.db.execute('INSERT INTO goods_motion(id,route,accepted) VALUES(?,2,1)',(ident,))
   player_fleet.reserve(self.db,'a',ident,[11,2])
  self.db.execute('UPDATE fleet_order SET assigned=1 WHERE id=1');self.db.commit()
 def tearDown(self):self.db.close()
 def test_only_receiver_exit_releases_finished_order(self):
  player_fleet.advance(self.db);self.assertEqual(self.db.execute('SELECT assigned FROM fleet_order WHERE id=2').fetchone()[0],0)
  for city,proof in [('a',[11,5,2]),('c',[11,5,2]),('b',[11,4,2])]:
   with self.assertRaises(ValueError):player_fleet.receiver_exited(self.db,city,1,[11,2],proof)
  with self.assertRaises(ValueError):player_fleet.returned(self.db,'a',1,[11,2])
  for _ in range(30):player_fleet.receiver_exited(self.db,'b',1,[11,2],[11,5,2])
  # 24차: loading decisions run with the room (legacy path for cities without load reports).
  room=type('R',(),{})();room.coordinator=type('C',(),{'scenario':{'cities':['a','b']}})();room.post_load={}
  player_fleet.advance(self.db,room)
  self.assertEqual([tuple(r) for r in self.db.execute('SELECT assigned,home FROM fleet_order ORDER BY id')],[(1,1),(1,0)])
 def test_unsettled_cannot_release_and_save_preserves_gate(self):
  self.db.execute("UPDATE live_transfer SET state='travelling' WHERE id=1");self.db.commit()
  with self.assertRaises(ValueError):player_fleet.receiver_exited(self.db,'b',1,[11,2],[11,5,2])
  restored=sqlite3.connect(':memory:');restored.row_factory=sqlite3.Row;self.db.backup(restored)
  self.assertEqual(restored.execute('SELECT home FROM fleet_order WHERE id=1').fetchone()[0],0);restored.close()
 def test_report_routed_to_receiver_only(self):
  t=dict(id=1,sender='a',receiver='b',resource=11,quantity=5,state='finished',fleet=dict(home=0,building=11,generation=2))
  states={1:[1,10,0,11,5,2,0]}
  self.assertEqual(reports([t],states,'a'),[])
  self.assertEqual(reports([t],states,'b')[0]['op'],'live_receiver_exit')
  states[1][1]=11;self.assertEqual(reports([t],states,'b')[0]['op'],'live_receiver_exit_failed')
if __name__=='__main__':unittest.main()
