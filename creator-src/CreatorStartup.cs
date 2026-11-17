using System;
using System.IO;
using System.Text;
using System.Drawing;
using System.Diagnostics;
using System.Threading.Tasks;
using System.Windows.Forms;

partial class ScenarioCreator {
 static int StartupDataProbe() {
  EnsureGameData();
  int caller=System.Threading.Thread.CurrentThread.ManagedThreadId,worker=caller;
  var stages=new System.Collections.Generic.List<string>();
  var data=Task.Run(()=>{worker=System.Threading.Thread.CurrentThread.ManagedThreadId;return PrepareStartup(stages.Add);}).GetAwaiter().GetResult();
  if(worker==caller||stages.Count!=5||!File.Exists(data.map.image)||!File.Exists(data.map.metadata)||data.presets.terrain.Length==0||data.merged.cities.Length==0||data.scenario.slots.Length!=4||data.workspace.examples.Length==0)throw new Exception("Startup data probe failed");
  using(var bitmap=LoadMapBitmap(data.map.image)){if(bitmap.Width!=2000||bitmap.Height!=1000)throw new Exception("Startup bitmap dimensions failed");bitmap.GetPixel(100,100);}
  File.WriteAllText(Path.Combine(Root,"startup-data-results.json"),Json.Serialize(new {passed=true,stages=stages,caller=caller,worker=worker,gui_created=false,bitmap_decoded=true}),Encoding.UTF8);
  return 0;
 }
 public class StartupData {
  public MapCache map;
  public PresetCatalog presets;
  public MergedCatalog merged;
  public Scenario scenario;
  public CreatorProjectCatalog workspace;
 }
 // Only data and subprocess work here. Controls are created on the UI thread after await.
 static StartupData PrepareStartup(Action<string> progress) {
  var data=new StartupData();
  progress("1 / 5  원본 지형과 제국지도 준비\n첫 실행에는 여러 지도를 읽어 개인용 캐시를 만듭니다.");
  data.map=PrepareMap();
  progress("2 / 5  사용할 수 있는 시나리오 확인");
  data.presets=Json.Deserialize<PresetCatalog>(RunPython("creator_presets.py",""));
  progress("3 / 5  도시와 교역 목록 준비");
  data.merged=Json.Deserialize<MergedCatalog>(RunPython("creator_presets.py","--merged"));
  progress("4 / 5  새 시나리오 준비");
  data.scenario=Json.Deserialize<Scenario>(RunPython("creator_presets.py","--default 4"));
  progress("5 / 5  내 작업과 기본 제공 목록 확인");
  data.workspace=Json.Deserialize<CreatorProjectCatalog>(RunPython("creator_workspace.py","list"));
  return data;
 }
 static int RunStartup() {
  int result=0;
  using(var notice=new Form{Text="Augustus 멀티 시나리오 제작기 준비",ClientSize=new Size(540,195),FormBorderStyle=FormBorderStyle.FixedDialog,ControlBox=false,StartPosition=FormStartPosition.CenterScreen,BackColor=Paper,ForeColor=Dark,Font=new Font("Malgun Gothic",10)})
  using(var timer=new Timer{Interval=500})
  using(var context=new ApplicationContext(notice)) {
   var label=new Label{Left=20,Top=20,Width=500,Height=76,Text="시저 3 본편 폴더를 확인합니다."};
   var bar=new ProgressBar{Left=20,Top=105,Width=500,Height=20,Style=ProgressBarStyle.Marquee,MarqueeAnimationSpeed=35};
   var elapsed=new Label{Left=20,Top=140,Width=500,Height=35};
   notice.Controls.AddRange(new Control[]{label,bar,elapsed});Lang.Attach(notice);
   var watch=Stopwatch.StartNew();
   timer.Tick+=(s,e)=>{elapsed.Text="준비 중 · 경과 시간 "+(int)watch.Elapsed.TotalSeconds+"초";};
   notice.Shown+=async (s,e)=>{
    timer.Start();
    try {
     EnsureGameData();
     IProgress<string> progress=new Progress<string>(value=>label.Text=value);
     var data=await Task.Run(()=>PrepareStartup(value=>progress.Report(value)));
     label.Text="준비 완료 · 편집 화면을 열고 있습니다.";
     var editor=new ScenarioCreator(data);
     timer.Stop();
     context.MainForm=editor;
     notice.Close();
     Lang.Shown(editor).Show();
    } catch(OperationCanceledException) {notice.Close();}
    catch(Exception error) {
     result=1;timer.Stop();
     File.WriteAllText(Path.Combine(Root,"creator-error.log"),error.ToString(),Encoding.UTF8);
     LangBox.Show(notice,error.Message,"제작기 준비 오류",MessageBoxButtons.OK,MessageBoxIcon.Error);
     notice.Close();
    }
   };
   Application.Run(context);
  }
  return result;
 }
}

