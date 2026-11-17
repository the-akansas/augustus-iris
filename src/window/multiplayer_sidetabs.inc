/* Left side tabs (Anno-style), drawn over the city view.
 * One grey stone strip holds four original advisor icons (40x40, already framed like buttons).
 * The open icon sits in a 64x64 piece of the panel's own frame; the panel, drawn afterwards,
 * covers that frame's right side and the strip's edge, so the tab runs into its panel.
 * The panel is as tall as what it holds. A click anywhere outside closes it (and does nothing else).
 * Presentation only: numbers come from bridge files and the local city; buttons open existing
 * windows, select a legion or move the camera. */
#include "core/lang.h"
#include "figure/formation.h"
#include "translation/translation.h"
#include "core/string.h"
#include "assets/assets.h"
#define SIDE_HIDE_H 20
#include "graphics/scrollbar.h"
/* When a tab holds more than the screen can show, its content scrolls under the original
 * scrollbar (8 px per step) and the panel widens by two blocks to make room for the bar. */
#define SIDE_SCROLL_STEP 8
static scrollbar_type side_sb;
static int side_scrolling,side_sb_tab;
static int side_offset(void){return side_scrolling?(int)side_sb.scroll_position*SIDE_SCROLL_STEP:0;}
static int side_scroll_offset(void){return side_offset();}
static const int side_icons[4]={7,10,3,1};/* advisor icons: tablet A, coin, columns, military banner */
static const char*side_titles[4]={"해야 할 일","교역 게시판","멀티플레이 상황","군사"};
/* Trade tab: 0 = the trade board (cities, relation, what waits on me), 1 = my posts (무역 현황). */
static int side_trade_view;
static const char*side_title(int tab){return tab==2 && side_trade_view?"무역 현황":side_titles[tab-1];}
static const int side_widths[4]={17,30,22,24};/* panel width in 16 px blocks (the trade board is a wide table) */
static int side_width(int tab){return tab==2 && side_trade_view?17:side_widths[tab-1];}
static unsigned side_read_at;
static int side_measure,side_swallow;
typedef struct {int building,generation,loaded,inbound,leave,away,queue;} side_post;
typedef struct {int id,gift,resource,quantity,post;} side_order;
static side_post side_posts[8];static side_order side_orders[64]; /* every post (up to 5 partners) and its queue */
static int side_post_count,side_order_count,side_road,side_standing;
typedef struct {int incoming,color;char title[128],detail[160];} side_army_row;
static side_army_row side_army[12];static int side_army_count;
/* state: 0 ok, 1 late, 2 reconnecting, 3 left (city is neutral now) */
typedef struct {int state,color,host,me,can_watch,watch,watch_revision;char name[64],city[64],date[48],ping[32],id[64],generation[72];} side_player;
static struct {char id[64];int revision;unsigned sent;} side_watch_wait[8];
static side_player side_players[8];static int side_player_count;static char side_speed[64],side_save[96];
static const char*side_resource_name(int r){for(int i=0;i<(int)(sizeof(trade_resource_ids)/sizeof(*trade_resource_ids));i++)if(trade_resource_ids[i]==r)return trade_names[i];return "물품";}
static void side_trim(char*s){s[strcspn(s,"\r\n")]=0;while(*s==' '){memmove(s,s+1,strlen(s));}size_t n=strlen(s);while(n && s[n-1]==' ')s[--n]=0;}
static void side_read(void){
 unsigned now=time_get_millis();if(side_read_at && now-side_read_at<500)return;side_read_at=now;
 const char*dir=getenv("AUGUSTUS_MP_BRIDGE");if(!dir)return;char path[2048],line[512];FILE*f;
 snprintf(path,sizeof(path),"%s/side-trade.txt",dir);
 if((f=fopen(path,"rb"))){
  side_post_count=side_order_count=side_road=side_standing=0;
  while(fgets(line,sizeof(line),f)){
   side_post p={0};side_order o={0};
   if(line[0]=='P' && side_post_count<8 && sscanf(line+1,"%d %d %d %d %d %d",&p.building,&p.generation,&p.loaded,&p.inbound,&p.leave,&p.away)==6)side_posts[side_post_count++]=p;
   else if(line[0]=='Q' && side_order_count<64 && side_post_count && sscanf(line+1,"%d %d %d %d",&o.id,&o.gift,&o.resource,&o.quantity)==4){o.post=side_post_count-1;side_orders[side_order_count++]=o;side_posts[side_post_count-1].queue++;}
   else if(line[0]=='C')sscanf(line+1,"%d %d",&side_road,&side_standing);
  }
  fclose(f);
 }
 snprintf(path,sizeof(path),"%s/side-army.txt",dir);
 if((f=fopen(path,"rb"))){
  side_army_count=0;
  while(side_army_count<12 && fgets(line,sizeof(line),f)){
   side_army_row*r=&side_army[side_army_count];char*a=strtok(line,"\t"),*b=strtok(0,"\t"),*c=strtok(0,"\t"),*d=strtok(0,"\t\r\n");
   if(!a || !b || !c)continue;r->incoming=atoi(a);r->color=atoi(b);snprintf(r->title,sizeof(r->title),"%s",c);snprintf(r->detail,sizeof(r->detail),"%s",d?d:"");side_army_count++;
  }
  fclose(f);
 }
 /* state colour host me name city date ping, tab separated (game_bridge.side_players) */
 snprintf(path,sizeof(path),"%s/side-players.txt",dir);
 if((f=fopen(path,"rb"))){
  side_player_count=0;
  while(side_player_count<8 && fgets(line,sizeof(line),f)){
   char*part[9];int n=0;char*s=line;line[strcspn(line,"\r\n")]=0;
   while(n<9){part[n++]=s;char*sep=strchr(s,'\t');if(!sep)break;*sep=0;s=sep+1;}
   if(n<8)continue;
   side_player*p=&side_players[side_player_count++];memset(p,0,sizeof(*p));
   if(n>8)snprintf(p->id,sizeof(p->id),"%s",part[8]);
   p->state=atoi(part[0]);p->color=atoi(part[1]);p->host=atoi(part[2]);p->me=atoi(part[3]);
   snprintf(p->name,sizeof(p->name),"%s",part[4]);snprintf(p->city,sizeof(p->city),"%s",part[5]);snprintf(p->date,sizeof(p->date),"%s",part[6]);snprintf(p->ping,sizeof(p->ping),"%s",part[7]);
  }
  fclose(f);
 }
 /* Who may watch my city: city generation editable allowed revision (participant_admin.py) */
 snprintf(path,sizeof(path),"%s/observe-permissions.txt",dir);
 if((f=fopen(path,"rb"))){
  char id[64],gen[72];int editable,allowed,revision;
  while(fgets(line,sizeof(line),f))if(sscanf(line,"%63s %71s %d %d %d",id,gen,&editable,&allowed,&revision)==5)
   for(int i=0;i<side_player_count;i++)if(!strcmp(id,side_players[i].id)){side_player*p=&side_players[i];
    p->can_watch=editable==1 && p->state!=3;p->watch=allowed==1;p->watch_revision=revision;snprintf(p->generation,sizeof(p->generation),"%s",gen);}
  fclose(f);
 }
 /* Room speed and save line: the last two lines of debug-status.txt */
 snprintf(path,sizeof(path),"%s/debug-status.txt",dir);
 if((f=fopen(path,"rb"))){
  side_speed[0]=side_save[0]=0;
  while(fgets(line,sizeof(line),f)){
   char*sep=strstr(line," / ");if(sep)*sep=0;side_trim(line);
   if(!strncmp(line,"방장 목표",strlen("방장 목표")))snprintf(side_speed,sizeof(side_speed),"방장 속도 %s",line+strlen("방장 목표 "));
   else if(strstr(line,"저장"))snprintf(side_save,sizeof(side_save),"%s",line);
  }
  fclose(f);
 }
}
static int side_post_reminders(void){int others,i=post_reminder_find(&others);return i<0?0:1+others;}
static int side_cash_cards(void){int others,i=cash_card_find(&others);return i<0?0:1+others;}
static int side_badge(int tab){
 if(tab==1)return city_notice_count+side_post_reminders()+side_cash_cards();
 if(tab==4){int n=0;for(int i=0;i<side_army_count;i++)n+=side_army[i].incoming;return n;}
 return 0;
}
/* ---------- drawing that can also just measure (side_measure=1) ---------- */
static void sd_text(const char*s,int x,int y,int w,font_t font){if(!side_measure)draw_utf8(s,x,y,w,font);}
static void sd_dim(const char*s,int x,int y,int w){if(side_measure)return;uint8_t t[512];encoding_from_utf8(s,t,sizeof(t));text_draw_ellipsized(t,x,y,w,MP_DIM_FONT,COLOR_FONT_GRAY_GREEN);}
static void sd_inner(int x,int y,int wb,int hb){if(!side_measure)inner_panel_draw(x,y,wb,hb);}
static void sd_chip(int x,int y,int w,int h,color_t c){if(side_measure)return;graphics_fill_rect(x,y,w,h,c);graphics_draw_rect(x,y,w,h,COLOR_BLACK);}
static void sd_row(int x,int y,int w,const char*left,const char*right,font_t font,font_t rfont){
 if(side_measure)return;
 if(right){uint8_t t[160];encoding_from_utf8(right,t,sizeof(t));int tw=text_get_width(t,rfont);draw_utf8(right,x+w-tw,y,tw+2,rfont);draw_utf8(left,x,y,w-tw-12,font);}
 else draw_utf8(left,x,y,w,font);
}
/* An inner (dark) list box sized for rows of `row` px: returns the box height in px. */
static int sd_box(int ix,int iw,int y,int rows,int row){int hb=(rows*row+12+15)/16;sd_inner(ix-4,y-2,(iw+8)/16,hb);return hb*16;}
static int side_hover(int x,int y,int w,int h){const mouse*m=mouse_get();return m->x>=x && m->x<x+w && m->y>=y && m->y<y+h;}

/* Bottom row: one or two equal buttons, centred, 28 px tall, 20 px above the frame's bottom. */
static int side_buttons(const char*a,const char*b,int*bx,int*by,int*bw){
 int ix=side_px+16,iw=side_pw-32;*by=side_py+side_ph-48;*bw=(iw-16)/2;
 if(b){bx[0]=ix;bx[1]=ix+*bw+16;return 2;}
 bx[0]=ix+(iw-*bw)/2;return 1;
}
static void side_draw_buttons(const char*a,const char*b){
 int bx[2],by,bw,n=side_buttons(a,b,bx,&by,&bw);const char*t[2]={a,b};
 for(int i=0;i<n;i++){large_label_draw_custom_size(bx[i],by,bw,28);if(side_hover(bx[i],by,bw,28))button_border_draw(bx[i],by,bw,28,1);gift_center(t[i],bx[i]+4,by+8,bw-8,FONT_NORMAL_BLACK);}
}
static const char*side_button_b(int tab){return tab==2?"지난 거래":0;}
static const char*side_button_a(int tab){return tab==1?(city_notice_log_mode?"할 일 보기":"지난 알림"):tab==2?(side_trade_view?"교역 게시판":"무역 현황"):tab==3?"채팅 기록":"제국 지도";}

/* ---------- notices: the cards lay themselves out inside the panel ---------- */
static int side_notices_bottom(int top){
 if(city_notice_log_mode)city_notice_log_read();
 int y=top;
 if(city_notice_log_mode || city_notice_count)y+=city_notice_panel_height()+4;
 if(side_post_reminders())y+=city_card_h()+4;
 if(side_cash_cards())y+=city_card_h()+4;
 if(y==top)y+=28;
 return y;
}
static void side_draw_notices(int ix,int iw,int top){
 if(!city_notice_count && !side_post_reminders() && !side_cash_cards() && !city_notice_log_mode)sd_dim("지금 할 일이 없습니다.",ix,top+4,iw);
 city_notice_draw();
}
/* ---------- trade ---------- */
static int side_post_slot(const side_post*p){
 if(p->building>0 && (unsigned)p->building<building_count()){const building*bd=building_get(p->building);if(bd->type==BUILDING_PLAYER_TRADE_POST)return bd->subtype.orientation;}
 return 0;
}
static int side_draw_trade(int ix,int iw,int y){
 char a[160],b[96];
 if(!side_post_count){sd_dim("내 전용 교역소가 없습니다.",ix,y,iw);sd_dim("계약을 맺고 교역소를 지으면 여기에 보입니다.",ix,y+22,iw);y+=48;}
 for(int k=0;k<side_post_count;k++){ /* every post; the panel scrolls when they do not fit */
  side_post*p=&side_posts[k];int slot=side_post_slot(p);const char*peer="";color_t c=slot?mp_route_peer_color(slot):0xffcbd1d7;
  for(int i=0;i<partner_count;i++)if(partner_rows[i].slot==slot)peer=partner_label(partner_rows[i].city);
  /* The partner's colour leads the line, the same colour as its roof and flags. */
  sd_chip(ix,y+1,12,14,c);
  snprintf(a,sizeof(a),"%s%s교역소 #%d",peer,peer[0]?" · ":"",p->building);sd_text(a,ix+18,y,iw-18,FONT_NORMAL_BLACK);y+=22;
  /* One dark box per post: the load bar, when it leaves, then this post's own loading order. */
  int rows=p->queue,hb=(48+rows*20+15)/16;
  sd_inner(ix-4,y-2,(iw+8)/16,hb);
  int fill=(iw-8)*(p->loaded>16?16:p->loaded)/16;
  if(!side_measure){graphics_fill_rect(ix+4,y+8,fill,12,c);graphics_draw_rect(ix+4,y+8,iw-8,12,COLOR_BLACK);}
  snprintf(a,sizeof(a),"실린 짐 %d/16포대",p->loaded);
  if(p->away)snprintf(b,sizeof(b),"상단 운송 중");
  else if(p->leave<0)snprintf(b,sizeof(b),p->queue?"짐 모으는 중":"주문 없음");
  else if(p->leave<50)snprintf(b,sizeof(b),"곧 출발");
  else snprintf(b,sizeof(b),"출발까지 %d.%d일",p->leave/50,(p->leave%50)/5);
  sd_row(ix+4,y+26,iw-8,a,b,FONT_NORMAL_WHITE,FONT_NORMAL_WHITE);
  int n=0;for(int i=0;i<side_order_count;i++){side_order*o=&side_orders[i];if(o->post!=k)continue;
   snprintf(a,sizeof(a),"%d  %s %s %d포대",n+1,o->gift?"선물":"판매",side_resource_name(o->resource),o->quantity);sd_text(a,ix+8,y+46+n*20,iw-16,FONT_NORMAL_WHITE);n++;}
  y+=hb*16+4;
  if(p->inbound){snprintf(a,sizeof(a),"교역소로 오는 짐 %d포대",p->inbound);sd_text(a,ix,y,iw,FONT_SMALL_PLAIN);y+=18;}
  y+=6;
 }
 snprintf(a,sizeof(a),"%d편",side_road);sd_row(ix,y,iw,"길 위의 상단",a,FONT_NORMAL_BLACK,FONT_NORMAL_BLACK);
 snprintf(a,sizeof(a),"%d건",side_standing);sd_row(ix,y+22,iw,"지속 계약",a,FONT_NORMAL_BLACK,FONT_NORMAL_BLACK);
 return y+44;
}
/* ---------- trade board: every partner city as a ruled table (same data as the 플레이어 교역 window) ---------- */
#define SIDE_BOARD_ROW 44
static void side_right(const char*s,int right,int y,font_t font,color_t color);
static int side_board_top;
static const char*side_relation(const partner_row*p,int online){
 return !online?"교역 불가":p->state==0?"계약 없음":p->state==2?"계약 제안 받음":p->state==3?"수락 대기 중":
  !p->my_post?"내 교역소 필요":!p->peer_post?"상대 교역소 대기":"거래 가능";
}
static int side_draw_board(int ix,int iw,int y){
 char a[160];int todo=partner_todo();
 sd_text("도시를 누르면 그 도시와의 거래 창이 열립니다.",ix,y,iw-130,FONT_SMALL_PLAIN);
 if(todo){snprintf(a,sizeof(a),"내가 처리할 일 %d건",todo);side_right(a,ix+iw,y,FONT_NORMAL_BLACK,0);}
 y+=24;
 int cx=ix+14,rx=ix+168,gx=ix+290,tw=104,tx=ix+iw-tw;
 sd_text("도시",cx,y,140,FONT_SMALL_PLAIN);sd_text("관계",rx,y,110,FONT_SMALL_PLAIN);sd_text("진행 중",gx,y,110,FONT_SMALL_PLAIN);side_right("내 차례",ix+iw,y,FONT_SMALL_PLAIN,0);
 y+=16;if(!side_measure)graphics_draw_line(ix,ix+iw,y,y,0xff9b8060);
 side_board_top=y;
 if(!partner_count){sd_text("다른 플레이어 도시가 없습니다.",cx,y+12,iw-14,FONT_NORMAL_BLACK);return y+SIDE_BOARD_ROW+8;}
 for(int i=0;i<partner_count;i++){
  partner_row*p=&partner_rows[i];int ry=y+i*SIDE_BOARD_ROW,online=partner_online(p->city);
  if(side_measure)continue;
  if(side_hover(ix,ry+1,iw,SIDE_BOARD_ROW-2))button_border_draw(ix,ry+1,iw,SIDE_BOARD_ROW-2,1);
  sd_chip(ix+2,ry+6,6,SIDE_BOARD_ROW-12,online?mp_route_peer_color(p->slot):0xff9a9a8c);
  uint8_t t[160];encoding_from_utf8(partner_label(p->city),t,sizeof(t));
  text_draw_ellipsized(t,cx,online?ry+14:ry+6,rx-cx-8,FONT_NORMAL_BLACK,online?0:COLOR_FONT_GRAY_GREEN);
  if(!online)draw_utf8("중립 도시 · 접속 끊김",cx,ry+24,rx-cx-8,FONT_SMALL_PLAIN);
  draw_utf8(side_relation(p,online),rx,ry+14,gx-rx-8,FONT_NORMAL_BLACK);
  if(p->running || p->standing)snprintf(a,sizeof(a),"운송 %d · 계약 %d",p->running,p->standing);else snprintf(a,sizeof(a),"없음");
  draw_utf8(a,gx,ry+14,tx-gx-8,FONT_NORMAL_BLACK);
  if(online && (p->inbox || (p->state==1 && !p->my_post && !mp_route_post_for(p->slot)))){
   /* What waits on me: the same gold tag as the 플레이어 교역 window. */
   graphics_fill_rect(tx,ry+9,tw,26,0xfff0d27a);graphics_draw_rect(tx,ry+9,tw,26,COLOR_BLACK);
   if(p->inbox)snprintf(a,sizeof(a),"응답 %d건",p->inbox);else snprintf(a,sizeof(a),"교역소 건설");
   gift_center(a,tx+4,ry+15,tw-8,FONT_NORMAL_BLACK);
  }
  graphics_draw_line(ix,ix+iw,ry+SIDE_BOARD_ROW,ry+SIDE_BOARD_ROW,0xffc8b088);
 }
 return y+partner_count*SIDE_BOARD_ROW+8;
}
/* A row opens that city's trade window; closing it comes back to the city. */
static int side_board_input(const mouse*m){
 if(!m->left.went_up)return 0;
 int ix=side_px+16,iw=side_content_w;
 for(int i=0;i<partner_count;i++){
  int ry=side_board_top+i*SIDE_BOARD_ROW;if(m->x<ix || m->x>=ix+iw || m->y<ry || m->y>=ry+SIDE_BOARD_ROW)continue;
  char city[64];snprintf(city,sizeof(city),"%s",partner_rows[i].city);
  side_tab=0;side_return_tab=2;window_multiplayer_trade_show();
  snprintf(gift_recipient,sizeof(gift_recipient),"%s",city);gift_peer_locked=1;gift_picker=0;gift_received=6;partner_direct=1;partner_answer_dismissed=0;partner_page=0;
  return 1;
 }
 return 0;
}
/* ---------- players ---------- */
static const char*side_state_text(int s){return s==3?"나감 · 중립":s==2?"재접속 대기":s==1?"늦음":"정상";}
static int side_watch_pending(const side_player*p){
 for(int k=0;k<8;k++)if(side_watch_wait[k].id[0] && !strcmp(side_watch_wait[k].id,p->id)){
  if(p->watch_revision>side_watch_wait[k].revision || time_get_millis()-side_watch_wait[k].sent>8000){side_watch_wait[k].id[0]=0;return 0;}
  return 1;}
 return 0;
}
/* Players as a small table: colour | name / city·date | status / ping | watch checkbox.
 * Text sits on the parchment in black like the original advisors; rows are ruled, columns line up. */
#define SIDE_ROW 42
static int side_status_right(int ix,int iw){return ix+iw-34;}
static void side_watch_box(int ix,int iw,int ry,int*x,int*y){*x=ix+iw-22;*y=ry+(SIDE_ROW-20)/2;}
static void side_right(const char*s,int right,int y,font_t font,color_t color){
 if(side_measure)return;uint8_t t[160];encoding_from_utf8(s,t,sizeof(t));int w=text_get_width(t,font);text_draw(t,right-w,y,font,color);
}
/* 관전 (Korean edition, multiplayer_spectate.inc, included later by multiplayer_room.inc): its part under the players */
#if defined(__has_include)
#if __has_include("multiplayer_spectate.inc") && __has_include("multiplayer_hall.inc")
#define MP_SPECTATE 1
#endif
#endif
#ifdef MP_SPECTATE
static int spectate_tab_draw(int ix,int iw,int y);
static int spectate_tab_input(const mouse *m);
#endif
static int side_draw_players(int ix,int iw,int y){
 char a[160],b[160];int late=-1,watch=0,sr=side_status_right(ix,iw);
 /* the host's speed on the left, the joint save on the right; in a longer language the two would run into each other
  * (user 2026-11-17, Spanish): then the save goes on a line of its own */
 {const char *speed=side_speed[0]?side_speed:"방장 속도";uint8_t t[200];
  encoding_from_utf8(speed,t,sizeof(t));int left=text_get_width(t,FONT_NORMAL_BLACK),right=0;
  if(side_save[0]){encoding_from_utf8(side_save,t,sizeof(t));right=text_get_width(t,FONT_SMALL_PLAIN);}
  int apart=right && left+right+12>iw;
  sd_text(speed,ix,y,apart?iw:iw-right-12,FONT_NORMAL_BLACK);
  if(apart){y+=20;sd_text(side_save,ix,y+2,iw,FONT_SMALL_PLAIN);}
  else if(side_save[0])side_right(side_save,ix+iw,y+2,FONT_SMALL_PLAIN,0);}
 y+=26;
 /* column heads */
 for(int i=0;i<side_player_count;i++)if(side_players[i].can_watch)watch=1;
 /* A longer "watch" heading (English "Watch") ran into the status heading: the status column moves left by what
  * the heading needs beyond the box column (user 2026-11-17: "StatusWatch"). */
 if(watch){uint8_t t[64];encoding_from_utf8("관전",t,sizeof(t));int need=text_get_width(t,FONT_SMALL_PLAIN)+10;if(ix+iw-need<sr)sr=ix+iw-need;}
 sd_text("플레이어",ix+12,y,120,FONT_SMALL_PLAIN);side_right("상태",sr,y,FONT_SMALL_PLAIN,0);
 if(watch)side_right("관전",ix+iw,y,FONT_SMALL_PLAIN,0);
 y+=16;
 if(!side_measure)graphics_draw_line(ix,ix+iw,y,y,0xff9b8060);
 if(!side_player_count){sd_text("접속 정보를 기다리는 중입니다.",ix+12,y+12,iw-12,FONT_NORMAL_BLACK);y+=SIDE_ROW;}
 for(int i=0;i<side_player_count;i++){
  side_player*p=&side_players[i];int ry=y+i*SIDE_ROW,gone=p->state==3;
  sd_chip(ix,ry+5,6,SIDE_ROW-10,p->color>=0?mp_player_color(p->color):0xffcbd1d7);
  snprintf(a,sizeof(a),"%s%s%s",p->name,p->host?" (방장)":"",p->me?" (나)":"");
  /* the date is translated by itself (user 2026-11-17: '1/· 기원전 350 Mediolanum' in Spanish, the whole line having
   * met the date's own pattern) */
  int joined=0;
  if(gone)snprintf(b,sizeof(b),"%s · 중립 도시",p->city);else{char city[96];snprintf(city,sizeof(city),"%s",mp_i18n_translate(p->city));snprintf(b,sizeof(b),"%s · %s",city,mp_i18n_translate(p->date));joined=1;}   /* one translation at a time: it answers from one buffer */
  if(!side_measure){
   uint8_t t[160];encoding_from_utf8(a,t,sizeof(t));text_draw_ellipsized(t,ix+12,ry+6,sr-ix-12-64,FONT_NORMAL_BLACK,gone?COLOR_FONT_GRAY_GREEN:0);
   if(joined)mp_i18n_suspend(1);
   encoding_from_utf8(b,t,sizeof(t));text_draw_ellipsized(t,ix+12,ry+24,sr-ix-12-56,FONT_SMALL_PLAIN,gone?COLOR_FONT_GRAY_GREEN:0);
   if(joined)mp_i18n_suspend(0);
  }
  side_right(side_state_text(p->state),sr,ry+6,p->state==1 || p->state==2?FONT_NORMAL_RED:FONT_NORMAL_BLACK,gone?COLOR_FONT_GRAY_GREEN:0);
  if(!gone)side_right(p->ping,sr,ry+24,FONT_SMALL_PLAIN,0);
  if(p->can_watch && !side_measure){
   int x,yy;side_watch_box(ix,iw,ry,&x,&yy);int pending=side_watch_pending(p);
   /* The original options checkbox: a 20 px button border with an x. */
   button_border_draw(x,yy,20,20,pending || side_hover(x,yy,20,20));
   if(p->watch && !pending)text_draw(string_from_ascii("x"),x+6,yy+3,FONT_NORMAL_BLACK,0);
  }
  if(!side_measure)graphics_draw_line(ix,ix+iw,ry+SIDE_ROW,ry+SIDE_ROW,0xffc8b088);
  if((p->state==1 || p->state==2) && late<0)late=i;
 }
 y+=side_player_count*SIDE_ROW+8;
 if(late>=0){snprintf(a,sizeof(a),"%s 쪽을 기다리는 중입니다.",side_players[late].city);sd_text(a,ix,y,iw,FONT_NORMAL_BLACK);y+=22;}
 if(watch){sd_dim("관전에 x 표시: 그 플레이어가 내 도시를 볼 수 있습니다",ix,y,iw);y+=20;}
#ifdef MP_SPECTATE
 y=spectate_tab_draw(ix,iw,y+4);
#endif
 return y;
}
static int side_players_list_top(void){return side_py+52+26+16-side_offset();}
static int side_players_input(const mouse*m){
 if(!m->left.went_up)return 0;
 int ix=side_px+16,iw=side_content_w,y=side_players_list_top();
 for(int i=0;i<side_player_count;i++){
  side_player*p=&side_players[i];if(!p->can_watch)continue;
  int x,yy;side_watch_box(ix,iw,y+i*SIDE_ROW,&x,&yy);
  if(m->x<x || m->x>=x+20 || m->y<yy || m->y>=yy+20)continue;
  if(side_watch_pending(p))return 1;
  char payload[200];snprintf(payload,sizeof(payload),"%s\n%s\n%d\n%d",p->id,p->generation,p->watch_revision,!p->watch);
  if(mp_client_command("observe-permission",payload))
   for(int k=0;k<8;k++)if(!side_watch_wait[k].id[0]){snprintf(side_watch_wait[k].id,sizeof(side_watch_wait[k].id),"%s",p->id);side_watch_wait[k].revision=p->watch_revision;side_watch_wait[k].sent=time_get_millis();break;}
  return 1;
 }
 return 0;
}
/* ---------- army: my legions like an RTS unit list; click selects and moves the camera ---------- */
typedef struct {int id,own,selectable;} side_unit;
static side_unit side_units[12];static int side_unit_count;
static void side_collect_units(void){
 side_unit_count=0;
 for(int i=1;i<formation_count() && side_unit_count<12;i++){
  const formation*m=formation_get(i);if(!m->in_use)continue;
  int own=m->is_legion && !m->mp_expedition_role,visitor=m->mp_expedition_id && (m->mp_expedition_role==1 || m->mp_expedition_role==2);
  if(!own && !visitor)continue;
  int away=own && (m->in_distant_battle || m->mp_expedition_id);
  side_unit u={i,own,!away && m->num_figures>0};side_units[side_unit_count++]=u;
 }
}
static void side_unit_lines(const formation*m,int own,char*title,size_t ts,uint8_t*detail,size_t ds){
 char head[96],tail[96];
 if(own){
  encoding_to_utf8(lang_get_string(m->legion_name_group,m->legion_name_id),title,(int)ts,0);
  int off=m->morale/5;if(off>20)off=20;
  const char*state=m->in_distant_battle?"황제 원정":m->mp_expedition_id?"파견 중":m->recent_fight?"교전 중":m->is_at_fort?"요새 대기":"출동";
  /* The unit kind leads the line, in the original advisor's words. */
  translation_key kind=m->figure_type==FIGURE_FORT_JAVELIN?TR_WINDOW_ADVISOR_JAVELIN:m->figure_type==FIGURE_FORT_MOUNTED?TR_WINDOW_ADVISOR_MOUNTED:
   m->figure_type==FIGURE_FORT_INFANTRY?TR_WINDOW_ADVISOR_MILITARY_INFANTRY:m->figure_type==FIGURE_FORT_ARCHER?TR_WINDOW_ADVISOR_MILITARY_ARCHER:TR_WINDOW_ADVISOR_LEGIONARIES;
  snprintf(head,sizeof(head)," %d명 · 사기 ",formation_legion_count_alive_soldiers(m->id));
  snprintf(tail,sizeof(tail),"%s",m->empire_service?" · 황제 차출":"");
  snprintf(title+strlen(title),ts-strlen(title),"\t%s",state); /* state goes right-aligned on the title line */
  size_t n=0;const uint8_t*k=translation_for(kind);while(*k && n+1<ds)detail[n++]=*k++;detail[n]=0;
  encoding_from_utf8(head,detail+n,(int)(ds-n));n=strlen((char*)detail);
  const uint8_t*word=lang_get_string(138,37+off);while(*word && n+1<ds)detail[n++]=*word++;detail[n]=0;
  encoding_from_utf8(tail,detail+n,(int)(ds-n));
 }else{
  snprintf(title,ts,"%s",m->mp_expedition_role==2?"방문 공격군":"방문 지원군");
  snprintf(head,sizeof(head),"%d명 · %s",m->num_figures,m->mp_expedition_role==2?"우리 도시를 공격 중":m->layout==FORMATION_MOP_UP?"자동 · 적 추적":"수동 · 위치 고수");
  encoding_from_utf8(head,detail,(int)ds);
 }
}
static int side_army_list_top;
/* Row buttons: the military advisor's own three (go to the legion, return, empire service), same icons, 30x30.
 * Fixed columns from the right so the icons line up; a unit only shows what applies to it:
 *   own legion in the city: all three · own legion away on an expedition: return (= call it back)
 *   visiting support: go, return (= send it home to its owner) · visiting attackers: go */
#include "figure/formation_legion.h"
#include "city/warning.h"
#define SIDE_UNIT_BTN 30
#define SIDE_UNIT_BTN_W 102
static int side_unit_button_x(int ix,int iw,int kind){return ix+iw-4-SIDE_UNIT_BTN-(3-kind)*34;}
static int side_unit_has(const side_unit*u,const formation*m,int kind){
 if(u->own){
  if(m->in_distant_battle)return 0;
  if(m->mp_expedition_id)return kind==2;
  return 1;
 }
 return kind==1 || (kind==2 && m->mp_expedition_role==1);
}
static const char*side_unit_hint(const side_unit*u,const formation*m,int kind){
 if(kind==1)return "이 부대가 있는 곳을 비춥니다.";
 if(kind==3)return m->empire_service?"황제 원정 차출을 끕니다.":"황제 원정 차출을 켭니다.";
 if(!u->own)return "지원군을 주인 도시로 돌려보냅니다. 두 번 눌러 확정.";
 if(m->mp_expedition_id)return "파견한 군단을 불러들입니다. 두 번 눌러 확정.";
 return m->is_at_fort?"이미 요새에 있습니다.":"요새로 돌려보냅니다.";
}
static void side_unit_say(const char*utf8){static uint8_t text[200];encoding_from_utf8(utf8,text,sizeof(text));city_warning_show_custom(text,NEW_WARNING_SLOT);}
static unsigned side_unit_asked_at;static int side_unit_asked_id;
static void side_unit_press(const side_unit*u,int kind){
 formation*m=formation_get(u->id);
 if(kind==1){if(m->x_home || m->y_home)city_view_go_to_grid_offset(map_grid_offset(m->x_home,m->y_home));return;}
 if(kind==3){formation_toggle_empire_service(m->id);formation_calculate_figures();return;}
 if(u->own && !m->mp_expedition_id){if(!m->in_distant_battle && !m->is_at_fort)formation_legion_return_home(m);return;}
 /* Sending a legion across the empire is asked twice (5 seconds), like the legion panel. */
 unsigned now=time_get_millis();
 if(side_unit_asked_id!=u->id || now-side_unit_asked_at>5000){side_unit_asked_id=u->id;side_unit_asked_at=now;
  side_unit_say(u->own?"한 번 더 누르면 파견한 군단을 불러들입니다.":"한 번 더 누르면 이 지원군을 주인에게 돌려보냅니다.");return;}
 char command[48];
 if(u->own)snprintf(command,sizeof(command),"recall %d",u->id);else snprintf(command,sizeof(command),"dismiss %u",m->mp_expedition_id);
 side_unit_asked_id=0;
 side_unit_say(!mp_client_command("army",command)?"이전 요청을 처리 중입니다. 잠시 뒤 다시 눌러 주세요.":u->own?"군단을 불러들입니다. 돌아오는 데 시간이 걸립니다.":"지원군을 돌려보냅니다. 곧 도시를 떠납니다.");
}
static int side_draw_army(int ix,int iw,int y){
 side_collect_units();
 sd_text("내 지도의 부대",ix,y,iw,FONT_NORMAL_BLACK);y+=22;side_army_list_top=y;
 int rows=side_unit_count?side_unit_count:1,h=sd_box(ix,iw,y,rows,40);const char*hint=0;
 if(!side_unit_count)sd_text("아직 부대가 없습니다.",ix+4,y+8,iw-8,FONT_NORMAL_WHITE);
 for(int i=0;i<side_unit_count;i++){
  const formation*m=formation_get(side_units[i].id);int ry=y+6+i*40;char title[128];uint8_t detail[256];
  side_unit_lines(m,side_units[i].own,title,sizeof(title),detail,sizeof(detail));
  if(side_measure)continue;
  int tw=iw-SIDE_UNIT_BTN_W-4; /* text keeps clear of the three button columns */
  if(side_units[i].selectable && side_hover(ix,ry,tw,38))button_border_draw(ix,ry-2,tw+2,40,1);
  int x=ix+4;
  /* No unit picture; a visitor keeps its owner's colour mark. */
  if(!side_units[i].own){color_t c=mp_army_token_color(m->mp_expedition_id);graphics_fill_rect(x,ry+2,6,32,c?c:0xffcbd1d7);graphics_draw_rect(x,ry+2,6,32,COLOR_BLACK);x+=12;}
  for(int kind=1;kind<=3;kind++){
   if(!side_unit_has(&side_units[i],m,kind))continue;
   int bx=side_unit_button_x(ix,iw,kind),by=ry+3,over=side_hover(bx,by,SIDE_UNIT_BTN,SIDE_UNIT_BTN),icon=image_group(GROUP_FORT_ICONS);
   if(kind==2)icon+=side_units[i].own && !m->mp_expedition_id && m->is_at_fort?2:1;
   if(kind==3)icon+=m->empire_service?3:4;
   button_border_draw(bx,by,SIDE_UNIT_BTN,SIDE_UNIT_BTN,over);image_draw(icon,bx+3,by+3,COLOR_MASK_NONE,SCALE_NONE);
   if(over)hint=side_unit_hint(&side_units[i],m,kind);
  }
  font_t f=side_units[i].own?FONT_NORMAL_WHITE:m->mp_expedition_role==2?FONT_NORMAL_RED:FONT_NORMAL_WHITE;
  char*state=strchr(title,'\t');if(state)*state++=0;
  int sw=0;if(state){uint8_t t[96];encoding_from_utf8(state,t,sizeof(t));sw=text_get_width(t,FONT_NORMAL_WHITE);text_draw(t,ix+tw-4-sw,ry+2,FONT_NORMAL_WHITE,0);sw+=10;}
  if(side_units[i].selectable || !side_units[i].own)draw_utf8(title,x,ry+2,tw-(x-ix)-4-sw,f);
  else{uint8_t t[160];encoding_from_utf8(title,t,sizeof(t));text_draw_ellipsized(t,x,ry+2,tw-(x-ix)-4-sw,FONT_NORMAL_WHITE,COLOR_FONT_GRAY_GREEN);}
  text_draw_ellipsized(detail,x,ry+20,tw-(x-ix)-4,FONT_SMALL_PLAIN,0);
 }
 y+=h+6;
 /* Expeditions on the empire map: what I sent and what is coming to me. */
 int shown=0;
 for(int k=0;k<2;k++){
  int n=0;for(int i=0;i<side_army_count;i++)n+=side_army[i].incoming==k;if(!n)continue;
  sd_text(k?"우리 도시로 오는 부대":"파견 상황",ix,y,iw,FONT_NORMAL_BLACK);y+=22;
  for(int i=0;i<side_army_count && shown<12;i++){side_army_row*r=&side_army[i];if(r->incoming!=k)continue;
   int x=ix;if(r->color>=0){sd_chip(x,y+1,6,14,mp_player_color(r->color));x+=12;}
   char line[300];snprintf(line,sizeof(line),"%s · %s",r->title,r->detail);sd_text(line,x,y,iw-(x-ix),k?FONT_NORMAL_RED:FONT_NORMAL_BLACK);y+=20;shown++;}
  y+=6;
 }
 if(side_unit_count)sd_dim(hint?hint:"이름을 누르면 선택 · 오른쪽 단추는 자문관과 같습니다.",ix,y,iw),y+=20;
 return y;
}
/* ---------- layout ---------- */
static int side_content(int tab,int ix,int iw,int top){
 if(tab==1){if(!side_measure)side_draw_notices(ix,iw,top);return side_notices_bottom(top);}
 if(tab==2)return side_trade_view?side_draw_trade(ix,iw,top):side_draw_board(ix,iw,top);
 if(tab==3)return side_draw_players(ix,iw,top);
 return side_draw_army(ix,iw,top);
}
static void side_layout(void){
 int vx,vy,vw,vh;city_view_get_viewport(&vx,&vy,&vw,&vh);
 side_px=vx+SIDE_PANEL_X;side_py=vy+SIDE_PANEL_Y;side_pw=side_width(side_tab?side_tab:1)*16;side_content_w=side_pw-32;
 if(!side_tab){side_ph=0;side_scrolling=0;return;}
 side_measure=1;int bottom=side_content(side_tab,side_px+16,side_content_w,side_py+52);side_measure=0;
 int hb=(bottom-side_py+12+28+20+15)/16,max=(vh-SIDE_PANEL_Y-8)/16;
 int alerts=window_multiplayer_trade_alert_top();if(alerts>0 && (alerts-6-side_py)/16<max)max=(alerts-6-side_py)/16; /* stay above the bottom banners */
 /* Never shorter than the stone strip, and always below the open tab's icon. */
 int least=side_tab*4+2;if(least<(4*SIDE_SLOT)/16+1)least=(4*SIDE_SLOT)/16+1;
 if(hb<least)hb=least;
 side_scrolling=hb>max;
 if(side_scrolling){
  hb=max;side_pw+=32;
  int view=hb*16-52-60,total=bottom-(side_py+52);
  side_sb.x=side_px+side_pw-16-24;side_sb.y=side_py+48;side_sb.length=view+8;side_sb.scrollable_width=side_pw-16;
  side_sb.elements_in_view=(unsigned)(view/SIDE_SCROLL_STEP);side_sb.step_size=3;
  if(side_sb_tab!=side_tab){side_sb_tab=side_tab;scrollbar_init(&side_sb,0,(unsigned)((total+SIDE_SCROLL_STEP-1)/SIDE_SCROLL_STEP));}
  else scrollbar_update_total_elements(&side_sb,(unsigned)((total+SIDE_SCROLL_STEP-1)/SIDE_SCROLL_STEP));
 }else side_sb_tab=0;
 side_ph=hb*16;
}
/* Height taken by the pinned to-do cards (0 while the notice tab shows them itself). */
static int side_pinned_height(void){if(side_tab==1)return 0;return (side_post_reminders()?city_card_h()+4:0)+(side_cash_cards()?city_card_h()+4:0);}
/* ---------- arrival card (top right) while the notice tab is shut ---------- */
static unsigned long long side_cash_toasted;
static city_notice*side_toast_notice(void){for(int i=city_notice_count-1;i>=0;i--)if(city_notices[i].sequence==city_toast_sequence)return &city_notices[i];return 0;}
/* The card's text, or 0 when there is nothing to show. */
static const char*side_toast_text(char*buf,size_t size){
 city_notice*n=side_toast_notice();if(n)return n->text;
 int others,cash=city_toast_sequence?-1:cash_card_find(&others);if(cash<0)return 0;
 snprintf(buf,size,"%d Dn이 도착했습니다 · %s",deal_rows[cash].money,partner_label(deal_rows[cash].peer));return buf;
}
static int side_toast_rect(int*x,int*y,int*w,int*h){
 if(side_tab==1)city_toast_until=0;
 if((int)(city_toast_until-time_get_millis())<=0)return 0;
 char buf[256];const char*text=side_toast_text(buf,sizeof(buf));if(!text)return 0;
 /* Beside the notice tab, like a note sliding out of it; past an open panel if another tab is open. */
 int vx,vy,vw,vh;city_view_get_viewport(&vx,&vy,&vw,&vh);*x=side_pinned_left();*y=side_pinned_top()+side_pinned_height();
 *w=280;if(*x+*w>vx+vw-8)*w=vx+vw-8-*x;if(*w<160)return 0;
 /* The whole message, wrapped (at most three lines), then one small hint line. */
 uint8_t t[512];encoding_from_utf8(text,t,sizeof(t));int lines=text_measure_multiline(t,*w-20,FONT_NORMAL_BLACK,0);
 if(lines<1)lines=1;if(lines>3)lines=3;*h=10+lines*18+24;return 1;
}
/* For the room notes at the top (multiplayer_chat.c, user 2026-11-17): they start right of the side tabs (or their open
 * panel) and below what stays there: the folded notice, the to-do cards and the note sliding out of the tabs. */
int window_multiplayer_pinned_left(void){return side_pinned_left();}
int window_multiplayer_pinned_bottom(void){
 int x,y,w,h,others,bottom=side_pinned_top();
 if(side_tab!=1){post_reminder_rect(&x,&y,&w);if(post_reminder_find(&others)>=0)y+=city_card_h()+4;if(cash_card_find(&others)>=0)y+=city_card_h()+4;if(y>bottom)bottom=y;}
 if(side_toast_rect(&x,&y,&w,&h) && y+h>bottom)bottom=y+h;
 return bottom;
}
static void side_toast_poll(void){
 int others,i=cash_card_find(&others);
 if(i>=0 && deal_rows[i].id!=side_cash_toasted){side_cash_toasted=deal_rows[i].id;city_toast_sequence=0;city_toast_until=time_get_millis()+15000;}
}
static void side_toast_draw(void){
 int x,y,w,h;if(!side_toast_rect(&x,&y,&w,&h))return;
 char buf[256];const char*text=side_toast_text(buf,sizeof(buf));city_notice*n=side_toast_notice();
 large_label_draw_custom_size(x,y,w,h);graphics_draw_rect(x,y,w,h,0xffffcf70);
 if(side_hover(x,y,w,h))button_border_draw(x,y,w,h,1);
 uint8_t t[512];encoding_from_utf8(text,t,sizeof(t));
 graphics_set_clip_rectangle(x,y,w,h-22);text_draw_multiline(t,x+10,y+9,w-20,0,FONT_NORMAL_BLACK,0);graphics_reset_clip_rectangle();
 draw_utf8(n && (n->kind==3 || n->kind==4)?"눌러서 제안 보기 · 오른쪽 클릭 닫기":"눌러서 알림 탭 열기 · 오른쪽 클릭 닫기",x+10,y+h-20,w-20,FONT_SMALL_PLAIN);
}
static int side_toast_input(const mouse*m){
 int x,y,w,h;if(!side_toast_rect(&x,&y,&w,&h) || m->x<x || m->x>=x+w || m->y<y || m->y>=y+h)return 0;
 if(m->right.went_up){city_toast_until=0;return 1;}
 if(!m->left.went_up)return 1;
 city_notice*n=side_toast_notice();city_toast_until=0;
 if(n && (n->kind==3 || n->kind==4)){city_notice copy=*n;if(city_notice_open_proposal(&copy))return 1;}
 side_tab=1;city_notice_log_mode=0;return 1;
}
/* ---------- frame ---------- */
#include "multiplayer_throne.inc" /* Race for the Throne: coup notices and the paranoia display, drawn with the tabs */
static void side_tabs_draw_tabs(void);
/* Draw order follows click order (user 2026-11-17: nothing covered may still take, or lose, a click): the throne box,
 * its card and the maker tools first, the side tabs over them (throne_hud_input gives way where they are drawn over);
 * a throne dialog or the scoreboard last, over everything, as it alone is clicked; no side tab stays open under it.
 * Opening a side tab closes the maker panel, and the panel closes a side tab (multiplayer_dev.inc). */
static void side_tabs_draw(void){
 static int side_tab_seen;
 if(side_tab && side_tab!=side_tab_seen)th_dev_close();
 side_tab_seen=side_tab;
 int modal=throne_hud_modal();if(modal && side_tab)side_close();
 if(!modal)throne_hud_draw();
 side_tabs_draw_tabs();
 if(modal)throne_hud_draw();
}
static void side_tabs_draw_tabs(void){
 side_read();city_notice_read();partner_read();side_toast_poll();side_layout();
 int vx,vy;side_view(&vx,&vy);int sx=vx,sy=vy+SIDE_PANEL_Y;
 if(side_hidden){
  /* Folded away: a narrow handle with a right arrow (and a red mark when something waits). */
  large_label_draw_bg(sx,sy,SIDE_HANDLE_W,SIDE_SLOT);graphics_draw_rect(sx,sy,SIDE_HANDLE_W,SIDE_SLOT,0xff2c241a);/* narrower than a full label */
  if(side_hover(sx,sy,SIDE_HANDLE_W,SIDE_SLOT))button_border_draw(sx,sy,SIDE_HANDLE_W,SIDE_SLOT,1);
  int arrow=assets_get_image_id("UI","Expand Menu Icon");if(arrow)image_draw(arrow,sx+(SIDE_HANDLE_W-14)/2,sy+(SIDE_SLOT-14)/2,COLOR_MASK_NONE,SCALE_NONE);
  if(side_badge(1)+side_badge(4)){graphics_fill_rect(sx+6,sy+6,8,8,0xffb02a20);graphics_draw_rect(sx+6,sy+6,8,8,COLOR_BLACK);}
  post_reminder_draw();cash_card_draw();side_toast_draw();return;
 }
 /* Hide control above the strip, like a browser's tab-bar toggle. */
 large_label_draw_custom_size(sx,sy-SIDE_HIDE_H-2,SIDE_STRIP_W,SIDE_HIDE_H);
 if(side_hover(sx,sy-SIDE_HIDE_H-2,SIDE_STRIP_W,SIDE_HIDE_H))button_border_draw(sx,sy-SIDE_HIDE_H-2,SIDE_STRIP_W,SIDE_HIDE_H,1);
 {int arrow=assets_get_image_id("UI","Expand Menu Icon Left");if(arrow)image_draw(arrow,sx+(SIDE_STRIP_W-14)/2,sy-SIDE_HIDE_H-2+(SIDE_HIDE_H-14)/2,COLOR_MASK_NONE,SCALE_NONE);}
 large_label_draw_custom_size(sx,sy,SIDE_STRIP_W,4*SIDE_SLOT);graphics_shade_rect(sx+1,sy+1,SIDE_STRIP_W-2,4*SIDE_SLOT-2,3);graphics_draw_rect(sx,sy,SIDE_STRIP_W,4*SIDE_SLOT,0xff2c241a);
 for(int i=0;i<4;i++){
  int y=sy+i*SIDE_SLOT,ix=sx+(SIDE_STRIP_W-40)/2,iy=y+12;
  if(side_tab==i+1)outer_panel_draw(ix-12,y,4,4);
  image_draw(image_group(GROUP_ADVISOR_ICONS)+side_icons[i],ix,iy,COLOR_MASK_NONE,SCALE_NONE);
  int badge=side_badge(i+1);
  if(badge){char t[8];snprintf(t,sizeof(t),"%d",badge>9?9:badge);int bx=ix+25,by=iy+2;graphics_fill_rect(bx,by,13,13,0xffb02a20);graphics_draw_rect(bx,by,13,13,COLOR_BLACK);gift_center(t,bx,by+2,13,FONT_SMALL_PLAIN);}
 }
 if(side_tab!=1){post_reminder_draw();cash_card_draw();} /* to-dos stay in view */
 side_toast_draw();
 if(!side_tab)return;
 outer_panel_draw(side_px,side_py,side_pw/16,side_ph/16);
 draw_utf8(side_title(side_tab),side_px+16,side_py+16,side_pw-32,FONT_LARGE_BLACK);
 graphics_push_outer_clip(side_px+8,side_py+48,side_content_w+16,side_ph-48-56);
 side_content(side_tab,side_px+16,side_content_w,side_py+52-side_offset());
 graphics_pop_outer_clip();
 if(side_scrolling)scrollbar_draw(&side_sb);
 side_draw_buttons(side_button_a(side_tab),side_button_b(side_tab));
}
static void side_close(void){if(side_tab==1 && !city_notice_log_mode)city_notice_ack_visible();side_tab=0;city_notice_log_mode=0;}
void window_multiplayer_chat_history_show_from_city(void); /* multiplayer_chat.c */
static int side_tabs_input(const mouse*m){
 throne_notices_post();   /* posting may open a popup window: done while handling input, never while drawing */
 if(throne_hud_input(m))return 1;   /* the throne box (top right) takes its own clicks */
 /* The release of a click that closed the panel belongs to that click. */
 if(side_swallow){if(m->left.went_up || m->right.went_up)side_swallow=0;if(!m->left.is_down && !m->right.is_down)side_swallow=0;return 1;}
 if(side_toast_input(m))return 1;
 if(side_tab!=1 && (post_reminder_input(m) || cash_card_input(m)))return 1;
 int vx,vy;side_view(&vx,&vy);int sx=vx,sy=vy+SIDE_PANEL_Y;side_layout();
 if(side_hidden){
  if(m->x>=sx && m->x<sx+SIDE_HANDLE_W && m->y>=sy && m->y<sy+SIDE_SLOT){if(m->left.went_up)side_hidden=0;return 1;}
  return 0;
 }
 if(m->x>=sx && m->x<sx+SIDE_STRIP_W && m->y>=sy-SIDE_HIDE_H-2 && m->y<sy-2){if(m->left.went_up){side_close();side_hidden=1;}return 1;}
 if(m->x>=sx && m->x<sx+SIDE_STRIP_W && m->y>=sy && m->y<sy+4*SIDE_SLOT){
  if(m->left.went_up){int t=(m->y-sy)/SIDE_SLOT+1;int was=side_tab;side_close();side_tab=was==t?0:t;}
  return 1;
 }
 if(!side_tab)return 0;
 if(m->x<side_px || m->x>=side_px+side_pw || m->y<side_py || m->y>=side_py+side_ph){
  /* Anywhere else: the first click only closes the panel. */
  if(m->left.went_down || m->right.went_down){side_close();side_swallow=1;return 1;}
  if(m->left.went_up || m->right.went_up){side_close();return 1;}
  return 0;
 }
 if(m->right.went_up){side_close();return 1;}
 int bx[2],by,bw,n=side_buttons(side_button_a(side_tab),side_button_b(side_tab),bx,&by,&bw);
 if(m->y>=by && m->y<by+28){
  for(int i=0;i<n;i++)if(m->x>=bx[i] && m->x<bx[i]+bw && m->left.went_up){
   if(side_tab==1)city_notice_action(3,0);
   else if(side_tab==2){if(i){side_tab=0;window_multiplayer_history_show();history_from_form=2;side_return_tab=2;}else{side_trade_view=!side_trade_view;side_sb_tab=0;}}
   else if(side_tab==3){side_tab=0;side_return_tab=3;window_multiplayer_chat_history_show_from_city();}
   else {side_tab=0;window_empire_show();}
  }
  return 1;
 }
 if(side_scrolling && scrollbar_handle_mouse(&side_sb,m,0))return 1;
 /* Only the visible part of the content takes clicks (the rest is scrolled out of view). */
 if(m->y<side_py+48 || m->y>=side_py+side_ph-56)return 1;
 if(side_tab==1){city_notice_input(m);return 1;}
#ifdef MP_SPECTATE
 if(side_tab==3 && spectate_tab_input(m))return 1;
#endif
 if(side_tab==3){side_players_input(m);return 1;}
 if(side_tab==2 && !side_trade_view){side_board_input(m);return 1;}
 if(side_tab==4 && m->left.went_up){
  int ix=side_px+16,iw=side_content_w;side_collect_units();
  for(int i=0;i<side_unit_count;i++){int ry=side_army_list_top+6+i*40;
   if(m->x<ix || m->x>=ix+iw || m->y<ry || m->y>=ry+38)continue;
   const formation*f=formation_get(side_units[i].id);
   if(m->x>=ix+iw-SIDE_UNIT_BTN_W-4){
    for(int kind=1;kind<=3;kind++){int bx=side_unit_button_x(ix,iw,kind);
     if(side_unit_has(&side_units[i],f,kind) && m->x>=bx && m->x<bx+SIDE_UNIT_BTN && m->y>=ry+3 && m->y<ry+3+SIDE_UNIT_BTN)side_unit_press(&side_units[i],kind);}
    return 1;
   }
   if(f->x_home || f->y_home)city_view_go_to_grid_offset(map_grid_offset(f->x_home,f->y_home));
   /* An own legion at home is selected like the original: the next map click moves it.
    * A visiting support legion too: its host places it, changes its layout or sends it back (legion panel). */
   if((side_units[i].own || f->mp_expedition_role==1) && side_units[i].selectable){side_tab=0;window_city_military_show(f->id);}
   return 1;
  }
 }
 return 1;
}
/* ---------- the trade panel on the empire map ---------- */
static int side_empire_open;
int window_multiplayer_side_trade_open(void){return side_empire_open;}
void window_multiplayer_side_trade_toggle(void){side_empire_open=!side_empire_open;}
static void side_empire_rect(int x,int y,int maxh){
 side_px=x;side_py=y;side_pw=17*16;
 side_measure=1;int bottom=side_draw_trade(side_px+16,side_pw-32,side_py+52);side_measure=0;
 int hb=(bottom-side_py+12+28+20+15)/16;if(hb*16>maxh)hb=maxh/16;side_ph=hb*16;
}
void window_multiplayer_side_trade_draw(int x,int y,int maxh){
 if(!side_empire_open || !entered)return;
 side_read();partner_read();side_empire_rect(x,y,maxh);
 outer_panel_draw(side_px,side_py,side_pw/16,side_ph/16);
 draw_utf8("무역 현황",side_px+16,side_py+16,side_pw-32,FONT_LARGE_BLACK);
 graphics_push_outer_clip(side_px+8,side_py+48,side_pw-16,side_ph-48-56);
 side_draw_trade(side_px+16,side_pw-32,side_py+52);graphics_pop_outer_clip();
 side_draw_buttons("닫기","교역 게시판");   /* close left, the board right */
}
int window_multiplayer_side_trade_input(const mouse*m,int x,int y,int maxh){
 if(!side_empire_open || !entered)return 0;
 side_empire_rect(x,y,maxh);
 if(m->x<side_px || m->x>=side_px+side_pw || m->y<side_py || m->y>=side_py+side_ph)return 0;
 if(m->right.went_up){side_empire_open=0;return 1;}
 int bx[2],by,bw,n=side_buttons("a","b",bx,&by,&bw);
 if(m->left.went_up && m->y>=by && m->y<by+28)for(int i=0;i<n;i++)if(m->x>=bx[i] && m->x<bx[i]+bw){if(!i)side_empire_open=0;else window_multiplayer_trade_show();}
 return 1;
}
