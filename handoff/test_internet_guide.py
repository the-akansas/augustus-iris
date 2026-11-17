"""인터넷으로 함께하기 (user 2026-11-17: "안내서로 처리"): every package says how to play with people on another
network, in each language of the edition (tools/make_release.py INTERNET_GUIDE)."""
import re,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT/'Augustus'))
import make_release as M

class Guide(unittest.TestCase):
    def test_every_language_of_a_package(self):
        self.assertEqual(set(M.INTERNET_GUIDE),{'ko',*M.README_CODES})
    def test_the_facts_it_states_are_the_games(self):
        import room_discovery,inspect
        self.assertIn('hall_port=48921',(ROOT/'Augustus'/'network_play.py').read_text(encoding='utf-8'))
        self.assertIn('server_port=48921',inspect.getsource(room_discovery.probe))
        for code,text in M.INTERNET_GUIDE.items():
            self.assertIn('48921',text,code);self.assertIn('Tailscale',text,code);self.assertIn('runtime\\python.exe',text,code)
            self.assertEqual(text.count('100.'),1,code)
            self.assertNotRegex(text,r'\d+\.\d+\.\d+\.\d+',code)   # no real address in a public text
    def test_screen_words_are_the_games_own(self):
        """The names of buttons and fields quoted in each language are what the game shows in that language."""
        catalogs={}
        for code in M.README_CODES:
            rows=(ROOT/'Augustus'/'i18n'/(code+'.tsv')).read_text(encoding='utf-8').splitlines()
            catalogs[code]=dict(r.split('\t',1) for r in rows if '\t' in r)
        for code,words in catalogs.items():
            for korean in ('방장 IP','사용할 네트워크'):
                self.assertIn(words[korean],M.INTERNET_GUIDE[code],(code,korean))
        for korean in ('방장 IP','사용할 네트워크','방 만들기','방 입장','랜 플레이'):self.assertIn(korean,M.INTERNET_GUIDE['ko'])

if __name__=='__main__':unittest.main()
