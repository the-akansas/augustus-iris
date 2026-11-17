"""시나리오 제작자 방 on a player's PC (user 2026-11-17: "다 똑같이 가는거 아니야?"): the LAN's 방 만들기 has the same
시나리오 제작자 모드 as the game hall, in both editions (maker_room.py, multiplayer_room.inc lan_maker)."""
import shutil,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
ROOT=Path(__file__).resolve().parents[1];A=ROOT/'Augustus'
sys.path.insert(0,str(A));sys.path.insert(0,str(ROOT/'tools'))
import maker_room,start_catalog

def folder(test):
    d=Path(tempfile.mkdtemp());test.addCleanup(shutil.rmtree,d,True);return d

class Flag(unittest.TestCase):
    def test_mark_and_read(self):
        d=folder(self);server=SimpleNamespace(coordinator=SimpleNamespace())
        maker_room.mark(server,d,False);self.assertFalse(server.coordinator.dev_mode);self.assertFalse(maker_room.is_maker(d/'room.sqlite'))
        maker_room.mark(server,d,True);self.assertTrue(server.coordinator.dev_mode);self.assertTrue(maker_room.is_maker(d/'room.sqlite'))
    def test_saves_continue_only_in_the_same_kind_of_room(self):
        d=folder(self);normal=d/'a'/'room.sqlite';maker=d/'b'/'room.sqlite'
        for p in (normal,maker):p.parent.mkdir()
        (maker.parent/maker_room.MARK).write_text('1\n')
        self.assertTrue(maker_room.check(True,None));self.assertFalse(maker_room.check(False,None))   # a new game: what was ticked
        self.assertFalse(maker_room.check(False,normal));self.assertTrue(maker_room.check(True,maker))
        with self.assertRaisesRegex(ValueError,'제작자 방에서만'):maker_room.check(False,maker)
        with self.assertRaisesRegex(ValueError,'일반 방의 저장은'):maker_room.check(True,normal)
    def test_save_list_names_maker_saves(self):
        d=folder(self);entries=[]
        for i,name in enumerate(('a','b')):
            (d/name).mkdir();entries.append(dict(database=str(d/name/'room.sqlite'),id=1,available=True,sort_time=i,modified='2026-11-17 04:00:00',title='시험',date='기원전 350년 1월',status='복원 시 해시 검증'))
        (d/'b'/maker_room.MARK).write_text('1\n')
        rows={Path(r['restore']).parent.name:r for r in start_catalog.save_choices(entries,'p.json')}
        self.assertTrue(rows['b']['label'].endswith(' · 제작자 방'));self.assertNotIn('제작자',rows['a']['label'])
        self.assertNotIn('dev',rows['b'])   # the request carries what was ticked; the save's own flag is read again (check)

class ChosenKeys(unittest.TestCase):
    """rules.maker_tools (user 2026-11-17: the author picks the test keys; by mode, without conflicts)."""
    def load(self,name):
        import json
        return json.loads((A/'scenarios'/name/'scenario.json').read_text(encoding='utf-8-sig'))
    def test_mode_decides_what_can_be_chosen(self):
        import scenario_project as sp
        self.assertEqual(sp.maker_tools(self.load('coop-6p')),['money','invade','favor','goods'])
        self.assertEqual(sp.maker_tools(self.load('throne-6p')),['money','invade','favor','goods','throne'])
        self.assertEqual(sp.maker_tools(self.load('progress-6p')),['money','invade','favor','goods','progress'])
        for name,bad in (('coop-6p','throne'),('coop-6p','progress'),('throne-6p','progress'),('progress-6p','throne')):
            d=self.load(name);d['rules']['maker_tools']=['money',bad]
            with self.assertRaisesRegex(ValueError,'방식에는 없는'):sp.validate(d)
        for wrong in ('money',['money','money'],['cash'],[1]):
            d=self.load('coop-6p');d['rules']['maker_tools']=wrong
            with self.assertRaises(ValueError):sp.validate(d)
        d=self.load('throne-6p');d['rules']['maker_tools']=['throne'];sp.validate(d)
        self.assertEqual(sp.maker_tools(d),['throne'])
        d['rules']['maker_tools']=[];self.assertEqual(sp.maker_tools(sp.validate(d)),[])   # none at all is a choice too
    def test_room_refuses_keys_the_scenario_left_out(self):
        import lobby
        room=lobby.Lobby.__new__(lobby.Lobby);room.dev_mode=True;room._maker_tools=['money','favor']
        with self.assertRaisesRegex(ValueError,'쓰지 않습니다'):room.dev_tools('throne')
        with self.assertRaisesRegex(ValueError,'쓰지 않습니다'):room.dev_tools('progress')
        room._maker_tools=['throne'];import dev_tools;self.assertIs(room.dev_tools('throne'),dev_tools)
        normal=lobby.Lobby.__new__(lobby.Lobby);normal.dev_mode=False
        with mock.patch.dict(sys.modules,{'mp_test_tools':None}):
            with self.assertRaises(ValueError):normal.dev_tools('throne')   # a normal room: unknown, as before
    def test_bridge_tells_the_game(self):
        import game_bridge
        written={}
        b=SimpleNamespace(write_changed=lambda name,text:written.__setitem__(name,text))
        src=(A/'game_bridge.py').read_text(encoding='utf-8')
        line=next(l for l in src.splitlines() if "write_changed('room-dev.txt'" in l and 'dev_tools' in l).strip()
        for state,want in ((dict(dev=True,dev_tools=['money','throne']),'1 money,throne'),(dict(dev=True,dev_tools=[]),'1 -'),(dict(),'')):
            exec(line.split('   #')[0].replace('self.','b.'),dict(b=b,state=state));self.assertEqual(written['room-dev.txt'],want)
        game=(ROOT/'src/window/multiplayer_dev.inc').read_text(encoding='utf-8')
        for key in ('"money"}','"invade"}','"favor"}','"goods"}','dev_allows("throne")','dev_allows("progress")','building_warehouses_add_resource(dev_goods,DEV_GOODS_LOADS,0)'):self.assertIn(key,game)
        self.assertNotIn('t-hide',game)   # no 숨기기: the 제작 button opens and closes (user 2026-11-17)

class Editions(unittest.TestCase):
    def test_tools_are_in_both_editions(self):
        import make_release as M
        for name in ('dev_tools.py','multiplayer_dev.inc','maker_room.py'):self.assertNotIn(name,M.KOREAN_ONLY)
        self.assertIn('test_dev_rooms.py',M.KOREAN_ONLY)   # the game hall's part
    def test_screen_and_bridge_agree(self):
        room=(ROOT/'src/window/multiplayer_room.inc').read_text(encoding='utf-8')
        self.assertIn('snprintf(value,sizeof(value),"%d %d %d\\n%s",network_adapter,network_start,lan_maker?1:0,name);',room)
        play=(A/'network_play.py').read_text(encoding='utf-8')
        self.assertIn("if len(numbers) not in (2,3):raise ValueError('select scenario')",play)   # an older game's two numbers still work
        self.assertIn("maker_room.mark(self.server,room,dev)",play)
        for f in ('migration.py','recovery_group.py'):self.assertIn('maker_room.mark(server,target,',(A/f).read_text(encoding='utf-8'),f)   # a new host keeps it

class RealRoom(unittest.TestCase):
    def test_a_marked_room_answers_the_tools(self):
        sys.path.insert(0,str(Path(__file__).resolve().parent))
        import test_throne_room_flow as F
        if not (F.DATA and F.native_library(1)):self.skipTest('needs AUGUSTUS_C3_DATA and the C library: '+F._why)
        import room_host
        from contextlib import closing
        for dev in (False,True):
            d=folder(self)/'room'
            with mock.patch('connection_config.engine_hash',lambda:'0'*64):
                server=room_host.create_room(d,project=A/'scenarios'/'freebuild-2p'/'scenario.json')
            self.addCleanup(server.server_close)
            maker_room.mark(server,d,dev);lobby=server.coordinator
            with closing(lobby.coordinator.connect()) as db:status=lobby.status(db)
            self.assertEqual(bool(status.get('dev')),dev)
            if dev:
                import dev_tools;self.assertIs(lobby.dev_tools(),dev_tools)
            else:
                with mock.patch.dict(sys.modules,{'mp_test_tools':None}):
                    with self.assertRaises(ValueError):lobby.dev_tools()

if __name__=='__main__':unittest.main()
