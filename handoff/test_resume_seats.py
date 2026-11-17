"""Resuming a joint save offers every seat of the original scenario (restore_expansion): the saved cities stay, the
other seats can be taken by new players with fresh cities. The waiting room map and scenario text must show those
free seats as seats, not as neutral cities (user report 2026-11-13: a six-city map played by two, resumed, showed
only the two saved cities)."""
import json,sqlite3,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];A=ROOT/'Augustus'
sys.path.insert(0,str(A))
import lobby_map
from scenario_project import load
from room_roster import effective_project

class ResumeSeats(unittest.TestCase):
    def room(self,folder,cities,original=True):
        six=load(A/'scenarios/provincial-sextet/scenario.json')
        two,_=effective_project(six,['player3','player4'])
        (folder/'scenario-project.json').write_text(json.dumps(two,ensure_ascii=False),encoding='utf8')
        if original:(folder/'scenario-original.json').write_text(json.dumps(six,ensure_ascii=False),encoding='utf8')
        db=sqlite3.connect(folder/'room.sqlite');db.execute('CREATE TABLE scenario_binding(value TEXT)')
        db.execute('INSERT INTO scenario_binding VALUES(?)',(json.dumps(dict(cities=cities)),));db.commit();db.close()
        return folder/'room.sqlite'
    def seats(self,rows):return sorted(r['id'] for r in rows if r.get('id'))
    def test_resumed_room_shows_every_seat(self):
        with tempfile.TemporaryDirectory() as t:
            path=self.room(Path(t),[f'player{i}' for i in range(1,7)])
            self.assertEqual(lobby_map.room_project(path).name,'scenario-original.json')
            self.assertEqual(self.seats(lobby_map.load(path)),[f'player{i}' for i in range(1,7)])
            self.assertIn('린둠',lobby_map.briefing(path))                     # a free seat's city is in the scenario text
    def test_started_room_shows_the_played_roster(self):
        with tempfile.TemporaryDirectory() as t:
            path=self.room(Path(t),['player3','player4'])                   # roster written back after the start
            self.assertEqual(lobby_map.room_project(path).name,'scenario-project.json')
            self.assertEqual(self.seats(lobby_map.load(path)),['player3','player4'])
    def test_plain_room_unchanged(self):
        with tempfile.TemporaryDirectory() as t:
            path=self.room(Path(t),['player3','player4'],original=False)
            self.assertEqual(lobby_map.room_project(path).name,'scenario-project.json')
    def test_unreadable_room_falls_back(self):
        with tempfile.TemporaryDirectory() as t:
            path=self.room(Path(t),[f'player{i}' for i in range(1,7)]);path.write_bytes(b'not a database')
            self.assertEqual(lobby_map.room_project(path).name,'scenario-project.json')

if __name__=='__main__':unittest.main()
