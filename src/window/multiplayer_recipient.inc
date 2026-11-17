/* Recipient IDs are stable protocol values; display labels are never sent as IDs. */
static struct {char id[64],label[256];int online;} gift_peers[8];
static int gift_peer_count,gift_picker,gift_peer_hover=-1,gift_peer_locked;

static void gift_read_peers(void){
 gift_peer_count=0;const char *dir=getenv("AUGUSTUS_MP_BRIDGE");if(!dir)return;
 char path[2048],line[512];snprintf(path,sizeof(path),"%s/trade-recipients.txt",dir);FILE *f=fopen(path,"rb");if(!f)return;
 while(gift_peer_count<8 && fgets(line,sizeof(line),f)){
  char *flag=strchr(line,'\t');if(!flag)continue;*flag++=0;char *label=strchr(flag,'\t');if(!label)continue;*label++=0;label[strcspn(label,"\r\n")]=0;
  int n=gift_peer_count++;snprintf(gift_peers[n].id,sizeof(gift_peers[n].id),"%s",line);snprintf(gift_peers[n].label,sizeof(gift_peers[n].label),"%s",label);gift_peers[n].online=flag[0]=='1';
 }
 fclose(f);
 if(!gift_recipient[0] && gift_peer_count==1)snprintf(gift_recipient,sizeof(gift_recipient),"%s",gift_peers[0].id);
}
static int gift_selected_peer(void){for(int i=0;i<gift_peer_count;i++)if(!strcmp(gift_recipient,gift_peers[i].id))return i;return -1;}
static void gift_peer_click(const generic_button *b){
 if(gift_peer_locked)return;
 int i=b->parameter1;
 if(i==-2){gift_picker=1;gift_peer_hover=-1;return;}if(i==-1){gift_picker=0;return;}
 if(i>=0 && i<gift_peer_count && gift_peers[i].online){snprintf(gift_recipient,sizeof(gift_recipient),"%s",gift_peers[i].id);gift_picker=0;notice[0]=0;}
}
static generic_button gift_peer_open={48,76,528,28,gift_peer_click,0,-2};
static generic_button gift_peer_cancel={240,392,160,28,gift_peer_click,0,-1}; /* 28px above the panel's bottom edge */
static void gift_picker_draw(void){
 graphics_in_dialog();outer_panel_draw(112,48,26,25);inner_panel_draw(128,112,24,17);
 draw_utf8("받는 사람 선택",144,72,352,FONT_LARGE_BLACK);
 if(!gift_peer_count)draw_utf8("선택할 수 있는 플레이어가 없습니다.",144,132,352,FONT_NORMAL_WHITE);
 for(int i=0;i<gift_peer_count;i++){
  int y=120+i*30;char label[320];snprintf(label,sizeof(label),"%s%s",gift_peers[i].label,gift_peers[i].online?"":" (연결 없음)");
  if(!strcmp(gift_recipient,gift_peers[i].id))button_border_draw(136,y,368,28,1);
  if(!gift_peers[i].online){mp_button_text(label,148,y+7,344,2);continue;}
  draw_utf8(label,148,y+7,344,gift_peer_hover==i?FONT_NORMAL_RED:FONT_NORMAL_WHITE);
 }
 large_label_draw_custom_size(240,402,160,28);gift_center("취소",248,409,144,FONT_NORMAL_BLACK);graphics_reset_dialog();
}
static void gift_picker_handle(const mouse *m,const hotkeys *h){
 if(h->close_pressed){gift_picker=0;return;}
 const mouse *local=mouse_in_dialog(m);gift_peer_hover=-1;
 for(int i=0;i<gift_peer_count;i++){
  generic_button row={136,120+i*30,368,28,gift_peer_click,0,i};
  if(local->x>=136 && local->x<504 && local->y>=row.y && local->y<row.y+28)gift_peer_hover=i;
  if(generic_buttons_handle_mouse(local,0,0,&row,1,&focus))return;
 }
 generic_buttons_handle_mouse(local,0,0,&gift_peer_cancel,1,&focus);window_request_refresh();
}
