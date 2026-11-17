"""Windows editor data regression. No GUI constructors, clicks or input.

Run after build_creator.py and copying its EXE/config into Augustus.
Uses an isolated copy of that actual assembly, not a mock editor.
"""
import json,os,shutil,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Augustus'))
import creator_presets as cp,scenario_project as sp,scenario_cities as cities

class EditorLogic(unittest.TestCase):
    def test_empty_trade_survives_python_to_csharp_boundary(self):
        p=cp.default_project(4)
        c=next(c for c in p['empire']['cities'] if c['role']=='npc' and not c.get('reserved') and cities.status(p,c['name_id'])['eligible'])
        c.update(sea=0,cost=0,sells={},buys={})
        c.pop('trade_players',None);c.pop('sea_auto',None)
        q=cities.swap_city(p,p['slots'][0]['id'],c['name_id'])
        kept=cities.find(q,c['name_id'])['parked_trade']
        self.assertEqual(kept,dict(sea=0,cost=0,sells={},buys={}))
        sp.validate(q)
        restored=cities.swap_city(q,p['slots'][0]['id'],p['slots'][0]['name_id'])
        actual=cities.find(restored,c['name_id'])
        self.assertEqual({k:actual[k] for k in cities.TRADE},kept)

    @unittest.skipUnless(os.name=='nt','Actual .NET Framework executable requires Windows')
    def test_actual_csharp_assembly(self):
        csc=Path(os.environ.get('WINDIR',r'C:\Windows'))/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
        self.assertTrue(csc.is_file(),'C# compiler required; not treated as a pass')
        with tempfile.TemporaryDirectory(prefix='augustus-logic-') as tmp:
            out=Path(tmp)
            shutil.copy2(ROOT/'Augustus/Augustus-Scenario-Creator.exe',out)
            p=cp.default_project(4);reserved=next(c for c in p['empire']['cities'] if c['role']=='npc')
            reserved.update(reserved=True,enabled=True,sea=0,cost=0,sells={},buys={},trade_players=[])
            sp.validate(p);fixture=out/'fixture.json';fixture.write_bytes(sp.canonical(p))
            for name in ('LogicProbe','Regression','SlotProbe'):
                subprocess.run([str(csc),'/nologo','/r:'+str(out/'Augustus-Scenario-Creator.exe'),'/r:System.Web.Extensions.dll','/r:System.Windows.Forms.dll','/out:'+str(out/(name+'.exe')),str(ROOT/'handoff'/(name+'.cs'))],check=True,capture_output=True)
                target=out/'roundtrip.json' if name=='LogicProbe' else out/'results' if name=='Regression' else out/'slot'
                r=subprocess.run([str(out/(name+'.exe')),str(fixture),str(target)],capture_output=True,text=True,encoding='utf8',check=True)
                result=json.loads(r.stdout)
                rows=result if isinstance(result,list) else result['results']
                self.assertTrue(all(x['passed'] for x in rows),rows)
                print(name+': '+str(len(rows))+' checks passed',flush=True)
            restored=sp.load(out/'roundtrip.json')
            self.assertEqual(sp.layout(p),sp.layout(restored))
            deleted=sp.load(out/'results/removed-player.json')
            self.assertEqual(len(deleted['slots']),3)
            self.assertNotIn('player1',deleted['rules']['objectives']['per_city'])
            funds=sp.load(out/'slot/funds.json');self.assertEqual([s.get('starting_funds') for s in funds['slots']][:2],[0,25000])
            pairs=sp.load(out/'slot/pairs.json');self.assertEqual(pairs['rules']['player_trade']['exceptions'],[dict(between=['player1','player3'],allow=False),dict(between=['player2','player4'],allow=False)])

if __name__=='__main__':unittest.main(verbosity=2)
