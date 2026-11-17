"""황위 시험 규칙 v1, end to end without a window: room server, TCP, bridges, the city's money mailbox, joint saves,
restoring a room (own DB and a backup replica), the end of the trial and refunds that continue afterwards.

Real parts:
  * room_host.create_room (the real room creation and restore path), Lobby, coordinator.Server on 127.0.0.1 (TCP);
  * game_bridge.Bridge with its real city_client.Client, driven only through its command file and step() loop
    (throne panel commands, throne_client.sync with its own openings and hand-in, cash_bridge's mailbox exchange);
  * the city side of the money path in real C: src/multiplayer/post_ipc.c + post_city.c + post_book.c +
    core/buffer.c built into one library per city (handoff/native_post/shim_post.c), answering the bridge's
    post-request.bin with post-response.bin exactly as the game thread does (post_ipc_exchange);
  * joint saves through the room's own save_begin / save_part / save_status, save_replica.download for the backup
    copy, and create_room(restore=...) for the new room.
Stand-ins (stated):
  * the city engine itself: its treasury is a variable in the shim (the real code reads/adds it), its city save is
    that library's MPCS piece + treasury, and its clock reports are sent by the test (clock op) instead of the engine;
  * start_loaded is sent by the test with the real save hash (the engine sends it after loading);
  * the cash exchange timer of the bridge (cash_next) is set to 'now' before a step, so the test does not sleep 5 s;
  * receipt compaction (Windows SHA-256) is not built: never requested here; if it were, it would be rejected.
Reconnect: the refund's acknowledgement is lost by dropping the bridge's TCP connection after the city took it; the
same bridge reconnects (the game and its mailbox keep running). A new bridge process for a game that keeps running is
not tested: the engine's post_ipc only accepts a request sequence >= its last one (post_ipc.c) and re-initialises only
when the city reloads (post_runtime.c), so such a bridge (sequence from 1) is refused until the game reloads. The
product joins a started room only through shared restore (network_play: 'started room requires shared restore'),
which reloads the city. Existing cash protocol, not throne code; recorded, not changed.
Not covered: the engine process, real SAV files, the game window. Needs AUGUSTUS_C3_DATA (scenario check) and a C
compiler or AUGUSTUS_POST_NATIVE_DIR (prebuilt library per city: post_native-1.so/.dll ...); otherwise skipped."""
import base64,ctypes,json,os,shutil,struct,subprocess,sys,tempfile,time,unittest,uuid,zlib
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Augustus'))
DATA=os.environ.get('AUGUSTUS_C3_DATA')
PROJECT=ROOT/'Augustus/scenarios/throne-test-v1/scenario.json'
NATIVE_DIR=os.environ.get('AUGUSTUS_POST_NATIVE_DIR')
SRC=Path(os.environ.get('AUGUSTUS_SRC_ROOT') or ROOT)/'src'   # the full game source tree (test-24 has it; wip-24 only holds changes)
EXT='.dll' if os.name=='nt' else '.so'
FUNDS=200000

_built=None;_why=''
def native_library(index):
    """A separate copy per city: post_city.c keeps one city's book in static memory, like one game process."""
    global _built,_why
    if NATIVE_DIR:
        p=Path(NATIVE_DIR)/f'post_native-{index}{EXT}'
        return p if p.is_file() else None
    if _built is None and not _why:
        cc=shutil.which('gcc') or shutil.which('cc')
        if not cc:_why='no C compiler';return None
        out=Path(tempfile.mkdtemp())
        src=SRC
        if not (src/'core/buffer.c').is_file():_why='full game source not found (set AUGUSTUS_SRC_ROOT)';return None
        r=subprocess.run([cc,'-shared','-fPIC','-O1','-std=gnu99','-I'+str(ROOT/'handoff/native_post/stub'),'-I'+str(src),'-I'+str(src/'multiplayer'),
                          '-o',str(out/('post_native'+EXT)),str(src/'multiplayer/post_ipc.c'),str(src/'multiplayer/post_city.c'),str(src/'multiplayer/post_book.c'),
                          str(src/'core/buffer.c'),str(ROOT/'handoff/native_post/shim_post.c')],capture_output=True,text=True)
        if r.returncode:_why='build failed: '+r.stderr[-400:];return None
        _built=out
    if _built is None:return None
    copy=_built/f'post_native-{index}{EXT}'
    if not copy.exists():shutil.copy2(_built/('post_native'+EXT),copy)
    return copy

class Buffer(ctypes.Structure):_fields_=[('data',ctypes.c_void_p),('size',ctypes.c_size_t),('index',ctypes.c_size_t),('overflow',ctypes.c_int)]

class City:
    """One city's engine side of the money path: the real C mailbox and book, the treasury in the shim."""
    PIECE=64000
    def __init__(self,index,funds):
        self.lib=ctypes.CDLL(str(native_library(index)))
        self.lib.shim_ipc_size.restype=ctypes.c_size_t
        self.lib.post_ipc_exchange.argtypes=[ctypes.c_void_p,ctypes.c_char_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t]
        self.lib.post_ipc_init.argtypes=[ctypes.c_void_p,ctypes.c_char_p,ctypes.c_char_p,ctypes.c_uint]
        self.lib.mp_post_city_restore.argtypes=[ctypes.POINTER(Buffer)];self.lib.mp_post_city_save.argtypes=[ctypes.POINTER(Buffer)]
        self.ipc=ctypes.create_string_buffer(self.lib.shim_ipc_size());self.run=os.urandom(16);self.ready=False
        self.lib.mp_post_city_reset();self.lib.shim_set_treasury(funds)
    @property
    def treasury(self):return self.lib.shim_get_treasury()
    def set_treasury(self,v):self.lib.shim_set_treasury(v)
    def piece(self):
        raw=ctypes.create_string_buffer(self.PIECE);b=Buffer(ctypes.cast(raw,ctypes.c_void_p),self.PIECE,0,0)
        self.lib.mp_post_city_save(ctypes.byref(b));return raw.raw
    def save(self):return b'CITYSTUB'+struct.pack('<i',self.treasury)+self.piece()      # the stand-in city save
    def load(self,data):
        assert data[:8]==b'CITYSTUB';self.set_treasury(struct.unpack_from('<i',data,8)[0]);raw=ctypes.create_string_buffer(data[12:],self.PIECE)
        b=Buffer(ctypes.cast(raw,ctypes.c_void_p),self.PIECE,0,0);assert self.lib.mp_post_city_restore(ctypes.byref(b))==1;self.ready=False
    def pump(self,root,answer=True):
        """What the game thread does each frame: publish the capability, answer one request (real post_ipc_exchange)."""
        root=Path(root)
        try:scope,owner=(root/'post-identity.txt').read_text().split()
        except (OSError,ValueError):return False
        if not self.ready:
            assert self.lib.post_ipc_init(self.ipc,self.run,scope.encode(),int(owner))==1;self.ready=True
        (root/'post-capability.bin').write_bytes(self.run+scope.encode()+struct.pack('<I',int(owner)))
        req=root/'post-request.bin'
        if not answer or not req.exists():return False
        data=req.read_bytes();out=ctypes.create_string_buffer(64136)
        if not self.lib.post_ipc_exchange(self.ipc,data,len(data),out,64136):return False
        tmp=root/'post-response.tmp';tmp.write_bytes(out.raw);os.replace(tmp,root/'post-response.bin');return True

def fake_engine(saves):
    class Engine:
        def run(self,mode,root,out,**k):
            city=mode.split('-',1)[1];Path(out).mkdir(parents=True,exist_ok=True)
            return saves[city],struct.pack('<4sQiiiii',b'MPC1',0,0,0,0,0,0)
    return Engine

@unittest.skipUnless(DATA and PROJECT.is_file() and native_library(1),'needs AUGUSTUS_C3_DATA and the real post_* C library: '+_why)
class RoomFlow(unittest.TestCase):
    def setUp(self):
        self.tmp=Path(tempfile.mkdtemp());self.addCleanup(shutil.rmtree,self.tmp,True)
        import connection_config
        if not (ROOT/'Augustus/augustus-mp-ui.exe').is_file():   # Linux: no game executable to hash (stand-in hash)
            p=patch.object(connection_config,'engine_hash',lambda:'0'*64);p.start();self.addCleanup(p.stop)
        try:import observe_channel                           # Windows: the real shared-memory clock/observe channel
        except OSError:
            import types;sys.modules['observe_channel']=observe_channel=types.SimpleNamespace(Channel=None,FRAME_CAP=0)
        if observe_channel.Channel is None:
            # Linux: observe_atomic.dll does not exist. The clock pump and the observation publisher (shared memory with
            # the engine) are off; the test sends the engines' clock reports itself. The money path uses neither.
            import clock_pump,observe_bridge
            for module in (clock_pump,observe_bridge):p=patch.object(module,'poll',lambda bridge:None);p.start();self.addCleanup(p.stop)
        import network_diagnostics;self.addCleanup(lambda:network_diagnostics.flush(5))
        self.cities={}
        # The host's one draw per coup (throne_play: secrets.randbelow) is set by the test where an outcome is needed
        # (stated stand-in; the real code still draws once, stores the value and never draws again).
        import throne_play
        self.draws=[];real=throne_play.secrets.randbelow
        p=patch.object(throne_play.secrets,'randbelow',lambda n:self.draws.pop(0) if self.draws else real(n));p.start();self.addCleanup(p.stop)

    # ---------------- room, players, clock
    def make_room(self,name,restore=None):
        import room_host,threading
        if not restore:
            for i,c in enumerate(['player1','player2','player3','player4']):self.cities[c]=City(i+1,FUNDS)
        saves={c:city.save() for c,city in self.cities.items()}
        with patch.object(room_host,'Engine',fake_engine(saves)),patch.object(room_host,'verify_city',lambda *a:None):
            server=room_host.create_room(self.tmp/name,restore=restore,project=PROJECT)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        room=server.coordinator
        with closing(room.coordinator.connect()) as db:
            parts={r[0]:bytes(r[1]) for r in db.execute('SELECT id,save FROM city')}
        for i,c in enumerate(sorted(parts)):
            if c not in self.cities:self.cities[c]=City(i+1,FUNDS)
            if restore:self.cities[c].load(parts[c])     # the new room's city files are the saved ones
        return dict(server=server,room=room,root=self.tmp/name,configs=[self.tmp/name/f'player-{i+1}.json' for i in range(len(parts))])
    def bridge(self,room,index,city,again=False):
        import game_bridge
        folder=self.tmp/city/room['root'].name;folder.mkdir(parents=True,exist_ok=again)   # same parent per player: its own record store
        b=game_bridge.Bridge(room['configs'][index],folder);self.addCleanup(b.close);self.addCleanup(b.client.disconnect)
        b.step();(b.root/'command.txt').write_text('choose-city\n'+city,encoding='utf8')
        for _ in range(3):b.step()
        self.assertEqual(b.client.city,city);return b
    def start(self,room,bridges):
        # The host confirms the room options as they are and every player acknowledges them (what the lobby screens do).
        host=bridges['player1'];view=host.client.call('lobby_view',invite=host.config['invite'])
        opts=view['room_options']
        if not opts['initialized']:
            opts=host.client.call('room_options_set',invite=host.config['invite'],revision=opts['revision'],values=opts['values'])
        for b in bridges.values():b.client.call('room_options_ack',invite=b.config['invite'],revision=opts['revision'])
        for b in bridges.values():b.client.call('lobby_ready',ready=True)
        host=bridges['player1'];start=host.client.call('room_start')['start']
        with closing(room['room'].coordinator.connect()) as db:
            for c,b in bridges.items():
                save=db.execute('SELECT save FROM city WHERE id=?',(c,)).fetchone()[0]
                from coordinator import sha
                b.client.call('start_loaded',attempt=start['attempt'],layout=start['layout'],save_hash=sha(save))
        deadline=time.time()+20
        while not room['room'].started and time.time()<deadline:
            for b in bridges.values():b.client.call('lobby_status')
            time.sleep(0.25)
        self.assertTrue(room['room'].started)
        for b in bridges.values():b.client.call('play_begin')
    def clock(self,room,bridges,target):
        """The engines' clock reports (stand-in): all cities walk up to `target` within the room's grant."""
        lobby=room['room']
        for _ in range(4000):
            now=min(lobby.grant,target)
            for b in bridges.values():b.client.call('clock',ticks=now)
            if now>=target:return now
        self.fail('clock did not reach '+str(target))
    def pump(self,bridges,rounds=6,skip=()):
        """Bridge steps + city mailboxes. A city in `skip` takes no request (its game is busy or gone)."""
        for _ in range(rounds):
            for c,b in bridges.items():
                b.cash_next=0
                b.step()
                if c not in skip:self.cities[c].pump(b.root)
    def take_debit(self,b,amount):
        """Run this player's mailbox until its city has taken the debit (or a refund: negative amount), and stop
        there: the response is written by the city but not yet read by the bridge (the host has not heard)."""
        city=self.cities[b.client.city];start=city.treasury
        for _ in range(12):
            b.cash_next=0;b.step();city.pump(b.root)
            if city.treasury==start-amount:return
        self.fail('money did not move')
    def command(self,b,text):
        (b.root/'command.txt').write_text('throne\n'+text+'\n'+str(self.cities[b.client.city].treasury),encoding='utf8');b.step()
    def own(self,b):return b.client.call('throne_mine')
    def hud(self,b):return (b.root/'throne-box.txt').read_text(encoding='utf8')+(b.root/'throne-dialog.txt').read_text(encoding='utf8')   # the box and the open dialog (2026-11-14)
    def fixture(self,room,city,**values):
        """TEST FIXTURE ONLY (allowed): a finalist's stage/paranoia in the room's record; validated by the real code."""
        import throne_state as ts,throne_rules as tr
        lobby=room['room']
        with lobby.lock,closing(lobby.coordinator.connect()) as db:
            st=ts.current(db,lobby.coordinator.scenario);p=st['players'][city]
            for k in ('stage',):
                if k in values:p['stage']=values.pop(k)
            p['secret'].update(values);p['secret']['next_cost']=ts.expected_cost(st['spec']['rules'],p['stage'],p['secret']['failures'])
            ts.store(db,st,lobby.coordinator.scenario);db.commit()
    def joint_save(self,room,bridges):
        lobby=room['room'];host=bridges['player1']
        tick=self.clock(room,bridges,lobby.grant)
        saved=host.client.call('save_begin',request_id=uuid.uuid4().hex)
        self.clock(room,bridges,saved['ticks'])
        for c,b in bridges.items():b.client.call('save_part',id=saved['id'],ticks=saved['ticks'],save=base64.b64encode(self.cities[c].save()).decode())
        status=host.client.call('save_status');self.assertEqual(status['complete']['id'],saved['id'])
        self.pump(bridges,rounds=2)                   # each player fetches and keeps its own opening (throne_client.sync)
        return saved
    def spend_states(self,room):
        import throne_state as ts
        lobby=room['room']
        with lobby.lock,closing(lobby.coordinator.connect()) as db:
            st=ts.current(db,lobby.coordinator.scenario)
        return {c:[(e['kind'],e['state'],e['result'],e['amount'],e['seq']) for e in p['secret']['spends']] if 'secret' in p else 'pending' for c,p in st['players'].items()},st

    # ---------------- the flows
    def test_spend_end_refund_save_reload_and_handover(self):
        os.environ['AUGUSTUS_C3_DATA']=DATA
        a=self.make_room('room-a')
        names=['player1','player2','player3','player4']
        bridges={c:self.bridge(a,i,c) for i,c in enumerate(names)}
        self.start(a,bridges);self.clock(a,bridges,50)
        # 1. a coup funding from the panel, through TCP, charged by the city's real C mailbox
        p3=bridges['player3'];self.command(p3,'coup');self.assertIn('amount\t지원 금액\t5,000 Dn',self.hud(p3))
        self.command(p3,'go');self.pump(bridges)
        own=self.own(p3)
        self.assertTrue(own['active']);self.assertEqual(own['last']['state'],'done')
        self.assertEqual(self.cities['player3'].treasury,FUNDS-5000)
        # 2. two finalists at the same tick; player2 accepted first, player1's receipt reaches the host first
        self.fixture(a,'player1',stage=4,paranoia=50);self.fixture(a,'player2',stage=4,paranoia=50)
        tick=self.clock(a,bridges,1600)
        p1,p2=bridges['player1'],bridges['player2']
        for b in (p2,p1):self.command(b,'coup')                 # the panel starts at the 80,000 Dn minimum
        self.assertEqual((p1.throne_ui['quote']['amount'],p1.throne_ui['quote']['chance_text']),(80000,'15.00%'))
        self.draws+=[0,0];self.command(p2,'go');self.command(p1,'go')      # both draws succeed (TEST INPUT)
        states,_=self.spend_states(a);self.assertLess(states['player2'][-1][4],states['player1'][-1][4])   # acceptance order kept
        self.take_debit(p2,80000)                                   # player2's city pays, the host has not heard yet
        self.pump({'player1':p1},rounds=4)                          # player1's debit taken and confirmed first
        self.pump({'player2':p2},rounds=4)                          # player2's afterwards
        states,st=self.spend_states(a)
        self.assertEqual((st['winner'],st['ended']),('player1',True))
        self.assertIn(states['player2'][-1][1],('refunding','refunded','cancelled'))
        self.pump({'player1':p1},rounds=1);self.assertIn('state\tended',self.hud(p1))
        # 3. the end and a joint save overlap: player2's refund is under way when the save starts
        saved=self.joint_save(a,bridges)
        self.pump(bridges)
        states,_=self.spend_states(a)
        if states['player2'][-1][1]=='refunding':self.pump(bridges)
        states,_=self.spend_states(a)
        self.assertEqual(states['player2'][-1][1],'refunded');self.assertEqual(self.cities['player2'].treasury,FUNDS)
        self.assertEqual(self.cities['player1'].treasury,FUNDS-80000)
        self.assertIn('돌려받았습니다',self.hud(p2))
        # 5. new requests after the end are refused without a charge
        before=self.cities['player4'].treasury;self.command(bridges['player4'],'coup')
        self.assertIn('state\tended',self.hud(bridges['player4']));self.assertNotIn('kind\t',self.hud(bridges['player4']));self.command(bridges['player4'],'go');self.pump(bridges,rounds=2)
        self.assertEqual(self.cities['player4'].treasury,before)
        # 6. the ended room saved and restored by its own host: nothing is charged or refunded again
        saved=self.joint_save(a,bridges);snapshot={c:city.save() for c,city in self.cities.items()}
        b=self.make_room('room-a2',restore=a['root']/'room.sqlite')
        nb={c:self.bridge(b,i,c) for i,c in enumerate(names)}
        self.start(b,nb);self.pump(nb,rounds=4)
        states,st=self.spend_states(b);self.assertEqual(st['winner'],'player1')
        self.assertEqual(states['player2'][-1][1],'refunded')
        self.assertEqual((self.cities['player1'].treasury,self.cities['player2'].treasury),(FUNDS-80000,FUNDS))

    def test_refund_after_end_continues_across_handover_and_lost_ack(self):
        os.environ['AUGUSTUS_C3_DATA']=DATA
        a=self.make_room('room-b')
        names=['player1','player2','player3','player4']
        bridges={c:self.bridge(a,i,c) for i,c in enumerate(names)}
        self.start(a,bridges);self.clock(a,bridges,50)
        p3=bridges['player3'];self.command(p3,'coup');self.command(p3,'go');self.pump(bridges)   # paranoia on
        self.fixture(a,'player1',stage=4,paranoia=50);self.fixture(a,'player2',stage=4,paranoia=50)
        self.clock(a,bridges,1600)
        p1,p2=bridges['player1'],bridges['player2']
        self.draws+=[0,0]
        for b in (p1,p2):self.command(b,'coup');self.command(b,'go')
        # player2's city takes its debit, but the host hears nothing yet; player1 ends the trial
        self.take_debit(p2,80000)
        self.pump({'player1':p1},rounds=4)
        _,st=self.spend_states(a);self.assertEqual(st['winner'],'player1')
        # joint save now: player2's spend is still 'charging' (taken in its city, unknown to the host)
        saved=self.joint_save(a,{c:bridges[c] for c in names})
        # host crash; player3 keeps a backup replica; a new host restores it (sealed records only)
        # player3's bridge keeps its backup copy by itself after a complete save (replica worker in the bridge loop)
        for _ in range(40):
            found=sorted((self.tmp/'player3').glob(f"host-backup-*-{saved['id']}/room.sqlite"))
            if found:break
            self.pump({'player3':bridges['player3']},rounds=1);time.sleep(0.1)
        self.assertTrue(found,'the bridge made no backup copy');replica=found[-1]
        old_seq={c:v[-1][4] for c,v in self.spend_states(a)[0].items() if v!='pending' and v}
        # player2's own record store is not reachable yet (moved aside): after the restore its record stays pending
        held=self.tmp/'player2'/'throne-own';held.rename(held.with_name('throne-own.hold'))
        b=self.make_room('room-b2',restore=replica)
        nb={c:self.bridge(b,i,c) for i,c in enumerate(names)}
        self.start(b,nb);self.pump(nb,rounds=4)
        states,st=self.spend_states(b)
        self.assertEqual(states['player2'],'pending');self.assertEqual(st['winner'],'player1')
        self.assertEqual(self.cities['player2'].treasury,FUNDS-80000)          # its city save holds the debit
        # a new request is accepted while player2's record is still sealed: it goes after every earlier one
        self.fixture(b,'player4',paranoia=60)
        p4=nb['player4'];self.command(p4,'gift')
        self.assertIn('state\tended',self.hud(p4));self.assertNotIn('kind\t',self.hud(p4))   # the race has ended: no dialog opens, no charge
        self.command(p4,'go');self.assertEqual(self.cities['player4'].treasury,FUNDS)
        # player2's record store comes back; its bridge hands the record in; the late receipt is refunded
        for f in held.with_name('throne-own.hold').glob('*.json'):shutil.copy2(f,held/f.name)   # the player's own records are back
        self.pump(nb,rounds=2,skip=('player2',))                                # others go on; player2 hands its record in
        p2b=nb['player2']
        for _ in range(12):                                                      # player2's mailbox, one exchange at a time
            states,st=self.spend_states(b)
            if states['player2']!='pending' and states['player2'][-1][1]=='refunding':break
            p2b.cash_next=0;p2b.step();self.cities['player2'].pump(p2b.root)
        states,st=self.spend_states(b);self.assertNotEqual(states['player2'],'pending')
        self.assertEqual(states['player2'][-1][4],old_seq['player2'])             # acceptance order kept through the handover
        self.assertEqual(states['player2'][-1][1],'refunding')
        # the refund is taken by the city, then the connection drops before the host hears (acknowledgement lost);
        # the same bridge reconnects (a network drop does not restart the game or its mailbox)
        self.take_debit(nb['player2'],-80000)
        nb['player2'].client.disconnect()
        self.pump(nb,rounds=6)
        states,_=self.spend_states(b)
        self.assertEqual(states['player2'][-1][1],'refunded');self.assertEqual(self.cities['player2'].treasury,FUNDS)   # once
        self.pump(nb,rounds=4);self.assertEqual(self.cities['player2'].treasury,FUNDS)

if __name__=='__main__':unittest.main()
