using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using System.Windows.Forms;

/* Multilingual scenario creator (user 2026-11-14). The creator is written in Korean; what it shows is translated at
 * the moment it is shown, with the game's own catalogs (Augustus/i18n/<code>.tsv, built from i18n/review.csv), so
 * the code keeps comparing and storing its Korean texts as before:
 *  - a control's Text (labels, buttons, tabs, read-only text boxes, the window title) is replaced when it is set;
 *  - list and combo items, grid cells and grid drop-downs are translated only for display (Format events);
 *  - list views, tool tips, context menus, message boxes, file dialogs and text drawn on the map go through T().
 * What the person types (titles, briefings, numbers) is never touched. The language is the game's own setting
 * (설정 > 화면 언어, mp_language in augustus.ini); AUGUSTUS_CREATOR_LANG=en|ru|de|es|fr overrides it for tests.
 * Translation works like the game's (src/core/mp_i18n.c): the whole text, then line by line exact texts, then
 * templates with {0} {1} / %d %s slots (a slot that is itself a known text is translated as well), and as a last
 * resort known phrases inside a line. Anything unknown stays Korean. */
static class Lang {
 public static string Code="ko";
 public static bool EditorChoice=true;   // the editor's own language box counts (the editor only)
 public static readonly string[] Names={"한국어","English","Русский","Deutsch","Español","Français"};   // same order as Codes and the game's list
 public static string ChoiceFile(string root){return Path.Combine(root,"creator-language.txt");}
 public static int Index{get{return Math.Max(0,Array.IndexOf(Codes,Code));}}
 // Editions (user 2026-11-14): a language is offered only when its catalog ships (Augustus/i18n/<code>.tsv); Korean always.
 // edition.txt (2026-11-15, tools/make_release.py): the languages of this edition; the English edition has no Korean.
 static string[] Edition(string root){try{string f=Path.Combine(root,"i18n","edition.txt");if(File.Exists(f))return File.ReadAllText(f,Encoding.UTF8).Split(new[]{' ',',','\r','\n'},StringSplitOptions.RemoveEmptyEntries);}catch(Exception){}return null;}
 public static int[] Available(string root){
  var edition=Edition(root);var list=new List<int>();
  for(int i=0;i<Codes.Length;i++)if((edition==null||edition.Contains(Codes[i]))&&(i==0||File.Exists(Path.Combine(root,"i18n",Codes[i]+".tsv"))))list.Add(i);
  if(list.Count==0)list.Add(0);return list.ToArray();
 }
 public static void Choose(string root,int index){File.WriteAllText(ChoiceFile(root),Codes[index],new UTF8Encoding(false));}
 static readonly string[] Codes={"ko","en","ru","de","es","fr"};
 static readonly Dictionary<string,string> exact=new Dictionary<string,string>(StringComparer.Ordinal);
 class Template{public string[] pieces;public int[] order;public string value;public int literal;}
 static readonly List<Template> templates=new List<Template>();
 static readonly Dictionary<char,List<string>> phrases=new Dictionary<char,List<string>>();
 static readonly Dictionary<string,string> cache=new Dictionary<string,string>(StringComparer.Ordinal);
 public static bool Active{get{return exact.Count>0||templates.Count>0;}}

 static bool Hangul(string s){if(string.IsNullOrEmpty(s))return false;foreach(char c in s)if(c>='가'&&c<='힣')return true;return false;}

 public static void Init(string root,bool keepKorean){
  if(keepKorean)return;   // self checks compare Korean texts
  string code=Detect(root);var offered=Available(root);
  // Nothing chosen yet, or not in this edition: the edition's first language (edition.txt order: the Global edition
  // lists English first, user 2026-11-16); without edition.txt the first one offered.
  if(code==null||!offered.Contains(Array.IndexOf(Codes,code))){var edition=Edition(root);code=(edition==null?null:edition.FirstOrDefault(c=>offered.Contains(Array.IndexOf(Codes,c))))??Codes[offered[0]];}
  if(code=="ko")return;
  string file=Path.Combine(root,"i18n",code+".tsv");
  if(!File.Exists(file))return;
  try{Load(file);}catch(Exception){exact.Clear();templates.Clear();phrases.Clear();return;}
  if(!Active)return;
  Code=code;
  Application.Idle+=(s,e)=>{foreach(Form f in Application.OpenForms.Cast<Form>().ToArray())Attach(f);RefreshLists();};
 }

 // The game's language: AUGUSTUS_CREATOR_LANG, else mp_language in the game's augustus.ini (1 ko, 2 en, 3 ru, 4 de, 5 es, 6 fr).
 static string Detect(string root){
  string forced=Environment.GetEnvironmentVariable("AUGUSTUS_CREATOR_LANG");
  if(!string.IsNullOrEmpty(forced)&&Codes.Contains(forced))return forced;
  // The editor's own choice (the language box at the top, user 2026-11-14) comes before the game's setting.
  // The launchers (NetworkLauncher.cs, AutosaveSettings.cs) follow the game only: EditorChoice=false.
  if(EditorChoice)try{string own=ChoiceFile(root);if(File.Exists(own)){string code=File.ReadAllText(own,Encoding.UTF8).Trim();if(Codes.Contains(code))return code;}}catch(Exception){}
  var folders=new List<string>();
  string profile=Path.Combine(root,"user-profile");
  try{string marker=Path.Combine(profile,"user_dir.txt");if(File.Exists(marker)){string dir=File.ReadAllText(marker,Encoding.UTF8).Trim().Trim('\0');folders.Add(dir.Length>0?dir:root);}}catch(Exception){}
  folders.Add(profile);folders.Add(root);
  foreach(string dir in folders){
   foreach(string ini in new[]{Path.Combine(dir,"config","augustus.ini"),Path.Combine(dir,"augustus.ini")}){
    try{
     if(!File.Exists(ini))continue;
     foreach(string line in File.ReadAllLines(ini)){
      int eq=line.IndexOf('=');if(eq<0||line.Substring(0,eq).Trim()!="mp_language")continue;
      int value;if(int.TryParse(line.Substring(eq+1).Trim(),out value)&&value>=1&&value<=Codes.Length)return Codes[value-1];
      return null;   // 0: not chosen in the game yet
     }
    }catch(Exception){}
   }
  }
  return null;
 }

 static string Unescape(string s){
  var b=new StringBuilder(s.Length);
  for(int i=0;i<s.Length;i++){if(s[i]=='\\'&&i+1<s.Length){char c=s[++i];b.Append(c=='n'?'\n':c=='t'?'\t':c);}else b.Append(s[i]);}
  return b.ToString();
 }
 static string CodeUnescape(string s){
  var b=new StringBuilder(s.Length);
  for(int i=0;i<s.Length;i++){
   if(s[i]=='\\'&&i+1<s.Length&&"nrt\"\\".IndexOf(s[i+1])>=0){char c=s[++i];b.Append(c=='n'?'\n':c=='r'?'\r':c=='t'?'\t':c);}
   else b.Append(s[i]);
  }
  return b.ToString();
 }
 // Length of a slot at s[i] ({n} or a printf spec), 0 if none; number: n for {n}, -1 for printf.
 static int SlotAt(string s,int i,out int number){
  number=-1;
  if(s[i]=='{'&&i+1<s.Length&&char.IsDigit(s[i+1])){int j=i+1,n=0;while(j<s.Length&&char.IsDigit(s[j]))n=n*10+(s[j++]-'0');if(j<s.Length&&s[j]=='}'){number=n;return j+1-i;}return 0;}
  if(s[i]!='%'||i+1>=s.Length||s[i+1]=='%')return 0;
  int k=i+1;while(k<s.Length&&"-+ #0".IndexOf(s[k])>=0)k++;while(k<s.Length&&char.IsDigit(s[k]))k++;
  if(k<s.Length&&s[k]=='.'){k++;while(k<s.Length&&char.IsDigit(s[k]))k++;}
  while(k<s.Length&&(s[k]=='l'||s[k]=='h'||s[k]=='z'))k++;
  if(k<s.Length&&"diuxXsScfgeEp".IndexOf(s[k])>=0)return k+1-i;
  return 0;
 }
 static void Load(string file){
  foreach(string raw in File.ReadAllLines(file,Encoding.UTF8)){
   if(raw.Length==0||raw[0]=='#')continue;
   int tab=raw.IndexOf('\t');if(tab<=0||tab+1>=raw.Length)continue;
   string key=Unescape(raw.Substring(0,tab)),value=Unescape(raw.Substring(tab+1));
   // texts taken from C# code keep their escapes in the catalog (\n \r \" as written): turn them into the text
   if(key.IndexOf('\\')>=0){key=CodeUnescape(key);value=CodeUnescape(value);}
   key=key.Replace("\r\n","\n");value=value.Replace("\r\n","\n");
   var t=new Template{order=new int[8]};var pieces=new List<string>();int start=0,printf=0,slots=0;bool bad=false;
   for(int i=0;i<key.Length;){
    int number,n=SlotAt(key,i,out number);
    if(n==0){i+=key[i]=='%'&&i+1<key.Length&&key[i+1]=='%'?2:1;continue;}
    if(slots==8){bad=true;break;}
    pieces.Add(key.Substring(start,i-start).Replace("%%","%"));t.order[slots++]=number>=0?number:printf++;
    i+=n;start=i;
   }
   if(bad)continue;
   if(slots==0){exact[key]=value;AddPhrase(key);continue;}
   pieces.Add(key.Substring(start).Replace("%%","%"));
   t.pieces=pieces.ToArray();t.value=value;t.literal=t.pieces.Sum(p=>p.Length);
   Array.Resize(ref t.order,slots);templates.Add(t);
  }
  // A text of several lines is also known line by line, so a line still translates when the creator adds
  // another line to it (cityHelp.Text+="\n원본: ..."). Only when both sides have the same number of lines.
  foreach(var pair in exact.ToArray()){
   if(pair.Key.IndexOf('\n')<0)continue;
   string[] ko=pair.Key.Split('\n'),tr=pair.Value.Split('\n');
   if(ko.Length!=tr.Length)continue;
   for(int i=0;i<ko.Length;i++)if(Hangul(ko[i])&&!exact.ContainsKey(ko[i])){exact[ko[i]]=tr[i];AddPhrase(ko[i]);}
  }
  templates.Sort((a,b)=>b.literal-a.literal);
  foreach(var list in phrases.Values)list.Sort((a,b)=>b.Length-a.Length);
 }
 static void AddPhrase(string key){
  // phrases used inside longer lines: Korean, at least two letters, one line, not just a particle
  if(key.IndexOf('\n')>=0||key.Trim().Length<2||!Hangul(key))return;
  List<string> list;if(!phrases.TryGetValue(key[0],out list))phrases[key[0]]=list=new List<string>();
  list.Add(key);
 }

 public static string T(string text){return Translate(text,0);}
 public static string T(object value){return value==null?null:Translate(Convert.ToString(value),0);}

 static string Translate(string text,int depth){
  if(!Active||!Hangul(text))return text;
  string cached;if(depth==0&&cache.TryGetValue(text,out cached))return cached;
  string result=TranslateText(text,depth);
  if(depth==0){if(cache.Count>20000)cache.Clear();cache[text]=result;}
  return result;
 }
 static string TranslateText(string text,int depth){
  string whole=text.Replace("\r\n","\n"),found;
  if(exact.TryGetValue(whole,out found))return Restore(found,text);
  // line by line, keeping the line ends as they were
  var output=new StringBuilder(text.Length+16);int i=0;
  while(i<=text.Length){
   int end=text.IndexOf('\n',i);string line=end<0?text.Substring(i):text.Substring(i,end-i);
   bool cr=line.EndsWith("\r");if(cr)line=line.Substring(0,line.Length-1);
   output.Append(TranslateLine(line,depth));
   if(end<0)break;
   output.Append(cr?"\r\n":"\n");i=end+1;
  }
  return output.ToString();
 }
 static string Restore(string translated,string original){return original.Contains("\r\n")?translated.Replace("\n","\r\n"):translated;}

 static string TranslateLine(string line,int depth){
  if(!Hangul(line))return line;
  string found;
  if(exact.TryGetValue(line,out found))return found;
  // keep leading and trailing blanks (indented list lines, " · " joins)
  string core=line.Trim();
  if(core.Length!=line.Length&&exact.TryGetValue(core,out found)){int lead=line.IndexOf(core,StringComparison.Ordinal);return line.Substring(0,lead)+found+line.Substring(lead+core.Length);}
  string viaTemplate=ByTemplate(line,depth);
  if(viaTemplate!=null)return viaTemplate;
  return ByPhrases(line);
 }
 static string ByTemplate(string line,int depth){
  string first=null;
  foreach(var t in templates){
   if(!line.StartsWith(t.pieces[0],StringComparison.Ordinal))continue;
   int p=t.pieces[0].Length,slots=t.order.Length;var starts=new int[slots];var lengths=new int[slots];bool ok=true;
   for(int k=0;k<slots&&ok;k++){
    string next=t.pieces[k+1];int end;
    if(k+1==slots){end=line.Length-next.Length;if(end<p||!line.EndsWith(next,StringComparison.Ordinal))end=-1;}
    else end=next.Length>0&&p+1<=line.Length?line.IndexOf(next,p+1,StringComparison.Ordinal):-1;
    if(end<0||end==p){ok=false;break;}
    starts[k]=p;lengths[k]=end-p;p=end+next.Length;
   }
   if(!ok||p!=line.Length)continue;
   var output=new StringBuilder(t.value.Length+32);
   for(int v=0;v<t.value.Length;){
    int number=-1,n=t.value[v]=='{'?SlotAt(t.value,v,out number):0;
    if(n>0&&number>=0){
     for(int k=0;k<slots;k++)if(t.order[k]==number){
      string piece=line.Substring(starts[k],lengths[k]);
      // a slot holding a known text (a city or a building name, another sentence) is shown translated too
      string shown=depth<3&&Hangul(piece)?Translate(piece,depth+1):piece;
      // a slot holding a list ("점토, 목재, 올리브"): each item on its own, so a long list is not cut off by the depth limit
      if(depth<3&&Hangul(shown)&&piece.Contains(", "))shown=string.Join(", ",piece.Split(new[]{", "},StringSplitOptions.None).Select(x=>Hangul(x)?Translate(x,depth+1):x));
      output.Append(shown);break;
     }
     v+=n;
    }else output.Append(t.value[v++]);
   }
   // several templates can fit one line: the first whose result has no Korean left wins (2026-11-16: "모드: 협동 — ..."
   // was cut by a longer template in the wrong places); otherwise the first fit, as before
   string done=output.ToString();if(!Hangul(done))return done;if(first==null)first=done;
  }
  return first;
 }
 static string ByPhrases(string line){
  var output=new StringBuilder(line.Length+16);bool changed=false;
  for(int i=0;i<line.Length;){
   List<string> list;string hit=null;
   if(phrases.TryGetValue(line[i],out list))foreach(string key in list)if(string.CompareOrdinal(line,i,key,0,key.Length)==0){hit=key;break;}
   if(hit!=null){output.Append(exact[hit]);i+=hit.Length;changed=true;}
   else output.Append(line[i++]);
  }
  return changed?output.ToString():line;
 }

 // ---------- display hooks ----------
 static readonly HashSet<object> attached=new HashSet<object>();
 static readonly List<ListView> lists=new List<ListView>();
 static bool settingText;

 // A window is translated before it is first drawn (2026-11-14): the idle hook above only reaches a window after it
 // is on screen, which could show its Korean texts for a moment.
 public static T Shown<T>(T window) where T:Control{Attach(window);return window;}
 public static void Attach(Control c){
  if(!Active||c==null||c.IsDisposed||attached.Contains(c))return;
  attached.Add(c);c.Disposed+=(s,e)=>{attached.Remove(s);var lv=s as ListView;if(lv!=null)lists.Remove(lv);};
  if(c is UpDownBase)return;   // a number box: its inner text box shows the number
  ApplyText(c);
  c.TextChanged+=(s,e)=>ApplyText((Control)s);
  var button=c as ButtonBase;
  if(button!=null){Fit(button);button.SizeChanged+=(s,e)=>Fit((ButtonBase)s);button.FontChanged+=(s,e)=>{if(!fitting)baseFonts.Remove((Control)s);Fit((ButtonBase)s);};}
  var lc=c as ListControl;
  if(lc!=null)EnableFormat(lc);
  // Another language is longer than Korean (user 2026-11-17: the Global edition's editor cut many texts). An open list
  // is as wide as its longest item; a fixed label ends with '...' and shows the whole text when pointed at; a label
  // column of a form grows to its longest label; a grid's column to its header.
  var picker=c as ComboBox;if(picker!=null)picker.DropDown+=(s,e)=>WidenList((ComboBox)s);
  var fixedLabel=c as Label;if(fixedLabel!=null&&!fixedLabel.AutoSize)fixedLabel.AutoEllipsis=true;
  var table=c as TableLayoutPanel;if(table!=null){table.Layout+=(s,e)=>WidenLabelColumns((TableLayoutPanel)s);}
  var grid=c as DataGridView;
  if(grid!=null){
   foreach(DataGridViewColumn column in grid.Columns){column.HeaderText=T(column.HeaderText);WidenHeader(grid,column);}
   grid.ColumnAdded+=(s,e)=>{e.Column.HeaderText=T(e.Column.HeaderText);WidenHeader((DataGridView)s,e.Column);};
   grid.CellFormatting+=(s,e)=>{var text=e.Value as string;if(Hangul(text)){e.Value=T(text);e.FormattingApplied=true;}};
   grid.EditingControlShowing+=(s,e)=>{var combo=e.Control as ComboBox;if(combo!=null&&attached.Add(combo))EnableFormat(combo);};
  }
  var list=c as ListView;
  if(list!=null){lists.Add(list);TranslateList(list);}
  if(c.ContextMenuStrip!=null)AttachMenu(c.ContextMenuStrip);
  AttachFields(c);
  c.ControlAdded+=(s,e)=>Attach(e.Control);
  foreach(Control child in c.Controls)Attach(child);
 }
 // Items show through the Format event. A list without a window yet gets its item texts from it when the window is
 // made, so only the switch is set (no refresh, no selection events); a list already on screen with items is
 // refreshed once (ListControl.RefreshItems through the FormattingEnabled switch), which keeps its selection.
 static readonly FieldInfo formattingField=typeof(ListControl).GetField("formattingEnabled",BindingFlags.Instance|BindingFlags.NonPublic);
 static void EnableFormat(ListControl lc){
  lc.Format+=FormatItem;
  var box=lc as ListBox;var combo=lc as ComboBox;
  int count=box!=null?box.Items.Count:combo!=null?combo.Items.Count:0;
  if(lc.IsHandleCreated&&count>0){lc.FormattingEnabled=false;lc.FormattingEnabled=true;return;}
  if(!lc.FormattingEnabled){if(formattingField!=null&&formattingField.FieldType==typeof(bool))formattingField.SetValue(lc,true);else lc.FormattingEnabled=true;}
 }
 static void FormatItem(object sender,ListControlConvertEventArgs e){
  string text=e.Value as string??(e.ListItem==null?null:Convert.ToString(e.ListItem));
  if(Hangul(text))e.Value=T(text);
 }
 static void ApplyText(Control c){
  if(settingText||c is ComboBox||c is UpDownBase||c.Parent is UpDownBase)return;
  var box=c as TextBoxBase;if(box!=null&&!box.ReadOnly)return;   // typed by the person: never changed
  string now=c.Text;if(!Hangul(now))return;
  string shown=T(now);if(shown==now)return;
  settingText=true;try{c.Text=shown;}finally{settingText=false;}
  var fitButton=c as ButtonBase;if(fitButton!=null)Fit(fitButton);
  var inTable=c.Parent as TableLayoutPanel;if(inTable!=null&&c is Label)WidenLabelColumns(inTable);   // its column, now that the text is longer
 }
 static void WidenList(ComboBox combo){
  if(combo.IsDisposed)return;int widest=combo.Width;
  foreach(object item in combo.Items){int w=TextRenderer.MeasureText(combo.GetItemText(item)??"",combo.Font).Width+SystemInformation.VerticalScrollBarWidth+12;if(w>widest)widest=w;}
  var screen=Screen.FromControl(combo).WorkingArea;combo.DropDownWidth=Math.Min(widest,Math.Max(combo.Width,screen.Width-40));
 }
 static void WidenHeader(DataGridView grid,DataGridViewColumn column){
  if(column.AutoSizeMode==DataGridViewAutoSizeColumnMode.Fill)return;
  int need=TextRenderer.MeasureText(column.HeaderText??"",grid.ColumnHeadersDefaultCellStyle.Font??grid.Font).Width+18;
  if(need>column.Width)column.Width=Math.Min(need,320);
 }
 static readonly HashSet<TableLayoutPanel> widened=new HashSet<TableLayoutPanel>();static bool widening;
 static void WidenLabelColumns(TableLayoutPanel table){
  if(widening||table.IsDisposed)return;
  for(int col=0;col<table.ColumnStyles.Count&&col<table.ColumnCount;col++){
   var style=table.ColumnStyles[col];if(style.SizeType!=SizeType.Absolute)continue;int need=0;
   foreach(Control child in table.Controls){var label=child as Label;if(label==null||table.GetColumn(label)!=col||table.GetColumnSpan(label)>1||label.Text.Contains("\n"))continue;int w=TextRenderer.MeasureText(label.Text??"",label.Font).Width+label.Padding.Horizontal+label.Margin.Horizontal+2;if(w>need)need=w;}
   if(need>style.Width&&need<=Math.Max(style.Width*2.2f,280)){widening=true;try{style.Width=need;}finally{widening=false;}}
  }
 }
 // A fixed-size button keeps its size; a longer translation gets a smaller type (down to 70 %) instead of being cut.
 static readonly Dictionary<Control,Font> baseFonts=new Dictionary<Control,Font>();
 static readonly Dictionary<string,Font> fitFonts=new Dictionary<string,Font>();
 static bool fitting;
 static void Fit(ButtonBase b){
  if(fitting||b.AutoSize||b.Width<=12||string.IsNullOrEmpty(b.Text)||b.IsDisposed)return;
  Font start;if(!baseFonts.TryGetValue(b,out start)){start=b.Font;baseFonts[b]=start;b.Disposed+=(s,e)=>baseFonts.Remove((Control)s);}
  if(b.Parent is FlowLayoutPanel&&((FlowLayoutPanel)b.Parent).WrapContents){int want=TextRenderer.MeasureText(b.Text,start).Width+b.Padding.Horizontal+18;if(want>b.Width&&want<=Math.Max(b.Width*2,240)){fitting=true;try{b.Width=want;}finally{fitting=false;}}}   // a row that flows: wider, not smaller
  int room=b.Width-b.Padding.Horizontal-8,high=b.Height-b.Padding.Vertical-2;
  Font pick=start;
  for(float size=start.Size;size>=start.Size*0.7f;size-=0.5f){
   pick=FitFont(start,size);
   var need=TextRenderer.MeasureText(b.Text,pick,new Size(room,0),TextFormatFlags.WordBreak);
   var line=TextRenderer.MeasureText(b.Text,pick);
   if(line.Width<=room||(need.Width<=room&&need.Height<=high))break;
  }
  if(pick.Equals(b.Font))return;
  fitting=true;try{b.Font=pick;}finally{fitting=false;}
 }
 static Font FitFont(Font start,float size){
  if(Math.Abs(size-start.Size)<0.01f)return start;
  string key=start.FontFamily.Name+"|"+size+"|"+(int)start.Style+"|"+(int)start.Unit;
  Font f;if(!fitFonts.TryGetValue(key,out f)){f=new Font(start.FontFamily,size,start.Style,start.Unit);fitFonts[key]=f;}
  return f;
 }
 static void TranslateList(ListView list){
  foreach(ColumnHeader column in list.Columns)if(Hangul(column.Text))column.Text=T(column.Text);
  foreach(ListViewItem item in list.Items)foreach(ListViewItem.ListViewSubItem sub in item.SubItems)if(Hangul(sub.Text)){string t=T(sub.Text);if(t!=sub.Text)sub.Text=t;}
 }
 public static void Refresh(ListView list){if(Active&&list!=null&&!list.IsDisposed)TranslateList(list);}   // right after a list is filled, not at the next idle
 static void RefreshLists(){foreach(var list in lists.ToArray())if(!list.IsDisposed)TranslateList(list);}

 // Tool tips and context menus the creator keeps in fields (not in the control tree).
 static void AttachFields(object owner){
  if(owner.GetType().Assembly!=typeof(Lang).Assembly)return;
  foreach(var field in owner.GetType().GetFields(BindingFlags.Instance|BindingFlags.NonPublic|BindingFlags.Public)){
   object value;try{value=field.GetValue(owner);}catch(Exception){continue;}
   var tip=value as ToolTip;if(tip!=null)AttachTip(tip);
   var menu=value as ContextMenuStrip;if(menu!=null)AttachMenu(menu);
  }
 }
 public static ToolTip AttachTip(ToolTip tip){
  if(!Active||tip==null||!attached.Add(tip))return tip;
  tip.OwnerDraw=true;
  tip.Popup+=(s,e)=>{string text=T(tip.GetToolTip(e.AssociatedControl));if(string.IsNullOrEmpty(text))return;var size=TextRenderer.MeasureText(text,SystemFonts.StatusFont,new Size(480,0),TextFormatFlags.WordBreak);e.ToolTipSize=new Size(size.Width+10,size.Height+8);};
  tip.Draw+=(s,e)=>{e.DrawBackground();e.DrawBorder();TextRenderer.DrawText(e.Graphics,T(e.ToolTipText),SystemFonts.StatusFont,new Rectangle(e.Bounds.X+5,e.Bounds.Y+4,e.Bounds.Width-10,e.Bounds.Height-8),SystemColors.InfoText,TextFormatFlags.WordBreak);};
  return tip;
 }
 static void AttachMenu(ToolStrip menu){
  if(!attached.Add(menu))return;
  menu.ItemAdded+=(s,e)=>TranslateItem(e.Item);
  var drop=menu as ToolStripDropDown;if(drop!=null)drop.Opening+=(s,e)=>{foreach(ToolStripItem item in drop.Items)TranslateItem(item);};
  foreach(ToolStripItem item in menu.Items)TranslateItem(item);
 }
 static void TranslateItem(ToolStripItem item){
  if(Hangul(item.Text))item.Text=T(item.Text);
  if(Hangul(item.ToolTipText))item.ToolTipText=T(item.ToolTipText);
  var drop=item as ToolStripDropDownItem;if(drop!=null)foreach(ToolStripItem child in drop.DropDownItems)TranslateItem(child);
 }
}

// MessageBox with translated text and caption: every MessageBox.Show of the creator goes through here.
static class LangBox {
 public static DialogResult Show(string text){return MessageBox.Show(Lang.T(text));}
 public static DialogResult Show(string text,string caption){return MessageBox.Show(Lang.T(text),Lang.T(caption));}
 public static DialogResult Show(string text,string caption,MessageBoxButtons buttons){return MessageBox.Show(Lang.T(text),Lang.T(caption),buttons);}
 public static DialogResult Show(string text,string caption,MessageBoxButtons buttons,MessageBoxIcon icon){return MessageBox.Show(Lang.T(text),Lang.T(caption),buttons,icon);}
 public static DialogResult Show(string text,string caption,MessageBoxButtons buttons,MessageBoxIcon icon,MessageBoxDefaultButton button){return MessageBox.Show(Lang.T(text),Lang.T(caption),buttons,icon,button);}
 public static DialogResult Show(IWin32Window owner,string text){return MessageBox.Show(owner,Lang.T(text));}
 public static DialogResult Show(IWin32Window owner,string text,string caption){return MessageBox.Show(owner,Lang.T(text),Lang.T(caption));}
 public static DialogResult Show(IWin32Window owner,string text,string caption,MessageBoxButtons buttons){return MessageBox.Show(owner,Lang.T(text),Lang.T(caption),buttons);}
 public static DialogResult Show(IWin32Window owner,string text,string caption,MessageBoxButtons buttons,MessageBoxIcon icon){return MessageBox.Show(owner,Lang.T(text),Lang.T(caption),buttons,icon);}
 public static DialogResult Show(IWin32Window owner,string text,string caption,MessageBoxButtons buttons,MessageBoxIcon icon,MessageBoxDefaultButton button){return MessageBox.Show(owner,Lang.T(text),Lang.T(caption),buttons,icon,button);}
}
