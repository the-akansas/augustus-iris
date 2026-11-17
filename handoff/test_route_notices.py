"""Contract notifications survive retries/restarts without altering contracts."""
import copy,json,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Augustus'))
import route_bridge,city_notices

class RouteNotices(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
  self.root=Path(self.tmp.name)
 def tearDown(self):self.tmp.cleanup()
 def bridge(self,city='player2'):
  folder=self.root/city;folder.mkdir(exist_ok=True)
  return SimpleNamespace(root=folder,client=SimpleNamespace(city=city,session='a'*32),city_names={'player1':'카푸아','player2':'타렌툼'},write_changed=lambda n,t:(folder/n).write_text(t,encoding='utf8'))
 def data(self,state='offered',revision=1):
  return {'links':[dict(a='player1',b='player2',proposer='player1',state=state,revision=revision)]}
 def publish(self,b,data):route_bridge.publish(b,data,['player1','player2','player3'])
 def test_offer_accept_retries_restart(self):
  b=self.bridge();data=self.data();original=copy.deepcopy(data)
  for _ in range(30):self.publish(b,data)
  self.assertEqual(data,original)
  events=city_notices.state(b)['events'];self.assertEqual(len(events),1)
  self.assertEqual(events[0][1:3],[3,1]);self.assertIn('카푸아',events[0][-1]);self.assertIn('제안',events[0][-1])
  b=self.bridge();self.publish(b,data);self.assertEqual(len(city_notices.state(b)['events']),1)
  self.publish(b,self.data('active'));self.publish(b,self.data('active'))
  # One line per partner: the answered offer is replaced by the acceptance (2026-11-11).
  self.assertEqual(len(city_notices.state(b)['events']),1)
  self.assertIn('수락',city_notices.state(b)['events'][-1][-1])
 def read(self,b,events):
  (b.root/'city-notice-read.txt').write_text('\n'.join(str(e[0]) for e in events))
 def test_read_pending_stays_then_resolved_disappears(self):
  b=self.bridge();self.publish(b,self.data());s=city_notices.state(b)
  old=list(s['events']);self.read(b,old);self.publish(b,self.data())
  self.assertEqual(s['events'],old)
  self.publish(b,self.data('active'))
  self.assertEqual(len(s['events']),1);self.assertIn('수락',s['events'][0][-1])
  # Accepted contract = build-post to-do: reading it does not remove it (2026-11-11).
  self.read(b,s['events']);self.publish(b,self.data('active'));self.assertEqual(len(s['events']),1)
  self.publish(b,dict(self.data('active'),posts=[dict(city='player2',peer='player1',building=9,generation=1,active=1)]));self.assertEqual(s['events'],[])
 def test_resolved_unread_retained_new_arrival_not_acknowledged(self):
  b=self.bridge();self.publish(b,self.data('active'));s=city_notices.state(b);old=list(s['events'])
  city_notices.add(s,'new',1,44,0,0,0,'새 도착')
  self.read(b,old);city_notices.publish(b,s)
  # The build-post to-do stays; the unread arrival is not acknowledged by it.
  self.assertEqual([e[2] for e in s['events']],[1,44])
  self.read(b,s['events']);city_notices.publish(b,s);self.assertEqual([e[2] for e in s['events']],[1])
  city_notices.add(s,'new',1,44,0,0,0,'새 도착');city_notices.publish(b,s);self.assertEqual([e[2] for e in s['events']],[1])
 def test_legacy_state_and_read_then_new_revision(self):
  b=self.bridge();self.publish(b,self.data());s=city_notices.state(b)
  legacy={k:s[k] for k in ('sequence','seen','events')}
  (b.root/'city-notice-state.json').write_text(json.dumps(legacy))
  b=self.bridge();s=city_notices.state(b);self.read(b,s['events']);self.publish(b,self.data(revision=2))
  self.assertEqual(len(s['events']),1);self.assertIn(s['events'][0][0],s['pending'])
 def test_sender_and_unrelated_city(self):
  b=self.bridge('player1');self.publish(b,self.data());self.assertFalse(city_notices.state(b)['events'])
  self.publish(b,self.data('active'));self.assertIn('타렌툼',city_notices.state(b)['events'][-1][-1])
  b=self.bridge('player3');self.publish(b,self.data('active'));self.assertFalse(city_notices.state(b)['events'])
 def test_peer_colors_follow_authoritative_color_not_slot_or_owner(self):
  b=self.bridge('player2');b.route_player_colors={'player1':3,'player2':0,'player3':6}
  self.publish(b,self.data('active'))
  self.assertEqual((b.root/'route-player-colors.txt').read_text(),'1 3\n2 0\n3 6\n')
  self.assertTrue((b.root/'route-state.txt').read_text().startswith('1 player1 1 1'))
  b.route_player_colors={'player1':True,'player2':9}
  self.publish(b,self.data('active'))
  self.assertEqual((b.root/'route-player-colors.txt').read_text(),'1 -1\n2 -1\n3 -1\n')
 def test_rejection_reoffer_and_existing_notices(self):
  b=self.bridge('player1');s=city_notices.state(b)
  city_notices.add(s,'trade:1',1,1,0,0,0,'물품 거래')
  self.publish(b,self.data('rejected'));self.assertEqual(len(s['events']),2)
  self.assertIn('거절',s['events'][-1][-1]);self.assertEqual(s['events'][0][-1],'물품 거래')
  b=self.bridge();self.publish(b,self.data());self.publish(b,self.data(revision=2))
  self.assertEqual(len(city_notices.state(b)['events']),1) # The re-offer replaces the old one.

if __name__=='__main__':unittest.main()
