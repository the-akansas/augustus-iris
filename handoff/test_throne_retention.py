"""Windows filesystem retention and real custody/restore regressions; no GUI."""
import sys,tempfile,json,sqlite3,os,unittest
from contextlib import closing
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if not (ROOT/'Augustus').is_dir() and __import__('os').environ.get('AUGUSTUS_TEST_COPY'):ROOT=Path(__import__('os').environ['AUGUSTUS_TEST_COPY'])   # tests run from outside a test copy
sys.path[:0]=[str(ROOT/'Augustus'),str(ROOT/'handoff')]
import throne_client as tc,throne_state as ts,throne_events as te
from test_throne_events import B,CITIES,room,replica,restore
from test_throne_custody import save,store_and_confirm

class Retention(unittest.TestCase):
 def test_live_handover_reference_survives_without_a_local_backup(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp);db=room();files={};save(db,1,800)
   for c in CITIES:store_and_confirm(db,c,1,files)
   old=te.own_opening(db,B,'player1',1);tc.keep_opening(path,'player1',old)
   for sid in range(2,44):
    save(db,sid,sid*800)
    own=te.own(db,B,'player1')
    self.assertIn(old['commit'],own['protected_commits'])
    tc.protect_openings(path,'session','player1',own['protected_commits'])
    tc.keep_opening(path,'player1',te.own_opening(db,B,'player1',sid))
   self.assertIsNotNone(tc.find_opening(path,old['commit']))
   self.assertEqual(len(list(path.glob('*.json'))),41)
 def test_client_real_storage_confirmation_and_new_host_restore(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=room();save(db,1,800);active=[db];calls=[]
   class Client:
    city='player1'
    def call(self,op,**kw):
     calls.append(op);d=active[0]
     if op=='throne_mine':return te.own(d,B,self.city)
     if op=='throne_opening':return dict(opening=te.own_opening(d,B,self.city,kw['id']))
     if op=='throne_opening_stored':return te.confirm_stored(d,B,self.city,kw['id'],kw['commit'])
     if op=='throne_hand_in':return te.hand_in(d,B,self.city,kw['secret'],kw['nonce'])
     raise AssertionError(op)
   bridge=SimpleNamespace(root=Path(tmp)/'bridge',config={'session':'one'},client=Client(),joined=True,write_changed=lambda *args:None)
   tc.sync(bridge,{'throne':te.public_status(db,B)})
   self.assertIn('throne_opening_stored',calls)
   active[0]=restore(replica(db,1,800),1,800)
   bridge.config={'session':'two'}
   tc.sync(bridge,{'throne':te.public_status(active[0],B)})
   self.assertFalse(te.own(active[0],B,'player1')['restoring'])
 def test_recovery_download_selects_eligible_older_checkpoint(self):
  from replica_worker import recovery_save,Replicas
  self.assertEqual(recovery_save({'throne':{'handover_save':1,'sealed_save':2}},{'complete':{'id':2}}),1)
  self.assertIsNone(recovery_save({'throne':{'handover_save':None}},{'complete':{'id':2}}))
  self.assertEqual(recovery_save({}, {'complete':{'id':2}}),2)
  with tempfile.TemporaryDirectory() as tmp:
   c=SimpleNamespace(session='s',city='player1',token='t',address=('127.0.0.1',1),scenario='x')
   bridge=SimpleNamespace(root=Path(tmp),client=c,departed=False,replicated_id=2)
   worker=Replicas();downloaded=[]
   with patch('replica_worker.download',side_effect=lambda b,sid,check:downloaded.append(sid)):
    worker.poll(bridge,1);self.assertIsNotNone(worker.job)
    worker.job.thread.join(3);self.assertFalse(worker.job.thread.is_alive())
    worker.poll(bridge,1)
   self.assertEqual(downloaded,[1]);self.assertEqual(bridge.replicated_id,1);worker.close()
 def test_older_save_requires_explicit_restore_choice(self):
  from game_bridge import Bridge
  output={}
  bridge=SimpleNamespace(close=lambda:None,was_started=True,succession_armed=True,succession_id=1,last_throne_recovery={'sealed_save':2},write_changed=lambda k,v:output.update({k:v}))
  Bridge.connection_exit(bridge,'disconnected','연결 종료')
  self.assertFalse(bridge.migration_requested)
  self.assertEqual(output['room-exit.txt'],'disconnected')
  self.assertIn('이전 저장 #1',output['room-exit-detail.txt'])
  self.assertIn('자동으로 되돌리지 않았습니다',output['room-exit-detail.txt'])
 def test_commit_path_traversal_is_rejected(self):
  self.assertIsNone(tc.find_opening(Path('.'),'../other'))
 def test_same_tick_carried_seal_needs_no_new_confirmation(self):
  db=room();files={};save(db,1,800)
  for c in CITIES:store_and_confirm(db,c,1,files)
  save(db,2,800,present={'player1','player2'})
  for c in CITIES[:2]:store_and_confirm(db,c,2,files)
  self.assertTrue(ts.custody(db,B,2)['ready'])
  self.assertEqual(ts.handover_save(db,B),2)
 def test_keep_old_backup_and_restore_after_more_than_forty_saves(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);path=root/'throne-own';path.mkdir();db=room();save(db,1,800)
   old=te.own_opening(db,B,'player1',1);self.assertTrue(tc.keep_opening(path,'player1',old))
   out=root/'host-backup-test-1';out.mkdir();rep=replica(db,1,800);rep.commit()
   with closing(sqlite3.connect(out/'room.sqlite')) as disk:rep.backup(disk)
   for sid in range(2,44):
    save(db,sid,800*sid);self.assertTrue(tc.keep_opening(path,'player1',te.own_opening(db,B,'player1',sid)))
   found=tc.find_opening(path,old['commit']);self.assertIsNotNone(found)
   restored=restore(rep,1,800);te.hand_in(restored,B,'player1',found['secret'],found['nonce'])
   self.assertFalse(te.own(restored,B,'player1')['restoring'])
   self.assertEqual(len(list(path.glob('*.json'))),41)
 def test_unreferenced_records_keep_latest_forty(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp);db=room()
   for sid in range(1,44):
    save(db,sid,800*sid);opening=te.own_opening(db,B,'player1',sid)
    self.assertTrue(tc.keep_opening(path,'player1',opening))
    os.utime(path/(opening['commit']+'.json'),(sid,sid))
   self.assertEqual(len(list(path.glob('*.json'))),40)
   self.assertIsNotNone(tc.find_opening(path,opening['commit']))
 def test_unreadable_backup_does_not_delete_recovery_material(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);path=root/'throne-own';path.mkdir();out=root/'host-backup-broken-1';out.mkdir();(out/'room.sqlite').write_bytes(b'broken')
   db=room()
   for sid in range(1,43):
    save(db,sid,sid*800);self.assertTrue(tc.keep_opening(path,'player1',te.own_opening(db,B,'player1',sid)))
   self.assertEqual(len(list(path.glob('*.json'))),42)

if __name__=='__main__':unittest.main(verbosity=2)
