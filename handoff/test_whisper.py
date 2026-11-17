"""In-game whisper (user 2026-11-13: '게임중 전체채팅과 귓속말'). The real Lobby and Coordinator (same minimal room as
test_chat_affiliation), and the real bridge display."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_chat_affiliation import Room,CITIES,mid

class Whisper(unittest.TestCase):
    def setUp(self):
        self.r=Room(self);self.tok={}
        for i in range(3):
            inv=self.r.lobby.invite();self.r.call(op='lobby_arrive',invite=inv,name=f'P{i+1}')
            self.tok[i]=self.r.call(op='lobby_join',city=CITIES[i],invite=inv)['token']
            self.r.call(op='player_name',city=CITIES[i],token=self.tok[i],name=f'P{i+1}')
    def send(self,i,text,to=None):
        k=dict(op='chat_send',city=CITIES[i],token=self.tok[i],message_id=mid(),text=text)
        if to is not None:k['to']=to
        return self.r.call(**k)
    def read(self,i):   # player lines (join notices left out)
        return [m for m in self.r.call(op='chat_read',city=CITIES[i],token=self.tok[i],after=0)['messages'] if m['city']!='system']
    def test_only_the_two_see_a_whisper(self):
        self.send(0,'모두 안녕');self.send(0,'몰래 말해요',to=CITIES[1])
        for i in (0,1):
            texts={m['text']:m.get('whisper_to') for m in self.read(i)}
            self.assertEqual(texts,{'모두 안녕':None,'몰래 말해요':'P2'})
        self.assertEqual([m['text'] for m in self.read(2)],['모두 안녕'])
        lobby=self.r.call(op='lobby_status',city=CITIES[2],token=self.tok[2]).get('lobby_messages',[])
        self.assertNotIn('몰래 말해요',[m['text'] for m in lobby])
    def test_bad_receiver_is_refused(self):
        for to in (CITIES[0],'nowhere',CITIES[5],7):
            with self.assertRaises(ValueError):self.send(0,'x',to=to)
    def test_bridge_shows_who_it_went_to(self):
        import tempfile,shutil,game_bridge
        from types import SimpleNamespace
        self.send(0,'몰래',to=CITIES[1])
        root=Path(tempfile.mkdtemp());self.addCleanup(shutil.rmtree,root,True)
        written={}
        b=SimpleNamespace(cursor=0,chat_session='s'*32,city_names={},journal=root/'chat-events.txt',journal_ids=set(),client=SimpleNamespace(city=CITIES[1],chat_after=0),
                          chat_incoming=[],lines=[],chat_rows=[],config={'host':'h','port':1},write_changed=lambda n,t:written.__setitem__(n,t))
        b.publish_lobby_chat=lambda:None
        game_bridge.Bridge.accept_chat(b,self.read(1))
        self.assertIn('P1 · 귓속말 (P2에게)\t몰래',(root/'chat-events.txt').read_text(encoding='utf-8'))

if __name__=='__main__':unittest.main()
