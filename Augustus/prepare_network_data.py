from windows_paths import filesystem_path
"""Private local C3 copy plus Korean resources. Never modifies the original install."""
import hashlib,json,os,shutil,threading,uuid,time
from pathlib import Path
RETIRE_AFTER=86400   # a copy left behind is removed only after a day (user 2026-11-16: "용량이 미쳤는데")
def retire(folder,root):
 """Renamed first, then deleted: a copy a running game still has a file open in cannot be renamed and stays whole."""
 gone=root/('removing-'+uuid.uuid4().hex)
 try:os.rename(folder,gone)
 except OSError:return
 shutil.rmtree(gone,ignore_errors=True)
def prune(root,keep,source):
 """Old private copies of this game folder: the ones made for the same original folder before its files (or the
 Korean resources) changed, an unfinished copy, a half-deleted one. A copy of another original folder is kept (another
 launcher may use it). Never fatal: the game starts whatever happens here."""
 try:
  now=time.time()
  for d in root.iterdir():
   try:
    if d==keep or not d.is_dir() or d.is_symlink():continue
    if d.name.startswith('removing-'):shutil.rmtree(d,ignore_errors=True);continue
    if now-d.stat().st_mtime<RETIRE_AFTER:continue
    if d.name.startswith('preparing-'):retire(d,root);continue
    m=json.loads((d/'prepared.json').read_text(encoding='utf-8'))
    if m.get('private_game_data') and m.get('source')==str(source):retire(d,root)
   except (OSError,ValueError,AttributeError):continue
 except OSError:pass
def tidy_later(root,keep,source):
 threading.Thread(target=prune,args=(root,keep,source),daemon=True,name='private-data-tidy').start()
EXT={'.pak','.555','.sg2','.emp','.map','.mapx','.smk','.wav','.mp3','.ogg','.eng','.txt'}
SKIP={'assets','saves','savegames','configs','screenshots'}
def prepare(source,root,patch):
 source,root,patch=filesystem_path(source),filesystem_path(root),filesystem_path(patch)
 for name in ['c3.sg2','mission1.pak','c3.emp','c3_model.txt']:
  if not (source/name).is_file():raise ValueError('missing original game file: '+name)
 if not patch.is_dir():raise ValueError('Korean resource directory missing')
 files=[]
 for p in source.rglob('*'):
  if not p.is_file() or p.is_symlink():continue
  rel=p.relative_to(source)
  if any(x.lower() in SKIP for x in rel.parts[:-1]) or p.name.lower().startswith('augustus') or p.suffix.lower() not in EXT:continue
  # Do not copy a recursively nested work/cache folder selected by mistake.
  if root==p or root in p.parents:continue
  files.append((p,rel))
 patches=sorted(p for p in patch.iterdir() if p.is_file())
 fingerprint=hashlib.sha256(json.dumps(['own-text-1',str(source),[(str(rel),p.stat().st_size,p.stat().st_mtime_ns) for p,rel in sorted(files)],[(p.name,p.stat().st_size,p.stat().st_mtime_ns) for p in patches]],sort_keys=True).encode()).hexdigest()
 root.mkdir(parents=True,exist_ok=True);target=root/fingerprint[:24]
 def complete(folder):
  try:
   m=json.loads((folder/'prepared.json').read_text(encoding='utf-8'))
   return m.get('fingerprint')==fingerprint and all((folder/n).is_file() for n in ['c3.sg2','mission1.pak','c3.emp','c3_model.txt'])
  except (OSError,ValueError,AttributeError):return False
 if complete(target):tidy_later(root,target,source);return target
 # Never overwrite an existing incomplete/private folder. Reuse a completed
 # alternate from a previous repair, otherwise publish under a fresh name.
 for existing in sorted(root.glob(fingerprint[:24]+'-ready-*')):
  if existing.is_dir() and not existing.is_symlink() and complete(existing):tidy_later(root,existing,source);return existing
 if target.exists():target=root/(fingerprint[:24]+'-ready-'+uuid.uuid4().hex)

 stage=root/('preparing-'+uuid.uuid4().hex);stage.mkdir()
 for p,rel in files:
  out=stage/rel;out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,out)
 for p in patches:shutil.copy2(p,stage/p.name)
 # Multilingual (wip-25): the player's own Caesar III texts, converted to our letter encoding, next to the Korean
 # ones. The game reads them only when a non-Korean screen language is chosen (src/core/lang.c). Never fatal.
 try:
  from c3_text_convert import convert_folder
  own=convert_folder(source,stage)
 except Exception:own=None
 (stage/'prepared.json').write_text(json.dumps(dict(source=str(source),fingerprint=fingerprint,private_game_data=True,own_text=own)),encoding='utf-8')
 for attempt in range(6):
  try:
   os.rename(stage,target)
   tidy_later(root,target,source)
   return target
  except OSError as error:
   if error.errno not in (13,17,39) and getattr(error,'winerror',None) not in (5,32,183):raise
   if target.exists():
    # A concurrent launch may have published a complete copy. Keep our own
    # completed staging folder untouched; no recursive deletion of game data.
    if complete(target):return target
    target=root/(fingerprint[:24]+'-ready-'+uuid.uuid4().hex)
   if attempt==5:
    raise RuntimeError('개인용 게임 데이터 폴더를 준비했지만 확정하지 못했습니다. 다른 게임 실행을 종료한 뒤 다시 실행해 주세요. 기존 데이터는 보존했습니다.') from error
   time.sleep(.2)

