"""Trusted headless native inspection, bound to immutable source bytes.
No gameplay detach/arrival yet. The rewritten inspection SAV is not published.
"""
from pathlib import Path
import hashlib
import json
import uuid
from tempfile import TemporaryDirectory
from expedition_state import manifest, integer, identifier
from city_client import Engine, HERE


def sha(data): return hashlib.sha256(data).hexdigest()


def inspect_snapshot(source, scratch):
    source=Path(source);scratch=Path(scratch)
    # Read once and inspect this private copy, never a live file changing mid-run.
    sav=(source/'city.sav').read_bytes();receipt=(source/'receipt.bin').read_bytes()
    return inspect_bytes(sav,receipt,scratch)


def inspect_bytes(sav,receipt,scratch):
    """Inspect private immutable bytes, reclaiming all drafts even on failure."""
    scratch=Path(scratch);scratch.mkdir(parents=True,exist_ok=True)
    with TemporaryDirectory(prefix='army-inspect-',dir=scratch) as directory:
        root=Path(directory);original=root/'input';original.mkdir()
        (original/'city.sav').write_bytes(sav);(original/'receipt.bin').write_bytes(receipt)
        Engine().run('inspect',original,root/'output')
        report=json.loads((root/'output/legions.json').read_text())
        audit=json.loads((root/'output/roster-audit.json').read_text())
    if set(report)!={'version','legions'} or report['version']!=1 or not isinstance(report['legions'],list):
        raise ValueError('invalid native report')
    return dict(source_hash=sha(sav),receipt_hash=sha(receipt),
                worker_hash=sha((HERE/'engine-city-test.exe').read_bytes()),
                source=sav,receipt=receipt,report=report,
                clock=tuple(audit[k] for k in ('year','month','day','tick')))


def select_army(inspection, formation_id, owner, army_id):
    identifier(owner);identifier(army_id);integer(formation_id,1,2**31-1)
    if sha(inspection['source'])!=inspection['source_hash'] or sha(inspection['receipt'])!=inspection['receipt_hash']:
        raise ValueError('snapshot changed')
    rows=[r for r in inspection['report']['legions'] if r['formation_id']==formation_id]
    if len(rows)!=1:raise ValueError('missing or ambiguous formation')
    row=rows[0];soldiers=row['soldiers']
    if row.get('mp_expedition_id') or not row['at_fort'] or row['recent_fight'] or row['empire_service'] or row['distant_battle']:
        raise ValueError('legion is not available at its fort')
    if row['unit_type'] not in (11,12,13,92,94) or not 1<=len(soldiers)<=16:
        raise ValueError('unsupported or empty legion')
    ids=set()
    for s in soldiers:
        integer(s['local_id'],1,2**31-1);integer(s['damage'],0,s['max_damage'])
        if s['local_id'] in ids or s['type']!=row['unit_type'] or not s['at_rest'] or s['action']!=80 or s['opponent'] or s['attackers']:
            raise ValueError('soldier moving, fighting or duplicated')
        ids.add(s['local_id'])
    data=manifest(dict(army_id=army_id,owner=owner,unit_type=row['unit_type'],soldiers=len(soldiers),
                       morale=row['morale'],trained=row['trained'],total_damage=sum(s['damage'] for s in soldiers),
                       months_from_home=row['months_from_home']))
    # Full native detail remains alongside the small state-machine summary.
    return dict(manifest=data,native=json.loads(json.dumps(row)),source_hash=inspection['source_hash'],
                receipt_hash=inspection['receipt_hash'],worker_hash=inspection['worker_hash'])


def import_army(store, source, scratch, formation_id, owner, army_id):
    """Single trusted inspection -> atomic manifest+source evidence import.
    This records initial state only; it does not reserve or remove game soldiers.
    """
    inspection=inspect_snapshot(source,scratch)
    selected=select_army(inspection,formation_id,owner,army_id)
    store.seed(selected['manifest'],source=inspection['source'],detail=selected)
    return selected
