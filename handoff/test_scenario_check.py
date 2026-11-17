"""개편 1단계: scenario contract view and pre-export checks.
Terrain here is synthetic: small flag grids plus the two engine answer fields ('entry_exit', 'sea') set by hand.
What the engine really answers for real maps is not tested here (see docs, final integration test)."""
import copy,json,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/'Augustus'
sys.path.insert(0,str(ROOT))
import scenario_check as sc,scenario_project as sp,creator_presets,throne_state
W,R,T,M=4,2,1,2048
MARBLE,QUARRY,DOCK,WAREHOUSE,WHARF,SHIPYARD=11,106,75,72,76,74
SEA_OK=dict(river_entry=1,river_exit=1,open_water=20,exit_reached=1,dock_sites=3,dock_sites_clear=3)
LAKE_SEA=dict(river_entry=0,river_exit=0,open_water=0,exit_reached=0,dock_sites=0,dock_sites_clear=0)
FISH_OK=dict(points=2,sites=6,two_sites=1)
NO_FISH=dict(points=0,sites=0,two_sites=0)
def route(now=1,cleared=None,bridged=None):
    cleared=now if cleared is None else cleared;bridged=cleared if bridged is None else bridged
    return dict(entry=[0,2],exit=[9,2],now=now,cleared=cleared,bridged=bridged)
def grid(rows,sea=SEA_OK,road=route(),fishing=FISH_OK):
    code={'.':0,'w':W,'r':R,'t':T,'m':M}
    t=dict(width=len(rows[0]),height=len(rows),terrain_flags=[code[c] for row in rows for c in row])
    if sea is not None:t['sea']=sea
    if road is not None:t['entry_exit']=road
    if fishing is not None:t['fishing']=fishing
    return t
RICH=grid(['wwwwwwwwww','wwwwwwwwww','..........','mmttrr....','..........'])
BARE=grid(['..........']*5,sea=LAKE_SEA,fishing=NO_FISH)
LAKE=grid(['mmttrr....','..wwwww...','..wwwww...','..wwwww...','..........'],sea=LAKE_SEA,fishing=NO_FISH)      # a lake: no trade ships, no fishing points
FISH_LAKE=grid(['..........','..wwwww...','..wwwww...','..wwwww...','..........'],sea=LAKE_SEA)                  # a lake with fishing points
ROCKY=grid(['wwwwwwwwww','wwwwwwwwww','rrrrrrrrrr','mmtt......','..........'],sea=dict(SEA_OK,dock_sites_clear=0))   # every dock site sits on rock
CUT=grid(['wwwwwwwwww','wwwwwwwwww','....r.....','mmttr.....','....r.....'],road=route(0,0,0))
OLD=grid(['wwwwwwwwww','wwwwwwwwww','..........','mmttrr....','..........'],sea=None,road=None,fishing=None)       # terrain.json from a worker without the new fields
def base():return creator_presets.default_project(4)
def everywhere(data,t):return {s['id']:t for s in data['slots']}
def kinds(result,severity):return sorted({f['check'] for f in result['findings'] if f['severity']==severity})
def of(result,check):return [f for f in result['findings'] if f['check']==check]
def no_marble_seller(data):
    for c in data['empire']['cities']:c['sells'].pop(str(MARBLE),None)
    for s in data['slots']:s['allowed_buildings']=[b for b in s['allowed_buildings'] if b!=QUARRY]
def sea_port(data,goods,partners=None):
    """Turn one neutral city into an enabled sea seller of goods."""
    n=next(c for c in data['empire']['cities'] if c['role']=='npc' and c['sea'] and not c.get('reserved'))
    n.update(enabled=True,sells={str(g):15 for g in goods});n['buys']={k:v for k,v in n['buys'].items() if int(k) not in goods}
    if partners is not None:n['trade_players']=partners
    return n
def land_port(data,goods):
    n=next(c for c in data['empire']['cities'] if c['role']=='npc' and not c['sea'] and not c.get('reserved'))
    n.update(enabled=True,sells={str(g):15 for g in goods});n['buys']={k:v for k,v in n['buys'].items() if int(k) not in goods}
    return n
def isolate(data):
    for c in data['empire']['cities']:
        if c['role']=='npc':c['enabled']=False

class Contract(unittest.TestCase):
    def test_model_and_no_mutation(self):
        data=base();before=sp.digest(data);r=sc.check(data,everywhere(data,RICH))
        self.assertFalse(r['blocked']);self.assertEqual(r['counts']['warn'],0,r['findings']);self.assertEqual(r['counts']['unverified'],0,r['findings'])
        self.assertTrue(r['export']['allowed']);self.assertEqual(sp.digest(data),before)
        model=sc.city_model(data);self.assertEqual(sum(c['kind']=='player' for c in model),4)
        import scenario_cities
        for c in model:
            if c['kind']!='neutral':continue
            offered=bool(scenario_cities.preset_terrains(c['name_id']))                 # a neutral city keeps its terrain and stays selectable for play
            self.assertEqual((c['has_terrain'],c['eligible'],c['map']['source']!='none'),(offered,offered,offered))
        self.assertTrue(any(c['has_terrain'] for c in model if c['kind']=='neutral') and any(not c['has_terrain'] for c in model if c['kind']=='neutral'))
    def test_bad_reference_and_preset_block(self):
        data=base();next(c for c in data['empire']['cities'] if c['role']=='npc')['trade_players']=['ghost']
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'s.json';p.write_text(json.dumps(data),encoding='utf-8');r=sc.check_file(p)
        self.assertEqual(kinds(r,'block'),['format'])
        data=base();data['empire']['template']=500;sp.validate(data);self.assertEqual(kinds(sc.check(data,everywhere(data,RICH)),'block'),['preset'])

class Sea(unittest.TestCase):
    def setUp(self):
        self.data=base();isolate(self.data)
        self.port=sea_port(self.data,[MARBLE]);sp.validate(self.data)
        self.terrain=everywhere(self.data,RICH);self.terrain['player1']=LAKE          # only player1 has no sea access
        self.r=sc.check(self.data,self.terrain)
    def test_1_player_land_trade_stays(self):
        d=copy.deepcopy(self.data);no_marble_seller(d);d['slots'][1]['allowed_buildings'].append(QUARRY);sp.validate(d)   # player2 can quarry
        r=sc.check(d,self.terrain)
        self.assertFalse([f for f in of(r,'resource') if 'player1' in f['target'] and f['severity']=='warn'],of(r,'resource'))   # reaches player1 by land
        self.assertFalse(r['blocked'])                                                                                   # never a scenario-wide block
    def test_2_only_sea_neutral_trade_is_limited(self):
        limit={l['slot']:l for l in self.r['limits']}
        self.assertEqual(limit['player1']['sea'],'blocked');self.assertEqual(limit['player1']['sea_neutrals'],[self.port['name_id']])
        self.assertTrue(limit['player1']['reason'])
        for other in ('player2','player3','player4'):self.assertEqual((limit[other]['sea'],limit[other]['sea_neutrals'],limit[other]['buildings']),('candidate',[],[]))
        d=copy.deepcopy(self.data);land_port(d,[MARBLE]);sp.validate(d);r=sc.check(d,self.terrain)
        self.assertEqual({l['slot']:l for l in r['limits']}['player1']['sea_neutrals'],[self.port['name_id']])               # the land seller is not listed
        note=[f for f in of(self.r,'sea') if 'player1' in f['target']];self.assertEqual(len(note),1)
        self.assertIn('육로',note[0]['reason']);self.assertEqual(note[0]['severity'],'warn')
    def test_3_only_sea_trade_buildings_disabled(self):
        limit={l['slot']:l for l in self.r['limits']}['player1']
        self.assertEqual(limit['buildings'],[DOCK])
        for general in (WAREHOUSE,WHARF,SHIPYARD):self.assertNotIn(general,limit['buildings'])
        self.assertIn(DOCK,self.data['slots'][0]['allowed_buildings'])                                                     # the stored choice is kept, only reported
        out=subprocess.run([sys.executable,'-X','utf8',str(ROOT/'scenario_check.py'),str(self.write()),'--limits'],capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(out.returncode,0,out.stderr);self.assertIn('limits',json.loads(out.stdout))
    def write(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);p=Path(self.tmp.name)/'s.json';p.write_text(json.dumps(self.data),encoding='utf-8');return p
    def test_unknown_is_not_blocked(self):
        t=dict(self.terrain);t['player1']=OLD;r=sc.check(self.data,t);limit={l['slot']:l for l in r['limits']}['player1']
        self.assertEqual((limit['sea'],limit['buildings'],limit['sea_neutrals']),('unknown',[],[]))
        blind={l['slot']:l for l in sc.check(self.data)['limits']};self.assertTrue(all(l['sea']=='unknown' and not l['buildings'] for l in blind.values()))

class Supply(unittest.TestCase):
    def test_4_real_trade_supply_gives_no_warning(self):
        data=base();no_marble_seller(data);land_port(data,[MARBLE]);sp.validate(data)
        self.assertFalse(of(sc.check(data,everywhere(data,RICH)),'resource'))
    def test_5_trade_without_a_source_is_not_a_supply(self):
        data=base();no_marble_seller(data);sp.validate(data)                       # four players may trade freely, nobody can make or buy marble
        r=sc.check(data,everywhere(data,RICH));marble=[f for f in of(r,'resource') if '대리석' in f['reason']]
        self.assertEqual(len(marble),4);self.assertTrue(all(f['severity']=='warn' and '다른 플레이어 도시 없음' in f['reason'] for f in marble))
        self.assertFalse(r['blocked'])
        sea=base();no_marble_seller(sea);isolate(sea);sea_port(sea,[MARBLE]);sp.validate(sea)   # the only seller is by sea and nobody has sea access
        r=sc.check(sea,everywhere(sea,LAKE));self.assertEqual(len([f for f in of(r,'resource') if '대리석' in f['reason'] and f['severity']=='warn']),4)
        t=everywhere(sea,LAKE);t['player3']=RICH                                                  # one city with sea access is enough: it can pass marble on by land
        self.assertFalse([f for f in of(sc.check(sea,t),'resource') if '대리석' in f['reason']])
        blind=sc.check(sea);self.assertTrue(all(f['severity']=='unverified' for f in of(blind,'resource')))   # no engine result: neither obtainable nor missing
    def test_6_no_food_warns_but_does_not_block(self):
        data=base();isolate(data);sp.validate(data);r=sc.check(data,everywhere(data,BARE))
        self.assertEqual(len([f for f in of(r,'food') if f['severity']=='warn']),4);self.assertFalse(r['blocked']);self.assertTrue(r['export']['allowed'])

class Export(unittest.TestCase):
    def setUp(self):
        self.dir=tempfile.TemporaryDirectory();self.keep=sc.EVIDENCE;sc.EVIDENCE=Path(self.dir.name)/'evidence'
    def tearDown(self):sc.EVIDENCE=self.keep;self.dir.cleanup()
    def verify(self,data,terrain):
        for s in data['slots']:sc.store_evidence(s,terrain[s['id']] if isinstance(terrain,dict) and s['id'] in terrain else terrain)
    def test_7_cut_and_unverified_are_different_refusals(self):
        data=base()
        with self.assertRaises(ValueError) as pending:sc.gate(data)
        self.assertIn('[검증 미완료]',str(pending.exception));self.assertNotIn('[막힘]',str(pending.exception))
        self.verify(data,RICH);self.assertTrue(sc.gate(data)['export']['allowed'])
        cut=base();cut['slots'][0]['terrain_edits']=[dict(x=5,y=5,kind='rock')];sp.validate(cut)
        sc.store_evidence(cut['slots'][0],CUT)
        with self.assertRaises(ValueError) as blocked:sc.gate(cut)
        self.assertIn('[막힘]',str(blocked.exception));self.assertIn('단절 확정',str(blocked.exception));self.assertNotIn('[검증 미완료]',str(blocked.exception))
        old=base();old['slots'][1]['terrain_edits']=[dict(x=6,y=6,kind='land')];sp.validate(old);sc.store_evidence(old['slots'][1],OLD)
        with self.assertRaises(ValueError) as stale:sc.gate(old)                    # an engine result without the route answer is not a pass
        self.assertIn('[검증 미완료]',str(stale.exception))
        for state in ((0,1,1),(0,0,1)):                                             # trees to clear / a bridge to build: connected
            self.assertEqual(sc.terrain_facts(grid(['..........']*5,road=route(*state)))['road'],('cleared','bridged')[state[1]==0])
    def test_8_changed_map_needs_a_new_result(self):
        data=base();self.verify(data,RICH);self.assertTrue(sc.gate(data)['export']['allowed'])
        changed=copy.deepcopy(data);changed['slots'][2]['terrain_edits']=[dict(x=10,y=10,kind='rock')];sp.validate(changed)
        with self.assertRaises(ValueError) as e:sc.gate(changed)
        self.assertIn('[검증 미완료]',str(e.exception));self.assertEqual(len(sc.check(changed,None,sc.evidence(changed))['export']['pending']),1)
        other=copy.deepcopy(data);other['slots'][0]['campaign_scenario']=other['slots'][1]['campaign_scenario']
        self.assertNotEqual(sc.terrain_key(other['slots'][0]),sc.terrain_key(data['slots'][0]))
        self.assertEqual(sc.terrain_key(copy.deepcopy(data['slots'][0])),sc.terrain_key(data['slots'][0]))
        keep=sc._worker[:];sc._worker[:]=['another-engine-build']                    # a rebuilt engine also invalidates old results
        try:self.assertEqual(sc.evidence(data),{})
        finally:sc._worker[:]=keep
    def test_9_zero_starting_funds(self):
        data=base();data['rules']['starting_funds']=0;sp.validate(data);self.verify(data,RICH);r=sc.gate(data)
        self.assertEqual([f['severity'] for f in of(r,'funds')],['info']);self.assertEqual(r['counts']['warn'],0)
        data['rules']['starting_funds']=-1
        with self.assertRaises(ValueError):sp.validate(data)                         # existing rule (0..1,000,000) is unchanged
    def test_10_saving_and_rome_unchanged(self):
        data=base();data['schema']=5;data['rules']['mode']='race-for-throne';data['rules']['throne']=throne_state.defaults()
        data['empire']['rome']=dict(id='rome',x=900,y=500);sp.validate(data)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'s.json';p.write_bytes(sp.canonical(data))                      # what the editor's save writes
            self.assertEqual(sp.canonical(sp.load(p)),p.read_bytes())                  # loads and round-trips with nothing verified
            plain=subprocess.run([sys.executable,'-X','utf8',str(ROOT/'scenario_project.py'),str(p)],capture_output=True,text=True,encoding='utf-8')
            self.assertEqual(plain.returncode,0,plain.stderr)                          # validation without --export does not consult the gate
        r=sc.check(data,everywhere(data,RICH))
        self.assertEqual(len(of(r,'entry-exit')),0);self.assertFalse([f for f in r['findings'] if f['target']=='로마' and f['severity']!='info'])
        self.assertEqual([c['map'] for c in sc.city_model(data) if c['kind']=='rome'],[dict(source='none')])
        self.assertEqual(len(r['limits']),4)                                           # Rome is not a checked city
        self.assertFalse([f for f in r['findings'] if f['check']=='throne' and f['severity']=='unverified'])   # no affordability check
    def test_cli_export(self):
        data=base();p=Path(self.dir.name)/'s.json';p.write_text(json.dumps(data),encoding='utf-8')
        run=lambda z:subprocess.run([sys.executable,'-X','utf8','-c','import sys,pathlib;sys.path.insert(0,sys.argv[1]);import scenario_check as sc;sc.EVIDENCE=pathlib.Path(sys.argv[2]);import runpy;sys.argv=[sys.argv[1]+"/scenario_project.py",sys.argv[3],"--export",sys.argv[4]];runpy.run_path(sys.argv[0],run_name="__main__")',str(ROOT),str(sc.EVIDENCE),str(p),str(z)],capture_output=True,text=True,encoding='utf-8')
        out=run(Path(self.dir.name)/'a.zip');self.assertEqual(out.returncode,1);self.assertIn('검증 미완료',out.stderr);self.assertFalse((Path(self.dir.name)/'a.zip').exists())
        self.verify(data,RICH);out=run(Path(self.dir.name)/'b.zip');self.assertEqual(out.returncode,0,out.stderr);self.assertTrue((Path(self.dir.name)/'b.zip').exists())

import scenario_cities as cities
MERIDIAN=dict(format='augustus-mapx',sha256=__import__('hashlib').sha256(b'VERSION\0map').hexdigest(),data=__import__('base64').b64encode(b'VERSION\0map').decode())
def plain_neutral(data):
    """A neutral city for which the catalog offers no map."""
    return next(c for c in data['empire']['cities'] if c['role']=='npc' and not c.get('reserved') and not cities.preset_terrains(c['name_id']))
def row(data,name_id):return next(c for c in sc.city_model(data) if c['name_id']==name_id)

class Roles(unittest.TestCase):
    def test_a_attach_map_makes_a_neutral_city_playable(self):
        data=base();n=plain_neutral(data)['name_id']
        before=cities.status(data,n);self.assertEqual((before['has_terrain'],before['eligible'],before['role']),(False,False,'neutral'))
        with self.assertRaises(ValueError) as refused:cities.to_player(data,n)          # no terrain: cannot be chosen for play
        self.assertIn('지형이 없는 도시',str(refused.exception))
        linked=sp.validate(cities.attach_terrain(data,n,MERIDIAN))
        state=cities.status(linked,n);self.assertEqual((state['has_terrain'],state['eligible'],state['role'],state['slot']),(True,True,'neutral',None))
        self.assertEqual(state['terrain']['source'],'external');self.assertEqual(row(linked,n)['map']['held'],'parked')
        played=sp.validate(cities.to_player(linked,n))
        self.assertEqual(cities.status(played,n)['role'],'player');self.assertEqual(sp.validate(played)['slots'][-1]['terrain_asset'],MERIDIAN)
        self.assertEqual(len(data['slots']),4);self.assertNotIn('map',plain_neutral(data))                       # the input project was not touched
    def test_b_city_keeps_terrain_and_trade_across_roles(self):
        data=base();slot=data['slots'][1];n=slot['name_id']
        slot.update(terrain_edits=[dict(x=30,y=30,kind='rock')],terrain_asset=MERIDIAN,allowed_buildings=[72,75,106])
        slot['governance'].update(rank=3,savings=500);sp.validate(data);terrain={k:copy.deepcopy(slot[k]) for k in cities.TERRAIN}
        neutral=sp.validate(cities.to_neutral(data,n))                                    # the slot is deleted, the city keeps its terrain
        state=cities.status(neutral,n);self.assertEqual((state['role'],state['has_terrain'],state['eligible'],state['slot']),('neutral',True,True,None))
        self.assertEqual(cities.find(neutral,n)['map'],terrain)                           # terrain only: slot settings are not kept on the city
        self.assertEqual(row(neutral,n)['map']['source'],'external')
        traded=cities.set_sea(neutral,n,True);city=cities.find(traded,n);city.update(enabled=True,cost=300,sells={'11':20});city['trade_players']=['player1']
        sp.validate(traded)
        back=sp.validate(cities.to_player(traded,n));new=back['slots'][-1]
        self.assertEqual({k:new[k] for k in cities.TERRAIN},terrain)                      # preset, edits and external map are back
        self.assertEqual(len(new['allowed_buildings']),len(cities._all_buildings()));self.assertEqual(new['governance']['rank'],0)   # a new slot starts from defaults
        self.assertEqual(cities.find(back,n)['parked_trade'],dict(sea=1,cost=300,sells={'11':20},buys={},trade_players=['player1']))
        again=sp.validate(cities.to_neutral(back,n,enabled=True));city=cities.find(again,n)
        self.assertEqual((city['sea'],city['cost'],city['sells'],city['trade_players']),(1,300,{'11':20},['player1']))
        self.assertEqual(city['map'],terrain)
    def test_b2_slot_keeps_its_settings_when_its_city_changes(self):
        data=base();slot=data['slots'][0];a=slot['name_id'];slot.update(allowed_buildings=[72,76,100],terrain_edits=[dict(x=12,y=12,kind='water')])
        slot['governance'].update(rank=5,favor=70);sp.validate(data);a_terrain={k:copy.deepcopy(slot[k]) for k in cities.TERRAIN if k in slot}
        b=next(c for c in data['empire']['cities'] if c['role']=='npc' and cities.preset_terrains(c['name_id']) and not c.get('reserved'))
        b.update(enabled=True,cost=200,sells={'7':10});sp.validate(data);n=b['name_id']
        other=cities.to_neutral(data,data['slots'][3]['name_id'])                           # a city that was played with different settings before
        notes=[];moved=sp.validate(cities.swap_city(data,slot['id'],n,notes=notes));now=next(s for s in moved['slots'] if s['id']==slot['id'])
        self.assertEqual((now['name_id'],now['allowed_buildings'],now['governance']['rank'],now['governance']['favor']),(n,[72,76,100],5,70))
        self.assertEqual(now['terrain_edits'],[]);self.assertIn(now['campaign_scenario'],cities.preset_terrains(n))   # B's terrain, not A's edits
        self.assertEqual(cities.find(moved,a)['map'],dict(a_terrain,terrain_edits=a_terrain['terrain_edits']))        # A keeps its terrain and edits
        self.assertEqual(cities.find(moved,n)['parked_trade'],dict(sea=b['sea'],cost=200,sells={'7':10},buys=b['buys']))
        self.assertEqual(len(moved['slots']),4);self.assertEqual(notes,[])
        back=sp.validate(cities.swap_city(moved,slot['id'],a));again=next(s for s in back['slots'] if s['id']==slot['id'])
        self.assertEqual({k:again[k] for k in a_terrain},a_terrain);self.assertEqual(again['allowed_buildings'],[72,76,100])
        self.assertEqual((cities.find(back,n)['cost'],cities.find(back,n)['sells']),(200,{'7':10}))
        third=other['slots'][0];c=data['slots'][3]['name_id']                                # swap onto the city another slot used: nothing of that slot comes along
        got=next(s for s in sp.validate(cities.swap_city(other,third['id'],c))['slots'] if s['id']==third['id'])
        self.assertEqual((got['allowed_buildings'],got['governance']),(third['allowed_buildings'],third['governance']))
    def test_b3_older_kept_settings_never_override_a_slot(self):
        data=base();slot=data['slots'][0];slot['allowed_buildings']=[72];sp.validate(data)
        n=data['slots'][3]['name_id'];draft=cities.to_neutral(data,n)
        cities.find(draft,n)['map'].update(allowed_buildings=[75,106],governance=dict(rank=9,salary_rank=-1,savings=0,favor=50,policy='fixed'))   # as the first draft wrote it
        sp.validate(draft)                                                                   # still a valid file
        notes=[];moved=sp.validate(cities.swap_city(draft,slot['id'],n,notes=notes));now=next(s for s in moved['slots'] if s['id']==slot['id'])
        self.assertEqual((now['allowed_buildings'],now['governance']['rank']),([72],0));self.assertEqual(len(notes),1);self.assertIn('allowed_buildings',notes[0])
        fresh=sp.validate(cities.to_player(draft,n))['slots'][-1]                            # a new slot has no values of its own, so the kept ones are used
        self.assertEqual((fresh['allowed_buildings'],fresh['governance']['rank']),([75,106],9))
    def test_c_goals_are_not_dropped_silently(self):
        data=base();data['rules']['mode']='cooperative';ids=[s['id'] for s in data['slots']]
        data['rules']['objectives']=dict(population_total=0,per_city={i:dict(population=0,culture=0,prosperity=0,peace=0,favor=0,treasury=0) for i in ids})
        data['rules']['objectives']['per_city'][ids[0]]['population']=500;sp.validate(data)
        with self.assertRaises(ValueError):cities.to_neutral(data,data['slots'][0]['name_id'])
        self.assertEqual(len(sp.validate(cities.to_neutral(data,data['slots'][1]['name_id']))['slots']),3)
    def test_d_old_files_and_layout(self):
        data=base();neutral=cities.to_neutral(data,data['slots'][3]['name_id'])
        self.assertNotIn('map',json.dumps(data));old=copy.deepcopy(neutral);old['schema']=3
        with self.assertRaises(ValueError):sp.validate(old)                                                       # older formats refuse the field instead of ignoring it
        plain=copy.deepcopy(neutral);cities.find(plain,data['slots'][3]['name_id']).pop('map')
        self.assertEqual(sp.layout(sp.validate(neutral)),sp.layout(sp.validate(plain)))                           # the engine layout does not see kept maps
    def test_e_neutral_cities_are_not_route_checked(self):
        data=base();sea_port(data,[MARBLE]);n=data['slots'][3]['name_id'];neutral=sp.validate(cities.to_neutral(data,n,enabled=True))
        r=sc.check(neutral,everywhere(neutral,RICH))
        self.assertEqual(len(r['limits']),3);self.assertTrue(r['export']['allowed'],r['export'])                  # the kept map needs no engine result
        self.assertFalse([f for f in r['findings'] if f['check']=='entry-exit'])

class SeaMode(unittest.TestCase):
    def setUp(self):
        self.dir=tempfile.TemporaryDirectory();self.addCleanup(self.dir.cleanup);self.keep=cities.HERE;cities.HERE=Path(self.dir.name)
        self.addCleanup(lambda:setattr(cities,'HERE',self.keep))
        rows=['0'*100 for _ in range(50)];rows[10]='1'*100                                                         # a band of sea at y 200..219
        (Path(self.dir.name)/'empire-coast.json').write_text(json.dumps(dict(schema=1,templates={'25':dict(cell=20,reach=0,rows=rows)})),encoding='utf-8')
        self.data=base();self.n=plain_neutral(self.data)['name_id']
    def test_f_manual_choice_beats_the_estimate(self):
        on_land=cities.move(cities.set_sea(self.data,self.n,True),self.n,500,600)        # checked by hand, moved inland
        self.assertEqual((cities.find(on_land,self.n)['sea'],cities.status(on_land,self.n)['sea_mode']),(1,'manual'))
        at_sea=cities.move(cities.set_sea(self.data,self.n,False),self.n,500,210)        # unchecked by hand, moved onto the coast
        self.assertEqual(cities.find(at_sea,self.n)['sea'],0);self.assertNotIn('sea_auto',cities.find(at_sea,self.n))
        stored=copy.deepcopy(self.data);cities.find(stored,self.n)['sea']=1              # an existing file: a stored value with no marker is manual
        self.assertEqual(cities.find(cities.move(stored,self.n,500,600),self.n)['sea'],1)
    def test_g_only_auto_cities_follow_a_move(self):
        auto=cities.set_sea_auto(cities.move(self.data,self.n,500,600),self.n)
        self.assertEqual((cities.find(auto,self.n)['sea'],cities.status(auto,self.n)['sea_mode']),(0,'auto'))
        moved=sp.validate(cities.move(auto,self.n,500,210));self.assertEqual(cities.find(moved,self.n)['sea'],1)
        self.assertEqual(cities.find(cities.move(moved,self.n,500,600),self.n)['sea'],0)
        manual=cities.set_sea(moved,self.n,True);self.assertEqual(cities.find(cities.move(manual,self.n,500,600),self.n)['sea'],1)   # hand choice ends auto mode
        (Path(self.dir.name)/'empire-coast.json').unlink()
        blind=cities.move(moved,self.n,500,600);self.assertEqual(cities.find(blind,self.n)['sea'],1)              # no coast data: no guess, value kept
        self.assertIsNone(cities.coast_estimate(25,500,600)['estimate'])

class Fishing(unittest.TestCase):
    def setUp(self):
        self.data=base();isolate(self.data)
        for s in self.data['slots']:s['allowed_buildings']=[b for b in s['allowed_buildings'] if not 100<=b<=105]   # no farms: fish is the only food
        sp.validate(self.data)
    def test_h_lake_without_ships_can_still_fish(self):
        r=sc.check(self.data,everywhere(self.data,FISH_LAKE));limit=r['limits'][0]
        self.assertEqual((limit['sea'],limit['fishing']),('blocked','candidate'))
        self.assertEqual(limit['buildings'],[DOCK]);self.assertFalse(of(r,'food'));self.assertFalse(of(r,'fishing'))    # wharf and shipyard untouched, fish counts as food
    def test_i_lake_without_fishing_points_cannot_fish(self):
        r=sc.check(self.data,everywhere(self.data,LAKE));self.assertEqual(r['limits'][0]['fishing'],'blocked')
        self.assertEqual(len([f for f in of(r,'food') if f['severity']=='warn']),4);self.assertEqual(len(of(r,'fishing')),4)
        self.assertIn('어장',of(r,'fishing')[0]['reason']);self.assertFalse(r['blocked'])
        t=everywhere(self.data,LAKE);t['player2']=FISH_LAKE                                # one fishing city feeds the others by land
        self.assertFalse(of(sc.check(self.data,t),'food'))
        d=copy.deepcopy(self.data);d['slots'][0]['allowed_buildings'].remove(SHIPYARD);sp.validate(d)
        self.assertFalse(of(sc.check(d,everywhere(d,FISH_LAKE)),'food'))                    # the other three still fish and can pass it on
        solo=copy.deepcopy(self.data);[s['allowed_buildings'].remove(SHIPYARD) for s in solo['slots']];sp.validate(solo)
        self.assertEqual(len([f for f in of(sc.check(solo,everywhere(solo,FISH_LAKE)),'food') if f['severity']=='warn']),4)   # a wharf without a shipyard gets no boat
        self.assertTrue(all(f['severity']=='unverified' for f in of(sc.check(self.data,everywhere(self.data,OLD)),'food')))
    def test_candidate_is_not_confirmed(self):
        d=base();sea_port(d,[MARBLE]);sp.validate(d);r=sc.check(d,everywhere(d,ROCKY))
        self.assertTrue(all(l['sea']=='unknown' and not l['buildings'] for l in r['limits']))                       # rock under every site: neither confirmed
        note=[f for f in of(sc.check(d,everywhere(d,RICH)),'sea')];self.assertTrue(note and all(f['severity']=='info' and '후보' in f['reason'] for f in note))

class Stale(unittest.TestCase):
    def test_j_role_or_map_change_drops_old_results(self):
        with tempfile.TemporaryDirectory() as d:
            keep=sc.EVIDENCE;sc.EVIDENCE=Path(d)
            try:
                data=base()
                for s in data['slots']:sc.store_evidence(s,LAKE if s['id']=='player1' else RICH)
                first={l['slot']:l['sea'] for l in sc.check(data,None,sc.evidence(data))['limits']};self.assertEqual(first['player1'],'blocked')
                n=data['slots'][0]['name_id'];neutral=cities.to_neutral(data,n);self.assertNotIn('player1',{l['slot'] for l in sc.check(neutral,None,sc.evidence(neutral))['limits']})
                remap=cities.to_player(cities.attach_terrain(cities.to_neutral(data,n),n,MERIDIAN),n,slot_id='player1')   # same city and slot name, another map
                again={l['slot']:l['sea'] for l in sc.check(sp.validate(remap),None,sc.evidence(remap))['limits']}
                self.assertEqual(again['player1'],'unknown')                                                          # the old "blocked" is not reused
                with self.assertRaises(ValueError) as e:sc.gate(remap)
                self.assertIn('[검증 미완료]',str(e.exception))
                same=cities.to_player(cities.to_neutral(data,n),n,slot_id='player1')                                    # unchanged map: the result still applies
                self.assertEqual({l['slot']:l['sea'] for l in sc.check(same,None,sc.evidence(same))['limits']}['player1'],'blocked')
            finally:sc.EVIDENCE=keep

class WharfNotice(unittest.TestCase):
    def notices(self,allowed,terrain):
        data=base()
        for s in data['slots']:s['allowed_buildings']=[b for b in s['allowed_buildings'] if b not in (WHARF,SHIPYARD)]+allowed
        sp.validate(data);r=sc.check(data,everywhere(data,terrain) if terrain else None)
        return r,[(f['severity'],f['reason']) for f in of(r,'fishing')]
    def test_wharf_by_fishing_points(self):
        r,n=self.notices([WHARF,SHIPYARD],LAKE);self.assertEqual(len(n),4);self.assertTrue(all(s=='warn' and '어장이 없습니다' in t for s,t in n))
        self.assertFalse(r['blocked']);self.assertFalse(r['export']['blocks'])               # a warning only
        self.assertEqual(self.notices([WHARF,SHIPYARD],FISH_LAKE)[1],[])                     # wharf + fishing points: nothing to say
        r,n=self.notices([WHARF,SHIPYARD],OLD);self.assertTrue(len(n)==4 and all(s=='unverified' and '확인하지 못했습니다' in t for s,t in n))   # no data is not "no fishing points"
        self.assertTrue(all(s=='unverified' for s,t in self.notices([WHARF,SHIPYARD],None)[1]))
        for terrain in (LAKE,FISH_LAKE,OLD,None):
            self.assertEqual(self.notices([],terrain)[1],[])                                  # wharf not allowed: never mentioned
            self.assertEqual(self.notices([SHIPYARD],terrain)[1],[])                          # shipyard alone is no reason either
    def test_other_reasons_are_named_differently(self):
        cramped=grid(['..........','..wwwww...','..wwwww...','..wwwww...','..........'],sea=LAKE_SEA,fishing=dict(points=2,sites=1,two_sites=0))
        noshore=grid(['..........','..wwwww...','..wwwww...','..wwwww...','..........'],sea=LAKE_SEA,fishing=dict(points=2,sites=0,two_sites=0))
        for terrain in (cramped,noshore):
            n=self.notices([WHARF,SHIPYARD],terrain)[1];self.assertEqual(len(n),4)
            self.assertTrue(all(s=='warn' and '어장은 있지만' in t and '어장이 없습니다' not in t for s,t in n))
        n=self.notices([WHARF],FISH_LAKE)[1];self.assertTrue(len(n)==4 and all('조선소' in t and '어장은 있습니다' in t for s,t in n))
    def test_food_is_judged_separately(self):
        r,n=self.notices([WHARF,SHIPYARD],LAKE);self.assertEqual(len(n),4);self.assertFalse(of(r,'food'))   # no fishing, but the lake map has meadow for farms
        data=base();isolate(data)
        for s in data['slots']:s['allowed_buildings']=[b for b in s['allowed_buildings'] if not 100<=b<=105]
        land_port(data,[1]);sp.validate(data)                                                 # no farms, no fish, but a land city sells wheat
        self.assertFalse(of(sc.check(data,everywhere(data,LAKE)),'food'))
        self.assertTrue(all(f['severity']=='unverified' for f in of(sc.check(data,everywhere(data,OLD)),'food')) )
    def test_neutral_city_gets_no_wharf_notice(self):
        data=base();n=data['slots'][3]['name_id'];neutral=sp.validate(cities.to_neutral(data,n))
        r=sc.check(neutral,everywhere(neutral,LAKE));self.assertEqual(len(of(r,'fishing')),3)

class Throne(unittest.TestCase):
    def test_schema_5_survives_reading_and_writing(self):
        data=base();data['schema']=5;data['rules']['mode']='race-for-throne';data['rules']['throne']=throne_state.defaults()
        data['empire']['rome']=dict(id='rome',x=900,y=500);sp.validate(data);raw=sp.canonical(data)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'s.json';p.write_bytes(raw);loaded=sp.load(p)
            self.assertEqual((loaded['schema'],loaded['empire']['rome'],loaded['rules']['throne']),(5,data['empire']['rome'],data['rules']['throne']))
            self.assertEqual(sp.canonical(loaded),raw)
        n=data['slots'][3]['name_id'];changed=sp.validate(cities.to_neutral(data,n))          # a data edit keeps the format and Rome
        self.assertEqual((changed['schema'],changed['empire']['rome'],changed['rules']['throne']),(5,data['empire']['rome'],data['rules']['throne']))
        lowered=copy.deepcopy(data);lowered['schema']=4                                       # what the editor's upgrade step would have produced
        with self.assertRaises(ValueError):sp.validate(lowered)
        lowered['empire'].pop('rome')
        with self.assertRaises(ValueError):sp.validate(lowered)                               # the throne rules are refused in a schema 4 file as well
    def test_editor_keeps_schema_5_as_schema_5(self):
        source=Path(__file__).resolve().parents[1]/'creator-src'/'ScenarioCreator.cs'
        if not source.is_file():self.skipTest('creator source not in this tree')
        text=source.read_text(encoding='utf-8-sig');body=text[text.index('void Upgrade(Scenario data){'):]
        # 2026-11-14: the editor opens a throne scenario (CreatorThrone.cs). It works on it as format 4 + rules.throne and
        # writes format 5 back with the mode and Rome; it never drops them silently. Source check only; not compiled here.
        self.assertTrue(body.startswith('void Upgrade(Scenario data){AdoptThrone(data);'))
        throne=(source.parent/'CreatorThrone.cs').read_text(encoding='utf-8-sig')
        self.assertIn('value["schema"]=5;rules["mode"]="race-for-throne"',throne);self.assertIn('["rome"]=new Dictionary<string,object>{{"id","rome"}',throne)
        self.assertIn('ApplyThroneToFile(value);',(source.parent/'CreatorMergedEmpire.cs').read_text(encoding='utf-8-sig'))

class ProgressGoods(unittest.TestCase):
    """황제의 순행 goods (user 2026-11-15): judged like resources - made, bought from a neutral city, or passed on by a player."""
    def setUp(self):
        import imperial_progress
        self.data=base();self.data['rules']['mode']='imperial-progress';self.data['rules']['progress']=imperial_progress.defaults()
        self.good=16;self.workshop=sc.rules()['industry'][str(self.good)]   # furniture and the building that makes it
    def without(self,data):
        for c in data['empire']['cities']:c['sells'].pop(str(self.good),None)
        for s in data['slots']:s['allowed_buildings']=[b for b in s['allowed_buildings'] if b!=self.workshop]
    def test_all_obtainable_is_one_note(self):
        sp.validate(self.data);r=of(sc.check(self.data,everywhere(self.data,RICH)),'progress-goods')
        self.assertEqual([f['severity'] for f in r],['info'])
    def test_nobody_can_get_it_warns(self):
        self.without(self.data);sp.validate(self.data);r=of(sc.check(self.data,everywhere(self.data,RICH)),'progress-goods')
        self.assertEqual(len(r),1);self.assertEqual(r[0]['severity'],'warn');self.assertIn('가구',r[0]['reason']);self.assertFalse(sc.check(self.data,everywhere(self.data,RICH))['blocked'])
    def test_one_maker_supplies_the_others_by_trade(self):
        self.without(self.data);self.data['slots'][0]['allowed_buildings'].append(self.workshop);sp.validate(self.data)
        self.assertEqual([f['severity'] for f in of(sc.check(self.data,everywhere(self.data,RICH)),'progress-goods')],['info'])
    def test_neutral_seller_counts(self):
        self.without(self.data);land_port(self.data,[self.good]);sp.validate(self.data)
        self.assertEqual([f['severity'] for f in of(sc.check(self.data,everywhere(self.data,RICH)),'progress-goods')],['info'])
    def test_no_engine_result_is_unverified(self):
        sp.validate(self.data);r=of(sc.check(self.data),'progress-goods')
        self.assertTrue(r and all(f['severity']=='unverified' for f in r))

if __name__=='__main__':unittest.main()
