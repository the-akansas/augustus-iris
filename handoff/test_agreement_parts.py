"""24차: a contract round of 32 sacks travels as 16+16 and ends only when both parts are settled and home."""
import sqlite3,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Augustus'))
import live_trade,player_fleet,trade_agreements
class PartTests(unittest.TestCase):
 def setUp(self):
  self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row;live_trade.initialize(self.db);trade_agreements.initialize(self.db)
  for i,state in [(1,'finished'),(2,'travelling')]:
   self.db.execute('INSERT INTO live_transfer(id,request,sender,receiver,resource,quantity,money,kind,state) VALUES(?,?,?,?,?,?,?,?,?)',(i,str(i)*32,'a','b',1,16,160,'sale',state))
  self.db.execute('INSERT INTO fleet_order(id,city,building,generation,assigned,home,origin) VALUES(1,"a",11,2,1,1,0)')
  self.db.execute('INSERT INTO fleet_order(id,city,building,generation,assigned,home,origin) VALUES(2,"a",11,2,1,0,1)')
 def test_round_waits_for_remainder(self):
  a=dict(transfer=1)
  self.assertFalse(trade_agreements.settled(self.db,a))
  self.db.execute("UPDATE live_transfer SET state='finished' WHERE id=2")
  self.assertFalse(trade_agreements.settled(self.db,a))
  self.db.execute('UPDATE fleet_order SET home=1 WHERE id=2')
  self.assertTrue(trade_agreements.settled(self.db,a))
 def test_queue_gate_removed(self):
  src=(Path(trade_agreements.__file__)).read_text(encoding='utf8')
  self.assertNotIn("FROM fleet_order WHERE city=? AND building=? AND generation=? AND home=0",src)
if __name__=='__main__':unittest.main()
