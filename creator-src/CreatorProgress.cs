using System;
using System.Linq;
using System.Drawing;
using System.Collections;
using System.Collections.Generic;
using System.Windows.Forms;
// 황제의 순행 in the scenario editor (user 2026-11-15): the second competition mode of the victory page.
// The scenario carries every number in rules.progress and says rules.mode "imperial-progress" (format 4); the game
// checks the same ranges (Augustus/imperial_progress.py validate_spec). The demand is drawn for each progress between
// two bounds, at most one warehouse (32), and is not shown to the players before the emperor arrives.
// Also here: the fewest players a scenario starts with (rules.min_players, shown in the scenario list of the game).
partial class ScenarioCreator {
 static readonly int[] ProgressGoods={1,2,3,4,5,15,16,17,18,19};
 // key, label, lowest, highest, default
 static readonly object[][] ProgressRows={
  new object[]{"rounds","순행 횟수",1,20,6},new object[]{"start_months","첫 순행까지의 기간 (개월)",0,600,24},new object[]{"gap_months","순행 사이 기간 (개월)",0,120,3},
  new object[]{"min_bid","최저 입찰가 (Dn)",1,1000000,500},new object[]{"prepare_min","낙찰 뒤 도착까지, 최소 (개월)",1,24,2},new object[]{"prepare_max","낙찰 뒤 도착까지, 최대 (개월)",1,24,4},
  new object[]{"amount_min","요구량, 최소 (순행마다 비밀로 정함)",1,32,16},new object[]{"amount_max","요구량, 최대 (창고 1개분 32까지)",1,32,32},new object[]{"shortfall_price","부족분 1단위 값 (Dn)",0,10000,100}};
 Panel progressPanel;DataGridView progressGrid;CheckedListBox progressGoods;Label progressSummary;bool progressFilling;string progressError;
 NumericUpDown minPlayers=new NumericUpDown{Minimum=1,Maximum=6,Value=1,Width=50};Label minPlayersNote=new Label{AutoSize=true,Padding=new Padding(4,8,0,0),ForeColor=Color.FromArgb(120,60,30)};
 // 황제의 순행 never starts alone (scenario_project.min_players, lobby.py): the box cannot go below two then.
 // A box the floor raised from 1 goes back to 1 when the mode that needs two is left (2026-11-15: choosing 황제의 순행
 // and then free build left "at least 2 players" in the file, which the author never chose). A value set by hand stays.
 bool minPlayersRaised,minPlayersFlooring;
 void MinPlayersFloor(){bool two=ProgressEnabled||RaceEnabled;minPlayersFlooring=true;
  try{if(two&&minPlayers.Value<2)minPlayersRaised=true;minPlayers.Minimum=two?2:1;if(!two&&minPlayersRaised){minPlayersRaised=false;if(minPlayers.Value==2)minPlayers.Value=1;}}finally{minPlayersFlooring=false;}
  minPlayersNote.Text=two?Lang.T(RaceEnabled?"기한 경쟁은 2명 이상":"황제의 순행은 2명 이상"):"";}
 bool ProgressEnabled{get{return project!=null&&project.rules!=null&&project.rules.ContainsKey("progress")&&project.rules["progress"]!=null;}}
 static Dictionary<string,object> ProgressDefaults(){
  var d=new Dictionary<string,object>{{"version",1}};foreach(var row in ProgressRows)d[(string)row[0]]=row[4];
  d["goods"]=new List<object>{1,2,3,4,15,16,17,18};return d;
 }
 Control BuildProgressPanel(){
  var layout=new TableLayoutPanel{Dock=DockStyle.Top,ColumnCount=2,RowCount=3,Height=70+30+ProgressRows.Length*26+8+44};
  layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,60));layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,40));
  layout.RowStyles.Add(new RowStyle(SizeType.Absolute,70));layout.RowStyles.Add(new RowStyle(SizeType.Absolute,30+ProgressRows.Length*26+8));layout.RowStyles.Add(new RowStyle(SizeType.Absolute,44));
  var intro=TextLabel("황제가 순행할 때마다 후보 물품 세 가지를 공고하고, 총독들이 한 달 동안 비공개로 입찰합니다. 가장 높은 금액을 쓴 총독의 도시로 황제가 가서 세 가지 가운데 한 가지만 찾습니다.\n모두 드리면 총애 +3, 절반 이상 +1, 그보다 적으면 -1이고 부족분은 돈으로 냅니다. 모든 순행이 끝났을 때 총애가 가장 높은 총독이 승리합니다. 2명 이상이 있어야 시작합니다.");
  layout.Controls.Add(intro,0,0);layout.SetColumnSpan(intro,2);
  progressGrid=new DataGridView{Dock=DockStyle.Fill,AllowUserToAddRows=false,AllowUserToDeleteRows=false,RowHeadersVisible=false,AutoSizeColumnsMode=DataGridViewAutoSizeColumnsMode.Fill,BackgroundColor=Paper,ScrollBars=ScrollBars.None};
  progressGrid.Columns.Add("k","항목");progressGrid.Columns.Add("v","값");progressGrid.Columns[0].ReadOnly=true;progressGrid.Columns[0].FillWeight=300;progressGrid.Columns[1].DefaultCellStyle.Alignment=DataGridViewContentAlignment.MiddleRight;progressGrid.RowTemplate.Height=26;
  layout.Controls.Add(progressGrid,0,1);
  var goods=new TableLayoutPanel{Dock=DockStyle.Fill,ColumnCount=1,RowCount=2};goods.RowStyles.Add(new RowStyle(SizeType.Absolute,24));goods.RowStyles.Add(new RowStyle(SizeType.Percent,100));
  goods.Controls.Add(new Label{Text="순행 물품 (세 가지 이상)",AutoSize=true,ForeColor=Dark},0,0);
  progressGoods=new CheckedListBox{Dock=DockStyle.Fill,CheckOnClick=true,BackColor=Paper,IntegralHeight=false};foreach(int g in ProgressGoods)progressGoods.Items.Add(Lang.T(Resources[g-1]));
  goods.Controls.Add(progressGoods,0,1);layout.Controls.Add(goods,1,1);
  progressSummary=TextLabel("");layout.Controls.Add(progressSummary,0,2);layout.SetColumnSpan(progressSummary,2);
  progressGrid.CellValueChanged+=(s,e)=>{if(!progressFilling&&e.RowIndex>=0)ProgressEdited();};
  progressGoods.ItemCheck+=(s,e)=>{if(!progressFilling)BeginInvoke((MethodInvoker)(()=>ProgressEdited()));};   // the check state changes after this event
  progressPanel=new Panel{Dock=DockStyle.Fill,Visible=false,AutoScroll=true};progressPanel.Controls.Add(layout);return progressPanel;
 }
 void ProgressFill(Dictionary<string,object> rules){
  progressFilling=true;progressGrid.Rows.Clear();
  foreach(var row in ProgressRows){object v;int i=progressGrid.Rows.Add(Lang.T((string)row[1]),rules.TryGetValue((string)row[0],out v)?v:row[4]);progressGrid.Rows[i].Tag=row;}
  var chosen=new HashSet<int>();object list;if(rules.TryGetValue("goods",out list)&&list is IEnumerable)foreach(object g in (IEnumerable)list)chosen.Add(Convert.ToInt32(g));
  for(int i=0;i<ProgressGoods.Length;i++)progressGoods.SetItemChecked(i,chosen.Contains(ProgressGoods[i]));
  progressFilling=false;
 }
 Dictionary<string,object> ProgressRead(){
  if(!progressGrid.EndEdit())throw new Exception("황제의 순행 설정에 입력한 값을 확인하세요.");
  var rules=new Dictionary<string,object>{{"version",1}};
  foreach(DataGridViewRow row in progressGrid.Rows){
   var spec=(object[])row.Tag;int n;string label=Convert.ToString(row.Cells[0].Value);
   if(!int.TryParse(Convert.ToString(row.Cells[1].Value).Replace(",","").Trim(),out n))throw new Exception(label+": 정수를 입력하세요.");
   if(n<(int)spec[2]||n>(int)spec[3])throw new Exception(label+": "+((int)spec[2]).ToString("N0")+"~"+((int)spec[3]).ToString("N0")+" 범위의 정수여야 합니다.");
   rules[(string)spec[0]]=n;
  }
  if((int)rules["prepare_min"]>(int)rules["prepare_max"])throw new Exception("준비 기간의 최소가 최대보다 큽니다.");
  if((int)rules["amount_min"]>(int)rules["amount_max"])throw new Exception("요구량의 최소가 최대보다 큽니다.");
  var goods=new List<object>();for(int i=0;i<ProgressGoods.Length;i++)if(progressGoods.GetItemChecked(i))goods.Add(ProgressGoods[i]);
  if(goods.Count<3)throw new Exception("순행 물품은 서로 다른 세 가지 이상을 골라야 합니다.");
  rules["goods"]=goods;return rules;
 }
 void ProgressEdited(bool byUser=true){
  try{var rules=ProgressRead();progressError=null;if(ProgressEnabled){project.rules["progress"]=rules;if(byUser)Changed();}
   int months=(int)rules["start_months"]+(int)rules["rounds"]*(1+(int)rules["prepare_max"])+((int)rules["rounds"]-1)*(int)rules["gap_months"];
   progressSummary.Text=Lang.T("순행")+" "+rules["rounds"]+" / "+Lang.T("가장 길게 걸리는 경우")+": "+months+" "+Lang.T("개월");}
  catch(Exception e){progressError=e.Message;progressSummary.Text=e.Message;}
  progressSummary.ForeColor=progressError==null?Dark:Color.Firebrick;
 }
 // Competition with 황제의 순행 chosen: the numbers of the file, else the defaults. Any other choice: none.
 void ProgressModeChosen(bool on){
  if(project==null)return;
  if(!on){project.rules.Remove("progress");progressError=null;if(Convert.ToString(project.rules["mode"])=="imperial-progress")project.rules["mode"]="free-build";MinPlayersFloor();return;}
  if(!ProgressEnabled)project.rules["progress"]=ProgressDefaults();
  project.rules.Remove("objectives");project.rules["mode"]="imperial-progress";MinPlayersFloor();
  ProgressFill((Dictionary<string,object>)Json.Deserialize<Dictionary<string,object>>(Json.Serialize(project.rules["progress"])));ProgressEdited();
 }
 void ProgressRequireValid(){if(ProgressEnabled&&progressError!=null)throw new Exception("황제의 순행 설정: "+progressError);}
 // Free build / cooperative / competition and, within competition, which one.
 void CompetitionChosen(bool competition){
  bool progress=competition&&competitionKind.SelectedIndex==1,race=competition&&competitionKind.SelectedIndex==2;
  if(race){ThroneModeChosen(false);ProgressModeChosen(false);RaceModeChosen(true);}
  else if(progress){RaceModeChosen(false);ThroneModeChosen(false);ProgressModeChosen(true);}
  else{RaceModeChosen(false);ProgressModeChosen(false);ThroneModeChosen(competition);}
 }
 // rules.min_players in the file: only when above one, never above the seats that can play online.
 static void ApplyMinPlayersToFile(Dictionary<string,object> value){
  object rulesObject;if(!value.TryGetValue("rules",out rulesObject)||!(rulesObject is Dictionary<string,object>))return;
  var rules=(Dictionary<string,object>)rulesObject;object raw;if(!rules.TryGetValue("min_players",out raw)||raw==null){rules.Remove("min_players");return;}
  int seats=((IEnumerable)value["slots"]).Cast<object>().Count(),n=Math.Min(Convert.ToInt32(raw),Math.Min(seats,6));
  if(n<=1)rules.Remove("min_players");else rules["min_players"]=n;
 }
 void MinPlayersChanged(){
  if(!minPlayersFlooring)minPlayersRaised=false;   // chosen by hand (or read from a file)
  if(loading||project==null)return;int n=(int)minPlayers.Value;
  if(n<=1)project.rules.Remove("min_players");else project.rules["min_players"]=n;
  Changed();
 }
 // 시나리오 제작자 모드 시험 단추 (user 2026-11-17: "시나리오 제작기에서 테스트게임에서 쓸 치트 버튼을 고를수 있으면"):
 // rules.maker_tools, the keys a maker room of this scenario shows (Augustus/scenario_project.py maker_tools, the same
 // rule). Absent = every key of the mode. 황위 쟁탈전 keys only in a throne scenario, 황제의 순행 only in a progress one;
 // the file never keeps a key its mode does not have (ApplyMakerToolsToFile), so changing the mode cannot leave one.
 TabPage makerPage;CheckBox[] makerChecks;Label makerNote;bool makerFilling;
 static readonly string[] MakerTools={"money","invade","favor","goods","throne","progress"};
 static readonly string[] MakerToolNames={"자금 +10,000","침략군 부르기","호의 +10","물자 넣기 (고른 물자를 창고에 16수레)","황위 쟁탈전 시험 단추 (편집증·단계·쿠데타 결과)","황제의 순행: 다음 단계로"};
 void BuildMakerPage(){
  makerPage=new TabPage("③  제작자 모드 시험 단추"){BackColor=Paper};
  var flow=new FlowLayoutPanel{Dock=DockStyle.Fill,FlowDirection=FlowDirection.TopDown,WrapContents=false,Padding=new Padding(16,12,16,12),AutoScroll=true};
  flow.Controls.Add(new Label{Text="이 시나리오로 '시나리오 제작자 모드' 방을 열었을 때 게임 안 제작자 도구에 나올 단추를 고릅니다.",AutoSize=true,MaximumSize=new Size(900,0)});
  flow.Controls.Add(new Label{Text="일반 방에는 어떤 단추도 나오지 않습니다. 황위 쟁탈전과 황제의 순행 단추는 그 방식의 시나리오에서만 고를 수 있습니다.",AutoSize=true,MaximumSize=new Size(900,0),Padding=new Padding(0,4,0,10)});
  makerChecks=new CheckBox[MakerTools.Length];
  for(int i=0;i<MakerTools.Length;i++){makerChecks[i]=new CheckBox{Text=MakerToolNames[i],AutoSize=true,Padding=new Padding(0,2,0,2)};makerChecks[i].CheckedChanged+=(s,e)=>MakerChanged();flow.Controls.Add(makerChecks[i]);}
  makerNote=new Label{AutoSize=true,ForeColor=Color.FromArgb(120,60,30),Padding=new Padding(0,10,0,0),MaximumSize=new Size(900,0)};flow.Controls.Add(makerNote);
  makerPage.Controls.Add(flow);goalTabs.TabPages.Add(makerPage);
 }
 static bool MakerApplies(string tool,int schema,string mode){return tool=="throne"?schema==5:tool=="progress"?mode=="imperial-progress":true;}
 bool MakerApplies(string tool){if(project==null||project.rules==null)return false;object m;string mode=project.rules.TryGetValue("mode",out m)?Convert.ToString(m):"";return MakerApplies(tool,ThroneEnabled?5:4,mode);}
 List<string> MakerChosen(){object v;if(project==null||project.rules==null||!project.rules.TryGetValue("maker_tools",out v)||v==null)return null;var list=new List<string>();foreach(var x in (IEnumerable)v)list.Add(Convert.ToString(x));return list;}
 void ShowMakerTools(){
  if(makerChecks==null||project==null)return;makerFilling=true;
  try{var chosen=MakerChosen();int on=0,can=0;
   for(int i=0;i<MakerTools.Length;i++){bool applies=MakerApplies(MakerTools[i]);makerChecks[i].Enabled=applies;makerChecks[i].Checked=applies&&(chosen==null||chosen.Contains(MakerTools[i]));if(applies)can++;if(makerChecks[i].Checked)on++;}
   makerNote.Text=chosen==null?"고른 단추가 없으면 이 방식의 모든 단추를 씁니다(기본값).":on==0?"제작자 방에서도 시험 단추가 나오지 않습니다.":"고른 단추 "+on+"개 / 이 방식에서 쓸 수 있는 단추 "+can+"개";
  }finally{makerFilling=false;}
 }
 void MakerChanged(){
  if(makerFilling||project==null)return;var on=new List<string>();bool all=true;
  for(int i=0;i<MakerTools.Length;i++){if(!MakerApplies(MakerTools[i]))continue;if(makerChecks[i].Checked)on.Add(MakerTools[i]);else all=false;}
  if(all)project.rules.Remove("maker_tools");else project.rules["maker_tools"]=on.ToArray();
  Changed();ShowMakerTools();
 }
 static void ApplyMakerToolsToFile(Dictionary<string,object> value){
  object rulesObject;if(!value.TryGetValue("rules",out rulesObject)||!(rulesObject is Dictionary<string,object>))return;
  var rules=(Dictionary<string,object>)rulesObject;object raw;if(!rules.TryGetValue("maker_tools",out raw))return;
  if(raw==null){rules.Remove("maker_tools");return;}
  int schema=Convert.ToInt32(value["schema"]);object m;string mode=rules.TryGetValue("mode",out m)?Convert.ToString(m):"";
  var keep=new List<string>();foreach(var x in (IEnumerable)raw){string t=Convert.ToString(x);if(Array.IndexOf(MakerTools,t)>=0&&MakerApplies(t,schema,mode)&&!keep.Contains(t))keep.Add(t);}
  if(MakerTools.Where(t=>MakerApplies(t,schema,mode)).All(keep.Contains))rules.Remove("maker_tools");else rules["maker_tools"]=MakerTools.Where(keep.Contains).ToArray();
 }

}
