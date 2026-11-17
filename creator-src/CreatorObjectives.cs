using System;
using System.IO;
using System.Linq;
using System.Drawing;
using System.Collections.Generic;
using System.Windows.Forms;
public class ObjectiveTarget {public int population,culture,prosperity,peace,favor,treasury;}
public class DeliveryGoal {public string id,sender,receiver,kind;public int resource,quantity;}
public class DeliveryResource {public string name;public int resource;public override string ToString(){return name;}}
public class ObjectiveSettings {public List<DeliveryGoal> deliveries=new List<DeliveryGoal>();public string celebration="notice";public int population_total,treasury_total;public Dictionary<string,ObjectiveTarget> per_city;
 // Totals for a game started with fewer players than cities: "<players>" -> {population_total, treasury_total}. null = none.
 public Dictionary<string,Dictionary<string,int>> by_players;}
partial class ScenarioCreator {
 List<DeliveryGoal> deliveryTasks=new List<DeliveryGoal>();
 ListBox deliveryList=new ListBox{Dock=DockStyle.Fill,HorizontalScrollbar=true,BackColor=Paper,ForeColor=Dark,ItemHeight=28};
 ComboBox deliveryFrom=new ComboBox{DropDownStyle=ComboBoxStyle.DropDownList,Width=180},deliveryTo=new ComboBox{DropDownStyle=ComboBoxStyle.DropDownList,Width=180},deliveryItem=new ComboBox{DropDownStyle=ComboBoxStyle.DropDownList,Width=140},deliveryKind=new ComboBox{DropDownStyle=ComboBoxStyle.DropDownList,Width=160};
 NumericUpDown deliveryAmount=new NumericUpDown{Minimum=1,Maximum=1000000,Value=10,ThousandsSeparator=true,Width=120};
 string DeliveryCity(string id){var slot=project.slots.FirstOrDefault(x=>x.id==id);return slot==null?"삭제된 도시 ("+id+")":CityName(slot.name_id);}
 string DeliveryDescription(DeliveryGoal g){var item=deliveryItem.Items.Cast<DeliveryResource>().FirstOrDefault(x=>x.resource==g.resource);return DeliveryCity(g.sender)+"에서 "+DeliveryCity(g.receiver)+"(으)로"+" / "+(item==null?g.resource.ToString():item.name)+" "+g.quantity.ToString("N0")+"포대 / "+(g.kind=="gift"?"선물만":g.kind=="sale"?"판매만":"선물 또는 판매");}
 void RefreshDeliveryList(){deliveryList.Items.Clear();foreach(var g in deliveryTasks)deliveryList.Items.Add(DeliveryDescription(g));}
 static int DeliveryPolicyProbe(){
  var before=new ObjectiveSettings{population_total=0,per_city=new Dictionary<string,ObjectiveTarget>(),deliveries=new List<DeliveryGoal>{new DeliveryGoal{id="delivery-test",sender="capua",receiver="tarentum",kind="gift",resource=15,quantity=12}}};
  var after=Json.Deserialize<ObjectiveSettings>(Json.Serialize(before));
  if(after.deliveries.Count!=1||after.deliveries[0].quantity!=12||after.deliveries[0].sender!="capua")throw new Exception("Delivery roundtrip failed");
  var legacy=Json.Deserialize<ObjectiveSettings>("{\"population_total\":100,\"per_city\":{}}");
  if(legacy.deliveries==null||legacy.deliveries.Count!=0)throw new Exception("Legacy goals changed");
  RequireGoalChoice(1,after.deliveries.Count>0);
  File.WriteAllText(Path.Combine(Root,"delivery-editor-results.json"),Json.Serialize(new{passed=true,gui_created=false,roundtrip=after,legacy_empty=true}));return 0;
 }
 Control BuildDeliveryPanel(){
  var layout=new TableLayoutPanel{Dock=DockStyle.Fill,ColumnCount=1,RowCount=4,Padding=new Padding(20)};
  layout.RowStyles.Add(new RowStyle(SizeType.Absolute,80));layout.RowStyles.Add(new RowStyle(SizeType.Absolute,110));layout.RowStyles.Add(new RowStyle(SizeType.Percent,100));layout.RowStyles.Add(new RowStyle(SizeType.Absolute,48));
  layout.Controls.Add(TextLabel("플레이어 도시 사이의 물품 배송을 공동 승리 조건으로 정합니다. 최대 16개.\n제안하거나 수락한 수량이 아니라, 받는 도시까지 실제로 배송을 마친 수량을 누적합니다.\n미참가 도시의 과제는 대기합니다. 돈과 중립도시 교역은 집계하지 않습니다."),0,0);
  var choices=new FlowLayoutPanel{Dock=DockStyle.Fill,AutoScroll=true};
  foreach(var pair in new[]{new KeyValuePair<string,Control>("보내는 도시",deliveryFrom),new KeyValuePair<string,Control>("받는 도시",deliveryTo),new KeyValuePair<string,Control>("물품",deliveryItem),new KeyValuePair<string,Control>("거래 방식",deliveryKind),new KeyValuePair<string,Control>("목표 포대",deliveryAmount)}){
   var box=new FlowLayoutPanel{FlowDirection=FlowDirection.TopDown,AutoSize=true,WrapContents=false};box.Controls.Add(new Label{Text=pair.Key,AutoSize=true});box.Controls.Add(pair.Value);choices.Controls.Add(box);
  }
  deliveryKind.Items.AddRange(new object[]{"선물 또는 판매","선물만","판매만"});deliveryKind.SelectedIndex=0;
  foreach(var item in Json.Deserialize<DeliveryResource[]>(File.ReadAllText(Path.Combine(Root,"trade-catalog.json"))))if(item.resource!=0)deliveryItem.Items.Add(item);
  if(deliveryItem.Items.Count>0)deliveryItem.SelectedIndex=0;
  choices.Controls.Add(Button("과제 추가",()=>{
   RequireCooperativeEdit(objectiveChosen?objectiveMode.SelectedIndex:-1);
   if(deliveryFrom.SelectedIndex<0||deliveryTo.SelectedIndex<0||deliveryFrom.SelectedIndex==deliveryTo.SelectedIndex)throw new Exception("서로 다른 보내는 도시와 받는 도시를 선택하세요.");
   if(deliveryTasks.Count>=16)throw new Exception("납품 과제는 최대 16개입니다.");
   deliveryTasks.Add(new DeliveryGoal{id="delivery-"+Guid.NewGuid().ToString("N"),sender=project.slots[deliveryFrom.SelectedIndex].id,receiver=project.slots[deliveryTo.SelectedIndex].id,resource=((DeliveryResource)deliveryItem.SelectedItem).resource,quantity=(int)deliveryAmount.Value,kind=new[]{"either","gift","sale"}[deliveryKind.SelectedIndex]});
   RefreshDeliveryList();StoreObjectives(false);Changed();
  },120));layout.Controls.Add(choices,0,1);layout.Controls.Add(deliveryList,0,2);
  var footer=new FlowLayoutPanel{Dock=DockStyle.Fill};footer.Controls.Add(Button("선택 과제 삭제",()=>{RequireCooperativeEdit(objectiveChosen?objectiveMode.SelectedIndex:-1);int n=deliveryList.SelectedIndex;if(n<0)return;deliveryTasks.RemoveAt(n);RefreshDeliveryList();StoreObjectives(false);Changed();},160));footer.Controls.Add(Button("전체 승리 조건 확인",()=>ShowGoalPage(0),190));layout.Controls.Add(footer,0,3);
  return layout;
 }
 void RefreshDeliveryCities(){
  string from=deliveryFrom.SelectedIndex>=0&&deliveryFrom.SelectedIndex<project.slots.Length?project.slots[deliveryFrom.SelectedIndex].id:null;
  string to=deliveryTo.SelectedIndex>=0&&deliveryTo.SelectedIndex<project.slots.Length?project.slots[deliveryTo.SelectedIndex].id:null;
  deliveryFrom.Items.Clear();deliveryTo.Items.Clear();foreach(var slot in project.slots){deliveryFrom.Items.Add(CityName(slot.name_id));deliveryTo.Items.Add(CityName(slot.name_id));}
  int a=Array.FindIndex(project.slots,x=>x.id==from),b=Array.FindIndex(project.slots,x=>x.id==to);
  if(project.slots.Length>0)deliveryFrom.SelectedIndex=a>=0?a:0;if(project.slots.Length>1)deliveryTo.SelectedIndex=b>=0?b:1;
 }

 ComboBox celebrationMode=new ComboBox{DropDownStyle=ComboBoxStyle.DropDownList,Width=240};
 ComboBox objectiveMode=new ComboBox{DropDownStyle=ComboBoxStyle.DropDownList,Width=220};
 // 경쟁 (index 2) has kinds; only Race for the Throne for now (user 2026-11-14).
 ComboBox competitionKind=new ComboBox{DropDownStyle=ComboBoxStyle.DropDownList,Width=200,Visible=false};
 ComboBox goalRecipe=new ComboBox{DropDownStyle=ComboBoxStyle.DropDownList,Width=200};
 NumericUpDown recipeAmount=new NumericUpDown{Minimum=1,Maximum=10000000,Value=20000,Width=140,ThousandsSeparator=true};
 NumericUpDown recipeCulture=new NumericUpDown{Minimum=0,Maximum=100,Value=50,Width=60};
 Label recipeLabel=new Label{AutoSize=true,Padding=new Padding(0,7,0,0)};
 Label cultureLabel=new Label{Text="문화",AutoSize=true,Padding=new Padding(8,7,0,0)};
 // "모든 도시 발전시키기" fills every city figure at once (user 2026-11-15: culture alone was odd); 0 leaves one out.
 NumericUpDown recipeProsperity=new NumericUpDown{Minimum=0,Maximum=100,Value=50,Width=60},recipePeace=new NumericUpDown{Minimum=0,Maximum=100,Value=50,Width=60},recipeFavor=new NumericUpDown{Minimum=0,Maximum=100,Value=50,Width=60};
 Label prosperityLabel=new Label{Text="번영",AutoSize=true,Padding=new Padding(8,7,0,0)},peaceLabel=new Label{Text="평화",AutoSize=true,Padding=new Padding(8,7,0,0)},favorLabel=new Label{Text="지지도",AutoSize=true,Padding=new Padding(8,7,0,0)};
 NumericUpDown totalPopulation=new NumericUpDown{Minimum=0,Maximum=10000000,Width=130,ThousandsSeparator=true};
 NumericUpDown totalTreasury=new NumericUpDown{Minimum=0,Maximum=1000000000,Width=150,ThousandsSeparator=true};
 DataGridView playerGoalGrid=new DataGridView{Dock=DockStyle.Fill,AllowUserToAddRows=false,AllowUserToDeleteRows=false,RowHeadersVisible=false,AutoSizeColumnsMode=DataGridViewAutoSizeColumnsMode.Fill,BackgroundColor=Paper};
 DataGridView objectiveGrid=new DataGridView{Dock=DockStyle.Fill,AllowUserToAddRows=false,AllowUserToDeleteRows=false,RowHeadersVisible=false,AutoSizeColumnsMode=DataGridViewAutoSizeColumnsMode.Fill,BackgroundColor=Paper};
 TextBox objectiveSummary=new TextBox{Dock=DockStyle.Fill,Multiline=true,ReadOnly=true,ScrollBars=ScrollBars.Vertical,BackColor=Paper,BorderStyle=BorderStyle.FixedSingle};
 Panel advancedGoals=new Panel{Dock=DockStyle.Fill,Visible=false};
 Panel goalBody;
 TableLayoutPanel goalLayout;
 Control goalRecipePanel,goalOptionsPanel,goalFooter,deliveryPanel;
 Button[] goalNavigation;
 int goalPage;
 static void RequireCooperativeEdit(int mode){if(mode!=1)throw new Exception("공동 승리를 먼저 선택해야 조건을 편집할 수 있습니다.");}
 static void ApplyGoalMode(Dictionary<string,object> rules,int mode,ObjectiveSettings settings){
  RequireGoalChoice(mode,settings!=null);
  rules["mode"]=mode==0?"free-build":"cooperative";
  if(mode==0)rules.Remove("objectives");else rules["objectives"]=settings;
 }
 void ShowGoalPage(int page){
  goalPage=objectiveChosen&&objectiveMode.SelectedIndex==1?page:0;bool competition=objectiveChosen&&objectiveMode.SelectedIndex==2;
  if(thronePanel!=null)thronePanel.Visible=competition&&!ProgressEnabled&&!RaceEnabled;if(racePanel!=null)racePanel.Visible=competition&&RaceEnabled;if(progressPanel!=null)progressPanel.Visible=competition&&ProgressEnabled;
  objectiveSummary.Visible=!competition&&goalPage==0;advancedGoals.Visible=!competition&&goalPage==1;deliveryPanel.Visible=!competition&&goalPage==2;
  if(goalPage==2)RefreshDeliveryCities();
  foreach(var b in goalNavigation){bool active=(int)b.Tag==goalPage;b.FlatAppearance.BorderSize=active?2:1;b.ForeColor=active?Color.SaddleBrown:Dark;}
 }

 Label goalSelection=new Label{Dock=DockStyle.Fill,Font=new Font("Malgun Gothic",12,FontStyle.Bold),TextAlign=ContentAlignment.MiddleLeft};
 bool objectiveChosen;
 bool objectivesInitialized,storingObjectives;
 void BuildObjectivesTab(){
  var tab=new TabPage("4  공동 목표"){BackColor=Paper};tabs.TabPages.Add(tab);
  var layout=new TableLayoutPanel{Dock=DockStyle.Fill,ColumnCount=1,RowCount=4,Padding=new Padding(16)};goalLayout=layout;
  layout.RowStyles.Add(new RowStyle(SizeType.Absolute,92));layout.RowStyles.Add(new RowStyle(SizeType.Absolute,46));layout.RowStyles.Add(new RowStyle(SizeType.Percent,100));layout.RowStyles.Add(new RowStyle(SizeType.Absolute,56));tab.Controls.Add(layout);
  objectiveMode.Items.AddRange(new object[]{"자유 건설 · 목표 없음","협동 · 공동 승리","경쟁","목표를 선택하세요 (저장 필수)"});objectiveMode.Width=300;
  competitionKind.Items.Add("황위 쟁탈전");competitionKind.Items.Add("황제의 순행");competitionKind.Items.Add("기한 경쟁");competitionKind.SelectedIndex=0;
  competitionKind.SelectedIndexChanged+=(s,e)=>{if(loading||!objectivesInitialized||objectiveMode.SelectedIndex!=2)return;try{CompetitionChosen(true);}catch(Exception error){LangBox.Show(this,error.Message,"승리 조건",MessageBoxButtons.OK,MessageBoxIcon.Warning);}SetGoalEnabled();StoreObjectives(false);Changed();};
  celebrationMode.Items.AddRange(new object[]{"승리하면: 결과 알림","승리하면: 원본 승리 영상"});celebrationMode.SelectedIndex=0;
  var modes=new FlowLayoutPanel{Dock=DockStyle.Fill};modes.Controls.Add(objectiveMode);modes.Controls.Add(competitionKind);modes.Controls.Add(celebrationMode);
  var header=new TableLayoutPanel{Dock=DockStyle.Fill,ColumnCount=1,RowCount=2};header.RowStyles.Add(new RowStyle(SizeType.Absolute,40));header.RowStyles.Add(new RowStyle(SizeType.Percent,100));header.Controls.Add(modes,0,0);header.Controls.Add(goalSelection,0,1);layout.Controls.Add(header,0,0);
  var options=new FlowLayoutPanel{Dock=DockStyle.Fill};goalOptionsPanel=options;
  string[] pages={"승리 조건 요약","도시 수치 설정","납품 조건 설정"};goalNavigation=new Button[3];
  for(int i=0;i<3;i++){int n=i;var b=Button(pages[i],()=>ShowGoalPage(n),165);b.Tag=i;goalNavigation[i]=b;options.Controls.Add(b);}
  options.Controls.Add(Button("모든 조건 지우기",()=>{RequireCooperativeEdit(objectiveChosen?objectiveMode.SelectedIndex:-1);ClearObjectiveValues();StoreObjectives(false);Changed();},165));layout.Controls.Add(options,0,1);
  goalBody=new Panel{Dock=DockStyle.Fill};layout.Controls.Add(goalBody,0,2);
  // 도시 수치 설정 (user 2026-11-15): the city table and the totals by number of players side by side and tall enough for
  // every row; one line of help each; the quick fill at the bottom. The totals controls stay as the store of the last row.
  var metricPage=new TableLayoutPanel{Dock=DockStyle.Fill,ColumnCount=1,RowCount=2};metricPage.RowStyles.Add(new RowStyle(SizeType.Percent,100));metricPage.RowStyles.Add(new RowStyle(SizeType.Absolute,44));
  var tables=new TableLayoutPanel{Dock=DockStyle.Fill,ColumnCount=2,RowCount=2};tables.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,62));tables.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,38));tables.RowStyles.Add(new RowStyle(SizeType.Absolute,26));tables.RowStyles.Add(new RowStyle(SizeType.Percent,100));metricPage.Controls.Add(tables,0,0);advancedGoals.Controls.Add(metricPage);
  var recipe=new FlowLayoutPanel{Dock=DockStyle.Fill,WrapContents=false};goalRecipePanel=recipe;recipe.Controls.Add(new Label{Text="빠른 채우기",AutoSize=true,Font=actionFont,Padding=new Padding(0,8,6,0)});
  goalRecipe.Items.AddRange(new object[]{"함께 큰 제국 만들기","모든 도시 발전시키기","함께 자금 모으기"});recipe.Controls.Add(goalRecipe);recipe.Controls.Add(recipeLabel);recipe.Controls.Add(recipeAmount);recipe.Controls.Add(cultureLabel);recipe.Controls.Add(recipeCulture);recipe.Controls.Add(prosperityLabel);recipe.Controls.Add(recipeProsperity);recipe.Controls.Add(peaceLabel);recipe.Controls.Add(recipePeace);recipe.Controls.Add(favorLabel);recipe.Controls.Add(recipeFavor);
  recipe.Controls.Add(Button("바꾸기",()=>ApplyGoalRecipe(true),80));recipe.Controls.Add(Button("더하기",()=>ApplyGoalRecipe(false),80));metricPage.Controls.Add(recipe,0,1);
  string[] columns={"도시","인구","문화","번영","평화","지지도","현재 자금 (데나리)"};for(int i=0;i<columns.Length;i++)objectiveGrid.Columns.Add("goal"+i,columns[i]);objectiveGrid.Columns[0].ReadOnly=true;objectiveGrid.Columns[0].FillWeight=160;for(int i=1;i<columns.Length;i++){objectiveGrid.Columns[i].DefaultCellStyle.Alignment=DataGridViewContentAlignment.MiddleRight;objectiveGrid.Columns[i].DefaultCellStyle.Format="N0";}objectiveGrid.RowTemplate.Height=26;objectiveGrid.ColumnHeadersHeight=26;tables.Controls.Add(new Label{AutoSize=true,ForeColor=Dark,Font=actionFont,Padding=new Padding(0,4,0,0),Text="도시별 목표 (그 도시 혼자, 0은 조건 없음)"},0,0);tables.Controls.Add(objectiveGrid,0,1);
  tables.Controls.Add(new Label{AutoSize=true,ForeColor=Dark,Font=actionFont,Padding=new Padding(0,4,0,0),Text="참가 인원별 합계 목표 (0은 조건 없음)"},1,0);
  string[] playerColumns={"시작 인원","전체 인구 합계","전체 자금 합계"};for(int i=0;i<playerColumns.Length;i++)playerGoalGrid.Columns.Add("players"+i,playerColumns[i]);playerGoalGrid.Columns[0].ReadOnly=true;for(int i=1;i<playerColumns.Length;i++)playerGoalGrid.Columns[i].DefaultCellStyle.Alignment=DataGridViewContentAlignment.MiddleRight;playerGoalGrid.RowTemplate.Height=26;playerGoalGrid.ColumnHeadersHeight=26;tables.Controls.Add(playerGoalGrid,1,1);
  playerGoalGrid.CellValueChanged+=(s,e)=>{if(e.RowIndex<0||loading)return;var row=playerGoalGrid.Rows[e.RowIndex];if(IsTotalRow(row)){int n;bool was=loading;loading=true;try{if(int.TryParse(Convert.ToString(row.Cells[1].Value).Replace(",","").Trim(),out n))totalPopulation.Value=Math.Max(totalPopulation.Minimum,Math.Min(totalPopulation.Maximum,n));if(int.TryParse(Convert.ToString(row.Cells[2].Value).Replace(",","").Trim(),out n))totalTreasury.Value=Math.Max(totalTreasury.Minimum,Math.Min(totalTreasury.Maximum,n));}finally{loading=was;}}GoalChanged();};
  playerGoalGrid.CellValidating+=(s,e)=>{if(e.ColumnIndex<=0||e.RowIndex<0||loading)return;string typed=Convert.ToString(e.FormattedValue).Replace(",","").Trim();int number;int maximum=e.ColumnIndex==1?10000000:1000000000;if(!int.TryParse(typed,out number)||number<0||number>maximum){e.Cancel=true;playerGoalGrid.Rows[e.RowIndex].ErrorText="0~"+maximum.ToString("N0")+"의 정수를 입력하세요.";}else playerGoalGrid.Rows[e.RowIndex].ErrorText="";};

  deliveryPanel=BuildDeliveryPanel();goalBody.Controls.Add(BuildThronePanel());goalBody.Controls.Add(BuildProgressPanel());goalBody.Controls.Add(BuildRacePanel());goalBody.Controls.Add(objectiveSummary);goalBody.Controls.Add(advancedGoals);goalBody.Controls.Add(deliveryPanel);
  goalFooter=TextLabel("도시 수치는 현재 값, 납품은 배송 완료 누적량입니다. 모든 조건을 충족한 공동 검사 시점에 승리합니다.\n승리 후에도 계속 플레이합니다. 영상 선택 시 모두 종료하면 재개하며, 최대 3분 대기합니다.");layout.Controls.Add(goalFooter,0,3);
  goalRecipe.SelectedIndexChanged+=(s,e)=>{int n=goalRecipe.SelectedIndex;recipeAmount.Maximum=n==2?1000000000:n==1?1000000:10000000;recipeAmount.Value=n==2?100000:n==1?5000:20000;recipeLabel.Text=n==2?"합계 데나리":n==1?"도시마다 인구":"합계 인구";foreach(Control c in new Control[]{recipeCulture,cultureLabel,recipeProsperity,prosperityLabel,recipePeace,peaceLabel,recipeFavor,favorLabel})c.Visible=n==1;};goalRecipe.SelectedIndex=0;
  objectiveMode.SelectedIndexChanged+=(s,e)=>{if(loading||!objectivesInitialized)return;int m=objectiveMode.SelectedIndex;objectiveChosen=m>=0&&m<=2;try{CompetitionChosen(m==2);}catch(Exception error){LangBox.Show(this,error.Message,"승리 조건",MessageBoxButtons.OK,MessageBoxIcon.Warning);loading=true;objectiveMode.SelectedIndex=3;objectiveChosen=false;loading=false;}SetGoalEnabled();StoreObjectives(false);Changed();};
  totalPopulation.ValueChanged+=(s,e)=>{SyncFullRosterRow();GoalChanged();};totalTreasury.ValueChanged+=(s,e)=>{SyncFullRosterRow();GoalChanged();};celebrationMode.SelectedIndexChanged+=(s,e)=>GoalChanged();
  objectiveGrid.CellValueChanged+=(s,e)=>{if(e.RowIndex>=0)GoalChanged();};
  objectiveGrid.CellValidating+=(s,e)=>{if(e.ColumnIndex<=0||e.RowIndex<0||loading)return;int number;int maximum=e.ColumnIndex==1?1000000:e.ColumnIndex==6?1000000000:100;if(!int.TryParse(Convert.ToString(e.FormattedValue).Replace(",",""),out number)||number<0||number>maximum){e.Cancel=true;objectiveGrid.Rows[e.RowIndex].ErrorText="0~"+maximum.ToString("N0")+"의 정수를 입력하세요.";}else objectiveGrid.Rows[e.RowIndex].ErrorText="";};
 }
 // The last row of the table is the full roster: it shows the totals above and is changed there.
 // A scenario may have up to 8 cities, but at most OnlinePlayerLimit (6) play (user 2026-11-15: goals must never be made
 // for 8). The table has a row for each number of players that can start; its last row is the scenario's own total
 // (rules.objectives.population_total / treasury_total, kept in totalPopulation/totalTreasury), the other rows are
 // rules.objectives.by_players. A scenario with more cities than can play also keeps the last row in by_players, so a
 // full room uses it (room_roster.effective_project).
 int MostPlayers(){return project==null?1:Math.Max(1,Math.Min(project.slots.Length,OnlinePlayerLimit));}
 bool IsTotalRow(DataGridViewRow row){return Convert.ToInt32(row.Tag)==MostPlayers();}
 void SyncFullRosterRow(){foreach(DataGridViewRow row in playerGoalGrid.Rows)if(IsTotalRow(row)){row.Cells[1].Value=((int)totalPopulation.Value).ToString("N0");row.Cells[2].Value=((int)totalTreasury.Value).ToString("N0");}}
 void GoalChanged(){if(!loading&&objectivesInitialized){try{StoreObjectives(false);}catch(Exception e){objectiveSummary.Text=e.Message;}Changed();}}
 void SetGoalEnabled(){
  bool cooperative=objectiveChosen&&objectiveMode.SelectedIndex==1;
  celebrationMode.Enabled=objectiveGrid.Enabled=playerGoalGrid.Enabled=totalPopulation.Enabled=totalTreasury.Enabled=cooperative;
  goalRecipePanel.Enabled=goalOptionsPanel.Enabled=deliveryPanel.Enabled=advancedGoals.Enabled=cooperative;
  bool competition=objectiveChosen&&objectiveMode.SelectedIndex==2;competitionKind.Visible=competition;celebrationMode.Visible=!competition;goalOptionsPanel.Visible=!competition;goalLayout.RowStyles[1].Height=competition?0:46;
  goalFooter.Visible=cooperative;goalLayout.RowStyles[3].Height=cooperative?56:0;
  goalSelection.Text=!objectiveChosen?"현재 목표: 미설정 — 자유 건설, 협동, 경쟁 중 하나를 선택하세요.":competition&&RaceEnabled?"현재 목표: 경쟁 · 기한 경쟁 — "+RaceSummary()+"합니다.":competition&&ProgressEnabled?"현재 목표: 경쟁 · 황제의 순행 — 순행이 모두 끝났을 때 황제의 총애가 가장 높은 총독이 승리합니다.":competition?"현재 목표: 경쟁 · 황위 쟁탈전 — 5단계 쿠데타를 먼저 끝낸 총독이 승리합니다.":cooperative?"현재 목표: 공동 승리 — 모든 조건을 함께 달성합니다.":"현재 목표: 없음 — 도시 수치와 납품 조건 모두 승리 판정에 사용하지 않습니다.";
  goalSelection.ForeColor=objectiveChosen?Dark:Color.Firebrick;ShowGoalPage(goalPage);
 }
 static void RequireGoalChoice(int mode,bool positive){
  if(mode<0||mode>2)throw new Exception("승리 조건에서 자유 건설, 협동, 경쟁 중 하나를 먼저 선택하세요.");
  if(mode==1&&!positive)throw new Exception("공동 승리의 조건을 하나 이상 설정하거나 자유 건설을 선택하세요.");
 }
 void RequireGoalsForSave(){try{StoreObjectives(true);}catch{if(stepsPage!=null)OpenVictoryPage();else tabs.SelectedIndex=3;objectiveMode.Focus();throw;}}
 static int GoalPolicyProbe(){
  RequireGoalChoice(0,false);RequireGoalChoice(1,true);
  RequireGoalChoice(2,false);
  foreach(int mode in new[]{-1,3,1}){bool rejected=false;try{RequireGoalChoice(mode,false);}catch{rejected=true;}if(!rejected)throw new Exception("Unset or empty goal accepted");}
  var settings=new ObjectiveSettings{population_total=100,per_city=new Dictionary<string,ObjectiveTarget>(),deliveries=new List<DeliveryGoal>{new DeliveryGoal{id="probe",sender="a",receiver="b",resource=15,quantity=10,kind="gift"}}};
  var rules=new Dictionary<string,object>{{"mode","cooperative"},{"objectives",settings},{"starting_funds",1000}};
  ApplyGoalMode(rules,0,settings);if(Convert.ToString(rules["mode"])!="free-build"||rules.ContainsKey("objectives")||(int)rules["starting_funds"]!=1000)throw new Exception("Free build serialized active conditions");
  RequireCooperativeEdit(1);foreach(int mode in new[]{-1,0,2}){bool rejected=false;try{RequireCooperativeEdit(mode);}catch{rejected=true;}if(!rejected)throw new Exception("Implicit cooperative switch allowed");}
  ApplyGoalMode(rules,1,settings);var restored=Json.Deserialize<ObjectiveSettings>(Json.Serialize(rules["objectives"]));if(restored.deliveries.Count!=1||restored.population_total!=100)throw new Exception("Explicit cooperative restore failed");
  File.WriteAllText(Path.Combine(Root,"goal-policy-results.json"),"{\"passed\":true,\"cases\":10,\"gui_created\":false}");return 0;
 }
 void ClearObjectiveValues(bool includeDeliveries=true){bool old=loading;loading=true;if(includeDeliveries){deliveryTasks.Clear();RefreshDeliveryList();}totalPopulation.Value=totalTreasury.Value=0;foreach(DataGridViewRow row in objectiveGrid.Rows)for(int i=1;i<7;i++)row.Cells[i].Value=0;foreach(DataGridViewRow row in playerGoalGrid.Rows)for(int i=1;i<3;i++)row.Cells[i].Value="0";SyncFullRosterRow();loading=old;}
 void ApplyGoalRecipe(bool replace){
  RequireCooperativeEdit(objectiveChosen?objectiveMode.SelectedIndex:-1);
  if(!objectiveGrid.EndEdit())return;bool old=loading;loading=true;if(replace)ClearObjectiveValues(false);
  if(goalRecipe.SelectedIndex==0||goalRecipe.SelectedIndex==2){int column=goalRecipe.SelectedIndex==0?1:2;var total=goalRecipe.SelectedIndex==0?totalPopulation:totalTreasury;total.Value=recipeAmount.Value;
   /* the amount is for the most players; fewer players get their share */foreach(DataGridViewRow row in playerGoalGrid.Rows)row.Cells[column].Value=((long)recipeAmount.Value*Convert.ToInt32(row.Tag)/MostPlayers()).ToString("N0");}
  else foreach(DataGridViewRow row in objectiveGrid.Rows){row.Cells[1].Value=(int)recipeAmount.Value;row.Cells[2].Value=(int)recipeCulture.Value;row.Cells[3].Value=(int)recipeProsperity.Value;row.Cells[4].Value=(int)recipePeace.Value;row.Cells[5].Value=(int)recipeFavor.Value;}
  loading=old;StoreObjectives(false);Changed();
 }
 void RefreshObjectives(){if(project==null)return;bool previous=loading;loading=true;objectivesInitialized=false;ObjectiveSettings settings=null;object raw;if(project.rules.TryGetValue("objectives",out raw)&&raw!=null)settings=Json.Deserialize<ObjectiveSettings>(Json.Serialize(raw));objectiveMode.SelectedIndex=!objectiveChosen?3:ThroneEnabled||ProgressEnabled||RaceEnabled?2:Convert.ToString(project.rules["mode"])=="cooperative"?1:0;totalPopulation.Value=settings==null?0:settings.population_total;totalTreasury.Value=settings==null?0:settings.treasury_total;celebrationMode.SelectedIndex=settings!=null&&settings.celebration=="video"?1:0;deliveryTasks=settings==null||settings.deliveries==null?new List<DeliveryGoal>():settings.deliveries;RefreshDeliveryList();RefreshDeliveryCities();objectiveGrid.Rows.Clear();foreach(var slot in project.slots){ObjectiveTarget target=null;if(settings!=null&&settings.per_city!=null)settings.per_city.TryGetValue(slot.id,out target);if(target==null)target=new ObjectiveTarget();int row=objectiveGrid.Rows.Add(CityName(slot.name_id),target.population,target.culture,target.prosperity,target.peace,target.favor,target.treasury);objectiveGrid.Rows[row].Tag=slot.id;}playerGoalGrid.Rows.Clear();for(int players=1;players<=MostPlayers();players++){Dictionary<string,int> entry=null;if(settings!=null&&settings.by_players!=null)settings.by_players.TryGetValue(players.ToString(),out entry);int value;int pop=settings==null?0:settings.population_total,cash=settings==null?0:settings.treasury_total;if(entry!=null&&entry.TryGetValue("population_total",out value))pop=value;if(entry!=null&&entry.TryGetValue("treasury_total",out value))cash=value;int row=playerGoalGrid.Rows.Add(players+"명"+(players==MostPlayers()?" (최대)":""),pop.ToString("N0"),cash.ToString("N0"));playerGoalGrid.Rows[row].Tag=players;}SyncFullRosterRow();competitionKind.SelectedIndex=ProgressEnabled?1:RaceEnabled?2:0;RaceFill();progressError=null;if(ProgressEnabled&&progressPanel!=null){ProgressFill(Json.Deserialize<Dictionary<string,object>>(Json.Serialize(project.rules["progress"])));ProgressEdited(false);}throneError=null;if(ThroneEnabled&&thronePanel!=null){if(ThroneGovernance())Changed();ThroneFill(ThroneCopy(project.rules["throne"]));try{ThroneEdited(false);}catch(Exception e){throneError=e.Message;}}SetGoalEnabled();objectivesInitialized=true;loading=previous;StoreObjectives(false);}
 void StoreObjectives(bool validate){if(storingObjectives)return;storingObjectives=true;try{
  if(!objectivesInitialized||project==null)return;
  if(!objectiveChosen){if(validate)RequireGoalChoice(-1,false);objectiveSummary.Text="목표 미설정";return;}
  if(objectiveMode.SelectedIndex==2){if(validate){ThroneRequireValid();ProgressRequireValid();}objectiveSummary.Text=RaceEnabled?"경쟁 · 기한 경쟁":ProgressEnabled?"경쟁 · 황제의 순행":"경쟁 · 황위 쟁탈전";return;}
  if(objectiveMode.SelectedIndex==0){ApplyGoalMode(project.rules,0,null);objectiveSummary.Text="목표 없음 · 자유 건설\r\n\r\n도시 수치와 납품 조건은 모두 비활성 상태입니다. 조건을 달성해도 승리 판정을 하지 않습니다.\r\n\r\n이 상태로 저장하면 승리 조건을 포함하지 않습니다. 조건을 사용하려면 위에서 공동 승리를 직접 선택하세요.";return;}
  if(!objectiveGrid.EndEdit())throw new Exception("도시별 목표에 입력한 값을 확인하세요.");
  var settings=new ObjectiveSettings{deliveries=deliveryTasks.ToList(),celebration=celebrationMode.SelectedIndex==1?"video":"notice",population_total=(int)totalPopulation.Value,treasury_total=(int)totalTreasury.Value,per_city=new Dictionary<string,ObjectiveTarget>()};bool positive=settings.population_total>0||settings.treasury_total>0||settings.deliveries.Count>0;
  if(validate&&settings.deliveries.Any(g=>!project.slots.Any(x=>x.id==g.sender)||!project.slots.Any(x=>x.id==g.receiver)))throw new Exception("삭제된 도시의 납품 과제가 있습니다. 납품 과제에서 삭제 후 다시 지정하세요.");
  foreach(DataGridViewRow row in objectiveGrid.Rows){int[] values=new int[6];for(int c=1;c<7;c++){int maximum=c==1?1000000:c==6?1000000000:100;if(!int.TryParse(Convert.ToString(row.Cells[c].Value).Replace(",",""),out values[c-1])||values[c-1]<0||values[c-1]>maximum)throw new Exception(Convert.ToString(row.Cells[0].Value)+": 목표 값의 범위를 확인하세요.");}if(values.Any(n=>n>0)){positive=true;settings.per_city[(string)row.Tag]=new ObjectiveTarget{population=values[0],culture=values[1],prosperity=values[2],peace=values[3],favor=values[4],treasury=values[5]};}}
  if(!playerGoalGrid.EndEdit())throw new Exception("인원별 합계 목표에 입력한 값을 확인하세요.");
  foreach(DataGridViewRow row in playerGoalGrid.Rows){if(IsTotalRow(row)&&project.slots.Length<=OnlinePlayerLimit)continue;var entry=new Dictionary<string,int>();string[] names={"population_total","treasury_total"};for(int c=1;c<3;c++){string typed=Convert.ToString(row.Cells[c].Value).Replace(",","").Trim();if(typed=="")continue;int number;int maximum=c==1?10000000:1000000000;if(!int.TryParse(typed,out number)||number<0||number>maximum)throw new Exception(Convert.ToString(row.Cells[0].Value)+": 인원별 합계 목표의 범위를 확인하세요.");entry[names[c-1]]=number;}if(entry.Count>0){if(settings.by_players==null)settings.by_players=new Dictionary<string,Dictionary<string,int>>();settings.by_players[Convert.ToString(row.Tag)]=entry;}}
  if(validate)RequireGoalChoice(objectiveMode.SelectedIndex,positive);ApplyGoalMode(project.rules,1,settings);
  var descriptions=new List<string>();
  /* the totals by number of players, as the table shows them (the room uses the row of the players who start) */
  Func<string,int,string> byPlayers=(key,full)=>{var parts=new List<string>();for(int n=1;n<=MostPlayers();n++){int v=full;Dictionary<string,int> row;int x;if(settings.by_players!=null&&settings.by_players.TryGetValue(n.ToString(),out row)&&row.TryGetValue(key,out x))v=x;parts.Add(Lang.T(n+"명 "+v.ToString("N0")));   /* each part on its own: the editor translates at most 3 slots deep */}return string.Join(", ",parts);};
  Func<string,int,bool> anyTotal=(key,full)=>{if(full>0)return true;if(settings.by_players==null)return false;foreach(var row in settings.by_players.Values){int x;if(row.TryGetValue(key,out x)&&x>0)return true;}return false;};
  if(anyTotal("population_total",settings.population_total))descriptions.Add("참가한 도시들의 인구 합계 (시작 인원별: "+byPlayers("population_total",settings.population_total)+") 이상");
  if(anyTotal("treasury_total",settings.treasury_total))descriptions.Add("참가한 도시들의 현재 자금 합계, 누적 수입 아님 (시작 인원별: "+byPlayers("treasury_total",settings.treasury_total)+") 이상");
  string[] labels={"인구","문화 등급","번영 등급","평화 등급","지지도","현재 자금"};
  for(int metric=0;metric<6;metric++){
   var targets=new List<KeyValuePair<string,int>>();foreach(var slot in project.slots){ObjectiveTarget t;if(!settings.per_city.TryGetValue(slot.id,out t))continue;int v=new int[]{t.population,t.culture,t.prosperity,t.peace,t.favor,t.treasury}[metric];if(v>0)targets.Add(new KeyValuePair<string,int>(CityName(slot.name_id),v));}
   string unit=metric==0?"명":metric==5?" 데나리":"";
   if(targets.Count==project.slots.Length&&targets.Select(x=>x.Value).Distinct().Count()==1)descriptions.Add("모든 플레이어 도시의 "+labels[metric]+"가 각각 "+targets[0].Value.ToString("N0")+unit+" 이상");
   else foreach(var target in targets)descriptions.Add(target.Key+"의 "+labels[metric]+"가 "+target.Value.ToString("N0")+unit+" 이상");
  }
  foreach(var g in settings.deliveries)descriptions.Add("누적 납품: "+DeliveryDescription(g));
  goalSelection.Text=positive?"현재 목표: 공동 승리 — "+descriptions.Count+"개 조건을 모두 달성하면 승리합니다.":"현재 목표: 공동 승리 — 조건 미설정 (저장할 수 없습니다.)";
  objectiveSummary.Text="이 시나리오는 이렇게 승리합니다\r\n\r\n"+(positive?"다음 "+descriptions.Count+"개 조건을 모두 충족하면 함께 승리합니다. 납품은 누적 완료량, 도시 수치는 검사 시점의 현재 값입니다.\r\n\r\n"+string.Join("\r\n",descriptions.Select((x,i)=>(i+1)+". "+x)):"아직 목표가 없습니다. '도시 수치 설정' 또는 '납품 조건 설정'에서 조건을 추가하세요.")+"\r\n\r\n승리하면: "+(settings.celebration=="video"?"원본 승리 영상, 결과 확인 후 계속 플레이":"결과 알림 후 계속 플레이");
 }finally{storingObjectives=false;}}
}
