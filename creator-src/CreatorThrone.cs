using System;
using System.IO;
using System.Linq;
using System.Drawing;
using System.Collections;
using System.Collections.Generic;
using System.Windows.Forms;
// Race for the Throne in the scenario editor (confirmed plan 2026-11-14, docs/황위-쟁탈전-확정안-20261114.md).
// The scenario carries the whole rule set in rules.throne; the game reads every number from it (throne_rules.py).
// Here: on/off, three presets (standard, short, long), and every number under "세부 설정". The presets and the check
// of an edited set come from throne_rules.py (--presets, --validate): one source for the editor and the game.
// Fixed: the five stage names (translations), who is told what, anonymity, how the emperor wakes up. The expedition
// cannot be switched off.
partial class ScenarioCreator {
 Dictionary<string,Dictionary<string,object>> thronePresets;
 static readonly string[] ThronePresetNames={"standard","short","long"};
 static readonly string[] ThronePresetLabels={"표준","짧은 판 (지원금과 공물 0.5배, 도전 간격 1개월)","긴 판 (지원금과 공물 1.5배, 도전 간격 3개월)","사용자 설정"};
 static readonly string[][] ThroneCommon={   // key (in 'expedition' when it starts with x.), label
  new[]{"monthly_paranoia","매달 오르는 편집증"},new[]{"failure_paranoia","쿠데타 실패 시 모두의 편집증"},new[]{"failure_percent","실패 뒤 최소 지원금 인상 (%)"},
  new[]{"attempt_months","쿠데타 도전 간격 (개월)"},new[]{"gift_price","충성선물 1점 값, 기준 하한까지 (Dn)"},new[]{"gift_price_below","충성선물 1점 값, 그 아래 (Dn)"},
  new[]{"x.march_months","원정 행군 기간 (개월, 공물 가능)"},new[]{"x.siege_months","도착 후 격퇴 기한 (개월)"},new[]{"x.cooldown_months","원정 뒤 유예 (개월)"},
  new[]{"x.tribute_reduction","공물을 바치면 편집증 감소"},new[]{"x.victory_reduction","황제군을 격파하면 편집증 감소"},new[]{"x.sack_reduction","약탈당하면 편집증 감소"},
  new[]{"x.army_initial","황제군 첫 규모 (명)"},new[]{"x.army_increment","원정마다 늘어나는 규모 (명)"},new[]{"x.army_cap","황제군 최대 규모 (명)"}};
 bool ThroneEnabled{get{return project!=null&&project.rules!=null&&project.rules.ContainsKey("throne")&&project.rules["throne"]!=null;}}
 Dictionary<string,Dictionary<string,object>> ThronePresets(){
  if(thronePresets==null)thronePresets=Json.Deserialize<Dictionary<string,Dictionary<string,object>>>(RunPython("throne_rules.py","--presets"));
  return thronePresets;
 }
 static Dictionary<string,object> ThroneCopy(object rules){return Json.Deserialize<Dictionary<string,object>>(Json.Serialize(rules));}
 // The rule set of a file made before the confirmed plan (the expedition had a preparation time): cannot run any more.
 static bool ThroneRulesOutdated(object rules){
  var r=rules as Dictionary<string,object>;if(r==null)return true;object x;
  if(!r.TryGetValue("expedition",out x)||!(x is Dictionary<string,object>))return true;
  return !((Dictionary<string,object>)x).ContainsKey("march_months")||!((Dictionary<string,object>)x).ContainsKey("sack_reduction");
 }
 // Working files stay inside the unpacked folder (user 2026-11-14): never the system temp folder.
 static string Scratch(){string d=Path.Combine(Root,"creator-cache");Directory.CreateDirectory(d);return d;}
 string ThroneValidate(Dictionary<string,object> rules,out string summary,out string preset){
  string file=Path.Combine(Scratch(),"augustus-throne-"+Guid.NewGuid().ToString("N")+".json");summary=preset=null;
  try{
   File.WriteAllText(file,Json.Serialize(rules),new System.Text.UTF8Encoding(false));
   var answer=Json.Deserialize<Dictionary<string,object>>(RunPython("throne_rules.py","--validate "+Quote(file)));
   if(!(bool)answer["valid"])return Convert.ToString(answer["error"]);
   summary=Convert.ToString(answer["summary"]);preset=answer["preset"]==null?null:Convert.ToString(answer["preset"]);return null;
  }finally{try{File.Delete(file);}catch{}}
 }
 // Written into the file: format 5, the mode, Rome's place (rome-capital.json). Without rules.throne nothing changes.
 static void ApplyThroneToFile(Dictionary<string,object> value){
  object rulesObject;if(!value.TryGetValue("rules",out rulesObject)||!(rulesObject is Dictionary<string,object>))return;
  var rules=(Dictionary<string,object>)rulesObject;object throne;
  if(!rules.TryGetValue("throne",out throne)||throne==null){rules.Remove("throne");return;}
  var spec=RomeCapital.Spec;if(spec==null)throw new Exception("로마의 위치 자료(rome-capital.json)를 읽지 못해 황위 쟁탈전 시나리오를 저장할 수 없습니다.");
  value["schema"]=5;rules["mode"]="race-for-throne";rules.Remove("objectives");
  ((Dictionary<string,object>)value["empire"])["rome"]=new Dictionary<string,object>{{"id","rome"},{"x",spec.x},{"y",spec.y}};
 }
 // Race for the Throne is one of the competition modes of the victory page (user 2026-11-14: free build, cooperative,
 // competition), not a separate button: choosing 경쟁 · 황위 쟁탈전 shows these settings in the page itself.
 // Every valid edit is kept in rules.throne at once; an invalid table blocks saving (ThroneRequireValid).
 Panel thronePanel;DataGridView throneStages,throneCommon,throneCommon2;ComboBox thronePreset;Label throneSummary;bool throneFilling;string throneError;
 static readonly string[] ThroneStageColumns={"완료 단계","다음 쿠데타","최소 지원금 (Dn)","성공률 기본 (%)","성공률 상한 (%)","기준 하한","선물 최저치","철수 공물 (Dn)"};
 Control BuildThronePanel(){
  // Fixed heights inside a scrolling panel, the common items in two side-by-side tables, so no row is cut off
  // on a small window (user 2026-11-14: the detail rows were clipped); a larger window shows everything at once.
  int commonRows=(ThroneCommon.Length+1)/2,commonHeight=30+commonRows*26+4;
  var layout=new TableLayoutPanel{Dock=DockStyle.Top,ColumnCount=1,RowCount=5,Height=52+36+176+commonHeight+44+8};
  layout.RowStyles.Add(new RowStyle(SizeType.Absolute,52));layout.RowStyles.Add(new RowStyle(SizeType.Absolute,36));layout.RowStyles.Add(new RowStyle(SizeType.Absolute,176));
  layout.RowStyles.Add(new RowStyle(SizeType.Absolute,commonHeight));layout.RowStyles.Add(new RowStyle(SizeType.Absolute,44));
  layout.Controls.Add(TextLabel("5단계 쿠데타를 먼저 끝낸 총독이 황제가 되고 그 순간 판이 끝납니다. 공동 목표는 쓰지 않습니다.\n단계 이름, 알림 규칙, 익명 원칙은 바꿀 수 없습니다. 황제의 징벌 원정은 항상 켜져 있습니다."),0,0);
  var top=new FlowLayoutPanel{Dock=DockStyle.Fill};top.Controls.Add(new Label{Text="프리셋",AutoSize=true,Padding=new Padding(0,6,8,0)});
  thronePreset=new ComboBox{DropDownStyle=ComboBoxStyle.DropDownList,Width=420};foreach(var label in ThronePresetLabels)thronePreset.Items.Add(label);thronePreset.SelectedIndex=0;   /* never empty, also before a throne scenario is open (the editor check wants every list chosen) */top.Controls.Add(thronePreset);layout.Controls.Add(top,0,1);
  throneStages=new DataGridView{Dock=DockStyle.Fill,AllowUserToAddRows=false,AllowUserToDeleteRows=false,RowHeadersVisible=false,AutoSizeColumnsMode=DataGridViewAutoSizeColumnsMode.Fill,BackgroundColor=Paper};
  for(int i=0;i<ThroneStageColumns.Length;i++){throneStages.Columns.Add("s"+i,ThroneStageColumns[i]);if(i<2)throneStages.Columns[i].ReadOnly=true;else throneStages.Columns[i].DefaultCellStyle.Alignment=DataGridViewContentAlignment.MiddleRight;}
  throneStages.Columns[0].FillWeight=55;throneStages.Columns[1].FillWeight=150;throneStages.RowTemplate.Height=28;layout.Controls.Add(throneStages,0,2);
  Func<DataGridView> commonGrid=()=>{var g=new DataGridView{Dock=DockStyle.Fill,AllowUserToAddRows=false,AllowUserToDeleteRows=false,RowHeadersVisible=false,AutoSizeColumnsMode=DataGridViewAutoSizeColumnsMode.Fill,BackgroundColor=Paper,ScrollBars=ScrollBars.None};
   g.Columns.Add("k","항목");g.Columns.Add("v","값");g.Columns[0].ReadOnly=true;g.Columns[0].FillWeight=300;g.Columns[1].DefaultCellStyle.Alignment=DataGridViewContentAlignment.MiddleRight;g.RowTemplate.Height=26;return g;};
  throneCommon=commonGrid();throneCommon2=commonGrid();
  var pair=new TableLayoutPanel{Dock=DockStyle.Fill,ColumnCount=2,RowCount=1,Margin=new Padding(0)};pair.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,50));pair.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,50));
  pair.Controls.Add(throneCommon,0,0);pair.Controls.Add(throneCommon2,1,0);layout.Controls.Add(pair,0,3);
  throneSummary=TextLabel("");layout.Controls.Add(throneSummary,0,4);
  thronePreset.SelectedIndexChanged+=(s,e)=>{if(throneFilling||thronePreset.SelectedIndex<0||thronePreset.SelectedIndex>2||project==null)return;ThroneFill(ThroneCopy(ThronePresets()[ThronePresetNames[thronePreset.SelectedIndex]]));ThroneEdited();};
  DataGridViewCellEventHandler edited=(s,e)=>{if(!throneFilling&&e.RowIndex>=0)ThroneEdited();};throneStages.CellValueChanged+=edited;throneCommon.CellValueChanged+=edited;throneCommon2.CellValueChanged+=edited;
  thronePanel=new Panel{Dock=DockStyle.Fill,Visible=false,AutoScroll=true};thronePanel.Controls.Add(layout);return thronePanel;
 }
 void ThroneFill(Dictionary<string,object> rules){
  throneFilling=true;throneStages.Rows.Clear();throneCommon.Rows.Clear();throneCommon2.Rows.Clear();int half=(ThroneCommon.Length+1)/2,at=0;
  var list=((IEnumerable)rules["stages"]).Cast<Dictionary<string,object>>().ToArray();var x=(Dictionary<string,object>)rules["expedition"];var tributes=((IEnumerable)x["tributes"]).Cast<object>().ToArray();
  for(int i=0;i<list.Length;i++)throneStages.Rows.Add(i.ToString(),Lang.T(Convert.ToString(list[i]["name"])),list[i]["cost"],list[i]["chance"],list[i]["cap"],list[i]["floor"],list[i]["gift_floor"],tributes[i]);
  foreach(var row in ThroneCommon){var g=at++<half?throneCommon:throneCommon2;bool raid=row[0].StartsWith("x.");int i=g.Rows.Add(Lang.T(row[1]),raid?x[row[0].Substring(2)]:rules[row[0]]);g.Rows[i].Tag=row[0];}
  throneStages.Tag=rules;throneFilling=false;
 }
 Dictionary<string,object> ThroneRead(){
  if(!throneStages.EndEdit()||!throneCommon.EndEdit()||!throneCommon2.EndEdit())throw new Exception("황위 쟁탈전 설정에 입력한 값을 확인하세요.");
  var rules=ThroneCopy(throneStages.Tag);var list=((IEnumerable)rules["stages"]).Cast<Dictionary<string,object>>().ToArray();var x=(Dictionary<string,object>)rules["expedition"];var tributes=new List<object>();
  string[] fields={"cost","chance","cap","floor","gift_floor"};
  Func<object,string,int> number=(cell,label)=>{int n;if(!int.TryParse(Convert.ToString(cell).Replace(",","").Trim(),out n))throw new Exception(label+": 정수를 입력하세요.");return n;};
  for(int i=0;i<list.Length;i++){for(int f=0;f<fields.Length;f++)list[i][fields[f]]=number(throneStages.Rows[i].Cells[f+2].Value,Convert.ToString(throneStages.Rows[i].Cells[1].Value)+" "+ThroneStageColumns[f+2]);tributes.Add(number(throneStages.Rows[i].Cells[7].Value,Convert.ToString(throneStages.Rows[i].Cells[1].Value)+" "+ThroneStageColumns[7]));}
  x["tributes"]=tributes;
  foreach(DataGridViewRow row in throneCommon.Rows.Cast<DataGridViewRow>().Concat(throneCommon2.Rows.Cast<DataGridViewRow>())){string key=(string)row.Tag;int n=number(row.Cells[1].Value,Convert.ToString(row.Cells[0].Value));if(key.StartsWith("x."))x[key.Substring(2)]=n;else rules[key]=n;}
  return rules;
 }
 // Checks the table (throne_rules.py --validate, the game's own check), shows the summary, keeps a valid set.
 void ThroneEdited(bool byUser=true){
  string text=null,name=null;
  try{var rules=ThroneRead();throneError=ThroneValidate(rules,out text,out name);if(throneError==null&&ThroneEnabled){project.rules["throne"]=rules;if(byUser)Changed();}}
  catch(Exception e){throneError=e.Message;}
  throneSummary.ForeColor=throneError==null?Dark:Color.Firebrick;throneSummary.Text=throneError??text;
  throneFilling=true;thronePreset.SelectedIndex=throneError==null&&name!=null?Array.IndexOf(ThronePresetNames,name):3;throneFilling=false;
 }
 // Competition chosen: the throne rules of the file, else the standard preset. Other modes: no throne rules.
 void ThroneModeChosen(bool competition){
  if(project==null)return;
  if(!competition){project.rules.Remove("throne");throneError=null;return;}
  if(RomeCapital.Spec==null)throw new Exception("로마의 위치 자료(rome-capital.json)를 읽지 못했습니다.");
  if(!ThroneEnabled||ThroneRulesOutdated(project.rules["throne"]))project.rules["throne"]=ThroneCopy(ThronePresets()["standard"]);
  project.rules.Remove("objectives");project.rules["mode"]="free-build";   // the file says race-for-throne (ApplyThroneToFile)
  ThroneGovernance();ThroneFill(ThroneCopy(project.rules["throne"]));ThroneEdited();
 }
 // The struggle for the throne needs the original favour rules (salary, gifts, tribute, anger, legions: scenario_check
 // 'throne-favor'). Choosing it sets every slot that pinned its favour ('fixed') to the original rules (user
 // 2026-11-15: the check used to ask the author to change it by hand); the slot's other values stay. Returns true
 // when something changed.
 bool ThroneGovernance(){
  bool changed=false;if(project==null||project.slots==null||!ThroneEnabled)return false;
  foreach(var slot in project.slots)if(slot.governance!=null&&slot.governance.policy=="fixed"){slot.governance.policy="original";changed=true;}
  return changed;
 }
 void ThroneRequireValid(){if(ThroneEnabled&&throneError!=null)throw new Exception("황위 쟁탈전 설정: "+throneError);}
 // A format-5 file is opened as the editor's working form: rules.throne kept, the mode handled by ApplyThroneToFile.
 static void AdoptThrone(Scenario data){
  if(data.schema!=5)return;
  data.schema=4;if(data.rules!=null){data.rules["mode"]="free-build";data.rules.Remove("objectives");}
 }
 static int ThroneProbe(){
  var presets=Json.Deserialize<Dictionary<string,Dictionary<string,object>>>(RunPython("throne_rules.py","--presets"));
  if(presets.Count!=3||ThroneRulesOutdated(presets["standard"]))throw new Exception("Throne presets missing");
  var old=ThroneCopy(presets["standard"]);var x=(Dictionary<string,object>)old["expedition"];x.Remove("march_months");x["preparation_months"]=3;
  if(!ThroneRulesOutdated(old))throw new Exception("An old rule set was not recognised");
  var scenario=new Scenario{schema=4,id="throne-check",title="황위 검증",revision=1,rules=new Dictionary<string,object>{{"mode","free-build"},{"player_transport","land"},{"starting_funds",10000},{"throne",presets["short"]}},slots=new Slot[0],empire=new Empire{cities=new City[0]}};
  var file=Json.Deserialize<Dictionary<string,object>>(SerializeProject(scenario));var rules=(Dictionary<string,object>)file["rules"];var empire=(Dictionary<string,object>)file["empire"];
  if(Convert.ToInt32(file["schema"])!=5||Convert.ToString(rules["mode"])!="race-for-throne"||!empire.ContainsKey("rome")||rules.ContainsKey("objectives"))throw new Exception("Throne scenario was not written as format 5");
  var back=Json.Deserialize<Scenario>(Json.Serialize(file));AdoptThrone(back);
  if(back.schema!=4||!back.rules.ContainsKey("throne")||Convert.ToString(back.rules["mode"])!="free-build")throw new Exception("Format 5 was not adopted");
  scenario.rules.Remove("throne");file=Json.Deserialize<Dictionary<string,object>>(SerializeProject(scenario));
  if(Convert.ToInt32(file["schema"])!=4||((Dictionary<string,object>)file["empire"]).ContainsKey("rome"))throw new Exception("A plain scenario was changed");
  File.WriteAllText(Path.Combine(Root,"throne-probe.json"),SerializeProject(new Scenario{schema=4,id="throne-check",title="황위 검증",revision=1,rules=new Dictionary<string,object>{{"mode","free-build"},{"player_transport","land"},{"starting_funds",10000},{"throne",presets["long"]}},slots=new Slot[0],empire=new Empire{cities=new City[0]}}),new System.Text.UTF8Encoding(false));
  return 0;
 }
}
