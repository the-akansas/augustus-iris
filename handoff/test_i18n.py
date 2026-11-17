"""Multilingual display (user 2026-11-13: Korean · English · Russian · German). The C matcher the game uses
(core/mp_i18n.c) is compiled and run against a small catalog; the string inventory tool is run on this tree."""
import os,shutil,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

CATALOG='''# test catalog
공동 저장 중입니다.\tJoint save in progress.
선물: %d 데나리\tGift: {0} Dn
방장 버전: {0}\tHost version: {0}
{0}개 도시 진행 중 / 방장 목표 {1}%\tHost target {1}% / {0} cities running
요청을 처리하지 못했습니다(원인: {0}). 잠시 후 다시 시도해 주세요.\tRequest failed (cause: {0}). Please try again shortly.
탭\\\\t그대로\ttab kept
번역 없음\t
%s %d포대를 %d Dn에 %s고 합니다.\t{3}: {0}, {1} loads for {2} Dn.
사겠다\tThey want to buy
밀\tWheat
'''

class Matcher(unittest.TestCase):
    def test_catalog_lookup(self):
        cc=shutil.which('gcc') or shutil.which('clang')
        if not cc:self.skipTest('no C compiler')
        tmp=Path(tempfile.mkdtemp());self.addCleanup(shutil.rmtree,tmp,True)
        (tmp/'en.tsv').write_text(CATALOG,encoding='utf-8')
        exe=tmp/'probe'
        r=subprocess.run([cc,'-std=gnu99','-Wall','-Werror','-I',str(ROOT/'src'),str(ROOT/'handoff/i18n_probe.c'),str(ROOT/'src/core/mp_i18n.c'),'-o',str(exe)],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)
        r=subprocess.run([str(exe),str(tmp/'en.tsv')],capture_output=True,text=True)
        self.assertEqual(r.stdout.strip().splitlines()[-1],'OK',r.stdout)

class Inventory(unittest.TestCase):
    def test_lists_texts_with_slots(self):
        sys.path.insert(0,str(ROOT/'tools'));import i18n_extract as X
        tmp=Path(tempfile.mkdtemp());self.addCleanup(shutil.rmtree,tmp,True)
        (tmp/'Augustus').mkdir();(tmp/'src/window').mkdir(parents=True);(tmp/'creator-src').mkdir()
        (tmp/'Augustus/a.py').write_text('"""문서는 빼기"""\nx="고정 문구"\ny=f"{n}명 접속"\n# 주석 빼기\n',encoding='utf-8')
        (tmp/'src/window/b.c').write_text('/* 주석 */ draw("버튼"); snprintf(t,9,"%d개",n); log_info("로그 빼기",0,0);\n',encoding='utf-8')
        (tmp/'creator-src/c.cs').write_text('var s="제작기 문구"; // 주석\n',encoding='utf-8')
        got={e['text']:e['kind'] for e in X.collect(tmp)}
        self.assertEqual(got,{'고정 문구':'plain','{0}명 접속':'fstring','버튼':'plain','%d개':'format','제작기 문구':'plain'})

if __name__=='__main__':unittest.main()
