using System;
using System.Linq;
using System.Drawing;
using System.Collections.Generic;
using System.Windows.Forms;
using System.IO;
partial class ScenarioCreator {
 /* P1-P8 on one line of small cards (user 2026-11-15): the map below gets the room. */TableLayoutPanel playerCards=new TableLayoutPanel{Dock=DockStyle.Top,AutoSize=true,AutoSizeMode=AutoSizeMode.GrowAndShrink,ColumnCount=8,RowCount=1};ToolTip cardTips=new ToolTip();
 Label mapInstruction=new Label{AutoSize=true,Font=new Font("Malgun Gothic",10,FontStyle.Bold),Margin=new Padding(12,3,3,3)};
 TabControl cityPages;Button attachTerrain;CheckBox editPositions=new CheckBox{Text="도시 위치 편집",AutoSize=true,Padding=new Padding(8,7,0,0)};
 TextBox citySearch=new TextBox{Dock=DockStyle.Fill};
 List<int> visibleCities=new List<int>();int assignmentSlot=-1;
 ContextMenuStrip cityActions=new ContextMenuStrip();
 Control BuildMapWorkflow(){
  var box=new TableLayoutPanel{Dock=DockStyle.Top,AutoSize=true,ColumnCount=1,RowCount=3};
  for(int i=0;i<8;i++)playerCards.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
  playerCards.RowStyles.Add(new RowStyle(SizeType.AutoSize));
  box.RowStyles.Add(new RowStyle(SizeType.AutoSize));box.RowStyles.Add(new RowStyle(SizeType.AutoSize));
  var playerRow=new TableLayoutPanel{Dock=DockStyle.Top,AutoSize=true,ColumnCount=2,RowCount=1};
  playerRow.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));playerRow.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
  playerRow.Controls.Add(playerCards,0,0);var playerTools=new FlowLayoutPanel{AutoSize=true,WrapContents=false,Margin=new Padding(12,0,0,0)};
  playerTools.Controls.Add(Button("플레이어 추가",AddPlayer,108));playerTools.Controls.Add(Button("선택 P 삭제",RemovePlayer,108));playerTools.Controls.Add(Button("지도 보관함…",ShowShelf,118));
  playerRow.Controls.Add(playerTools,1,0);box.Controls.Add(playerRow,0,0);
  var tools=new FlowLayoutPanel{Dock=DockStyle.Top,AutoSize=true,WrapContents=true};
  /* one line under the cards (user 2026-11-15): small map buttons, the two switches and the instruction */
  Func<Control,Control> small=c=>{c.Height=28;return c;};
  tools.Controls.Add(small(Button("배정 취소",CancelMapAssignment,90)));tools.Controls.Add(small(Button("＋",()=>map.ZoomAt(1.25f,new PointF(map.Width/2f,map.Height/2f)),40)));tools.Controls.Add(small(Button("－",()=>map.ZoomAt(.8f,new PointF(map.Width/2f,map.Height/2f)),40)));tools.Controls.Add(small(Button("지도 전체",()=>map.FitMap(),80)));tools.Controls.Add(editPositions);var routes=new CheckBox{Text="교역 연결 보기",AutoSize=true,Padding=new Padding(2,7,0,0)};routes.CheckedChanged+=(s,e)=>{map.ShowConnections=routes.Checked;map.Invalidate();};tools.Controls.Add(routes);
  tools.Controls.Add(mapInstruction);box.Controls.Add(tools,0,1);
  editPositions.CheckedChanged+=(s,e)=>{assignmentSlot=-1;map.EditPositions=editPositions.Checked;map.PlacementMode=false;pendingNeutral=0;posX.Enabled=posY.Enabled=editPositions.Checked;RefreshMapCards();};
  citySearch.TextChanged+=(s,e)=>{if(project!=null)RefreshCityList();};
  map.CityActionsRequested+=(id)=>Guard(()=>OpenMapActions(id));
  return box;
 }
 void RefreshMapCards(){
  if(project==null)return;if(assignmentSlot>=project.slots.Length)assignmentSlot=-1;
  playerCards.SuspendLayout();foreach(Control c in playerCards.Controls.Cast<Control>().ToArray()){playerCards.Controls.Remove(c);c.Dispose();}
  for(int i=0;i<project.slots.Length;i++){int index=i;var b=Button("P"+(i+1)+"  "+(assignmentSlot==i?Lang.T("도시 선택 중"):CityName(project.slots[i].name_id)),()=>BeginMapAssignment(index),112);b.Height=34;cardTips.SetToolTip(b,Lang.T("클릭하여 도시 변경"));b.BackColor=assignmentSlot==i?CreatorMapView.PlayerColor(i):ButtonFace;b.ForeColor=assignmentSlot==i?Color.White:Dark;b.FlatAppearance.BorderColor=CreatorMapView.PlayerColor(i);b.FlatAppearance.BorderSize=assignmentSlot==i?3:2;b.AutoEllipsis=true;playerCards.Controls.Add(b,i,0);}
  playerCards.ResumeLayout();map.AssignmentSlot=assignmentSlot;map.Invalidate();
  mapInstruction.Text=assignmentSlot>=0?"P"+(assignmentSlot+1)+"을 배정할 녹색 도시를 선택하세요. 다른 플레이어의 도시는 선택할 수 없습니다.":editPositions.Checked?"위치 편집 중 · 도시 점을 끌면 위치가 바뀝니다. 끝나면 ‘도시 위치 편집’을 끄세요.":"P자리를 고른 뒤 녹색 도시를 누르세요 (휠: 확대, 빈 곳 끌기: 이동). 최대 8자리 중 "+OnlinePlayerLimit+"명까지 플레이";
 }
 void BeginMapAssignment(int index){
  if(index<0||index>=project.slots.Length)return;StoreCity();editPositions.Checked=false;map.PlacementMode=false;pendingNeutral=0;assignmentSlot=index;SelectCity(project.slots[index].name_id);RefreshMapCards();
 }
 void CancelMapAssignment(){assignmentSlot=-1;map.PlacementMode=false;pendingNeutral=0;cityActions.Close();RefreshMapCards();}
 bool AssignMapCity(int id){
  if(assignmentSlot<0)return false;int slot=assignmentSlot;SelectCity(id);
  if(!HasTerrain(id))throw new Exception("이 도시는 중립도시입니다. 녹색 도시를 선택하세요.");
  int other=Array.FindIndex(project.slots,p=>p.name_id==id);if(other>=0&&other!=slot)throw new Exception("P"+(other+1)+"이 이미 배정된 도시입니다. 다른 녹색 도시를 선택하세요.");
  if(other!=slot){var current=project.slots[slot];if((current.terrain_edits!=null&&current.terrain_edits.Length>0)||current.terrain_asset!=null){if(LangBox.Show(this,"P"+(slot+1)+"의 도시를 변경하면 해당 자리의 지형 수정도 새 도시 원본으로 바뀝니다. 바꿀까요?","도시 변경",MessageBoxButtons.YesNo,MessageBoxIcon.Question,MessageBoxDefaultButton.Button2)!=DialogResult.Yes)return false;}AssignCity(slot,id);}
  CancelMapAssignment();mapInstruction.Text="P"+(slot+1)+": "+CityName(id)+" 배정 완료. 다음 P자리 또는 중립도시를 선택하세요.";return true;
 }
 void MapCitySelected(int id){if(assignmentSlot>=0){AssignMapCity(id);return;}SelectCity(id);}
 void OpenMapActions(int id){
  if(assignmentSlot>=0||editPositions.Checked)return;SelectCity(id);cityActions.Items.Clear();var city=Array.Find(project.empire.cities,c=>c.name_id==id);
  cityActions.Items.Add(CityName(id)).Enabled=false;
  if(city.role=="npc"&&HasTerrain(id)){var assign=new ToolStripMenuItem("플레이어 도시에 배정");for(int i=0;i<project.slots.Length;i++){int index=i;assign.DropDownItems.Add("P"+(i+1)+" · "+CityName(project.slots[i].name_id),null,(s,e)=>Guard(()=>{BeginMapAssignment(index);AssignMapCity(id);}));}cityActions.Items.Add(assign);}
  if(city.role=="npc"){cityActions.Items.Add(city.enabled?"중립도시 끄기":"중립도시 켜기",null,(s,e)=>Guard(()=>{SelectCity(id);RemoveNeutral();}));cityActions.Items.Add("교역 설정으로 이동",null,(s,e)=>{grid.Focus();});}
  else cityActions.Items.Add("지형·건설 설정으로 이동",null,(s,e)=>{OpenConstructionPage();slotPicker.SelectedIndex=Array.FindIndex(project.slots,p=>p.name_id==id);});
  var at=map.Position(city.x,city.y,map.ClientSize);cityActions.Show(map,new Point(Math.Max(0,Math.Min(map.Width-20,(int)at.X+14)),Math.Max(0,Math.Min(map.Height-20,(int)at.Y+14))));
 }
 void SearchCityList(){
  int keep=selected;bool previous=loading;loading=true;cities.Items.Clear();visibleCities.Clear();string find=citySearch.Text.Trim();
  foreach(var c in project.empire.cities){int slot=Array.FindIndex(project.slots,s=>s.name_id==c.name_id);string label=(slot>=0?"P"+(slot+1)+"  ":c.enabled?"중립  ":"꺼짐  ")+CityName(c.name_id);if(find.Length>0&&label.IndexOf(find,StringComparison.CurrentCultureIgnoreCase)<0)continue;visibleCities.Add(c.name_id);cities.Items.Add(label);}
  cities.SelectedIndex=keep>=0?visibleCities.IndexOf(project.empire.cities[keep].name_id):-1;loading=previous;
 }
 int MapWorkflowProbe(){
  string dir=Path.Combine(Root,"creator-probes","workflow-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(dir);
  int target=merged.cities.First(c=>HasTerrain(c.name_id)&&LocalAvailableTerrain(c.name_id)&&!project.slots.Any(s=>s.name_id==c.name_id)).name_id;
  BeginMapAssignment(1);bool blocked=false;try{AssignMapCity(project.slots[0].name_id);}catch{blocked=true;}if(!blocked||assignmentSlot!=1)throw new Exception("Occupied slot guard failed");
  int brown=merged.cities.First(c=>!HasTerrain(c.name_id)).name_id;blocked=false;try{AssignMapCity(brown);}catch{blocked=true;}if(!blocked||assignmentSlot!=1)throw new Exception("Neutral assignment guard failed");
  if(!AssignMapCity(target)||project.slots[1].name_id!=target||assignmentSlot!=-1)throw new Exception("Direct assignment failed");
  var city=project.empire.cities.First(c=>c.name_id==target);int x=city.x,y=city.y;if(map.DragCityTo(target,x+4,y+4)||city.x!=x)throw new Exception("Normal mode moved city");
  editPositions.Checked=true;if(!map.DragCityTo(target,x+4,y+4)||city.x!=x+4)throw new Exception("Position mode failed");map.DragCityTo(target,x,y);editPositions.Checked=false;
  citySearch.Text=CityName(target);if(visibleCities.Count!=1||visibleCities[0]!=target)throw new Exception("Search ID mapping failed");cities.SelectedIndex=0;if(project.empire.cities[selected].name_id!=target)throw new Exception("Filtered selection failed");citySearch.Text="";
  PrepareOffscreen(this);var anchor=new PointF(map.Width*.45f,map.Height*.5f);var before=map.World(anchor,map.ClientSize);map.ZoomAt(2,anchor);var after=map.World(anchor,map.ClientSize);if(Math.Abs(before.X-after.X)>1||Math.Abs(before.Y-after.Y)>1)throw new Exception("Zoom anchor shifted");map.PanBy(80,20);foreach(var c in project.empire.cities){var at=map.Position(c.x,c.y,map.ClientSize);var back=map.World(at,map.ClientSize);if(Math.Abs(back.X-c.x)>1||Math.Abs(back.Y-c.y)>1)throw new Exception("Zoomed coordinate roundtrip failed");}if(city.x!=x||city.y!=y)throw new Exception("Navigation changed scenario");map.FitMap();
  BeginMapAssignment(2);RenderEditor(dir,0);File.Copy(Path.Combine(dir,"editor-tab-0.png"),Path.Combine(dir,"assign-slot.png"));CancelMapAssignment();
  ClientSize=new Size(1280,820);RenderEditor(dir,0);File.Copy(Path.Combine(dir,"editor-tab-0.png"),Path.Combine(dir,"minimum-window.png"));
  RefreshMapCards();if(playerCards.Controls.Count!=4)throw new Exception("Four cards missing");var original=Json.Deserialize<Scenario>(SerializeProject(project));while(project.slots.Length<8)AddPlayer();bool rejected=false;try{AddPlayer();}catch{rejected=true;}if(!rejected)throw new Exception("Ninth player accepted");Adopt(original);
  int[] npcs=project.empire.cities.Where(c=>c.role=="npc").Take(3).Select(c=>c.name_id).ToArray();SetNeutralBatch(npcs,true,new[]{project.slots[0].id});foreach(var n in npcs){var c=project.empire.cities.First(v=>v.name_id==n);if(!c.enabled||c.trade_players.Length!=1)throw new Exception("Bulk access failed");}SelectCity(npcs[0]);if(construction.Enabled)throw new Exception("NPC construction enabled");RenderEditor(dir,0);File.Copy(Path.Combine(dir,"editor-tab-0.png"),Path.Combine(dir,"neutral-resources.png"));

  objectiveMode.SelectedIndex=1;/* goal conditions are editable only after choosing cooperative victory */
  goalRecipe.SelectedIndex=0;recipeAmount.Value=20000;ApplyGoalRecipe(true);
  goalRecipe.SelectedIndex=1;recipeAmount.Value=5000;recipeCulture.Value=50;recipeProsperity.Value=40;recipePeace.Value=30;recipeFavor.Value=60;ApplyGoalRecipe(false);/* every city figure at once (user 2026-11-15) */foreach(DataGridViewRow row in objectiveGrid.Rows)if(Convert.ToInt32(row.Cells[3].Value)!=40||Convert.ToInt32(row.Cells[4].Value)!=30||Convert.ToInt32(row.Cells[5].Value)!=60)throw new Exception("Develop-all recipe left figures out");
  recipeProsperity.Value=recipePeace.Value=recipeFavor.Value=0;ApplyGoalRecipe(false);
  goalRecipe.SelectedIndex=2;recipeAmount.Value=100000;ApplyGoalRecipe(false);
  StoreObjectives(true);var chosen=Json.Deserialize<ObjectiveSettings>(Json.Serialize(project.rules["objectives"]));
  if(chosen.population_total!=20000||chosen.treasury_total!=100000||chosen.per_city.Count!=4||chosen.per_city.Values.Any(v=>v.population!=5000||v.culture!=50))throw new Exception("Goal recipes lost conditions");
  if(!objectiveSummary.Text.Contains("4개 조건")||!objectiveSummary.Text.Contains("모든 플레이어 도시")||!objectiveSummary.Text.Contains("누적 수입 아님"))throw new Exception("Goal explanation mismatch");
  RefreshObjectives();StoreObjectives(true);if(totalTreasury.Value!=100000)throw new Exception("Treasury roundtrip lost");
  RenderEditor(dir,3);File.Copy(Path.Combine(dir,"editor-tab-3.png"),Path.Combine(dir,"goal-recipes.png"));
  objectiveMode.SelectedIndex=1;totalPopulation.Value=1234;celebrationMode.SelectedIndex=1;StoreObjectives(true);var rules=Json.Deserialize<ObjectiveSettings>(Json.Serialize(project.rules["objectives"]));if(rules.celebration!="video")throw new Exception("Victory option lost");RenderEditor(dir,3);
  string saved=Snapshot();File.Copy(saved,Path.Combine(dir,"scenario.json"));File.Delete(saved);
  File.WriteAllText(Path.Combine(dir,"result.json"),Json.Serialize(new{passed=true,direct_assignment=true,occupied_guard=true,neutral_guard=true,explicit_move_mode=true,search_mapping=true,zoom_pan_preserve_data=true,four_cards=true,bulk_neutrals=true,trade_access=true,goal_recipes=true,goal_roundtrip=true,gui_automation=false}));File.WriteAllText(Path.Combine(Root,"creator-workflow-probe-latest.txt"),dir);dirty=false;return 0;
 }
}

