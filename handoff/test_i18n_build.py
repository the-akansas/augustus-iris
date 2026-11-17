"""tools/i18n_build.py: review sheet -> Augustus/i18n/<code>.tsv (multilingual work)."""
import csv,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import i18n_build

def sheet(folder,rows):
    p=folder/'review.csv'
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['id','area','kind','ko','en','ru','de','es','fr','args','places'])
        for r in rows:w.writerow(r)
    return p

class Build(unittest.TestCase):
    def test_catalog_lines_escapes_and_empty(self):
        with tempfile.TemporaryDirectory() as t:
            t=Path(t);p=sheet(t,[['a','game','plain','방 나가기','Leave room','Покинуть комнату','','','Quitter',' ',''],
                                  ['b','game','plain','첫 줄\n둘째 줄','First\nsecond','','','','','','']])
            report,total=i18n_build.build(p,t/'out')
            self.assertEqual(report['en'][0],3);self.assertEqual(report['de'][0],0)
            self.assertFalse((t/'out/de.tsv').exists())
            lines=(t/'out/en.tsv').read_text(encoding='utf-8').splitlines()[1:]
            self.assertEqual(lines,['방 나가기\tLeave room','첫 줄\tFirst','둘째 줄\tsecond'])
            self.assertIn('방 나가기\tQuitter',(t/'out/fr.tsv').read_text(encoding='utf-8'))

    def test_slots_checked(self):
        self.assertIsNone(i18n_build.check('%s님이 %d개를 보냈습니다.','{1} sent by {0}.'))
        self.assertIsNone(i18n_build.check('방 주소 {0}','Room {0}'))
        self.assertEqual(i18n_build.check('%d명','{0} {1} players'),'unknown slot {1}')
        self.assertEqual(i18n_build.check('%s님 %d개','{0} sent'),'missing slot {1}')
        self.assertEqual(i18n_build.check('완료 100%%','Done %d'),'printf in a plain text')
        self.assertIsNone(i18n_build.check('완료 100%%','Done 100%'))

    def test_bad_rows_left_out(self):
        with tempfile.TemporaryDirectory() as t:
            t=Path(t);p=sheet(t,[['a','game','format','%d명','{0} {1}','','','','','%d','']])
            report,_=i18n_build.build(p,t/'out')
            self.assertEqual(report['en'][0],0);self.assertEqual(len(report['en'][1]),1)

class Lines(unittest.TestCase):
    def test_multiline_becomes_one_pair_per_line_with_local_slots(self):
        got=i18n_build.pairs('%s\n소속: %s · %s','{0}\nFrom: {1} · {2}')
        self.assertEqual(got,[('소속: %s · %s','From: {0} · {1}')])
    def test_line_count_must_match(self):
        with self.assertRaises(ValueError):i18n_build.pairs('첫 줄\n둘째 줄','one line')

if __name__=='__main__':unittest.main()
