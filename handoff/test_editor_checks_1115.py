"""Scenario editor logic and play checks found in the 2026-11-15 review (user: "시나리오 에디터 논리오류 및 인게임
시뮬레이션 압축검사").

  * a malformed project (a number where a table belongs, ...) is refused with ValueError, never a Python error;
  * a game mode that needs two players is refused for a scenario with one seat (no room could ever start);
  * an attack on an entry point the map does not have is a block in the shared-ZIP check: the city's game refuses to
    start then (creator_city_invasions.h), and the engine result of the map stays valid after such a change;
  * the scenario list counts at most six players for an eight-seat scenario;
  * a race on the emperor's favour warns about cities whose favour is pinned;
  * a trade exception between two seats does not stop a room that starts with fewer players than seats;
  * a treasury condition above a million is not cut to a million by the game (creator_city_events.h);
  * a repeat that waits for the city does not fire every missed repeat at once when the city gets there late;
  * a command whose handling keeps failing locally is given up after three tries instead of blocking the game;
  * a bridge round also prefetches the polls the last rounds made (high ping: fewer round trips per round);
  * what can be put in can be taken out (user 2026-11-15): a seat leaves with the goals that name it when asked, a
    city's kept terrain can be cleared, a neutral city goes back to what Caesar III gives, a scenario leaves the work
    list (moved aside, never deleted), and the editor's old leftovers are tidied without touching an edited map."""
import copy,json,os,shutil,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];A=ROOT/'Augustus'
sys.path.insert(0,str(A));sys.path.insert(0,str(Path(__file__).resolve().parent))
import scenario_project as sp,scenario_check as sc

def project(name='freebuild-2p'):return json.loads((A/'scenarios'/name/'scenario.json').read_text(encoding='utf-8-sig'))

class MalformedFiles(unittest.TestCase):
    def test_wrong_types_are_refused_as_mistakes(self):
        for change in (lambda d:d.__setitem__('rules','x'),lambda d:d.__setitem__('empire',7),lambda d:d['empire']['cities'].__setitem__(0,1.5),
                       lambda d:d['slots'].__setitem__(0,{'id':{'a':1}}),lambda d:d.__setitem__('schema',None),
                       lambda d:d['slots'][0].__setitem__('invasions',[True])):
            data=project();change(data)
            with self.assertRaises(ValueError):sp.validate(data)
    def test_every_default_scenario_still_passes(self):
        for p in sorted((A/'scenarios').glob('*/scenario.json')):sp.validate(json.loads(p.read_text(encoding='utf-8-sig')))

class PlayersNeeded(unittest.TestCase):
    def test_a_two_player_mode_needs_two_seats(self):
        data=project();data['rules']['mode']='deadline-race';data['rules']['race']=dict(stat='population',months=12)
        sp.validate(copy.deepcopy(data))
        gone=data['slots'].pop();city=next(c for c in data['empire']['cities'] if c['name_id']==gone['name_id'])
        city['role']='npc';city.pop('trade_players',None)
        with self.assertRaisesRegex(ValueError,'2명 이상'):sp.validate(data)

def terrain(points,exit_point=(5,5)):
    """A 10x10 meadow map with the given enemy entry points (x,y or None), rock at (9,9)."""
    flags=[0]*100;flags[99]=2
    return dict(width=10,height=10,terrain_flags=flags,exit=list(exit_point),
                invasion_points=[list(p) if p else [-1,-1] for p in points]+[[-1,-1]]*(8-len(points)))

class FewerPlayersThanSeats(unittest.TestCase):
    def test_trade_exceptions_of_empty_seats_leave_with_them(self):
        import room_roster
        data=project('freebuild-6p');ids=[s['id'] for s in data['slots']]
        data['rules']['player_trade']=dict(exceptions=[dict(between=sorted([ids[0],ids[5]]),allow=False),dict(between=sorted([ids[0],ids[1]]),allow=False)])
        sp.validate(data)
        played,_=room_roster.effective_project(data,ids[:3])               # refused before: the exception named player6
        self.assertEqual(played['rules']['player_trade']['exceptions'],[dict(between=sorted([ids[0],ids[1]]),allow=False)])

class ScenarioListLabel(unittest.TestCase):
    def test_eight_seats_are_listed_for_at_most_six_players(self):
        import test_eight_seat_room as E
        data=E.eight_seats();self.assertEqual(sp.players_label(data),'6')         # was '8': only six can play
        data['rules']['min_players']=2;self.assertEqual(sp.players_label(data),'2~6')
        self.assertEqual(sp.players_label(project('freebuild-2p')),'2')

class RaceOnPinnedFavour(unittest.TestCase):
    def test_a_favour_race_with_pinned_favour_is_warned(self):
        data=project('feature-trade-goals');data['rules'].pop('objectives');data['rules']['mode']='deadline-race'
        data['rules']['race']=dict(stat='favor',months=24);sp.validate(data)
        found=[f for f in sc.check(data)['findings'] if f['check']=='race']
        self.assertEqual(len(found),1);self.assertEqual(found[0]['severity'],'warn')
        data['rules']['race']['stat']='prosperity'
        self.assertFalse([f for f in sc.check(data)['findings'] if f['check']=='race'])

class InvasionPoints(unittest.TestCase):
    def found(self,data,t):
        return [f['reason'] for f in sc.check(data,terrain={data['slots'][0]['id']:t})['findings'] if f['check']=='invasion-point']
    def test_point_the_map_lacks_blocks_export(self):
        data=project();data['slots'][0]['invasions']=[dict(month=12,amount=20,point=2,target=0)];sp.validate(data)
        self.assertEqual(self.found(data,terrain([(1,1),(2,2)])),[])
        self.assertTrue(self.found(data,terrain([(1,1)])))                 # point 2 missing
        self.assertTrue(self.found(data,terrain([(1,1),(9,9)])))           # point 2 on rock
        data['slots'][0]['invasions'][0]['point']=0
        self.assertEqual(self.found(data,terrain([])),[])                   # automatic: the exit point serves
        self.assertTrue(self.found(data,terrain([],exit_point=(9,9))))      # nowhere to come in
    def test_older_engine_result_is_not_judged(self):
        data=project();data['slots'][0]['invasions']=[dict(month=12,amount=20,point=3,target=0)];sp.validate(data)
        t=terrain([]);t.pop('invasion_points')
        self.assertEqual(self.found(data,t),[])
    def test_the_engine_refuses_such_a_city(self):
        src=(ROOT/'mp-worker/creator_city_invasions.h').read_text(encoding='utf-8')
        self.assertIn('Creator invasion rejected',src)                      # why it is a block, not a warning

class MoneyCondition(unittest.TestCase):
    def test_constants_have_the_games_own_range(self):
        src=(ROOT/'mp-worker/creator_city_events.h').read_text(encoding='utf-8')
        self.assertIn('scenario_formula_add((const uint8_t*)text,-1000000000,1000000000)',src)
    @unittest.skipUnless((A/'engine-city-test.exe').is_file() and os.environ.get('AUGUSTUS_C3_DATA'),'needs the worker and the game data')
    def test_a_condition_above_a_million_waits(self):
        from city_client import Engine
        tmp=Path(tempfile.mkdtemp());self.addCleanup(shutil.rmtree,tmp,True)
        data=project();slot=data['slots'][0];slot.pop('governance',None);slot['starting_funds']=1000000
        slot['events']=[dict(kind='health',month=1,amount=5,resource=0,deadline=0,when=dict(stat='money',at_least=1500000))]
        sp.validate(data);sp.write_layout(data,tmp/'in')
        Engine().run('start-'+slot['id'],tmp/'in',tmp/'start');Engine().run('events-step',tmp/'start',tmp/'m2',qty=2)
        events=json.loads((tmp/'m2/events-audit.json').read_text())['events']
        self.assertEqual(events[0]['executions'],0)                          # 1,000,000 in the treasury: not yet

    @unittest.skipUnless((A/'engine-city-test.exe').is_file() and os.environ.get('AUGUSTUS_C3_DATA'),'needs the worker and the game data')
    def test_a_waiting_repeat_does_not_fire_all_at_once(self):
        # 3 grants every 2 months once the treasury reaches 20,000; it gets there at month 7 (a grant of 15,000).
        # Laid out as copies, all three fired the same day; the game's own repeat spaces them: months 8, 10, 12.
        from city_client import Engine
        tmp=Path(tempfile.mkdtemp());self.addCleanup(shutil.rmtree,tmp,True)
        data=project();slot=data['slots'][0];slot.pop('governance',None);slot['starting_funds']=10000
        slot['events']=[dict(kind='grant',month=1,amount=1,resource=0,deadline=0,repeat=dict(every=2,times=3),when=dict(stat='money',at_least=20000)),
                        dict(kind='grant',month=7,amount=15000,resource=0,deadline=0)]
        sp.validate(data);sp.write_layout(data,tmp/'in');Engine().run('start-'+slot['id'],tmp/'in',tmp/'m0');seen=[]
        for m in range(1,14):
            Engine().run('military-ticks',tmp/f'm{m-1}',tmp/f'm{m}',qty=800)
            seen.append(json.loads((tmp/f'm{m}/events-audit.json').read_text())['events'][0]['executions'])
        self.assertEqual(seen,[0,0,0,0,0,0,0,1,1,2,2,3,3])

class RepeatedInvasions(unittest.TestCase):
    """An attack that comes again (user 2026-11-15): 'repeat' {every, times}, the game's own repeat (INVREPEAT)."""
    def test_file_checks(self):
        data=project();slot=data['slots'][0]
        slot['invasions']=[dict(month=2,amount=20,point=0,target=4,repeat=dict(every=3,times=3))]
        sp.validate(data)
        import city_invasions as ci
        self.assertEqual(ci.repeats(data),[slot['id']+' 0 3 3']);self.assertEqual(ci.months(slot['invasions'][0]),[2,5,8])
        for bad in (dict(every=0,times=3),dict(every=3,times=1),dict(every=3,times=25),dict(every=241,times=2),dict(every=3),'x',dict(every=600,times=3)):
            d=copy.deepcopy(data);d['slots'][0]['invasions'][0]['repeat']=bad
            with self.assertRaises(ValueError,msg=str(bad)):sp.validate(d)
        d=copy.deepcopy(data);d['slots'][0]['invasions'].append(dict(month=5,amount=10,point=0,target=4,enemy=3))
        d['slots'][0]['invasions'][0]['enemy']=0
        with self.assertRaisesRegex(ValueError,'5개월'):sp.validate(d)          # a repeat meets another people in month 5

    @unittest.skipUnless((A/'engine-city-test.exe').is_file() and os.environ.get('AUGUSTUS_C3_DATA'),'needs the worker and the game data')
    def test_the_game_repeats_the_attack(self):
        from city_client import Engine
        tmp=Path(tempfile.mkdtemp());self.addCleanup(shutil.rmtree,tmp,True)
        data=project();slot=data['slots'][0]
        slot['invasions']=[dict(month=2,amount=20,point=0,target=4,repeat=dict(every=3,times=3)),dict(month=4,amount=10,point=0,target=4)]
        sp.validate(data);sp.write_layout(data,tmp/'in');Engine().run('start-'+slot['id'],tmp/'in',tmp/'m0');first={}
        for m in range(1,12):
            Engine().run('military-ticks',tmp/f'm{m-1}',tmp/f'm{m}',qty=800)
            for f in json.loads((tmp/f'm{m}/military-audit.json').read_text())['formations']:
                if not f['legion'] and f['soldiers']>0:first.setdefault(f['sequence'],m)
        self.assertEqual(sorted(first.values()),[2,4,5,8])                    # 2, 5, 8 and the single attack in month 4

@unittest.skipUnless(os.environ.get('AUGUSTUS_C3_DATA'),'needs the game data')
class MissingMapFile(unittest.TestCase):
    """A received scenario on a PC whose Caesar III folder lacks an original .map file (user 2026-11-15: "somebody who
    only receives a scenario must be able to play it"): named in the check and before a room is made, not as
    'engine operation rejected: 92'."""
    def setUp(self):
        self.tmp=Path(tempfile.mkdtemp());self.addCleanup(shutil.rmtree,self.tmp,True)
        data=Path(os.environ['AUGUSTUS_C3_DATA'])
        for f in data.iterdir():
            if f.name.lower()!='caesarea.map':
                if f.is_dir():shutil.copytree(f,self.tmp/f.name)
                else:shutil.copy2(f,self.tmp/f.name)
        p=patch.dict(os.environ,{'AUGUSTUS_C3_DATA':str(self.tmp)});p.start();self.addCleanup(p.stop)
        import creator_presets as cp,scenario_cities as cities
        base=cp.default_project(4);self.p=cities.swap_city(base,base['slots'][0]['id'],31)
    def test_a_seat_on_a_missing_file_is_named(self):
        import creator_presets as cp
        self.p['slots'][0]['campaign_scenario']=100;sp.validate(self.p)
        self.assertEqual([m[2] for m in cp.missing_maps(self.p)],['Caesarea.map'])
        found=[f for f in sc.check(self.p)['findings'] if f['check']=='map-file']
        self.assertEqual([f['severity'] for f in found],['block'])
    def test_a_campaign_seat_needs_no_map_file(self):
        import creator_presets as cp
        self.p['slots'][0]['campaign_scenario']=14;sp.validate(self.p)
        self.assertEqual(cp.missing_maps(self.p),[])

class TakeOutAgain(unittest.TestCase):
    def setUp(self):
        import creator_presets as cp,scenario_cities as cities
        self.cp,self.cities=cp,cities;self.data=cp.default_project(3)
    def test_a_seat_leaves_with_its_goals_when_asked(self):
        d=self.data;s0,s2=d['slots'][0]['id'],d['slots'][2]['id']
        d['rules']['mode']='cooperative';d['rules']['objectives']=dict(celebration='notice',population_total=3000,per_city={s2:dict(population=500)},
            deliveries=[dict(id='a',sender=s2,receiver=s0,kind='once',resource=3,quantity=5),dict(id='b',sender=s0,receiver=d['slots'][1]['id'],kind='once',resource=3,quantity=5)])
        name=d['slots'][2]['name_id']
        with self.assertRaises(ValueError):self.cities.to_neutral(d,name)
        out=self.cities.to_neutral(d,name,drop_goals=True);goals=out['rules']['objectives']
        self.assertEqual([g['id'] for g in goals['deliveries']],['b']);self.assertNotIn(s2,goals.get('per_city',{}))
        self.assertEqual(len(out['slots']),2)
    def test_kept_terrain_can_be_cleared_and_then_a_map_attached(self):
        name=self.data['slots'][2]['name_id'];self.data['slots'][2]['terrain_edits']=[dict(x=3,y=3,kind='tree')]
        out=self.cities.to_neutral(self.data,name);city=self.cities.find(out,name)
        self.assertTrue(city['map']['terrain_edits'])
        with self.assertRaises(ValueError):self.cities.attach_terrain(out,name,dict(format='mapx',sha256='0'*64,data=''))   # refused, not dropped
        out=self.cities.detach_terrain(out,name);self.assertNotIn('map',self.cities.find(out,name))
        out=self.cities.attach_terrain(out,name,dict(format='mapx',sha256='0'*64,data=''));self.assertIn('terrain_asset',self.cities.find(out,name)['map'])
    def test_a_neutral_city_goes_back_to_caesar_iii(self):
        c3={c['name_id']:c for c in self.cp.merged_empire()['cities']};city=next(c for c in self.data['empire']['cities'] if c['role']=='npc')
        n=city['name_id'];city.update(x=city['x']+50,cost=4321,sea=1-city['sea'],sells={'3':99},enabled=True,trade_players=[self.data['slots'][0]['id']],sea_auto=True,
                                      map=dict(campaign_scenario=2,terrain_edits=[dict(x=1,y=1,kind='tree')]))
        out=self.cities.reset_to_c3(self.data,n);got=self.cities.find(out,n)
        for k in ('x','y','sea','cost','sells','buys','enabled'):self.assertEqual(got[k],c3[n][k],k)
        for k in ('map','trade_players','sea_auto','parked_trade','reserved'):self.assertNotIn(k,got)
        self.assertEqual(sp.validate(out)['slots'],out['slots'])
        with self.assertRaises(ValueError):self.cities.reset_to_c3(out,out['slots'][0]['name_id'])
    def test_a_scenario_leaves_the_list_and_is_kept_aside(self):
        import creator_workspace as cw
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'scenarios').mkdir();w=cw.Workspace(root);folder=w.directory()
            mine=folder/'내 시나리오 [1].json';mine.write_text(json.dumps(project()),encoding='utf8')
            for i in range(3):(folder/(mine.name+'.2026111%d.bak'%i)).write_text('x')
            (folder/'other.json.1.bak').write_text('x')
            outside=root/'elsewhere.json';outside.write_text(json.dumps(project()),encoding='utf8')
            w.remember(mine);w.remember(outside)
            self.assertEqual(len(w.catalog()['entries']),2)
            moved=Path(w.discard(mine)['moved'])
            self.assertTrue(moved.is_file());self.assertFalse(mine.exists());self.assertEqual(len(list(moved.parent.glob('*.bak'))),3)
            self.assertTrue((folder/'other.json.1.bak').exists())
            self.assertIsNone(w.discard(outside)['moved']);self.assertTrue(outside.exists())
            self.assertEqual(w.catalog()['entries'],[]);self.assertEqual(w.read()['recent'],[])
            with self.assertRaises(ValueError):w.discard(root/'scenarios'/'x.json')
    def test_old_editor_leftovers_go_but_an_edited_map_stays(self):
        import creator_workspace as cw,hashlib
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);w=cw.Workspace(root);cache=root/'creator-cache';old=1_000_000_000
            def session(name,content,original):
                p=cache/'native-editor'/name;(p/'user'/'scenarios').mkdir(parents=True);(p/'user'/'scenarios'/'edit.mapx').write_bytes(content)
                (p/'session.json').write_text(json.dumps(dict(original_sha256=hashlib.sha256(original).hexdigest())));os.utime(p,(old,old));return p
            untouched=session('a',b'map',b'map');edited=session('b',b'changed',b'map');fresh=session('c',b'map',b'map');os.utime(fresh,None)
            check=cache/'validation-1';check.mkdir(parents=True);os.utime(check,(old,old))
            maps=root/'creator-maps'/'5';maps.mkdir(parents=True);os.utime(maps,(old,old))
            w.tidy()
            self.assertFalse(untouched.exists());self.assertTrue(edited.exists());self.assertTrue(fresh.exists());self.assertFalse(check.exists());self.assertTrue(maps.exists())

class RoundPlan(unittest.TestCase):
    def test_polls_of_the_last_rounds_ride_in_the_batch(self):
        import threading,city_client
        c=city_client.Client.__new__(city_client.Client);c.root=Path(tempfile.mkdtemp());self.addCleanup(shutil.rmtree,c.root,True)
        c.session='s';c.city='a'
        sent=[]
        def call(op,**fields):
            if op=='batch':sent.append(sorted(x['op'] for x in fields['calls']));return [dict(ok=True,result=None) for _ in fields['calls']]
            return None
        c.call=call;c._owner=threading.get_ident()
        def round_(ops):
            c.begin_round()
            for op in ops:c._take(op,{})
        round_(['lobby_status','save_status','army_overview'])               # the army poll only every other round
        round_(['lobby_status','save_status'])
        round_(['lobby_status','save_status'])
        self.assertIn('army_overview',sent[-1])                              # still asked for: seen two rounds ago
        round_(['lobby_status','save_status']);round_(['lobby_status','save_status'])
        self.assertNotIn('army_overview',sent[-1])                           # not for long
    def test_chat_read_takes_the_rounds_answer_from_an_older_cursor(self):
        import threading,city_client
        c=city_client.Client.__new__(city_client.Client);c.root=Path(tempfile.mkdtemp());self.addCleanup(shutil.rmtree,c.root,True)
        c.session='s';c.city='a';c.token='t';c._owner=threading.get_ident();asked=[]
        def network(op,**fields):
            asked.append(op)
            if op=='batch':return [dict(ok=True,result=dict(messages=['x'])) for _ in fields['calls']]
            raise AssertionError('went to the network: '+op)
        c._take('chat_read',dict(after=3));c._take('save_status',{})
        real=city_client.Client.call
        c.call=lambda op,**f:network(op,**f) if op=='batch' else real(c,op,**f)
        c.begin_round()
        self.assertEqual(c.call('chat_read',after=7),dict(messages=['x']))  # the cursor moved after a chat line: no extra trip
        self.assertEqual(asked,['batch'])


import test_throne_isolation as I
import test_throne_room_flow as F
@unittest.skipUnless(F.DATA and I.FREE.is_file() and F.native_library(1),'needs AUGUSTUS_C3_DATA and the real post_* C library: '+F._why)
class StuckCommand(I.FreeBuildRoom):
    """A command whose handling fails locally (a plain bug) was retried every round and the game waited for its
    answer for good. After three tries it is given up with the reason, like a refusal."""
    def test_a_failing_command_is_given_up(self):
        a=self.make_room('stuck');names=['player1','player2','player3','player4']
        bridges={c:self.bridge(a,i,c) for i,c in enumerate(names)};self.start(a,bridges);self.clock(a,bridges,800)
        h=bridges['player1'];real=h.client.call
        def broken(op,**fields):
            if op=='room_speed':raise TypeError('a plain bug')
            return real(op,**fields)
        (h.root/'command.txt').write_text('speed60\n',encoding='utf8')
        with patch.object(h.client,'call',broken):
            for _ in range(2):h.step()
            self.assertTrue((h.root/'command.txt').exists())                      # tried again: may be passing
            h.step()
        self.assertFalse((h.root/'command.txt').exists())
        self.assertEqual((h.root/'command-outcome.txt').read_text(encoding='utf8').strip(),'-1')
        (h.root/'command.txt').write_text('speed60\n',encoding='utf8');h.step()   # the next command works as before
        self.assertFalse((h.root/'command.txt').exists())
        self.assertEqual((h.root/'command-outcome.txt').read_text(encoding='utf8').strip(),'1')
for _n in [n for n in dir(I.FreeBuildRoom) if n.startswith('test_')]:
    if getattr(I.FreeBuildRoom,_n,None) is getattr(StuckCommand,_n,None):setattr(StuckCommand,_n,None)

if __name__=='__main__':unittest.main()
