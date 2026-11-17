"""Settings brought over from an earlier version the person picks (user 2026-11-13: new zip = settings and hotkeys
from scratch; pick the folder; joint saves stay behind). Real files in temporary folders, the module as shipped."""
import builtins,json,shutil,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Augustus'))
import previous_version as P

def package(parent,name,version):
    app=parent/name/'Augustus';app.mkdir(parents=True)
    (app/'release.json').write_text(json.dumps(dict(version=version,distribution='release')),encoding='utf-8')
    return app

def personal(app,tag):
    (app/'user-profile').mkdir();(app/'user-profile'/'augustus.ini').write_text('ini '+tag);(app/'user-profile'/'augustus-hotkeys.ini').write_text('keys '+tag)
    (app/'network-settings.json').write_text(json.dumps({'game_data':'C:/Games/Caesar3'}))
    (app/'network-preferences.json').write_text(json.dumps({'recent':['26.206.111.104'],'name':tag}))
    (app/'creator-projects').mkdir();(app/'creator-projects'/'mine.json').write_text('{"title":"'+tag+'"}')
    (app/'creator-workspace.json').write_text(json.dumps({'directory':str(app/'creator-projects'),'recent':[str(app/'creator-projects'/'mine.json'),'D:/elsewhere/x.json']}))
    (app/'rooms'/'network-play-1').mkdir(parents=True);(app/'rooms'/'network-play-1'/'joint.sav').write_bytes(b'save')

class Import(unittest.TestCase):
    def setUp(self):
        self.tmp=Path(tempfile.mkdtemp());self.addCleanup(shutil.rmtree,self.tmp,True)
        self.old=package(self.tmp/'D','Augustus-MP-261113-rc1','261113-rc1');personal(self.old,'old')
        self.new=package(self.tmp/'E','Augustus-MP-261120-rc2','261120-rc2')     # anywhere: the person picks the folder
    def test_picked_folder_brings_settings_not_saves(self):
        r=P.run(self.new,self.old.parent)                                    # the package folder, as a person picks it
        self.assertEqual(r['version'],'261113-rc1');self.assertIsNone(r['backup'])
        self.assertEqual((self.new/'user-profile'/'augustus-hotkeys.ini').read_text(),'keys old')
        for n in ('network-settings.json','network-preferences.json','creator-projects/mine.json'):self.assertTrue((self.new/n).is_file(),n)
        self.assertFalse((self.new/'rooms').exists())                       # joint saves stay behind (user decision)
        ws=json.loads((self.new/'creator-workspace.json').read_text())
        self.assertEqual(Path(ws['directory']),self.new/'creator-projects');self.assertEqual(ws['recent'][1],'D:/elsewhere/x.json')
        self.assertEqual((self.old/'user-profile'/'augustus.ini').read_text(),'ini old')   # the earlier folder is only read
        self.assertEqual(P.announcement(self.new),'이전 버전(261113-rc1)의 설정을 가져왔습니다.')
        self.assertIsNone(P.announcement(self.new))                          # once
    def test_existing_settings_are_kept_in_a_backup_and_scenarios_merged(self):
        (self.new/'user-profile').mkdir();(self.new/'user-profile'/'augustus.ini').write_text('changed here')
        (self.new/'creator-projects').mkdir();(self.new/'creator-projects'/'new-here.json').write_text('{}')
        (self.new/'creator-projects'/'mine.json').write_text('{"title":"newer"}')
        r=P.run(self.new,self.old)                                           # its Augustus folder works too
        self.assertEqual((self.new/'user-profile'/'augustus.ini').read_text(),'ini old')
        self.assertEqual((self.new/r['backup']/'user-profile'/'augustus.ini').read_text(),'changed here')
        self.assertTrue((self.new/'creator-projects'/'new-here.json').is_file())
        self.assertEqual((self.new/'creator-projects'/'mine.json').read_text(),'{"title":"newer"}')   # own scenarios never replaced
    def test_wrong_folders_change_nothing(self):
        with self.assertRaises(ValueError):P.run(self.new,self.tmp/'no-such-folder')
        with self.assertRaises(ValueError):P.run(self.new,self.new.parent)  # itself
        self.assertEqual(sorted(p.name for p in self.new.iterdir()),['release.json'])
    def test_the_file_asks_before_changing_anything(self):
        with patch.object(P,'HERE',self.new),patch.object(P,'pick_folder',lambda:str(self.old.parent)),patch.object(builtins,'input',lambda *_:'n'),patch('builtins.print'):
            self.assertEqual(P.main(['x']),1)
        self.assertEqual(sorted(p.name for p in self.new.iterdir()),['release.json'])
        with patch.object(P,'HERE',self.new),patch.object(P,'pick_folder',lambda:str(self.old.parent)),patch.object(builtins,'input',lambda *_:'Y'),patch('builtins.print'):
            self.assertEqual(P.main(['x']),0)
        self.assertTrue((self.new/'user-profile'/'augustus.ini').is_file())
    def test_no_dialog_falls_back_to_a_typed_path(self):
        answers=iter(['"'+str(self.old.parent)+'"','y'])
        with patch.object(P,'HERE',self.new),patch.object(P,'pick_folder',lambda:None),patch.object(builtins,'input',lambda *_:next(answers)),patch('builtins.print'):
            self.assertEqual(P.main(['x']),0)
        self.assertTrue((self.new/'network-settings.json').is_file())

class ReleaseRules(unittest.TestCase):
    def test_import_records_stay_out_of_the_package(self):
        sys.path.insert(0,str(ROOT/'tools'));import make_release as M
        self.assertTrue(M.left_out('previous-version.json',False))
        self.assertTrue(M.left_out('previous-version-backup-20261120-101010',True))
        self.assertTrue(M.left_out('user-profile.importing-ab12cd34',True))
        self.assertTrue(M.left_out('user-profile',True))
        self.assertTrue(M.left_out('diag_collect.py',False))    # the collector stays with the developer (user 2026-11-13)
        self.assertTrue(M.left_out('diag_relay.py',False))      # no test diagnostics in any release (user 2026-11-15)

if __name__=='__main__':unittest.main()
