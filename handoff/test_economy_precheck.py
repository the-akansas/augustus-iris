"""Economy measurement precheck (tools/economy_measure.py): no engine needed.
A 0-tick audit decides, before any long run, whether a city can show income for throne costs."""
import json,shutil,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import economy_measure as em

ZERO={k:0 for k in ('taxes','exports','donated','income_total','imports','wages','construction','interest','salary','sundries','tribute','levies','expenses_total','net_in_out','balance')}

def audit(folder,population,types,taxes=0,exports=0):
    folder.mkdir(parents=True)
    e=dict(year=0,month=0,day=0,tick=0,treasury=5000,tax_percentage=7,population=population,workers_employed=0,workers_needed=0,
           this_year=dict(ZERO,taxes=taxes),last_year=dict(ZERO,exports=exports))
    (folder/'economy-audit.json').write_text(json.dumps(e),encoding='utf8')
    (folder/'roster-audit.json').write_text(json.dumps(dict(year=0,month=0,day=0,tick=0,buildings=[[i+1,t,1,0,0,0,0,1] for i,t in enumerate(types)])),encoding='utf8')
    (folder/'trade-audit.json').write_text(json.dumps(dict(resources=[])),encoding='utf8')
    return folder

class Precheck(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.d=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()

    def test_cases(self):
        native=em.precheck(audit(self.d/'oppidum',0,[88]*61+[89,90]))                # native huts only, no people
        self.assertFalse(native['suitable_for_throne_costs']);self.assertIn('인구 또는 주택이 없음',native['reasons'])
        self.assertTrue(native['save_regression_usable']);self.assertIsNone(native['measured_income'])
        tents=em.precheck(audit(self.d/'tents',160,[10]*32+[73]*8))                  # prepared-1 shape: houses, no forum
        self.assertEqual(tents['houses'],32);self.assertEqual(tents['tax_buildings'],0)
        self.assertFalse(tents['suitable_for_throne_costs']);self.assertIn('수입원 없음',tents['reasons'][0])
        forum=em.precheck(audit(self.d/'forum',900,[12]*40+[86]))                     # tax building, no record yet
        self.assertTrue(forum['suitable_for_throne_costs']);self.assertFalse(forum['has_income_record'])
        trader=em.precheck(audit(self.d/'trader',400,[11]*20,exports=300))            # no forum but exports on record
        self.assertTrue(trader['suitable_for_throne_costs']);self.assertTrue(trader['has_income_record'])
        text=em.precheck_text('x',tents)
        for part in ('주택 32채','세금 징수 시설 0개','과거 수입 기록: 없음','실제 측정 수입: 미측정','부적합','저장·재로드 회귀: 사용 가능'):self.assertIn(part,text)

    def fake_engine(self,population,types):
        calls=[]
        def run(source,target,ticks):
            calls.append(ticks);audit(Path(target),population,types);return 0.0
        return calls,run

    def test_unsuitable_case_stops_before_the_long_run(self):
        case=self.d/'case';case.mkdir();(case/'city.sav').write_bytes(b's');(case/'receipt.bin').write_bytes(b'r')
        calls,em.run=self.fake_engine(0,[88])
        r=em.measure(case,self.d/'out')
        self.assertEqual(calls,[0])                                   # only the 0-tick audit ran
        self.assertIn('인구 또는 주택이 없음',r['skipped'])
        self.assertTrue((self.d/'out/case/precheck.json').is_file())
        self.assertIn('측정하지 않음',em.summary([dict(r,case_name='case')]))
        calls2,em.run=self.fake_engine(0,[88])
        with self.assertRaises(FileExistsError):em.measure(case,self.d/'out')   # earlier output is never replaced
        self.assertEqual(calls2,[])
        r=em.measure(case,self.d/'out2',allow_unsuitable=True)        # explicit: save/reload regression run
        self.assertNotIn('skipped',r);self.assertEqual(len(calls2),1+12+1+2+1)

    def test_check_reuses_an_existing_audit_and_writes_nothing_there(self):
        old=audit(self.d/'old-audit',160,[10]*32)
        before={p.name:p.read_bytes() for p in old.iterdir()}
        calls,em.run=self.fake_engine(0,[])
        report=em.check_only(self.d/'check',[old])
        self.assertEqual(calls,[]);self.assertEqual({p.name:p.read_bytes() for p in old.iterdir()},before)
        self.assertFalse(report[0]['suitable_for_throne_costs'])
        with self.assertRaises(FileExistsError):em.check_only(self.d/'check',[old])
        with self.assertRaises(SystemExit):em.check_only(self.d/'check2',[])        # nothing is read unless named

if __name__=='__main__':unittest.main()
