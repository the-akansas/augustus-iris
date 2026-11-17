"""Waiting-room head count '참가 · 도시 선택 · 준비' (user 2026-11-13). Real room, real TCP, real bridges (room-flow
harness). The three numbers follow the start rule: the host can start exactly when they are equal."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_throne_room_flow as F
import test_start_needs_cities as N
import lobby_counts

class LobbyCounts(F.RoomFlow):
    lobby_only=N.StartNeedsCities.lobby_only
    def counts(self,b):return b.client.call('lobby_status')['lobby_counts']
    def test_counts_follow_city_choice_and_ready(self):
        a=self.make_room('room-counts')
        bridges={c:self.bridge(a,i,c) for i,c in enumerate(['player1','player2','player3'])}
        waiting=self.lobby_only(a,3)                                   # admitted, no city yet
        host=bridges['player1']
        self.assertEqual(self.counts(host),dict(joined=4,chosen=3,ready=1))   # only the host counts as ready
        opts=host.client.call('lobby_view',invite=host.config['invite'])['room_options']
        if not opts['initialized']:opts=host.client.call('room_options_set',invite=host.config['invite'],revision=opts['revision'],values=opts['values'])
        for b in bridges.values():b.client.call('room_options_ack',invite=b.config['invite'],revision=opts['revision'])
        bridges['player2'].client.call('lobby_ready',ready=True)
        self.assertEqual(self.counts(host),dict(joined=4,chosen=3,ready=2))
        # the waiting player sees the same numbers, and the bridge writes the line the game draws
        waiting.step()
        text=(waiting.root/'lobby-counts.txt').read_text(encoding='utf8')
        self.assertEqual(text,'참가 4 · 도시 선택 3 · 준비 2\n참가 4 · 선택 3 · 준비 2\n')
        # version lines: both in every window, the host's own included
        for b in bridges.values():b.step()
        for b in (host,bridges['player2']):
            self.assertTrue((b.root/'lobby-host-version.txt').read_text(encoding='utf8').startswith('방장 버전: v'))
            self.assertTrue((b.root/'lobby-own-version.txt').read_text(encoding='utf8').startswith('내 버전: v'))
        self.assertTrue((waiting.root/'lobby-host-version.txt').read_text(encoding='utf8').startswith('방장 버전: v'))
        # someone without a city who has not been seen for 30 s is no longer counted (and no longer blocks the start)
        waiting.close();waiting.client.disconnect()
        a['room'].invite_seen={k:v-31 for k,v in a['room'].invite_seen.items()}
        for b in bridges.values():b.client.call('lobby_status')
        # read the room itself: after the steps above a bridge may answer from its prefetched copy
        from contextlib import closing
        with a['room'].lock,closing(a['room'].coordinator.connect()) as db:fresh=a['room'].status(db)['lobby_counts']
        self.assertEqual(fresh,dict(joined=3,chosen=3,ready=2))
    def test_host_without_a_city_yet(self):
        a=self.make_room('room-nohostcity')
        host=self.lobby_only(a,0)                                      # the host has not chosen a city
        guest=self.bridge(a,1,'player2');guest.step();host.step()
        for b in (host,guest):                                         # the host's version is known on entry, no city needed
            self.assertTrue((b.root/'lobby-host-version.txt').read_text(encoding='utf8').startswith('방장 버전: v'),b.root)
            self.assertTrue((b.root/'lobby-own-version.txt').read_text(encoding='utf8').startswith('내 버전: v'))
    def test_old_host_shows_nothing(self):
        self.assertEqual(lobby_counts.lines({}),'')
        self.assertEqual(lobby_counts.lines(dict(lobby_counts=dict(joined='6',chosen=5,ready=3))),'')

for _n in [n for n in dir(F.RoomFlow) if n.startswith('test_')]:setattr(LobbyCounts,_n,None)
if __name__=='__main__':unittest.main()
