"""Open the real Augustus editor on a private copy and import its native mapx (or the terrain of a saved city, .svx).

Only launch() opens a window, in response to the user's editor button. All other
operations use a muted SDL dummy worker. Original C3/editor graphics stay local.
"""
import argparse,base64,hashlib,json,os,shutil,subprocess,sys,urllib.request,uuid,zipfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from city_client import Engine,game_data
from scenario_project import load,write_layout

CACHE=HERE/'creator-cache'
ZIP_URL='https://github.com/bvschaik/julius-support/releases/download/editor/caesar3_map_editor_english.zip'
ZIP_SHA='0b1715ebf06307a6bf170ceadb0493cdbe3936a254f215642ca265dec76fb83f'
EDITOR_FILES=('c3_map.eng','c3_map_mm.eng','c3map.sg2','c3map.555','c3map_north.sg2','c3map_north.555','c3map_south.sg2','c3map_south.555','map_panels.555')

def digest(raw):return hashlib.sha256(raw).hexdigest()
def write_json(path,data):
    Path(path).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
def read_json(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def new_session():
    path=CACHE/'native-editor'/uuid.uuid4().hex
    path.mkdir(parents=True);return path

def editor_data():
    source=game_data().resolve()
    top={p.name.lower():p for p in source.iterdir() if p.is_file()}
    missing=[n for n in EDITOR_FILES if n not in top]
    key=digest((str(source)+'\n'+ZIP_SHA+'\nfont-binary-v2').encode())[:24]
    target=CACHE/('native-editor-data-'+key)
    if (target/'prepared.json').is_file() and all((target/n).is_file() for n in EDITOR_FILES):return target
    CACHE.mkdir(parents=True,exist_ok=True)
    archive=CACHE/'caesar3_map_editor_english.zip'
    if missing and (not archive.exists() or digest(archive.read_bytes())!=ZIP_SHA):
        request=urllib.request.Request(ZIP_URL,headers={'User-Agent':'Augustus-Korean-Scenario-Creator'})
        temp=CACHE/('editor-download-'+uuid.uuid4().hex+'.zip')
        try:
            with urllib.request.urlopen(request,timeout=90) as response, temp.open('wb') as f:
                length=0
                while True:
                    block=response.read(1024*1024)
                    if not block:break
                    length+=len(block)
                    if length>32*1024*1024:raise ValueError('편집기 자료가 허용 크기를 초과했습니다.')
                    f.write(block)
            if digest(temp.read_bytes())!=ZIP_SHA:raise ValueError('공식 편집기 자료의 해시가 달라 설치를 중단했습니다.')
            os.replace(temp,archive)
        finally:
            if temp.exists():temp.unlink()
    target.mkdir(parents=True,exist_ok=True)
    # Read-only game assets may be hard-linked. Native saves/configs go to a
    # separate session user directory, never onto these source files.
    extensions={'.pak','.555','.sg2','.emp','.map','.mapx','.smk','.wav','.mp3','.ogg','.eng','.txt','.bin'}
    for item in source.rglob('*'):
        if not item.is_file() or item.is_symlink() or item.suffix.lower() not in extensions:continue
        rel=item.relative_to(source)
        if any(x.lower() in {'assets','saves','savegames','config','configs','screenshots'} for x in rel.parts[:-1]):continue
        dest=target/rel;dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.exists():continue
        try:os.link(item,dest)
        except OSError:shutil.copy2(item,dest)
    if missing:
        with zipfile.ZipFile(archive) as z:
            members={i.filename.lower():i for i in z.infolist()}
            for name in missing:
                info=members.get(name)
                if not info or info.is_dir() or info.file_size>8*1024*1024:raise ValueError('편집기 자료 목록이 올바르지 않습니다.')
                # Fixed data-only allowlist: never extract or execute c3_mapper.exe.
                (target/name).write_bytes(z.read(info))
    if not all((target/n).is_file() for n in EDITOR_FILES):raise ValueError('편집기 그래픽 자료가 없습니다.')
    write_json(target/'prepared.json',dict(private_game_data=True,source=str(source),editor_source=ZIP_URL,editor_zip_sha256=ZIP_SHA,extracted=missing))
    return target

def run_roundtrip(source,target,data):
    source,target,data=Path(source),Path(target),Path(data);target.mkdir(parents=True,exist_ok=True)
    user=target/'user';user.mkdir(exist_ok=True)
    env=os.environ.copy();env['AUGUSTUS_KO_USER_PATH']=user.as_posix()+'/'
    with (target/'engine.log').open('wb') as log:
        result=subprocess.run([str(HERE/'engine-city-test.exe'),str(data),'native-editor-roundtrip',str(source),str(target),'0','0','0'],cwd=HERE,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=90)
    log=(target/'engine.log').read_text(errors='replace')
    # Proof that the worker ran silent: either line the engine prints for it (same pair as city_client.Engine.run; the
    # engine now prints the second one, and this check still knew only the first).
    silent=any(marker in log for marker in ('Using default audio driver: dummy','Audio output disabled: no playback device opened'))
    if result.returncode or not silent or 'ERROR:' in log:
        raise RuntimeError('정식 지도 편집기 변환에 실패했습니다. 로그: '+str(target/'engine.log'))

def preview(project,slot_id):
    project=Path(project).resolve();manifest=load(project)
    # Edit terrain before procedural starting buildings are added. Otherwise
    # exporting them into mapx would seed a second town on the next start.
    for item in manifest['slots']:item.pop('starting_setup',None)
    slot=next((s for s in manifest['slots'] if s['id']==slot_id),None)
    if slot is None:raise ValueError('선택한 도시가 시나리오에 없습니다.')
    key=digest(json.dumps(manifest,sort_keys=True).encode()+digest((HERE/'engine-city-test.exe').read_bytes()).encode())[:24]
    root=CACHE/'native-preview'/key/slot_id
    if not (root/'native/terrain.json').is_file():
        write_layout(manifest,root)
        Engine().run('start-'+slot_id,root,root/'native')
    return dict(metadata=str(root/'native/terrain.json'),source=str(root/'native'),slot=slot_id,project=str(project))

def prepare(project,slot_id):
    result=preview(project,slot_id);session=new_session()
    shutil.copy2(Path(project).resolve(),session/'project.json')
    Engine().run('native-map-export',result['source'],session/'export')
    data=editor_data()
    run_roundtrip(session/'export',session/'converted',data)
    # Editor save browser opens this session's scenarios directory. Keep the
    # generated file and snapshot separately so cancellation never loses input.
    maps=session/'user/scenarios';maps.mkdir(parents=True)
    editable=maps/'edit.mapx';shutil.copy2(session/'converted/terrain.mapx',editable)
    state=dict(schema=1,slot=slot_id,project=str(session/'project.json'),source_project=str(Path(project).resolve()),map=str(editable),data=str(data),user=str(session/'user'),original_sha256=digest(editable.read_bytes()))
    write_json(session/'session.json',state)
    return dict(session=str(session),map=str(editable),metadata=str(session/'converted/terrain.json'),save_directory=str(maps),editor_ready=True,missing=[],original_preserved=True)

def session_state(value):
    session=Path(value).resolve()
    if not session.is_relative_to((CACHE/'native-editor').resolve()):raise ValueError('이 편집기에서 준비한 작업 폴더가 아닙니다.')
    state=read_json(session/'session.json')
    if state.get('schema')!=1:raise ValueError('편집 작업 정보가 올바르지 않습니다.')
    return session,state

def launch(value):
    session,state=session_state(value)
    exe=next((p for p in [HERE/'augustus-mp-ui.exe',HERE/'augustus.exe'] if p.is_file()),None)
    if exe is None:raise ValueError('아우구스투스 편집기 실행 파일이 없습니다.')
    if not Path(state['map']).is_relative_to(session):raise ValueError('편집 지도 경로가 올바르지 않습니다.')
    env=os.environ.copy();env['AUGUSTUS_KO_USER_PATH']=Path(state['user']).as_posix()+'/'
    for key in list(env):
        if key.startswith('AUGUSTUS_MP_'):env.pop(key)
    # Explicit user action: visible native editor. This is not a test instance.
    log=(session/'editor.log').open('ab')
    try:p=subprocess.Popen([str(exe),'--windowed','--editor-map',state['map'],state['data']],cwd=HERE,env=env,stdout=log,stderr=subprocess.STDOUT)
    finally:log.close()
    state['pid']=p.pid;write_json(session/'session.json',state)
    return dict(pid=p.pid,session=str(session),map=state['map'],save_directory=str(session/'user/scenarios'))

def inspect_map(map_path,target):
    """Check an Augustus .mapx with the engine (load, export, reload, compare) and return it as a terrain asset.
    Only the map is read: the engine start later drops the file's campaign schedule (creator_reset_mission)."""
    map_path=Path(map_path).resolve();target=Path(target)
    if map_path.suffix.lower()!='.mapx' or not map_path.is_file():raise ValueError('정식 편집기에서 저장한 .mapx 파일을 선택하세요.')
    if not 16<=map_path.stat().st_size<=8*1024*1024:raise ValueError('지도는 최대 8 MiB까지 가져올 수 있습니다.')
    raw=map_path.read_bytes()
    if raw[:8]!=b'VERSION\0':raise ValueError('올바른 Augustus 지도 형식이 아닙니다.')
    target.mkdir(parents=True);(target/'terrain.mapx').write_bytes(raw)
    Engine().run('native-map-inspect',target,target/'native')
    Engine().run('inspect',target/'native',target/'reload')
    first=read_json(target/'native/terrain.json');second=read_json(target/'reload/terrain.json')
    for name in ('terrain_flags','elevation','entry','exit','river_entry','river_exit','fishing_points','herd_points','invasion_points','climate'):
        if first[name]!=second[name]:raise ValueError('저장 재검사에서 지형 정보가 달라졌습니다: '+name)
    return dict(format='augustus-mapx',sha256=digest(raw),data=base64.b64encode(raw).decode()),first

SAVE_LIMIT=64*1024*1024
def inspect_save(save_path,target):
    """A saved city (.svx) -> its terrain only, as a checked mapx asset (same form as inspect_map).
    The engine loads the save with the native loader, removes what the city built (buildings, roads, walls,
    aqueducts, gardens, rubble), keeps the map (terrain, height, water, trees, rocks, meadow, native villages,
    entry/exit, river, fishing/herd/invasion points, climate; trees cut for building grow back), writes a mapx,
    and that mapx then goes through the usual load/export/reload comparison."""
    save_path=Path(save_path).resolve();target=Path(target)
    if save_path.suffix.lower()!='.svx' or not save_path.is_file():raise ValueError('Augustus 저장 파일(.svx)을 선택하세요.')
    if not 16<=save_path.stat().st_size<=SAVE_LIMIT:raise ValueError('저장 파일은 최대 64 MiB까지 가져올 수 있습니다.')
    source=target/'save';source.mkdir(parents=True);shutil.copy2(save_path,source/'city.svx')
    try:Engine().run('native-save-terrain',source,target/'converted')
    except RuntimeError as error:raise ValueError('저장 파일에서 지형을 꺼내지 못했습니다. 이 버전의 게임에서 열리는 저장 파일인지 확인하세요. ('+str(error)+')')
    report=read_json(target/'converted/save-terrain.json')
    asset,first=inspect_map(target/'converted/terrain.mapx',target/'map')
    write_json(target/'save-source.json',dict(format='augustus-svx',sha256=digest(save_path.read_bytes()),**report))
    return asset,first      # the stored asset is the converted mapx: same form and checks as any imported map

def inspect_terrain_file(path,target):
    """.mapx (map editor) or .svx (saved city): both end as the same checked mapx asset."""
    return inspect_save(path,target) if Path(path).suffix.lower()=='.svx' else inspect_map(path,target)

def import_map(value,map_path):
    session,state=session_state(value);map_path=Path(map_path).resolve()
    target=session/('import-'+uuid.uuid4().hex)
    asset,first=inspect_terrain_file(map_path,target)
    metadata=target/('map/native' if map_path.suffix.lower()=='.svx' else 'native')/'terrain.json'
    result=dict(terrain_asset=asset,metadata=str(metadata),save_reload=True,source=str(map_path),slot=state['slot'])
    if (target/'save-source.json').is_file():result['save_terrain']=read_json(target/'save-source.json')
    write_json(target/'result.json',result);return result

def inspect_file(map_path):
    """A map (.mapx) or a saved city (.svx) checked on its own, for the editor's map list of a city (user 2026-11-15:
    several versions of one city's map, one chosen). Returns the asset and the preview metadata; nothing is kept here."""
    map_path=Path(map_path).resolve();target=CACHE/'map-library'/uuid.uuid4().hex
    asset,first=inspect_terrain_file(map_path,target)
    metadata=target/('map/native' if map_path.suffix.lower()=='.svx' else 'native')/'terrain.json'
    return dict(terrain_asset=asset,metadata=str(metadata),source=str(map_path),width=first.get('width'),height=first.get('height'))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['preview','prepare','launch','import','inspect'])
    p.add_argument('--project',type=Path);p.add_argument('--slot');p.add_argument('--session',type=Path);p.add_argument('--map',type=Path)
    a=p.parse_args()
    try:
        if a.command in ('preview','prepare'):
            if not a.project or not a.slot:raise ValueError('시나리오와 도시를 선택하세요.')
            result=(preview if a.command=='preview' else prepare)(a.project,a.slot)
        elif a.command=='launch':result=launch(a.session)
        elif a.command=='inspect':
            if not a.map:raise ValueError('지도 파일을 선택하세요.')
            result=inspect_file(a.map)
        else:result=import_map(a.session,a.map)
    except (ValueError,OSError,RuntimeError,subprocess.SubprocessError,KeyError,TypeError,zipfile.BadZipFile) as error:
        result=dict(ok=False,error=str(error))
    print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
