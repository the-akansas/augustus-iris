using System;
using System.IO;
using System.Linq;
using System.Drawing;
using System.Windows.Forms;

public class CreatorProjectEntry {public string path,title,modified;public int players;public bool recent;}
public class CreatorProjectCatalog {public string directory;public CreatorProjectEntry[] entries,examples;}
partial class ScenarioCreator {
 string currentProjectPath;
 CreatorProjectCatalog initialWorkspace;
 CreatorProjectCatalog WorkspaceCatalog(){if(initialWorkspace!=null){var ready=initialWorkspace;initialWorkspace=null;return ready;}return Json.Deserialize<CreatorProjectCatalog>(RunPython("creator_workspace.py","list"));}
 string WorkspaceDirectory(){return WorkspaceCatalog().directory;}
 void RememberProject(string path){if(IsExample(path))return;try{RunPython("creator_workspace.py","remember "+Quote(Path.GetFullPath(path)));}catch{status.Text+=" / 최근 작업 목록에 기록하지 못했습니다.";}}
 string ProjectFileName(string extension){string name=string.IsNullOrWhiteSpace(title.Text)?"새 시나리오":title.Text.Trim();foreach(char c in Path.GetInvalidFileNameChars())name=name.Replace(c,'_');name=name.TrimEnd(' ','.');if(name.Length>60)name=name.Substring(0,60);return (name.Length==0?"시나리오":name)+extension;}
 bool IsExample(string path){return Path.GetFullPath(path).StartsWith(Path.GetFullPath(Path.Combine(Root,"scenarios"))+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase);}
 // A built-in scenario and the new-scenario template are written in Korean. In another editor language their own
 // texts (title, introduction, start message, seat hints) are shown and saved in that language (user 2026-11-14).
 // A person's own files are never changed this way.
 static void LocalizeTexts(Scenario data){
  if(Lang.Code=="ko"||data==null)return;
  data.title=Lang.T(data.title);data.briefing=Lang.T(data.briefing);
  if(data.start_message!=null){
   data.start_message.common=Lang.T(data.start_message.common);
   if(data.start_message.per_city!=null)foreach(string key in new System.Collections.Generic.List<string>(data.start_message.per_city.Keys))data.start_message.per_city[key]=Lang.T(data.start_message.per_city[key]);
  }
  if(data.slots!=null)foreach(var slot in data.slots)slot.role_hint=Lang.T(slot.role_hint);
 }
 bool OpenProject(string path,bool confirm=true){
  if(confirm&&!Discard())return false;
  // A throne scenario made with the earlier trial rules cannot run any more: offer the standard preset, never change it unasked.
  string source=path;var first=Json.Deserialize<Scenario>(File.ReadAllText(path,System.Text.Encoding.UTF8));
  if(first.schema==5&&first.rules!=null&&first.rules.ContainsKey("throne")&&ThroneRulesOutdated(first.rules["throne"])){
   if(LangBox.Show(this,"이 황위 쟁탈전 시나리오는 이전 시험 규칙으로 만들어져 지금 게임에서 실행할 수 없습니다.\n황위 수치를 표준 프리셋으로 바꿔서 열까요? 원본 파일은 저장하기 전까지 바뀌지 않습니다.","황위 쟁탈전",MessageBoxButtons.YesNo,MessageBoxIcon.Question,MessageBoxDefaultButton.Button2)!=DialogResult.Yes)return false;
   var raw=Json.Deserialize<System.Collections.Generic.Dictionary<string,object>>(File.ReadAllText(path,System.Text.Encoding.UTF8));((System.Collections.Generic.Dictionary<string,object>)raw["rules"])["throne"]=ThronePresets()["standard"];
   source=Path.Combine(Scratch(),"augustus-throne-open-"+Guid.NewGuid().ToString("N")+".json");File.WriteAllText(source,Json.Serialize(raw),new System.Text.UTF8Encoding(false));
  }
  Check(source,"");var data=Json.Deserialize<Scenario>(File.ReadAllText(source,System.Text.Encoding.UTF8));if(source!=path)try{File.Delete(source);}catch{}
  if(data.schema<3 && LangBox.Show(this,"이전 형식을 가져오면 임무 규칙이 초기화되고 공통 시작 자금이 적용됩니다. 원본을 보존하려면 다른 이름으로 저장하세요. 가져올까요?","이전 시나리오",MessageBoxButtons.YesNo,MessageBoxIcon.Question,MessageBoxDefaultButton.Button2)!=DialogResult.Yes)return false;
  Upgrade(data);if(IsExample(path))LocalizeTexts(data);Adopt(data);currentProjectPath=IsExample(path)?null:Path.GetFullPath(path);status.Text="열었습니다: "+path;RememberProject(path);return true;
 }
 void SaveAsDialog(){RequireGoalsForSave();using(var dialog=new SaveFileDialog{Title=Lang.T("시나리오 작업 폴더에 저장"),InitialDirectory=WorkspaceDirectory(),Filter=Lang.T("작업 시나리오 (*.json)|*.json"),DefaultExt="json",AddExtension=true,RestoreDirectory=true,FileName=ProjectFileName(".json"),OverwritePrompt=true})if(dialog.ShowDialog(this)==DialogResult.OK)Save(dialog.FileName);}
 const string ShareExplanation="공유 ZIP은 다른 사람에게 시나리오를 전달하는 파일입니다.\n\n파일로 옮길 때: 작업 폴더의 프로젝트 JSON을 복사하세요. 기본 작업 폴더는 게임 설치 폴더의 creator-projects이며 변경했다면 선택한 작업 폴더를 사용합니다.\n지도 편집기에서 저장한 .mapx는 제작기로 가져와 프로젝트에 반영한 뒤 공유하세요.\n\n포함: 제국지도 배치, 플레이어 도시, 시작 자금과 목표, 교역·건설 설정, 가져온 편집 지도.\n미포함: 게임 실행 파일, 시저 3 본편 그림·음악·영상, 플레이 중인 공동 저장.\n\n받은 사람은 제작기의 ‘공유 ZIP 가져오기’로 작업 폴더에 추가할 수 있습니다. 원본 작업 파일은 그대로 유지됩니다.\n실행하려면 같은 게임 배포본과 각 PC의 시저 3 본편이 필요합니다. 게임 적용 검사는 별도로 진행하세요.";
 void ShowShareHelp(){LangBox.Show(this,ShareExplanation,"공유 ZIP 안내",MessageBoxButtons.OK,MessageBoxIcon.Information);}
 void ImportSharedProject(){using(var dialog=new OpenFileDialog{Title=Lang.T("공유 시나리오 가져오기"),InitialDirectory=WorkspaceDirectory(),Filter=Lang.T("공유 시나리오 (*.zip)|*.zip"),RestoreDirectory=true})if(dialog.ShowDialog(this)==DialogResult.OK){if(!Discard())return;var result=Json.Deserialize<System.Collections.Generic.Dictionary<string,string>>(RunPython("creator_workspace.py","import "+Quote(dialog.FileName)));OpenProject(result["path"],false);}}
 void DiscardProject(string path,IWin32Window owner){
  bool inside=Path.GetFullPath(path).StartsWith(Path.GetFullPath(WorkspaceDirectory())+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase);
  string ask=inside?Lang.T("이 시나리오를 목록에서 지울까요? 파일은 작업 폴더의 deleted-scenarios 폴더로 옮겨지며(백업 파일 포함), 거기서 다시 꺼낼 수 있습니다."):Lang.T("이 시나리오를 최근 목록에서 뺄까요? 작업 폴더 밖의 파일이라 파일 자체는 그대로 둡니다.");
  if(!NonInteractive&&LangBox.Show(owner,Path.GetFileName(path)+"\n\n"+ask,"목록에서 지우기",MessageBoxButtons.YesNo,MessageBoxIcon.Question,MessageBoxDefaultButton.Button2)!=DialogResult.Yes)return;
  var result=Json.Deserialize<System.Collections.Generic.Dictionary<string,object>>(RunPython("creator_workspace.py","discard "+Quote(path)));
  if(currentProjectPath!=null&&string.Equals(Path.GetFullPath(currentProjectPath),Path.GetFullPath(path),StringComparison.OrdinalIgnoreCase)&&result!=null&&result["moved"]!=null){currentProjectPath=null;dirty=true;}   /* still open: the next save asks for a name */
  status.Text=result!=null&&result["moved"]!=null?Lang.T("목록에서 지우고 옮겼습니다")+": "+result["moved"]:Lang.T("최근 목록에서 뺐습니다")+": "+path;
 }
 // Old .bak copies a save leaves next to the file: the newest few stay (user 2026-11-15: they piled up without end).
 static void PruneBackups(string path,int keep=5){
  try{var dir=Path.GetDirectoryName(Path.GetFullPath(path));var old=new DirectoryInfo(dir).GetFiles(Path.GetFileName(path)+".*.bak").OrderByDescending(f=>f.LastWriteTimeUtc).Skip(keep).ToList();foreach(var f in old)try{f.Delete();}catch{}}catch{}
 }
 // The editor's own leftovers in creator-cache (previews, checks, editor copies with nothing saved): in the background.
 void TidyCache(){if(NonInteractive)return;System.Threading.ThreadPool.QueueUserWorkItem(_=>{try{RunPython("creator_workspace.py","tidy");}catch{}});}
 void ShowProjectLibrary(){
  using(var library=new Form{Text="내 작업과 기본 제공 시나리오",ClientSize=new Size(900,530),MinimumSize=new Size(760,420),StartPosition=FormStartPosition.CenterParent,Font=Font,BackColor=Paper}){
   var layout=new TableLayoutPanel{Dock=DockStyle.Fill,ColumnCount=1,RowCount=5,Padding=new Padding(14)};library.Controls.Add(layout);
   layout.RowStyles.Add(new RowStyle(SizeType.Absolute,42));layout.RowStyles.Add(new RowStyle(SizeType.Absolute,36));layout.RowStyles.Add(new RowStyle(SizeType.Percent,100));layout.RowStyles.Add(new RowStyle(SizeType.Absolute,44));layout.RowStyles.Add(new RowStyle(SizeType.Absolute,38));
   var folder=new Label{Dock=DockStyle.Fill,AutoEllipsis=true};layout.Controls.Add(folder,0,0);
   var searchRow=new TableLayoutPanel{Dock=DockStyle.Fill,ColumnCount=3};searchRow.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,55));searchRow.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));searchRow.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,150));searchRow.Controls.Add(new Label{Text="검색",Dock=DockStyle.Fill},0,0);var search=new TextBox{Dock=DockStyle.Fill};search.AccessibleName="시나리오 이름 검색";searchRow.Controls.Add(search,1,0);var scope=new ComboBox{Dock=DockStyle.Fill,DropDownStyle=ComboBoxStyle.DropDownList};scope.Items.AddRange(new object[]{"내 작업","기본 제공"});scope.SelectedIndex=0;searchRow.Controls.Add(scope,2,0);layout.Controls.Add(searchRow,0,1);
   var list=new ListView{Dock=DockStyle.Fill,View=View.Details,FullRowSelect=true,MultiSelect=false,HideSelection=false};list.Columns.Add("시나리오",240);list.Columns.Add("인원",95);list.Columns.Add("수정일",140);list.Columns.Add("파일 위치",355);layout.Controls.Add(list,0,2);
   CreatorProjectCatalog catalog=null;var hint=new Label{Dock=DockStyle.Fill};layout.Controls.Add(hint,0,4);
   Action filter=()=>{list.Items.Clear();var entries=scope.SelectedIndex==1?catalog.examples:catalog.entries;folder.Text=scope.SelectedIndex==1?"배포본에 포함된 기본 시나리오입니다. 수정 후 다른 이름으로 저장하면 내 작업에 추가됩니다.":"작업 폴더: "+catalog.directory;hint.Text=scope.SelectedIndex==1?"공동 저장은 플레이 진행 파일이므로 제작기 목록에는 표시하지 않습니다.":"내 작업이 없으면 기본 제공에서 시나리오를 열어 다른 이름으로 저장하세요. 공동 저장은 게임에서 이어갑니다.";foreach(var entry in entries??new CreatorProjectEntry[0]){if(search.Text.Length>0&&entry.title.IndexOf(search.Text,StringComparison.CurrentCultureIgnoreCase)<0&&entry.path.IndexOf(search.Text,StringComparison.CurrentCultureIgnoreCase)<0)continue;var row=new ListViewItem(new[]{entry.title,entry.players.ToString(),entry.modified,entry.path}){Tag=entry};list.Items.Add(row);}Lang.Refresh(list);};
   Action refresh=()=>{catalog=WorkspaceCatalog();folder.Text="작업 폴더: "+catalog.directory;filter();};
   var actions=new FlowLayoutPanel{Dock=DockStyle.Fill,WrapContents=false};layout.Controls.Add(actions,0,3);
   var open=Button("선택한 시나리오 열기",()=>{if(list.SelectedItems.Count==1&&OpenProject(((CreatorProjectEntry)list.SelectedItems[0].Tag).path))library.Close();},175);actions.Controls.Add(open);open.Enabled=false;
   actions.Controls.Add(Button("작업 폴더 변경",()=>{using(var dialog=new FolderBrowserDialog{Description=Lang.T("시나리오 작업 전용 폴더를 선택하세요."),SelectedPath=catalog.directory,ShowNewFolderButton=true})if(dialog.ShowDialog(library)==DialogResult.OK){RunPython("creator_workspace.py","folder "+Quote(dialog.SelectedPath));refresh();}},140));
   actions.Controls.Add(Button("공유 ZIP 가져오기",()=>{ImportSharedProject();refresh();},155));
   /* off the list again (user 2026-11-15): a file in the work folder goes to deleted-scenarios (with its .bak copies), a file elsewhere only leaves the list */
   var discard=Button("목록에서 지우기",()=>{if(list.SelectedItems.Count!=1||scope.SelectedIndex==1)return;var entry=(CreatorProjectEntry)list.SelectedItems[0].Tag;DiscardProject(entry.path,library);refresh();},140);actions.Controls.Add(discard);discard.Enabled=false;
   actions.Controls.Add(Button("새로 고침",()=>refresh(),100));
   var close=Button("닫기",()=>library.Close(),80);actions.Controls.Add(close);library.CancelButton=close;library.AcceptButton=open;
   scope.SelectedIndexChanged+=(s,e)=>filter();
   search.TextChanged+=(s,e)=>filter();list.SelectedIndexChanged+=(s,e)=>{open.Enabled=list.SelectedItems.Count==1;discard.Enabled=open.Enabled&&scope.SelectedIndex==0;};list.DoubleClick+=(s,e)=>{if(open.Enabled)open.PerformClick();};
   refresh();Lang.Shown(library).ShowDialog(this);
  }
 }
}
