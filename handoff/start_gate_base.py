"""Base class of handoff/test_routes.py: a started four-city room (Coordinator + Lobby, controlled clock).

Kept from test-24\\Augustus\\test_start_gate56.py (2026-11-16): that file is in no current work folder, so test_routes failed to import. The
original start-gate tests below run again with test_routes; no game, no window."""
from pathlib import Path
from contextlib import closing
import sys,unittest,tempfile,struct,json,zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Augustus'))
from coordinator import Coordinator,PROTOCOL,BUILD,sha
from lobby import Lobby
import network_diagnostics as diag
class StartGateTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=Path(__file__).parent);self.root=Path(self.tmp.name);self.now=0.
  self.cities=['p1','p2','p3','p4'];self.co=Coordinator(self.root/'room.sqlite','session',dict(sha256='layout',cities=self.cities))
  for c in self.cities:self.co.provision(c,b'save-'+c.encode(),struct.pack('<4sQiiiii',b'MPC1',0,0,0,0,0,0))
  self.room=Lobby(self.co,lambda:self.now);self.base=dict(protocol=PROTOCOL,build=BUILD,session='session',scenario='layout');self.tokens={};self.invites={}
  for c in self.cities:
   self.invites[c]=self.room.invite();self.tokens[c]=self.room.request(dict(self.base,city=c,op='lobby_join',invite=self.invites[c]))['token'];self.call(c,'lobby_ready',ready=True)
  self.initial=self.call('p1','room_start')['start']
 def tearDown(self):
  self.assertTrue(diag.flush(5));self.tmp.cleanup()
 def call(self,c,op,**kw):return self.room.request(dict(self.base,city=c,token=self.tokens[c],op=op,**kw))
 def ack(self,c,**kw):return self.call(c,'start_loaded',**(dict(attempt=self.initial['attempt'],layout='layout',save_hash=sha(b'save-'+c.encode()))|kw))
 def contact(self):
  for c in self.cities:self.call(c,'chat_read')
 def test_443ms_serial_requests_do_not_cancel(self):
  for i in range(24):self.now+=.443;self.call(self.cities[i%4],'chat_read')
  self.assertEqual(self.call('p1','lobby_status')['start']['phase'],'loading')
  for c in self.cities:self.ack(c)
  self.contact();self.now+=5;self.contact();self.call('p1','lobby_status');self.assertTrue(self.room.started)
 def test_no_start_until_all_four_hash_acks(self):
  for c in self.cities[:3]:self.ack(c)
  for i in range(8):self.now+=10;self.contact();self.assertEqual(self.call('p1','lobby_status')['start']['phase'],'loading')
  self.ack('p4');deadline=self.room.start_at
  self.ack('p4');self.assertEqual(self.room.start_at,deadline)
  self.now+=5;self.contact();self.assertEqual(self.call('p1','lobby_status')['start']['phase'],'started')
 def test_wrong_hash_and_old_attempt_rejected(self):
  for kw in ({'save_hash':'0'*64},{'attempt':'old-attempt'},{'layout':'wrong'}):
   with self.assertRaises(ValueError):self.ack('p2',**kw)
  self.assertFalse(self.room.start_gate['acks'])
 def test_disconnect_30s_cancels_with_peer(self):
  self.now=31;self.call('p1','chat_read');state=self.call('p1','lobby_status')['start'];self.assertEqual(state['phase'],'lobby');self.assertIn('연결',state['detail'])
 def test_download_deadline_despite_live_traffic(self):
  for i in range(12):self.now+=10;self.contact()
  state=self.call('p1','lobby_status')['start'];self.assertEqual(state['phase'],'lobby');self.assertIn('준비 시간',state['detail'])
 def test_ready_cancel_and_retry_rejects_late_ack(self):
  self.call('p2','lobby_ready',ready=False);self.assertIsNone(self.room.start_at)
  self.call('p2','lobby_ready',ready=True);new=self.call('p1','room_start')['start'];self.assertNotEqual(new['attempt'],self.initial['attempt'])
  with self.assertRaises(ValueError):self.ack('p2')
 def test_guest_leave_cancels_not_silent_roster_change(self):
  self.call('p4','lobby_leave',invite=self.invites['p4']);self.assertEqual(self.call('p1','lobby_status')['start']['phase'],'lobby')
 def test_checkpoint_changes_after_ack_cancel(self):
  for c in self.cities:self.ack(c)
  with closing(self.co.connect()) as db:db.execute("UPDATE city SET save=? WHERE id='p2'",(b'changed',));db.commit()
  self.now=5;self.contact();self.assertIn('저장',self.call('p1','lobby_status')['start']['detail']);self.assertFalse(self.room.started)
 def test_unauthorized_ack_does_not_refresh_contact(self):
  self.now=20
  with self.assertRaises(ValueError):self.room.request(dict(self.base,city='p2',token='wrong',op='start_loaded'))
  self.assertEqual(self.room.presence['p2'][0],0)
 def test_room_start_retries_keep_attempt(self):
  self.assertEqual(self.call('p1','room_start')['start']['attempt'],self.initial['attempt'])
 def test_started_same_invite_recovers_only_owned_city(self):
  for c in self.cities:self.ack(c)
  self.now=5;self.contact();self.call('p1','lobby_status');self.assertTrue(self.room.started)
  result=self.room.request(dict(self.base,op='lobby_join',city='p2',invite=self.invites['p2']))
  self.assertEqual(result['token'],self.tokens['p2'])
  with self.assertRaises(ValueError):self.room.request(dict(self.base,op='lobby_join',city='p3',invite=self.invites['p2']))
 def test_report_excludes_sensitive_files_and_rotates(self):
  secret='SECRET_AUTH_TOKEN_PRIVATE_CHAT_26.1.2.3'
  (self.root/'chat-events.txt').write_text(secret);(self.root/'config.json').write_text(secret);(self.root/'city.sav').write_text(secret)
  limit=diag._LIMIT;diag._LIMIT=300
  try:
   for i in range(20):diag.record(self.root,'rpc',session=diag.ident('session'),op='chat_read',outcome='ok',ms=i)
   diag.record(self.root,'rpc',outcome='failed',reason='TimeoutError')
   self.assertTrue(diag.flush(5))
   self.assertTrue((self.root/'network-events.failure.jsonl').exists())
   path=diag.export(self.root,self.root/'reports',self.root)
   with zipfile.ZipFile(path) as z:
    contents=b''.join(z.read(n) for n in z.namelist());self.assertNotIn(secret.encode(),contents);self.assertNotIn(str(self.root).encode(),contents)
  finally:diag._LIMIT=limit
 def test_report_command_creates_zip_without_gui_automation(self):
  from types import SimpleNamespace
  from unittest.mock import patch
  import network_play
  s=network_play.Session.__new__(network_play.Session);s.root=self.root;s.mail=self.root/'bridge';s.mail.mkdir()
  s.visits=SimpleNamespace(poll=lambda bridge:None);s.finish_search=lambda:None
  s.helper=s.importer=s.creator=None
  s.bridge=SimpleNamespace(notice_text='',notice_until=0,step=lambda:None,departed=False)
  (s.mail/'command.txt').write_text('network-report\n')
  with patch.object(network_play,'HERE',self.root),patch.object(network_play.os,'startfile',create=True) as opened:
   s.step()
   self.assertTrue(s.report_job.done.wait(10))
   s.step()
  self.assertFalse((s.mail/'command.txt').exists())
  filename=(s.mail/'diagnostic-result.txt').read_text(encoding='utf8')
  with zipfile.ZipFile(self.root/'reports'/filename) as z:self.assertIsNone(z.testzip())
  self.assertIn('문제 보고 파일',s.bridge.notice_text)
  self.assertLessEqual(opened.call_count,1)
if __name__=='__main__':unittest.main(verbosity=2)

