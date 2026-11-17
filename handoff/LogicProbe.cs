using System;
using System.IO;
using System.Reflection;
using System.Runtime.Serialization;
using System.Collections.Generic;
using System.Web.Script.Serialization;
class LogicProbe {
 static Type T=typeof(Scenario).Assembly.GetType("ScenarioCreator");
 static BindingFlags F=BindingFlags.Instance|BindingFlags.Static|BindingFlags.NonPublic;
 static object Call(object o,string n,params object[] a){return T.GetMethod(n,F).Invoke(o,a);}
 static void Main(string[] args){
 var json=new JavaScriptSerializer{MaxJsonLength=16777216};
 var p=json.Deserialize<Scenario>(File.ReadAllText(args[0]));
 var o=FormatterServices.GetUninitializedObject(T);T.GetField("project",F).SetValue(o,p);
 var results=new List<object>();
 var s=p.slots[0];s.terrain_edits=new[]{new TerrainEdit{x=10,y=10,kind="land"}};
 string a=(string)Call(o,"SeaStamp");s.terrain_edits[0].kind="rock";string b=(string)Call(o,"SeaStamp");
 results.Add(new{name="terrain_kind_cache_invalidation",passed=a!=b,before=a,after=b});
 s.terrain_edits[0]=new TerrainEdit{x=10,y=33,kind="land"};a=(string)Call(o,"SeaStamp");
 s.terrain_edits[0]=new TerrainEdit{x=11,y=10,kind="land"};b=(string)Call(o,"SeaStamp");
 results.Add(new{name="terrain_coordinate_cache_invalidation",passed=a!=b,before=a,after=b});
 var c=new City{name_id=999,role="npc",sells=new Dictionary<string,int>(),buys=new Dictionary<string,int>()};
 T.GetField("merged",F).SetValue(o,new MergedCatalog{cities=new[]{new MergedCity{name_id=999,default_trade_id="default",trade_presets=new[]{new TradePreset{id="default",sea=1,cost=100,sells=new Dictionary<string,int>{{"1",15}},buys=new Dictionary<string,int>()}}}}});
 Call(o,"ParkNeutralTrade",c);Call(o,"ParkPlayerCity",c,s);
 results.Add(new{name="empty_neutral_trade_roundtrip",passed=c.sea==0&&c.cost==0&&c.sells.Count==0,sea=c.sea,cost=c.cost,sells=c.sells});
 var kept=(Slot)Call(o,"ParkedCopy",s);var target=new Slot{allowed_buildings=new[]{76},governance=new Governance{favor=33},starting_setup="empty"};
 Call(o,"RestoreParked",target,kept);
 results.Add(new{name="slot_settings_stay",passed=target.allowed_buildings[0]==76&&target.governance.favor==33&&target.starting_setup=="empty"&&target.campaign_scenario==s.campaign_scenario});
 p=json.Deserialize<Scenario>(File.ReadAllText(args[0]));
 string saved=(string)Call(null,"SerializeProject",p);File.WriteAllText(args[1],saved);
 results.Add(new{name="reserved_field_preserved",passed=saved.Contains("\"reserved\":true")});
 Console.WriteLine(json.Serialize(results));
 }
}
