using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Collections.Generic;
using System.Windows.Forms;
// The map versions of a city (user 2026-11-15: one city can have several maps; pick the one that is used, and see
// which one that is). A version is either one of the game's own maps of that city (the presets) or a map the author
// brought in (.mapx from the map editor, or the terrain of a saved city, .svx). Brought-in maps are kept per city in
// creator-maps\<city>\ next to the editor, so they stay available for every scenario; the scenario itself carries
// only the one that is used (Slot.terrain_asset), as before. The folder is the author's own: never shipped.
public class MapVersion {public string name,source,imported;public int name_id,base_preset,width,height;public TerrainAsset terrain_asset;
 public override string ToString(){return name+" ("+Lang.T("가져온 지도")+(width>0?" "+width+"×"+height:"")+")";}}
partial class ScenarioCreator {
 static string MapLibraryDir(int nameId){var d=Path.Combine(Root,"creator-maps",nameId.ToString());Directory.CreateDirectory(d);return d;}
 static string MapKey(TerrainAsset a){return a==null||string.IsNullOrEmpty(a.sha256)||a.sha256.Length<16?null:a.sha256.Substring(0,16).ToLowerInvariant();}
 static List<MapVersion> MapVersions(int nameId){
  var list=new List<MapVersion>();
  foreach(var file in Directory.GetFiles(MapLibraryDir(nameId),"*.json")){
   if(file.EndsWith(".terrain.json",StringComparison.OrdinalIgnoreCase))continue;
   try{var v=Json.Deserialize<MapVersion>(File.ReadAllText(file,Encoding.UTF8));if(v!=null&&v.terrain_asset!=null&&MapKey(v.terrain_asset)==Path.GetFileNameWithoutExtension(file))list.Add(v);}
   catch{}   // a damaged entry is left alone and not offered
  }
  return list.OrderBy(v=>v.imported??"").ThenBy(v=>v.name).ToList();
 }
 // automatic: the map comes with a scenario that was opened, not from the author; a map the author took off the shelf
 // then stays off (null). Putting a map in on purpose takes it off the removed list again.
 static MapVersion MapVersionAdd(int nameId,TerrainAsset asset,string name,string source,int basePreset,int width,int height,string metadata,bool automatic=false){
  string key=MapKey(asset);if(key==null)throw new Exception("지도 자료가 올바르지 않습니다.");
  if(automatic&&ShelfRemoved(nameId).Contains(key))return null;if(!automatic)ShelfMarkRemoved(nameId,key,false);
  string dir=MapLibraryDir(nameId),file=Path.Combine(dir,key+".json");
  var old=MapVersions(nameId).FirstOrDefault(x=>MapKey(x.terrain_asset)==key);if(old!=null)return old;   // the same map again: one entry
  var v=new MapVersion{name=string.IsNullOrWhiteSpace(name)?Lang.T("가져온 지도"):name.Trim(),source=source??"",imported=DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss"),name_id=nameId,base_preset=basePreset,width=width,height=height,
   terrain_asset=new TerrainAsset{format=asset.format,sha256=asset.sha256,data=asset.data}};
  File.WriteAllText(file,Json.Serialize(v),new UTF8Encoding(false));
  if(metadata!=null&&File.Exists(metadata))File.Copy(metadata,Path.Combine(dir,key+".terrain.json"),true);
  ShelfChanged(nameId);return v;
 }
 // The map that a scenario file carries is offered too (a file from somebody else, or made before this list); one the
 // author took off the shelf is listed for this scenario only (not written back onto the shelf).
 MapVersion MapVersionEnsure(Slot slot){
  if(slot==null||slot.terrain_asset==null||MapKey(slot.terrain_asset)==null)return null;
  if(MapVersions(slot.name_id).Any(v=>MapKey(v.terrain_asset)==MapKey(slot.terrain_asset)))return null;
  string name=Lang.T("시나리오에 들어 있던 지도")+" ("+(project==null?"":project.title)+")";
  try{if(MapVersionAdd(slot.name_id,slot.terrain_asset,name,"",slot.campaign_scenario,0,0,null,true)!=null)return null;}catch{}
  return new MapVersion{name=name,source="",imported="",name_id=slot.name_id,base_preset=slot.campaign_scenario,terrain_asset=slot.terrain_asset};
 }
 static void MapVersionRemove(MapVersion v){
  string key=MapKey(v.terrain_asset),dir=MapLibraryDir(v.name_id);
  foreach(var f in new[]{key+".json",key+".terrain.json"}){var p=Path.Combine(dir,f);if(File.Exists(p))File.Delete(p);}
  ShelfMarkRemoved(v.name_id,key,true);ShelfChanged(v.name_id);
 }
 // Preview of a brought-in map: kept beside it; made once with the engine when missing.
 TerrainData MapVersionPreview(MapVersion v){
  string key=MapKey(v.terrain_asset),cached=Path.Combine(MapLibraryDir(v.name_id),key+".terrain.json");
  if(!File.Exists(cached)){
   string temp=Path.Combine(Scratch(),"map-"+Guid.NewGuid().ToString("N")+".mapx");
   try{File.WriteAllBytes(temp,Convert.FromBase64String(v.terrain_asset.data));var result=ParseNative(RunPython("creator_native_editor.py","inspect --map "+Quote(temp)));File.Copy(result.metadata,cached,true);}
   finally{try{File.Delete(temp);}catch{}}
  }
  return Json.Deserialize<TerrainData>(File.ReadAllText(cached,Encoding.UTF8));
 }
 // Bring a map file into a city's list (no scenario change). null when the author cancelled.
 MapVersion MapVersionImport(int nameId,int basePreset,string suggested=null){   // suggested: the map the game's editor saves (it opens there)
  string chosen;
  if(NonInteractive&&suggested!=null)chosen=suggested;
  else using(var dialog=new OpenFileDialog{Title=Lang.T("도시 지도 파일 가져오기"),Filter=Lang.T("Augustus 지도 또는 저장 파일 (*.mapx;*.svx)|*.mapx;*.svx"),InitialDirectory=suggested==null?"":Path.GetDirectoryName(suggested),FileName=suggested==null?"":Path.GetFileName(suggested)}){if(dialog.ShowDialog(this)!=DialogResult.OK)return null;chosen=dialog.FileName;}
  UseWaitCursor=true;status.Text=Lang.T("지도를 읽고 게임 형식을 검사하고 있습니다…");
  try{
   var result=Json.Deserialize<MapInspectResult>(RunPython("creator_native_editor.py","inspect --map "+Quote(chosen)));
   if(result==null||!string.IsNullOrEmpty(result.error))throw new Exception(result==null?"검사 결과가 없습니다.":result.error);
   string name=Path.GetFileNameWithoutExtension(chosen);if(chosen.EndsWith(".svx",StringComparison.OrdinalIgnoreCase))name=Lang.T("저장 파일")+": "+name;
   var v=MapVersionAdd(nameId,result.terrain_asset,name,chosen,basePreset,result.width,result.height,result.metadata);
   status.Text=CityName(nameId)+": "+Lang.T("지도 목록에 넣었습니다")+" ("+v.name+")";return v;
  }finally{UseWaitCursor=false;}
 }
 // The versions of a slot's city as the picker and the list show them: the game's maps (ids >= 0) and the brought-in
 // maps (id -1, -2, ... in the order of `files`). current: the one the slot uses.
 MissionPreset[] TerrainVersions(Slot slot,out List<MapVersion> files,out int current){
  var kept=MapVersionEnsure(slot);files=MapVersions(slot.name_id);if(kept!=null)files.Add(kept);
  var list=CityTerrains(slot.name_id).ToList();var own=Array.Find(presets.terrain,t=>t.id==slot.campaign_scenario);
  /* the game map named in the slot is listed when the slot plays on it, or when it is this city's own; a city that plays on
     an imported map keeps a base mission of another city (Capua by default) only for the engine start: not a map of its own
     (user 2026-11-15: Pergamum listed "카푸아 (80×80)") */
  if(own!=null&&!list.Any(t=>t.id==own.id)&&(slot.terrain_asset==null||own.name_id==slot.name_id))list.Insert(0,own);
  current=slot.campaign_scenario;
  for(int i=0;i<files.Count;i++){
   var v=files[i];list.Add(VersionItem(v,i));
   if(slot.terrain_asset!=null&&MapKey(slot.terrain_asset)==MapKey(v.terrain_asset))current=-1-i;
  }
  return list.ToArray();
 }
 static MissionPreset VersionItem(MapVersion v,int index){return new MissionPreset{id=-1-index,title=v.name,width=v.width,height=v.height,name_id=v.name_id,available=true,
  note=Lang.T("가져온 지도")+(string.IsNullOrEmpty(v.source)?"":" · "+Path.GetFileName(v.source))+" · "+v.imported};}
 TerrainData LoadVersion(List<MapVersion> files,int id){return id>=0?LoadTerrain(id):MapVersionPreview(files[-1-id]);}
 // Use version `id` for the slot. Returns false when nothing changed (same one, or the author said no).
 bool ApplyTerrainVersion(Slot slot,int id,List<MapVersion> files){
  bool usesFile=slot.terrain_asset!=null,edited=slot.terrain_edits!=null&&slot.terrain_edits.Length>0;
  if(id>=0){
   if(!usesFile&&slot.campaign_scenario==id)return false;
   if(edited&&LangBox.Show(this,"지형을 바꾸면 이 도시의 이전 지형 수정 내용이 초기화됩니다. 바꿀까요?","지형 변경",MessageBoxButtons.YesNo)!=DialogResult.Yes)return false;
   slot.campaign_scenario=id;slot.terrain_asset=null;
  }else{
   var v=files[-1-id];if(usesFile&&MapKey(slot.terrain_asset)==MapKey(v.terrain_asset))return false;
   if(edited&&LangBox.Show(this,"지형을 바꾸면 이 도시의 이전 지형 수정 내용이 초기화됩니다. 바꿀까요?","지형 변경",MessageBoxButtons.YesNo)!=DialogResult.Yes)return false;
   slot.campaign_scenario=SafeBase(slot.name_id,Array.Exists(presets.terrain,t=>t.id==v.base_preset)?v.base_preset:slot.campaign_scenario);   /* a campaign mission: CreatorCityLibrary.cs SafeBase */
   slot.terrain_asset=new TerrainAsset{format=v.terrain_asset.format,sha256=v.terrain_asset.sha256,data=v.terrain_asset.data};
  }
  slot.terrain_edits=new TerrainEdit[0];nativeSessions.Remove(slot.id);nativePreviews.Remove(slot.id);boundTerrainSlot=-1;Changed();
  return true;
 }
 // What a slot uses, in words (the building page, the terrain page, the checks).
 string TerrainVersionText(Slot slot){
  if(slot.terrain_asset!=null){var v=MapVersions(slot.name_id).FirstOrDefault(x=>MapKey(x.terrain_asset)==MapKey(slot.terrain_asset));return v==null?Lang.T("가져온 지도"):v.ToString();}
  var p=Array.Find(presets.terrain,t=>t.id==slot.campaign_scenario);return p==null?"?":p.ToString();
 }
}
public class MapInspectResult {public TerrainAsset terrain_asset;public string metadata,source,error;public int width,height;}
