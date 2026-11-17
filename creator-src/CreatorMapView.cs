using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Collections.Generic;
using System.Windows.Forms;
public class MapCity { public int name_id,x,y; public string name; }
public class MapData { public int width,height; public MapCity[] cities; }
public class MapCache { public string image,metadata; }
// One trade relation of a player city, as judged by scenario_check.py (the same answer the checks and the lobby use).
// state: ok | candidate | unknown | broken | off.  A line means "the scenario lets these two trade", not a caravan on the way.
public class CityLink { public string kind,slot,transport,allow_source,state,reason; public int name_id; public bool allowed,approximate; public int[] sells,buys; }
public class CreatorMapView : Control {
 public HashSet<int> PlayableCities=new HashSet<int>();
 public Bitmap Background; public MapData Data; public Scenario Project;
 public int Selected=2,Origin=2; public bool PlacementMode;
 public event Action<int> CitySelected; public event Action<int,int,int> CityMoved; public event Action<int,int> MapPlaced;
 public event Action<int> CityActionsRequested;
 // Rome (RomeCapital): selectable for read-only information only; choosing it never changes Selected or a slot.
 public bool RomeChosen; public event Action RomeSelected; public event Action<int> PositionRefused;
 public bool HitRome(PointF p,Size size){return RomeDistance(p,size)<=196;}
 float RomeDistance(PointF p,Size size){var s=RomeCapital.Spec;if(s==null||Data==null)return float.MaxValue;var q=Position(s.x,s.y,size);return (p.X-q.X)*(p.X-q.X)+(p.Y-q.Y)*(p.Y-q.Y);}
 float CityDistance(int id,PointF p,Size size){var c=Project==null?null:Array.Find(Project.empire.cities,v=>v.name_id==id);if(c==null)return float.MaxValue;var q=Position(c.x,c.y,size);return (p.X-q.X)*(p.X-q.X)+(p.Y-q.Y)*(p.Y-q.Y);}
 // Rome or a city: whichever marker is nearer to the pointer. Neither range grows, so neither takes the other's clicks.
 public bool PicksRome(PointF p,Size size,int city){return HitRome(p,size)&&RomeDistance(p,size)<CityDistance(city,p,size);}
 public Func<int,CityLink[]> LinksFor; public bool ShowForbidden; public string LinksNote;
 public bool ShowConnections;public bool EditPositions;public int AssignmentSlot=-1;public float Zoom=1;PointF pan;bool panning;
 public static Color PlayerColor(int i){Color[] colors={Color.FromArgb(28,123,73),Color.FromArgb(35,96,173),Color.FromArgb(174,64,44),Color.FromArgb(126,66,155),Color.FromArgb(146,103,15),Color.FromArgb(23,126,135),Color.FromArgb(173,57,116),Color.FromArgb(85,100,48)};return colors[i%colors.Length];}
 public void FitMap(){Zoom=1;pan=PointF.Empty;Invalidate();}
 public void ZoomAt(float factor,PointF anchor){var before=Target(ClientSize);float u=(anchor.X-before.X)/before.Width,v=(anchor.Y-before.Y)/before.Height;Zoom=Math.Max(1,Math.Min(4,Zoom*factor));var after=Target(ClientSize);pan.X+=anchor.X-(after.X+u*after.Width);pan.Y+=anchor.Y-(after.Y+v*after.Height);ClampPan();Invalidate();}
 void ClampPan(){var r=Target(ClientSize);if(r.Width<=Width)pan.X=0;else if(r.Left>12)pan.X-=r.Left-12;else if(r.Right<Width-12)pan.X+=Width-12-r.Right;r=Target(ClientSize);if(r.Height<=Height)pan.Y=0;else if(r.Top>12)pan.Y-=r.Top-12;else if(r.Bottom<Height-12)pan.Y+=Height-12-r.Bottom;}
 int dragging,hovered; Point dragStart; bool didMove; readonly ToolTip cityTooltip=new ToolTip{InitialDelay=250,ReshowDelay=100,AutoPopDelay=10000};
 public CreatorMapView(){DoubleBuffered=true;ResizeRedraw=true;Dock=DockStyle.Fill;Cursor=Cursors.Hand;BackColor=Color.FromArgb(45,42,34);}
 public static string CityLabel(int id){switch(id){case 1:return "타렌툼";case 2:return "카푸아";case 3:return "브룬디시움";case 10:return "시라쿠세";case 4:return "메디올라눔";case 6:return "카르타고";case 13:return "렙티스";default:return "도시 "+id;}}
 public string Label(int id){if(Data!=null && Data.cities!=null){var c=Array.Find(Data.cities,x=>x.name_id==id);if(c!=null && !string.IsNullOrEmpty(c.name))return c.name;}return CityLabel(id);}
 public RectangleF WorldBounds(){return new RectangleF(0,0,Data==null?2000:Data.width,Data==null?1000:Data.height);}
 public RectangleF Target(Size size){var w=WorldBounds();float scale=Math.Max(.01f,Math.Min((size.Width-24)/w.Width,(size.Height-24)/w.Height))*Zoom;return new RectangleF((size.Width-w.Width*scale)/2+pan.X,(size.Height-w.Height*scale)/2+pan.Y,w.Width*scale,w.Height*scale);}
 public PointF Position(MapCity c,Size size){return Position(c.x,c.y,size);}
 public PointF Position(int x,int y,Size size){var t=Target(size);var w=WorldBounds();return new PointF(t.X+x*t.Width/w.Width,t.Y+y*t.Height/w.Height);}
 public Point World(PointF p,Size size){var t=Target(size);var w=WorldBounds();return new Point(Math.Max(16,Math.Min((int)w.Width-17,(int)Math.Round((p.X-t.X)*w.Width/t.Width))),Math.Max(16,Math.Min((int)w.Height-17,(int)Math.Round((p.Y-t.Y)*w.Height/t.Height))));}
 public int Hit(PointF p,Size size){if(Project==null)return 0;int id=0;float best=225;foreach(var c in Project.empire.cities){var q=Position(c.x,c.y,size);float d=(p.X-q.X)*(p.X-q.X)+(p.Y-q.Y)*(p.Y-q.Y);if(d<best){id=c.name_id;best=d;}}return id;}
 public void MoveCity(int id,int x,int y){var c=Array.Find(Project.empire.cities,v=>v.name_id==id);if(c==null)return;int nx=Math.Max(16,Math.Min(Data.width-17,x)),ny=Math.Max(16,Math.Min(Data.height-17,y));
  if(RomeCapital.TooClose(nx,ny)){if(PositionRefused!=null)PositionRefused(id);return;}   // the city stays where it was
  c.x=nx;c.y=ny;if(CityMoved!=null)CityMoved(id,c.x,c.y);Invalidate();}
 // Wheel zooms at the pointer as soon as the pointer is over the map (a wheel goes to the focused control), and the
 // wheel button drags the map from anywhere, also from on top of a city (the left button there selects or moves it).
 protected override void OnMouseEnter(EventArgs e){base.OnMouseEnter(e);var form=FindForm();if(form!=null&&form.ContainsFocus&&!(form.ActiveControl is TextBoxBase))Focus();}
 protected override void OnMouseDown(MouseEventArgs e){base.OnMouseDown(e);if(e.Button==MouseButtons.Middle&&Project!=null){Focus();dragging=0;dragStart=e.Location;didMove=true;panning=true;Capture=true;return;}if(e.Button!=MouseButtons.Left || Project==null)return;Focus();if(!legendBox.IsEmpty&&legendBox.Contains(e.Location)){LegendOpen=!LegendOpen;dragging=0;didMove=true;Invalidate();return;}if(PlacementMode && Target(ClientSize).Contains(e.Location)){var at=World(e.Location,ClientSize);if(MapPlaced!=null)MapPlaced(at.X,at.Y);return;}dragging=Hit(e.Location,ClientSize);dragStart=e.Location;didMove=false;panning=dragging==0;Capture=true;}
 public void PanBy(float x,float y){pan.X+=x;pan.Y+=y;ClampPan();Invalidate();}
 public void RevealCity(int id){if(Project==null)return;var c=Array.Find(Project.empire.cities,v=>v.name_id==id);if(c==null)return;var p=Position(c.x,c.y,ClientSize);if(p.X<30||p.X>Width-30||p.Y<30||p.Y>Height-30)PanBy(Width/2f-p.X,Height/2f-p.Y);}
 public bool DragCityTo(int id,int x,int y){if(!EditPositions)return false;MoveCity(id,x,y);return true;}
 protected override void OnMouseMove(MouseEventArgs e){base.OnMouseMove(e);
  if(Capture&&panning&&e.Button==MouseButtons.Middle){PanBy(e.X-dragStart.X,e.Y-dragStart.Y);dragStart=e.Location;return;}
  if(Capture&&e.Button==MouseButtons.Left){int dx=e.X-dragStart.X,dy=e.Y-dragStart.Y;if(Math.Abs(dx)+Math.Abs(dy)>4)didMove=true;if(didMove){if(panning){PanBy(dx,dy);dragStart=e.Location;}else if(EditPositions){var point=World(e.Location,ClientSize);DragCityTo(dragging,point.X,point.Y);}}return;}
  if(Project!=null){int hit=Hit(e.Location,ClientSize);if(PicksRome(e.Location,ClientSize,hit)){if(hovered!=-1){hovered=-1;cityTooltip.SetToolTip(this,RomeCapital.Title+" · "+RomeCapital.Summary);}return;}if(hit!=hovered){hovered=hit;var city=Array.Find(Project.empire.cities,c=>c.name_id==hit);cityTooltip.SetToolTip(this,city==null?"":Label(hit)+(PlayableCities.Contains(hit)?" · 플레이 지형 있음":" · 중립 교역도시")+(city.enabled?"":" · 사용 안 함"));}}
 }

 protected override void OnMouseUp(MouseEventArgs e){base.OnMouseUp(e);int clicked=dragging;dragging=0;panning=false;Capture=false;if(e.Button==MouseButtons.Left&&!didMove&&!EditPositions&&PicksRome(e.Location,ClientSize,clicked)){RomeChosen=true;Invalidate();if(RomeSelected!=null)RomeSelected();return;}
  if(e.Button==MouseButtons.Left&&!didMove&&clicked!=0){RomeChosen=false;bool assigning=AssignmentSlot>=0;if(CitySelected!=null)CitySelected(clicked);if(!assigning&&!EditPositions&&CityActionsRequested!=null)CityActionsRequested(clicked);}}
 protected override void OnMouseWheel(MouseEventArgs e){base.OnMouseWheel(e);ZoomAt(e.Delta>0?1.2f:1/1.2f,e.Location);}
 protected override void OnPaint(PaintEventArgs e){base.OnPaint(e);Draw(e.Graphics,ClientSize);}
 static readonly Color Earth=Color.FromArgb(176,126,62),Water=Color.FromArgb(78,160,222);
 // Emphasis order: forbidden (only on request) < unknown < broken < candidate < ok, so working links stay on top.
 static int Rank(string state){switch(state){case "off":return 0;case "unknown":return 1;case "broken":return 2;case "candidate":return 3;default:return 4;}}
 bool legendPending;string legendNote;
 void DrawPlayerLinks(Graphics g,Size size,City chosen){
  var links=LinksFor==null?null:LinksFor(chosen.name_id);
  var start=Position(chosen.x,chosen.y,size);
  if(links!=null){
   var order=new List<CityLink>(links);order.Sort((a,b)=>Rank(a.state).CompareTo(Rank(b.state)));
   foreach(var link in order){
    if(!link.allowed&&!ShowForbidden)continue;
    City other=null;
    if(link.kind=="player"){var slot=Array.Find(Project.slots,s=>s.id==link.slot);if(slot!=null)other=Array.Find(Project.empire.cities,c=>c.name_id==slot.name_id);}
    else other=Array.Find(Project.empire.cities,c=>c.name_id==link.name_id);
    if(other==null)continue;
    var end=Position(other.x,other.y,size);
    Color tone=link.transport=="sea"?Water:Earth;float width=link.state=="ok"||link.state=="candidate"?3.2f:2.2f;
    if(link.state=="unknown"||link.state=="off")tone=Color.FromArgb(link.state=="off"?110:170,tone);
    using(var under=new Pen(Color.FromArgb(link.state=="off"?90:200,0,0,0),width+2.4f))g.DrawLine(under,start,end);
    using(var pen=new Pen(tone,width)){
     pen.DashStyle=link.state=="candidate"?DashStyle.Dash:link.state=="unknown"||link.state=="off"?DashStyle.Dot:link.state=="broken"?DashStyle.DashDot:DashStyle.Solid;
     g.DrawLine(pen,start,end);
    }
    if(link.state=="broken"){var mid=new PointF((start.X+end.X)/2,(start.Y+end.Y)/2);using(var cross=new Pen(Color.FromArgb(220,200,40,30),3)){g.DrawLine(cross,mid.X-6,mid.Y-6,mid.X+6,mid.Y+6);g.DrawLine(cross,mid.X-6,mid.Y+6,mid.X+6,mid.Y-6);}}
   }
  }
  legendPending=true;legendNote=links==null?(LinksNote??"교역 연결을 확인하는 중입니다."):null; // drawn last, above the city markers
 }
 // The legend sits over the map's corner and hid the cities under it: a click folds it to a small tab and back.
 public bool LegendOpen=true;RectangleF legendBox;
 void DrawLinkLegend(Graphics g,Size size,string note){
  // Top right (no city sits there; user 2026-11-13), with a fold/unfold button that looks like one, so it is found the first time.
  if(!LegendOpen){
   using(var font=new Font("Malgun Gothic",8.5f,FontStyle.Bold)){
    string tab="범례 펴기 ▼";var m=g.MeasureString(Lang.T(tab),font);legendBox=new RectangleF(size.Width-m.Width-30,12,m.Width+18,m.Height+10);
    using(var back=new SolidBrush(Color.FromArgb(235,30,28,22)))g.FillRectangle(back,legendBox);
    DrawLegendButton(g,legendBox,tab,font);
   }
   return;
  }
  // Each row shows the real line style next to its meaning, so colour is never the only cue.
  var rows=new[]{
   Tuple.Create("육로 가능",Earth,DashStyle.Solid),Tuple.Create("해로 후보(확정 아님)",Water,DashStyle.Dash),
   Tuple.Create("미확인",Color.FromArgb(170,Water),DashStyle.Dot),Tuple.Create("불가 ✕ (이유: 3번 탭 교역 관계)",Water,DashStyle.DashDot)};
  string foot="연결 종류 표시(직선) · 선 없음 = 교역 연결 없음";
  using(var font=new Font("Malgun Gothic",8f))using(var bold=new Font("Malgun Gothic",8.5f,FontStyle.Bold)){
   string fold="접기 ▲";var fm=g.MeasureString(Lang.T(fold),bold);float head=fm.Height+12;
   float w=g.MeasureString(Lang.T(foot),font).Width,line=g.MeasureString(Lang.T("가"),font).Height+3,h=head+line*(rows.Length+1)+(note==null?0:line)+8;
   foreach(var r in rows)w=Math.Max(w,g.MeasureString(Lang.T(r.Item1),font).Width+40);
   w=Math.Max(w,g.MeasureString(Lang.T("범례"),bold).Width+fm.Width+40);
   var box=new RectangleF(size.Width-w-24,12,w+16,h); // top right: no city sits there
   legendBox=box;
   using(var back=new SolidBrush(Color.FromArgb(225,30,28,22)))g.FillRectangle(back,box);
   g.DrawString(Lang.T("범례"),bold,Brushes.Ivory,box.X+8,box.Y+7);
   DrawLegendButton(g,new RectangleF(box.Right-fm.Width-26,box.Y+4,fm.Width+18,fm.Height+6),fold,bold);
   float y=box.Y+head+3;
   if(note!=null){g.DrawString(Lang.T(note),font,Brushes.Gold,box.X+8,y);y+=line;}
   foreach(var r in rows){
    float mid=y+line/2-1;
    using(var under=new Pen(Color.Black,4.4f))g.DrawLine(under,box.X+8,mid,box.X+34,mid);
    using(var pen=new Pen(r.Item2,2.6f){DashStyle=r.Item3})g.DrawLine(pen,box.X+8,mid,box.X+34,mid);
    if(r.Item3==DashStyle.DashDot)using(var cross=new Pen(Color.FromArgb(220,200,40,30),2)){g.DrawLine(cross,box.X+18,mid-4,box.X+26,mid+4);g.DrawLine(cross,box.X+18,mid+4,box.X+26,mid-4);}
    g.DrawString(Lang.T(r.Item1),font,Brushes.Gainsboro,box.X+40,y);y+=line;
   }
   g.DrawString(Lang.T(foot),font,Brushes.Ivory,box.X+8,y);
  }
 }
 // A button-like chip (gold frame and text), the whole legend answers the click.
 static void DrawLegendButton(Graphics g,RectangleF r,string text,Font font){
  using(var fill=new SolidBrush(Color.FromArgb(255,74,60,30)))g.FillRectangle(fill,r);
  using(var edge=new Pen(Color.FromArgb(255,214,170,70),1.5f))g.DrawRectangle(edge,r.X,r.Y,r.Width,r.Height);
  var m=g.MeasureString(Lang.T(text),font);g.DrawString(Lang.T(text),font,Brushes.Gold,r.X+(r.Width-m.Width)/2,r.Y+(r.Height-m.Height)/2);
 }
 // Rome's flag: plain red, like the neutral cities' flags on the game's empire map (the editor cannot read those pictures).
 static void DrawRedFlag(Graphics g,RectangleF r){
  using(var red=new SolidBrush(Color.FromArgb(179,18,28)))g.FillRectangle(red,r);
  using(var edge=new Pen(Color.FromArgb(58,16,6)))g.DrawRectangle(edge,r.X,r.Y,r.Width,r.Height);
 }
 void DrawRome(Graphics g,Size size){
  var s=RomeCapital.Spec;if(s==null)return;var at=Position(s.x,s.y,size);if(at.X<-40||at.X>size.Width+40||at.Y<-40||at.Y>size.Height+40)return;
  var t=Target(size);float d=Math.Max(.45f,Math.Min(1f,t.Width/WorldBounds().Width));   // true map size, never under .45 (same rule as the game)
  var icon=RomeCapital.Icon;float w=icon==null?16:icon.Width*d,h=icon==null?16:icon.Height*d;var box=new RectangleF(at.X-w/2,at.Y-h/2,w,h);
  using(var plate=new SolidBrush(Color.FromArgb(176,243,230,196)))g.FillRectangle(plate,box.X-2,box.Y-2,box.Width+4,box.Height+4);   // pale plate: apart from map and markers
  using(var edge=new Pen(Color.FromArgb(107,86,56)))g.DrawRectangle(edge,box.X-2,box.Y-2,box.Width+4,box.Height+4);
  if(RomeChosen)using(var mark=new Pen(Color.Gold,2.5f))g.DrawRectangle(mark,box.X-4,box.Y-4,box.Width+8,box.Height+8);
  if(icon!=null){var old=g.InterpolationMode;g.InterpolationMode=InterpolationMode.NearestNeighbor;g.DrawImage(icon,box);g.InterpolationMode=old;
   // red cloth on the icon's own pole, where Augustus hangs its flag frames (offset 16,6 in ui.xml)
   DrawRedFlag(g,new RectangleF(box.X+18*d,box.Y+8*d,Math.Max(6,15*d),Math.Max(5,11*d)));}
  else{using(var fill=new SolidBrush(Color.DarkGoldenrod))g.FillRectangle(fill,box);g.DrawRectangle(Pens.Black,box.X,box.Y,box.Width,box.Height);}
  using(var font=new Font("Malgun Gothic",9,FontStyle.Bold)){string name=s.name??"로마";var text=g.MeasureString(Lang.T(name),font);float x=box.X-text.Width-8,y=at.Y-text.Height/2;
   using(var back=new SolidBrush(Color.FromArgb(225,64,42,20)))g.FillRectangle(back,x-3,y-2,text.Width+6,text.Height+4);g.DrawString(Lang.T(name),font,Brushes.Ivory,x,y);}
 }
 public void Draw(Graphics g,Size size){
  g.Clear(Color.FromArgb(42,39,32));if(Data==null || Background==null || Project==null || size.Width<40 || size.Height<40)return;
  var target=Target(size);g.InterpolationMode=InterpolationMode.HighQualityBicubic;g.DrawImage(Background,target,WorldBounds(),GraphicsUnit.Pixel);g.SmoothingMode=SmoothingMode.AntiAlias;
  var chosen=Array.Find(Project.empire.cities,c=>c.name_id==Selected);
  if(ShowConnections&&chosen!=null&&chosen.role=="npc"&&chosen.enabled){var start=Position(chosen.x,chosen.y,size);foreach(var slot in Project.slots){if(chosen.trade_players!=null&&Array.IndexOf(chosen.trade_players,slot.id)<0)continue;var c=Array.Find(Project.empire.cities,v=>v.name_id==slot.name_id);var end=Position(c.x,c.y,size);using(var edge=new Pen(Color.Black,4))g.DrawLine(edge,start,end);using(var pen=new Pen(Color.White,2)){if(chosen.sea==1)pen.DashStyle=DashStyle.Dash;g.DrawLine(pen,start,end);}}}
  if(ShowConnections&&chosen!=null&&chosen.role=="player")DrawPlayerLinks(g,size,chosen);
  DrawRome(g,size);   // above the trade lines, below the city markers so no city is hidden
  var labels=new List<RectangleF>();
  using(var font=new Font("Malgun Gothic",9,FontStyle.Bold))foreach(var c in Project.empire.cities){var at=Position(c.x,c.y,size);if(at.X<0||at.X>size.Width||at.Y<0||at.Y>size.Height)continue;bool player=c.role=="player";int slot=Array.FindIndex(Project.slots,s=>s.name_id==c.name_id)+1;
   if(!c.enabled && c.name_id!=Selected){using(var dot=new SolidBrush(PlayableCities.Contains(c.name_id)?Color.Chartreuse:Color.Magenta))g.FillEllipse(dot,at.X-5,at.Y-5,10,10);using(var edge=new Pen(Color.Black,2))g.DrawEllipse(edge,at.X-6,at.Y-6,12,12);continue;}
   using(var outline=new Pen(Color.Black,5))g.DrawEllipse(outline,at.X-12,at.Y-12,24,24);
   using(var fill=new SolidBrush(player?PlayerColor(slot-1):PlayableCities.Contains(c.name_id)?Color.Chartreuse:Color.Magenta))g.FillEllipse(fill,at.X-11,at.Y-11,22,22);
   using(var edge=new Pen(c.name_id==Selected?Color.White:Color.Black,c.name_id==Selected?3f:1.4f))g.DrawEllipse(edge,at.X-12,at.Y-12,24,24);
   string badge=player?slot.ToString():"·";var badgeSize=g.MeasureString(Lang.T(badge),font);g.DrawString(Lang.T(badge),font,Brushes.White,at.X-badgeSize.Width/2,at.Y-badgeSize.Height/2);
   string name=Label(c.name_id)+(player?"  P"+slot:!c.enabled?" (꺼짐)":"");SizeF text=g.MeasureString(Lang.T(name),font);float x=at.X+16,y=at.Y-11;
   x=Math.Max(3,Math.Min(x,size.Width-text.Width-9));y=Math.Max(3,Math.Min(y,size.Height-text.Height-9));
   RectangleF label=new RectangleF(x-3,y-2,text.Width+6,text.Height+4);for(int attempt=0;attempt<12;attempt++){bool overlaps=false;foreach(var used in labels)if(used.IntersectsWith(label)){overlaps=true;break;}if(!overlaps)break;float shift=((attempt/2)+1)*(text.Height+7)*(attempt%2==0?1:-1);label.Y=Math.Max(3,Math.Min(at.Y-11+shift,size.Height-label.Height-3));}labels.Add(label);x=label.X+3;y=label.Y+2;if(Math.Abs(y-(at.Y-11))>3){using(var leader=new Pen(Color.FromArgb(210,241,226,188),1))g.DrawLine(leader,at,new PointF(label.X,label.Y+label.Height/2));}
   using(var brush=new SolidBrush(c.name_id==Selected?Color.FromArgb(245,70,41,21):Color.FromArgb(220,36,34,26)))g.FillRectangle(brush,x-3,y-2,text.Width+6,text.Height+4);g.DrawString(Lang.T(name),font,Brushes.Ivory,x,y);
  }
  if(legendPending){legendPending=false;DrawLinkLegend(g,size,legendNote);}else legendBox=RectangleF.Empty;
  if(PlacementMode){using(var font=new Font("Malgun Gothic",11,FontStyle.Bold))g.DrawString(Lang.T("도시를 놓을 위치를 클릭하세요"),font,Brushes.Gold,18,18);
  }
 }
 protected override void Dispose(bool disposing){if(disposing){cityTooltip.Dispose();if(Background!=null)Background.Dispose();}base.Dispose(disposing);}
}
