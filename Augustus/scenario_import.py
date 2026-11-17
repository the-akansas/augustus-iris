from multiplayer_limits import MAX_ONLINE_PLAYERS
"""Validate then copy an authored scenario into the user workspace."""
import uuid,shutil,zipfile
from pathlib import Path
from creator_workspace import Workspace
from scenario_project import load

def import_scenario(root,source):
 source=Path(source);workspace=Workspace(root)
 if source.suffix.lower()=='.zip':
  workspace.root.mkdir(parents=True,exist_ok=True)
  try:target=Path(workspace.import_zip(source)['path'])
  except (zipfile.BadZipFile,RuntimeError,NotImplementedError) as error:raise ValueError('읽을 수 없는 공유 ZIP입니다. 제작기에서 내보낸 파일인지 확인하세요.') from error
 else:
  load(source)
  target=workspace.directory()/('scenario-'+uuid.uuid4().hex+'.json')
  shutil.copy2(source,target);workspace.remember(target)
 data=load(target)
 return dict(path=str(target),message=('가져왔습니다. 내 시나리오에서 선택하세요.' if len(data['slots'])<=MAX_ONLINE_PLAYERS else f'가져왔습니다. {len(data["slots"])}자리 중 최대 {MAX_ONLINE_PLAYERS}명이 골라서 플레이합니다. 내 시나리오에서 선택하세요.'))
