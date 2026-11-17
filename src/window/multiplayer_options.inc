#define ROOM_OPTION_ROW_Y 120
#define ROOM_OPTION_ROW_H 26
static int room_options_open,room_options_tab,room_options_offset,room_options_revision=-1,room_options_locked,room_options_initialized;
static int room_options_edit_revision,room_options_draft[CONFIG_ROOM_OPTION_COUNT];
static char room_options_session[65],room_options_message[256];
static int room_options_pending,room_options_close_armed;
static unsigned room_options_polled;
static int room_options_from_city;
#include "multiplayer_save_options.inc"
static int room_options_send(int revision,const int *v){
 char body[512];int n=snprintf(body,sizeof(body),"%d",revision);
 for(int i=0;i<CONFIG_ROOM_OPTION_COUNT;i++)n+=snprintf(body+n,sizeof(body)-n," %d",v[i]);
 return mp_client_command("room-options-set",body);
}
static void room_options_poll(void){
 unsigned now=time_get_millis();if(now-room_options_polled<100)return;room_options_polled=now;
 char entry[16],event[32];room_read("network-entry.txt",entry,sizeof(entry));room_read("room-exit.txt",event,sizeof(event));
 if(entry[0]=='1' || event[0]){config_room_clear();room_options_revision=-1;room_options_session[0]=0;room_options_open=0;return;}
 FILE *f=room_list_open("room-options.txt");if(!f)return;
 char header[64],session[65],extra;int revision,locked,initialized,v[CONFIG_ROOM_OPTION_COUNT],ok=0;
 if(!room_list_line(f,header,sizeof(header)) || strcmp(header,"AUGROOM2") || !room_list_line(f,session,sizeof(session)))goto done;
 if(strlen(session)!=32 || strspn(session,"0123456789abcdef")!=32)goto done;
 if(fscanf(f,"%d %d %d",&revision,&locked,&initialized)!=3 || revision<0 || (locked!=0 && locked!=1) || (initialized!=0 && initialized!=1))goto done;
 for(int i=0;i<CONFIG_ROOM_OPTION_COUNT;i++)if(fscanf(f,"%d",&v[i])!=1 || v[i]<0 || v[i]>config_room_max(i))goto done;
 if(fscanf(f," %c",&extra)==1)goto done;ok=1;
done:fclose(f);if(!ok)return;
 if(strcmp(room_options_session,session)){config_room_clear();room_options_revision=-1;snprintf(room_options_session,sizeof(room_options_session),"%s",session);}
 room_options_locked=locked;room_options_initialized=initialized;
 if(!initialized){
  room_options_revision=revision;
  /* A new room starts from the room defaults, not from whatever the host's own game settings happen to be. */
  if(local_role()==1){int seed[CONFIG_ROOM_OPTION_COUNT];for(int i=0;i<CONFIG_ROOM_OPTION_COUNT;i++)seed[i]=config_room_default(i);room_options_send(revision,seed);}
  return;
 }
 if(revision<room_options_revision)return;
 if(!config_room_apply(v))return;room_options_revision=revision;
 if(room_options_open && room_options_pending){room_options_pending=0;room_options_edit_revision=revision;snprintf(room_options_message,sizeof(room_options_message),"적용했습니다. 계속 고칠 수 있습니다.");}
 const char *dir=getenv("AUGUSTUS_MP_BRIDGE");if(!dir)return;char path[2048],tmp[2048];
 snprintf(path,sizeof(path),"%s/room-options-ack.txt",dir);snprintf(tmp,sizeof(tmp),"%s/room-options-ack.tmp",dir);
 char ack[128],expected[128];room_read("room-options-ack.txt",ack,sizeof(ack));snprintf(expected,sizeof(expected),"%s %d",session,revision);if(!strcmp(ack,expected))return;
 f=fopen(tmp,"wb");if(f){fputs(expected,f);if(!fclose(f)){remove(path);rename(tmp,path);}}
}
static void room_options_begin(void){
 room_options_from_city=0;room_options_open=1;room_options_tab=room_options_offset=0;room_options_edit_revision=room_options_revision;room_options_message[0]=0;room_options_pending=room_options_close_armed=0;
 for(int i=0;i<CONFIG_ROOM_OPTION_COUNT;i++)room_options_draft[i]=config_room_value(i);
 input_box_stop(&input);
}
#include "graphics/scrollbar.h"
#define ROOM_OPTION_ROWS 14
static void room_options_scrolled(void);
static scrollbar_type room_options_sb={.x=728,.y=ROOM_OPTION_ROW_Y,.length=ROOM_OPTION_ROWS*ROOM_OPTION_ROW_H,.scrollable_width=704,.on_scroll_callback=room_options_scrolled,.step_size=3,.elements_in_view=ROOM_OPTION_ROWS};
static void room_options_scrolled(void){room_options_offset=(int)room_options_sb.scroll_position;window_invalidate();}
/* Display order only (the stored option order never changes): the difficulty tab leads with
 * difficulty and cheats, then its other rules; city management holds the rest. Weather (stored last) is not offered
 * (user 2026-11-15): the room keeps it off (room_options.py). */
#define ROOM_TAB0_RULES 12
#define ROOM_STORED_LAST 2 /* cheats, weather: stored after every other rule */
#define ROOM_LEAD 1 /* cheats, shown right under difficulty */
static int room_options_total(void){return room_options_tab?(CONFIG_ROOM_OPTION_COUNT-ROOM_TAB0_RULES-ROOM_STORED_LAST):ROOM_TAB0_RULES+ROOM_LEAD;}
static int room_options_index(int position){
 if(position<0 || position>=room_options_total())return -1;
 if(room_options_tab)return ROOM_TAB0_RULES+position;
 if(position==0)return 0;
 if(position<=ROOM_LEAD)return CONFIG_ROOM_OPTION_COUNT-ROOM_STORED_LAST+position-1;
 return position-ROOM_LEAD;
}
static int room_options_scrolls(void){return room_options_tab!=2 && room_options_total()>ROOM_OPTION_ROWS;}
static void room_options_bar(void){
 static int ready;int total=room_options_total();if(!ready){ready=1;scrollbar_init(&room_options_sb,0,(unsigned)total);}
 if(room_options_offset>total-ROOM_OPTION_ROWS)room_options_offset=total>ROOM_OPTION_ROWS?total-ROOM_OPTION_ROWS:0;
 room_options_sb.elements_in_view=ROOM_OPTION_ROWS;scrollbar_update_total_elements(&room_options_sb,(unsigned)total);
 if((int)room_options_sb.scroll_position!=room_options_offset)scrollbar_reset(&room_options_sb,(unsigned)room_options_offset);
}
/* Choice rows (difficulty, grand temples): one key per value, starting right after the label column. */
#define ROOM_KEYS_X 280
static void room_key_rect(int i,int k,int*x,int*w){*w=i==0?80:40;*x=ROOM_KEYS_X+k*(*w+6);}
static void room_key_name(int i,int k,char*out,size_t size){
 static const char*difficulty[]={"매우 쉬움","쉬움","보통","어려움","매우 어려움"};
 if(i==0 && k>=0 && k<5)snprintf(out,size,"%s",difficulty[k]);else snprintf(out,size,"%d",k);
}
static int room_options_editable(void){return local_role()==1 && !room_options_locked && room_options_initialized;}
static void room_options_action(const generic_button *b){
 int id=b->parameter1;
 if(id==1 && room_options_tab!=2 && !room_options_close_armed && local_role()==1 && !room_options_locked && room_options_initialized){
  /* Closing must not silently throw away choices the host has not applied yet. */
  for(int i=0;i<CONFIG_ROOM_OPTION_COUNT;i++)if(room_options_draft[i]!=config_room_value(i)){room_options_close_armed=1;snprintf(room_options_message,sizeof(room_options_message),"적용하지 않은 변경이 있습니다. 닫기를 한 번 더 누르면 버립니다.");return;}
 }
 room_options_close_armed=0;
 if(id==1){room_options_open=0;if(room_options_from_city){room_options_from_city=0;input_box_stop(&input);window_city_show();}else input_box_start(&input);return;}
 if(id==2 || id==3){room_options_tab=id-2;room_options_offset=0;return;}
 if(id==8){room_options_tab=2;room_save_begin();return;}
 if(!room_options_editable())return;
 if(id==6){for(int i=0;i<CONFIG_ROOM_OPTION_COUNT;i++)room_options_draft[i]=config_room_default(i);return;}
 if(id==7 || id==4){
  /* 7 applies and keeps the window open, 4 applies and closes. */
  if(room_options_pending){snprintf(room_options_message,sizeof(room_options_message),"적용하는 중입니다. 잠시 기다려 주세요.");return;}
  if(room_options_edit_revision!=room_options_revision){snprintf(room_options_message,sizeof(room_options_message),"설정이 바뀌었습니다. 닫았다가 다시 열어 주세요.");return;}
  if(room_options_send(room_options_edit_revision,room_options_draft)){
   if(id==7){room_options_pending=1;snprintf(room_options_message,sizeof(room_options_message),"적용하는 중…");}
   else{room_options_open=0;input_box_start(&input);}
  }else snprintf(room_options_message,sizeof(room_options_message),"이전 요청을 처리하고 있습니다. 잠시 기다려 주세요.");return;
 }
 if((id>=10 && id<10+ROOM_OPTION_ROWS) || (id>=30 && id<30+ROOM_OPTION_ROWS)){
  int down=id>=30,i=room_options_index(room_options_offset+(down?id-30:id-10));
  if(i>=0){
   int max=config_room_max(i),v=room_options_draft[i];
   if(max==1)v=!v;else{v+=down?-1:1;if(v<0)v=0;if(v>max)v=max;} /* numbers stop at their ends */
   room_options_draft[i]=v;
  }
 }
}
static generic_button room_options_buttons[]={
 {48,528,164,28,room_options_action,0,1},{48,84,144,28,room_options_action,0,2},{200,84,144,28,room_options_action,0,3},
 {588,528,164,28,room_options_action,0,4},{640,484,112,28,room_options_action,0,5},
 {228,528,164,28,room_options_action,0,6},{408,528,164,28,room_options_action,0,7},{352,84,144,28,room_options_action,0,8}
};
static void room_options_draw(void){
 graphics_in_dialog_with_size(800,600);outer_panel_draw(8,8,49,36);
 draw_utf8("멀티플레이 방 옵션",48,28,704,FONT_LARGE_BLACK);
 if(room_options_tab==2){
  draw_utf8("공동 저장 전용 설정 · 방장만 변경할 수 있습니다.",48,58,704,FONT_NORMAL_BLACK);room_save_draw();
  const char *labels[]={"닫기","난이도","도시 관리","","","","","공동 저장"};
  for(int i=0;i<8;i++){if(i>2 && i<7)continue;generic_button *b=&room_options_buttons[i];large_label_draw_custom_size(b->x,b->y,b->width,b->height);gift_center(labels[i],b->x+8,b->y+(b->height-12)/2,b->width-16,FONT_NORMAL_BLACK);}
  graphics_draw_rect(352,84,144,28,0xffa16d25);graphics_reset_dialog();return;
 }
 draw_utf8(room_options_editable()?"방장만 변경 가능 · 적용하면 참가자 준비가 해제됩니다.":room_options_locked?"게임 시작 후에는 모든 플레이어가 조회만 가능합니다.":"방장 설정을 따릅니다. 참가자는 조회만 가능합니다.",48,58,704,FONT_NORMAL_BLACK);
 int scrolls=room_options_scrolls(),roww=scrolls?672:704,right=48+roww-8;
 if(scrolls){room_options_bar();scrollbar_draw(&room_options_sb);}
 for(int j=0;j<ROOM_OPTION_ROWS;j++){
  int i=room_options_index(room_options_offset+j);if(i<0)break;int y=ROOM_OPTION_ROW_Y+j*ROOM_OPTION_ROW_H;int value=room_options_editable()?room_options_draft[i]:config_room_value(i);
  if(j%2==0)graphics_fill_rect(48,y,roww,ROOM_OPTION_ROW_H-1,0xffe7d9bc);
  char label[64];if(i==0){const char *names[]={"매우 쉬움","쉬움","보통","어려움","매우 어려움"};snprintf(label,sizeof(label),"%s",names[value]);}else if(config_room_max(i)>1)snprintf(label,sizeof(label),"%d",value);else snprintf(label,sizeof(label),"%s",value?"[켜짐]":"[꺼짐]");
  if(config_room_max(i)==1){
   button_border_draw(56,y+3,20,20,0);
   if(value)text_draw(string_from_ascii("x"),62,y+6,FONT_NORMAL_BLACK,0);
   draw_utf8(config_room_label(i),88,y+6,roww-48,FONT_NORMAL_BLACK);
  }else{
   /* A choice: every value is a marble key right beside its label; the current one is lit. */
   draw_utf8(config_room_label(i),88,y+6,ROOM_KEYS_X-96,FONT_NORMAL_BLACK);
   const mouse*km=mouse_in_dialog_with_size(mouse_get(),800,600);
   for(int k=0;k<=config_room_max(i);k++){
    int kx,kw;room_key_rect(i,k,&kx,&kw);char key[32];room_key_name(i,k,key,sizeof(key));
    int hot=room_options_editable() && km->x>=kx && km->x<kx+kw && km->y>=y+1 && km->y<y+25;
    if(k==value)graphics_fill_rect(kx+3,y+4,kw-6,18,0xfff3e4c5);
    button_border_draw(kx,y+1,kw,24,k==value || hot);
    mp_button_text(key,kx+2,y+6,kw-4,k==value || room_options_editable()?0:2);
   }

  }
 }
 draw_utf8(room_options_message[0]?room_options_message:"개인 설정·단축키와 별개입니다. 초기화도 방 옵션에만 적용됩니다.",48,494,704,FONT_SMALL_PLAIN);
 const char *labels[]={"닫기","난이도","도시 관리","확인","","방 옵션 기본값","적용","공동 저장"};
 for(int i=0;i<8;i++){if(i==4 || ((i==3 || i==5 || i==6) && !room_options_editable()))continue;generic_button *b=&room_options_buttons[i];large_label_draw_custom_size(b->x,b->y,b->width,b->height);gift_center(labels[i],b->x+8,b->y+(b->height-12)/2,b->width-16,FONT_NORMAL_BLACK);}
 graphics_draw_rect(room_options_tab?200:48,84,144,28,0xffa16d25);
 graphics_reset_dialog();
}
static void room_options_handle(const mouse *m,const hotkeys *h){
 const mouse *local=mouse_in_dialog_with_size(m,800,600);
 if(h->close_pressed){generic_button b={0};b.parameter1=1;room_options_action(&b);return;}
 if(room_options_tab==2){
  for(int i=0;i<8;i++){if(i>2 && i<7)continue;if(generic_buttons_handle_mouse(local,0,0,&room_options_buttons[i],1,&focus))return;}
  if(local_role()==1)for(int i=0;i<ROOM_SAVE_BUTTONS;i++){if(i==7 && !mp_clock_active())continue;if(generic_buttons_handle_mouse(local,0,0,&room_save_buttons[i],1,&focus))return;}return;
 }
 int scrolls=room_options_scrolls(),roww=scrolls?672:704,right=48+roww-8;
 if(scrolls){room_options_bar();if(scrollbar_handle_mouse(&room_options_sb,local,1))return;}
 if(local->left.went_up && local->x>=48 && local->x<48+roww && local->y>=ROOM_OPTION_ROW_Y && local->y<ROOM_OPTION_ROW_Y+ROOM_OPTION_ROWS*ROOM_OPTION_ROW_H){
  int row=(local->y-ROOM_OPTION_ROW_Y)/ROOM_OPTION_ROW_H,i=room_options_index(room_options_offset+row);generic_button b={0};
  if(i<0)return;
  if(config_room_max(i)>1){
   /* a choice row: only its keys react */
   if(!room_options_editable())return;
   for(int k=0;k<=config_room_max(i);k++){int kx,kw;room_key_rect(i,k,&kx,&kw);if(local->x>=kx && local->x<kx+kw){room_options_draft[i]=k;room_options_close_armed=0;return;}}
   return;
  }else b.parameter1=10+row;
  room_options_action(&b);return;
 }
 for(int i=0;i<8;i++){if(i==4 || ((i==3 || i==5 || i==6) && !room_options_editable()))continue;if(generic_buttons_handle_mouse(local,0,0,&room_options_buttons[i],1,&focus))return;}
 window_request_refresh();
}
