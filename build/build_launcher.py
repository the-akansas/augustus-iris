"""Build the launchers from source (2026-11-16: they had shipped without it). Run with the bundled Python on Windows;
never starts what it builds.

  python build/build_launcher.py --root <work folder> [--out <folder>]   (default <root>/build/local)

  Augustus.exe, Augustus-Network.exe  creator-src/NetworkLauncher.cs + CreatorLang.cs (the same program under both
                                      names: the game's menu starts Augustus.exe, network_play.py Augustus-Network.exe)
  멀티저장설정.exe                     creator-src/AutosaveSettings.cs + CreatorLang.cs (tools/make_release.py names it
                                      Autosave-Settings.exe outside the Korean edition)
  observe_atomic.dll                  creator-src/observe_atomic.c with the project's compiler (build/native-sources.json)
The C# compiler is the one of .NET Framework 4 (like build/build_creator.py). The icon is the original Augustus icon
(res/augustus.ico of the Augustus source), when present. Prints one JSON line: success, the files and their sha256."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess,sys

def main():
    parser=argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--root',type=Path,required=True);parser.add_argument('--out',type=Path)
    args=parser.parse_args();root=args.root.resolve();src=root/'creator-src'
    out=(args.out or root/'build/local').resolve();out.mkdir(parents=True,exist_ok=True)
    csc=Path(os.environ.get('WINDIR',r'C:\Windows'))/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    manifest=json.loads((root/'build/native-sources.json').read_text(encoding='utf8'))
    clang=(root/manifest['compiler']).resolve()
    icon=root/'res/augustus.ico'
    refs=['/r:System.Windows.Forms.dll','/r:System.Drawing.dll','/r:System.Web.Extensions.dll']
    report=dict(success=False,files={},notes=[])
    def run(command,what):
        r=subprocess.run([str(x) for x in command],capture_output=True,text=True,encoding='utf8',errors='replace')
        if r.returncode:raise SystemExit(json.dumps(dict(success=False,failed=what,output=(r.stdout+r.stderr)[-3000:]),ensure_ascii=False))
    if not icon.is_file():report['notes'].append('res/augustus.ico not found: built without an icon')
    with_icon=['/win32icon:'+str(icon)] if icon.is_file() else []
    run([csc,'/nologo','/target:winexe','/platform:x64','/optimize+',*with_icon,*refs,'/out:'+str(out/'Augustus.exe'),src/'NetworkLauncher.cs',src/'CreatorLang.cs'],'Augustus.exe')
    shutil.copy2(out/'Augustus.exe',out/'Augustus-Network.exe')
    run([csc,'/nologo','/target:winexe','/platform:x64','/optimize+',*refs,'/out:'+str(out/'멀티저장설정.exe'),src/'AutosaveSettings.cs',src/'CreatorLang.cs'],'멀티저장설정.exe')
    run([clang,'-O2','-shared','-o',out/'observe_atomic.dll',src/'observe_atomic.c'],'observe_atomic.dll')
    for name in ('Augustus.exe','Augustus-Network.exe','멀티저장설정.exe','observe_atomic.dll'):
        report['files'][name]=hashlib.sha256((out/name).read_bytes()).hexdigest()
    report.update(success=True,out=str(out))
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
