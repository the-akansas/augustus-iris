"""황제의 순행 (user 2026-11-15: "시나리오 생성부터 인게임 압축 시뮬까지"), a whole game in a real room.

Same real parts and stand-ins as test_default_rooms / test_throne_room_flow: room_host.create_room, the room server
over TCP, game_bridge.Bridge driven through its command file, the C money mailbox (post_ipc/post_city/post_book) for
every debit, joint saves through save_begin/save_part, the guest's backup replica and create_room(restore=...).
The city engine is a stand-in here, also for the visit: `serve` does what src/multiplayer/emperor_visit.inc does
(a visit number above the last one is served once from a stock, the answer is written every time; the real C is run
by handoff/test_emperor_visit_engine.py). The waiting times are skipped with the test tool (imperial_progress.
mp_test_tools.progress_adjust, the same as the test launcher's button)."""
import base64,json,shutil,sys,time,unittest,uuid
from contextlib import closing
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
TEST_TOOLS=(Path(__file__).resolve().parents[1]/'Augustus'/'mp_test_tools.py').is_file()   # the test launcher's tools: in no release, not in the public source
import test_throne_room_flow as F
import test_default_rooms as D

@unittest.skipUnless(TEST_TOOLS,'needs the test launcher tools (Augustus/mp_test_tools.py), which are not in this copy')
class ProgressGame(D.DefaultRooms):
    SEATS=['player2','player4','player6']
    def setUp(self):
        super().setUp();self.last={};self.stock={}
    # ---- helpers
    def state(self,room):
        import imperial_progress as ip
        lobby=room['room']
        with lobby.lock,closing(lobby.coordinator.connect()) as db:return ip.current(db,lobby.coordinator.scenario)
    def skip(self,room):
        import imperial_progress as ip
        lobby=room['room']
        with lobby.lock,closing(lobby.coordinator.connect()) as db:__import__('mp_test_tools').progress_adjust(db,lobby.coordinator.scenario,'next');db.commit()
    def bid(self,b,amount):
        funds=self.cities[b.client.city].treasury
        (b.root/'command.txt').write_text('throne\ngo\n%d\n%d'%(funds,amount),encoding='utf8');b.step()
    def serve(self,b):
        """The city engine's side of the visit (stand-in for emperor_visit.inc)."""
        city=b.client.city;path=b.root/'emperor-visit-request.txt'
        try:scope,owner,visit,resource,amount=path.read_text().split()
        except (OSError,ValueError):return
        visit,resource,amount=int(visit),int(resource),int(amount)
        last=self.last.get(city)
        if not last or visit>last[0]:
            have=self.stock.get(city,{}).get(resource,0);taken=min(have,amount)
            self.stock.setdefault(city,{})[resource]=have-taken;last=self.last[city]=(visit,resource,amount,taken)
        (b.root/'emperor-visit.txt').write_text('%d %d %d %d %d\n'%(*last,self.cities[city].treasury))
    def go(self,room,bridges,rounds=3):
        for _ in range(rounds):
            self.pump(bridges,rounds=1)
            for b in bridges.values():self.serve(b)
    def walk(self,room,bridges,phase,limit=12):
        for _ in range(limit):
            s=self.state(room)
            if s['phase']==phase:return s
            if s['phase'] in ('idle','bidding','travel'):self.skip(room)
            self.go(room,bridges,1)
        self.fail('progress did not reach %s: %s'%(phase,self.state(room)['phase']))
    def joint_save(self,room,bridges,host):
        lobby=room['room'];h=bridges[host]
        self.clock(room,bridges,lobby.grant)
        saved=h.client.call('save_begin',request_id=uuid.uuid4().hex)
        self.clock(room,bridges,saved['ticks'])
        for c,b in bridges.items():b.client.call('save_part',id=saved['id'],ticks=saved['ticks'],save=base64.b64encode(self.cities[c].save()).decode())
        self.assertEqual(h.client.call('save_status')['complete']['id'],saved['id'])
        return saved
    def reopen(self,old,bridges,saved,guest):
        """The host is gone; `guest` keeps the backup replica its bridge made; a new room restores it."""
        found=[]
        for _ in range(60):
            found=sorted((self.tmp/guest).glob(f"host-backup-*-{saved['id']}/room.sqlite"))
            if found:break
            self.pump({guest:bridges[guest]},rounds=1);time.sleep(0.1)
        self.assertTrue(found,'no backup copy on '+guest)
        for b in bridges.values():b.close();b.client.disconnect()
        old['server'].shutdown();old['server'].server_close()
        from unittest.mock import patch
        with patch.object(F,'PROJECT',found[-1].parent/'scenario-project.json'):   # what network_play/recovery_group pass
            new=self.make_room(old['root'].name+'-r',restore=found[-1])
        nb={c:self.bridge(new,i,c) for i,c in enumerate(sorted(bridges))}
        self.start(new,nb);self.pump(nb,rounds=2)
        return new,nb
    def start(self,room,bridges):
        # F.RoomFlow.start assumes player1 hosts; here the first bridge is the host
        host=next(iter(bridges.values()));view=host.client.call('lobby_view',invite=host.config['invite']);opts=view['room_options']
        if not opts['initialized']:opts=host.client.call('room_options_set',invite=host.config['invite'],revision=opts['revision'],values=opts['values'])
        for b in bridges.values():b.client.call('room_options_ack',invite=b.config['invite'],revision=opts['revision'])
        for b in bridges.values():b.client.call('lobby_ready',ready=True)
        start=host.client.call('room_start')['start']
        from coordinator import sha
        with closing(room['room'].coordinator.connect()) as db:
            for c,b in bridges.items():b.client.call('start_loaded',attempt=start['attempt'],layout=start['layout'],save_hash=sha(db.execute('SELECT save FROM city WHERE id=?',(c,)).fetchone()[0]))
        deadline=time.time()+20
        while not room['room'].started and time.time()<deadline:
            for b in bridges.values():b.client.call('lobby_status')
            time.sleep(0.25)
        self.assertTrue(room['room'].started)
        for b in bridges.values():b.client.call('play_begin')

    # ---- the game
    def test_a_whole_game_with_saves_a_restore_and_a_player_leaving(self):
        room,bridges,frozen=self.run_one('progress-6p',self.SEATS)
        p2,p4,p6=(bridges[c] for c in self.SEATS);T=lambda c:self.cities[c].treasury
        rules=self.scenario['rules']['progress'];start={c:T(c) for c in self.SEATS}

        # 1. outbid, the highest bidder cannot pay when the debit arrives: the next bidder pays, nobody else
        s=self.walk(room,bridges,'bidding');self.assertEqual(s['round'],1)
        self.bid(p2,900);self.bid(p4,1500)
        self.assertEqual(self.state(room)['bids']['player4']['amount'],1500)
        self.bid(p4,2000);self.assertEqual(self.state(room)['bids']['player4']['amount'],1500)   # one bid only
        self.assertIn('refuse\t이미 입찰했습니다',(p4.root/'throne-prep-bid.txt').read_text(encoding='utf8'))   # what the next click opens
        self.cities['player4'].set_treasury(1000)                                 # spent before the close
        s=self.walk(room,bridges,'travel')
        self.assertEqual((s['holder'],s['chosen'],s['paid']),('player2','bid',900))
        self.assertEqual((T('player2'),T('player4'),T('player6')),(start['player2']-900,1000,start['player6']))
        self.stock['player2']={s['good']:s['amount']}                             # everything the court will ask
        s=self.walk(room,bridges,'idle')
        self.assertEqual(s['results'][-1]['result'],'full');self.assertEqual(s['favor'],dict(player2=3,player4=0,player6=0))
        self.assertEqual(self.stock['player2'][s['results'][-1]['good']],0)
        self.go(room,bridges,2);self.assertEqual(self.state(room)['favor']['player2'],3)        # the answer, again: once
        self.cities['player4'].set_treasury(start['player4'])

        # 2. no bid: the emperor picks a city for free; it has nothing: -1 and the shortfall in money, at most its treasury
        s=self.walk(room,bridges,'travel');self.assertEqual(s['round'],2);self.assertEqual((s['chosen'],s['paid']),('random',0))
        holder=s['holder'];before=T(holder)
        s=self.walk(room,bridges,'idle')
        r=s['results'][-1];self.assertEqual((r['result'],r['taken'],r['delta']),('poor',0,-1))
        self.assertEqual(r['fine'],min(r['amount']*rules['shortfall_price'],before));self.assertEqual(T(holder),before-r['fine'])

        # 3. a joint save while the winner's city has paid but the host has not heard; the host is lost; a guest's
        #    backup restores the room: the bid is not taken twice and the progress goes on where it was
        s=self.walk(room,bridges,'bidding');self.assertEqual(s['round'],3)
        t6=T('player6');self.bid(p6,700);self.skip(room)
        p6.client.call('progress_mine')                                            # the close: the debit is staged
        self.assertEqual(self.state(room)['phase'],'charging')
        self.take_debit(p6,700)                                                    # p6's city paid, the host did not hear
        self.assertEqual(T('player6'),t6-700)
        saved=self.joint_save(room,bridges,'player2')
        favor=dict(self.state(room)['favor'])
        room,bridges=self.reopen(room,bridges,saved,'player4')
        p2,p4,p6=(bridges[c] for c in self.SEATS)
        self.assertEqual(self.state(room)['round'],3);self.assertEqual(self.state(room)['favor'],favor)
        s=self.walk(room,bridges,'travel')
        self.assertEqual((s['holder'],s['paid']),('player6',700));self.assertEqual(T('player6'),t6-700)   # once
        self.stock['player6']={s['good']:(s['amount']+1)//2}                      # half: +1
        s=self.walk(room,bridges,'idle');self.assertEqual((s['results'][-1]['result'],s['favor']['player6']),('part',favor['player6']+1))

        # 4. the hosting player leaves on the way: that progress is cancelled, the next one follows
        s=self.walk(room,bridges,'bidding');self.assertEqual(s['round'],4)
        t4=T('player4');self.bid(p4,600);s=self.walk(room,bridges,'travel');self.assertEqual(s['holder'],'player4')
        f4=s['favor']['player4'];p4.close();p4.client.call('lobby_leave',invite=p4.config['invite']);p4.client.disconnect();del bridges['player4']
        s=self.walk(room,bridges,'idle');self.assertEqual(s['results'][-1]['result'],'cancelled');self.assertEqual(s['favor']['player4'],f4)
        self.assertEqual(T('player4'),t4-600)                       # a bid already taken is not returned

        # 5. the last two progresses; the end names the right hand
        for n in (5,6):
            s=self.walk(room,bridges,'bidding');self.assertEqual(s['round'],n)
            self.bid(p2,500+n)
            s=self.walk(room,bridges,'travel');self.assertEqual(s['holder'],'player2')
            self.stock['player2']={s['good']:s['amount']}
            s=self.walk(room,bridges,'ended' if n==6 else 'idle')
        self.assertEqual(s['favor']['player2'],9-(holder=='player2'));   # round 2 went to a random city
        self.assertEqual(s['winners'],['player2'])
        self.go(room,bridges,1)
        self.assertIn('황제의 오른팔',(p6.root/'throne-events.txt').read_text(encoding='utf8'))
        self.bid(p6,900);self.assertEqual(self.state(room)['bids'],{})            # no bid after the end
        self.assertEqual([r['round'] for r in s['results']],[1,2,3,4,5,6])
        self.assertEqual(self.refused,[])

for _name in [n for n in dir(D.DefaultRooms) if n.startswith('test_')]:setattr(ProgressGame,_name,None)   # only this file's game

if __name__=='__main__':unittest.main()
