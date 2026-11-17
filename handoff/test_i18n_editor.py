"""No Korean left in the scenario editor in another language (user 2026-11-16: "한글이 남거나 다른 언어가 보이거나 하는건
지양"). tools/i18n_editor_check.py reads creator-src/*.cs the way the editor translates (whole text, line, template,
phrase) and lists what would stay Korean; this test fails when a new one appears. When it fails after an editor change:
add the listed text to i18n/review.csv (values as {0} {1} ...), translate it, run tools/i18n_build.py."""
import io,sys,unittest
from contextlib import redirect_stdout
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
# Korean on purpose: the editor's own self-test texts, the language's own name in the language list, a letter used
# only to measure a line's height.
KNOWN={'두 도시의 협력\\n함께 성장하세요. 한글과 줄바꿈 보존','모두에게\\n둘째 줄','한국어','가'}

@unittest.skipUnless((ROOT/'creator-src').is_dir() and (ROOT/'Augustus/i18n/en.tsv').is_file(),'editor source and catalogs needed')
class Editor(unittest.TestCase):
    def test_nothing_stays_korean(self):
        import i18n_editor_check
        for lang in ('en','ru','de','es','fr'):
            out=io.StringIO();old=sys.argv
            try:
                sys.argv=['i18n_editor_check.py','--lang',lang]
                with redirect_stdout(out):i18n_editor_check.main()
            finally:sys.argv=old
            left={l.split(' | ',1)[1] for l in out.getvalue().splitlines() if ' | ' in l}-KNOWN
            self.assertEqual(sorted(left),[],lang)

if __name__=='__main__':unittest.main()
