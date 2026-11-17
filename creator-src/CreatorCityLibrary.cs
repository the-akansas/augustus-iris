using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Drawing;
using System.Collections.Generic;
using System.Windows.Forms;
// The author's own map shelf (user 2026-11-15: "an author keeps adding maps and making scenarios; adding maps, even
// cities placed where the game has none, must be easy to manage. Someone who only receives a scenario must never be
// unable to play or edit it for want of a city"). The shelf is creator-maps\<city>\ next to the editor (never shipped):
//   * the maps of a city (CreatorTerrainLibrary.cs), and where that city was placed on the empire map (place.txt);
//   * a city with a map on the shelf is a city with terrain in every scenario of this PC (green): assigning it to a
//     seat uses its newest map, and "지도 파일 연결…" offers the shelf before a file;
//   * every map a scenario carries goes onto the shelf when the scenario is opened, so a received scenario adds its
//     cities to the receiver's shelf too; the scenario file itself always carries the maps it uses (Slot.terrain_asset,
//     City.map), so it plays and edits without anybody's shelf;
//   * a new scenario puts the cities of the shelf where the author last placed them.
// Everything that goes onto the shelf can come off it again (user 2026-11-15: "what can be put in must be removable"):
// "지도 보관함…" lists it; a map taken off is remembered (removed.txt) so that opening a scenario that carries it does not
// put it back; only the author putting it in again does.
partial class ScenarioCreator {
 static Dictionary<int,int> shelfCounts;
 static string ShelfRoot(){var d=Path.Combine(Root,"creator-maps");Directory.CreateDirectory(d);return d;}
 static void ShelfScan(){
  var counts=new Dictionary<int,int>();
  try{foreach(var dir in Directory.GetDirectories(ShelfRoot())){int id;if(!int.TryParse(Path.GetFileName(dir),out id)||id<=0)continue;int n=MapVersions(id).Count;if(n>0)counts[id]=n;}}catch{}
  shelfCounts=counts;
 }
 static void ShelfChanged(int nameId){if(shelfCounts==null){ShelfScan();return;}int n=MapVersions(nameId).Count;if(n>0)shelfCounts[nameId]=n;else shelfCounts.Remove(nameId);}
 static IEnumerable<int> ShelfCities(){if(shelfCounts==null)ShelfScan();return shelfCounts.Keys.ToList();}
 static bool ShelfHasMap(int nameId){if(shelfCounts==null)ShelfScan();return shelfCounts.ContainsKey(nameId);}
 static MapVersion ShelfNewest(int nameId){return MapVersions(nameId).OrderBy(v=>v.imported??"").LastOrDefault();}
 static void ShelfRememberPlace(int nameId,int x,int y){try{File.WriteAllText(Path.Combine(MapLibraryDir(nameId),"place.txt"),x+" "+y,new UTF8Encoding(false));}catch{}}
 static void ShelfForgetPlace(int nameId){try{var p=Path.Combine(Root,"creator-maps",nameId.ToString(),"place.txt");if(File.Exists(p))File.Delete(p);}catch{}}
 static string ShelfRemovedFile(int nameId){return Path.Combine(MapLibraryDir(nameId),"removed.txt");}
 static HashSet<string> ShelfRemoved(int nameId){var set=new HashSet<string>();try{var p=ShelfRemovedFile(nameId);if(File.Exists(p))foreach(var l in File.ReadAllLines(p))if(l.Trim().Length>0)set.Add(l.Trim());}catch{}return set;}
 static void ShelfMarkRemoved(int nameId,string key,bool removed){
  if(key==null)return;var set=ShelfRemoved(nameId);if(removed?!set.Add(key):!set.Remove(key))return;
  try{var p=ShelfRemovedFile(nameId);if(set.Count==0){if(File.Exists(p))File.Delete(p);}else File.WriteAllLines(p,set.OrderBy(k=>k).ToArray(),new UTF8Encoding(false));}catch{}
 }
 static bool ShelfPlace(int nameId,out int x,out int y){
  x=y=0;try{var p=Path.Combine(Root,"creator-maps",nameId.ToString(),"place.txt");if(!File.Exists(p))return false;var parts=File.ReadAllText(p).Split(' ');return parts.Length==2&&int.TryParse(parts[0],out x)&&int.TryParse(parts[1],out y)&&x>0&&y>0;}catch{return false;}
 }
 // Opening a scenario: the maps it carries go onto the shelf (and the place of a neutral city that carries one), except a
 // map the author took off the shelf (automatic). "열린 시나리오의 지도 넣기" puts them in on purpose (automatic=false).
 // (A neutral city that carries a map is usually switched off: it waits to be given a seat, so it brings its map all the
 // same; the author takes a map out of a scenario with "연결한 지도 빼기" or "C3 상태로 되돌리기".) Returns how many maps
 // went onto the shelf.
 int ShelfTakeFrom(Scenario data,bool automatic=true){
  int added=0;if(data==null||data.empire==null)return 0;string from=Lang.T("시나리오에 들어 있던 지도")+" ("+(data.title??"")+")";
  Func<int,TerrainAsset,int,bool> put=(id,asset,basePreset)=>{bool had=MapVersions(id).Any(v=>MapKey(v.terrain_asset)==MapKey(asset));var v2=MapVersionAdd(id,asset,from,"",basePreset,0,0,null,automatic);if(v2!=null&&!had)added++;return v2!=null;};
  foreach(var s in data.slots??new Slot[0])if(s.terrain_asset!=null&&MapKey(s.terrain_asset)!=null){try{put(s.name_id,s.terrain_asset,s.campaign_scenario);}catch{}}
  foreach(var c in data.empire.cities??new City[0]){
   if(c.map==null||c.map.terrain_asset==null||MapKey(c.map.terrain_asset)==null)continue;
   try{if(put(c.name_id,c.map.terrain_asset,c.map.campaign_scenario)){int px,py;if(!ShelfPlace(c.name_id,out px,out py))ShelfRememberPlace(c.name_id,c.x,c.y);}}catch{}
  }
  return added;
 }
 // A new scenario: the shelf's cities where the author placed them (not next to Rome). Returns how many moved.
 static int ShelfApplyPlaces(Scenario data){
  int moved=0;
  foreach(var c in data.empire.cities){int x,y;if(c.role!="npc"||!ShelfHasMap(c.name_id)||!ShelfPlace(c.name_id,out x,out y)||RomeCapital.TooClose(x,y))continue;if(c.x!=x||c.y!=y){c.x=x;c.y=y;moved++;}}
  return moved;
 }
 // The map a seat takes when the city has no map in this scenario and none in the game: the newest one on the shelf.
 MapVersion ShelfMapFor(int nameId){return CityTerrains(nameId).Length==0&&ShelfHasMap(nameId)?ShelfNewest(nameId):null;}
 // "지도 파일 연결…": the city's maps on the shelf first; a file only when asked for (or when there is none).
 // Returns the chosen map, or null for "a file".
 MapVersion ChooseShelfMap(City city,out bool cancelled){
  cancelled=false;var maps=MapVersions(city.name_id);if(maps.Count==0||NonInteractive)return null;
  using(var dialog=new Form{Text=Lang.T("도시에 연결할 지도"),ClientSize=new Size(460,300),StartPosition=FormStartPosition.CenterParent,FormBorderStyle=FormBorderStyle.FixedDialog,MaximizeBox=false,MinimizeBox=false,BackColor=Paper,Font=Font}){
   dialog.Controls.Add(new Label{Text=CityName(city.name_id)+": "+Lang.T("이 PC의 지도 보관함에 있는 지도"),Left=16,Top=12,AutoSize=true});
   var list=new ListBox{Left=16,Top=38,Width=428,Height=190,IntegralHeight=false};foreach(var v in maps.AsEnumerable().Reverse())list.Items.Add(v);list.SelectedIndex=0;dialog.Controls.Add(list);
   var use=new Button{Text=Lang.T("이 지도 연결"),Left=16,Top=244,Width=140,Height=34,DialogResult=DialogResult.OK};var file=new Button{Text=Lang.T("다른 파일 찾기…"),Left=166,Top=244,Width=140,Height=34,DialogResult=DialogResult.Retry};
   var cancel=new Button{Text=Lang.T("취소"),Left=344,Top=244,Width=100,Height=34,DialogResult=DialogResult.Cancel};
   dialog.Controls.Add(use);dialog.Controls.Add(file);dialog.Controls.Add(cancel);dialog.AcceptButton=use;dialog.CancelButton=cancel;list.DoubleClick+=(s,e)=>{dialog.DialogResult=DialogResult.OK;};
   var answer=Lang.Shown(dialog).ShowDialog(this);
   if(answer==DialogResult.OK)return list.SelectedItem as MapVersion;
   if(answer!=DialogResult.Retry)cancelled=true;return null;
  }
 }
 // The mission a city with its own map is started from (start year, money, rules; the map itself is the city's own).
 // It must be one every Caesar III has (the campaign, mission1.pak), never a separate .map file: a scenario whose own
 // map sat on Caesarea.map did not start on a PC without that file (user 2026-11-15: "somebody who only receives a
 // scenario must be able to play it"). The city's own campaign mission when there is one, else Capua's.
 int SafeBase(int nameId,int wanted){
  Func<MissionPreset,bool> campaign=t=>t!=null&&!string.IsNullOrEmpty(t.source_file)&&!t.source_file.EndsWith(".map",StringComparison.OrdinalIgnoreCase);
  var w=Array.Find(presets.terrain,t=>t.id==wanted);if(campaign(w))return wanted;
  var own=presets.terrain.FirstOrDefault(t=>t.name_id==nameId&&campaign(t));if(own!=null)return own.id;
  var capua=Array.Find(presets.terrain,t=>t.id==2);if(campaign(capua))return 2;
  var any=presets.terrain.FirstOrDefault(t=>campaign(t));return any!=null?any.id:wanted;
 }
 // Every seat and neutral city that carries its own map is started from such a mission (older files included).
 // Returns how many were changed.
 int SafeBases(Scenario data){
  int changed=0;if(data==null||presets==null||presets.terrain==null)return 0;
  foreach(var s in data.slots??new Slot[0])if(s.terrain_asset!=null){int b=SafeBase(s.name_id,s.campaign_scenario);if(b!=s.campaign_scenario){s.campaign_scenario=b;changed++;}}
  foreach(var c in data.empire.cities??new City[0])if(c.map!=null&&c.map.terrain_asset!=null){int b=SafeBase(c.name_id,c.map.campaign_scenario);if(b!=c.map.campaign_scenario){c.map.campaign_scenario=b;changed++;}}
  return changed;
 }
 // Cities with anything on the shelf: maps, a remembered place.
 static List<int> ShelfAllCities(){
  var ids=new List<int>();
  try{foreach(var dir in Directory.GetDirectories(ShelfRoot())){int id;if(!int.TryParse(Path.GetFileName(dir),out id)||id<=0)continue;int x,y;if(MapVersions(id).Count>0||ShelfPlace(id,out x,out y))ids.Add(id);}}catch{}
  return ids;
 }
 // Takes a city off the shelf: every map and the remembered place (the scenario files keep the maps they carry).
 static void ShelfEmptyCity(int nameId){foreach(var v in MapVersions(nameId))MapVersionRemove(v);ShelfForgetPlace(nameId);ShelfChanged(nameId);}
 // "지도 보관함…": what this PC keeps, and taking it off again.
 void ShowShelf(){
  StoreCity();
  using(var dialog=new Form{Text=Lang.T("이 PC의 지도 보관함"),ClientSize=new Size(720,470),MinimumSize=new Size(640,420),StartPosition=FormStartPosition.CenterParent,BackColor=Paper,Font=Font}){
   var layout=new TableLayoutPanel{Dock=DockStyle.Fill,ColumnCount=2,RowCount=4,Padding=new Padding(12)};dialog.Controls.Add(layout);
   layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,40));layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,60));
   layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));layout.RowStyles.Add(new RowStyle(SizeType.Percent,100));layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
   var note=new Label{Text=Lang.T("지도를 넣은 도시는 이 PC의 모든 시나리오에서 녹색이 되고, 새 시나리오에서는 마지막에 놓은 위치에 놓입니다. 빼도 이미 저장한 시나리오 파일 안의 지도는 그대로이고, 그 시나리오를 다시 열어도 자동으로 다시 넣지 않습니다."),AutoSize=true,MaximumSize=new Size(690,0),Padding=new Padding(0,0,0,8)};
   layout.Controls.Add(note,0,0);layout.SetColumnSpan(note,2);
   var cityList=new ListBox{Dock=DockStyle.Fill,IntegralHeight=false};var mapList=new ListBox{Dock=DockStyle.Fill,IntegralHeight=false,HorizontalScrollbar=true};
   layout.Controls.Add(cityList,0,1);layout.Controls.Add(mapList,1,1);
   var placeNote=new Label{AutoSize=true,MaximumSize=new Size(690,0),Padding=new Padding(0,6,0,6)};layout.Controls.Add(placeNote,0,2);layout.SetColumnSpan(placeNote,2);
   var actions=new FlowLayoutPanel{Dock=DockStyle.Fill,AutoSize=true,WrapContents=true};layout.Controls.Add(actions,0,3);layout.SetColumnSpan(actions,2);
   List<int> ids=null;
   Func<int> current=()=>cityList.SelectedIndex>=0&&ids!=null&&cityList.SelectedIndex<ids.Count?ids[cityList.SelectedIndex]:0;
   Action showMaps=()=>{
    mapList.Items.Clear();int id=current();placeNote.Text="";if(id==0)return;
    foreach(var v in MapVersions(id).AsEnumerable().Reverse())mapList.Items.Add(v);if(mapList.Items.Count>0)mapList.SelectedIndex=0;
    int x,y;placeNote.Text=CityName(id)+": "+(ShelfPlace(id,out x,out y)?Lang.T("저장된 위치")+" X "+x+", Y "+y:Lang.T("저장된 위치 없음"));
   };
   Action fill=()=>{
    int keep=current();ids=ShelfAllCities().OrderBy(i=>CityName(i)).ToList();cityList.Items.Clear();
    foreach(int id in ids){int x,y;int n=MapVersions(id).Count;cityList.Items.Add(CityName(id)+" · "+Lang.T("지도")+" "+n+(ShelfPlace(id,out x,out y)?" · "+Lang.T("위치"):""));}
    int at=ids.IndexOf(keep);cityList.SelectedIndex=at>=0?at:ids.Count>0?0:-1;showMaps();
    if(ids.Count==0)placeNote.Text=Lang.T("보관함이 비어 있습니다.");
   };
   cityList.SelectedIndexChanged+=(s,e)=>showMaps();
   actions.Controls.Add(Button("고른 지도 빼기",()=>{var v=mapList.SelectedItem as MapVersion;if(v==null)return;
    if(LangBox.Show(this,"이 지도를 보관함에서 뺄까요? 이 지도를 쓰는 시나리오 파일은 바뀌지 않습니다.","지도 보관함",MessageBoxButtons.YesNo)!=DialogResult.Yes)return;MapVersionRemove(v);fill();},130));
   actions.Controls.Add(Button("저장된 위치 지우기",()=>{int id=current();if(id==0)return;ShelfForgetPlace(id);fill();},150));
   actions.Controls.Add(Button("이 도시 비우기",()=>{int id=current();if(id==0)return;
    if(LangBox.Show(this,CityName(id)+": "+Lang.T("이 도시의 지도와 저장된 위치를 보관함에서 모두 뺄까요? 시나리오 파일은 바뀌지 않습니다."),"지도 보관함",MessageBoxButtons.YesNo)!=DialogResult.Yes)return;ShelfEmptyCity(id);fill();},130));
   actions.Controls.Add(Button("열린 시나리오의 지도 넣기",()=>{int n=ShelfTakeFrom(project,false);fill();placeNote.Text=Lang.T("보관함에 넣은 지도")+": "+n;},200));
   var close=Button("닫기",()=>dialog.Close(),80);actions.Controls.Add(close);dialog.CancelButton=close;
   fill();Lang.Shown(dialog).ShowDialog(this);
  }
  SyncPlayable();map.Invalidate();if(selected>=0)ShowCity(selected);
 }
 // ---- a city back to Caesar III (user 2026-11-15: "the reset is what loading C3 gives") ----
 // C3's own values for a city: the unified empire built from the game's files (creator_presets.py --merged), the same
 // values a new scenario starts with.
 MergedCity C3City(int nameId){var c=merged==null?null:merged.cities.FirstOrDefault(m=>m.name_id==nameId);if(c==null)throw new Exception("C3 자료에서 이 도시를 찾지 못했습니다.");return c;}
 // The city where C3 puts it (any city, seats too); the shelf forgets the place it remembered.
 void ResetCityPosition(){
  if(selected<0)throw new Exception("도시를 먼저 선택하세요.");var city=project.empire.cities[selected];var c3=C3City(city.name_id);
  if(RomeCapital.TooClose(c3.x,c3.y))throw new Exception(RomeCapital.Refusal);
  map.MoveCity(city.name_id,c3.x,c3.y);ShelfForgetPlace(city.name_id);
  loading=true;posX.Value=Math.Max(posX.Minimum,Math.Min(posX.Maximum,city.x));posY.Value=Math.Max(posY.Minimum,Math.Min(posY.Maximum,city.y));loading=false;
  Changed();map.Invalidate();status.Text=CityName(city.name_id)+": "+Lang.T("C3의 원래 위치로 옮겼습니다.");
 }
 // A neutral city as a new scenario has it from C3: place, trade, route cost, sea, who may trade, switched off; its
 // attached map and the terrain kept from an earlier seat leave the scenario. The PC's shelf is not touched.
 void ResetCityToC3(){
  if(selected<0)throw new Exception("도시를 먼저 선택하세요.");var city=project.empire.cities[selected];
  if(city.role!="npc")throw new Exception("플레이어 도시는 먼저 플레이어 자리에서 빼 주세요. 위치는 'C3 위치로'로 되돌릴 수 있습니다.");
  var c3=C3City(city.name_id);
  if(!NonInteractive&&LangBox.Show(this,CityName(city.name_id)+": "+Lang.T("C3의 원래 상태로 되돌릴까요?\n위치, 교역 품목, 개설 비용, 바닷길, 교역 허용이 C3 값으로 돌아가고, 연결한 지도와 보관된 지형은 이 시나리오에서 빠집니다. 도시는 새 시나리오처럼 꺼진 상태가 됩니다.\n이 PC의 지도 보관함은 바뀌지 않습니다."),"C3 상태로 되돌리기",MessageBoxButtons.YesNo,MessageBoxIcon.Question,MessageBoxDefaultButton.Button2)!=DialogResult.Yes)return;
  city.x=c3.x;city.y=c3.y;city.sea=c3.sea;city.cost=c3.cost;city.sells=new Dictionary<string,int>(c3.sells??new Dictionary<string,int>());city.buys=new Dictionary<string,int>(c3.buys??new Dictionary<string,int>());
  city.enabled=c3.enabled;city.map=null;city.parked_trade=null;city.trade_players=null;city.sea_auto=false;city.reserved=false;
  ShelfForgetPlace(city.name_id);cityTerrainSessions.Remove(city.name_id);
  Changed();SyncPlayable();ShowCity(selected);map.Invalidate();
  status.Text=CityName(city.name_id)+": "+Lang.T("C3의 원래 상태로 되돌렸습니다.")+(ShelfHasMap(city.name_id)?" "+Lang.T("이 PC의 지도 보관함에 이 도시의 지도가 있어 녹색으로 남습니다('지도 보관함…'에서 뺄 수 있습니다)."):"");
 }
 // A map put on a neutral city (from the shelf or from a file).
 void AttachCityAsset(City city,TerrainAsset asset,int basePreset){
  if(city.map==null)city.map=new Slot{campaign_scenario=SafeBase(city.name_id,basePreset),terrain_edits=new TerrainEdit[0]};else city.map.campaign_scenario=SafeBase(city.name_id,city.map.campaign_scenario);
  city.map.terrain_asset=new TerrainAsset{format=asset.format,sha256=asset.sha256,data=asset.data};
  ShelfRememberPlace(city.name_id,city.x,city.y);
  Changed();if(selected>=0&&project.empire.cities[selected]==city)ShowCity(selected);map.Invalidate();
  status.Text=CityName(city.name_id)+": "+Lang.T("지형을 연결했습니다. 이제 플레이 도시로 배정할 수 있습니다.");
 }
}
