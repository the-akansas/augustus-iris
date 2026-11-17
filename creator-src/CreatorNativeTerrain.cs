using System;
using System.IO;
using System.Text;
using System.Linq;
using System.Drawing;
using System.Threading.Tasks;
using System.Collections.Generic;
using System.Windows.Forms;
public class NativeTerrainResult {public string session,map,metadata,error;public bool editor_ready;public string[] missing;public TerrainAsset terrain_asset;}
partial class ScenarioCreator {
 static NativeTerrainResult ParseNative(string raw){var result=Json.Deserialize<NativeTerrainResult>(raw);if(result==null)throw new Exception("정식 편집기 응답이 없습니다.");if(!string.IsNullOrEmpty(result.error))throw new Exception(result.error);return result;}
 Dictionary<string,NativeTerrainResult> nativeSessions=new Dictionary<string,NativeTerrainResult>();
 Dictionary<string,TerrainData> nativePreviews=new Dictionary<string,TerrainData>();
 Label nativeHelp=new Label{Dock=DockStyle.Fill};
 // "지형" (user 2026-11-15): one page for a city's terrain. Left: the versions of this city's map (the game's own maps
 // and the maps brought in, CreatorTerrainLibrary.cs) with the one in use marked; right: the chosen version, large.
 // A version is used by "이 지형 쓰기", or at once when a map file is brought in ("지도 파일 가져오기": the map saved in the
 // game's editor too). The game's editor opens the version chosen in the list (user 2026-11-15: it opened the one in use).
 ListBox terrainVersionList=new ListBox{Dock=DockStyle.Fill,IntegralHeight=false,FormattingEnabled=true};List<MapVersion> terrainFiles=new List<MapVersion>();int terrainCurrent=int.MinValue,terrainRequest;
 Label terrainHeading=new Label{AutoSize=true,Font=new Font("Malgun Gothic",13,FontStyle.Bold),Padding=new Padding(0,6,0,0)};
 void BuildNativeTerrainTab(){var tab=new TabPage("3  정식 지형 편집"){BackColor=Paper};tabs.TabPages.Add(tab);
  var layout=new TableLayoutPanel{Dock=DockStyle.Fill,ColumnCount=2,RowCount=3,Padding=new Padding(14,8,14,8)};layout.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,430));layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));
  layout.RowStyles.Add(new RowStyle(SizeType.Absolute,44));layout.RowStyles.Add(new RowStyle(SizeType.Percent,100));layout.RowStyles.Add(new RowStyle(SizeType.Absolute,58));tab.Controls.Add(layout);
  var head=new FlowLayoutPanel{Dock=DockStyle.Fill,WrapContents=false};terrainSlot.Visible=false;head.Controls.Add(terrainSlot);head.Controls.Add(terrainHeading);layout.Controls.Add(head,0,0);layout.SetColumnSpan(head,2);
  var left=new TableLayoutPanel{Dock=DockStyle.Fill,ColumnCount=1,RowCount=3,Margin=new Padding(0,0,10,0)};left.RowStyles.Add(new RowStyle(SizeType.Percent,100));left.RowStyles.Add(new RowStyle(SizeType.Absolute,48));left.RowStyles.Add(new RowStyle(SizeType.Absolute,140));
  var versionsBox=new GroupBox{Text="이 도시의 지형",Dock=DockStyle.Fill,ForeColor=Dark,Padding=new Padding(8)};versionsBox.Controls.Add(terrainVersionList);left.Controls.Add(versionsBox,0,0);
  var useRow=new FlowLayoutPanel{Dock=DockStyle.Fill,Margin=new Padding(0,4,0,0)};useRow.Controls.Add(Button("이 지형 쓰기",UseChosenTerrain,120));useRow.Controls.Add(Button("지도 파일 가져오기",ImportTerrainVersion,160));useRow.Controls.Add(Button("목록에서 빼기",RemoveTerrainVersion,120));left.Controls.Add(useRow,0,1);
  var editBox=new GroupBox{Text="고른 지형 고치기",Dock=DockStyle.Fill,ForeColor=Dark,Padding=new Padding(8)};var editRow=new FlowLayoutPanel{Dock=DockStyle.Fill};
  editRow.Controls.Add(Button("정식 편집기로 열기",()=>OpenNativeTerrain(),170));
  editRow.Controls.Add(new Label{AutoSize=true,MaximumSize=new Size(385,0),Padding=new Padding(0,6,0,0),Text="위 목록에서 고른 지형을 게임의 정식 편집기로 엽니다. 고친 뒤 .mapx로 저장하고 '지도 파일 가져오기'로 가져오면 목록에 들어가고 바로 이 도시의 지형이 됩니다. 저장 게임(.svx)은 건물을 걷어낸 지형만 가져옵니다."});
  editBox.Controls.Add(editRow);left.Controls.Add(editBox,0,2);layout.Controls.Add(left,0,1);
  var right=new TableLayoutPanel{Dock=DockStyle.Fill,ColumnCount=1,RowCount=2};right.RowStyles.Add(new RowStyle(SizeType.Percent,100));right.RowStyles.Add(new RowStyle(SizeType.Absolute,40));
  terrainView.ReadOnly=true;terrainView.ShowProtected=false;right.Controls.Add(terrainView,0,0);var viewRow=new FlowLayoutPanel{Dock=DockStyle.Fill};viewRow.Controls.Add(Button("미리보기 맞춤",()=>terrainView.Fit(),125));right.Controls.Add(viewRow,0,1);layout.Controls.Add(right,1,1);
  layout.Controls.Add(terrainInfo,0,2);layout.SetColumnSpan(terrainInfo,2);
  terrainVersionList.Format+=(s,e)=>{var p=e.ListItem as MissionPreset;if(p!=null&&p.id==terrainCurrent)e.Value="["+Lang.T("사용 중")+"] "+Lang.T(Convert.ToString(p));};
  terrainVersionList.SelectedIndexChanged+=(s,e)=>PreviewChosenTerrain();
  terrainSlot.SelectedIndexChanged+=(s,e)=>{if(!loading&&NativeTerrainVisible())Guard(RefreshTerrainVersions);};tabs.SelectedIndexChanged+=(s,e)=>{if(NativeTerrainVisible())Guard(RefreshTerrainVersions);};
 }
 Slot TerrainSlotData(){return project==null||terrainSlot.SelectedIndex<0||terrainSlot.SelectedIndex>=project.slots.Length?null:project.slots[terrainSlot.SelectedIndex];}
 void RefreshTerrainVersions(){var slot=TerrainSlotData();if(slot==null)return;terrainHeading.Text=CityName(slot.name_id)+Lang.T("의 지형");
  var choices=TerrainVersions(slot,out terrainFiles,out terrainCurrent);terrainVersionList.BeginUpdate();terrainVersionList.Items.Clear();foreach(var p in choices)terrainVersionList.Items.Add(p);terrainVersionList.EndUpdate();
  for(int i=0;i<terrainVersionList.Items.Count;i++)if(((MissionPreset)terrainVersionList.Items[i]).id==terrainCurrent){terrainVersionList.SelectedIndex=i;break;}
  if(terrainVersionList.SelectedIndex<0&&terrainVersionList.Items.Count>0)terrainVersionList.SelectedIndex=0;}
 // The chosen version, large: the one in use as it is now (with an imported map or old edits), any other from its file.
 async void PreviewChosenTerrain(){var slot=TerrainSlotData();var p=terrainVersionList.SelectedItem as MissionPreset;if(slot==null||p==null)return;int request=++terrainRequest;
  string about=p.title+(p.width>0?"  ·  "+p.width+"×"+p.height:"")+(p.id>=0?"  ·  "+p.ClimateText:"")+"\n"+p.PopulationNotice+"\n"+(p.id==terrainCurrent?Lang.T("지금 이 도시가 쓰는 지형입니다."):Lang.T("미리보기입니다. 쓰려면 '이 지형 쓰기'를 누르세요."));
  if(p.id==terrainCurrent){boundTerrainSlot=-1;try{ShowTerrain();}catch(Exception e){terrainInfo.Text=e.Message;return;}terrainInfo.Text=about;return;}
  terrainInfo.Text=p.title+"\n"+Lang.T("지형을 읽고 있습니다…");var files=terrainFiles;
  try{var data=await Task.Run(()=>LoadVersion(files,p.id));if(IsDisposed||request!=terrainRequest)return;terrainView.Bind(data,new TerrainEdit[0]);boundTerrainSlot=-1;terrainInfo.Text=about;}
  catch(Exception e){if(request==terrainRequest)terrainInfo.Text=Lang.T("지형을 읽지 못했습니다.")+" "+e.Message;}}
 void UseChosenTerrain(){var slot=TerrainSlotData();var p=terrainVersionList.SelectedItem as MissionPreset;if(slot==null||p==null)return;if(ApplyTerrainVersion(slot,p.id,terrainFiles)){RefreshTerrainVersions();if(slotPicker.SelectedIndex==terrainSlot.SelectedIndex)ShowSlot();status.Text=CityName(slot.name_id)+": "+Lang.T("지형을 바꿨습니다. 프로젝트를 저장해 주세요.");}}
 void ImportTerrainVersion(){var slot=TerrainSlotData();if(slot==null)return;NativeTerrainResult session;nativeSessions.TryGetValue(slot.id,out session);
  var v=MapVersionImport(slot.name_id,slot.campaign_scenario,session==null?null:session.map);if(v==null)return;RefreshTerrainVersions();
  for(int i=0;i<terrainVersionList.Items.Count;i++){var p=(MissionPreset)terrainVersionList.Items[i];if(p.id<0&&MapKey(terrainFiles[-1-p.id].terrain_asset)==MapKey(v.terrain_asset)){terrainVersionList.SelectedIndex=i;if(ApplyTerrainVersion(slot,p.id,terrainFiles))nativeSessions.Remove(slot.id);RefreshTerrainVersions();if(slotPicker.SelectedIndex==terrainSlot.SelectedIndex)ShowSlot();break;}}
  status.Text=CityName(slot.name_id)+": "+Lang.T("가져온 지도를 이 도시의 지형으로 정했습니다. 예전 지형은 목록에서 골라 '이 지형 쓰기'로 되돌릴 수 있습니다. 프로젝트를 저장해 주세요.");}
 void RemoveTerrainVersion(){var p=terrainVersionList.SelectedItem as MissionPreset;if(p==null)return;if(p.id>=0)throw new Exception("게임에 들어 있는 지형은 뺄 수 없습니다. 가져온 지도만 뺄 수 있습니다.");if(p.id==terrainCurrent)throw new Exception("지금 쓰는 지형은 뺄 수 없습니다. 다른 지형을 먼저 쓰세요.");if(LangBox.Show(this,"이 지도를 도시의 지도 목록에서 뺄까요? 이 지도를 쓰는 다른 시나리오 파일은 바뀌지 않습니다.","지도 목록",MessageBoxButtons.YesNo)!=DialogResult.Yes)return;MapVersionRemove(terrainFiles[-1-p.id]);RefreshTerrainVersions();}
 // The map a slot uses now, for showing only (the invasion map): the imported map's engine preview, or the game's own.
 TerrainData CurrentTerrainOf(Slot slot){TerrainData cached;if(nativePreviews.TryGetValue(slot.id,out cached))return cached;
  if(slot.terrain_asset!=null){string path=PreviewSnapshot();try{cached=ReadNativeTerrain(ParseNative(RunPython("creator_native_editor.py","preview --project "+Quote(path)+" --slot "+Quote(slot.id))));nativePreviews[slot.id]=cached;return cached;}finally{File.Delete(path);}}
  return LoadTerrain(slot.campaign_scenario);}
 void ShowTerrain(){if(project==null||terrainSlot.SelectedIndex<0)return;int index=terrainSlot.SelectedIndex;if(boundTerrainSlot==index)return;var slot=project.slots[index];TerrainData cached;if(nativePreviews.TryGetValue(slot.id,out cached)){terrainView.Bind(cached,new TerrainEdit[0]);}else if(slot.terrain_asset!=null){string path=PreviewSnapshot();try{var response=ParseNative(RunPython("creator_native_editor.py","preview --project "+Quote(path)+" --slot "+Quote(slot.id)));cached=ReadNativeTerrain(response);nativePreviews[slot.id]=cached;terrainView.Bind(cached,new TerrainEdit[0]);}finally{File.Delete(path);}}else terrainView.Bind(LoadTerrain(slot.campaign_scenario),slot.terrain_edits);boundTerrainSlot=index;TerrainStatus();}
 static TerrainData ReadNativeTerrain(NativeTerrainResult result){if(result==null||string.IsNullOrEmpty(result.metadata)||!File.Exists(result.metadata))throw new Exception("편집한 지형의 미리보기 자료를 읽지 못했습니다.");return Json.Deserialize<TerrainData>(File.ReadAllText(result.metadata,Encoding.UTF8));}
 void TerrainStatus(){if(boundTerrainSlot<0)return;var slot=project.slots[boundTerrainSlot];terrainInfo.Text=CityName(slot.name_id)+" · "+terrainView.Data.width+" × "+terrainView.Data.height+"칸 · "+"사용 중인 지형: "+TerrainVersionText(slot)+(slot.terrain_asset==null&&slot.terrain_edits.Length>0?" + 이전 수정 "+slot.terrain_edits.Length+"칸":"")+"\n저장 후 ‘게임 적용 검사’로 지형과 출입 경로를 검사하세요. 기존 저장 게임과 시저 3 원본은 바뀌지 않습니다.";}
 // The project as a file with `slot` on version `id` of the list (a game map: id >= 0, a brought-in map: -1, -2, ...),
 // for the editor's preparation only; never saved.
 string SlotVersionProject(Slot slot,int id){
  var value=Json.Deserialize<Dictionary<string,object>>(SerializeProject(project));
  var row=((System.Collections.IEnumerable)value["slots"]).Cast<Dictionary<string,object>>().First(s=>Convert.ToString(s["id"])==slot.id);
  if(id!=terrainCurrent){
   row["terrain_edits"]=new List<object>();row.Remove("terrain_asset");
   if(id>=0)row["campaign_scenario"]=id;
   else{var v=terrainFiles[-1-id];row["campaign_scenario"]=SafeBase(slot.name_id,v.base_preset);row["terrain_asset"]=Json.Deserialize<Dictionary<string,object>>(Json.Serialize(v.terrain_asset));}
  }
  string path=Path.Combine(Root,"creator-cache","terrain-version-"+Guid.NewGuid().ToString("N")+".json");Directory.CreateDirectory(Path.GetDirectoryName(path));
  File.WriteAllText(path,Json.Serialize(value),new UTF8Encoding(false));return path;
 }
 async void OpenNativeTerrain(){string path=null;try{if(terrainSlot.SelectedIndex<0)return;var slot=project.slots[terrainSlot.SelectedIndex];
  var chosen=terrainVersionList.SelectedItem as MissionPreset;int id=chosen==null?terrainCurrent:chosen.id;bool own=id==terrainCurrent;
  bool imported=own?slot.terrain_asset!=null:id<0;var original=imported?null:Array.Find(presets.terrain,p=>p.id==(own?slot.campaign_scenario:id));
  if(original!=null&&original.original_population>0&&LangBox.Show(this,"정식 지형 편집으로 변환하면 기존 로마 건물과 주민은 제외됩니다. 원본은 보존됩니다.\n변환한 사본을 열까요?","지형 편집용 사본 만들기",MessageBoxButtons.YesNo,MessageBoxIcon.Warning,MessageBoxDefaultButton.Button2)!=DialogResult.Yes)return;
  path=SlotVersionProject(slot,id);Enabled=false;UseWaitCursor=true;status.Text="정식 지형 편집용 사본을 준비하고 있습니다…";string source=path;
  var result=ParseNative(await Task.Run(()=>RunPython("creator_native_editor.py","prepare --project "+Quote(source)+" --slot "+Quote(slot.id))));
  if(!result.editor_ready)throw new Exception("정식 편집기에 필요한 파일을 준비하지 못했습니다. "+string.Join(", ",result.missing??new string[0]));
  nativeSessions[slot.id]=result;if(!NonInteractive)ParseNative(RunPython("creator_native_editor.py","launch --session "+Quote(result.session)));
  status.Text=Lang.T("편집기에서 지도를 저장한 뒤 '지도 파일 가져오기'를 누르세요. 아직 프로젝트 지형은 바뀌지 않았습니다.");File.Delete(path);path=null;}
  catch(Exception e){if(NonInteractive)throw;LangBox.Show(this,e.Message,"지형 편집기",MessageBoxButtons.OK,MessageBoxIcon.Warning);}finally{Enabled=true;UseWaitCursor=false;if(path!=null)try{File.Delete(path);}catch{}}}
 void ResetNativeTerrain(){if(terrainSlot.SelectedIndex<0)return;var slot=project.slots[terrainSlot.SelectedIndex];if(LangBox.Show(this,"이 도시의 지형을 선택한 원본으로 복원할까요? 건설 허용 목록과 공동 목표는 유지됩니다.","지형 복원",MessageBoxButtons.YesNo,MessageBoxIcon.Question,MessageBoxDefaultButton.Button2)!=DialogResult.Yes)return;slot.terrain_asset=null;slot.terrain_edits=new TerrainEdit[0];nativeSessions.Remove(slot.id);nativePreviews.Remove(slot.id);boundTerrainSlot=-1;ShowTerrain();Changed();}
 int NativeBridgeProbe(){string dir=Path.Combine(Root,"creator-probes","native-bridge-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(dir);objectiveMode.SelectedIndex=0;/* saving needs a goal choice (free build) */string source=Snapshot();try{var slot=project.slots[0];var prepared=ParseNative(RunPython("creator_native_editor.py","prepare --project "+Quote(source)+" --slot "+Quote(slot.id)));if(!prepared.editor_ready||!File.Exists(prepared.map))throw new Exception("Native editor prepare failed");var imported=ParseNative(RunPython("creator_native_editor.py","import --session "+Quote(prepared.session)+" --map "+Quote(prepared.map)));if(imported.terrain_asset==null||imported.terrain_asset.format!="augustus-mapx")throw new Exception("Native import asset missing");slot.terrain_asset=imported.terrain_asset;slot.terrain_edits=new TerrainEdit[0];string target=Snapshot();File.Copy(target,Path.Combine(dir,"scenario.json"));var reloaded=Json.Deserialize<Scenario>(File.ReadAllText(target,Encoding.UTF8));Adopt(reloaded);terrainSlot.SelectedIndex=0;ShowTerrain();if(terrainView.Data.width!=ReadNativeTerrain(imported).width)throw new Exception("Imported preview dimension mismatch");RenderEditor(dir,2);File.WriteAllText(Path.Combine(dir,"result.json"),Json.Serialize(new{passed=true,prepare=true,import=true,asset_sha256=reloaded.slots[0].terrain_asset.sha256,save_reload=true,preview=true,native_editor_launched=false}));File.WriteAllText(Path.Combine(Root,"creator-native-probe-latest.txt"),dir);File.Delete(target);dirty=false;return 0;}finally{File.Delete(source);}}
}
