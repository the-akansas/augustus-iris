using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Net.NetworkInformation;
using System.Net.Sockets;
using System.Text;
using System.Web.Script.Serialization;
using System.Windows.Forms;

/* Augustus.exe and Augustus-Network.exe (the same program under two names; build/build_launcher.py).
 * Written again from the program that shipped without its source (2026-11-16, for the public source): the same
 * options, files, dialogs and exit codes. Two differences: the Python it runs is the package's runtime\python.exe,
 * else AUGUSTUS_PYTHON, else python on the PATH (the old program fell back to one developer's folder); and what it
 * shows follows the game's display language (CreatorLang.cs, compiled in).
 *
 *   (no option)              ask for the Caesar III folder once (network-settings.json), then run network_play.py
 *   --multiplayer            the same, and the game opens the multiplayer lobby (the game's menu button)
 *   --project <scenario>     the same, with that scenario project (AUGUSTUS_MP_PROJECT)
 *   --adapter-probe          write network-adapters.json (name, IPv4 address of every working adapter)
 *   --scenario-picker <out>  file dialog: a scenario or a shared ZIP; writes {"path": ...} to <out>
 *   --dialog host|join <out> the old connection dialogs (address and port / invitation code); writes the choice to <out>
 *   --invite <file>          shows an invitation code with a copy button
 *   --settings-probe <settings> <dir>, --settings-read-probe <settings> <dir>   checks of the settings file (tests)
 * Exit codes: 0 done, 1 error (shown in a message box, or network-adapter-error.log for the probe), 2 cancelled,
 * 3 and 4 the settings probes' failures. */
class NetworkLauncher {
 class Nic {public string address;public string name;public override string ToString(){return name+" / "+address;}}
 class Saved {
  public string database{get;set;}
  public int id{get;set;}
  public string date{get;set;}
  public bool available{get;set;}
  public string room{get;set;}
  public override string ToString(){return date+" / #"+id+" / "+room;}
 }
 class Catalog {public Saved[] entries{get;set;}}

 static readonly string Root=AppDomain.CurrentDomain.BaseDirectory;
 static readonly JavaScriptSerializer Json=new JavaScriptSerializer();

 static string Q(string s){return "\""+s.Replace("\"","\\\"")+"\"";}

 static string Python(){
  string bundled=Path.Combine(Root,"runtime","python.exe");
  if(File.Exists(bundled))return bundled;
  string chosen=Environment.GetEnvironmentVariable("AUGUSTUS_PYTHON");
  return string.IsNullOrEmpty(chosen)?"python.exe":chosen;
 }

 static ProcessStartInfo RunPython(string args){
  var info=new ProcessStartInfo(Python(),"-X utf8 "+Q(Path.Combine(Root,"network_play.py"))+" "+args);
  info.UseShellExecute=false;info.CreateNoWindow=true;info.WindowStyle=ProcessWindowStyle.Hidden;info.WorkingDirectory=Root;
  info.RedirectStandardError=true;info.StandardErrorEncoding=Encoding.UTF8;
  return info;
 }

 // Working adapters other than loopback, their IPv4 addresses; Radmin VPN adapters first.
 static Nic[] Adapters(){
  return NetworkInterface.GetAllNetworkInterfaces()
   .Where(n=>n.OperationalStatus==OperationalStatus.Up&&n.NetworkInterfaceType!=NetworkInterfaceType.Loopback)
   .SelectMany(n=>n.GetIPProperties().UnicastAddresses.Where(a=>a.Address.AddressFamily==AddressFamily.InterNetwork)
    .Select(a=>new Nic{address=a.Address.ToString(),name=n.Name+" ("+n.Description+")"}))
   .OrderByDescending(n=>n.name.IndexOf("Radmin",StringComparison.OrdinalIgnoreCase)>=0)
   .ToArray();
 }

 static Form Window(string title,int height){
  var f=new Form();f.Text=title;f.ClientSize=new Size(620,height);f.StartPosition=FormStartPosition.CenterScreen;
  f.Font=new Font("Malgun Gothic",10f);f.FormBorderStyle=FormBorderStyle.FixedDialog;f.MaximizeBox=false;f.MinimizeBox=false;
  f.AutoScaleMode=AutoScaleMode.Dpi;
  return f;
 }
 static Label Text(string text,int y,int h){var l=new Label();l.Text=text;l.Left=20;l.Top=y;l.Width=580;l.Height=h;return l;}
 static Button Press(string text,int x,int y,int width){var b=new Button();b.Text=text;b.Left=x;b.Top=y;b.Width=width;b.Height=34;return b;}

 static void Save(string path,object data){File.WriteAllText(path,Json.Serialize(data),new UTF8Encoding(false));}

 // Finished joint saves (save_catalog.py).
 static Saved[] SavedGames(){
  var info=RunPython("");
  info.Arguments="-X utf8 "+Q(Path.Combine(Root,"save_catalog.py"));
  info.RedirectStandardOutput=true;info.StandardOutputEncoding=Encoding.UTF8;
  using(var p=Process.Start(info)){
   var error=p.StandardError.ReadToEndAsync();
   string output=p.StandardOutput.ReadToEnd();
   p.WaitForExit();
   if(p.ExitCode!=0)throw new Exception(error.Result);
   return Json.Deserialize<Catalog>(output).entries.Where(e=>e.available).ToArray();
  }
 }

 static int Dialog(string mode,string output){
  bool host=mode=="host";
  using(var f=Window(host?"방 만들기 - 네트워크 선택":"방 입장 - 초대 코드",host?420:340)){
   int y=host?365:285;
   var ok=Press(host?"방 만들기":"입장",380,y,105);
   var cancel=Press("취소",495,y,105);cancel.DialogResult=DialogResult.Cancel;
   f.Controls.Add(ok);f.Controls.Add(cancel);f.CancelButton=cancel;
   if(host){
    f.Controls.Add(Text("Radmin VPN에 연결한 뒤 Radmin 어댑터를 선택하세요.\n일반 LAN에서는 같은 네트워크의 어댑터를 선택할 수 있습니다.",20,50));
    var nics=new ComboBox();nics.Left=20;nics.Top=80;nics.Width=580;nics.DropDownStyle=ComboBoxStyle.DropDownList;
    nics.Items.AddRange(Adapters());
    if(nics.Items.Count>0)nics.SelectedIndex=0;
    f.Controls.Add(nics);
    f.Controls.Add(Text("사용할 포트",120,25));
    var port=new NumericUpDown();port.Left=160;port.Top=118;port.Width=120;port.Minimum=1024;port.Maximum=65535;port.Value=48921;
    f.Controls.Add(port);
    f.Controls.Add(Text("시나리오",160,25));
    var project=new TextBox();project.Left=20;project.Top=190;project.Width=470;project.ReadOnly=true;
    project.Text=Environment.GetEnvironmentVariable("AUGUSTUS_MP_PROJECT")??Path.Combine(Root,"scenarios","four-cities","scenario.json");
    f.Controls.Add(project);
    var browse=Press("찾아보기",500,186,100);
    f.Controls.Add(browse);
    browse.Click+=(o,e)=>{
     using(var pick=new OpenFileDialog()){
      pick.Filter=Lang.T("시나리오 프로젝트")+"|*.json";pick.InitialDirectory=Path.Combine(Root,"scenarios");
      if(pick.ShowDialog()==DialogResult.OK)project.Text=pick.FileName;
     }
    };
    var resume=new CheckBox();resume.Text="공동 저장 이어하기";resume.Left=20;resume.Top=235;resume.Width=250;
    f.Controls.Add(resume);
    var saved=new ComboBox();saved.Left=20;saved.Top=268;saved.Width=580;saved.DropDownStyle=ComboBoxStyle.DropDownList;saved.Enabled=false;
    f.Controls.Add(saved);
    resume.CheckedChanged+=(o,e)=>{
     if(resume.Checked){
      try{
       saved.Items.Clear();saved.Items.AddRange(SavedGames());
       if(saved.Items.Count>0)saved.SelectedIndex=0;
       else{LangBox.Show("완료된 공동 저장이 없습니다.");resume.Checked=false;}
      }catch(Exception error){LangBox.Show(error.Message);resume.Checked=false;}
     }
     saved.Enabled=resume.Checked;browse.Enabled=!resume.Checked;
    };
    f.Controls.Add(Text("방 생성 후 대기실의 '초대 코드'를 상대방에게 전달하세요.",318,30));
    ok.Click+=(o,e)=>{
     var nic=nics.SelectedItem as Nic;
     if(nic==null){LangBox.Show("사용 가능한 네트워크가 없습니다. Radmin 연결을 확인하세요.");return;}
     var game=resume.Checked?saved.SelectedItem as Saved:null;
     Save(output,new{mode="host",address=nic.address,port=(int)port.Value,project=project.Text,restore=game!=null?game.database:null,save_id=game!=null?(int?)game.id:null});
     f.DialogResult=DialogResult.OK;f.Close();
    };
   }else{
    f.Controls.Add(Text("방장이 보내 준 초대 코드를 붙여넣으세요.\n두 PC 모두 같은 Radmin 네트워크와 같은 게임 빌드를 사용해야 합니다.",20,55));
    var code=new TextBox();code.Left=20;code.Top=85;code.Width=580;code.Height=180;code.Multiline=true;code.ScrollBars=ScrollBars.Vertical;code.MaxLength=4096;
    f.Controls.Add(code);
    ok.Click+=(o,e)=>{
     if(!code.Text.Trim().StartsWith("AUGMP1.")){LangBox.Show("초대 코드를 확인하세요.");return;}
     Save(output,new{mode="join",code=code.Text.Trim()});
     f.DialogResult=DialogResult.OK;f.Close();
    };
   }
   return Lang.Shown(f).ShowDialog()==DialogResult.OK?0:2;
  }
 }

 static void Invitation(string path){
  using(var f=Window("방 초대 코드",290)){
   f.Controls.Add(Text("이 코드를 함께 플레이할 사람에게 보내세요.\n방장 권한은 포함되지 않습니다. 새 방을 만들면 코드도 바뀝니다.",20,55));
   var text=new TextBox();text.Left=20;text.Top=85;text.Width=580;text.Height=125;text.Multiline=true;text.ReadOnly=true;text.ScrollBars=ScrollBars.Vertical;
   text.Text=File.ReadAllText(path);
   f.Controls.Add(text);
   var copy=Press("복사",380,235,105);
   copy.Click+=(o,e)=>{Clipboard.SetText(text.Text);copy.Text="복사됨";};
   var close=Press("닫기",495,235,105);close.DialogResult=DialogResult.OK;
   f.Controls.Add(copy);f.Controls.Add(close);f.CancelButton=close;
   Lang.Shown(f).ShowDialog();
  }
 }

 // The Caesar III folder kept in network-settings.json (or its .backup), when it still holds c3.sg2.
 static string SavedPath(string path){
  foreach(string file in new[]{path,path+".backup"}){
   try{
    var data=Json.Deserialize<Dictionary<string,object>>(File.ReadAllText(file,Encoding.UTF8));
    object value;
    if(data.TryGetValue("game_data",out value)&&value is string&&File.Exists(Path.Combine((string)value,"c3.sg2")))return (string)value;
   }catch{}
  }
  return null;
 }

 // Keeps the other keys; written through a temporary file, the previous file kept as .backup.
 static void StorePath(string settings,string dir){
  var data=new Dictionary<string,object>();
  try{data=Json.Deserialize<Dictionary<string,object>>(File.ReadAllText(settings,Encoding.UTF8));}catch{}
  if(data==null)data=new Dictionary<string,object>();
  data["game_data"]=dir;
  string temp=settings+"."+Guid.NewGuid().ToString("N")+".tmp";
  File.WriteAllText(temp,Json.Serialize(data),new UTF8Encoding(false));
  try{
   if(File.Exists(settings))File.Replace(temp,settings,settings+".backup");
   else File.Move(temp,settings);
  }finally{if(File.Exists(temp))File.Delete(temp);}
 }

 static string GameData(){
  string settings=Path.Combine(Root,"network-settings.json");
  string path=SavedPath(settings);
  if(path!=null)return path;
  using(var pick=new FolderBrowserDialog()){
   pick.Description=Lang.T("시저 3 본편 C3 폴더를 선택하세요. (c3.sg2 파일이 있는 폴더)");pick.ShowNewFolderButton=false;
   if(pick.ShowDialog()!=DialogResult.OK)return null;
   path=pick.SelectedPath;
   if(!File.Exists(Path.Combine(path,"c3.sg2")))throw new Exception("선택한 폴더에 c3.sg2가 없습니다. 시저 3 본편 폴더를 선택하세요.");
   try{StorePath(settings,path);}
   catch(Exception error){throw new Exception("본편 경로를 저장하지 못했습니다. 압축을 완전히 풀고 쓰기 가능한 폴더에서 실행해 주세요.\n"+error.Message);}
   return path;
  }
 }

 [STAThread]
 static int Main(string[] args){
  try{
   if(args.Length==1&&args[0]=="--adapter-probe"){
    Save(Path.Combine(Root,"network-adapters.json"),Adapters().Select(n=>new{name=n.name,address=n.address}).ToArray());
    return 0;
   }
   if(args.Length==3&&args[0]=="--settings-probe"){StorePath(args[1],args[2]);return SavedPath(args[1])!=args[2]?3:0;}
   if(args.Length==3&&args[0]=="--settings-read-probe")return SavedPath(args[1])==args[2]?0:4;
   Application.EnableVisualStyles();
   Lang.EditorChoice=false;Lang.Init(Root,false);
   if(args.Length==2&&args[0]=="--scenario-picker"){
    using(var pick=new OpenFileDialog()){
     pick.Title=Lang.T("시나리오 가져오기");pick.Filter=Lang.T("시나리오 또는 공유 ZIP")+"|*.json;*.zip";pick.CheckFileExists=true;
     if(pick.ShowDialog()!=DialogResult.OK)return 2;
     Save(args[1],new{path=pick.FileName});
     return 0;
    }
   }
   if(args.Length==3&&args[0]=="--dialog")return Dialog(args[1],args[2]);
   if(args.Length==2&&args[0]=="--invite"){Invitation(args[1]);return 0;}
   if(args.Length==2&&args[0]=="--project"&&File.Exists(args[1]))Environment.SetEnvironmentVariable("AUGUSTUS_MP_PROJECT",Path.GetFullPath(args[1]));
   else if(args.Length==1&&args[0]=="--multiplayer")Environment.SetEnvironmentVariable("AUGUSTUS_MP_OPEN_LOBBY","1");
   else if(args.Length!=0)throw new Exception("잘못된 실행 옵션입니다.");
   string data=GameData();
   if(data==null)return 0;
   using(var p=Process.Start(RunPython("--game-data "+Q(data)))){
    string error=p.StandardError.ReadToEnd();
    p.WaitForExit();
    if(p.ExitCode!=0){
     File.WriteAllText(Path.Combine(Root,"network-last-error.log"),error,Encoding.UTF8);
     throw new Exception("네트워크 실행을 마치지 못했습니다. network-last-error.log를 확인하세요.\n"+(error.Length>600?error.Substring(error.Length-600):error));
    }
   }
   return 0;
  }catch(Exception error){
   if(args.Length==1&&args[0]=="--adapter-probe"){File.WriteAllText(Path.Combine(Root,"network-adapter-error.log"),error.ToString());return 1;}
   LangBox.Show(error.Message,"아우구스투스 멀티플레이",MessageBoxButtons.OK,MessageBoxIcon.Error);
   return 1;
  }
 }
}
