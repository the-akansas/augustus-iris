using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using System.Windows.Forms;
using System.Drawing;
using System.Text;
using System.Threading.Tasks;
public class ParkedTrade { public int sea,cost; public Dictionary<string,int> sells,buys; public string[] trade_players; public bool sea_auto; }
public class CoastGuess { public int? estimate; public string basis; }
public class AssetResult { public TerrainAsset terrain_asset; }
// City roles. Same rules as Augustus/scenario_cities.py (that file is the tested reference):
//  - the city owns its terrain (preset, tile edits, external map): kept in City.map while it is neutral, back when it is played;
//  - the slot owns allowed buildings, governance and the other play settings: they stay with the slot when its city changes;
//  - a neutral trade setup is kept on a player city (City.parked_trade);
//  - "sea only" set by hand always wins; only sea_auto cities follow the coast estimate.
partial class ScenarioCreator {
 CheckBox seaAuto=new CheckBox{Text="위치로 자동 추정",AutoSize=true};
 System.Windows.Forms.Timer coastTimer; City coastPending;

 static void CleanCityRecord(Dictionary<string,object> record){
  object reserved;if(record.TryGetValue("reserved",out reserved)&&!Equals(reserved,true))record.Remove("reserved");
  object flag;if(record.TryGetValue("sea_auto",out flag)&&!(flag is bool&&(bool)flag))record.Remove("sea_auto");
  object kept;
  if(record.TryGetValue("map",out kept)){
   var body=kept as Dictionary<string,object>;
   if(body==null)record.Remove("map");
   else{
    body.Remove("id");body.Remove("name_id");
    foreach(string key in new[]{"allowed_buildings","starting_setup","terrain_asset","governance","events","invasions","invasion_enemy","starting_funds","role_hint"})if(body.ContainsKey(key)&&body[key]==null)body.Remove(key);
    if(body.ContainsKey("terrain_edits")&&body["terrain_edits"]==null)body["terrain_edits"]=new object[0];
   }
  }
  object trade;
  if(record.TryGetValue("parked_trade",out trade)){
   var setup=trade as Dictionary<string,object>;
   if(setup==null)record.Remove("parked_trade");
   else{
    if(setup.ContainsKey("trade_players")&&setup["trade_players"]==null)setup.Remove("trade_players");
    object auto;if(setup.TryGetValue("sea_auto",out auto)&&!(auto is bool&&(bool)auto))setup.Remove("sea_auto");
   }
  }
 }

 // Only the terrain goes to the city. Slot settings are not copied.
 Slot ParkedCopy(Slot slot){return new Slot{campaign_scenario=slot.campaign_scenario,terrain_edits=slot.terrain_edits==null?new TerrainEdit[0]:(TerrainEdit[])slot.terrain_edits.Clone(),terrain_asset=slot.terrain_asset};}

 // player -> neutral: keep the terrain on the city; bring back the neutral trade setup it had.
 void ParkPlayerCity(City city,Slot slot){
  if(slot!=null)city.map=ParkedCopy(slot);
  var setup=city.parked_trade;
  if(setup==null){RestoreDefaultTrade(city);return;}
  city.sea=setup.sea;city.cost=setup.cost;
  city.sells=setup.sells??new Dictionary<string,int>();city.buys=setup.buys??new Dictionary<string,int>();
  city.trade_players=setup.trade_players==null?null:setup.trade_players.Where(id=>project.slots.Any(p=>p.id==id)).ToArray();
  city.sea_auto=setup.sea_auto;city.parked_trade=null;
 }

 // neutral -> player: remember the neutral trade setup before the player role clears it.
 void ParkNeutralTrade(City city){
  if(city.sells==null)city.sells=new Dictionary<string,int>();if(city.buys==null)city.buys=new Dictionary<string,int>();
  city.parked_trade=new ParkedTrade{sea=city.sea,cost=city.cost,sells=new Dictionary<string,int>(city.sells),buys=new Dictionary<string,int>(city.buys),trade_players=city.trade_players==null?null:(string[])city.trade_players.Clone(),sea_auto=city.sea_auto};
  city.trade_players=null;city.sea_auto=false;
 }

 // dropGoals: the shared goals that name this seat (its city numbers, the deliveries it sends or receives) leave with it
 // (user 2026-11-15: what can be put in must come out again; asked first in RemovePlayer).
 class GoalsInUseException : Exception {public GoalsInUseException(string m):base(m){}}
 Slot RequirePlayerRemoval(int name){return CheckPlayerRemoval(name,false);}   /* one-argument forms: handoff/Regression.cs calls them by name */
 Slot CheckPlayerRemoval(int name,bool dropGoals){
  var city=Array.Find(project.empire.cities,c=>c.name_id==name);
  var slot=Array.Find(project.slots,s=>s.name_id==name);
  if(city==null||city.role!="player"||slot==null)throw new Exception("플레이 도시가 아닙니다.");
  if(project.slots.Length<=2)throw new Exception("플레이어 도시는 최소 2개가 필요합니다.");
  object raw;
  if(project.rules.TryGetValue("objectives",out raw)&&raw!=null){
   var goals=Json.Deserialize<ObjectiveSettings>(Json.Serialize(raw));ObjectiveTarget target;
   bool uses=goals.per_city!=null&&goals.per_city.TryGetValue(slot.id,out target)&&
    (target.population!=0||target.culture!=0||target.prosperity!=0||target.peace!=0||target.favor!=0||target.treasury!=0);
   if(!dropGoals&&(uses||(goals.deliveries!=null&&goals.deliveries.Any(g=>g.sender==slot.id||g.receiver==slot.id))))
    throw new GoalsInUseException("이 도시를 쓰는 공동 목표가 있습니다. 목표에서 먼저 빼 주세요.");
  }
  return slot;
 }
 void RemovePlayerData(int name){RemovePlayerWithGoals(name,false);}
 void RemovePlayerWithGoals(int name,bool dropGoals){
  var leaving=CheckPlayerRemoval(name,dropGoals);object raw;
  if(project.rules.TryGetValue("objectives",out raw)&&raw!=null){
   var goals=Json.Deserialize<Dictionary<string,object>>(Json.Serialize(raw));object perCity;
   if(goals.TryGetValue("per_city",out perCity)&&perCity is Dictionary<string,object>)((Dictionary<string,object>)perCity).Remove(leaving.id);
   object sent;if(dropGoals&&goals.TryGetValue("deliveries",out sent)&&sent is System.Collections.IEnumerable)
    goals["deliveries"]=((System.Collections.IEnumerable)sent).Cast<object>().Where(g=>{var d=g as Dictionary<string,object>;return d==null||(Convert.ToString(d.ContainsKey("sender")?d["sender"]:null)!=leaving.id&&Convert.ToString(d.ContainsKey("receiver")?d["receiver"]:null)!=leaving.id);}).ToList();
   // 2026-11-15: counts of players the smaller scenario can no longer have leave too (the file allows 1..cities-1;
   // with more cities than can play, the last row is also the scenario total, so nothing is lost)
   object table;if(goals.TryGetValue("by_players",out table)&&table is Dictionary<string,object>){
    var rows=(Dictionary<string,object>)table;int left=project.slots.Length-1;
    foreach(var key in rows.Keys.ToList()){int n;if(!int.TryParse(key,out n)||n>=left)rows.Remove(key);}
    if(rows.Count==0)goals.Remove("by_players");
   }
   project.rules["objectives"]=goals;
  }
  project.slots=project.slots.Where(p=>p.id!=leaving.id).ToArray();
  if(project.start_message!=null&&project.start_message.per_city!=null)project.start_message.per_city.Remove(leaving.id);   // its own start text has no reader any more (else the file is refused)
  ForgetSlotPairs(leaving.id); // player-to-player exceptions name slots and leave with them
  var ids=new HashSet<string>(project.slots.Select(p=>p.id));
  foreach(var other in project.empire.cities){
   if(other.trade_players!=null)other.trade_players=other.trade_players.Where(ids.Contains).ToArray();
   if(other.parked_trade!=null&&other.parked_trade.trade_players!=null)
    other.parked_trade.trade_players=other.parked_trade.trade_players.Where(ids.Contains).ToArray();
  }
  var city=Array.Find(project.empire.cities,c=>c.name_id==name);
  city.role="npc";city.enabled=false;ParkPlayerCity(city,leaving);ForgetSeaLimits();
 }

 void RestoreParked(Slot slot,Slot kept){
  slot.campaign_scenario=kept.campaign_scenario;slot.terrain_edits=kept.terrain_edits??new TerrainEdit[0];slot.terrain_asset=kept.terrain_asset;
 }

 // A map written by the first draft of this feature may carry slot settings.
 // A newly created slot has no values of its own and takes them; an existing slot keeps its own and the author is told.
 void AdoptKeptSettings(Slot created,Slot kept){
  if(kept.allowed_buildings!=null)created.allowed_buildings=kept.allowed_buildings;
  if(kept.governance!=null)created.governance=kept.governance;
  if(kept.starting_setup!=null)created.starting_setup=kept.starting_setup;
  if(kept.events!=null)created.events=kept.events;
  if(kept.invasions!=null)created.invasions=kept.invasions;
  if(kept.invasion_enemy!=null)created.invasion_enemy=kept.invasion_enemy;
 }
 void NoteKeptSettings(Slot slot,Slot kept){
  bool differs=kept.governance!=null||kept.events!=null||kept.invasions!=null||kept.starting_setup!=null||(kept.allowed_buildings!=null&&(slot.allowed_buildings==null||!kept.allowed_buildings.SequenceEqual(slot.allowed_buildings)));
  if(differs&&!NonInteractive)LangBox.Show(this,"이 도시에 예전 형식으로 함께 보관돼 있던 허용 건물·통치 설정은 적용하지 않았습니다.\n이 자리의 현재 설정을 그대로 유지합니다.","플레이어 도시 변경",MessageBoxButtons.OK,MessageBoxIcon.Information);
 }

 void AttachCityTerrain(){
  if(selected<0)throw new Exception("도시를 먼저 선택하세요.");
  var city=project.empire.cities[selected];
  if(city.role!="npc")throw new Exception("플레이 도시의 지형은 지형 탭에서 바꿉니다.");
  if(city.map!=null&&city.map.terrain_edits!=null&&city.map.terrain_edits.Length>0)throw new Exception("이 도시에는 예전 플레이어 자리에서 그린 지형 수정이 남아 있습니다. 아래 '보관된 지형 지우기'로 먼저 지우세요.");
  NativeTerrainResult session;cityTerrainSessions.TryGetValue(city.name_id,out session);   /* after the editor: its save folder first */
  bool cancelled;var shelf=ChooseShelfMap(city,out cancelled);if(cancelled)return;
  if(shelf!=null){AttachCityAsset(city,shelf.terrain_asset,shelf.base_preset);return;}
  using(var dialog=new OpenFileDialog{Title=Lang.T("도시에 연결할 지도 파일"),Filter=Lang.T("Augustus 지도 또는 저장 파일 (*.mapx;*.svx)|*.mapx;*.svx"),InitialDirectory=session==null?"":Path.GetDirectoryName(session.map),FileName=session==null?"":Path.GetFileName(session.map)}){
   if(dialog.ShowDialog(this)!=DialogResult.OK)return;
   AttachCityTerrainFile(city,dialog.FileName);
  }
 }
 void AttachCityTerrainFile(City city,string file){
  var result=Json.Deserialize<AssetResult>(RunPython("scenario_cities.py","asset "+Quote(file)));
  if(result==null||result.terrain_asset==null)throw new Exception("지도 파일을 읽지 못했습니다.");
  string name=Path.GetFileNameWithoutExtension(file);if(file.EndsWith(".svx",StringComparison.OrdinalIgnoreCase))name=Lang.T("저장 파일")+": "+name;
  int basePreset=city.map!=null?city.map.campaign_scenario:-1;
  try{MapVersionAdd(city.name_id,result.terrain_asset,name,file,basePreset<0?2:basePreset,0,0,null);}catch{}   // onto the shelf too (CreatorCityLibrary.cs)
  AttachCityAsset(city,result.terrain_asset,basePreset);
 }

 // A neutral city's own map, without making it a player city (user 2026-11-15: "따로 지형편집만 할수 있는 로직"): the
 // map can be attached, opened in the map editor, brought back from it, and taken off again. The editor works on a
 // temporary copy of the project in which this city sits in the first seat; the project itself is not changed until
 // the saved map is attached. Before, a map could only be seen or edited after a player was assigned to the city.
 FlowLayoutPanel cityTerrainBar;Button editCityTerrain,detachCityTerrain,resetCityButton;Label cityTerrainNote;
 Dictionary<int,NativeTerrainResult> cityTerrainSessions=new Dictionary<int,NativeTerrainResult>();
 Control BuildCityTerrainBar(){
  cityTerrainBar=new FlowLayoutPanel{Dock=DockStyle.Top,AutoSize=true,AutoSizeMode=AutoSizeMode.GrowAndShrink,WrapContents=true,Margin=new Padding(0,4,0,0)};
  cityTerrainNote=new Label{AutoSize=true,MaximumSize=new Size(380,0),Padding=new Padding(0,0,0,4)};cityTerrainBar.Controls.Add(cityTerrainNote);cityTerrainBar.SetFlowBreak(cityTerrainNote,true);
  attachTerrain=Button("지도 파일 연결…",AttachCityTerrain);editCityTerrain=Button("지형 편집기 열기",OpenCityTerrainEditor);detachCityTerrain=Button("연결한 지도 빼기",DetachCityTerrain);
  cityTerrainBar.Controls.Add(attachTerrain);cityTerrainBar.Controls.Add(editCityTerrain);cityTerrainBar.Controls.Add(detachCityTerrain);
  /* the whole city back to what C3 gives (CreatorCityLibrary.cs ResetCityToC3) */resetCityButton=Button("C3 상태로 되돌리기",ResetCityToC3);cityTerrainBar.SetFlowBreak(detachCityTerrain,true);cityTerrainBar.Controls.Add(resetCityButton);
  return cityTerrainBar;
 }
 void RefreshCityTerrainBar(City c){
  if(cityTerrainBar==null||c==null||c.role!="npc")return;
  bool own=c.map!=null&&c.map.terrain_asset!=null,shipped=LocalAvailableTerrain(c.name_id);
  editCityTerrain.Enabled=own||shipped||(c.map!=null&&Array.Exists(presets.terrain,t=>t.id==c.map.campaign_scenario&&t.available));
  /* a map attached here, or the terrain kept from an earlier seat: both can be taken out (user 2026-11-15) */
  detachCityTerrain.Visible=c.map!=null;detachCityTerrain.Text=Lang.T(own?"연결한 지도 빼기":"보관된 지형 지우기");
  int shelfMaps=c.map==null&&!shipped?MapVersions(c.name_id).Count:0;
  cityTerrainNote.Text=Lang.T("이 도시의 지도")+": "+(own?Lang.T("연결한 지도 파일"):shipped?Lang.T("본편 지도"):c.map!=null?Lang.T("보관된 지형"):shelfMaps>0?Lang.T("이 PC의 지도 보관함")+" ("+shelfMaps+") — "+Lang.T("배정하면 가장 최근 지도를 씁니다."):Lang.T("없음 — 지도 파일을 연결하면 플레이 도시로 배정할 수 있습니다."))
   +(cityTerrainSessions.ContainsKey(c.name_id)?"\n"+Lang.T("편집기에서 저장한 뒤 '지도 파일 연결…'로 가져오세요."):"");
 }
 // The project as a file, with `city` in the first seat (its map, no starting town, no events or invasions that belong to
 // the seat's own map). Only for the editor's preparation; never saved.
 string CityTerrainProject(City city,out string seat){
  int terrainId=city.map!=null?city.map.campaign_scenario:PreferredTerrain(city.name_id);
  var value=Json.Deserialize<Dictionary<string,object>>(SerializeProject(project));
  var slots=((System.Collections.IEnumerable)value["slots"]).Cast<Dictionary<string,object>>().ToList();var first=slots[0];seat=Convert.ToString(first["id"]);
  int previous=Convert.ToInt32(first["name_id"]);
  foreach(string key in new[]{"terrain_asset","starting_setup","events","invasions","invasion_enemy"})first.Remove(key);
  first["name_id"]=city.name_id;first["campaign_scenario"]=terrainId;
  first["terrain_edits"]=city.map!=null&&city.map.terrain_edits!=null?(object)Json.Deserialize<List<object>>(Json.Serialize(city.map.terrain_edits)):new List<object>();
  if(city.map!=null&&city.map.terrain_asset!=null)first["terrain_asset"]=Json.Deserialize<Dictionary<string,object>>(Json.Serialize(city.map.terrain_asset));
  foreach(var other in ((System.Collections.IEnumerable)((Dictionary<string,object>)value["empire"])["cities"]).Cast<Dictionary<string,object>>()){
   int id=Convert.ToInt32(other["name_id"]);
   if(id==previous){other["role"]="npc";other["enabled"]=false;
    /* its neutral trade, kept while it plays (parked_trade: player cities only, scenario_project.py), comes back as it would */
    object kept;if(other.TryGetValue("parked_trade",out kept)&&kept is Dictionary<string,object>){foreach(var kv in (Dictionary<string,object>)kept)other[kv.Key]=kv.Value;other.Remove("parked_trade");}}
   if(id==city.name_id){other["role"]="player";other["enabled"]=true;other["sea"]=0;other["cost"]=0;other["sells"]=new Dictionary<string,object>();other["buys"]=new Dictionary<string,object>();foreach(string key in new[]{"map","trade_players","parked_trade","sea_auto","reserved"})other.Remove(key);}
  }
  string path=Path.Combine(Root,"creator-cache","city-terrain-"+Guid.NewGuid().ToString("N")+".json");Directory.CreateDirectory(Path.GetDirectoryName(path));
  File.WriteAllText(path,Json.Serialize(value),new UTF8Encoding(false));return path;
 }
 async void OpenCityTerrainEditor(){
  string path=null;
  try{
   if(selected<0)return;var city=project.empire.cities[selected];if(city.role!="npc")throw new Exception("플레이 도시의 지형은 3번 탭의 지형 페이지에서 편집합니다.");
   int terrainId=city.map!=null?city.map.campaign_scenario:PreferredTerrain(city.name_id);var original=Array.Find(presets.terrain,t=>t.id==terrainId);
   if((city.map==null||city.map.terrain_asset==null)&&original!=null&&original.original_population>0&&LangBox.Show(this,"정식 지형 편집으로 변환하면 기존 로마 건물과 주민은 제외됩니다. 원본은 보존됩니다.\n변환한 사본을 열까요?","지형 편집용 사본 만들기",MessageBoxButtons.YesNo,MessageBoxIcon.Warning,MessageBoxDefaultButton.Button2)!=DialogResult.Yes)return;
   string seat;path=CityTerrainProject(city,out seat);Enabled=false;UseWaitCursor=true;status.Text=CityName(city.name_id)+": "+Lang.T("정식 지형 편집용 사본을 준비하고 있습니다…");
   string source=path,slotId=seat;var result=ParseNative(await Task.Run(()=>RunPython("creator_native_editor.py","prepare --project "+Quote(source)+" --slot "+Quote(slotId))));
   if(!result.editor_ready)throw new Exception("정식 편집기에 필요한 파일을 준비하지 못했습니다. "+string.Join(", ",result.missing??new string[0]));
   cityTerrainSessions[city.name_id]=result;
   if(!NonInteractive)ParseNative(RunPython("creator_native_editor.py","launch --session "+Quote(result.session)));
   status.Text=CityName(city.name_id)+": "+Lang.T("편집기에서 지도를 저장한 뒤 '지도 파일 연결…'로 가져오세요. 아직 프로젝트는 바뀌지 않았습니다.");
   RefreshCityTerrainBar(city);
  }catch(Exception e){if(NonInteractive)throw;LangBox.Show(this,e.Message,"지형 편집기",MessageBoxButtons.OK,MessageBoxIcon.Warning);}
  finally{Enabled=true;UseWaitCursor=false;if(path!=null)try{File.Delete(path);}catch{}}
 }
 void DetachCityTerrain(){
  if(selected<0)return;var city=project.empire.cities[selected];if(city.role!="npc"||city.map==null)return;bool own=city.map.terrain_asset!=null;
  if(!NonInteractive&&LangBox.Show(this,own?"이 도시에 연결한 지도를 뺄까요? 이 PC의 지도 보관함에 있는 지도는 그대로 남습니다.":"이 도시에 보관된 지형(예전 플레이어 자리의 지형과 지형 수정)을 지울까요? 다시 배정하면 처음 지형으로 시작합니다.",own?"연결한 지도 빼기":"보관된 지형 지우기",MessageBoxButtons.YesNo,MessageBoxIcon.Question,MessageBoxDefaultButton.Button2)!=DialogResult.Yes)return;
  city.map=null;   /* edits belong to the map they were painted on: they leave with it */
  cityTerrainSessions.Remove(city.name_id);Changed();SyncPlayable();ShowCity(selected);map.Invalidate();
  status.Text=CityName(city.name_id)+": "+Lang.T(own?"연결한 지도를 뺐습니다.":"보관된 지형을 지웠습니다.");
 }

 void WireCityRoles(){
  seaAuto.CheckedChanged+=(s,e)=>{
   if(loading||selected<0)return;
   var city=project.empire.cities[selected];if(city.role!="npc")return;
   city.sea_auto=seaAuto.Checked;if(city.sea_auto)ReestimateSea(city);
   Changed();map.Invalidate();
  };
 }

 // The estimate is a guess from the empire picture. It never touches a city whose value was set by hand.
 void ReestimateSea(City city){
  try{
   var guess=Json.Deserialize<CoastGuess>(RunPython("scenario_cities.py","coast "+project.empire.template+" "+city.x+" "+city.y));
   if(guess!=null&&guess.estimate.HasValue&&city.sea_auto){
    city.sea=guess.estimate.Value;
    if(selected>=0&&project.empire.cities[selected]==city){bool previous=loading;loading=true;sea.Checked=city.sea==1;loading=previous;RefreshAccess(city);}
   }
   if(guess!=null)status.Text=CityName(city.name_id)+": "+guess.basis;
  }catch(Exception error){status.Text=error.Message;}
 }

 void QueueCoast(City city){
  coastPending=city;
  if(coastTimer==null){
   coastTimer=new System.Windows.Forms.Timer{Interval=500};
   coastTimer.Tick+=(s,e)=>{coastTimer.Stop();var target=coastPending;coastPending=null;if(target!=null&&target.sea_auto)ReestimateSea(target);};
  }
  coastTimer.Stop();coastTimer.Start();
 }
}
