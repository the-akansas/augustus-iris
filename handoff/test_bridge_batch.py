"""One round trip for a bridge round's routine polls (coordinator 'batch', city_client.Client.begin_round).

Real room server, TCP and bridges (as test_throne_isolation, a free-build room). Checked:
  * a batch answers each entry exactly as the same request sent alone; a failing entry fails alone; nesting and
    unauthenticated operations are refused; another player's credentials are needed for another player's data;
  * a bridge round after the first sends its polls in one request and asks the network for nothing it was handed;
  * an answer is never reused in a later round; a command's effect is visible in the same round (batch is sent after it);
  * a host without 'batch' (older build): the bridge falls back to single requests;
  * with a simulated 400 ms ping a guest round is well under the 12 round trips it used to take.
Needs AUGUSTUS_C3_DATA and the post_* C library (as test_throne_room_flow)."""
import os,sys,time,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_throne_isolation as I
import test_throne_room_flow as F

@unittest.skipUnless(F.DATA and I.FREE.is_file() and F.native_library(1),'needs AUGUSTUS_C3_DATA and the real post_* C library: '+F._why)
class Batch(I.FreeBuildRoom):
    def room(self,started=True):
        a=self.make_room('batch');names=['player1','player2','player3','player4']
        bridges={c:self.bridge(a,i,c) for i,c in enumerate(names)}
        if started:self.start(a,bridges);self.clock(a,bridges,800)
        return a,bridges
    def network(self,client):
        """Record the requests that really go to the server (the frames), not the answers handed out."""
        sent=[];import json
        real=client.connection
        def spy(timeout):
            sock,reader,reused=real(timeout)
            class Tap:
                def __getattr__(s,n):return getattr(sock,n)
                def sendall(s,wire):sent.append(json.loads(wire)['op']);return sock.sendall(wire)
            return Tap(),reader,reused
        p=patch.object(client,'connection',spy);p.start();self.addCleanup(p.stop);return sent
    def test_batch_answers_like_single_requests(self):
        a,b=self.room();c=b['player2'].client
        single=[c.call('lobby_status'),c.call('save_status'),c.call('chat_read',after=0)]
        got=c.call('batch',calls=[dict(op='lobby_status'),dict(op='save_status'),dict(op='chat_read',after=0),dict(op='no_such_operation'),dict(op='chat_read',after=-1)])
        self.assertEqual([x['ok'] for x in got],[True,True,True,False,False])
        def steady(x):   # contact ages move with the clock
            if isinstance(x,dict):return {k:steady(v) for k,v in x.items() if k not in ('contact_age_ms','age_ms','remaining')}
            return [steady(v) for v in x] if isinstance(x,list) else x
        self.assertEqual([steady(x['result']) for x in got[:3]],[steady(x) for x in single])
        for bad in ([dict(op='batch',calls=[dict(op='lobby_status')])],[dict(op='public_info',version=1)],[],[dict(op='lobby_status')]*33,'x'):
            with self.assertRaises(ValueError):c.call('batch',calls=bad)
        other=c.call('batch',calls=[dict(op='throne_mine',city='player3')])   # player2's token does not open player3
        self.assertFalse(other[0]['ok'])
    def test_round_uses_one_request_for_its_polls(self):
        a,b=self.room();g=b['player2'];g.step();g.step()
        sent=self.network(g.client);g.cash_next=time.monotonic()+60;g.step()
        self.assertEqual(sent.count('batch'),1)
        for op in ('lobby_heartbeat','lobby_status','save_status','chat_read','play_begin','recovery_plan','army_install_status'):
            self.assertNotIn(op,sent,op)
        self.assertLessEqual(len(sent),6,sent)
        self.assertFalse(g.client._ready and [k for k,_,_ in g.client._ready if k[0] not in ('army_overview','army_order_status','clock')])
        self.assertIn('ms',(g.root/'debug-status.txt').read_text(encoding='utf8'))
    def test_command_effect_is_seen_in_the_same_round(self):
        a,b=self.room(started=False);g=b['player2'];host=b['player1']
        opts=host.client.call('lobby_view',invite=host.config['invite'])['room_options']
        if not opts['initialized']:opts=host.client.call('room_options_set',invite=host.config['invite'],revision=opts['revision'],values=opts['values'])
        g.client.call('room_options_ack',invite=g.config['invite'],revision=opts['revision'])
        g.step();g.step()
        self.assertEqual((g.root/'slots.txt').read_text(encoding='utf8').splitlines()[1],'나 / 선택됨')
        (g.root/'command.txt').write_text('ready\n',encoding='utf8');g.step()        # one round: command, then the batch
        self.assertEqual((g.root/'slots.txt').read_text(encoding='utf8').splitlines()[1],'나 / 준비')
    def test_host_without_batch_falls_back(self):
        a,b=self.room();g=b['player2'];g.step()
        import coordinator
        real=coordinator.Handler.answer
        def old(handler,data):
            import json
            if json.loads(data).get('op')=='batch':
                handler.wfile.write(b'{"ok":false,"error":"invalid_request"}\n');return True
            return real(handler,data)
        with patch.object(coordinator.Handler,'answer',old):
            g.step();self.assertTrue(g.client._no_batch);sent=self.network(g.client);g.step()
            self.assertNotIn('batch',sent);self.assertIn('lobby_heartbeat',sent)
    def test_guest_round_at_400ms(self):
        a,b=self.room();g=b['player2'];g.step();g.step()
        with patch.dict(os.environ,dict(AUGUSTUS_MP_TEST_TOOLS='1',AUGUSTUS_TEST_RTT_MS='400')):
            times=[]
            for _ in range(4):
                g.cash_next=time.monotonic()+60;t=time.monotonic();g.step();times.append(time.monotonic()-t)
        print(f'guest round at 400 ms: {sorted(times)[len(times)//2]:.2f}s (was about 5.3s)',file=sys.stderr)
        self.assertLess(sorted(times)[len(times)//2],2.6)

for _n in [n for n in dir(I.FreeBuildRoom) if n.startswith('test_')]:
    if not hasattr(Batch,_n) or getattr(I.FreeBuildRoom,_n,None) is getattr(Batch,_n,None):setattr(Batch,_n,None)
if __name__=='__main__':unittest.main()
