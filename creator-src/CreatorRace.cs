using System;
using System.Linq;
using System.Drawing;
using System.Collections.Generic;
using System.Windows.Forms;
// 기한 경쟁 (competition, user 2026-11-15): after rules.race.months months the city with the most of rules.race.stat
// wins; a tie shares the win and play goes on. rules.mode "deadline-race" (format 4). The room judges it with the
// shared samples of the cooperative goals (Augustus/objectives.py race_*).
partial class ScenarioCreator {
 static readonly string[] RaceStats={"prosperity","population","culture","peace","favor","treasury"};
 static readonly string[] RaceStatNames={"번영","인구","문화","평화","황제 지지도","자금"};
 Panel racePanel;ComboBox raceStat=new ComboBox{DropDownStyle=ComboBoxStyle.DropDownList,Width=180};NumericUpDown raceMonths=new NumericUpDown{Minimum=6,Maximum=600,Value=120,Width=90};bool raceFilling;
 bool RaceEnabled{get{return project!=null&&project.rules!=null&&project.rules.ContainsKey("race")&&project.rules["race"]!=null;}}
 Control BuildRacePanel(){
  racePanel=new Panel{Dock=DockStyle.Top,Height=170,Visible=false};
  var t=new TableLayoutPanel{Dock=DockStyle.Fill,ColumnCount=2,RowCount=3};t.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,150));t.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));
  t.RowStyles.Add(new RowStyle(SizeType.Absolute,82));t.RowStyles.Add(new RowStyle(SizeType.Absolute,36));t.RowStyles.Add(new RowStyle(SizeType.Absolute,36));
  var intro=TextLabel("정해진 기간이 끝났을 때 고른 수치가 가장 높은 도시가 승리합니다. 동점이면 함께 승리하고, 그 뒤에도 계속 플레이합니다.\n기간 중에는 반 달마다 하는 공동 검사 때 순위를 보여 주고, 마감 뒤 첫 공동 검사에서 승자가 정해집니다. 모든 플레이 도시가 참여해야 판정합니다.");
  t.Controls.Add(intro,0,0);t.SetColumnSpan(intro,2);
  foreach(var n in RaceStatNames)raceStat.Items.Add(Lang.T(n));raceStat.SelectedIndex=0;
  t.Controls.Add(new Label{Text="비교할 수치",AutoSize=true,Padding=new Padding(0,7,0,0)},0,1);t.Controls.Add(raceStat,1,1);
  var months=new FlowLayoutPanel{AutoSize=true,WrapContents=false,Margin=new Padding(0)};months.Controls.Add(raceMonths);months.Controls.Add(new Label{AutoSize=true,Text="개월 뒤 마감 (시작부터)"});
  t.Controls.Add(new Label{Text="기간",AutoSize=true,Padding=new Padding(0,7,0,0)},0,2);t.Controls.Add(months,1,2);
  racePanel.Controls.Add(t);
  raceStat.SelectedIndexChanged+=(s,e)=>RaceEdited();raceMonths.ValueChanged+=(s,e)=>RaceEdited();
  return racePanel;
 }
 void RaceEdited(){
  if(raceFilling||loading||!RaceEnabled)return;
  project.rules["race"]=new Dictionary<string,object>{{"stat",RaceStats[Math.Max(0,raceStat.SelectedIndex)]},{"months",(int)raceMonths.Value}};Changed();
 }
 void RaceFill(){
  if(!RaceEnabled)return;var race=project.rules["race"] as Dictionary<string,object>;if(race==null)return;raceFilling=true;
  try{object v;int i=race.TryGetValue("stat",out v)?Array.IndexOf(RaceStats,Convert.ToString(v)):0;raceStat.SelectedIndex=Math.Max(0,i);
   if(race.TryGetValue("months",out v))raceMonths.Value=Math.Max(raceMonths.Minimum,Math.Min(raceMonths.Maximum,Convert.ToInt32(v)));}
  finally{raceFilling=false;}
 }
 void RaceModeChosen(bool on){
  if(project==null)return;
  if(!on){project.rules.Remove("race");if(Convert.ToString(project.rules["mode"])=="deadline-race")project.rules["mode"]="free-build";MinPlayersFloor();return;}
  if(!RaceEnabled)project.rules["race"]=new Dictionary<string,object>{{"stat","prosperity"},{"months",120}};
  project.rules.Remove("objectives");project.rules["mode"]="deadline-race";RaceFill();MinPlayersFloor();
 }
 string RaceSummary(){if(!RaceEnabled)return "";var race=project.rules["race"] as Dictionary<string,object>;object s,m;if(race==null||!race.TryGetValue("stat",out s)||!race.TryGetValue("months",out m))return "";int i=Array.IndexOf(RaceStats,Convert.ToString(s));return m+"개월 뒤 "+(i<0?Convert.ToString(s):RaceStatNames[i])+" 값이 가장 높은 도시가 승리";}
}
