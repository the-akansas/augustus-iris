from windows_paths import filesystem_path
from pathlib import Path
import os,shutil,uuid,json
FILES=tuple(prefix+n for prefix in ('','config/') for n in ('augustus.ini','augustus-hotkeys.ini','c3.inf'))
# Personal files the game keeps in its config location (difficulty in c3.inf, options, hotkeys, chat display time).
PERSONAL=('augustus.ini','augustus-hotkeys.ini','c3.inf','multiplayer-chat.ini')
SAVES=('.sav','.svx')
def prepare_profile(install,game_data=None):
 root=filesystem_path(install);target=root/'user-profile'
 if not target.is_dir():_create(root,target)
 adopt(target,game_data)
 return target
def adopt(profile,game_data=None):
 """Personal files live in user-profile, chosen for the person (user 2026-11-13).
 Without this the game asked for a user folder on first start, and the usual answer (the game folder) put difficulty,
 options and hotkeys into private-game-data/<fingerprint>, which is rebuilt for a new version or another C3 folder:
 the question came back and settings were reset, and '이전 버전 설정 가져오기' could not find them.
 Only when user_dir.txt does not exist yet: a folder the person picked in 설정 > 사용자 설정 경로 (an empty file is the
 game folder picked on purpose) is left alone. Files found in the game folder are copied, never moved or replaced."""
 marker=profile/'user_dir.txt'
 if marker.exists():return False
 config=profile/'config';config.mkdir(exist_ok=True);(profile/'savegames').mkdir(exist_ok=True)
 sources=[p for p in (Path(game_data) if game_data else None,profile) if p is not None and p.is_dir()]
 for name in PERSONAL:
  if (config/name).exists():continue
  found=[s/name for s in sources if (s/name).is_file() and not (s/name).is_symlink()]
  if found:_copy(max(found,key=lambda p:p.stat().st_mtime_ns),config/name)
 if game_data and Path(game_data).is_dir():
  for p in Path(game_data).iterdir():
   if p.suffix.lower() in SAVES and p.is_file() and not p.is_symlink() and not (profile/'savegames'/p.name).exists():_copy(p,profile/'savegames'/p.name)
 ini=config/'augustus.ini'
 text=ini.read_text(encoding='utf-8',errors='replace') if ini.is_file() else ''
 if 'has_set_user_directories=' not in text:   # the game would ask again without it
  with ini.open('a',encoding='utf-8',newline='\n') as f:f.write(('' if not text or text.endswith('\n') else '\n')+'has_set_user_directories=1\n')
 # the same text the game writes for its recommended choice (this folder, as the launcher hands it over)
 temp=profile/('user_dir.txt.'+uuid.uuid4().hex+'.tmp');temp.write_bytes((profile.as_posix()+'/').encode('utf-8'))
 try:temp.replace(marker)
 finally:
  if temp.exists():temp.unlink()
 return True
def _copy(source,target):
 # contents and time only: a read-only original must not make the profile copy read-only (the game saves into it)
 shutil.copyfile(source,target);st=source.stat();os.utime(target,ns=(st.st_atime_ns,st.st_mtime_ns))
def _create(root,target):
 stage=root/('profile-preparing-'+uuid.uuid4().hex);stage.mkdir()
 candidates=[p for p in (root/'rooms').glob('network-play-*/user') if p.is_dir() and not p.is_symlink() and any((p/n).is_file() for n in FILES)]
 source=max(candidates,key=lambda p:max(((p/n).stat().st_mtime_ns for n in FILES if (p/n).is_file()),default=0)) if candidates else None
 if source:
  for n in FILES:
   p=source/n
   if p.is_file() and not p.is_symlink():(stage/n).parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,stage/n)
 (stage/'profile-migration.json').write_text(json.dumps({'migrated':source is not None,'source':str(source) if source else None}),encoding='utf8')
 try:stage.rename(target)
 except OSError:
  if not target.is_dir():raise
