"""The launchers are built from their sources (2026-11-16: Augustus.exe, Augustus-Network.exe, 멀티저장설정.exe and
observe_atomic.dll had shipped without source). build/build_launcher.py builds them on Windows; here the same sources
are compiled with Mono's C# compiler and MinGW when those are installed (skipped, not passed, when they are not).
Their texts are checked for other languages by test_i18n_editor.py (the files are in creator-src)."""
import re,shutil,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'creator-src'
sys.path.insert(0,str(ROOT/'tools'))

class Sources(unittest.TestCase):
    def test_no_developer_folder_and_same_options(self):
        text=(SRC/'NetworkLauncher.cs').read_text(encoding='utf-8')
        self.assertIsNone(re.search(r'[A-Za-z]:\\\\',text),'a drive path inside the launcher')
        self.assertIn('Path.Combine(Root,"runtime","python.exe")',text)
        # the options network_play.py, the game's menu and the test tools use
        for option in ('--adapter-probe','--scenario-picker','--dialog','--invite','--project','--multiplayer','--settings-probe','--settings-read-probe'):
            self.assertIn('"'+option+'"',text,option)
        for used in ('network-adapters.json','network-settings.json','network-last-error.log','network-adapter-error.log','AUGUSTUS_MP_OPEN_LOBBY','AUGUSTUS_MP_PROJECT'):
            self.assertIn(used,text,used)
        self.assertIn('multiplayer-settings.json',(SRC/'AutosaveSettings.cs').read_text(encoding='utf-8'))
        self.assertIn('{0,300,600,1200,1800}',(SRC/'AutosaveSettings.cs').read_text(encoding='utf-8'))   # autosave_policy.py's choices
    def test_release_knows_them(self):
        import make_release as R
        for exe,src in R.LAUNCHER_SOURCES.items():self.assertTrue((ROOT/src).is_file(),src)
        self.assertEqual(R.OTHER_EDITION_NAMES,{'멀티저장설정.exe':'Autosave-Settings.exe'})
        self.assertTrue((ROOT/'build/build_launcher.py').is_file())

@unittest.skipUnless(shutil.which('mcs'),'Mono C# compiler (mcs) not installed')
class CSharp(unittest.TestCase):
    def test_compiles(self):
        refs=['-r:System.Windows.Forms.dll','-r:System.Drawing.dll','-r:System.Web.Extensions.dll']
        with tempfile.TemporaryDirectory() as d:
            for out,main in (('Augustus.exe','NetworkLauncher.cs'),('Autosave.exe','AutosaveSettings.cs')):
                r=subprocess.run(['mcs','-nologo','-target:winexe','-platform:x64',*refs,'-out:'+str(Path(d)/out),str(SRC/main),str(SRC/'CreatorLang.cs')],capture_output=True,text=True)
                self.assertEqual(r.returncode,0,r.stdout+r.stderr)

@unittest.skipUnless(shutil.which('x86_64-w64-mingw32-gcc') and shutil.which('objdump'),'MinGW compiler not installed')
class Atomic(unittest.TestCase):
    def test_exports(self):
        with tempfile.TemporaryDirectory() as d:
            dll=Path(d)/'observe_atomic.dll'
            r=subprocess.run(['x86_64-w64-mingw32-gcc','-O2','-shared','-o',str(dll),str(SRC/'observe_atomic.c')],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)
            table=subprocess.run(['objdump','-p',str(dll)],capture_output=True,text=True).stdout
            self.assertIn('obs_exchange',table);self.assertIn('obs_compare',table)
            code=subprocess.run(['objdump','-d',str(dll)],capture_output=True,text=True).stdout
            self.assertRegex(code,r'<obs_exchange>:[\s\S]*?xchg')                    # InterlockedExchange
            self.assertRegex(code,r'<obs_compare>:[\s\S]*?mov\s+%r8d,%eax[\s\S]*?lock cmpxchg %edx,\(%rcx\)')   # comparand third

if __name__=='__main__':unittest.main()
