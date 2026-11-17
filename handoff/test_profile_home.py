"""Personal files stay in Augustus/user-profile (user 2026-11-13: '처음 한번 사용자 경로 지정하고 이후에도 또 뜨거나 난이도 및
설정 초기화'). Real files in temporary folders with Korean names, the shipped modules."""
import json,os,shutil,stat,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Augustus'))
import persistent_profile as PP
import previous_version as PV

def game_folder(root,tag):
    g=root/'private-game-data'/'ed36e3f59fff315717176c06';g.mkdir(parents=True)
    (g/'c3.sg2').write_bytes(b'x')
    (g/'augustus.ini').write_text('has_set_user_directories=1\nui_language_dir=\n'+tag+'\n');(g/'c3.inf').write_bytes(b'D'*560)
    (g/'augustus-hotkeys.ini').write_text('keys '+tag);(g/'multiplayer-chat.ini').write_text('toast_seconds=30\n');(g/'내 도시.sav').write_bytes(b'save')
    for p in g.iterdir():p.chmod(stat.S_IREAD)            # a read-only original must still give a writable copy
    return g

class Adopt(unittest.TestCase):
    def setUp(self):
        self.tmp=Path(tempfile.mkdtemp())/'한글 폴더';self.tmp.mkdir()
        self.addCleanup(lambda:(os.system('chmod -R u+w "'+str(self.tmp.parent)+'"'),shutil.rmtree(self.tmp.parent,True)))
        self.app=self.tmp/'Augustus-MP'/'Augustus';self.app.mkdir(parents=True)
    def test_game_folder_settings_move_into_the_profile_once(self):
        g=game_folder(self.app,'old')
        p=PP.prepare_profile(self.app,g)
        self.assertEqual((p/'user_dir.txt').read_text(encoding='utf-8'),p.as_posix()+'/')
        for n in PP.PERSONAL:self.assertEqual((p/'config'/n).read_bytes(),(g/n).read_bytes(),n)
        self.assertTrue(os.access(p/'config'/'c3.inf',os.W_OK))
        self.assertEqual((p/'savegames'/'내 도시.sav').read_bytes(),b'save')
        self.assertTrue((g/'c3.inf').is_file())                                  # copied, not moved
        (p/'config'/'c3.inf').write_bytes(b'N'*560)                              # the person changes difficulty later
        PP.prepare_profile(self.app,g)
        self.assertEqual((p/'config'/'c3.inf').read_bytes(),b'N'*560)           # never replaced again
    def test_new_person_is_not_asked(self):
        p=PP.prepare_profile(self.app,None)
        self.assertIn('has_set_user_directories=1',(p/'config'/'augustus.ini').read_text())
    def test_a_folder_the_person_picked_is_kept(self):
        p=PP.prepare_profile(self.app,None);(p/'user_dir.txt').write_text('D:/내 저장')
        shutil.rmtree(p/'config');PP.prepare_profile(self.app,game_folder(self.app,'x'))
        self.assertEqual((p/'user_dir.txt').read_text(),'D:/내 저장');self.assertFalse((p/'config').exists())
        (p/'user_dir.txt').write_text('')                                        # the game folder, picked on purpose
        PP.prepare_profile(self.app,None);self.assertEqual((p/'user_dir.txt').read_text(),'')

class ImportFromRc1(unittest.TestCase):
    def setUp(self):
        self.tmp=Path(tempfile.mkdtemp());self.addCleanup(lambda:(os.system('chmod -R u+w "'+str(self.tmp)+'"'),shutil.rmtree(self.tmp,True)))
        def package(name,version):
            app=self.tmp/name/'Augustus';app.mkdir(parents=True)
            (app/'release.json').write_text(json.dumps(dict(version=version)));return app
        self.old=package('Augustus-MP-261113-rc1','261113-rc1');self.new=package('새 버전','261120-rc2')
    def test_settings_kept_in_the_game_folder_come_along(self):
        (self.old/'user-profile').mkdir();(self.old/'user-profile'/'profile-migration.json').write_text('{}')
        game_folder(self.old,'rc1')
        self.assertIn('user-profile',PV.available(self.old))
        r=PV.run(self.new,self.old.parent)
        self.assertIn('user-profile',r['copied'])
        cfg=self.new/'user-profile'/'config'
        self.assertIn('rc1',(cfg/'augustus.ini').read_text());self.assertEqual((cfg/'c3.inf').read_bytes(),b'D'*560)
        self.assertTrue((self.new/'user-profile'/'savegames'/'내 도시.sav').is_file())
    def test_profile_pointer_to_the_old_folder_is_dropped(self):
        p=PP.prepare_profile(self.old,game_folder(self.old,'rc2'))
        PV.run(self.new,self.old)
        self.assertFalse((self.new/'user-profile'/'user_dir.txt').exists())      # would keep using the old folder
        q=PP.prepare_profile(self.new,None)
        self.assertEqual((q/'user_dir.txt').read_text(encoding='utf-8'),q.as_posix()+'/')
        self.assertIn('rc2',(q/'config'/'augustus.ini').read_text())

if __name__=='__main__':unittest.main()
