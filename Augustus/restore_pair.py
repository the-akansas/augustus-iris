from windows_paths import sqlite_readonly_uri
"""Read-only validation of completed pairs; restoration always creates a new room."""
import json,sqlite3
import transport_snapshot
import save_provenance
import objectives
import expedition_snapshot
import throne_state
import room_options
import observe_permissions
from contextlib import closing
from pathlib import Path
from coordinator import sha,MAX_SAVE

def read_pair(database,binding,save_id=None):
 if save_id is not None and (type(save_id)!=int or save_id<=0):raise ValueError("잘못된 공동 저장 번호입니다.")
 from windows_paths import legacy_process_path
 database=Path(legacy_process_path(Path(database).resolve()))
 with closing(sqlite3.connect(sqlite_readonly_uri(database),uri=True)) as db:
  db.row_factory=sqlite3.Row;db.execute('BEGIN')
  actual=json.loads(db.execute('SELECT value FROM scenario_binding').fetchone()[0])
  from scenario_pair import compatible_binding
  if not compatible_binding(actual,binding):raise ValueError('저장본과 현재 시나리오 버전이 다릅니다.')
  if save_id is None:
   saved=db.execute("SELECT id,ticks,speed FROM joint_save WHERE state='complete' ORDER BY id DESC LIMIT 1").fetchone()
  else:
   saved=db.execute("SELECT id,ticks,speed FROM joint_save WHERE state='complete' AND id=?",(save_id,)).fetchone()
  if not saved:raise ValueError('완료된 공동 저장이 없습니다.')
  if type(saved['ticks'])!=int or not 0<=saved['ticks']<2**53 or saved['speed'] not in (0,10,20,30,40,50,60,70,80,90,100):raise ValueError('저장 시각/속도 정보가 잘못되었습니다.')
  rows=db.execute('SELECT city,save,hash FROM joint_part WHERE id=?',(saved['id'],)).fetchall()
  if sorted(r['city'] for r in rows)!=sorted(binding['cities']):raise ValueError('두 도시의 저장본이 모두 필요합니다.')
  parts={}
  for r in rows:
   if not r['save'] or len(r['save'])>MAX_SAVE or sha(r['save'])!=r['hash']:raise ValueError('저장본 해시 검증 실패: '+r['city'])
   # Live trading is not enabled yet. Reject non-pristine receipts instead of
   # silently restoring a future trade state from an unrelated initial receipt.
   row=db.execute('SELECT receipt FROM city WHERE id=?',(r['city'],)).fetchone()
   from coordinator import receipt
   rec=receipt(row[0])
   if any(rec.values()):raise ValueError('거래 이력이 있는 저장 복원은 아직 지원하지 않습니다.')
   parts[r['city']]=(bytes(r['save']),bytes(row[0]))
  transport=transport_snapshot.read(db,saved['id'],actual['cities'])
  import imperial_progress
  return dict(progress=imperial_progress.read(db,saved['id'],actual),throne=throne_state.read(db,saved['id'],actual,saved['ticks']),observe_permissions=observe_permissions.read(db,saved['id'],actual['cities']),room_options=room_options.read(db,saved['id']),expedition=expedition_snapshot.read(db,saved['id'],actual['cities']),objectives=objectives.read(db,saved['id'],actual),provenance=save_provenance.read(db,saved['id'],actual['cities']),transport=transport,binding=actual,source=str(database),id=saved['id'],ticks=saved['ticks'],speed=saved['speed'],parts=parts)

def latest_saved_database(rooms):
 candidates=[]
 for root in Path(rooms).glob('game-*'):
  path=root/'room.sqlite'
  if not path.is_file():continue
  with closing(sqlite3.connect(sqlite_readonly_uri(path),uri=True)) as db:
   if not db.execute("SELECT 1 FROM sqlite_master WHERE name='joint_save'").fetchone():continue
   if db.execute("SELECT 1 FROM joint_save WHERE state='complete' LIMIT 1").fetchone():candidates.append(path)
 if not candidates:raise ValueError('완료된 공동 저장이 없습니다. 새 방에서 공동 저장을 먼저 해주세요.')
 # Do not silently fall back to an older save when the latest one is corrupt.
 return max(candidates,key=lambda p:p.stat().st_mtime_ns)
