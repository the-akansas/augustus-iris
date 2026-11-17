"""Resume list rows (start_catalog.save_choices): when it was saved comes first, to the second, so the narrow list
row never cuts it off (user 2026-11-13). The '[이어하기]' / '[이전 저장]' prefix stays: the game sorts rows by it."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Augustus'))
from start_catalog import save_choices
def entry(i,t,when,status='복원 시 해시 검증'):return dict(available=True,database='room.sqlite',sort_time=t,id=i,title='The Provincial Sextet',date='기원전 350년 1월',modified=when,status=status)

class Label(unittest.TestCase):
    def test_time_first(self):
        rows=[c['label'] for c in save_choices([entry(3,2,'2026-11-13 11:11:50'),entry(1,1,'2026-11-13 10:56:10','남은 도시 저장')],'x')]
        self.assertEqual(rows,['[이어하기] 11-13 11:11:50 · The Provincial Sextet · 기원전 350년 1월 #3',
                               '[이전 저장] 11-13 10:56:10 · The Provincial Sextet · 기원전 350년 1월 #1 · 남은 도시'])
    def test_unexpected_time_text_is_kept(self):
        self.assertTrue(save_choices([entry(1,1,'어제')],'x')[0]['label'].startswith('[이어하기] 어제 · '))

if __name__=='__main__':unittest.main()
