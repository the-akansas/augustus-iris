import copy,json,sqlite3,sys,tempfile,unittest,uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Augustus'))
import live_trade,trade_agreements as agreements,city_trade_routes as routes,agreement_bridge,city_notices

class PurchaseTests(unittest.TestCase):
 def setUp(self):
  self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row;live_trade.initialize(self.db)
  self.room=SimpleNamespace(started=True,clock=lambda:10,active_cities=lambda db:['a','b'],coordinator=SimpleNamespace(scenario={'cities':['a','b']},post_protocol=1))
  row=routes.request(self.db,['a','b'],'a','route_offer','b',uuid.uuid4().hex)
  routes.request(self.db,['a','b'],'b','route_accept','a',revision=row['revision'])
  routes.register(self.db,['a','b'],'a',[[11,1,2]]);routes.register(self.db,['a','b'],'b',[[22,2,1]])
  self.db.executemany('INSERT INTO fleet_site VALUES(?,?,?,1)',[('a',11,1),('b',22,2)]);self.db.commit()
  self.res=next(iter(live_trade.RESOURCES.values()))
  agreements.report_stock(self.room,"b",[[self.res,1]],storage=True)
 def tearDown(self):self.db.close()
 def call(self,city,op,**args):return agreements.request(self.room,self.db,city,dict(op=op,**args))
 def offer(self,partial=0):
  self.original=dict(request_id=uuid.uuid4().hex,mode='buy',peer='b',resource=self.res,quantity=20,money=200,repeat=0,post=[11,1],allow_partial=partial)
  return self.call('a','agreement_offer',**self.original)
 def counter(self,a,qty=12,key=None):return self.call('b','agreement_counter',id=a['id'],revision=a['revision'],quantity=qty,post=[22,2],request_id=key or uuid.uuid4().hex)
 def test_buy_over_seller_stock_and_private_poll(self):
  a=self.offer();agreements.report_stock(self.room,'b',[[self.res,987]])
  with patch.object(agreements,'advance'):data=self.call('a','agreement_poll')
  self.assertEqual(data['stocks'],{'a':{}})  # inspect stock payload, not random request-id substrings
  self.assertEqual(a['quantity'],20)
  self.assertEqual(data['purchase_catalogs']['b'],[self.res])
 def test_purchase_catalog_is_pair_specific_and_persistent(self):
  other=next(r for r in live_trade.RESOURCES.values() if r!=self.res)
  self.db.execute("INSERT INTO live_transfer(sender,receiver,resource,state) VALUES('b','third',?,'finished')",(other,))
  self.db.execute("INSERT INTO live_transfer(sender,receiver,resource,state) VALUES('a','b',?,'rejected')",(other,))
  self.assertNotIn(other,agreements.purchase_catalog(self.db,self.room,'a','b'))
  agreements.report_stock(self.room,'b',[],storage=True)
  with self.assertRaises(ValueError):self.offer()
  self.db.execute("INSERT INTO live_transfer(sender,receiver,resource,state) VALUES('b','a',?,'finished')",(self.res,))
  self.assertEqual(agreements.purchase_catalog(self.db,self.room,'a','b'),[self.res])
  self.assertEqual(self.offer()['quantity'],20)
  self.room.trade_storage_stock={};self.assertEqual(agreements.purchase_catalog(self.db,self.room,'a','b'),[self.res])
 def test_post_only_and_stale_storage_do_not_unlock_purchase(self):
  self.room.trade_storage_stock={}
  agreements.report_stock(self.room,'b',[[self.res,987]])
  with self.assertRaises(ValueError):self.offer()
  agreements.report_stock(self.room,'b',[[self.res,1]],storage=True)
  self.room.clock=lambda:21
  with self.assertRaises(ValueError):self.offer()
 def test_counter_requires_buyer_confirmation(self):
  a=self.offer();b=self.counter(a);self.assertEqual((b['state'],b['proposer'],b['quantity'],b['money']),('offered','b',12,120))
  with self.assertRaises(ValueError):self.call('b','agreement_accept',id=b['id'],revision=1,post=[22,2])
  agreements.report_stock(self.room,'b',[[self.res,12]])
  c=self.call('a','agreement_accept',id=b['id'],revision=1,post=[11,1],request_id=uuid.uuid4().hex)
  self.assertEqual(c['state'],'active')
 def test_partial_permission_and_repeat_replay(self):
  a=self.offer(1);key=uuid.uuid4().hex;b=self.counter(a,key=key)
  self.assertEqual((b['state'],b['quantity'],b['money']),('active',12,120))
  for _ in range(30):self.assertEqual(self.counter(a,key=key),b)
  self.assertEqual(self.call('a','agreement_offer',**self.original),b)
  with self.assertRaises(ValueError):self.counter(a,qty=11,key=key)
 def test_stale_and_unauthorized_actions(self):
  a=self.offer();b=self.counter(a)
  for actor,op,args in [('b','agreement_accept',{}),('a','agreement_stop',{}),('b','agreement_counter',dict(quantity=8))]:
   with self.assertRaises(ValueError):self.call(actor,op,id=a['id'],revision=0,post=[22,2],**args)
  with self.assertRaises(ValueError):self.call('other','agreement_accept',id=b['id'],revision=1)
  # The proposer cannot answer its own counter; a third city cannot either.
  with self.assertRaises(ValueError):self.call('b','agreement_counter',id=b['id'],revision=1,quantity=8,post=[22,2])
  with self.assertRaises(ValueError):self.call('other','agreement_counter',id=b['id'],revision=1,quantity=8,post=[11,1])
 def test_quantity_bounds_and_no_money_rounding(self):
  a=self.offer(1)
  for qty in (0,-1,20,33,True,1.5):
   with self.assertRaises(ValueError):self.counter(a,qty)
  self.assertEqual(agreements.item(self.db,'a',a['id']),a)
  # More than offered is a new proposal for the buyer, never concluded at once.
  b=self.counter(a,21);self.assertEqual((b['state'],b['quantity'],b['money'],b['allow_partial']),('offered',21,210,0))
 def test_all_partial_quantities_conserve_unit_price(self):
  for qty in range(1,20):
   a=self.offer(1);b=self.counter(a,qty);self.assertEqual(b['money'],qty*10);self.assertEqual(b['state'],'active')
 def test_removed_post_does_not_accept(self):
  a=self.offer(1);self.db.execute("UPDATE city_trade_post SET active=0 WHERE city='b'");self.db.commit()
  with self.assertRaises(ValueError):self.counter(a)
  self.assertEqual(agreements.item(self.db,'a',a['id']),a)
 def test_accept_waits_for_post_workers_and_road(self):
  a=self.offer();self.db.execute("UPDATE fleet_site SET active=0 WHERE city='b'");self.db.commit()
  b=self.call('b','agreement_accept',id=a['id'],revision=0,post=[22,2],request_id=uuid.uuid4().hex)
  self.assertEqual((b['state'],b['post'],b['transfer']),('active',22,None))
 def test_counter_and_partial_accept_wait_for_post_workers(self):
  for partial in (0,1):
   a=self.offer(partial);self.db.execute("UPDATE fleet_site SET active=0 WHERE city='b'");self.db.commit()
   b=self.counter(a)
   self.assertEqual(b['state'],'active' if partial else 'offered')
   self.assertEqual(b['quantity'],12)
 def test_ready_report_drop_preserves_consent_but_blocks_departure(self):
  import army_orders,army_install,cash_live,joint_save
  a=self.offer();a=self.call('b','agreement_accept',id=a['id'],revision=0,post=[22,2])
  self.room.coordinator.post_protocol=0
  self.db.execute("UPDATE fleet_site SET active=0 WHERE city='b'");self.db.commit()
  with patch.object(joint_save,'pending',return_value=False),patch.object(army_orders,'busy',return_value=False),patch.object(army_install,'pending',return_value=False),patch.object(cash_live,'ready',return_value=True):
   for _ in range(3):agreements.advance(self.room,self.db)
   b=agreements.item(self.db,'a',a['id']);self.assertEqual(b['state'],'active');self.assertIsNone(b['transfer'])
   self.assertEqual(self.db.execute('SELECT count(*) FROM fleet_order').fetchone()[0],0)
   self.db.execute("UPDATE city_trade_post SET active=0 WHERE city='b'");self.db.commit()
   agreements.advance(self.room,self.db)
   self.assertEqual(agreements.item(self.db,'a',a['id'])['state'],'paused')
 def test_wrong_post_and_generation_are_rejected(self):
  a=self.offer()
  for post in ([11,1],[22,99],[0,0]):
   with self.assertRaises(ValueError):self.call('b','agreement_accept',id=a['id'],revision=0,post=post)
 def test_save_restore_and_legacy(self):
  a=self.counter(self.offer());rows=agreements.snapshot(self.db)
  transport={'version':1};agreements.validate(rows,['a','b'],transport)
  target=sqlite3.connect(':memory:');target.row_factory=sqlite3.Row
  agreements.restore(target,rows);self.assertEqual(agreements.snapshot(target),rows);target.close()
  legacy=[{k:a[k] for k in agreements.LEGACY_FIELDS}];agreements.validate(legacy,['a','b'],transport)
  bad=copy.deepcopy(rows);bad[0]['money']+=1
  with self.assertRaises(ValueError):agreements.validate(bad,['a','b'],transport)
 def test_bridge_drops_remote_stock_and_notifies_once(self):
  a=self.offer()
  with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as d:
   root=Path(d);b=SimpleNamespace(root=root,client=SimpleNamespace(city='b',session='test'),agreements=[a],write_changed=lambda n,t:(root/n).write_text(t,encoding='utf8'))
   for _ in range(3):agreement_bridge.publish(b,dict(stocks={'a':{self.res:987},'b':{self.res:12}}))
   self.assertEqual((root/'trade-peer-stock.txt').read_text(),f'self {self.res} 12\n')
   self.assertEqual(len(city_notices.state(b)['events']),1)
   self.assertEqual(city_notices.state(b)['events'][0][1],4)

class TermsTests(PurchaseTests):
 def terms(self,city,a,qty,money,post):return self.call(city,'agreement_counter',id=a['id'],revision=a['revision'],quantity=qty,money=money,post=post,request_id=uuid.uuid4().hex)
 def test_price_counter_needs_confirmation_even_with_partial(self):
  a=self.offer(1);b=self.terms('b',a,12,180,[22,2])
  self.assertEqual((b['state'],b['proposer'],b['quantity'],b['money'],b['allow_partial']),('offered','b',12,180,0))
  rows=agreements.snapshot(self.db);agreements.validate(rows,['a','b'],{'version':1})
 def test_back_and_forth_then_accept(self):
  a=self.offer();b=self.terms('b',a,16,240,[22,2]);c=self.terms('a',b,16,200,[11,1])
  self.assertEqual((c['proposer'],c['post'],c['generation'],c['money']),('a',22,2,200))
  with self.assertRaises(ValueError):self.terms('a',c,15,200,[11,1])
  agreements.report_stock(self.room,'b',[[self.res,16]])
  d=self.call('b','agreement_accept',id=c['id'],revision=c['revision'],post=[22,2],request_id=uuid.uuid4().hex)
  self.assertEqual((d['state'],d['quantity'],d['money']),('active',16,200))
  agreements.validate(agreements.snapshot(self.db),['a','b'],{'version':1})
 def test_unchanged_and_bad_price(self):
  a=self.offer()
  for money in (200,0,-5,1000001,True,2.5):
   with self.assertRaises(ValueError):self.terms('b',a,20,money,[22,2])
 def test_sale_offer_can_be_countered_by_buyer(self):
  agreements.report_stock(self.room,'a',[[self.res,30]],storage=True);agreements.report_stock(self.room,'a',[[self.res,30]])
  a=self.call('a','agreement_offer',request_id=uuid.uuid4().hex,mode='sell',peer='b',resource=self.res,quantity=10,money=150,repeat=0,post=[11,1],allow_partial=0)
  b=self.terms('b',a,10,100,[0,0]);self.assertEqual((b['proposer'],b['post'],b['money']),('b',11,100))
  c=self.call('a','agreement_accept',id=b['id'],revision=b['revision'],post=[11,1],request_id=uuid.uuid4().hex)
  self.assertEqual(c['state'],'active')


class DeadlineTests(PurchaseTests):
 def accepted(self):
  a=self.offer();return self.call('b','agreement_accept',id=a['id'],revision=0,post=[22,2],request_id=uuid.uuid4().hex)
 def run_at(self,tick,stock=0):
  import army_orders,army_install,cash_live,joint_save
  self.room.progress={'a':(tick,0),'b':(tick,0)};agreements.report_stock(self.room,'b',[[self.res,stock]])
  with patch.object(joint_save,'pending',return_value=False),patch.object(army_orders,'busy',return_value=False),patch.object(army_install,'pending',return_value=False),patch.object(cash_live,'ready',return_value=True):
   agreements.advance(self.room,self.db)
  return agreements.item(self.db,'a',1)
 def test_round_not_sent_in_three_months_expires(self):
  self.room.coordinator.post_protocol=0;self.accepted()
  self.assertEqual(self.run_at(1000)['due_tick'],1000+agreements.DUE_TICKS)
  self.assertEqual(self.run_at(1000+agreements.DUE_TICKS-1)['state'],'active')
  rows=agreements.snapshot(self.db);agreements.validate(rows,['a','b'],{'version':1})
  a=self.run_at(1000+agreements.DUE_TICKS)
  self.assertEqual((a['state'],a['expired'],a['transfer']),('stopped',1,None))
 def test_stale_stock_report_never_expires(self):
  self.room.coordinator.post_protocol=0;self.accepted();self.run_at(1000)
  self.room.clock=lambda:100 # the seller's stock report is old: no judgement
  import army_orders,army_install,cash_live,joint_save
  self.room.progress={'a':(9000,0),'b':(9000,0)}
  with patch.object(joint_save,'pending',return_value=False),patch.object(army_orders,'busy',return_value=False),patch.object(army_install,'pending',return_value=False),patch.object(cash_live,'ready',return_value=True):
   agreements.advance(self.room,self.db)
  self.assertEqual(agreements.item(self.db,'a',1)['state'],'active')
 def test_old_saves_without_deadline_fields_restore(self):
  a=self.accepted();rows=agreements.snapshot(self.db)
  old=[{k:v for k,v in r.items() if k not in ('due_tick','expired')} for r in rows];agreements.validate(old,['a','b'],{'version':1})
  target=sqlite3.connect(':memory:');target.row_factory=sqlite3.Row;agreements.restore(target,old)
  self.assertEqual(agreements.snapshot(target)[0]['due_tick'],0);target.close()

if __name__=='__main__':unittest.main()
