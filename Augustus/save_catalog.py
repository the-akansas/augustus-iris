from windows_paths import sqlite_readonly_uri
"""Read-only save catalog. Selection is revalidated when restoring, never repaired in place."""
import sys,json,sqlite3
from pathlib import Path
from contextlib import closing
from datetime import datetime
sys.path.insert(0,str(Path(__file__).parent))
import transport_snapshot
import save_provenance
from scenario_pair import load_pair,compatible_binding
from status_display import date_label
from city_client import game_data

LIMIT=8   # games offered to continue (user 2026-11-15: "이어하기는 총 8개 제한")

def catalog(rooms,binding,limit=LIMIT):
 entries=[];warnings=[]
 paths=list(Path(rooms).glob('game-*/room.sqlite'))+list(Path(rooms).glob('network-play-*/host-*/room.sqlite'))
 for path in sorted(paths):
  folder=path.parent
  if not path.is_file():continue
  try:
   room_binding=binding;title='공동 게임';first_year=None
   project=folder/'scenario-project.json'
   if project.exists():
    room_binding=load_pair(game_data(),project)[1]
    whole=json.loads(project.read_text(encoding='utf-8-sig'));title=whole.get('title',title)
    import scenario_project;first_year=scenario_project.start_year(whole)   # the scenario's own first year (2026-11-17)
   modified=path.stat().st_mtime
   with closing(sqlite3.connect(sqlite_readonly_uri(path),uri=True)) as db:
    db.row_factory=sqlite3.Row;db.execute('BEGIN')
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='joint_save'").fetchone():continue
    if not compatible_binding(json.loads(db.execute('SELECT value FROM scenario_binding').fetchone()[0]),room_binding):
     warnings.append(folder.name+': 시나리오 버전 불일치');continue
    for saved in db.execute("SELECT id,ticks,speed FROM joint_save WHERE state='complete' ORDER BY id DESC LIMIT 1"):   # the newest save of each game (user 2026-11-15)
     parts=[r[0] for r in db.execute('SELECT city FROM joint_part WHERE id=?',(saved['id'],))]
     ticks=saved['ticks'];speed=saved['speed']
     valid=sorted(parts)==sorted(room_binding['cities']) and type(ticks)==int and 0<=ticks<2**53 and speed in range(0,101,10)
     transport=transport_snapshot.read(db,saved['id'],room_binding['cities'])
     provenance=save_provenance.read(db,saved['id'],room_binding['cities'])
     transfer=transport_snapshot.transfer_of(transport)   # saves since the contract/route envelopes nest it (2026-11-13)
     travel=bool(transfer)
     returning=travel and transfer.get('state')=='returning'
     collecting=travel and transfer.get('state')=='collecting'
     departing=travel and transfer.get('state')=='departing'
     entries.append(dict(title=title,database=str(path.resolve()),room=folder.name,id=saved['id'],ticks=ticks,speed=speed,date=date_label(ticks,first_year) if type(ticks)==int and ticks>=0 else '?',modified=datetime.fromtimestamp(modified).strftime('%Y-%m-%d %H:%M:%S'),sort_time=modified,available=valid,status=('남은 도시 저장: 다른 도시는 마지막 확인 시점' if provenance else '도시 출구로 이동 중 · 복원 시 해시 검증' if departing else '출발지 수집 중 · 복원 시 해시 검증' if collecting else '화물 반환 대기 · 복원 시 해시 검증' if returning else '운송 중 · 복원 시 해시 검증' if travel else '복원 시 해시 검증') if valid else '복원 불가: 도시/시각/속도 누락'))
  except (sqlite3.Error,ValueError,TypeError,OSError,KeyError,AttributeError) as e:warnings.append(folder.name+': 읽기 실패 ('+repr(e)+')')   # one bad room never stops the list
 entries.sort(key=lambda r:(r['sort_time'],r['id']),reverse=True)
 return dict(entries=entries[:limit],warnings=warnings)

def prune(rooms,binding,current=None):
 """The games past the newest LIMIT are deleted (user 2026-11-15: "자동으로 지워줘"): their room folder
 (rooms/game-*, rooms/network-play-*/host-*), never the session folders themselves (the player's profile and
 own records live there) and nothing under `current` (the running session). Only games the list can read are
 counted; a folder it cannot read is left alone."""
 import shutil
 rooms=Path(rooms).resolve();current=Path(current).resolve() if current else None;removed=[]
 for entry in catalog(rooms,binding,limit=None)['entries'][LIMIT:]:
  folder=Path(entry['database']).parent
  if not (folder.name.startswith('game-') or folder.name.startswith('host-')):continue
  if not folder.is_relative_to(rooms) or folder==rooms or (current and folder.is_relative_to(current)):continue
  shutil.rmtree(folder,ignore_errors=True);removed.append(folder.name)
 return removed
if __name__=='__main__':
 here=Path(__file__).parent
 print(json.dumps(catalog(here/'rooms',load_pair(game_data())[1]),ensure_ascii=False))
