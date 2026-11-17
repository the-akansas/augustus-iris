"""2·4·6-player free-build drafts (tools/make_free_build_drafts.py): valid, built only from the shipped default, and
kept as drafts. The listed defaults are made from them by tools/make_default_scenarios.py (test_default_scenarios.py)."""
import json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Augustus'));sys.path.insert(0,str(ROOT/'tools'))
import scenario_project as sp,scenario_check as sc,make_free_build_drafts as mk
BASE=ROOT/'Augustus/scenarios/unified-sandbox/scenario.json'
def draft(n):return ROOT/f'Augustus/scenario-drafts/free-build-{n}/scenario.json'

class Drafts(unittest.TestCase):
    def setUp(self):self.base=json.loads(BASE.read_text(encoding='utf-8-sig'))
    def test_files_are_valid_and_current(self):
        for n in (2,4,6):
            d=sp.load(draft(n));sp.require_runtime(d);sp.layout(d)
            self.assertEqual(d,mk.draft(self.base,n))                       # the file is what the generator makes now
            self.assertEqual(len(d['slots']),n)
            self.assertEqual(sc.check_file(draft(n))['counts']['block'],0)
    def test_settings_come_from_the_default(self):
        for n in (2,4,6):
            d=sp.load(draft(n))
            self.assertEqual(d['rules'],self.base['rules']);self.assertEqual(d['empire']['template'],self.base['empire']['template'])
            for s in d['slots']:self.assertEqual(s['allowed_buildings'],self.base['slots'][0]['allowed_buildings'])
            self.assertEqual([s['name_id'] for s in d['slots']][:min(n,4)],[s['name_id'] for s in self.base['slots']][:min(n,4)])
            changed={c['name_id'] for c,o in zip(d['empire']['cities'],self.base['empire']['cities']) if c!=o}
            self.assertEqual(changed,{2:{4,10},4:set(),6:{6,7}}[n])
        six={c['name_id']:c for c in sp.load(draft(6))['empire']['cities']};old={c['name_id']:c for c in self.base['empire']['cities']}
        for i in (6,7):self.assertEqual(six[i]['parked_trade'],{k:old[i][k] for k in ('sea','cost','sells','buys')})
    def test_drafts_stay_out_of_the_lobby(self):
        src=(ROOT/'Augustus/network_play.py').read_text(encoding='utf8')
        self.assertNotIn('scenario-drafts',src)                                    # the lobby reads the default list, never the draft folder
        self.assertFalse(list((ROOT/'Augustus/scenarios').rglob('free-build-*')))
        self.assertEqual(json.loads(BASE.read_text(encoding='utf-8-sig'))['id'],'unified-sandbox')

if __name__=='__main__':unittest.main()
