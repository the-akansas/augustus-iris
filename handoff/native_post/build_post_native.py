"""Build the engine-side money mailbox (real post_ipc.c, post_city.c, post_book.c, core/buffer.c + shim_post.c) into
post_native-1..N shared libraries for handoff/test_throne_room_flow.py (one copy per city: post_city.c keeps one
city's book in static memory, like one game process). Test tool only; not shipped with the game.

  python build_post_native.py --src <game source root containing src/> --out <empty folder> [--cities 4]

Tries gcc, then clang, then MSVC cl (whichever is on PATH; --cc forces one). Prints the compiler and its output and
exits non-zero on failure; nothing is skipped silently. Then set AUGUSTUS_POST_NATIVE_DIR=<out>."""
import argparse,os,shutil,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
EXPORTS=('post_ipc_init','post_ipc_exchange','mp_post_city_reset','mp_post_city_save','mp_post_city_restore',
         'shim_set_treasury','shim_get_treasury','shim_ipc_size')

def main():
    a=argparse.ArgumentParser();a.add_argument('--src',required=True);a.add_argument('--out',required=True)
    a.add_argument('--cities',type=int,default=4);a.add_argument('--cc')
    o=a.parse_args()
    src=Path(o.src)/'src';out=Path(o.out);out.mkdir(parents=True,exist_ok=True)
    files=[src/'multiplayer/post_ipc.c',src/'multiplayer/post_city.c',src/'multiplayer/post_book.c',src/'core/buffer.c',HERE/'shim_post.c']
    for f in files:
        if not f.is_file():sys.exit(f'missing source: {f}')
    ext='.dll' if os.name=='nt' else '.so';first=out/('post_native-1'+ext)
    cc=o.cc or shutil.which('gcc') or shutil.which('clang') or shutil.which('cl')
    if not cc:sys.exit('no C compiler on PATH (gcc, clang or cl)')
    inc=[str(HERE/'stub'),str(src),str(src/'multiplayer')]   # stub/windows.h: SHA-256 only, reports failure (compaction rejected)
    if Path(cc).stem.lower()=='cl':
        cmd=[cc,'/nologo','/LD','/O1',*['/I'+i for i in inc],*map(str,files),'/Fe:'+str(first),'/Fo:'+str(out)+os.sep,
             '/link',*['/EXPORT:'+e for e in EXPORTS]]
    else:
        cmd=[cc,'-shared','-O1','-std=gnu99',*([] if os.name=='nt' else ['-fPIC']),*['-I'+i for i in inc],'-o',str(first),*map(str,files)]
    print('compiler:',cc);print(' '.join(cmd))
    r=subprocess.run(cmd,capture_output=True,text=True)
    print(r.stdout[-4000:],r.stderr[-4000:])
    if r.returncode or not first.is_file():sys.exit(f'build failed ({r.returncode})')
    for i in range(2,o.cities+1):shutil.copy2(first,out/f'post_native-{i}{ext}')
    import ctypes
    lib=ctypes.CDLL(str(first));missing=[e for e in EXPORTS if not hasattr(lib,e)]
    if missing:sys.exit('missing exports: '+', '.join(missing))
    print('built',o.cities,'copies in',out)

if __name__=='__main__':main()
