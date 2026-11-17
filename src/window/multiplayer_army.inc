/* Empire-map army menu. Engine state is read on the engine thread only. */
#include "figure/formation.h"
#include "figure/figure.h"
static int army_role=1,army_selected,army_page,army_confirm;
static char army_destination[65],army_target_label[160];
static int army_forms[20],army_count;
static char army_visits[12][65],army_visit_city[12][65],army_visit_label[12][240];
static int army_visit_role[12],army_visits_count,army_visit_page;
static char army_order_id[65],army_order_state[32],army_order_notice[512];
static void army_click(const generic_button *b);
/* 576x448 dialog at (32,16); content keeps 40px side and 28px bottom margins. */
#define ARMY_L 72
#define ARMY_R 568
static generic_button army_buttons[]={
 {72,112,288,24,army_click,0,0},{72,136,288,24,army_click,0,1},
 {72,160,288,24,army_click,0,2},{72,184,288,24,army_click,0,3},
 {72,208,288,24,army_click,0,4},{72,232,288,24,army_click,0,5},
 {376,112,92,28,army_click,0,10},{476,112,92,28,army_click,0,11},
 {376,224,192,28,army_click,0,12},{448,294,120,22,army_click,0,13},
 {72,260,140,24,army_click,0,14},{220,260,140,24,army_click,0,15},
 {72,318,496,22,army_click,0,20},{72,342,496,22,army_click,0,21},
 {72,366,496,22,army_click,0,22},
 {72,408,200,28,army_click,0,30},{368,408,200,28,army_click,0,31}
};
/* Legions abroad: three rows show; more scroll under the original scrollbar (first row = army_visit_page). */
#include "graphics/scrollbar.h"
static void army_visit_scrolled(void);
static scrollbar_type army_visit_sb={.x=ARMY_R-24,.y=316,.length=72,.scrollable_width=496,.on_scroll_callback=army_visit_scrolled,.step_size=1,.elements_in_view=3};
static void army_visit_scrolled(void){army_visit_page=(int)army_visit_sb.scroll_position;window_invalidate();}
static void army_visit_bar(void){
 if(army_visit_page>army_visits_count-3)army_visit_page=army_visits_count>3?army_visits_count-3:0;
 static int ready;if(!ready){ready=1;scrollbar_init(&army_visit_sb,0,(unsigned)army_visits_count);}
 army_visit_sb.elements_in_view=3;scrollbar_update_total_elements(&army_visit_sb,(unsigned)army_visits_count);
 if((int)army_visit_sb.scroll_position!=army_visit_page)scrollbar_reset(&army_visit_sb,(unsigned)army_visit_page);
}
static void army_read(void){
 army_count=0;
 for(int i=1;i<formation_count() && army_count<20;i++){
  const formation *m=formation_get(i);
  if(m->in_use && m->is_legion && !m->mp_expedition_id)army_forms[army_count++]=i;
 }
 army_visits_count=0;army_order_id[0]=army_order_state[0]=army_order_notice[0]=0;
 const char *dir=getenv("AUGUSTUS_MP_BRIDGE");if(!dir)return;
 char path[2048],line[512];snprintf(path,sizeof(path),"%s/army-visits.txt",dir);FILE *f=fopen(path,"rb");
 if(f){while(army_visits_count<12 && fgets(line,sizeof(line),f)){
  int i=army_visits_count;
  if(sscanf(line,"%64s\t%64s\t%d\t%239[^\r\n]",army_visits[i],army_visit_city[i],&army_visit_role[i],army_visit_label[i])==4)army_visits_count++;
 }fclose(f);}
 snprintf(path,sizeof(path),"%s/army-order.txt",dir);f=fopen(path,"rb");
 if(f){fscanf(f,"%64s\n%31s\n",army_order_id,army_order_state);fgets(army_order_notice,sizeof(army_order_notice),f);fclose(f);}
}
static int army_waiting(void){return !strcmp(army_order_state,"saving") || !strcmp(army_order_state,"preparing");}
/* The newest order is on the road ("moving"): it can still be called back, and it no longer blocks sending another legion. */
static int army_cancellable(void){return army_waiting() || !strcmp(army_order_state,"moving");}
static const char *army_type(int type){return type==11?"투창병":type==12?"기병":type==13?"군단병":type==92?"보조 보병":"궁병";}
static int army_available(int id){
 const formation *m=formation_get(id);
 if(!m->in_use || !m->is_legion || m->mp_expedition_id || !m->is_at_fort || !m->num_figures || m->recent_fight || m->empire_service || m->in_distant_battle)return 0;
 for(unsigned i=1;i<figure_count();i++){const figure *v=figure_get(i);if(v->formation_id==(unsigned)id && !figure_is_dead(v) && figure_is_legion(v) && (v->action_state!=80 || !v->formation_at_rest || v->opponent_id || v->num_attackers))return 0;}
 return 1;
}
static const char *army_blocked(int id){
 if(id==31)return army_cancellable()?0:"취소할 파견 요청이 없습니다.";
 if(army_waiting())return "파견 요청을 처리하고 있습니다. 끝나면 다시 고를 수 있습니다.";
 if(mp_clock_trade_busy())return "공동 저장 중입니다. 잠시 뒤 다시 눌러 주세요.";
 if(id==12)return !army_count?"요새에 대기 중인 군단이 없습니다.":!army_selected?"왼쪽 목록에서 군단을 먼저 고르세요.":!army_available(army_selected)?"이 군단은 요새에서 쉬고 있지 않아 지금 보낼 수 없습니다.":0;
 if(id==14 || id==15)return army_count>6?0:"군단이 한 쪽에 모두 보입니다.";
 return 0;
}
static void army_draw(void){
 army_read();graphics_in_dialog();outer_panel_draw(32,16,36,28);
 draw_utf8("군단 파견",ARMY_L,40,ARMY_R-ARMY_L,FONT_LARGE_BLACK);
 char label[512];snprintf(label,sizeof(label),"목적지: %s",army_target_label);draw_utf8(label,ARMY_L,72,ARMY_R-ARMY_L,FONT_NORMAL_BLACK);
 draw_utf8("요새에서 쉬고 있는 군단만 보낼 수 있습니다.",ARMY_L,94,ARMY_R-ARMY_L,FONT_SMALL_PLAIN);
 inner_panel_draw(ARMY_L,112,18,9);
 for(int i=0;i<6;i++){
  int index=army_page*6+i;if(index>=army_count)break;const formation *m=formation_get(army_forms[index]);
  snprintf(label,sizeof(label),"%s %d명 · 사기 %d%s",army_type(m->figure_type),m->num_figures,m->morale,army_available(m->id)?"":" · 대기 필요");
  if(army_selected==(int)m->id)button_border_draw(ARMY_L,112+i*24,288,24,1);
  draw_utf8(label,ARMY_L+8,118+i*24,272,army_selected==(int)m->id?FONT_NORMAL_RED:FONT_NORMAL_WHITE);
 }
 if(!army_count)draw_utf8("보낼 수 있는 군단이 없습니다.",ARMY_L+8,124,272,FONT_NORMAL_WHITE);
 /* Role buttons (support / attack) on top, what the chosen role does below them. */
 if(army_role==2){
  draw_utf8("상대 도시를 공격합니다.",376,148,192,FONT_SMALL_PLAIN);
  draw_utf8("편도 2개월 · 한 도시에 2부대까지",376,164,192,FONT_SMALL_PLAIN);
  draw_utf8("병사를 잃을 수 있습니다.",376,180,192,FONT_SMALL_PLAIN);
 }else{
  draw_utf8("침략을 함께 막아 줍니다.",376,148,192,FONT_SMALL_PLAIN);
  draw_utf8("편도 2개월 · 여러 군단 가능",376,164,192,FONT_SMALL_PLAIN);
  draw_utf8("자원을 쓰지 않습니다.",376,180,192,FONT_SMALL_PLAIN);
 }
 if(army_confirm)draw_utf8(army_role==2?"한 번 더 누르면 공격하러 출발합니다.":"한 번 더 누르면 출발합니다.",376,202,192,FONT_NORMAL_RED);
 graphics_draw_line(ARMY_L,ARMY_R,290,290,0xff9b8060);
 draw_utf8("파견 중인 군단 · 누르면 귀환",ARMY_L,298,360,FONT_NORMAL_BLACK);
 for(int i=0;i<3;i++){
  int index=army_visit_page+i,w=army_visits_count>3?468:496;if(index>=army_visits_count)break;
  large_label_draw_custom_size(ARMY_L,318+i*24,w,22);draw_utf8(army_visit_label[index],ARMY_L+8,322+i*24,w-16,FONT_NORMAL_BLACK);
 }
 if(!army_visits_count)draw_utf8("파견 중인 군단이 없습니다.",ARMY_L+8,324,480,FONT_NORMAL_BLACK);
 if(army_visits_count>3){army_visit_bar();scrollbar_draw(&army_visit_sb);}
 const char *message=notice[0]?notice:army_order_notice;
 draw_utf8(message,ARMY_L,392,ARMY_R-ARMY_L,notice[0]?FONT_NORMAL_RED:FONT_NORMAL_BLACK);
 for(int i=6;i<sizeof(army_buttons)/sizeof(army_buttons[0]);i++){
  generic_button *b=&army_buttons[i];int id=b->parameter1;if(id>=20 && id<=22)continue;
  if(id==13)continue; /* paging became the scrollbar */
  const char *text=id==10?"지원군":id==11?"공격군":id==12?(army_confirm?"파견 확인":"선택한 군단 파견"):id==13?"다음 목록":id==14?"이전 군단":id==15?"다음 군단":id==30?"제국지도로":"마지막 파견 취소";
  int selected=(id==10 && army_role==1)||(id==11 && army_role==2);
  mp_label_button(b->x,b->y,b->width,b->height,text,selected?1:id!=30 && id!=13 && army_blocked(id)?2:0);
 }
 graphics_reset_dialog();
}
static void army_click(const generic_button *b){
 int id=b->parameter1;char cmd[1024];
 if(id==30){army_tab=0;notice[0]=0;window_go_back();return;}
 if(id!=13 && id<20 && (id>=10 || id==31) && army_blocked(id)){snprintf(notice,sizeof(notice),"%s",army_blocked(id));return;}
 if(id==31){snprintf(cmd,sizeof(cmd),"cancel %s",army_order_id);if(mp_client_command("army",cmd))notice[0]=0;return;}
 if(army_waiting() || mp_clock_trade_busy())return;
 if(id<6){int index=army_page*6+id;if(index<army_count){army_selected=army_forms[index];army_confirm=0;}return;}
 if(id==10 || id==11){army_role=id==10?1:2;army_confirm=0;notice[0]=0;return;}
 if(id==14 || id==15){int pages=(army_count+5)/6;if(pages)army_page=(army_page+(id==14?-1:1)+pages)%pages;return;}
 if(id==12){
  if(!army_confirm){army_confirm=1;notice[0]=0;return;}
  const formation *m=formation_get(army_selected);
  int n=snprintf(cmd,sizeof(cmd),"depart %s %d %d %d %d",army_destination,army_role,army_selected,m->building_id,m->figure_type);
  for(unsigned i=1;i<figure_count() && n<(int)sizeof(cmd)-32;i++){const figure *v=figure_get(i);if(v->formation_id==m->id && !figure_is_dead(v) && figure_is_legion(v))n+=snprintf(cmd+n,sizeof(cmd)-n," %u:%u",v->id,v->created_sequence);}
 }else if(id>=20 && id<=22){int index=army_visit_page+id-20;if(index>=army_visits_count)return;snprintf(cmd,sizeof(cmd),"return %s %d %s",army_visit_city[index],army_visit_role[index],army_visits[index]);}
 else return;
 if(mp_client_command("army",cmd)){notice[0]=0;army_confirm=0;}else strcpy(notice,"이전 요청을 처리 중입니다.");
}
static void army_handle(const mouse *m,const hotkeys *h){
 if(h->close_pressed){army_tab=0;notice[0]=0;window_go_back();return;}
 if(army_visits_count>3){army_visit_bar();if(scrollbar_handle_mouse(&army_visit_sb,mouse_in_dialog(m),1))return;}
 int n=sizeof(army_buttons)/sizeof(army_buttons[0]);
 for(int i=0;i<n;i++){
  if(army_buttons[i].parameter1==13)continue;
  if(generic_buttons_handle_mouse(mouse_in_dialog(m),0,0,&army_buttons[i],1,&focus))return;
 }
}
