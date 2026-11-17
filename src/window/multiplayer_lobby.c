#include "multiplayer/army_seal.h"
#include "graphics/button.h"
#include "graphics/image.h"
#include "game/resource.h"
#include "multiplayer/chat.h"
#include "graphics/screen.h"
#include "game/system.h"
#include "window/message_list.h"
#include "multiplayer/clock.h"
#include "multiplayer_lobby.h"
#include "core/mp_i18n.h"
#include "core/encoding.h"
#include "core/config.h"
#include "graphics/window.h"
#include "graphics/graphics.h"
#include "graphics/generic_button.h"
#include "graphics/panel.h"
#include "graphics/text.h"
#include "widget/input_box.h"
#include "window/main_menu.h"
#include "window/city.h"
#include "window/multiplayer_chat.h"
#include "city/view.h"
#include "window/empire.h"
#include "game/file.h"
#include "game/settings.h"
#include "scenario/property.h"
#include "city/finance.h"
#include "building/building.h"
#include "core/time.h"
#include "sound/effect.h"
#include "city/resource.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Local bridge mailbox. Networking never runs on or mutates the engine thread.
 * Only UTF-8 display data and explicit UI commands cross this boundary. */
static uint8_t draft[241],player_name[97];
static input_box name_input={160,120,15,2,FONT_NORMAL_WHITE,1,player_name,sizeof(player_name)};
static input_box input={32,384,30,2,FONT_NORMAL_WHITE,1,draft,sizeof(draft)};
static unsigned int focus;
static int entered, from_city, chat_open, lobby_name_active=1;
static char sent_draft[1024];
static int history_tab;
static int history_from_form; /* history opened from the new-offer form (1), a city side tab (2) or the partner list (3): back returns there */
static int side_return_tab;   /* a window opened from a city side tab: coming back to the city reopens that tab */
static int army_tab;
static int trade_tab, trade_mode=1, trade_resource=8, trade_quantity=0, trade_price=10, trade_cash=0, trade_step=10;
static char notice[256];
static unsigned int trade_notice_read,trade_notice_sound;
static unsigned long long trade_notice_seen,trade_notice_pending;
static int trade_notice_count;
static void trade_notice_poll(void){
 unsigned int now=time_get_millis();
 if(now-trade_notice_read>=250){
  trade_notice_read=now;const char *dir=getenv("AUGUSTUS_MP_BRIDGE");
  if(dir){char path[2048];snprintf(path,sizeof(path),"%s/trade-notify.txt",dir);FILE *f=fopen(path,"rb");
   if(f){unsigned long long latest;int count;
    if(fscanf(f,"%llu %d",&latest,&count)==2 && count>=0){
     trade_notice_count=count;
     if(latest>trade_notice_seen){trade_notice_seen=latest;trade_notice_pending=latest;}
    }fclose(f);
   }
  }
 }
 if(trade_notice_pending && trade_notice_count && now-trade_notice_sound>=3000){
  sound_effect_play(SOUND_EFFECT_FANFARE);trade_notice_sound=now;trade_notice_pending=0;
 }
 if(!trade_notice_count)trade_notice_pending=0;
}
static void click(const generic_button *button);
static generic_button buttons[]={
 {32,72,120,28,click,0,1},{164,72,120,28,click,0,2},
 {296,72,120,28,click,0,3},{428,72,180,28,click,0,4},
 {528,384,80,28,click,0,5},{32,428,120,28,click,0,6},{428,120,180,28,click,0,7},{32,120,80,28,click,0,8},{120,120,80,28,click,0,9},{208,120,80,28,click,0,10},{296,120,120,28,click,0,11},{164,428,120,28,click,0,12},{296,428,120,28,click,0,13},{428,428,180,28,click,0,14}
};
static const char *labels[]={"카푸아 참가","타렌툼 참가","준비 전환","새로 고침","보내기","뒤로","도시로 / 계속","60%","80%","100%","전체 정지","공동 저장","저장 취소","거래 이력"};
static void draw_utf8(const char *s,int x,int y,int width,font_t font){
 uint8_t converted[2048];encoding_from_utf8(s,converted,sizeof(converted));
 text_draw_ellipsized(converted,x,y,width,font,0);
}
/* A chat line "sender: text" (lobby-chat.txt). What players type and their names are never looked up in the language
 * catalog; a room notice (sender 시스템) is shown in the reader's language (2026-11-14). */
static void draw_chat_utf8(const char *s,int x,int y,int width,font_t font){
 static const char system_prefix[]="시스템: ";
 char line[2048];
 if(!strncmp(s,system_prefix,sizeof(system_prefix)-1)){
  char who[128];snprintf(who,sizeof(who),"%s",mp_i18n_translate("시스템"));
  snprintf(line,sizeof(line),"%s: %s",who,mp_i18n_translate(s+sizeof(system_prefix)-1));
 } else snprintf(line,sizeof(line),"%s",s);
 mp_i18n_suspend(1);draw_utf8(line,x,y,width,font);mp_i18n_suspend(0);
}
/* Button text: one glyph size for every state. Dimmed uses the brown font
 * (same size as black) in the original gray-green; never a smaller font. */
#define MP_DIM_FONT FONT_NORMAL_BROWN
static void mp_button_text(const char *s,int x,int y,int width,int state){
 uint8_t text[512];encoding_from_utf8(s,text,sizeof(text));
 font_t font=state==1?FONT_NORMAL_RED:state==2?MP_DIM_FONT:FONT_NORMAL_BLACK;
 color_t color=state==2?COLOR_FONT_GRAY_GREEN:0;
 if(text_get_width(text,font)<=width)text_draw_centered(text,x,y,width,font,color);
 else text_draw_ellipsized(text,x,y,width,font,color);
}
/* One look for in-game multiplayer buttons: 0 normal, 1 selected, 2 dimmed
 * (the click handler explains why). */
static void mp_label_button(int x,int y,int width,int height,const char *s,int state){
 large_label_draw_custom_size(x,y,width,height);
 if(state==1)button_border_draw(x,y,width,height,1);
 mp_button_text(s,x+6,y+(height-14)/2,width-12,state);
}
static int local_role(void){return mp_client_role();}
static void recover_failed_chat(void){
 const char *dir=getenv("AUGUSTUS_MP_BRIDGE");if(!dir)return;
 char path[2048],failed[1024]={0};snprintf(path,sizeof(path),"%s/chat-failed.txt",dir);FILE *f=fopen(path,"rb");
 if(!f)return;fread(failed,1,sizeof(failed)-1,f);fclose(f);
 if(!failed[0])return;
 strcpy(notice,"전송하지 못한 메시지가 있습니다. 입력칸을 비우면 복원됩니다.");
 if(!draft[0]){encoding_from_utf8(failed,draft,sizeof(draft));if(chat_open || (window_is(WINDOW_MULTIPLAYER_LOBBY) && !lobby_name_active))input_box_refresh_text(&input);remove(path);memset(sent_draft,0,sizeof(sent_draft));}
}

static void background(void){
 if(trade_tab || history_tab || army_tab)window_draw_underlying_window();
 else {
  graphics_reset_dialog();
  graphics_reset_clip_rectangle();
  image_draw_fullscreen_background(image_group(GROUP_INTERMEZZO_BACKGROUND));
 }
}

static void trade_click(const generic_button *b);
static void trade_previous(const generic_button *b);
static generic_button trade_buttons[]={
 {40,164,170,28,trade_click,0,0},{224,164,170,28,trade_click,trade_previous,1},{408,164,184,28,trade_click,0,2},
 {40,208,44,28,trade_click,0,3},{232,208,44,28,trade_click,0,4},
 {320,208,44,28,trade_click,0,5},{548,208,44,28,trade_click,0,6},
 {40,280,170,28,trade_click,0,7},{224,280,170,28,trade_click,0,8},{408,280,184,28,trade_click,0,9}
};
#include "multiplayer/trade_catalog.h"
static unsigned long long trade_id;static int trade_actions;
static void trade_view(char *buf,size_t size){
 const char *dir=getenv("AUGUSTUS_MP_BRIDGE");char path[2048];trade_id=0;trade_actions=0;buf[0]=0;
 if(!dir)return;snprintf(path,sizeof(path),"%s/trade-view.txt",dir);FILE *f=fopen(path,"rb");
 if(f){if(fscanf(f,"%llu %d\n",&trade_id,&trade_actions)==2)fread(buf,1,size-1,f);fclose(f);}
}
static void trade_draw(void){
 char buf[2048]={0},label[128];trade_view(buf,sizeof(buf));
 for(int i=0;i<10;i++){
  const generic_button *b=&trade_buttons[i];const char *text="";
  if(i==0)text=trade_mode?"종류: 선물":"종류: 판매";
  else if(i==1){snprintf(label,sizeof(label),"물품: %s",trade_names[trade_resource]);text=label;}
  else if(i==2){snprintf(label,sizeof(label),"조절 단위: %d",trade_step);text=label;}
  else if(i==3 || i==5)text="-";else if(i==4 || i==6)text="+";
  else if(i==7)text="제안 보내기";else if(i==8)text="받은 제안 수락";else text=(trade_actions&4)?"화물 반환 재시도":"거절 / 거래 취소";
  large_label_draw_custom_size(b->x,b->y,b->width,b->height);
  int disabled=(i==8 && !(trade_actions&1)) || (i==9 && !(trade_actions&2)) || (i<8 && mp_clock_trade_busy());
  mp_button_text(text,b->x+6,b->y+8,b->width-12,disabled?2:0);
 }
 snprintf(label,sizeof(label),trade_resource==8?"%d 데나리":"수량: %d포대",trade_resource==8?trade_cash:trade_quantity);
 draw_utf8(label,92,216,132,FONT_NORMAL_WHITE);
 snprintf(label,sizeof(label),"포대당 %d 데나리",trade_mode?0:trade_price);draw_utf8(label,372,216,168,FONT_NORMAL_WHITE);
 snprintf(label,sizeof(label),"보낼 제안: %s / %s / 합계 %d 데나리",trade_mode?"선물":"판매",trade_names[trade_resource],trade_resource==8?trade_cash:trade_mode?0:trade_quantity*trade_price);
 draw_utf8(label,40,250,552,FONT_NORMAL_WHITE);
 if(entered){
  int resource=trade_resource_ids[trade_resource];
  if(resource)snprintf(label,sizeof(label),"내 재고: %d포대 / 내 자금: %d데나리",city_resource_get_total_amount(resource,0),city_finance_treasury());
  else snprintf(label,sizeof(label),"내 자금: %d데나리",city_finance_treasury());
  draw_utf8(label,40,264,552,FONT_NORMAL_WHITE);
 }

 char *line=strtok(buf,"\n");int y=320;while(line && y<=354){draw_utf8(line,40,y,552,FONT_NORMAL_WHITE);line=strtok(0,"\n");y+=17;}
}
static void trade_previous(const generic_button *b){
 if(mp_clock_trade_busy())return;
 trade_resource=(trade_resource+MP_TRADE_RESOURCE_COUNT-1)%MP_TRADE_RESOURCE_COUNT;
 if(trade_resource==8)trade_mode=1;
}
static void trade_click(const generic_button *b){
 int id=b->parameter1;
 if(id<8 && mp_clock_trade_busy())return;
 if(id==0){trade_mode=!trade_mode;if(!trade_mode && trade_resource==8)trade_resource=0;return;}
 if(id==1){trade_resource=(trade_resource+1)%MP_TRADE_RESOURCE_COUNT;if(trade_resource==8)trade_mode=1;return;}
 if(id==2){trade_step=trade_step==1?10:trade_step==10?100:1;return;}
 if(id==3 || id==4){int *value=trade_resource==8?&trade_cash:&trade_quantity;*value+=(id==3?-1:1)*(trade_resource==8?trade_step:1);if(*value<1)*value=1;if(*value>(trade_resource==8?1000000:32))*value=trade_resource==8?1000000:32;return;}
 if(id==5 || id==6){trade_price+=(id==5?-1:1)*trade_step;if(trade_price<1)trade_price=1;if(trade_price>31250)trade_price=31250;return;}
 const char *dir=getenv("AUGUSTUS_MP_BRIDGE");if(!dir)return;
 char path[2048],tmp[2048];snprintf(path,sizeof(path),"%s/command.txt",dir);snprintf(tmp,sizeof(tmp),"%s/command.tmp",dir);
 FILE *pending=fopen(path,"rb");if(pending){fclose(pending);return;}
 /* Use the ID displayed with this offer; never accept a replacement offer silently. */
 if((id==8 && !(trade_actions&1)) || (id==9 && !(trade_actions&2)))return;
 FILE *f=fopen(tmp,"wb");if(!f)return;
 if(id==7)fprintf(f,"trade\noffer %d %d %d %d",trade_mode,trade_resource,trade_resource==8?trade_cash:trade_quantity,trade_price);
 else fprintf(f,"trade\n%s %llu",id==8?"accept":"reject",trade_id);
 if(fclose(f))return;rename(tmp,path);
}

static void history_draw(void){
 const char *dir=getenv("AUGUSTUS_MP_BRIDGE");if(!dir)return;
 char path[2048],buf[8192]={0};snprintf(path,sizeof(path),"%s/trade-history.txt",dir);
 FILE *f=fopen(path,"rb");if(f){fread(buf,1,sizeof(buf)-1,f);fclose(f);}
 draw_utf8("최근 거래 10건 ,  새 거래가 위에 표시됩니다",40,164,560,FONT_NORMAL_WHITE);
 char *line=strtok(buf,"\n");int y=190;
 while(line && y<=352){draw_utf8(line,40,y,560,FONT_NORMAL_WHITE);line=strtok(0,"\n");y+=18;}
}
static void read_alerts(int *unread,unsigned long long *offer){
 *unread=0;*offer=0;const char *dir=getenv("AUGUSTUS_MP_BRIDGE");if(!dir)return;
 char path[2048];snprintf(path,sizeof(path),"%s/alerts.txt",dir);FILE *f=fopen(path,"rb");
 if(f){if(fscanf(f,"%d %llu",unread,offer)!=2){*unread=0;*offer=0;}fclose(f);}
}
/* The entry latch survives opening the lobby from another panel (or the lobby
 * itself). The previous window alone is not a multiplayer session indicator. */
static int proposal_counts[2];static unsigned proposal_targets[2],proposal_read_at;
static void proposal_poll(void){
 unsigned now=time_get_millis();if(proposal_read_at && now-proposal_read_at<250)return;proposal_read_at=now;
 memset(proposal_counts,0,sizeof(proposal_counts));memset(proposal_targets,0,sizeof(proposal_targets));
 const char*dir=getenv("AUGUSTUS_MP_BRIDGE");if(!dir)return;
 for(int i=0;i<2;i++){
  char path[2048];snprintf(path,sizeof(path),"%s/%s-inbox.txt",dir,i?"agreement":"route");FILE*f=fopen(path,"rb");if(!f)continue;
  unsigned target;while(proposal_counts[i]<128 && fscanf(f,"%u",&target)==1){if(!target || (!i && target>8))continue;if(!proposal_counts[i])proposal_targets[i]=target;proposal_counts[i]++;}fclose(f);
 }
}
/* Attack banners over the city ("카르타고 공격군 / 2개월 이내 도착 ..."): army-alert.txt lines are "id<TAB>text".
 * A click hides that banner until its march ends (user 2026-11-13: it covered the city for two months).
 * Old lines without an id are shown as before and cannot be hidden. */
static struct {char id[64],text[704];} army_banners[3];static int army_banner_count;
static char army_hidden[8][64];static int army_hidden_next;
static int army_banner_hidden(const char *id){for(int i=0;i<8;i++)if(id[0] && !strcmp(army_hidden[i],id))return 1;return 0;}
static void army_banner_read(void){
 army_banner_count=0;const char *folder=getenv("AUGUSTUS_MP_BRIDGE");if(!folder)return;
 char path[2048],line[768];snprintf(path,sizeof(path),"%s/army-alert.txt",folder);FILE *f=fopen(path,"rb");if(!f)return;
 while(army_banner_count<3 && fgets(line,sizeof(line),f)){
  line[strcspn(line,"\r\n")]=0;if(!line[0])continue;
  char *tab=strchr(line,'\t'),*text=line,id[64]={0};
  if(tab){*tab=0;snprintf(id,sizeof(id),"%s",line);text=tab+1;}
  if(army_banner_hidden(id))continue;
  snprintf(army_banners[army_banner_count].id,sizeof(army_banners[0].id),"%s",id);
  snprintf(army_banners[army_banner_count].text,sizeof(army_banners[0].text),"%s",text);army_banner_count++;
 }
 fclose(f);
}
static int army_banner_click(const mouse *m){
 for(int n=0;n<army_banner_count;n++)if(m->x>=80 && m->x<600 && m->y>=146+n*28 && m->y<172+n*28){
  if(m->left.went_up && army_banners[n].id[0]){snprintf(army_hidden[army_hidden_next],sizeof(army_hidden[0]),"%s",army_banners[n].id);army_hidden_next=(army_hidden_next+1)%8;army_banner_read();window_invalidate();}
  return 1;
 }
 return 0;
}
static int proposal_alert_rect(int index,int*x,int*y,int*width){
 proposal_poll();if(!entered || index<0 || index>1 || !proposal_counts[index])return 0;
 int vx,vy,vw,vh;city_view_get_viewport(&vx,&vy,&vw,&vh);*width=vw-32;if(*width>560)*width=560;*x=vx+(vw-*width)/2;
 int unread;unsigned long long offer;read_alerts(&unread,&offer);
 *y=window_multiplayer_notification_bottom()-28-(offer?32:0)-(index && proposal_counts[0]?32:0);return *y>=30;
}
static int trade_alert_rect(int *x,int *y,int *width){
 int unread;unsigned long long offer;read_alerts(&unread,&offer);if(!offer || !entered)return 0;
 int vx,vy,vw,vh;city_view_get_viewport(&vx,&vy,&vw,&vh);*width=vw-32;if(*width>560)*width=560;
 *x=vx+(vw-*width)/2;*y=window_multiplayer_notification_bottom()-28;return *y>=30;
}
int window_multiplayer_trade_alert_top(void){int x,y,width,top=trade_alert_rect(&x,&y,&width)?y:0;for(int i=0;i<2;i++)if(proposal_alert_rect(i,&x,&y,&width) && (!top || y<top))top=y;return top;}
static int can_return_to_city(void){return entered || from_city;}
static const char *return_label(void){if(trade_tab || history_tab || army_tab)return from_city?"도시로 돌아가기":"제국지도로";return can_return_to_city()?"도시로 돌아가기":"메인 메뉴";}
static void return_from_lobby(void){
 if(mp_clock_trade_busy()){strcpy(notice,"거래 저장을 적용 중입니다. 완료 후 돌아갈 수 있습니다.");return;}
 notice[0]=0;input_box_stop(&input);
 if(trade_tab || history_tab || army_tab){trade_tab=history_tab=army_tab=0;window_go_back();return;}
 if(can_return_to_city())window_city_show();else window_main_menu_show(0);
}
static int visible_button(int i){
 if(trade_tab || history_tab || army_tab)return i==5 || i==3 || i==13;
 return i==0 || i==1 || (i==2 && local_role()!=1) || i==4 || i==5 || (i==6 && local_role()==1);
}
/* Test launcher tools (user 2026-11-15: in no release): the chat commands (multiplayer_testtools.inc) and the panel
 * under the throne box (multiplayer_throne_test.inc). tools/make_release.py builds the release with AUGUSTUS_RELEASE
 * and leaves both files out of its source archive, so the released game has none of this code. */
#if !defined(AUGUSTUS_RELEASE) && defined(__has_include)
#if __has_include("multiplayer_testtools.inc") && __has_include("multiplayer_throne_test.inc")
#define MP_TEST_TOOLS 1
#endif
#endif
#include "multiplayer_gift.inc"
#include "multiplayer_army.inc"
#include "multiplayer_notices.inc"
#include "multiplayer_sidetabs.inc"
#include "multiplayer_room.inc"
#include "multiplayer_history.inc"
#ifndef MP_SPECTATE   /* no spectators in this edition (multiplayer_spectate.inc, Korean edition) */
int window_multiplayer_spectating(void){return 0;}
int window_multiplayer_spectate_tick(void){return 0;}
void window_multiplayer_spectate_banner(int x,int y,int width){(void)x;(void)y;(void)width;}
void window_multiplayer_spectate_leave_map(void){}
#endif
#ifdef MP_TEST_TOOLS
#include "multiplayer_testtools.inc"
#else
static int testtools_command(const char *text){(void)text;return 0;}
#endif
static void foreground(void){
 recover_failed_chat();
 if(army_tab){window_draw_underlying_window();army_draw();return;}
 if(trade_tab){window_draw_underlying_window();gift_draw();return;}
 if(!history_tab){room_draw();return;}
 window_draw_underlying_window();history_screen_draw();return;
 /* Alpha glyphs and changing labels must start from clean panels each frame. */
 background();
 graphics_in_dialog();
 int role=local_role();
 draw_utf8((trade_tab || history_tab)?(trade_tab?"플레이어 교역 / 선물":"거래 이력"):role==1?"멀티플레이 - 나: 방장":role==2?"멀티플레이 - 나: 참가자":"멀티플레이 - 도시를 선택하세요",32,32,576,FONT_LARGE_BLACK);
 char clock_label[256];
 snprintf(clock_label,sizeof(clock_label),"도시 선택  ->  참가자 준비  ->  방장 시작  ->  5초 카운트다운");
 draw_utf8(clock_label,32,56,576,FONT_SMALL_PLAIN);
 for(int i=0;i<14;i++){
  if(!visible_button(i))continue;
  large_label_draw_custom_size(buttons[i].x,buttons[i].y,buttons[i].width,buttons[i].height);
  draw_utf8(i==5?return_label():i==13?"거래 이력":i==3?"교역 / 선물":i==6?"게임 시작":labels[i],buttons[i].x+6,buttons[i].y+8,buttons[i].width-12,FONT_NORMAL_BLACK);
 }
 const char *dir=getenv("AUGUSTUS_MP_BRIDGE");char path[2048];static char state[8192]={0};char incoming[8192]={0};
 if(dir){snprintf(path,sizeof(path),"%s/state.txt",dir);FILE *f=fopen(path,"rb");if(f){size_t n=fread(incoming,1,sizeof(incoming)-1,f);if(n && !ferror(f))memcpy(state,incoming,sizeof(state));fclose(f);}}
 if(!state[0])strcpy(state,"시험방 연결을 기다리는 중입니다.");
 if(dir && sent_draft[0]){char ackbuf[2048]={0};snprintf(path,sizeof(path),"%s/chat-sent.txt",dir);FILE *af=fopen(path,"rb");if(af){fread(ackbuf,1,sizeof(ackbuf)-1,af);fclose(af);char *body=strchr(ackbuf,'\n');if(body && !strcmp(body+1,sent_draft)){char current[1024];encoding_to_utf8(draft,current,sizeof(current),0);memset(sent_draft,0,sizeof(sent_draft));}}}
 char parsed[8192];memcpy(parsed,state,sizeof(parsed));
 char *line=strtok(parsed,"\n");if(line)draw_utf8(notice[0]?notice:line,296,103,312,FONT_SMALL_PLAIN);
 if(history_tab)history_draw();
 else if(trade_tab)trade_draw();
 else {
 draw_utf8("플레이어 이름",40,128,115,FONT_SMALL_PLAIN);
 if(!entered){if(lobby_name_active)input_box_draw(&name_input);else{inner_panel_draw(name_input.x,name_input.y,name_input.width_blocks,2);text_draw(player_name,name_input.x+16,name_input.y+10,FONT_NORMAL_WHITE,0);}}
 char chatbuf[8192]={0};
 if(dir){snprintf(path,sizeof(path),"%s/lobby-chat.txt",dir);FILE *f=fopen(path,"rb");if(f){fread(chatbuf,1,sizeof(chatbuf)-1,f);fclose(f);}}
 char *chatline=strtok(chatbuf,"\n");int cy=164;
 int chatfirst=1;while(chatline && cy<368){if(chatfirst)draw_utf8(chatline,40,cy,552,FONT_NORMAL_WHITE);else draw_chat_utf8(chatline,40,cy,552,FONT_NORMAL_WHITE);chatfirst=0;cy+=28;chatline=strtok(0,"\n");}
 input.x=32;input.y=384;input.width_blocks=30;if(!lobby_name_active)input_box_draw(&input);else{inner_panel_draw(input.x,input.y,30,2);text_draw(draft,input.x+16,input.y+10,FONT_NORMAL_WHITE,0);}

 }
 static char slots[2][128]={"선택 가능","선택 가능"};
 if(dir){snprintf(path,sizeof(path),"%s/slots.txt",dir);FILE *f=fopen(path,"rb");
  if(f){char a[128]={0},b[128]={0};if(fgets(a,sizeof(a),f) && fgets(b,sizeof(b),f)){
   a[strcspn(a,"\r\n")]=0;b[strcspn(b,"\r\n")]=0;strcpy(slots[0],a);strcpy(slots[1],b);
  }fclose(f);}}
 if(!trade_tab && !history_tab && !army_tab){draw_utf8(slots[0],32,103,120,FONT_SMALL_PLAIN);draw_utf8(slots[1],164,103,120,FONT_SMALL_PLAIN);}

 draw_utf8(trade_tab?"물품: 왼쪽 클릭 다음 / 오른쪽 클릭 이전 ,  수량은 포대":"Enter: 채팅 보내기 ,  참가자만 준비, 방장은 게임 시작",32,416,576,FONT_SMALL_PLAIN);
 graphics_reset_dialog();
}
static void click(const generic_button *b){
 if(b->parameter1==14){history_tab=1;trade_tab=0;focus=0;history_scroll_open();return;}
 if(b->parameter1==4){history_tab=0;trade_tab=1;focus=0;return;}
 if((trade_tab || history_tab) && b->parameter1==5)return;
 if(b->parameter1==6){return_from_lobby();return;}
 if(b->parameter1==7 && mp_clock_trade_busy())return;
 const char *dir=getenv("AUGUSTUS_MP_BRIDGE");if(!dir)return;
 char path[2048],tmp[2048],message[1024]={0};
 snprintf(path,sizeof(path),"%s/command.txt",dir);snprintf(tmp,sizeof(tmp),"%s/command.tmp",dir);
 FILE *pending=fopen(path,"rb");if(pending){fclose(pending);strcpy(notice,"이전 요청을 처리하고 있습니다. 잠시 후 다시 시도해 주세요.");return;}   /* said, not dropped silently (high ping, 2026-11-15) */
 if(b->parameter1==7){
  if(entered){input_box_stop(&input);window_city_show();return;}
  if(local_role()!=1)return;
 }
 if(b->parameter1==1 || b->parameter1==2){encoding_to_utf8(player_name,message,sizeof(message),0);input_box_stop(&name_input);lobby_name_active=0;input_box_start(&input);}
 if(b->parameter1==5){encoding_to_utf8(draft,message,sizeof(message),0);if(!message[0])return;snprintf(path,sizeof(path),"%s/chat-sent.txt",dir);remove(path);snprintf(path,sizeof(path),"%s/command.txt",dir);}
 const char *verbs[]={"","capua","tarentum","ready","refresh","send","","play","speed60","speed80","speed100","speed0","save","cancel_save"};
 if(!mp_client_command(verbs[b->parameter1],message))return;
 if(b->parameter1==5){strcpy(sent_draft,message);memset(draft,0,sizeof(draft));input_box_refresh_text(&input);}
 /* Retain draft until user clears it; transport failures must never discard text. */
}
static void handle(const mouse *m,const hotkeys *h){
 if(army_tab){army_handle(m,h);return;}
 if(trade_tab){gift_handle(m,h);return;}
 if(!history_tab){room_handle(m,h);return;}
 history_screen_handle(m,h);return;
 const mouse *local=mouse_in_dialog(m);
 if(h->close_pressed){generic_button back={0};back.parameter1=6;click(&back);return;}
 if(!entered && !trade_tab && !history_tab){
  if(local->left.went_up){
   if(local->y>=120 && local->y<152 && local->x>=160 && local->x<400 && !local_role()){lobby_name_active=1;input_box_start(&name_input);}
   else if(local->y>=384 && local->y<416 && local->x>=32 && local->x<512){lobby_name_active=0;input_box_start(&input);}
  }
  input_box_handle_mouse(local,lobby_name_active?&name_input:&input);
  if(!lobby_name_active && input_box_is_accepted()){generic_button send={0};send.parameter1=5;click(&send);}
  const char *dir=getenv("AUGUSTUS_MP_BRIDGE");char path[2048];
  if(dir){snprintf(path,sizeof(path),"%s/auto-enter.txt",dir);FILE *f=fopen(path,"rb");int go=f?fgetc(f):0;if(f)fclose(f);if(go=='1' && window_multiplayer_enter_city())return;}
 }
 if(trade_tab){if(generic_buttons_handle_mouse(local,0,0,trade_buttons,10,&focus))return;}
 for(int i=0;i<14;i++)if(visible_button(i) && generic_buttons_handle_mouse(local,0,0,&buttons[i],1,&focus))return;
 window_request_refresh();
}
void window_multiplayer_lobby_show(void){
 from_city=window_is(WINDOW_CITY) || window_is(WINDOW_CITY_MILITARY);
 focus=0;chat_open=0;input_box_stop(&input);input_box_stop(&name_input);input_box_stop(&network_input);
 if(!trade_tab && !history_tab && !army_tab){
  name_input.x=160;name_input.y=210;name_input.width_blocks=20;
  input.x=32;input.y=368;input.width_blocks=30;
  room_prefill();
  lobby_name_active=!room_identity;
#ifdef MP_HALL
  input_box_stop(&hall_input);
#endif
  if(room_network_entry()){if(network_mode==2)input_box_start(&network_input);else if(network_mode==1 || network_mode==4)input_box_start(&name_input);
#ifdef MP_HALL
   else if(network_mode==5)input_box_start(&hall_input);
#endif
  }
  else input_box_start(lobby_name_active?&name_input:&input);
 }
 window_type window={WINDOW_MULTIPLAYER_LOBBY,background,foreground,handle};window_show(&window);
}

/* Explicit engine-thread entry. The bridge publishes a complete immutable SAV
 * before this routine can see it. Reopening chat never reloads the city. */
static void native_start_trace(const char *dir,const char *state){
 char p[2048];snprintf(p,sizeof(p),"%s/native-start.txt",dir);FILE *f=fopen(p,"wb");
 if(f){fputs(state,f);fclose(f);}
}
int window_multiplayer_enter_city(void){
 if(room_menu_pending() || room_network_entry())return 0;
 if(entered){input_box_stop(&input);window_city_show();return 1;}
 const char *dir=getenv("AUGUSTUS_MP_BRIDGE");if(!dir)return 0;
 char path[2048];snprintf(path,sizeof(path),"%s/play.sav",dir);
 FILE *f=fopen(path,"rb");if(!f){strcpy(notice,"도시 파일을 준비하고 있습니다.");return 0;}fclose(f);
 native_start_trace(dir,"loading");
 if(game_file_load_saved_game(path)!=FILE_LOAD_SUCCESS){native_start_trace(dir,"load_failed");strcpy(notice,"도시 저장 파일을 읽지 못했습니다.");return 0;}
 native_start_trace(dir,"loaded");
 /* The room's city saves carry no player name: the advisors' title and letters showed a blank (user 2026-11-13).
    Use the waiting room name, and keep it in the settings so reloads during play (clock.c) find it again. */
 if(player_name[0]){setting_set_player_name(player_name);scenario_set_player_name(player_name);}
 input_box_stop(&name_input);entered=1;mp_clock_start();notice[0]=0;input_box_stop(&input);window_city_show();return 1;
}
static void chat_close(void){chat_open=0;input_box_stop(&input);window_invalidate();}
static void chat_input_layout(void){
 input.x=16;input.y=screen_height()-64;input.width_blocks=(screen_width()-32)/16;
 if(input.width_blocks>48)input.width_blocks=48;
}
int window_multiplayer_chat_input_top(void){return chat_open?screen_height()-90:0;}
/* Whisper (user 2026-11-13): the receiver is picked on the chat bar; empty = everyone. Ids come from the bridge's
   recipient list (the other seated players), never from typed text. */
static char chat_to[64],chat_to_label[192];
static void chat_target_rect(int *x,int *y,int *w,int *h){*x=input.x;*y=input.y-26;*w=240;*h=22;}
static void chat_target_next(void){
 const char *dir=getenv("AUGUSTUS_MP_BRIDGE");char path[2048],line[512],ids[8][64],labels[8][192];int n=0,at=-1;
 if(dir){snprintf(path,sizeof(path),"%s/trade-recipients.txt",dir);FILE *f=fopen(path,"rb");
  if(f){while(n<8 && fgets(line,sizeof(line),f)){char *flag=strchr(line,'\t');if(!flag)continue;*flag++=0;char *label=strchr(flag,'\t');if(!label)continue;*label++=0;label[strcspn(label,"\r\n")]=0;
   snprintf(ids[n],sizeof(ids[n]),"%s",line);snprintf(labels[n],sizeof(labels[n]),"%s",label);if(!strcmp(ids[n],chat_to))at=n;n++;}fclose(f);}}
 if(!chat_to[0])at=-1;int next=at+1;
 if(next>=n){chat_to[0]=chat_to_label[0]=0;}else{snprintf(chat_to,sizeof(chat_to),"%s",ids[next]);snprintf(chat_to_label,sizeof(chat_to_label),"%s",labels[next]);}
 window_invalidate();
}
void window_multiplayer_chat_begin(void){
 if(!entered || chat_open)return;
 chat_input_layout();
 chat_open=1;input_box_start(&input);
 system_keyboard_set_input_rect(input.x,input.y,input.width_blocks*16,32);
}
void window_multiplayer_chat_draw(void){
 recover_failed_chat();
 if(!entered)return;
 trade_notice_poll();
 if(side_return_tab && window_is(WINDOW_CITY)){side_tab=side_return_tab;side_return_tab=0;}
 side_tabs_draw();
 for(int i=0;i<2;i++){int px,py,pw;if(proposal_alert_rect(i,&px,&py,&pw)){
  char label[160];snprintf(label,sizeof(label),i?"미확인 구매 / 반복 거래 제안 %d건 / 눌러서 확인":"미확인 교역 계약 제안 %d건 / 눌러서 확인",proposal_counts[i]);
  large_label_draw_custom_size(px,py,pw,28);graphics_draw_rect(px,py,pw,28,0xffffcf70);graphics_draw_rect(px+1,py+1,pw-2,26,0xffb88d38);draw_utf8(label,px+8,py+8,pw-16,FONT_NORMAL_BLACK);
 }}
 {army_banner_read();for(int n=0;n<army_banner_count;n++){large_label_draw_custom_size(80,146+n*28,520,26);draw_utf8(army_banners[n].text,88,153+n*28,504,FONT_NORMAL_RED);}}
 char path[2048],buf[2048]={0};const char *dir=getenv("AUGUSTUS_MP_BRIDGE");
 if(dir && sent_draft[0]){
  snprintf(path,sizeof(path),"%s/chat-sent.txt",dir);FILE *f=fopen(path,"rb");
  if(f){fread(buf,1,sizeof(buf)-1,f);fclose(f);char *body=strchr(buf,'\n');
   if(body && !strcmp(body+1,sent_draft)){
    char current[1024];encoding_to_utf8(draft,current,sizeof(current),0);
    
    memset(sent_draft,0,sizeof(sent_draft));
   }
  }
 }
 int unread;unsigned long long offer;read_alerts(&unread,&offer);
 int tx,ty,tw;
 if(offer && trade_alert_rect(&tx,&ty,&tw)){char alert[512]={0};const char *folder=getenv("AUGUSTUS_MP_BRIDGE");if(folder){char file[2048];snprintf(file,sizeof(file),"%s/trade-alert.txt",folder);FILE *f=fopen(file,"rb");if(f){fread(alert,1,sizeof(alert)-1,f);fclose(f);}}large_label_draw_custom_size(tx,ty,tw,28);graphics_draw_rect(tx,ty,tw,28,0xffffcf70);graphics_draw_rect(tx+1,ty+1,tw-2,26,0xffb88d38);draw_utf8(alert[0]?alert:"받은 거래 제안 , 눌러서 확인",tx+8,ty+8,tw-16,FONT_NORMAL_BLACK);}
 if(chat_open){
  chat_input_layout();
  input_box_draw(&input);
  int bx,by,bw,bh;chat_target_rect(&bx,&by,&bw,&bh);char who[256];snprintf(who,sizeof(who),chat_to[0]?"귓속말: %s":"받는 사람: 전체",chat_to_label);
  graphics_tint_rect(bx,by,bw,bh,0x171b20,175);button_border_draw(bx,by,bw,bh,1);draw_utf8(who,bx+8,by+4,bw-16,FONT_NORMAL_WHITE);
  draw_utf8("눌러서 받는 사람 바꾸기 · Enter 보내기 / Esc 닫기",bx+bw+10,by+4,input.width_blocks*16-bw-10,FONT_NORMAL_WHITE);
 }
}
static void trade_inbox_open(void){
 if(!window_is(WINDOW_CITY) && !window_is(WINDOW_CITY_MILITARY) && !window_is(WINDOW_EMPIRE))return;
 if(!mp_client_command("trade","inbox"))return;
 if(chat_open)chat_close();
 window_multiplayer_trade_show();
}
int window_multiplayer_chat_input(const mouse *m,const hotkeys *h){
 if(!entered)return 0;
 int tx,ty,tw;
 if(trade_alert_rect(&tx,&ty,&tw) && m->x>=tx && m->x<tx+tw && m->y>=ty && m->y<ty+28){
  if(m->left.went_up)trade_inbox_open();return 1;
 }
 if(chat_open){
  if(h->close_pressed){chat_close();return 1;}
  {int bx,by,bw,bh;chat_target_rect(&bx,&by,&bw,&bh);if(m->x>=bx && m->x<bx+bw && m->y>=by && m->y<by+bh){if(m->left.went_up)chat_target_next();return 1;}}
  if(input_box_is_accepted()){
   char message[1024];encoding_to_utf8(draft,message,sizeof(message),0);
   if(message[0]){
    const char *dir=getenv("AUGUSTUS_MP_BRIDGE");char ack[2048];
    if(dir){snprintf(ack,sizeof(ack),"%s/chat-sent.txt",dir);remove(ack);}
   }
   {const char *p=message;while(*p==' ')p++;if(!*p){memset(draft,0,sizeof(draft));chat_close();return 1;}}   /* Enter on an empty (or only spaces) line closes the bar (user 2026-11-13) */
   if(testtools_command(message)){memset(draft,0,sizeof(draft));chat_close();return 1;}
   char whisper[1200];if(chat_to[0])snprintf(whisper,sizeof(whisper),"%s\n%s",chat_to,message);
   if(message[0] && (chat_to[0]?mp_client_command("whisper",whisper):mp_client_command("send",message))){
    strcpy(sent_draft,message);memset(draft,0,sizeof(draft));chat_close();
   }
   return 1;
  }
  input_box_handle_mouse(m,&input);return 1;
 }
 if(h->enter_pressed){window_multiplayer_chat_begin();return 1;}
 if(army_banner_click(m))return 1;
 for(int i=0;i<2;i++)if(proposal_alert_rect(i,&tx,&ty,&tw) && m->x>=tx && m->x<tx+tw && m->y>=ty && m->y<ty+28){if(m->left.went_up){city_notice n={0};n.kind=i?4:3;n.target=proposal_targets[i];city_notice_open_proposal(&n);}return 1;}
 if(side_tabs_input(m))return 1;
 return 0;
}

void window_multiplayer_reset(void){chat_to[0]=chat_to_label[0]=0;proposal_read_at=0;config_room_clear();city_notice_reset();trade_notice_seen=trade_notice_pending=0;trade_notice_count=0;memset(room_busy_active,0,sizeof(room_busy_active));mp_clock_stop();entered=0;from_city=0;chat_open=0;input_box_stop(&input);memset(sent_draft,0,sizeof(sent_draft));trade_tab=0;history_tab=0;room_identity=0;room_picker=0;room_ui_reset();
#ifdef MP_HALL
 hall_ready=0;hall_creating=0;input_box_stop(&hall_input);
#endif
 notice[0]=0;}

void window_multiplayer_trade_show(void){if(!window_is(WINDOW_EMPIRE) && !window_is(WINDOW_CITY) && !window_is(WINDOW_CITY_MILITARY))return;army_tab=0;gift_send_pending=0;gift_send_error[0]=0;gift_peer_locked=0;gift_picker=0;char view[2048]={0};trade_view(view,sizeof(view));gift_received=5;partner_direct=0;partner_page=0;partner_read_at=0;history_tab=0;trade_tab=1;input_box_stop(&input);window_multiplayer_lobby_show();}
void window_multiplayer_trade_show_for_city(int name_id){
 gift_send_pending=0;gift_send_error[0]=0;
 if(!window_is(WINDOW_EMPIRE))return;
 army_tab=0; /* a legion screen left by a hotkey must not cover this one */
 gift_recipient[0]=0;
 const char *dir=getenv("AUGUSTUS_MP_BRIDGE");char path[2048],line[512];
 if(dir){
  snprintf(path,sizeof(path),"%s/empire-player-slots.txt",dir);FILE *f=fopen(path,"rb");
  if(f){while(fgets(line,sizeof(line),f)){
   char *id=strchr(line,'\t');if(!id)continue;*id++=0;
   char *end=strchr(id,'\t');if(!end)continue;*end=0;
   if(atoi(line)==name_id){snprintf(gift_recipient,sizeof(gift_recipient),"%s",id);break;}
  }fclose(f);}
 }
 window_multiplayer_trade_show();
 gift_peer_locked=1;gift_picker=0;
 int state,revision;mp_route_peer(gift_recipient,&state,&revision);gift_received=gift_recipient[0]?6:5;partner_direct=1;partner_answer_dismissed=0;
}

void window_multiplayer_cash_show(int name_id){
 window_multiplayer_trade_show_for_city(name_id);
 if(!window_is(WINDOW_MULTIPLAYER_LOBBY) || !gift_recipient[0])return;
 partner_direct=1;partner_answer_dismissed=0;cash_open(0);
}

void window_multiplayer_history_show(void){if(!window_is(WINDOW_EMPIRE) && !window_is(WINDOW_CITY) && !window_is(WINDOW_CITY_MILITARY) && !(window_is(WINDOW_MULTIPLAYER_LOBBY) && (trade_tab || history_tab)))return;int already_open=window_is(WINDOW_MULTIPLAYER_LOBBY);trade_tab=army_tab=0;history_tab=1;history_from_form=0;history_scroll_open();input_box_stop(&input);if(!already_open)window_multiplayer_lobby_show();else window_invalidate();}

void window_multiplayer_army_show(int name_id){
 if(MP_ARMY_DISPATCH_SEALED || !window_is(WINDOW_EMPIRE))return;   /* multiplayer/army_seal.h */
 const char *dir=getenv("AUGUSTUS_MP_BRIDGE");if(!dir)return;
 char path[2048],line[512],id[65],label[160];int number;
 snprintf(path,sizeof(path),"%s/empire-player-slots.txt",dir);FILE *f=fopen(path,"rb");if(!f)return;
 army_destination[0]=0;
 while(fgets(line,sizeof(line),f))if(sscanf(line,"%d\t%64s\t%159[^\r\n]",&number,id,label)==3 && number==name_id){snprintf(army_destination,sizeof(army_destination),"%s",id);snprintf(army_target_label,sizeof(army_target_label),"%s",label);break;}
 fclose(f);if(!army_destination[0])return;
 trade_tab=history_tab=0;army_tab=1;army_selected=army_confirm=0;notice[0]=0;
 window_multiplayer_lobby_show();
}

void window_multiplayer_save_options_show(void){
 if(!mp_clock_active())return;
 trade_tab=history_tab=army_tab=0;window_multiplayer_lobby_show();room_options_begin();
 room_options_from_city=1;room_options_tab=2;room_save_begin();
}
void window_multiplayer_transport_show(void){if(!window_is(WINDOW_EMPIRE))return;window_multiplayer_trade_show();}

void window_multiplayer_trade_show_for_post(unsigned id){
 gift_send_pending=0;gift_send_error[0]=0;
 if(!window_is(WINDOW_CITY) && !window_is(WINDOW_CITY_MILITARY))return;
 army_tab=0;
 if(!id || id>=building_count() || building_get(id)->type!=BUILDING_PLAYER_TRADE_POST)return;
 gift_post=id;gift_recipient[0]=0;
 if(id && id<building_count()){
  int peer=building_get(id)->subtype.orientation;const char *dir=getenv("AUGUSTUS_MP_BRIDGE");
  if(dir){char path[2048],city[64];int slot,state,revision;snprintf(path,sizeof(path),"%s/route-state.txt",dir);FILE *f=fopen(path,"rb");
   if(f){while(fscanf(f,"%d %63s %d %d",&slot,city,&state,&revision)==4)if(slot==peer){snprintf(gift_recipient,sizeof(gift_recipient),"%s",city);break;}fclose(f);}
  }
 }
 window_multiplayer_trade_show();gift_peer_locked=1;gift_picker=0;gift_received=gift_recipient[0]?6:5;partner_direct=1;partner_answer_dismissed=0;
}
