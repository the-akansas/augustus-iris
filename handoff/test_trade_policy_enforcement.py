import sys,unittest,uuid,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'Augustus'),str(ROOT/'handoff')]
from test_purchase_negotiation import PurchaseTests
import live_trade,trade_agreements
class Enforcement(unittest.TestCase):
 def setUp(self):
  self.fixture=PurchaseTests();self.fixture.setUp();self.db=self.fixture.db;self.room=self.fixture.room
 def tearDown(self):self.fixture.tearDown()
 def block(self):self.room.coordinator.scenario['player_trade_blocked']=[['a','b']]
 def refuse(self,fn):
  before=list(self.db.iterdump())
  with self.assertRaisesRegex(ValueError,'허용되지 않습니다'):fn()
  self.assertEqual(before,list(self.db.iterdump()))
 def test_sale_and_goods_and_cash_gifts_both_directions(self):
  self.block()
  for sender,receiver in [('a','b'),('b','a')]:
   for kind,res,qty,money in [('sale',self.fixture.res,2,100),('gift',self.fixture.res,2,0),('gift',0,0,100)]:
    self.refuse(lambda:live_trade.request(self.room,self.db,sender,dict(op='live_offer',receiver=receiver,request_id=uuid.uuid4().hex,kind=kind,resource=res,quantity=qty,money=money)))
 def test_pending_accept_is_denied(self):
  a=self.fixture.offer();self.block()
  self.refuse(lambda:self.fixture.call('b','agreement_accept',id=a['id'],revision=0,post=[22,2],request_id=uuid.uuid4().hex))
 def test_paused_resume_is_denied(self):
  a=self.fixture.offer();self.db.execute("UPDATE trade_agreement SET state='paused' WHERE id=?",(a['id'],));self.db.commit();self.block()
  self.refuse(lambda:self.fixture.call('a','agreement_resume',id=a['id'],revision=0,request_id=uuid.uuid4().hex))
 def test_partial_accept_cannot_bypass_policy(self):
  a=self.fixture.offer(1);self.block()
  self.refuse(lambda:self.fixture.counter(a))
if __name__=='__main__':unittest.main(defaultTest='Enforcement',verbosity=2)
