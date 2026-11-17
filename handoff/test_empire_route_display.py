"""In-game empire map trade paths (display only): host answer, player file, the game's reader and dash drawing.

Checked here:
  * every real relation and only those (same answer as the editor's checks and the game's empire build);
  * the host computes once per project and reuses its cache; a room without a project answers with no routes;
  * the player file marks own relations and contracts in force; a relation without a terrain path is written as a
    straight stand-in between its two cities (shape 1), never as a terrain path; a relation whose cities have no
    position is left out (nothing is guessed);
  * the bridge asks once per scenario layout, spaces retries, and never raises (trade is never held up);
  * the C reader (route_display.h) accepts the file and refuses a damaged one as a whole; the dashes are long
    pieces with gaps (no dots), follow the path and keep their rhythm across bends;
  * the empire window draws them under cities and caravan icons, re-reads the file only when it changes, leaves the
    caravan/ship icon movement as it was, never draws the original dotted route in multiplayer, and draws the trade
    routes and contracts the game itself knows as straight dashed stand-ins when the file has nothing for them.
"""
import copy,json,os,shutil,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Augustus'))
import empire_route_display as erd,empire_paths as ep,scenario_check as sc,scenario_project as sp,creator_presets

def project(n=4,neutrals=True):
    d=creator_presets.default_project(n)
    if neutrals:
        ids=[s['id'] for s in d['slots']]
        for c in d['empire']['cities']:
            if c['role']=='npc' and not c.get('reserved'):c['enabled']=True;c['trade_players']=ids[:2]
    return d

class Relations(unittest.TestCase):
    def test_same_relations_as_the_checks(self):
        d=project(4);d['rules']['player_trade']=dict(exceptions=[dict(between=sorted(['player1','player3']),allow=False)]);sp.validate(d)
        slot_name={s['id']:s['name_id'] for s in d['slots']}
        mine=set()
        for kind,transport,a,b,sa,sb in ep.relations(d):
            if kind=='player':mine|={(sa,slot_name[sb],'player'),(sb,slot_name[sa],'player')}
            else:
                slot,other=(sa,b) if sa else (sb,a);mine.add((slot,other,'neutral',transport))
        theirs=set()
        for g in sc.check(d,None,sc.evidence(d))['links']:
            for l in g['links']:
                if not l['allowed']:continue
                if l['kind']=='player':theirs.add((g['slot'],slot_name[l['slot']],'player'))
                else:theirs.add((g['slot'],l['name_id'],'neutral',l['transport']))
        self.assertEqual(mine,theirs)
        self.assertNotIn(('player1',slot_name['player3'],'player'),mine)       # a forbidden pair is not drawn
    def test_disabled_and_reserved_cities_have_no_relation(self):
        d=project(4,neutrals=False)
        names={c['name_id'] for c in d['empire']['cities'] if c['role']=='npc'}
        self.assertFalse(any(k=='neutral' for k,*_ in ep.relations(d)))
        self.assertTrue(names)
    def test_player_transport_follows_the_rule(self):
        d=project(2,neutrals=False);d['rules']['player_transport']='sea'
        self.assertEqual({r[1] for r in ep.relations(d) if r[0]=='player'},{'sea'})

class Host(unittest.TestCase):
    def test_room_without_project(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(erd.host_routes(Path(t)/'room.sqlite')['routes'],[])
    def test_computed_once_and_cached_per_project(self):
        with tempfile.TemporaryDirectory() as t:
            room=Path(t)/'room.sqlite';d=project(4)
            (Path(t)/'scenario-project.json').write_text(json.dumps(d,ensure_ascii=False),encoding='utf8')
            first=erd.host_routes(room);calls=[]
            original=ep.display_routes;ep.display_routes=lambda *a,**k:calls.append(1) or original(*a,**k)
            try:
                self.assertEqual(erd.host_routes(room),first);self.assertEqual(calls,[])            # cache reused
                d['empire']['cities'][0]['y']+=1
                (Path(t)/'scenario-project.json').write_text(json.dumps(d,ensure_ascii=False),encoding='utf8')
                erd.host_routes(room);self.assertEqual(calls,[1])                                   # project changed
            finally:ep.display_routes=original
            self.assertTrue(erd._valid(first))
            self.assertEqual(len(first['routes']),len(ep.relations(d)))

def answer(d):return ep.display_routes(d)
def slots(d):return [dict(city=s['id'],name_id=s['name_id']) for s in d['slots']]

class PlayerFile(unittest.TestCase):
    def test_mine_and_contracts(self):
        d=project(4);a=answer(d);own='player1';own_name=d['slots'][0]['name_id']
        text=erd.encode(a,own,slots(d),{'player2':1,'player3':3})
        lines=text.splitlines();self.assertEqual(lines[0],'AUGROUTES2');n=int(lines[1])
        heads=[list(map(int,lines[2+2*i].split())) for i in range(n)]
        p2=next(s['name_id'] for s in d['slots'] if s['id']=='player2');p3=next(s['name_id'] for s in d['slots'] if s['id']=='player3')
        for kind,sea,x,y,mine,active,shape,count in heads:
            if shape==1:self.assertEqual(count,2)
            self.assertEqual(mine,int(own_name in (x,y)))
            if kind==0 and mine:self.assertEqual(active,1 if p2 in (x,y) else 0)      # 3 = offer waiting: not in force
            if not mine or kind==1:self.assertEqual(active,-1)
        self.assertEqual(n,len(a['routes']))
    def test_relation_without_path_is_a_straight_stand_in(self):
        d=project(4);a=copy.deepcopy(answer(d));r=a['routes'][0];r['points']=None
        lines=erd.encode(a,'player1',slots(d),{}).splitlines()
        head=lines[2].split();self.assertEqual((head[6],head[7]),('1','2'))
        self.assertEqual(lines[3],' '.join(f'{x} {y}' for x,y in r['ends']))
    def test_city_without_position_is_not_guessed(self):
        d=project(4);a=copy.deepcopy(answer(d));a['routes'][0].update(points=None,ends=None)
        self.assertEqual(int(erd.encode(a,'player1',slots(d),{}).splitlines()[1]),len(a['routes'])-1)
    def test_bridge_asks_once_and_never_raises(self):
        d=project(2);a=answer(d)
        with tempfile.TemporaryDirectory() as t:
            written={};asked=[]
            class Client:
                city='player1'
                def call(self,op,**k):
                    asked.append(op)
                    if self.fail:raise RuntimeError('host gone')
                    return a
            client=Client();client.fail=False
            b=SimpleNamespace(joined=True,client=client,root=Path(t),write_changed=lambda n,txt:written.__setitem__(n,txt))
            state=dict(layout_version='v1',slots=slots(d))
            for _ in range(3):erd.publish(b,state)
            self.assertEqual(asked,['empire_routes']);self.assertTrue(written['empire-routes.txt'].startswith('AUGROUTES2'))
            client.fail=True;state=dict(state,layout_version='v2')
            erd.publish(b,state);erd.publish(b,state)                                # failure: no exception, spaced retry
            self.assertEqual(asked,['empire_routes','empire_routes'])
            self.assertEqual(written['empire-routes.txt'],erd.EMPTY)                 # nothing of the earlier layout stays
            client.fail=False;b.route_display_retry=0;client.call=lambda op,**k:asked.append(op) or {'routes':[{'kind':'x'}]}
            erd.publish(b,state);self.assertNotEqual(getattr(b,'route_display_for',None),'v2')   # a malformed answer is not used

CC=os.environ.get('AUGUSTUS_CC') or shutil.which('gcc')
@unittest.skipUnless(CC and (ROOT/'src/multiplayer/route_display.h').is_file(),'C compiler needed')
class Native(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.mkdtemp();cls.exe=Path(cls.tmp)/('probe.exe' if os.name=='nt' else 'probe')
        r=subprocess.run([CC,'-std=gnu99','-Wall','-Werror=implicit-function-declaration','-I',str(ROOT/'src'),str(Path(__file__).parent/'route_display_probe.c'),'-o',str(cls.exe),'-lm'],capture_output=True,text=True)
        if r.returncode:raise AssertionError(r.stderr)
    @classmethod
    def tearDownClass(cls):shutil.rmtree(cls.tmp,ignore_errors=True)
    def parse(self,text):
        f=Path(self.tmp)/'routes.txt';f.write_text(text,encoding='utf8',newline='')
        return subprocess.run([str(self.exe),'parse',str(f)],capture_output=True,text=True).stdout.split()
    def test_reader_accepts_the_file_and_refuses_damage(self):
        d=project(6);text=erd.encode(answer(d),'player1',slots(d),{})
        out=self.parse(text);n=int(text.splitlines()[1])
        self.assertEqual(out[:2],['ok',str(n)]);self.assertGreater(n,10)
        self.assertEqual(self.parse(text.replace('\n','\r\n'))[0],'ok')
        lines=text.splitlines()
        for damaged in (text.replace('AUGROUTES2','AUGROUTES1'),'\n'.join(lines[:-1])+'\n',text+'7\n',
                        '\n'.join(['AUGROUTES2','1','0 0 3 3 1 -1 0 2','1 1 2 2'])+'\n','\n'.join(['AUGROUTES2','1','0 0 1 2 1 -1 0 2','1 1 5000 2'])+'\n',
                        '\n'.join(['AUGROUTES2','1','0 0 1 2 1 -1 0 1','1 1'])+'\n','\n'.join(['AUGROUTES2','1','0 0 1 2 1 -1 2 2','1 1 2 2'])+'\n',
                        '\n'.join(['AUGROUTES2','1','0 0 1 2 1 -1 1 3','1 1 2 2 3 3'])+'\n','\n'.join(['AUGROUTES2','1','0 0 1 2 1 -1 2','1 1 2 2'])+'\n'):
            self.assertEqual(self.parse(damaged),['refused','0'])
        self.assertEqual(self.parse('\n'.join(['AUGROUTES2','1','0 0 1 2 1 -1 1 2','1 1 2 2'])+'\n')[:2],['ok','1'])   # a stand-in, valid
    def dashes(self,sea,points):
        r=subprocess.run([str(self.exe),'dashes',str(sea)]+[str(v) for p in points for v in p],capture_output=True,text=True)
        return [tuple(map(float,l.split())) for l in r.stdout.splitlines()]
    def test_long_dashes_no_dots_and_following_the_path(self):
        import math
        path=[(0,0),(100,0),(100,57),(160,90)]
        for sea,longest in ((0,11),(1,14)):
            pieces=self.dashes(sea,path);self.assertGreater(len(pieces),8)
            # join pieces split at a bend: a dash is a run of touching pieces
            dashes=[];cur=0;last=None
            for x1,y1,x2,y2 in pieces:
                if last and abs(last[0]-x1)<1e-3 and abs(last[1]-y1)<1e-3:cur+=math.dist((x1,y1),(x2,y2))
                else:
                    if last:dashes.append(cur)
                    cur=math.dist((x1,y1),(x2,y2))
                last=(x2,y2)
            dashes.append(cur)
            body=dashes[:-1]                                       # the last one may be cut by the path's end
            self.assertTrue(all(d>=4.9 for d in body),dashes)      # never a dot
            self.assertAlmostEqual(max(body),longest,places=2)
            if sea:self.assertTrue(any(abs(d-5)<0.01 for d in body))   # long dash, short dash
            else:self.assertTrue(all(abs(d-11)<0.01 for d in body))
            for x1,y1,x2,y2 in pieces:                             # on the path
                on=lambda x,y:any(abs((bx-ax)*(y-ay)-(by-ay)*(x-ax))/max(math.dist((ax,ay),(bx,by)),1e-9)<1e-2 and min(ax,bx)-1e-3<=x<=max(ax,bx)+1e-3 and min(ay,by)-1e-3<=y<=max(ay,by)+1e-3 for (ax,ay),(bx,by) in zip(path,path[1:]))
                self.assertTrue(on(x1,y1) and on(x2,y2))

class EmpireWindow(unittest.TestCase):
    """The hooks in the empire window (source checks; the drawing itself is checked on screen by the user)."""
    def setUp(self):
        self.c=(ROOT/'src/window/empire.c').read_text(encoding='utf8');self.inc=(ROOT/'src/window/empire_route_paths.inc').read_text(encoding='utf8')
    def test_route_lines_are_not_drawn(self):
        # 2026-11-13 (user): the multiplayer trade lines on the in-game empire map looked wrong and were removed.
        # empire.c neither includes nor calls the drawing; the original route display is back for multiplayer too.
        # Later the same day the user asked for the dotted, pulsing route style between player cities as well:
        # empire_player_dots.inc (test_player_links_use_the_original_dot_style). The dashed lines stay out.
        self.assertNotIn('draw_route_paths',self.c);self.assertNotIn('empire_route_paths.inc',self.c)
        trade=self.c[self.c.index('static void empire_draw_object_trade_route'):];trade=trade[:trade.index('\n}\n')]
        self.assertNotIn('mp_clock_active',trade);self.assertIn('window_empire_draw_static_trade_waypoints(',trade)
    def test_player_links_use_the_original_dot_style(self):
        dots=(ROOT/'src/window/empire_player_dots.inc').read_text(encoding='utf8');code=dots.split('*/',1)[1]
        self.assertIn('#include "empire_player_dots.inc"',self.c)
        draw=self.c[self.c.index('static void draw_map(void)'):];draw=draw[:draw.index('\n}\n')]
        self.assertLess(draw.index('draw_player_link_dots();'),draw.index('empire_object_foreach_of_type(draw_empire_object, EMPIRE_OBJECT_CITY)'))   # under the cities
        self.assertIn('r->kind != 0',code)                                         # player-to-player rows only
        self.assertIn('if (!mine && !shown_for_selection)',code)                  # no web of every pair
        self.assertIn('int in_force = mine && r->active == 1;',code);self.assertIn('if (in_force && animate && dots > 1)',code)   # pulse only on a contract in force
        for word in ('LandRouteDot','SeaRouteDot','TRADE_DOT_SPACING','TRADE_PULSE_DOT_MS','CONFIG_UI_ANIMATE_TRADE_ROUTES','ezx(x)'):self.assertIn(word,code)
        for word in ('graphics_draw_line','mp_route_display_dashes','empire_paths'):self.assertNotIn(word,code)      # no dashed lines, no path finding
        self.assertIn('now - player_links_state.checked_at < 1000',code)          # the file is looked at once a second
    def test_stand_ins_come_only_from_relations_the_game_knows(self):
        body=self.inc[self.inc.index('static void draw_route_paths'):]
        self.assertIn('city->type != EMPIRE_CITY_TRADE',body)                    # own trade routes only
        self.assertIn('trade_city_edges[route->trade_route_id]',body)            # their own legs, straight
        self.assertIn('!route_paths_state.peer_active[i]',body)                  # player lines only for contracts in force
        self.assertIn('file_neutral[city->name_id]',body);self.assertIn('file_player[peer]',body)   # never twice
    def test_no_per_frame_work_and_no_animation(self):
        self.assertIn('now - route_paths_state.checked_at < 1000',self.inc);self.assertIn('stamp == route_paths_state.stamp',self.inc)
        self.assertNotIn('empire_paths',self.inc)
        for word in ('time_get_millis() /','animation','pulse'):self.assertNotIn(word,self.inc.split('*/',1)[1])
    def test_caravan_icons_move_as_before(self):
        t=(ROOT/'src/window/empire_transport.inc').read_text(encoding='utf8')
        self.assertIn('int x=ax+(int)((bx-ax)*p)',t);self.assertNotIn('route_paths',t)

if __name__=='__main__':unittest.main()
