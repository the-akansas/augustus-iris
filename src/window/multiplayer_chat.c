#include "core/mp_i18n.h"
#include "multiplayer_chat.h"
#include "multiplayer/chat.h"
#include "multiplayer/clock.h"
#include "scenario/custom_messages.h"
#include "graphics/window.h"
#include "graphics/graphics.h"
#include "graphics/panel.h"
#include "graphics/text.h"
#include "graphics/screen.h"
#include "graphics/scrollbar.h"
#include "graphics/generic_button.h"
#include "window/city.h"
#include "window/multiplayer_lobby.h"
#include "city/view.h"
#include "window/message_list.h"
#include "core/encoding.h"
#include "core/time.h"
#include "game/state.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
/* Only line offsets are cached; visible text is fetched by stable archive ID. */
typedef struct {int id,offset,length;} chat_line;
static chat_line *lines;static int line_count,line_capacity,indexed,cache_generation=-1;
static int following=1,new_messages,step=21;
static unsigned int focus;
static int preference_failed;
static void scrolled(void);
static scrollbar_type scroll={.x=584,.y=96,.length=288,.scrollable_width=544,.on_scroll_callback=scrolled,.step_size=3};
static void button(const generic_button *b);
/* One row, same width, 40px from the stone border at x=16..624. */
/* Two actions; the toast time is six keys on their own row (the chosen one is lit). */
static generic_button buttons[]={{56,428,160,28,button,0,0},{424,428,160,28,button,0,1}};
static const int toast_choices[]={3,5,8,15,30,60};
static void toast_key_rect(int i,int *x,int *y,int *w){*w=52;*x=168+i*58;*y=392;}
static void utf8(const char *s,int x,int y,int w,font_t font){uint8_t b[4096];encoding_from_utf8(s,b,sizeof(b));text_draw_ellipsized(b,x,y,w,font,0);}
/* Measure the exact displayed string after truncation, using the active font. measure_only: the height it would
 * take, nothing drawn (the bottom-up chat stack needs each box's height before placing it). */
static int note_x=8;   /* the left edge of the room notes at the top (window_multiplayer_overlay_draw) */
static int toast_layout(const char *s,int y,int max_width,int left,int color,int measure_only){
 /* color 0-7: the sender's player-colour mark leads a chat line (the text keeps its normal white). */
 int mark=color>=0 && color<8?12:0;
 /* chat toasts are final text (multiplayer/chat.c): never looked up in the catalog again (2026-11-14) */
 uint8_t text[4096],second[4096]={0};mp_i18n_suspend(1);encoding_from_utf8(s,text,sizeof(text));mp_i18n_suspend(0);
 int lines=1,line_step=font_definition_for(FONT_NORMAL_WHITE)->line_height+4;
 if(left>=0 && text_get_width(text,FONT_NORMAL_WHITE)>max_width){
  int count=text_get_max_length_for_width(text,0,FONT_NORMAL_WHITE,max_width,0);
  if(count>0 && text[count]){memcpy(second,text+count,strlen((char*)text+count)+1);text[count]=0;lines=2;}
 }
 text_ellipsize(text,FONT_NORMAL_WHITE,max_width);text_ellipsize(second,FONT_NORMAL_WHITE,max_width);
 int width=text_get_width(text,FONT_NORMAL_WHITE),width2=text_get_width(second,FONT_NORMAL_WHITE);
 if(width2>width)width=width2;if(width<=0)return 0;
 int height=26+(lines-1)*line_step;
 if(measure_only)return height;
 if(left>=0 && y-2+height>window_multiplayer_notification_bottom())return 0;
 int x=left>=0?left-(width+mark+16)/2:note_x;
 graphics_tint_rect(x,y-2,width+mark+16,height,0x171b20,175);
 graphics_draw_rect(x,y-2,width+mark+16,height,0xff9d917b);
 if(mark)mp_chat_draw_chip(x+8,y+5,7,10,color);
 text_draw(text,x+8+mark,y+4,FONT_NORMAL_WHITE,0);
 if(lines==2)text_draw(second,x+8+mark,y+4+line_step,FONT_NORMAL_WHITE,0);
 return height;
}
static int toast_draw(const char *s,int y,int max_width,int left,int color){return toast_layout(s,y,max_width,left,color,0);}
static void push(int id,int off,int len){
 if(line_count==line_capacity){int cap=line_capacity?line_capacity*2:512;chat_line *p=realloc(lines,cap*sizeof(*p));if(!p)return;lines=p;line_capacity=cap;}
 lines[line_count++]=(chat_line){id,off,len};
}
static void update(void){
 if(cache_generation!=mp_chat_generation()){indexed=line_count=0;cache_generation=mp_chat_generation();following=1;}
 int count=mp_chat_count(),old=indexed;
 for(;indexed<count;indexed++){
  int id=mp_chat_record(indexed);custom_message_t *m=custom_messages_get(id);if(!m)continue;
  push(id,-1,0);const uint8_t *text=custom_messages_get_text(m);int off=0;
  while(text && text[off]){
   int n=text_get_max_length_for_width(text+off,0,FONT_NORMAL_WHITE,520,0);
   if(n<=0)break;
   push(id,off,n);off+=n;
  }
  push(id,-2,0);
 }
 if(indexed!=old){
  scrollbar_update_total_elements(&scroll,line_count);
  if(following)scrollbar_reset(&scroll,scroll.max_scroll_position);else new_messages+=indexed-old;
 }
}
static int opened_from_city; /* opened from the city side tab: back returns to the city (and that tab) */
static void background(void){window_city_draw_all();}
static void draw(void){
 update();graphics_in_dialog();outer_panel_draw(16,32,38,28);
 utf8("멀티플레이 채팅",40,50,540,FONT_LARGE_BLACK);
 char label[128];snprintf(label,sizeof(label),"전체 %d개 대화 · 게임은 계속 진행됩니다",mp_chat_count());utf8(label,40,80,540,FONT_SMALL_PLAIN);
 inner_panel_draw(32,96,36,18);
 for(unsigned int i=0;i<scroll.elements_in_view && i+scroll.scroll_position<(unsigned)line_count;i++){
  chat_line *l=&lines[i+scroll.scroll_position];if(l->offset==-2)continue;
  custom_message_t *m=custom_messages_get(l->id);if(!m)continue;
  int y=104+i*step;
  if(l->offset==-1){
   /* sender line: player-colour mark (colour at sending), then the name in its usual yellow */
   int color=mp_chat_color(l->id),mark=color>=0?12:0;mp_chat_draw_chip(44,y+3,7,10,color);
   const uint8_t *s=custom_messages_get_subtitle(m);if(s)text_draw_ellipsized(s,44+mark,y,520-mark,FONT_NORMAL_WHITE,COLOR_FONT_YELLOW);}
  else {uint8_t buf[2048];const uint8_t *s=custom_messages_get_text(m);int n=l->length;if(n>=sizeof(buf))n=sizeof(buf)-1;memcpy(buf,s+l->offset,n);buf[n]=0;text_draw(buf,52,y,FONT_NORMAL_WHITE,0);}
 }
 scrollbar_draw(&scroll);
 const char *texts[2];char latest[64];
 snprintf(latest,sizeof(latest),new_messages?"새 대화 %d개":"최신 대화로",new_messages);
 texts[0]=opened_from_city?"돌아가기":"메시지함";texts[1]=latest;
 for(int i=0;i<2;i++){
  large_label_draw_custom_size(buttons[i].x,buttons[i].y,buttons[i].width,buttons[i].height);
  uint8_t t[128];encoding_from_utf8(texts[i],t,sizeof(t));text_draw_centered(t,buttons[i].x+6,buttons[i].y+8,buttons[i].width-12,FONT_NORMAL_BLACK,0);
 }
 utf8("새 대화 알림 표시",56,398,108,FONT_NORMAL_BLACK);
 const mouse *km=mouse_in_dialog(mouse_get());
 for(int i=0;i<6;i++){
  int x,y,w;toast_key_rect(i,&x,&y,&w);int chosen=toast_choices[i]==mp_chat_duration(),hot=km->x>=x && km->x<x+w && km->y>=y && km->y<y+24;
  if(chosen)graphics_fill_rect(x+3,y+3,w-6,18,0xfff3e4c5);
  button_border_draw(x,y,w,24,chosen || hot);
  char key[16];snprintf(key,sizeof(key),"%d초",toast_choices[i]);uint8_t t[32];encoding_from_utf8(key,t,sizeof(t));text_draw_centered(t,x,y+5,w,FONT_NORMAL_BLACK,0);
 }
 if(preference_failed)utf8("저장하지 못했습니다.",520,398,80,FONT_NORMAL_RED);
 graphics_reset_dialog();
}
static void scrolled(void){following=scroll.scroll_position==scroll.max_scroll_position;if(following)new_messages=0;window_request_refresh();}
static void leave(void){if(opened_from_city){opened_from_city=0;window_go_back();}else window_message_list_show();}
static void button(const generic_button *b){if(!b->parameter1)leave();else{following=1;new_messages=0;scrollbar_reset(&scroll,scroll.max_scroll_position);}}
static void handle(const mouse *m,const hotkeys *h){
 if(h->close_pressed){leave();return;}
 const mouse *local=mouse_in_dialog(m);scrollbar_handle_mouse(&scroll,local,1);
 if(local->left.went_up)for(int i=0;i<6;i++){int x,y,w;toast_key_rect(i,&x,&y,&w);
  if(local->x>=x && local->x<x+w && local->y>=y && local->y<y+24){
   /* the preference only steps forward: step until the chosen time is reached */
   preference_failed=0;for(int n=0;n<6 && mp_chat_duration()!=toast_choices[i];n++)if(!mp_chat_duration_cycle()){preference_failed=1;break;}
   window_request_refresh();return;}}
 generic_buttons_handle_mouse(local,0,0,buttons,2,&focus);
}
void window_multiplayer_chat_history_show(void){
 opened_from_city=0;
 step=font_definition_for(FONT_NORMAL_WHITE)->line_height+5;if(step<16)step=16;
 indexed=line_count=0;cache_generation=mp_chat_generation();following=1;new_messages=0;
 scroll.elements_in_view=280/step;scrollbar_init(&scroll,0,0);update();
 window_type w={WINDOW_MULTIPLAYER_CHAT,background,draw,handle};window_show(&w);
}
int window_multiplayer_notification_bottom(void){
 int bottom=screen_height()-16,input_top=window_multiplayer_chat_input_top();
 if(input_top && bottom>input_top-10)bottom=input_top-10;
 return bottom;
}
int window_multiplayer_hud_left(int top,int bottom);   /* multiplayer_throne.inc */
int window_multiplayer_hud_bottom(int x,int top,int bottom);
int window_multiplayer_pinned_left(void);              /* multiplayer_notices.inc: right of the side tabs or their open panel */
int window_multiplayer_pinned_bottom(void);            /* multiplayer_notices.inc: below the to-do cards and the note there */
/* The game's own column at the top centre (user 2026-11-17: the zoom note hid our chat): its warnings, one of which is
 * the zoom on every wheel turn (graphics/warning.c, rows at 30 and 55), and the paused banner (window/city.c, 448 wide
 * at 40, warnings then from 100). The bottom kept for its first two rows when [left, right) meets it, else 0; *edge:
 * its left edge. What we add at the top keeps out of it. */
int window_multiplayer_top_reserved(int left,int right,int *edge){
 int vx,vy,vw,vh;city_view_get_viewport(&vx,&vy,&vw,&vh);
 int c=(screen_width()-180)/2,l=c-230,r=c+230,paused=game_state_is_paused();
 if(paused){int bl=vx+(vw-448)/2;if(bl<l)l=bl;if(bl+448>r)r=bl+448;}
 if(edge)*edge=l;
 if(right<=l || left>=r)return 0;
 return paused?152:82;
}
void window_multiplayer_overlay_draw(void){
 if(!mp_clock_active())return;graphics_reset_dialog();
 int width=screen_width()-180;if(width>760)width=760;if(width<300)width=300;
 static char last_notice[512];static unsigned int notice_until;
 char notice[512]={0},notice_path[2048];const char *bridge=getenv("AUGUSTUS_MP_BRIDGE");
 if(bridge){snprintf(notice_path,sizeof(notice_path),"%s/ingame-status.txt",bridge);FILE *f=fopen(notice_path,"rb");if(f){fread(notice,1,sizeof(notice)-1,f);fclose(f);}}
 if(strcmp(notice,last_notice)){strcpy(last_notice,notice);notice_until=time_get_millis()+6000;}
 /* The room notes (user 2026-11-17: nothing of ours under the game's own top items, nor over our keys): right of the
  * side tabs and their open panel, below the to-do cards there (they stay put; a note comes and goes), before the
  * throne box and the maker tools at the top right, and left of the game's warning column (below it when too little is
  * left beside it). A note too long for its room is cut with "...". */
 int y=window_multiplayer_pinned_bottom()+4;
 note_x=window_multiplayer_pinned_left();if(note_x<8)note_x=8;
 {int free=window_multiplayer_hud_left(y-2,y+70)-note_x-16-8;
  if(free>=160){if(free<width)width=free;}
  else{int low=window_multiplayer_hud_bottom(note_x+176,y-2,y+70);if(low+4>y)y=low+4;   /* no room beside them: below them */
   free=window_multiplayer_hud_left(y-2,y+70)-note_x-16-8;if(free<width)width=free<160?160:free;}}
 {int edge,reserved=window_multiplayer_top_reserved(note_x,note_x+width+16,&edge);
  if(reserved){int beside=edge-note_x-16-8;if(beside>=240)width=beside;else if(y<reserved+4)y=reserved+4;}}
 const char *request=mp_client_request_status();
 if(request)y+=toast_draw(request,y,width,-1,-1)+6;
 if(last_notice[0] && time_get_millis()<notice_until)y+=toast_draw(last_notice,y,width,-1,-1)+6;

 /* The status-key hint is a reminder, not a fixture: show it for the first
  * 10 seconds of a session, then keep the city view clean. */
 static unsigned int hint_since;if(!hint_since)hint_since=time_get_millis();
 if(mp_debug_hint_visible() && time_get_millis()-hint_since<10000){
  int hint_width=width<420?width:420;int top=y;
  utf8("Ctrl+Shift+F11 : 멀티플레이 상태 보기",note_x+8,top+4,hint_width,FONT_NORMAL_WHITE);
  y=top+28;
 }
 if(mp_debug_visible()){
  char path[2048],buf[4096]={0};const char *dir=getenv("AUGUSTUS_MP_BRIDGE");
  if(dir){snprintf(path,sizeof(path),"%s/debug-status.txt",dir);FILE *f=fopen(path,"rb");if(f){fread(buf,1,sizeof(buf)-1,f);fclose(f);}}
  int lines=1;for(const char *p=buf;*p;p++)if(*p=='\n')lines++;
  int height=36+lines*20;if(height<126)height=126;if(height>screen_height()-60)height=screen_height()-60;
  int top=y;int bottom=top+height;if(bottom>screen_height()-30)bottom=screen_height()-30;
  utf8("멀티 상태 / Ctrl+Shift+F11 숨기기",16,top+6,width,FONT_NORMAL_WHITE);
  char *line=strtok(buf,"\n");int row=top+28;
  while(line && row<bottom-10){utf8(line,16,row,width,FONT_NORMAL_WHITE);line=strtok(0,"\n");row+=20;}
  y=row+10;
 }
 if(window_is(WINDOW_CITY) || window_is(WINDOW_CITY_MILITARY) || window_is(WINDOW_TOP_MENU)){
  int vx,vy,vw,vh;city_view_get_viewport(&vx,&vy,&vw,&vh);
  int max_width=vw-48;if(max_width>760)max_width=760;if(max_width<80)return;
  /* Bottom-centred chat (user 2026-11-14): the newest line sits at the bottom and pushes older ones up, above the
   * trade/proposal bars, and never over the status or notices at the top. The stack always ends where the chat
   * input line begins (shown or not): the very bottom edge was too low to notice (user, same day). */
  int ceiling=y>vy+10?y:vy+10;
  int bottom=screen_height()-100;   /* window_multiplayer_chat_input_top() - 10 while the input is open */
  if(bottom>window_multiplayer_notification_bottom())bottom=window_multiplayer_notification_bottom();
  int bars=window_multiplayer_trade_alert_top();if(bars && bars-8<bottom)bottom=bars-8;
  if(bottom>vy+vh-8)bottom=vy+vh-8;
  for(int i=2;i>=0;i--){
   const char *s=mp_chat_toast(i);if(!s)continue;
   int height=toast_layout(s,0,max_width-12,vx+vw/2,mp_chat_toast_color(i),1);if(!height)continue;
   int top=bottom-height+2;   /* toast boxes span y-2 .. y-2+height */
   if(top-2<ceiling)break;
   if(!toast_draw(s,top,max_width-12,vx+vw/2,mp_chat_toast_color(i)))break;
   bottom=top-2-4;
  }
 }
}
void window_multiplayer_chat_history_show_from_city(void){window_multiplayer_chat_history_show();opened_from_city=1;}
