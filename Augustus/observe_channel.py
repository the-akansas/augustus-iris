"""Single writer memory channel. Odd/even atomic publication, bounded read retries."""
import ctypes,mmap,struct,uuid
from mailbox_io import publish_text
CAP=16*1024*1024
FRAME_CAP=40*1024*1024
HEADER=64
from pathlib import Path
kernel=ctypes.CDLL(str(Path(__file__).with_name('observe_atomic.dll')))
exchange=kernel.obs_exchange;exchange.argtypes=[ctypes.POINTER(ctypes.c_long),ctypes.c_long];exchange.restype=ctypes.c_long
compare=kernel.obs_compare;compare.argtypes=[ctypes.POINTER(ctypes.c_long),ctypes.c_long,ctypes.c_long];compare.restype=ctypes.c_long
class Channel:
 def __init__(self,root,base,capacity=CAP):
  self.root=root;self.base=base;self.capacity=capacity;self.token=uuid.uuid4().hex;self.name='Local\\AugustusState-'+self.token
  self.map=mmap.mmap(-1,capacity+HEADER,tagname=self.name);self.closed=False
  self.ptr=ctypes.cast(ctypes.addressof(ctypes.c_long.from_buffer(self.map,4)),ctypes.POINTER(ctypes.c_long))
  self.request=0;self.serial=0
  publish_text(root/(base+'.txt'),self.token)
 def demand(self):
  self.request=(self.request+1)&0xffffffff or 1;struct.pack_into('<I',self.map,0,self.request);return self.request
 def read(self):
  for _ in range(3):
   stamp=compare(self.ptr,0,0)
   if not stamp or stamp&1:return None
   length,_,seq,ticks=struct.unpack_from('<IIQQ',self.map,8)
   if not 0<length<=self.capacity:return None
   data=bytes(self.map[HEADER:HEADER+length])
   if compare(self.ptr,0,0)==stamp:return seq,ticks,data
  return None
 def write(self,data,seq,ticks=0):
  if not 0<len(data)<=self.capacity:raise ValueError('channel size')
  self.serial=(self.serial+2)&0x7ffffffe or 2
  exchange(self.ptr,self.serial-1)
  self.map[HEADER:HEADER+len(data)]=data
  struct.pack_into('<IIQQ',self.map,8,len(data),0,seq,ticks)
  exchange(self.ptr,self.serial)
 def close(self):
  if self.closed:return
  self.closed=True
  path=self.root/(self.base+'.txt')
  try:
   if path.read_text().strip()==self.token:path.unlink()
  except OSError:pass
  self.map.close()

