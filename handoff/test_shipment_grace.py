"""24차: a not-full caravan waits two game days after the last change, and while carts are on their way."""
import sqlite3,sys,time,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Augustus'))
import live_trade,player_fleet
class Room:
 def __init__(self):
  self.coordinator=type('C',(),{'scenario':{'cities':['a','b']}})();self.post_load={};self.progress={}
class GraceTests(unittest.TestCase):
 def setUp(self):
  self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row;live_trade.initialize(self.db)
  player_fleet.register(self.db,'a',[[11,2,1]]);self.room=Room();self.n=0
 def order(self,res,qty):
  self.n+=1;i=self.n
  self.db.execute('INSERT INTO live_transfer(id,request,sender,receiver,resource,quantity,money,kind,state) VALUES(?,?,?,?,?,?,?,?,?)',(i,str(i)*32,'a','b',res,qty,0,'gift','queued'))
  self.db.execute('INSERT INTO goods_motion(id,route,accepted) VALUES(?,2,1)',(i,));player_fleet.reserve(self.db,'a',i,[11,2]);self.db.commit()
 def at(self,tick,held,inbound=0):
  self.room.post_load={'a':(time.monotonic(),{(11,2):{r:(h,inbound if k==0 else 0) for k,(r,h) in enumerate(held.items())}})}
  self.room.progress={'a':(tick,)};player_fleet.schedule(self.room,self.db)
  return [r[0] for r in self.db.execute('SELECT id FROM fleet_order WHERE assigned=1')]
 def test_waits_two_days_then_leaves(self):
  self.order(1,5)
  self.assertEqual(self.at(1000,{1:5}),[])
  self.assertEqual(self.at(1099,{1:5}),[])
  self.assertEqual(self.at(1100,{1:5}),[1])
 def test_new_order_restarts_wait_and_joins(self):
  self.order(1,5);self.at(1000,{1:5})
  self.order(6,6);self.assertEqual(self.at(1080,{1:5,6:6}),[])
  self.assertEqual(self.at(1150,{1:5,6:6}),[])
  self.assertEqual(self.at(1180,{1:5,6:6}),[1,2])
 def test_inbound_cart_holds_caravan(self):
  self.order(1,5)
  self.assertEqual(self.at(1000,{1:5},inbound=3),[])
  self.assertEqual(self.at(1200,{1:5},inbound=3),[])
  self.assertEqual(self.at(1250,{1:5}),[])
  self.assertEqual(self.at(1350,{1:5}),[1])
 def test_full_leaves_at_once(self):
  self.order(6,6);self.order(15,10)
  self.assertEqual(self.at(1000,{6:6,15:10}),[1,2])
if __name__=='__main__':unittest.main()
