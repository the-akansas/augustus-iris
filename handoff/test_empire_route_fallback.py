"""Execute the actual empire fallback renderer against fixture engine state; no GUI.
Drawing calls are captured, not rasterized. Real network delivery has its own flow test.
"""
import os,sys,shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CC=os.environ.get('AUGUSTUS_CC') or shutil.which('gcc')
@unittest.skipUnless(CC,'C compiler needed')
class Fallback(unittest.TestCase):
    def test_actual_fallback_renderer_and_equal_timestamp_refresh(self):
        with tempfile.TemporaryDirectory() as d:
            exe=Path(d)/('probe.exe' if os.name=='nt' else 'probe')
            r=subprocess.run([CC,'-std=gnu99','-Wall','-Werror=implicit-function-declaration','-I',str(ROOT/'src'),str(ROOT/'handoff/route_fallback_probe.c'),'-o',str(exe),'-lm'],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)
            r=subprocess.run([str(exe),d],cwd=d,capture_output=True,text=True)
            print(r.stdout,flush=True)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            self.assertIn('ALL OK',r.stdout)
if __name__=='__main__':unittest.main()
