"""Portable restored creator build. Run with bundled Python; never launches UI."""
from pathlib import Path
import subprocess, os, argparse, ast
parser=argparse.ArgumentParser()
parser.add_argument('--root',type=Path,required=True)
parser.add_argument('--source',type=Path)
parser.add_argument('--output',type=Path)
args=parser.parse_args()
root=args.root.resolve()
source=(args.source or root/'creator-src').resolve()
target=(args.output or root/'build/local/Augustus-Scenario-Creator.exe').resolve()
names='ScenarioCreator CreatorCityEvents CreatorInvasions CreatorMapView CreatorTerrainView CreatorPresetPicker CreatorObjectives CreatorMergedEmpire CreatorNativeTerrain CreatorMapWorkflow CreatorTradeAccess CreatorSeaLimits CreatorCityRoles CreatorSlotSettings CreatorWorkflowLayout CreatorRome CreatorSalary CreatorWorkspace CreatorStartup CreatorBriefing CreatorLang CreatorThrone CreatorProgress CreatorTerrainLibrary CreatorBuildingTiles CreatorLook CreatorRace CreatorCityLibrary'.split()   # CreatorLang: the creator follows the game's language (2026-11-14)
compiler=Path(os.environ.get('WINDIR',r'C:\Windows'))/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
target.parent.mkdir(parents=True,exist_ok=True)
tree=ast.parse((root/'Augustus/multiplayer_limits.py').read_text(encoding='utf8'))
values=[n.value.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='MAX_ONLINE_PLAYERS' for t in n.targets) and isinstance(n.value,ast.Constant)]
assert len(values)==1 and type(values[0]) is int and 1<=values[0]<=8,'Invalid online player policy'
limits=target.parent/'CreatorLimits.cs'
limits.write_text('partial class ScenarioCreator { const int OnlinePlayerLimit = '+str(values[0])+'; }\n',encoding='utf8')
subprocess.run([str(compiler),'/nologo','/target:winexe','/platform:x64','/r:System.Windows.Forms.dll','/r:System.Drawing.dll','/r:System.Web.Extensions.dll','/out:'+str(target),*[str(source/(n+'.cs')) for n in names],str(limits)],check=True)
target.with_suffix('.exe.config').write_text("""<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <startup><supportedRuntime version="v4.0" sku=".NETFramework,Version=v4.8"/></startup>
  <runtime><AppContextSwitchOverrides value="Switch.System.IO.UseLegacyPathHandling=false;Switch.System.IO.BlockLongPaths=false"/></runtime>
</configuration>
""",encoding='utf8')
print('Built',target)

