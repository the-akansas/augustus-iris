using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.Serialization;
using System.Collections.Generic;
using System.Web.Script.Serialization;
class Regression {
 static Type T=typeof(Scenario).Assembly.GetType("ScenarioCreator");
 static BindingFlags F=BindingFlags.Instance|BindingFlags.Static|BindingFlags.NonPublic;
 static JavaScriptSerializer J=new JavaScriptSerializer{MaxJsonLength=16777216};
 static string fixture;static List<object> results=new List<object>();static int failed;
 static object Call(object o,string n,params object[] args){try{return T.GetMethod(n,F).Invoke(o,args);}catch(TargetInvocationException e){throw e.InnerException;}}
 static void Set(object o,string n,object v){T.GetField(n,F).SetValue(o,v);}
 static object Get(object o,string n){return T.GetField(n,F).GetValue(o);}
 static Scenario P(){return J.Deserialize<Scenario>(fixture);}
 static object Editor(Scenario p){var o=FormatterServices.GetUninitializedObject(T);Set(o,"project",p);Set(o,"seaLimits",new Dictionary<string,CityLimit>());return o;}
 static void Check(string name,bool ok){results.Add(new{name=name,passed=ok});if(!ok)failed++;}
 static string Save(Scenario p){return (string)Call(null,"SerializeProject",p);}
 static bool EqualData(object a,object b){
  var da=a as Dictionary<string,object>;var db=b as Dictionary<string,object>;
  if(da!=null)return db!=null&&da.Count==db.Count&&da.All(k=>db.ContainsKey(k.Key)&&EqualData(k.Value,db[k.Key]));
  var aa=a as object[];var ab=b as object[];
  if(aa!=null)return ab!=null&&aa.Length==ab.Length&&aa.Select((v,i)=>EqualData(v,ab[i])).All(x=>x);
  return Equals(a,b);
 }
 static bool Same(string a,string b){return EqualData(J.DeserializeObject(a),J.DeserializeObject(b));}
 static LimitReport Report(Scenario p,string sea){return new LimitReport{limits=p.slots.Select(s=>new CityLimit{slot=s.id,sea=sea,reason="fixture"}).ToArray()};}
 static void Main(string[] args){fixture=File.ReadAllText(args[0]);string output=args[1];Directory.CreateDirectory(output);
  var p=P();var o=Editor(p);string a=(string)Call(o,"SeaStamp");
  p.empire.cities.First(c=>c.role=="npc").sea^=1;
  Check("cache_includes_neutral_trade",a!=(string)Call(o,"SeaStamp"));
  a=(string)Call(o,"SeaStamp");p.slots[0].starting_setup="practice";
  Check("cache_includes_starting_setup",a!=(string)Call(o,"SeaStamp"));
  a=(string)Call(o,"SeaStamp");bool stable=true;for(int i=0;i<100;i++){Call(o,"RequirePlayerRemoval",p.slots[0].name_id);stable&=a==(string)Call(o,"SeaStamp");}
  Check("unchanged_input_cache_stable",stable);
  int calls=0;
  Func<LimitReport> broken=()=>{calls++;throw new IOException("injected read failure");};
  Check("failed_read_not_success",!(bool)Call(o,"RefreshSeaLimits","v1",broken));
  Check("failed_read_has_reason",((string)Get(o,"seaLimitsError")).Contains("injected"));
  Func<LimitReport> ready=()=>{calls++;return Report(p,"blocked");};
  Check("failed_read_retries_same_stamp",(bool)Call(o,"RefreshSeaLimits","v1",ready)&&calls==2);
  Check("successful_read_is_cached",(bool)Call(o,"RefreshSeaLimits","v1",broken)&&calls==2);
  Check("changed_input_failure_clears_old_result",!(bool)Call(o,"RefreshSeaLimits","v2",broken)&&((Dictionary<string,CityLimit>)Get(o,"seaLimits")).Count==0);
  Func<LimitReport> partial=()=>new LimitReport{limits=new[]{new CityLimit{slot=p.slots[0].id,sea="blocked"}}};
  Check("partial_report_not_cached",!(bool)Call(o,"RefreshSeaLimits","v2",partial)&&Get(o,"seaLimitsStamp")==null);
  Check("partial_report_retry",(bool)Call(o,"RefreshSeaLimits","v2",ready));
  Set(o,"seaLimitsStamp",Call(o,"SeaStamp"));
  var reader=(Func<string,CityLimit>)Call(o,"SeaReader");
  ((Dictionary<string,CityLimit>)Get(o,"seaLimits")).Clear();
  Check("list_refresh_uses_consistent_snapshot",reader(p.slots[0].id).sea=="blocked");
  var dockOnly=new CityLimit{sea="blocked",buildings=new[]{75}};
  Check("dock_is_restricted",(bool)Call(null,"SeaBuildingBlocked",dockOnly,75));
  Check("fishing_buildings_not_restricted",!(bool)Call(null,"SeaBuildingBlocked",dockOnly,76)&&!(bool)Call(null,"SeaBuildingBlocked",dockOnly,74));
  var blocked=new CityLimit{sea="blocked"};var unknown=new CityLimit{sea="unknown"};var candidate=new CityLimit{sea="candidate"};
  Check("blocked_new_selection_denied",!(bool)Call(null,"TradeSelectionAllowed",false,true,1,blocked));
  Check("blocked_existing_selection_preserved",(bool)Call(null,"TradeSelectionAllowed",true,true,1,blocked));
  Check("blocked_existing_can_uncheck",!(bool)Call(null,"TradeSelectionAllowed",true,false,1,blocked));
  Check("blocked_unchecked_cannot_recheck",!(bool)Call(null,"TradeSelectionAllowed",false,true,1,blocked));
  Check("land_toggle_allows",(bool)Call(null,"TradeSelectionAllowed",false,true,0,blocked));
  Check("sea_toggle_restricts",!(bool)Call(null,"TradeSelectionAllowed",false,true,1,blocked));
  Check("unknown_does_not_block",(bool)Call(null,"TradeSelectionAllowed",false,true,1,unknown));
  Check("candidate_does_not_block",(bool)Call(null,"TradeSelectionAllowed",false,true,1,candidate));
  Check("missing_result_does_not_block",(bool)Call(null,"TradeSelectionAllowed",false,true,1,null));
  p=P();o=Editor(p);var ns=p.empire.cities.Where(c=>c.role=="npc"&&!c.reserved).Take(2).ToArray();
  ns[0].sea=1;ns[0].trade_players=new[]{p.slots[1].id};ns[1].sea=0;ns[1].trade_players=new string[0];
  var all=p.slots.Select(s=>s.id).ToArray();Func<string,CityLimit> blockAll=id=>blocked;
  int rejected=(int)Call(o,"ApplyNeutralBatchData",ns.Select(c=>c.name_id).ToArray(),(bool?)true,all,blockAll);
  Check("batch_filters_only_new_sea_links",rejected==3&&ns[0].trade_players.SequenceEqual(new[]{p.slots[1].id})&&ns[1].trade_players.SequenceEqual(all));
  Check("batch_enabled_state",ns.All(c=>c.enabled));
  foreach(var metric in new[]{"population","culture","prosperity","peace","favor","treasury"}){
   p=P();o=Editor(p);var goal=new ObjectiveTarget();typeof(ObjectiveTarget).GetField(metric).SetValue(goal,1);
   p.rules["objectives"]=new ObjectiveSettings{population_total=100,per_city=new Dictionary<string,ObjectiveTarget>{{p.slots[0].id,goal}}};p.rules["mode"]="cooperative";
   string before=Save(p);bool refused=false;try{Call(o,"RemovePlayerData",p.slots[0].name_id);}catch(Exception e){refused=e.Message.Contains("공동 목표");}
   string after=Save(p);
   Check("remove_refuses_goal_"+metric,refused&&Same(after,before));
  }
  foreach(bool sender in new[]{true,false}){
   p=P();o=Editor(p);p.rules["mode"]="cooperative";p.rules["objectives"]=new ObjectiveSettings{per_city=new Dictionary<string,ObjectiveTarget>(),deliveries=new List<DeliveryGoal>{new DeliveryGoal{id="x",sender=p.slots[sender?0:1].id,receiver=p.slots[sender?1:0].id,resource=1,quantity=10,kind="gift"}}};
   string before=Save(p);bool refused=false;try{Call(o,"RemovePlayerData",p.slots[0].name_id);}catch(Exception e){refused=e.Message.Contains("공동 목표");}
   string after=Save(p);
   Check("remove_refuses_delivery_"+(sender?"sender":"receiver"),refused&&Same(after,before));
  }
  p=P();o=Editor(p);var leaving=p.slots[0];var remaining=p.slots[1];
  p.rules["mode"]="cooperative";p.rules["objectives"]=new ObjectiveSettings{population_total=100,per_city=new Dictionary<string,ObjectiveTarget>{{leaving.id,new ObjectiveTarget()}}};
  var npc=p.empire.cities.First(c=>c.role=="npc"&&!c.reserved);npc.trade_players=new[]{leaving.id,remaining.id};
  var other=p.empire.cities.First(c=>c.name_id==remaining.name_id);other.parked_trade=new ParkedTrade{sea=0,cost=0,sells=new Dictionary<string,int>(),buys=new Dictionary<string,int>(),trade_players=new[]{leaving.id,remaining.id}};
  Set(o,"merged",new MergedCatalog{cities=new MergedCity[0]});
  Call(o,"RemovePlayerData",leaving.name_id);
  Check("remove_cleans_live_and_parked_partners",npc.trade_players.SequenceEqual(new[]{remaining.id})&&other.parked_trade.trade_players.SequenceEqual(new[]{remaining.id}));
  var goals=J.Deserialize<ObjectiveSettings>(J.Serialize(p.rules["objectives"]));
  Check("remove_cleans_zero_goal",!goals.per_city.ContainsKey(leaving.id));
  var released=p.empire.cities.First(c=>c.name_id==leaving.name_id);
  Check("remove_keeps_terrain",released.role=="npc"&&!released.enabled&&released.map.campaign_scenario==leaving.campaign_scenario);
  File.WriteAllText(Path.Combine(output,"removed-player.json"),Save(p));
  p=P();o=Editor(p);Set(o,"merged",new MergedCatalog{cities=new MergedCity[0]});
  Call(o,"RemovePlayerData",p.slots[0].name_id);Call(o,"RemovePlayerData",p.slots[0].name_id);
  string last=Save(p);bool min=false;try{Call(o,"RemovePlayerData",p.slots[0].name_id);}catch(Exception e){min=e.Message.Contains("최소 2개");}
  Check("minimum_two_preserved",min&&Same(Save(p),last));
  p=P();o=Editor(p);var reserved=p.empire.cities.First(c=>c.reserved);
  Check("reserved_city_not_assignable",!(bool)Call(o,"HasTerrain",reserved.name_id));
  Console.WriteLine(J.Serialize(new{passed=failed==0,total=results.Count,failed=failed,results=results}));Environment.ExitCode=failed==0?0:1;
 }
}
