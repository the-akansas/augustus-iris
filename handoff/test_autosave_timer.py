"""Host recovery-save timer (user 2026-11-13: '제멋대로 되는 느낌'). The shipped module on a simulated clock:
  * every interval while nothing else saves;
  * counted again from any finished joint save (a trade save is not followed by another one at once);
  * a refused request is tried again after 10 s, not a whole interval later;
  * guests never ask; switched off means no saves."""
import sys,tempfile,shutil,unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Augustus'))
import autosave_policy as P

class Timer(unittest.TestCase):
    def setUp(self):
        self.root=Path(tempfile.mkdtemp());self.addCleanup(shutil.rmtree,self.root,True)
        P.set_interval(self.root,300,True)
    def run_for(self,minutes,refuse=(),others=(),role='1'):
        """others: seconds at which some other joint save finishes (trade, army, manual)."""
        asked=[];done=[0]
        b=SimpleNamespace(last_autosave=0)
        def call(op,**k):
            if any(a<=b.now<a+2 for a in refuse):raise ValueError('both engines required')
            asked.append(b.now);done[0]+=1
        b.client=SimpleNamespace(call=call)
        for s in range(minutes*60):
            b.now=s
            if s in others:done[0]+=1
            P.poll(b,self.root,role,'started',1000,None,now=s,complete=dict(id=done[0]) if done[0] else None)
        return asked
    def test_regular(self):
        asked=self.run_for(16);self.assertEqual(asked[0],300)
        self.assertTrue(all(300<=b-a<=302 for a,b in zip(asked,asked[1:])),asked)   # own save takes a moment to finish
    def test_other_save_restarts_the_count(self):
        asked=self.run_for(16,others=(290,));self.assertEqual(asked[0],590,asked)   # not 300 right after the trade save at 290
    def test_refused_is_retried_soon(self):
        asked=self.run_for(11,refuse=(300,));self.assertEqual(asked[0],310,asked)
    def test_guest_and_off(self):
        self.assertEqual(self.run_for(11,role='2'),[])
        P.set_interval(self.root,300,False)
        self.assertEqual(self.run_for(11),[])
    def test_own_save_finishing_counts_from_there(self):
        # the timer's own save finishing (id changes) also restarts the count: still about every 5 minutes
        asked=self.run_for(16)
        self.assertTrue(all(b-a>=300 for a,b in zip(asked,asked[1:])))

class Default(unittest.TestCase):
    def test_new_install_is_on_every_5_minutes_and_off_is_kept(self):
        root=Path(tempfile.mkdtemp());self.addCleanup(shutil.rmtree,root,True)
        self.assertEqual(P.read_preferences(root),(True,300))            # no settings file yet
        P.set_interval(root,600,False);self.assertEqual(P.read_preferences(root),(False,600))
        (root/'multiplayer-settings.json').write_text('{"other":1}');self.assertEqual(P.read_preferences(root),(True,300))

if __name__=='__main__':unittest.main()
