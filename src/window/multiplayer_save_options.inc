/* Save scheduling is separate from the 41 immutable simulation rules. */
static int room_save_seconds=300,room_save_enabled,room_save_kept_seconds=300,room_save_kept_enabled;
static void room_save_begin(void){char text[64];room_read("joint-save-options.txt",text,sizeof(text));room_save_seconds=300;room_save_enabled=1;if(sscanf(text,"%d %d",&room_save_enabled,&room_save_seconds)!=2){room_save_seconds=300;room_save_enabled=1;} /* default: on, 5 min */if(room_save_seconds<30 || room_save_seconds>7200)room_save_seconds=300;room_save_enabled=room_save_enabled==1;room_save_kept_seconds=room_save_seconds;room_save_kept_enabled=room_save_enabled;}
static void room_save_action(const generic_button *b){
 if(local_role()!=1)return;
 int id=b->parameter1;static const int choices[]={60,300,600,900,1800,3600};
 if(id==35){room_save_enabled=!room_save_enabled;return;}
 if(id>=40 && id<46){room_save_seconds=choices[id-40];return;} /* preset keys */
 if(id==33){char value[32];snprintf(value,sizeof(value),"%d %d",room_save_enabled,room_save_seconds);int sent=mp_client_command("joint-save-settings",value);snprintf(room_options_message,sizeof(room_options_message),sent?"설정 저장을 요청했습니다.":"이전 요청을 처리하고 있습니다.");if(sent){room_save_kept_seconds=room_save_seconds;room_save_kept_enabled=room_save_enabled;}}
 if(id==34 && mp_clock_active())mp_client_command("save","");
}
/* Interval: six preset keys (marble; the chosen one is lit); then the two actions and the checkbox. */
static generic_button room_save_buttons[]={
 {248,182,60,26,room_save_action,0,40},{316,182,60,26,room_save_action,0,41},{384,182,60,26,room_save_action,0,42},
 {452,182,60,26,room_save_action,0,43},{520,182,60,26,room_save_action,0,44},{588,182,60,26,room_save_action,0,45},
 {496,248,248,32,room_save_action,0,33},{48,328,248,32,room_save_action,0,34},{48,140,280,32,room_save_action,0,35}
};
#define ROOM_SAVE_BUTTONS 9
static void room_save_draw(void){
 button_border_draw(48,146,20,20,0);if(room_save_enabled && local_role()==1)draw_utf8("x",54,149,16,FONT_NORMAL_BLACK);
 draw_utf8(local_role()==1?"자동 공동 저장 켜기":"자동 공동 저장 (방장 전용)",80,150,640,FONT_NORMAL_BLACK);
 draw_utf8("저장 간격 (실제 시간)",48,188,196,FONT_NORMAL_BLACK);
 char label[128];
 {static const int choices[]={60,300,600,900,1800,3600};const char*names[]={"1분","5분","10분","15분","30분","60분"};
  const mouse*sm=mouse_in_dialog_with_size(mouse_get(),800,600);
  for(int i=0;i<6;i++){generic_button*b=&room_save_buttons[i];
   int chosen=choices[i]==room_save_seconds,hot=local_role()==1 && sm->x>=b->x && sm->x<b->x+b->width && sm->y>=b->y && sm->y<b->y+b->height;
   if(chosen)graphics_fill_rect(b->x+3,b->y+3,b->width-6,b->height-6,0xfff3e4c5);
   button_border_draw(b->x,b->y,b->width,b->height,chosen || hot);
   mp_button_text(names[i],b->x+2,b->y+6,b->width-4,local_role()==1?0:2);}
  if(local_role()!=1)draw_utf8("방장이 관리합니다",48,216,400,FONT_SMALL_PLAIN);}
 draw_utf8("공동 저장 중에는 도시를 잠시 동기화한 뒤 계속 진행합니다.",48,298,688,FONT_NORMAL_BLACK);
 draw_utf8("연간·월간 개인 자동저장은 멀티플레이에 적용되지 않습니다.",48,390,688,FONT_NORMAL_BLACK);
 draw_utf8("이 설정은 방장 PC에 별도로 보관되며, 진행 중에도 변경할 수 있습니다.",48,418,688,FONT_NORMAL_BLACK);
 if(local_role()==1){const char *labels[]={"공동 저장 설정 적용","지금 공동 저장"};for(int i=0;i<2;i++){if(i==1 && !mp_clock_active())continue;generic_button *b=&room_save_buttons[6+i];large_label_draw_custom_size(b->x,b->y,b->width,b->height);gift_center(labels[i],b->x+8,b->y+(b->height-12)/2,b->width-16,FONT_NORMAL_BLACK);}}
 char status[256];room_read("joint-save-result.txt",status,sizeof(status));
 if(local_role()==1 && (room_save_seconds!=room_save_kept_seconds || room_save_enabled!=room_save_kept_enabled))draw_utf8("바꾼 설정은 '공동 저장 설정 적용'을 눌러야 저장됩니다.",48,462,688,FONT_NORMAL_RED); /* user 2026-11-13 */
 else draw_utf8(status[0]?status:room_options_message,48,462,688,FONT_SMALL_PLAIN);
}
