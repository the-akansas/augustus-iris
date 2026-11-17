"""Room search reasons and the waiting-room hover card (user 2026-11-13).
  * a room that cannot be entered says why (full, started, preparing, closed, other version), one line;
  * a city map the bridge already received is shown again at once, without a request;
  * a failed preview build is tried again instead of being kept."""
import sys,threading,time,unittest
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Augustus'))
import room_discovery,city_preview

def found(**k):
    r=dict(compatible=True,joinable=True,phase='lobby',players=2,maximum=6);r.update(k);return r

class Refusal(unittest.TestCase):
    def test_reasons(self):
        self.assertIn('가득 찼습니다(6/6명)',room_discovery.refusal(found(players=6,joinable=False)))
        self.assertIn('이미 게임을 시작한 방',room_discovery.refusal(found(phase='started',joinable=False)))
        self.assertIn('시작 준비 중',room_discovery.refusal(found(phase='countdown',joinable=False)))
        self.assertIn('종료된 방',room_discovery.refusal(found(phase='closed',joinable=False)))
        self.assertIn('게임 버전이 다릅니다',room_discovery.refusal(found(compatible=False)))
        for r in (found(players=6,joinable=False),found(compatible=False)):self.assertNotIn('\n',room_discovery.refusal(r))

class Bridge:
    def __init__(self,answers):
        self.files={};self.calls=[];self.answers=answers
        self.client=SimpleNamespace(session='s1',call=self.call);self.config={'invite':'i'}
    def call(self,op,**k):self.calls.append(k['preview_city']);return self.answers.pop(0)
    def write_changed(self,name,text):self.files[name]=text

class HoverCache(unittest.TestCase):
    def test_second_hover_needs_no_request(self):
        b=Bridge([dict(city='capua',status='ready',width=2,height=1,grid='WL',caption='시작할 때의 도시 모습')])
        b.preview_city='capua';b.preview_next=0
        city_preview.poll_bridge(b)
        self.assertEqual(b.files['city-preview.txt'],'capua\n2 1\nWL\n시작할 때의 도시 모습')
        self.assertEqual(city_preview.cached(b,'capua'),b.files['city-preview.txt'])
        self.assertIsNone(city_preview.cached(b,'tarentum'))
        b.client.session='s2';self.assertIsNone(city_preview.cached(b,'capua'))   # another room: nothing reused

class HoverHasItsOwnChannel(unittest.TestCase):
    def test_hover_request_file(self):
        import tempfile,shutil
        root=Path(tempfile.mkdtemp());self.addCleanup(shutil.rmtree,root,True)
        b=Bridge([]);b.root=root;b.city_ids={'capua','tarentum'}
        b.preview_cache={('s1','capua'):'capua\n1 1\nW\n'}
        (root/'preview-request.txt').write_text('capua\n1',encoding='utf-8')
        city_preview.hover_request(b)
        self.assertEqual(b.files['city-preview.txt'],'capua\n1 1\nW\n')   # from its own copy, no room request
        self.assertEqual(b.calls,[])
        city_preview.hover_request(b);self.assertEqual(b.calls,[])            # the same request is handled once
        (root/'preview-request.txt').write_text('tarentum\n2',encoding='utf-8')
        city_preview.hover_request(b)
        self.assertEqual(b.preview_city,'tarentum');self.assertEqual(b.files['city-preview-busy.txt'],'1')
        (root/'preview-request.txt').write_text('nowhere\n3',encoding='utf-8')
        city_preview.hover_request(b)                                         # an unknown city is ignored, never raises
        self.assertEqual(b.preview_city,'tarentum')
        self.assertFalse((root/'command.txt').exists())                       # the command slot stays free for the click

class FailedBuildIsRetried(unittest.TestCase):
    def test_error_is_not_kept(self):
        import sqlite3
        db=sqlite3.connect(':memory:');db.execute('CREATE TABLE city(id TEXT,save BLOB,receipt BLOB)');db.execute("INSERT INTO city VALUES('capua',x'00',x'00')")
        room=SimpleNamespace(coordinator=SimpleNamespace(scenario={'cities':['capua']},path='/nonexistent/room.sqlite'),started=False,start_at=None,roster_job=None)
        key=__import__('hashlib').sha256(b'\x00\x00').hexdigest()
        room.city_previews={'capua':dict(key=key,result=dict(status='error'))}
        started=[]
        real=threading.Thread
        class Recorder:
            def __init__(self,target,daemon):started.append(target)
            def start(self):pass
        threading.Thread=Recorder
        try:r=city_preview.request(room,db,'capua')
        finally:threading.Thread=real
        self.assertEqual(r['status'],'pending');self.assertEqual(len(started),1)   # a new build, not the old failure

if __name__=='__main__':unittest.main()
