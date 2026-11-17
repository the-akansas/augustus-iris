#include "core/time.h"
/* Participants and city-visit permissions (576x448 dialog, 800x600 base).
 * Every player decides who may watch their own city, per player (team play
 * later); the host cannot override it. Disconnecting a participant is host-only.
 * No pause command and no OS input automation. */
#define ADMIN_W 576
#define ADMIN_H 448
static struct { char city[64],generation[65],label[256],detail[256];int removable,can_observe,allowed,revision,pending; } admin_rows[8];
static int admin_count,admin_selected=-1,admin_confirm;
static char admin_target[64],admin_generation[65],admin_reason[160];
static struct { char city[64];int revision;time_millis sent; } admin_waiting[8];
static unsigned int admin_focus;
static int admin_is_host(void){
 const char *dir=getenv("AUGUSTUS_MP_BRIDGE");char p[2048];if(!dir)return 0;
 snprintf(p,sizeof(p),"%s/role.txt",dir);FILE *f=fopen(p,"rb");int v=f?fgetc(f):0;if(f)fclose(f);return v=='1';
}
static void admin_text(const char *s,int x,int y,int width,font_t font){
 uint8_t buf[1024];encoding_from_utf8(s,buf,sizeof(buf));text_draw_multiline(buf,x,y,width,0,font,0);
}
static void admin_line(const char *s,int x,int y,int width,font_t font){
 uint8_t buf[1024];encoding_from_utf8(s,buf,sizeof(buf));text_draw_ellipsized(buf,x,y,width,font,0);
}
static void admin_center(const char *s,int x,int y,int width,font_t font){
 uint8_t buf[1024];encoding_from_utf8(s,buf,sizeof(buf));
 /* Never shrink a label: same-level text keeps one size; long text is shortened. */
 if(text_get_width(buf,font)>width)text_draw_ellipsized(buf,x,y,width,font,0);
 else text_draw_centered(buf,x,y,width,font,0);
}
static void admin_read(void){
 const char *dir=getenv("AUGUSTUS_MP_BRIDGE");char p[2048],line[1024];admin_count=0;if(!dir)return;
 snprintf(p,sizeof(p),"%s/participants.txt",dir);FILE *f=fopen(p,"rb");if(!f)return;
 while(admin_count<8 && fgets(line,sizeof(line),f)){
  char *parts[5];parts[0]=line;int ok=1;
  for(int i=1;i<5;i++){char *q=strchr(parts[i-1],'\t');if(!q){ok=0;break;}*q=0;parts[i]=q+1;}
  if(!ok)continue;parts[4][strcspn(parts[4],"\r\n")]=0;int n=admin_count++;
  snprintf(admin_rows[n].city,sizeof(admin_rows[n].city),"%s",parts[0]);
  snprintf(admin_rows[n].generation,sizeof(admin_rows[n].generation),"%s",parts[1]);
  admin_rows[n].removable=atoi(parts[2]);
  snprintf(admin_rows[n].label,sizeof(admin_rows[n].label),"%s",parts[3]);
  snprintf(admin_rows[n].detail,sizeof(admin_rows[n].detail),"%s",parts[4]);
 }
 fclose(f);
 for(int i=0;i<admin_count;i++){admin_rows[i].can_observe=0;admin_rows[i].pending=0;}
 snprintf(p,sizeof(p),"%s/observe-permissions.txt",dir);f=fopen(p,"rb");
 if(f){while(fgets(line,sizeof(line),f)){
  char city[64],gen[65];int editable,allowed,revision;
  if(sscanf(line,"%63s %64s %d %d %d",city,gen,&editable,&allowed,&revision)!=5)continue;
  for(int i=0;i<admin_count;i++)if(!strcmp(city,admin_rows[i].city)&&!strcmp(gen,admin_rows[i].generation)){
   admin_rows[i].can_observe=editable==1;admin_rows[i].allowed=allowed==1;admin_rows[i].revision=revision;
  }
 }fclose(f);}
 /* A sent change shows "pending" until a newer revision arrives (or 8s pass:
  * a rejected request leaves the old value, and the reason in admin-result). */
 time_millis now=time_get_millis();
 for(int k=0;k<8;k++)if(admin_waiting[k].city[0] && now-admin_waiting[k].sent>8000)admin_waiting[k].city[0]=0;
 for(int i=0;i<admin_count;i++)for(int k=0;k<8;k++)if(admin_waiting[k].city[0] && !strcmp(admin_waiting[k].city,admin_rows[i].city)){
  if(admin_rows[i].revision>admin_waiting[k].revision)admin_waiting[k].city[0]=0;else admin_rows[i].pending=1;
 }
 admin_selected=-1;
 for(int i=0;i<admin_count;i++)if(!strcmp(admin_target,admin_rows[i].city)&&!strcmp(admin_generation,admin_rows[i].generation))admin_selected=i;
}
static void admin_explain(const char *text){snprintf(admin_reason,sizeof(admin_reason),"%s",text);}
static void admin_click(const generic_button *b){
 if(b->parameter1==-1){if(admin_confirm)admin_confirm=0;else window_go_back();return;}
 if(b->parameter1>=100){
  int i=b->parameter1-100;if(i>=admin_count)return;
  if(!admin_rows[i].can_observe){admin_explain("내 도시는 언제든 내가 볼 수 있습니다.");return;}
  if(admin_rows[i].pending){admin_explain("변경 요청을 처리하고 있습니다. 잠시 기다려 주세요.");return;}
  char payload[180];snprintf(payload,sizeof(payload),"%s\n%s\n%d\n%d",admin_rows[i].city,admin_rows[i].generation,admin_rows[i].revision,!admin_rows[i].allowed);
  if(!mp_client_command("observe-permission",payload)){admin_explain("이전 요청을 처리하고 있습니다. 잠시 후 다시 눌러 주세요.");return;}
  for(int k=0;k<8;k++)if(!admin_waiting[k].city[0]){snprintf(admin_waiting[k].city,sizeof(admin_waiting[k].city),"%s",admin_rows[i].city);admin_waiting[k].revision=admin_rows[i].revision;admin_waiting[k].sent=time_get_millis();break;}
  admin_reason[0]=0;return;
 }
 if(b->parameter1==-2){
  if(!admin_is_host()){admin_explain("연결 해제는 방장만 할 수 있습니다.");return;}
  if(admin_selected<0 || !admin_rows[admin_selected].removable){admin_explain("연결을 해제할 참가자를 목록에서 먼저 고르세요.");return;}
  if(!admin_confirm){admin_confirm=1;admin_reason[0]=0;return;}
  char payload[160];snprintf(payload,sizeof(payload),"%s\n%s",admin_target,admin_generation);
  mp_client_command("participant-remove",payload);admin_confirm=0;admin_target[0]=0;admin_selected=-1;return;
 }
 if(!admin_is_host())return;
 int i=b->parameter1;if(i<0 || i>=admin_count || !admin_rows[i].removable)return;
 snprintf(admin_target,sizeof(admin_target),"%s",admin_rows[i].city);
 snprintf(admin_generation,sizeof(admin_generation),"%s",admin_rows[i].generation);admin_selected=i;admin_reason[0]=0;
}
static generic_button admin_buttons[]={
 {40,ADMIN_H-56,160,28,admin_click,0,-1},{ADMIN_W-200,ADMIN_H-56,160,28,admin_click,0,-2}};
static void admin_background(void){window_draw_underlying_window();}
static void admin_foreground(void){
 admin_read();graphics_in_dialog_with_size(ADMIN_W,ADMIN_H);outer_panel_draw(0,0,ADMIN_W/16,ADMIN_H/16);
 admin_center("참가자 · 내 도시 관람 허용",0,28,ADMIN_W,FONT_LARGE_BLACK);
 admin_center("누가 내 도시를 볼 수 있는지 플레이어마다 직접 정합니다. 방장도 바꿀 수 없습니다.",40,58,ADMIN_W-80,FONT_SMALL_PLAIN);
 if(admin_confirm){
  if(admin_selected<0){admin_confirm=0;admin_center("참가자가 변경되었습니다. 다시 선택해 주세요.",40,150,ADMIN_W-80,FONT_NORMAL_BLACK);}
  else{
   admin_center(admin_rows[admin_selected].label,40,110,ADMIN_W-80,FONT_NORMAL_BLACK);
   admin_center("이 참가자의 연결을 해제할까요?",40,150,ADMIN_W-80,FONT_NORMAL_BLACK);
   admin_text("다른 참가자는 계속 플레이합니다. 도시는 보존되며, 미저장 진행은 복구되지 않을 수 있습니다.",56,196,ADMIN_W-112,FONT_NORMAL_BLACK);
   admin_text("진행 중인 방에는 바로 재입장할 수 없습니다.",56,256,ADMIN_W-112,FONT_NORMAL_BLACK);
  }
 }else{
  inner_panel_draw(40,84,(ADMIN_W-80)/16,17);
  if(!admin_count)admin_center("참가자 정보를 기다리고 있습니다.",40,214,ADMIN_W-80,FONT_NORMAL_WHITE);
  for(int i=0;i<admin_count && i<6;i++){
   int y=90+i*44;
   if(i==admin_selected){graphics_draw_rect(46,y,ADMIN_W-92,42,COLOR_BORDER_BROWN);graphics_draw_rect(47,y+1,ADMIN_W-94,40,COLOR_BORDER_BROWN);}
   admin_line(admin_rows[i].label,56,y+4,300,admin_focus==(unsigned)(i+3)?FONT_NORMAL_RED:FONT_NORMAL_WHITE);
   admin_line(admin_rows[i].detail,56,y+23,300,FONT_SMALL_PLAIN);
   if(admin_rows[i].can_observe){
    graphics_draw_rect(380,y+12,18,18,COLOR_BORDER_BROWN);graphics_draw_rect(381,y+13,16,16,COLOR_BORDER_BROWN);
    if(admin_rows[i].allowed)graphics_fill_rect(384,y+16,10,10,COLOR_BORDER_BROWN);
    admin_line(admin_rows[i].pending?"변경 중…":admin_rows[i].allowed?"관람 허용":"관람 막음",408,y+14,120,admin_rows[i].pending?FONT_NORMAL_WHITE:admin_rows[i].allowed?FONT_NORMAL_WHITE:FONT_NORMAL_RED);
   }else admin_line("내 도시",408,y+14,120,FONT_NORMAL_WHITE);
  }
 }
 const char *dir=getenv("AUGUSTUS_MP_BRIDGE");char path[2048],note[512]={0};
 if(dir){snprintf(path,sizeof(path),"%s/admin-result.txt",dir);FILE *f=fopen(path,"rb");if(f){if(!fgets(note,sizeof(note),f))note[0]=0;fclose(f);note[strcspn(note,"\r\n")]=0;}}
 if(admin_reason[0])admin_center(admin_reason,40,ADMIN_H-82,ADMIN_W-80,FONT_NORMAL_RED);
 else admin_center(note,40,ADMIN_H-82,ADMIN_W-80,FONT_NORMAL_BLACK);
 for(int i=0;i<2;i++)large_label_draw_custom_size(admin_buttons[i].x,admin_buttons[i].y,admin_buttons[i].width,admin_buttons[i].height);
 admin_center(admin_confirm?"취소":"닫기",admin_buttons[0].x+8,admin_buttons[0].y+8,admin_buttons[0].width-16,admin_focus==1?FONT_NORMAL_RED:FONT_NORMAL_BLACK);
 int can_remove=admin_is_host() && (admin_confirm || (admin_selected>=0 && admin_rows[admin_selected].removable));
 if(can_remove)admin_center("연결 해제",admin_buttons[1].x+8,admin_buttons[1].y+8,admin_buttons[1].width-16,admin_focus==2?FONT_NORMAL_RED:FONT_NORMAL_BLACK);
 else{uint8_t buf[64];encoding_from_utf8("연결 해제",buf,sizeof(buf));text_draw_centered(buf,admin_buttons[1].x+8,admin_buttons[1].y+8,admin_buttons[1].width-16,FONT_NORMAL_BROWN,COLOR_FONT_GRAY_GREEN);}
 graphics_reset_dialog();
}
static void admin_handle(const mouse *m,const hotkeys *h){
 const mouse *local=mouse_in_dialog_with_size(m,ADMIN_W,ADMIN_H);
 if(input_go_back_requested(m,h)){if(admin_confirm)admin_confirm=0;else window_go_back();return;}
 if(generic_buttons_handle_mouse(local,0,0,admin_buttons,2,&admin_focus))return;
 if(!admin_confirm)for(int i=0;i<admin_count && i<6;i++){
  unsigned int f=0;
  generic_button check={372,90+i*44,ADMIN_W-424,42,admin_click,0,100+i};
  if(generic_buttons_handle_mouse(local,0,0,&check,1,&f))return;
  generic_button row={46,90+i*44,320,42,admin_click,0,i};
  if(generic_buttons_handle_mouse(local,0,0,&row,1,&f))return;
  if(f){admin_focus=i+3;break;}
 }
 window_request_refresh();
}
static void menu_mp_admin(int param){
 if(!mp_clock_active())return;
 clear_state();window_city_show();admin_selected=-1;admin_target[0]=0;admin_confirm=0;admin_focus=0;admin_reason[0]=0;
 window_type w={WINDOW_PLAIN_MESSAGE_DIALOG,admin_background,admin_foreground,admin_handle};window_show(&w);
}
