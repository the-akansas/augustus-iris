import sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Augustus'))
import command_feedback as feedback
class FeedbackTests(unittest.TestCase):
 def test_success_and_failure_are_structured_and_ordered(self):
  for error,expected in [(None,'1'),('길 연결 확인','-1')]:
   b=SimpleNamespace(root=Path('mailbox'));writes=[]
   feedback.begin(b,'trade\noffer a gift 15 5 0')
   with patch.object(feedback,'publish_text',side_effect=lambda p,t:writes.append((p.name,t))):feedback.finish(b,error)
   self.assertEqual(writes[0],('command-outcome.txt',expected));self.assertEqual(writes[1][0],'command-result.txt')
   self.assertEqual(writes[1][1].startswith('요청 실패:'),error is not None)
   self.assertIsNone(b.feedback_command)
 def test_counter_is_tracked(self):
  self.assertTrue(feedback.tracked('trade\ncontract_counter 1 2 3'))
if __name__=='__main__':unittest.main()
