using System;
using System.IO;
using System.Text;
using System.Security.Cryptography;
using System.Collections.Generic;
using System.Windows.Forms;
public class CityLimit { public string slot,sea,reason; public int[] buildings,sea_neutrals; public SalaryFacts salary; }
public class LimitReport { public CityLimit[] limits; public SlotLinks[] links; public Finding[] findings; public ExportState export; }
public class SlotLinks { public string slot; public int name_id; public CityLink[] links; }
// Per-city limits come from scenario_check.py (engine results for the current map). Nothing is decided here.
// "blocked" is a confirmed state; "unknown" (no engine result yet) never disables anything.
partial class ScenarioCreator {
 Dictionary<string,CityLimit> seaLimits=new Dictionary<string,CityLimit>();
 Dictionary<string,CityLink[]> slotLinks=new Dictionary<string,CityLink[]>();
 string seaLimitsStamp=null;
 string seaLimitsError=null;
 static object OrderedJson(object value){
  var fields=value as IDictionary<string,object>;
  if(fields!=null){var sorted=new SortedDictionary<string,object>(StringComparer.Ordinal);foreach(var pair in fields)sorted.Add(pair.Key,OrderedJson(pair.Value));return sorted;}
  var sequence=value as System.Collections.IEnumerable;
  if(sequence!=null&&!(value is string)){var items=new List<object>();foreach(var item in sequence)items.Add(OrderedJson(item));return items;}
  return value;
 }
 string SeaStamp(){
  // Hash the actual input, including city roles/trade and full edit coordinates/kinds.
  // No lossy arithmetic or string-length shortcuts.
  var worker=new FileInfo(Path.Combine(Root,"engine-city-test.exe"));
  string input=Json.Serialize(OrderedJson(Json.DeserializeObject(SerializeProject(project))))+"\n"+(worker.Exists?worker.Length+":"+worker.LastWriteTimeUtc.Ticks:"missing");
  using(var hash=SHA256.Create())return Convert.ToBase64String(hash.ComputeHash(Encoding.UTF8.GetBytes(input)));
 }
 void ForgetSeaLimits(){seaLimitsStamp=null;seaLimitsError=null;if(salaryCache!=null)salaryCache.Clear();}
 bool RefreshSeaLimits(string stamp,Func<LimitReport> read){
  if(stamp==seaLimitsStamp)return true;
  seaLimitsStamp=null;seaLimits.Clear();slotLinks=new Dictionary<string,CityLink[]>();
  try{
   var report=read();
   if(report==null||report.limits==null)throw new Exception("도시별 검사 결과가 없습니다.");
   var fresh=new Dictionary<string,CityLimit>();
   foreach(var limit in report.limits){
    if(limit==null||limit.slot==null||fresh.ContainsKey(limit.slot)||
      (limit.sea!="blocked"&&limit.sea!="candidate"&&limit.sea!="unknown"))
     throw new Exception("도시별 검사 결과가 올바르지 않습니다.");
    fresh.Add(limit.slot,limit);
   }
   foreach(var slot in project.slots)if(!fresh.ContainsKey(slot.id))throw new Exception("일부 도시의 검사 결과가 없습니다.");
   var links=new Dictionary<string,CityLink[]>();
   if(report.links!=null)foreach(var row in report.links)if(row!=null&&row.slot!=null&&row.links!=null)links[row.slot]=row.links;
   lastFindings=report.findings??new Finding[0];lastExport=report.export;
   seaLimits=fresh;slotLinks=links;seaLimitsStamp=stamp;seaLimitsError=null;return true;
  }catch(Exception error){
   // A failed read is not a cached answer. The next request retries.
   seaLimitsError="해상 교역 검사 미확인: "+error.Message;return false;
  }
 }
 CityLimit SeaLimit(string slotId){
  if(project==null||project.slots==null||slotId==null)return null;
  try{
   string stamp=SeaStamp();
   RefreshSeaLimits(stamp,()=>{
    string tmp=Path.Combine(Scratch(),"augustus-limits-"+Guid.NewGuid().ToString("N")+".json");
    try{
     File.WriteAllText(tmp,SerializeProject(project),new UTF8Encoding(false));
     return Json.Deserialize<LimitReport>(RunPython("scenario_check.py",Quote(tmp)+" --links"));
    }finally{File.Delete(tmp);}
   });
  }catch(Exception error){seaLimits.Clear();slotLinks=new Dictionary<string,CityLink[]>();seaLimitsStamp=null;seaLimitsError="해상 교역 검사 미확인: "+error.Message;}
  CityLimit found;return seaLimits.TryGetValue(slotId,out found)?found:null;
 }
 Func<string,CityLimit> SeaReader(){
  if(project.slots.Length>0)SeaLimit(project.slots[0].id);
  var snapshot=new Dictionary<string,CityLimit>(seaLimits);
  return id=>{CityLimit found;return snapshot.TryGetValue(id,out found)?found:null;};
 }
 static bool SeaBuildingBlocked(CityLimit limit,int building){return limit!=null&&limit.sea=="blocked"&&limit.buildings!=null&&Array.IndexOf(limit.buildings,building)>=0;}
 bool SeaBlocked(string slotId,int building){return SeaBuildingBlocked(SeaLimit(slotId),building);}
 string SeaNote(string slotId){var limit=SeaLimit(slotId);return limit!=null&&limit.sea=="blocked"?" · 해상 교역 불가: "+limit.reason:seaLimitsError==null?"":" · "+seaLimitsError;}
}
