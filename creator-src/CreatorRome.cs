using System;
using System.IO;
using System.Drawing;
using System.Text.RegularExpressions;
using System.Web.Script.Serialization;
// Rome on the empire map: a fixed capital apart from P1..P8 and neutral trade cities. Shown in every mode.
// Place and keep-clear distance come from rome-capital.json (shared with scenario_check.py and the lobby, evidence in that file).
// The picture is the game's own asset UI/Empire_Icon_Roman_05: the unpacked PNG when present, otherwise cut out of the packed
// atlas named in ui.xml. Nothing here writes to a scenario; Rome cannot be moved, deleted or given a slot.
public class RomeSpec { public string name,title,description,facts,facts_detail,icon,icon_atlas,icon_file; public int x,y,keep_clear; }
public static class RomeCapital {
 public static string Root=AppDomain.CurrentDomain.BaseDirectory;
 static RomeSpec spec; static bool specRead; static Bitmap icon; static bool iconRead;
 // Every Rome text comes from rome-capital.json, the same file the lobby texts are made from.
 public static string Title{get{var s=Spec;return s!=null&&s.title!=null?s.title:"로마";}}
 public static string Summary{get{var s=Spec;return s!=null&&s.facts!=null?s.facts:"";}}
 public static string Text{get{var s=Spec;if(s==null)return Title;return Title+"\r\n\r\n"+(s.description??"")+"\r\n\r\n"+(s.facts??"")+"\r\n"+(s.facts_detail??"");}}
 public static RomeSpec Spec{get{
  if(!specRead){specRead=true;try{var s=new JavaScriptSerializer().Deserialize<RomeSpec>(File.ReadAllText(Path.Combine(Root,"rome-capital.json")));spec=s!=null&&s.keep_clear>0?s:null;}catch(Exception){spec=null;}}
  return spec;}}
 public static Bitmap Icon{get{if(!iconRead){iconRead=true;icon=LoadIcon();}return icon;}}
 static Bitmap LoadIcon(){
  var s=Spec;if(s==null)return null;
  try{if(s.icon_file!=null){var file=Path.Combine(Root,s.icon_file.Replace('/',Path.DirectorySeparatorChar));if(File.Exists(file))using(var raw=new Bitmap(file))return new Bitmap(raw);}}catch(Exception){}
  try{
   var xml=Path.Combine(Root,s.icon_atlas.Replace('/',Path.DirectorySeparatorChar));if(!File.Exists(xml))return null;
   string text=File.ReadAllText(xml);
   var sheet=Regex.Match(text,"<assetlist\\s+name=\"([^\"]+)\"");
   var layer=Regex.Match(text,"<image\\s+id=\""+Regex.Escape(s.icon)+"\"[^>]*>\\s*<layer\\s+src_x=\"(\\d+)\"\\s+src_y=\"(\\d+)\"\\s+width=\"(\\d+)\"\\s+height=\"(\\d+)\"");
   if(!sheet.Success||!layer.Success)return null;
   var png=Path.Combine(Path.GetDirectoryName(xml),sheet.Groups[1].Value+".png");if(!File.Exists(png))return null;
   var area=new Rectangle(int.Parse(layer.Groups[1].Value),int.Parse(layer.Groups[2].Value),int.Parse(layer.Groups[3].Value),int.Parse(layer.Groups[4].Value));
   using(var atlas=new Bitmap(png)){if(!new Rectangle(0,0,atlas.Width,atlas.Height).Contains(area))return null;return atlas.Clone(area,atlas.PixelFormat);}
  }catch(Exception){return null;}
 }
 // A city whose centre is closer than keep_clear sits on the Rome icon. Farther cities are fine, however near.
 public static bool TooClose(int x,int y){var s=Spec;if(s==null)return false;long dx=x-s.x,dy=y-s.y;return dx*dx+dy*dy<(long)s.keep_clear*s.keep_clear;}
 public static string Refusal{get{var s=Spec;return "로마(고정 수도) 자리와 겹치는 곳에는 도시를 둘 수 없습니다"+(s==null?".":"(로마 중심에서 "+s.keep_clear+" 이상 떨어뜨려 주세요).");}}
}
