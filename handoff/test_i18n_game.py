"""No Korean left in the game's own windows in another language (user 2026-11-16: the language check kept finding
something each time; this closes the gap for the C side). Every Korean text the game's C source draws
(tools/i18n_extract.py reads src/**/*.c, *.inc, *.h) must come out without Korean in all five catalogs, translated the
way the game does it (Augustus/ui_text.py: whole line, then templates). printf slots (%d, %s) are filled with a number.
Files that are in no release (test launcher tools) are not checked. When this fails after a change: add the text it
names to i18n/review.csv, translate it, run tools/i18n_build.py.
The other two sides: Python sentences in test_i18n_coverage.py, the scenario editor in test_i18n_editor.py."""
import re,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'Augustus')]
HANGUL=re.compile('[가-힣]')
PRINTF=re.compile(r'%[-+ #0]*\d*(?:\.\d+)?(?:hh|h|ll|l|z)?[diuxXsScfgeEp]')
# in no release: the test launcher's tools (tools/make_release.py TEST_ONLY)
SKIP_FILES={'multiplayer_testtools.inc','multiplayer_throne_test.inc'}
# Korean on purpose
KNOWN={'시스템: ':'the prefix the room puts before a system line: read, not drawn (the word itself is translated)',
       '못했':'a word looked for inside a status line, never drawn',
       '/관리자':'chat command typed by the administrator','/공지 %s':'chat command','/내보내기 %d':'chat command','/채팅지우기':'chat command',
       '/방닫기':'chat command','/시나리오내리기':'chat command','/로그아웃':'chat command'}

@unittest.skipUnless((ROOT/'src').is_dir() and (ROOT/'Augustus/i18n/en.tsv').is_file(),'game source and catalogs needed')
class Game(unittest.TestCase):
    def test_nothing_stays_korean(self):
        import i18n_extract,ui_text
        texts={}
        for e in i18n_extract.collect(ROOT):
            places=[p for p in e['places'] if p.startswith('src/') and p.split(':')[0].rsplit('/',1)[-1] not in SKIP_FILES]
            if places and e['text'] not in KNOWN and HANGUL.search(e['text']):texts[e['text']]=places[0]
        self.assertGreater(len(texts),500)
        for lang in ('en','ru','de','es','fr'):
            table=ui_text._load(lang,ROOT/'Augustus');left=[]
            for text,place in texts.items():
                sample=PRINTF.sub('7',text).replace('%%','%')
                empty=PRINTF.sub('7',re.sub(r'%[-+ #0]*\d*s','',text))   # a %s that may be empty ("%s%s교역소 #%d")
                for form in (sample,text,empty):
                    out='\n'.join((ui_text._line(l,table) or l) for l in form.split('\n'))
                    if not HANGUL.search(out):break
                else:left.append(f'{place}  {text}')
            self.assertEqual(left,[],lang)

if __name__=='__main__':unittest.main()
