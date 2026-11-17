"""Readers/writers for the Korean font files the engine loads (src/core/image.c build_multibyte_font)."""
import re,numpy as np,struct
N=11266;STY=[12,15,20];PAD=4
def cell(s):return STY[s]+PAD
def style_bytes(s):return ((cell(s)+1)//2)*cell(s)
def read_v2(path):
    raw=np.fromfile(path,np.uint8);out=[];pos=0
    for s in range(3):
        c=cell(s);rb=(c+1)//2;blk=raw[pos:pos+N*rb*c].reshape(N,c,rb);pos+=N*rb*c
        lo=blk&15;hi=blk>>4;g=np.empty((N,c,rb*2),np.uint8);g[:,:,0::2]=lo;g[:,:,1::2]=hi
        out.append(g[:,:,:c])
    assert pos==len(raw);return out           # values 0..15, cell incl. 2px pad each side
def write_v2(path,styles):
    parts=[]
    for s,g in enumerate(styles):
        c=cell(s);rb=(c+1)//2;p=np.zeros((N,c,rb*2),np.uint8);p[:,:,:c]=g
        parts.append((p[:,:,0::2]|(p[:,:,1::2]<<4)).astype(np.uint8).ravel())
    np.concatenate(parts).tofile(path)
def read_ascii(path):return np.fromfile(path,np.uint8).reshape(940,48,48)
def read_hd(path):
    raw=open(path,'rb').read();assert raw[:4]==b'KHD1';n=struct.unpack_from('<H',raw,4)[0];pos=8;out=[]
    for i in range(n):
        w,h,x,y=struct.unpack_from('<HHhh',raw,pos);out.append((x,y,np.frombuffer(raw,np.uint8,w*h,pos+8).reshape(h,w)));pos+=8+w*h
    return out
def write_hd(path,glyphs):
    with open(path,'wb') as f:
        f.write(b'KHD1'+struct.pack('<HH',len(glyphs),0))
        for x,y,a in glyphs:h,w=a.shape;f.write(struct.pack('<HHhh',w,h,x,y));f.write(np.ascontiguousarray(a,np.uint8).tobytes())
def table(src=None):
    from pathlib import Path
    src=src or Path(__file__).resolve().parents[2]/'src'/'core'/'encoding_korean.c'   # this source tree's table
    t={}
    for cp,b0,b1,b2,i in re.findall(r'\{0x([0-9a-f]{4}), \{0x([0-9a-f]{2}), 0x([0-9a-f]{2}), 0x([0-9a-f]{2})\}, (\d+)\}',open(src,encoding='utf-8').read()):
        ch=bytes([int(b0,16),int(b1,16),int(b2,16)]).rstrip(b'\0').decode('utf-8');t.setdefault(int(i),ch)
    return t   # image index -> character
def ink(a):
    ys,xs=np.nonzero(a)
    return (xs.min(),ys.min(),xs.max(),ys.max()) if len(xs) else None
