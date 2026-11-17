"""Rome as a fixed capital on every empire map, and the salary amounts shown in the editor.

Rome: rome-capital.json is the one shared position (evidence in that file); schema-5 files keep their own empire.rome.
Rome is never a player or trade city, never counted, never written into a scenario, and a city on top of it is reported
(never moved). Salary: the editor shows only what the engine reported for the current map (governance-audit.json of the
real start path: base and city_emperor_salary_for_rank for every rank). EngineSalary runs the real worker when the game
data and the worker are present, otherwise it is skipped (and says so)."""
import copy,json,os,shutil,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/'Augustus'
sys.path.insert(0,str(ROOT))
import scenario_check as sc,scenario_project as sp,creator_presets,rome_capital,scenario_overview,lobby_map,throne_state

def base():return creator_presets.default_project(4)
def of(result,check):return [f for f in result['findings'] if f['check']==check]
def catalog():return json.loads((ROOT/'preset-catalog.json').read_text(encoding='utf-8-sig'))
ENGINE_TABLE=[0,2,5,8,12,20,30,40,60,80,100]   # what the worker reported at base 100 (see EngineSalary)

class Rome(unittest.TestCase):
    def test_shared_position_and_evidence(self):
        s=rome_capital.spec()
        self.assertEqual((s['x'],s['y'],s['keep_clear'],s['icon']),(768,496,24,'Empire_Icon_Roman_05'))
        self.assertIn('Valentia.map',s['evidence'])
        self.assertEqual(rome_capital.position(base()),(768,496,'shared'))
    def test_schema5_keeps_its_own_rome(self):
        data=base();data['schema']=5;data['rules']['mode']='race-for-throne';data['rules']['throne']=throne_state.defaults()
        data['empire']['rome']=dict(id='rome',x=900,y=500);sp.validate(data)
        self.assertEqual(rome_capital.position(data),(900,500,'scenario'))
        before=copy.deepcopy(data);sc.check(data);scenario_overview.overview(data,catalog())
        self.assertEqual(data,before)                                                    # nothing rewritten
    def test_not_a_city_not_counted_not_saved(self):
        data=base();before=copy.deepcopy(data);r=sc.check(data)
        self.assertEqual(data,before);self.assertNotIn('rome',data['empire'])           # a plain file is never raised to schema 5
        self.assertEqual(r['rome'],dict(name='로마',x=768,y=496,source='shared',keep_clear=24))
        self.assertEqual(len(r['limits']),len(data['slots']))
        self.assertFalse([c for c in sc.city_model(data) if c['kind']=='rome'])           # contract view unchanged for schema < 5
        for row in r['links']:
            self.assertFalse([l for l in row['links'] if l.get('name_id') in (None,0) and l['kind']!='player'])
        view=scenario_overview.overview(data,catalog())
        self.assertNotIn('로마',[c['name'] for c in view['cities']])
        self.assertIn(f"플레이 도시 {len(data['slots'])}개",view['subtitle'])
        lines=scenario_overview.encode('X',view).splitlines();at=lines.index('ROME 768 496')
        s=rome_capital.spec()
        self.assertEqual(lines[at+1:at+5],['ROMETITLE\t로마 — 위대한 제국의 수도','ROMETEXT\t'+s['description'],'ROMEFACT\t'+s['facts'],'ROMEFACT\t'+s['facts_detail']])
        self.assertEqual(s['description'],'위대한 황제께서 거처하시며 온 세상은 그의 발밑에 있습니다. 당신은 그의 명령에 복종합니다. 지금으로서는 그렇습니다.')
    def test_lobby_map_line(self):
        rows=[dict(id='player1',name='카푸아',x=818,y=537),dict(id='',name='타렌툼',x=921,y=574),dict(rome=True,name='로마',x=768,y=496)]
        class B:joined=False
        state=dict(slots=[dict(city='player1',claimed=False,ready=False,online=False,name='',player_color=0)],host_city='',empire_map=rows)
        text=lobby_map.encode(B(),state).splitlines()
        self.assertEqual(text[:2],['AUGLOBBYMAP3','2']);self.assertEqual(text[-1],'ROME 768 496')
        self.assertNotIn('로마',text[2:-1])
        state['empire_map']=rows[:2];self.assertNotIn('ROME',lobby_map.encode(B(),state))  # older state: no Rome line
    def test_city_on_rome_is_reported_not_moved(self):
        data=base();city=next(c for c in data['empire']['cities'] if c['role']!='player')
        city['x'],city['y'],city['enabled']=770,500,True;before=copy.deepcopy(data)
        r=sc.check(data);hit=of(r,'rome-position')
        self.assertEqual(len(hit),1);self.assertEqual(hit[0]['severity'],'block');self.assertIn('옮겨',hit[0]['reason'])
        e=r['export'];self.assertFalse(e['allowed']);self.assertIn('rome-position',[f['check'] for f in e['blocks']]);self.assertEqual(data,before)
        city['x']=768+24;self.assertFalse(of(sc.check(data),'rome-position'))           # 24 away is allowed (not too strict)
        city['x'],city['enabled']=768,False;self.assertEqual([f['severity'] for f in of(sc.check(data),'rome-position')],['info'])
        player=next(c for c in data['empire']['cities'] if c['role']=='player');city['x']=1500;player['x'],player['y']=768,496
        self.assertEqual([f['severity'] for f in of(sc.check(data),'rome-position')],['block'])
    def test_icon_is_the_original_asset(self):
        xml=(ROOT/'assets/Graphics/ui.xml')
        if not xml.is_file():self.skipTest('packed ui.xml not in this copy')
        self.assertIn('id="Empire_Icon_Roman_05"',xml.read_text(encoding='utf-8',errors='replace'))

class Salary(unittest.TestCase):
    def setUp(self):
        self.dir=tempfile.TemporaryDirectory();self.old=sc.EVIDENCE;sc.EVIDENCE=Path(self.dir.name)
    def tearDown(self):sc.EVIDENCE=self.old;self.dir.cleanup()
    def terrain(self):return dict(width=3,height=1,terrain_flags=[0,0,0])
    def test_facts_parse(self):
        self.assertEqual(sc.salary_facts(dict(caesar_salary=100,salary_for_rank=ENGINE_TABLE)),dict(base=100,by_rank=ENGINE_TABLE))
        for bad in (None,{},dict(caesar_salary=100),dict(caesar_salary=100,salary_for_rank=[1]*10),dict(caesar_salary='100',salary_for_rank=ENGINE_TABLE)):
            self.assertIsNone(sc.salary_facts(bad))
    def test_limits_follow_the_engine_evidence(self):
        data=base();slot=data['slots'][1]
        self.assertTrue(all(l['salary'] is None for l in sc.check(data,facts=sc.evidence(data))['limits']))   # no result: unknown
        sc.store_evidence(slot,self.terrain(),dict(caesar_salary=150,salary_for_rank=[v*3//2 for v in ENGINE_TABLE]))
        limits={l['slot']:l for l in sc.check(data,facts=sc.evidence(data))['limits']}
        self.assertEqual(limits[slot['id']]['salary'],dict(base=150,by_rank=[v*3//2 for v in ENGINE_TABLE]))  # never assumed to be 100
        self.assertIsNone(limits[data['slots'][0]['id']]['salary'])
        slot['governance']=dict(rank=9,salary_rank=10,savings=0,favor=50,policy='fixed')                       # governance is not in the key
        self.assertIsNotNone({l['slot']:l for l in sc.check(data,facts=sc.evidence(data))['limits']}[slot['id']]['salary'])
        slot['campaign_scenario']=(slot['campaign_scenario']+1)%20                                             # another map: unknown again
        self.assertIsNone({l['slot']:l for l in sc.check(data,facts=sc.evidence(data))['limits']}[slot['id']]['salary'])
    def test_old_worker_gives_unknown(self):
        data=base();sc.store_evidence(data['slots'][0],self.terrain(),dict(rank=0,salary_rank=0,savings=0,favor=50,policy_code=0))
        self.assertIsNone(sc.check(data,facts=sc.evidence(data))['limits'][0]['salary'])

class EngineSalary(unittest.TestCase):
    """The real worker on the review151 fixture: base, per-rank amounts, the applied amount for P1 (rank 9, matched),
    P2 (rank 3, salary rank 8), P3 (no settings) and that the save keeps them. Slow (one engine start per slot)."""
    def test_engine(self):
        exe=ROOT/'engine-city-test.exe';fixture=ROOT.parent/'handoff/review151/scenario.json'
        if not exe.is_file() or not fixture.is_file() or not os.environ.get('AUGUSTUS_C3_DATA'):self.skipTest('worker, review151 fixture or game data missing')
        import creator_terrain
        data=json.loads(fixture.read_text(encoding='utf-8-sig'))
        data['slots'][0]['governance']=dict(rank=9,salary_rank=-1,savings=0,favor=50,policy='fixed')
        data['slots'][1]['governance']=dict(rank=3,salary_rank=8,savings=500,favor=50,policy='original')
        data['slots'][2].pop('governance',None)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'p.json';p.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
            r=creator_terrain.validate_project(p)
            try:
                self.assertTrue(r['valid'],r['errors'])
                audit=lambda s,*sub:json.loads(Path(r['output'],s,*sub,'governance-audit.json').read_text(encoding='utf8'))
                if 'salary_for_rank' not in audit('player1'):self.skipTest('worker predates the salary fields')
                for slot,(rank,paid) in dict(player1=(9,9),player2=(3,8),player3=(0,0)).items():
                    a=audit(slot);self.assertEqual((a['rank'],a['salary_rank'],a['salary_amount']),(rank,paid,a['salary_for_rank'][paid]))
                    self.assertEqual(a['salary_for_rank'],[a['caesar_salary']*p//100 for p in (0,2,5,8,12,20,30,40,60,80,100)])
                    self.assertEqual({k:v for k,v in audit(slot,'reload').items() if 'salary' in k},{k:v for k,v in a.items() if 'salary' in k})
                limits={l['slot']:l for l in sc.check(sp.load(p),facts=sc.evidence(sp.load(p)))['limits']}
                self.assertEqual(limits['player1']['salary']['by_rank'],audit('player1')['salary_for_rank'])
            finally:shutil.rmtree(r['output'],ignore_errors=True)

if __name__=='__main__':unittest.main()
