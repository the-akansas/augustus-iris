"""Lobby city choice: no duplicate city, and a changed choice or changed room options never keep an old 'ready'.
Uses the real Lobby and Coordinator with the review151 fixture saves. Needs the game data (AUGUSTUS_C3_DATA)."""
import json,os,sys,tempfile,unittest,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Augustus'))
DATA=os.environ.get('AUGUSTUS_C3_DATA')
FIXTURE=ROOT/'handoff/review151'

@unittest.skipUnless(DATA and (FIXTURE/'scenario.json').is_file() and (FIXTURE/'prepared-1/checked/city.sav').is_file(),'game data and review151 fixtures required')
class LobbySelection(unittest.TestCase):
    def setUp(self):
        from coordinator import Coordinator,PROTOCOL,BUILD
        from lobby import Lobby
        from scenario_project import load,write_layout
        from scenario_pair import load_pair
        import room_options
        self.dir=tempfile.TemporaryDirectory();self.addCleanup(self.dir.cleanup);run=Path(self.dir.name)
        manifest=load(FIXTURE/'scenario.json');_,binding=load_pair(Path(DATA),manifest)
        write_layout(manifest,run);(run/'scenario-project.json').write_text(json.dumps(manifest,ensure_ascii=False),encoding='utf8')
        co=Coordinator(run/'room.sqlite',uuid.uuid4().hex,binding)
        for i,c in enumerate(binding['cities'],1):
            f=FIXTURE/f'prepared-{min(i,3)}/checked';co.provision(c,(f/'city.sav').read_bytes(),(f/'receipt.bin').read_bytes())
        import network_diagnostics
        self.addCleanup(lambda:self.assertTrue(network_diagnostics.flush(5),'diagnostic writer did not finish before cleanup'))
        self.lobby=Lobby(co);self.cities=binding['cities'];self.defaults=[s['default'] for s in room_options.SCHEMA]
        self.call=lambda r:self.lobby.request(dict(r,protocol=PROTOCOL,build=BUILD,session=co.session,scenario=co.wire_scenario))
    def slots(self,city,token):return {s['city']:(s['claimed'],s['ready']) for s in self.call(dict(op='lobby_status',city=city,token=token))['slots']}
    def ready(self,city,invite,token):
        revision=self.call(dict(op='room_options_ack',city=city,invite=invite,revision=self.revision))['revision']
        return self.call(dict(op='lobby_ready',city=city,token=token,ready=True))
    def test_duplicate_switch_and_options(self):
        a,b,c=self.cities[:3];host,guest=self.lobby.invite(),self.lobby.invite()
        ta=self.call(dict(op='lobby_join',city=a,invite=host))['token']
        self.revision=self.call(dict(op='room_options_set',city=a,invite=host,revision=0,values=self.defaults))['revision']
        tb=self.call(dict(op='lobby_join',city=b,invite=guest))['token']
        with self.assertRaises(ValueError) as e:self.call(dict(op='lobby_join',city=a,invite=guest))
        self.assertIn('occupied',str(e.exception))                                   # one city, one player
        self.ready(b,guest,tb);self.assertEqual(self.slots(b,tb)[b],(True,True))
        tb=self.call(dict(op='lobby_join',city=c,invite=guest))['token']               # changes city
        s=self.slots(c,tb);self.assertEqual((s[b],s[c]),((False,False),(True,False)))  # old city freed, ready cleared
        self.ready(c,guest,tb);self.assertTrue(self.slots(c,tb)[c][1])
        values=list(self.defaults);values[0]=(values[0]+1)%2
        self.revision=self.call(dict(op='room_options_set',city=a,invite=host,revision=self.revision,values=values))['revision']
        self.assertFalse(self.slots(c,tb)[c][1])                                      # new room conditions: ready again needed
        with self.assertRaises(ValueError):self.call(dict(op='lobby_ready',city=c,token=tb,ready=True))   # not before acknowledging them

if __name__=='__main__':unittest.main()
