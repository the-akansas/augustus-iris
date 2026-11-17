"""The host cannot start while someone in the waiting room has not chosen a city (user report 2026-11-13: the game
started anyway and that player was sent back to the main menu). Real room (room_host, Lobby, TCP) and real bridges,
from the room-flow harness. Someone who has not been seen for 30 s does not block (the same rule that frees the seat)."""
import sys,time,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_throne_room_flow as F

class StartNeedsCities(F.RoomFlow):
    def lobby_only(self,room,index):
        import game_bridge
        folder=self.tmp/f'nocity{index}'/room['root'].name;folder.mkdir(parents=True)
        b=game_bridge.Bridge(room['configs'][index],folder);self.addCleanup(b.close);self.addCleanup(b.client.disconnect)
        for _ in range(3):b.step()                                   # in the waiting room, no city chosen
        from contextlib import closing
        from coordinator import sha
        with closing(room['room'].coordinator.connect()) as db:
            row=db.execute('SELECT city FROM lobby_invite WHERE token=?',(sha(b.config['invite'].encode()),)).fetchone()
        self.assertIsNotNone(row);self.assertIsNone(row[0]);return b
    def ready_all(self,bridges):
        host=bridges['player1'];opts=host.client.call('lobby_view',invite=host.config['invite'])['room_options']
        if not opts['initialized']:opts=host.client.call('room_options_set',invite=host.config['invite'],revision=opts['revision'],values=opts['values'])
        for b in bridges.values():b.client.call('room_options_ack',invite=b.config['invite'],revision=opts['revision'])
        for b in bridges.values():b.client.call('lobby_ready',ready=True)
    def test_start_waits_for_the_city_choice(self):
        a=self.make_room('room-nocity')
        bridges={c:self.bridge(a,i,c) for i,c in enumerate(['player1','player2','player3'])}
        waiting=self.lobby_only(a,3)
        self.ready_all(bridges)
        with self.assertRaises(ValueError) as refused:bridges['player1'].client.call('room_start')
        self.assertEqual(str(refused.exception),'participants must choose cities')   # reaches the host as it is
        self.assertFalse(a['room'].started);self.assertIsNone(a['room'].start_at)
        self.assertFalse(getattr(a['room'],'roster_job',None))
        import game_bridge
        self.assertIn('도시를 고르지 않은 참가자',game_bridge.Bridge.error_message('participants must choose cities'))
        # the late player chooses a city: the start is no longer held by this rule
        (waiting.root/'command.txt').write_text('choose-city\nplayer4',encoding='utf8')
        for _ in range(3):waiting.step()
        self.assertEqual(waiting.client.city,'player4')               # now chosen
        bridges['player4']=waiting
        F.RoomFlow.start(self,a,bridges)                              # the harness start: ends with the room started
        self.assertTrue(a['room'].started)
    def test_someone_gone_for_30_seconds_does_not_block(self):
        a=self.make_room('room-gone')
        bridges={c:self.bridge(a,i,c) for i,c in enumerate(['player1','player2','player3','player4'][:3])}
        waiting=self.lobby_only(a,3);waiting.close();waiting.client.disconnect()
        a['room'].invite_seen={k:v-31 for k,v in a['room'].invite_seen.items()}    # 31 s pass for everybody's last look
        for b in bridges.values():b.client.call('lobby_status')       # the three still in the room are seen again now
        self.ready_all(bridges)
        try:bridges['player1'].client.call('room_start')
        except ValueError as e:self.assertNotEqual(str(e),'participants must choose cities')

for _n in [n for n in dir(F.RoomFlow) if n.startswith('test_')]:setattr(StartNeedsCities,_n,None)
if __name__=='__main__':unittest.main()
