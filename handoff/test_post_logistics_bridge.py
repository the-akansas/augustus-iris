import sys,unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Augustus'))
from post_logistics_bridge import publish
from trade_board import cards
class LogisticsBridgeTest(unittest.TestCase):
 def test_private_sites_and_bounded_demand(self):
  written={}; b=SimpleNamespace(client=SimpleNamespace(city='a'),write_changed=lambda k,v:written.update({k:v}))
  a=dict(seller='a',buyer='b',resource=1,quantity=24,state='offered',transfer=0)
  data=dict(routes=dict(posts=[dict(city='a',peer='b',building=4,generation=7,active=1),dict(city='b',peer='a',building=8,generation=9,active=1)]),agreements=dict(agreements=[a,dict(a)]),rows=[])
  self.assertEqual(publish(b,data),{'b':(4,7)});self.assertEqual(written['post-demand.txt'],'4 7 1 32 0\n')
  data['agreements']['agreements']=[dict(a,state='paused'),dict(a,transfer=2)]
  data['rows']=[dict(id=17,sender='b',receiver='a',resource=1,quantity=5,state='collecting')]
  publish(b,data);self.assertEqual(written['post-demand.txt'],'')
  data['rows']=[dict(id=17,sender='a',receiver='b',resource=1,quantity=5,state='collecting')]
  publish(b,data);self.assertEqual(written['post-demand.txt'],'4 7 1 5 17\n')
  data['routes']['posts'][0]['active']=0
  publish(b,data);self.assertEqual(written['post-demand.txt'],'')
 def test_remote_unknown_is_not_zero_stock(self):
  a=dict(id=1,seller='b',buyer='a',resource=1,quantity=8,state='active',transfer=0,post=4,generation=7,repeat=0,money=80,cycle=0)
  self.assertEqual(cards('a',[],[a],{'a':{}})[0][2],'상대 준비 대기')
if __name__=='__main__':unittest.main()
