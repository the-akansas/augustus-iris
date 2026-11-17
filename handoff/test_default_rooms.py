"""The three built-in scenarios in a real room, started with fewer players than seats (user report 2026-11-14).

What happened: a two-player room on a six-seat scenario refused "게임 시작" with 'invalid_request'. The cities nobody
took become neutral when the roster is frozen, and a record the free-build map keeps on its player cities
('parked_trade') made the frozen scenario invalid. No test started a room with empty seats, so nothing caught it.

Here every listed default (Augustus/default-scenarios.json) is run with the same real parts as test_throne_room_flow
(room_host.create_room, the room server over TCP, game_bridge.Bridge, the C money mailbox): the players join, take
cities that are NOT the first seats, get ready, the host starts, the cities load, play begins and the clock runs.
Checked: the room starts; exactly the taken cities play; every player gets the scenario's start message; the mode
is what the scenario says (free build, joint goals with the totals for that number of players, throne with its box
and one coup payment going through). Stand-ins are those of test_throne_room_flow (no engine process, no window).
Needs AUGUSTUS_C3_DATA and a C compiler or AUGUSTUS_POST_NATIVE_DIR; set AUGUSTUS_SRC_ROOT to the full game source
when this tree only holds the changes."""
import json,sys,time,unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
TEST_TOOLS=(Path(__file__).resolve().parents[1]/'Augustus'/'mp_test_tools.py').is_file()   # the test launcher's tools: in no release, not in the public source
needs_test_tools=unittest.skipUnless(TEST_TOOLS,'needs the test launcher tools (Augustus/mp_test_tools.py), which are not in this copy')
import test_throne_room_flow as F

A=F.ROOT/'Augustus'
try:NAMES=json.loads((A/'default-scenarios.json').read_text(encoding='utf8'))['scenarios']
except OSError:NAMES=[]

@unittest.skipUnless(F.DATA and NAMES and F.native_library(1),'needs AUGUSTUS_C3_DATA and the real post_* C library: '+F._why)
class DefaultRooms(F.RoomFlow):
    def setUp(self):
        super().setUp()
        # Every request the room refuses is kept: a refusal the player would see as "요청을 처리하지 못했습니다" must not
        # happen in an ordinary game (the solo cash report did, every few seconds).
        import coordinator,traceback
        handler=next(c for c in vars(coordinator).values() if isinstance(c,type) and hasattr(c,'refusal'))
        self.refused=[];real=handler.refusal
        def refusal(this,error):
            self.refused.append(''.join(traceback.format_exception(error))[-600:]);return real(this,error)
        p=patch.object(handler,'refusal',refusal);p.start();self.addCleanup(p.stop)
    def open(self,name,seats):
        """A room on scenario `name`; `seats` = the cities taken, the first one by the host."""
        project=A/'scenarios'/name/'scenario.json'
        p=patch.object(F,'PROJECT',project);p.start();self.addCleanup(p.stop)
        self.scenario=json.loads(project.read_text(encoding='utf-8-sig'))
        for i,slot in enumerate(self.scenario['slots']):
            if i>=4:self.cities[slot['id']]=F.City(i+1,F.FUNDS)       # make_room prepares the first four stand-in cities
        room=self.make_room(name+'-'+str(len(seats)))
        bridges={city:self.bridge(room,i,city) for i,city in enumerate(seats)}
        return room,bridges
    def begin(self,room,bridges,host):
        """What the waiting room does: options confirmed and acknowledged, everybody ready, the host starts."""
        h=bridges[host];view=h.client.call('lobby_view',invite=h.config['invite']);opts=view['room_options']
        if not opts['initialized']:
            opts=h.client.call('room_options_set',invite=h.config['invite'],revision=opts['revision'],values=opts['values'])
        for b in bridges.values():b.client.call('room_options_ack',invite=b.config['invite'],revision=opts['revision'])
        for b in bridges.values():b.client.call('lobby_ready',ready=True)
        # Empty seats: the room rebuilds the start saves for the cities that play (room_roster.begin, a thread that runs
        # the city engine). The engine is the same stand-in make_room uses; everything around it is the real code.
        import city_client,scenario_pair
        saves={c:city.save() for c,city in self.cities.items()}
        for target,name,value in ((city_client,'Engine',F.fake_engine(saves)),(scenario_pair,'verify_city',lambda *a:None)):
            p=patch.object(target,name,value);p.start();self.addCleanup(p.stop)
        start=h.client.call('room_start').get('start') or {}                   # the call that answered 'invalid_request'
        deadline=time.time()+40
        while not start.get('attempt') and time.time()<deadline:               # the roster job, then the start attempt
            time.sleep(0.25);start=h.client.call('lobby_status').get('start') or {}
        self.assertTrue(start.get('attempt'),'no start attempt: '+self.roster_error(room))
        from coordinator import sha
        deadline=time.time()+30;loaded=set()
        while not room['room'].started and time.time()<deadline:
            with closing(room['room'].coordinator.connect()) as db:
                for c,b in bridges.items():
                    row=db.execute('SELECT save FROM city WHERE id=?',(c,)).fetchone()
                    status=b.client.call('lobby_status')
                    if c not in loaded and row and status.get('start',{}).get('phase') not in (None,'lobby','preparing'):
                        try:b.client.call('start_loaded',attempt=start['attempt'],layout=start['layout'],save_hash=sha(row[0]));loaded.add(c)
                        except ValueError:pass
            time.sleep(0.25)
        self.assertTrue(room['room'].started,'the room did not start: '+self.roster_error(room))
        return {c:b.client.call('play_begin') for c,b in bridges.items()}

    def roster_error(self,room):
        try:return (room['root']/'roster-error.txt').read_text(encoding='utf8')
        except OSError:return '(no roster error recorded)'

    def run_one(self,name,seats):
        room,bridges=self.open(name,seats);begun=self.begin(room,bridges,seats[0])
        frozen=room['room'].coordinator.scenario
        self.assertEqual(sorted(frozen['cities']),sorted(seats),name)
        want=self.scenario.get('start_message',{}).get('common')
        for c,answer in begun.items():self.assertEqual((answer.get('start_message') or {}).get('body','').split('\n')[0],want.split('\n')[0],(name,c))
        self.clock(room,bridges,1600);self.pump(bridges)
        self.assertEqual(self.refused,[],name)
        return room,bridges,frozen

    def test_free_build_with_two_and_one(self):
        self.run_one('freebuild-6p',['player2','player6'])
    def test_free_build_alone(self):
        self.run_one('freebuild-6p',['player4'])
    def test_joint_victory_with_two_takes_the_two_player_totals(self):
        room,bridges,frozen=self.run_one('coop-6p',['player2','player6'])
        self.assertEqual(frozen['objectives']['population_total'],3000)      # 2 x 1,500, not the six-city 9,000
        self.assertEqual(sorted(frozen['objectives']['per_city']),['player2','player6'])
    def test_joint_victory_alone(self):
        room,bridges,frozen=self.run_one('coop-6p',['player3'])
        self.assertEqual(frozen['objectives']['population_total'],1500)
    def test_throne_alone_runs_a_coup(self):
        # user 2026-11-15: alone is allowed (becoming emperor is the goal). The money leaves the player's own city with
        # nobody receiving it: the contract and the native receipt name the city itself (trade_post_ledger.stage_debit).
        room,bridges,frozen=self.run_one('throne-6p',['player5'])
        b=bridges['player5'];rules=self.scenario['rules']['throne']
        self.command(b,'coup');self.assertEqual(b.throne_ui['quote']['amount'],rules['stages'][0]['cost'])
        self.draws+=[0];before=self.cities['player5'].treasury
        self.command(b,'go');self.pump(bridges)
        own=self.own(b);self.assertEqual(own['last']['state'],'done')
        self.assertEqual(self.cities['player5'].treasury,before-rules['stages'][0]['cost'])
        self.assertEqual(own['stage'],1)                                     # the draw was set to succeed (TEST INPUT)
    def test_throne_with_two_runs_a_coup(self):
        room,bridges,frozen=self.run_one('throne-6p',['player2','player6'])
        b=bridges['player2'];rules=self.scenario['rules']['throne']
        self.assertIsNotNone(b.client.call('lobby_view',invite=b.config['invite']).get('throne'))
        box=(b.root/'throne-box.txt').read_text(encoding='utf8');self.assertIn('state\t',box)
        self.command(b,'coup');self.assertEqual(b.throne_ui['quote']['amount'],rules['stages'][0]['cost'])
        self.draws+=[0];before=self.cities['player2'].treasury
        self.command(b,'go');self.pump(bridges)
        own=self.own(b);self.assertEqual(own['last']['state'],'done')
        self.assertEqual(self.cities['player2'].treasury,before-rules['stages'][0]['cost'])
        self.assertEqual(own['stage'],1)                                     # the draw was set to succeed (TEST INPUT)
    def test_imperial_progress_needs_two_players(self):
        # user 2026-11-15: the scenario's author sets the fewest players; 황제의 순행 never starts alone
        room,bridges=self.open('progress-6p',['player3']);self.ready_all(bridges,'player3')
        with self.assertRaisesRegex(ValueError,'needs players 2'):bridges['player3'].client.call('room_start')
        self.assertFalse(room['room'].started)
    @needs_test_tools
    def test_imperial_progress_with_two_runs_a_bid_and_a_visit(self):
        # The whole round in a real room: announcement, one sealed bid from the game's dialog, the winner's debit
        # through the C money mailbox, the arrival order for the city's engine and its answer, the favour.
        import imperial_progress as ip
        room,bridges,frozen=self.run_one('progress-6p',['player2','player6'])
        b=bridges['player2'];other=bridges['player6'];lobby=room['room'];rules=self.scenario['rules']['progress']
        def state():
            with closing(lobby.coordinator.connect()) as db:return ip.current(db,lobby.coordinator.scenario)
        def skip():                                    # TEST INPUT: the waiting time of the current step is over
            with closing(lobby.coordinator.connect()) as db:__import__('mp_test_tools').progress_adjust(db,lobby.coordinator.scenario,'next');db.commit()
        self.assertEqual(sorted(state()['favor']),['player2','player6'])
        self.assertIn('state\tprogress',(b.root/'throne-box.txt').read_text(encoding='utf8'))
        self.assertIn('refuse\t',(b.root/'throne-prep-bid.txt').read_text(encoding='utf8'))      # no progress yet: the click says why
        skip();self.pump(bridges)
        self.assertEqual(state()['phase'],'bidding')
        prep=(b.root/'throne-prep-bid.txt').read_text(encoding='utf8')
        self.assertIn('kind\tbid',prep);self.assertIn('calc\tbid\t%d\t'%rules['min_bid'],prep)
        self.assertIn('황제의 순행 1/',(b.root/'throne-events.txt').read_text(encoding='utf8'))   # the announcement popup
        before=self.cities['player2'].treasury
        (b.root/'command.txt').write_text('throne\ngo\n%d\n900'%before,encoding='utf8');b.step()
        self.assertEqual(state()['bids']['player2']['amount'],900)
        self.assertEqual(self.cities['player2'].treasury,before)                              # a bid charges nothing
        self.assertIn('내 입찰\t900 Dn',(b.root/'throne-box.txt').read_text(encoding='utf8'))
        self.assertNotIn('900',(other.root/'throne-box.txt').read_text(encoding='utf8'))       # sealed
        skip();self.pump(bridges);self.pump(bridges)
        s=state();self.assertEqual((s['phase'],s['holder'],s['paid']),('travel','player2',900))
        self.assertEqual(self.cities['player2'].treasury,before-900)
        self.assertEqual(self.cities['player6'].treasury,F.FUNDS)
        skip();self.pump(bridges)
        s=state();self.assertEqual(s['phase'],'arrived')
        scope,owner,visit,resource,amount=(b.root/'emperor-visit-request.txt').read_text().split()
        self.assertEqual((int(visit),int(resource),int(amount)),(1,s['good'],s['amount']));self.assertTrue(rules['amount_min']<=s['amount']<=rules['amount_max'])
        self.assertEqual((other.root/'emperor-visit-request.txt').read_text() if (other.root/'emperor-visit-request.txt').exists() else '','')
        # the city's engine (stand-in: no engine process here) took everything
        (b.root/'emperor-visit.txt').write_text('%s %s %s %s %d\n'%(visit,resource,amount,amount,self.cities['player2'].treasury));self.pump(bridges)
        s=state();self.assertEqual((s['phase'],s['favor']),('idle',dict(player2=3,player6=0)))
        self.assertIn('총애 +3',(other.root/'throne-events.txt').read_text(encoding='utf8'))       # everyone hears the outcome
        self.assertEqual(self.refused,[])
    def ready_all(self,bridges,host):
        h=bridges[host];view=h.client.call('lobby_view',invite=h.config['invite']);opts=view['room_options']
        if not opts['initialized']:
            opts=h.client.call('room_options_set',invite=h.config['invite'],revision=opts['revision'],values=opts['values'])
        for b in bridges.values():b.client.call('room_options_ack',invite=b.config['invite'],revision=opts['revision'])
        for b in bridges.values():b.client.call('lobby_ready',ready=True)
        import city_client,scenario_pair
        saves={c:city.save() for c,city in self.cities.items()}
        for target,name,value in ((city_client,'Engine',F.fake_engine(saves)),(scenario_pair,'verify_city',lambda *a:None)):
            p=patch.object(target,name,value);p.start();self.addCleanup(p.stop)
    def test_host_cancels_the_start(self):
        # user 2026-11-14: only a guest taking back "ready" could stop a start; the host now can (button 3, 시작 취소)
        seats=[s['id'] for s in json.loads((A/'scenarios'/'freebuild-6p'/'scenario.json').read_text(encoding='utf-8-sig'))['slots']]
        room,bridges=self.open('freebuild-6p',seats);self.ready_all(bridges,seats[0])
        h=bridges[seats[0]]
        self.assertEqual(h.client.call('room_start')['start']['phase'],'loading')        # every seat taken: no roster job
        with self.assertRaisesRegex(ValueError,'host only'):bridges[seats[1]].client.call('room_start_cancel')
        st=h.client.call('room_start_cancel')['start']
        self.assertEqual(st['phase'],'lobby');self.assertIn('방장이 시작을 취소했습니다',st.get('detail',''))
        self.assertFalse(room['room'].started)
        self.assertEqual(h.client.call('room_start')['start']['phase'],'loading')        # and it can start again
    def test_host_cancel_while_empty_seats_are_turned_neutral(self):
        room,bridges=self.open('freebuild-6p',['player2','player6']);self.ready_all(bridges,'player2')
        h=bridges['player2'];h.client.call('room_start');h.client.call('room_start_cancel')
        deadline=time.time()+40;st={}
        while time.time()<deadline:
            st=h.client.call('lobby_status').get('start') or {}
            if st.get('phase')=='lobby' and '방장이 시작을 취소했습니다' in st.get('detail',''):break
            time.sleep(0.25)
        self.assertEqual(st.get('phase'),'lobby',self.roster_error(room));self.assertFalse(room['room'].started)
        self.assertEqual(self.refused,[])
    def test_all_six_seats(self):
        for name in NAMES:
            with self.subTest(name=name):
                seats=[s['id'] for s in json.loads((A/'scenarios'/name/'scenario.json').read_text(encoding='utf-8-sig'))['slots']]
                self.run_one(name,seats)

if __name__=='__main__':unittest.main()
