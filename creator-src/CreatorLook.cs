using System;
using System.Drawing;
using System.Windows.Forms;
// Readability in Caesar III colours (user 2026-11-15: "the tabs and buttons sink into the colours, the scenario
// introduction / start message tabs most"). The parchment and stone stay; what is chosen now stands out the way the
// game's own panels do: a bronze tab with light lettering and a gold edge, and buttons of warm sandstone framed in
// bronze. Every tab strip of the editor is drawn this one way.
partial class ScenarioCreator {
 static readonly Color ButtonFace=Color.FromArgb(224,206,160),ButtonHover=Color.FromArgb(238,224,184),ButtonDown=Color.FromArgb(200,176,126),
  Bronze=Color.FromArgb(102,70,40),Gold=Color.FromArgb(214,172,82),TabIdle=Color.FromArgb(212,199,168),TabText=Color.FromArgb(252,244,222);
 void StyleTabs(Control root){
  foreach(Control c in root.Controls){
   var t=c as TabControl;
   if(t!=null && t.DrawMode!=TabDrawMode.OwnerDrawFixed){t.DrawMode=TabDrawMode.OwnerDrawFixed;t.Padding=new Point(Math.Max(t.Padding.X,16),Math.Max(t.Padding.Y,6));t.DrawItem+=DrawTab;t.SelectedIndexChanged+=(s,e)=>((Control)s).Invalidate();}
   StyleTabs(c);
  }
 }
 static void DrawTab(object sender,DrawItemEventArgs e){
  var t=(TabControl)sender;if(e.Index<0||e.Index>=t.TabPages.Count)return;
  var r=t.GetTabRect(e.Index);bool chosen=e.Index==t.SelectedIndex;var g=e.Graphics;
  using(var fill=new SolidBrush(chosen?Bronze:TabIdle))g.FillRectangle(fill,r);
  if(chosen)using(var edge=new SolidBrush(Gold))g.FillRectangle(edge,r.X,r.Y,r.Width,3);
  using(var line=new Pen(chosen?Bronze:Color.FromArgb(150,128,92)))g.DrawRectangle(line,r.X,r.Y,r.Width-1,r.Height-1);
  using(var font=new Font(t.Font,FontStyle.Bold))
   TextRenderer.DrawText(g,t.TabPages[e.Index].Text,font,new Rectangle(r.X,r.Y+(chosen?2:0),r.Width,r.Height),chosen?TabText:Dark,TextFormatFlags.HorizontalCenter|TextFormatFlags.VerticalCenter|TextFormatFlags.SingleLine|TextFormatFlags.NoPrefix);
 }
 // One line of controls side by side (a label, a box, a button) is drawn on one middle line, whatever each one's
 // height (user 2026-11-15: "heights all differ, align them"). A line holding stacked "label over box" groups lines
 // up its captions on one top line and puts anything else on the bottom edge, beside the boxes, not their captions.
 static readonly System.Collections.Generic.HashSet<FlowLayoutPanel> aligning=new System.Collections.Generic.HashSet<FlowLayoutPanel>();
 void AlignFlows(Control root){
  foreach(Control c in root.Controls){
   var f=c as FlowLayoutPanel;
   if(f!=null&&f.FlowDirection==FlowDirection.LeftToRight&&f.Tag as string!="aligned"){f.Tag=f.Tag??"aligned";f.Layout+=(s,e)=>AlignLine((FlowLayoutPanel)s);foreach(Control k in f.Controls)if(k is Label||k is CheckBox||k is RadioButton)k.Padding=new Padding(k.Padding.Left,0,k.Padding.Right,0);AlignLine(f);}
   AlignFlows(c);
  }
 }
 // A caption in a form table (label left, field right) stands on the middle of the field's first line.
 void AlignCaptions(Control root){
  foreach(Control c in root.Controls){
   var t=c as TableLayoutPanel;
   if(t!=null)foreach(Control k in t.Controls){
    var label=k as Label;if(label==null||!label.AutoSize||label.Dock!=DockStyle.None)continue;
    var at=t.GetCellPosition(label);if(at.Column<0||at.Row<0)continue;var right=t.GetControlFromPosition(at.Column+1,at.Row);if(right==null||right is Label)continue;
    int line=FirstLine(right);if(line<=0||line>48)continue;
    int lh=label.GetPreferredSize(Size.Empty).Height-label.Padding.Vertical;
    label.Padding=new Padding(label.Padding.Left,Math.Max(0,right.Margin.Top+(line-lh)/2-label.Margin.Top),label.Padding.Right,0);
   }
   AlignCaptions(c);
  }
 }
 static int FirstLine(Control c){
  var f=c as FlowLayoutPanel;
  if(f!=null){if(f.FlowDirection!=FlowDirection.LeftToRight)return -1;int high=0;foreach(Control k in f.Controls)high=Math.Max(high,Tall(k)+k.Margin.Vertical);return high;}
  if(c is TextBox&&((TextBox)c).Multiline)return -1;
  if(c is TextBox||c is ComboBox||c is NumericUpDown||c is CheckBox||c is Button)return Tall(c);
  return -1;
 }
 static int Tall(Control c){return c.AutoSize?c.GetPreferredSize(Size.Empty).Height:c.Height;}
 static void AlignLine(FlowLayoutPanel f){
  if(aligning.Contains(f)||f.Controls.Count<2)return;aligning.Add(f);
  try{
   // split into the lines the panel will wrap into (its width now), then align each line on its own
   var lines=new System.Collections.Generic.List<System.Collections.Generic.List<Control>>{new System.Collections.Generic.List<Control>()};
   int room=f.WrapContents&&f.ClientSize.Width>0?f.ClientSize.Width-f.Padding.Horizontal:int.MaxValue,used=0;
   foreach(Control c in f.Controls){
    if(!c.Visible&&f.Visible)continue;
    int w=(c.AutoSize?c.GetPreferredSize(Size.Empty).Width:c.Width)+c.Margin.Horizontal;
    if(used>0&&used+w>room){lines.Add(new System.Collections.Generic.List<Control>());used=0;}
    lines[lines.Count-1].Add(c);used+=w;if(f.GetFlowBreak(c)){lines.Add(new System.Collections.Generic.List<Control>());used=0;}
   }
   foreach(var line in lines){
    int high=0;bool stacked=false;
    foreach(Control c in line){high=Math.Max(high,Tall(c));var b=c as FlowLayoutPanel;if(b!=null&&b.FlowDirection==FlowDirection.TopDown)stacked=true;}
    foreach(Control c in line){
     var box=c as FlowLayoutPanel;bool group=box!=null&&box.FlowDirection==FlowDirection.TopDown;
     int h=Tall(c),spare=Math.Max(0,high-h),top=!stacked?spare/2:group?0:spare;var m=c.Margin;   // groups: captions on one line; the rest: on the boxes' bottom
     if(m.Top!=3+top||m.Bottom!=3+spare-top)c.Margin=new Padding(m.Left,3+top,m.Right,3+spare-top);
    }
   }
  }finally{aligning.Remove(f);}
 }
 static void StyleButton(Button b){b.BackColor=ButtonFace;b.ForeColor=Dark;b.FlatStyle=FlatStyle.Flat;b.FlatAppearance.BorderColor=Bronze;b.FlatAppearance.BorderSize=1;b.FlatAppearance.MouseOverBackColor=ButtonHover;b.FlatAppearance.MouseDownBackColor=ButtonDown;}
}
