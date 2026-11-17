using System;
using System.Linq;
using System.Drawing;
using System.Windows.Forms;
partial class ScenarioCreator {
 FlowLayoutPanel accessBar=new FlowLayoutPanel{Dock=DockStyle.Top,AutoSize=true,WrapContents=true};
 static bool TradeSelectionAllowed(bool wasSelected,bool requested,int sea,CityLimit limit){
  return requested&&(wasSelected||sea!=1||limit==null||limit.sea!="blocked");
 }
 string[] FilterTradeSelection(City city,string[] requested,Func<string,CityLimit> read){
  return project.slots.Where(s=>TradeSelectionAllowed(city.trade_players==null||city.trade_players.Contains(s.id),
   requested.Contains(s.id),city.sea,city.sea==1?read(s.id):null)).Select(s=>s.id).ToArray();
 }
 int ApplyNeutralBatchData(int[] names,bool? enabled,string[] players,Func<string,CityLimit> read){
  int rejected=0;
  foreach(var city in project.empire.cities.Where(c=>c.role=="npc"&&names.Contains(c.name_id))){
   if(players!=null){var allowed=FilterTradeSelection(city,players,read);rejected+=players.Except(allowed).Count();city.trade_players=allowed;}
   if(enabled.HasValue)city.enabled=enabled.Value;
  }
  return rejected;
 }
 void RefreshAccess(City city){
  foreach(Control control in accessBar.Controls.Cast<Control>().ToArray()){accessBar.Controls.Remove(control);control.Dispose();}
  accessBar.Visible=city.role=="npc";if(city.role!="npc")return;
  var readLimits=city.sea==1?SeaReader():(Func<string,CityLimit>)(id=>null);
  accessBar.Controls.Add(new Label{Text="교역 허용",AutoSize=true,Padding=new Padding(0,6,0,0)});
  for(int i=0;i<project.slots.Length;i++){
   string id=project.slots[i].id;
   var check=new CheckBox{Text="P"+(i+1),AutoSize=true,Checked=city.trade_players==null||city.trade_players.Contains(id)};
   check.Tag=id;
   check.CheckedChanged+=(s,e)=>{
    if(loading)return;
    var currentLimits=city.sea==1?SeaReader():(Func<string,CityLimit>)(key=>null);
    city.trade_players=FilterTradeSelection(city,accessBar.Controls.OfType<CheckBox>().Where(c=>c.Checked).Select(c=>(string)c.Tag).ToArray(),currentLimits);
    bool previous=loading;loading=true;
    try{check.Checked=city.trade_players.Contains(id);check.Enabled=TradeSelectionAllowed(check.Checked,true,city.sea,currentLimits(id));}
    finally{loading=previous;}
    map.Invalidate();Changed();
   };
   accessBar.Controls.Add(check);var lim=readLimits(id);bool noSea=lim!=null&&lim.sea=="blocked";
   check.Enabled=TradeSelectionAllowed(check.Checked,true,city.sea,lim);
   if(noSea){check.Text+=" (해상 불가)";check.ForeColor=Color.Firebrick;}
   tradeTip.SetToolTip(check,CityName(project.slots[i].name_id)+(noSea?"와는 해상 교역이 이루어지지 않습니다: "+lim.reason:seaLimitsError!=null?" · "+seaLimitsError:"와 교역 허용"));
  }
 }
 void SetNeutralBatch(int[] names,bool? enabled,string[] players){StoreCity();int rejected=ApplyNeutralBatchData(names,enabled,players,players==null?(Func<string,CityLimit>)(id=>null):SeaReader());RefreshCityList();if(selected>=0)ShowCity(selected);map.Invalidate();Changed();if(rejected>0)status.Text="해상 교역이 불가능한 상대 "+rejected+"건은 새로 허용하지 않았습니다.";}
 void BulkNeutrals(){
  StoreCity();using(var dialog=new Form{Text="중립도시 일괄 설정",ClientSize=new Size(650,640),BackColor=Paper,Font=Font,StartPosition=FormStartPosition.CenterParent,MinimizeBox=false,MaximizeBox=false}){
   var layout=new TableLayoutPanel{Dock=DockStyle.Fill,Padding=new Padding(14),RowCount=6,ColumnCount=1};foreach(int h in new[]{40,40})layout.RowStyles.Add(new RowStyle(SizeType.Absolute,h));layout.RowStyles.Add(new RowStyle(SizeType.Percent,100));foreach(int h in new[]{40,60,45})layout.RowStyles.Add(new RowStyle(SizeType.Absolute,h));dialog.Controls.Add(layout);
   var search=new TextBox{Dock=DockStyle.Fill};layout.Controls.Add(search,0,0);var list=new CheckedListBox{Dock=DockStyle.Fill,CheckOnClick=true,IntegralHeight=false,BackColor=Paper};layout.Controls.Add(list,0,2);var all=project.empire.cities.Where(c=>c.role=="npc").ToArray();var chosen=new System.Collections.Generic.HashSet<int>();bool filtering=false;
   Action refresh=()=>{filtering=true;list.Items.Clear();foreach(var c in all.Where(c=>CityName(c.name_id).IndexOf(search.Text,StringComparison.CurrentCultureIgnoreCase)>=0))list.Items.Add(new NameChoice{name_id=c.name_id,name=CityName(c.name_id)+(c.enabled?" · 켜짐":" · 꺼짐")},chosen.Contains(c.name_id));filtering=false;};search.TextChanged+=(s,e)=>refresh();list.ItemCheck+=(s,e)=>{if(filtering)return;int id=((NameChoice)list.Items[e.Index]).name_id;if(e.NewValue==CheckState.Checked)chosen.Add(id);else chosen.Remove(id);};
   var selection=new FlowLayoutPanel{Dock=DockStyle.Fill};selection.Controls.Add(Button("검색 결과 모두 선택",()=>{foreach(NameChoice n in list.Items)chosen.Add(n.name_id);refresh();},190));selection.Controls.Add(Button("선택 해제",()=>{chosen.Clear();refresh();},120));layout.Controls.Add(selection,0,1);
   var state=new ComboBox{DropDownStyle=ComboBoxStyle.DropDownList,Width=240};state.Items.AddRange(new object[]{"켜짐·꺼짐 유지","선택한 중립도시 켜기","선택한 중립도시 끄기"});state.SelectedIndex=0;layout.Controls.Add(state,0,3);
   var access=new FlowLayoutPanel{Dock=DockStyle.Fill};var change=new CheckBox{Text="교역 허용도 변경",AutoSize=true};access.Controls.Add(change);for(int i=0;i<project.slots.Length;i++){var check=new CheckBox{Text="P"+(i+1)+" "+CityName(project.slots[i].name_id),Tag=project.slots[i].id,Checked=true,AutoSize=true};access.Controls.Add(check);}layout.Controls.Add(access,0,4);
   var actions=new FlowLayoutPanel{Dock=DockStyle.Fill};actions.Controls.Add(Button("선택한 도시에 적용",()=>{if(chosen.Count==0){LangBox.Show(dialog,"적용할 도시를 먼저 체크하세요.");return;}var ids=change.Checked?access.Controls.OfType<CheckBox>().Where(c=>c!=change&&c.Checked).Select(c=>(string)c.Tag).ToArray():null;SetNeutralBatch(chosen.ToArray(),state.SelectedIndex==0?(bool?)null:state.SelectedIndex==1,ids);dialog.DialogResult=DialogResult.OK;},210));actions.Controls.Add(Button("취소",()=>dialog.Close(),120));layout.Controls.Add(actions,0,5);refresh();Lang.Shown(dialog).ShowDialog(this);
  }
 }
}
