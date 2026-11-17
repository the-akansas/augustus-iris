"""Expand only a new restore lobby. Never change the source database or SAVs."""
import copy,json,threading,uuid
from pathlib import Path
from scenario_project import load,write_layout,digest
from room_roster import effective_project

def original_project(folder,current,_seen=None):
    folder=Path(folder).resolve();seen=set() if _seen is None else _seen
    if folder in seen or len(seen)>=16:return None
    seen.add(folder)
    for name in ('scenario-original.json','scenario-before-neutral.json'):
        path=Path(folder)/name
        if not path.exists():continue
        original=load(path)
        if original['schema']<2:return None
        active=[s['id'] for s in current['slots']]
        if not set(active)<={s['id'] for s in original['slots']}:raise ValueError('원본 시나리오의 도시 정보가 다릅니다.')
        expected,_=effective_project(original,active)
        if digest(expected)!=digest(current):
            legacy,_=effective_project(original,active,legacy_neutral=True)
            if digest(legacy)!=digest(current):raise ValueError('원본 시나리오와 저장된 시나리오가 다릅니다.')
        return original
    # network15 did not copy the original roster when a solo save was restored.
    # Recover it through the existing read-only restoration provenance when present.
    provenance=folder/'restored-from.json'
    if provenance.is_file():
        data=json.loads(provenance.read_text(encoding='utf-8'))
        source=data.get('source')
        if isinstance(source,str) and Path(source).is_absolute() and Path(source).is_file():
            return original_project(Path(source).parent,current,seen)
    return None

def begin(room,db,participants):
    context=room.restore_expansion;required=set(context['restored']['parts'])
    if getattr(room,'roster_job',None):return
    effective,removed=effective_project(context['original'],set(participants)|required)
    root=Path(room.coordinator.path).parent
    cache=Path(__file__).resolve().parent/'restore-cache';cache.mkdir(exist_ok=True)
    job=dict(participants=list(participants),project=effective,removed=removed,result=None,error=None,stage=str(cache/uuid.uuid4().hex),expansion=True)
    room.roster_job=job
    room.system_chat(db,'저장된 도시는 유지하고 새 참가자의 도시를 준비합니다. 잠시 기다려 주세요.')
    def build():
        try:
            from scenario_pair import load_pair,verify_city
            from city_client import Engine,game_data
            stage=Path(job['stage']);stage.mkdir();preset,binding=load_pair(game_data(),effective);parts={}
            added=set(participants)-required
            for city in binding['cities']:
                out=stage/city
                if city in required:
                    sav,rec=context['restored']['parts'][city]
                    if not added:parts[city]=(sav,rec);continue
                    source=stage/(city+'-source');source.mkdir();write_layout(effective,source)
                    (source/'city.sav').write_bytes(sav);(source/'receipt.bin').write_bytes(rec)
                    own=next(s['name_id'] for s in effective['slots'] if s['id']==city)
                    parts[city]=Engine().run('expand-roster',source,out,qty=own)
                else:
                    source=stage/(city+'-start');source.mkdir();write_layout(effective,source)
                    Engine().run('start-'+city,source,source/'initial')
                    parts[city]=Engine().run('align-roster-time',source/'initial',out,seq=context['restored']['ticks'])
                verify_city(out,city,preset)
            job['result']=(binding,parts)
        except Exception as error:
            job['error']=str(error);(root/'restore-expansion-error.txt').write_text(str(error),encoding='utf8')
    thread=threading.Thread(target=build,daemon=True);job['thread']=thread;thread.start()

def restore_goals(room,db,binding):
    import objectives
    saved=room.restore_expansion['restored'];old=saved.get('objectives')
    if old and old['rules']==binding.get('objectives') and set(saved['parts'])==set(binding['cities']):
        objectives.restore(db,old,binding,saved['ticks'])
    # New participants change the population/treasury aggregate and city goals.
    # Keep city progress; evaluate the expanded mission again at the saved tick.
    else:objectives.configure(db,binding,room.origin)
