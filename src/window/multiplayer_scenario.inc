/* Read-only scenario briefing. No scenario/save is loaded into the live city.
 * Drawn in an 800x600 dialog: map x 48..480, briefing column x 504..752. */
#include <math.h>
#include "assets/assets.h"
#define SCENE_X 48
#define SCENE_TEXT_X 504
#define SCENE_TEXT_W 248
#define SCENE_GRID_Y 336
#define SCENE_MAX_CITIES 40
#define SCENE_MAX_LINES 4096
#define SCENE_CITY_LINES 192
/* No page buttons or page counters: the city list and the text scroll under the original scrollbar,
 * whose thumb size tells how much is left. City list: two columns, SCENE_GRID_ROWS rows in view. */
#define SCENE_GRID_ROWS 5
#define SCENE_GRID_COL 204
#define SCENE_GRID_W 196
#define SCENE_TEXT_ROWS 19
static int scene_room;
static int scene_hall;   /* the window shows a scenario or save of the game hall (Korean edition) */
#ifdef MP_HALL
/* The hall's room window (user 2026-11-16 "이름만 보고 어찌 만드누"): the same window for a scenario or save of the server,
 * whose text the bridge asks the server for (hall-briefing.txt: '' while it comes, '0 <why>' when it cannot be shown). */
static int scene_hall_sent;static time_millis scene_hall_asked;static char scene_hall_key[128],scene_hall_said[256];
#endif
static void selector_action(const generic_button *b);
static int scene_valid,scene_city=-1,scene_city_row,scene_text_top;
static int scene_count,scene_line_count;
static int scene_dragging,scene_drag_x,scene_drag_y;
static float scene_zoom=1,scene_pan_x,scene_pan_y;
static int scene_map_y(void){return 100;}
static int scene_map_w(void){return 432;}
static int scene_map_h(void){return scene_map_w()/2;}
static int scene_in_map(int x,int y){return x>=SCENE_X && x<SCENE_X+scene_map_w() && y>=scene_map_y() && y<scene_map_y()+scene_map_h();}
static void scene_clamp(void){
 float mx=scene_map_w()*(scene_zoom-1),my=scene_map_h()*(scene_zoom-1);
 if(scene_pan_x<0)scene_pan_x=0;if(scene_pan_x>mx)scene_pan_x=mx;
 if(scene_pan_y<0)scene_pan_y=0;if(scene_pan_y>my)scene_pan_y=my;
}
static void scene_city_scrolled(void);static void scene_text_scrolled(void);
static scrollbar_type scene_city_sb={.x=SCENE_X+2*SCENE_GRID_COL-4,.y=SCENE_GRID_Y,.length=SCENE_GRID_ROWS*24,.scrollable_width=2*SCENE_GRID_COL,.elements_in_view=SCENE_GRID_ROWS,.on_scroll_callback=scene_city_scrolled,.step_size=1};
static scrollbar_type scene_text_sb={.x=SCENE_TEXT_X+SCENE_TEXT_W+4,.y=160,.length=SCENE_TEXT_ROWS*18,.scrollable_width=SCENE_TEXT_W+8,.elements_in_view=SCENE_TEXT_ROWS,.on_scroll_callback=scene_text_scrolled,.step_size=1};
static void scene_city_scrolled(void){scene_city_row=(int)scene_city_sb.scroll_position;window_request_refresh();}
static void scene_text_scrolled(void){scene_text_top=(int)scene_text_sb.scroll_position;window_request_refresh();}
static int scene_city_rows(void){return (scene_count+1)/2;}
static int scene_text_count(void);static int scene_rome_selected;
/* Keep both bars in step with the current list (city change, reload) before drawing or handling input. */
static void scene_sync_scroll(void){
 scrollbar_update_total_elements(&scene_city_sb,(unsigned)scene_city_rows());if(scene_city_row>(int)scene_city_sb.max_scroll_position)scene_city_row=(int)scene_city_sb.max_scroll_position;
 if(scene_city_sb.scroll_position!=(unsigned)scene_city_row)scrollbar_reset(&scene_city_sb,(unsigned)scene_city_row);
 scrollbar_update_total_elements(&scene_text_sb,(unsigned)scene_text_count());if(scene_text_top>(int)scene_text_sb.max_scroll_position)scene_text_top=(int)scene_text_sb.max_scroll_position;
 if(scene_text_sb.scroll_position!=(unsigned)scene_text_top)scrollbar_reset(&scene_text_sb,(unsigned)scene_text_top);
}
static void scene_fit(void){scene_zoom=1;scene_pan_x=scene_pan_y=0;scene_dragging=0;}
static void scene_zoom_at(int x,int y,int direction){
 float old=scene_zoom;scene_zoom*=direction>0?1.5f:1/1.5f;if(scene_zoom<1)scene_zoom=1;if(scene_zoom>6)scene_zoom=6;
 scene_pan_x=(scene_pan_x+x-SCENE_X)*scene_zoom/old-(x-SCENE_X);
 scene_pan_y=(scene_pan_y+y-scene_map_y())*scene_zoom/old-(y-scene_map_y());scene_clamp();
}

/* Lines are kept as display lines, already wrapped to the text column with the game's own font width.
 * kind: 0 plain (older files), 'H' heading, 'F' fact, 'R' the author's suggestion, 'W' warning, 'T' trade link, 'C' continuation.
 * A 'T' line also carries the link state (ok/candidate/unknown/broken), transport (land/sea) and the city index it points to. */
typedef struct {char kind,state,sea;signed char target;} scene_meta;
static char scene_title[512],scene_subtitle[512],scene_lines[SCENE_MAX_LINES][256];static scene_meta scene_line_meta[SCENE_MAX_LINES];
static struct {int player,x,y,count,links;char name[256],lines[SCENE_CITY_LINES][256];scene_meta meta[SCENE_CITY_LINES],link[SCENE_MAX_CITIES];} scene_cities[SCENE_MAX_CITIES];
static const char *lobby_city_status_by_name(const char *name); /* multiplayer_lobby_map.inc: who holds a city in the room */
static int lobby_city_flag_by_name(const char *name); /* 3 mine, 2 taken, 1 free, 0 unknown */
/* Rome: a fixed capital shown on every scenario map (rome_capital.py sends its place as an optional "ROME x y" last line).
 * Not a player or trade city: never in the city list, never counted, no actions. Selecting it shows read-only text. */
static int scene_rome_x=-1,scene_rome_y=-1;
static char scene_rome_lines[12][256];static scene_meta scene_rome_meta[12];static int scene_rome_count;
static char scene_rome_title[256]; /* from the trailing ROMETITLE line */
/* Text that may hold an em dash: the game font has no such glyph, so each dash is drawn as a short line between the parts. */
static void mp_draw_dash_text(const char *text,int x,int y,int w,font_t font,color_t dash){
 const char *p=text;int left=x;
 while(*p && left<x+w){
  const char *d=strstr(p,"\xE2\x80\x94");char part[512];int n=d?(int)(d-p):(int)strlen(p);if(n>=(int)sizeof(part))n=sizeof(part)-1;
  memcpy(part,p,n);part[n]=0;
  if(n){uint8_t t[1024];encoding_from_utf8(part,t,sizeof(t));draw_utf8(part,left,y,x+w-left,font);left+=text_get_width(t,font);}
  if(!d)break;
  graphics_fill_rect(left+3,y+6,12,2,dash);left+=18;p=d+3;while(*p==' ')p++;
 }
}

/* Shared with the room map: the Roman capital icon (UI/Empire_Icon_Roman_05) centred on cx,cy, shown size factor d,
 * with its name to the left. The flag animation is left out; the base picture is the same one the editor shows. */
static void mp_rome_draw(int cx,int cy,float d,int selected){
 int id=assets_lookup_image_id(ASSET_UI_EMP_ICON_5);const image *img=id?image_get(id):0;
 int w=img?(int)(img->width*d):14,h=img?(int)(img->height*d):14,left=cx-w/2,top=cy-h/2;
 graphics_fill_rect(left-2,top-2,w+4,h+4,0xb0f3e6c4);graphics_draw_rect(left-2,top-2,w+4,h+4,0xff6b5638); /* pale plate: apart from map and markers */
 if(selected)graphics_draw_rect(left-4,top-4,w+8,h+8,0xffffd278);
 if(img)image_draw(id,(int)(left/d),(int)(top/d),COLOR_MASK_NONE,1/d);
 if(img){ /* Rome flies the same red flag the neutral cities fly on the empire map (their untinted flag frame),
   * hung where the icon's own flag goes (animation offset 16,6 in ui.xml). */
  int trade=image_group(GROUP_EMPIRE_CITY_TRADE);const image *icon=image_get(trade);
  if(icon && icon->animation && icon->animation->num_sprites)image_draw(trade+1,(int)((left+16*d)/d),(int)((top+6*d)/d),COLOR_MASK_NONE,1/d);
 }
 else{graphics_fill_rect(left,top,w,h,0xffb8860b);graphics_draw_rect(left,top,w,h,0xff3a2a10);}
 uint8_t name[32];encoding_from_utf8("로마",name,sizeof(name));int tw=text_get_width(name,FONT_NORMAL_WHITE)+8,tx=left-tw-2,ty=cy-9;
 graphics_fill_rect(tx,ty,tw,18,0xe0402a14);draw_utf8("로마",tx+4,ty+3,tw,FONT_NORMAL_WHITE);
}
static int scene_text_width(const char *utf8){uint8_t text[1024];encoding_from_utf8(utf8,text,sizeof(text));return text_get_width(text,FONT_NORMAL_BLACK);}
/* Split one tagged line into display lines of at most `width` pixels. Returns the number of lines written. */
static int scene_wrap(const char *line,char out[][256],scene_meta *meta,int room){
 scene_meta m={0,0,0,-1};const char *text=line;
 if(line[0] && line[1]=='\t' && strchr("HFRWTCL",line[0])){
  m.kind=line[0];text=line+2;
  if(m.kind=='T' || m.kind=='L'){char state[16]={0},how[8]={0};int target=-1,used=0;
   if(sscanf(text,"%15[^\t]\t%7[^\t]\t%d\t%n",state,how,&target,&used)>=3 && used>0){text+=used;m.state=state[0];m.sea=how[0]=='s';m.target=(signed char)(target>=0 && target<SCENE_MAX_CITIES?target:-1);}
   else m.kind='F';}
 }
 int indent=m.kind=='T' || m.kind=='R' || m.kind=='W'?14:m.kind=='H'?6:0,width=SCENE_TEXT_W-indent-4,count=0;
 const char *p=text;
 do{
  if(count>=room)break;
  char buf[256];int n=0,last_space=-1;
  while(p[n]){
   int len=1;unsigned char c=(unsigned char)p[n];if(c>=0xF0)len=4;else if(c>=0xE0)len=3;else if(c>=0xC0)len=2;
   if(n+len>=255)break;memcpy(buf,p,n+len);buf[n+len]=0;
   if(n>0 && scene_text_width(buf)>width)break;
   if(p[n]==' ')last_space=n;n+=len;
  }
  if(p[n] && last_space>0)n=last_space+1;
  memcpy(out[count],p,n);out[count][n]=0;
  meta[count]=count==0?m:(scene_meta){m.kind?'C':0,m.kind,0,-1};
  if(count>0)meta[count].state=m.kind; /* continuation remembers the kind it continues */
  count++;p+=n;while(*p==' ')p++;
 }while(*p);
 if(!count){out[0][0]=0;meta[0]=m;count=1;}
 return count;
}
static int scene_number(FILE *f,int limit){char buf[64],extra;int n;if(!room_list_line(f,buf,sizeof(buf)) || sscanf(buf,"%d %c",&n,&extra)!=1 || n<0 || n>limit)return -1;return n;}
static int scene_load_file(const char *file,const char *expected){
 char line[ROOM_LIST_LINE];
 FILE *f=room_list_open(file);if(!f)return 0;
 int ok=0;scene_count=0;scene_rome_x=scene_rome_y=-1;scene_rome_count=0;scene_rome_selected=0;scene_rome_title[0]=0;
 if(!room_list_line(f,line,sizeof(line)) || strcmp(line,"AUGSCENARIO1"))goto done;
 if(!room_list_line(f,line,sizeof(line)) || strcmp(line,expected))goto done;
 if(!room_list_line(f,scene_title,sizeof(scene_title)) || !room_list_line(f,scene_subtitle,sizeof(scene_subtitle)))goto done;
 int logical=scene_number(f,SCENE_MAX_LINES);if(logical<0)goto done;
 scene_line_count=0;
 for(int j=0;j<logical;j++){if(!room_list_line(f,line,sizeof(line)))goto done;scene_line_count+=scene_wrap(line,&scene_lines[scene_line_count],&scene_line_meta[scene_line_count],SCENE_MAX_LINES-scene_line_count);}
 scene_count=scene_number(f,SCENE_MAX_CITIES);if(scene_count<1)goto done;
 for(int i=0;i<scene_count;i++){
  char extra;if(!room_list_line(f,line,sizeof(line)) || sscanf(line,"%d %d %d %c",&scene_cities[i].player,&scene_cities[i].x,&scene_cities[i].y,&extra)!=3)goto done;
  if(scene_cities[i].player<0 || scene_cities[i].player>1 || scene_cities[i].x<0 || scene_cities[i].x>2000 || scene_cities[i].y<0 || scene_cities[i].y>1000)goto done;
  if(!room_list_line(f,scene_cities[i].name,sizeof(scene_cities[i].name)))goto done;
  int logical=scene_number(f,SCENE_CITY_LINES);if(logical<0)goto done;
  scene_cities[i].count=0;
  scene_cities[i].links=0;
  for(int j=0;j<logical;j++){if(!room_list_line(f,line,sizeof(line)))goto done;
   if(line[0]=='L' && line[1]=='\t'){ /* map-only link: keep it, show no text */
    char tmp[2][256];scene_meta meta[2];scene_wrap(line,tmp,meta,1);
    if(meta[0].kind=='L' && meta[0].target>=0 && scene_cities[i].links<SCENE_MAX_CITIES)scene_cities[i].link[scene_cities[i].links++]=meta[0];
    continue;}
   scene_cities[i].count+=scene_wrap(line,&scene_cities[i].lines[scene_cities[i].count],&scene_cities[i].meta[scene_cities[i].count],SCENE_CITY_LINES-scene_cities[i].count);}
 }
 /* Optional last lines (rome_capital.py): ROME x y, then the ROMETITLE/ROMETEXT/ROMEFACT texts. */
 while(room_list_line(f,line,sizeof(line))){int rx,ry;char extra;   /* unknown lines are skipped */
  if(sscanf(line,"ROME %d %d %c",&rx,&ry,&extra)==2 && rx>=0 && rx<=2000 && ry>=0 && ry<=1000){scene_rome_x=rx;scene_rome_y=ry;}
  else if(!strncmp(line,"ROMETITLE\t",10))snprintf(scene_rome_title,sizeof(scene_rome_title),"%s",line+10);
  else if(!strncmp(line,"ROMETEXT\t",9) || !strncmp(line,"ROMEFACT\t",9)){
   char tagged[ROOM_LIST_LINE];snprintf(tagged,sizeof(tagged),"F\t%s",line+9);
   scene_rome_count+=scene_wrap(tagged,&scene_rome_lines[scene_rome_count],&scene_rome_meta[scene_rome_count],12-scene_rome_count);
   if(line[4]=='T' && scene_rome_count<12){scene_rome_lines[scene_rome_count][0]=0;scene_rome_meta[scene_rome_count]=(scene_meta){0,0,0,-1};scene_rome_count++;}}
 }
 ok=1;
done:fclose(f);if(!ok)scene_count=0;return ok;
}
static int scene_load(void){char file[96];snprintf(file,sizeof(file),"scenario-overview-%d.txt",selector_selected);return scene_load_file(file,selector_selected_label);}
static void scene_open_room(void){scene_hall=0;scene_room=scene_opened=1;scene_fit();scene_city=-1;scene_city_row=scene_text_top=0;input_box_stop(&input);scene_valid=scene_load_file("lobby-overview.txt","ROOM");scrollbar_init(&scene_city_sb,0,(unsigned)scene_city_rows());scrollbar_init(&scene_text_sb,0,(unsigned)scene_text_count());window_request_refresh();}
static void scene_open(void){scene_hall=0;scene_room=0;scene_opened=1;scene_fit();scene_city=-1;scene_city_row=scene_text_top=0;input_box_stop(&selector_input);scene_valid=scene_load();scrollbar_init(&scene_city_sb,0,(unsigned)scene_city_rows());scrollbar_init(&scene_text_sb,0,(unsigned)scene_text_count());window_request_refresh();}
#ifdef MP_HALL
static void scene_open_hall(void){
 selector_field(selector_selected_label,0,scene_hall_key,sizeof(scene_hall_key));scene_hall_said[0]=0;
 const char *dir=getenv("AUGUSTUS_MP_BRIDGE");if(dir){char path[2048];snprintf(path,sizeof(path),"%s/hall-briefing.txt",dir);remove(path);}
 scene_hall_sent=mp_client_command("hall-briefing",scene_hall_key);scene_hall_asked=time_get_millis();   /* another request on its way: sent after it */
 scene_room=0;scene_hall=scene_opened=1;scene_valid=0;scene_count=0;scene_fit();scene_city=-1;scene_city_row=scene_text_top=0;scene_rome_selected=0;
 input_box_stop(&selector_input);window_request_refresh();
}
static void scene_hall_poll(void){   /* the answer comes once: read until it is there */
 if(!scene_hall || scene_valid || scene_hall_said[0])return;
 if(!scene_hall_sent){
  scene_hall_sent=mp_client_command("hall-briefing",scene_hall_key);
  if(!scene_hall_sent && time_get_millis()-scene_hall_asked>10000)snprintf(scene_hall_said,sizeof(scene_hall_said),"%s","시나리오 정보를 요청하지 못했습니다.");
  window_request_refresh();return;}
 char head[512];room_read("hall-briefing.txt",head,sizeof(head));
 if(head[0]=='0' && head[1]==' '){head[strcspn(head,"\r\n")]=0;snprintf(scene_hall_said,sizeof(scene_hall_said),"%s",head+2);window_request_refresh();return;}
 if(strncmp(head,"AUGSCENARIO1",12))return;
 scene_valid=scene_load_file("hall-briefing.txt",scene_hall_key);
 if(!scene_valid)snprintf(scene_hall_said,sizeof(scene_hall_said),"%s","시나리오 정보를 읽지 못했습니다.");
 scrollbar_init(&scene_city_sb,0,(unsigned)scene_city_rows());scrollbar_init(&scene_text_sb,0,(unsigned)scene_text_count());window_request_refresh();
}
#endif
static void scene_close(void){scene_hall=0;scene_opened=0;if(scene_room){scene_room=0;input_box_start(&input);}else input_box_start(&selector_input);window_request_refresh();}
static int scene_text_count(void){return scene_rome_selected?scene_rome_count:scene_city<0?scene_line_count:scene_cities[scene_city].count;}
static void scene_action(const generic_button *b){
 int id=b->parameter1;
 if(id==1){scene_close();return;}
 if(id==2){
  if(scene_room)return;
#ifdef MP_HALL
  if(scene_hall){   /* 방 만들기 from here: the same as the room window's 만들기 (a recovery password first) */
   if(!scene_valid)return;scene_hall=scene_opened=0;input_box_start(&selector_input);generic_button made={0};made.parameter1=3;selector_action(&made);return;}
#endif
  char current[ROOM_LIST_LINE];int count;network_choice("network-starts.txt",selector_selected,current,sizeof(current),&count);
  if(!scene_valid || selector_selected<0 || selector_selected>=count || strcmp(current,selector_selected_label)){scene_valid=0;return;}
  network_start=selector_selected;scene_opened=0;selector_close();return;
 }
 if(id==3){scene_city=-1;scene_rome_selected=0;scene_text_top=0;}
 if(id==8 && scene_rome_x>=0){scene_city=-1;scene_rome_selected=1;scene_text_top=0;}
 if(id==9)scene_fit();
 if(id>=10 && id<10+scene_count){scene_city=id-10;scene_rome_selected=0;scene_text_top=0;
  /* A city picked on the map scrolls into view in the list. */
  int row=scene_city/2;if(row<scene_city_row)scene_city_row=row;if(row>=scene_city_row+SCENE_GRID_ROWS)scene_city_row=row-SCENE_GRID_ROWS+1;if(scene_zoom>1){scene_pan_x=scene_cities[scene_city].x*scene_map_w()*scene_zoom/2000-scene_map_w()/2;scene_pan_y=scene_cities[scene_city].y*scene_map_h()*scene_zoom/1000-scene_map_h()/2;scene_clamp();}}
 window_request_refresh();
}
static generic_button scene_buttons[]={
 {48,528,176,28,scene_action,0,1},{576,528,176,28,scene_action,0,2},
 {504,100,248,24,scene_action,0,3},{312,528,176,28,scene_action,0,9}
};
static color_t scene_link_color(const scene_meta *m){
 if(m->state=='b')return 0xffc0392b;if(m->state=='u')return 0xff9a958a;return m->sea?0xff4ea0de:0xffb07e3e;
}
/* A dashed line from (x1,y1) to (x2,y2): dash/gap in pixels; dash<=0 means solid. Two pixels wide. */
static void scene_dashed(int x1,int y1,int x2,int y2,int dash,int gap,color_t color){
 int dx=x2-x1,dy=y2-y1;int len=(int)sqrtf((float)(dx*dx+dy*dy));if(len<1)return;
 int step=dash<=0?len:dash,skip=dash<=0?0:gap;
 for(int t=0;t<len;t+=step+skip){int e=t+step>len?len:t+step;
  int ax=x1+dx*t/len,ay=y1+dy*t/len,bx=x1+dx*e/len,by=y1+dy*e/len;
  graphics_draw_line(ax,bx,ay,by,color);graphics_draw_line(ax+1,bx+1,ay,by,color);graphics_draw_line(ax,bx,ay+1,by+1,color);}
}
/* Trade relations of the chosen city, from the same judgement the editor uses. A line is a relation, not a caravan. */
static void scene_draw_links(int mw,int mh,int my){
 if(scene_city<0)return;
 int fx=SCENE_X+scene_cities[scene_city].x*mw*scene_zoom/2000-scene_pan_x,fy=my+scene_cities[scene_city].y*mh*scene_zoom/1000-scene_pan_y;
 int lines=scene_cities[scene_city].count,total=lines+scene_cities[scene_city].links;
 for(int pass=0;pass<2;pass++)for(int j=0;j<total;j++){
  const scene_meta *m=j<lines?&scene_cities[scene_city].meta[j]:&scene_cities[scene_city].link[j-lines];
  if((m->kind!='T' && m->kind!='L') || m->target<0 || m->target>=scene_count)continue;
  int working=m->state=='o' || m->state=='c';if(working!=pass)continue; /* broken/unknown first, working links on top */
  int tx=SCENE_X+scene_cities[m->target].x*mw*scene_zoom/2000-scene_pan_x,ty=my+scene_cities[m->target].y*mh*scene_zoom/1000-scene_pan_y;
  color_t c=scene_link_color(m);
  scene_dashed(fx,fy,tx,ty,m->state=='o'?0:m->state=='c'?8:m->state=='u'?2:6,m->state=='u'?4:5,c);
  if(m->state=='b'){int cx=(fx+tx)/2,cy=(fy+ty)/2;graphics_draw_line(cx-4,cx+4,cy-4,cy+4,0xffc0392b);graphics_draw_line(cx-4,cx+4,cy+4,cy-4,0xffc0392b);}
 }
}
static void scene_marker(const scene_meta *m,int x,int y){
 color_t c=scene_link_color(m);
 if(m->state=='o')graphics_fill_rect(x,y+3,9,9,c);
 else if(m->state=='c'){graphics_draw_rect(x,y+3,9,9,c);graphics_fill_rect(x+3,y+6,3,3,c);}
 else if(m->state=='u')graphics_draw_rect(x,y+3,9,9,c);
 else {graphics_draw_line(x,x+8,y+3,y+11,c);graphics_draw_line(x,x+8,y+11,y+3,c);}
}
/* One display line of the text column, styled by its kind. */
static void scene_text_line(const char *text,const scene_meta *m,int x,int y){
 char kind=m->kind=='C'?m->state:m->kind;
 if(m->kind=='H'){graphics_fill_rect(x,y-1,SCENE_TEXT_W,17,0xff786543);draw_utf8(text,x+6,y+2,SCENE_TEXT_W-10,FONT_NORMAL_WHITE);return;}
 int indent=kind=='T' || kind=='R' || kind=='W'?14:0;
 if(m->kind=='T')scene_marker(m,x,y);
 if(m->kind=='R')graphics_fill_rect(x+1,y+4,8,8,0xff4f7d3a);
 if(m->kind=='W')draw_utf8("!",x+2,y+1,10,FONT_NORMAL_RED);
 draw_utf8(text,x+indent,y+1,SCENE_TEXT_W-indent,kind=='W'?FONT_NORMAL_RED:kind=='R'?FONT_NORMAL_GREEN:FONT_NORMAL_BLACK);
}
static void scene_draw(void){
 outer_panel_draw(8,8,49,36);
#ifdef MP_HALL
 scene_hall_poll();
 if(scene_hall && !scene_valid){
  draw_utf8(scene_hall_said[0]?"시나리오 정보를 볼 수 없습니다.":"시나리오 정보를 받고 있습니다.",SCENE_X,28,704,FONT_LARGE_BLACK);
  draw_utf8(scene_hall_said[0]?scene_hall_said:"잠시 기다려 주세요.",SCENE_X,58,704,scene_hall_said[0]?FONT_NORMAL_RED:FONT_NORMAL_BLACK);
  if(!scene_hall_said[0])room_busy_draw(8,1,SCENE_X,84,248);else room_busy_draw(8,0,0,0,0);}
 else
#endif
 {
 draw_utf8(scene_valid?scene_title:"시나리오 정보를 불러오지 못했습니다.",SCENE_X,28,704,FONT_LARGE_BLACK);
 draw_utf8(scene_valid?scene_subtitle:"목록으로 돌아가 새로고침한 뒤 다시 선택해 주세요.",SCENE_X,58,704,FONT_NORMAL_BLACK);}
 if(scene_valid){
  /* All shipped empire templates share the original full empire artwork. */
  const image *map=image_get(image_group(GROUP_EMPIRE_MAP));
  int mw=scene_map_w(),mh=scene_map_h(),my=scene_map_y();
  float scale=map->width/(mw*scene_zoom);
  graphics_set_clip_rectangle(SCENE_X,my,mw,mh);
  image_draw(image_group(GROUP_EMPIRE_MAP),(int)((SCENE_X-scene_pan_x)*scale),(int)((my-scene_pan_y)*scale),COLOR_MASK_NONE,scale);
  scene_draw_links(mw,mh,my);
  if(scene_rome_x>=0){
   int x=SCENE_X+scene_rome_x*mw*scene_zoom/2000-scene_pan_x,y=my+scene_rome_y*mh*scene_zoom/1000-scene_pan_y;
   float d=mw*scene_zoom/2000.f;if(d<.45f)d=.45f;if(d>1)d=1;   /* true map size, never under .45: the same rule as the editor */
   if(scene_in_map(x,y))mp_rome_draw(x,y,d,scene_rome_selected);
  }
  for(int i=0;i<scene_count;i++){
   int x=SCENE_X+scene_cities[i].x*mw*scene_zoom/2000-scene_pan_x,y=my+scene_cities[i].y*mh*scene_zoom/1000-scene_pan_y;
   if(!scene_in_map(x,y))continue;
   graphics_fill_rect(x-9,y-8,19,17,scene_cities[i].player?0xff345775:0xff786543);
   graphics_draw_rect(x-10,y-9,21,19,i==scene_city?0xffffd278:0xffe6dbba);
   char num[16];snprintf(num,sizeof(num),"%d",i+1);draw_utf8(num,x-7,y-6,20,FONT_NORMAL_WHITE);
  }
  graphics_reset_clip_rectangle();graphics_draw_rect(SCENE_X,my,mw,mh,0xff6b5638);
  draw_utf8(scene_city>=0 && scene_cities[scene_city].player?"선: 이 도시의 교역 관계 (실선 가능·점선 후보/미확인·빨강 불가)":"휠 확대 · 오른쪽 드래그 이동 / 파랑: 플레이 도시",SCENE_X,82,mw,FONT_SMALL_PLAIN);
  scene_sync_scroll();
  for(int j=0;j<2*SCENE_GRID_ROWS;j++){
   int i=scene_city_row*2+j;if(i>=scene_count)break;int x=SCENE_X+(j%2)*SCENE_GRID_COL,y=SCENE_GRID_Y+(j/2)*24;
   large_label_draw_custom_size(x,y,SCENE_GRID_W,22);char name[320];snprintf(name,sizeof(name),"%d. %s",i+1,scene_cities[i].name);
   /* Reserve the role badge independently of an ellipsized city name. */
   color_t role_color=scene_cities[i].player?0xff345775:0xff786543;
   graphics_fill_rect(x+2,y+2,3,17,role_color);
   draw_utf8(name,x+8,y+5,SCENE_GRID_W-62,i==scene_city?FONT_NORMAL_RED:FONT_NORMAL_BLACK);
   graphics_fill_rect(x+SCENE_GRID_W-52,y+2,49,18,role_color);
   int held=scene_room && scene_cities[i].player?lobby_city_flag_by_name(scene_cities[i].name):0;
   gift_center(held==3?"내 도시":held==2?"선택됨":held==1?"빈자리":scene_cities[i].player?"플레이":"중립",x+SCENE_GRID_W-52,y+5,49,FONT_NORMAL_WHITE);
   if(i==scene_city)graphics_draw_rect(x,y,SCENE_GRID_W,22,0xffb87324);
  }
  scrollbar_draw(&scene_city_sb);
  char heading[320];
  if(scene_rome_selected)snprintf(heading,sizeof(heading),"%s",scene_rome_title[0]?scene_rome_title:"로마");
  else if(scene_city<0)snprintf(heading,sizeof(heading),"시나리오 설명");
  else{const char *holder=scene_room && scene_cities[scene_city].player?lobby_city_status_by_name(scene_cities[scene_city].name):0;
   snprintf(heading,sizeof(heading),"%s%s%s",scene_cities[scene_city].name,holder?" · ":"",holder?holder:"");}
  mp_draw_dash_text(heading,SCENE_TEXT_X,136,SCENE_TEXT_W,FONT_NORMAL_BLACK,0xff3a2a10);
  int count=scene_text_count();
  for(int j=0;j<SCENE_TEXT_ROWS;j++){int n=scene_text_top+j;if(n>=count)break;
   if(scene_rome_selected)scene_text_line(scene_rome_lines[n],&scene_rome_meta[n],SCENE_TEXT_X,160+j*18);
   else if(scene_city<0)scene_text_line(scene_lines[n],&scene_line_meta[n],SCENE_TEXT_X,160+j*18);
   else scene_text_line(scene_cities[scene_city].lines[n],&scene_cities[scene_city].meta[n],SCENE_TEXT_X,160+j*18);}
  scrollbar_draw(&scene_text_sb);
 }
 const char *pick="이 시나리오 선택";
#ifdef MP_HALL
 if(scene_hall)pick=selector_category==2?"이 저장으로 방 만들기":"이 시나리오로 방 만들기";
#endif
 const char *labels[]={scene_room?"대기실로":"목록으로",pick,scene_city<0 && !scene_rome_selected?"시나리오 전체 설명":"전체 설명으로","지도 초기화"};
 for(int i=0;i<4;i++){generic_button *b=&scene_buttons[i];if((scene_room && i==1) || (!scene_valid && i!=0))continue;large_label_draw_custom_size(b->x,b->y,b->width,b->height);gift_center(labels[i],b->x+6,b->y+(b->height-12)/2,b->width-12,FONT_NORMAL_BLACK);}
}
static void scene_handle(const mouse *m,const hotkeys *h){
#ifdef MP_HALL
 scene_hall_poll();
#endif
 if(h->close_pressed){scene_dragging=0;scene_close();return;}
 for(int i=0;i<4;i++){
  if((scene_room && i==1) || (!scene_valid && i!=0))continue;
  if(generic_buttons_handle_mouse(m,0,0,&scene_buttons[i],1,&focus))return;
 }
 if(!scene_valid)return;
 if(m->right.went_down && scene_in_map(m->x,m->y)){scene_dragging=1;scene_drag_x=m->x;scene_drag_y=m->y;}
 if(scene_dragging){
  if(m->right.is_down){scene_pan_x-=m->x-scene_drag_x;scene_pan_y-=m->y-scene_drag_y;scene_drag_x=m->x;scene_drag_y=m->y;scene_clamp();}
  else scene_dragging=0;
 }
 scene_sync_scroll();
 /* The wheel goes to whatever is under the mouse: map zoom, the city list or the text. */
 int over_text=m->x>=SCENE_TEXT_X-8 && m->y>=140 && m->y<160+SCENE_TEXT_ROWS*18;
 int over_grid=m->x>=SCENE_X && m->x<SCENE_X+2*SCENE_GRID_COL+24 && m->y>=SCENE_GRID_Y && m->y<SCENE_GRID_Y+SCENE_GRID_ROWS*24;
 if(scene_text_sb.is_dragging_scrollbar_dot || (over_text && !scene_city_sb.is_dragging_scrollbar_dot)){if(scrollbar_handle_mouse(&scene_text_sb,m,0))return;}
 else if(scene_city_sb.is_dragging_scrollbar_dot || over_grid){if(scrollbar_handle_mouse(&scene_city_sb,m,0))return;}
 if(m->scrolled && scene_in_map(m->x,m->y))scene_zoom_at(m->x,m->y,m->scrolled==SCROLL_UP?1:-1);
 if(m->left.went_up && !scene_dragging){
  int chosen=-1,dist=100000;
  if(scene_in_map(m->x,m->y))for(int i=0;i<scene_count;i++){
   int x=SCENE_X+scene_cities[i].x*scene_map_w()*scene_zoom/2000-scene_pan_x,y=scene_map_y()+scene_cities[i].y*scene_map_h()*scene_zoom/1000-scene_pan_y;
   int d=(m->x-x)*(m->x-x)+(m->y-y)*(m->y-y);if(scene_in_map(x,y) && d<=225 && d<dist){chosen=i;dist=d;}
  }
  for(int j=0;j<2*SCENE_GRID_ROWS;j++){int x=SCENE_X+(j%2)*SCENE_GRID_COL,y=SCENE_GRID_Y+(j/2)*24;if(m->x>=x && m->x<x+SCENE_GRID_W && m->y>=y && m->y<y+22 && scene_city_row*2+j<scene_count)chosen=scene_city_row*2+j;}
  if(scene_rome_x>=0 && scene_in_map(m->x,m->y)){   /* map click: Rome if it is nearer than any city marker */
   int x=SCENE_X+scene_rome_x*scene_map_w()*scene_zoom/2000-scene_pan_x,y=scene_map_y()+scene_rome_y*scene_map_h()*scene_zoom/1000-scene_pan_y;
   int d=(m->x-x)*(m->x-x)+(m->y-y)*(m->y-y);
   if(d<=196 && d<dist){generic_button b={0};b.parameter1=8;scene_action(&b);chosen=-1;}
  }
  if(chosen>=0){generic_button b={0};b.parameter1=10+chosen;scene_action(&b);}
 }
 window_request_refresh();
}
