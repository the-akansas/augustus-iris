using System;
using System.IO;
using System.Linq;
using System.Drawing;
using System.Collections.Generic;
using System.Windows.Forms;
public class CityInvasion {public int month,amount,point,target;public int? enemy;public InvasionRepeat repeat;}   // enemy: this attack's people, null = the city's; repeat: null = once
public class InvasionRepeat {public int every,times;}   // the attack comes again every `every` months, `times` attacks in all (user 2026-11-15; Augustus/city_invasions.py)
partial class ScenarioCreator {
 ComboBox invasionCity=new ComboBox{Width=210,DropDownStyle=ComboBoxStyle.DropDownList},invasionPoint=new ComboBox{Width=180,DropDownStyle=ComboBoxStyle.DropDownList},invasionTarget=new ComboBox{Width=190,DropDownStyle=ComboBoxStyle.DropDownList};
 NumericUpDown invasionEvery=new NumericUpDown{Minimum=1,Maximum=240,Value=12,Width=70},invasionTimes=new NumericUpDown{Minimum=2,Maximum=24,Value=3,Width=60};CheckBox invasionRepeat=new CheckBox{Text="반복",AutoSize=true,Padding=new Padding(0,4,0,0)};
 NumericUpDown invasionMonth=new NumericUpDown{Minimum=1,Maximum=1200,Value=12,Width=100},invasionAmount=new NumericUpDown{Minimum=5,Maximum=150,Value=40,Width=100};
 ListBox invasionList=new ListBox{Dock=DockStyle.Fill,IntegralHeight=false,HorizontalScrollbar=true,BackColor=Paper,ForeColor=Dark};
 // The 20 enemy peoples of the original game (its own names, text group 37). Peoples whose soldiers share one picture
 // file look the same and fight alike (scenario/invasion.c), so they are offered as one choice (user 2026-11-15); the
 // first of a group is what the file keeps. Each attack names its people. The game shows one picture file at a time:
 // attacks with different pictures may not come in the same month, and when other pictures arrive the soldiers of the
 // earlier people still in the city leave the map (src/scenario/invasion.c switch_enemy_people). An older file's
 // city-wide people (Slot.invasion_enemy) still counts for its attacks that name none; it is no longer edited here.
 static readonly string[] EnemyPeoples={"야만인","에트루리아인","삼늄인","카르타고인","마케도니아인","그리스인","이집트인","페르가뭄인","셀루시드인","픽트족","켈트족","브리튼인","갈리아인","헬베티아인","고트족","서고트족","훈족","이베리아족","누미디아인","유대인"};
 static readonly int[][] PeopleGroups={new[]{0},new[]{1,2},new[]{3},new[]{4,5},new[]{6},new[]{7},new[]{8,17,19},new[]{9,10,11},new[]{12,13},new[]{14,15,16},new[]{18}};
 static readonly int[] PictureFile={0,1,1,2,3,3,4,5,6,7,7,7,8,8,0,0,0,6,9,6};   // as scenario/invasion.c ENEMY_PICTURE_FILE
 static int GroupOf(int people){for(int g=0;g<PeopleGroups.Length;g++)if(Array.IndexOf(PeopleGroups[g],people)>=0)return g;return 0;}
 static string GroupText(int g){return string.Join(", ",PeopleGroups[g].Select(i=>Lang.T(EnemyPeoples[i])));}
 ComboBox invasionPeople=new ComboBox{Width=300,DropDownStyle=ComboBoxStyle.DropDownList};
 PictureBox enemyPicture=new PictureBox{Width=176,Height=88,SizeMode=PictureBoxSizeMode.CenterImage,BackColor=Color.FromArgb(214,199,163),Margin=new Padding(3,6,3,3)};Dictionary<int,Image> enemyPictures;Label enemyPictureNote=new Label{AutoSize=true,MaximumSize=new Size(300,0),ForeColor=Dark};
 Label invasionHeading=new Label{AutoSize=true,Font=new Font("Malgun Gothic",13,FontStyle.Bold),Padding=new Padding(0,6,0,0)},invasionCount=new Label{AutoSize=true,Padding=new Padding(14,12,0,0)};
 void LoadEnemyPictures(){if(enemyPictures!=null)return;enemyPictures=new Dictionary<int,Image>();try{var raw=Json.Deserialize<Dictionary<string,object>>(RunPython("creator_enemy_images.py",""));var map=raw["pictures"] as Dictionary<string,object>;if(map!=null)foreach(var kv in map){using(var stream=new MemoryStream(File.ReadAllBytes(Convert.ToString(kv.Value))))enemyPictures[int.Parse(kv.Key)]=new Bitmap(Image.FromStream(stream));}}catch{}}
 CreatorTerrainView invasionMap=new CreatorTerrainView{ReadOnly=true,ShowProtected=false,Cursor=Cursors.Default};Label invasionMapNote=new Label{AutoSize=true,ForeColor=Dark,Padding=new Padding(0,4,0,0)};
 // The map of the chosen city with its points; the point chosen in the form is ringed ("자동 선택": the first one, as the game does).
 void ShowInvasionMap(){var slot=InvasionSlot();if(slot==null){invasionMap.Bind(null,new TerrainEdit[0]);return;}
  try{invasionMap.Bind(CurrentTerrainOf(slot),new TerrainEdit[0]);}catch(Exception error){invasionMap.Bind(null,new TerrainEdit[0]);invasionMapNote.Text=Lang.T("지도를 읽지 못했습니다.")+" "+error.Message;return;}
  ShowInvasionPoint();}
 int FirstInvasionPoint(){var d=invasionMap.Data;if(d==null||d.invasion_points==null)return -1;for(int i=0;i<d.invasion_points.Length;i++){var p=d.invasion_points[i];if(p!=null&&p.Length==2&&p[0]>=0&&p[1]>=0)return i;}return -1;}
 void ShowInvasionPoint(){if(invasionMap.Data==null)return;int n=invasionMap.InvasionPointCount,chosen=invasionPoint.SelectedIndex;
  invasionMap.HighlightInvasion=chosen<=0?FirstInvasionPoint():chosen-1;invasionMap.Invalidate();
  string text=n==0?Lang.T("이 지도에는 적군 진입점이 없습니다. 자동 선택이면 출구에서 들어옵니다."):Lang.T("빨간 번호가 적군 진입점입니다")+" ("+n+Lang.T("곳")+"). "+(chosen<=0?Lang.T("자동 선택은 가장 앞 번호를 씁니다."):"");
  if(chosen>0&&(invasionMap.Data.invasion_points==null||chosen>invasionMap.Data.invasion_points.Length||invasionMap.Data.invasion_points[chosen-1][0]<0))text+=Lang.T(" 고른 번호는 이 지도에 없습니다. 게임 적용 검사에서 막힙니다.");
  invasionMapNote.Text=text;}
 // The same attacks on every other city (user 2026-11-15). Their own lists are replaced. A numbered entry point that
 // another map lacks is refused by the engine check (게임 적용 검사), so "자동 선택" travels best.
 void CopyInvasionsToAll(){
  var from=InvasionSlot();if(from==null)return;if(project.slots.Length<2)throw new Exception("다른 플레이 도시가 없습니다.");
  if(LangBox.Show(this,"다른 도시의 침략을 모두 지우고 "+CityName(from.name_id)+"의 침략과 똑같이 바꿀까요?\n번호로 고른 진입점은 다른 지도에 없을 수 있으니 게임 적용 검사로 확인하세요.","침략 복사",MessageBoxButtons.YesNo)!=DialogResult.Yes)return;
  string body=Json.Serialize(from.invasions??new List<CityInvasion>());
  foreach(var slot in project.slots){if(slot==from)continue;var copy=Json.Deserialize<List<CityInvasion>>(body);slot.invasions=copy.Count==0?null:copy;}
  Changed();status.Text=Lang.T("침략을 다른 도시에 복사했습니다.");
 }
 static int? InvasionPeople(Slot slot,CityInvasion e){return e.enemy??slot.invasion_enemy;}
 string PeopleText(Slot slot,CityInvasion e){int? p=InvasionPeople(slot,e);return p==null?Lang.T("지도의 원래 적군"):GroupText(GroupOf(p.Value));}
 int? ChosenPeople(){int i=invasionPeople.SelectedIndex;return i<=0?(int?)null:PeopleGroups[i-1][0];}
 void ShowEnemyPicture(){int? people=ChosenPeople();Image picture=null;if(people!=null&&enemyPictures!=null)enemyPictures.TryGetValue(people.Value,out picture);enemyPicture.Image=picture;
  enemyPictureNote.Text=people==null?Lang.T("지도마다 달라 미리 볼 수 없습니다."):picture==null?Lang.T("시저 3 폴더에서 그림을 읽지 못했습니다."):"";}
 // Two attacks in one month must look alike: the same picture file (an attack that names none: the file's city people).
 static IEnumerable<int> AttackMonths(CityInvasion e){if(e.repeat==null){yield return e.month;yield break;}for(int i=0;i<e.repeat.times;i++)yield return e.month+i*e.repeat.every;}
 static void RequireOnePeoplePerMonth(Slot slot,IEnumerable<CityInvasion> rows){var seen=new Dictionary<int,int>();foreach(var e in rows)foreach(int month in AttackMonths(e)){int? p=InvasionPeople(slot,e);int file=p==null?-1:PictureFile[p.Value];int had;if(seen.TryGetValue(month,out had)&&had!=file)throw new Exception("시작 후 "+month+"개월에 그림이 다른 적군이 함께 들어오게 됩니다. 한 도시에는 한 가지 적군 그림만 보이므로, 같은 달의 침략은 같은 적군으로 정하세요.");seen[month]=file;}}
 readonly string[] attackTargets={"식량 시설","자금 관련 시설","고급 건물","방어 병력","무작위"};
 Slot InvasionSlot(){return project!=null&&invasionCity.SelectedIndex>=0&&invasionCity.SelectedIndex<project.slots.Length?project.slots[invasionCity.SelectedIndex]:null;}
 void RefreshInvasionList(){
  int keep=invasionList.SelectedIndex;invasionList.Items.Clear();var slot=InvasionSlot();
  invasionHeading.Text=slot==null?"":CityName(slot.name_id)+Lang.T("에 오는 침략");
  int n=slot==null||slot.invasions==null?0:slot.invasions.Count;invasionCount.Text=n+" / 16"+Lang.T("회");
  if(slot!=null&&slot.invasions!=null)foreach(var e in slot.invasions)invasionList.Items.Add("시작 후 "+e.month+"개월"+(e.repeat==null?"":" "+Lang.T("부터")+" "+e.repeat.every+Lang.T("개월마다")+" "+e.repeat.times+Lang.T("회"))+"  /  "+PeopleText(slot,e)+"  /  "+e.amount+"명  /  "+(e.point==0?"자동 진입점":"진입점 "+e.point)+"  /  "+attackTargets[e.target]);
  if(keep>=0&&keep<invasionList.Items.Count)invasionList.SelectedIndex=keep;
 }
 void RefreshInvasionCities(){int old=invasionCity.SelectedIndex;invasionCity.Items.Clear();if(project==null)return;foreach(var slot in project.slots)invasionCity.Items.Add(CityName(slot.name_id));if(project.slots.Length>0)invasionCity.SelectedIndex=Math.Min(Math.Max(old,0),project.slots.Length-1);else RefreshInvasionList();ShowEnemyPicture();}
 CityInvasion InvasionFromForm(){return new CityInvasion{month=(int)invasionMonth.Value,amount=(int)invasionAmount.Value,point=invasionPoint.SelectedIndex,target=invasionTarget.SelectedIndex,enemy=ChosenPeople(),repeat=invasionRepeat.Checked?new InvasionRepeat{every=(int)invasionEvery.Value,times=(int)invasionTimes.Value}:null};}
 // The attacks of a city are kept in month order (the list reads like a timeline).
 static void SortInvasions(Slot slot){slot.invasions=slot.invasions.OrderBy(e=>e.month).ToList();}
 // A click on an attack puts its values in the form: change them and press "선택한 침략 바꾸기".
 void InvasionToForm(){
  var slot=InvasionSlot();int i=invasionList.SelectedIndex;if(slot==null||slot.invasions==null||i<0||i>=slot.invasions.Count)return;var e=slot.invasions[i];
  invasionMonth.Value=Math.Max(invasionMonth.Minimum,Math.Min(invasionMonth.Maximum,e.month));invasionAmount.Value=Math.Max(invasionAmount.Minimum,Math.Min(invasionAmount.Maximum,e.amount));
  invasionPoint.SelectedIndex=e.point;invasionTarget.SelectedIndex=e.target;invasionRepeat.Checked=e.repeat!=null;if(e.repeat!=null){invasionEvery.Value=Math.Max(invasionEvery.Minimum,Math.Min(invasionEvery.Maximum,e.repeat.every));invasionTimes.Value=Math.Max(invasionTimes.Minimum,Math.Min(invasionTimes.Maximum,e.repeat.times));}int? p=InvasionPeople(slot,e);invasionPeople.SelectedIndex=p==null?0:GroupOf(p.Value)+1;ShowEnemyPicture();
 }
 void BuildInvasionsTab(){
  var tab=new TabPage("7  침략 설정"){BackColor=Paper};tabs.TabPages.Add(tab);
  var layout=new TableLayoutPanel{Dock=DockStyle.Fill,Padding=new Padding(16,8,16,8),ColumnCount=1,RowCount=3};tab.Controls.Add(layout);
  layout.RowStyles.Add(new RowStyle(SizeType.Absolute,44));layout.RowStyles.Add(new RowStyle(SizeType.Absolute,46));layout.RowStyles.Add(new RowStyle(SizeType.Percent,100));
  // 1. the city (the slot chosen at the top of the page): its name is the heading
  var head=new FlowLayoutPanel{Dock=DockStyle.Fill,WrapContents=false};invasionCity.Visible=false;head.Controls.Add(invasionCity);head.Controls.Add(invasionHeading);head.Controls.Add(invasionCount);layout.Controls.Add(head,0,0);
  // 2. two lines of help; they scroll on their own when they do not fit (a longer language, a small window)
  {var helpBox=new Panel{Dock=DockStyle.Fill,AutoScroll=true};var help=new Label{AutoSize=true,ForeColor=Dark,Text="적군이 이 도시를 공격합니다. 설정마다 한 번이며(반복을 켜면 정한 간격으로 다시 옵니다) 병력은 난이도 보정을 받고 최대 150명입니다. 진입점 1~8은 정식 지형 편집기의 번호입니다.\n그림이 다른 적군은 같은 달에 넣을 수 없고, 그림이 다른 적군이 들어오면 남아 있던 이전 적군은 지도에서 사라집니다. 새 시나리오로 시작해야 적용됩니다."};helpBox.Controls.Add(help);helpBox.Resize+=(s,e)=>help.MaximumSize=new Size(Math.Max(100,helpBox.ClientSize.Width-24),0);layout.Controls.Add(helpBox,0,1);}
  // 3. left: the city's attacks in month order; right: one attack's values
  var body=new TableLayoutPanel{Dock=DockStyle.Fill,ColumnCount=2,RowCount=1,Margin=new Padding(0)};body.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));body.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,470));layout.Controls.Add(body,0,2);
  var listBox=new GroupBox{Text="침략 목록 (시작 후 개월 순)",Dock=DockStyle.Fill,ForeColor=Dark,Padding=new Padding(8)};/* the list fills its box; deleting moved to the right with adding and changing (user 2026-11-15) */var listLayout=new TableLayoutPanel{Dock=DockStyle.Fill,ColumnCount=1,RowCount=1};listLayout.RowStyles.Add(new RowStyle(SizeType.Percent,100));
  listLayout.Controls.Add(invasionList,0,0);var deleteInvasion=Button("선택한 침략 삭제",()=>{var slot=InvasionSlot();int i=invasionList.SelectedIndex;if(slot==null||slot.invasions==null||i<0)throw new Exception("왼쪽 목록에서 지울 침략을 고르세요.");slot.invasions.RemoveAt(i);RefreshInvasionList();Changed();},150);
  {var copy=new FlowLayoutPanel{AutoSize=true,Dock=DockStyle.Fill};copy.Controls.Add(Button("이 침략들을 다른 도시에도",CopyInvasionsToAll,210));listLayout.RowCount=2;listLayout.RowStyles.Add(new RowStyle(SizeType.AutoSize));listLayout.Controls.Add(copy,0,1);}
  listBox.Controls.Add(listLayout);body.Controls.Add(listBox,0,0);
  // the city's map with its entrance, exit and numbered entry points (user 2026-11-15), under the list
  {var mapBox=new GroupBox{Text="진입 위치 지도",Dock=DockStyle.Fill,ForeColor=Dark,Padding=new Padding(6)};var mapLayout=new TableLayoutPanel{Dock=DockStyle.Fill,ColumnCount=1,RowCount=2};mapLayout.RowStyles.Add(new RowStyle(SizeType.Percent,100));mapLayout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
   mapLayout.Controls.Add(invasionMap,0,0);mapLayout.Controls.Add(invasionMapNote,0,1);mapBox.Controls.Add(mapLayout);
   var left=new TableLayoutPanel{Dock=DockStyle.Fill,ColumnCount=1,RowCount=2,Margin=new Padding(0)};left.RowStyles.Add(new RowStyle(SizeType.Percent,46));left.RowStyles.Add(new RowStyle(SizeType.Percent,54));
   body.Controls.Remove(listBox);left.Controls.Add(listBox,0,0);left.Controls.Add(mapBox,0,1);body.Controls.Add(left,0,0);}
  invasionPoint.SelectedIndexChanged+=(s,e)=>ShowInvasionPoint();
  var formBox=new GroupBox{Text="침략 내용",Dock=DockStyle.Fill,ForeColor=Dark,Padding=new Padding(10)};var form=new TableLayoutPanel{Dock=DockStyle.Fill,ColumnCount=2,AutoScroll=true};form.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,120));form.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));
  Action<string,Control> row=(label,control)=>{int r=form.RowCount++;form.RowStyles.Add(new RowStyle(SizeType.AutoSize));form.Controls.Add(new Label{Text=label,AutoSize=true,Padding=new Padding(0,7,0,0)},0,r);form.Controls.Add(control,1,r);};
  invasionPeople.Items.Add("지도의 원래 적군");for(int g=0;g<PeopleGroups.Length;g++)invasionPeople.Items.Add(GroupText(g));invasionPeople.SelectedIndex=0;invasionPeople.SelectedIndexChanged+=(s,e)=>ShowEnemyPicture();
  invasionPoint.Items.Add("자동 선택");for(int i=1;i<=8;i++)invasionPoint.Items.Add("지도 진입점 "+i);invasionPoint.SelectedIndex=0;invasionTarget.Items.AddRange(attackTargets);invasionTarget.SelectedIndex=4;
  // the enemy picture above its list: an open list no longer covers it (user 2026-11-17)
  {var pictureBox=new FlowLayoutPanel{AutoSize=true,FlowDirection=FlowDirection.TopDown,WrapContents=false};pictureBox.Controls.Add(enemyPicture);pictureBox.Controls.Add(enemyPictureNote);row("적군",pictureBox);}row("",invasionPeople);row("시작 후 개월",invasionMonth);{var again=new FlowLayoutPanel{AutoSize=true,WrapContents=false};again.Controls.Add(invasionRepeat);again.Controls.Add(invasionEvery);again.Controls.Add(new Label{Text="개월마다, 모두",AutoSize=true,Padding=new Padding(0,6,0,0)});again.Controls.Add(invasionTimes);again.Controls.Add(new Label{Text="회",AutoSize=true,Padding=new Padding(0,6,0,0)});Action sync=()=>{invasionEvery.Enabled=invasionTimes.Enabled=invasionRepeat.Checked;};invasionRepeat.CheckedChanged+=(s,e)=>sync();sync();row("반복 (선택)",again);}row("기본 병력 (명)",invasionAmount);row("진입 위치",invasionPoint);row("우선 공격 목표",invasionTarget);
  var actions=new FlowLayoutPanel{AutoSize=true,Margin=new Padding(0,10,0,0)};
  actions.Controls.Add(Button("침략 추가",()=>{var slot=InvasionSlot();if(slot==null)throw new Exception("플레이 자리를 선택하세요.");if(slot.invasions==null)slot.invasions=new List<CityInvasion>();if(slot.invasions.Count>=16)throw new Exception("도시마다 최대 16회입니다.");var added=InvasionFromForm();RequireOnePeoplePerMonth(slot,slot.invasions.Concat(new[]{added}));slot.invasions.Add(added);SortInvasions(slot);RefreshInvasionList();invasionList.SelectedIndex=slot.invasions.IndexOf(added);Changed();},100));
  actions.Controls.Add(Button("선택한 침략 바꾸기",()=>{var slot=InvasionSlot();int i=invasionList.SelectedIndex;if(slot==null||slot.invasions==null||i<0)throw new Exception("왼쪽 목록에서 바꿀 침략을 고르세요.");var changed=InvasionFromForm();var rows=slot.invasions.ToList();rows[i]=changed;RequireOnePeoplePerMonth(slot,rows);slot.invasions=rows;SortInvasions(slot);RefreshInvasionList();invasionList.SelectedIndex=slot.invasions.IndexOf(changed);Changed();},150));
  actions.Controls.Add(deleteInvasion);actions.WrapContents=false;   // add, change, delete on one line under the form
  {int r=form.RowCount++;form.RowStyles.Add(new RowStyle(SizeType.AutoSize));form.Controls.Add(actions,0,r);form.SetColumnSpan(actions,2);}
  {int r=form.RowCount++;form.RowStyles.Add(new RowStyle(SizeType.AutoSize));var hint=new Label{AutoSize=true,MaximumSize=new Size(420,0),ForeColor=Dark,Padding=new Padding(0,6,0,0),Text="저장 후 '게임 적용 검사'로 진입 위치를 확인하세요."};form.Controls.Add(hint,0,r);form.SetColumnSpan(hint,2);}
  formBox.Controls.Add(form);body.Controls.Add(formBox,1,0);
  invasionList.SelectedIndexChanged+=(s,e)=>InvasionToForm();
  invasionCity.SelectedIndexChanged+=(s,e)=>{invasionList.ClearSelected();RefreshInvasionList();ShowEnemyPicture();ShowInvasionMap();};
  tab.Enter+=(s,e)=>{LoadEnemyPictures();RefreshInvasionCities();ShowInvasionMap();};
 }
 static int InvasionsProbe(){var a=new Slot{invasions=new List<CityInvasion>{new CityInvasion{month=12,amount=32,point=2,target=3}}};var b=Json.Deserialize<Slot>(Json.Serialize(a));if(b.invasions.Count!=1||b.invasions[0].point!=2||b.invasions[0].target!=3)throw new Exception("Invasion roundtrip failed");if(Json.Deserialize<Slot>("{\"id\":\"old\"}").invasions!=null)throw new Exception("Legacy invasion changed");var en=Json.Deserialize<Slot>(Json.Serialize(new Slot{invasion_enemy=7}));if(en.invasion_enemy!=7||Json.Deserialize<Slot>("{\"id\":\"old\"}").invasion_enemy!=null)throw new Exception("Invasion enemy roundtrip failed");var rp=Json.Deserialize<Slot>(Json.Serialize(new Slot{invasions=new List<CityInvasion>{new CityInvasion{month=6,amount=20,repeat=new InvasionRepeat{every=12,times=4}}}}));if(rp.invasions[0].repeat==null||rp.invasions[0].repeat.every!=12||rp.invasions[0].repeat.times!=4||AttackMonths(rp.invasions[0]).Last()!=42)throw new Exception("Invasion repeat roundtrip failed");bool clash=false;try{RequireOnePeoplePerMonth(new Slot(),new[]{new CityInvasion{month=6,repeat=new InvasionRepeat{every=12,times=4},enemy=0},new CityInvasion{month=30,enemy=3}});}catch(Exception){clash=true;}if(!clash)throw new Exception("Repeated month clash not found");File.WriteAllText(Path.Combine(Root,"invasions-editor-results.json"),"{\"passed\":true,\"gui_created\":false}");return 0;}
}
