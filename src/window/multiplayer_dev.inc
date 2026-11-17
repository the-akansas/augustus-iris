/* 시나리오 제작자 방의 도구 패널 (user 2026-11-17: "개발자 방에서만 허용"). Both editions since 2026-11-17.
 * Included by multiplayer_throne.inc when this file is present. The panel shows only while the room says it is a
 * maker room (room-dev.txt from game_bridge.py: the room's dev_mode, set when 시나리오 제작자 모드 was ticked in the
 * game hall's or the LAN's 방 만들기); in a test build the test launcher's switch shows it as before. The room refuses
 * the throne/progress keys anywhere else (lobby.py dev_tools), and a maker room's saves continue only in maker rooms
 * (game_hall.py, maker_room.py).
 *   황위 쟁탈전: the test situations under the paranoia box (open the box);
 *   황제의 순행: 다음 단계로, under the box;
 *   every mode: 자금 +10,000, 침략군 부르기, 호의 +10 (this city only, as the original console cheats book them).
 * A red "제작자 도구" button (top right, or under the throne / progress box) opens and closes the panel; the keys are the
 * ones the scenario allows (scenario_project.maker_tools, room-dev.txt). */
#include "scenario/invasion.h"
#include "city/ratings.h"
#include "building/warehouse.h"
#include "game/resource.h"
#ifdef MP_TEST_TOOLS
static int dev_test_switch(void){const char *v=getenv("AUGUSTUS_MP_TEST_TOOLS");return v && v[0]=='1';}
#else
static int dev_test_switch(void){return 0;}
#endif
static int dev_room_flag,dev_allow_all;static char dev_allowed[128];static unsigned dev_room_read_at;
/* room-dev.txt: "1 money,invade,favor,throne,progress" (the keys the scenario's author left on, scenario_project.maker_tools;
 * "-" none), "1" alone from an older bridge: every key */
static int dev_room(void){
 unsigned now=time_get_millis();
 if(!dev_room_read_at || now-dev_room_read_at>=500){
  dev_room_read_at=now?now:1;dev_room_flag=0;dev_allow_all=0;dev_allowed[0]=0;
  FILE *file=th_open("room-dev.txt");
  if(file){char line[160]={0};if(fgets(line,sizeof(line),file)){line[strcspn(line,"\r\n")]=0;dev_room_flag=line[0]=='1';
    if(line[1]==' ' && line[2])snprintf(dev_allowed,sizeof(dev_allowed),",%s,",line+2);else dev_allow_all=1;}
   fclose(file);}
 }
 return dev_room_flag;
}
static int th_test_tools(void){return dev_room() || dev_test_switch();}
/* the test launcher has every key; a maker room the keys its scenario allows */
static int dev_allows(const char *tool){
 if(!dev_room())return dev_test_switch();
 if(dev_allow_all)return 1;
 char key[32];snprintf(key,sizeof(key),",%s,",tool);return strstr(dev_allowed,key)!=0;
}
static int th_test_rect[4];
static int th_test_hidden,dev_open;   /* th_test_hidden: kept for the test launcher's /tools (nothing hides the panel now); dev_open: the panel is open */
static const char *th_test_keys[][2]={{"t-p+10","편집증 +10"},{"t-p-10","편집증 -10"},{"t-p100","편집증 100 (원정)"},{"t-wait","쿠데타 대기 없애기"},
 {"t-s+1","내 단계 +1"},{"t-s-1","내 단계 -1"},{"t-win","다음 쿠데타 성공"},{"t-lose","다음 쿠데타 실패"},{"t-rival","상대 단계 +1"}};
static const char *dev_keys[][3]={{"d-money","자금 +10,000","money"},{"d-invade","침략군 부르기","invade"},{"d-favor","호의 +10","favor"},
 {"d-goods-pick","","goods"},{"d-goods","창고에 16수레 넣기","goods"}};   /* 물자 (user 2026-11-17): which one, then into the warehouses */
#define DEV_GOODS_LOADS 16
static int dev_goods=RESOURCE_TIMBER;static char dev_goods_label[160];
/* the goods key's label: "물자: 목재" (the game's own name of the resource); the next storable one on each click */
static const char *dev_goods_name(void){
 if(dev_goods<RESOURCE_MIN || dev_goods>=RESOURCE_MAX || !resource_is_storable(dev_goods))dev_goods=RESOURCE_TIMBER;
 char name[120];encoding_to_utf8(resource_get_data(dev_goods)->text,name,sizeof(name),0);snprintf(dev_goods_label,sizeof(dev_goods_label),"물자: %s",name);return dev_goods_label;
}
static void dev_goods_next(void){for(int i=0;i<RESOURCE_MAX;i++){dev_goods++;if(dev_goods>=RESOURCE_MAX)dev_goods=RESOURCE_MIN;if(resource_is_storable(dev_goods))return;}}
#define DEV_KEYS ((int)(sizeof(dev_keys)/sizeof(dev_keys[0])))
#define DEV_TITLE "제작자 도구"
#define DEV_NONE "이 시나리오는 시험 단추를 쓰지 않습니다."
/* a key's width for `keys`; the panel (two keys a row) is never narrower than its title and 닫기 */
static int dev_width(const char *keys[][2],int n,int least){
 for(int i=0;i<n;i++){int t=th_width(keys[i][1],FONT_NORMAL_BLACK)+16;if(t>least)least=t;}
 int title=th_width(DEV_TITLE,FONT_SMALL_PLAIN)+th_width("닫기",FONT_NORMAL_BLACK)+48;
 if(!n)title=th_width(DEV_NONE,FONT_SMALL_PLAIN)+24;
 if(least*2+24<title)least=(title-24+1)/2;
 return least;
}
/* the panel: its title, 닫기, then the `n` keys, two to a row */
static void dev_panel(int x,int y,int w,const char *keys[][2],int n){
 int bw=(w-24)/2,rows=(n+1)/2,h=30+(n?rows*28:20)+6;
 th_paper(x,y,w,h);th_left(DEV_TITLE,x+10,y+8,FONT_SMALL_PLAIN,0);
 {int cw=th_width("닫기",FONT_NORMAL_BLACK)+16;th_button("d-close","닫기",x+w-cw-8,y+4,cw,22,1);}
 if(!n)th_left(DEV_NONE,x+10,y+32,FONT_SMALL_PLAIN,0);
 for(int i=0;i<n;i++)th_button(keys[i][0],keys[i][1],x+8+(i%2)*(bw+8),y+28+(i/2)*28,bw,24,1);
 th_dev_rect[3]=h;
}
/* The "제작자 도구" button opens and closes the panel (user 2026-11-17: no 숨기기 in a maker room, only open and close). It
 * sits at the top right of the city view (y), or under the throne / progress box (box_w: its width; 0 without one).
 * The mode's own keys come first while the box has something to test: 황위 쟁탈전 (its states 2, 3) or 황제의 순행
 * (state 5: the waiting time of the current step is over). */
/* The button itself: red with a gold frame, so it is seen at once (user 2026-11-17: "제작 버튼이 잘보여도 돼"). */
#define DEV_BUTTON "제작자 도구"
static void dev_button(int x,int y,int w,int h){
 int hot=th_over(x,y,w,h);
 graphics_fill_rect(x,y,w,h,hot?0xffc8321f:dev_open?0xff7a1610:0xffa8261a);
 graphics_draw_rect(x,y,w,h,0xffffcf70);graphics_draw_rect(x+1,y+1,w-2,h-2,0xff3a1a10);
 th_center(DEV_BUTTON,x,y+(h-14)/2,w,FONT_NORMAL_WHITE,0);
 if(th_hit_count<TH_HITS){th_hit *b=&th_hits[th_hit_count++];b->x=x;b->y=y;b->w=w;b->h=h;b->on=1;snprintf(b->id,sizeof(b->id),"%s",dev_open?"d-close":"d-open");}
}
static void th_dev_close(void){dev_open=0;}
/* The open panel keeps clear of what the side tabs show at the top left: the to-do cards and the note beside the
 * tabs (an open side tab closes the panel; the panel closes a side tab), and of the game's warning column at the top
 * centre (the zoom note; multiplayer_chat.c). Below them when they would meet. */
static int dev_panel_top(int x,int w,int top){
 {int reserved=window_multiplayer_top_reserved(x,x+w,0);if(reserved+4>top)top=reserved+4;}
 int left=side_pinned_left(),right=left+side_pinned_width();if(x>=right+4)return top;
 int bottom=side_pinned_top()+side_pinned_height(),tx,ty,tw,tht;
 if(side_toast_rect(&tx,&ty,&tw,&tht) && ty+tht>bottom)bottom=ty+tht;
 return side_pinned_height() || bottom>side_pinned_top()?(bottom+4>top?bottom+4:top):top;
}
static void th_test_draw(int vx,int vw,int y,int box_w){
 th_test_rect[2]=0;th_dev_rect[2]=0;if(!th_test_tools())return;
 if(throne_hud_modal())return;   /* a dialog or the scoreboard is open: only it takes clicks */
 const char *keys[16][2];int n=0;
 if(box_w && th_box.state>=2 && th_box.state!=4){
  if(th_box.state==5){if(dev_allows("progress")){keys[n][0]="t-next";keys[n][1]="다음 단계로";n++;}}
  else if(dev_allows("throne"))for(int i=0;i<(int)(sizeof(th_test_keys)/sizeof(th_test_keys[0]));i++){keys[n][0]=th_test_keys[i][0];keys[n][1]=th_test_keys[i][1];n++;}
 }
 for(int i=0;i<DEV_KEYS;i++)if(dev_allows(dev_keys[i][2])){keys[n][0]=dev_keys[i][0];keys[n][1]=dev_keys[i][1][0]?dev_keys[i][1]:dev_goods_name();n++;}
 int lw=th_width(DEV_BUTTON,FONT_NORMAL_WHITE)+28,bx=vx+vw-lw-1;
 if(!box_w){int reserved=window_multiplayer_top_reserved(bx,bx+lw,0);if(reserved+4>y)y=reserved+4;}   /* clear of the game's warnings on a narrow screen */
 dev_button(bx,y,lw,28);
 th_test_rect[0]=bx;th_test_rect[1]=y;th_test_rect[2]=lw;th_test_rect[3]=28;
 if(!dev_open)return;
 int w=dev_width(keys,n,0)*2+24;if(w<box_w)w=box_w;if(w>vw-8)w=vw-8;
 int px=vx+vw-w-1,py=dev_panel_top(px,w,y+30);dev_panel(px,py,w,keys,n);
 th_dev_rect[0]=px;th_dev_rect[1]=py;th_dev_rect[2]=w;   /* dev_panel set its height */
}
/* the panel's own keys: 1 when `id` was one of them (the t-... keys go to the room, which checks the room again) */
static int th_test_click(const char *id){
 if(strncmp(id,"d-",2))return 0;
 if(!th_test_tools())return 1;
 if(!strcmp(id,"d-open")){dev_open=1;side_close();return 1;}
 if(!strcmp(id,"d-close")){dev_open=0;return 1;}
 for(int i=0;i<DEV_KEYS;i++)if(!strcmp(id,dev_keys[i][0]) && !dev_allows(dev_keys[i][2])){strcpy(notice,"제작: 이 시나리오는 이 시험 단추를 쓰지 않습니다.");return 1;}
 if(!strcmp(id,"d-money")){city_finance_process_console(10000);strcpy(notice,"제작: 자금 10,000 Dn을 넣었습니다.");return 1;}
 if(!strcmp(id,"d-invade")){scenario_invasion_start_from_console(INVASION_TYPE_ENEMY_ARMY,16,0);strcpy(notice,"제작: 침략군을 불렀습니다.");return 1;}
 if(!strcmp(id,"d-favor")){city_ratings_change_favor(10);strcpy(notice,"제작: 호의를 10 올렸습니다.");return 1;}
 if(!strcmp(id,"d-goods-pick")){dev_goods_next();return 1;}
 if(!strcmp(id,"d-goods")){   /* into the warehouses, whatever their settings; what does not fit is not added */
  dev_goods_name();int left=building_warehouses_add_resource(dev_goods,DEV_GOODS_LOADS,0);
  if(left>=DEV_GOODS_LOADS)strcpy(notice,"제작: 물자를 넣을 창고 자리가 없습니다.");
  else snprintf(notice,sizeof(notice),"%s",left?"제작: 창고에 자리가 있는 만큼 물자를 넣었습니다.":"제작: 창고에 물자 16수레를 넣었습니다.");
  return 1;
 }
 return 0;
}
