using System;
using System.Linq;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Windows.Forms;
public class TerrainEdit {public int x,y; public string kind;}
public class TerrainData {public int width,height; public string[] tiles; public int[][] @protected;
 // map points from the engine's terrain.json (creator_terrain.h); absent in older files = not drawn
 public int[] entry,exit,river_entry,river_exit; public int[][] invasion_points;
 public int climate=-1;}   // 0 central, 1 northern, 2 desert (scenario climate); -1 = not in the file
public class CreatorTerrainView : Control {
 // Entrance, exit and the enemies' entry points on the map (user 2026-11-15): which numbered point an invasion uses.
 public bool ShowPoints=true; public int HighlightInvasion=-1;
 bool PointOk(int[] p){return p!=null&&p.Length==2&&p[0]>=0&&p[1]>=0&&p[0]<Data.width&&p[1]<Data.height;}
 void Marker(Graphics g,Size size,int[] p,Color fill,string text,bool big){
  PointF c=TilePoint(p[0],p[1],size);float r=big?11:text.Length<=1?8:6;var box=new RectangleF(c.X-r,c.Y-r,2*r,2*r);
  if(big)using(var ring=new Pen(Color.FromArgb(255,224,64),3))g.DrawEllipse(ring,box.X-3,box.Y-3,box.Width+6,box.Height+6);
  using(var b=new SolidBrush(fill))g.FillEllipse(b,box);using(var edge=new Pen(Color.White,1.5f))g.DrawEllipse(edge,box);
  using(var font=new Font("Malgun Gothic",big?9:8,FontStyle.Bold)){var sz=g.MeasureString(text,font);
   if(text.Length<=1)g.DrawString(text,font,Brushes.White,c.X-sz.Width/2,c.Y-sz.Height/2);
   else tags.Add(Tuple.Create(new RectangleF(c.X+r+2,c.Y-sz.Height/2,sz.Width,sz.Height),text));}
 }
 void DrawPoints(Graphics g,Size size){
  if(!ShowPoints||Data==null)return;g.SmoothingMode=SmoothingMode.AntiAlias;
  tags.Clear();
  if(PointOk(Data.river_entry))Marker(g,size,Data.river_entry,Color.FromArgb(40,110,190),Lang.T("강 입구"),false);
  if(PointOk(Data.river_exit))Marker(g,size,Data.river_exit,Color.FromArgb(40,110,190),Lang.T("강 출구"),false);
  if(PointOk(Data.entry))Marker(g,size,Data.entry,Color.FromArgb(46,130,60),Lang.T("입구"),false);
  if(PointOk(Data.exit))Marker(g,size,Data.exit,Color.FromArgb(150,60,40),Lang.T("출구"),false);
  if(Data.invasion_points!=null)for(int i=0;i<Data.invasion_points.Length;i++)if(PointOk(Data.invasion_points[i]))Marker(g,size,Data.invasion_points[i],Color.FromArgb(170,30,30),(i+1).ToString(),i==HighlightInvasion);
  // names last, over every circle, so a point on top of another never hides a name
  using(var font=new Font("Malgun Gothic",8,FontStyle.Bold))using(var back=new SolidBrush(Color.FromArgb(210,30,26,20)))foreach(var t in tags){g.FillRectangle(back,t.Item1);g.DrawString(t.Item2,font,Brushes.White,t.Item1.X,t.Item1.Y);}
 }
 List<Tuple<RectangleF,string>> tags=new List<Tuple<RectangleF,string>>();
 public int InvasionPointCount{get{return Data==null||Data.invasion_points==null?0:Data.invasion_points.Count(PointOk);}}
 public TerrainData Data; public string BrushKind="land"; public int BrushSize=1; public bool ShowProtected=true,ReadOnly; public float Zoom=1;
 public event Action Changed; public event Action<string> PositionChanged;
 Dictionary<int,string> edits=new Dictionary<int,string>(); HashSet<int> protectedTiles=new HashSet<int>();
 Stack<Dictionary<int,string>> undo=new Stack<Dictionary<int,string>>(); Dictionary<int,string> strokeBefore;
 Point hover=new Point(-1,-1),lastPaint=new Point(-1,-1),panStart; PointF pan,panBefore; bool painting,panning;
 public int EditCount {get{return edits.Count;}} public bool CanUndo {get{return undo.Count>0;}}
 public CreatorTerrainView(){DoubleBuffered=true;ResizeRedraw=true;Dock=DockStyle.Fill;BackColor=Color.FromArgb(43,43,34);Cursor=Cursors.Cross;TabStop=true;}
 public void Bind(TerrainData data,TerrainEdit[] changes){Data=data;edits.Clear();protectedTiles.Clear();undo.Clear();strokeBefore=null;pan=PointF.Empty;Zoom=1;if(data==null)return;if(data.tiles==null||data.tiles.Length!=data.width*data.height)throw new Exception("지형 자료의 크기가 올바르지 않습니다.");if(data.@protected!=null)foreach(var p in data.@protected)if(p.Length==2)protectedTiles.Add(p[1]*data.width+p[0]);if(changes!=null)foreach(var p in changes){if(p.x<0||p.y<0||p.x>=data.width||p.y>=data.height)throw new Exception("도시 지형 편집 좌표가 범위를 벗어났습니다.");if(protectedTiles.Contains(p.y*data.width+p.x))throw new Exception("보호된 지형 칸을 수정한 파일입니다.");edits[p.y*data.width+p.x]=p.kind;}Invalidate();}
 public TerrainEdit[] GetEdits(){return edits.OrderBy(p=>p.Key).Select(p=>new TerrainEdit{x=p.Key%Data.width,y=p.Key/Data.width,kind=p.Value}).ToArray();}
 public bool Protected(int x,int y){return Data==null||x<0||y<0||x>=Data.width||y>=Data.height||protectedTiles.Contains(y*Data.width+x);}
 public string Kind(int x,int y){string kind;int id=y*Data.width+x;return edits.TryGetValue(id,out kind)?kind:Data.tiles[id];}
 public void BeginStroke(){if(strokeBefore==null)strokeBefore=new Dictionary<int,string>(edits);}
 public bool PaintTile(int x,int y){if(Data==null)return false;bool changed=false;int low=-(BrushSize/2),high=low+BrushSize;for(int dy=low;dy<high;dy++)for(int dx=low;dx<high;dx++){int tx=x+dx,ty=y+dy;if(Protected(tx,ty))continue;int key=ty*Data.width+tx;if(Kind(tx,ty)==BrushKind)continue;if(BrushKind==Data.tiles[key])edits.Remove(key);else edits[key]=BrushKind;changed=true;}if(changed){Invalidate();if(Changed!=null)Changed();}return changed;}
 public void EndStroke(){if(strokeBefore!=null){if(strokeBefore.Count!=edits.Count||strokeBefore.Any(p=>!edits.ContainsKey(p.Key)||edits[p.Key]!=p.Value))undo.Push(strokeBefore);strokeBefore=null;}}
 public void Undo(){EndStroke();if(undo.Count==0)return;edits=undo.Pop();Invalidate();if(Changed!=null)Changed();}
 public void ResetEdits(){EndStroke();if(edits.Count==0)return;undo.Push(new Dictionary<int,string>(edits));edits.Clear();Invalidate();if(Changed!=null)Changed();}
 public void SetZoom(float zoom){Zoom=Math.Max(.5f,Math.Min(4,zoom));Invalidate();}
 public void Fit(){Zoom=1;pan=PointF.Empty;Invalidate();}
 float HalfWidth(Size size){if(Data==null)return 1;return Math.Max(.2f,Math.Min((size.Width-36f)/(Data.width+Data.height),(size.Height-44f)*2/(Data.width+Data.height)))*Zoom;}
 PointF Origin(Size size){float hw=HalfWidth(size);return new PointF(size.Width/2f-(Data.width-Data.height)*hw/2+pan.X,size.Height/2f-(Data.width+Data.height-2)*hw/4+pan.Y);}
 public PointF TilePoint(int x,int y,Size size){float hw=HalfWidth(size);PointF o=Origin(size);return new PointF(o.X+(x-y)*hw,o.Y+(x+y)*hw/2);}
 public Point TileAt(PointF p,Size size){float hw=HalfWidth(size);PointF o=Origin(size);float a=(p.X-o.X)/hw,b=(p.Y-o.Y)/(hw/2);return new Point((int)Math.Floor((a+b)/2+.5f),(int)Math.Floor((b-a)/2+.5f));}
 // Colours by the map's climate (user 2026-11-15: a desert map was drawn green): sand in the desert. Meadow, the ground
 // where farms may be built, stands apart from plain ground in every climate.
 static Color TerrainColor(string kind,int climate){
  bool desert=climate==2,north=climate==1;
  switch(kind){
   case "water":return Color.FromArgb(51,115,164);
   case "rock":return desert?Color.FromArgb(150,134,108):Color.FromArgb(130,125,109);
   case "tree":case "trees":return desert?Color.FromArgb(86,118,58):Color.FromArgb(49,103,60);
   case "road":return desert?Color.FromArgb(172,136,92):Color.FromArgb(195,158,103);
   case "building":return Color.FromArgb(161,100,65);
   case "meadow":return desert?Color.FromArgb(132,168,64):Color.FromArgb(196,196,78);
   default:return desert?Color.FromArgb(214,193,142):north?Color.FromArgb(124,146,106):Color.FromArgb(137,151,99);
  }
 }
 static string ClimateName(int climate){return climate==2?Lang.T("사막"):climate==1?Lang.T("북부"):climate==0?Lang.T("중부"):"";}
 // The legend, bottom left; its title opens and closes it (kept for every map view of the editor).
 static bool legendOpen=true;RectangleF legendHeader;
 void DrawLegend(Graphics g,Size size){
  g.SmoothingMode=SmoothingMode.AntiAlias;int c=Data.climate;
  var rows=new List<Tuple<Color,string,bool>>{
   Tuple.Create(TerrainColor("land",c),c==2?Lang.T("모래땅"):Lang.T("풀밭"),false),Tuple.Create(TerrainColor("meadow",c),Lang.T("초지 (농장을 지을 수 있는 땅)"),false),
   Tuple.Create(TerrainColor("water",c),Lang.T("물"),false),Tuple.Create(TerrainColor("trees",c),Lang.T("나무·덤불"),false),Tuple.Create(TerrainColor("rock",c),Lang.T("바위·고지대"),false),
   Tuple.Create(TerrainColor("road",c),Lang.T("도로"),false),Tuple.Create(TerrainColor("building",c),Lang.T("건물"),false)};
  if(ShowPoints){rows.Add(Tuple.Create(Color.FromArgb(46,130,60),Lang.T("입구"),true));rows.Add(Tuple.Create(Color.FromArgb(150,60,40),Lang.T("출구"),true));rows.Add(Tuple.Create(Color.FromArgb(40,110,190),Lang.T("강 입구·출구"),true));rows.Add(Tuple.Create(Color.FromArgb(170,30,30),Lang.T("적군 진입점 (번호)"),true));}
  using(var font=new Font("Malgun Gothic",8.5f))using(var bold=new Font("Malgun Gothic",8.5f,FontStyle.Bold))using(var back=new SolidBrush(Color.FromArgb(215,30,26,20))){
   string title=Lang.T("범례")+(c>=0?" · "+Lang.T("기후")+": "+ClimateName(c):""),toggle=legendOpen?Lang.T("접기"):Lang.T("펴기");
   // two columns when one does not fit the view's height (user 2026-11-17: the title went off a short view)
   float line=17,cw=rows.Max(q=>g.MeasureString(q.Item2,font).Width)+40;int cols=24+rows.Count*line+6>size.Height-20?2:1,per=(rows.Count+cols-1)/cols;
   float w=Math.Max(g.MeasureString(title,bold).Width+g.MeasureString(toggle,font).Width+28,legendOpen?cw*cols:0),h=24+(legendOpen?per*line+6:0);
   float x=10,y=size.Height-h-10;g.FillRectangle(back,x,y,w,h);
   g.DrawString(title,bold,Brushes.Ivory,x+8,y+5);var ts=g.MeasureString(toggle,font);
   legendHeader=new RectangleF(x,y,w,22);
   using(var edge=new Pen(Color.FromArgb(200,170,120),1))g.DrawRectangle(edge,x+w-ts.Width-14,y+3,ts.Width+8,17);
   g.DrawString(toggle,font,Brushes.Gold,x+w-ts.Width-10,y+5);
   if(!legendOpen)return;
   float top=y+26,r=top,x0=x;int n=0;
   foreach(var row in rows){if(n>0&&n%per==0){x+=cw;r=top;}n++;
    using(var b=new SolidBrush(row.Item1)){if(row.Item3){g.FillEllipse(b,x+10,r+2,11,11);g.DrawEllipse(Pens.White,x+10,r+2,11,11);}else g.FillPolygon(b,new[]{new PointF(x+15.5f,r+2),new PointF(x+23,r+7.5f),new PointF(x+15.5f,r+13),new PointF(x+8,r+7.5f)});}
    g.DrawString(row.Item2,font,Brushes.Ivory,x+30,r);r+=line;}
   x=x0;
  }
 }
 PointF[] Diamond(PointF c,float hw){return new[]{new PointF(c.X,c.Y-hw/2),new PointF(c.X+hw,c.Y),new PointF(c.X,c.Y+hw/2),new PointF(c.X-hw,c.Y)};}
 public void Draw(Graphics g,Size size){g.Clear(BackColor);if(Data==null)return;float hw=HalfWidth(size);g.SmoothingMode=SmoothingMode.None;var brushes=new Dictionary<string,SolidBrush>();using(var changedEdge=new Pen(Color.FromArgb(215,244,211,116),.7f))using(var protectedFill=new SolidBrush(Color.FromArgb(90,92,39,27))){for(int y=0;y<Data.height;y++)for(int x=0;x<Data.width;x++){PointF c=TilePoint(x,y,size);if(c.X+hw<0||c.X-hw>size.Width||c.Y+hw/2<0||c.Y-hw/2>size.Height)continue;string k=Kind(x,y);SolidBrush brush;if(!brushes.TryGetValue(k,out brush)){brush=new SolidBrush(TerrainColor(k,Data.climate));brushes[k]=brush;}var polygon=Diamond(c,hw+.15f);g.FillPolygon(brush,polygon);if(edits.ContainsKey(y*Data.width+x)&&hw>=3)g.DrawPolygon(changedEdge,polygon);if(ShowProtected&&Protected(x,y))g.FillPolygon(protectedFill,polygon);if(k=="rock"&&hw>=5){using(var ridge=new Pen(Color.FromArgb(170,197,190,170),1))g.DrawLines(ridge,new[]{new PointF(c.X-hw/2,c.Y+hw/5),new PointF(c.X,c.Y-hw/3),new PointF(c.X+hw/2,c.Y+hw/5)});}}}foreach(var b in brushes.Values)b.Dispose();if(hover.X>=0&&hover.Y>=0&&hover.X<Data.width&&hover.Y<Data.height){using(var p=new Pen(Protected(hover.X,hover.Y)?Color.OrangeRed:Color.Ivory,1.4f)){int low=-(BrushSize/2);for(int dy=low;dy<low+BrushSize;dy++)for(int dx=low;dx<low+BrushSize;dx++){int x=hover.X+dx,y=hover.Y+dy;if(x>=0&&y>=0&&x<Data.width&&y<Data.height)g.DrawPolygon(p,Diamond(TilePoint(x,y,size),hw));}}}DrawPoints(g,size);DrawLegend(g,size);using(var font=new Font("Malgun Gothic",9)){string hint=Lang.T(ReadOnly?"실제 도시 지형 미리보기 · 휠로 확대":"왼쪽: 지형 칠하기  |  오른쪽: 지도 이동  |  휠: 확대·축소");g.DrawString(hint,font,Brushes.Ivory,Math.Max(12,size.Width-g.MeasureString(hint,font).Width-12),12);}}   // top right: the legend (bottom left) reaches the top of a short view (user 2026-11-17)
 protected override void OnPaint(PaintEventArgs e){Draw(e.Graphics,ClientSize);}
 protected override void OnMouseDown(MouseEventArgs e){base.OnMouseDown(e);if(Data==null)return;Focus();if(e.Button==MouseButtons.Left&&legendHeader.Contains(e.Location)){legendOpen=!legendOpen;Invalidate();return;}if(e.Button==MouseButtons.Right){panning=true;panStart=e.Location;panBefore=pan;Capture=true;}else if(e.Button==MouseButtons.Left && !ReadOnly){painting=true;BeginStroke();hover=lastPaint=TileAt(e.Location,ClientSize);PaintTile(hover.X,hover.Y);Capture=true;}}
 protected override void OnMouseMove(MouseEventArgs e){base.OnMouseMove(e);if(Data==null)return;if(panning){pan=new PointF(panBefore.X+e.X-panStart.X,panBefore.Y+e.Y-panStart.Y);Invalidate();return;}hover=TileAt(e.Location,ClientSize);if(painting&&hover!=lastPaint){int steps=Math.Max(Math.Abs(hover.X-lastPaint.X),Math.Abs(hover.Y-lastPaint.Y));if(steps>0&&steps<1000)for(int i=1;i<=steps;i++)PaintTile(lastPaint.X+(hover.X-lastPaint.X)*i/steps,lastPaint.Y+(hover.Y-lastPaint.Y)*i/steps);lastPaint=hover;}if(PositionChanged!=null)PositionChanged(hover.X>=0&&hover.Y>=0&&hover.X<Data.width&&hover.Y<Data.height?"지형 좌표 "+hover.X+", "+hover.Y+(Protected(hover.X,hover.Y)?" · 보호된 칸":""):"도시 지도 바깥");Invalidate();}
 protected override void OnMouseUp(MouseEventArgs e){base.OnMouseUp(e);if(painting)EndStroke();painting=panning=false;Capture=false;}
 protected override void OnMouseLeave(EventArgs e){base.OnMouseLeave(e);if(!painting&&!panning){hover=new Point(-1,-1);Invalidate();}}
 protected override void OnMouseWheel(MouseEventArgs e){base.OnMouseWheel(e);SetZoom(Zoom*(e.Delta>0?1.15f:1/1.15f));}
 protected override bool ProcessCmdKey(ref Message msg,Keys keyData){if(keyData==(Keys.Control|Keys.Z)){Undo();return true;}return base.ProcessCmdKey(ref msg,keyData);}
}
