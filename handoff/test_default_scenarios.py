"""Default scenario list (tools/make_default_scenarios.py, Augustus/default-scenarios.json): the lobby and the editor
show exactly the listed scenarios, in order; other folders under scenarios/ open only through AUGUSTUS_MP_PROJECT."""
import json,os,shutil,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];A=ROOT/'Augustus'
sys.path.insert(0,str(A));sys.path.insert(0,str(ROOT/'tools'))
import scenario_project as sp,scenario_check as sc,make_default_scenarios as mk
NAMES=json.loads((A/'default-scenarios.json').read_text(encoding='utf8'))['scenarios']

class Files(unittest.TestCase):
    def test_list_and_files_are_current(self):
        self.assertEqual(NAMES,mk.DEFAULTS)
        self.assertEqual(NAMES,['freebuild-6p','coop-6p','throne-6p','progress-6p'])   # user 2026-11-14: one tutorial per victory condition, 6 players each, one to two hours
        self.assertEqual([sp.load(A/'scenarios'/n/'scenario.json')['rules']['mode'] for n in NAMES],['free-build','cooperative','race-for-throne','imperial-progress'])
        self.assertEqual({len(sp.load(A/'scenarios'/n/'scenario.json')['slots']) for n in NAMES},{6})
        for n in NAMES:   # every player starts as governor (rank 9, 총독): paying oneself less than that raises favor
            self.assertEqual({s['governance']['rank'] for s in sp.load(A/'scenarios'/n/'scenario.json')['slots']},{9},n)
        made={}
        for n in NAMES:
            p=A/'scenarios'/n/'scenario.json';d=sp.load(p);sp.require_runtime(d);sp.layout(d)
            self.assertEqual(sc.check_file(p)['counts']['block'],0,n)
            self.assertEqual(d['rules']['player_transport'],'land',n)
            self.assertTrue(d.get('start_message',{}).get('common'),n)            # a tutorial says what the game is about when it starts
            if n in made:self.assertEqual(d,sp.validate(made[n]) if hasattr(sp,'validate') else d)
            else:self.assertEqual(json.loads(p.read_text(encoding='utf8')),{'coop-6p':mk.coop,'throne-6p':mk.throne,'progress-6p':mk.progress}[n]()) if n!='freebuild-6p' else self.assertIn(mk.TUTORIAL,d['briefing'])
        self.assertEqual(len({sp.load(A/'scenarios'/n/'scenario.json')['id'] for n in NAMES}),len(NAMES))
    def test_every_default_starts_with_any_players(self):
        """A room freezes the roster at the start: cities nobody took become neutral (room_roster.effective_project).
        Every choice of one to six cities must give a valid scenario. Found by the user on 2026-11-14: the cities of
        the free-build map carry 'parked_trade', and a start with two players was refused ('invalid_request')."""
        import itertools,room_roster
        for n in NAMES:
            d=sp.load(A/'scenarios'/n/'scenario.json');ids=[s['id'] for s in d['slots']]
            for k in range(1,len(ids)+1):
                for keep in itertools.combinations(ids,k):
                    if k<sp.min_players(d):   # the author's minimum (user 2026-11-15): refused, with the number
                        with self.assertRaisesRegex(ValueError,'needs players %d'%sp.min_players(d)):room_roster.effective_project(d,list(keep))
                        continue
                    frozen,removed=room_roster.effective_project(d,list(keep))
                    self.assertEqual(len(frozen['slots']),k,(n,keep));self.assertEqual(len(removed),len(ids)-k)
                    self.assertFalse([c for c in frozen['empire']['cities'] if c['role']!='player' and 'parked_trade' in c],(n,keep))
    def test_no_fishing_buildings_without_fish(self):
        for d in (mk.free_build(2),mk.free_build(4),mk.free_build(6),mk.feature_example()):   # examples, made but not shipped
            n=d['id']
            for s in d['slots']:
                if s['name_id'] in mk.NO_FISH:self.assertFalse({mk.SHIPYARD,mk.WHARF}&set(s['allowed_buildings']),(n,s['id']))
    def test_feature_example_uses_the_editor_features(self):
        d=mk.feature_example();slot={s['id']:s for s in d['slots']}
        self.assertEqual(d['rules']['mode'],'cooperative');self.assertEqual(len(d['rules']['objectives']['deliveries']),2)
        self.assertEqual(d['rules']['player_trade']['exceptions'][0]['between'],['player1','player4'])
        self.assertEqual(slot['player1']['starting_funds'],12000);self.assertTrue(all(s.get('role_hint') for s in d['slots']))
        self.assertEqual(slot['player1']['governance']['policy'],'fixed');self.assertEqual(len(slot['player2']['invasions']),1)
        self.assertEqual({e['kind'] for s in d['slots'] for e in s.get('events',[])},{'grant','request'})
        self.assertTrue(any(c.get('trade_players') for c in d['empire']['cities']))

class Lists(unittest.TestCase):
    def labels(self,project=None):
        import network_play as np
        old=os.environ.pop('AUGUSTUS_MP_PROJECT',None)
        if project:os.environ['AUGUSTUS_MP_PROJECT']=str(project)
        try:
            s=np.Session.__new__(np.Session);s.starts=[];s.publish=lambda *a:None
            try:s.prepare_starts()
            except Exception:
                if not s.starts:raise                                        # the saved-room part needs game data; the scenario part is done by then
            return [x['label'] for x in s.starts if x['label'].startswith('[기본 제공]')],s.starts
        finally:
            os.environ.pop('AUGUSTUS_MP_PROJECT',None)
            if old is not None:os.environ['AUGUSTUS_MP_PROJECT']=old
    def test_lobby_shows_the_list_in_order(self):
        labels,starts=self.labels()
        titles=[sp.load(A/'scenarios'/n/'scenario.json')['title'] for n in NAMES]
        self.assertEqual(len(labels),len(NAMES))
        for label,title in zip(labels,titles):self.assertIn(title,label)
        self.assertEqual(Path(starts[0]['project']).parent.name,NAMES[0])    # the automatic choice is the first listed one
        self.assertEqual(len([l for l in labels if '황위 쟁탈전' in l]),1)
    def test_other_bundled_folder_opens_only_when_named(self):
        other=A/'scenarios/unified-sandbox/scenario.json'
        if not other.is_file():self.skipTest('unified-sandbox is not in this copy')
        labels,starts=self.labels(other)
        self.assertEqual(len(labels),len(NAMES)+1);self.assertEqual(Path(starts[0]['project']).parent.name,'unified-sandbox')
    def test_throne_scenario_is_offered_to_every_launcher(self):
        throne=A/'scenarios/throne-test-v1/scenario.json'
        if not throne.is_file():self.skipTest('throne-test-v1 is not in this copy')
        old=os.environ.pop('AUGUSTUS_MP_TEST_TOOLS',None)
        try:
            labels,starts=self.labels(throne)                                 # even when named directly
            self.assertTrue([s for s in starts if 'throne-test-v1' in s['project']]);self.assertEqual(len(labels),len(NAMES)+1)   # no hold any more (user 2026-11-14)
            os.environ['AUGUSTUS_MP_TEST_TOOLS']='1'
            labels,starts=self.labels(throne)
            self.assertTrue([s for s in starts if 'throne-test-v1' in s['project']])
        finally:
            os.environ.pop('AUGUSTUS_MP_TEST_TOOLS',None)
            if old is not None:os.environ['AUGUSTUS_MP_TEST_TOOLS']=old
    def test_windows_path_aliases_keep_bundled_category_and_no_duplicates(self):
        from windows_paths import filesystem_path
        for name in (NAMES[0],'unified-sandbox'):
            ordinary=A/'scenarios'/name/'scenario.json'
            labels,starts=self.labels(ordinary)
            extended_labels,extended_starts=self.labels(filesystem_path(ordinary))
            self.assertEqual(labels,extended_labels)
            self.assertEqual(len(labels),len(NAMES)+(name not in NAMES))
            self.assertEqual(sum(Path(s.get('project','')).parent.name==name for s in starts),1)
            self.assertEqual(sum(Path(s.get('project','')).parent.name==name for s in extended_starts),1)
    def test_editor_examples_follow_the_list(self):
        from creator_workspace import Workspace
        with tempfile.TemporaryDirectory() as t:
            shutil.copytree(A/'scenarios',Path(t)/'scenarios');(Path(t)/'default-scenarios.json').write_text((A/'default-scenarios.json').read_text(encoding='utf8'),encoding='utf8')
            ex=Workspace(Path(t)).catalog()['examples']
        self.assertEqual([Path(e['path']).parent.name for e in ex],NAMES)

if __name__=='__main__':unittest.main()
