"""Build native targets from explicit sources; never consume historical objects."""
from pathlib import Path
import argparse,concurrent.futures,ctypes,hashlib,json,subprocess,tempfile,time

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--target',choices=('ui','worker'),default='ui')
    parser.add_argument('--jobs',type=int,default=6)
    # a release build (tools/make_release.py, user 2026-11-15): AUGUSTUS_RELEASE leaves the test launcher's tools out
    parser.add_argument('--release',action='store_true',help='build without the test launcher tools (AUGUSTUS_RELEASE)')
    # another edition's release (user 2026-11-17: the Global edition showed 서버 접속 and 업데이트 확인): its src/ without
    # the Korean edition's files (EDITIONS.md), made by tools/make_release.py; every 'src/...' is read from there
    parser.add_argument('--src',type=Path,help='a src folder to build from instead of <root>/src')
    args=parser.parse_args();root=args.root.resolve();src=args.src.resolve() if args.src else None
    manifest=json.loads(Path(__file__).with_name('native-sources.json').read_text(encoding='utf8'))
    target=manifest['targets'][args.target]
    if target['missing']:
        parser.error('Missing original sources: '+', '.join(target['missing']))
    if not 1<=args.jobs<=16:parser.error('jobs must be 1..16')
    def place(relative):
        parts=Path(relative).parts
        if src and parts and parts[0]=='src':return src.joinpath(*parts[1:]).resolve(),src
        return (root/relative).resolve(),root
    def local(relative):
        path,base=place(relative)
        if not path.is_relative_to(base) or not path.is_file():raise ValueError('Invalid input: '+relative)
        return path
    sources=[local(s) for s in target['sources']]
    if len(set(sources)) != len(sources):
        raise ValueError('Duplicate source entries in target: '+args.target)
    libraries=[str(local(x['file'])) if isinstance(x,dict) else x for x in target['libraries']]
    if any(str(x).lower().endswith(('.obj','.o')) for x in libraries):raise ValueError('Prebuilt objects forbidden')
    compiler=local(manifest['compiler'])
    args.out.mkdir(parents=True,exist_ok=True)
    out=Path(tempfile.mkdtemp(prefix=args.target+'-',dir=args.out.resolve()))
    includes=['-I'+str(place(p)[0]) for p in manifest['includes']]
    for p in manifest['system_includes']:includes+=['-isystem',str(place(p)[0])]
    started=time.time()
    def compile_one(item):
        index,source=item;obj=out/(str(index)+'.obj')
        command=[str(compiler),'-O2','-std=gnu99',*(['-DAUGUSTUS_RELEASE'] if args.release else []),*includes,'-c',str(source),'-o',str(obj)]
        result=subprocess.run(command,capture_output=True,text=True,encoding='utf8',errors='replace')
        return dict(source=str(source.relative_to(src if src and source.is_relative_to(src) else root)),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),object=str(obj),returncode=result.returncode,output=result.stdout+result.stderr,command=command)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        results=list(pool.map(compile_one,enumerate(sources)))
    report=dict(target=args.target,base_commit=manifest['base_commit'],release=args.release,src=str(src) if src else None,sources=results,success=False,prebuilt_game_objects=False)
    if not any(r['returncode'] for r in results):
        executable=out/target['executable'];rsp=out/'link.rsp'
        rsp.write_text('\n'.join('"'+x.replace('\\','/')+'"' for x in [r['object'] for r in results]+libraries),encoding='utf8')
        result=subprocess.run([str(compiler),'@'+str(rsp),'-Wl,--wrap,fopen,--wrap,rename,--wrap,remove','-lbcrypt','-mwindows' if args.target=='ui' else '-mconsole','-o',str(executable)],capture_output=True,text=True)
        report['link']=dict(returncode=result.returncode,output=result.stdout+result.stderr)
        if result.returncode==0:
            k=ctypes.WinDLL('kernel32',use_last_error=True)
            k.BeginUpdateResourceW.argtypes=[ctypes.c_wchar_p,ctypes.c_int];k.BeginUpdateResourceW.restype=ctypes.c_void_p
            k.UpdateResourceW.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_ushort,ctypes.c_void_p,ctypes.c_uint];k.UpdateResourceW.restype=ctypes.c_int
            k.EndUpdateResourceW.argtypes=[ctypes.c_void_p,ctypes.c_int];k.EndUpdateResourceW.restype=ctypes.c_int
            data=local('build/utf8.manifest').read_bytes();buf=ctypes.create_string_buffer(data);handle=k.BeginUpdateResourceW(str(executable),False)
            if not handle:raise ctypes.WinError(ctypes.get_last_error())
            if not k.UpdateResourceW(handle,24,1,0,buf,len(data)):
                k.EndUpdateResourceW(handle,True);raise ctypes.WinError(ctypes.get_last_error())
            if not k.EndUpdateResourceW(handle,False):raise ctypes.WinError(ctypes.get_last_error())
            report.update(success=True,executable=str(executable),sha256=hashlib.sha256(executable.read_bytes()).hexdigest())
    report['seconds']=time.time()-started
    (out/'build-report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k!='sources'}));print('report:',out/'build-report.json')
    raise SystemExit(0 if report['success'] else 1)

if __name__=='__main__':main()
