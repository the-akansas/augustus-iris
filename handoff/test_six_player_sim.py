"""28차: a short six-city run of normal play; nothing may break, and a city whose player left holds nothing back."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import sim_six_players as S
def tearDownModule():S.restore()   # the real room functions for the tests after this one
class SixPlayers(unittest.TestCase):
 def test_normal_play_then_one_player_leaves(self):
  s=S.Sim(7,leave=False)
  for _ in range(90):s.day()
  gone=s.active[2];s.active.remove(gone);s.progress.pop(gone,None)
  for _ in range(25):s.day()
  self.assertEqual(s.problems,[])
  waiting=s.rows("""SELECT t.id,t.state FROM live_transfer t LEFT JOIN fleet_order f ON f.id=t.id
   WHERE (t.sender=? OR t.receiver=?) AND t.state NOT IN ('finished','rejected') AND COALESCE(f.assigned,0)=0""",gone,gone)
  self.assertEqual(waiting,[])
  for a in s.rows("SELECT * FROM trade_agreement WHERE state IN ('offered','active','paused') AND (seller=? OR buyer=?)",gone,gone):
   t=s.db.execute('SELECT state FROM live_transfer WHERE id=?',(a['transfer'],)).fetchone() if a['transfer'] else None
   self.assertTrue(t and t[0] not in ('finished','rejected'),a) # only a round already on its way may keep its contract open
  self.assertTrue(s.log['정산']>50)
if __name__=='__main__':unittest.main()
