import sys,sqlite3,unittest,copy,uuid
from pathlib import Path
W=Path(__file__).resolve().parent;sys.path.insert(0,str(W.parent/'Augustus'))
import city_trade_routes as routes,transport_snapshot as checkpoints,live_trade
import start_gate_base as baseline   # was test_start_gate56 (test-24 only), 2026-11-16

def database():
 db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row;live_trade.initialize(db);return db
class RouteTests(unittest.TestCase):
 def setUp(self):self.db=database();self.cities=['p1','p2','p3','p4']
 def tearDown(self):self.db.close()
 def offer(self,a='p1',b='p2',key=None):return routes.request(self.db,self.cities,a,'route_offer',b,key or uuid.uuid4().hex)
 def accept(self,a='p2',b='p1',revision=1):return routes.request(self.db,self.cities,a,'route_accept',b,revision=revision)
 def test_duplicate_offer_accept(self):
  key=uuid.uuid4().hex;first=self.offer(key=key)
  for _ in range(30):self.assertEqual(first,self.offer(key=key))
  with self.assertRaises(ValueError):self.accept('p1','p2')
  self.accept()
  for _ in range(30):self.assertEqual(self.accept()['state'],'active')
  self.assertEqual(len(routes.snapshot(self.db)['links']),1)
 def test_reject_reoffer_stale_accept(self):
  self.offer();routes.request(self.db,self.cities,'p2','route_reject','p1',revision=1);self.offer('p2','p1')
  with self.assertRaises(ValueError):self.accept('p1','p2',1)
  self.accept('p1','p2',2)
 def test_post_contract_and_identity(self):
  with self.assertRaises(ValueError):routes.bind(self.db,self.cities,'p1','p2',50,10)
  self.offer();self.accept();routes.bind(self.db,self.cities,'p1','p2',50,10)
  with self.assertRaises(ValueError):routes.bind(self.db,self.cities,'p1','p2',51,11)
  routes.deactivate(self.db,'p1',50,9)
  with self.assertRaises(ValueError):routes.bind(self.db,self.cities,'p1','p2',51,11)
  routes.deactivate(self.db,'p1',50,10);routes.bind(self.db,self.cities,'p1','p2',51,11)
 def test_save_without_any_goods_orders(self):
  self.offer();self.accept();routes.bind(self.db,self.cities,'p1','p2',50,10)
  saved=checkpoints.current(self.db);self.assertEqual(saved['version'],10);checkpoints.validate(saved,self.cities)
  target=database()
  try:checkpoints.restore(target,saved,self.cities);self.assertEqual(saved,checkpoints.current(target))
  finally:target.close()
 def test_legacy_save_unchanged(self):
  old=checkpoints.current(self.db);self.assertNotEqual(old['version'],10);checkpoints.validate(old,self.cities)
  target=database()
  try:checkpoints.restore(target,old,self.cities);self.assertEqual(old,checkpoints.current(target));self.assertFalse(routes.snapshot(target)['links'])
  finally:target.close()
 def test_bad_snapshot(self):
  self.offer();self.accept();valid=routes.snapshot(self.db)
  for changes in [dict(a='p2',b='p1'),dict(proposer='p3'),dict(revision=True),dict(state='unknown'),dict(request='x'),dict(a=[]),dict(b=None)]:
   bad=copy.deepcopy(valid);bad['links'][0].update(changes)
   with self.assertRaises(ValueError):routes.validate(bad,self.cities)
  bad=copy.deepcopy(valid);bad['links']*=2
  with self.assertRaises(ValueError):routes.validate(bad,self.cities)
 def test_delayed_old_offer_cannot_reopen_rejected_route(self):
  key=uuid.uuid4().hex;self.offer(key=key)
  routes.request(self.db,self.cities,'p2','route_reject','p1',revision=1)
  self.offer();routes.request(self.db,self.cities,'p2','route_reject','p1',revision=2)
  before=routes.snapshot(self.db)
  self.offer(key=key);self.assertEqual(before,routes.snapshot(self.db))
 def test_catalog_atomic_and_matching_peer(self):
  self.offer();self.accept();self.offer('p1','p3');self.accept('p3','p1')
  routes.register(self.db,self.cities,'p1',[[50,10,2]])
  before=routes.snapshot(self.db)
  with self.assertRaises(ValueError):routes.register(self.db,self.cities,'p1',[[50,10,2],[51,11,2]])
  self.assertEqual(before,routes.snapshot(self.db))
  with self.assertRaises(ValueError):routes.require_posts(self.db,self.cities,'p1','p2',[50,10])
  routes.register(self.db,self.cities,'p2',[[60,20,1]])
  self.assertEqual(routes.require_posts(self.db,self.cities,'p1','p2',[50,10]),[[50,10],[60,20]])
  with self.assertRaises(ValueError):routes.require_posts(self.db,self.cities,'p1','p2',[50,9])
  routes.register(self.db,self.cities,'p2',[])
  with self.assertRaises(ValueError):routes.require_posts(self.db,self.cities,'p1','p2',[50,10])
 def test_four_city_pair_isolation(self):
  for a,b in [('p1','p2'),('p1','p3'),('p2','p4')]:self.offer(a,b);self.accept(b,a)
  self.assertEqual(len(routes.snapshot(self.db)['links']),3);self.assertFalse(routes.active(self.db,self.cities,'p3','p4'))
class AuthRoutes(baseline.StartGateTest):
 def call(self,c,op,**kw):
  if op=='lobby_ready' and kw.get('ready'):
   import room_options
   current=baseline.StartGateTest.call(self,c,'lobby_status')['room_options']
   if not current['initialized']:
    current=baseline.StartGateTest.call(self,c,'room_options_set',invite=self.invites[c],revision=current['revision'],values=current['values'])
   baseline.StartGateTest.call(self,c,'room_options_ack',invite=self.invites[c],revision=current['revision'])
  return baseline.StartGateTest.call(self,c,op,**kw)

 def test_authenticated_four_city_routes(self):
  for c in self.cities:self.ack(c)
  self.now=5;self.contact();self.call('p1','lobby_status')
  for a,b in [('p1','p2'),('p2','p3'),('p3','p4')]:
   self.now+=.4;row=self.call(a,'route_offer',peer=b,request_id=uuid.uuid4().hex)
   self.now+=.4;self.call(b,'route_accept',peer=a,revision=row['revision'])
  state=self.call('p1','route_status');self.assertEqual(len(state['links']),3)
  with self.assertRaises(ValueError):self.room.request(dict(self.base,city='p2',token=self.tokens['p3'],op='route_offer',peer='p4',request_id=uuid.uuid4().hex))
if __name__=='__main__':unittest.main()

