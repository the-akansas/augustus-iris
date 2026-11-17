#include "window/popup_dialog.h"
/* Room UI uses the same stone panels and list selection as the original game.
 * Every screen is a centred dialog sized for its task (800x600 base):
 *   connect 432x320, host/join 576x416, name 480x288, city picker 576x448,
 *   waiting room / options / scenario 800x600. Buttons keep 40px from the
 *   panel's sides and 28px from its bottom; buttons in one row share a size. */
/* Waiting room (800x600): content spans x 48..752. */
#define ROOM_CHAT_Y 364
#define ROOM_INPUT_Y 452
#define ROOM_HINT_Y 494
#define ROOM_BOTTOM_Y 528
#define ROOM_MAKER_Y 272   /* LAN 방 만들기: the 시나리오 제작자 모드 line, under 방장 아이디 (y 230, 32 high) */
static int room_join_field;
static int room_migrating;
static int network_mode,network_adapter,network_start,lan_maker;   /* lan_maker: 시나리오 제작자 모드 of a LAN room (maker_room.py, both editions) */
static uint8_t network_ip[64];
/* network_mode: 0 menu, 1 open a room, 2 join by address, 3 LAN menu (only with a server entry), 4 server sign-in,
 * 5 game hall (multiplayer_hall.inc). The server entry is a Korean-edition file; without it the menu is the LAN menu. */
#if defined(__has_include)
#if __has_include("multiplayer_server_entry.inc")
#define MP_SERVER_ENTRY 1
#endif
#endif
/* The server administrator's login in the hall (Korean edition only, multiplayer_hall_admin.inc; EDITIONS.md) */
#if defined(__has_include)
#if __has_include("multiplayer_hall_admin.inc")
#define MP_HALL_ADMIN 1
#endif
#endif
/* The game hall: one lobby of many rooms on the server (multiplayer_hall.inc). Korean edition only, reached through
 * 서버 접속; the Global edition plays over the LAN alone (user 2026-11-16, EDITIONS.md). */
#if defined(__has_include)
#if __has_include("multiplayer_hall.inc")
#define MP_HALL 1
#endif
#endif
#if defined(MP_SERVER_ENTRY) && !defined(MP_HALL)
#error "multiplayer_server_entry.inc needs multiplayer_hall.inc"
#endif
#ifdef MP_SERVER_ENTRY
#define ROOM_LAN_MENU 3
#define ROOM_UPDATE 1   /* "업데이트 확인" under 서버 접속 and 랜 플레이 (Korean edition, user 2026-11-16) */
#else
#define ROOM_LAN_MENU 0
#define ROOM_UPDATE 0
#endif
#ifdef MP_HALL
static int hall_from,hall_creating,hall_hover_room=-1,hall_own_row=-1,hall_transfer_wait,hall_transfer_done;
static int hall_dev_mode;   /* 개발자 모드 ticked in 방 만들기 (user 2026-11-17): the room is opened as a developer room */
static uint8_t hall_text[241];
static input_box hall_input={48,ROOM_INPUT_Y,38,2,FONT_NORMAL_WHITE,1,hall_text,sizeof(hall_text)};
static int hall_selected(int kind,const char *line,const char *typed,const char *secret);
static void hall_secret_open(int asking,const char *line,const char *title);
static void hall_secret_draw(void);
static void hall_secret_handle(const mouse *m,const hotkeys *h);
static void hall_board_draw(void);   /* 알림판 (multiplayer_hall_board.inc) */
static void hall_board_handle(const mouse *m,const hotkeys *h);
#ifdef MP_SPECTATE
static void spectate_draw(void);   /* 관전 (multiplayer_spectate.inc) */
static void spectate_handle(const mouse *m,const hotkeys *h);
#endif
static int hall_saves_asked;
static void hall_own_country(char *code,size_t size);
#ifdef MP_HALL_ADMIN
static int hall_admin_chat(const char *text);
static const char *hall_admin_hint(void);
static void hall_admin_draw(void);
static void hall_admin_handle(const mouse *m,const hotkeys *h);
static void hall_admin_hall_draw(void);
static int hall_admin_hall_handle(const mouse *m);
static void hall_admin_pick(int index);
static int hall_admin_picked(const char *key);
static int hall_admin_on(void);
static void hall_admin_panel_draw(void);
static void hall_admin_panel_handle(const mouse *m,const hotkeys *h);
static void hall_admin_selector_draw(void);
static int hall_admin_selector_handle(const mouse *m);
#endif
static void hall_flag_draw(const char *code,int x,int y);
static void hall_plain(const char *s,int x,int y,int width,font_t font,color_t color);   /* multiplayer_hall.inc: text shown as typed */
#endif
static input_box network_input={40,106,18,2,FONT_NORMAL_WHITE,1,network_ip,sizeof(network_ip)};
static int room_identity,room_picker,room_hover,room_exit_seen;
static struct { int available; char id[64],label[384]; } room_choices[8];
static char room_later_verb[24],room_later_text[512];static unsigned room_later_at;   /* room_send: a click kept until the bridge is free */
static int room_choice_count;
static void room_read(const char *name,char *buf,size_t size){
 buf[0]=0;const char *dir=getenv("AUGUSTUS_MP_BRIDGE");if(!dir)return;
 char path[2048];snprintf(path,sizeof(path),"%s/%s",dir,name);FILE *f=fopen(path,"rb");
 if(f){size_t n=fread(buf,1,size-1,f);buf[n]=0;fclose(f);}
}
#include "multiplayer_busy.inc"
static int room_network_entry(void){if(room_menu_pending())return 1;char value[8];room_read("network-entry.txt",value,sizeof(value));return value[0]=='1';}
static int room_network_managed(void){char value[8];room_read("network-entry.txt",value,sizeof(value));return value[0]!=0;}
static int room_joined(void){char city[64];room_read("own-city.txt",city,sizeof(city));return city[0]!=0;}
#include "multiplayer_selector.inc"
static void room_read_choices(void){
 char options[4096];room_read("city-choices.txt",options,sizeof(options));room_choice_count=0;
 char *line=strtok(options,"\n");
 while(line && room_choice_count<8){
  int i=room_choice_count;char *id=strchr(line,'\t'),*label=id?strchr(id+1,'\t'):0;
  if(id && label){*id++=0;*label++=0;label[strcspn(label,"\r\n")]=0;room_choices[i].available=line[0]=='1';snprintf(room_choices[i].id,64,"%s",id);snprintf(room_choices[i].label,384,"%s",label);room_choice_count++;}
  else if(i<2 && strlen(line)>2){room_choices[i].available=line[0]=='1';snprintf(room_choices[i].id,64,"%s",i?"tarentum":"capua");snprintf(room_choices[i].label,384,"%s",line+2);room_choice_count++;}
  line=strtok(0,"\n");
 }
}
/* Dialog-local text helpers: titles and one-line descriptions are centred. */
static void room_title(const char *s,int width){gift_center(s,0,28,width,FONT_LARGE_BLACK);}
static void room_center(const char *s,int y,int width,font_t font){gift_center(s,40,y,width-80,font);}
static void room_right(const char *s,int right,int y,int width,font_t font){
 uint8_t text[1024];encoding_from_utf8(s,text,sizeof(text));int w=text_get_width(text,font);if(w>width)w=width;
 text_draw_ellipsized(text,right-w,y,width,font,0);
}
#include "multiplayer_preview.inc"
#include "multiplayer_lobby_map.inc"
#include "multiplayer_options.inc"
static void room_action(const generic_button *b);
#ifdef MP_HALL
#include "multiplayer_hall.inc"
#include "multiplayer_hall_board.inc"   /* 알림판 (user 2026-11-17) */
#ifdef MP_SPECTATE
#include "multiplayer_spectate.inc"   /* 관전 (user 2026-11-17; MP_SPECTATE: multiplayer_sidetabs.inc) */
#endif
#endif
#ifdef MP_HALL_ADMIN
#include "multiplayer_hall_admin.inc"
#endif
#ifdef MP_SERVER_ENTRY
#include "multiplayer_server_entry.inc"
#endif
static void room_leave_reply(int accepted,int checked){
 if(!accepted){if(!room_identity && !room_name_waiting)input_box_start(&name_input);return;}
 if(!mp_client_command("leave",""))strcpy(notice,"이전 요청을 처리하고 있습니다. 잠시 후 다시 시도해 주세요.");
}
static void room_leave_ask(void){
 static uint8_t title[128],body[512];
 encoding_from_utf8("방에서 나가기",title,sizeof(title));
 encoding_from_utf8(local_role()==1?"남은 참가자는 확인된 공동 저장에서 방장을 이어받습니다. 저장 이후 진행은 되돌아갈 수 있습니다. 나가시겠습니까?":"방에서 나가 메인 메뉴로 돌아가시겠습니까?",body,sizeof(body));
 window_popup_dialog_show_confirmation(title,body,0,room_leave_reply);
}
static void room_closed_reply(int accepted,int checked){(void)accepted;(void)checked;}
static void room_recovery_draw(void){
 graphics_in_dialog_with_size(480,160);outer_panel_draw(0,0,30,10);
 room_title("방장을 변경하고 있습니다.",480);
 room_center("공동 저장을 복구하면 내 도시로 자동으로 돌아갑니다.",76,480,FONT_NORMAL_BLACK);
 room_busy_draw(0,1,120,108,240);
 graphics_reset_dialog();
}
static void room_recovery_input(const mouse *m,const hotkeys *h){
 (void)m;(void)h;window_request_refresh();
}
static void room_recovery_show(void){
 window_type w={WINDOW_MULTIPLAYER_LOBBY,room_recovery_draw,0,room_recovery_input};window_show(&w);
}
void window_multiplayer_room_poll(void){
 room_options_poll();
 if(room_menu_pending())return;
 /* Left a room that was entered through the hall: the bridge is back in the hall, so is the screen. */
#ifdef MP_HALL
 if(hall_from && !room_migrating && window_is(WINDOW_MAIN_MENU) && room_network_entry()){
  char back[8];room_read("hall-return.txt",back,sizeof(back));
  if(back[0]=='1'){hall_from=0;hall_open();window_multiplayer_lobby_show();return;}
 }
#endif
 if(room_migrating){
  char result[32];room_read("room-recovery-result.txt",result,sizeof(result));
  if(!strcmp(result,"failed")){
   room_migrating=0;room_exit_seen=1;window_multiplayer_lobby_show();return;
  }
  char pending[32],go[8];room_read("room-exit.txt",pending,sizeof(pending));
  if(!pending[0]){
   if(room_network_entry()){room_migrating=0;room_exit_seen=0;window_multiplayer_lobby_show();return;}
   room_read("auto-enter.txt",go,sizeof(go));
   if(go[0]=='1' && window_multiplayer_enter_city()){room_migrating=0;room_exit_seen=0;return;}
  }
  window_request_refresh();return;
 }
 char event[32];room_read("room-exit.txt",event,sizeof(event));if(!event[0]){room_exit_seen=0;return;}
 if(room_exit_seen)return;
 char detail[1024];room_read("room-exit-detail.txt",detail,sizeof(detail));
 room_exit_seen=1;window_main_menu_show(0);
 if(room_network_managed()){
  const char *dir=getenv("AUGUSTUS_MP_BRIDGE");char path[2048];snprintf(path,sizeof(path),"%s/room-exit-seen.txt",dir);
  FILE *ack=fopen(path,"wb");if(ack){fputs("1",ack);fclose(ack);}
 }
 if(!strcmp(event,"migrate")){room_identity=1;room_migrating=1;room_recovery_show();return;}
 if(!strcmp(event,"closed") || !strcmp(event,"disconnected") || !strcmp(event,"fenced") || !strcmp(event,"removed")){
  static uint8_t title[128],body[2048];encoding_from_utf8("멀티플레이 연결 종료",title,sizeof(title));
  encoding_from_utf8(detail[0]?detail:"방장이 나가서 방이 종료되었습니다.",body,sizeof(body));
  window_popup_dialog_show_confirmation(title,body,0,room_closed_reply);
 }
}
/* Positions are set per screen by room_layout(). */
static generic_button room_buttons[]={
 {0,0,128,28,room_action,0,33},{0,0,128,28,room_action,0,32},{0,0,176,28,room_action,0,31},
 {0,0,128,28,room_action,0,1},{0,0,176,28,room_action,0,2},{0,0,176,28,room_action,0,3},{0,0,80,32,room_action,0,4},
 {0,0,128,28,room_action,0,5},{0,0,160,28,room_action,0,6},
 {0,0,176,30,room_action,0,10},{0,0,176,30,room_action,0,11},{0,0,176,30,room_action,0,12},{0,0,176,30,room_action,0,13},
 {0,0,176,30,room_action,0,14},{0,0,176,30,room_action,0,15},{0,0,176,30,room_action,0,16},{0,0,176,30,room_action,0,17},
 {0,0,320,32,room_action,0,20},{0,0,320,32,room_action,0,21},{0,0,496,32,room_action,0,23},{0,0,496,32,room_action,0,24},
 {0,0,160,28,room_action,0,25},{0,0,96,32,room_action,0,26},{0,0,128,32,room_action,0,27},{0,0,160,28,room_action,0,28},
 {0,0,160,28,room_action,0,29},{0,0,96,32,room_action,0,30},
 {0,0,320,32,room_action,0,34},{0,0,320,32,room_action,0,35},{0,0,128,28,room_action,0,36},
 {0,0,176,28,room_action,0,37},{0,0,176,28,room_action,0,38},{0,0,80,32,room_action,0,39},{0,0,320,32,room_action,0,40},
 {0,0,164,28,room_action,0,41},
 {0,0,128,28,room_action,0,42}   /* 관전 허용 (waiting room, the host; multiplayer_spectate.inc) */
};
#define ROOM_BUTTON_COUNT ((int)(sizeof(room_buttons)/sizeof(room_buttons[0])))
static int room_visible(int id){
 if(id==31)return 0;   /* no in-game problem report: the release notes say where to write (user 2026-11-14) */
 if(room_network_entry()){
  if(id==6)return 1;
  if(network_mode==ROOM_LAN_MENU)return id==20 || id==21;
  switch(network_mode){
   case 0:return id==34 || id==35 || (ROOM_UPDATE && id==40);
   case 1:return id==25 || id==23 || id==24 || id==27;
   case 2:return id==25 || id==26 || id==27 || id==30;
   case 4:return id==36 || id==27;
   case 5:return id==37 || id==38 || id==39 || id==41;
  }
  return 0;
 }
 if(id==22)return 0;
 if(!room_identity)return id==5 || id==6 || id==27;
 if(room_picker)return (id>=10 && id<10+room_choice_count) || id==28 || id==29;
 #ifdef MP_SPECTATE
 if(id==42)return spectate_waiting_label()[0]!=0;
#endif
 return (id>=2 && id<=4) || id==32 || id==33;   /* no "도시 변경": choose on the map/roster, preview on hover (user 2026-11-13) */
}
static int room_wide(void){return !room_network_entry() && room_identity && !room_picker && !room_selector && !scene_room && !room_options_open;}
static void room_dialog_size(int *w,int *h){
 if(room_network_entry()){
  if(network_mode==5){*w=800;*h=600;}else if(network_mode==4){*w=480;*h=288;}
  else if(network_mode==1 || network_mode==2){*w=576;*h=416;}else if(ROOM_UPDATE && network_mode==0){*w=512;*h=368;}else{*w=432;*h=320;}
  return;
 }
 if(!room_identity){*w=480;*h=288;return;}
 if(room_picker){*w=576;*h=448;return;}
 *w=800;*h=600;
}
static void room_put(int id,int x,int y,int width,int height){
 for(int i=0;i<ROOM_BUTTON_COUNT;i++)if(room_buttons[i].parameter1==id){generic_button *b=&room_buttons[i];b->x=x;b->y=y;b->width=width;b->height=height;}
}
static void room_layout(void){
 int w,h;room_dialog_size(&w,&h);int bottom=h-56;
 if(room_network_entry()){
  if(network_mode==5){
   room_put(39,672,ROOM_INPUT_Y,80,32);
   /* 나가기 / 방 만들기 / 입장 / 알림판 (user 2026-11-17) */
   room_put(6,48,ROOM_BOTTOM_Y,164,28);room_put(37,228,ROOM_BOTTOM_Y,164,28);room_put(38,408,ROOM_BOTTOM_Y,164,28);room_put(41,588,ROOM_BOTTOM_Y,164,28);
  }else if(network_mode==4){
   room_put(27,336,92,104,32);room_put(6,40,bottom,128,28);room_put(36,312,bottom,128,28);
  }else if(network_mode!=1 && network_mode!=2){
   int x=ROOM_UPDATE && network_mode==0?96:56;   /* the first screen is wider with the update check: its answer is one line */
   room_put(20,56,104,320,32);room_put(21,56,148,320,32);room_put(34,x,104,320,32);room_put(35,x,148,320,32);room_put(40,x,192,320,32);
   room_put(6,40,bottom,160,28);room_put(31,232,bottom,160,28);   /* main menu (back) left */
  }else{
   room_put(23,40,106,496,32);room_put(24,40,168,496,32);
   room_put(26,336,106,96,32);room_put(30,440,106,96,32);
   room_put(27,408,network_mode==2?260:230,128,32);
   room_put(6,40,bottom,160,28);room_put(25,376,bottom,160,28);
  }
  return;
 }
 if(!room_identity){
  room_put(27,336,92,104,32);
  room_put(6,40,bottom,128,28);room_put(31,176,bottom,128,28);room_put(5,312,bottom,128,28);
  return;
 }
 if(room_picker){
  for(int i=0;i<8;i++)room_put(10+i,48,88+i*34,176,32);
  room_put(28,40,bottom,160,28);room_put(29,376,bottom,160,28);
  return;
 }
 room_put(32,488,56,128,28);room_put(33,624,56,128,28);room_put(42,352,56,128,28);room_put(1,0,0,0,0);
 room_put(4,672,ROOM_INPUT_Y,80,32);
 room_put(2,48,ROOM_BOTTOM_Y,176,28);room_put(31,312,ROOM_BOTTOM_Y,176,28);room_put(3,576,ROOM_BOTTOM_Y,176,28);
 if(input.x!=48 || input.y!=ROOM_INPUT_Y || input.width_blocks!=38){
  input.x=48;input.y=ROOM_INPUT_Y;input.width_blocks=38;
  if(room_identity && !room_picker && !room_selector && !scene_room)input_box_start(&input);
 }
}
/* Disabled buttons still answer a click with the reason. */
/* A start under way (empty seats turned neutral, files being prepared, the countdown): the host's button stops it. */
static int room_starting(void){
 char phase[64];room_read("start-state.txt",phase,sizeof(phase));
 return !strncmp(phase,"preparing",9) || !strncmp(phase,"loading",7) || !strncmp(phase,"countdown",9);
}
static const char *room_ready_reason(void){
 if(!local_role())return "방 연결을 확인하고 있습니다. 잠시 기다려 주세요.";
 if(!room_joined())return "먼저 지도나 참가 목록에서 도시를 선택해 주세요.";
 return 0;
}
/* A warning inside the dark search box: the game's own red font, so the letters look like the rest of the screen
   (user 2026-11-13: the tinted plain font looked thin and spaced out). */
static void room_warning(const char *s,int x,int y){draw_utf8(s,x,y,472,FONT_NORMAL_RED);}
static void room_draw_network(int w,int h){
 char status[1024];room_read("network-status.txt",status,sizeof(status));
 const char *message=notice[0]?notice:status;
#ifdef MP_HALL
 if(network_mode==5){hall_draw();return;}
#endif
#ifdef MP_SERVER_ENTRY
 if(network_mode==4){server_entry_draw(w,h);return;}
#endif
 if(network_mode!=1 && network_mode!=2){
  int lan=network_mode==ROOM_LAN_MENU;
  room_title(lan && ROOM_LAN_MENU?"랜 플레이":"멀티플레이",w);
  room_center(lan?"방장은 방을 만들고, 다른 플레이어는 방장 IP로 입장합니다.":"서버 로비에서 만나거나 랜으로 직접 연결합니다.",68,w,FONT_NORMAL_BLACK);
#ifdef MP_SERVER_ENTRY
  /* The bridge's greeting "방 만들기 또는 입장하기를 선택하세요." belongs to the LAN menu (its buttons): not here (user 2026-11-16). */
  if(!lan){update_check_draw(w);if(strcmp(message,"방 만들기 또는 입장하기를 선택하세요."))room_center(message,280,w,FONT_SMALL_PLAIN);room_busy_draw(1,room_connect_busy(),136,296,240);return;}
#endif
  room_center(message,200,w,FONT_SMALL_PLAIN);
  room_busy_draw(1,room_connect_busy(),96,222,240);
  return;
 }
 if(network_mode==1){
  room_title("방 만들기",w);
  room_center("혼자 할 때는 네트워크에서 '혼자 플레이'를 고르세요.",60,w,FONT_NORMAL_BLACK);
  draw_utf8("사용할 네트워크",40,88,496,FONT_NORMAL_BLACK);
  draw_utf8("시나리오 / 공동 저장",40,150,496,FONT_NORMAL_BLACK);
  draw_utf8("방장 아이디",40,212,350,FONT_NORMAL_BLACK);
  input_box_draw(&name_input);
  /* 시나리오 제작자 모드 (user 2026-11-17: the same in both editions): the original options checkbox, then its line */
  button_border_draw(40,ROOM_MAKER_Y,20,20,0);if(lan_maker)draw_utf8("x",46,ROOM_MAKER_Y+3,12,FONT_NORMAL_BLACK);
  draw_utf8(lan_maker?"시나리오 제작자 모드: 시험용 방 (저장은 제작자 방에서만 이어집니다)":"시나리오 제작자 모드",68,ROOM_MAKER_Y+4,468,lan_maker?FONT_NORMAL_RED:FONT_NORMAL_BLACK);
  uint8_t text[2048];encoding_from_utf8(message,text,sizeof(text));
  text_draw_multiline(text,40,ROOM_MAKER_Y+30,496,0,FONT_SMALL_PLAIN,0);
  room_busy_draw(1,room_connect_busy(),40,ROOM_MAKER_Y+68,460);
  return;
 }
 room_title("방 입장",w);
 room_center("방장에게 받은 IP를 입력하고 검색한 뒤 입장하세요.",60,w,FONT_NORMAL_BLACK);
 draw_utf8("방장 IP",40,88,280,FONT_NORMAL_BLACK);
 input_box *active=room_join_field?&name_input:&network_input;input_box *inactive=room_join_field?&network_input:&name_input;
 inner_panel_draw(inactive->x,inactive->y,inactive->width_blocks,2);text_draw(inactive->text,inactive->x+16,inactive->y+10,FONT_NORMAL_WHITE,0);input_box_draw(active);
 inner_panel_draw(40,150,31,5);
 char info[2048],ip[128];encoding_to_utf8(network_ip,ip,sizeof(ip),0);room_read("network-room-info.txt",info,sizeof(info));
 char *flag=strchr(info,'\n'),*body=flag?strchr(flag+1,'\n'):0;if(flag)*flag=0;
 char searching[8];room_read("network-search-busy.txt",searching,sizeof(searching));
 if(searching[0]=='1')room_busy_draw(5,1,52,180,300);
 else{
  room_busy_draw(5,0,0,0,0);
  if(body && !strcmp(ip,info)){
   /* Line 2 of the search result: '1' joinable, '0 <why>' not now, '2' no answer. The reason is drawn in red inside
      this box, where the eyes already are (user 2026-11-13: an empty box looked like an error). */
   char state=flag[1],none[1]={0};*body=0;char *why=state=='0' && flag[2]==' '?flag+3:none;why[strcspn(why,"\r")]=0;
   if(state=='2'){room_warning("방이 응답하지 않습니다.",52,166);room_warning("방장 IP와 연결을 확인하고 다시 검색해 주세요.",52,186);}
   else{
    int limit=why[0]?207:224;char *line=body+1;int y=158;while(*line && y<limit){char *next=strchr(line,'\n');if(next)*next=0;draw_utf8(line,52,y,472,FONT_NORMAL_WHITE);if(!next)break;line=next+1;y+=17;}
    if(why[0])room_warning(why,52,209);
   }
  }
  else draw_utf8("검색하면 방 정보가 여기에 표시됩니다.",52,182,472,FONT_NORMAL_WHITE);
 }
 draw_utf8("아이디",40,242,350,FONT_NORMAL_BLACK);
 room_center(message,304,w,notice[0]?FONT_NORMAL_RED:FONT_SMALL_PLAIN);
 room_busy_draw(1,room_connect_busy(),40,324,460);
}
static void room_draw_identity(int w,int h){
 (void)h;
 room_title("멀티플레이 입장",w);
 room_center("새 아이디를 입력하거나 저장한 아이디를 고르세요.",60,w,FONT_NORMAL_BLACK);
 if(room_name_waiting){inner_panel_draw(name_input.x,name_input.y,name_input.width_blocks,2);text_draw(player_name,name_input.x+16,name_input.y+10,FONT_NORMAL_WHITE,0);}
 else input_box_draw(&name_input);
 room_center("최대 24자 · 이 PC에서 언제든 다시 고를 수 있습니다.",134,w,FONT_SMALL_PLAIN);
 if(room_name_waiting)room_center("아이디를 저장하고 있습니다.",156,w,FONT_NORMAL_BLACK);
 else if(notice[0])room_center(notice,156,w,FONT_NORMAL_RED);
 room_busy_draw(2,room_name_waiting,120,182,240);
}
static void room_draw_picker(int w,int h){
 (void)h;
 room_title("도시 선택",w);
 room_center("도시를 누르면 오른쪽에서 지도를 미리 볼 수 있습니다.",58,w,FONT_SMALL_PLAIN);
 inner_panel_draw(40,80,12,18);
 char own[64];room_read("own-city.txt",own,sizeof(own));own[strcspn(own,"\r\n")]=0;
 for(int i=0;i<room_choice_count;i++){
  int y=88+i*34,selected=room_preview_index==i;
  if(selected)large_label_draw_custom_size(48,y,176,32);
  int mine=own[0] && !strcmp(room_choices[i].id,own);
  if(!selected && !room_choices[i].available && !mine){uint8_t t[256];encoding_from_utf8(room_choices[i].label,t,sizeof(t));text_draw_ellipsized(t,56,y+1,160,MP_DIM_FONT,COLOR_FONT_GRAY_GREEN);}
  else draw_utf8(room_choices[i].label,56,y+1,160,selected?FONT_NORMAL_BLACK:room_hover==10+i?FONT_NORMAL_GREEN:FONT_NORMAL_WHITE);
  draw_utf8(mine?"내 도시":room_choices[i].available?"선택 가능":"다른 플레이어가 선택",56,y+18,160,FONT_SMALL_PLAIN);
 }
 room_preview_draw();
 if(notice[0])room_center(notice,372,w,FONT_NORMAL_RED);
}
static void room_draw_wide(void){
 char label[512],city[64],ready[8],phase[64];
 room_read("own-city.txt",city,sizeof(city));room_read("ready.txt",ready,sizeof(ready));room_read("start-state.txt",phase,sizeof(phase));
 draw_utf8("멀티플레이 대기실",48,28,300,FONT_LARGE_BLACK);
 char host_version[256];room_read("lobby-host-version.txt",host_version,sizeof(host_version));room_right(host_version,752,32,360,FONT_SMALL_PLAIN);
 char own_version[256];room_read("lobby-own-version.txt",own_version,sizeof(own_version));own_version[strcspn(own_version,"\r\n")]=0;
 if(own_version[0]=='!')room_right(own_version+1,752,46,360,FONT_NORMAL_RED);else room_right(own_version,752,46,360,FONT_SMALL_PLAIN);
 char name[256];encoding_to_utf8(player_name,name,sizeof(name),0);
 snprintf(label,sizeof(label),"%s · %s",name,local_role()==1?"방장":local_role()==2?"참가자":"연결 중");draw_utf8(label,48,58,290,FONT_NORMAL_BLACK);
 char address[128];room_read("room-address.txt",address,sizeof(address));address[strcspn(address,"\r\n")]=0;
 if(address[0]){snprintf(label,sizeof(label),"방 주소 %s",address);draw_utf8(label,48,76,290,FONT_SMALL_PLAIN);}
 lobby_map_draw();
 inner_panel_draw(48,ROOM_CHAT_Y,44,5);
 lobby_chat_draw();
 input_box_draw(&input);
 const char *hint=!city[0]?"지도나 참가 목록에서 내 도시를 고르세요.":local_role()==1?"혼자서도 시작할 수 있습니다. 빈 도시는 중립도시가 됩니다.":ready[0]=='1'?"준비 완료. 방장이 게임을 시작할 때까지 기다려 주세요.":"도시와 아이디를 확인한 뒤 준비해 주세요.";
 if(!strncmp(phase,"preparing",9))hint="빈 도시를 중립도시로 전환하고 있습니다. 잠시 기다려 주세요.";
 char start_detail[512];room_read("start-detail.txt",start_detail,sizeof(start_detail));
 if(!strncmp(phase,"lobby",5) && start_detail[0])hint=start_detail;
 if(!strncmp(phase,"loading",7))hint=start_detail[0]?start_detail:"참가자의 도시 파일 준비를 기다립니다.";
 if(!strncmp(phase,"countdown",9))hint="곧 게임을 시작합니다. 대화창의 카운트다운을 확인하세요.";
 char status[512];room_read("lobby-error.txt",status,sizeof(status));if(status[0])hint=status;
 const char *request=mp_client_request_status();
 int busy=!strncmp(phase,"preparing",9) || !strncmp(phase,"loading",7) || !strncmp(phase,"countdown",9);
 {char pending[64];room_read("command.txt",pending,sizeof(pending));if(pending[0] || room_later_verb[0])busy=1;}   /* a click on its way (high ping, 2026-11-15): shown at once, not after the round trip */
 draw_utf8(request?request:notice[0]?notice:hint,48,ROOM_HINT_Y,busy?520:704,notice[0] && !request?FONT_NORMAL_RED:FONT_SMALL_PLAIN);
 room_busy_draw(4,busy,576,ROOM_HINT_Y,176);
 /* Clear only the acknowledged draft; a failed send preserves the input. */
 if(sent_draft[0]){char ack[2048];room_read("chat-sent.txt",ack,sizeof(ack));char *body=strchr(ack,'\n');if(body && !strcmp(body+1,sent_draft)){char current[1024];encoding_to_utf8(draft,current,sizeof(current),0);memset(sent_draft,0,sizeof(sent_draft));}}
 lobby_hover_preview_draw();   /* city map on hover, on top of the waiting room */
}
static const char *room_button_text(int id,char *label,size_t size){
 char city[64],ready[8];
 switch(id){
  case 1:room_read("own-city.txt",city,sizeof(city));return city[0]?"도시 변경":"도시 선택";
  case 2:return can_return_to_city()?"도시로 돌아가기":"방 나가기";
  case 3:room_read("ready.txt",ready,sizeof(ready));return local_role()==1?(room_starting()?"시작 취소":"게임 시작"):local_role()==2?(ready[0]=='1'?"준비 취소":"준비 완료"):"연결 중";
  case 4:return "보내기";
  case 5:return "입장";
  case 6:return room_network_entry() && !network_mode?"메인 메뉴":network_mode==3?"뒤로":network_mode==5?"나가기":"취소";
  case 20:return "방 만들기";
  case 21:return "방 입장하기";
  case 23:case 24:{int count;network_choice(id==23?"network-adapters.txt":"network-starts.txt",id==23?network_adapter:network_start,label,size,&count);return label[0]?label:"선택 항목 없음";}
  case 25:return network_mode==1?"방 만들기":"입장";
  case 26:return "최근 IP";
  case 27:return "아이디 목록";
  case 28:return "취소";
  case 29:return "이 도시 선택";
  case 30:return "방 검색";
  case 31:return "문제 보고";
  case 32:return "시나리오 정보";
  case 33:return "방 옵션";
  case 34:return "서버 접속";
  case 35:return "랜 플레이";
  case 36:return "접속";
  case 37:return "방 만들기";
  case 38:
#ifdef MP_SPECTATE
   if(network_mode==5 && hall_spectate_offered())return hall_spectate_label(label,size);
#endif
   return "입장";
#ifdef MP_SPECTATE
  case 42:return spectate_waiting_label();
#endif
  case 39:return "보내기";
  case 40:return "업데이트 확인";
#ifdef MP_HALL
  case 41:{int n=hall_board_new_posts();if(n<=0)return "알림판";snprintf(label,size,"알림판 (새 글 %d)",n);return label;}
#endif
 }
 return "";
}
/* High ping (2026-11-15): the bridge takes one command at a time, so a click that came while the previous one was
 * still on its way was dropped without a word - picking a city and pressing 선택 quickly did nothing. The city list
 * now moves at once and the last such request is sent as soon as the bridge is free (a newer one replaces it). */
static int room_send(const char *verb,const char *text){
 if(mp_client_command(verb,text)){if(!strcmp(room_later_verb,verb))room_later_verb[0]=0;return 1;}
 snprintf(room_later_verb,sizeof(room_later_verb),"%s",verb);snprintf(room_later_text,sizeof(room_later_text),"%s",text);room_later_at=time_get_millis();return 0;
}
static void room_send_later(void){
 if(room_later_verb[0] && time_get_millis()-room_later_at>15000)room_later_verb[0]=0;   /* a stale click is never sent */
 if(room_later_verb[0] && mp_client_command(room_later_verb,room_later_text))room_later_verb[0]=0;
}
static void room_draw(void){
 room_send_later();
 if(room_options_open){room_options_draw();return;}
 if(scene_opened && (scene_room || room_selector)){graphics_in_dialog_with_size(800,600);scene_draw();graphics_reset_dialog();return;}
 room_layout();
 room_prefill();room_poll_name();room_read_choices();
 if(room_menu_pending()){
  graphics_in_dialog_with_size(480,160);outer_panel_draw(0,0,30,10);
  room_title("방에서 나오는 중입니다.",480);room_center("연결을 정리하고 있습니다. 잠시 기다려 주세요.",76,480,FONT_NORMAL_BLACK);
  room_busy_draw(0,1,120,108,240);graphics_reset_dialog();return;
 }
 room_busy_draw(0,0,0,0,0);
 if(room_selector){graphics_in_dialog();selector_draw();graphics_reset_dialog();return;}
 if(!room_network_entry() && network_mode){char joined[256];room_read("network-joined-name.txt",joined,sizeof(joined));network_mode=0;
#ifdef MP_HALL
hall_ready=0;hall_creating=0;input_box_stop(&hall_input);
#endif
input_box_stop(&network_input);if(joined[0]){encoding_from_utf8(joined,player_name,sizeof(player_name));room_identity=1;input_box_start(&input);}else input_box_start(&name_input);}
 if(!room_network_entry() && !room_identity){char joined[256];room_read("network-joined-name.txt",joined,sizeof(joined));if(joined[0]){encoding_from_utf8(joined,player_name,sizeof(player_name));room_identity=1;input_box_stop(&name_input);input_box_start(&input);}}
 room_layout();
 int w,h;room_dialog_size(&w,&h);
 graphics_in_dialog_with_size(w,h);
 if(w==800)outer_panel_draw(8,8,49,36);else outer_panel_draw(0,0,w/16,h/16);
 if(room_network_entry())room_draw_network(w,h);
 else if(!room_identity)room_draw_identity(w,h);
 else if(room_picker)room_draw_picker(w,h);
 else room_draw_wide();
 for(int i=0;i<ROOM_BUTTON_COUNT;i++){
  generic_button *b=&room_buttons[i];int id=b->parameter1;if(!room_visible(id) || (id>=10 && id<20))continue;
  char label[2048];const char *text=room_button_text(id,label,sizeof(label));
  large_label_draw_custom_size(b->x,b->y,b->width,b->height);
  /* Selector fields read like a field (left aligned); every real button is centred. */
  int dimmed=(id==3 && room_ready_reason()) || (id==29 && (room_preview_index<0 || room_preview_index>=room_choice_count || !room_choices[room_preview_index].available));
#ifdef MP_HALL
#ifdef MP_SPECTATE
  if(id==38 && hall_spectate_offered())dimmed=dimmed || hall_room_spectate_now>=hall_room_spectate_max || hall_spectate_wait;else
#endif
  dimmed=dimmed || (id==38 && (!hall_room[0] || !hall_room_joinable));
#endif
  font_t label_font=room_hover==id?FONT_NORMAL_RED:FONT_NORMAL_BLACK;
  if(id==23 || id==24){draw_utf8(text,b->x+10,b->y+(b->height-12)/2,b->width-80,label_font);draw_utf8("목록",b->x+b->width-54,b->y+(b->height-12)/2,46,FONT_NORMAL_BLACK);}
  else if(dimmed)mp_button_text(text,b->x+8,b->y+(b->height-12)/2,b->width-16,2); /* same size, gray-green */
  else gift_center(text,b->x+8,b->y+(b->height-12)/2,b->width-16,label_font);
 }
 graphics_reset_dialog();
}
static void room_action(const generic_button *b){
 int id=b->parameter1;
 if(id==33){room_options_begin();return;}
 if(id==32){scene_open_room();return;}
 if(id==31){mp_client_command("network-report","");return;}
 if(room_menu_pending() || room_connect_busy())return;
#ifdef MP_SPECTATE
 if(id==42 && !room_network_entry()){spectate_waiting_click();return;}   /* 관전 허용 of the waiting room (user 2026-11-17: the click never got here) */
#endif
 if(room_network_entry() && ((id>=34 && id<=40) || id==41)){   /* 41: 알림판 of the hall (it never got here either) */
  if(id==35){notice[0]=0;network_mode=3;
#ifdef MP_HALL
   hall_from=0;
#endif
  }
#ifdef MP_SERVER_ENTRY
  else if(id==34)server_entry_begin();
  else if(id==36)server_entry_connect();
  else if(id==40)update_check_begin();
#endif
#ifdef MP_HALL
  else if(id==37){if(hall_entry()!=1)strcpy(notice,"로비에 연결된 뒤에 방을 만들 수 있습니다.");else if(!hall_creating){notice[0]=0;selector_open(5);}}
#ifdef MP_SPECTATE
  else if(id==38 && hall_spectate_offered()){if(hall_room_spectate_now>=hall_room_spectate_max)strcpy(notice,"관전자가 가득 찼습니다.");else if(!hall_spectate_wait)hall_spectate_start();}
#endif
  else if(id==38)hall_join();
  else if(id==41)hall_board_open();
  else if(id==39){hall_send_chat();if(!room_selector)input_box_start(&hall_input);}   /* /관리자: its window keeps the keyboard */
#endif
  return;
 }
 if(id==20 || id==21){notice[0]=0;network_mode=id==20?1:2;input_box_stop(&name_input);room_prefill();if(network_mode==2){room_join_field=0;input_box_start(&network_input);}else{input_box_start(&name_input);network_start=0;mp_client_command("network-refresh-starts","");}return;}
 if(id==23 || id==24 || id==26 || id==27){if(room_name_waiting)return;selector_open(id==23?1:id==24?2:id==26?3:4);return;}
 if(id==30){char host[128];encoding_to_utf8(network_ip,host,sizeof(host),0);if(!host[0]){strcpy(notice,"방장 IP를 입력해 주세요.");return;}if(mp_client_command("network-search",host))notice[0]=0;return;}
 if(id==25){char value[512];if(network_mode==1){char name[256];encoding_to_utf8(player_name,name,sizeof(name),0);if(!name[0]){strcpy(notice,"방장 아이디를 입력해 주세요.");return;}snprintf(value,sizeof(value),"%d %d %d\n%s",network_adapter,network_start,lan_maker?1:0,name);}else{
  char host[128],name[256],info[2048];encoding_to_utf8(network_ip,host,sizeof(host),0);encoding_to_utf8(player_name,name,sizeof(name),0);
  room_read("network-room-info.txt",info,sizeof(info));char *flag=strchr(info,'\n');if(flag)*flag++=0;
  if(!flag || strcmp(info,host)){strcpy(notice,"먼저 방 검색으로 방 정보를 확인해 주세요.");return;}
  if(flag[0]=='2'){strcpy(notice,"방이 응답하지 않습니다. 방장 IP와 연결을 확인하고 다시 검색해 주세요.");return;}
  if(flag[0]!='1'){char none[1]={0},*why=flag[1]==' '?flag+2:none;why[strcspn(why,"\r\n")]=0;snprintf(notice,sizeof(notice),"%s",why[0]?why:"지금은 입장할 수 없는 방입니다. 다시 검색해 주세요.");return;}
  if(!name[0]){strcpy(notice,"아이디를 입력해 주세요.");return;}snprintf(value,sizeof(value),"%s\n%s",host,name);
 }
 if(!mp_client_command(network_mode==1?"network-host-ip":"network-join-found",value))strcpy(notice,"이전 요청을 처리하고 있습니다. 잠시 후 다시 시도해 주세요.");else notice[0]=0;return;}
 if(room_network_entry()){
  if(id==6){
   notice[0]=0;
   if(0){}
#ifdef MP_HALL
   else if(network_mode==5)hall_leave();
#endif
#ifdef MP_SERVER_ENTRY
   else if(network_mode==4)server_entry_cancel();
#endif
   else if(network_mode==1 || network_mode==2){network_mode=ROOM_LAN_MENU;input_box_stop(&network_input);input_box_stop(&name_input);}
   else if(network_mode){network_mode=0;input_box_stop(&network_input);input_box_stop(&name_input);}
   else window_main_menu_show(0);
  }
  return;
 }
 if(id==5){
  if(room_name_waiting)return;
  char name[256];encoding_to_utf8(player_name,name,sizeof(name),0);
  char *first=name;while(*first && (unsigned char)*first<=32)first++;if(first!=name)memmove(name,first,strlen(first)+1);
  size_t length=strlen(name);while(length && (unsigned char)name[length-1]<=32)name[--length]=0;
  if(!name[0]){strcpy(notice,"아이디를 입력해 주세요.");return;}
  for(size_t i=0;name[i];i++)if((unsigned char)name[i]<32 || (unsigned char)name[i]==127){strcpy(notice,"아이디에는 줄바꿈이나 제어 문자를 사용할 수 없습니다.");return;}
  encoding_from_utf8(name,player_name,sizeof(player_name));
  if(room_network_managed()){
   const char *dir=getenv("AUGUSTUS_MP_BRIDGE");char path[2048];snprintf(path,sizeof(path),"%s/network-name-result.txt",dir);remove(path);
   if(!mp_client_command("network-save-name",name)){strcpy(notice,"이전 요청을 처리하고 있습니다. 잠시 후 다시 시도해 주세요.");return;}
   snprintf(room_pending_name,sizeof(room_pending_name),"%s",name);room_name_waiting=1;room_name_started=time_get_millis();notice[0]=0;input_box_stop(&name_input);return;
  }
  room_identity=1;lobby_name_active=0;notice[0]=0;input_box_stop(&name_input);input_box_start(&input);return;}
 if(id==6 || id==28){room_name_waiting=0;if(room_picker){room_picker=0;notice[0]=0;input_box_start(&input);}else room_leave_ask();return;}
 if(id==1){notice[0]=0;room_preview_index=-1;room_read_choices();
  char own[64];room_read("own-city.txt",own,sizeof(own));
  for(int i=0;i<room_choice_count;i++)if(own[0] && !strcmp(room_choices[i].id,own))room_preview_index=i;
  if(room_preview_index>=0)mp_client_command("preview-city",room_choices[room_preview_index].id);
  room_picker=1;input_box_stop(&input);return;}
 if(id>=10 && id<18){room_read_choices();int index=id-10;if(index>=room_choice_count)return;
  room_send("preview-city",room_choices[index].id);room_preview_index=index;room_busy_active[3]=0;notice[0]=0;return;}
 if(id==29){room_read_choices();int index=room_preview_index;if(index<0 || index>=room_choice_count){strcpy(notice,"먼저 왼쪽 목록에서 도시를 골라 주세요.");return;}if(!room_choices[index].available){strcpy(notice,"다른 플레이어가 선택한 도시입니다.");return;}
  char name[256],payload[384];encoding_to_utf8(player_name,name,sizeof(name),0);snprintf(payload,sizeof(payload),"%s\n%s",room_choices[index].id,name);
  room_send("choose-city",payload);room_picker=0;lobby_name_active=0;notice[0]=0;input_box_start(&input);return;}
 generic_button old={0};
 if(id==2){notice[0]=0;if(can_return_to_city())return_from_lobby();else room_leave_ask();return;}
 if(id==3 && local_role()==1 && room_starting()){if(mp_client_command("start-cancel",""))notice[0]=0;return;}   /* user 2026-11-14 */
 if(id==3){const char *reason=room_ready_reason();if(reason){snprintf(notice,sizeof(notice),"%s",reason);return;}notice[0]=0;old.parameter1=local_role()==1?7:3;}
 if(id==4)old.parameter1=5;
 if(old.parameter1)click(&old);
}
static void room_handle(const mouse *m,const hotkeys *h){
 lobby_roster_mouse_x=lobby_roster_mouse_y=-1;
 if(room_options_open){room_options_handle(m,h);return;}
 if(scene_opened && (scene_room || room_selector)){scene_handle(mouse_in_dialog_with_size(m,800,600),h);return;}
 room_layout();
 int w,hh;room_dialog_size(&w,&hh);
 /* the selector windows sit in the standard dialog; the administrator's login (8) and window (9) sit over the 800x600 hall */
 const mouse *local=room_selector && room_selector<8?mouse_in_dialog(m):room_selector>=8?mouse_in_dialog_with_size(m,800,600):mouse_in_dialog_with_size(m,w,hh);
 if(room_wide()){lobby_roster_mouse_x=local->x;lobby_roster_mouse_y=local->y;}
 if(room_selector){selector_handle(local,h);return;}
 room_poll_name();room_hover=0;
 if(room_wide() && lobby_chat_scroll_input(local))return;
 if(room_wide() && local->left.went_up){
  if(lobby_color_click(local->x,local->y))return;
  int index=lobby_roster_hit(local->x,local->y);
  if(index>=0){lobby_map_choose(index);return;}
  index=lobby_map_hit(local->x,local->y);
  if(index>=0){if(lobby_map_cities[index].num)lobby_map_choose(index);else{scene_open_room();scene_city=index;}return;}
 }
 for(int i=0;i<ROOM_BUTTON_COUNT;i++){
  generic_button *b=&room_buttons[i];if(room_visible(b->parameter1) && local->x>=b->x && local->x<b->x+b->width && local->y>=b->y && local->y<b->y+b->height)room_hover=b->parameter1;
 }
 if(h->close_pressed){generic_button b={0};b.parameter1=room_network_entry() || room_picker || !room_identity?6:2;room_action(&b);return;}
 if(room_network_entry() && network_mode==1 && local->left.went_up && local->x>=40 && local->x<536 && local->y>=ROOM_MAKER_Y && local->y<ROOM_MAKER_Y+22 && !room_connect_busy()){lan_maker=!lan_maker;window_request_refresh();return;}
 if(room_network_entry() && network_mode==1){input_box_handle_mouse(local,&name_input);if(input_box_is_accepted()){generic_button b={0};b.parameter1=25;room_action(&b);}}
 if(room_network_entry() && network_mode==2){
  if(local->left.went_up){int field=local->x>=40 && local->x<392 && local->y>=260 && local->y<292?1:local->x>=40 && local->x<328 && local->y>=106 && local->y<138?0:-1;
   if(field>=0 && field!=room_join_field){input_box_stop(room_join_field?&name_input:&network_input);room_join_field=field;input_box_start(room_join_field?&name_input:&network_input);}}
  input_box_handle_mouse(local,room_join_field?&name_input:&network_input);
  if(input_box_is_accepted()){generic_button b={0};b.parameter1=room_join_field?25:30;room_action(&b);input_box_start(room_join_field?&name_input:&network_input);}
 }
 if(room_network_entry() && network_mode==4){input_box_handle_mouse(local,&name_input);if(input_box_is_accepted()){generic_button b={0};b.parameter1=36;room_action(&b);}}
#ifdef MP_HALL
 if(room_network_entry() && network_mode==5 && hall_handle(local)){window_request_refresh();return;}
#endif
 if(!room_network_entry() && !room_picker && !room_name_waiting){if(room_identity && local->left.went_up && local->x>=input.x && local->x<input.x+input.width_blocks*16 && local->y>=input.y && local->y<input.y+32){lobby_name_active=0;input_box_start(&input);}input_box_handle_mouse(local,room_identity?&input:&name_input);if(input_box_is_accepted()){generic_button b={0};b.parameter1=room_identity?4:5;room_action(&b);}}
 for(int i=0;i<ROOM_BUTTON_COUNT;i++)if(room_visible(room_buttons[i].parameter1) && generic_buttons_handle_mouse(local,0,0,&room_buttons[i],1,&focus))return;
 if(room_identity && !entered){char go[8];room_read("auto-enter.txt",go,sizeof(go));if(go[0]=='1' && window_multiplayer_enter_city())return;}
 window_request_refresh();
}
