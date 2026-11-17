#include "multiplayer/route_post.h"
#include "building/construction.h"
static void route_click(const generic_button *b){
 int state,revision;int peer=mp_route_peer(gift_recipient,&state,&revision);
 if(b->parameter1==0){if(state==1)gift_received=0;else return_from_lobby();return;}
 if(b->parameter1==5){return_from_lobby();return;}
 if(!peer || mp_client_request_pending())return;
 if(b->parameter1==4){
  if(state==1 && mp_route_select(peer)){
   trade_tab=history_tab=army_tab=0;window_city_show();building_construction_set_type(BUILDING_PLAYER_TRADE_POST,0);
  }return;
 }
 char command[160];
 if(b->parameter1==1 && state==0)snprintf(command,sizeof(command),"route_offer %s",gift_recipient);
 else if((b->parameter1==2 || b->parameter1==3) && state==2)snprintf(command,sizeof(command),"route_%s %s %d",b->parameter1==2?"accept":"reject",gift_recipient,revision);
 else return;
 mp_client_command("trade",command);
}
static generic_button route_buttons[]={
 {0,312,128,28,route_click,0,1},{0,312,128,28,route_click,0,2},
 {0,312,128,28,route_click,0,3},{0,312,128,28,route_click,0,4},
 {0,312,128,28,route_click,0,0},{0,312,128,28,route_click,0,5}
};
static int route_visible(int i,int state,int peer){return i==4 || (i==5 && state==1) || (i==0 && state==0 && peer) || ((i==1 || i==2) && state==2) || (i==3 && state==1 && !mp_route_post_for(peer));}
/* Visible buttons share one row, same width, centred in the 448x256 panel at (96,112). */
static void route_layout(int state,int peer){
 /* close first (left), then reject, then the ways forward (right) */
 int close_first[]={4,2,1,0,3,5},trading[]={5,3,4,0,1,2};int *order=state==1?trading:close_first,n=0;for(int k=0;k<6;k++)if(route_visible(order[k],state,peer))n++;
 int width=112,gap=16,x=96+(448-(n*width+(n-1)*gap))/2; /* 3 buttons: 40px sides */
 for(int k=0;k<6;k++)if(route_visible(order[k],state,peer)){route_buttons[order[k]].x=(short)x;route_buttons[order[k]].width=(short)width;x+=width+gap;}
}
static void route_draw(void){
 gift_read_peers();if(gift_picker){gift_picker_draw();return;}
 int state,revision;int peer=mp_route_peer(gift_recipient,&state,&revision),selected_peer=gift_selected_peer();
 graphics_in_dialog();outer_panel_draw(96,112,28,16);
 draw_utf8("도시 교역 계약",112,128,416,FONT_LARGE_BLACK);
 char label[512];snprintf(label,sizeof(label),"거래 상대: %s",selected_peer>=0?gift_peers[selected_peer].label:"선택해 주세요");
 draw_utf8(label,112,166,416,FONT_NORMAL_BLACK);
 draw_utf8(!peer?"상대 도시를 선택하세요.":state==1?"계약 체결됨":state==2?"도착한 교역 제안":state==3?"상대 도시의 수락 대기 중":"교역 계약 없음",112,202,416,FONT_NORMAL_BLACK);
 int post=mp_route_post_for(peer);
 if(state==1)draw_utf8(post?"전용 교역소 건설됨":"거래하려면 양쪽 도시에 교역소가 필요합니다.",112,224,416,FONT_SMALL_PLAIN);
 const char *labels[]={"계약 제안","수락","거절","전용 교역소 건설",state==1?"물품 거래":"닫기","닫기"};
 route_layout(state,peer);
 for(int i=0;i<6;i++)if(route_visible(i,state,peer)){
  generic_button *b=&route_buttons[i];mp_label_button(b->x,b->y,b->width,b->height,labels[i],mp_client_request_pending() && i!=4 && i!=5?2:0);
 }
 const char *status=mp_client_request_status();if(status)draw_utf8(status,112,288,416,FONT_SMALL_PLAIN);
 graphics_reset_dialog();
}
static void route_handle(const mouse *m,const hotkeys *h){
 if(gift_picker){gift_picker_handle(m,h);return;}if(h->close_pressed){return_from_lobby();return;}
 const mouse *local=mouse_in_dialog(m);
 if(!gift_peer_locked && local->x>=112 && local->x<528 && local->y>=160 && local->y<188){if(local->left.went_up)gift_peer_click(&gift_peer_open);return;}
 int state,revision,peer=mp_route_peer(gift_recipient,&state,&revision);route_layout(state,peer);
 for(int i=0;i<6;i++)if(route_visible(i,state,peer) && generic_buttons_handle_mouse(local,0,0,&route_buttons[i],1,&focus))return;
}
