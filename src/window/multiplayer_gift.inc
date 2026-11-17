#include "multiplayer/route_post.h"
#include "multiplayer/post_logistics.h"
/* Player gift form follows the original gift dialog: choose a row, choose an
 * amount, inspect recipient/total, then send. Existing trade protocol is retained. */
#include "window/numeric_input.h"
#define GIFT_ROWS 10
#include "core/string.h"
static int gift_page,gift_received,gift_repeat,gift_input_resource;
static int gift_send_pending;
static char gift_send_error[768];
/* Set when the purchase form answers a received sale with other terms. */
static unsigned long long partner_counter_reject;
static int gift_send_poll(void){
 if(!gift_send_pending || mp_client_request_pending())return 0;
 int target=gift_send_pending;gift_send_pending=0;
 if(target==-1){
  if(mp_client_request_outcome()==1){trade_tab=history_tab=army_tab=0;gift_send_error[0]=0;window_go_back();return 1;}
  const char*error=mp_client_request_status();snprintf(gift_send_error,sizeof(gift_send_error),"%s",error?error:"요청 결과를 확인하지 못했습니다.");return 0;
 }
 if(gift_received)return 0;
 if(mp_client_request_outcome()==1){
  (void)target;
  /* The new terms are on their way: now decline the offer they replace. */
  if(partner_counter_reject){char cmd[64];snprintf(cmd,sizeof(cmd),"reject %llu",partner_counter_reject);partner_counter_reject=0;mp_client_command("trade",cmd);}
  /* A sent proposal starts the next form from zero, so nothing repeats by accident. */
  trade_quantity=0;trade_tab=history_tab=army_tab=0;gift_send_error[0]=0;window_go_back();return 1;
 }
 else {const char*error=mp_client_request_status();snprintf(gift_send_error,sizeof(gift_send_error),"%s",error?error:"요청 결과를 확인하지 못했습니다.");}
 return 0;
}
static int gift_partial,agreement_revision,agreement_quantity,agreement_partial,counter_quantity,counter_revision;
static unsigned long long counter_id;
static unsigned long long counter_input_id;
static int counter_input_revision;
static void gift_counter_quantity(int n){if(counter_input_id==counter_id && counter_input_revision==counter_revision)counter_quantity=n;}
static void gift_quantity_input(int n){if(trade_resource==gift_input_resource){if(trade_resource==8)trade_cash=n;else trade_quantity=n;}}
static void gift_price_input(int n){trade_price=n;}

static unsigned gift_post;
static char gift_recipient[64];
static building *gift_current_post(void){
 int state,revision,peer=mp_route_peer(gift_recipient,&state,&revision);
 unsigned id=mp_route_post_for(peer);gift_post=id;return id?building_get(id):0;
}
static const char *gift_post_readiness(const building *b){
 if(!b)return "교역소 없음";
 const char *dir=getenv("AUGUSTUS_MP_BRIDGE");if(!dir)return "출발 확인 중";
 char path[2048];snprintf(path,sizeof(path),"%s/post-readiness.txt",dir);FILE*f=fopen(path,"rb");
 int reason=3,workers,v;unsigned id,g;
 if(f){while(fscanf(f,"%u %u %d %d",&id,&g,&workers,&v)==4)if(id==b->id && g==b->created_sequence){reason=v;break;}fclose(f);}
 const char*labels[]={"출발 준비 완료","출발 경로 확인 중","인접 도로 없음","출발 경로 확인 중","도시 출입구 경로 불가","역병으로 운송 중지"};
 return reason>=0 && reason<6?labels[reason]:labels[3];
}
static void gift_next_post(void){
 unsigned count=building_count();for(unsigned offset=1;offset<=count;offset++){
  unsigned i=(gift_post+offset)%count;building *b=building_get(i);
  if(b->type==BUILDING_PLAYER_TRADE_POST && b->state==BUILDING_STATE_IN_USE){gift_post=i;return;}
 }
}
static void gift_center(const char *s,int x,int y,int width,font_t font){
 uint8_t text[2048];encoding_from_utf8(s,text,sizeof(text));int w=text_get_width(text,font);
 /* Keep the caller's font: a long label is shortened, never drawn smaller. */
 int offset=w<width?(width-w)/2:0;text_draw_ellipsized(text,x+offset,y,width-offset,font,0);
}
#include "multiplayer_recipient.inc"
/* Display order is separate from stable network/catalog IDs. */
static int gift_resource_at(int position){return position==0?8:position<=8?position-1:position;}
static int gift_items[MP_TRADE_RESOURCE_COUNT],gift_item_count;
static int gift_buy_known[MP_TRADE_RESOURCE_COUNT];
static int gift_remote[MP_TRADE_RESOURCE_COUNT],gift_known[MP_TRADE_RESOURCE_COUNT];
static int gift_available(int r){return r==8?city_finance_treasury():city_resource_get_total_amount(trade_resource_ids[r],0)+mp_post_city_stock(trade_resource_ids[r]);}
static void gift_inventory(void){
 memset(gift_remote,0,sizeof(gift_remote));memset(gift_known,0,sizeof(gift_known));
 const char*dir=getenv("AUGUSTUS_MP_BRIDGE");char path[2048],city[64];int res,qty;
 if(dir){snprintf(path,sizeof(path),"%s/trade-peer-stock.txt",dir);FILE*f=fopen(path,"rb");
  if(f){while(fscanf(f,"%63s %d %d",city,&res,&qty)==3){
   if(strcmp(city,"self"))continue;
   for(int i=0;i<MP_TRADE_RESOURCE_COUNT;i++)if(trade_resource_ids[i]==res){gift_known[i]=1;gift_remote[i]=qty>0?qty:0;}
  }fclose(f);}
 }
 memset(gift_buy_known,0,sizeof(gift_buy_known));
 if(dir){snprintf(path,sizeof(path),"%s/trade-buy-catalog.txt",dir);FILE*f=fopen(path,"rb");
  if(f){while(fscanf(f,"%63s %d",city,&res)==2)if(!strcmp(city,gift_recipient)){
   for(int i=0;i<MP_TRADE_RESOURCE_COUNT;i++)if(trade_resource_ids[i]==res)gift_buy_known[i]=1;
  }fclose(f);}
 }
 gift_item_count=0;
 for(int pos=0;pos<MP_TRADE_RESOURCE_COUNT;pos++){int r=gift_resource_at(pos);if(r==8)continue; /* Money has its own whisper dialog. */
  if(trade_mode==2?gift_buy_known[r]:(gift_available(r)>0 || gift_known[r] || r==trade_resource))gift_items[gift_item_count++]=r;
 }
 if(gift_page>gift_item_count-GIFT_ROWS)gift_page=gift_item_count>GIFT_ROWS?gift_item_count-GIFT_ROWS:0;
 int found=0;for(int i=0;i<gift_item_count;i++)if(gift_items[i]==trade_resource)found=1;
 /* Keep the selection inside the list: the first item, or 8 (= nothing picked: the form then asks to pick, no controls) */
 if(!found)trade_resource=gift_item_count?gift_items[0]:8;
}
static void agreement_view(char *buf,size_t size){
 trade_id=0;trade_actions=0;buf[0]=0;const char*dir=getenv("AUGUSTUS_MP_BRIDGE");if(!dir)return;
 char path[2048];snprintf(path,sizeof(path),"%s/agreement-view.txt",dir);FILE*f=fopen(path,"rb");
 if(f){char header[256],peer[64]={0};
  if(fgets(header,sizeof(header),f) && sscanf(header,"%llu %d %d %d %d %63s",&trade_id,&trade_actions,&agreement_revision,&agreement_quantity,&agreement_partial,peer)==6 && !strcmp(peer,gift_recipient)){
   fread(buf,1,size-1,f);
   if(counter_id!=trade_id || counter_revision!=agreement_revision){counter_id=trade_id;counter_revision=agreement_revision;counter_quantity=agreement_quantity>1?agreement_quantity-1:1;}
  }else{trade_id=0;trade_actions=0;snprintf(buf,size,"이 도시의 거래 제안이 없습니다.");}fclose(f);}
}
static void gift_click(const generic_button *b);
static generic_button gift_buttons[]={

 {48,112,248,24,gift_click,0,100},{48,136,248,24,gift_click,0,101},
 {48,160,248,24,gift_click,0,102},{48,184,248,24,gift_click,0,103},
 {48,208,248,24,gift_click,0,104},{48,232,248,24,gift_click,0,105},
 {48,256,248,24,gift_click,0,106},{48,280,248,24,gift_click,0,107},
 {48,304,248,24,gift_click,0,108},{48,328,248,24,gift_click,0,109},
 {48,312,120,24,gift_click,0,22},{184,312,120,24,gift_click,0,23},
 {320,112,80,28,gift_click,0,20},{408,112,80,28,gift_click,0,21},
 {320,226,58,22,gift_click,0,30},{386,226,58,22,gift_click,0,31},{452,226,58,22,gift_click,0,32},
 {320,196,32,26,gift_click,0,3},{544,196,32,26,gift_click,0,4},
 {320,276,32,26,gift_click,0,5},{544,276,32,26,gift_click,0,6},
 {320,360,256,28,gift_click,0,7},{518,226,58,22,gift_click,0,33},
 {48,408,120,28,gift_click,0,25},{184,408,120,28,gift_click,0,26},{320,408,124,28,gift_click,0,24},
 {80,280,220,28,gift_click,0,8},{328,280,220,28,gift_click,0,9},
 {48,356,248,28,gift_click,0,34},{48,356,248,28,gift_click,0,35},
 {496,112,80,28,gift_click,0,41},{320,148,256,24,gift_click,0,42},
 {452,408,124,28,gift_click,0,40},{328,316,220,28,gift_click,0,43},
 {80,316,220,28,gift_click,0,44},
 {320,306,58,22,gift_click,0,45},{386,306,58,22,gift_click,0,46},{452,306,58,22,gift_click,0,47},
 {360,196,176,26,gift_click,0,50},{360,276,176,26,gift_click,0,51},{518,306,58,22,gift_click,0,53},
 {448,148,128,24,gift_click,0,54},{80,248,220,26,gift_click,0,55},{328,248,220,26,gift_click,0,56}
};
/* Goods list: ten rows; more scroll under the original scrollbar (gift_page = first row shown). */
#include "graphics/scrollbar.h"
static void gift_list_scrolled(void);
static scrollbar_type gift_list_sb={.x=272,.y=160,.length=240,.scrollable_width=248,.on_scroll_callback=gift_list_scrolled,.step_size=1,.elements_in_view=GIFT_ROWS};
static void gift_list_scrolled(void){gift_page=(int)gift_list_sb.scroll_position;window_invalidate();}
static void gift_list_bar(void){
 static int ready;if(!ready){ready=1;scrollbar_init(&gift_list_sb,0,(unsigned)gift_item_count);}
 gift_list_sb.elements_in_view=GIFT_ROWS;scrollbar_update_total_elements(&gift_list_sb,(unsigned)gift_item_count);
 if((int)gift_list_sb.scroll_position!=gift_page)scrollbar_reset(&gift_list_sb,(unsigned)gift_page);
}
/* Keep management screens independent from the proposal layout. */
static void gift_layout(void){
 static generic_button original[sizeof(gift_buttons)/sizeof(gift_buttons[0])];
 static int saved;
 if(!saved){memcpy(original,gift_buttons,sizeof(gift_buttons));saved=1;}
 memcpy(gift_buttons,original,sizeof(gift_buttons));
 if(gift_received)return;
 for(int i=0;i<sizeof(gift_buttons)/sizeof(gift_buttons[0]);i++){
  generic_button *b=&gift_buttons[i];int id=b->parameter1;
  if(id>=100){b->y=160+(id-100)*24;}
  if(id==20 || id==21 || id==41){b->x=48+(id==20?0:id==21?1:2)*180;b->y=112;b->width=168;}
  if(id==22 || id==23)b->y=360;
  if(id==34)b->y=386;
  if(id==42 || id==54)b->y=334;
  if(id==7){b->y=386;b->height=32;}
  if(id==26){b->x=416;b->y=468;b->width=160;b->height=28;}   /* history on the right, back on the left */
  if(id==25){b->x=48;b->y=468;b->width=160;b->height=28;}
 }
}
static int gift_visible(int index){
 int id=gift_buttons[index].parameter1;
 if(id==22 || id==23 || id==24 || id==40)return 0; /* paging became the scrollbar; side trips left the form */
 if(!gift_received && trade_resource==8 && (id==3 || id==4 || id==5 || id==6 || id==7 || (id>=30 && id<=33) || id==42 || id==50 || (id>=45 && id<=54)))return 0;   /* nothing picked: no amount, price, options or send */
 if(id==54)return !gift_received && trade_mode==2;
 if(id==55)return 0; /* the count box moved into the trade-adjust dialog */
 if(id==56)return gift_received==2 && (trade_actions&16);

 if((id==45 || id==46 || id==47 || id==51 || id==53) && (trade_mode==1 || trade_resource==8))return 0;
 if(id==34)return 0; /* Received offers are answered on the partner screen. */
 if(id==40)return 1;
 if(id==43)return gift_received==2 && (trade_actions&4);
 if(id==44)return gift_received==2 && (trade_actions&1);
 if(id==35)return gift_received==2;
 if(id==42 && trade_mode==1)return 0;
 if(id==25 || id==26 || id==24)return 1;
 if(gift_received)return (id==8 && (trade_actions&1)) || (id==9 && (trade_actions&2));
 if(id==8 || id==9)return 0;
 if(id>=100)return gift_page+id-100<gift_item_count;
 if((id==5 || id==6) && (trade_mode==1 || trade_resource==8))return 0;
 return 1;
}
/* Defined with the partner table: 1 when the partner city has built its post for us. */
static int gift_peer_post_ready(void);
static int can_offer(void){
 int route_state,route_revision;if(!mp_route_peer(gift_recipient,&route_state,&route_revision) || route_state!=1)return 0;
 int recipient=gift_selected_peer();if(recipient<0 || !gift_peers[recipient].online)return 0;
 if(mp_client_request_pending() || mp_clock_trade_busy() || (trade_resource==8?trade_cash:trade_quantity)<=0)return 0;
 if(!gift_item_count)return 0;
 if(trade_mode!=2 && gift_available(trade_resource)<=0)return 0;
 /* Goods always move post to post, so every goods offer (gift, sale, purchase)
  * needs both cities' dedicated posts, exactly as the server requires. */
 if(!gift_current_post() || !gift_peer_post_ready())return 0;
 if(trade_resource==8)return trade_mode && city_finance_treasury()>=trade_cash;
 if(trade_mode==2)return gift_buy_known[trade_resource];
 return gift_available(trade_resource)>=trade_quantity;
}
#include "multiplayer_trade_board.inc"
#include "multiplayer_routes.inc"
#include "multiplayer_partner.inc"
static void gift_draw(void){
 if(gift_send_poll())return;
 if(gift_received==4){route_draw();return;}
 if(gift_received==3){board_draw();return;}
 if(gift_received==5){partner_list_draw();return;}
 if(gift_received==6){partner_detail_draw();return;}
 if(gift_received==7){cash_draw();return;}
 if(gift_received==9){counter_draw();return;}
 gift_read_peers();gift_inventory();if(gift_picker){gift_picker_draw();return;}
 char buf[2048]={0},label[512],peer[256]="상대 플레이어";trade_view(buf,sizeof(buf));if(gift_received==2)agreement_view(buf,sizeof(buf));
 const char *dir=getenv("AUGUSTUS_MP_BRIDGE");if(dir){char path[2048];snprintf(path,sizeof(path),"%s/trade-peer.txt",dir);FILE *f=fopen(path,"rb");if(f){fgets(peer,sizeof(peer),f);fclose(f);}}

 /* 608 wide at x=8: content at 48..576 keeps 40px from the stone border. */
 gift_layout();graphics_in_dialog();outer_panel_draw(8,32,38,gift_received?27:31);
 draw_utf8(gift_received==2?"플레이어 교역 · 계약 관리":gift_received?(trade_actions&16?"돈 선물":"플레이어 교역 · 운송 현황"):trade_mode==2?(partner_counter_reject?"다른 조건으로 구매 제안":"구매 제안"):trade_mode==1?"선물 보내기":"판매 제안",48,48,528,FONT_LARGE_BLACK);
 if(gift_received)draw_utf8(gift_received==1 && (trade_actions&16)?"수락 또는 거절하면 도시 화면으로 돌아갑니다.":"육상 상단 · 물품과 대금 방향을 확인하세요.",48,80,528,FONT_NORMAL_BLACK);
 else {
  /* Who this goes to: plain text with the partner's colour (nothing to press here). */
  int selected=gift_selected_peer();partner_row*pr=partner_selected();
  graphics_fill_rect(48,82,10,16,pr?mp_route_peer_color(pr->slot):0xffcbd1d7);graphics_draw_rect(48,82,10,16,COLOR_BLACK);
  snprintf(label,sizeof(label),"거래 상대: %s",selected>=0?gift_peers[selected].label:"선택해 주세요");draw_utf8(label,66,84,510,FONT_NORMAL_BLACK);
 }

 if(gift_received){
  inner_panel_draw(48,112,33,9);char *line=strtok(buf,"\n");int y=140;
  while(line && y<250){draw_utf8(line,64,y,496,FONT_NORMAL_WHITE);line=strtok(0,"\n");y+=26;}
  char hint[512]={0};if(dir){char path[2048];snprintf(path,sizeof(path),"%s/trade-hint.txt",dir);FILE *f=fopen(path,"rb");if(f){fread(hint,1,sizeof(hint)-1,f);fclose(f);}}
  if(gift_received==1)draw_utf8(hint,64,330,496,FONT_NORMAL_BLACK);
  if(gift_received==2){building*p=gift_current_post();snprintf(label,sizeof(label),"내 교역소: 무인 운영 · %s",gift_post_readiness(p));draw_utf8(label,48,388,528,FONT_SMALL_PLAIN);}
 }else{
  draw_utf8(trade_mode==2?"구매할 물품":"보낼 물품",48,146,248,FONT_NORMAL_BLACK);
  inner_panel_draw(48,160,16,15);
  int scroll=gift_item_count>GIFT_ROWS,roww=scroll?221:245;
  if(scroll){gift_list_bar();scrollbar_draw(&gift_list_sb);}
  for(int i=0;i<GIFT_ROWS;i++){
   int position=gift_page+i;if(position>=gift_item_count)break;int r=gift_items[position];
   int y=160+i*24;int resource=trade_resource_ids[r];
   if(r==trade_resource){graphics_fill_rect(51,y+2,roww,21,0xffead6ad);graphics_fill_rect(51,y+2,3,21,0xff804326);}
   image_draw(resource_get_data(resource?resource:RESOURCE_DENARII)->image.icon,56,y+3,COLOR_MASK_NONE,SCALE_NONE);
   if(trade_mode==2)snprintf(label,sizeof(label),"%s",trade_names[r]);
   else if(r!=8)snprintf(label,sizeof(label),"%s  %d포대",trade_names[r],gift_available(r));
   else snprintf(label,sizeof(label),r==8?"%s  %d 데나리":"%s  %d포대",trade_names[r],gift_available(r));
   if(trade_mode!=2 && !gift_available(r))snprintf(label,sizeof(label),"%s · 재고 없음",trade_names[r]);
   if(trade_mode!=2 && !gift_available(r)){uint8_t muted[256];encoding_from_utf8(label,muted,sizeof(muted));text_draw_ellipsized(muted,88,y+5,roww-44,FONT_NORMAL_WHITE,0xffb8b8b8);}
   else draw_utf8(label,88,y+5,roww-44,r==trade_resource?FONT_NORMAL_RED:FONT_NORMAL_WHITE);
  }
  if(!gift_item_count)draw_utf8("보유 물품 / 거래 이력이 없습니다.",56,176,232,FONT_SMALL_PLAIN);
  if(gift_current_post()){snprintf(label,sizeof(label),"교역소 %d/32 · 무인 운영",mp_post_total(gift_current_post()));gift_center(label,48,410,256,FONT_SMALL_PLAIN);}
  else gift_center(trade_mode==2?"보유·거래 이력 품목 · 수량 비공개":"내 재고 · 자동 갱신",48,410,256,FONT_SMALL_PLAIN);

  /* Money is not in this list (it has its own "돈 보내기"); with no goods to pick the selection used to stay on money
     and offered amounts and +100/+500 for it (user 2026-11-13: confusing). Now: what to do, and no controls. */
  if(trade_resource==8){
   draw_utf8(gift_item_count?"왼쪽 목록에서 물품을 고르세요.":trade_mode==2?"구매할 수 있는 물품이 없습니다.":"보낼 수 있는 물품이 없습니다.",320,176,256,FONT_NORMAL_BLACK);
   draw_utf8("돈은 제국지도의 '돈 보내기'로 보냅니다.",320,200,256,FONT_SMALL_PLAIN);
  }else{
  snprintf(label,sizeof(label),"%s %s",trade_mode==2?"구매 수량:":"보낼 수량:",trade_names[trade_resource]);draw_utf8(label,320,176,256,FONT_NORMAL_BLACK);
  if(trade_mode!=1 && trade_resource!=8){
   graphics_draw_line(320,576,252,252,0xff9b8060);
   draw_utf8("포대당 가격",320,256,256,FONT_NORMAL_BLACK);
  }
  if(trade_mode!=1)snprintf(label,sizeof(label),"%s: %d Dn / 회차",trade_mode==2?"지불액":"받을 금액",trade_quantity*trade_price);
  else if(trade_resource==8)snprintf(label,sizeof(label),"선물: %d 데나리",trade_cash);
  else snprintf(label,sizeof(label),"선물: %s %d포대",trade_names[trade_resource],trade_quantity);draw_utf8(label,320,366,256,FONT_NORMAL_BLACK);
  const char *hint=gift_selected_peer()<0?"받는 사람을 선택해 주세요.":!gift_peers[gift_selected_peer()].online?"선택한 플레이어의 연결을 기다리고 있습니다.":mp_clock_trade_busy()?"이전 거래를 처리하고 있습니다.":
   (trade_resource==8?trade_cash:trade_quantity)==0?(trade_resource==8?"보낼 금액을 더해 주세요.":trade_mode==2?"구매 수량을 정해 주세요.":"보낼 수량을 정해 주세요."):
   !can_offer()?(!gift_current_post()?"전용 교역소를 먼저 지어 주세요.":!gift_peer_post_ready()?"상대 도시가 교역소를 지으면 보낼 수 있습니다.":trade_mode==2?"도시 계약과 교역소를 확인하세요.":trade_resource==8?"자금이 부족합니다.":"내 재고와 교역소를 확인하세요."):
   trade_mode==1?"선물은 일회 전달입니다.":trade_mode==2?"거래 이력 물품은 재고 없이 요청 가능":"육상 교역 · 상대 동의 후 시작 · 출발 시 재검사";
  /* The reason is shown by the submit control without competing with navigation. */
  draw_utf8(!can_offer()?hint:trade_mode==2?(gift_partial?"상대가 수량을 줄여 보내도 그대로 체결됩니다.":"수락하면 상대 상단이 실어 옵니다."):gift_post_readiness(gift_current_post()),320,422,256,FONT_SMALL_PLAIN);
  }
 }
 for(int i=GIFT_ROWS;i<sizeof(gift_buttons)/sizeof(gift_buttons[0]);i++){ /* the first GIFT_ROWS entries are the list rows */
  if(!gift_visible(i))continue;generic_button *b=&gift_buttons[i];int id=b->parameter1;const char *text="";
  if(id==34)text="받은 제안 / 계약";
  else if(id==44){building *post=gift_current_post();if(post)snprintf(label,sizeof(label),"교역소 #%u / 상단 1개",post->id);else snprintf(label,sizeof(label),"교역소 건설 필요");text=label;}
  else if(id==35)text="다음 계약";
  else if(id==40)text=gift_current_post()?"내 교역소":"교역소 없음";
  else if(id==41)text="구매";
  else if(id>=45 && id<=47){snprintf(label,sizeof(label),"+%d",id==45?5:id==46?10:100);text=label;}
  else if(id==50){snprintf(label,sizeof(label),"%d %s",trade_resource==8?trade_cash:trade_quantity,trade_resource==8?"Dn":"포대");text=label;}
  else if(id==51){snprintf(label,sizeof(label),"%d Dn",trade_price);text=label;}
  else if(id==42){b->width=trade_mode==2?128:256;text=trade_mode==2?(gift_repeat?"[x] 반복 거래":"[ ] 반복 거래"):(gift_repeat?"[x] 반복 거래":"[ ] 반복 거래");}
  else if(id==54)text=gift_partial?"[x] 일부 허용":"[ ] 일부 허용";
  else if(id==55){snprintf(label,sizeof(label),"수정 수량: %d 포대",counter_quantity);text=label;}
  else if(id==56)text="거래 조정";
  else if(id==43)text="다시 동의 요청";
  else if(id==22)text="이전 물품";else if(id==23)text="다음 물품";
  else if(id==20)text="선물";else if(id==21)text="판매";
  else if(id>=30 && id<=32){int v=trade_resource==8?(id==30?100:id==31?500:1000):(id==30?1:id==31?5:10);snprintf(label,sizeof(label),"+%d",v);text=label;}
  else if(id==33 || id==53)text="초기화";
  else if(id==3 || id==5)text="-";else if(id==4 || id==6)text="+";
  else if(id==7)text=gift_send_pending?"응답 대기 중":trade_mode==2?"구매 제안 보내기":trade_mode==1?"선물 보내기":gift_repeat?"지속 판매 제안":"판매 제안 보내기";
  else if(id==25)text=gift_recipient[0] && partner_selected()?"뒤로":return_label();else if(id==26)text="거래 이력";else if(id==24)text="무역 상황판";
  else if(id==8)text="제안 수락";else if(id==9)text=gift_received==2?"거절 / 중단":(trade_actions&4)?"반환 재시도":(trade_actions&8)?"보내기 취소":"거절";
  int helper=(id>=30 && id<=33) || (id>=45 && id<=47) || id==53 || (id>=3 && id<=6);
  if(id==42 || id==54){
   /* The original options checkbox: a 20 px bordered box with an x, then the label. */
   int on=id==42?gift_repeat:gift_partial,cy=b->y+(b->height-20)/2;
   button_border_draw(b->x,cy,20,20,0);if(on)text_draw(string_from_ascii("x"),b->x+6,cy+3,FONT_NORMAL_BLACK,0);
   draw_utf8(id==42?"반복 거래":"부족해도 받기",b->x+28,b->y+(b->height-14)/2,b->width-28,FONT_NORMAL_BLACK);continue;
  }
  else if(helper)button_border_draw(b->x,b->y,b->width,b->height,0);
  else large_label_draw_custom_size(b->x,b->y,b->width,b->height);
  if(id==50 || id==51){graphics_fill_rect(b->x+3,b->y+3,b->width-6,b->height-6,0xfff3e4c5);button_border_draw(b->x,b->y,b->width,b->height,1);}
  if(id==7 && can_offer()){graphics_fill_rect(b->x+3,b->y+3,b->width-6,b->height-6,0xff78432c);}
  if((id==20 && trade_mode==1) || (id==21 && trade_mode==0) || (id==41 && trade_mode==2)){
   button_border_draw(b->x,b->y,b->width,b->height,1);
   graphics_fill_rect(b->x+3,b->y+b->height-5,b->width-6,3,0xff542b15);
  }
  int disabled=((id==7 || id==8 || id==9 || id==43) && mp_client_request_pending()) || (id==8 && !(trade_actions&1)) || (id==9 && !(trade_actions&2)) || (id==7 && !can_offer()) || ((id==22 || id==23) && gift_item_count<=8);
  /* Every button in this form uses one glyph size; only colour marks state. */
  if(id==7 && !disabled){gift_center(text,b->x+8,b->y+(b->height-14)/2,b->width-16,FONT_NORMAL_WHITE);continue;}
  int chosen=(id==20 && trade_mode==1) || (id==21 && trade_mode==0) || (id==41 && trade_mode==2);
  mp_button_text(text,b->x+4,b->y+(b->height-14)/2,b->width-8,disabled?2:chosen?1:0);
 }
 if(!gift_received)graphics_draw_line(48,576,466,466,0xff9b8060);
 const char *request=mp_client_request_status();
 if(!gift_received && (gift_send_pending || gift_send_error[0])){
  const char*message=gift_send_pending?(request?request:"요청 전송 중입니다."):gift_send_error;uint8_t encoded[2048];encoding_from_utf8(message,encoded,sizeof(encoded));
  text_draw_multiline(encoded,48,438,528,0,gift_send_pending?FONT_NORMAL_BLACK:FONT_NORMAL_RED,0);
 }
 else if(gift_send_error[0])draw_utf8(gift_send_error,48,388,528,FONT_NORMAL_RED);
 else if(request)draw_utf8(request,48,gift_received?388:438,528,FONT_NORMAL_BLACK);
 else if(notice[0])draw_utf8(notice,48,gift_received?388:438,528,FONT_NORMAL_RED);
 graphics_reset_dialog();
}
static void gift_click(const generic_button *b){
 int id=b->parameter1;
 if(id==25 || id==26 || id==24 || id==34 || id==40)gift_send_pending=0;
 else if(mp_client_request_pending())return;
 else gift_send_error[0]=0;

 if(id==34){char cmd[128];snprintf(cmd,sizeof(cmd),"contract_open %s",gift_recipient);if(mp_client_command("trade",cmd))gift_received=2;return;}
 if(id==44){gift_next_post();return;}
 if(id==40){gift_received=4;return;}
 if(id==42){gift_repeat=!gift_repeat;return;}
 if(id==54){gift_partial=!gift_partial;return;}
 if(id==35){if(gift_received==2)mp_client_command("trade","contract_next");return;}
 if(id==25){partner_counter_reject=0;if(gift_recipient[0] && partner_selected()){gift_received=6;gift_send_pending=0;return;}return_from_lobby();return;}
 if(id==26){window_multiplayer_history_show();history_from_form=1;return;}
 if(id==24){gift_received=3;board_read_at=0;return;}
 if(mp_client_request_pending() || (mp_clock_trade_busy() && id!=9))return;
 if(id==55){counter_input_id=counter_id;counter_input_revision=counter_revision;window_numeric_input_bound_show(0,0,b,2,1,agreement_quantity-1,gift_counter_quantity);return;}
 if(id==56){
  /* Same dialog as the deal table: quantity and price, the other side confirms. */
  for(int i=0;i<deal_count;i++)if(deal_rows[i].id_type && deal_rows[i].id==trade_id){counter_open(i);return;}
  strcpy(notice,"제안 정보를 불러오는 중입니다. 잠시 후 다시 눌러 주세요.");return;
 }
 if(id>=45 && id<=47){trade_price+=id==45?5:id==46?10:100;if(trade_price>31250)trade_price=31250;return;}
 if(id==50){gift_input_resource=trade_resource;window_numeric_input_bound_show(0,0,b,trade_resource==8?7:2,0,trade_resource==8?1000000:32,gift_quantity_input);return;}
 if(id==51){window_numeric_input_bound_show(0,0,b,5,1,31250,gift_price_input);return;}
 if(id>=100){int position=gift_page+id-100;if(position<gift_item_count){int r=gift_items[position];trade_resource=r;if(r==8)trade_mode=1;}return;}
 if(id==22 || id==23){int pages=(gift_item_count+7)/8;if(pages<=1){strcpy(notice,"물품이 한 쪽에 모두 보입니다.");return;}gift_page=(gift_page+(id==22?-1:1)+pages)%pages;notice[0]=0;return;}
 if(id==20 || id==21 || id==41){trade_mode=id==20?1:id==21?0:2;gift_page=0;gift_inventory();return;}
 if(id==33){if(trade_resource==8)trade_cash=0;else trade_quantity=0;return;}
 if(id==53){trade_price=1;return;} /* reset = the minimum price */
 if(id>=30 && id<=32){int *v=trade_resource==8?&trade_cash:&trade_quantity;int add=trade_resource==8?(id==30?100:id==31?500:1000):(id==30?1:id==31?5:10);int max=trade_resource==8?1000000:32;*v+=add;if(*v>max)*v=max;return;}
 if(id==3 || id==4){int *v=trade_resource==8?&trade_cash:&trade_quantity;*v+=(id==3?-1:1)*(trade_resource==8?100:1);int max=trade_resource==8?1000000:32;if(*v<0)*v=0;if(*v>max)*v=max;return;}
 if(id==5 || id==6){trade_price+=id==5?-1:1;if(trade_price<1)trade_price=1;if(trade_price>31250)trade_price=31250;return;}
 if((id==7 && !can_offer()) || (id==8 && !(trade_actions&1)) || (id==9 && !(trade_actions&2)))return;
 char cmd[256];
 if(id==7){building *post=gift_current_post();
  if(trade_mode==2 || (trade_mode==0 && gift_repeat))snprintf(cmd,sizeof(cmd),"contract_offer %d %d %d %d %s %u %u %d %d",trade_mode,trade_resource,trade_quantity,trade_price,gift_recipient,post?post->id:0,post?post->created_sequence:0,gift_repeat,trade_mode==2?gift_partial:0);
  else snprintf(cmd,sizeof(cmd),"offer %d %d %d %d %s %u %u",trade_mode,trade_resource,trade_resource==8?trade_cash:trade_quantity,trade_price,gift_recipient,post?post->id:0,post?post->created_sequence:0);
 }
 else if(gift_received==2){building *post=gift_current_post();snprintf(cmd,sizeof(cmd),"%s %llu %u %u %d",id==8?"contract_accept":id==43?"contract_resume":"contract_stop",trade_id,post?post->id:0,post?post->created_sequence:0,agreement_revision);}
 else snprintf(cmd,sizeof(cmd),"%s %llu",id==8?"accept":"reject",trade_id);
 if(mp_client_command("trade",cmd)){notice[0]=0;int target=(gift_received==2 || (id==7 && (trade_mode==2 || (trade_mode==0 && gift_repeat))))?2:1;if(id==7){gift_send_pending=(trade_mode==1 && trade_resource==8)?-1:target;gift_send_error[0]=0;}else if(gift_received==1 && (trade_actions&16) && (id==8 || id==9)){gift_send_pending=-1;gift_send_error[0]=0;}else gift_received=target;}else strcpy(notice,"이전 요청을 처리 중입니다.");
}
static void gift_handle(const mouse *m,const hotkeys *h){
 if(gift_received==4){route_handle(m,h);return;}
 if(gift_received==3){board_handle(m,h);return;}
 if(gift_received==5){partner_list_handle(m,h);return;}
 if(gift_received==6){partner_detail_handle(m,h);return;}
 if(gift_received==7){cash_handle(m,h);return;}
 if(gift_received==9){counter_handle(m,h);return;}
 if(gift_picker){gift_picker_handle(m,h);return;}
 if(h->close_pressed){gift_send_pending=0;partner_counter_reject=0;if(gift_recipient[0] && partner_selected()){gift_received=6;return;}return_from_lobby();return;}
 const mouse *local=mouse_in_dialog(m);
 if(!gift_received && gift_item_count>GIFT_ROWS){gift_list_bar();if(scrollbar_handle_mouse(&gift_list_sb,local,1))return;}
 for(int i=0;i<sizeof(gift_buttons)/sizeof(gift_buttons[0]);i++)if(gift_visible(i) && generic_buttons_handle_mouse(local,0,0,&gift_buttons[i],1,&focus))return;
}
