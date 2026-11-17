#include "assets/assets.h"
/* 800x600 partner list and per-partner deal table.
 * Presentation and explicit UI commands only: every row comes from
 * trade-partners.txt / trade-deals.txt published by trade_partner_bridge.py.
 * Nothing here reserves cargo, moves a caravan or changes money. */
#define PARTNER_W 800
#define PARTNER_H 600
#define PARTNER_PAGE 6
typedef struct {int slot,state,my_post,peer_post,running,standing,inbox,revision;char city[64];} partner_row;
typedef struct {char peer[64],status[256];int kind,id_type,resource,quantity,money,outgoing,phase,actions,revision,cycle,repeat;unsigned long long id;} deal_row;
static partner_row partner_rows[8];
static deal_row deal_rows[128];
static int partner_count,deal_count,partner_page,partner_direct,partner_stale=1,partner_answering;
static unsigned partner_read_at,partner_row_focus,partner_bar_focus;
static int partner_dialog_h=600;
static int partner_answer_dismissed,partner_ready_notice;
static void counter_open(int index);
static int counter_return=6; /* the screen the trade-adjustment dialog was opened from */
static void cash_open(int back);

static void partner_read(void){
 unsigned now=time_get_millis();if(partner_read_at && now-partner_read_at<250)return;partner_read_at=now;
 const char*dir=getenv("AUGUSTUS_MP_BRIDGE");partner_stale=1;if(!dir)return;
 char path[2048],line[512];int version,count;long long stamp;
 snprintf(path,sizeof(path),"%s/trade-partners.txt",dir);FILE*f=fopen(path,"rb");
 if(f){
  static partner_row next[8];int ok=0;memset(next,0,sizeof(next));
  if(fgets(line,sizeof(line),f) && sscanf(line,"%d %lld %d",&version,&stamp,&count)==3 && version==1 && count>=0 && count<=8){
   ok=1;
   for(int i=0;i<count && ok;i++){
    partner_row*p=&next[i];
    if(!fgets(line,sizeof(line),f) || sscanf(line,"%d %63s %d %d %d %d %d %d %d",&p->slot,p->city,&p->state,&p->my_post,&p->peer_post,&p->running,&p->standing,&p->inbox,&p->revision)!=9 ||
       p->slot<1 || p->slot>8 || p->state<0 || p->state>3)ok=0;
   }
  }
  fclose(f);
  if(ok){memcpy(partner_rows,next,sizeof(next));partner_count=count;long long age=(long long)time(0)-stamp;partner_stale=age<0 || age>5;}
 }
 snprintf(path,sizeof(path),"%s/trade-deals.txt",dir);f=fopen(path,"rb");
 if(f){
  static deal_row next[128];int ok=0;memset(next,0,sizeof(next));
  if(fgets(line,sizeof(line),f) && sscanf(line,"%d %lld %d",&version,&stamp,&count)==3 && version==1 && count>=0 && count<=128){
   ok=1;
   for(int i=0;i<count && ok;i++){
    deal_row*d=&next[i];
    if(!fgets(line,sizeof(line),f) || sscanf(line,"%63s %d %d %llu %d %d %d %d %d %d %d %d %d",d->peer,&d->kind,&d->id_type,&d->id,&d->resource,&d->quantity,&d->money,&d->outgoing,&d->phase,&d->actions,&d->revision,&d->cycle,&d->repeat)!=13 ||
       d->kind<0 || d->kind>3 || d->id_type<0 || d->id_type>1 || !d->id || d->resource<0 || d->resource>=RESOURCE_MAX || d->phase<-1 || d->phase>4 ||
       !fgets(d->status,sizeof(d->status),f)){ok=0;break;}
    d->status[strcspn(d->status,"\r\n")]=0;
   }
  }
  fclose(f);
  if(ok){memcpy(deal_rows,next,sizeof(next));deal_count=count;}
 }
}
static const char*partner_label(const char*city){for(int i=0;i<gift_peer_count;i++)if(!strcmp(gift_peers[i].id,city))return gift_peers[i].label;return city;}
static int partner_online(const char*city){for(int i=0;i<gift_peer_count;i++)if(!strcmp(gift_peers[i].id,city))return gift_peers[i].online;return 0;}
static partner_row*partner_selected(void){for(int i=0;i<partner_count;i++)if(!strcmp(partner_rows[i].city,gift_recipient))return &partner_rows[i];return 0;}
static int gift_peer_post_ready(void){partner_read();partner_row*p=partner_selected();return p && p->peer_post;}
static const char*partner_resource_name(int resource){for(int i=0;i<MP_TRADE_RESOURCE_COUNT;i++)if(trade_resource_ids[i]==resource)return trade_names[i];return "물품";}
static int partner_todo(void){int n=0;for(int i=0;i<partner_count;i++){n+=partner_rows[i].inbox;if(partner_rows[i].state==1 && !partner_rows[i].my_post && partner_online(partner_rows[i].city))n++;}return n;}
static void partner_to_list(void){gift_received=5;gift_peer_locked=0;partner_direct=0;notice[0]=0;}
static void partner_close(void){trade_tab=history_tab=army_tab=0;notice[0]=0;partner_answer_dismissed=0;window_go_back();}
static void partner_button(const generic_button*b,const char*text,int enabled){
 mp_label_button(b->x,b->y,b->width,b->height,text,enabled?0:2);
}

/* ---------- partner list: as tall as the roster needs ---------- */
static void partner_list_click(const generic_button*b){
 int i=b->parameter1;
 if(i==100){window_multiplayer_history_show();history_from_form=3;return;}
 if(i==101){return_from_lobby();return;}
 if(i<0 || i>=partner_count)return;
 snprintf(gift_recipient,sizeof(gift_recipient),"%s",partner_rows[i].city);
 gift_peer_locked=1;gift_picker=0;gift_received=6;partner_page=0;partner_direct=0;partner_answer_dismissed=0;notice[0]=0;
}
static generic_button partner_list_rows[]={
 {36,120,728,54,partner_list_click,0,0},{36,176,728,54,partner_list_click,0,1},{36,232,728,54,partner_list_click,0,2},
 {36,288,728,54,partner_list_click,0,3},{36,344,728,54,partner_list_click,0,4},{36,400,728,54,partner_list_click,0,5},
 {36,456,728,54,partner_list_click,0,6}
};
/* 40px from the stone border, 28px above its bottom edge. */
static generic_button partner_list_bar[]={{584,532,160,28,partner_list_click,0,100},{56,532,160,28,partner_list_click,0,101}};   /* back left, history right */
static int partner_list_layout(int*inner_blocks,int*outer_blocks){
 int shown=partner_count>7?7:partner_count,rows=shown?shown:1;
 *inner_blocks=(rows*56+8+15)/16;int bottom=116+*inner_blocks*16;
 partner_list_bar[0].y=partner_list_bar[1].y=(short)(bottom+16);
 *outer_blocks=(bottom+16+28+28-20+15)/16;partner_dialog_h=20+*outer_blocks*16+20;
 return shown;
}
static void partner_list_draw(void){
 gift_read_peers();partner_read();char label[512];int inner,outer,shown=partner_list_layout(&inner,&outer);
 graphics_in_dialog_with_size(PARTNER_W,partner_dialog_h);
 outer_panel_draw(16,20,48,outer);
 draw_utf8("플레이어 교역",40,40,420,FONT_LARGE_BLACK);
 snprintf(label,sizeof(label),"내가 처리할 일 %d건",partner_todo());draw_utf8(label,580,48,180,FONT_NORMAL_BLACK);
 draw_utf8(partner_stale?"교역 정보를 받아오는 중입니다.":"도시를 누르면 그 도시와의 계약, 제안, 운송을 봅니다.",40,76,720,partner_stale?FONT_NORMAL_RED:FONT_NORMAL_BLACK);
 draw_utf8("도시",68,100,180,FONT_SMALL_PLAIN);draw_utf8("관계",280,100,160,FONT_SMALL_PLAIN);
 draw_utf8("진행 중",448,100,180,FONT_SMALL_PLAIN);draw_utf8("내 차례",644,100,110,FONT_SMALL_PLAIN);
 inner_panel_draw(32,116,46,inner);
 for(int i=0;i<shown;i++){
  partner_row*p=&partner_rows[i];int y=120+i*56,online=partner_online(p->city);
  if(partner_row_focus==(unsigned)(i+1))button_border_draw(36,y,728,54,1);
  graphics_fill_rect(48,y+9,10,36,online?mp_route_peer_color(p->slot):0xff9a9a8c);graphics_draw_rect(48,y+9,10,36,COLOR_BLACK);
  draw_utf8(partner_label(p->city),68,online?y+20:y+9,200,FONT_NORMAL_WHITE);
  if(!online)draw_utf8("중립 도시 · 접속 끊김",68,y+31,200,FONT_NORMAL_GREEN);
  const char*relation=!online?"교역 불가":p->state==0?"계약 없음":p->state==2?"계약 제안 받음":p->state==3?"수락 대기 중":
   !p->my_post?"내 교역소 필요":!p->peer_post?"상대 교역소 대기":"거래 가능";
  draw_utf8(relation,280,y+20,160,FONT_NORMAL_WHITE);
  if(p->running || p->standing)snprintf(label,sizeof(label),"운송 %d건 · 계약 %d건",p->running,p->standing);else snprintf(label,sizeof(label),"없음");
  draw_utf8(label,448,y+20,188,FONT_NORMAL_WHITE);
  if(online && (p->inbox || (p->state==1 && !p->my_post && !mp_route_post_for(p->slot)))){
   graphics_fill_rect(644,y+14,112,26,0xfff0d27a);graphics_draw_rect(644,y+14,112,26,COLOR_BLACK);
   if(p->inbox)snprintf(label,sizeof(label),"응답 %d건",p->inbox);else snprintf(label,sizeof(label),"교역소 건설");
   gift_center(label,648,y+20,104,FONT_NORMAL_BLACK);
  }
  if(i+1<shown)graphics_draw_line(40,760,y+55,y+55,0xff6d6750);
 }
 if(!shown)draw_utf8("다른 플레이어 도시가 없습니다.",48,136,700,FONT_NORMAL_WHITE);
 partner_button(&partner_list_bar[0],"거래 이력",1);partner_button(&partner_list_bar[1],return_label(),1);
 const char*request=mp_client_request_status();if(request)gift_center(request,224,partner_list_bar[0].y+7,352,FONT_SMALL_PLAIN);
 graphics_reset_dialog();
}
static void partner_list_handle(const mouse*m,const hotkeys*h){
 if(h->close_pressed){return_from_lobby();return;}
 int inner,outer,shown=partner_list_layout(&inner,&outer);
 const mouse*local=mouse_in_dialog_with_size(m,PARTNER_W,partner_dialog_h);
 if(generic_buttons_handle_mouse(local,0,0,partner_list_rows,shown,&partner_row_focus))return;
 generic_buttons_handle_mouse(local,0,0,partner_list_bar,2,&partner_bar_focus);
}

/* ---------- one partner ---------- */
static int partner_deal_list(int*list){
 int n=0;for(int i=0;i<deal_count;i++)if(!strcmp(deal_rows[i].peer,gift_recipient))list[n++]=i;
 return n;
}
/* A single question gets a small dialog; the city stays visible behind it.
 * The deal table only appears once there is something to list. */
static int partner_compact(const partner_row*p,int online){
 int list[128];
 return !p || !online || p->state!=1 || (!gift_current_post() && !partner_deal_list(list));
}
#define COMPACT_W 448
#define COMPACT_H 224
static void partner_compact_click(const generic_button*b){
 int id=b->parameter1;partner_row*p=partner_selected();char cmd[160];
 if(id==9){if(partner_direct)return_from_lobby();else partner_to_list();return;}
 if(!p || mp_client_request_pending() || !partner_online(gift_recipient))return;
 if(id==4){
  if(p->state==1 && mp_route_select(p->slot)){trade_tab=history_tab=army_tab=0;window_city_show();building_construction_set_type(BUILDING_PLAYER_TRADE_POST,0);}
  return;
 }
 if(id==5){cash_open(1);return;}
 if(id==1 && p->state==0)snprintf(cmd,sizeof(cmd),"route_offer %s",p->city);
 else if((id==2 || id==3) && p->state==2)snprintf(cmd,sizeof(cmd),"route_%s %s %d",id==2?"accept":"reject",p->city,p->revision);
 else return;
 if(mp_client_command("trade",cmd)){notice[0]=0;partner_read_at=0;partner_answering=1;}
}
static int partner_compact_buttons(const partner_row*p,int online,generic_button*out,const char**texts){
 int ids[3],n=0;
 if(p && online){
  if(p->state==0){ids[n]=1;texts[n++]="계약 제안";ids[n]=5;texts[n++]="돈 보내기";}
  else if(p->state==2){ids[n]=3;texts[n++]="거절";ids[n]=2;texts[n++]="수락";}
  else if(p->state==3){ids[n]=5;texts[n++]="돈 보내기";}
  else if(p->state==1 && !p->my_post && !mp_route_post_for(p->slot)){ids[n]=4;texts[n++]="교역소 건설";ids[n]=5;texts[n++]="돈 보내기";}
  else if(p->state==1){ids[n]=5;texts[n++]="돈 보내기";}
 }
 ids[n]=9;texts[n++]=p && online && p->state==2?"나중에":"닫기";
 /* close/later goes first (left), the way forward last (right): rotate it to the front */
 {int id=ids[n-1];const char*t=texts[n-1];for(int i=n-1;i>0;i--){ids[i]=ids[i-1];texts[i]=texts[i-1];}ids[0]=id;texts[0]=t;}
 /* Buttons keep a clear margin inside the stone border. */
 int width=112,gap=16,x=(COMPACT_W-(n*width+(n-1)*gap))/2;
 for(int i=0;i<n;i++){generic_button b={(short)(x+i*(width+gap)),168,(short)width,28,partner_compact_click,0,ids[i],0};out[i]=b;}
 return n;
}
static void partner_compact_draw(const partner_row*p,int online){
 char label[512];int state=p?p->state:-1;
 graphics_in_dialog_with_size(COMPACT_W,COMPACT_H);
 outer_panel_draw(0,0,COMPACT_W/16,COMPACT_H/16);
 graphics_fill_rect(24,22,12,28,p && online?mp_route_peer_color(p->slot):0xff9a9a8c);graphics_draw_rect(24,22,12,28,COLOR_BLACK);
 snprintf(label,sizeof(label),"%s",partner_label(gift_recipient));draw_utf8(label,46,24,COMPACT_W-70,FONT_LARGE_BLACK);
 const char*first=!p?"교역 정보를 받아오는 중입니다.":!online?"플레이어 접속이 끊겨 중립 도시가 되었습니다.":
  state==0?"아직 교역 계약이 없습니다.":state==2?"교역 계약 제안이 왔습니다.":state==3?"교역 계약을 제안했습니다.":"교역 계약이 체결되었습니다.";
 const char*second=!p?"":!online?"지금은 교역할 수 없습니다.":
  state==0?"계약을 맺으면 전용 교역소를 지어 거래할 수 있습니다.":state==2?"수락하면 전용 교역소를 지어 거래할 수 있습니다.":
  state==3?"상대 도시의 수락을 기다리고 있습니다.":"전용 교역소를 지으면 물품을 거래할 수 있습니다.";
 gift_center(first,16,72,COMPACT_W-32,FONT_NORMAL_BLACK);gift_center(second,16,96,COMPACT_W-32,FONT_NORMAL_BLACK);
 const char*request=mp_client_request_status();
 if(request)gift_center(request,16,126,COMPACT_W-32,FONT_SMALL_PLAIN);
 generic_button buttons[3];const char*texts[3];int n=partner_compact_buttons(p,online,buttons,texts);
 for(int i=0;i<n;i++)partner_button(&buttons[i],texts[i],buttons[i].parameter1==9 || !mp_client_request_pending());
 graphics_reset_dialog();
}

/* ---------- money gift: a private whisper, independent of contracts and posts ---------- */
#define CASH_H 272
static int cash_amount=100,cash_back,cash_waiting;
static char cash_error[256];
static uint8_t cash_text[8];
static input_box cash_input={144,92,10,2,FONT_NORMAL_WHITE,0,cash_text,sizeof(cash_text),0,0,0,0,"0123456789"}; /* kept for its text only */
static unsigned cash_focus;
static const int cash_presets[]={100,500,1000}; /* quick-add steps, like the sale form */
static void cash_set(int value){
 if(value<0)value=0;
 if(value>1000000)value=1000000;
 cash_amount=value;snprintf((char*)cash_text,sizeof(cash_text),"%d",value);input_box_refresh_text(&cash_input);cash_error[0]=0;
}
static void cash_sync(void){
 /* The keyboard edits the text; the amount always follows it. */
 int value=0;for(const uint8_t*c=cash_text;*c;c++)if(*c>='0' && *c<='9' && value<=100000)value=value*10+(*c-'0');
 if(value!=cash_amount){cash_amount=value>1000000?1000000:value;cash_error[0]=0;}
}
static void cash_open(int back){
 cash_back=back;cash_waiting=0;gift_picker=0;gift_peer_locked=1;gift_received=7;
 cash_set(0); /* starts empty, like the other forms */
}
static void cash_leave(void){}
static void cash_typed(int v){cash_set(v);}
static void cash_click(const generic_button*b);
/* - [amount] + , then +100 +500 +1,000 초기화 (marble calculator keys), then the two actions. */
static generic_button cash_buttons[]={
 {96,96,32,26,cash_click,0,1},{320,96,32,26,cash_click,0,3},{136,96,176,26,cash_click,0,6},
 {96,128,58,22,cash_click,0,10},{162,128,58,22,cash_click,0,11},{228,128,58,22,cash_click,0,12},{294,128,58,22,cash_click,0,14},
 {232,216,112,28,cash_click,0,4},{104,216,112,28,cash_click,0,5}   /* send right, cancel left */
};
#define CASH_BUTTONS (sizeof(cash_buttons)/sizeof(cash_buttons[0]))
static int cash_can_send(void){
 return partner_online(gift_recipient) && cash_amount>=1 && cash_amount<=city_finance_treasury() && !mp_client_request_pending() && !cash_waiting;
}
static void cash_send(void){
 if(!cash_can_send())return;
 char cmd[192];snprintf(cmd,sizeof(cmd),"offer 1 8 %d 10 %s",cash_amount,gift_recipient);
 if(mp_client_command("trade",cmd)){cash_waiting=1;cash_error[0]=0;}
}
static void cash_click(const generic_button*b){
 int id=b->parameter1;
 if(id==5){cash_leave();if(cash_back){gift_received=6;return;}return_from_lobby();return;}
 if(cash_waiting || mp_client_request_pending())return;
 if(id==1 || id==3){cash_set(cash_amount+(id==1?-100:100));return;}
 if(id>=10 && id<13){cash_set(cash_amount+cash_presets[id-10]);return;}
 if(id==14){cash_set(0);return;}
 if(id==6){window_numeric_input_bound_show(0,0,b,7,1,1000000,cash_typed);return;}
 if(id==4)cash_send();
}
static void cash_draw(void){
 gift_read_peers();partner_read();char label[384];
 if(cash_waiting && !mp_client_request_pending()){
  cash_waiting=0;
  if(mp_client_request_outcome()==1){cash_leave();partner_close();return;}
  const char*error=mp_client_request_status();snprintf(cash_error,sizeof(cash_error),"%s",error?error:"보내지 못했습니다. 잠시 후 다시 시도해 주세요.");
 }
 partner_row*p=partner_selected();int online=partner_online(gift_recipient),treasury=city_finance_treasury();
 graphics_in_dialog_with_size(COMPACT_W,CASH_H);
 outer_panel_draw(0,0,COMPACT_W/16,CASH_H/16);
 graphics_fill_rect(24,22,12,28,p && online?mp_route_peer_color(p->slot):0xff9a9a8c);graphics_draw_rect(24,22,12,28,COLOR_BLACK);
 snprintf(label,sizeof(label),"%s에 돈 보내기",partner_label(gift_recipient));draw_utf8(label,46,24,COMPACT_W-70,FONT_LARGE_BLACK);
 snprintf(label,sizeof(label),"내 자금 %d Dn",treasury);gift_center(label,16,66,COMPACT_W-32,FONT_NORMAL_BLACK);
 /* Calculator keys are marble (bordered parchment); the amount is the light box between - and +. */
 const mouse*cm=mouse_in_dialog_with_size(mouse_get(),COMPACT_W,CASH_H);
 const char*keys[]={"-","+","","+100","+500","+1,000","초기화"};
 for(int i=0;i<7;i++){
  generic_button*b=&cash_buttons[i];int hot=!cash_waiting && cm->x>=b->x && cm->x<b->x+b->width && cm->y>=b->y && cm->y<b->y+b->height;
  if(i==2){snprintf(label,sizeof(label),"%d Dn",cash_amount);
   graphics_fill_rect(b->x+3,b->y+3,b->width-6,b->height-6,0xfff3e4c5);button_border_draw(b->x,b->y,b->width,b->height,1);
   mp_button_text(label,b->x+4,b->y+(b->height-14)/2,b->width-8,0);continue;}
  button_border_draw(b->x,b->y,b->width,b->height,hot);
  mp_button_text(keys[i],b->x+2,b->y+(b->height-14)/2,b->width-4,cash_waiting?2:0);
 }
 const char*hint=!online?"플레이어 접속이 끊겨 보낼 수 없습니다.":cash_amount<1?"보낼 금액을 입력해 주세요.":cash_amount>treasury?"자금이 부족합니다.":
  cash_waiting?"보내는 중입니다.":"금액 칸을 누르면 직접 입력합니다. 받는 사람만 알게 됩니다.";
 gift_center(cash_error[0]?cash_error:hint,16,176,COMPACT_W-32,cash_error[0] || cash_amount>treasury?FONT_NORMAL_RED:FONT_NORMAL_BLACK);
 partner_button(&cash_buttons[7],cash_waiting?"보내는 중":"보내기",cash_can_send());
 partner_button(&cash_buttons[8],"취소",1);
 graphics_reset_dialog();
}
static void cash_handle(const mouse*m,const hotkeys*h){
 if(h->close_pressed){generic_button b={0};b.parameter1=5;cash_click(&b);return;}
 const mouse*local=mouse_in_dialog_with_size(m,COMPACT_W,CASH_H);
 generic_buttons_handle_mouse(local,0,0,cash_buttons,CASH_BUTTONS,&cash_focus);
}

/* Buttons for one row, left to right. Returns their count. */
static int partner_deal_actions(const deal_row*d,int*actions,const char**texts){
 int n=0;
 if(d->actions&1){actions[n]=1;texts[n++]="수락";}
 /* A received one-off sale can be answered with different terms once: the
  * purchase form opens pre-filled, and the original offer is declined only
  * after the new proposal has been sent. No back-and-forth revision loop. */
 if(!d->id_type && d->kind==0 && d->resource && d->money && !d->outgoing && d->quantity>0){actions[n]=16;texts[n++]="조건 변경";}
 if(d->actions&4){actions[n]=4;texts[n++]="거래 조정";}
 if(d->actions&8){actions[n]=8;texts[n++]="다시 제안";}
 if(d->actions&2){actions[n]=2;texts[n++]=d->kind==0?"거절":d->id_type && d->kind!=2?"계약 중단":"취소";}
 /* reject/cancel on the left, accept on the right: reverse the order built above */
 for(int i=0;i<n/2;i++){int a=actions[i];const char*t=texts[i];actions[i]=actions[n-1-i];texts[i]=texts[n-1-i];actions[n-1-i]=a;texts[n-1-i]=t;}
 return n;
}
static void partner_deal_click(const generic_button*b){
 if(mp_client_request_pending() || b->parameter1<0 || b->parameter1>=deal_count)return;
 deal_row*d=&deal_rows[b->parameter1];int action=b->parameter2;char cmd[256];
 if(action==16){
  if(strcmp(d->peer,gift_recipient) || !d->quantity)return;
  int index=-1;for(int i=0;i<MP_TRADE_RESOURCE_COUNT;i++)if(trade_resource_ids[i]==d->resource)index=i;
  if(index<0)return;
  trade_mode=2;trade_resource=index;trade_quantity=d->quantity;trade_price=d->money/d->quantity>0?d->money/d->quantity:1;
  gift_repeat=0;gift_partial=0;gift_page=0;gift_send_pending=0;gift_send_error[0]=0;partner_counter_reject=d->id;gift_received=0;
  return;
 }
 if(!(d->actions&action) || strcmp(d->peer,gift_recipient))return;
 if(!d->id_type){
  if(action!=1 && action!=2)return;
  snprintf(cmd,sizeof(cmd),"%s %llu",action==1?"accept":"reject",d->id);
 }else if(action==4){
  counter_open(b->parameter1);
  return;
 }else{
  building*post=gift_current_post();
  snprintf(cmd,sizeof(cmd),"%s %llu %u %u %d",action==1?"contract_accept":action==8?"contract_resume":"contract_stop",d->id,post?post->id:0,post?post->created_sequence:0,d->revision);
 }
 if(mp_client_command("trade",cmd)){notice[0]=0;partner_read_at=0;partner_answering=d->kind==0;}
}

/* ---------- answering one received offer: a small message, the city stays visible ---------- */
#define ANSWER_W 512
#define ANSWER_H 288
/* A shortage reads as a small red tag with white text: same size, readable on the dark box. */
static void answer_shortage(const char*s,int x,int y,int width){
 uint8_t t[256];encoding_from_utf8(s,t,sizeof(t));int w=text_get_width(t,FONT_SMALL_PLAIN)+8;if(w>width)w=width;
 graphics_fill_rect(x-2,y-3,w,15,0xffb02a20);graphics_draw_rect(x-2,y-3,w,15,COLOR_BLACK);
 text_draw_ellipsized(t,x+2,y,w-6,FONT_SMALL_PLAIN,COLOR_WHITE);
}
/* The small circular-arrow icon beside "내 재고": shows the figure is live and re-reads it on click. */
static unsigned answer_refreshed_at;
static int answer_refresh_rect(int col,int*x,int*y){
 uint8_t t[64];encoding_from_utf8("내 재고",t,sizeof(t));*x=44+2*col+text_get_width(t,FONT_SMALL_PLAIN)+6;*y=116;
 return assets_get_image_id("UI","Rotate Build Icon");
}
static void answer_refresh_draw(int col){
 int x,y,id=answer_refresh_rect(col,&x,&y);if(!id)return;
 const mouse*m=mouse_in_dialog_with_size(mouse_get(),ANSWER_W,ANSWER_H);
 int hot=m->x>=x-2 && m->x<x+16 && m->y>=y-2 && m->y<y+16,flash=time_get_millis()-answer_refreshed_at<500;
 image_draw(id,x,y,COLOR_MASK_NONE,SCALE_NONE);
 if(hot || flash)graphics_draw_rect(x-2,y-2,18,18,flash?0xffffcf70:0xffd8c8a0);
}
/* While the pointer is on the icon, the hint line under the facts says what it does. */
static int answer_refresh_hot(void){
 int x,y;if(!answer_refresh_rect((ANSWER_W-64)/3,&x,&y))return 0;
 const mouse*m=mouse_in_dialog_with_size(mouse_get(),ANSWER_W,ANSWER_H);
 return m->x>=x-2 && m->x<x+16 && m->y>=y-2 && m->y<y+16;
}
static int answer_index(void){
 for(int i=0;i<deal_count;i++)if(deal_rows[i].kind==0 && deal_rows[i].resource && !strcmp(deal_rows[i].peer,gift_recipient))return i;
 return -1;
}
static int answer_counter_kind(const deal_row*d){
 if(d->actions&4)return 4; /* adjust quantity and price of a received contract offer */
 if(!d->id_type && d->money && !d->outgoing && d->quantity>0)return 16; /* other terms for a sale */
 return 0;
}
static int answer_buttons(const deal_row*d,generic_button*out,const char**texts){
 int ids[4],n=0;
 /* later, reject, change, accept: back on the left, the way forward on the right */
 ids[n]=9;texts[n++]="나중에";ids[n]=2;texts[n++]="거절";
 int counter=answer_counter_kind(d);if(counter){ids[n]=counter;texts[n++]=counter==4?"거래 조정":"조건 변경";}
 ids[n]=1;texts[n++]="수락";
 /* 4 buttons still keep 40px sides; the row sits 28px above the bottom edge. */
 int width=96,gap=12,x=(ANSWER_W-(n*width+(n-1)*gap))/2;
 for(int i=0;i<n;i++){generic_button b={(short)(x+i*(width+gap)),232,(short)width,28,0,0,0,ids[i]};out[i]=b;}
 return n;
}
static void answer_draw(int index){
 deal_row*d=&deal_rows[index];partner_row*p=partner_selected();char line[384];
 const char*name=partner_resource_name(d->resource);int selling=d->outgoing,unit=d->quantity?d->money/d->quantity:0;
 graphics_in_dialog_with_size(ANSWER_W,ANSWER_H);
 outer_panel_draw(0,0,ANSWER_W/16,ANSWER_H/16);
 graphics_fill_rect(24,22,12,28,p?mp_route_peer_color(p->slot):0xffcbd1d7);graphics_draw_rect(24,22,12,28,COLOR_BLACK);
 snprintf(line,sizeof(line),d->money?"%s에서 온 교역 제안":"%s에서 온 선물",partner_label(gift_recipient));draw_utf8(line,46,24,ANSWER_W-70,FONT_LARGE_BLACK);
 if(d->id_type && d->revision>0)snprintf(line,sizeof(line),"조건을 조정해 다시 제안했습니다: %s %d포대 · %d Dn",name,d->quantity,d->money);
 else if(!d->money)snprintf(line,sizeof(line),"%s %d포대를 선물로 보냈습니다.",name,d->quantity);
 else snprintf(line,sizeof(line),"%s %d포대를 %d Dn에 %s고 합니다.",name,d->quantity,d->money,selling?"사겠다":"팔겠다");
 gift_center(line,16,66,ANSWER_W-32,FONT_NORMAL_BLACK);
 if(d->id_type && d->repeat)gift_center("재고가 있는 동안 반복되는 지속 거래입니다.",16,86,ANSWER_W-32,FONT_SMALL_PLAIN);
 /* Three facts side by side: goods, money, and what it does to my city. */
 inner_panel_draw(32,108,(ANSWER_W-64)/16,5);
 int col=(ANSWER_W-64)/3;
 image_draw(resource_get_data(d->resource)->image.icon,44,120,COLOR_MASK_NONE,SCALE_NONE);
 draw_utf8(selling?"보낼 물품":"받을 물품",72,118,col-44,FONT_SMALL_PLAIN);
 snprintf(line,sizeof(line),"%s %d포대",name,d->quantity);draw_utf8(line,44,146,col-16,FONT_NORMAL_WHITE);
 draw_utf8(selling?"받을 금액":d->money?"낼 금액":"금액",44+col,118,col-16,FONT_SMALL_PLAIN);
 if(d->money)snprintf(line,sizeof(line),"%d Dn",d->money);else snprintf(line,sizeof(line),"없음");draw_utf8(line,44+col,140,col-16,FONT_NORMAL_WHITE);
 if(d->money){snprintf(line,sizeof(line),"포대당 %d Dn",unit);draw_utf8(line,44+col,162,col-16,FONT_SMALL_PLAIN);}
 int catalog=-1;for(int i=0;i<MP_TRADE_RESOURCE_COUNT;i++)if(trade_resource_ids[i]==d->resource)catalog=i;
 if(selling){
  int have=catalog>=0?gift_available(catalog):0;
  draw_utf8("내 재고",44+2*col,118,col-16,FONT_SMALL_PLAIN);
  snprintf(line,sizeof(line),"%d포대",have);draw_utf8(line,44+2*col,140,col-16,FONT_NORMAL_WHITE);
  snprintf(line,sizeof(line),have>=d->quantity?"거래 후 %d포대":"%d포대 부족",have>=d->quantity?have-d->quantity:d->quantity-have);
  if(have>=d->quantity)draw_utf8(line,44+2*col,162,col-16,FONT_SMALL_PLAIN);else answer_shortage(line,44+2*col,162,col-16);
  answer_refresh_draw(col);
 }else if(d->money){
  int have=city_finance_treasury();
  draw_utf8("내 자금",44+2*col,118,col-16,FONT_SMALL_PLAIN);
  snprintf(line,sizeof(line),"%d Dn",have);draw_utf8(line,44+2*col,140,col-16,FONT_NORMAL_WHITE);
  snprintf(line,sizeof(line),have>=d->money?"거래 후 %d Dn":"%d Dn 부족",have>=d->money?have-d->money:d->money-have);
  if(have>=d->money)draw_utf8(line,44+2*col,162,col-16,FONT_SMALL_PLAIN);else answer_shortage(line,44+2*col,162,col-16);
 }else{
  building*post=gift_current_post();
  draw_utf8("내 교역소",44+2*col,118,col-16,FONT_SMALL_PLAIN);
  if(post)snprintf(line,sizeof(line),"%d/32포대",mp_post_total(post));else snprintf(line,sizeof(line),"없음");
  draw_utf8(line,44+2*col,140,col-16,FONT_NORMAL_WHITE);
 }
 const char*request=mp_client_request_status();
 int short_goods=selling && catalog>=0 && gift_available(catalog)<d->quantity;
 const char*hint=request?request:short_goods?"수락하면 모자란 만큼은 재고가 생기는 대로 실어 보냅니다.":selling?"수락하면 내 상단이 교역소에서 물품을 싣고 출발합니다.":"수락하면 상대 상단이 물품을 싣고 출발합니다. 대금은 하역 후 지급됩니다.";
 if(!d->money && !selling && !request)hint="수락하면 상대 상단이 물품을 싣고 출발합니다.";
 if(!selling && d->money && !request && city_finance_treasury()<d->money)hint="자금이 모자란 채로 상단이 출발하면 거래가 취소되고 물품은 돌아갑니다.";
 if(selling && !request && time_get_millis()-answer_refreshed_at<1500)hint="내 재고를 새로 읽었습니다.";
 else if(selling && !request && answer_refresh_hot())hint="눌러서 내 재고(창고와 교역소)를 새로 읽습니다.";
 gift_center(hint,16,206,ANSWER_W-32,FONT_SMALL_PLAIN);
 generic_button buttons[4];const char*texts[4];int n=answer_buttons(d,buttons,texts);
 for(int i=0;i<n;i++)partner_button(&buttons[i],texts[i],buttons[i].parameter2==9 || !mp_client_request_pending());
 graphics_reset_dialog();
}
static void answer_handle(int index,const mouse*m,const hotkeys*h){
 if(h->close_pressed){if(partner_direct)return_from_lobby();else partner_answer_dismissed=1;return;}
 const mouse*local=mouse_in_dialog_with_size(m,ANSWER_W,ANSWER_H);
 if(deal_rows[index].outgoing && local->left.went_up){
  int x,y;answer_refresh_rect((ANSWER_W-64)/3,&x,&y);
  if(local->x>=x-2 && local->x<x+16 && local->y>=y-2 && local->y<y+16){partner_read_at=0;answer_refreshed_at=time_get_millis();window_invalidate();return;}
 }
 generic_button buttons[4];const char*texts[4];int n=answer_buttons(&deal_rows[index],buttons,texts);
 for(int i=0;i<n;i++){
  generic_button*b=&buttons[i];
  if(local->x<b->x || local->x>=b->x+b->width || local->y<b->y || local->y>=b->y+b->height)continue;
  if(!local->left.went_up)return;
  if(b->parameter2==9){if(partner_direct)return_from_lobby();else partner_answer_dismissed=1;return;}
  generic_button act={0};act.parameter1=index;act.parameter2=b->parameter2;partner_deal_click(&act);return;
 }
}

/* ---------- trade adjustment: same goods, my quantity and unit price; the other side confirms ----------
 * Same controls as the sale/gift form: a value box (click to type), - +, quick-add buttons, reset. */
#define COUNTER_H 352
static unsigned long long counter_deal;
static int counter_quantity_max,counter_unit,counter_money,counter_revision,counter_partial,counter_waiting,counter_selling,counter_resource;
static int counter_q,counter_p;
static int counter_value(void){return counter_q;}
static int counter_price(void){return counter_p;}
static void counter_set(int v){if(v>32)v=32;if(v<1)v=1;counter_q=v;if((long long)counter_q*counter_p>1000000)counter_p=1000000/counter_q;}
static void counter_set_price(int v){int cap=1000000/(counter_q>0?counter_q:1);if(cap>31250)cap=31250;if(v>cap)v=cap;if(v<1)v=1;counter_p=v;}
static void counter_typed_quantity(int v){counter_set(v);}
static void counter_typed_price(int v){counter_set_price(v);}
static void counter_reset(void){counter_q=counter_quantity_max;counter_p=counter_unit>0?counter_unit:1;}
static void counter_open(int index){
 if(index<0 || index>=deal_count)return;deal_row*d=&deal_rows[index];
 if(!d->id_type || d->quantity<1)return;
 counter_deal=d->id;counter_quantity_max=d->quantity;counter_money=d->money;counter_unit=d->money/d->quantity;counter_revision=d->revision;counter_partial=(d->actions&32)!=0;counter_waiting=0;
 counter_selling=d->outgoing;counter_resource=d->resource;
 notice[0]=0;counter_reset();counter_return=gift_received==2?2:6;gift_received=9;
}
static void counter_leave(void){}
static int counter_changed(void){return counter_q!=counter_quantity_max || counter_q*counter_p!=counter_money;}
static const char*counter_reason(void){
 if(counter_q<1 || counter_q>32)return "수량은 1~32포대입니다.";
 if(counter_p<1 || (long long)counter_q*counter_p>1000000)return "가격을 확인해 주세요.";
 if(!counter_changed())return "수량이나 가격을 바꿔 주세요.";
 return 0;
}
static int counter_valid(void){return !counter_reason() && !counter_waiting && !mp_client_request_pending();}
static void counter_send(void){
 const char*why=counter_reason();if(why){snprintf(notice,sizeof(notice),"%s",why);return;}
 if(counter_waiting || mp_client_request_pending())return;
 building*post=gift_current_post();char cmd[192];
 snprintf(cmd,sizeof(cmd),"contract_counter %llu %d %d %u %u %d",counter_deal,counter_revision,counter_q,post && counter_selling?post->id:0,post && counter_selling?post->created_sequence:0,counter_p);
 if(mp_client_command("trade",cmd)){counter_waiting=1;notice[0]=0;}
}
/* ids: 1/2 quantity -/+, 5/6 price -/+, 10 quantity box, 11 price box, 20-22 +1 +5 +10, 23 reset quantity,
 * 30-32 +5 +10 +100 Dn, 33 reset price, 3 send, 4 cancel. Rows keep 28 px buttons; quick-adds are 24 px helpers. */
static generic_button counter_buttons[]={
 {136,96,32,26,0,0,0,1},{176,96,176,26,0,0,0,10},{360,96,32,26,0,0,0,2},
 {136,128,58,22,0,0,0,20},{202,128,58,22,0,0,0,21},{268,128,58,22,0,0,0,22},{334,128,58,22,0,0,0,23},
 {136,176,32,26,0,0,0,5},{176,176,176,26,0,0,0,11},{360,176,32,26,0,0,0,6},
 {136,208,58,22,0,0,0,30},{202,208,58,22,0,0,0,31},{268,208,58,22,0,0,0,32},{334,208,58,22,0,0,0,33},
 {232,296,112,28,0,0,0,3},{104,296,112,28,0,0,0,4}   /* send right, cancel left */
};
#define COUNTER_BUTTONS (int)(sizeof(counter_buttons)/sizeof(*counter_buttons))
static void counter_draw(void){
 char line[256];int v=counter_q,p=counter_p;
 if(counter_waiting && !mp_client_request_pending()){
  counter_waiting=0;
  /* Sent: nothing left to do here. Back to where the player was. */
  if(mp_client_request_outcome()==1){counter_leave();partner_close();return;}
  const char*e=mp_client_request_status();snprintf(notice,sizeof(notice),"%s",e?e:"보내지 못했습니다. 잠시 후 다시 시도해 주세요.");
 }
 graphics_in_dialog_with_size(COMPACT_W,COUNTER_H);
 outer_panel_draw(0,0,COMPACT_W/16,COUNTER_H/16);
 snprintf(line,sizeof(line),"%s에 거래 조정 제안",partner_label(gift_recipient));draw_utf8(line,28,24,COMPACT_W-56,FONT_LARGE_BLACK);
 const char*name=partner_resource_name(counter_resource);
 snprintf(line,sizeof(line),"받은 제안: %s %d포대 · 포대당 %d Dn",name,counter_quantity_max,counter_unit);gift_center(line,16,64,COMPACT_W-32,FONT_NORMAL_BLACK);
 /* Goods stay fixed; only how many and for how much change. */
 draw_utf8("수량",40,102,90,FONT_NORMAL_BLACK);draw_utf8("포대당 가격",40,182,90,FONT_NORMAL_BLACK);
 const mouse*m=mouse_in_dialog_with_size(mouse_get(),COMPACT_W,COUNTER_H);
 for(int i=0;i<COUNTER_BUTTONS;i++){
  generic_button*b=&counter_buttons[i];int id=b->parameter2;const char*text="";char label[32];
  if(id==1 || id==5)text="-";else if(id==2 || id==6)text="+";
  else if(id>=20 && id<=22){snprintf(label,sizeof(label),"+%d",id==20?1:id==21?5:10);text=label;}
  else if(id>=30 && id<=32){snprintf(label,sizeof(label),"+%d",id==30?5:id==31?10:100);text=label;}
  else if(id==23 || id==33)text="초기화";
  else if(id==10){snprintf(label,sizeof(label),"%d 포대",v);text=label;}
  else if(id==11){snprintf(label,sizeof(label),"%d Dn",p);text=label;}
  else if(id==3)text=counter_waiting?"보내는 중":"보내기";else if(id==4)text="취소";
  int hover=m->x>=b->x && m->x<b->x+b->width && m->y>=b->y && m->y<b->y+b->height;
  if(id==10 || id==11){
   /* The value itself, like the sale form: a light box; click to type a number. */
   graphics_fill_rect(b->x+3,b->y+3,b->width-6,b->height-6,0xfff3e4c5);button_border_draw(b->x,b->y,b->width,b->height,1);
   mp_button_text(text,b->x+4,b->y+(b->height-14)/2,b->width-8,0);continue;
  }
  if((id>=20 && id<=23) || (id>=30 && id<=33) || id==1 || id==2 || id==5 || id==6){ /* calculator keys: marble */
   button_border_draw(b->x,b->y,b->width,b->height,hover && !counter_waiting);
   mp_button_text(text,b->x+2,b->y+(b->height-14)/2,b->width-4,counter_waiting?2:0);continue;
  }
  if(id==3){partner_button(b,text,counter_valid());if(hover && counter_valid())button_border_draw(b->x,b->y,b->width,b->height,1);continue;}
  partner_button(b,text,id==4 || !counter_waiting);
  if(hover && (id==4 || !counter_waiting))button_border_draw(b->x,b->y,b->width,b->height,1);
 }
 const char*why=counter_reason();
 snprintf(line,sizeof(line),"%s %s %d포대 · %s 총 %d Dn",counter_selling?"보낼 물품":"받을 물품",name,v,counter_selling?"받을 금액":"낼 금액",v*p);
 gift_center(line,16,248,COMPACT_W-32,why && counter_changed()?FONT_NORMAL_RED:FONT_NORMAL_BLACK);
 int instant=counter_partial && counter_selling && v<counter_quantity_max && (long long)p*counter_quantity_max==counter_money; /* same unit price, fewer sacks */
 gift_center(notice[0]?notice:why?why:instant?"상대가 일부 수량을 허용해 보내면 바로 체결됩니다.":"상대가 다시 확인하면 체결됩니다.",16,268,COMPACT_W-32,notice[0]?FONT_NORMAL_RED:FONT_SMALL_PLAIN);
 graphics_reset_dialog();
}
static void counter_handle(const mouse*m,const hotkeys*h){
 if(h->close_pressed){counter_leave();gift_received=counter_return;return;}
 const mouse*local=mouse_in_dialog_with_size(m,COMPACT_W,COUNTER_H);
 if(!local->left.went_up)return;
 for(int i=0;i<COUNTER_BUTTONS;i++){
  generic_button*b=&counter_buttons[i];
  if(local->x<b->x || local->x>=b->x+b->width || local->y<b->y || local->y>=b->y+b->height)continue;
  int id=b->parameter2;
  if(id==4){counter_leave();gift_received=counter_return;return;}
  if(counter_waiting || mp_client_request_pending())return;
  notice[0]=0;
  if(id==1 || id==2)counter_set(counter_q+(id==1?-1:1));
  else if(id==5 || id==6)counter_set_price(counter_p+(id==5?-1:1));
  else if(id>=20 && id<=22)counter_set(counter_q+(id==20?1:id==21?5:10));
  else if(id>=30 && id<=32)counter_set_price(counter_p+(id==30?5:id==31?10:100));
  else if(id==23)counter_set(1);          /* reset = the minimum, like the sale form */
  else if(id==33)counter_set_price(1);
  else if(id==10)window_numeric_input_bound_show(0,0,b,2,1,32,counter_typed_quantity);
  else if(id==11)window_numeric_input_bound_show(0,0,b,5,1,31250,counter_typed_price);
  else if(id==3)counter_send();
  return;
 }
}
static void partner_bar_click(const generic_button*b){
 int id=b->parameter1;partner_row*p=partner_selected();
 int ready=p && p->state==1 && partner_online(gift_recipient) && gift_current_post() && p->peer_post;
 if(id==2){if(partner_online(gift_recipient))cash_open(1);return;}
 if(id==1){
  if(mp_client_request_pending())return;
  /* A dimmed button must still say why it does nothing. */
  if(!ready){
   snprintf(notice,sizeof(notice),"%s",!gift_current_post()?"먼저 이 도시용 전용 교역소를 지어 주세요.":
    p && !p->peer_post?"상대 도시가 아직 전용 교역소를 짓지 않았습니다. 지으면 물품을 거래할 수 있습니다.":"지금은 제안할 수 없습니다. 상대 도시의 연결을 확인해 주세요.");
   partner_ready_notice=1;return;
  }
  gift_send_pending=0;gift_send_error[0]=0;gift_received=0;gift_page=0;trade_mode=0;
  return;
 }
 if(id==3){if(partner_page>0)partner_page--;return;}
 if(id==4){int list[128];if(partner_page+PARTNER_PAGE<partner_deal_list(list))partner_page++;return;}
 if(id==5 || (id==6 && !partner_direct)){partner_to_list();return;}
 return_from_lobby();
}
static generic_button partner_bar[]={
 /* back/cancel on the left, the way forward on the right (the original game's rule; user 2026-11-13) */
 {584,532,160,28,partner_bar_click,0,1},{416,532,160,28,partner_bar_click,0,2},
 {608,38,76,28,partner_bar_click,0,3},{692,38,76,28,partner_bar_click,0,4},
 {416,532,160,28,partner_bar_click,0,5},{56,532,160,28,partner_bar_click,0,6}
};
static generic_button partner_build_button={520,80,224,28,partner_compact_click,0,4};
/* More deals than fit: the table scrolls a row at a time under the original scrollbar
 * (partner_page is the first row shown) and narrows to make room for the bar. */
#include "graphics/scrollbar.h"
static void partner_scrolled(void);
static scrollbar_type partner_sb={.x=724,.y=124,.length=PARTNER_PAGE*58,.scrollable_width=696,.on_scroll_callback=partner_scrolled,.step_size=1,.elements_in_view=PARTNER_PAGE};
static void partner_scrolled(void){partner_page=(int)partner_sb.scroll_position;window_invalidate();}
static int partner_scrolls(int count){return count>PARTNER_PAGE;}
static int partner_right(int count){return partner_scrolls(count)?716:764;} /* right edge of the row buttons */
/* Table height follows the rows shown; returns the rows shown. */
static int partner_detail_layout(int count,int*inner_blocks,int*outer_blocks,int*bottom){
 if(partner_page>count-PARTNER_PAGE)partner_page=count>PARTNER_PAGE?count-PARTNER_PAGE:0;if(partner_page<0)partner_page=0;
 if(partner_scrolls(count)){static int ready;if(!ready){ready=1;scrollbar_init(&partner_sb,0,(unsigned)count);}partner_sb.elements_in_view=PARTNER_PAGE;scrollbar_update_total_elements(&partner_sb,(unsigned)count);if((int)partner_sb.scroll_position!=partner_page)scrollbar_reset(&partner_sb,(unsigned)partner_page);}
 int rows=count-partner_page;if(rows>PARTNER_PAGE)rows=PARTNER_PAGE;
 *inner_blocks=((rows>0?rows:1)*58+2+15)/16;*bottom=124+*inner_blocks*16;
 for(int i=0;i<6;i++)if(i!=2 && i!=3)partner_bar[i].y=(short)(*bottom+28);
 *outer_blocks=(*bottom+28+28+28-20+15)/16;partner_dialog_h=20+*outer_blocks*16+20;
 return rows>0?rows:0;
}
static void partner_detail_draw(void){
 gift_read_peers();partner_read();
 partner_row*p=partner_selected();int online=partner_online(gift_recipient);char label[512];
 if(partner_answering && !mp_client_request_pending()){
  partner_answering=0;
  /* An answered proposal is finished business: go back to where the player was. */
  if(mp_client_request_outcome()==1){partner_close();return;}
 }
 if(!partner_answer_dismissed && online){int a=answer_index();if(a>=0){answer_draw(a);return;}}
 if(partner_compact(p,online)){partner_compact_draw(p,online);return;}
 building*post=gift_current_post();
 int list[128],count=partner_deal_list(list),inner,outer,bottom,rows=partner_detail_layout(count,&inner,&outer,&bottom);
 graphics_in_dialog_with_size(PARTNER_W,partner_dialog_h);
 outer_panel_draw(16,20,48,outer);
 graphics_fill_rect(40,38,12,28,mp_route_peer_color(p->slot));graphics_draw_rect(40,38,12,28,COLOR_BLACK);
 snprintf(label,sizeof(label),"%s · 교역",partner_label(gift_recipient));draw_utf8(label,62,40,530,FONT_LARGE_BLACK);
 if(post)snprintf(label,sizeof(label),"내 교역소: %d/32포대",mp_post_total(post));else snprintf(label,sizeof(label),"내 교역소: 없음");
 /* Facts, not buttons: plain text on the parchment. */
 draw_utf8(label,62,86,220,FONT_NORMAL_BLACK);
 draw_utf8(p->peer_post?"상대 교역소: 준비됨":"상대 교역소: 아직 없음",290,86,220,FONT_NORMAL_BLACK);
 if(!post)partner_button(&partner_build_button,"교역소 건설",!mp_client_request_pending());
 inner_panel_draw(32,124,partner_scrolls(count)?43:46,inner);
 if(partner_scrolls(count)){partner_sb.length=inner*16;scrollbar_draw(&partner_sb);}
 const char*stages[]={"수집","출발","이동","하역","정산"};
 for(int row=0;row<rows;row++){
  deal_row*d=&deal_rows[list[partner_page+row]];int y=128+row*58;
  image_draw(resource_get_data(d->resource?d->resource:RESOURCE_DENARII)->image.icon,44,y+8,COLOR_MASK_NONE,SCALE_NONE);
  int used;
  if(!d->resource)used=snprintf(label,sizeof(label),"%s %d Dn",d->outgoing?"돈 선물 보내기":"돈 선물 받기",d->money);
  else{
   used=snprintf(label,sizeof(label),"%s %d포대 %s",partner_resource_name(d->resource),d->quantity,d->money?(d->outgoing?"판매":"구매"):(d->outgoing?"선물 보내기":"선물 받기"));
   if(d->money && used>0 && used<(int)sizeof(label))used+=snprintf(label+used,sizeof(label)-used," · %d Dn",d->money);
   if(d->id_type && d->repeat && used>0 && used<(int)sizeof(label))snprintf(label+used,sizeof(label)-used," · 반복 %d회차",d->cycle);
  }
  draw_utf8(label,76,y+7,440,FONT_NORMAL_WHITE);
  if(d->phase>=0){
   for(int k=0;k<5;k++){
    int x=76+k*50;graphics_fill_rect(x,y+30,48,20,k<d->phase?0xffa8935f:k==d->phase?0xfff0d27a:0xff6a644f);
    gift_center(stages[k],x+2,y+33,44,k<=d->phase?FONT_NORMAL_BLACK:FONT_NORMAL_WHITE);
   }
   draw_utf8(d->status,334,y+33,190,FONT_NORMAL_WHITE);
  }else draw_utf8(d->status,76,y+33,440,FONT_NORMAL_GREEN);
  int actions[5];const char*texts[5];int n=partner_deal_actions(d,actions,texts);
  for(int j=0;j<n;j++){
   generic_button b={(short)(partner_right(count)-(n-j)*80),(short)(y+14),76,28,partner_deal_click,0,list[partner_page+row],actions[j]};
   partner_button(&b,texts[j],!mp_client_request_pending());
  }
  if(row+1<rows)graphics_draw_line(40,partner_right(count)-4,y+57,y+57,0xff6d6750);
 }
 if(!count)draw_utf8(!post?"전용 교역소를 지으면 물품을 거래할 수 있습니다.":p->peer_post?"진행 중인 거래가 없습니다. 새 제안을 보내 보세요.":"상대 도시가 교역소를 지으면 물품을 거래할 수 있습니다.",48,146,700,FONT_NORMAL_WHITE);
 int ready=post && p->peer_post,answering=0;
 if(ready && partner_ready_notice){partner_ready_notice=0;notice[0]=0;} /* the reason no longer applies */
 for(int i=0;i<count;i++)if(deal_rows[list[i]].kind==0)answering=1;
 /* While an offer waits for my answer, "new offer" would read like a reply: hide it. */
 if(!answering)partner_button(&partner_bar[0],"새 제안",ready);
 partner_button(&partner_bar[1],"돈 보내기",1);
 partner_button(&partner_bar[5],partner_direct?return_label():"뒤로",1);
 const char*request=mp_client_request_status();
 if(request)draw_utf8(request,36,bottom+7,728,FONT_NORMAL_BLACK);
 else if(notice[0])draw_utf8(notice,36,bottom+7,728,FONT_NORMAL_RED);
 graphics_reset_dialog();
}
static void partner_detail_handle(const mouse*m,const hotkeys*h){
 if(h->close_pressed){if(partner_direct)return_from_lobby();else partner_to_list();return;}
 partner_row*p=partner_selected();int online=partner_online(gift_recipient);
 if(!partner_answer_dismissed && online){int a=answer_index();if(a>=0){answer_handle(a,m,h);return;}}
 if(partner_compact(p,online)){
  const mouse*local=mouse_in_dialog_with_size(m,COMPACT_W,COMPACT_H);
  generic_button buttons[3];const char*texts[3];int n=partner_compact_buttons(p,online,buttons,texts);
  for(int i=0;i<n;i++)if(generic_buttons_handle_mouse(local,0,0,&buttons[i],1,&partner_row_focus))return;
  return;
 }
 int list[128],count=partner_deal_list(list),inner,outer,bottom,rows=partner_detail_layout(count,&inner,&outer,&bottom);
 const mouse*local=mouse_in_dialog_with_size(m,PARTNER_W,partner_dialog_h);
 if(partner_scrolls(count) && scrollbar_handle_mouse(&partner_sb,local,1))return;
 if(!gift_current_post() && generic_buttons_handle_mouse(local,0,0,&partner_build_button,1,&partner_row_focus))return;
 for(int row=0;row<rows;row++){
  int index=list[partner_page+row];deal_row*d=&deal_rows[index];int y=128+row*58;
  int actions[5];const char*texts[5];int n=partner_deal_actions(d,actions,texts);
  for(int j=0;j<n;j++){
   generic_button b={(short)(partner_right(count)-(n-j)*80),(short)(y+14),76,28,partner_deal_click,0,index,actions[j]};
   if(generic_buttons_handle_mouse(local,0,0,&b,1,&partner_row_focus))return;
  }
 }
 int answering=0;for(int i=0;i<count;i++)if(deal_rows[list[i]].kind==0)answering=1;
 for(int i=0;i<6;i++){
  if(i==2 || i==3 || i==4)continue; /* paging became the scrollbar; no partner list from one city's window */
  if(i==0 && answering)continue;
  if(generic_buttons_handle_mouse(local,0,0,&partner_bar[i],1,&partner_bar_focus))return;
 }
}
