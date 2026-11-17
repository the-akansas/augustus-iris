"""Authored start message (common + per city) and cooperative totals by number of players (user decisions 2026-11-14).

  * start_message: {'common': text, 'per_city': {slot id: text}} -> one confirm window per player at game start:
    the common text, then the player's own city text. Plain text; the author's '@' cannot become a rich-text command.
  * objectives.by_players: {'<players>': {population_total, treasury_total}} -> when a room starts with fewer players
    than cities, the frozen roster takes the totals of that count. No entry: the full-roster totals stay.
Runs the real code (scenario_project, scenario_briefing, room_roster.effective_project, scenario_pair binding rule).
The scenario is the shipped feature-trade-goals project with TEST INPUT values."""
import copy,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/'Augustus'
sys.path.insert(0,str(ROOT))
import scenario_project as sp,scenario_briefing as sb

def project():
    return json.loads((ROOT/'scenarios/provincial-quartet/scenario.json').read_text(encoding='utf8'))

class StartMessage(unittest.TestCase):
    def setUp(self):self.d=project();self.ids=[s['id'] for s in self.d['slots']]
    def test_absent_is_valid_and_shows_nothing(self):
        sp.validate(self.d);self.assertIsNone(sb.start_message(self.d,self.ids[0]));self.assertEqual(sb.start_message_file(None),'')
    def test_common_then_own_city(self):
        self.d['start_message']=dict(common='모두에게.\n둘째 줄',per_city={self.ids[1]:'둘째 도시만.'});sp.validate(self.d)
        a,b=sb.start_message(self.d,self.ids[0]),sb.start_message(self.d,self.ids[1])
        self.assertEqual(a['body'],'모두에게.\n둘째 줄');self.assertEqual(b['body'],'모두에게.\n둘째 줄\n\n둘째 도시만.')
        self.assertNotEqual(a['id'],b['id']);self.assertEqual(len(a['id']),32)
        self.assertEqual(sb.start_message_file(b),b['id']+'\t'+self.d['title']+'\t모두에게.@L둘째 줄@P둘째 도시만.\n')
    def test_only_city_text(self):
        self.d['start_message']=dict(per_city={self.ids[0]:'첫 도시.'});sp.validate(self.d)
        self.assertEqual(sb.start_message(self.d,self.ids[0])['body'],'첫 도시.');self.assertIsNone(sb.start_message(self.d,self.ids[1]))
    def test_id_follows_text(self):
        self.d['start_message']=dict(common='가');one=sb.start_message(self.d,self.ids[0])['id']
        self.d['start_message']=dict(common='나');self.assertNotEqual(one,sb.start_message(self.d,self.ids[0])['id'])
    def test_author_at_sign_and_tabs_cannot_break_the_file(self):
        self.d['start_message']=dict(common='@H 제목\t탭 @G12');line=sb.start_message_file(sb.start_message(self.d,self.ids[0]))
        self.assertEqual(line.count('\t'),2);self.assertEqual(line.count('\n'),1);self.assertNotIn('@',line.split('\t')[2])
    def test_refused(self):
        for bad in (dict(common='x'*(sp.START_MESSAGE_MAX+1)),dict(per_city={'nobody':'x'}),dict(other='x'),dict(common=1),dict(common='a\x07'),'text'):
            d=copy.deepcopy(self.d);d['start_message']=bad
            with self.assertRaises(ValueError,msg=repr(bad)[:40]):sp.validate(d)

class PlayerCountGoals(unittest.TestCase):
    def setUp(self):
        self.d=project();self.ids=[s['id'] for s in self.d['slots']]
        self.d['rules']['mode']='cooperative'
        self.d['rules']['objectives']=dict(population_total=8000,treasury_total=40000,per_city={})
    def test_table_is_valid_and_not_in_the_binding_rules(self):
        self.d['rules']['objectives']['by_players']={'2':dict(population_total=3000,treasury_total=15000),'3':dict(population_total=5500)}
        sp.validate(self.d)
        import objectives
        rules={k:v for k,v in self.d['rules']['objectives'].items() if k!='by_players'};objectives.validate_rules(rules,self.ids)
        self.assertIn("if k!='by_players'",(ROOT/'scenario_pair.py').read_text(encoding='utf8'))
    def test_refused(self):
        n=len(self.ids)
        for bad in ({str(n):dict(population_total=1)},{'0':dict(population_total=1)},{'02':dict(population_total=1)},{'2':{}},{'2':dict(per_city={})},{'2':dict(population_total=-1)},[]):
            d=copy.deepcopy(self.d);d['rules']['objectives']['by_players']=bad
            with self.assertRaises(ValueError,msg=repr(bad)):sp.validate(d)
    def roster(self,keep):
        import room_roster
        try:return room_roster.effective_project(self.d,keep)[0]
        except ModuleNotFoundError as e:self.skipTest('creator_presets not in this tree: '+str(e))
    def test_fewer_players_take_their_totals(self):
        self.d['rules']['objectives']['by_players']={'2':dict(population_total=3000,treasury_total=15000),'3':dict(population_total=5500)}
        two=self.roster(self.ids[:2])['rules']['objectives']
        self.assertEqual((two['population_total'],two['treasury_total']),(3000,15000));self.assertNotIn('by_players',two)
        three=self.roster(self.ids[:3])['rules']['objectives']
        self.assertEqual((three['population_total'],three['treasury_total']),(5500,40000))   # only the entered total changes
    def test_full_roster_and_missing_entry_keep_the_totals(self):
        self.d['rules']['objectives']['by_players']={'2':dict(population_total=3000)}
        full=self.roster(self.ids)['rules']['objectives'];self.assertEqual(full['population_total'],8000);self.assertNotIn('by_players',full)
        if len(self.ids)>3:self.assertEqual(self.roster(self.ids[:3])['rules']['objectives']['population_total'],8000)
    def test_all_zero_for_a_count_becomes_free_build(self):
        self.d['rules']['objectives']['by_players']={'2':dict(population_total=0,treasury_total=0)}
        self.assertEqual(self.roster(self.ids[:2])['rules']['mode'],'free-build')

if __name__=='__main__':unittest.main()
