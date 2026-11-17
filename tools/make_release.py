"""Release package builder and checker (2026-11-13).

Copies a built work folder (test-24 after the build) into a new release folder by fixed rules, writes release.json,
makes the corresponding source archive, then checks the result. Nothing in the work folder is changed.

  python tools/make_release.py [--source WORK] [--out DIR] [--build NAME] [--package REV] [--zip]

Rules (Augustus/):
  kept      *.py *.exe *.dll *.config, the data files named in KEEP_JSON, the folders in KEEP_DIRS, and from scenarios/ only the folders named in
            default-scenarios.json plus INTERNAL_SCENARIOS (code loads those by path)
  left out  personal and per-machine files (settings, recent addresses, player names, work lists, caches, rooms, saves,
            prepared game data), tests and test fixtures, logs, old and draft scenarios
  anything else is NOT copied and is listed in the report under "unclassified" so that a new file is never shipped unseen
The game (augustus-mp-ui.exe) and the city engine (engine-city-test.exe) of the package are built here again, as a
release build (build/build_from_source.py --release): the test launcher's tools are not compiled in (user 2026-11-15:
"시험용 진단기능은 없어야 해"), and their files (TEST_ONLY) are in neither the package nor the source archive.
The check fails (exit 1) on: a missing executable, an executable older than its sources, a left-out name inside the
package, a personal path inside a text file, a default scenario that is missing / does not load, a launcher that
turns the test tools on, a release build that failed, or a test tool found inside a packaged executable. A failed package folder is kept for inspection and named in the report."""
import argparse,hashlib,json,os,re,shutil,sys,zipfile
from datetime import date
from pathlib import Path

KEEP_DIRS=['assets','i18n','korean','licenses','runtime']   # i18n: multilingual catalogs (tools/i18n_build.py)
KEEP_SUFFIXES={'.py','.exe','.dll','.config'}
# data files are named one by one: a json that is not here may be somebody's settings and is reported instead of shipped
KEEP_JSON={'building-catalog.json','capua-tarentum.json','capua-tarentum-legacy-r3.json','creator-city-catalog.json','default-scenarios.json',
           'empire-coast.json','empire-passage.json','preset-catalog.json','release.json','rome-capital.json','room_options_schema.json',
           'scenario-rules.json','trade-catalog.json'}
KEEP_DATA={'countries.tsv'}   # country names of the game hall's people list (hall_client / network_play), every edition
# Korean edition only (EDITIONS.md, user 2026-11-15): the company's game server, its address and the crash reports sent
# to it. Shipped with the Korean edition (languages ko); never inside another edition's package or source archive.
KOREAN_ONLY={'server_entry.py','server-address.txt','crash_report.py','diag_relay.py','dedicated_server.py','report_inbox.py',
             'diag_collect.py','multiplayer_server_entry.inc','test_server_entry.py','test_crash_report.py','test_dedicated_server.py','test_diag_relay.py',
             'hall_admin.py','hall_admin_client.py','multiplayer_hall_admin.inc','test_hall_admin.py',   # the server administrator (2026-11-15)
             'release_korean.py',   # the Korean edition's release in one go, with the NAS folder
             'update_check.py','update_server.py','ed25519.py','update-key.txt','test_update.py',   # 업데이트확인.cmd (2026-11-16)
             'game_hall.py','hall_client.py','multiplayer_hall.inc','test_game_hall.py',
             'multiplayer_hall_board.inc','test_hall_board.py',   # the hall's 알림판 (user 2026-11-17)
             'test_dev_rooms.py',   # 제작자 방의 로비 부분 검사; dev_tools.py, multiplayer_dev.inc are in both editions (user 2026-11-17)
             'spectate.py','spectate_client.py','multiplayer_spectate.inc','test_spectate.py',   # 관전 (user 2026-11-17)
             'patch-notes.txt'}   # 패치 기록 (user 2026-11-17): read by game_hall.py on the server   # the game hall: reached through 서버 접속 only; the Global edition is LAN only (user 2026-11-16)
KOREAN_ONLY_FOLDERS=('nas-server/',)
# Pictures made from Caesar III's own sprites (flag cloth, post office roof): the Korean edition ships them; another
# edition makes them on the player's PC from the player's own game (Augustus/caesar3_tints.py, user 2026-11-16)
FROM_CAESAR3=('Augustus/assets/Graphics/MP_Flags/E','Augustus/assets/Graphics/MP_Flags/S_','Augustus/assets/Graphics/Admin_Logistics/Player_Trade_Roof_Shade.png')
KOREAN_REQUIRED=['server_entry.py','server-address.txt','crash_report.py','hall_admin_client.py','update_check.py','ed25519.py','update-key.txt']
# A program whose file name is Korean gets an English one in the other editions (user 2026-11-16: no Korean left in the
# Global edition). Nothing starts it by name; the person opens it from the folder.
OTHER_EDITION_NAMES={'멀티저장설정.exe':'Autosave-Settings.exe'}
# The launchers built from their sources (build/build_launcher.py, 2026-11-16): each must be newer than its source.
LAUNCHER_SOURCES={'Augustus.exe':'creator-src/NetworkLauncher.cs','Augustus-Network.exe':'creator-src/NetworkLauncher.cs',
                  '멀티저장설정.exe':'creator-src/AutosaveSettings.cs','observe_atomic.dll':'creator-src/observe_atomic.c'}
KOREAN_DATA={'server-address.txt','update-key.txt','patch-notes.txt'}   # data files of the Korean edition only: the server's address, the key updates are checked with
INTERNAL_SCENARIOS=['capua-tarentum']      # scenario_project.DEFAULT: city_client and scenario_pair load it by path
REQUIRED=sorted(KEEP_JSON-{'capua-tarentum-legacy-r3.json'})+['Augustus.exe','Augustus-Network.exe','augustus-mp-ui.exe','engine-city-test.exe','Augustus-Scenario-Creator.exe',
          'SDL2.dll','SDL2_mixer.dll','runtime/python.exe','scenario_project.py','network_play.py','countries.tsv','licenses/Augustus-AGPL-3.0.md']
# name -> why it stays out
LEFT_OUT_DIRS={'도움말':'help texts written for builds network12..42 (2~4 players, old tab numbers, a preview scenario that is not shipped): wrong for this version',
               '예제 배치도':'layout pictures of the two practice examples that were dropped','__pycache__':'cache','creator-cache':'cache','lobby-preview-cache':'cache','roster-cache':'cache',
               'creator-projects':'the author\'s own scenarios','private-game-data':'prepared Caesar 3 data','rooms':'room databases and saves',
               'test-work':'test output','scenario-drafts':'drafts','creator-probes':'editor self-check output','bridge':'session files',
               'user-profile':'game settings and hotkeys','creator-maps':'the author\'s own city maps (editor map list)'}
# Test launcher tools and developer diagnostics: in no release, in no source archive (user 2026-11-15)
TEST_ONLY={'mp_test_tools.py':'test launcher tools (simulated ping, 황위·순행 test panel)','diag_relay.py':'developer diagnostics (developer key)',
           'diag_collect.py':'developer diagnostics collector','diag-key.txt':'developer key',
           'multiplayer_testtools.inc':'test launcher chat commands (/money, /invade, /fort)','multiplayer_throne_test.inc':'황위·순행 test panel'}
TEST_MARKS=[b'AUGUSTUS_MP_TEST_TOOLS',b'AUGUSTUS_TEST_RTT']   # inside a packaged executable: a test tool was compiled in
RELEASE_BUILDS=[('ui','augustus-mp-ui.exe'),('worker','engine-city-test.exe')]
# What only the Korean edition's game files read (the hall, 서버 접속 and 업데이트 확인, 관전, 알림판, 관리자): never
# inside another edition's game (user 2026-11-17: the Global edition's menu showed 'Game server' and 'Check for updates',
# as its release build had compiled the Korean files still in the work folder's src/)
KOREAN_MARKS=[b'update-check.txt',b'hall-chat.txt',b'hall-entry.txt',b'spectate-state.txt',b'hall-board.txt',b'hall-admin.txt']
LEFT_OUT_FILES={'creator-language.txt':'the editor language somebody chose','previous-version.json':'settings import record (personal)','network-settings.json':'this PC\'s Caesar 3 folder','profile-migration.json':'personal profile state','creator-workspace.json':'recent work list (personal paths)','multiplayer-settings.json':'personal settings',
                'network-preferences.json':'recent addresses and player names','network-adapters.json':'this machine\'s network adapters',
                'start_fixture.py':'test fixture','empire-coast-report.md':'working report',
                'dedicated_server.py':'the game server (runs on the NAS from nas-server, not on a player PC)','report_inbox.py':'the game server\'s crash report inbox (NAS only)',
                'hall_admin.py':'the game server\'s administrator login and commands (NAS only)',
                'update_server.py':'the game server\'s side of 업데이트확인.cmd (NAS only)'}
LEFT_OUT_PATTERNS=[(r'test_.*\.py','test'),(r'.*\.log','log'),(r'.*\.(pdb|mdb|ilk|exp|lib|obj)','build by-product'),(r'tmp.*','temporary'),
                   (r'.*-latest\.txt','editor self-check output'),(r'creator-.*\.png','editor self-check output'),(r'.*(probe|results)\.json','editor self-check output'),(r'.*\.(sav|svx|sqlite|db)','save or room data'),
                   (r'korean-(dotum|hahmlet|ridi|museum|taebaek|original)-.*','old Korean font (global edition ships Noto Sans KR only, 2026-11-14)')]
TEXT_SUFFIXES={'.py','.json','.txt','.md','.cmd','.bat','.config','.xml','.ini','.cfg'}
PERSONAL=re.compile(r'[A-Za-z]:[\\/]+(?:Claude|Codex|Users|Documents and Settings)\b|/home/[a-z]|/Users/[A-Za-z]',re.I)
SOURCE_PARTS=[('creator-src','**/*'),('tools','make_*.py'),('tools','gen_*.py'),('tools','build_*.py'),('tools','*.h'),('tools','i18n_*.py'),('tools','font/*.py'),('i18n','*'),('build','*.py'),('build','native-sources.json'),('build','utf8.manifest'),('Augustus','*.py')]
SOURCE_SUFFIXES={'.c','.h','.inc','.cpp','.hpp','.cs','.py','.json','.manifest','.xml','.txt','.md','.csv'}

def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(1<<20),b''):h.update(block)
    return h.hexdigest()

def left_out(name,is_dir):
    if is_dir:
        if name in LEFT_OUT_DIRS:return LEFT_OUT_DIRS[name]
        if re.fullmatch(r'diag-\d{8}-\d{6}',name):return 'developer diagnostics output'
        if re.fullmatch(r'previous-version-backup-.*|.*\.importing-[0-9a-f]+',name):return 'settings import (personal)'
        return 'temporary' if re.fullmatch(r'tmp.*',name) else None
    if name in TEST_ONLY:return 'test only, in no release: '+TEST_ONLY[name]
    if name in LEFT_OUT_FILES:return LEFT_OUT_FILES[name]
    return next((why for pattern,why in LEFT_OUT_PATTERNS if re.fullmatch(pattern,name,re.I)),None)

def newest(folder,suffixes):
    best=(0,None)
    for p in folder.rglob('*'):
        if p.is_file() and p.suffix.lower() in suffixes and '__pycache__' not in p.parts:best=max(best,(p.stat().st_mtime,p))
    return best

def copy_tree(src,dst,report,korean=True):
    """A kept folder is copied whole, minus caches and anything a left-out rule names."""
    for p in sorted(src.rglob('*')):
        rel=p.relative_to(src)
        if any(part=='__pycache__' for part in rel.parts):continue
        if p.is_dir():continue
        why=None if src.name=='runtime' else left_out(p.name,False)    # the python runtime is copied as it is
        if not why and not korean and ('Augustus/'+src.name+'/'+str(rel).replace('\\','/')).startswith(FROM_CAESAR3):why='made from Caesar III\'s sprites: made on the player\'s PC (caesar3_tints.py)'
        if why:report['left_out'].append((str(Path(src.name)/rel),why));continue
        (dst/rel).parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dst/rel)

def korean_edition(names):return names['languages']==['ko']

def edition_src(source,work,report):
    """Another edition's src/: the work folder's, without the Korean edition's files (EDITIONS.md), as the public
    source has it. Built from there, the game has no 서버 접속, 업데이트 확인, hall, 관전 or 알림판 (user 2026-11-17)."""
    out=work/'src'
    if out.exists():shutil.rmtree(out)
    def skip(folder,names):return [n for n in names if n in KOREAN_ONLY or n in TEST_ONLY]
    shutil.copytree(source/'src',out,ignore=skip)
    report['notes'].append('release build from src/ without the Korean edition\'s files: '+', '.join(sorted(n for n in KOREAN_ONLY if any((source/'src').rglob(n)))))
    return out

def release_build(source,target,work,report,names=None):
    """The package's game and engine, built again from the work folder as a release build (AUGUSTUS_RELEASE: no test
    launcher tool compiled in). `work`: a scratch folder outside the package, removed when every build succeeded.
    Another edition than the Korean one is built from its own src/ (edition_src)."""
    import subprocess
    script=source/'build/build_from_source.py'
    if not script.is_file():report['fail'].append('build/build_from_source.py not found: the release build could not run');return
    work.mkdir(parents=True,exist_ok=True)
    extra=[] if names is None or korean_edition(names) else ['--src',str(edition_src(source,work,report))]
    ok=True
    for kind,exe in RELEASE_BUILDS:
        print(f'  릴리스 빌드: {exe} (몇 분 걸립니다)',flush=True)
        r=subprocess.run([sys.executable,'-B','-X','utf8',str(script),'--root',str(source),'--out',str(work),'--target',kind,'--release','--jobs',str(min(16,os.cpu_count() or 4)),*extra],
                         capture_output=True,text=True,encoding='utf8',errors='replace')
        line=next((l for l in r.stdout.splitlines() if l.startswith('{')),'{}')
        try:info=json.loads(line)
        except ValueError:info={}
        if r.returncode or not info.get('success') or not info.get('release') or (extra and not info.get('src')):
            ok=False;tail=(r.stdout+r.stderr).strip().splitlines()[-6:]
            report['fail'].append(f'release build of {exe} failed (run the test launcher first: it brings build_from_source.py with --release): '+' | '.join(tail));continue
        shutil.copy2(info['executable'],target/'Augustus'/exe)
        report['notes'].append(f'release build: {exe} sha256 {sha(target/"Augustus"/exe)[:16]} (no test tools)')
    if ok:shutil.rmtree(work,ignore_errors=True)
    else:report['notes'].append(f'release build output kept for inspection: {work}')

def build(source,target,names,report):
    a=source/'Augustus';out=target/'Augustus';out.mkdir(parents=True)
    listed=json.loads((a/'default-scenarios.json').read_text(encoding='utf-8-sig'))['scenarios']
    for p in sorted(a.iterdir()):
        why=left_out(p.name,p.is_dir())
        if not why and p.name in KOREAN_ONLY and not korean_edition(names):why='Korean edition only (EDITIONS.md)'
        if why:report['left_out'].append((p.name+('/' if p.is_dir() else ''),why));continue
        if p.is_dir():
            if p.name=='scenarios':
                for folder in sorted(x for x in p.iterdir()):
                    if folder.is_dir() and folder.name in listed+INTERNAL_SCENARIOS:shutil.copytree(folder,out/'scenarios'/folder.name,ignore=shutil.ignore_patterns('__pycache__'))
                    else:report['left_out'].append(('scenarios/'+folder.name,'not a default scenario'))
            elif p.name=='i18n':
                # Editions (user 2026-11-14): Korean first, then English, the other languages later. A display
                # language is offered by the game and the editor only when its catalog is in the package.
                (out/'i18n').mkdir(parents=True,exist_ok=True)
                for f in sorted(p.iterdir()):
                    if not f.is_file():continue
                    if f.suffix.lower()!='.tsv' or f.stem in names['languages']:shutil.copy2(f,out/'i18n'/f.name)   # extra-letters.txt: always (c3_text_convert.py)
                    else:report['left_out'].append(('i18n/'+f.name,'language not in this edition'))
                # the edition's display languages (2026-11-15): the game and the editor offer only these (the English
                # edition has no Korean; src/core/mp_language.c, creator-src/CreatorLang.cs)
                (out/'i18n'/'edition.txt').write_text(' '.join(names['languages'])+'\n',encoding='ascii',newline='')
            elif p.name in KEEP_DIRS:copy_tree(p,out/p.name,report,korean_edition(names))
            else:report['unclassified'].append(p.name+'/')
        elif p.suffix.lower() in KEEP_SUFFIXES or p.name in KEEP_JSON or p.name in KEEP_DATA or (p.name in KOREAN_DATA and korean_edition(names)):shutil.copy2(p,out/(p.name if korean_edition(names) else OTHER_EDITION_NAMES.get(p.name,p.name)))
        else:report['unclassified'].append(p.name)
    old=json.loads((a/'release.json').read_text(encoding='utf-8-sig'))
    old.update(version=names['version'],internal_build=names['build'],multiplayer_build=names['build'],package_revision=names['package'],
               channel='release',distribution='release',modified_date=names['date'],corresponding_source_archive=names['sources'],
               contains_personal_saves=False,contains_caesar3_base_data=False)
    (out/'release.json').write_text(json.dumps(old,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    write_package_notes(target,names)


def write_package_notes(target,names):
    """The launchers and readmes at the top of a package (Korean edition: Korean names; Global: English names only)."""
    (target/'실행.cmd').write_text('@echo off\r\npushd "%~dp0Augustus"\r\nstart "" "Augustus.exe"\r\npopd\r\n',encoding='ascii',newline='')
    # settings from an earlier version the person picks (previous_version.py: folder dialog, confirm; joint saves stay behind)
    (target/'이전-버전-설정-가져오기.cmd').write_bytes(('@echo off\r\nchcp 65001 >nul\r\n'
        'rem 예전 버전 폴더를 골라 게임 설정·단축키·시저 3 폴더 위치·최근 IP·아이디·내 시나리오를 가져온다(공동 저장은 가져오지 않는다).\r\n'
        'pushd "%~dp0Augustus"\r\n"runtime\\python.exe" -B -X utf8 previous_version.py\r\npopd\r\npause\r\n').encode('utf-8'))
    if korean_edition(names):   # the Korean edition brings itself to the server's version (update_check.py, 2026-11-16)
        (target/'업데이트확인.cmd').write_bytes(('@echo off\r\nchcp 65001 >nul\r\ntitle 업데이트 확인\r\n'
            'rem 회사 게임 서버에서 최신 버전을 확인하고, 바뀐 파일만 받아 바꾼다. 게임과 에디터를 끈 뒤 실행한다.\r\n'
            'rem 한 줄로 끝낸다: 업데이트가 이 파일을 바꿔도 cmd가 바뀐 파일의 남은 줄을 읽지 않게(exit /b).\r\n'
            '"%~dp0Augustus\\runtime\\python.exe" -B -X utf8 "%~dp0Augustus\\update_check.py" & pause & exit /b\r\n').encode('utf-8'))
    (target/'읽어보기.txt').write_text(
        'Augustus 멀티플레이 '+names['version']+'\r\n\r\n'
        '실행: 실행.cmd (또는 Augustus\\Augustus.exe)\r\n'
        +('업데이트: 게임을 끄고 업데이트확인.cmd를 실행하면 서버의 최신 버전으로 바뀐 파일만 받습니다.\r\n' if korean_edition(names) else '')+
        '시저 3 원본 게임이 설치되어 있어야 합니다. 이 꾸러미에는 원본 게임 자료가 들어 있지 않습니다.\r\n'
        '같은 방에 들어가려면 모두 같은 버전을 써야 합니다. 대기실 오른쪽 위에 방장 버전과 내 버전이 나옵니다.\r\n'
        '예전 버전 폴더 위에 덮어 풀어도 방 저장·설정·내 시나리오는 그대로 남습니다(이 꾸러미에는 그런 파일이 없습니다).\r\n'
        '예전 버전의 게임 설정·단축키·시저 3 폴더 위치·최근 IP·아이디·내 시나리오는 이전-버전-설정-가져오기.cmd를 실행해 예전 폴더를 고르면 가져옵니다(공동 저장은 가져오지 않습니다).\r\n'
        '새 폴더에 풀면 예전 저장은 예전 폴더에 남습니다. 예전 버전에서 만든 방 저장을 이 버전에서 이어 하는 것은 보장하지 않습니다.\r\n\r\n'
        'Augustus는 GNU AGPL v3 라이선스입니다(Augustus\\licenses 폴더). 이 버전의 소스 코드는 '+names['sources']+' 에 있습니다.\r\n',encoding='utf-8-sig',newline='')
    # Players who do not read Korean (multilingual, 2026-11-14): the same two launchers under English names and a
    # README in the other languages of this edition. The Korean files stay as they were. Korean edition: none.
    readmes=[t for code,t in zip(README_CODES,README_LANGUAGES) if code in names['languages']]
    if len(names['languages'])==1:   # one language: the game never asks, so the README does not say it does
        readmes=[r.replace(r.split('\n')[2].split('. ',1)[1],'').replace('Augustus.exe). \n','Augustus.exe).\n') if '. ' in r.split('\n')[2] else r for r in readmes]
    if readmes:
        (target/'Play.cmd').write_bytes((target/'실행.cmd').read_bytes())
        (target/'Import-previous-settings.cmd').write_bytes((target/'이전-버전-설정-가져오기.cmd').read_bytes())
        (target/'README.txt').write_text('\r\n'.join(t.format(version=names['version'],sources=names['sources']).replace('\n','\r\n') for t in readmes)+'\r\n',encoding='utf-8-sig',newline='')
    if 'ko' in names['languages']:(target/'인터넷으로-함께하기.txt').write_text(INTERNET_GUIDE['ko'].replace('\n','\r\n'),encoding='utf-8-sig',newline='')
    guides=[INTERNET_GUIDE[c] for c in README_CODES if c in names['languages']]
    if guides:(target/'Internet-play.txt').write_text('\r\n'.join(guides).replace('\n','\r\n'),encoding='utf-8-sig',newline='')
    if 'ko' not in names['languages']:   # an edition without Korean (the English one): only the English launchers and README
        for name in ('실행.cmd','이전-버전-설정-가져오기.cmd','읽어보기.txt'):(target/name).unlink()
    elif not korean_edition(names) and readmes:
        # The Global edition with Korean among its languages (user 2026-11-17: no Korean file names in the Global
        # package): the Korean readme and internet guide go inside README.txt and Internet-play.txt, last.
        ko=(target/'읽어보기.txt').read_text(encoding='utf-8-sig').replace('실행.cmd','Play.cmd').replace('이전-버전-설정-가져오기.cmd','Import-previous-settings.cmd')
        with (target/'README.txt').open('a',encoding='utf-8',newline='') as f:f.write('\r\n'+ko.replace('\r\n','\n').replace('\n','\r\n'))
        if guides:
            with (target/'Internet-play.txt').open('a',encoding='utf-8',newline='') as f:f.write('\r\n'+INTERNET_GUIDE['ko'].replace('인터넷으로-함께하기.txt','Internet-play.txt').replace('\n','\r\n'))
        for name in ('실행.cmd','이전-버전-설정-가져오기.cmd','읽어보기.txt','인터넷으로-함께하기.txt'):(target/name).unlink(missing_ok=True)


# Playing over the internet (user 2026-11-17: "안내서로 처리"): a room is one TCP port on the host's PC, so the
# package says how to reach it from afar (virtual LAN, or a forwarded port). Korean in 인터넷으로-함께하기.txt, the other
# languages of the edition together in Internet-play.txt.
INTERNET_GUIDE={
'ko':"""인터넷으로 함께하기 (같은 집·사무실 네트워크가 아닐 때)

이 게임의 멀티플레이는 방장 PC에 다른 사람이 IP로 들어오는 방식입니다(TCP 포트 48921 하나).
같은 네트워크(같은 공유기, 같은 사무실)라면 따로 할 일이 없습니다. 멀리 있는 사람과 하려면 아래 둘 중 하나를 고릅니다.

1. 가상 랜 (권장, 공유기 설정 필요 없음)
   Radmin VPN, Tailscale, ZeroTier 같은 프로그램을 모두가 설치하고 같은 네트워크에 들어갑니다.
   방장: 멀티플레이 > 랜 플레이 > 방 만들기에서 "사용할 네트워크"로 그 프로그램의 주소(Tailscale은 100.으로 시작)를 고릅니다.
   참가자: 방 입장의 "방장 IP"에 방장의 그 주소를 넣고 검색한 뒤 입장합니다.
   목록에 그 주소가 안 보이면 가상 랜 프로그램이 켜져 연결되어 있는지 확인한 뒤 게임을 다시 엽니다.

2. 공유기 포트 열기 (방장만 설정)
   방장 공유기에서 TCP 48921을 방장 PC의 내부 IP로 넘기도록 설정합니다(포트 포워딩).
   방장: 방 만들기에서 "사용할 네트워크"로 그 내부 IP(보통 192.168. 또는 10.으로 시작)를 고릅니다.
   참가자: "방장 IP"에 방장의 공인 IP(검색창에 "내 IP"로 확인)를 넣습니다.
   통신사가 공인 IP를 나눠 쓰는 경우(CGNAT)에는 포트를 열어도 들어올 수 없습니다. 그때는 1번을 쓰세요.

공통
- 처음 방을 만들 때 Windows 방화벽 창이 뜨면 "허용"을 누르세요. 놓쳤다면 Windows 방화벽 설정에서 이 게임 폴더의 Augustus\\runtime\\python.exe를 허용합니다.
- 모두 같은 버전이어야 합니다. 대기실 오른쪽 위에 방장 버전과 내 버전이 나옵니다.
- 주소는 IPv4(숫자 네 개)만 됩니다. 이름 주소나 IPv6는 넣을 수 없습니다.
""",
'en':"""Playing over the internet (when you are not on the same home or office network)

Multiplayer works by the other players connecting to the host's PC by IP (one TCP port, 48921).
On the same network (same router, same office) there is nothing to set up. To play with people far away, pick one of these.

1. Virtual LAN (recommended, no router settings)
   Everyone installs a program such as Radmin VPN, Tailscale or ZeroTier and joins the same network.
   Host: Multiplayer > LAN play > Create room, and under "Network to use" pick that program's address (Tailscale's starts with 100.).
   Players: Join room, enter that address as "Host IP", search, then join.
   If the address is not in the list, check that the virtual LAN program is running and connected, then open the game again.

2. Open a port on the router (host only)
   On the host's router, forward TCP 48921 to the host PC's local IP (port forwarding).
   Host: under "Network to use" pick that local IP (usually starting with 192.168. or 10.).
   Players: enter the host's public IP as "Host IP" (search the web for "what is my IP").
   If the internet provider shares one public IP among customers (CGNAT), an open port does not help; use option 1.

Good to know
- When Windows Firewall asks the first time you create a room, choose Allow. If you missed it, allow Augustus\\runtime\\python.exe of this game folder in the Windows Firewall settings.
- Everyone needs the same version. The lobby shows the host's version and yours at the top right.
- Addresses must be IPv4 (four numbers). Host names and IPv6 do not work.
""",
'ru':"""Игра через интернет (если вы не в одной домашней или офисной сети)

Сетевая игра работает так: остальные подключаются к ПК хоста по IP (один порт TCP 48921).
В одной сети (один роутер, один офис) настраивать ничего не нужно. Чтобы играть с теми, кто далеко, выберите один из вариантов.

1. Виртуальная локальная сеть (рекомендуется, роутер настраивать не нужно)
   Все ставят программу вроде Radmin VPN, Tailscale или ZeroTier и входят в одну сеть.
   Хост: «Сетевая игра» > «Игра по локальной сети» > «Создать комнату», в поле «Сеть» выберите адрес этой программы (у Tailscale он начинается со 100.).
   Игроки: «Войти в комнату», укажите этот адрес как «IP хоста», найдите комнату и войдите.
   Если адреса нет в списке, проверьте, что программа запущена и подключена, и откройте игру заново.

2. Открыть порт на роутере (только хост)
   На роутере хоста перенаправьте TCP 48921 на локальный IP ПК хоста (проброс портов).
   Хост: в поле «Сеть» выберите этот локальный IP (обычно начинается с 192.168. или 10.).
   Игроки: укажите внешний IP хоста как «IP хоста» (найдите в интернете «мой IP»).
   Если провайдер делит один внешний IP между клиентами (CGNAT), открытый порт не поможет; используйте вариант 1.

Полезно знать
- Когда при первом создании комнаты брандмауэр Windows спросит разрешение, нажмите «Разрешить». Если пропустили, разрешите Augustus\\runtime\\python.exe из папки игры в настройках брандмауэра Windows.
- У всех должна быть одна версия. В лобби справа вверху видны версии хоста и ваша.
- Адрес только IPv4 (четыре числа). Имена и IPv6 не подходят.
""",
'de':"""Über das Internet spielen (wenn ihr nicht im selben Heim- oder Büronetz seid)

Im Mehrspieler verbinden sich die anderen per IP mit dem PC des Hosts (ein TCP-Port, 48921).
Im selben Netz (gleicher Router, gleiches Büro) ist nichts einzurichten. Um mit Leuten weit weg zu spielen, wählt eine der beiden Möglichkeiten.

1. Virtuelles LAN (empfohlen, keine Router-Einstellungen)
   Alle installieren ein Programm wie Radmin VPN, Tailscale oder ZeroTier und treten demselben Netz bei.
   Host: Mehrspieler > LAN-Spiel > Raum erstellen und unter „Zu nutzendes Netzwerk“ die Adresse dieses Programms wählen (bei Tailscale beginnt sie mit 100.).
   Spieler: Raum beitreten, diese Adresse als „Host-IP“ eingeben, suchen und beitreten.
   Steht die Adresse nicht in der Liste, prüfen, ob das Programm läuft und verbunden ist, und das Spiel neu öffnen.

2. Einen Port am Router öffnen (nur der Host)
   Am Router des Hosts TCP 48921 an die lokale IP des Host-PCs weiterleiten (Portweiterleitung).
   Host: unter „Zu nutzendes Netzwerk“ diese lokale IP wählen (beginnt meist mit 192.168. oder 10.).
   Spieler: die öffentliche IP des Hosts als „Host-IP“ eingeben (im Web nach „meine IP“ suchen).
   Teilt der Anbieter eine öffentliche IP unter vielen Kunden (CGNAT), hilft ein offener Port nicht; dann Möglichkeit 1 nutzen.

Gut zu wissen
- Fragt die Windows-Firewall beim ersten Erstellen eines Raums, „Zulassen“ wählen. Falls verpasst, Augustus\\runtime\\python.exe aus dem Spielordner in den Einstellungen der Windows-Firewall zulassen.
- Alle brauchen dieselbe Version. Oben rechts in der Lobby stehen die Version des Hosts und deine.
- Nur IPv4-Adressen (vier Zahlen). Namen und IPv6 gehen nicht.
""",
'es':"""Jugar por internet (si no estáis en la misma red de casa u oficina)

El multijugador funciona así: los demás se conectan al PC del anfitrión por IP (un puerto TCP, 48921).
En la misma red (mismo router, misma oficina) no hay que configurar nada. Para jugar con gente lejos, elige una de estas opciones.

1. LAN virtual (recomendado, sin tocar el router)
   Todos instalan un programa como Radmin VPN, Tailscale o ZeroTier y entran en la misma red.
   Anfitrión: Multijugador > Juego en LAN > Crear sala, y en «Red a usar» elige la dirección de ese programa (la de Tailscale empieza por 100.).
   Jugadores: Entrar en sala, escribe esa dirección como «IP del anfitrión», busca y entra.
   Si la dirección no aparece en la lista, comprueba que el programa está abierto y conectado y vuelve a abrir el juego.

2. Abrir un puerto en el router (solo el anfitrión)
   En el router del anfitrión, redirige TCP 48921 a la IP local del PC del anfitrión (redirección de puertos).
   Anfitrión: en «Red a usar» elige esa IP local (suele empezar por 192.168. o 10.).
   Jugadores: escribe la IP pública del anfitrión como «IP del anfitrión» (busca «cuál es mi IP» en la web).
   Si tu proveedor comparte una IP pública entre clientes (CGNAT), abrir el puerto no sirve; usa la opción 1.

Conviene saber
- Cuando el Firewall de Windows pregunte al crear la primera sala, elige Permitir. Si se te pasó, permite Augustus\\runtime\\python.exe de la carpeta del juego en la configuración del Firewall de Windows.
- Todos necesitan la misma versión. En la sala de espera, arriba a la derecha, se ven la del anfitrión y la tuya.
- Solo direcciones IPv4 (cuatro números). No sirven nombres ni IPv6.
""",
'fr':"""Jouer par internet (si vous n'êtes pas sur le même réseau à la maison ou au bureau)

En multijoueur, les autres se connectent au PC de l'hôte par IP (un seul port TCP, 48921).
Sur le même réseau (même box, même bureau), rien à régler. Pour jouer avec des gens éloignés, choisissez une de ces solutions.

1. LAN virtuel (conseillé, pas de réglage de la box)
   Tout le monde installe un programme comme Radmin VPN, Tailscale ou ZeroTier et rejoint le même réseau.
   Hôte : Multijoueur > Jeu en LAN > Créer un salon, et dans « Réseau à utiliser » choisissez l'adresse de ce programme (celle de Tailscale commence par 100.).
   Joueurs : Rejoindre un salon, saisissez cette adresse comme « IP de l'hôte », recherchez puis rejoignez.
   Si l'adresse n'est pas dans la liste, vérifiez que le programme est lancé et connecté, puis rouvrez le jeu.

2. Ouvrir un port sur la box (l'hôte seulement)
   Sur la box de l'hôte, redirigez TCP 48921 vers l'IP locale du PC de l'hôte (redirection de port).
   Hôte : dans « Réseau à utiliser », choisissez cette IP locale (commence souvent par 192.168. ou 10.).
   Joueurs : saisissez l'IP publique de l'hôte comme « IP de l'hôte » (cherchez « quelle est mon IP » sur le web).
   Si le fournisseur partage une IP publique entre clients (CGNAT), ouvrir le port ne suffit pas ; utilisez la solution 1.

Bon à savoir
- Quand le pare-feu Windows demande l'autorisation à la création du premier salon, choisissez Autoriser. Si vous l'avez manqué, autorisez Augustus\\runtime\\python.exe du dossier du jeu dans les réglages du pare-feu Windows.
- Tout le monde doit avoir la même version. En haut à droite du salon s'affichent la version de l'hôte et la vôtre.
- Adresses IPv4 uniquement (quatre nombres). Les noms et l'IPv6 ne marchent pas.
""",
}

# Package README for players who do not read Korean (see the 'Play.cmd' lines above). {version} and {sources} are filled in.
README_CODES=['en','ru','de','es','fr']   # same order as README_LANGUAGES
README_LANGUAGES=[
"""Augustus multiplayer {version}

Start: Play.cmd (or Augustus\\Augustus.exe). The game asks for the language the first time it starts; change it later with the "Display language" option.
The original Caesar III must be installed. This package does not contain the original game data.
Everyone in a room must use the same version. The lobby shows the host's version and yours at the top right.
Unpacking over an earlier version's folder keeps room saves, settings and your scenarios (this package has no such files).
To bring game settings, hotkeys, the Caesar III folder, recent IP addresses and names and your scenarios from an earlier version, run Import-previous-settings.cmd and choose the earlier folder (joint saves are not brought over).
Unpacked into a new folder, earlier saves stay in the earlier folder. Continuing a room save made with an earlier version is not guaranteed.
Augustus is licensed under the GNU AGPL v3 (Augustus\\licenses folder). The source code of this version is in {sources}.
""",
"""Augustus, сетевая игра {version}

Запуск: Play.cmd (или Augustus\\Augustus.exe). При первом запуске игра спросит язык; позже его можно сменить параметром «Язык интерфейса».
Нужна установленная оригинальная Caesar III. В этом пакете нет данных оригинальной игры.
В одной комнате у всех должна быть одна и та же версия. В лобби справа вверху видны версии хоста и ваша.
Если распаковать поверх папки прежней версии, сохранения комнат, настройки и ваши сценарии останутся (в пакете таких файлов нет).
Чтобы перенести из прежней версии настройки игры, горячие клавиши, папку Caesar III, последние IP и имена и ваши сценарии, запустите Import-previous-settings.cmd и выберите прежнюю папку (общие сохранения не переносятся).
При распаковке в новую папку прежние сохранения остаются в прежней папке. Продолжение сохранений комнат из прежних версий не гарантируется.
Augustus распространяется по лицензии GNU AGPL v3 (папка Augustus\\licenses). Исходный код этой версии: {sources}.
""",
"""Augustus Mehrspieler {version}

Start: Play.cmd (oder Augustus\\Augustus.exe). Beim ersten Start fragt das Spiel nach der Sprache; später änderst du sie mit der Option „Anzeigesprache“.
Das originale Caesar III muss installiert sein. Dieses Paket enthält keine Daten des Originalspiels.
Alle in einem Raum müssen dieselbe Version nutzen. Oben rechts in der Lobby stehen die Version des Hosts und deine.
Entpackst du über den Ordner einer früheren Version, bleiben Raum-Spielstände, Einstellungen und deine Szenarien erhalten (dieses Paket enthält solche Dateien nicht).
Um Spieleinstellungen, Tastenkürzel, den Caesar-III-Ordner, letzte IP-Adressen und Namen sowie deine Szenarien aus einer früheren Version zu übernehmen, starte Import-previous-settings.cmd und wähle den früheren Ordner (gemeinsame Spielstände werden nicht übernommen).
In einem neuen Ordner bleiben frühere Spielstände im früheren Ordner. Ob sich Raum-Spielstände früherer Versionen fortsetzen lassen, ist nicht garantiert.
Augustus steht unter der GNU AGPL v3 (Ordner Augustus\\licenses). Der Quellcode dieser Version liegt in {sources}.
""",
"""Augustus multijugador {version}

Inicio: Play.cmd (o Augustus\\Augustus.exe). El juego pregunta el idioma la primera vez que se inicia; después puedes cambiarlo con la opción «Idioma de la interfaz».
Debes tener instalado el Caesar III original. Este paquete no incluye los datos del juego original.
Todos los de una sala deben usar la misma versión. En la sala, arriba a la derecha, aparecen la versión del anfitrión y la tuya.
Si lo descomprimes sobre la carpeta de una versión anterior, se conservan los guardados de sala, los ajustes y tus escenarios (este paquete no trae esos archivos).
Para traer de una versión anterior los ajustes del juego, los atajos, la carpeta de Caesar III, las IP y nombres recientes y tus escenarios, ejecuta Import-previous-settings.cmd y elige la carpeta anterior (los guardados conjuntos no se traen).
Si lo descomprimes en una carpeta nueva, los guardados anteriores se quedan en la carpeta anterior. No se garantiza poder continuar guardados de sala de versiones anteriores.
Augustus tiene licencia GNU AGPL v3 (carpeta Augustus\\licenses). El código fuente de esta versión está en {sources}.
""",
"""Augustus multijoueur {version}

Lancement : Play.cmd (ou Augustus\\Augustus.exe). Le jeu demande la langue au premier lancement ; vous pourrez la changer ensuite avec l'option « Langue d'affichage ».
Caesar III d'origine doit être installé. Ce paquet ne contient pas les données du jeu d'origine.
Tous les joueurs d'un salon doivent utiliser la même version. Le salon affiche en haut à droite la version de l'hôte et la vôtre.
Décompressé par-dessus le dossier d'une version précédente, il conserve les sauvegardes de salon, les réglages et vos scénarios (ce paquet ne contient pas de tels fichiers).
Pour importer d'une version précédente les réglages du jeu, les raccourcis, le dossier de Caesar III, les adresses IP et noms récents et vos scénarios, lancez Import-previous-settings.cmd et choisissez l'ancien dossier (les sauvegardes communes ne sont pas importées).
Décompressé dans un nouveau dossier, les anciennes sauvegardes restent dans l'ancien dossier. La reprise de sauvegardes de salon d'anciennes versions n'est pas garantie.
Augustus est sous licence GNU AGPL v3 (dossier Augustus\\licenses). Le code source de cette version se trouve dans {sources}.
""",
]

def source_archive(source,path,report,names=None):
    """Corresponding source: every file the native build compiles (build/native-sources.json) and every header or
    include file under its include folders, the editor source, the build and release scripts, the package's scripts.
    Third-party parts under deps/ (compiler, SDL) are not ours and are named in the report instead."""
    wanted={}
    def add(p):
        if p.is_file() and '__pycache__' not in p.parts and p.suffix.lower() in SOURCE_SUFFIXES and p.stat().st_size<8<<20:
            wanted[str(p.relative_to(source)).replace('\\','/')]=p
    manifest=source/'build/native-sources.json'
    if manifest.is_file():
        m=json.loads(manifest.read_text(encoding='utf8'));folders=set()
        for target in m['targets'].values():
            for s in target['sources']:
                if (source/s).is_file():wanted[s.replace('\\','/')]=source/s
                else:report['fail'].append('source listed by the build is missing: '+s)
        for folder in list(m['includes'])+list(m['system_includes']):
            if folder.startswith('deps/'):folders.add('(third party, not included) '+folder);continue
            for q in (source/folder).rglob('*'):
                if q.suffix.lower() in ('.h','.inc','.c','.cpp','.hpp'):add(q)
        report['notes']+=sorted(folders)
    else:
        report['notes'].append('build/native-sources.json not found: took src/ as it is')
        for q in (source/'src').rglob('*'):add(q)
    for folder,pattern in SOURCE_PARTS:
        base=source/folder
        if not base.is_dir():report['notes'].append('source folder not found: '+folder);continue
        for q in sorted(base.glob(pattern)):
            if not left_out(q.name,False) or q.suffix.lower()=='.py':add(q)
    for name in ('LICENSE.txt','LICENSE.txt','Augustus/licenses/Augustus-AGPL-3.0.md','res/augustus.ico'):   # the icon: in Augustus.exe (build/build_launcher.py)
        if (source/name).is_file():wanted[name]=source/name
    for name in [n for n in wanted if n.rsplit('/',1)[-1] in TEST_ONLY]:   # test and developer only, in no edition (2026-11-15)
        del wanted[name];report['left_out'].append(('source: '+name,'test only, in no release: '+TEST_ONLY[name.rsplit('/',1)[-1]]))
    if names is not None and not korean_edition(names):   # the Korean-only parts are not in another edition's source (EDITIONS.md)
        for name in [n for n in wanted if n.rsplit('/',1)[-1] in KOREAN_ONLY or n.startswith(KOREAN_ONLY_FOLDERS)]:
            del wanted[name];report['left_out'].append(('source: '+name,'Korean edition only (EDITIONS.md)'))
    leaks=[]
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
        for name in sorted(wanted):
            z.write(wanted[name],name)
            try:
                if re.search(r'[A-Za-z]:[\\/]+(?:Claude|Codex|Users)\b',wanted[name].read_text(encoding='utf-8-sig',errors='replace')):leaks.append(name)   # upstream files may mention unix paths: only this PC's folders count
            except OSError:pass
    report['notes'].append(f'source archive: {path.name} ({len(wanted)} files)')
    if leaks:report['fail'].append('personal path inside the source archive: '+', '.join(leaks[:12])+(' ...' if len(leaks)>12 else ''))
    if not any(n.endswith('.c') for n in wanted):report['fail'].append('source archive has no C sources')

def check(source,target,report,names=None):
    a=source/'Augustus';out=target/'Augustus';fail=report['fail']
    korean=names is None or korean_edition(names)
    for name in REQUIRED+(KOREAN_REQUIRED if korean else []):
        if not (out/name).is_file():fail.append('missing: Augustus/'+name)
    if not korean:
        for p in out.rglob('*'):
            if p.name in KOREAN_ONLY:fail.append('Korean-edition file inside another edition: Augustus/'+str(p.relative_to(out)))
    # executables must be newer than what they are built from
    for exe,folder,suffixes in (('augustus-mp-ui.exe','src',{'.c','.h','.inc','.cpp'}),('engine-city-test.exe','src',{'.c','.h','.inc','.cpp'}),('Augustus-Scenario-Creator.exe','creator-src',{'.cs'})):
        if (a/exe).is_file() and (source/folder).is_dir():
            when,which=newest(source/folder,suffixes)
            if which and when>(a/exe).stat().st_mtime+1:fail.append(f'{exe} is older than {which.relative_to(source)}: rebuild first')
        elif not (source/folder).is_dir():report['notes'].append(f'{folder}/ not found: could not compare {exe} with its sources')
    for exe,src in LAUNCHER_SOURCES.items():
        made=a/exe
        if made.is_file() and (source/src).is_file() and (source/src).stat().st_mtime>made.stat().st_mtime+1:fail.append(f'{exe} is older than {src}: rebuild first (build/build_launcher.py)')
        elif not (source/src).is_file():fail.append(f'{src} not found: {exe} has no source')
    # the packaged game and engine: release builds, no test tool compiled in
    for name in [n for _,n in RELEASE_BUILDS]:
        p=out/name
        if p.is_file():
            data=p.read_bytes()
            for mark in TEST_MARKS:
                if mark in data:fail.append(f'test tool inside Augustus/{name} ({mark.decode()}): not a release build')
            if not korean:
                for mark in KOREAN_MARKS:
                    if mark in data:fail.append(f'Korean-edition part inside Augustus/{name} ({mark.decode()}): built from src/ with the Korean files')
    # nothing that a rule leaves out may be inside, at any depth (the python runtime keeps its own test_*.py: allowed there)
    for p in sorted(out.rglob('*')):
        rel=p.relative_to(out)
        if rel.parts[0]=='runtime' and not (p.is_dir() and p.name=='__pycache__'):continue
        why=left_out(p.name,p.is_dir())
        if why:fail.append(f'left-out item inside the package: Augustus/{rel} ({why})')
    # personal paths in text files
    for p in sorted(target.rglob('*')):
        if not p.is_file() or p.suffix.lower() not in TEXT_SUFFIXES or p.stat().st_size>4<<20:continue
        if p.relative_to(target).parts[:2]==('Augustus','runtime'):continue
        try:text=p.read_text(encoding='utf-8-sig',errors='replace')
        except OSError:continue
        m=PERSONAL.search(text)
        if m:fail.append(f'personal path in {p.relative_to(target)}: {text[max(0,m.start()-20):m.end()+30]!r}')
        if p.suffix.lower() in ('.cmd','.bat','.json','.config') and 'AUGUSTUS_MP_TEST_TOOLS' in text:fail.append(f'test tools switch in {p.relative_to(target)}')
    # default scenarios, with the package's own loader
    sys.path.insert(0,str(out));sys.dont_write_bytecode=True
    try:
        import scenario_project as sp
        listed=json.loads((out/'default-scenarios.json').read_text(encoding='utf-8-sig'))['scenarios']
        if not listed:fail.append('default scenario list is empty')
        for n in listed:
            f=out/'scenarios'/n/'scenario.json'
            try:
                d=sp.load(f);sp.require_runtime(d)
                # a throne scenario may be a default since 2026-11-14 (user): sp.load has already checked its rules and Rome
            except Exception as e:fail.append(f'default scenario {n}: {type(e).__name__} {e}')
        if not Path(sp.DEFAULT).is_file():fail.append('internal scenario missing: '+str(Path(sp.DEFAULT).relative_to(out)))
        extra=sorted(x.name for x in (out/'scenarios').iterdir() if x.name not in listed+INTERNAL_SCENARIOS)
        if extra:fail.append('extra scenario folders: '+', '.join(extra))
    except Exception as e:fail.append(f'scenario check could not run: {type(e).__name__} {e}')
    finally:sys.path.pop(0)
    licences=[p for p in (out/'licenses').glob('*') if p.is_file()] if (out/'licenses').is_dir() else []
    if not any('GNU AFFERO GENERAL PUBLIC LICENSE' in p.read_text(encoding='utf-8-sig',errors='replace')[:400] for p in licences):
        fail.append('the AGPL licence text of Augustus is not in Augustus/licenses')

def main():
    here=Path(__file__).resolve().parents[1]
    ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,default=here);ap.add_argument('--out',type=Path)
    ap.add_argument('--build',default='261113');ap.add_argument('--package',default='rc1');ap.add_argument('--zip',action='store_true')
    ap.add_argument('--languages',default='ko',help='display languages of this edition: ko (Korean edition), en (English edition), or a list such as ko,en')
    ap.add_argument('--changes',type=Path,help='change set folder (wip-25) that must already be applied to --source')
    ap.add_argument('--no-release-build',action='store_true',help='check only: copy the built executables as they are (the result is marked failed)')
    args=ap.parse_args();source=args.source.resolve();out_root=(args.out or source.parent/'release').resolve()
    for value in (args.build,args.package):
        if not re.fullmatch('[a-zA-Z0-9._-]{1,24}',value):sys.exit('version names: letters, digits, . _ - only')
    today=date.today();names=dict(build=args.build,package=args.package,date=today.isoformat(),version=f'{args.build}-{args.package}')   # e.g. 261113-rc1: what the waiting room shows after the upstream version
    names['languages']=list(dict.fromkeys(x.strip() for x in args.languages.split(',') if x.strip()))   # in the order given: the first is the edition's default language (edition.txt; Global edition: en first, user 2026-11-16)
    if not names['languages'] or any(x not in ['ko']+README_CODES for x in names['languages']):sys.exit('languages: ko, en, ru, de, es, fr')
    # the Korean edition keeps the plain names; another edition adds its languages (e.g. Augustus-MP-261115-rc1-en)
    tag='' if names['languages']==['ko'] else '-global' if set(names['languages'])==set(['ko']+README_CODES) else '-'+'-'.join(names['languages']);names['tag']=tag
    names['sources']=f'Augustus-MP-{names["version"]}{tag}-sources.zip';target=out_root/f'Augustus-MP-{names["version"]}{tag}'
    if not (source/'Augustus/default-scenarios.json').is_file():sys.exit(f'not a built work folder: {source}')
    if target.exists():sys.exit(f'already exists (delete or choose another name): {target}')
    if out_root==source or source in out_root.parents and (out_root.relative_to(source).parts[0] in ('Augustus','src')):sys.exit('choose an output folder outside Augustus/ and src/')
    report=dict(left_out=[],unclassified=[],notes=[],fail=[])
    build(source,target,names,report)
    if args.no_release_build:report['fail'].append('release build skipped (--no-release-build): this folder is not a release')
    else:release_build(source,target,out_root/f'.release-build-{names["version"]}{tag}',report,names)
    source_archive(source,out_root/names['sources'],report,names);check(source,target,report,names)
    # The main menu shows the version compiled into the game (src/platform/version.c), not release.json: it said
    # network62 on the 261113-rc1 package (user 2026-11-13). The package name must be in it.
    try:
        shown=re.search(r'AUGUSTUS_VERSION_SUFFIX\s+"([^"]*)"',(source/'src/platform/version.c').read_text(encoding='utf-8',errors='replace'))
        if not shown or names['version'] not in shown.group(1):
            report['fail'].append(f"main menu version ({shown.group(1) if shown else 'not found'}) does not name {names['version']}: change AUGUSTUS_VERSION_SUFFIX in src/platform/version.c and rebuild")
    except OSError as e:report['fail'].append('main menu version file unreadable: '+str(e))
    if args.changes:
        # The test launcher copies the change set onto the work folder before building (prepare_and_run.py, .txt files
        # excepted). A package made before that would miss the latest changes and still pass every other check.
        changes=args.changes.resolve();stale=[]
        if not changes.is_dir():report['fail'].append(f'change set folder not found: {changes}')
        else:
            for f in sorted(changes.rglob('*')):
                if not f.is_file() or (f.suffix.lower()=='.txt' and f.parent==changes) or '__pycache__' in f.parts:continue   # notes at the top only
                rel=f.relative_to(changes);there=source/rel
                if rel.parts[0]=='work':continue   # backups and records of each delivery (work/claude-*), not part of the change set
                if rel.parts[:2]==('Augustus','i18n') and f.suffix.lower()=='.tsv' and f.stem not in names['languages']:continue   # the Korean test copy (test-ko) has no other language (2026-11-15)
                if not there.is_file() or there.read_bytes()!=f.read_bytes():stale.append(str(rel))
            if stale:report['fail'].append(f'{len(stale)} changed file(s) not applied to the work folder yet (run the test launcher, which copies and builds): '+', '.join(stale[:8])+(' ...' if len(stale)>8 else ''))
            else:report['notes'].append(f'change set applied: every file of {changes.name} matches the work folder')
    files={str(p.relative_to(target)).replace('\\','/'):sha(p) for p in sorted(target.rglob('*')) if p.is_file()}
    (target/'files.sha256.json').write_text(json.dumps(dict(version=names['version'],files=files),ensure_ascii=False,indent=1),encoding='utf8')
    size=sum(p.stat().st_size for p in target.rglob('*') if p.is_file())
    lines=[f'배포 점검 결과 — {names["version"]}',f'원본 작업 폴더: {source}',f'배포 폴더: {target}',f'파일 {len(files)}개, {size/1048576:.1f} MB','',
           '언어: '+', '.join(names['languages']),'결과: '+('실패 — 아래 항목을 고친 뒤 이 폴더를 지우고 다시 실행' if report['fail'] else '통과'),'']
    lines+=['[실패]']+['- '+x for x in report['fail']]+[''] if report['fail'] else []
    lines+=['[분류되지 않아 넣지 않은 항목 — 필요한 파일이면 알려 주세요]']+['- '+x for x in report['unclassified']]+[''] if report['unclassified'] else []
    lines+=['[참고]']+['- '+x for x in report['notes']]+['','[규칙에 따라 뺀 항목]']+[f'- {n}: {why}' for n,why in report['left_out']]
    lines+=['','이 점검이 보지 않는 것: 게임 실행과 화면, 다른 PC에서의 설치, 시저 3 원본 인식.']
    (out_root/f'배포-점검결과-{names["version"]}{names["tag"]}.txt').write_text('\r\n'.join(lines)+'\r\n',encoding='utf-8-sig',newline='')
    if args.zip and not report['fail']:
        with zipfile.ZipFile(out_root/f'Augustus-MP-{names["version"]}{names["tag"]}.zip','w',zipfile.ZIP_DEFLATED) as z:
            for p in sorted(target.rglob('*')):
                if p.is_file():z.write(p,str(Path(target.name)/p.relative_to(target)).replace('\\','/'))
    print('\n'.join(lines[:6]))
    for x in report['fail']:print('  실패:',x)
    for x in report['unclassified']:print('  분류 안 됨:',x)
    return 1 if report['fail'] else 0

if __name__=='__main__':sys.exit(main())
