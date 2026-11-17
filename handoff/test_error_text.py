"""Notices name the cause (user 2026-11-13: an army dispatch bug once showed an unrelated message)."""
import sys,unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Augustus'))
import error_text,game_bridge

class Text(unittest.TestCase):
    def test_reason_hides_paths_and_stays_short(self):
        r=error_text.reason(r"[Errno 2] No such file: 'D:\Games\내 폴더\rooms\x\expedition.sqlite'")
        self.assertNotIn('Games',r);self.assertIn('<경로>',r)
        self.assertNotIn('home',error_text.reason('cannot open /home/player/runs/a.txt'))
        self.assertLessEqual(len(error_text.reason('x'*500)),90);self.assertNotIn('\n',error_text.reason('a\nb'))
    def test_where_names_type_and_line(self):
        try:{}['flag']
        except KeyError as e:w=error_text.where(e)
        self.assertTrue(w.startswith("KeyError: 'flag' (test_error_text.py "),w)
    def test_unknown_rejection_keeps_its_cause(self):
        m=game_bridge.Bridge.error_message('soldier count mismatch')
        self.assertIn('soldier count mismatch',m);self.assertIn('요청을 처리하지 못했습니다',m)
        self.assertEqual(game_bridge.Bridge.error_message('room closed'),'방장이 나가서 방이 종료되었습니다.')

class StepKeepsRunning(unittest.TestCase):
    def test_a_plain_bug_becomes_a_notice(self):
        import tempfile,shutil
        root=Path(tempfile.mkdtemp());self.addCleanup(shutil.rmtree,root,True)
        published=[]
        b=SimpleNamespace(root=root,client=SimpleNamespace(session='s',city='c'),failure_since=None,publish=published.append)
        def tick():raise KeyError('flag')
        b.tick=tick
        game_bridge.Bridge.step(b)                                  # must not raise
        self.assertTrue(b.notice_text.startswith("로컬 처리 오류: KeyError: 'flag' (test_error_text.py "),b.notice_text)
        self.assertIn('KeyError',(root/'local-last-error.log').read_text(encoding='utf-8'))

if __name__=='__main__':unittest.main()
