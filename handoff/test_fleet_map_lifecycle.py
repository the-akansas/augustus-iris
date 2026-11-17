import sys,tempfile,unittest,copy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Augustus'))
import fleet_map
class FleetMapTest(unittest.TestCase):
 def test_completed_caravan_never_reappears(self):
  with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as d:
   p=Path(d);(p/'empire-player-slots.txt').write_text('1\ta\tA\n2\tb\tB\n')
   written={};b=SimpleNamespace(root=p,write_changed=lambda k,v:written.update({k:v}))
   t=dict(id=8,sender='a',receiver='b',state='travelling',resource=11,quantity=5,fleet=dict(assigned=1,home=0,building=59))
   fleet_map.publish(b,[t]);self.assertEqual(written['empire-fleet.txt'].splitlines()[1].split()[8],'1')
   t['cargo_delivered']=True;fleet_map.publish(b,[t]);self.assertEqual(written['empire-fleet.txt'].splitlines()[1].split()[8],'2')
   # Unloaded: the goods icon is gone (resource 0, quantity 0) while the caravan leaves.
   head=written['empire-fleet.txt'].splitlines()[1].split();self.assertEqual((head[3],head[5]),('0','0'))
   t['state']='finished';t['fleet']['home']=1;original=copy.deepcopy(t)
   for sec in (0,29,30,31,60,120,300):
    with patch.object(fleet_map.time,'monotonic',return_value=sec):fleet_map.publish(b,[t])
    self.assertEqual(written['empire-fleet.txt'].splitlines()[0],'0')
   self.assertEqual(t,original)
 def test_returning_refund_and_hold(self):
  with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as d:
   p=Path(d);(p/'empire-player-slots.txt').write_text('1\ta\tA\n2\tb\tB\n')
   written={};b=SimpleNamespace(root=p,write_changed=lambda k,v:written.update({k:v}))
   t=dict(id=8,sender='a',receiver='b',state='returning',resource=11,quantity=5,fleet=dict(assigned=1,home=0,building=59))
   fleet_map.publish(b,[t]);self.assertEqual(written['empire-fleet.txt'].splitlines()[1].split()[8],'3')
   t['suspended']=True;fleet_map.publish(b,[t]);self.assertEqual(written['empire-fleet.txt'].splitlines()[1].split()[8],'4')
if __name__=='__main__':unittest.main()
