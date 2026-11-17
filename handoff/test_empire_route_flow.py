"""In-game empire map trade lines: the delivery from host to the game file, end to end without any window.

Real parts: Coordinator, Lobby (room host request handling), coordinator.Server on 127.0.0.1 (real TCP), the real
city_client.Client inside the real game_bridge.Bridge, driven by its own command file and step() loop, and the real
empire_route_display / empire_paths code on both sides. The file is then read by the real C reader
(route_display.h via handoff/route_display_probe.c) when a C compiler is available.
Stand-ins (stated, not hidden):
  * the room is made like test_lobby_selection: Coordinator + provision() with the review151 fixture saves, instead
    of room_host.create_room (which starts every city in the engine);
  * route-state.txt (contract state) is written by the real route_bridge.publish with the room's real route_status
    answer; in a running game live_sync calls it, which needs a started game and the engine;
  * no game window: what the game draws from the file is a user screen check.
Needs the game data (AUGUSTUS_C3_DATA) and the review151 fixtures, like test_lobby_selection.
"""
import json,os,shutil,subprocess,sys,tempfile,threading,unittest,uuid
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Augustus'))
DATA=os.environ.get('AUGUSTUS_C3_DATA')
FIXTURE=ROOT/'handoff/review151'
CC=os.environ.get('AUGUSTUS_CC') or shutil.which('gcc')

def parse_text(text):
    """Python reading of AUGROUTES2 (the C reader is checked separately when a compiler exists)."""
    lines=text.splitlines();assert lines[0]=='AUGROUTES2';n=int(lines[1]);out=[]
    for i in range(n):
        kind,sea,a,b,mine,active,shape,count=map(int,lines[2+2*i].split());v=list(map(int,lines[3+2*i].split()))
        assert len(v)==2*count
        out.append(dict(kind=kind,sea=sea,a=a,b=b,mine=mine,active=active,shape=shape,points=[v[k:k+2] for k in range(0,len(v),2)]))
    assert len(lines)==2+2*n
    return out

@unittest.skipUnless(DATA and (FIXTURE/'scenario.json').is_file() and (FIXTURE/'prepared-1/checked/city.sav').is_file(),'game data and review151 fixtures required')
class Flow(unittest.TestCase):
    def setUp(self):
        self.tmp=Path(tempfile.mkdtemp());self.addCleanup(shutil.rmtree,self.tmp,True)
        import network_diagnostics
        self.addCleanup(lambda:network_diagnostics.flush(5))
    def room(self,name,project=None,write_project=True):
        from coordinator import Coordinator,Server
        from lobby import Lobby
        from scenario_project import load,write_layout
        from scenario_pair import load_pair
        run=self.tmp/name;run.mkdir()
        manifest=project or load(FIXTURE/'scenario.json');_,binding=load_pair(Path(DATA),manifest)
        write_layout(manifest,run)
        if write_project:(run/'scenario-project.json').write_text(json.dumps(manifest,ensure_ascii=False),encoding='utf8')
        co=Coordinator(run/'room.sqlite',uuid.uuid4().hex,binding)
        for i,c in enumerate(binding['cities'],1):
            f=FIXTURE/f'prepared-{min(i,3)}/checked';co.provision(c,(f/'city.sav').read_bytes(),(f/'receipt.bin').read_bytes())
        lobby=Lobby(co);server=Server(lobby,'127.0.0.1',0)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        return dict(co=co,lobby=lobby,server=server,binding=binding,manifest=manifest,run=run)
    def bridge(self,room,city,folder,invite=None):
        import game_bridge
        from coordinator import PROTOCOL,BUILD
        cfg=dict(protocol=PROTOCOL,build=BUILD,session=room['co'].session,scenario=room['binding']['sha256'],host='127.0.0.1',port=room['server'].server_address[1],invite=invite or room['lobby'].invite())
        path=self.tmp/(folder+'-'+uuid.uuid4().hex[:6]+'.json');path.write_text(json.dumps(cfg))
        b=game_bridge.Bridge(path,self.tmp/folder);self.addCleanup(b.close);self.addCleanup(b.client.disconnect)
        asked=[];real=b.client.call
        def counted(op,**k):
            if op=='empire_routes':asked.append(op)
            return real(op,**k)
        b.client.call=counted;b.asked=asked;b.invite=cfg['invite']
        b.step()                                                     # lobby view: the room's city list
        (b.root/'command.txt').write_text('choose-city\n'+city,encoding='utf8')
        for _ in range(3):b.step()
        self.assertEqual(b.client.city,city);self.assertTrue(b.joined)
        return b
    def routes(self,b):return parse_text((b.root/'empire-routes.txt').read_text(encoding='utf8'))
    def shapes(self,rows):return sorted((r['kind'],r['sea'],r['a'],r['b'],r['shape'],json.dumps(r['points'])) for r in rows)

    def test_delivery_two_players_contract_reconnect_and_new_room(self):
        import empire_paths,route_bridge
        a=self.room('a')
        b1=self.bridge(a,'player1','p1');b2=self.bridge(a,'player2','p2')
        r1,r2=self.routes(b1),self.routes(b2)
        relations=[r for r in empire_paths.relations(a['manifest'])]
        self.assertEqual(len(r1),len(relations));self.assertGreater(len(r1),20)
        self.assertEqual(self.shapes(r1),self.shapes(r2))                         # same scenario, same lines
        self.assertTrue(any(r['shape']==0 for r in r1))
        self.assertTrue(all(len(r['points'])==2 for r in r1 if r['shape']==1))     # stand-ins are straight
        names={s['id']:s['name_id'] for s in a['manifest']['slots']}
        mine1={(r['a'],r['b']) for r in r1 if r['mine']}
        self.assertTrue(all(names['player1'] in pair for pair in mine1))
        self.assertEqual(b1.asked,['empire_routes'])
        for _ in range(3):b1.step()
        self.assertEqual(b1.asked,['empire_routes'])                              # asked once, not per step
        pair=tuple(sorted((names['player1'],names['player2'])))
        line=lambda rows:next(r for r in rows if (r['a'],r['b'])==pair and r['kind']==0)
        self.assertEqual(line(r1)['active'],0)
        # contract offered and accepted over the real room, published by the real route bridge
        offer=b1.client.call('route_offer',peer='player2',request_id=uuid.uuid4().hex)
        b2.client.call('route_accept',peer='player1',revision=offer['revision'])
        for b in (b1,b2):
            route_bridge.publish(b,b.client.call('route_status'),a['binding']['cities']);b.step()
        self.assertEqual(line(self.routes(b1))['active'],1);self.assertEqual(line(self.routes(b2))['active'],1)
        # reconnect: a new bridge process for the same player asks again and writes the file again
        (b1.root/'empire-routes.txt').unlink()
        again=self.bridge(a,'player1','p1',invite=b1.invite)
        self.assertEqual(again.asked,['empire_routes']);self.assertEqual(self.shapes(self.routes(again)),self.shapes(r1))
        # another room with another scenario, same bridge folder: nothing of room a stays
        project=json.loads(json.dumps(a['manifest']))
        for c in project['empire']['cities']:
            if c['role']=='npc':c['enabled']=False
        b_room=self.room('b',project)
        other=self.bridge(b_room,'player1','p1')
        rows=self.routes(other)
        self.assertEqual(len(rows),len(empire_paths.relations(project)))
        self.assertTrue(all(r['kind']==0 for r in rows))                          # room a's neutral lines are gone
        if CC:self.native(other.root/'empire-routes.txt',len(rows))

    def test_failures_never_block_the_room_or_trade(self):
        import empire_paths
        # 1. path making fails on the host: the room opens, the answer is empty, trade still works
        with patch.object(empire_paths,'display_routes',side_effect=RuntimeError('broken')):
            c=self.room('c')
        self.assertEqual(c['lobby'].empire_routes['routes'],[])
        b1=self.bridge(c,'player1','c1');b2=self.bridge(c,'player2','c2')
        self.assertEqual(self.routes(b1),[])
        offer=b1.client.call('route_offer',peer='player2',request_id=uuid.uuid4().hex)
        self.assertEqual(b2.client.call('route_accept',peer='player1',revision=offer['revision'])['state'],'active')
        # 2. no project file (older scenario): empty answer, the room works
        d=self.room('d',write_project=False);self.assertEqual(d['lobby'].empire_routes['routes'],[])
        self.assertEqual(self.routes(self.bridge(d,'player1','d1')),[])
        # 3. unreadable passage data: every relation still delivered, as straight stand-ins only
        with patch.object(empire_paths,'load',side_effect=OSError('missing')):
            e=self.room('e')
        rows=self.routes(self.bridge(e,'player1','e1'))
        self.assertGreater(len(rows),20);self.assertEqual({r['shape'] for r in rows},{1})
        # 4. a damaged cache beside the project is not trusted: it is made again
        f=self.room('f');(f['run']/'empire-routes-cache.json').write_text('{broken',encoding='utf8')
        import empire_route_display
        self.assertEqual(empire_route_display.host_routes(f['run']/'room.sqlite'),f['lobby'].empire_routes)
        # 5. the host answers something malformed: the bridge keeps an empty file and keeps working
        g=self.room('g');g['lobby'].empire_routes={'routes':[{'kind':'x'}]}
        bg=self.bridge(g,'player1','e1')                            # the folder still holds room e's lines
        self.assertEqual(self.routes(bg),[]);bg.step()

    def native(self,path,expected):
        exe=self.tmp/('probe.exe' if os.name=='nt' else 'probe')
        r=subprocess.run([CC,'-std=gnu99','-I',str(ROOT/'src'),str(Path(__file__).parent/'route_display_probe.c'),'-o',str(exe),'-lm'],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)
        out=subprocess.run([str(exe),'parse',str(path)],capture_output=True,text=True).stdout.split()
        self.assertEqual(out[:2],['ok',str(expected)])

if __name__=='__main__':unittest.main()
