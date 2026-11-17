"""Verified preset metadata, local-only preview caches and portable authoring projects."""
import argparse, copy, hashlib, json, sys
from collections import Counter
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))

def catalog():
    return json.loads((HERE/'preset-catalog.json').read_text(encoding='utf8'))

def write_catalog(raw_path):
    raw=json.loads(Path(raw_path).read_text(encoding='utf8'))
    excluded={'metadata','empire_image','image','error'}
    def clean(row):return {k:v for k,v in row.items() if k not in excluded}
    result=dict(schema=1,source_hashes=raw['source_hashes'],terrain=[clean(x) for x in raw['terrains']],empire=[clean(x) for x in raw['empires']],neutral=raw['neutral_union'])
    (HERE/'preset-catalog.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    return result

def installed_catalog():
    from city_client import game_data
    result=catalog();directory=game_data();valid={}
    for name,expected in result['source_hashes'].items():
        p=directory/name
        valid[name]=p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==expected
    for row in result['terrain']:
        row['available']=valid.get(row['source_file'],False) and valid.get(row.get('empire_source','c3.emp'),False)
    return result

def missing_maps(project):
    """Seats this PC cannot start (2026-11-15: a received scenario must play): the original map file a seat is started
    from is missing here or another version. [(slot id, map title, file)]. A seat carrying its own map is started from
    its base mission all the same (engine_main.c loads the template first)."""
    rows={t['id']:t for t in installed_catalog()['terrain']}
    return [(s['id'],rows[s['campaign_scenario']]['title'],rows[s['campaign_scenario']]['source_file']) for s in project.get('slots',[])
            if s.get('campaign_scenario') in rows and not rows[s['campaign_scenario']]['available']]

def missing_maps_text(missing):
    return '이 PC의 시저 3 폴더에 이 시나리오가 쓰는 원본 지도 파일이 없습니다: '+', '.join(f'{slot} - {title} ({file})' for slot,title,file in missing)+'. 시저 3 설치 폴더를 확인하거나, 만든 사람에게 이 도시들의 지형을 지도 파일로 넣어 달라고 하세요(제작기에서 가져온 지도는 시나리오 파일에 함께 들어갑니다).'

def local_inventory():
    from export_preset_inventory import prepare
    return json.loads(Path(prepare()['metadata']).read_text(encoding='utf8'))

def empire_preset(template):
    data=catalog();selected=next((x for x in data['empire'] if x['id']==template),None)
    if selected is None:raise ValueError('알 수 없는 제국지도 프리셋입니다.')
    primary={x['name_id']:x for x in selected['cities']};titles={x['id']:x['title'] for x in data['terrain']}
    cities=[]
    for fallback in data['neutral']:
        original=primary.get(fallback['name_id']);row=copy.deepcopy(original or fallback)
        row['enabled']=original is not None;row['role']='npc'
        source=selected['terrain_id'] if original else fallback['provenance']['terrain_id']
        row['source_title']=titles.get(source,str(source))
        row['placement_note']='선택한 제국지도의 원래 위치와 교역 조건' if original else '다른 미션에서 가져온 위치와 교역 조건 · 기본 꺼짐'
        cities.append(row)
    return dict(template=template,title=selected['title'],width=selected['width'],height=selected['height'],cities=cities)

def city_fields(row):
    return {k:copy.deepcopy(row[k]) for k in ('name_id','role','enabled','x','y','sea','cost','sells','buys')}

def merged_empire():
    data=catalog();cities=[]
    for neutral in data['neutral']:
        ident=neutral['name_id'];variants=[];placements=[];sources=[]
        for terrain in data['terrain']:
            for row in terrain.get('cities',[]):
                if row['name_id']!=ident:continue
                placements.append((row['x'],row['y']))
                sources.append(dict(terrain_id=terrain['id'],title=terrain['title'],empire=terrain['empire_template'],x=row['x'],y=row['y']))
                # OURS/future/decorative cities have no active neutral trading policy.
                if row.get('original_type') not in (2,3) and not (row['sells'] or row['buys']):continue
                policy={k:copy.deepcopy(row[k]) for k in ('sea','cost','sells','buys')}
                if not(policy['sells'] or policy['buys']):continue
                key=hashlib.sha256(json.dumps(policy,sort_keys=True).encode()).hexdigest()[:16]
                found=next((v for v in variants if v['id']==key),None)
                title=terrain['title']+(' (자유 건설)' if terrain['id']>=100 else ' (캠페인)')
                if found:found['source_titles'].append(title)
                else:variants.append(dict(policy,id=key,title=title,source_titles=[title]))
        empty=dict(id='none',title='없음',source_titles=[],sea=0,cost=0,sells={},buys={})
        variants.append(empty)
        # Select one real observed location, using the most common coordinate pair.
        # This merges city identity without inventing offsets when missions disagree.
        x,y=Counter(placements).most_common(1)[0][0]
        terrain_ids=[t['id'] for t in data['terrain'] if t.get('name_id')==ident]
        row=city_fields(neutral);chosen=variants[0]
        row.update({k:copy.deepcopy(chosen[k]) for k in ('sea','cost','sells','buys')})
        row.update(x=x,y=y,enabled=False,role='npc',playable=bool(terrain_ids),terrain_ids=terrain_ids,
                   trade_presets=variants,default_trade_id=chosen['id'],source_title='여러 원본 지도의 통합 위치',
                   placement_note='원본에서 가장 자주 쓰인 좌표',placement_sources=sources)
        row['name']=neutral['name'];cities.append(row)
    return dict(template=25,title='통합 제국지도',width=2000,height=1000,cities=cities)

def default_project(count=4):
    if type(count) is not int or not 2<=count<=8:raise ValueError('제작 도시 수는 2~8개입니다.')
    data=catalog();terrain={x['id']:x for x in data['terrain']}
    allowed=[x['id'] for x in json.loads((HERE/'building-catalog.json').read_text(encoding='utf8'))]
    cities=[city_fields(c) for c in merged_empire()['cities']]
    ids=[2,1,4,10,6,7,3,11];slots=[]
    for i,n in enumerate(ids[:count]):
        candidates=[t for t in data['terrain'] if t.get('name_id')==n and t['id']>=2]
        chosen=next((t for t in candidates if t['id']<20),candidates[0] if candidates else terrain[2+i%4])
        slots.append(dict(id='player'+str(i+1),name_id=n,campaign_scenario=chosen['id'],allowed_buildings=list(allowed),terrain_edits=[],governance=dict(rank=0,salary_rank=-1,savings=0,favor=50,policy='fixed')))
        city=next(c for c in cities if c['name_id']==n);city.update(role='player',enabled=True,sea=0,cost=0,sells={},buys={})
    result=dict(schema=4,id='unified-sandbox',title='통합 제국 자유 건설',revision=1,rules=dict(mode='free-build',player_transport='land',starting_funds=10000),slots=slots,empire=dict(template=25,cities=cities))
    from scenario_project import validate
    return validate(result)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--empire',type=int);p.add_argument('--default',type=int);p.add_argument('--build-catalog',type=Path);p.add_argument('--merged',action='store_true');a=p.parse_args()
    try:
        result=write_catalog(a.build_catalog) if a.build_catalog else merged_empire() if a.merged else empire_preset(a.empire) if a.empire is not None else default_project(a.default) if a.default is not None else installed_catalog()
        print(json.dumps(result,ensure_ascii=False))
    except (ValueError,OSError,RuntimeError) as e:p.exit(1,str(e)+'\n')
