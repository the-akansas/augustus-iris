"""Terrain from a saved city (.svx): plan item 2 (external map -> terrain only).

Without the engine: file checks and the .mapx/.svx dispatch (real creator_native_editor / scenario_cities code).
With the engine (engine-city-test.exe in the Augustus folder, AUGUSTUS_C3_DATA set and a sample .svx present: the
user's 'Oppidum Obiorum WHK.svx' from Augustus-Home\\inputs or AUGUSTUS_TEST_SVX): the real conversion and the usual
mapx load/export/reload comparison, then the stored asset must contain no built tile except native villages.
"""
import json,os,sys,tempfile,unittest,base64
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
if not (ROOT/'Augustus').is_dir() and __import__('os').environ.get('AUGUSTUS_TEST_COPY'):ROOT=Path(__import__('os').environ['AUGUSTUS_TEST_COPY'])   # tests run from outside a test copy
sys.path.insert(0,str(ROOT/'Augustus'))
import creator_native_editor as cne

BUILT={'road':0x40,'aqueduct':0x100,'wall':0x4000,'gatehouse':0x8000,'garden':0x20,'rubble':0x1000,'highway':0x1e0000}
BUILDING=0x8

def sample():
    names=[os.environ.get('AUGUSTUS_TEST_SVX')]+[str(base/'Augustus-Home/inputs/Oppidum Obiorum WHK.svx') for base in (ROOT.parent,)]
    return next((Path(n) for n in names if n and Path(n).is_file()),None)

class Files(unittest.TestCase):
    def test_wrong_or_missing_file(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x.sav';p.write_bytes(b'x'*64)
            with self.assertRaises(ValueError):cne.inspect_save(p,Path(d)/'t1')
            with self.assertRaises(ValueError):cne.inspect_save(Path(d)/'none.svx',Path(d)/'t2')
            tiny=Path(d)/'tiny.svx';tiny.write_bytes(b'x')
            with self.assertRaises(ValueError):cne.inspect_save(tiny,Path(d)/'t3')
    def test_dispatch(self):
        calls=[]
        with patch.object(cne,'inspect_save',lambda p,t:calls.append(('svx',Path(p).name)) or ({},{})),patch.object(cne,'inspect_map',lambda p,t:calls.append(('mapx',Path(p).name)) or ({},{})):
            cne.inspect_terrain_file('a.SVX','t');cne.inspect_terrain_file('b.mapx','t')
        self.assertEqual(calls,[('svx','a.SVX'),('mapx','b.mapx')])
        import scenario_cities
        self.assertIn('inspect_terrain_file',Path(scenario_cities.__file__).read_text(encoding='utf8'))   # neutral-city attach uses it too
    def test_engine_failure_is_reported_in_korean(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'c.svx';p.write_bytes(b'x'*64)
            class Broken:
                def run(self,*a,**k):raise RuntimeError('engine operation rejected: 110')
            with patch.object(cne,'Engine',Broken):
                with self.assertRaises(ValueError) as e:cne.inspect_save(p,Path(d)/'t')
            self.assertIn('저장 파일에서 지형을 꺼내지 못했습니다',str(e.exception))

@unittest.skipUnless((ROOT/'Augustus/engine-city-test.exe').is_file() and os.environ.get('AUGUSTUS_C3_DATA') and sample(),'engine, game data or sample .svx missing')
class Engine(unittest.TestCase):
    def test_saved_city_becomes_terrain_only(self):
        with tempfile.TemporaryDirectory() as d:
            asset,first=cne.inspect_save(sample(),Path(d)/'t')
            import scenario_project
            raw=scenario_project.decode_terrain_asset(asset)                     # the stored form is a normal mapx asset
            self.assertEqual(raw[:8],b'VERSION\0')
            report=json.loads((Path(d)/'t/save-source.json').read_text(encoding='utf8'))
            self.assertEqual(report['format'],'augustus-svx');self.assertGreater(report['removed_tiles'],0)
            flags=first['terrain_flags']
            for name,bit in BUILT.items():self.assertEqual(sum(1 for t in flags if t&bit),0,name)
            self.assertEqual(sum(1 for t in flags if t&BUILDING),report['native_tiles'])   # only native villages remain
            self.assertEqual(first['climate'],report['climate'])
            self.assertTrue(first['entry'] and first['exit'])


class WorkerContract(unittest.TestCase):
    def invoke(self,root,log_text,missing=False):
        import city_client
        from types import SimpleNamespace
        def worker(*args,**kwargs):
            kwargs['stdout'].write(log_text.encode())
            (root/'out/terrain.mapx').write_bytes(b'VERSION\0')
            if not missing:(root/'out/save-terrain.json').write_text('{}')
            return SimpleNamespace(returncode=0)
        with patch.object(city_client,'game_data',lambda:root),patch.object(city_client.subprocess,'run',worker):
            return city_client.Engine().run('native-save-terrain',root/'input',root/'out')
    def test_export_reads_map_and_report_without_city_save(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self.invoke(Path(d),'Audio output disabled: no playback device opened'),(b'VERSION\0',b'{}'))
    def test_export_still_rejects_engine_log_errors(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(RuntimeError,'engine validation log failed'):
                self.invoke(Path(d),'Audio output disabled: no playback device opened\nERROR: broken')
    def test_export_still_requires_all_output_files(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileNotFoundError):self.invoke(Path(d),'Audio output disabled: no playback device opened',True)

if __name__=='__main__':unittest.main()
