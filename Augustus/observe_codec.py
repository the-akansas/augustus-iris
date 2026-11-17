"""Bounded verified block deltas; never a simulation command or recovery save."""
import base64,hashlib,struct,zlib
MAX_STATE=16*1024*1024
MAX_WIRE=2*1024*1024
BLOCK=4096
MAX_PATCH=MAX_STATE+8*((MAX_STATE+BLOCK-1)//BLOCK)
def digest(data):return hashlib.sha256(data).hexdigest()
def encode(before,after):
 if not isinstance(after,bytes) or not 16<=len(after)<=MAX_STATE:raise ValueError('state size')
 records=[]
 for off in range(0,len(after),BLOCK):
  block=after[off:off+BLOCK]
  if before is None or before[off:off+BLOCK]!=block:records.append(struct.pack('<II',off,len(block))+block)
 packed=zlib.compress(b''.join(records),1)
 if len(packed)>MAX_WIRE:raise ValueError('stream bandwidth limit')
 return dict(base=digest(before) if before is not None else '',hash=digest(after),size=len(after),patch=base64.b64encode(packed).decode(),blocks=len(records))
def decode(before,packet):
 if not isinstance(packet,dict) or type(packet.get('size'))is not int or not 16<=packet['size']<=MAX_STATE:raise ValueError('state size')
 base=packet.get('base');hashed=packet.get('hash')
 if not isinstance(base,str) or (base and (len(base)!=64 or any(c not in '0123456789abcdef' for c in base))):raise ValueError('base hash')
 if not isinstance(hashed,str) or len(hashed)!=64 or any(c not in '0123456789abcdef' for c in hashed):raise ValueError('state hash')
 if base and (before is None or base!=digest(before)):raise ValueError('delta base')
 text=packet.get('patch');size=packet['size']
 if not isinstance(text,str) or len(text)>4*((MAX_WIRE+2)//3):raise ValueError('wire size')
 try:
  packed=base64.b64decode(text,validate=True);d=zlib.decompressobj();raw=d.decompress(packed,MAX_PATCH+1)
 except Exception as e:raise ValueError('delta encoding') from e
 if len(raw)>MAX_PATCH or not d.eof or d.unused_data or d.unconsumed_tail:raise ValueError('delta compression')
 result=bytearray((before or b'')[:size] if base else b'');result.extend(b'\0'*(size-len(result)))
 pos=0;last=-BLOCK;seen=0
 while pos<len(raw):
  if pos+8>len(raw):raise ValueError('delta header')
  off,n=struct.unpack_from('<II',raw,pos);pos+=8
  if off%BLOCK or off<=last or off>=size or n!=min(BLOCK,size-off) or pos+n>len(raw):raise ValueError('delta block')
  if not base and off!=seen*BLOCK:raise ValueError('keyframe coverage')
  result[off:off+n]=raw[pos:pos+n];pos+=n;last=off;seen+=1
 if not base and seen!=(size+BLOCK-1)//BLOCK:raise ValueError('keyframe incomplete')
 result=bytes(result)
 if digest(result)!=hashed:raise ValueError('delta integrity')
 return result

def to_initial_save(data):
 """Only the first viewer bootstrap; subsequent updates never load SAV files."""
 if len(data)<16:raise ValueError('state header')
 magic,version,resources,count=struct.unpack_from('<4I',data)
 if magic not in (0x32534341,0x33534341) or not 1<=count<=256:raise ValueError('state layout')
 out=[];at=16
 for _ in range(count):
  if at+8>len(data):raise ValueError('state piece')
  flags,n=struct.unpack_from('<II',data,at);at+=8
  if flags&~3 or at+n>len(data):raise ValueError('state piece')
  if flags&2:
   out.append(struct.pack('<I',n))
   if not n:continue
  if flags&1:out.append(struct.pack('<I',0x80000000))
  out.append(data[at:at+n]);at+=n
 if magic==0x33534341:
  if at+12>len(data):raise ValueError('render trailer')
  tag,cells,planes=struct.unpack_from('<3I',data,at)
  if tag!=0x474d4952 or cells!=162*162 or planes!=3 or len(data)-at!=12+cells*planes*4:raise ValueError('render trailer')
 elif at!=len(data):raise ValueError('state trailing bytes')
 return b''.join(out)
