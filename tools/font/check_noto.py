"""Measurable checks on the font files as the engine reads them (decoded again from disk)."""
import sys,json,numpy as np
from kfmt import *
D=sys.argv[1];t=table();idx={c:i for i,c in t.items()}
v=read_v2(f'{D}/korean-noto-v2.555');asc=read_ascii(f'{D}/korean-noto-ascii.bin');hd=read_hd(f'{D}/korean-noto-hd.bin')
cfg=json.load(open(f'{D}/noto-build.json'));res={}
ASCII_H=cfg['settings']['ascii_height']
res['entries']=dict(hangul=[len(x) for x in v],ascii=len(asc),hd=len(hd),hd_expected=3*N+940)
res['empty_hangul']=[(s,t[i]) for s in range(3) for i in range(N) if not v[s][i].any()]
res['empty_ascii']=[(st,chr(33+k)) for st in range(10) for k in range(94) if not asc[st*94+k].any()]
# ink outside the drawn cell (inside the 2px padding) and touching the padded border
for s,h in enumerate(STY):
    g=v[s];c=h+4
    outside=(g[:,:2,:].any((1,2))|g[:,h+2:,:].any((1,2))|g[:,:,:2].any((1,2))|g[:,:,h+2:].any((1,2)))
    border=(g[:,0,:].any(1)|g[:,-1,:].any(1)|g[:,:,0].any(1)|g[:,:,-1].any(1))
    res[f'hangul{h}_ink_in_padding']=int(outside[:11172].sum());res[f'hangul{h}_touch_border']=int(border.sum())
    rows=np.array([np.nonzero(g[i].any(1))[0][[0,-1]] for i in range(11172) if g[i].any()])-2
    res[f'hangul{h}_ink_rows_p1_p50_p99']=dict(top=np.percentile(rows[:,0],[1,50,99]).tolist(),bottom=np.percentile(rows[:,1],[1,50,99]).tolist())
# common baseline: flat-bottom ASCII letters end on the same row in every style of a height, and Hangul '가' sits on it
for st in range(10):
    h=ASCII_H[st];bots={ch:int(np.nonzero(asc[st*94+ord(ch)-33].any(1))[0][-1])-8 for ch in 'HExz1'}
    res.setdefault('ascii_baseline_row',{})[st]=dict(height=h,rows=bots,same=len(set(bots.values()))==1)
# 4-bit loss: ink mass of the 8-bit HD downsampled vs the 4-bit cell
loss=[]
for s,h in enumerate(STY):
    for ch in '가힣쀍뷁읽밝값궤ㅢ습립':
        i=idx[ch];dx,dy,a=hd[s*N+i];big=np.zeros(((h+4)*4,(h+4)*4));big[8+dy:8+dy+a.shape[0],8+dx:8+dx+a.shape[1]]=a/255
        m=big.reshape(h+4,4,h+4,4).mean((1,3));q=v[s][i]/15
        loss.append((h,ch,round(float(np.abs(m-q).max()),3),int(((m>0)&(q==0)).sum())))
res['hd_vs_cell_maxdiff_and_dropped_px']=loss
res['hd_limits_ok']=all(1<=a.shape[0]<=192 and 1<=a.shape[1]<=192 and -32<=x<=192 and -32<=y<=192 for x,y,a in hd)
json.dump(res,open(f'{D}/check.json','w'),ensure_ascii=False,indent=1,default=int)
print(json.dumps({k:res[k] for k in res if k!='ascii_baseline_row'},ensure_ascii=False,default=int)[:2500])
print({k:(v_['height'],v_['same'],v_['rows']['H']) for k,v_ in res['ascii_baseline_row'].items()})
# extra letters (Cyrillic, Latin-1 ...): decoded from korean-noto-extra.bin, 10 styles x SLOTS x 48x48
import re
hdr=open(f'{D}/korean_extra_chars.h').read()
SL=int(re.search(r'KOREAN_EXTRA_SLOTS (\d+)',hdr).group(1));NC=int(re.search(r'KOREAN_EXTRA_CHARS (\d+)',hdr).group(1))
codes=[int(x,16) for x in re.findall(r'0x([0-9a-fA-F]+)',hdr.split('korean_extra_chars')[1].split('}')[0])][:NC]
ex=np.fromfile(f'{D}/korean-noto-extra.bin',np.uint8).reshape(10,SL,48,48)
res['extra_count']=NC;res['extra_empty']=[(st,hex(codes[k])) for st in range(10) for k in range(NC) if not ex[st,k].any() and codes[k]!=0xA0]
res['extra_touch_border']=int(sum(1 for st in range(10) for k in range(NC) if ex[st,k,0].any() or ex[st,k,-1].any() or ex[st,k,:,0].any() or ex[st,k,:,-1].any()))
bl={}
for st in range(10):
    H=int(np.nonzero(asc[st*94+ord('H')-33].any(1))[0][-1])
    bl[st]=all(int(np.nonzero(ex[st,codes.index(ord(c))].any(1))[0][-1])==H for c in 'НШЖ')
res['extra_baseline_same_as_H']=bl
json.dump(res,open(f'{D}/check.json','w'),ensure_ascii=False,indent=1,default=int)
print('extra',NC,'empty',res['extra_empty'],'border',res['extra_touch_border'],'baseline',bl)
