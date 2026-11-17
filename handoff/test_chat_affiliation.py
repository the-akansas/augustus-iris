"""Chat player colours and owner hover text (trade post partner / soldier owner).

Real code, no game data needed:
  * the real Lobby and Coordinator (minimal scenario of 9 cities, city rows inserted directly instead of real saves)
    for lobby_chat_send / chat_send / chat_read / lobby_view / lobby_status;
  * the real bridge functions: game_bridge.Bridge.accept_chat (journal + lobby-chat-colors.txt),
    chat_presentation.journal_key/key_base, affiliation.post_partners/army_owners/publish, affiliation.Recorder;
  * the native parsers: handoff/affiliation_probe.c is compiled with the game's own multiplayer/chat.c and
    widget/city/multiplayer_affiliation.inc when a C compiler and the game source are present (skipped otherwise).
"""
import json,os,shutil,sqlite3,subprocess,sys,tempfile,unittest,uuid
from contextlib import closing
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Augustus'))
CITIES=['capua','tarentum','neapolis','brundisium','sparta','athenae','corinthus','syracusae','messana']
NAMES={c:c.capitalize() for c in CITIES}
WHITE=1   # palette index 1 is the white player (0xfff4f4f0)

class Room:
    def __init__(self,test):
        from coordinator import Coordinator,PROTOCOL,BUILD
        from lobby import Lobby
        d=tempfile.TemporaryDirectory();test.addCleanup(d.cleanup);run=Path(d.name)
        scenario={'cities':CITIES,'sha256':'0'*64,'city_names':NAMES}
        self.co=Coordinator(run/'room.sqlite',uuid.uuid4().hex,scenario)
        with closing(self.co.connect()) as db:
            for c in CITIES:db.execute('INSERT INTO city VALUES(?,?,?,?,NULL)',(c,'-',b'',b''))
            db.commit()
        import network_diagnostics
        test.addCleanup(lambda:network_diagnostics.flush(5))
        self.lobby=Lobby(self.co)
        self.base=dict(protocol=PROTOCOL,build=BUILD,session=self.co.session,scenario=self.co.wire_scenario)
    def call(self,**r):return self.lobby.request(dict(r,**self.base))
    def db(self):return closing(self.co.connect())

def mid():return uuid.uuid4().hex

class LobbyChatColours(unittest.TestCase):
    def setUp(self):self.room=Room(self)
    def test_colour_at_sending_kept_after_reassignment(self):
        r=self.room;invites=[r.lobby.invite() for _ in range(9)];tokens={}
        for i,inv in enumerate(invites):r.call(op='lobby_arrive',invite=inv,name=f'P{i+1}')
        # Before choosing a city: no player colour anywhere yet -> no mark (-1), never P1's colour.
        r.call(op='lobby_chat_send',invite=invites[3],message_id=mid(),text='도시 고르는 중')
        for i,inv in enumerate(invites):tokens[i]=r.call(op='lobby_join',city=CITIES[i],invite=inv)['token']
        for i in range(9):r.call(op='player_name',city=CITIES[i],token=tokens[i],name=f'P{i+1}')
        sent={}
        for i in range(9):
            sent[i]=f'안녕 {i}';r.call(op='chat_send',city=CITIES[i],token=tokens[i],message_id=mid(),text=sent[i])
        r.call(op='lobby_chat_send',invite=invites[2],message_id=mid(),text='도시 고른 뒤')
        rows=r.call(op='chat_read',city=CITIES[0],token=tokens[0],after=0)['messages']
        by_text={m['text']:m for m in rows}
        self.assertEqual(by_text['도시 고르는 중']['player_color'],-1)
        self.assertEqual(by_text['도시 고른 뒤']['player_color'],2)
        self.assertEqual([by_text[sent[i]]['player_color'] for i in range(9)],[0,1,2,3,4,5,6,7,0])   # 8 colours, 9th wraps
        self.assertEqual(by_text[sent[1]]['player_color'],WHITE)
        system=[m for m in rows if m['city']=='system']
        self.assertTrue(system and all(m['player_color']==-1 for m in system))           # system: no colour
        status={s['city']:s for s in r.call(op='lobby_status',city=CITIES[0],token=tokens[0])['slots']}
        self.assertEqual([status[c]['player_color'] for c in CITIES[:8]],list(range(8)))  # same source as roofs/flags
        self.assertEqual(status['capua']['player_name'],'P1')
        # Reassignment: the first guest's admission is dropped -> every later participant's colour shifts by one.
        with r.db() as db:
            db.execute('DELETE FROM lobby_invite WHERE token=(SELECT token FROM lobby_invite ORDER BY rowid LIMIT 1 OFFSET 1)');db.commit()
        status={s['city']:s for s in r.call(op='lobby_status',city=CITIES[0],token=tokens[0])['slots']}
        self.assertEqual(status['neapolis']['player_color'],1)                           # now white
        again={m['text']:m['player_color'] for m in r.call(op='chat_read',city=CITIES[0],token=tokens[0],after=0)['messages']}
        self.assertEqual(again[sent[2]],2)                                               # old message keeps its colour
        r.call(op='chat_send',city=CITIES[2],token=tokens[2],message_id=mid(),text='재배정 후')
        again={m['text']:m['player_color'] for m in r.call(op='chat_read',city=CITIES[0],token=tokens[0],after=0)['messages']}
        self.assertEqual((again[sent[2]],again['재배정 후']),(2,1))
        view=r.call(op='lobby_view',invite=invites[0])
        self.assertEqual({m['text']:m['player_color'] for m in view['lobby_messages']}[sent[2]],2)
    def test_bridge_status_writes_owner_files(self):
        """The real Bridge.publish_slots with a real lobby_status: route slots and the own line come from the room."""
        import game_bridge
        r=self.room;inv=[r.lobby.invite() for _ in range(3)]
        tok=[r.call(op='lobby_join',city=CITIES[i],invite=inv[i])['token'] for i in range(3)]
        for i in range(2):r.call(op='player_name',city=CITIES[i],token=tok[i],name=f'P{i}')
        state=r.call(op='lobby_status',city=CITIES[0],token=tok[0])
        with tempfile.TemporaryDirectory() as d:
            b=game_bridge.Bridge.__new__(game_bridge.Bridge)
            b.root=Path(d);b.published={};b.client=FakeClient();b.joined=True;b.config={'session':'s','invite':inv[0]}
            b.publish_slots(state)
            posts=(Path(d)/'post-partners.txt').read_text(encoding='utf8').splitlines()
            order=sorted(CITIES)
            self.assertEqual(posts[0],'AUGPOST1')
            self.assertIn(f"{order.index('tarentum')+1}\tTarentum\tP1",posts)
            self.assertIn(f"{order.index('neapolis')+1}\tNeapolis\t아이디 미확인",posts)    # joined, no name yet
            self.assertIn(f"{order.index('sparta')+1}\tSparta\t담당자 없음",posts)
            self.assertFalse(any(p.split('\t')[0]==str(order.index('capua')+1) for p in posts[1:]))
            self.assertEqual((Path(d)/'army-owners.txt').read_text(encoding='utf8'),'AUGARMY1\nown\tCapua\tP0\n')
    def test_old_records_without_colour(self):
        r=self.room
        with r.db() as db:
            db.execute("INSERT INTO chat(city,message_id,text) VALUES('capua',?,'옛 기록')",(mid(),));db.commit()   # pre-colour row
        inv=r.lobby.invite();token=r.call(op='lobby_join',city='capua',invite=inv)['token']
        old=[m for m in r.call(op='chat_read',city='capua',token=token,after=0)['messages'] if m['text']=='옛 기록'][0]
        self.assertEqual(old['player_color'],-1)

class FakeClient:
    city='capua';address=('127.0.0.1',1);session='s'
class BridgeChat(unittest.TestCase):
    def bridge(self,root):
        import game_bridge
        b=game_bridge.Bridge.__new__(game_bridge.Bridge)
        b.root=Path(root);b.published={};b.client=FakeClient();b.chat_session='a'*32;b.journal=b.root/'chat-events.txt'
        b.journal_ids=set();b.cursor=0;b.lines=[];b.chat_rows=[];b.chat_incoming=[];b.chat_phase='started';b.city_names=NAMES
        return b
    def test_journal_and_lobby_rows(self):
        from chat_presentation import journal_key,key_base
        with tempfile.TemporaryDirectory() as d:
            b=self.bridge(d)
            msgs=[dict(id=i+1,city=CITIES[i%9],sender=f'P{i}',text=f't{i}',player_color=c) for i,c in enumerate([0,1,2,3,4,5,6,7,-1])]
            msgs.append(dict(id=10,city='system',sender='시스템',text='알림',player_color=-1))
            msgs.append(dict(id=11,city='capua',sender='옛',text='old'))                              # no colour field
            b.accept_chat(msgs)
            keys=[l.split('\t')[0] for l in (Path(d)/'chat-events.txt').read_text(encoding='utf8').splitlines()]
            self.assertEqual(keys[:8],[f'mpchat:{"a"*32}:{i+1}:c{i}' for i in range(8)])
            self.assertEqual(keys[8:],[f'mpchat:{"a"*32}:9',f'mpchat:{"a"*32}:10',f'mpchat:{"a"*32}:11'])
            colours=(Path(d)/'lobby-chat-colors.txt').read_text(encoding='utf8').splitlines()
            self.assertEqual(colours[0],'AUGCHAT1')
            self.assertEqual([int(l.split('\t')[0]) for l in colours[1:]],[0,1,2,3,4,5,6,7,-1,-1,-1])
            self.assertTrue(all(l.split('\t')[1] for l in colours[1:]))
            # A restarted bridge reads the same messages again (cursor 0); an archive written before this change
            # (key without colour) is not archived a second time.
            legacy=Path(d)/'chat-events.txt';text=legacy.read_text(encoding='utf8').replace(':1:c0\t',':1\t')
            legacy.write_text(text,encoding='utf8')
            b2=self.bridge(d);b2.journal_ids={key_base(l.split('\t',1)[0]) for l in text.splitlines()}
            b2.accept_chat(msgs)
            self.assertEqual(len(legacy.read_text(encoding='utf8').splitlines()),11)
            self.assertEqual(key_base(journal_key('a'*32,dict(id=5,player_color=3))),f'mpchat:{"a"*32}:5')
            self.assertEqual(key_base(f'mpchat:{"a"*32}:5'),f'mpchat:{"a"*32}:5')

def slot(city,name,claimed=True,online=True,departed=False):
    return dict(city=city,player_name=name if claimed else None,name=name if claimed else city,claimed=claimed,online=online,departed=departed)

class Affiliation(unittest.TestCase):
    def setUp(self):
        self.slots=[slot('capua','Aurelia'),slot('tarentum','김철수'),slot('neapolis','Aurelia'),     # same name, two cities
                    slot('brundisium','Bob',online=False),slot('sparta','Gone',departed=True,online=False),
                    slot('athenae',None,claimed=False),slot('corinthus','x'*40)]
        self.names={c:NAMES[c] for c in CITIES[:7]};self.names['tarentum']='타렌툼'
    def table(self,text,magic):
        lines=text.splitlines();self.assertEqual(lines[0],magic)
        return {l.split('\t')[0]:tuple(l.split('\t')[1:]) for l in lines[1:]}
    def test_post_partners_by_route_slot(self):
        import affiliation
        t=self.table(affiliation.post_partners(self.slots,self.names,'capua'),'AUGPOST1')
        order=sorted(c for c in CITIES[:7])                      # route slot = position in the sorted city list
        expect={str(i):c for i,c in enumerate(order,1) if c!='capua'}
        self.assertEqual(set(t),set(expect))
        label={c:t[k] for k,c in expect.items()}
        self.assertEqual(label['tarentum'],('타렌툼','김철수'))
        self.assertEqual(label['neapolis'],('Neapolis','Aurelia'))   # same id as mine, told apart by the city
        self.assertEqual(label['brundisium'][1],'Bob (연결 끊김)')
        self.assertEqual(label['sparta'][1],'Gone (퇴장)')
        self.assertEqual(label['athenae'][1],'담당자 없음')            # never another player's name
        self.assertTrue(len(label['corinthus'][1])<=24 and label['corinthus'][1].endswith('…'))
        self.assertNotIn(str(order.index('capua')+1),t)                  # no post points at my own city
    def test_army_owners(self):
        import affiliation
        rows=[dict(token=11,origin='tarentum',destination='capua',incoming=True,phase='stationed',role=1),
              dict(token=12,origin='neapolis',destination='capua',incoming=True,phase='stationed',role=2),
              dict(token=13,origin='capua',destination='tarentum',incoming=False,phase='stationed',role=1),   # mine, away
              dict(token=14,origin='tarentum',destination='capua',incoming=True,phase='returned',role=1),    # gone home
              dict(token=15,origin='rome',destination='capua',incoming=True,phase='stationed',role=1),       # not a player
              dict(token=0,origin='tarentum',destination='capua',incoming=True,phase='stationed',role=1)]
        t=self.table(affiliation.army_owners(self.slots,self.names,'capua',rows),'AUGARMY1')
        self.assertEqual(t['own'],('Capua','Aurelia'))
        self.assertEqual(t['11'],('타렌툼','김철수'))                    # support shows its sender, not the host city
        self.assertEqual(t['12'],('Neapolis','Aurelia'))
        self.assertEqual(set(t),{'own','11','12'})
    def test_publish_refreshes_and_records_without_extra_request(self):
        import affiliation
        calls=[]
        class Client:
            city='capua'
            def call(self,op,**k):
                calls.append(op);return [dict(token=21,origin='tarentum',incoming=True,phase='stationed',role=1)] if op=='army_overview' else {}
        class B:
            joined=True;city_names=self.names
            def __init__(s):s.client=Client();s.files={}
            def write_changed(s,n,t):s.files[n]=t
        b=B();affiliation.publish(b,dict(slots=self.slots))
        rec=affiliation.Recorder(b.client);b.client=rec
        b.client.call('army_order_status');b.client.call('army_overview');b.client.extra=1
        b.client=rec.client
        self.assertEqual(calls,['army_order_status','army_overview']);self.assertEqual(b.client.extra,1)
        affiliation.publish(b,rows=rec.army_rows)
        self.assertIn('21\t타렌툼\t김철수',b.files['army-owners.txt'])
        # The partner leaves: the next status rewrites the line (no old name kept).
        changed=[s if s['city']!='tarentum' else slot('tarentum','김철수',departed=True,online=False) for s in self.slots]
        affiliation.publish(b,dict(slots=changed))
        self.assertIn('21\t타렌툼\t김철수 (퇴장)',b.files['army-owners.txt'])
        # The legion went home: gone from the table.
        affiliation.publish(b,rows=[])
        self.assertNotIn('21\t',b.files['army-owners.txt'])
        # A new player takes the city before the next game: the new name, never the previous one.
        affiliation.publish(b,dict(slots=[s if s['city']!='tarentum' else slot('tarentum','Newbie') for s in self.slots]))
        self.assertIn('타렌툼\tNewbie',b.files['post-partners.txt']);self.assertNotIn('김철수',b.files['post-partners.txt'])
    def test_city_or_session_change_clears_old_visitors(self):
        import affiliation
        from types import SimpleNamespace
        files={}
        b=SimpleNamespace(joined=True,client=SimpleNamespace(city='capua',session='one'),city_names=self.names,write_changed=lambda k,v:files.update({k:v}))
        affiliation.publish(b,dict(slots=self.slots),rows=[dict(token=31,origin='neapolis',destination='capua',incoming=True,phase='stationed')])
        self.assertIn('31\t',files['army-owners.txt'])
        b.client.city='tarentum'
        affiliation.publish(b,dict(slots=self.slots))
        self.assertNotIn('31\t',files['army-owners.txt'])
        affiliation.publish(b,rows=[dict(token=32,origin='neapolis',destination='tarentum',incoming=True,phase='stationed')])
        self.assertIn('32\t',files['army-owners.txt'])
        b.client.session='two'
        affiliation.publish(b,dict(slots=self.slots))
        self.assertNotIn('32\t',files['army-owners.txt'])
        b.joined=False
        affiliation.publish(b,dict(slots=self.slots))
        self.assertEqual(files['army-owners.txt'],'AUGARMY1\n')
        self.assertEqual(files['post-partners.txt'],'AUGPOST1\n')
    def test_wrong_destination_is_not_my_visiting_army(self):
        import affiliation
        rows=[dict(token=31,origin='neapolis',destination='sparta',incoming=True,phase='stationed')]
        self.assertNotIn('31\t',affiliation.army_owners(self.slots,self.names,'capua',rows))
    def test_nothing_private(self):
        import affiliation,inspect
        source=inspect.getsource(affiliation)
        for word in ('throne','paranoia','secret','attempt','gift'):
            self.assertNotIn(word,source.split('"""',2)[2].lower(),word)   # code after the module notes never reads them

GAME=Path(os.environ.get('AUGUSTUS_GAME_SRC',str(ROOT/'src')))
CC=os.environ.get('AUGUSTUS_CC') or shutil.which('gcc')   # Windows: the compiler build_from_source.py uses
@unittest.skipUnless(CC and (GAME/'multiplayer/chat.c').is_file() and (ROOT/'src/widget/city/multiplayer_affiliation.inc').is_file(),'C compiler and full game source needed')
class NativeParsers(unittest.TestCase):
    """Compiles handoff/affiliation_probe.c (the real chat.c uid parser and the real .inc file parser/text builder,
    with figure/building/map stubs) and checks the text the city tooltip shows."""
    def test_native(self):
        with tempfile.TemporaryDirectory() as d:
            exe=Path(d)/('probe.exe' if os.name=='nt' else 'probe')
            r=subprocess.run([CC,'-std=gnu99','-w','-I',str(ROOT/'src'),'-I',str(GAME),'-I',str(GAME/'multiplayer'),str(Path(__file__).parent/'affiliation_probe.c'),'-o',str(exe)],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr[-3000:])
            r=subprocess.run([str(exe),d],capture_output=True,text=True,encoding='utf8')
            self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertIn('ALL OK',r.stdout)

if __name__=='__main__':unittest.main()
