using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Drawing;
using System.Collections.Generic;
using System.Windows.Forms;
public class Finding { public string check,target,severity,label,reason; public bool required; }
public class ExportState { public bool allowed; public int blocks,pending; }
// Work order of the editor: 1 victory conditions, then the overview text (one page) -> 2 empire map and cities -> 3 player slots
// -> 4 validation and export (engine check, sharing, multiplayer start).
// The pages built by the existing Build*Tab methods are only moved here; their logic and the file format are unchanged.
// One "current slot" drives every slot picker, the map selection and the trade list, so they never point at different slots.
partial class ScenarioCreator {
 TabPage overviewPage,mapPage,slotPage,victoryPage,checkPage,constructionPage,nativePage,governancePage,eventsPage,invasionsPage;
 TabControl slotTabs=new TabControl{Dock=DockStyle.Fill};
 ComboBox currentSlot=new ComboBox{DropDownStyle=ComboBoxStyle.DropDownList,Width=300};
 Label slotHeader=new Label{AutoSize=true,ForeColor=Color.FromArgb(40,35,29),Padding=new Padding(0,6,0,0)};
 Label overviewFacts=new Label{Dock=DockStyle.Top,AutoSize=true,Padding=new Padding(16,12,16,10),Font=new Font("Malgun Gothic",10)};
 TextBox citySummary=new TextBox{Dock=DockStyle.Fill,Multiline=true,ReadOnly=true,ScrollBars=ScrollBars.Vertical,BorderStyle=BorderStyle.FixedSingle};
 ListView findingsList=new ListView{Dock=DockStyle.Fill,View=View.Details,FullRowSelect=true,HideSelection=false};
 Label exportState=new Label{AutoSize=true,Font=new Font("Malgun Gothic",11,FontStyle.Bold),Padding=new Padding(0,6,12,0)};
 Finding[] lastFindings=new Finding[0];ExportState lastExport;
 bool syncingSlot;

 static TabPage PageStarting(TabControl owner,string prefix){foreach(TabPage p in owner.TabPages)if(p.Text.StartsWith(prefix))return p;return null;}
 void ArrangeWorkflowTabs(){
  mapPage=PageStarting(tabs,"1  ");constructionPage=PageStarting(tabs,"2  ");nativePage=PageStarting(tabs,"3  ");victoryPage=PageStarting(tabs,"4  ");
  governancePage=PageStarting(tabs,"5  ");eventsPage=PageStarting(tabs,"6  ");invasionsPage=PageStarting(tabs,"7  ");overviewPage=PageStarting(tabs,"8  ");
  if(new[]{mapPage,constructionPage,nativePage,victoryPage,governancePage,eventsPage,invasionsPage,overviewPage,slotSettingsTab}.Any(p=>p==null))return; // keep the old layout rather than lose a page
  tabs.TabPages.Clear();
  overviewPage.Text="1  시나리오 개요";mapPage.Text="2  제국지도·도시";victoryPage.Text="4  승리 조건";
  slotPage=new TabPage("3  플레이 자리 설정"){BackColor=Paper};checkPage=new TabPage("5  검증·내보내기"){BackColor=Paper};
  foreach(var p in new[]{overviewPage,mapPage,slotPage,victoryPage,checkPage})tabs.TabPages.Add(p);
  slotSettingsTab.Text="시작 자금·추천·교역";constructionPage.Text="건설 허용";nativePage.Text="지형";   /* one terrain page (user 2026-11-15) */governancePage.Text="통치자·황제 지지도";eventsPage.Text="도시별 이벤트";invasionsPage.Text="침략 설정";
  foreach(var p in new[]{slotSettingsTab,nativePage,constructionPage,governancePage,eventsPage,invasionsPage})slotTabs.TabPages.Add(p);
  var slotLayout=new TableLayoutPanel{Dock=DockStyle.Fill,ColumnCount=1,RowCount=2,Padding=new Padding(6)};slotLayout.RowStyles.Add(new RowStyle(SizeType.AutoSize));slotLayout.RowStyles.Add(new RowStyle(SizeType.Percent,100));
  var bar=new FlowLayoutPanel{Dock=DockStyle.Fill,AutoSize=true,WrapContents=true,Padding=new Padding(4)};
  bar.Controls.Add(new Label{Text="플레이 자리",AutoSize=true,Font=new Font("Malgun Gothic",10,FontStyle.Bold),Padding=new Padding(0,6,0,0)});bar.Controls.Add(currentSlot);
  bar.Controls.Add(Button("지도에서 보기",()=>{var s=CurrentSlotData();if(s==null)return;tabs.SelectedTab=mapPage;SelectCity(s.name_id);map.RevealCity(s.name_id);},120));
  bar.Controls.Add(slotHeader);slotLayout.Controls.Add(bar,0,0);slotLayout.Controls.Add(slotTabs,0,1);slotPage.Controls.Add(slotLayout);
  BuildOverviewFacts();BuildCheckPage();AttachCitySummary();MergeGoalPage();EmphasizeTabs();
  // The slot picker inside the funds page is driven by the shared picker above; hide the duplicate row.
  var own=slotSettingsPicker.Parent as TableLayoutPanel;if(own!=null){foreach(Control c in own.Controls)if(own.GetRow(c)==0)c.Visible=false;own.RowStyles[0]=new RowStyle(SizeType.Absolute,0);}
  currentSlot.SelectedIndexChanged+=(s,e)=>{if(!syncingSlot)FocusSlot(currentSlot.SelectedIndex,true);};
  // Only a person's choice in a picker moves the shared slot. Pickers refilled by their own pages are put back afterwards (Resync).
  foreach(var picker in SlotPickers())picker.SelectionChangeCommitted+=(s,e)=>{if(!syncingSlot){var c=(ComboBox)s;if(c.SelectedIndex>=0)FocusSlot(c.SelectedIndex,true);}};
  slotTabs.SelectedIndexChanged+=(s,e)=>{if(slotTabs.SelectedTab==nativePage)Guard(RefreshTerrainVersions);if(slotTabs.SelectedTab==slotSettingsTab)RefreshSlotSettings();Resync();};
  tabs.SelectedIndexChanged+=(s,e)=>{
   if(tabs.SelectedTab==slotPage){RefreshCurrentSlotList();if(slotTabs.SelectedTab==nativePage)Guard(RefreshTerrainVersions);if(slotTabs.SelectedTab==slotSettingsTab)RefreshSlotSettings();Resync();}
   if(tabs.SelectedTab==stepsPage&&goalTabs.SelectedTab==overviewPage)RefreshOverviewFacts();
   if(tabs.SelectedTab==checkPage)RefreshChecks();
  };
  map.ShowConnections=true;foreach(var box in AllControls(mapPage).OfType<CheckBox>().Where(b=>b.Text=="교역 연결 보기")){box.Checked=true;box.Text="교역 연결 보기 (플레이 도시를 선택하세요)";}
  tabs.SelectedTab=mapPage;
 }
 // Page 1 holds two steps as inner tabs, in the order they are done: ① victory conditions, ② overview and briefing.
 // The two former pages are used as they are (each keeps the full height it was laid out for); a first attempt that
 // stacked them in one view squeezed the briefing box to a line and cut the delivery settings off (2026-11-13).
 TabPage stepsPage;TabControl goalTabs;
 void MergeGoalPage(){
  stepsPage=new TabPage("1  승리 조건·시나리오 개요"){BackColor=Paper};
  goalTabs=new TabControl{Dock=DockStyle.Fill};
  tabs.TabPages.Clear();
  victoryPage.Text="①  승리 조건 (먼저 정합니다)";overviewPage.Text="②  시나리오 개요 (조건에 맞춰 씁니다)";
  goalTabs.TabPages.Add(victoryPage);goalTabs.TabPages.Add(overviewPage);BuildMakerPage();
  var first=new FlowLayoutPanel{Dock=DockStyle.Top,AutoSize=true,WrapContents=true,Padding=new Padding(8,6,8,4)};
  first.Controls.Add(new Label{Text="승리 조건을 먼저 정한 뒤, 그 조건에 맞춰 시나리오 개요를 씁니다.",AutoSize=true,Padding=new Padding(0,8,16,0)});
  // No "② 시나리오 개요 쓰기" button: the ② tab right below does the same (user 2026-11-14).
  stepsPage.Controls.Add(goalTabs);stepsPage.Controls.Add(first);   // the bar is added last: it docks above the inner tabs
  goalTabs.SelectedIndexChanged+=(s,e)=>{if(goalTabs.SelectedTab==overviewPage)RefreshOverviewFacts();if(goalTabs.SelectedTab==makerPage)ShowMakerTools();};
  foreach(var p in new[]{stepsPage,mapPage,slotPage,specialPage,checkPage})tabs.TabPages.Add(p);
  checkPage.Text="5  검증·내보내기";
 }
 void OpenVictoryPage(){if(stepsPage==null)return;tabs.SelectedTab=stepsPage;goalTabs.SelectedTab=victoryPage;}
 // The numbered tabs are the work order: larger and bold. Pages keep the form's own font (a TabControl hands its font down).
 void EmphasizeTabs(){
  foreach(TabPage p in tabs.TabPages)p.Font=Font;
  goalTabs.Font=new Font("Malgun Gothic",10,FontStyle.Bold);goalTabs.Padding=new Point(14,5);foreach(TabPage p in goalTabs.TabPages)p.Font=Font;
  tabs.Font=new Font("Malgun Gothic",11,FontStyle.Bold);tabs.Padding=new Point(16,7);
 }
 bool NativeTerrainVisible(){return nativePage!=null?tabs.SelectedTab==slotPage&&slotTabs.SelectedTab==nativePage:tabs.SelectedIndex==2;}
 void OpenConstructionPage(){if(slotPage==null){tabs.SelectedIndex=1;return;}tabs.SelectedTab=slotPage;slotTabs.SelectedTab=constructionPage;}
 void OpenSlotSettings(int slot){if(slotPage==null)return;tabs.SelectedTab=slotPage;slotTabs.SelectedTab=slotSettingsTab;FocusSlot(slot,true);}

 IEnumerable<ComboBox> SlotPickers(){
  var list=new List<ComboBox>{slotPicker,terrainSlot,slotSettingsPicker};
  if(eventCity!=null)list.Add(eventCity);if(invasionCity!=null)list.Add(invasionCity);
  var governance=governancePage==null?null:AllControls(governancePage).OfType<ComboBox>().FirstOrDefault();if(governance!=null)list.Add(governance);
  return list;
 }
 void Resync(){int i=currentSlot.SelectedIndex;if(i>=0)FocusSlot(i,false);}
 Slot CurrentSlotData(){int i=currentSlot.SelectedIndex;return project==null||i<0||i>=project.slots.Length?null:project.slots[i];}
 void RefreshCurrentSlotList(){
  if(project==null)return;syncingSlot=true;int keep=currentSlot.SelectedIndex;currentSlot.Items.Clear();
  for(int i=0;i<project.slots.Length;i++)currentSlot.Items.Add("P"+(i+1)+" · "+CityName(project.slots[i].name_id));
  if(project.slots.Length>0)currentSlot.SelectedIndex=Math.Max(0,Math.Min(keep<0?0:keep,project.slots.Length-1));
  syncingSlot=false;UpdateSlotHeader();
 }
 // Every slot picker, the map selection and the trade list follow one slot.
 void FocusSlot(int index,bool selectOnMap){
  if(project==null||index<0||index>=project.slots.Length||syncingSlot)return;
  syncingSlot=true;
  try{
   if(currentSlot.Items.Count!=project.slots.Length)RefreshCurrentSlotList();
   if(slotSettingsPicker.Items.Count!=project.slots.Length)RefreshSlotSettings();
   /* the governance page fills its city list when it gets the focus; fill it here too so it is never shown empty */
   var governanceCity=governancePage==null?null:AllControls(governancePage).OfType<ComboBox>().FirstOrDefault();
   if(governanceCity!=null&&governanceCity.Items.Count!=project.slots.Length){governanceCity.Items.Clear();foreach(var s in project.slots)governanceCity.Items.Add(s.id+" / "+CityName(s.name_id));}
   syncingSlot=true;
   if(currentSlot.SelectedIndex!=index)currentSlot.SelectedIndex=index;
   foreach(var picker in SlotPickers())if(picker.Items.Count>index&&picker.SelectedIndex!=index)picker.SelectedIndex=index;
   if(selectOnMap&&(selected<0||project.empire.cities[selected].name_id!=project.slots[index].name_id))SelectCity(project.slots[index].name_id);
  }finally{syncingSlot=false;}
  UpdateSlotHeader();if(tabs.SelectedTab==slotPage&&slotTabs.SelectedTab==slotSettingsTab)ShowSlotSettings();
 }
 string FundsText(Slot s){int common=CommonFunds();return s.starting_funds.HasValue?s.starting_funds.Value.ToString("N0")+" (이 자리 전용)":common.ToString("N0")+" (기본값)";}
 void UpdateSlotHeader(){var s=CurrentSlotData();slotHeader.Text=s==null?"":"도시: "+CityName(s.name_id)+"   시작 자금: "+FundsText(s)+(s.role_hint==null?"":"   추천: "+s.role_hint);}

 // ---- 1 overview ----
 void BuildOverviewFacts(){overviewPage.Controls.Add(overviewFacts);foreach(Control c in overviewPage.Controls)if(c!=overviewFacts)c.BringToFront();}
 void RefreshOverviewFacts(){
  if(project==null)return;object mode;project.rules.TryGetValue("mode",out mode);string m=Convert.ToString(mode);
  string modeText=m=="cooperative"?"협동 — 승리 조건은 ① 승리 조건의 공동 목표":ProgressEnabled?"경쟁 · 황제의 순행: 황제의 총애가 가장 높은 총독이 승리합니다 (① 승리 조건에서 바꿉니다)":ThroneEnabled?"경쟁 · 황위 쟁탈전: 5단계 쿠데타를 먼저 끝낸 총독이 승리합니다 (① 승리 조건에서 바꿉니다)":"자유 건설 — 정해진 승리 조건 없음";
  int n=project.slots.Length;
  overviewFacts.Text="모드: "+modeText+"\r\n플레이 자리: "+n+"개"+(n>OnlinePlayerLimit?" ("+n+"자리 중 최대 "+OnlinePlayerLimit+"명이 골라서 플레이합니다. 고르지 않은 자리는 중립 도시가 됩니다)":" (최대 8자리, 그중 "+OnlinePlayerLimit+"명까지 플레이)")+
   "\r\n기본 시작 자금: "+CommonFunds().ToString("N0")+" 데나리 (자리마다 다르게: 3번 탭)"+"\r\n아래 브리핑은 로비의 시나리오 설명 첫머리에 그대로 보입니다.";
 }

 // ---- 2 map: selected city summary ----
 void AttachCitySummary(){
  var right=cityHelp.Parent as TableLayoutPanel;if(right==null)return;
  var pos=right.GetPositionFromControl(cityHelp);right.Controls.Remove(cityHelp);
  var box=new TableLayoutPanel{Dock=DockStyle.Fill,ColumnCount=1,RowCount=2,Margin=Padding.Empty};box.RowStyles.Add(new RowStyle(SizeType.AutoSize));box.RowStyles.Add(new RowStyle(SizeType.Percent,100));
  cityHelp.Dock=DockStyle.Fill;cityHelp.AutoSize=true;cityHelp.MaximumSize=new Size(340,0);box.Controls.Add(cityHelp,0,0);box.Controls.Add(citySummary,0,1);
  right.Controls.Add(box,pos.Column,pos.Row);if(pos.Row<right.RowStyles.Count)right.RowStyles[pos.Row]=new RowStyle(SizeType.Absolute,170);
 }
 void AfterShowCity(){
  if(project==null||selected<0||selected>=project.empire.cities.Length)return;
  var c=project.empire.cities[selected];int slotIndex=Array.FindIndex(project.slots,s=>s.name_id==c.name_id);
  if(c.role=="player"&&slotIndex>=0&&!syncingSlot)FocusSlot(slotIndex,false);
  map.RomeChosen=false;citySummary.Text=DescribeCity(c,slotIndex);
 }
 // Rome is information only: the selected city and the shared slot stay as they were.
 void ShowRome(){citySummary.Text=RomeCapital.Text;status.Text=RomeCapital.Title;}
 string DescribeCity(City c,int slotIndex){
  var t=new StringBuilder();
  bool terrain=HasTerrain(c.name_id);
  if(c.role=="player"&&slotIndex>=0){
   var s=project.slots[slotIndex];
   t.AppendLine("역할: 플레이 도시 (P"+(slotIndex+1)+")   지형: "+(s.terrain_asset!=null?"외부 지도":"원작 지도")+(s.terrain_edits!=null&&s.terrain_edits.Length>0?" · 수정 "+s.terrain_edits.Length+"칸":""));
   t.AppendLine("시작 자금: "+FundsText(s));
   if(s.role_hint!=null)t.AppendLine("제작자 추천(규칙 아님): "+s.role_hint);
   t.AppendLine("허용 건물 "+(s.allowed_buildings==null?0:s.allowed_buildings.Length)+"종 · 통치·이벤트·침략은 3번 탭");
   var links=LinksForSlot(s.id);
   if(links==null)t.AppendLine("교역: "+(seaLimitsError??"확인 중"));
   else{
    var on=links.Where(l=>l.allowed).ToArray();
    t.AppendLine("교역 상대 "+on.Length+"곳: 가능 "+on.Count(l=>l.state=="ok")+" · 후보 "+on.Count(l=>l.state=="candidate")+" · 미확인 "+on.Count(l=>l.state=="unknown")+" · 불가 "+on.Count(l=>l.state=="broken")+(links.Any(l=>!l.allowed)?" · 금지 "+links.Count(l=>!l.allowed):""));
    foreach(var l in on.Where(l=>l.state=="broken"))t.AppendLine("  불가: "+(l.kind=="player"?CityName(project.slots.First(x=>x.id==l.slot).name_id):CityName(l.name_id))+" — "+l.reason);
   }
   var mine=lastFindings.Where(f=>f.target!=null&&f.target.Contains("("+s.id+")")&&(f.severity=="block"||f.severity=="warn")).ToArray();
   if(mine.Length>0)t.AppendLine("검사: 막힘 "+mine.Count(f=>f.severity=="block")+" · 경고 "+mine.Count(f=>f.severity=="warn")+" (5번 탭)");
  }else{
   t.AppendLine("역할: "+(c.reserved?"플레이어 자리로 비워 둔 도시":"중립 교역 도시")+(c.enabled?"":" · 사용 안 함")+"   지형: "+(terrain?"있음 (플레이 도시로 배정 가능)":"없음"));
   if(c.enabled&&!c.reserved){
    t.AppendLine("교역 방식: "+(c.sea==1?"해상만":"육로")+(c.sea_auto?" (위치로 자동 추정)":"")+" · 개설 비용 "+c.cost);
    int allowed=c.trade_players==null?project.slots.Length:c.trade_players.Length;
    t.AppendLine("교역 허용 플레이어: "+allowed+"/"+project.slots.Length+" · 파는 품목 "+(c.sells==null?0:c.sells.Count)+" · 사는 품목 "+(c.buys==null?0:c.buys.Count));
    if(c.sea==1){var lake=project.slots.Where(s=>{var l=LinksForSlot(s.id);return l!=null&&l.Any(x=>x.kind=="neutral"&&x.name_id==c.name_id&&x.allowed&&x.state=="broken");}).ToArray();
     if(lake.Length>0)t.AppendLine("해상 교역 불가 플레이어: "+string.Join(", ",lake.Select(s=>CityName(s.name_id))));}
   }
  }
  return t.ToString().TrimEnd();
 }

 // ---- 5 validation and export ----
 // 검증·내보내기 (user 2026-11-15), in this order: 1. every special setting at a glance, 2. the warnings (checked again
 // by themselves whenever the scenario changed: the check is keyed by the scenario's content), 3. the engine check
 // and the export.
 TabControl checkTabs;TabPage specialPage,warningsPage;RichTextBox specialText=new RichTextBox{Dock=DockStyle.Fill,ReadOnly=true,BorderStyle=BorderStyle.None,BackColor=Color.FromArgb(244,236,214),Font=new Font("Malgun Gothic",10)};
 void BuildCheckPage(){
  // Two pages of the top row (user 2026-11-15: "4 한눈에 보기, 5 검증·내보내기"; they were two inner tabs of page 4):
  // everything that is not a default, and the check with the export it can stop.
  specialPage=new TabPage("4  한눈에 보기"){BackColor=Paper,Padding=new Padding(12)};warningsPage=checkPage;checkPage.Padding=new Padding(12);
  specialText.Font=new Font("Malgun Gothic",10);specialPage.Controls.Add(specialText);
  var run=new TableLayoutPanel{Dock=DockStyle.Fill,ColumnCount=1,RowCount=4};for(int i=0;i<3;i++)run.RowStyles.Add(new RowStyle(SizeType.AutoSize));run.RowStyles.Add(new RowStyle(SizeType.Percent,100));
  run.Controls.Add(exportState,0,0);
  var buttons=new FlowLayoutPanel{AutoSize=true,Dock=DockStyle.Fill,Margin=new Padding(0,8,0,0)};
  buttons.Controls.Add(Button("게임 적용 검사 (실제 엔진)",()=>ValidateGame(false),220));buttons.Controls.Add(Button("공유 ZIP 만들기",()=>Guard(ExportDialog),150));buttons.Controls.Add(Button("공유 안내",ShowShareHelp,100));buttons.Controls.Add(Button("이 시나리오 멀티시작",Launch,180));
  run.Controls.Add(buttons,0,1);
  run.Controls.Add(new Label{AutoSize=true,ForeColor=Dark,MaximumSize=new Size(1100,0),Padding=new Padding(0,8,0,8),Text="아래 목록은 이 탭을 열 때마다 저절로 다시 검사됩니다. 게임 적용 검사는 실제 게임 엔진으로 도시를 만들어 보며, 결과도 이 목록에 나옵니다. 지형을 바꾸면 다시 하세요.\n줄을 두 번 누르면 관련 자리로 이동합니다. 경고·미검증은 알려 주기만 하고, 막힘이 있으면 공유 ZIP을 만들 수 없습니다."},0,2);
  findingsList.Columns.Add("구분",80);findingsList.Columns.Add("대상",180);findingsList.Columns.Add("내용",760);
  findingsList.DoubleClick+=(s,e)=>{if(findingsList.SelectedItems.Count==0)return;var f=findingsList.SelectedItems[0].Tag as Finding;if(f==null||f.target==null)return;int i=Array.FindIndex(project.slots,x=>f.target.Contains("("+x.id+")"));if(i>=0)OpenSlotSettings(i);};
  findingsList.Resize+=(s,e)=>{if(findingsList.Columns.Count==3)findingsList.Columns[2].Width=Math.Max(200,findingsList.ClientSize.Width-270);};
  run.Controls.Add(findingsList,0,3);warningsPage.Controls.Add(run);
  tabs.SelectedIndexChanged+=(s,e)=>{if(tabs.SelectedTab==specialPage)RefreshSpecialSettings();};
 }
 // The same event repeated (a request every 4 years) is one line: its months, then what it is.
 IEnumerable<string> EventGroups(List<CityEvent> events){return Repeats(events.Select(e=>{var t=EventText(e);return Tuple.Create(e.month,t.Substring(t.IndexOf(" / ")+3));}));}
 IEnumerable<string> Repeats(IEnumerable<Tuple<int,string>> items){
  foreach(var g in items.GroupBy(x=>x.Item2)){
   var months=g.Select(x=>x.Item1).OrderBy(m=>m).ToList();string when;
   if(months.Count==1)when=Lang.T("시작 후")+" "+months[0]+Lang.T("개월");
   else{int step=months[1]-months[0];bool even=step>0;for(int i=2;i<months.Count;i++)if(months[i]-months[i-1]!=step)even=false;
    when=even?months[0]+Lang.T("개월부터")+" "+step+Lang.T("개월마다")+" "+months.Count+Lang.T("회")+" ("+Lang.T("마지막")+" "+months[months.Count-1]+Lang.T("개월")+")":string.Join(", ",months)+Lang.T("개월")+" ("+months.Count+Lang.T("회")+")";}
   yield return when+" / "+g.Key;
  }
 }
 // Everything that is not a default, city by city: what a reviewer would otherwise have to open every tab for.
 void RefreshSpecialSettings(){
  if(project==null)return;specialText.Clear();
  Action<string> head=t=>{specialText.SelectionFont=new Font("Malgun Gothic",12,FontStyle.Bold);specialText.AppendText(Lang.T(t)+"\n");specialText.SelectionFont=specialText.Font;};
  Action<string> line=t=>{specialText.SelectionFont=specialText.Font;specialText.AppendText("    "+t+"\n");};
  head("시나리오 전체");
  line(Lang.T("승리 조건")+": "+goalSelection.Text.Replace("현재 목표: ",""));
  object raw;int least=project.rules.TryGetValue("min_players",out raw)&&raw!=null?Convert.ToInt32(raw):1;if(ProgressEnabled||RaceEnabled)least=Math.Max(2,least);if(least>1)line(Lang.T("최소 인원")+": "+least+Lang.T("명")+(ProgressEnabled?" ("+Lang.T("황제의 순행은 2명 이상")+")":RaceEnabled?" ("+Lang.T("기한 경쟁은 2명 이상")+")":""));
  if(RaceEnabled)line(Lang.T("기한 경쟁")+": "+RaceSummary());
  line(Lang.T("기본 시작 자금")+": "+CommonFunds().ToString("N0")+" "+Lang.T("데나리"));
  if(project.rules.TryGetValue("objectives",out raw)&&raw!=null){var o=Json.Deserialize<ObjectiveSettings>(Json.Serialize(raw));if(o.deliveries!=null)foreach(var g in o.deliveries)line(Lang.T("납품 목표")+": "+DeliveryDescription(g));}
  foreach(var row in ReadPairs()){var pair=PairOf(row);if(pair.Length!=2)continue;var a=Array.Find(project.slots,x=>x.id==pair[0]);var b=Array.Find(project.slots,x=>x.id==pair[1]);if(a==null||b==null)continue;line(Lang.T("플레이어 교역")+": "+CityName(a.name_id)+" - "+CityName(b.name_id)+" "+(Convert.ToBoolean(row["allow"])?Lang.T("허용"):Lang.T("금지")));}
  specialText.AppendText("\n");
  // Grouped by kind (user: "도시별 이벤트 모음과 침략 설정 모음"), each line naming its city.
  int all=catalog==null?0:catalog.Count();
  Func<int,string> who=k=>"P"+(k+1)+" "+CityName(project.slots[k].name_id)+"  ";
  Action<string,Func<int,IEnumerable<string>>> group=(title,lines)=>{head(title);int n=0;for(int k=0;k<project.slots.Length;k++)foreach(var t in lines(k)){line(who(k)+t);n++;}if(n==0)line(Lang.T("없음"));specialText.AppendText("\n");};
  group("도시별 이벤트 모음",k=>{var slot=project.slots[k];return slot.events==null?new string[0]:EventGroups(slot.events);});
  group("침략 모음",k=>{var slot=project.slots[k];return slot.invasions==null?new string[0]:Repeats(slot.invasions.Select(e=>Tuple.Create(e.month,PeopleText(slot,e)+", "+e.amount+Lang.T("명"))));});
  group("통치자와 황제 지지도",k=>{var g=project.slots[k].governance;if(g==null)return new string[0];return new[]{RankNames[Math.Max(0,Math.Min(RankNames.Length-1,g.rank))]+", "+Lang.T("봉급")+" "+(g.salary_rank<0?Lang.T("직급에 맞춤"):RankNames[Math.Min(RankNames.Length-1,g.salary_rank)])+", "+Lang.T("개인 재산")+" "+g.savings.ToString("N0")+", "+Lang.T("황제 지지도")+" "+g.favor+(g.policy=="fixed"?" ("+Lang.T("고정")+")":"")};});
  group("자리별 시작 조건",k=>{var slot=project.slots[k];var r=new List<string>();if(slot.starting_funds.HasValue)r.Add(Lang.T("시작 자금")+" "+slot.starting_funds.Value.ToString("N0")+" "+Lang.T("데나리"));if(!string.IsNullOrEmpty(slot.starting_setup))r.Add(Lang.T("시작 배치")+" "+slot.starting_setup);if(!string.IsNullOrWhiteSpace(slot.role_hint))r.Add(Lang.T("추천 역할")+" "+slot.role_hint.Replace("\r"," ").Replace("\n"," "));return r;});
  group("건설 제한",k=>{var slot=project.slots[k];return slot.allowed_buildings!=null&&all>0&&slot.allowed_buildings.Length<all?new[]{Lang.T("허용")+" "+slot.allowed_buildings.Length+" / "+all+" ("+Lang.T("금지")+" "+(all-slot.allowed_buildings.Length)+")"}:new string[0];});
  group("지형",k=>{var slot=project.slots[k];return new[]{TerrainVersionText(slot)+(slot.terrain_asset==null&&slot.terrain_edits!=null&&slot.terrain_edits.Length>0?" + "+Lang.T("이전 수정")+" "+slot.terrain_edits.Length:"")};});
  specialText.SelectionStart=0;specialText.ScrollToCaret();
 }
 void RefreshChecks(){
  if(project==null||project.slots.Length==0)return;
  SeaLimit(project.slots[0].id);linksShownVersion=linksVersion;
  findingsList.BeginUpdate();findingsList.Items.Clear();
  if(seaLimitsError!=null){exportState.Text="검사를 실행하지 못했습니다";exportState.ForeColor=Color.Firebrick;findingsList.Items.Add(new ListViewItem(new[]{"미검증","시나리오",seaLimitsError}));findingsList.EndUpdate();Lang.Refresh(findingsList);return;}
  foreach(var f in lastFindings){var item=new ListViewItem(new[]{f.label??f.severity,f.target??"",f.reason??""}){Tag=f};
   item.ForeColor=f.severity=="block"?Color.Firebrick:f.severity=="warn"?Color.FromArgb(150,90,0):f.severity=="unverified"?Color.FromArgb(70,70,120):Dark;findingsList.Items.Add(item);}
  findingsList.EndUpdate();Lang.Refresh(findingsList);
  if(lastExport==null){exportState.Text="";return;}
  exportState.Text=lastExport.allowed?"공유 ZIP을 만들 수 있습니다":"공유 ZIP 불가 — 막힘 "+lastExport.blocks+" · 검증 미완료 "+lastExport.pending;
  exportState.ForeColor=lastExport.allowed?Color.DarkGreen:Color.Firebrick;
 }
 // ---- offscreen layout probe (no window shown, no input): selection sync and one picture per page ----
 int LayoutProbe(){
  string dir=Path.Combine(Root,"creator-probes","workflow-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(dir);
  var results=new List<object>();Func<string> state=()=>"current="+currentSlot.SelectedIndex+" slot="+slotPicker.SelectedIndex+" settings="+slotSettingsPicker.SelectedIndex+" terrain="+terrainSlot.SelectedIndex+" map="+map.Selected+" selected="+(selected>=0?project.empire.cities[selected].name_id:-1);Action<string,bool> check=(n,ok)=>results.Add(new{name=n,passed=ok,state=state()});
  ClientSize=new Size(1280,820);PrepareOffscreen(this);
  RefreshChecks();check("findings_listed",findingsList.Items.Count>0&&exportState.Text.Length>0);
  check("five_work_pages",tabs.TabPages.Count==5&&tabs.TabPages[3]==specialPage&&tabs.TabPages[4]==checkPage&&slotTabs.TabPages.Count==6&&tabs.TabPages[0].Text.StartsWith("1  승리 조건")&&goalTabs.TabPages.Count==2&&goalTabs.TabPages[0]==victoryPage);
  ForgetSeaLimits();SeaLimit(project.slots[0].id);linksShownVersion=linksVersion;
  FocusSlot(1,true);AfterShowCity();
  bool pickersFollow=SlotPickers().All(c=>c.Items.Count<=1||c.SelectedIndex==1);
  check("p2_all_pickers",pickersFollow&&currentSlot.SelectedIndex==1);
  check("p2_map_selected",map.Selected==project.slots[1].name_id&&project.empire.cities[selected].name_id==project.slots[1].name_id);
  check("p2_summary",citySummary.Text.Contains("P2"));
  ShowSlotSettings();results.Add(new{name="p2_trade_text",passed=true,state=linkSummary.Text.Length>300?linkSummary.Text.Substring(0,300):linkSummary.Text});check("p2_trade_list",slotSettingsPicker.SelectedIndex==1&&linkSummary.Text.Length>0&&!linkSummary.Text.Contains(CityName(project.slots[1].name_id)+" — "));
  SelectCity(project.slots[2].name_id);AfterShowCity();
  check("map_click_moves_slot",currentSlot.SelectedIndex==2&&slotPicker.SelectedIndex==2&&slotSettingsPicker.SelectedIndex==2);
  slotPicker.SelectedIndex=0;FocusSlot(slotPicker.SelectedIndex,true);check("inner_picker_moves_all",currentSlot.SelectedIndex==0&&slotSettingsPicker.SelectedIndex==0&&terrainSlot.SelectedIndex==0);
  Changed();check("stale_links_hidden",MapLinksFor(project.slots[0].name_id)==null);
  RefreshLinksNow();check("fresh_links_drawn",MapLinksFor(project.slots[0].name_id)!=null);
  FocusSlot(1,true);AfterShowCity();
  foreach(var size in new[]{new Size(1280,820),new Size(1024,700)}){
   ClientSize=size;PrepareOffscreen(this);
   for(int i=0;i<tabs.TabPages.Count;i++){
    tabs.SelectedIndex=i;if(tabs.SelectedTab==checkPage)RefreshChecks();if(tabs.SelectedTab==stepsPage)RefreshOverviewFacts();
    int inner=tabs.SelectedTab==slotPage?slotTabs.TabPages.Count:tabs.SelectedTab==stepsPage?goalTabs.TabPages.Count:1;
    for(int j=0;j<inner;j++){
     if(tabs.SelectedTab==slotPage){slotTabs.SelectedIndex=j;if(slotTabs.SelectedTab==slotSettingsTab)ShowSlotSettings();}
     if(tabs.SelectedTab==stepsPage)goalTabs.SelectedIndex=j;
     PrepareOffscreen(this);
     using(var ui=new Bitmap(ClientSize.Width,ClientSize.Height))using(var g=Graphics.FromImage(ui)){PaintOffscreen(Controls[0],g,Point.Empty);ui.Save(Path.Combine(dir,size.Width+"-tab"+(i+1)+(inner>1?"-"+(j+1):"")+".png"));}
    }
   }
  }
  check("pages_keep_slot",currentSlot.SelectedIndex==1&&SlotPickers().All(c=>c.Items.Count<=1||c.SelectedIndex==1)&&project.empire.cities[selected].name_id==project.slots[1].name_id);
  // ---- Rome: fixed capital, read-only (CreatorRome.cs, rome-capital.json) ----
  var rome=RomeCapital.Spec;check("rome_spec",rome!=null&&rome.x==768&&rome.y==496&&rome.keep_clear==24);
  check("rome_icon",RomeCapital.Icon!=null&&RomeCapital.Icon.Width==50&&RomeCapital.Icon.Height==53);
  if(rome!=null){
   var mapSize=new Size(900,450);var at=map.Position(rome.x,rome.y,mapSize);
   check("rome_hit_not_city",map.HitRome(at,mapSize)&&map.Hit(at,mapSize)==0);
   int slotBefore=currentSlot.SelectedIndex,cityBefore=map.Selected;string before=SerializeProject(project);
   ShowRome();check("rome_keeps_slot",currentSlot.SelectedIndex==slotBefore&&map.Selected==cityBefore&&citySummary.Text.Contains("고정 수도")&&SerializeProject(project)==before);
   check("rome_not_saved",!before.Contains("\"rome\""));
   const string romeText="위대한 황제께서 거처하시며 온 세상은 그의 발밑에 있습니다. 당신은 그의 명령에 복종합니다. 지금으로서는 그렇습니다.";
   check("rome_text_exact",citySummary.Text.StartsWith("로마 — 위대한 제국의 수도")&&citySummary.Text.Contains(romeText)&&citySummary.Text.Contains("고정 수도 · 플레이 도시 아님")&&rome.description==romeText);
   var near=project.empire.cities.OrderBy(c=>(c.x-rome.x)*(c.x-rome.x)+(c.y-rome.y)*(c.y-rome.y)).First();var nearAt=map.Position(near.x,near.y,mapSize);
   results.Add(new{name="rome_neighbour",passed=true,state=CityName(near.name_id)+" "+near.x+","+near.y+" screen "+(int)Math.Sqrt((nearAt.X-at.X)*(nearAt.X-at.X)+(nearAt.Y-at.Y)*(nearAt.Y-at.Y))+"px"});
   check("rome_and_neighbour_separate",map.PicksRome(at,mapSize,map.Hit(at,mapSize))&&!map.PicksRome(nearAt,mapSize,map.Hit(nearAt,mapSize))&&map.Hit(nearAt,mapSize)==near.name_id);
   string beforeDraw=SerializeProject(project);var linksBefore=Json.Serialize(MapLinksFor(project.slots[0].name_id));
   using(var bmp=new Bitmap(mapSize.Width,mapSize.Height))using(var g=Graphics.FromImage(bmp)){map.Draw(g,mapSize);bmp.Save(Path.Combine(dir,"map-rome.png"));}
   check("drawing_changes_nothing",SerializeProject(project)==beforeDraw&&Json.Serialize(MapLinksFor(project.slots[0].name_id))==linksBefore);
   var npc=project.empire.cities.First(c=>c.role=="npc");int ox=npc.x,oy=npc.y;bool refused=false;Action<int> onRefuse=id=>refused=true;map.PositionRefused+=onRefuse;
   map.MoveCity(npc.name_id,rome.x+5,rome.y+3);check("rome_move_refused",refused&&npc.x==ox&&npc.y==oy);
   refused=false;map.MoveCity(npc.name_id,rome.x+30,rome.y);check("rome_near_allowed",!refused&&npc.x==rome.x+30&&npc.y==rome.y);
   map.MoveCity(npc.name_id,ox,oy);map.PositionRefused-=onRefuse;
   int count=project.empire.cities.Length;bool addRefused=false;   // placing (or re-placing) a neutral city on Rome
   try{AddNeutral(npc.name_id,rome.x,rome.y);}catch(Exception){addRefused=true;}check("rome_add_refused",addRefused&&project.empire.cities.Length==count&&npc.x==ox&&npc.y==oy);
  }
  // ---- salary amounts: labels and notes only, values unchanged (CreatorSalary.cs) ----
  var govTab=slotTabs.TabPages.Cast<TabPage>().First(t=>t.Text.Contains("통치자"));var govPanel=govTab.Controls.OfType<TableLayoutPanel>().First();
  var gUse=(CheckBox)govPanel.GetControlFromPosition(1,1);var gRank=(ComboBox)govPanel.GetControlFromPosition(1,2);var gSalary=(ComboBox)govPanel.GetControlFromPosition(1,3);var gNote=(Label)govPanel.GetControlFromPosition(0,7);
  var table=new[]{0,2,5,8,12,20,30,40,60,80,100};   // engine output of city_emperor_salary_for_rank at base 100 (worker governance-audit.json)
  salaryCache[SalaryKey(project.slots[1])]=new SalaryFacts{@base=100,by_rank=table};salaryCache[SalaryKey(project.slots[0])]=null;
  FocusSlot(1,true);gUse.Checked=true;gRank.SelectedIndex=9;gSalary.SelectedIndex=0;
  check("salary_rank_label",(string)gRank.Items[9]=="총독 — 월 80 데나리"&&(string)gSalary.Items[0]=="직급에 맞춤 — 현재 월 80 데나리"&&gNote.Text.Contains("봉급: 월 80 데나리"));
  check("salary_all_ranks",Enumerable.Range(0,11).All(i=>((string)gRank.Items[i]).EndsWith("월 "+table[i].ToString("N0")+" 데나리")&&((string)gSalary.Items[i+1]).EndsWith("월 "+table[i].ToString("N0")+" 데나리")));
  gSalary.SelectedIndex=11;check("salary_differs",gNote.Text.Contains("직급 기준 월 80 데나리 / 설정 봉급 월 100 데나리"));
  check("salary_saved_values",project.slots[1].governance!=null&&project.slots[1].governance.rank==9&&project.slots[1].governance.salary_rank==10);
  gRank.SelectedIndex=4;check("salary_match_follows_rank",(string)gSalary.Items[0]=="직급에 맞춤 — 현재 월 12 데나리");
  string beforeSwitch=SerializeProject(project);FocusSlot(0,true);
  check("salary_standard_other_slot",(string)gRank.Items[9]=="총독 — 월 80 데나리 (표준)"&&gNote.Text.Contains("표준"));
  FocusSlot(1,true);check("salary_relabel_no_change",SerializeProject(project)==beforeSwitch&&(string)gRank.Items[4]=="검찰관 — 월 12 데나리");
  var copy=Json.Deserialize<Scenario>(SerializeProject(project));check("salary_roundtrip",copy.slots[1].governance.rank==4&&copy.slots[1].governance.salary_rank==10);
  gUse.Checked=false;check("salary_off",project.slots[1].governance==null&&gNote.Text.Contains("기존 시작 방식의 봉급(시민 직급): 월 0 데나리"));
  gUse.Checked=true;FocusSlot(1,true);
  string gone=project.slots[3].id;if(project.start_message==null)project.start_message=new StartMessage();if(project.start_message.per_city==null)project.start_message.per_city=new Dictionary<string,string>();project.start_message.per_city[gone]="probe";RemovePlayerData(project.slots[3].name_id);
  {string saved=Path.Combine(Root,"creator-probes","delete-check.json"),error="";try{StoreCity();File.WriteAllText(saved,SerializeProject(project),new UTF8Encoding(false));Check(saved,"");}catch(Exception e){error=e.Message;}finally{File.Delete(saved);}check("delete_keeps_file_valid",error==""&&!project.start_message.per_city.ContainsKey(gone));project.start_message.per_city.Clear();}RefreshCities();Changed();RefreshLinksNow();FocusSlot(2,true);AfterShowCity();
  check("delete_cleans_selection",currentSlot.Items.Count==3&&slotSettingsPicker.Items.Count==3&&currentSlot.SelectedIndex==2&&LinksForSlot(gone)==null&&!slotLinks.Values.Any(ls=>ls.Any(l=>l.slot==gone)));
  // 황제의 순행 (user 2026-11-15: "시나리오 생성부터"): chosen on the victory page, edited, checked by the game's own
  // validation, written as format 4; the struggle for the throne next to it leaves no trace and back.
  {Func<Dictionary<string,object>> file=()=>Json.Deserialize<Dictionary<string,object>>(SerializeProject(project));
   Func<string> valid=()=>{string saved=Path.Combine(Root,"creator-probes","progress-check.json");try{StoreCity();File.WriteAllText(saved,SerializeProject(project),new UTF8Encoding(false));Check(saved,"");return "";}catch(Exception e){return e.Message;}finally{File.Delete(saved);}};
   objectiveMode.SelectedIndex=2;competitionKind.SelectedIndex=1;CompetitionChosen(true);
   var f=file();var r=(Dictionary<string,object>)f["rules"];
   check("progress_chosen",ProgressEnabled&&Convert.ToInt32(f["schema"])==4&&Convert.ToString(r["mode"])=="imperial-progress"&&r.ContainsKey("progress")&&!r.ContainsKey("throne")&&!r.ContainsKey("objectives")&&minPlayers.Minimum==2);results.Add(new{name="progress_state",passed=true,state=Json.Serialize(r)+" min "+minPlayers.Minimum+" schema "+f["schema"]});
   foreach(DataGridViewRow row in progressGrid.Rows)if((string)((object[])row.Tag)[0]=="rounds")row.Cells[1].Value="9";
   r=(Dictionary<string,object>)file()["rules"];check("progress_edit_kept",Convert.ToInt32(((Dictionary<string,object>)r["progress"])["rounds"])==9&&progressError==null);
   check("progress_file_valid",valid()=="");
   for(int i=0;i<progressGoods.Items.Count;i++)progressGoods.SetItemChecked(i,i<2);ProgressEdited();
   bool blocked=false;try{ProgressRequireValid();}catch(Exception){blocked=true;}check("progress_two_goods_blocked",blocked&&progressError!=null);
   for(int i=0;i<progressGoods.Items.Count;i++)progressGoods.SetItemChecked(i,i<4);ProgressEdited();
   foreach(DataGridViewRow row in progressGrid.Rows)if((string)((object[])row.Tag)[0]=="amount_min")row.Cells[1].Value="33";
   check("progress_range_blocked",progressError!=null);
   foreach(DataGridViewRow row in progressGrid.Rows)if((string)((object[])row.Tag)[0]=="amount_min")row.Cells[1].Value="8";
   check("progress_range_fixed",progressError==null&&valid()=="");
   competitionKind.SelectedIndex=0;CompetitionChosen(true);f=file();r=(Dictionary<string,object>)f["rules"];
   check("progress_to_throne",Convert.ToInt32(f["schema"])==5&&Convert.ToString(r["mode"])=="race-for-throne"&&!r.ContainsKey("progress"));
   competitionKind.SelectedIndex=1;CompetitionChosen(true);f=file();r=(Dictionary<string,object>)f["rules"];
   check("throne_to_progress",Convert.ToInt32(f["schema"])==4&&Convert.ToString(r["mode"])=="imperial-progress"&&!r.ContainsKey("throne")&&!((Dictionary<string,object>)f["empire"]).ContainsKey("rome")&&valid()=="");
   objectiveMode.SelectedIndex=0;CompetitionChosen(false);r=(Dictionary<string,object>)file()["rules"];
   check("progress_off",!r.ContainsKey("progress")&&Convert.ToString(r["mode"])=="free-build"&&minPlayers.Minimum==1&&!r.ContainsKey("min_players"));
   objectiveMode.SelectedIndex=2;competitionKind.SelectedIndex=1;CompetitionChosen(true);minPlayers.Value=3;objectiveMode.SelectedIndex=0;CompetitionChosen(false);r=(Dictionary<string,object>)file()["rules"];
   check("min_players_by_hand_stays",r.ContainsKey("min_players")&&Convert.ToInt32(r["min_players"])==3);minPlayers.Value=1;}
  File.WriteAllText(Path.Combine(dir,"result.json"),Json.Serialize(results));File.WriteAllText(Path.Combine(Root,"creator-workflow-latest.txt"),dir);
  Console.WriteLine(Json.Serialize(new{dir=dir,results=results}));dirty=false;return results.Cast<object>().All(r=>(bool)r.GetType().GetProperty("passed").GetValue(r))?0:1;
 }
}

// Busy frame (user 2026-11-13): while the editor works (an engine check, a terrain import... the window is disabled and shows
// the wait cursor), two gold marks run around the window's edge, in the margin of the outer panel, so it is plain that the
// editor is working and not frozen. Drawing only: nothing else changes.
partial class ScenarioCreator {
 System.Windows.Forms.Timer busyTimer;float busyPhase;bool busyShown;
 void StartBusyFrame(Control host){
  typeof(Control).GetProperty("DoubleBuffered",System.Reflection.BindingFlags.NonPublic|System.Reflection.BindingFlags.Instance).SetValue(host,true,null);
  busyTimer=new System.Windows.Forms.Timer{Interval=33};
  busyTimer.Tick+=(s,e)=>{
   bool busy=UseWaitCursor||!Enabled;
   if(busy){busyPhase+=0.011f;if(busyPhase>=1)busyPhase-=1;busyShown=true;InvalidateBusyFrame(host);}
   else if(busyShown){busyShown=false;InvalidateBusyFrame(host);}
  };
  busyTimer.Start();
  host.Paint+=(s,e)=>{if(busyShown)DrawBusyFrame(e.Graphics,host.ClientRectangle);};
  FormClosed+=(s,e)=>busyTimer.Dispose();
 }
 static void InvalidateBusyFrame(Control host){var r=host.ClientRectangle;int b=12;
  host.Invalidate(new Rectangle(r.Left,r.Top,r.Width,b));host.Invalidate(new Rectangle(r.Left,r.Bottom-b,r.Width,b));
  host.Invalidate(new Rectangle(r.Left,r.Top,b,r.Height));host.Invalidate(new Rectangle(r.Right-b,r.Top,b,r.Height));}
 static PointF AlongFrame(RectangleF r,float d){float w=r.Width,h=r.Height,p=2*(w+h);d%=p;if(d<0)d+=p;
  if(d<w)return new PointF(r.Left+d,r.Top);d-=w;if(d<h)return new PointF(r.Right,r.Top+d);d-=h;if(d<w)return new PointF(r.Right-d,r.Bottom);d-=w;return new PointF(r.Left,r.Bottom-d);}
 void DrawBusyFrame(Graphics g,Rectangle area){
  var r=new RectangleF(area.Left+6f,area.Top+6f,area.Width-12,area.Height-12);if(r.Width<40||r.Height<40)return;
  float p=2*(r.Width+r.Height),tail=p*.2f;var old=g.SmoothingMode;g.SmoothingMode=System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
  using(var track=new Pen(Color.FromArgb(80,150,110,40),5f))g.DrawRectangle(track,r.X,r.Y,r.Width,r.Height);
  for(int k=0;k<2;k++){float head=busyPhase*p+k*p/2;
   for(float t=0;t<tail;t+=3){float a=t/tail;
    using(var pen=new Pen(Color.FromArgb((int)(20+235*a*a),226,150,10),6f){StartCap=System.Drawing.Drawing2D.LineCap.Round,EndCap=System.Drawing.Drawing2D.LineCap.Round})
     g.DrawLine(pen,AlongFrame(r,head-tail+t),AlongFrame(r,Math.Min(head,head-tail+t+3)));}}
  g.SmoothingMode=old;}
}
