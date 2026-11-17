"""Decode a local C3 city template to an editable grid; no assets are redistributed."""
import argparse,hashlib,json,uuid,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from city_client import HERE,Engine,game_data
from scenario_project import load,layout,write_layout
from scenario_pair import load_pair

def prepare(template):
    from creator_presets import local_inventory
    inventory=local_inventory()
    row=next((r for r in inventory['terrains'] if r['id']==template and r.get('available')),None)
    if row is None:raise ValueError('이 지형의 원본 파일을 시저 3 폴더에서 찾지 못했습니다.')
    path=Path(row['metadata']);data=json.loads(path.read_text(encoding='utf8'))
    if len(data['tiles'])!=data['width']*data['height']:raise ValueError('지형 정보의 크기가 올바르지 않습니다.')
    return dict(template=template,metadata=str(path),metadata_sha256=hashlib.sha256(path.read_bytes()).hexdigest())

def validate_project(project):
    from scenario_pair import verify_city
    manifest=load(project);preset,binding=load_pair(game_data(),manifest,authoring=True)
    root=HERE/'creator-cache'/('validation-'+uuid.uuid4().hex);root.mkdir(parents=True)
    write_layout(manifest,root)
    result=dict(valid=True,errors=[],cities=[],output=str(root),scenario_sha256=binding['sha256'])
    for slot in manifest['slots']:
        city=slot['id'];target=root/city
        try:
            Engine().run('start-'+city,root,target);info=verify_city(target,city,preset)
            terrain=json.loads((target/'terrain.json').read_text(encoding='utf8'));w=terrain['width']
            for e in slot.get('terrain_edits',[]):
                if terrain['tiles'][e['y']*w+e['x']]!=e['kind']:raise ValueError('칠한 지형이 게임에 반영되지 않았습니다.')
            Engine().run('inspect',target,target/'reload');verify_city(target/'reload',city,preset)
            reloaded=json.loads((target/'reload/terrain.json').read_text(encoding='utf8'))
            if reloaded['terrain_flags']!=terrain['terrain_flags']:raise ValueError('저장 후 지형 정보가 달라졌습니다.')
            # Salary as the engine applied it at this start (base, amount per rank); it must survive the save as well.
            def audit(folder):
                try:return json.loads((folder/'governance-audit.json').read_text(encoding='utf8'))
                except (OSError,ValueError):return None
            governance,again=audit(target),audit(target/'reload')
            keys=('caesar_salary','salary_rank','salary_amount','salary_for_rank')
            if governance and again and any(governance.get(k)!=again.get(k) for k in keys):raise ValueError('저장 후 봉급 정보가 달라졌습니다.')
            # Keep the engine's answers for this exact map so the export gate can require them later.
            import scenario_check;scenario_check.store_evidence(slot,terrain,governance)
            result['cities'].append(dict(id=city,width=w,height=terrain['height'],painted_tiles=len(slot.get('terrain_edits',[])),allowed_buildings=len(info['allowed_buildings']),save_reload=True))
        except (ValueError,RuntimeError,OSError) as error:
            log=(target/'engine.log').read_text(errors='replace') if (target/'engine.log').exists() else ''
            if 'protected or invalid tile:' in log:
                detail=next(line.split('tile:',1)[1].strip() for line in log.splitlines() if 'protected or invalid tile:' in line)
                reason='보호된 지형 또는 지도 밖의 칸은 변경할 수 없습니다: '+detail
            elif 'existing entry/exit route was disconnected' in log:
                reason='지형 변경으로 기존 육로 또는 하천의 입구와 출구가 끊어집니다.'
            else:reason=str(error)
            result['valid']=False;result['errors'].append(city+': '+reason)
    (root/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('template',type=int,nargs='?');parser.add_argument('--validate',type=Path);args=parser.parse_args()
    try:
        if args.validate:result=validate_project(args.validate)
        elif args.template is not None:result=prepare(args.template)
        else:parser.error('지형 번호 또는 --validate 시나리오 경로가 필요합니다.')
    except (ValueError,RuntimeError,OSError) as error:result=dict(valid=False,errors=[str(error)])
    print(json.dumps(result,ensure_ascii=False))
