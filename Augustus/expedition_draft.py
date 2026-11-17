"""Frozen test snapshots only: no live publication, RPC or ledger phase change.
A dedicated vacancy token is persisted; paired atomic publication is still required.
"""
from pathlib import Path
import copy,json,uuid
from expedition_adapter import select_army,sha
from expedition_state import integer
from city_client import Engine


def packet(row):
    keys=('formation_id','fort_id','unit_type','morale','trained','months_from_home',
          'months_low_morale','months_very_low_morale','food_modifier')
    values=[row[k] for k in keys]+[len(row['soldiers'])]
    # Stable internal vacancy identity; not authentication or a global operation ID.
    token=int(sha(json.dumps({k:row[k] for k in ('formation_id','fort_id','unit_type')},sort_keys=True).encode())[:8],16) or 1
    token=row.get('vacancy_token',token)
    lines=['EX2 '+str(token)+' '+' '.join(map(str,values))]
    for s in row['soldiers']:
        lines.append(' '.join(str(s[k]) for k in ('local_id','generation','damage','x','y','name','direction')))
    return '\n'.join(lines)+'\n'


def transform(sav,receipt,row,scratch,mode):
    root=Path(scratch)/('army-draft-'+uuid.uuid4().hex);source=root/'input';source.mkdir(parents=True)
    (source/'city.sav').write_bytes(sav);(source/'receipt.bin').write_bytes(receipt)
    (source/'expedition.txt').write_text(packet(row),encoding='ascii')
    result,rec=Engine().run(mode,source,root/'output')
    return dict(save=result,receipt=rec,hash=sha(result),root=str(root),
                report=json.loads((root/'output/legions.json').read_text()))


def prepare_departure(inspection,selection,scratch):
    row=selection['native'];m=selection['manifest']
    actual=select_army(inspection,row['formation_id'],m['owner'],m['army_id'])
    if actual!=selection:raise ValueError('selection changed')
    row=copy.deepcopy(row);row['vacancy_token']=(uuid.uuid4().int & 0xffffffff) or 1
    draft=transform(inspection['source'],inspection['receipt'],row,scratch,'expedition-detach')
    selection=copy.deepcopy(selection);selection['native']=row
    draft['selection']=selection
    draft['selection_hash']=sha(json.dumps(selection,sort_keys=True,separators=(',',':')).encode())
    return draft


def prepare_return(departure,scratch,*,survivors=None,morale=None):
    if sha(departure['save'])!=departure['hash']:raise ValueError('departure snapshot changed')
    if sha(json.dumps(departure['selection'],sort_keys=True,separators=(',',':')).encode())!=departure['selection_hash']:
        raise ValueError('departure roster changed')
    row=copy.deepcopy(departure['selection']['native']);original=row['soldiers']
    if survivors is None:survivors=list(range(len(original)))
    if not isinstance(survivors,list):raise ValueError('survivors')
    for i in survivors:integer(i,0,len(original)-1)
    if len(set(survivors))!=len(survivors):raise ValueError('duplicate survivors')
    row['soldiers']=[original[i] for i in survivors]
    if morale is not None:integer(morale,0,105);row['morale']=morale
    return transform(departure['save'],departure['receipt'],row,scratch,'expedition-restore')
