"""Staged cargo backend; not yet wired into live_trade.

A SAV alone is insufficient once goods are loaded. Keep all three payloads and
their manifest together. Never publish worker output before paired-room commit.
Hashes detect corruption/mismatches, not malicious edits by a local file owner.
"""
import hashlib,json,os,struct,uuid
from pathlib import Path
from city_client import Engine
FILES=('city.sav','receipt.bin','cargo.bin')
EMPTY=struct.pack('<4sQiiii',b'MPCG',0,0,0,0,0)
def digest(b):return hashlib.sha256(b).hexdigest()
def cargo(data):
    if len(data)!=28:raise ValueError('cargo length')
    magic,contract,resource,total,remaining,state=struct.unpack('<4sQiiii',data)
    if magic!=b'MPCG':raise ValueError('cargo magic')
    if not contract:
        if any((resource,total,remaining,state)):raise ValueError('nonempty zero cargo')
    elif not (1<=resource<=21 and 1<=total<=32 and
              ((state==1 and remaining==total) or (state==2 and 0<remaining<=total) or (state in (3,4) and remaining==0))):
        raise ValueError('cargo state')
    return dict(contract=contract,resource=resource,total=total,remaining=remaining,state=state)
def read(root):
    root=Path(root)
    manifest=json.loads((root/'cargo-manifest.json').read_text(encoding='utf-8'))
    if set(manifest)!= {'version','files'} or type(manifest['version'])!=int or manifest['version']!=1 or set(manifest['files'])!=set(FILES):raise ValueError('cargo manifest')
    parts={name:(root/name).read_bytes() for name in FILES}
    if any(digest(data)!=manifest['files'][name] for name,data in parts.items()):raise ValueError('cargo snapshot hash mismatch')
    cargo(parts['cargo.bin'])
    return parts
def publish(target,parts):
    target=Path(target).resolve()
    if target.exists():raise FileExistsError(target)
    if set(parts)!=set(FILES):raise ValueError('cargo snapshot files')
    cargo(parts['cargo.bin'])
    target.parent.mkdir(parents=True,exist_ok=True)
    draft=target.parent/(target.name+'.draft-'+uuid.uuid4().hex);draft.mkdir()
    manifest=dict(version=1,files={name:digest(data) for name,data in parts.items()})
    for name,data in dict(parts,**{'cargo-manifest.json':json.dumps(manifest,sort_keys=True).encode()}).items():
        with (draft/name).open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
    # Same-volume directory rename publishes the complete set. Failed drafts are
    # intentionally retained for diagnostics and never treated as current saves.
    os.rename(draft,target)
    return cargo(parts['cargo.bin'])
def initialize(source,target):
    source=Path(source)
    if (source/'cargo.bin').exists() or (source/'cargo-manifest.json').exists():raise ValueError('cargo already initialized')
    return publish(target,{'city.sav':(source/'city.sav').read_bytes(),'receipt.bin':(source/'receipt.bin').read_bytes(),'cargo.bin':EMPTY})
def checkpoint(source,target,save,receipt):
    """Trusted engine-thread SAV checkpoint while cargo stays outside the city.

    Caller must supply the SAME city's current SAV and serialize against cargo
    operations. A multiplayer integration must commit BOTH cities atomically.
    """
    parts=read(source);parts.update({'city.sav':save,'receipt.bin':receipt})
    return publish(target,parts)
def apply(source,target,operation,contract,resource,quantity):
    if operation not in ('load','return','consume'):raise ValueError('cargo operation')
    if type(contract)!=int or not 0<contract<2**64 or type(resource)!=int or not 1<=resource<=21 or type(quantity)!=int or not 1<=quantity<=32:raise ValueError('cargo arguments')
    target=Path(target).resolve()
    if target.exists():raise FileExistsError(target)
    parts=read(source) # Copy verified bytes, avoiding a later read of mutable source.
    target.parent.mkdir(parents=True,exist_ok=True)
    scratch=target.parent/(target.name+'.worker-'+uuid.uuid4().hex);scratch.mkdir()
    base=scratch/'base';base.mkdir()
    for name,data in parts.items():(base/name).write_bytes(data)
    out=scratch/'result'
    Engine().run('cargo-'+operation,base,out,quantity,resource,contract)
    return publish(target,{name:(out/name).read_bytes() for name in FILES})
