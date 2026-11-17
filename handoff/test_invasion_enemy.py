"""The enemy people of a city's invasions (user 2026-11-14): one per city, absent = the map's own."""
import copy,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'Augustus'))
from scenario_project import validate,layout

def scenario():
    return json.loads((ROOT/'Augustus/scenarios/provincial-quartet/scenario.json').read_text(encoding='utf-8-sig'))

class InvasionEnemy(unittest.TestCase):
    def test_absent_leaves_the_layout_as_before(self):
        d=scenario();validate(d)
        self.assertNotIn('ENEMIES',layout(d))

    def test_written_after_the_other_sections(self):
        d=scenario();d['slots'][0]['invasion_enemy']=12;validate(d)
        rows=layout(d).splitlines()
        self.assertEqual(rows[-2:],['ENEMIES 1','player1 12'])
        self.assertLess(rows.index(next(r for r in rows if r.startswith('INVASIONS '))),rows.index('ENEMIES 1'))

    def test_after_funds_when_both(self):
        d=scenario();d['slots'][1]['invasion_enemy']=0;d['slots'][2]['starting_funds']=4000;validate(d)
        rows=layout(d).splitlines()
        self.assertEqual(rows[-4:],['FUNDS 1','player3 4000','ENEMIES 1','player2 0'])

    def test_positional_sections_filled_without_invasions(self):
        d=scenario()
        for s in d['slots']:s.pop('invasions',None);s.pop('events',None);s.pop('governance',None)
        d['slots'][0]['invasion_enemy']=5;validate(d)
        rows=layout(d).splitlines()
        for tag in ('GOVERNANCE 0','EVENTS 0','INVASIONS 0'):self.assertIn(tag,rows)
        self.assertEqual(rows[-2:],['ENEMIES 1','player1 5'])

    def test_range_checked(self):
        for bad in (-1,20,'3',None):
            d=scenario();d['slots'][0]['invasion_enemy']=bad
            with self.assertRaises(ValueError):validate(d)

    def test_kept_with_the_city_settings(self):
        import scenario_cities
        self.assertIn('invasion_enemy',scenario_cities.SETTINGS)

class PeoplePerAttack(unittest.TestCase):
    """Each attack may name its people (user 2026-11-15); one people per month."""
    def test_raiders_section_after_enemies(self):
        d=scenario();s=d['slots'][0];s['invasion_enemy']=9
        s['invasions']=[dict(month=12,amount=40,point=0,target=4,enemy=12),dict(month=24,amount=30,point=0,target=4),dict(month=36,amount=50,point=0,target=4,enemy=3)]
        validate(d);rows=layout(d).splitlines()
        self.assertEqual(rows[-5:],['ENEMIES 1',s['id']+' 9','RAIDERS 2',s['id']+' 0 12',s['id']+' 2 3'])
    def test_no_raiders_when_no_attack_names_one(self):
        d=scenario();d['slots'][0]['invasions']=[dict(month=12,amount=40,point=0,target=4)];validate(d)
        self.assertNotIn('RAIDERS',layout(d))
    def test_one_people_per_month(self):
        d=scenario();s=d['slots'][0]
        s['invasions']=[dict(month=12,amount=40,point=0,target=4,enemy=12),dict(month=12,amount=30,point=0,target=4,enemy=9)]
        with self.assertRaises(ValueError):validate(d)
        s['invasions'][1]['enemy']=12;validate(d)                               # the same people twice: fine
        del s['invasions'][1]['enemy']                                          # the city's people (the map's own) vs Gauls
        with self.assertRaises(ValueError):validate(d)
        s['invasion_enemy']=12;validate(d)                                      # the city's people is Gauls: fine
        s['invasions'][0]['enemy']=13;validate(d)                               # Helvetii look like Gauls: fine
        s['invasions'][0]['enemy']=0;s['invasions'][1]['enemy']=16;validate(d)  # barbarians and Huns: one picture file
    def test_range(self):
        for bad in (-1,20,'3'):
            d=scenario();d['slots'][0]['invasions']=[dict(month=12,amount=40,point=0,target=4,enemy=bad)]
            with self.assertRaises(ValueError):validate(d)

if __name__=='__main__':unittest.main()
