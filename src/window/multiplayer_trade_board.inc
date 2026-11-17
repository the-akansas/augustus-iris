/* Display only: never reserves cargo or advances a trader. */
#include "figure/figure.h"
#include "figure/action.h"
#include "figure/trader.h"
#include "empire/city.h"
#include <time.h>

typedef struct {int kind,phase,sea;char origin[512],destination[512];char line[4][512];} board_row;
static board_row board_rows[256],board_player[128];
static int board_count,board_player_count,board_tab,board_page,board_stale,board_more;
static unsigned board_read_at;

static board_row *board_add(int kind){
 if(board_count>=256){board_more=1;return 0;}
 board_row*r=&board_rows[board_count++];memset(r,0,sizeof(*r));r->kind=kind;return r;
}
static void board_read_players(void){
 static board_row incoming[128];static char previous_root[2048];
 const char*dir=getenv("AUGUSTUS_MP_BRIDGE");board_stale=1;if(!dir){board_player_count=0;return;}
 if(strcmp(previous_root,dir)){snprintf(previous_root,sizeof(previous_root),"%s",dir);board_player_count=0;}
 char path[2048],header[128];snprintf(path,sizeof(path),"%s/trade-board.txt",dir);
 FILE*f=fopen(path,"rb");if(!f)return;
 int version=0,count=0,ok=1;long long stamp=0;
 if(!fgets(header,sizeof(header),f) || sscanf(header,"%d %lld %d",&version,&stamp,&count)!=3 || (version!=1 && version!=2) || count<0 || count>128){fclose(f);return;}
 memset(incoming,0,sizeof(incoming));
 for(int i=0;i<count && ok;i++){
  snprintf(incoming[i].origin,512,"판매 도시");snprintf(incoming[i].destination,512,"구매 도시");
  for(int j=0;j<(version==2?7:4);j++){
   char line[512];
   if(!fgets(line,sizeof(line),f) || !strchr(line,'\n')){ok=0;break;}
   line[strcspn(line,"\r\n")]=0;
   if(version==2 && j==0){
    char extra;int phase,sea;
    if(sscanf(line,"%d %d %c",&phase,&sea,&extra)!=2 || phase<0 || phase>4 || sea<0 || sea>1){ok=0;break;}
    incoming[i].phase=phase;incoming[i].sea=sea;
   }else if(version==2 && j<3)snprintf(j==1?incoming[i].origin:incoming[i].destination,512,"%s",line);
   else snprintf(incoming[i].line[j-(version==2?3:0)],512,"%s",line);
  }
 }
 if(fgetc(f)!=EOF)ok=0;fclose(f);if(!ok)return;
 memcpy(board_player,incoming,sizeof(incoming));board_player_count=count;
 long long age=(long long)time(0)-stamp;board_stale=age<0 || age>5;
}
static const char *board_npc_state(int state){
 switch(state){
 case FIGURE_ACTION_100_TRADE_CARAVAN_CREATED:case FIGURE_ACTION_110_TRADE_SHIP_CREATED:return "도시 진입 준비";
 case FIGURE_ACTION_101_TRADE_CARAVAN_ARRIVING:return "창고로 이동 중";
 case FIGURE_ACTION_102_TRADE_CARAVAN_TRADING:return "창고에서 거래 중";
 case FIGURE_ACTION_103_TRADE_CARAVAN_LEAVING:case FIGURE_ACTION_115_TRADE_SHIP_LEAVING:return "거래 종료 · 도시를 떠나는 중";
 case FIGURE_ACTION_111_TRADE_SHIP_GOING_TO_DOCK:return "선창으로 이동 중";
 case FIGURE_ACTION_112_TRADE_SHIP_MOORED:return "선창 정박 · 하역/선적 중";
 case FIGURE_ACTION_113_TRADE_SHIP_GOING_TO_DOCK_QUEUE:case FIGURE_ACTION_114_TRADE_SHIP_ANCHORED:return "선창 차례 대기";
 default:return "이동/경로 확인 중";
 }
}
static void board_npc_map(board_row*r,const figure*f,const char*city){
 snprintf(r->origin,512,"%s",city);snprintf(r->destination,512,"내 도시");r->sea=f->type==FIGURE_TRADE_SHIP;
 switch(f->action_state){
 case FIGURE_ACTION_101_TRADE_CARAVAN_ARRIVING:case FIGURE_ACTION_111_TRADE_SHIP_GOING_TO_DOCK:r->phase=2;break;
 case FIGURE_ACTION_102_TRADE_CARAVAN_TRADING:case FIGURE_ACTION_112_TRADE_SHIP_MOORED:r->phase=3;break;
 case FIGURE_ACTION_103_TRADE_CARAVAN_LEAVING:case FIGURE_ACTION_115_TRADE_SHIP_LEAVING:r->phase=4;break;
 default:r->phase=0;
 }
}
static void board_npc(void){
 for(unsigned i=1;i<figure_count();i++){
  const figure*f=figure_get(i);
  if(figure_is_dead(f) || f->mp_contract_id || (f->type!=FIGURE_TRADE_CARAVAN && f->type!=FIGURE_TRADE_SHIP))continue;
  empire_city*c=empire_city_get(f->empire_city_id);if(!c || !c->in_use)continue;
  char city[160];encoding_to_utf8(empire_city_get_name(c),city,sizeof(city),0);
  int traded=0;
  for(int res=RESOURCE_MIN;res<RESOURCE_MAX;res++){
   int bought=trader_bought_resources(f->trader_id,res),sold=trader_sold_resources(f->trader_id,res);
   if(!bought && !sold)continue;traded=1;board_row*r=board_add(1);if(!r)return;board_npc_map(r,f,city);
   char resource[100];encoding_to_utf8(resource_get_data(res)->text,resource,sizeof(resource),0);
   snprintf(r->line[0],512,"[중립 · %s] %s · 상인 #%u",f->type==FIGURE_TRADE_SHIP?"해상":"육상",city,i);
   snprintf(r->line[1],512,"%s · 이번 방문 수입 %d / 수출 %d포대",resource,sold,bought);
   snprintf(r->line[2],512,"%s · 위치 (%d, %d)",board_npc_state(f->action_state),f->x,f->y);
   snprintf(r->line[3],512,"창고/선창 #%u · 다음 품목은 원본 AI가 결정",f->destination_building_id);
  }
  if(!traded){board_row*r=board_add(1);if(!r)return;board_npc_map(r,f,city);
   snprintf(r->line[0],512,"[중립 · %s] %s · 상인 #%u",f->type==FIGURE_TRADE_SHIP?"해상":"육상",city,i);
   snprintf(r->line[1],512,"%s · 위치 (%d, %d)",board_npc_state(f->action_state),f->x,f->y);
   snprintf(r->line[2],512,"이번 방문 거래 전 · 창고/선창 #%u",f->destination_building_id);
   snprintf(r->line[3],512,"선적 품목/수량은 거래 시 확정됩니다.");
  }
 }
}
static void board_refresh(void){
 unsigned now=time_get_millis();if(board_read_at && now-board_read_at<500)return;board_read_at=now;
 board_read_players();board_count=board_more=0;
 for(int i=0;i<board_player_count;i++){board_row*r=board_add(0);if(r)*r=board_player[i];}
 board_npc();
}
static int board_matches(int i){return !board_tab || board_rows[i].kind==board_tab-1;}
static void board_click(const generic_button*b){
 int id=b->parameter1;notice[0]=0;
 if(id<3){board_tab=id;board_page=0;}
 else if(id==3){if(board_page>0)board_page--;else strcpy(notice,"첫 항목입니다.");}
 else if(id==4){int count=0;for(int i=0;i<board_count;i++)count+=board_matches(i);if(board_page+1<count)board_page++;else strcpy(notice,"마지막 항목입니다.");}
 else if(id==5)gift_received=1;
 else if(id==6)gift_received=2;
 else gift_received=0;
}
static generic_button board_buttons[]={
 {48,96,120,24,board_click,0,0},{176,96,120,24,board_click,0,1},{304,96,120,24,board_click,0,2},
 {48,424,96,28,board_click,0,3},{156,424,96,28,board_click,0,4},
 {264,424,96,28,board_click,0,5},{372,424,96,28,board_click,0,6},{480,424,96,28,board_click,0,7}
};
static void board_draw(void){
 /* 608x464 at (8,16): 40px sides, buttons 28px above the bottom edge. */
 board_refresh();graphics_in_dialog();outer_panel_draw(8,16,38,29);
 draw_utf8("무역 상황판",48,44,528,FONT_LARGE_BLACK);
 draw_utf8(board_stale?"플레이어 정보 지연 · 중립 상인은 현재 도시 기준":"도시 간 교역 노선도 · 현재 단계와 다음 주문",48,78,528,board_stale?FONT_NORMAL_RED:FONT_NORMAL_BLACK);
 int count=0;for(int i=0;i<board_count;i++)count+=board_matches(i);
 if(board_page>=count)board_page=count?count-1:0;
 int at=0;
 for(int i=0;i<board_count;i++)if(board_matches(i)){
  if(at++<board_page)continue;
  board_row*r=&board_rows[i];color_t route=r->sea?0xff4cbbdb:0xffdcb66c;
  inner_panel_draw(48,128,33,16);
  draw_utf8(r->line[0],60,138,504,FONT_NORMAL_WHITE);
  draw_utf8(r->line[1],60,163,504,FONT_NORMAL_WHITE);
  /* Schematic: positions describe workflow, never elapsed distance or ETA. */
  graphics_fill_rect(96,230,384,4,route);
  for(int k=0;k<10;k++){
   int x=r->phase==4?302-k:302+k;
   graphics_fill_rect(x,222+k,1,20-k*2,route);
  }
  large_label_draw_custom_size(64,195,152,27);large_label_draw_custom_size(408,195,152,27);
  gift_center(r->origin,68,202,144,FONT_NORMAL_BLACK);gift_center(r->destination,412,202,144,FONT_NORMAL_BLACK);
  gift_center(r->kind?"중립도시": "판매 도시",64,242,152,FONT_NORMAL_WHITE);
  gift_center(r->kind?"창고 / 선창":"구매 도시",408,242,152,FONT_NORMAL_WHITE);
  gift_center(r->sea?"해상 항로":"육상 교역로",220,202,184,FONT_NORMAL_WHITE);
  draw_utf8(r->line[2],60,275,504,FONT_NORMAL_WHITE);
  const char*stages[]={"대기","수거","운송","하역/거래","귀환"};
  for(int k=0;k<5;k++){
   int x=60+k*100;graphics_fill_rect(x,305,94,26,r->phase==k?route:0xff4b4b42);
   gift_center(stages[k],x+2,312,90,r->phase==k?FONT_NORMAL_BLACK:FONT_NORMAL_WHITE);
  }
  draw_utf8(r->line[3],60,350,504,FONT_NORMAL_WHITE);
  draw_utf8(r->kind?"중립 수량은 이번 방문 누적 · 다음 품목은 거래 시 결정":"다음 주문은 재고와 계약 상태에 따라 변경됩니다.",60,377,504,FONT_SMALL_PLAIN);
  break;
 }
 if(!count)draw_utf8(board_tab==2?"현재 도시에 방문 중인 중립 상인이 없습니다.":"표시할 운송 또는 대기 주문이 없습니다.",60,160,504,FONT_NORMAL_BLACK);
 char label[96];snprintf(label,sizeof(label),"%d/%d · %d건%s",board_page+1,count?count:1,count,board_more?"+":"");draw_utf8(label,440,101,136,FONT_NORMAL_BLACK);
 const char*labels[]={"전체","플레이어","중립도시","이전","다음","제안 / 운송","계약 관리","제안 작성"};
 for(int i=0;i<8;i++){generic_button*b=&board_buttons[i];
  int dim=(i==3 && board_page<=0) || (i==4 && board_page+1>=count);
  mp_label_button(b->x,b->y,b->width,b->height,labels[i],i<3 && board_tab==i?1:dim?2:0);}
 if(notice[0])draw_utf8(notice,48,400,528,FONT_NORMAL_RED);
 else draw_utf8("개략 노선도 · 실제 거리나 도착 시간을 뜻하지 않습니다.",48,400,528,FONT_SMALL_PLAIN);
 graphics_reset_dialog();
}
static void board_handle(const mouse*m,const hotkeys*h){
 if(h->close_pressed){gift_received=0;notice[0]=0;return;}
 generic_buttons_handle_mouse(mouse_in_dialog(m),0,0,board_buttons,8,&focus);
}
