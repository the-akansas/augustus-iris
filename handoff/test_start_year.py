"""시작 연도 (user 2026-11-17: "시나리오 에디트에서 연도를 정할수 있으면 좋겠어"): rules.start_year, -500..300 without 0;
a scenario without it starts in -350 as before."""
import json,os,shutil,sys,tempfile,unittest
from pathlib import Path
A=Path(__file__).resolve().parents[1]/'Augustus'
sys.path.insert(0,str(A))
import scenario_project as sp,status_display,scenario_overview
SCENARIO=A/'scenarios'/'freebuild-2p'/'scenario.json'

UNSET=object()
def scenario(year=UNSET):
    data=json.loads(SCENARIO.read_text(encoding='utf-8-sig'))
    if year is not UNSET:data['rules']['start_year']=year
    return data

class Rules(unittest.TestCase):
    def test_range(self):
        for year in (-500,-350,-1,1,300):self.assertEqual(sp.start_year(sp.validate(scenario(year))),year)
        for bad in (-501,301,0,'-44',1.5,True,None):
            with self.assertRaises(ValueError,msg=repr(bad)):sp.validate(scenario(bad))
        self.assertEqual(sp.start_year(scenario()),-350)
    def test_layout(self):
        plain=sp.layout(scenario());self.assertNotIn('YEAR',plain)                     # older engines read it as before
        rows=sp.layout(scenario(-44)).splitlines();at=rows.index('YEAR -44')
        self.assertTrue(all(any(r.startswith(t+' ') for r in rows[:at]) for t in ('GOVERNANCE','EVENTS','INVASIONS')))
        self.assertFalse(any(r.split()[0] in ('FUNDS','ENEMIES','RAIDERS','EVENTTEXT','EVENTCOND','EVENTREPEAT','INVREPEAT') for r in rows[:at]))   # the first tail section
    def test_dates(self):
        self.assertEqual(status_display.date_label(0),'기원전 350년 1월')
        self.assertEqual(status_display.date_label(800*13,-44),'기원전 43년 2월')
        self.assertEqual(status_display.date_label(0,120),'서기 120년 1월')
    def test_overview_names_it_only_when_set(self):
        catalog=json.loads((A/'preset-catalog.json').read_text(encoding='utf-8-sig'))
        text=lambda d:json.dumps(scenario_overview.overview(sp.validate(d),catalog),ensure_ascii=False)
        self.assertNotIn('시작 연도',text(scenario()))
        self.assertIn('시작 연도: 기원전 44년',text(scenario(-44)));self.assertIn('시작 연도: 서기 120년',text(scenario(120)))

@unittest.skipUnless(os.environ.get('AUGUSTUS_C3_DATA') and (A/'engine-city-test.exe').exists(),'needs the city engine and Caesar III data')
class Engine(unittest.TestCase):
    def city_year(self,year):
        from scenario_pair import load_pair,verify_city
        from city_client import Engine as E
        tmp=Path(tempfile.mkdtemp());self.addCleanup(shutil.rmtree,tmp,True)
        data=sp.validate(scenario(year));preset,binding=load_pair(os.environ['AUGUSTUS_C3_DATA'],data)
        sp.write_layout(data,tmp)
        city=data['slots'][0]['id'];out=tmp/city;E().run('start-'+city,tmp,out);verify_city(out,city,preset)
        return json.loads((out/'scenario.json').read_text())['year'],binding['sha256']
    def test_cities_start_in_the_authors_year(self):
        usual,a=self.city_year(UNSET);self.assertEqual(usual,-350)
        early,b=self.city_year(-44);self.assertEqual(early,-44)
        late,c=self.city_year(120);self.assertEqual(late,120)
        self.assertEqual(len({a,b,c}),3)     # another year is another scenario for the room

if __name__=='__main__':unittest.main()
