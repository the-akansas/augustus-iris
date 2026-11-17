using System;
using System.Linq;
using System.Drawing;
using System.Collections.Generic;
using System.Windows.Forms;
// Slot settings: starting funds, the author's role hint and player-to-player trade exceptions.
// Same data rules as Augustus/trade_policy.py and scenario_project.py (those are the tested reference):
//  - starting_funds on a slot overrides rules.starting_funds; absent = the common amount. 0 is a real amount.
//  - player_trade exceptions name slots, are stored once per pair (sorted ids) and leave with a deleted slot.
// Trade states shown here come from scenario_check.py --links, never from a separate judgement.
partial class ScenarioCreator {
 ComboBox slotSettingsPicker=new ComboBox{DropDownStyle=ComboBoxStyle.DropDownList,Width=330};
 CheckBox useCommonFunds=new CheckBox{AutoSize=true};
 NumericUpDown slotFunds=new NumericUpDown{Minimum=0,Maximum=1000000,ThousandsSeparator=true,Width=150};
 TextBox roleHint=new TextBox{Width=520,MaxLength=300};
 CheckedListBox playerTrade=new CheckedListBox{Dock=DockStyle.Fill,CheckOnClick=true,IntegralHeight=false};
 TextBox linkSummary=new TextBox{Dock=DockStyle.Fill,Multiline=true,ReadOnly=true,ScrollBars=ScrollBars.Vertical};
 CheckBox showForbidden=new CheckBox{Text="지도에 교역 금지 관계도 흐리게 표시",AutoSize=true};
 TabPage slotSettingsTab;
 Timer linksTimer;int linksVersion,linksShownVersion=-1;

 void BuildSlotSettingsTab(){
  slotSettingsTab=new TabPage("9  자리별 시작 자금·교역"){BackColor=Paper};tabs.TabPages.Add(slotSettingsTab);
  var panel=new TableLayoutPanel{Dock=DockStyle.Fill,ColumnCount=2,RowCount=7,Padding=new Padding(18)};
  panel.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,170));panel.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));
  foreach(int h in new[]{40,72,64,24})panel.RowStyles.Add(new RowStyle(SizeType.Absolute,h));
  panel.RowStyles.Add(new RowStyle(SizeType.Percent,40));panel.RowStyles.Add(new RowStyle(SizeType.Absolute,30));panel.RowStyles.Add(new RowStyle(SizeType.Percent,60));
  slotSettingsTab.Controls.Add(panel);
  panel.Controls.Add(new Label{Text="플레이어 자리",AutoSize=true,Padding=new Padding(0,6,0,0)},0,0);panel.Controls.Add(slotSettingsPicker,1,0);
  var funds=new FlowLayoutPanel{Dock=DockStyle.Fill,WrapContents=true};funds.Controls.Add(useCommonFunds);funds.Controls.Add(slotFunds);funds.Controls.Add(new Label{Text="데나리",AutoSize=true,Padding=new Padding(0,6,8,0)});
  funds.Controls.Add(Button("모든 자리에 이 금액 적용",()=>Guard(ApplyFundsToAll),200));
  funds.Controls.Add(new Label{Text="0도 그대로 0으로 시작합니다. 이어하기에서는 다시 지급하지 않습니다.",AutoSize=true,ForeColor=Dark,Padding=new Padding(0,6,0,0)});
  panel.Controls.Add(new Label{Text="시작 자금",AutoSize=true,Padding=new Padding(0,6,0,0)},0,1);panel.Controls.Add(funds,1,1);
  var hint=new FlowLayoutPanel{Dock=DockStyle.Fill,WrapContents=true};hint.Controls.Add(roleHint);
  hint.Controls.Add(new Label{Text="로비에 \"제작자 추천\"으로만 보입니다. 규칙이 아니며 플레이를 강제하지 않습니다.",AutoSize=true,ForeColor=Dark});
  panel.Controls.Add(new Label{Text="추천 역할 (선택)",AutoSize=true,Padding=new Padding(0,6,0,0)},0,2);panel.Controls.Add(hint,1,2);
  panel.Controls.Add(new Label{Text="체크한 플레이어와 교역할 수 있습니다. 해제하면 판매·선물·계약이 모두 막힙니다(양방향).",AutoSize=true,ForeColor=Dark},1,3);
  panel.Controls.Add(new Label{Text="플레이어 간 교역",AutoSize=true,Padding=new Padding(0,6,0,0)},0,4);panel.Controls.Add(playerTrade,1,4);
  panel.Controls.Add(showForbidden,1,5);
  panel.Controls.Add(new Label{Text="이 도시의 교역 관계",AutoSize=true,Padding=new Padding(0,6,0,0)},0,6);panel.Controls.Add(linkSummary,1,6);
  slotSettingsPicker.SelectedIndexChanged+=(s,e)=>{if(!slotSettingsLoading)ShowSlotSettings();};
  useCommonFunds.CheckedChanged+=(s,e)=>{if(slotSettingsLoading)return;var slot=CurrentSettingsSlot();if(slot==null)return;slot.starting_funds=useCommonFunds.Checked?(int?)null:(int)slotFunds.Value;slotFunds.Enabled=!useCommonFunds.Checked;Changed();ShowSlotSettings();};
  slotFunds.ValueChanged+=(s,e)=>{if(slotSettingsLoading)return;var slot=CurrentSettingsSlot();if(slot==null||useCommonFunds.Checked)return;slot.starting_funds=(int)slotFunds.Value;Changed();};
  roleHint.TextChanged+=(s,e)=>{if(slotSettingsLoading)return;var slot=CurrentSettingsSlot();if(slot==null)return;string text=roleHint.Text.Replace("\r"," ").Replace("\n"," ").Trim();slot.role_hint=text.Length==0?null:text;Changed();};
  playerTrade.ItemCheck+=(s,e)=>{if(slotSettingsLoading)return;var slot=CurrentSettingsSlot();if(slot==null)return;var other=(NameChoiceSlot)playerTrade.Items[e.Index];SetPairAllowed(slot.id,other.id,e.NewValue==CheckState.Checked);Changed();};
  showForbidden.CheckedChanged+=(s,e)=>{map.ShowForbidden=showForbidden.Checked;map.Invalidate();};
  tabs.SelectedIndexChanged+=(s,e)=>{if(tabs.SelectedTab==slotSettingsTab)RefreshSlotSettings();};
 }
 bool slotSettingsLoading;
 class NameChoiceSlot { public string id,label; public override string ToString(){return label;} }
 Slot CurrentSettingsSlot(){int i=slotSettingsPicker.SelectedIndex;return project==null||i<0||i>=project.slots.Length?null:project.slots[i];}
 int CommonFunds(){object v;return project.rules.TryGetValue("starting_funds",out v)&&v!=null?Convert.ToInt32(v):0;}

 void RefreshSlotSettings(){
  if(project==null)return;slotSettingsLoading=true;int keep=Math.Max(0,slotSettingsPicker.SelectedIndex);slotSettingsPicker.Items.Clear();
  for(int i=0;i<project.slots.Length;i++)slotSettingsPicker.Items.Add("P"+(i+1)+" · "+CityName(project.slots[i].name_id));
  slotSettingsPicker.SelectedIndex=project.slots.Length==0?-1:Math.Min(keep,project.slots.Length-1);slotSettingsLoading=false;ShowSlotSettings();
 }
 void ShowSlotSettings(){
  var slot=CurrentSettingsSlot();if(slot==null)return;slotSettingsLoading=true;
  int common=CommonFunds();useCommonFunds.Text="기본 시작 자금 사용 ("+common.ToString("N0")+")";
  useCommonFunds.Checked=!slot.starting_funds.HasValue;slotFunds.Value=Math.Max(0,Math.Min(1000000,slot.starting_funds??common));slotFunds.Enabled=slot.starting_funds.HasValue;
  roleHint.Text=slot.role_hint??"";
  playerTrade.Items.Clear();
  for(int i=0;i<project.slots.Length;i++){var other=project.slots[i];if(other.id==slot.id)continue;playerTrade.Items.Add(new NameChoiceSlot{id=other.id,label="P"+(i+1)+" · "+CityName(other.name_id)},PairAllowed(slot.id,other.id));}
  slotSettingsLoading=false;linkSummary.Text=DescribeLinks(slot);
 }
 void ApplyFundsToAll(){
  int amount=(int)slotFunds.Value;
  if(LangBox.Show(this,"모든 자리의 시작 자금을 "+amount.ToString("N0")+" 데나리로 맞출까요?\n자리별로 따로 정한 금액은 지워지고 기본 시작 자금이 이 값으로 바뀝니다.","시작 자금",MessageBoxButtons.YesNo)!=DialogResult.Yes)return;
  project.rules["starting_funds"]=amount;foreach(var s in project.slots)s.starting_funds=null;
  loading=true;startingFunds.Value=amount;loading=false;Changed();ShowSlotSettings();
 }

 // ---- player-to-player exceptions in rules.player_trade (one record per sorted pair) ----
 List<Dictionary<string,object>> ReadPairs(){
  var rows=new List<Dictionary<string,object>>();object raw;
  if(!project.rules.TryGetValue("player_trade",out raw)||raw==null)return rows;
  var policy=Json.Deserialize<Dictionary<string,object>>(Json.Serialize(raw));object list;
  if(policy.TryGetValue("exceptions",out list)&&list is System.Collections.IEnumerable)foreach(var item in (System.Collections.IEnumerable)list){var row=item as Dictionary<string,object>;if(row!=null)rows.Add(row);}
  return rows;
 }
 static string[] PairOf(Dictionary<string,object> row){var pair=((System.Collections.IEnumerable)row["between"]).Cast<object>().Select(Convert.ToString).ToArray();return pair;}
 void WritePairs(List<Dictionary<string,object>> rows){
  rows.Sort((a,b)=>string.CompareOrdinal(string.Join("\u0001",PairOf(a)),string.Join("\u0001",PairOf(b))));
  if(rows.Count==0)project.rules.Remove("player_trade");else project.rules["player_trade"]=new Dictionary<string,object>{{"exceptions",rows}};
 }
 bool PairAllowed(string a,string b){
  var key=new[]{a,b}.OrderBy(x=>x,StringComparer.Ordinal).ToArray();
  foreach(var row in ReadPairs()){var pair=PairOf(row);if(pair.Length==2&&pair[0]==key[0]&&pair[1]==key[1])return Convert.ToBoolean(row["allow"]);}
  return true; // no team rules yet: the base policy lets players trade
 }
 void SetPairAllowed(string a,string b,bool allow){
  var key=new[]{a,b}.OrderBy(x=>x,StringComparer.Ordinal).ToArray();
  var rows=ReadPairs().Where(r=>{var p=PairOf(r);return !(p.Length==2&&p[0]==key[0]&&p[1]==key[1]);}).ToList();
  if(!allow)rows.Add(new Dictionary<string,object>{{"between",key},{"allow",false}});
  WritePairs(rows);
 }
 void ForgetSlotPairs(string id){WritePairs(ReadPairs().Where(r=>!PairOf(r).Contains(id)).ToList());}

 // ---- shared trade-link answers (scenario_check.py --links) for the map and this tab ----
 CityLink[] LinksForSlot(string id){CityLink[] found;return slotLinks.TryGetValue(id,out found)?found:null;}
 CityLink[] MapLinksFor(int nameId){
  if(project==null||linksShownVersion!=linksVersion){map.LinksNote="교역 연결을 다시 확인하는 중입니다.";return null;}
  var slot=Array.Find(project.slots,s=>s.name_id==nameId);if(slot==null)return null;
  var links=LinksForSlot(slot.id);map.LinksNote=links==null?(seaLimitsError??"교역 연결 결과가 없습니다."):null;return links;
 }
 void ScheduleLinks(){
  linksVersion++;
  if(linksTimer==null){linksTimer=new Timer{Interval=600};linksTimer.Tick+=(s,e)=>{linksTimer.Stop();RefreshLinksNow();};}
  linksTimer.Stop();linksTimer.Start();
 }
 void RefreshLinksNow(){
  if(project==null||project.slots.Length==0)return;int version=linksVersion;
  SeaLimit(project.slots[0].id); // one call refreshes limits and links together
  linksShownVersion=version;map.Invalidate();
  if(tabs.SelectedTab==slotSettingsTab){var slot=CurrentSettingsSlot();if(slot!=null)linkSummary.Text=DescribeLinks(slot);}
 }
 string DescribeLinks(Slot slot){
  var links=LinksForSlot(slot.id);
  if(links==null)return seaLimitsError??"교역 관계를 아직 확인하지 않았습니다. 잠시 후 다시 열거나 다른 설정을 바꾸면 갱신됩니다.";
  // Only what cannot trade, and why (2026-11-13: listing every partner with its goods was too much to read).
  var lines=new List<string>();
  Func<CityLink,string> who=l=>l.kind=="player"?"P"+(Array.FindIndex(project.slots,s=>s.id==l.slot)+1)+" "+CityName(project.slots.First(s=>s.id==l.slot).name_id):CityName(l.name_id);
  Func<string,string> word=s=>s=="ok"?"가능":s=="candidate"?"가능 후보(확정 아님)":s=="unknown"?"미확인":s=="broken"?"불가":"허용 안 함";
  Func<int[],string> goods=ids=>ids==null||ids.Length==0?"없음":string.Join(", ",ids.Where(r=>r>=1&&r<=Resources.Length).Select(r=>Resources[r-1]));
  if(links.Length==0)return "교역 상대가 없습니다.";
  int fine=links.Count(l=>l.allowed&&(l.state=="ok"||l.state=="candidate"));
  var broken=links.Where(l=>l.allowed&&l.state=="broken").ToArray();var off=links.Where(l=>!l.allowed).ToArray();var unknown=links.Where(l=>l.allowed&&l.state=="unknown").ToArray();
  lines.Add("교역 가능 "+fine+"곳 · 불가 "+(broken.Length+off.Length)+"곳"+(unknown.Length>0?" · 미확인 "+unknown.Length+"곳":""));
  foreach(var l in broken.OrderBy(l=>l.kind=="player"?0:1))lines.Add("불가: "+who(l)+" ("+(l.transport=="sea"?"해로":"육로")+") — "+l.reason);
  foreach(var l in off.OrderBy(l=>l.kind=="player"?0:1))lines.Add("허용 안 함: "+who(l)+" — "+(l.kind=="player"?"이 탭의 \"플레이어 간 교역\"에서 꺼 둠":"2번 탭에서 그 중립도시의 교역 허용에 이 자리가 빠져 있음"));
  if(unknown.Length>0)lines.Add("미확인: "+string.Join(", ",unknown.Select(who))+" — 5번 탭의 게임 적용 검사 뒤에 판정됩니다.");
  if(broken.Length+off.Length+unknown.Length==0)lines.Add("거래할 수 없는 도시가 없습니다.");
  return string.Join("\r\n",lines);
 }
}
