"""기한 경쟁 (deadline race, 2026-11-15): after `months` months the city with the most of one figure wins.

The room judges it with the shared samples of the cooperative goals (objectives.py): each sample before the deadline
only updates the standing; the first complete sample at or after months*800 ticks decides, a tie shares the win, and
play goes on. Here the room is a stand-in (the clock, the cities' progress and the database the room keeps); the
scenario side is the real one (scenario_project, scenario_pair binding, scenario_overview)."""
import json,sqlite3,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'Augustus'))
import objectives

def stats(prosperity,population=1000):return dict(population=population,culture=10,prosperity=prosperity,peace=10,favor=50,treasury=5000)

class Coordinator:
    def __init__(self,cities):self.scenario=dict(cities=cities,city_names={'p1':'카푸아','p2':'타렌툼','p3':'메디올라눔'})
class Room:
    def __init__(self,cities):self.coordinator=Coordinator(cities);self.started=True;self.grant=0;self.progress={};self.now=100.0
    def clock(self):return self.now
    def active_cities(self,db):return list(self.coordinator.scenario['cities'])

class Race(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row
        self.db.execute('CREATE TABLE joint_save(id INTEGER)')
        self.db.execute("CREATE TABLE chat(id INTEGER PRIMARY KEY,city TEXT,message_id TEXT,text TEXT,sender TEXT)")
        self.db.execute('CREATE TABLE notification_event(key TEXT PRIMARY KEY)')
        objectives.initialize(self.db)
        self.cities=['p1','p2','p3'];self.room=Room(self.cities)
        binding=dict(cities=self.cities,objectives=dict(population_total=0,per_city={},race=dict(stat='prosperity',months=6)))
        objectives.configure(self.db,binding,0)
    def sample(self,tick,values):
        """Every shared check up to `tick` (one each 400 ticks, as the room runs them), the cities reporting `values`."""
        start=getattr(self,'reached',-objectives.INTERVAL)+objectives.INTERVAL
        for t in range(start,tick+1,objectives.INTERVAL):
            self.room.grant=t;self.room.progress={c:(t,self.room.now) for c in self.cities}
            for c in self.cities:result=objectives.submit(self.room,self.db,c,dict(ticks=t,stats=values[c]))
        self.reached=tick;return result
    def test_standing_then_the_deadline_decides(self):
        before=self.sample(4400,dict(p1=stats(30),p2=stats(50),p3=stats(40)))
        self.assertIsNone(before['completed_tick']);self.assertEqual(before['mode'],'race')
        text=objectives.lines(before,self.room.coordinator.scenario['city_names'],'p1')
        self.assertTrue(text.startswith('기한 경쟁'));self.assertLess(text.index('타렌툼'),text.index('메디올라눔'))   # ranking: 1위 p2
        self.assertEqual(self.db.execute('SELECT count(*) FROM chat').fetchone()[0],0)
        done=self.sample(4800,dict(p1=stats(60),p2=stats(55),p3=stats(10)))                     # 6 months: the deadline
        self.assertEqual(done['completed_tick'],4800)
        message=self.db.execute('SELECT text FROM chat').fetchone()[0]
        self.assertIn('승리: 카푸아',message);self.assertIn('번영 60',message);self.assertNotIn('타렌툼',message)
        later=self.sample(5200,dict(p1=stats(0),p2=stats(90),p3=stats(90)))                    # play goes on; the result stays
        self.assertEqual(later['completed_tick'],4800);self.assertEqual(self.db.execute('SELECT count(*) FROM chat').fetchone()[0],1)
    def test_a_tie_shares_the_win(self):
        self.sample(4800,dict(p1=stats(70),p2=stats(70),p3=stats(20)))
        message=self.db.execute('SELECT text FROM chat').fetchone()[0];self.assertIn('카푸아, 타렌툼',message)
    def leave(self,city):
        """The player of `city` leaves the room for good (lobby.py: departed_invite), as the room records it."""
        self.db.execute('CREATE TABLE IF NOT EXISTS lobby_invite(token TEXT,city TEXT)');self.db.execute('CREATE TABLE IF NOT EXISTS departed_invite(token TEXT)')
        for c in self.cities:
            if not self.db.execute('SELECT 1 FROM lobby_invite WHERE city=?',(c,)).fetchone():self.db.execute('INSERT INTO lobby_invite VALUES(?,?)',('t-'+c,c))
        self.db.execute('INSERT INTO departed_invite VALUES(?)',('t-'+city,))
        self.room.active_cities=lambda db,gone=city:[c for c in self.cities if c!=gone]
    def test_a_city_whose_player_left_is_not_judged(self):
        # user 2026-11-15: "나간도시를 빼고 판정해줘" - before, the race waited for that city for good
        self.sample(2000,dict(p1=stats(30),p2=stats(50),p3=stats(90)))
        self.leave('p3');self.cities=['p1','p2']                                                 # p3 reports no more
        done=self.sample(4800,dict(p1=stats(60),p2=stats(55)))
        self.assertEqual(done['completed_tick'],4800);self.assertEqual(done['left'],['p3'])
        message=self.db.execute('SELECT text FROM chat').fetchone()[0]
        self.assertIn('승리: 카푸아',message);self.assertNotIn('메디올라눔',message)
    def test_the_standing_leaves_out_a_city_that_left(self):
        self.sample(2000,dict(p1=stats(30),p2=stats(50),p3=stats(90)))
        self.leave('p3')
        text=objectives.lines(objectives.status(self.room,self.db),self.room.coordinator.scenario['city_names'],'p1')
        self.assertIn('나간 도시는 판정에서 뺍니다: 메디올라눔',text);self.assertNotIn('위 메디올라눔',text)
        self.assertNotIn('판정 대기',text)
    def test_a_city_taken_again_is_judged_again(self):
        self.leave('p3');self.db.execute('INSERT INTO lobby_invite VALUES(?,?)',('t-new','p3'))           # another player took it
        self.assertEqual(objectives.departed(self.room,self.db),set())
    def test_rules_are_checked(self):
        for race in (dict(stat='rome',months=12),dict(stat='prosperity',months=3),dict(stat='prosperity')):
            with self.assertRaises(ValueError):objectives.validate_rules(dict(population_total=0,per_city={},race=race),self.cities)

class CooperativeLeft(Race):
    """The same rule for cooperative goals: the goals of a city whose player left are not judged."""
    def setUp(self):
        super().setUp()
        self.db.execute('DELETE FROM objective_state')
        binding=dict(cities=self.cities,objectives=dict(population_total=0,per_city=dict(p1=dict(population=0,culture=0,prosperity=50,peace=0,favor=0,treasury=0),
                                                                                       p3=dict(population=0,culture=0,prosperity=80,peace=0,favor=0,treasury=0))))
        objectives.configure(self.db,binding,0)
    def test_goals_of_a_city_that_left_are_not_judged(self):
        self.sample(800,dict(p1=stats(60),p2=stats(0),p3=stats(10)))
        self.assertIsNone(objectives.state(self.db)['completed_tick'])                          # p3 short of 80
        self.leave('p3');self.cities=['p1','p2']
        done=self.sample(1600,dict(p1=stats(60),p2=stats(0)))
        self.assertEqual(done['completed_tick'],1200)                                             # the first check after p3 left
        text=objectives.lines(dict(done,completed_tick=None),self.room.coordinator.scenario['city_names'],'p1')   # as shown before the end
        self.assertIn('플레이어가 나가서 이 도시의 조건은 판정하지 않습니다.',text)
    test_standing_then_the_deadline_decides=test_a_tie_shares_the_win=test_a_city_whose_player_left_is_not_judged=test_the_standing_leaves_out_a_city_that_left=None

class Scenario(unittest.TestCase):
    def test_file_binding_and_overview(self):
        import scenario_project as sp,scenario_pair,scenario_overview,creator_presets
        data=json.loads((ROOT/'Augustus/scenarios/freebuild-6p/scenario.json').read_text(encoding='utf-8-sig'))
        data['rules']['mode']='deadline-race';data['rules']['race']=dict(stat='population',months=120);sp.validate(data);sp.require_runtime(data)
        self.assertEqual(sp.min_players(data),2)
        lines=scenario_overview.overview(data,creator_presets.catalog())['briefing']
        self.assertTrue(any('120개월이 지났을 때 인구 값이 가장 높은 도시가 승리합니다' in l for l in lines))
        data['rules']['race']=dict(stat='population',months=1)
        with self.assertRaises(ValueError):sp.validate(data)
        data['rules'].pop('race')
        with self.assertRaises(ValueError):sp.validate(data)
    def test_binding(self):
        src=(ROOT/'Augustus/scenario_pair.py').read_text(encoding='utf-8')
        self.assertIn("binding['objectives']=dict(population_total=0,per_city={},race=manifest['rules']['race'])",src)

sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_default_rooms as R
F=R.F
@unittest.skipUnless(F.DATA and R.NAMES and F.native_library(1),'needs AUGUSTUS_C3_DATA and the real post_* C library: '+F._why)
class RaceRoom(R.DefaultRooms):
    """A real room on a 기한 경쟁 scenario (the parts of test_default_rooms): two players start and the room keeps the race."""
    def open(self,name,seats):
        import tempfile,shutil
        from unittest.mock import patch
        folder=Path(tempfile.mkdtemp());self.addCleanup(lambda:shutil.rmtree(folder,ignore_errors=True))
        data=json.loads((ROOT/'Augustus/scenarios/freebuild-6p/scenario.json').read_text(encoding='utf-8-sig'))
        data['rules']['mode']='deadline-race';data['rules']['race']=dict(stat='prosperity',months=6)
        project=folder/'scenario.json';project.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
        p=patch.object(F,'PROJECT',project);p.start();self.addCleanup(p.stop)
        self.scenario=data
        for i,slot in enumerate(data['slots']):
            if i>=4:self.cities[slot['id']]=F.City(i+1,F.FUNDS)
        room=self.make_room('race-'+str(len(seats)))
        return room,{city:self.bridge(room,i,city) for i,city in enumerate(seats)}
    def test_two_players_race(self):
        room,bridges,frozen=self.run_one('race',['player2','player5'])
        self.assertEqual(frozen['objectives']['race'],dict(stat='prosperity',months=6))
        status=bridges['player2'].client.call('objective_status');self.assertEqual(status['mode'],'race')
    def test_alone_is_refused(self):
        room,bridges=self.open('race',['player1'])
        h=bridges['player1'];view=h.client.call('lobby_view',invite=h.config['invite']);opts=view['room_options']
        if not opts['initialized']:opts=h.client.call('room_options_set',invite=h.config['invite'],revision=opts['revision'],values=opts['values'])
        h.client.call('room_options_ack',invite=h.config['invite'],revision=opts['revision']);h.client.call('lobby_ready',ready=True)
        with self.assertRaisesRegex(ValueError,'needs players 2'):h.client.call('room_start')
for _name in [n for n in dir(R.DefaultRooms) if n.startswith('test_')]:setattr(RaceRoom,_name,None)

if __name__=='__main__':unittest.main()
