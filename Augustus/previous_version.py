"""Bring personal settings over from an earlier version the person picks (user 2026-11-13).

A new version is a new zip unpacked into a new folder, so settings and hotkeys used to start from scratch. The person
runs 이전-버전-설정-가져오기.cmd (package root), picks the earlier package folder, confirms, and this copies:
  user-profile/              game settings and hotkeys (augustus.ini, augustus-hotkeys.ini, c3.inf)
  network-settings.json      this PC's Caesar 3 folder
  network-preferences.json   recent host addresses and player names
  multiplayer-settings.json  multiplayer save options
  creator-projects/, scenario-drafts/, creator-workspace.json   the person's own scenarios and the editor's work list
Joint saves (rooms/) are not taken (user decision). The earlier folder is only read. Settings already here are replaced,
the replaced ones kept in previous-version-backup-<time>/; own scenarios are only added to, never replaced.
previous-version.json records what happened (the release tool leaves it out); the next game start says so once.

  python previous_version.py            folder dialog (or typed path when no dialog can be shown), then confirm
  python previous_version.py --from X   no dialog, no question (tests and scripts)"""
import json,os,shutil,subprocess,sys,time,uuid
from pathlib import Path

MARK='previous-version.json'
FILES=['network-settings.json','network-preferences.json','multiplayer-settings.json']
DIRS=['user-profile','creator-projects','scenario-drafts']
SETTINGS=['user-profile']+FILES          # replaced (with a backup); scenarios are merged
WORKSPACE='creator-workspace.json'
HERE=Path(__file__).resolve().parent
NAMES={'user-profile':'게임 설정·단축키','network-settings.json':'시저 3 폴더 위치','network-preferences.json':'최근 IP·아이디',
       'multiplayer-settings.json':'멀티 저장 설정','creator-projects':'내 시나리오','scenario-drafts':'시나리오 초안',WORKSPACE:'에디터 작업 목록'}


def _plain(path):
    text=os.fspath(path)
    if text.startswith('\\\\?\\UNC\\'):return '\\\\'+text[8:]
    return text[4:] if text.startswith('\\\\?\\') else text


def _release(app):
    try:
        data=json.loads((Path(app)/'release.json').read_text(encoding='utf-8-sig'))
        return data if isinstance(data,dict) else {}
    except (OSError,ValueError):
        return {}


def resolve(here,source):
    """The earlier version's Augustus folder from what the person picked (the package folder or its Augustus folder)."""
    source=Path(source).expanduser().resolve();here=Path(here).resolve()
    if (source/'Augustus'/'release.json').is_file():source=source/'Augustus'
    if not (source/'release.json').is_file():raise ValueError('Augustus 배포판 폴더가 아닙니다(Augustus\\release.json이 없습니다).')
    if source==here:raise ValueError('지금 쓰는 버전과 같은 폴더입니다. 예전 버전 폴더를 골라 주세요.')
    return source


def available(source):
    """What the earlier folder has to bring over (names in NAMES order)."""
    have=[n for n in NAMES if (source/n).exists() and not (source/n).is_symlink()]
    import persistent_profile   # settings kept in the game folder copy (up to 261113-rc1) count as game settings too
    if 'user-profile' not in have and any((p/n).is_file() for p in (source/'private-game-data').glob('*') for n in persistent_profile.PERSONAL):have.insert(0,'user-profile')
    return have


def _copy_dir(src,dst):
    stage=dst.with_name(dst.name+'.importing-'+uuid.uuid4().hex[:8])
    shutil.copytree(src,stage,symlinks=False,ignore=shutil.ignore_patterns('__pycache__'))
    stage.rename(dst)


def _merge_dir(src,dst):
    added=0
    for p in src.rglob('*'):
        if '__pycache__' in p.parts or p.is_symlink() or not p.is_file():continue
        target=dst/p.relative_to(src)
        if target.exists():continue
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target);added+=1
    return added


def _workspace(src,here):
    """The editor's work list points into the earlier folder: point it at the copies here."""
    old=_plain(src);new=_plain(here)
    def move(value):
        if isinstance(value,str):
            if os.path.normcase(value).startswith(os.path.normcase(old+os.sep)) or os.path.normcase(value)==os.path.normcase(old):return new+value[len(old):]
            return value
        if isinstance(value,list):return [move(v) for v in value]
        if isinstance(value,dict):return {k:move(v) for k,v in value.items()}
        return value
    data=json.loads((src/WORKSPACE).read_text(encoding='utf-8-sig'))
    (here/WORKSPACE).write_text(json.dumps(move(data),ensure_ascii=False,indent=2),encoding='utf-8')


def _inside(path_text,folder):
    p=os.path.normcase(_plain(path_text.strip().replace('/',os.sep))).rstrip(os.sep)
    f=os.path.normcase(_plain(folder)).rstrip(os.sep)
    return p==f or p.startswith(f+os.sep)


def _point_profile_here(src,here):
    """user-profile/user_dir.txt names the earlier folder's profile: drop it, the next start points it here."""
    marker=here/'user-profile'/'user_dir.txt'
    try:text=marker.read_bytes().decode('utf-8').strip()
    except (OSError,UnicodeError):return
    if text and _inside(text,src):marker.unlink()


def _personal_from_game_folder(src,here):
    """Versions up to 261113-rc1 usually kept difficulty, options and hotkeys in private-game-data/<copy>/ (the game
    folder answer to the first-start question). Bring the newest copy's personal files over when the profile has none."""
    import persistent_profile
    config=here/'user-profile'/'config'
    folders=[p for p in (src/'private-game-data').glob('*') if p.is_dir() and not p.is_symlink() and any((p/n).is_file() for n in persistent_profile.PERSONAL)]
    if not folders or (config/'augustus.ini').exists():return []
    newest=max(folders,key=lambda p:max((p/n).stat().st_mtime_ns for n in persistent_profile.PERSONAL if (p/n).is_file()))
    config.mkdir(parents=True,exist_ok=True);saves=here/'user-profile'/'savegames';taken=[]
    for n in persistent_profile.PERSONAL:
        if (newest/n).is_file() and not (newest/n).is_symlink() and not (config/n).exists():persistent_profile._copy(newest/n,config/n);taken.append(n)
    for p in newest.iterdir():
        if p.suffix.lower() in persistent_profile.SAVES and p.is_file() and not p.is_symlink() and not (saves/p.name).exists():
            saves.mkdir(exist_ok=True);persistent_profile._copy(p,saves/p.name)
    return ['user-profile'] if taken else []


def run(here,source):
    here=Path(here).resolve();src=resolve(here,source)
    copied=[];backup=None
    present=[n for n in SETTINGS if (here/n).exists() and (src/n).exists()]
    if present:
        backup=here/('previous-version-backup-'+time.strftime('%Y%m%d-%H%M%S'));backup.mkdir()
        for n in present:shutil.move(str(here/n),str(backup/n))
    for n in FILES:
        if (src/n).is_file() and not (src/n).is_symlink() and not (here/n).exists():shutil.copy2(src/n,here/n);copied.append(n)
    for d in DIRS:
        if not (src/d).is_dir() or (src/d).is_symlink():continue
        if not (here/d).exists():_copy_dir(src/d,here/d);copied.append(d)
        elif d!='user-profile' and _merge_dir(src/d,here/d):copied.append(d)
    copied+=[n for n in _personal_from_game_folder(src,here) if n not in copied]
    _point_profile_here(src,here)
    if (src/WORKSPACE).is_file() and not (here/WORKSPACE).exists():
        try:_workspace(src,here);copied.append(WORKSPACE)
        except (OSError,ValueError):pass
    record=dict(time=time.strftime('%Y-%m-%d %H:%M:%S'),source=_plain(src),version=str(_release(src).get('version',''))[:60],
                copied=copied,announced=not copied,backup=backup.name if backup else None)
    (here/MARK).write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    return record


def announcement(here=HERE):
    """One line for the next first screen after an import, shown once."""
    try:
        record=json.loads((Path(here)/MARK).read_text(encoding='utf-8'))
        if record.get('announced') or not record.get('copied'):return None
        record['announced']=True;(Path(here)/MARK).write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
        return f"이전 버전({record.get('version') or '이전 폴더'})의 설정을 가져왔습니다."
    except (OSError,ValueError):
        return None


def pick_folder():
    """Windows folder dialog (PowerShell, nothing to install). None when it cannot be shown or nothing was picked."""
    if os.name!='nt':return None
    script=('[Console]::OutputEncoding=[Text.Encoding]::UTF8;Add-Type -AssemblyName System.Windows.Forms;'
            '$d=New-Object System.Windows.Forms.FolderBrowserDialog;$d.ShowNewFolderButton=$false;'
            "$d.Description='"+T('예전 버전 폴더를 고르세요 (예: Augustus-MP-261113-rc1)').replace("'","''")+"';"
            "if($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK){$d.SelectedPath}")
    try:
        r=subprocess.run(['powershell','-NoProfile','-STA','-ExecutionPolicy','Bypass','-Command',script],capture_output=True,timeout=600)
        text=r.stdout.decode('utf-8','replace').strip()
        return text or None
    except (OSError,subprocess.SubprocessError):
        return None


def T(text):
    """The console speaks the player's language (ui_text.py, the game's catalogs); Korean when anything is missing."""
    try:
        from ui_text import T as translate
        return translate(text,HERE)
    except Exception:
        return text


def say(text):print(T(text))


YES=('y','yes','ㅛ','예','네','д','да','j','ja','s','si','sí','o','oui')


def main(argv):
    if len(argv)>=3 and argv[1]=='--from':
        try:r=run(HERE,argv[2])
        except (OSError,ValueError) as e:say('가져오지 못했습니다: '+str(e));return 1
        say('가져온 것: '+(', '.join(NAMES.get(n,n) for n in r['copied']) or '없음'));return 0
    say('예전 버전의 설정을 이 버전으로 가져옵니다. 게임을 끈 뒤 진행하세요. 공동 저장(이어하기)은 가져오지 않습니다.\n')
    picked=pick_folder()
    if picked is None:
        try:picked=input(T('예전 버전 폴더 (예: D:\\Games\\Augustus-MP-261113-rc1): ')).strip().strip('"')
        except EOFError:picked=''
    if not picked:say('폴더를 고르지 않아 아무것도 바꾸지 않았습니다.');return 1
    try:
        src=resolve(HERE,picked);have=available(src)
        if not have:say('그 폴더에는 가져올 설정이 없습니다.');return 1
        say('고른 폴더: '+_plain(src.parent)+'  (버전 '+(str(_release(src).get('version','')) or '알 수 없음')+')')
        say('가져올 것: '+', '.join(NAMES[n] for n in have))
        replaced=[NAMES[n] for n in SETTINGS if (HERE/n).exists() and n in have]
        if replaced:say('이 버전에 이미 있는 '+', '.join(replaced)+'은(는) 바꾸기 전에 Augustus\\previous-version-backup-<시각> 폴더에 남깁니다.')
        if input(T('\n가져올까요? (Y/N): ')).strip().lower() not in YES:say('아무것도 바꾸지 않았습니다.');return 1
        r=run(HERE,src)
    except (OSError,ValueError,EOFError) as e:
        say('가져오지 못했습니다: '+str(e));return 1
    say('\n가져왔습니다: '+(', '.join(NAMES.get(n,n) for n in r['copied']) or '없음'))
    if r['backup']:say('바꾸기 전 설정: Augustus\\'+r['backup'])
    return 0


if __name__=='__main__':sys.exit(main(sys.argv))
