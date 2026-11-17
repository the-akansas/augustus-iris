"""Pinned campaign pair; data comes from each owner's C3 installation, not distribution."""
import json
from pathlib import Path
from coordinator import sha
from scenario_project import load, digest as project_digest, require_runtime, require_layout, DEFAULT, validate

PRESET=Path(__file__).with_name('capua-tarentum.json')

def load_pair(data_directory, project=DEFAULT, authoring=False):
    data=json.loads(PRESET.read_text(encoding='utf-8'))
    manifest=validate(project) if isinstance(project,dict) else load(project)
    (require_layout if authoring else require_runtime)(manifest)
    data['creator_manifest_sha256']=project_digest(manifest)
    if manifest['schema']>=2:
        data.update(schema=manifest['schema'],id=manifest['id'],revision=manifest['revision'],players=len(manifest['slots']))
        data['cities']={s['id']:dict(campaign_scenario=s['campaign_scenario'],name_id=s['name_id'],peer_name_ids=[t['name_id'] for t in manifest['slots'] if t['id']!=s['id']],allowed_buildings=s['allowed_buildings']) for s in manifest['slots']}
        data['creator_manifest']=manifest
        if 'start_year' in manifest['rules']:data['start_year']=manifest['rules']['start_year']   # the author's first year (2026-11-17): the engine's cities are checked against it

    if manifest['schema']>=3:
        catalog=json.loads(PRESET.with_name('preset-catalog.json').read_text(encoding='utf-8'))
        terrain={x['id']:x for x in catalog['terrain']}
        empire=next(x for x in catalog['empire'] if x['id']==manifest['empire']['template'])
        files={terrain[s['campaign_scenario']]['source_file'] for s in manifest['slots']}|{empire['source_file']}
        files|={terrain[s['campaign_scenario']]['empire_source'] for s in manifest['slots']}
        for name in files:
            # Only catalog-owned basenames can become dependencies. Never copy these files into exports.
            if Path(name).name!=name or '/' in name or '\\' in name:raise ValueError('invalid preset source')
            path=Path(data_directory)/name
            if not path.is_file():raise ValueError('시저 3 설치 폴더에 프리셋 원본이 없습니다: '+name)
            expected=catalog['source_hashes'].get(name)
            if not expected:raise ValueError('검증된 프리셋 원본 해시가 없습니다: '+name)
            data['dependencies'][name]=expected

    for name,expected in data['dependencies'].items():
        if sha((Path(data_directory)/name).read_bytes())!=expected:
            raise ValueError('campaign dependency mismatch: '+name)
    digest=sha(json.dumps(data,sort_keys=True,separators=(',',':')).encode())
    binding=dict(sha256=digest,cities=sorted(data['cities']),**({'transport':'sea'} if manifest['rules']['player_transport']=='sea' else {}))
    if manifest['schema']>=2:
        names={c['name_id']:c['name'] for c in json.loads(PRESET.with_name('creator-city-catalog.json').read_text(encoding='utf-8-sig'))}
        binding['city_names']={s['id']:names.get(s['name_id'],str(s['name_id'])) for s in manifest['slots']}
        binding['city_name_ids']={s['id']:s['name_id'] for s in manifest['slots']}
    if manifest['rules']['mode']=='cooperative':binding['objectives']={k:v for k,v in manifest['rules']['objectives'].items() if k!='by_players'}   # the per-player-count table is applied when the roster is frozen (room_roster)
    if manifest['rules']['mode']=='imperial-progress':binding['progress']=manifest['rules']['progress']
    if manifest['rules']['mode']=='deadline-race':binding['objectives']=dict(population_total=0,per_city={},race=manifest['rules']['race'])   # judged by objectives.py at the deadline
    if manifest['schema']==5:binding['throne']=dict(rules=manifest['rules']['throne'],rome=manifest['empire']['rome'])
    if 'player_trade' in manifest['rules']:
        # Resolved once here; the room server only reads this list. Absent = every pair may trade (older bindings unchanged).
        import trade_policy
        binding['player_trade_blocked']=trade_policy.blocked_pairs(manifest['rules'],[s['id'] for s in manifest['slots']])
    return data,binding

def verify_city(directory,city,preset):
    info=json.loads((Path(directory)/'scenario.json').read_text())
    expected=preset['cities'][city]
    ours=[c for c in info['cities'] if c['type']==1]
    peer_names=expected.get('peer_name_ids',[expected.get('peer_name_id')])
    peers=[c for c in info['cities'] if c['name_id'] in peer_names and c['type']==7]
    if info['difficulty']!=preset['difficulty'] or info['year']!=preset['start_year'] or len(ours)!=1 or ours[0]['name_id']!=expected['name_id'] or len(peers)!=len(peer_names):
        raise ValueError('wrong campaign city or peer')
    if preset.get('schema',1)>=2:
        # Validate the saved native state, not merely the authored metadata.
        actual={c['name_id']:c for c in info['cities']}
        for c in preset['creator_manifest']['empire']['cities']:
            if not c.get('enabled',True):
                if c['name_id'] in actual:raise ValueError('disabled neutral city present')
                continue
            native=actual.get(c['name_id'])
            if not native or [native['x']+16,native['y']+16]!=[c['x'],c['y']]:raise ValueError('empire position mismatch')
            if c['role']=='npc':
                permitted='trade_players' not in c or city in c['trade_players']
                if native['type']!=(6 if c.get('reserved') else 2 if permitted else 4):raise ValueError('neutral trade access mismatch')
                if not permitted and (any(native['sells']) or any(native['buys'])):raise ValueError('restricted city has trade resources')
        if set(info['allowed_buildings'])!=set(expected['allowed_buildings']):raise ValueError('building availability mismatch')
        manifest=preset['creator_manifest']
        if manifest['schema']>=3 and 'initial_funds' in info:
            slot=next(s for s in manifest['slots'] if s['id']==city)
            if info['initial_funds']!=slot.get('starting_funds',manifest['rules']['starting_funds']):raise ValueError('starting funds mismatch')
    return info


def compatible_binding(actual,current):
    if actual==current:return True
    preset=json.loads(PRESET.read_text(encoding='utf-8'))
    r4=dict(sha256=sha(json.dumps(preset,sort_keys=True,separators=(',',':')).encode()),cities=sorted(preset['cities']))
    preset['creator_manifest_sha256']='e76b6ecf8f6f5ea8222dd6266a7749edafa781d3313a17b45ff9f8bdb70dbbd0'
    expected=dict(sha256=sha(json.dumps(preset,sort_keys=True,separators=(',',':')).encode()),cities=sorted(preset['cities']))
    if current!=expected:return False
    legacy=json.loads(PRESET.with_name('capua-tarentum-legacy-r3.json').read_text(encoding='utf-8'))
    digest=sha(json.dumps(legacy,sort_keys=True,separators=(',',':')).encode())
    return actual==r4 or actual==dict(sha256=digest,cities=sorted(legacy['cities']))

