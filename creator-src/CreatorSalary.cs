using System;
using System.IO;
using System.Collections.Generic;
// Monthly salary as the engine pays it (city/emperor.c city_emperor_salary_for_rank; city/finance.c pay_monthly_salary).
// The amounts come from scenario_check.py (limits[].salary), which reads the engine check of this exact map: the base the
// start really uses and the engine's own amount for every rank. Nothing here computes or copies a salary table; with no
// engine result for the current map the amounts are shown as unknown.
public class SalaryFacts { public int @base; public int[] by_rank; }
partial class ScenarioCreator {
 Dictionary<string,SalaryFacts> salaryCache=new Dictionary<string,SalaryFacts>();
 // The salary base depends on the map and the start path, not on governance: changing rank or salary needs no new check.
 string SalaryKey(Slot s){
  var worker=new FileInfo(Path.Combine(Root,"engine-city-test.exe"));
  return Json.Serialize(new object[]{s.id,s.name_id,s.campaign_scenario,s.terrain_edits,s.terrain_asset,s.starting_setup})+"|"+(worker.Exists?worker.Length+":"+worker.LastWriteTimeUtc.Ticks:"missing");
 }
 SalaryFacts SalaryFor(int slotIndex){
  if(project==null||slotIndex<0||slotIndex>=project.slots.Length)return null;
  if(salaryCache==null)salaryCache=new Dictionary<string,SalaryFacts>();
  var slot=project.slots[slotIndex];string key=SalaryKey(slot);SalaryFacts found;
  if(salaryCache.TryGetValue(key,out found))return found;
  var limit=SeaLimit(slot.id);found=limit==null?null:limit.salary;
  if(found!=null&&(found.by_rank==null||found.by_rank.Length!=11))found=null;
  if(seaLimitsError==null)salaryCache[key]=found;   // a failed read is retried next time
  return found;
 }
 static string Monthly(int amount){return "월 "+amount.ToString("N0")+" 데나리";}
 // Standard monthly salary per rank: the engine's amounts at its usual base of 100 (city/emperor.c SALARY_PERCENTAGE_FOR_RANK).
 // Shown until the engine check of this exact map reports the real amounts (a map can start from another base).
 static readonly int[] StandardSalary={0,2,5,8,12,20,30,40,60,80,100};
 static readonly string[] RankNames={"시민","사무관","기술관","설계관","검찰관","행정관","조영관","치안관","집정관","총독","황제"};
 // List labels only; the selected indexes (the saved values) are never touched here.
 static void LabelSalaryLists(System.Windows.Forms.ComboBox rank,System.Windows.Forms.ComboBox salary,SalaryFacts f){
  // With no engine result for this map the lists show the standard amounts (marked 표준); the engine check replaces them.
  Func<int,string> amount=i=>f==null?Monthly(StandardSalary[i])+" (표준)":Monthly(f.by_rank[i]);
  for(int i=0;i<RankNames.Length&&i<rank.Items.Count;i++){string text=RankNames[i]+" — "+amount(i);if((string)rank.Items[i]!=text)rank.Items[i]=text;}
  int r=Math.Max(0,rank.SelectedIndex);string match="직급에 맞춤 — 현재 "+amount(r);
  if(salary.Items.Count>0&&(string)salary.Items[0]!=match)salary.Items[0]=match;
  for(int i=0;i<RankNames.Length&&i+1<salary.Items.Count;i++){string text=RankNames[i]+" — "+amount(i);if((string)salary.Items[i+1]!=text)salary.Items[i+1]=text;}
 }
 static string SalaryNote(bool use,int rank,int salaryRank,SalaryFacts f){
  string unknown="봉급 금액: 표준 금액으로 표시 중 — 이 자리 지도의 실제 금액은 엔진 검사 뒤 확인됩니다(5 검증·내보내기 탭의 게임 적용 검사).";
  string pay="\n봉급은 매달 도시 자금에서 나가 통치자의 개인 재산으로 들어갑니다. 도시 자금이 -5,000 이하인 달에는 지급되지 않습니다.";
  if(!use)return (f==null?"기존 시작 방식의 봉급(시민 직급): 표준 "+Monthly(StandardSalary[0])+" — 실제 금액은 엔진 검사 뒤 확인됩니다.":"기존 시작 방식의 봉급(시민 직급): "+Monthly(f.by_rank[0])+".")+pay;
  int paid=salaryRank<0?rank:salaryRank;
  if(f==null)return "봉급(표준): "+Monthly(StandardSalary[paid])+(paid==rank?"":" ("+RankNames[paid]+" 봉급, 직급 기준은 "+Monthly(StandardSalary[rank])+")")+"\n"+unknown+pay;
  string line=paid==rank?"봉급: "+Monthly(f.by_rank[rank])+" ("+RankNames[rank]+" 직급 기준과 같음)":"직급 기준 "+Monthly(f.by_rank[rank])+" / 설정 봉급 "+Monthly(f.by_rank[paid])+" ("+RankNames[paid]+" 봉급)";
  return line+" · 기준액 "+f.@base+"(엔진 검사 결과)"+pay;
 }
}
