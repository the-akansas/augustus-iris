"""Single-writer checkpoint bundle. Engine must be paused across capture of SAV + receipt.
Not yet a distributed two-city commit coordinator. Never ACK before publish returns.
"""
import hashlib,json,os,re,uuid
from pathlib import Path

def digest(b): return hashlib.sha256(b).hexdigest()
def durable(path,data):
 with path.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())

class Checkpoints:
 def __init__(self,root,session,city):
  self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
  self.session=session;self.city=city
 def load(self):
  pointer=self.root/'current.json'
  if not pointer.exists():return None
  meta=json.loads(pointer.read_text())
  if meta.get('session')!=self.session or meta.get('city')!=self.city or meta.get('schema')!=1:raise ValueError('identity mismatch')
  generation=meta.get('generation','')
  if not re.fullmatch('[0-9a-f]{32}',generation):raise ValueError('unsafe generation')
  directory=self.root/generation
  sav=(directory/'city.sav').read_bytes();receipt=(directory/'receipt.bin').read_bytes()
  if digest(sav)!=meta['save_hash'] or digest(receipt)!=meta['receipt_hash']:raise ValueError('corrupt checkpoint')
  return sav,receipt
 def publish(self,sav,receipt,fail_at=None):
  # Byte zero is locked on Windows, automatically released if process exits.
  import msvcrt
  with (self.root/'writer.lock').open('a+b') as lock:
   lock.seek(0)
   if not lock.read(1):lock.write(b'0');lock.flush()
   lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
   try:
    if not sav or not receipt:raise ValueError('empty checkpoint')
    generation=uuid.uuid4().hex;directory=self.root/generation;directory.mkdir()
    durable(directory/'city.sav',sav)
    if fail_at=='save':raise OSError('injected failure after save')
    durable(directory/'receipt.bin',receipt)
    meta=dict(schema=1,session=self.session,city=self.city,generation=generation,save_hash=digest(sav),receipt_hash=digest(receipt))
    encoded=json.dumps(meta,sort_keys=True).encode()
    durable(directory/'manifest.json',encoded)
    pointer=self.root/(generation+'.tmp');durable(pointer,encoded)
    if fail_at=='pointer':raise OSError('injected failure before publication')
    os.replace(pointer,self.root/'current.json')
    return generation
   finally:
    lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)
