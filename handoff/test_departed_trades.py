"""28차: trades under way with a city whose player left settle for the players who stay."""
import sqlite3,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Augustus'))
import live_trade,cash_live,post_recovery,save_provenance
from trade_post_ledger import Ledger
CITIES=['a','b','c']
class Room:
 def __init__(self,path):
  self.coordinator=type('C',(),{'scenario':{'cities':CITIES},'path':path})();self.started=True;self.active=list(CITIES);self.progress={}
 def active_cities(self,db):return list(self.active)
class Departed(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=str(Path(self.tmp.name)/'room.sqlite')
  self.db=sqlite3.connect(self.path);self.db.row_factory=sqlite3.Row
  live_trade.initialize(self.db);cash_live.initialize(self.db)
  self.db.execute('CREATE TABLE IF NOT EXISTS joint_save(id INTEGER PRIMARY KEY,request TEXT,ticks INTEGER,state TEXT,speed INTEGER)')
  import objectives;objectives.initialize(self.db);self.db.commit()
  self.room=Room(self.path);self.n=0
 def tearDown(self):self.db.close();self.tmp.cleanup()
 def ledger(self):return Ledger(self.path,CITIES,transport=True)
 def trade(self,sender,receiver,money,departed):
  """An accepted sale/gift of 5 sacks whose goods left the sender (escrow paid)."""
  self.n+=1;key=('%032x'%self.n)
  tid=self.db.execute("INSERT INTO live_transfer(request,sender,receiver,resource,quantity,money,kind,state) VALUES(?,?,?,?,?,?,?,'travelling')",(key,sender,receiver,1,5,money,'sale' if money else 'gift')).lastrowid
  self.db.execute('INSERT INTO cash_transfer VALUES(?,?)',(tid,key))
  self.db.execute('INSERT INTO goods_motion(id,route,accepted,departed) VALUES(?,2,1,?)',(tid,departed))
  self.db.execute('INSERT INTO fleet_order(id,city,building,generation,assigned,home) VALUES(?,?,11,2,1,0)',(tid,sender));self.db.commit()
  l=self.ledger()
  try:
   l.offer(sender,key,receiver,1,5,money);l.accept(receiver,key,CITIES)
   self.run_city(l,sender);self.run_city(l,receiver)   # export, escrow
   self.assertEqual(l._contract(sender,key)['phase'],'travel')
  finally:l.close()
  return tid,key
 def run_city(self,l,city):
  """The city's game applies every command waiting for it."""
  for c in l.commands(city,CITIES):l.ack(city,c['id'],c['digest'],True)
 def leave(self,city):self.room.active.remove(city)
 def settle(self,*playing):
  for _ in range(4):
   live_trade.settle_departed(self.room,self.db,set(CITIES)-set(self.room.active))
   l=self.ledger()
   try:
    for city in playing:self.run_city(l,city)
    cash_live.sync(self.db,l)
   finally:l.close()
 def state(self,tid):return dict(self.db.execute('SELECT * FROM live_transfer WHERE id=?',(tid,)).fetchone())
 def phase(self,key):
  l=self.ledger()
  try:return dict(l.db.execute('SELECT * FROM post_contract WHERE id=?',(key,)).fetchone())
  finally:l.close()
 def test_goods_to_a_city_that_left_come_back(self):
  tid,key=self.trade('a','b',50,1);self.leave('b');self.settle('a','c')
  c=self.phase(key);self.assertEqual(c['phase'],'cancelled');self.assertEqual(c['refunded_goods'],1)
  t=self.state(tid);self.assertEqual(t['state'],'rejected');self.assertEqual(t['error'],live_trade.LEFT_TEXT)
 def test_goods_from_a_city_that_left_still_arrive(self):
  tid,key=self.trade('b','a',50,1);self.leave('b');self.settle('a')
  self.assertEqual(self.phase(key)['phase'],'travel') # still on the road to a
  l=self.ledger()
  try:l.arrived('a',key);self.run_city(l,'a')
  finally:l.close()
  self.settle('a')
  c=self.phase(key);self.assertEqual(c['phase'],'complete');self.assertEqual(c['received'],1)
  self.assertEqual(self.state(tid)['state'],'finished')
 def test_goods_still_inside_a_city_that_left_release_the_buyer(self):
  tid,key=self.trade('b','a',50,0);self.leave('b');self.settle('a')
  c=self.phase(key);self.assertEqual(c['phase'],'cancelled');self.assertEqual(c['refunded_money'],1) # a has its money back
  self.assertEqual(self.state(tid)['state'],'rejected')
  self.assertEqual(self.db.execute('SELECT home FROM fleet_order WHERE id=?',(tid,)).fetchone()[0],1)
 def test_remaining_save_and_return_of_the_city(self):
  tid,key=self.trade('a','b',50,1);self.leave('b')
  room=self.room;self.db.execute('CREATE TABLE IF NOT EXISTS joint_trade_boundary(id INTEGER PRIMARY KEY,transfer_id INTEGER)')
  self.db.execute('CREATE TABLE IF NOT EXISTS joint_provenance(id INTEGER,city TEXT,ticks INTEGER,source_id INTEGER,mode TEXT)')
  self.db.execute('CREATE TABLE IF NOT EXISTS origin_provenance(city TEXT PRIMARY KEY,ticks INTEGER)')
  self.db.execute('CREATE TABLE IF NOT EXISTS city(id TEXT,save BLOB)');self.db.execute("INSERT INTO city VALUES('b',x'00')");self.db.commit()
  room.origin=0
  self.settle('a','c')
  l=self.ledger()
  try:self.assertEqual([],[dict(r) for r in l.db.execute("SELECT * FROM post_command WHERE state='pending'")])
  finally:l.close()
  self.assertEqual([p[0] for p in save_provenance.retained_parts(room,self.db,['a','c'])],['b']) # no longer refused
  # b comes back later from its older save: its book has no receipt of the escrow it paid.
  l=self.ledger()
  try:
   self.assertEqual(post_recovery.reconcile(l,'b',{},CITIES)['state'],'needs_city_recovery') # without forgiveness: held
   with l.db:l.db.execute('DELETE FROM post_recovery_hold')
   post_recovery.forgive(l.db,['b']);l.db.commit()
   self.assertEqual(post_recovery.reconcile(l,'b',{},CITIES)['state'],'reconciled')
  finally:l.close()
 def test_unsettled_step_of_the_city_that_left_still_blocks(self):
  tid,key=self.trade('a','b',50,1);self.leave('b')
  l=self.ledger()
  try:l.cancel('a',key);self.run_city(l,'a') # refund_money now waits for b
  finally:l.close()
  self.db.execute('CREATE TABLE IF NOT EXISTS joint_trade_boundary(id INTEGER PRIMARY KEY,transfer_id INTEGER)');self.db.commit()
  with self.assertRaises(ValueError):save_provenance.retained_parts(self.room,self.db,['a','c'])
if __name__=='__main__':unittest.main()
