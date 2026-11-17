using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Text;
using System.Web.Script.Serialization;
using System.Windows.Forms;

/* The joint autosave interval of the host (multiplayer-settings.json, autosave_seconds; read by autosave_policy.py).
 * Written again from the program that shipped without its source as 멀티저장설정.exe (2026-11-16, for the public
 * source): the same window, choices and file handling; what it shows follows the game's display language
 * (CreatorLang.cs, compiled in). build/build_launcher.py builds it. */
class AutosaveSettings : Form {
 readonly ComboBox choice=new ComboBox();
 readonly Label message=new Label();
 readonly string file=Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"multiplayer-settings.json");
 readonly JavaScriptSerializer json=new JavaScriptSerializer();
 readonly int[] seconds={0,300,600,1200,1800};

 AutosaveSettings(){
  Text="멀티플레이 자동저장";ClientSize=new Size(510,245);Font=new Font("Malgun Gothic",10f);
  FormBorderStyle=FormBorderStyle.FixedDialog;MaximizeBox=false;
  Controls.Add(new Label{Text="자동 공동저장 간격 (방장일 때 적용)",Location=new Point(20,20),Size=new Size(460,25)});
  choice.SetBounds(20,55,460,30);choice.DropDownStyle=ComboBoxStyle.DropDownList;
  choice.Items.AddRange(new object[]{"끄기 — 기본값","5분마다","10분마다","20분마다","30분마다"});
  choice.SelectedIndex=0;
  Controls.Add(choice);
  try{
   var data=json.Deserialize<Dictionary<string,object>>(File.ReadAllText(file));
   int index=Array.IndexOf(seconds,Convert.ToInt32(data["autosave_seconds"]));
   if(index>=0)choice.SelectedIndex=index;
  }catch(Exception){}
  Controls.Add(new Label{Text="끄면 자동 복구 지점이 갱신되지 않습니다. 필요할 때 수동 저장하세요.\n거래·퇴장 등에 필요한 별도 저장은 이 설정으로 꺼지지 않습니다.",Location=new Point(20,100),Size=new Size(470,55)});
  var save=new Button{Text="저장",Location=new Point(350,165),Size=new Size(130,32)};
  save.Click+=(s,e)=>Save();
  Controls.Add(save);
  message.SetBounds(20,205,470,30);
  Controls.Add(message);
 }

 // Keeps the other keys; written through a temporary file, the previous file kept as .backup.
 void Save(){
  try{
   var data=new Dictionary<string,object>();
   if(File.Exists(file)){
    try{data=json.Deserialize<Dictionary<string,object>>(File.ReadAllText(file));if(data==null)throw new FormatException();}
    catch(Exception){throw new InvalidDataException("설정 파일을 읽지 못했습니다. 기존 파일을 보존하고 확인해 주세요.");}
   }
   data["autosave_seconds"]=seconds[choice.SelectedIndex];
   string temp=file+"."+Guid.NewGuid().ToString("N")+".tmp";
   try{
    File.WriteAllText(temp,json.Serialize(data),new UTF8Encoding(false));
    if(File.Exists(file))File.Replace(temp,file,file+".backup");
    else File.Move(temp,file);
   }finally{if(File.Exists(temp))File.Delete(temp);}
   message.Text="저장했습니다. 다음 설정 확인 때 적용됩니다.";
  }catch(Exception error){message.Text="저장 실패: "+error.Message;}
 }

 [STAThread]
 static void Main(){
  Application.EnableVisualStyles();
  Lang.EditorChoice=false;Lang.Init(AppDomain.CurrentDomain.BaseDirectory,false);
  Application.Run(Lang.Shown(new AutosaveSettings()));
 }
}
