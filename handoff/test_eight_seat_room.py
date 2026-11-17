"""Eight seats, at most six players (user 2026-11-15: "8자리 중 최대 6명이 골라서 플레이합니다").

A scenario may offer up to eight player cities so the players have more to choose from; at most MAX_ONLINE_PLAYERS
(6) play. Before, a scenario with more than six seats was refused for play altogether (scenario_project.require_runtime).
Here the free-build scenario gets two more seats (the two extra cities of creator_presets.default_project(8)) and is
run in a real room with the parts of test_default_rooms: two players start and the six seats nobody took become
neutral; the start is refused for seven players. Same needs as test_default_rooms (AUGUSTUS_C3_DATA, the C library)."""
import copy,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_default_rooms as R
F=R.F
A=F.ROOT/'Augustus'
sys.path.insert(0,str(A))

def eight_seats():
    import creator_presets,scenario_project as sp
    data=json.loads((A/'scenarios'/'freebuild-6p'/'scenario.json').read_text(encoding='utf-8-sig'))
    extra=creator_presets.default_project(8)
    for slot in extra['slots'][6:]:
        slot=copy.deepcopy(slot);slot['allowed_buildings']=list(data['slots'][0]['allowed_buildings']);slot.pop('governance',None)
        data['slots'].append(slot)
        city=next(c for c in data['empire']['cities'] if c['name_id']==slot['name_id'])
        mine=next(c for c in extra['empire']['cities'] if c['name_id']==slot['name_id'])
        city.clear();city.update(copy.deepcopy(mine))
    sp.validate(data);return data

class Rules(unittest.TestCase):
    def test_eight_seats_may_be_played(self):
        import scenario_project as sp
        data=eight_seats();self.assertEqual(len(data['slots']),8)
        sp.require_runtime(data)                                       # refused before 2026-11-15
    def test_room_roster_takes_at_most_six(self):
        import room_roster
        data=eight_seats();ids=[s['id'] for s in data['slots']]
        self.assertEqual(len(room_roster.effective_project(data,ids[:6])[0]['slots']),6)
        with self.assertRaisesRegex(ValueError,'participant required'):room_roster.effective_project(data,ids[:7])

@unittest.skipUnless(F.DATA and R.NAMES and F.native_library(1),'needs AUGUSTUS_C3_DATA and the real post_* C library: '+F._why)
class EightSeatRoom(R.DefaultRooms):
    def open(self,name,seats):
        folder=Path(tempfile.mkdtemp());self.addCleanup(lambda:__import__('shutil').rmtree(folder,ignore_errors=True))
        project=folder/'scenario.json';project.write_text(json.dumps(eight_seats(),ensure_ascii=False),encoding='utf-8')
        p=patch.object(F,'PROJECT',project);p.start();self.addCleanup(p.stop)
        self.scenario=json.loads(project.read_text(encoding='utf-8'))
        for i,slot in enumerate(self.scenario['slots']):
            if i>=4:self.cities[slot['id']]=F.City(i+1,F.FUNDS)
        room=self.make_room('eight-'+str(len(seats)))
        return room,{city:self.bridge(room,i,city) for i,city in enumerate(seats)}
    def test_two_players_on_eight_seats(self):
        room,bridges,frozen=self.run_one('eight',['player8','player3'])
        self.assertEqual(sorted(frozen['cities']),['player3','player8'])
    def test_seven_players_are_refused(self):
        seats=['player%d'%i for i in range(1,8)]
        room,bridges=self.open('eight',seats)
        h=bridges[seats[0]];view=h.client.call('lobby_view',invite=h.config['invite']);opts=view['room_options']
        if not opts['initialized']:opts=h.client.call('room_options_set',invite=h.config['invite'],revision=opts['revision'],values=opts['values'])
        for b in bridges.values():b.client.call('room_options_ack',invite=b.config['invite'],revision=opts['revision'])
        for b in bridges.values():b.client.call('lobby_ready',ready=True)
        with self.assertRaisesRegex(ValueError,'too many players'):h.client.call('room_start')

    def test_at_most_six_come_in(self):
        # 2026-11-15: an eight-seat room let eight people in and then refused the start for everybody
        import room_host,uuid
        from coordinator import PROTOCOL,BUILD
        folder=Path(tempfile.mkdtemp());self.addCleanup(lambda:__import__('shutil').rmtree(folder,ignore_errors=True))
        project=folder/'scenario.json';project.write_text(json.dumps(eight_seats(),ensure_ascii=False),encoding='utf-8')
        data=json.loads(project.read_text(encoding='utf-8'))
        for i,slot in enumerate(data['slots']):self.cities[slot['id']]=F.City(i+1,F.FUNDS)
        saves={c:city.save() for c,city in self.cities.items()}
        with patch.object(room_host,'Engine',F.fake_engine(saves)),patch.object(room_host,'verify_city',lambda *a:None):
            server=room_host.create_room(folder/'room',project=project)
        self.addCleanup(server.server_close)
        info=server.public_info(dict(op='public_info',version=1));self.assertEqual(info['maximum'],6)
        ask=lambda:server.public_join(dict(op='public_join',protocol=PROTOCOL,build=BUILD,engine_sha256=info['engine_sha256'],client_id=uuid.uuid4().hex))
        for _ in range(5):ask()                                         # the host and five guests
        with self.assertRaisesRegex(ValueError,'room full'):ask()

# the cases of the parent classes are not repeated here
for _name in [n for n in dir(R.DefaultRooms) if n.startswith('test_')]:
    setattr(EightSeatRoom,_name,None)

if __name__=='__main__':unittest.main()
