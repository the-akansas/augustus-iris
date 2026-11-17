"""Automatic goal reports (objectives.poll_bridge): a 'wrong objective sample' rejection right after the start (the
host has not opened the check while a required city is still loading) is retried quietly after 2 s instead of showing
"요청을 처리하지 못했습니다" (user report 2026-11-13). Other rejections still reach the player. The bridge keeps the
exact rejection text in its own rejections.log."""
import json,sys,tempfile,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'Augustus'))
import objectives
from coordinator import sha

class Client:
    def __init__(self,answers):self.answers=list(answers);self.calls=0;self.city='player2';self.session='s'
    def call(self,op,**kw):
        self.calls+=1;a=self.answers.pop(0)
        if isinstance(a,Exception):raise a
        return a
class Bridge:
    def __init__(self,root,answers):
        self.root=Path(root);self.config=dict(session='s');self.client=Client(answers);self.city_names={};self.written={}
    def write_changed(self,name,text):self.written[name]=text
def ready(b,target=1200):
    request=sha(('s|player2|'+str(target)).encode())
    (b.root/'objective-stats.json').write_text(json.dumps(dict(ticks=target,request=request,stats={})),encoding='utf8')

class Retry(unittest.TestCase):
    def test_early_sample_is_retried_quietly(self):
        with tempfile.TemporaryDirectory() as t:
            b=Bridge(t,[ValueError('wrong objective sample')]);ready(b)
            objectives.poll_bridge(b,dict(objective_tick=1200),1200)                     # no exception reaches the player
            self.assertEqual(b.client.calls,1);self.assertGreater(b.objective_retry_at,time.monotonic())
            objectives.poll_bridge(b,dict(objective_tick=1200),1200)                     # within 2 s: not sent again
            self.assertEqual(b.client.calls,1)
            import network_diagnostics;self.assertTrue(network_diagnostics.flush(3))
            logs=''.join(p.read_text(encoding='utf8') for p in Path(t).rglob('*.jsonl'));self.assertIn('objective_sample_waiting',logs)
    def test_retry_after_the_wait_and_success_clears_it(self):
        with tempfile.TemporaryDirectory() as t:
            b=Bridge(t,[ValueError('wrong objective sample'),{}]);ready(b)
            objectives.poll_bridge(b,dict(objective_tick=1200),1200);b.objective_retry_at=0   # 2 s later
            try:objectives.poll_bridge(b,dict(objective_tick=1200),1200)
            except Exception:pass                                                       # publish() of an empty stand-in status
            self.assertEqual(b.client.calls,2);self.assertEqual(b.objective_retry_at,0)
            import network_diagnostics;network_diagnostics.flush(3)                     # the log thread is done before the folder goes
    def test_other_rejections_still_show(self):
        with tempfile.TemporaryDirectory() as t:
            b=Bridge(t,[ValueError('conflicting objective retry')]);ready(b)
            with self.assertRaises(ValueError):objectives.poll_bridge(b,dict(objective_tick=1200),1200)
    def test_the_host_sends_this_rejection_as_it_is(self):
        # the host turns every unlisted rejection into 'invalid_request'; this one must reach the bridge as it is,
        # or the quiet retry never applies (it did not, before this was added: the stand-in client above hid that)
        import coordinator
        h=coordinator.Handler.__new__(coordinator.Handler) if hasattr(coordinator,'Handler') else None
        refusal=next(v for v in vars(coordinator).values() if isinstance(v,type) and 'refusal' in vars(v)).refusal
        self.assertEqual(refusal(None,ValueError('wrong objective sample')),{'ok':False,'error':'wrong objective sample'})
        self.assertEqual(refusal(None,ValueError('something else'))['error'],'invalid_request')
    def test_bridge_keeps_the_rejection_text(self):
        src=(ROOT/'Augustus/game_bridge.py').read_text(encoding='utf8')
        block=src[src.index('  except ValueError as error:\n   from network_diagnostics import record,ident'):];block=block[:block.index('reason=')]
        self.assertIn("'rejections.log'",block);self.assertIn('self.error_message(str(error))',block)

if __name__=='__main__':unittest.main()
