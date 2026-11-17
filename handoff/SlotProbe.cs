using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.Serialization;
using System.Collections.Generic;
using System.Web.Script.Serialization;
// Slot funds, role hints, player-to-player exceptions and trade links in the actual editor assembly. No GUI.
class SlotProbe {
 static Type T=typeof(Scenario).Assembly.GetType("ScenarioCreator");
 static BindingFlags F=BindingFlags.Instance|BindingFlags.Static|BindingFlags.NonPublic;
 static JavaScriptSerializer J=new JavaScriptSerializer{MaxJsonLength=16777216};
 static List<object> results=new List<object>();
 static object Call(object o,string n,params object[] a){try{return T.GetMethod(n,F).Invoke(o,a);}catch(TargetInvocationException e){throw e.InnerException;}}
 static void Set(object o,string n,object v){T.GetField(n,F).SetValue(o,v);}
 static object Get(object o,string n){return T.GetField(n,F).GetValue(o);}
 static void Check(string name,bool ok){results.Add(new{name=name,passed=ok});}
 static void Main(string[] args){
  string fixture=File.ReadAllText(args[0]);Directory.CreateDirectory(args[1]);
  var p=J.Deserialize<Scenario>(fixture);var o=FormatterServices.GetUninitializedObject(T);Set(o,"project",p);Set(o,"seaLimits",new Dictionary<string,CityLimit>());
  p.slots[0].starting_funds=0;p.slots[1].starting_funds=25000;p.slots[2].role_hint="식량 공급을 맡기 좋은 도시";
  string saved=(string)Call(null,"SerializeProject",p);var data=J.DeserializeObject(saved) as Dictionary<string,object>;
  var slots=((object[])data["slots"]).Cast<Dictionary<string,object>>().ToArray();
  Check("zero_funds_saved_as_zero",slots[0].ContainsKey("starting_funds")&&Convert.ToInt32(slots[0]["starting_funds"])==0);
  Check("unset_funds_not_saved",!slots[3].ContainsKey("starting_funds")&&!slots[3].ContainsKey("role_hint"));
  Check("role_hint_saved",(string)slots[2]["role_hint"]=="식량 공급을 맡기 좋은 도시");
  File.WriteAllText(Path.Combine(args[1],"funds.json"),saved);
  Check("default_pair_allowed",(bool)Call(o,"PairAllowed","player1","player3"));
  Call(o,"SetPairAllowed","player3","player1",false);
  Check("pair_blocked_both_ways",!(bool)Call(o,"PairAllowed","player1","player3")&&!(bool)Call(o,"PairAllowed","player3","player1"));
  Call(o,"SetPairAllowed","player1","player3",false);
  var rows=(List<Dictionary<string,object>>)Call(o,"ReadPairs");
  Check("pair_stored_once_sorted",rows.Count==1&&string.Join(",",((System.Collections.IEnumerable)rows[0]["between"]).Cast<object>().Select(Convert.ToString))=="player1,player3");
  Call(o,"SetPairAllowed","player2","player4",false);
  File.WriteAllText(Path.Combine(args[1],"pairs.json"),(string)Call(null,"SerializeProject",p));
  Call(o,"SetPairAllowed","player2","player4",true);
  Check("allow_again_removes_record",((List<Dictionary<string,object>>)Call(o,"ReadPairs")).Count==1);
  Call(o,"ForgetSlotPairs","player3");
  Check("deleted_slot_takes_pairs",!p.rules.ContainsKey("player_trade"));
  var report=new LimitReport{limits=p.slots.Select(s=>new CityLimit{slot=s.id,sea="unknown",reason=""}).ToArray(),
   links=new[]{new SlotLinks{slot="player1",name_id=p.slots[0].name_id,links=new[]{new CityLink{kind="player",slot="player2",transport="land",state="ok",allowed=true}}}}};
  Check("links_read",(bool)Call(o,"RefreshSeaLimits","s1",(Func<LimitReport>)(()=>report))&&((CityLink[])Call(o,"LinksForSlot","player1")).Length==1);
  Check("no_links_for_other_slot",Call(o,"LinksForSlot","player2")==null);
  Func<LimitReport> broken=()=>{throw new IOException("injected");};
  Call(o,"RefreshSeaLimits","s2",broken);
  Check("failed_read_drops_links",Call(o,"LinksForSlot","player1")==null);
  Set(o,"map",new CreatorMapView());Set(o,"linksVersion",3);Set(o,"linksShownVersion",2);
  Check("stale_links_not_drawn",Call(o,"MapLinksFor",p.slots[0].name_id)==null);
  Console.WriteLine(J.Serialize(results));
 }
}
