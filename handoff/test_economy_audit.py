"""Engine measurement mode 'economy-ticks' (creator_economy_audit.h): plain ticks, then economy-audit.json.
Needs the built worker (Augustus/engine-city-test.exe), the game data (AUGUSTUS_C3_DATA) and the review151 fixtures.
Runs through city_client.Engine, so the usual exit-code and engine-log checks apply unchanged."""
import json,os,shutil,tempfile,unittest,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Augustus'))
FIXTURE=ROOT/'handoff/review151/prepared-1/checked'

@unittest.skipUnless((ROOT/'Augustus/engine-city-test.exe').is_file() and os.environ.get('AUGUSTUS_C3_DATA') and (FIXTURE/'city.sav').is_file(),'engine, game data or review151 fixture missing')
class EconomyAudit(unittest.TestCase):
    def setUp(self):
        self.tmp=Path(tempfile.mkdtemp());self.addCleanup(shutil.rmtree,self.tmp,True)
        (self.tmp/'in').mkdir()
        for name in ('city.sav','receipt.bin'):shutil.copy2(FIXTURE/name,self.tmp/'in'/name)
    def test_one_month_is_reported_from_the_engine_records(self):
        from city_client import Engine
        Engine().run('economy-ticks',self.tmp/'in',self.tmp/'start',qty=0)
        Engine().run('economy-ticks',self.tmp/'in',self.tmp/'month',qty=800)
        start=json.loads((self.tmp/'start/economy-audit.json').read_text());month=json.loads((self.tmp/'month/economy-audit.json').read_text())
        self.assertEqual((month['year']*12+month['month'])-(start['year']*12+start['month']),1)     # 800 ticks = one month
        self.assertEqual(month['treasury'],json.loads((self.tmp/'month/summary.json').read_text())['money'])
        self.assertEqual(month['this_year']['wages'],month['wages_so_far'])                         # advisor refresh ran
        for key in ('taxes','exports','imports','wages','salary','sundries','income_total','expenses_total'):
            self.assertIn(key,month['this_year']);self.assertIn(key,month['last_year'])
        self.assertTrue((FIXTURE/'city.sav').read_bytes()==(self.tmp/'in/city.sav').read_bytes())   # the fixture is untouched
    def test_tick_limit(self):
        from city_client import Engine
        with self.assertRaises(RuntimeError):Engine().run('economy-ticks',self.tmp/'in',self.tmp/'big',qty=10001)


class MonthlyAccounting(unittest.TestCase):
    def test_year_boundary_includes_both_years(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('measure',ROOT/'tools/economy_measure.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        def row(year,current,last):
            return dict(year=year,month=0,treasury=0,population=0,workers_employed=0,workers_needed=0,stock={},this_year={k:current for k in m.FIELDS},last_year={k:last for k in m.FIELDS})
        self.assertEqual(m.monthly([row(1,100,0),row(2,7,120)])[0]['taxes'],27)
        self.assertEqual(m.monthly([row(2,7,120),row(2,30,120)])[0]['taxes'],23)

@unittest.skipUnless(os.environ.get('AUGUSTUS_TEST_SVX') and os.environ.get('AUGUSTUS_C3_DATA'),'approved SVX copy and data required')
class SvxImport(unittest.TestCase):
    def test_import_preserves_observed_city_state_on_reload(self):
        import hashlib
        from city_client import Engine
        source=Path(os.environ['AUGUSTUS_TEST_SVX']);before=hashlib.sha256(source.read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'in').mkdir();shutil.copy2(source,root/'in/city.svx')
            Engine().run('economy-import-svx',root/'in',root/'imported')
            Engine().run('economy-ticks',root/'imported',root/'reloaded',qty=0)
            a=json.loads((root/'imported/economy-audit.json').read_text());b=json.loads((root/'reloaded/economy-audit.json').read_text())
            for k in ('year','month','day','tick','treasury','population','workers_employed','workers_needed'):self.assertEqual(a[k],b[k],k)
            for name in ('roster-audit.json','trade-audit.json'):
                self.assertEqual(json.loads((root/'imported'/name).read_text()),json.loads((root/'reloaded'/name).read_text()),name)
            with self.assertRaises(RuntimeError):Engine().run('economy-import-svx',root/'in',root/'bad',qty=1)
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),before)

if __name__=='__main__':unittest.main()
