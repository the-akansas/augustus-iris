using System;
using System.IO;
using System.Linq;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Collections.Generic;
using System.Windows.Forms;
// The build list drawn like the game's build panel (user 2026-11-15: "friendlier, like the in-game build interface"):
// each building is a tile with the picture the game draws for it, the category buttons carry the game's own build-menu
// icons. The pictures come from the owner's game files (creator_building_pictures.py) into the private cache; without
// them the tiles show the names only. The checked list stays the one place the choice is kept: a tile only checks or
// unchecks its line there, so every rule on that list (sea limits, the probes) still applies.
class BuildingTile : Control {
 public BuildingChoice Choice;public Image Picture;public bool Allowed,Blocked;public Action Toggle;
 protected override void OnClick(EventArgs e){base.OnClick(e);if(Toggle!=null)Toggle();}
 static readonly Color Card=Color.FromArgb(249,243,227),CardOff=Color.FromArgb(222,214,196),Edge=Color.FromArgb(150,128,92),Green=Color.FromArgb(58,122,58),Red=Color.FromArgb(150,48,40);
 public BuildingTile(){SetStyle(ControlStyles.AllPaintingInWmPaint|ControlStyles.OptimizedDoubleBuffer|ControlStyles.UserPaint|ControlStyles.ResizeRedraw,true);Size=new Size(120,104);Margin=new Padding(4);Cursor=Cursors.Hand;}
 protected override void OnPaint(PaintEventArgs e){
  var g=e.Graphics;g.SmoothingMode=SmoothingMode.AntiAlias;g.InterpolationMode=InterpolationMode.NearestNeighbor;
  var box=new Rectangle(0,0,Width-1,Height-1);
  using(var back=new SolidBrush(Allowed?Card:CardOff))g.FillRectangle(back,box);
  using(var pen=new Pen(Allowed?Green:Edge,Allowed?2:1))g.DrawRectangle(pen,Allowed?new Rectangle(1,1,Width-3,Height-3):box);
  var area=new Rectangle(6,4,Width-12,60);
  if(Picture!=null){
   float k=Math.Min(1f,Math.Min(area.Width/(float)Picture.Width,area.Height/(float)Picture.Height));
   int w=Math.Max(1,(int)(Picture.Width*k)),h=Math.Max(1,(int)(Picture.Height*k));var at=new Rectangle(area.X+(area.Width-w)/2,area.Bottom-h,w,h);
   if(Allowed)g.DrawImage(Picture,at);
   else using(var faded=new ImageAttributes()){   // a refused building: grey and pale, as the game greys a locked button
    float[][] m={new float[]{.3f,.3f,.3f,0,0},new float[]{.59f,.59f,.59f,0,0},new float[]{.11f,.11f,.11f,0,0},new float[]{0,0,0,.55f,0},new float[]{0,0,0,0,1}};
    faded.SetColorMatrix(new ColorMatrix(m));g.DrawImage(Picture,at,0,0,Picture.Width,Picture.Height,GraphicsUnit.Pixel,faded);}
  }
  // the mark in the corner, drawn (no symbol characters): a tick when allowed, a bar when refused
  var mark=new Rectangle(Width-22,5,16,16);
  if(Allowed){using(var b=new SolidBrush(Green))g.FillEllipse(b,mark);using(var p=new Pen(Color.White,2.2f))g.DrawLines(p,new[]{new Point(mark.X+4,mark.Y+8),new Point(mark.X+7,mark.Y+11),new Point(mark.X+12,mark.Y+5)});}
  else{using(var b=new SolidBrush(Red))g.FillEllipse(b,mark);using(var p=new Pen(Color.White,2.2f))g.DrawLine(p,mark.X+4,mark.Y+8,mark.X+12,mark.Y+8);}
  var text=new Rectangle(3,66,Width-6,Height-68);string name=Choice==null?"":Choice.name;
  if(Blocked)name=Lang.T(name.Replace(" (해상 교역 불가)",""))+"\n"+Lang.T("해상 교역 불가");else name=Lang.T(name);   /* the building's name in the editor's language */
  TextRenderer.DrawText(g,name,Font,text,Allowed?Color.FromArgb(40,35,29):Color.FromArgb(110,100,88),TextFormatFlags.HorizontalCenter|TextFormatFlags.Top|TextFormatFlags.WordBreak|TextFormatFlags.EndEllipsis);
 }
}
partial class ScenarioCreator {
 FlowLayoutPanel buildingTiles=new FlowLayoutPanel{Dock=DockStyle.Fill,AutoScroll=true,BackColor=Color.FromArgb(214,199,163),Padding=new Padding(4),BorderStyle=BorderStyle.FixedSingle};
 Dictionary<int,BuildingTile> tileOf=new Dictionary<int,BuildingTile>();
 Dictionary<int,Image> buildingPictures;Dictionary<int,Image> menuPictures=new Dictionary<int,Image>();
 // The game's build-menu buttons, in its order: housing, water, clear land, roads, administration, entertainment,
 // education, religion, engineering, security, health, industry (group 92, building_pictures.h).
 static readonly Dictionary<string,int> CategoryButton=new Dictionary<string,int>{
  {"주택",0},{"물 공급",1},{"도로",3},{"행정",4},{"총독 관저",4},{"조각상",4},{"공원",4},{"나무",4},{"정원 길",4},{"정원",4},{"오락",5},{"교육",6},
  {"종교",7},{"소형 신전",7},{"대형 신전",7},{"대신전",7},{"성소",7},{"시설",8},{"치안과 군사",9},{"군단 요새",9},{"보건",10},{"산업",11},{"농장",11},{"원자재",11},{"공방",11}};
 // Shrunk once, at load: a tile then only copies its picture (drawing 150 large pictures scaled on every repaint was slow).
 static Image Thumbnail(Image picture,int width,int height){float k=Math.Min(1f,Math.Min(width/(float)picture.Width,height/(float)picture.Height));if(k>=1f)return picture;
  var small=new Bitmap(Math.Max(1,(int)(picture.Width*k)),Math.Max(1,(int)(picture.Height*k)));using(var g=Graphics.FromImage(small)){g.InterpolationMode=InterpolationMode.HighQualityBicubic;g.PixelOffsetMode=PixelOffsetMode.HighQuality;g.DrawImage(picture,0,0,small.Width,small.Height);}picture.Dispose();return small;}
 static Image LoadPicture(string path){using(var stream=new MemoryStream(File.ReadAllBytes(path)))return new Bitmap(Image.FromStream(stream));}
 // The pictures are made from the owner's own game files (the engine draws them the first time, a few seconds) and
 // read from the cache after that. Both happen off the window's thread, started when the editor opens, so opening the
 // build tab never waits (user 2026-11-15: the first click on the tab froze the editor). Until they are there, the
 // tiles show the names, as without pictures.
 System.Threading.Tasks.Task picturesJob;Tuple<Dictionary<int,Image>,Dictionary<int,Image>> picturesReady;
 void LoadBuildingPictures(){
  if(buildingPictures==null&&picturesReady!=null){ShowBuildingPictures(picturesReady.Item1,picturesReady.Item2);return;}   // made while the window had no handle yet
  if(picturesJob!=null||buildingPictures!=null)return;
  picturesJob=System.Threading.Tasks.Task.Run(()=>{
   var made=new Dictionary<int,Image>();var menu=new Dictionary<int,Image>();
   try{
    var raw=Json.Deserialize<Dictionary<string,object>>(RunPython("creator_building_pictures.py",""));
    var map=raw["buildings"] as Dictionary<string,object>;if(map!=null)foreach(var kv in map){try{made[int.Parse(kv.Key)]=Thumbnail(LoadPicture(Convert.ToString(kv.Value)),108,60);}catch{}}
    map=raw["menu"] as Dictionary<string,object>;if(map!=null)foreach(var kv in map){try{menu[int.Parse(kv.Key)]=LoadPicture(Convert.ToString(kv.Value));}catch{}}
   }catch{}   // no pictures: the names alone, as before
   picturesReady=Tuple.Create(made,menu);
   try{if(!IsDisposed&&IsHandleCreated)BeginInvoke((Action)(()=>{if(buildingPictures==null)ShowBuildingPictures(made,menu);}));}catch(InvalidOperationException){}   // else: the next visit of the tab
  });
 }
 void ShowBuildingPictures(Dictionary<int,Image> made,Dictionary<int,Image> menu){
  buildingPictures=made;foreach(var kv in menu)menuPictures[kv.Key]=kv.Value;
  foreach(Control c in categories.Controls){var b=c as Button;int n;Image icon;if(b==null||!CategoryButton.TryGetValue((string)b.Tag,out n)||!menuPictures.TryGetValue(n,out icon))continue;b.Image=icon;b.ImageAlign=ContentAlignment.MiddleLeft;b.TextImageRelation=TextImageRelation.ImageBeforeText;b.TextAlign=ContentAlignment.MiddleLeft;b.Height=38;}
  foreach(var t in tileOf.Values){Image p;buildingPictures.TryGetValue(t.Choice.id,out p);t.Picture=p;t.Invalidate();}
 }
 BuildingTile TileFor(BuildingChoice b){
  BuildingTile t;if(tileOf.TryGetValue(b.id,out t))return t;
  t=new BuildingTile{Font=new Font("Malgun Gothic",9)};Image p=null;if(buildingPictures!=null)buildingPictures.TryGetValue(b.id,out p);t.Picture=p;
  int id=b.id;t.Toggle=()=>{int i=BuildingIndex(id);if(i>=0)buildings.SetItemChecked(i,!buildings.GetItemChecked(i));};
  tileOf[b.id]=t;return t;
 }
 // Probe: a tile click changes the city's list and the tile, and a second click undoes it.
 void ProbeBuildingTiles(){
  var tile=buildingTiles.Controls.OfType<BuildingTile>().FirstOrDefault();if(tile==null)throw new Exception("Building tiles missing");
  var slot=project.slots[slotPicker.SelectedIndex];bool before=slot.allowed_buildings.Contains(tile.Choice.id);
  tile.Toggle();if(slot.allowed_buildings.Contains(tile.Choice.id)==before||tile.Allowed==before)throw new Exception("Building tile click failed");
  tile.Toggle();if(slot.allowed_buildings.Contains(tile.Choice.id)!=before||tile.Allowed!=before)throw new Exception("Building tile undo failed");
  if(buildingTiles.Controls.Count!=buildings.Items.Count)throw new Exception("Building tiles differ from the list");
 }
 int BuildingIndex(int id){for(int i=0;i<buildings.Items.Count;i++)if(((BuildingChoice)buildings.Items[i]).id==id)return i;return -1;}
 // Called after the checked list was filled: the same buildings, in the same order, as tiles.
 void ShowBuildingTiles(){
  buildingTiles.SuspendLayout();buildingTiles.Controls.Clear();
  for(int i=0;i<buildings.Items.Count;i++){var b=(BuildingChoice)buildings.Items[i];var t=TileFor(b);t.Choice=b;t.Allowed=buildings.GetItemChecked(i);t.Blocked=b.name.EndsWith(" (해상 교역 불가)");buildingTiles.Controls.Add(t);t.Invalidate();}
  buildingTiles.ResumeLayout();
 }
 void BuildingTileChecked(ItemCheckEventArgs e){var b=(BuildingChoice)buildings.Items[e.Index];BuildingTile t;if(tileOf.TryGetValue(b.id,out t)){t.Allowed=e.NewValue==CheckState.Checked;t.Invalidate();}}
}
