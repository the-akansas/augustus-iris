"""Host loss and succession, end to end (user 2026-11-15: "튕김이나 접속끊김시 방장을 이어받거나 저장되는거 논리 검증").

Real parts (as test_throne_isolation, a four-player free-build room): room_host.create_room, the room server on
127.0.0.1, game_bridge.Bridge with its replica worker (save_replica.download) and acknowledgements (replica_ack), the
room's recovery plan (recovery_group.plan), and the takeover itself: recovery_group.recover for the designated guest
(new room from its own backup copy) and for the other guests (recovery_offer / recovery_join over TCP).
Stand-ins: the city engine (test_throne_room_flow.City), the clock reports (sent by the test), the network session
(only root, mail, publish and the server slots that recover() uses), and the host's loss (its server is shut down).
Needs what test_throne_room_flow needs."""
import base64,json,shutil,socket,sys,time,unittest,uuid
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_throne_isolation as I
import test_throne_room_flow as F

def free_port():
    with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]

class Session:
    """What recover()/promote() use of network_play's session."""
    def __init__(self,root):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True);self.mail=self.root/'mail';self.mail.mkdir(exist_ok=True)
        self.server=None;self.thread=None;self.bridge=None
    def publish(self,name,text):(self.mail/name).write_text(text,encoding='utf8')
    def close_server(self):
        if self.server:self.server.shutdown();self.server.server_close();self.server=None

@unittest.skipUnless(F.DATA and I.FREE.is_file() and F.native_library(1),'needs AUGUSTUS_C3_DATA and the real post_* C library: '+F._why)
class Succession(I.FreeBuildRoom):
    names=['player1','player2','player3','player4']
    def room(self):
        a=self.make_room('room-a');bridges={c:self.bridge(a,i,c) for i,c in enumerate(self.names)}
        for b in bridges.values():b.recovery_port=free_port();b.endpoint_registered=None
        self.start(a,bridges);self.clock(a,bridges,800);return a,bridges
    def save(self,a,bridges,kind=None):
        lobby=a['room'];host=bridges['player1']
        self.clock(a,bridges,lobby.grant)  # The stand-in engines must report current progress before a save.
        saved=host.client.call('save_begin',request_id=uuid.uuid4().hex,**({'kind':kind} if kind else {}))
        self.clock(a,bridges,saved['ticks'])
        for c,b in bridges.items():b.client.call('save_part',id=saved['id'],ticks=saved['ticks'],save=base64.b64encode(self.cities[c].save()).decode())
        self.assertEqual(host.client.call('save_status')['complete']['id'],saved['id']);return saved['id']
    def settle(self,bridges,until,rounds=60):
        """Bridge rounds (their replica workers download in the background) until `until()` holds."""
        for _ in range(rounds):
            for b in bridges.values():b.step()
            if until():return
            time.sleep(0.1)
        self.fail('did not settle')
    def lose_host(self,a):
        a['server'].shutdown();a['server'].server_close()
    def take_over(self,old):
        """recover() for one guest, the engine and city checks stood in as make_room does."""
        import room_host,recovery_group
        saves={c:city.save() for c,city in self.cities.items()}
        session=Session(self.tmp/('session-'+old.client.city))
        with patch.object(room_host,'Engine',F.fake_engine(saves)),patch.object(room_host,'verify_city',lambda *a:None):
            recovery_group.recover(session,old)
        self.addCleanup(session.close_server);self.addCleanup(lambda:session.bridge and session.bridge.close())
        return session

    def test_group_takes_over_from_the_shared_save(self):
        a,bridges=self.room();sid=self.save(a,bridges)
        guests={c:bridges[c] for c in self.names[1:]}
        self.settle(bridges,lambda:all(b.recovery_plan and b.recovery_plan['save_id']==sid for b in guests.values()))
        plan=guests['player2'].recovery_plan;self.assertEqual(plan['candidate'],'player2')
        self.lose_host(a)
        sessions={c:self.take_over(guests[c]) for c in ('player2','player3','player4')}   # the candidate first
        new=sessions['player2'].server.coordinator
        self.assertTrue(new.started)
        with closing(new.coordinator.connect()) as db:
            claimed={r[0] for r in db.execute('SELECT city FROM lobby_invite WHERE city IS NOT NULL AND token NOT IN (SELECT token FROM departed_invite)')}
        self.assertEqual(claimed,{'player2','player3','player4'})
        for c,s in sessions.items():self.assertEqual(s.bridge.client.city,c)

    def test_candidate_holds_the_save_the_plan_names(self):
        """Saves can come faster than one guest's copy: a guest that copied save 1 only and a candidate that copied
        save 2 only. The plan must name a save the candidate has (it builds the new room from its own copy)."""
        a,bridges=self.room()
        guests={c:bridges[c] for c in self.names[1:]}
        first=self.save(a,bridges)
        others={c:guests[c] for c in ('player3','player4')}
        self.settle(others,lambda:all(getattr(b,'replicated_id',None)==first and b.succession_id is not None for b in others.values()) or
                    all(getattr(b,'replica_asked',None)==first for b in others.values()))
        second=self.save(a,bridges)
        cand={'player2':guests['player2']}
        self.settle(cand,lambda:getattr(guests['player2'],'replica_asked',None)==second)
        self.settle(bridges,lambda:guests['player2'].recovery_plan is not None,rounds=10)
        plan=guests['player2'].recovery_plan
        replica=guests['player2'].root.parent/('host-backup-'+guests['player2'].config['session']+'-'+str(plan['save_id']))
        self.assertTrue(replica.is_dir(),f"plan names save {plan['save_id']}, the candidate holds {sorted(p.name for p in guests['player2'].root.parent.glob('host-backup-*'))}")
        self.lose_host(a)
        sessions={c:self.take_over(guests[c]) for c in ('player2','player3','player4')}
        self.assertTrue(sessions['player2'].server.coordinator.started)

    def test_host_lost_during_a_save_falls_back_to_the_last_complete_one(self):
        a,bridges=self.room();sid=self.save(a,bridges)
        guests={c:bridges[c] for c in self.names[1:]}
        self.settle(bridges,lambda:all(b.recovery_plan and b.recovery_plan['save_id']==sid for b in guests.values()))
        self.clock(a,bridges,a['room'].grant)
        host=bridges['player1'];pending=host.client.call('save_begin',request_id=uuid.uuid4().hex)
        self.clock(a,bridges,pending['ticks'])
        host.client.call('save_part',id=pending['id'],ticks=pending['ticks'],save=base64.b64encode(self.cities['player1'].save()).decode())
        for b in guests.values():b.step()                                    # the half-made save changes no plan
        self.assertTrue(all(b.recovery_plan['save_id']==sid for b in guests.values()))
        self.lose_host(a)
        sessions={c:self.take_over(guests[c]) for c in ('player2','player3','player4')}
        result=json.loads((sessions['player2'].root/'succession-result.json').read_text(encoding='utf8'))
        self.assertEqual(result['save_id'],sid)

    def test_a_guest_without_a_copy_does_not_stop_the_takeover(self):
        a,bridges=self.room();sid=self.save(a,bridges)
        guests={c:bridges[c] for c in self.names[1:]}
        quick={c:guests[c] for c in ('player2','player3')}                     # player4's copy is still on its way
        self.settle(quick,lambda:all(b.recovery_plan and b.recovery_plan['save_id']==sid for b in quick.values()))
        guests['player4'].replicas=type('NoCopy',(),{'poll':lambda self,b,sid:None,'close':lambda self:None})()
        for _ in range(2):guests['player4'].step()
        self.assertIsNone(getattr(guests['player4'],'replicated_id',None))   # no copy of its own
        self.assertTrue(guests['player4'].recovery_plan)                      # armed by the plan, without a copy of its own
        self.lose_host(a)
        sessions={c:self.take_over(guests[c]) for c in ('player2','player3','player4')}
        for c,s in sessions.items():self.assertEqual(s.bridge.client.city,c)

    def test_compressed_runs(self):
        """Randomised: saves at random moments, guests that fall behind at random, the host lost at a random moment.
        Every guest that holds a plan must get into the new room, which is built from the candidate's own save."""
        import random
        for seed in range(int(__import__('os').environ.get('SUCCESSION_RUNS','3'))):
            rng=random.Random(seed);self.cities={}
            a=self.make_room(f'run-{seed}');bridges={c:self.bridge(a,i,c) for i,c in enumerate(self.names)}
            for b in bridges.values():b.recovery_port=free_port();b.endpoint_registered=None
            self.start(a,bridges);self.clock(a,bridges,800);guests={c:bridges[c] for c in self.names[1:]}
            for _ in range(rng.randint(1,4)):
                self.save(a,bridges)
                awake=[b for b in guests.values() if rng.random()<0.7]
                for _ in range(rng.randint(1,15)):
                    for b in awake:b.step()
                    time.sleep(0.05)
            for b in bridges.values():b.step()
            planned={c:b for c,b in guests.items() if b.recovery_plan}
            if not planned:continue
            plan=next(iter(planned.values())).recovery_plan
            self.lose_host(a)
            order=[plan['candidate']]+[c for c in planned if c!=plan['candidate']]
            if plan['candidate'] not in planned:self.fail(f'seed {seed}: the candidate has no plan')
            sessions={c:self.take_over(guests[c]) for c in order}
            new=sessions[plan['candidate']].server.coordinator
            with closing(new.coordinator.connect()) as db:
                here={r[0] for r in db.execute('SELECT city FROM lobby_invite WHERE city IS NOT NULL AND token NOT IN (SELECT token FROM departed_invite)')}
            self.assertEqual(here,set(order),f'seed {seed}')
            for s_ in sessions.values():s_.close_server();s_.bridge.close()

    def test_a_player_leaving_during_a_save_does_not_hold_the_room(self):
        """A joint save waits for every city's file. A player who leaves before sending it must not keep the save
        (and the shared clock it holds) waiting for good."""
        a,bridges=self.room();host=bridges['player1']
        pending=host.client.call('save_begin',request_id=uuid.uuid4().hex)
        self.clock(a,bridges,pending['ticks'])
        for c in ('player1','player2','player3'):
            bridges[c].client.call('save_part',id=pending['id'],ticks=pending['ticks'],save=base64.b64encode(self.cities[c].save()).decode())
        bridges['player4'].client.call('lobby_leave',invite=bridges['player4'].config['invite'])
        status=host.client.call('save_status')
        self.assertIsNone(status['pending'],status)                           # finished without it, or given up
        later=host.client.call('save_begin',request_id=uuid.uuid4().hex)     # and the next save can start
        self.assertNotEqual(later['id'],pending['id'])

    def test_one_save_per_game(self):
        """user 2026-11-15: "수동저장이든 자동저장이든 게임당 최신1개만" - on the guests (their copies) and in the
        host's own room file; each holds every city's save."""
        a,bridges=self.room();guest=bridges['player2']
        made=[]
        for kind in ('auto','manual','auto','auto','manual','auto','manual'):
            sid=self.save(a,bridges,kind);made.append((sid,kind))
            self.settle({'player2':guest},lambda:getattr(guest,'replicated_id',None)==sid)
        self.settle({'player2':guest},lambda:guest.succession_id==made[-1][0])
        guest.step()
        kept={int(p.name.rsplit('-',1)[1]) for p in guest.root.parent.glob('host-backup-'+guest.client.session+'-*')}
        autos=[s for s,k in made if k=='auto'];manual=[s for s,k in made if k=='manual']
        self.assertEqual(kept,{made[-1][0]})
        with closing(a['room'].coordinator.connect()) as db:
            self.assertEqual(db.execute('SELECT kind FROM joint_save WHERE id=?',(manual[0],)).fetchone()[0],'manual')
            self.assertEqual({r[0] for r in db.execute('SELECT DISTINCT id FROM joint_part')},{made[-1][0]})
            self.assertEqual(db.execute("SELECT max(id) FROM joint_save WHERE state='complete'").fetchone()[0],made[-1][0])
        import save_catalog,scenario_pair
        rooms=self.tmp/'rooms';rooms.mkdir();shutil.copytree(a['root'],rooms/'game-a')   # where the game keeps rooms
        listed=[e for e in save_catalog.catalog(rooms,scenario_pair.load_pair(F.DATA and __import__('city_client').game_data(),a['root']/'scenario-project.json')[1])['entries'] if e['room']=='game-a']
        self.assertEqual([(e['id'],e['available']) for e in listed],[(made[-1][0],True)])

    def test_only_the_newest_eight_games_stay(self):
        """user 2026-11-15: "이어하기는 총 8개제한" + "자동으로 지워줘": older games are deleted, never a session's own
        folder (profile, records) nor the running session."""
        import os,shutil,save_catalog,scenario_pair,city_client
        a,bridges=self.room();self.save(a,bridges)
        rooms=self.tmp/'rooms';rooms.mkdir()
        for i in range(10):
            shutil.copytree(a['root'],rooms/f'game-{i}',ignore=shutil.ignore_patterns('*-wal','*-shm'))
            os.utime(rooms/f'game-{i}'/'room.sqlite',(1000+i,1000+i))
        session=rooms/'network-play-old';(session/'user').mkdir(parents=True);(session/'user'/'profile.json').write_text('{}')
        shutil.copytree(a['root'],session/'host-abc');os.utime(session/'host-abc'/'room.sqlite',(500,500))   # the oldest game
        running=rooms/'network-play-now';shutil.copytree(a['root'],running/'host-now');os.utime(running/'host-now'/'room.sqlite',(1,1))
        binding=scenario_pair.load_pair(city_client.game_data(),a['root']/'scenario-project.json')[1]
        removed=save_catalog.prune(rooms,binding,current=running)
        self.assertEqual(sorted(removed),['game-0','game-1','host-abc'])
        self.assertEqual(sorted(p.name for p in rooms.glob('game-*')),[f'game-{i}' for i in range(2,10)])
        self.assertTrue((session/'user'/'profile.json').is_file())           # the session folder itself stays
        self.assertTrue((running/'host-now').is_dir())                      # the running session is never touched
        self.assertEqual(len(save_catalog.catalog(rooms,binding)['entries']),8)

TWO=F.ROOT/'Augustus/scenarios/freebuild-2p/scenario.json'
@unittest.skipUnless(F.DATA and TWO.is_file() and F.native_library(1),'needs AUGUSTUS_C3_DATA and the real post_* C library: '+F._why)
class TwoPlayers(F.RoomFlow):
    """Two players: the guest that acknowledged a save becomes the host (migration.promote)."""
    def setUp(self):
        super().setUp()
        p=patch.object(F,'PROJECT',TWO);p.start();self.addCleanup(p.stop)
    def test_guest_takes_over(self):
        import room_host,migration
        a=self.make_room('two-a');bridges={c:self.bridge(a,i,c) for i,c in enumerate(['player1','player2'])}
        self.start(a,bridges);self.clock(a,bridges,800)
        sid=Succession.save(self,a,bridges);guest=bridges['player2']
        Succession.settle(self,bridges,lambda:guest.succession_armed and guest.succession_id==sid)
        a['server'].shutdown();a['server'].server_close()
        guest.connection_exit('disconnected','방장과 연결이 끊겼습니다.')
        self.assertTrue(guest.migration_requested)
        self.assertEqual((guest.root/'room-exit.txt').read_text(encoding='utf8'),'migrate')
        session=Session(self.tmp/'two-session')
        saves={c:city.save() for c,city in self.cities.items()}
        with patch.object(room_host,'Engine',F.fake_engine(saves)),patch.object(room_host,'verify_city',lambda *a:None):
            migration.promote(session,guest,port=0)
        self.addCleanup(session.close_server);self.addCleanup(lambda:session.bridge and session.bridge.close())
        room=session.server.coordinator;self.assertTrue(room.started)
        result=json.loads((session.root/'succession-result.json').read_text(encoding='utf8'))
        self.assertEqual((result['save_id'],result['city']),(sid,'player2'))
        with closing(room.coordinator.connect()) as db:
            parts={r[0]:bytes(r[1]) for r in db.execute('SELECT id,save FROM city')}
            left={r[0] for r in db.execute('SELECT city FROM lobby_invite WHERE token IN (SELECT token FROM departed_invite)')}
        self.assertEqual(left,{'player1'})                                  # the old host is out; its city waits
        self.assertEqual(session.bridge.client.city,'player2')

for _n in [n for n in dir(F.RoomFlow) if n.startswith('test_')]:
    if getattr(F.RoomFlow,_n,None) is getattr(TwoPlayers,_n,None):setattr(TwoPlayers,_n,None)
for _n in [n for n in dir(I.FreeBuildRoom) if n.startswith('test_')]:
    if getattr(I.FreeBuildRoom,_n,None) is getattr(Succession,_n,None):setattr(Succession,_n,None)

if __name__=='__main__':unittest.main()
