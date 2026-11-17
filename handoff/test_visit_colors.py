"""Observing another city: the city-view renderer gets the observer's colour tables (trade post roofs, pennants,
soldiers) without getting the multiplayer bridge. Bug 2026-11-12: player 2's post roof (partner = player 1, blue)
showed as the neutral grey (looks white) when player 1 watched player 2's city."""
import re,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Augustus'))
try:import observe_channel                          # Windows: the real shared-memory channel
except OSError:                                     # Linux: observe_atomic.dll does not exist; share_colors does not use it
    import types;sys.modules['observe_channel']=types.SimpleNamespace(Channel=None,FRAME_CAP=0)

class VisitColors(unittest.TestCase):
    def test_tables_are_copied_and_refreshed_only_on_change(self):
        import city_visit
        with tempfile.TemporaryDirectory() as d:
            bridge=SimpleNamespace(root=Path(d)/'bridge');bridge.root.mkdir();folder=Path(d)/'visit';folder.mkdir()
            (bridge.root/'route-player-colors.txt').write_text('1 0\n2 1\n',encoding='utf8')
            (bridge.root/'army-colors.txt').write_text('77 0\n',encoding='utf8')
            seen={};city_visit.share_colors(bridge,folder,seen)
            self.assertEqual((folder/'route-player-colors.txt').read_text(encoding='utf8'),'1 0\n2 1\n')
            self.assertEqual((folder/'army-colors.txt').read_text(encoding='utf8'),'77 0\n')
            self.assertFalse((folder/'empire-player-colors.txt').exists())             # missing source: nothing invented
            stamp=(folder/'route-player-colors.txt').stat().st_mtime_ns
            city_visit.share_colors(bridge,folder,seen)
            self.assertEqual((folder/'route-player-colors.txt').stat().st_mtime_ns,stamp)   # unchanged: not rewritten
            (bridge.root/'route-player-colors.txt').write_text('1 3\n2 1\n',encoding='utf8')
            city_visit.share_colors(bridge,folder,seen)
            self.assertEqual((folder/'route-player-colors.txt').read_text(encoding='utf8'),'1 3\n2 1\n')
    def test_renderer_still_runs_without_the_bridge(self):
        src=(ROOT/'Augustus/city_visit.py').read_text(encoding='utf8')
        self.assertIn("not k.startswith('AUGUSTUS_MP_')",src)
        self.assertLess(src.index('share_colors(bridge,folder,colors)'),src.index('process=subprocess.Popen'))   # tables before the renderer starts
    def test_only_colour_tables_fall_back_to_the_visit_folder(self):
        c=(ROOT/'src/multiplayer/route_post.c').read_text(encoding='utf8')
        self.assertIn('static const char *color_dir(void){const char*d=getenv("AUGUSTUS_MP_BRIDGE");if(d && *d)return d;d=getenv("AUGUSTUS_CITY_VISIT")',c)
        for name in ('empire-player-colors.txt','route-player-colors.txt','army-colors.txt'):
            body=c[:c.index(name)];self.assertEqual(body[body.rindex('const char*dir='):].split(';')[0],'const char*dir=color_dir()')
        lookup=c[c.index('static int lookup('):]
        self.assertIn('getenv("AUGUSTUS_MP_BRIDGE")',lookup.split('\n')[1])         # contract state stays bridge-only

if __name__=='__main__':unittest.main()
