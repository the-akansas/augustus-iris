import unittest,sys,tempfile,struct
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Augustus'))
import cash_bridge
class CashScheduleTests(unittest.TestCase):
 def test_active_wakes_idle_and_preserves_single_exchange(self):
  with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as d:
   root=Path(d);scope='a'*64;root.joinpath('post-capability.bin').write_bytes(b'x'*16+scope.encode()+struct.pack('<I',0));root.joinpath('post-response.bin').write_bytes(b'reply')
   calls=[]
   def call(op,**kw):
    calls.append(op)
    return dict(roster=scope,slot=0,epoch='e',nonce='n',cities=['a','b']) if op=='cash_challenge' else dict(state='reconciled',resend=[])
   b=SimpleNamespace(root=root,client=SimpleNamespace(call=call),cash_next=100,fleet_rows=[],write_changed=lambda *args:None)
   with patch.object(cash_bridge.time,'monotonic',return_value=10),patch.object(cash_bridge.post_ipc,'request',return_value=b'packet'),patch.object(cash_bridge.post_ipc,'response',return_value=(0,b'proof')):
    cash_bridge.poll(b);self.assertEqual(calls,[])
    b.fleet_rows=[dict(cash_live=True,state='travelling')];cash_bridge.poll(b);self.assertEqual(calls,['cash_challenge'])
    packet=b.cash_exchange
    with patch.object(cash_bridge.post_ipc,'response',side_effect=ValueError):cash_bridge.poll(b)
    self.assertIs(b.cash_exchange,packet);self.assertEqual(calls,['cash_challenge'])
    cash_bridge.poll(b);self.assertEqual(calls,['cash_challenge','cash_report']);self.assertAlmostEqual(b.cash_next,10.1)
    cash_bridge.poll(b);self.assertEqual(len(calls),2)
 def test_offer_and_completed_do_not_enable_fast_poll(self):
  for state in ['offered','finished','rejected']:
   self.assertFalse(cash_bridge.active_settlement(SimpleNamespace(fleet_rows=[dict(cash_live=True,state=state)])))
if __name__=='__main__':unittest.main()
