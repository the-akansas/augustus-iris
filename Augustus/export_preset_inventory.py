"""Private, reproducible inventory of installed Caesar III terrain and empire presets."""
import hashlib,json,sys,uuid,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from city_client import HERE,Engine,game_data
BUILTINS=['Caesarea','Carthago','Corinthus','Cyrene','Hierosolyma','Lindum','Londinium','Lugdunum','Mediolanum','Tarraco','Toletum','Valentia']
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def enrich_population(catalog):
    """Population is physical preset content, not an inherited objective."""
    changed=False
    for t in catalog['terrains']:
        if not t.get('available') or 'original_population' in t:continue
        audit=Path(t['metadata']).with_name('rules-audit.json')
        if audit.is_file():
            t['original_population']=json.loads(audit.read_text(encoding='utf8'))['population'];changed=True
    return changed
def prepare():
    from creator_data import environment
    os.environ['AUGUSTUS_C3_DATA']=environment(HERE)['AUGUSTUS_C3_DATA']
    data=game_data();sources={}
    for name in ['mission1.pak','c3.emp','c32.emp',*[x+'.map' for x in BUILTINS]]:
        p=data/name;sources[name]=sha(p) if p.exists() else None
    key=hashlib.sha256(json.dumps(dict(api=2,data=str(data.resolve()),sources=sources,worker=sha(HERE/'engine-city-test.exe')),sort_keys=True).encode()).hexdigest()
    cache=HERE/'creator-cache';cache.mkdir(exist_ok=True);marker=cache/'presets-current.json'
    if marker.exists():
        try:
            old=json.loads(marker.read_text(encoding='utf8'));catalog=json.loads(Path(old['metadata']).read_text(encoding='utf8'))
            if old['key']==key and catalog.get('empires') and any(t.get('available') for t in catalog['terrains']) and not any(t.get('error') for t in catalog['terrains']) and all(Path(t['metadata']).is_file() and Path(t['empire_image']).is_file() for t in catalog['terrains'] if t.get('available')):
                if enrich_population(catalog):Path(old['metadata']).write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding='utf8')
                return old
        except (ValueError,OSError,KeyError):pass
    root=cache/('presets-'+uuid.uuid4().hex);root.mkdir();terrains=[];empires={};union={};names={x['name_id']:x['name'] for x in json.loads((HERE/'creator-city-catalog.json').read_text(encoding='utf8'))}
    for ident in [*range(20),*range(100,112)]:
        filename='mission1.pak' if ident<20 else BUILTINS[ident-100]+'.map'
        if not sources.get(filename):
            terrains.append(dict(id=ident,title=BUILTINS[ident-100] if ident>=100 else str(ident),available=False,source_file=filename));continue
        target=root/str(ident)
        try:Engine().run('inventory-'+str(ident),root,target)
        except RuntimeError as error:
            terrains.append(dict(id=ident,title=filename,available=False,source_file=filename,error=str(error)));continue
        info=json.loads((target/'preset.json').read_text(encoding='utf8'));native=json.loads((target/'scenario.json').read_text(encoding='utf8'));terrain=json.loads((target/'terrain.json').read_text(encoding='utf8'))
        info.update(available=True,metadata=str(target/'terrain.json'),empire_image=str(target/'empire.bmp'),terrain_sha256=hashlib.sha256(json.dumps(terrain['terrain_flags'],separators=(',',':')).encode()).hexdigest())
        cities=[]
        for c in native['cities']:
            n=c['name_id']
            if n not in names:continue
            policy=dict(name_id=n,name=names[n],role='npc',enabled=True,x=c['x']+16,y=c['y']+16,sea=c['sea'],cost=c['cost'],sells={str(r):c['sell_limits'][r] for r in range(1,22) if c['sells'][r] and c['sell_limits'][r]>0},buys={str(r):c['buy_limits'][r] for r in range(1,22) if c['buys'][r] and c['buy_limits'][r]>0},original_type=c['type'])
            cities.append(policy)
            candidate=dict(policy,provenance=dict(terrain_id=ident,empire_template=info['empire_template'],source_file=info['empire_source']))
            if n not in union or info['empire_template']==25:union[n]=candidate
        info['cities']=cities;terrains.append(info)
        empire_id=info['empire_template']
        if empire_id not in empires or len(cities)>len(empires[empire_id]['cities']):
            empires[empire_id]=dict(id=empire_id,title=info['title']+' 제국지도',width=2000,height=1000,cities=cities,image=info['empire_image'],terrain_id=ident,source_file=info['empire_source'],raw_id=info['empire_raw_id'])
    catalog=dict(schema=1,source_hashes=sources,terrains=terrains,empires=list(empires.values()),neutral_union=[union[n] for n in sorted(union)])
    enrich_population(catalog)
    path=root/'catalog.json';path.write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding='utf8')
    result=dict(key=key,metadata=str(path),terrain_count=sum(t.get('available',False) for t in terrains),empire_count=len(empires),neutral_count=len(union))
    temporary=marker.with_suffix('.'+uuid.uuid4().hex+'.tmp');temporary.write_text(json.dumps(result),encoding='utf8');temporary.replace(marker)
    return result
if __name__=='__main__':print(json.dumps(prepare(),ensure_ascii=False))
