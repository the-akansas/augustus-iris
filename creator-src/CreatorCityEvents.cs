using System;
using System.IO;
using System.Linq;
using System.Drawing;
using System.Collections.Generic;
using System.Windows.Forms;
// kind: grant favor request building god goods health migration revolt message (Augustus/city_events.py KINDS).
// text: only for "message"; left out of the file otherwise (SerializeProject).
public class CityEvent {public string kind;public int month,amount,resource,deadline;public string text;public EventWhen when;public EventRepeat repeat;}
// Optional (2026-11-15): wait until the city reaches a value; happen several times, `every` months apart.
public class EventWhen {public string stat;public int at_least;}
public class EventRepeat {public int every,times;}
partial class ScenarioCreator {
 // The kinds in the order of the list, with what each one asks for (user 2026-11-15: all of the proposed ones).
 static readonly string[] EventKinds={"grant","favor","request","building","god","goods","health","migration","revolt","message"};
 static readonly string[] EventKindNames={"도시 지원금","황제 지지도 변화","황제 물품 요청","건물 허용·금지","신의 축복·저주","창고 물품 지급·몰수","도시 건강 변화","이민 증가·감소","검투사 반란","도시 소식 메시지"};
 static readonly string[] EventStats={"population","prosperity","culture","health","money","favor"};
 static readonly string[] EventStatNames={"인구","번영","문화","건강","자금","황제 지지도"};
 ComboBox eventWhen=new ComboBox{Width=120,DropDownStyle=ComboBoxStyle.DropDownList};NumericUpDown eventWhenValue=new NumericUpDown{Minimum=1,Maximum=1000000000,Value=3000,Width=100,ThousandsSeparator=true};
 NumericUpDown eventEvery=new NumericUpDown{Minimum=1,Maximum=240,Value=12,Width=70},eventTimes=new NumericUpDown{Minimum=1,Maximum=24,Value=1,Width=60};
 string WhenText(CityEvent e){if(e.when==null)return "";int i=Array.IndexOf(EventStats,e.when.stat);return " / "+(i<0?e.when.stat:EventStatNames[i])+" "+e.when.at_least.ToString("N0")+" 이상일 때";}
 string RepeatText(CityEvent e){return e.repeat==null?"":e.when!=null?" / 처음 일어난 뒤 "+e.repeat.every+"개월마다, 모두 "+e.repeat.times+"번":" / "+e.repeat.every+"개월마다 "+e.repeat.times+"번";}   // with a condition the game repeats it after each time (2026-11-15)
 static readonly string[] GodNames={"케레스","넵튠","머큐리","마르스","비너스"};
 static readonly string[] GodActs={"축복","작은 저주","큰 저주"};
 static readonly string[] EventHelp={
  "도시 자금에 지원금이 들어옵니다.",
  "황제 지지도가 바뀝니다(0~100). 통치자 탭의 '원본 규칙'이 필요합니다.",
  "황제가 물품을 요청합니다. 기본 규칙(정시 도착 지지도 +8, 기한 초과 -3, 무시 -5, 유예 2년). 통치자 탭의 '원본 규칙'이 필요합니다.",
  "그 달부터 이 건물을 새로 지을 수 있거나(허용) 없게(금지) 됩니다. 이미 지은 건물은 그대로 남습니다. 게임 안 메시지로 알려 줍니다.",
  "게임의 신 효과가 그대로 일어납니다. 예: 넵튠의 저주는 배를 가라앉히고, 마르스의 저주는 적을 부르거나 군단을 해칩니다. 게임의 원래 메시지가 뜹니다.",
  "양수는 보급(창고·곡물창고에 넣기), 음수는 징발(가져가기)입니다. 자리가 없거나 물품이 없으면 되는 만큼만 합니다. 다른 플레이어와의 교역과는 따로입니다.",
  "도시 건강이 바뀝니다(0~100). 메시지로 알려 줍니다.",
  "정한 개월 동안 이주민이 평소의 몇 %만큼 들어옵니다(100%가 평소). 기간이 끝나면 평소로 돌아옵니다.",
  "검투사 반란이 일어납니다. 게임의 원래 반란 규칙과 메시지를 따릅니다.",
  "작가가 쓴 글이 이 도시의 메시지 창에 뜹니다. 제목을 비우면 '도시 소식'이 제목이 됩니다. 아래 미리보기가 게임에서 보이는 모양입니다."};
 ComboBox eventCity=new ComboBox{Width=200,DropDownStyle=ComboBoxStyle.DropDownList},eventKind=new ComboBox{Width=230,DropDownStyle=ComboBoxStyle.DropDownList},eventResource=new ComboBox{Width=230,DropDownStyle=ComboBoxStyle.DropDownList},eventChoice=new ComboBox{Width=230,DropDownStyle=ComboBoxStyle.DropDownList};
 NumericUpDown eventMonth=new NumericUpDown{Minimum=1,Maximum=1200,Value=6,Width=100},eventAmount=new NumericUpDown{Minimum=1,Maximum=1000000,Value=1000,Width=130,ThousandsSeparator=true},eventDeadline=new NumericUpDown{Minimum=1,Maximum=20,Value=2,Width=100};
 TextBox eventText=new TextBox{Multiline=true,Width=300,Height=80,ScrollBars=ScrollBars.Vertical,MaxLength=260},eventTitle=new TextBox{Width=300,MaxLength=40};
 // 도시 소식: a title box, a body box and a small copy of the game's message window showing both (user 2026-11-15:
 // "first line is the title" was confusing). The file keeps "title\nbody" (Augustus/city_events.py message_text).
 Label eventTitleLabel=new Label{AutoSize=true,Text="제목",Padding=new Padding(0,7,0,0)},eventPreviewLabel=new Label{AutoSize=true,Text="미리보기",Padding=new Padding(0,7,0,0)};
 Panel eventPreview=new Panel{Width=300,Height=120,BackColor=Color.FromArgb(232,214,170),BorderStyle=BorderStyle.FixedSingle};
 Label previewTitle=new Label{Dock=DockStyle.Top,Height=26,TextAlign=ContentAlignment.MiddleCenter,Font=new Font("Malgun Gothic",11,FontStyle.Bold),ForeColor=Color.FromArgb(40,35,29)},
  previewSub=new Label{Dock=DockStyle.Top,Height=18,TextAlign=ContentAlignment.MiddleCenter,Font=new Font("Malgun Gothic",8),ForeColor=Color.FromArgb(110,90,60),Text="시나리오 도시 이벤트"},
  previewBody=new Label{Dock=DockStyle.Fill,Padding=new Padding(10,6,10,6),Font=new Font("Malgun Gothic",9),ForeColor=Color.FromArgb(40,35,29)};
 void ShowEventPreview(){string t=eventTitle.Text.Trim();previewTitle.Text=t.Length>0?t:Lang.T("도시 소식");previewBody.Text=eventText.Text.Trim().Length>0?eventText.Text.Trim():Lang.T("(여기에 쓴 내용이 이렇게 보입니다)");}
 ListBox eventList=new ListBox{Dock=DockStyle.Fill,BackColor=Paper,ForeColor=Dark,HorizontalScrollbar=true,IntegralHeight=false};
 Label eventAmountLabel=new Label{AutoSize=true,Text="지원금",Padding=new Padding(0,7,0,0)},eventResourceLabel=new Label{AutoSize=true,Padding=new Padding(0,7,0,0)},eventChoiceLabel=new Label{AutoSize=true,Padding=new Padding(0,7,0,0)},eventDeadlineLabel=new Label{AutoSize=true,Padding=new Padding(0,7,0,0)},eventTextLabel=new Label{AutoSize=true,Text="내용",Padding=new Padding(0,7,0,0)};
 Label eventHelp=new Label{AutoSize=true,MaximumSize=new Size(400,0),ForeColor=Dark,Padding=new Padding(0,8,0,0)};
 List<DeliveryResource> eventGoods=new List<DeliveryResource>();
 Slot EventSlot(){return project!=null&&eventCity.SelectedIndex>=0&&eventCity.SelectedIndex<project.slots.Length?project.slots[eventCity.SelectedIndex]:null;}
 string GoodName(int id){var r=eventGoods.FirstOrDefault(x=>x.resource==id);return r==null?id.ToString():r.name;}
 string BuildingName(int id){var b=catalog==null?null:catalog.FirstOrDefault(x=>x.id==id);return b==null?"#"+id:b.name;}
 string EventText(CityEvent e){
  string what;
  switch(e.kind){
   case "grant":what="지원금 "+e.amount.ToString("N0")+" 데나리";break;
   case "favor":what="황제 지지도 "+e.amount.ToString("+0;-0");break;
   case "request":what="황제 요청: "+GoodName(e.resource)+" "+e.amount+"포대 / 기한 "+e.deadline+"년";break;
   case "building":what=BuildingName(e.resource)+(e.amount==1?" 허용":" 금지");break;
   case "god":what=(e.resource>=1&&e.resource<=5?GodNames[e.resource-1]:"?")+"의 "+(e.amount>=1&&e.amount<=3?GodActs[e.amount-1]:"?");break;
   case "goods":what=(e.amount>0?"보급 ":"징발 ")+GoodName(e.resource)+" "+Math.Abs(e.amount)+"포대";break;
   case "health":what="도시 건강 "+e.amount.ToString("+0;-0");break;
   case "migration":what="이민 "+e.amount+"% ("+e.deadline+"개월)";break;
   case "revolt":what="검투사 반란";break;
   case "message":what="도시 소식: "+((e.text??"").Replace("\r","").Split('\n')[0]);break;   // the title
   default:what=e.kind;break;
  }
  return "시작 후 "+e.month+"개월 / "+what+WhenText(e)+RepeatText(e);
 }
 Label eventHeading=new Label{AutoSize=true,Font=new Font("Malgun Gothic",13,FontStyle.Bold),Padding=new Padding(0,4,0,0)};
 void RefreshCityEvents(){int keep=eventList.SelectedIndex;eventList.Items.Clear();var slot=EventSlot();eventHeading.Text=slot==null?"":CityName(slot.name_id)+Lang.T("의 도시별 이벤트");if(slot!=null&&slot.events!=null)foreach(var e in slot.events)eventList.Items.Add(EventText(e));if(keep>=0&&keep<eventList.Items.Count)eventList.SelectedIndex=keep;}
 void RefreshEventCities(){int old=eventCity.SelectedIndex;eventCity.Items.Clear();if(project==null)return;foreach(var slot in project.slots)eventCity.Items.Add(CityName(slot.name_id));if(project.slots.Length>0)eventCity.SelectedIndex=Math.Min(Math.Max(old,0),project.slots.Length-1);else RefreshCityEvents();}
 bool eventFilling;
 // The form for one kind: which boxes it shows, their names and ranges.
 void ShowEventKind(){
  int n=eventKind.SelectedIndex;if(n<0)return;string k=EventKinds[n];bool was=eventFilling;eventFilling=true;
  try{
   bool amount=k!="building"&&k!="god"&&k!="revolt"&&k!="message",resource=k=="request"||k=="building"||k=="goods"||k=="god",choice=k=="building"||k=="god",deadline=k=="request"||k=="migration",text=k=="message";
   eventAmount.Visible=eventAmountLabel.Visible=amount;eventResource.Visible=eventResourceLabel.Visible=resource;eventChoice.Visible=eventChoiceLabel.Visible=choice;eventDeadline.Visible=eventDeadlineLabel.Visible=deadline;eventText.Visible=eventTextLabel.Visible=eventTitle.Visible=eventTitleLabel.Visible=eventPreview.Visible=eventPreviewLabel.Visible=text;if(text)ShowEventPreview();
   eventAmount.Minimum=-1000000;eventAmount.Maximum=1000000;
   switch(k){
    case "grant":eventAmountLabel.Text="지원금 (데나리)";eventAmount.Minimum=1;eventAmount.Maximum=1000000;eventAmount.Value=1000;break;
    case "favor":eventAmountLabel.Text="변화 (+/-)";eventAmount.Minimum=-100;eventAmount.Maximum=100;eventAmount.Value=5;break;
    case "request":eventAmountLabel.Text="요청 수량 (포대)";eventAmount.Minimum=1;eventAmount.Maximum=10000;eventAmount.Value=10;break;
    case "goods":eventAmountLabel.Text="포대 (+지급 / -징발)";eventAmount.Minimum=-1000;eventAmount.Maximum=1000;eventAmount.Value=20;break;
    case "health":eventAmountLabel.Text="건강 변화 (+/-)";eventAmount.Minimum=-100;eventAmount.Maximum=100;eventAmount.Value=-10;break;
    case "migration":eventAmountLabel.Text="이민 비율 (%)";eventAmount.Minimum=10;eventAmount.Maximum=400;eventAmount.Value=200;break;
   }
   eventResource.Items.Clear();
   if(k=="request"||k=="goods"){eventResourceLabel.Text=k=="request"?"요청 물품":"물품";foreach(var r in eventGoods)eventResource.Items.Add(r);}
   else if(k=="building"){eventResourceLabel.Text="건물";if(catalog!=null)foreach(var b in catalog)eventResource.Items.Add(b);}
   else if(k=="god"){eventResourceLabel.Text="신";eventResource.Items.AddRange(GodNames);}
   if(eventResource.Items.Count==0)eventResource.Items.Add("-");eventResource.SelectedIndex=0;   // hidden then; never an empty list
   eventChoice.Items.Clear();
   if(k=="building"){eventChoiceLabel.Text="바꾸기";eventChoice.Items.AddRange(new object[]{"허용 (지을 수 있게)","금지 (새로 못 짓게)"});}
   else if(k=="god"){eventChoiceLabel.Text="효과";eventChoice.Items.AddRange(GodActs);}
   if(eventChoice.Items.Count==0)eventChoice.Items.Add("-");eventChoice.SelectedIndex=0;
   if(k=="request"){eventDeadlineLabel.Text="기한 (년)";eventDeadline.Minimum=1;eventDeadline.Maximum=20;eventDeadline.Value=2;}
   else if(k=="migration"){eventDeadlineLabel.Text="기간 (개월)";eventDeadline.Minimum=1;eventDeadline.Maximum=120;eventDeadline.Value=6;}
   eventHelp.Text=Lang.T(EventHelp[n]);
  }finally{eventFilling=was;}
 }
 CityEvent EventFromForm(Slot slot){
  int n=eventKind.SelectedIndex;if(n<0)throw new Exception("이벤트 종류를 고르세요.");string k=EventKinds[n];
  if((k=="favor"||k=="request")&&slot.governance!=null&&slot.governance.policy=="fixed")throw new Exception("통치자 탭에서 이 도시의 황제 지지도를 원본 규칙으로 바꾸세요.");
  var e=new CityEvent{kind=k,month=(int)eventMonth.Value};
  switch(k){
   case "grant":case "favor":case "health":e.amount=(int)eventAmount.Value;if(e.amount==0)throw new Exception("0은 쓸 수 없습니다.");break;
   case "request":e.amount=(int)eventAmount.Value;e.resource=((DeliveryResource)eventResource.SelectedItem).resource;e.deadline=(int)eventDeadline.Value;break;
   case "building":e.resource=((BuildingChoice)eventResource.SelectedItem).id;e.amount=eventChoice.SelectedIndex==0?1:2;break;
   case "god":e.resource=eventResource.SelectedIndex+1;e.amount=eventChoice.SelectedIndex+1;break;
   case "goods":e.amount=(int)eventAmount.Value;if(e.amount==0)throw new Exception("0포대는 쓸 수 없습니다.");e.resource=((DeliveryResource)eventResource.SelectedItem).resource;break;
   case "migration":e.amount=(int)eventAmount.Value;if(e.amount==100)throw new Exception("100%는 평소와 같습니다.");e.deadline=(int)eventDeadline.Value;break;
   case "revolt":e.amount=1;break;
   case "message":{e.amount=1;string title=eventTitle.Text.Replace("\r","").Replace("\n"," ").Trim(),body=eventText.Text.Replace("\r\n","\n").Trim();if(body.Length==0)throw new Exception("메시지 내용을 쓰세요.");
    e.text=(title.Length>0?title:"도시 소식")+"\n"+body;if(System.Text.Encoding.UTF8.GetByteCount(e.text)>600)throw new Exception("메시지가 너무 깁니다.");break;}
  }
  if(eventWhen.SelectedIndex>0){if(k=="migration")throw new Exception("이민 증가·감소에는 조건을 붙일 수 없습니다.");string stat=EventStats[eventWhen.SelectedIndex-1];int v=(int)eventWhenValue.Value;int most=stat=="population"?1000000:stat=="money"?1000000000:100;if(v>most)throw new Exception(EventStatNames[eventWhen.SelectedIndex-1]+" 조건은 "+most.ToString("N0")+" 이하로 쓰세요.");e.when=new EventWhen{stat=stat,at_least=v};}
  if(eventTimes.Value>1){e.repeat=new EventRepeat{every=(int)eventEvery.Value,times=(int)eventTimes.Value};if(e.month+e.repeat.every*(e.repeat.times-1)>1200)throw new Exception("반복하면 1200개월을 넘습니다.");}
  return e;
 }
 void EventToForm(CityEvent e){
  int n=Array.IndexOf(EventKinds,e.kind);if(n<0)return;eventKind.SelectedIndex=n;ShowEventKind();eventMonth.Value=Math.Max(eventMonth.Minimum,Math.Min(eventMonth.Maximum,e.month));
  if(eventAmount.Visible)eventAmount.Value=Math.Max(eventAmount.Minimum,Math.Min(eventAmount.Maximum,e.amount));
  if(e.kind=="request"||e.kind=="goods"){for(int i=0;i<eventResource.Items.Count;i++)if(((DeliveryResource)eventResource.Items[i]).resource==e.resource)eventResource.SelectedIndex=i;}
  else if(e.kind=="building"){for(int i=0;i<eventResource.Items.Count;i++)if(((BuildingChoice)eventResource.Items[i]).id==e.resource)eventResource.SelectedIndex=i;eventChoice.SelectedIndex=e.amount==1?0:1;}
  else if(e.kind=="god"){eventResource.SelectedIndex=Math.Max(0,Math.Min(4,e.resource-1));eventChoice.SelectedIndex=Math.Max(0,Math.Min(2,e.amount-1));}
  if(eventDeadline.Visible)eventDeadline.Value=Math.Max(eventDeadline.Minimum,Math.Min(eventDeadline.Maximum,e.deadline));
  eventWhen.SelectedIndex=e.when==null?0:Math.Max(0,Array.IndexOf(EventStats,e.when.stat)+1);if(e.when!=null)eventWhenValue.Value=Math.Max(eventWhenValue.Minimum,Math.Min(eventWhenValue.Maximum,e.when.at_least));
  eventTimes.Value=e.repeat==null?1:Math.Max(1,Math.Min(24,e.repeat.times));if(e.repeat!=null)eventEvery.Value=Math.Max(1,Math.Min(240,e.repeat.every));
  if(e.kind=="message"){string t=(e.text??"").Replace("\r\n","\n");int cut=t.IndexOf('\n');eventTitle.Text=cut<0?"":t.Substring(0,cut);eventText.Text=(cut<0?t:t.Substring(cut+1)).Replace("\n","\r\n");ShowEventPreview();}
 }
 // The same events in every other city (user 2026-11-15: fair contests). Their own lists are replaced. Favour changes and
 // requests are left out where a city keeps its favour fixed (they need the original rules there).
 void CopyEventsToAll(){
  var from=EventSlot();if(from==null)return;if(project.slots.Length<2)throw new Exception("다른 플레이 도시가 없습니다.");
  if(LangBox.Show(this,"다른 도시의 이벤트를 모두 지우고 "+CityName(from.name_id)+"의 이벤트와 똑같이 바꿀까요?","이벤트 복사",MessageBoxButtons.YesNo)!=DialogResult.Yes)return;
  int skipped=0;string body=Json.Serialize(from.events??new List<CityEvent>());
  foreach(var slot in project.slots){if(slot==from)continue;var copy=Json.Deserialize<List<CityEvent>>(body);
   if(slot.governance!=null&&slot.governance.policy=="fixed"){skipped+=copy.Count(e=>e.kind=="favor"||e.kind=="request");copy=copy.Where(e=>e.kind!="favor"&&e.kind!="request").ToList();}
   slot.events=copy.Count==0?null:copy;}
  Changed();status.Text=Lang.T("이벤트를 다른 도시에 복사했습니다.")+(skipped>0?" "+Lang.T("황제 지지도를 고정한 도시에는 지지도 변화·물품 요청을 넣지 않았습니다")+" ("+skipped+")":"");
 }
 static void SortEvents(Slot slot){slot.events=slot.events.Select((e,i)=>new{e,i}).OrderBy(x=>x.e.month).ThenBy(x=>x.i).Select(x=>x.e).ToList();}
 void BuildCityEventsTab(){
  var tab=new TabPage("6  도시별 이벤트"){BackColor=Paper};tabs.TabPages.Add(tab);
  var layout=new TableLayoutPanel{Dock=DockStyle.Fill,Padding=new Padding(16,8,16,8),ColumnCount=1,RowCount=3};
  layout.RowStyles.Add(new RowStyle(SizeType.Absolute,44));layout.RowStyles.Add(new RowStyle(SizeType.Absolute,30));layout.RowStyles.Add(new RowStyle(SizeType.Percent,100));tab.Controls.Add(layout);
  /* the city is the one chosen at the top (user 2026-11-15): hidden picker, the name as heading */
  var head=new FlowLayoutPanel{Dock=DockStyle.Fill,WrapContents=false};eventCity.Visible=false;head.Controls.Add(eventCity);head.Controls.Add(eventHeading);layout.Controls.Add(head,0,0);
  layout.Controls.Add(TextLabel("이 도시에서 정한 개월이 지나면 일어납니다. 조건을 고르면 그 값에 이른 뒤에, 반복을 정하면 여러 번 일어납니다. 이 도시에만 효과가 있고 승리 조건은 아닙니다. 새 시나리오로 시작해야 적용됩니다."),0,1);
  // left: the city's events in month order; right: one event's values (the same arrangement as 침략 설정)
  var body=new TableLayoutPanel{Dock=DockStyle.Fill,ColumnCount=2,RowCount=1,Margin=new Padding(0)};body.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));body.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,470));layout.Controls.Add(body,0,2);
  var listBox=new GroupBox{Text="이벤트 목록 (시작 후 개월 순)",Dock=DockStyle.Fill,ForeColor=Dark,Padding=new Padding(8)};{var listLayout=new TableLayoutPanel{Dock=DockStyle.Fill,ColumnCount=1,RowCount=2};listLayout.RowStyles.Add(new RowStyle(SizeType.Percent,100));listLayout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
   listLayout.Controls.Add(eventList,0,0);var copy=new FlowLayoutPanel{AutoSize=true,Dock=DockStyle.Fill};copy.Controls.Add(Button("이 이벤트들을 다른 도시에도",CopyEventsToAll,210));listLayout.Controls.Add(copy,0,1);listBox.Controls.Add(listLayout);}
  body.Controls.Add(listBox,0,0);
  var formBox=new GroupBox{Text="이벤트 내용",Dock=DockStyle.Fill,ForeColor=Dark,Padding=new Padding(10)};var form=new TableLayoutPanel{Dock=DockStyle.Fill,ColumnCount=2,AutoScroll=true};form.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,130));form.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));
  Action<Control,Control> row=(label,control)=>{int r=form.RowCount++;form.RowStyles.Add(new RowStyle(SizeType.AutoSize));form.Controls.Add(label,0,r);form.Controls.Add(control,1,r);};
  Func<string,Label> caption=t=>new Label{Text=t,AutoSize=true,Padding=new Padding(0,7,0,0)};
  foreach(var r in Json.Deserialize<DeliveryResource[]>(File.ReadAllText(Path.Combine(Root,"trade-catalog.json"))))if(r.resource>0)eventGoods.Add(r);
  eventKind.Items.AddRange(EventKindNames);
  row(caption("이벤트 종류"),eventKind);row(caption("시작 후 개월"),eventMonth);
  // when and how often (optional): one line each
  eventWhen.Items.Add("조건 없음");foreach(var n in EventStatNames)eventWhen.Items.Add(n);eventWhen.SelectedIndex=0;eventWhen.SelectedIndexChanged+=(s,e)=>{eventWhenValue.Enabled=eventWhen.SelectedIndex>0;};eventWhenValue.Enabled=false;
  {var w=new FlowLayoutPanel{AutoSize=true,WrapContents=false,Margin=new Padding(0)};w.Controls.Add(eventWhen);w.Controls.Add(eventWhenValue);w.Controls.Add(new Label{AutoSize=true,Text="이상"});row(caption("조건 (선택)"),w);}
  eventTimes.ValueChanged+=(s,e)=>{eventEvery.Enabled=eventTimes.Value>1;};eventEvery.Enabled=false;
  {var r=new FlowLayoutPanel{AutoSize=true,WrapContents=false,Margin=new Padding(0)};r.Controls.Add(eventEvery);r.Controls.Add(new Label{AutoSize=true,Text="개월마다"});r.Controls.Add(eventTimes);r.Controls.Add(new Label{AutoSize=true,Text="번 (1번 = 반복 없음)"});row(caption("반복 (선택)"),r);}
  row(eventResourceLabel,eventResource);row(eventChoiceLabel,eventChoice);row(eventAmountLabel,eventAmount);row(eventDeadlineLabel,eventDeadline);row(eventTitleLabel,eventTitle);row(eventTextLabel,eventText);row(eventPreviewLabel,eventPreview);eventPreview.Controls.Add(previewBody);eventPreview.Controls.Add(previewSub);eventPreview.Controls.Add(previewTitle);eventTitle.TextChanged+=(s,e)=>ShowEventPreview();eventText.TextChanged+=(s,e)=>ShowEventPreview();
  var actions=new FlowLayoutPanel{AutoSize=true,WrapContents=false,Margin=new Padding(0,10,0,0)};
  actions.Controls.Add(Button("이벤트 추가",()=>{var slot=EventSlot();if(slot==null)throw new Exception("도시를 선택하세요.");if(slot.events==null)slot.events=new List<CityEvent>();if(slot.events.Count>=32)throw new Exception("도시별 최대 32개입니다.");var added=EventFromForm(slot);slot.events.Add(added);SortEvents(slot);RefreshCityEvents();eventList.SelectedIndex=slot.events.IndexOf(added);Changed();},110));
  actions.Controls.Add(Button("선택 이벤트 바꾸기",()=>{var slot=EventSlot();int i=eventList.SelectedIndex;if(slot==null||slot.events==null||i<0)throw new Exception("왼쪽 목록에서 바꿀 이벤트를 고르세요.");var changed=EventFromForm(slot);slot.events[i]=changed;SortEvents(slot);RefreshCityEvents();eventList.SelectedIndex=slot.events.IndexOf(changed);Changed();},150));
  actions.Controls.Add(Button("선택 이벤트 삭제",()=>{var slot=EventSlot();int i=eventList.SelectedIndex;if(slot==null||slot.events==null||i<0)throw new Exception("왼쪽 목록에서 지울 이벤트를 고르세요.");slot.events.RemoveAt(i);RefreshCityEvents();Changed();},150));
  {int r=form.RowCount++;form.RowStyles.Add(new RowStyle(SizeType.AutoSize));form.Controls.Add(actions,0,r);form.SetColumnSpan(actions,2);}
  {int r=form.RowCount++;form.RowStyles.Add(new RowStyle(SizeType.AutoSize));form.Controls.Add(eventHelp,0,r);form.SetColumnSpan(eventHelp,2);}
  formBox.Controls.Add(form);body.Controls.Add(formBox,1,0);
  eventKind.SelectedIndexChanged+=(s,e)=>{if(!eventFilling)ShowEventKind();};eventKind.SelectedIndex=0;
  eventList.SelectedIndexChanged+=(s,e)=>{var slot=EventSlot();int i=eventList.SelectedIndex;if(slot!=null&&slot.events!=null&&i>=0&&i<slot.events.Count)EventToForm(slot.events[i]);};
  eventCity.SelectedIndexChanged+=(s,e)=>{eventList.ClearSelected();RefreshCityEvents();};
  tab.Enter+=(s,e)=>RefreshEventCities();
 }
 static int CityEventsProbe(){
  var slot=new Slot{events=new List<CityEvent>{new CityEvent{kind="request",month=6,amount=10,resource=1,deadline=2},new CityEvent{kind="message",month=7,amount=1,text="제목\n내용"}}};
  var copy=Json.Deserialize<Slot>(Json.Serialize(slot));
  if(copy.events.Count!=2||copy.events[0].month!=6||copy.events[0].amount!=10||copy.events[1].text!="제목\n내용")throw new Exception("Event roundtrip failed");
  if(Json.Deserialize<Slot>("{\"id\":\"old\"}").events!=null)throw new Exception("Legacy changed");
  // when + repeat (2026-11-15): kept through a save; absent parts are not written
  var waiting=new Slot{events=new List<CityEvent>{new CityEvent{kind="grant",month=3,amount=5,when=new EventWhen{stat="money",at_least=1500000},repeat=new EventRepeat{every=12,times=3}}}};
  var back=Json.Deserialize<Slot>(Json.Serialize(waiting)).events[0];
  if(back.when==null||back.when.stat!="money"||back.when.at_least!=1500000||back.repeat==null||back.repeat.every!=12||back.repeat.times!=3)throw new Exception("Condition/repeat roundtrip failed");
  File.WriteAllText(Path.Combine(Root,"city-events-editor-results.json"),"{\"passed\":true,\"gui_created\":false}");return 0;}
}
