"""Build the Noto Sans KR font files in the formats src/core/image.c loads (font-readability guide v1 workflow):
4x unhinted FreeType render on a common baseline and a fixed advance, ONE exact 4x4 area downscale,
no threshold / gamma / dilate / erode; 4-bit for the Hangul cells, 8-bit for ASCII and HD.
  python gen_noto.py OUTDIR"""
import sys,json,hashlib,freetype,numpy as np
from kfmt import *
import os
FONT=os.path.join(os.environ.get('NOTO_KR_DIR','fonts'),'NotoSansKR-%s.otf')   # notofonts/noto-cjk Sans/SubsetOTF/KR (commit f8d1575)
HANGUL_WEIGHT=['Medium','Medium','Bold']                   # styles 12 / 15 / 20
ASCII_H=[15,12,12,12,20,20,20,12,12,12]                    # per font_t (image.c: style 0 ->15, 4..6 ->20, else 12)
ASCII_WEIGHT=['Bold' if h==20 else 'Medium' for h in ASCII_H]
EM_PER_CELL=13/12                                           # Hangul ink ~0.92 em fills the cell like the shipped fonts
ASC=0.835                                                   # baseline below the cell top, in em
TRACK=0                                                     # keeps the shipped line widths (sum of advances = dotum)
Q=4
# Letters for Russian, German, Spanish (and French/Italian/Portuguese for free) that the CP949 table lacks.
# They travel in the CP949 user-defined area: slot k -> 0xC9A1+k (k<94) or 0xFEA1+k-94 (src/core/encoding_korean.c).
EXTRA_SLOTS=188
EXTRA=[0x401]+list(range(0x410,0x450))+[0x451]+[c for c in range(0xA1,0x100) if c not in (0xAD,0xB7)]+[0x2013,0x2014,0x2018,0x2019,0x201A,0x201C,0x201D,0x201E,0x2026,0x20AC,0x152,0x153]
assert len(EXTRA)<=EXTRA_SLOTS and len(set(EXTRA))==len(EXTRA)
faces={}
def face(w,em):
    k=(w,em)
    if k not in faces:
        f=freetype.Face(FONT%w);f.set_char_size(int(round(em*Q*64)));faces[k]=f
    return faces[k]
def em_for(h):return h*EM_PER_CELL
def base_for(h):return int(round(ASC*em_for(h)))
def render(w,h,ch,origin_x4,base_y4,size4):
    f=face(w,em_for(h));f.load_char(ch,freetype.FT_LOAD_RENDER|freetype.FT_LOAD_NO_HINTING|freetype.FT_LOAD_TARGET_NORMAL)
    g=f.glyph;b=g.bitmap;can=np.zeros((size4,size4),np.float64);over=0
    if b.width:
        a=np.array(b.buffer,np.uint8).reshape(b.rows,b.pitch)[:,:b.width]/255.0
        x0=origin_x4+g.bitmap_left;y0=base_y4-g.bitmap_top
        X0,Y0=max(0,x0),max(0,y0);X1,Y1=min(size4,x0+b.width),min(size4,y0+b.rows)
        over=a.sum()-a[Y0-y0:Y1-y0,X0-x0:X1-x0].sum()
        can[Y0:Y1,X0:X1]=a[Y0-y0:Y1-y0,X0-x0:X1-x0]
    return can,g.advance.x/64/Q,over
def down(can):n=can.shape[0]//Q;return can.reshape(n,Q,n,Q).mean((1,3))
def hd_crop(can,ox4,oy4):
    ys,xs=np.nonzero(can>=0.5/255)
    if not len(xs):return (0,0,np.zeros((1,1),np.uint8))
    a=can[ys.min():ys.max()+1,xs.min():xs.max()+1]
    return (int(xs.min()-ox4),int(ys.min()-oy4),np.round(a*255).astype(np.uint8))
def main(out):
    import os;os.makedirs(out,exist_ok=True)
    t=table();styles=[];hd=[];report=dict(overflow=[],empty=[])
    for s,h in enumerate(STY):
        w=HANGUL_WEIGHT[s];c=h+PAD;B=base_for(h);g=np.zeros((N,c,c),np.uint8)
        adv4=920*em_for(h)*Q/1000
        ox4=2*Q+int(round((h*Q-adv4)/2));by4=(2+B)*Q
        for i in range(N):
            can,adv,over=render(w,h,t[i],ox4,by4,c*Q)
            if over>0.5:report['overflow'].append((s,t[i],round(over/16,2)))
            m=down(can);g[i]=np.round(m*15).astype(np.uint8)
            if not g[i].any():report['empty'].append((s,t[i]))
            dx,dy,a=hd_crop(can,2*Q,2*Q);hd.append((dx,dy,a))
        styles.append(g);print('style',s,h,'em',round(em_for(h),2),'baseline',B,flush=True)
    write_v2(f'{out}/korean-noto-v2.555',styles)
    asc=np.zeros((940,48,48),np.uint8);widths=[]
    for st in range(10):
        h=ASCII_H[st];w=ASCII_WEIGHT[st];B=base_for(h)
        for k in range(94):
            ch=chr(33+k);can,adv,over=render(w,h,ch,8*Q,(8+B)*Q,48*Q)
            if over>0.5:report['overflow'].append(('ascii',st,ch))
            asc[st*94+k]=np.round(down(can)*255).astype(np.uint8)
            if not asc[st*94+k].any():report['empty'].append(('ascii',st,ch))
            widths.append(int(round(adv))+TRACK)
            hd.append(hd_crop(can,8*Q,8*Q))
    asc.tofile(f'{out}/korean-noto-ascii.bin')
    ext=np.zeros((10*EXTRA_SLOTS,48,48),np.uint8);ext_w=[]
    for st in range(10):
        h=ASCII_H[st];w=ASCII_WEIGHT[st];B=base_for(h)
        for k in range(EXTRA_SLOTS):
            if k<len(EXTRA):
                can,adv,over=render(w,h,chr(EXTRA[k]),8*Q,(8+B)*Q,48*Q)
                if over>0.5:report['overflow'].append(('extra',st,chr(EXTRA[k])))
                ext[st*EXTRA_SLOTS+k]=np.round(down(can)*255).astype(np.uint8)
                if not ext[st*EXTRA_SLOTS+k].any() and EXTRA[k]!=0xA0:report['empty'].append(('extra',st,chr(EXTRA[k])))
                ext_w.append(int(round(adv))+TRACK);hd.append(hd_crop(can,8*Q,8*Q))
            else:ext_w.append(0);hd.append((0,0,np.zeros((1,1),np.uint8)))
    ext.tofile(f'{out}/korean-noto-extra.bin')
    with open(f'{out}/korean_extra_chars.h','w',newline='\r\n') as f:
        f.write('/* Generated by tools/font/gen_noto.py: letters outside the CP949 table, kept in its user-defined area.\n'
                ' * Slot k is CP949 0xC9A1+k (k<94) or 0xFEA1+k-94; korean-noto-extra.bin holds 10 font styles x 188 slots. */\n')
        f.write('#define KOREAN_EXTRA_STYLES 10\n#define KOREAN_EXTRA_SLOTS %d\n#define KOREAN_EXTRA_CHARS %d\n'%(EXTRA_SLOTS,len(EXTRA)))
        f.write('static const unsigned short korean_extra_chars[KOREAN_EXTRA_CHARS] = {'+','.join('0x%04x'%c for c in EXTRA)+'};\n')
        f.write('static const unsigned char korean_extra_widths[10 * KOREAN_EXTRA_SLOTS] = {'+','.join(map(str,ext_w))+'};\n')
    write_hd(f'{out}/korean-noto-hd.bin',hd)
    json.dump(dict(widths=widths,report=report,settings=dict(hangul_weight=HANGUL_WEIGHT,ascii_weight=ASCII_WEIGHT,ascii_height=ASCII_H,
        em_per_cell=EM_PER_CELL,baseline_em=ASC,track=TRACK,supersample=Q,downscale='exact 4x4 area mean',quantize='round(a*15) / round(a*255)',
        hinting='none (FT_LOAD_NO_HINTING)',fonts={w:hashlib.sha256(open(FONT%w,'rb').read()).hexdigest() for w in ('Medium','Bold')})),
        open(f'{out}/noto-build.json','w'),ensure_ascii=False,indent=1)
    print('overflow',len(report['overflow']),report['overflow'][:10],'empty',report['empty'][:10])
if __name__=='__main__':main(sys.argv[1])
