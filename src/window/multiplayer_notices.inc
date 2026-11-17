/* Presentation only: move the camera once, never a unit. */
#include "multiplayer/mailbox_publish.h"
#include "city/view.h"
#include "city/map.h"
#include "map/grid.h"
#include "building/state.h"
#include <time.h>
typedef struct {
 unsigned long long sequence;
 unsigned target,fallback,generation;
 unsigned int resolved_at;
 int kind,source,grid,location;
 char text[768];
} city_notice;
static city_notice city_notices[8];
/* Left side tabs (multiplayer_sidetabs.inc): 0 closed, 1 notices, 2 trade, 3 players, 4 army.
 * While the notice tab is open, the notice list below lays itself out inside its panel. */
static int side_tab,side_hidden; /* side_hidden: the whole strip folded away (browser-style hide) */
#define SIDE_STRIP_W 52 /* grey stone strip; the open tab's 64 px frame reaches past it into the panel */
#define SIDE_SLOT 64
#define SIDE_PANEL_X 46
int window_city_topleft_labels_bottom(void);   /* window/city.c: time left, FPS, the scenario's custom variables */
int window_multiplayer_top_reserved(int left,int right,int *edge);   /* multiplayer_chat.c: the game's top centre column */
/* The strip's top below the game's own labels at the top left (user 2026-11-17: nothing of ours over the game's items);
 * 44 below the top menu without them. Its hide control (20 high) sits just above it. */
static int side_panel_y(void){int vx,vy,vw,vh;city_view_get_viewport(&vx,&vy,&vw,&vh);int y=window_city_topleft_labels_bottom()-vy+24;return y>44?y:44;}
#define SIDE_PANEL_Y side_panel_y()
/* Open panel rectangle, recomputed every frame from what the tab holds (side_layout). */
static int side_px,side_py,side_pw,side_ph,side_content_w;
static void side_view(int*x,int*y){int w,h;city_view_get_viewport(x,y,&w,&h);}
#define SIDE_HANDLE_W 20 /* folded strip: the handle that brings it back */
/* To-do cards (build a post, answer a money gift) stay pinned beside the tabs while the
 * notice tab is shut: right of the strip, of the folded handle, or of another open panel. */
static int side_pinned_left(void){int vx,vy,vw,vh;city_view_get_viewport(&vx,&vy,&vw,&vh);return side_hidden?vx+SIDE_HANDLE_W+2:side_tab?side_px+side_pw+4:vx+SIDE_STRIP_W+2;}
static int side_pinned_width(void){int vx,vy,vw,vh;city_view_get_viewport(&vx,&vy,&vw,&vh);int w=vx+vw-8-side_pinned_left();return w>280?280:w;}
/* The cards' top: beside the strip, and below the game's warning column (the zoom note) where they would meet it */
static int side_pinned_top(void){
 int vx,vy,vw,vh;city_view_get_viewport(&vx,&vy,&vw,&vh);int top=vy+SIDE_PANEL_Y+6,left=side_pinned_left();
 int reserved=window_multiplayer_top_reserved(left,left+side_pinned_width(),0);return reserved+4>top?reserved+4:top;
}
/* A short card at the top right when something new arrives while the notice tab is shut. */
static int side_scroll_offset(void);
static int city_notice_visible(void);
static unsigned long long city_toast_sequence;
static unsigned city_toast_until;
static int city_notice_count,city_notice_folded,city_notice_page,city_notice_log_mode;
static unsigned int city_notice_read_at,city_notice_until;
static unsigned long long city_notice_seen;
static void city_notice_reset(void){
 memset(city_notices,0,sizeof(city_notices));city_notice_count=city_notice_folded=city_notice_page=city_notice_log_mode=0;
 city_notice_seen=city_notice_read_at=city_notice_until=0;
}
static int city_notice_resolve(city_notice *n){
 if(n->kind==3 || n->kind==4){n->location=5;return 5;}
 if(n->kind==5 || n->kind==7){n->location=6;return 6;}   /* 7: Race for the Throne line (no place to show) */
 if(n->kind==6){
  /* Post holding goods no store can take: point at the post itself. */
  if(n->fallback<building_count()){const building*b=building_get(n->fallback);
   if(b->type==BUILDING_PLAYER_TRADE_POST && b->state==BUILDING_STATE_IN_USE && b->created_sequence==n->generation){n->grid=map_grid_offset(b->x,b->y);n->location=7;return 7;}}
  n->location=0;return 0;
 }
 for(unsigned i=1;i<figure_count();i++){
  const figure *f=figure_get(i);if(figure_is_dead(f) || f->is_ghost)continue;
  int matches=n->kind==1 && f->mp_contract_id==n->target && (f->type==FIGURE_TRADE_CARAVAN || f->type==FIGURE_TRADE_SHIP);
  if(n->kind==2 && f->formation_id && f->formation_id<(unsigned)formation_count()){
   const formation *m=formation_get(f->formation_id);matches=m->in_use && m->mp_expedition_id==n->target;
  }
  if(matches){n->grid=map_grid_offset(f->x,f->y);n->location=1;return 1;}
 }
 if(n->kind==1 && n->source && n->fallback<building_count()){
  const building*b=building_get(n->fallback);
  if(b->type==BUILDING_PLAYER_TRADE_POST && b->state==BUILDING_STATE_IN_USE && b->created_sequence==n->generation){n->grid=map_grid_offset(b->x,b->y);n->location=2;return 2;}
 }
 if(n->kind==2 && n->source && n->fallback<(unsigned)formation_count()){
  const formation*m=formation_get(n->fallback);
  if(m->in_use && m->mp_expedition_id==n->target && m->building_id>0 && (unsigned)m->building_id<building_count()){
   const building*b=building_get(m->building_id);if(b->state==BUILDING_STATE_IN_USE){n->grid=map_grid_offset(b->x,b->y);n->location=2;return 2;}
  }
 }
 if(n->grid>0){n->location=3;return 3;}
 if(!n->source){const map_tile *entry=city_map_entry_point();n->grid=entry->grid_offset;n->location=4;return 4;}
 n->location=0;return 0;
}
static void city_notice_read(void){
 unsigned int now=time_get_millis();if(now-city_notice_read_at<250)return;city_notice_read_at=now;
 const char*dir=getenv("AUGUSTUS_MP_BRIDGE");if(!dir)return;
 char path[2048],line[256];snprintf(path,sizeof(path),"%s/city-notices.txt",dir);FILE*f=fopen(path,"rb");if(!f)return;
 city_notice next[8]={0};int count=-1,ok=1;
 if(!fgets(line,sizeof(line),f) || sscanf(line,"%d",&count)!=1 || count<0 || count>8){fclose(f);return;}
 for(int i=0;i<count;i++){
  city_notice*n=&next[i];
  if(!fgets(line,sizeof(line),f) || sscanf(line,"%llu %d %u %u %u %d",&n->sequence,&n->kind,&n->target,&n->fallback,&n->generation,&n->source)!=6 || !n->sequence || !n->target || n->kind<1 || n->kind>7 || (n->kind==3 && n->target>8) || n->source<0 || n->source>1 || (i && n->sequence<=next[i-1].sequence) || !fgets(n->text,sizeof(n->text),f) || !strchr(n->text,'\n')){ok=0;break;}
  n->text[strcspn(n->text,"\r\n")]=0;
  for(int j=0;j<city_notice_count;j++)if(city_notices[j].kind==n->kind && city_notices[j].target==n->target && city_notices[j].source==n->source){n->grid=city_notices[j].grid;n->location=city_notices[j].location;n->resolved_at=city_notices[j].resolved_at;}
 }
 fclose(f);if(!ok)return;
 memcpy(city_notices,next,sizeof(next));city_notice_count=count;
 if(city_notice_page>=count)city_notice_page=0;
 if(!count)city_notice_until=0;
 if(count && next[count-1].sequence>city_notice_seen){
  int route_sound=0;for(int i=0;i<count;i++)if(next[i].sequence>city_notice_seen && (next[i].kind==3 || next[i].kind==4 || next[i].kind==6 || next[i].kind==7))route_sound=1;
  if(route_sound)sound_effect_play(SOUND_EFFECT_FANFARE);
  int k=next[count-1].kind;city_toast_sequence=next[count-1].sequence;city_toast_until=now+(k==3 || k==4?15000:8000);
  city_notice_seen=next[count-1].sequence;city_notice_folded=1;city_notice_page=0;city_notice_until=now+8000;
 }
}
/* Acknowledge exact displayed events, never a newer arrival by watermark. */
static void city_notice_ack_sequence(unsigned long long sequence){
 const char*dir=getenv("AUGUSTUS_MP_BRIDGE");if(!dir || !sequence)return;
 unsigned long long ids[64],v;int count=0;char path[2048],text[1600];
 snprintf(path,sizeof(path),"%s/city-notice-read.txt",dir);FILE*f=fopen(path,"rb");
 if(f){while(count<64 && fscanf(f,"%llu",&v)==1)if(v && v!=sequence)ids[count++]=v;fclose(f);}
 if(count==64){memmove(ids,ids+1,63*sizeof(*ids));count=63;}ids[count++]=sequence;
 size_t used=0;for(int i=0;i<count;i++)used+=snprintf(text+used,sizeof(text)-used,"%llu\n",ids[i]);
 mp_publish_text(dir,"city-notice-read",text,used);
}
static void city_notice_ack_visible(void){
 for(int row=0;row<city_notice_visible();row++){int i=city_notice_count-1-city_notice_page-row;if(i>=0 && i<city_notice_count)city_notice_ack_sequence(city_notices[i].sequence);}
}
/* Past notices: a read-only log the bell panel can open, newest first. */
#define CITY_NOTICE_LOG 64
#define CITY_NOTICE_LOG_ROWS 10
typedef struct {unsigned long long sequence;int kind;long long when;char text[384];} city_notice_log_entry;
static city_notice_log_entry city_notice_log[CITY_NOTICE_LOG];
static int city_notice_log_count,city_notice_log_offset;
static unsigned city_notice_log_read_at;
static void city_notice_log_read(void){
 unsigned now=time_get_millis();if(city_notice_log_read_at && now-city_notice_log_read_at<500)return;city_notice_log_read_at=now;
 const char*dir=getenv("AUGUSTUS_MP_BRIDGE");if(!dir)return;
 char path[2048],line[512];snprintf(path,sizeof(path),"%s/city-notice-log.txt",dir);FILE*f=fopen(path,"rb");if(!f)return;
 static city_notice_log_entry next[CITY_NOTICE_LOG];int count=-1,ok=1;
 if(!fgets(line,sizeof(line),f) || sscanf(line,"%d",&count)!=1 || count<0 || count>CITY_NOTICE_LOG){fclose(f);return;}
 for(int i=0;i<count;i++){
  city_notice_log_entry*e=&next[i];
  if(!fgets(line,sizeof(line),f) || sscanf(line,"%llu %d %lld",&e->sequence,&e->kind,&e->when)!=3 || !fgets(e->text,sizeof(e->text),f)){ok=0;break;}
  e->text[strcspn(e->text,"\r\n")]=0;
 }
 fclose(f);if(!ok)return;
 memcpy(city_notice_log,next,sizeof(next));city_notice_log_count=count;
 if(city_notice_log_offset>count-1)city_notice_log_offset=count>0?count-1:0;
}
static int city_notice_expanded(void){return side_tab==1;}
static int city_notice_preview(void){if(1)return 0;int k=city_notice_count?city_notices[city_notice_count-1].kind:0;return city_notice_count && k!=3 && k!=4 && city_notice_folded && (int)(city_notice_until-time_get_millis())>0;}
static int city_notice_visible(void){if(side_tab==1)return city_notice_count;int n=city_notice_count-city_notice_page;if(n>3)n=3;return n>0?n:0;}
static int city_notice_log_rows(void){return side_tab==1?city_notice_log_count:CITY_NOTICE_LOG_ROWS;}
/* Height of whatever the expanded panel shows below its header. */
static int city_notice_panel_height(void){return city_notice_log_mode?(city_notice_log_rows()>0?city_notice_log_rows():1)*22+16:city_notice_visible()*64;}
static int city_notice_width(void){return side_tab==1?side_content_w:side_pinned_width();}
static int city_notice_left(void){return side_tab==1?side_px+16:side_pinned_left();}
static int city_notice_right(void){return city_notice_left()+city_notice_width();}
static int city_notice_top(void){return side_tab==1?side_py+52-side_scroll_offset():side_pinned_top();}
static int city_notice_fold_left(void){return city_notice_right()-48;}
static int city_notice_open_proposal(city_notice*n){
 if(!n->sequence)for(int i=city_notice_count-1;i>=0;i--)if(city_notices[i].kind==n->kind && city_notices[i].target==n->target){n->sequence=city_notices[i].sequence;break;}
 if(n->kind==4){
  const char*dir=getenv("AUGUSTUS_MP_BRIDGE");if(!dir)return 0;
  char path[2048],peer[64],cmd[160];unsigned id;snprintf(path,sizeof(path),"%s/agreement-targets.txt",dir);FILE*f=fopen(path,"rb");if(!f)return 0;
  int found=0;while(fscanf(f,"%u %63s",&id,peer)==2)if(id==n->target){found=1;break;}fclose(f);if(!found)return 0;
  snprintf(cmd,sizeof(cmd),"contract_focus %u %s",n->target,peer);if(!mp_client_command("trade",cmd))return 0;
  city_notice_ack_sequence(n->sequence);window_multiplayer_trade_show();snprintf(gift_recipient,sizeof(gift_recipient),"%s",peer);gift_peer_locked=1;gift_picker=0;gift_received=6;partner_direct=1;partner_answer_dismissed=0;city_notice_folded=1;city_notice_until=0;return 1;
 }
 if(n->kind==3){
  const char*dir=getenv("AUGUSTUS_MP_BRIDGE");if(!dir)return 0;
  char path[2048],peer[64],chosen[64]={0};int slot,state,revision;
  snprintf(path,sizeof(path),"%s/route-state.txt",dir);FILE*f=fopen(path,"rb");if(!f)return 0;
  while(fscanf(f,"%d %63s %d %d",&slot,peer,&state,&revision)==4)if(slot==(int)n->target){snprintf(chosen,sizeof(chosen),"%s",peer);break;}
  fclose(f);if(!chosen[0])return 0;
  city_notice_ack_sequence(n->sequence);window_multiplayer_trade_show();
  snprintf(gift_recipient,sizeof(gift_recipient),"%s",chosen);gift_peer_locked=1;gift_picker=0;gift_received=6;partner_direct=1;partner_answer_dismissed=0;city_notice_folded=1;city_notice_until=0;return 1;
 }
 return 0;
}
/* CLI tests call actions directly, without synthetic input. */
static int city_notice_action(int action,int index){
 if(action==0){if(!city_notice_log_mode)city_notice_ack_visible();city_notice_folded=1;city_notice_log_mode=0;city_notice_until=0;if(side_tab==1)side_tab=0;return 1;}
 if(action==2){city_notice_folded=0;city_notice_page=0;city_notice_log_mode=!city_notice_count;city_notice_log_offset=0;city_notice_log_read_at=0;city_notice_until=time_get_millis()+8000;return 1;}
 if(action==3){if(!city_notice_log_mode)city_notice_ack_visible();city_notice_log_mode=!city_notice_log_mode;city_notice_log_offset=0;city_notice_log_read_at=0;city_notice_page=0;return 1;}
 int i=city_notice_count-1-city_notice_page-index;
 if(action!=1 || index<0 || index>=city_notice_visible() || i<0 || i>=city_notice_count)return 0;
 city_notice*n=&city_notices[i];
 if(n->kind==3 || n->kind==4)return city_notice_open_proposal(n);
 if(n->kind==5 || n->kind==7){city_notice_ack_sequence(n->sequence);return 1;}
 if(!city_notice_resolve(n) || n->grid<=0)return 0;
 city_notice_ack_sequence(n->sequence);city_view_go_to_grid_offset(n->grid);return n->grid;
}
/* Persistent build reminder: shown at the top right until every concluded
 * partner contract has its dedicated post. Presentation only; the build
 * button uses the same route selection as the partner dialog. */
static unsigned post_reminder_peers_at;
static int post_reminder_hover;
static int post_reminder_find(int*others){
 unsigned now=time_get_millis();
 if(!post_reminder_peers_at || now-post_reminder_peers_at>=500){post_reminder_peers_at=now;gift_read_peers();}
 partner_read();*others=0;int found=-1;
 for(int i=0;i<partner_count;i++){
  partner_row*p=&partner_rows[i];
  if(p->state!=1 || p->my_post || mp_route_post_for(p->slot) || !partner_online(p->city))continue;
  if(found<0)found=i;else (*others)++;
 }
 return found;
}
static int post_reminder_rect(int*x,int*y,int*w){
 *x=city_notice_left();*w=city_notice_width();*y=city_notice_top();
 if(city_notice_expanded())*y+=city_notice_panel_height()+4;
 else if(city_notice_preview())*y+=52;
 return *w>=220;
}
static int city_card_h(void){return 64;}
static int post_reminder_building(void){return building_construction_type()==BUILDING_PLAYER_TRADE_POST;}
static void post_reminder_draw(void){
 int others,i=post_reminder_find(&others),x,y,w;post_reminder_hover=0;
 if(i<0 || !post_reminder_rect(&x,&y,&w))return;
 partner_row*p=&partner_rows[i];int building=post_reminder_building();char line[384];
 int h=city_card_h(),narrow=1;
 large_label_draw_custom_size(x,y,w,h);graphics_draw_rect(x,y,w,h,0xffffcf70);
 graphics_fill_rect(x+8,y+8,8,h-16,mp_route_peer_color(p->slot));graphics_draw_rect(x+8,y+8,8,h-16,COLOR_BLACK);
 draw_utf8(building?"교역소를 지을 곳을 고르세요":"전용 교역소를 지을 수 있습니다",x+24,y+9,narrow?w-32:w-152,FONT_NORMAL_BLACK);
 if(narrow)snprintf(line,sizeof(line),others?"%s 외":"%s",partner_label(p->city));
 else if(others)snprintf(line,sizeof(line),"계약 상대: %s 외 %d곳",partner_label(p->city),others);
 else snprintf(line,sizeof(line),"계약 상대: %s",partner_label(p->city));
 draw_utf8(line,x+24,narrow?y+40:y+31,w-152,FONT_SMALL_PLAIN);
 const mouse*m=mouse_get();int bx=x+w-120,by=y+31;
 post_reminder_hover=m->x>=bx && m->x<bx+112 && m->y>=by && m->y<by+26;
 large_label_draw_custom_size(bx,by,112,26);if(post_reminder_hover)button_border_draw(bx,by,112,26,1);
 gift_center(building?"건설 취소":"교역소 건설",bx+4,by+7,104,FONT_NORMAL_BLACK);
}
static int post_reminder_input(const mouse*m){
 int others,i=post_reminder_find(&others),x,y,w;
 if(i<0 || !post_reminder_rect(&x,&y,&w) || m->x<x || m->x>=x+w || m->y<y || m->y>=y+city_card_h())return 0;
 int bx=x+w-120,by=y+31;
 if(m->left.went_up && m->x>=bx && m->x<bx+112 && m->y>=by && m->y<by+26){
  if(post_reminder_building())building_construction_cancel();
  else if(mp_route_select(partner_rows[i].slot)){building_construction_set_type(BUILDING_PLAYER_TRADE_POST,0);side_tab=0;} /* the next click goes to the map */
 }
 return 1;
}
/* Incoming money gift: answered right here, like a whisper. Only the two
 * cities involved ever see it; no contract, post or caravan is involved. */
static unsigned long long cash_card_answered;
static unsigned cash_card_answered_at;
static int cash_card_find(int*others){
 *others=0;int found=-1;
 if(cash_card_answered && time_get_millis()-cash_card_answered_at>=4000)cash_card_answered=0;
 for(int i=0;i<deal_count;i++){
  deal_row*d=&deal_rows[i];
  if(d->resource || d->kind!=0 || d->outgoing || d->id_type || d->id==cash_card_answered || !partner_online(d->peer))continue;
  if(found<0)found=i;else (*others)++;
 }
 return found;
}
static int cash_card_rect(int*x,int*y,int*w){
 if(!post_reminder_rect(x,y,w))return 0;
 int others;if(post_reminder_find(&others)>=0)*y+=city_card_h()+4;
 return 1;
}
static void cash_card_draw(void){
 int others,i=cash_card_find(&others),x,y,w;
 if(i<0 || !cash_card_rect(&x,&y,&w))return;
 deal_row*d=&deal_rows[i];char line[384];int slot=0;
 for(int k=0;k<partner_count;k++)if(!strcmp(partner_rows[k].city,d->peer))slot=partner_rows[k].slot;
 int h=city_card_h(),narrow=1;
 large_label_draw_custom_size(x,y,w,h);graphics_draw_rect(x,y,w,h,0xffffcf70);
 graphics_fill_rect(x+8,y+8,8,h-16,slot?mp_route_peer_color(slot):0xffcbd1d7);graphics_draw_rect(x+8,y+8,8,h-16,COLOR_BLACK);
 if(narrow)snprintf(line,sizeof(line),others?"%d Dn 도착 · %s 외":"%d Dn 도착 · %s",d->money,partner_label(d->peer));else snprintf(line,sizeof(line),"%d Dn이 도착했습니다",d->money);
 draw_utf8(line,x+24,y+9,narrow?w-32:w-192,FONT_NORMAL_BLACK);
 if(!narrow){if(others)snprintf(line,sizeof(line),"보낸 도시: %s · 외 %d건",partner_label(d->peer),others);else snprintf(line,sizeof(line),"보낸 도시: %s",partner_label(d->peer));
 draw_utf8(line,x+24,y+31,w-192,FONT_SMALL_PLAIN);}
 const char*texts[]={"받기","거절"};int enabled=!mp_client_request_pending();
 for(int k=0;k<2;k++){int bx=x+w-164+k*80,by=y+31;large_label_draw_custom_size(bx,by,76,26);gift_center(texts[k],bx+4,by+7,68,enabled?FONT_NORMAL_BLACK:FONT_SMALL_PLAIN);}
}
static int cash_card_input(const mouse*m){
 int others,i=cash_card_find(&others),x,y,w;
 if(i<0 || !cash_card_rect(&x,&y,&w) || m->x<x || m->x>=x+w || m->y<y || m->y>=y+city_card_h())return 0;
 if(!m->left.went_up || mp_client_request_pending())return 1;
 for(int k=0;k<2;k++){
  int bx=x+w-164+k*80,by=y+31;
  if(m->x>=bx && m->x<bx+76 && m->y>=by && m->y<by+26){
   char cmd[96];snprintf(cmd,sizeof(cmd),"%s %llu",k?"reject":"accept",deal_rows[i].id);
   if(mp_client_command("trade",cmd)){cash_card_answered=deal_rows[i].id;cash_card_answered_at=time_get_millis();partner_read_at=0;}
  }
 }
 return 1;
}
static void city_notice_draw(void){
 city_notice_read();if(side_tab!=1)return;post_reminder_draw();cash_card_draw();
 char label[96];int width=city_notice_width(),top=city_notice_top(),left=city_notice_left();
 if(!city_notice_expanded()){
  int x=city_notice_fold_left();large_label_draw_custom_size(x,top-30,48,26);
  /* Reuse only the bell from the original problem-area button. */
  graphics_set_clip_rectangle(x+28,top-28,16,22);
  image_draw(image_group(GROUP_MESSAGE_ICON)+22,x+6,top-30,COLOR_MASK_NONE,SCALE_NONE);
  graphics_reset_clip_rectangle();
  snprintf(label,sizeof(label),"%d",city_notice_count);draw_utf8(label,x+9,top-22,18,FONT_NORMAL_BLACK);
  if(city_notice_preview()){
   large_label_draw_custom_size(left,top,width,48);
   draw_utf8(city_notices[city_notice_count-1].text,left+8,top+8,width-16,FONT_NORMAL_BLACK);
   draw_utf8("눌러서 확인",left+8,top+29,width-16,FONT_SMALL_PLAIN);
  }
  return;
 }
 if(side_tab!=1){large_label_draw_custom_size(left,top-30,width,28);draw_utf8(city_notice_log_mode?"지난 알림":"중요 알림",left+8,top-22,width-180,FONT_NORMAL_BLACK);
 button_border_draw(left+width-160,top-28,72,24,0);gift_center(city_notice_log_mode?"중요 알림":"지난 알림",left+width-156,top-21,64,FONT_NORMAL_BLACK);
 button_border_draw(left+width-80,top-28,72,24,0);gift_center("접기",left+width-76,top-21,64,FONT_NORMAL_BLACK);}
 if(city_notice_log_mode){
  city_notice_log_read();int h=city_notice_panel_height();
  large_label_draw_custom_size(left,top,width,h);graphics_draw_rect(left,top,width,h,0xffffcf70);
  if(!city_notice_log_count)draw_utf8("지난 알림이 없습니다.",left+12,top+12,width-24,FONT_NORMAL_BLACK);
  for(int row=0;row<city_notice_log_rows();row++){
   int i=city_notice_log_offset+row;if(i>=city_notice_log_count)break;
   city_notice_log_entry*e=&city_notice_log[i];time_t when=(time_t)e->when;struct tm*t=localtime(&when);char stamp[16]="--:--";
   if(t)snprintf(stamp,sizeof(stamp),"%02d:%02d",t->tm_hour,t->tm_min);
   int y=top+8+row*22;draw_utf8(stamp,left+10,y+4,44,FONT_SMALL_PLAIN);draw_utf8(e->text,left+58,y+3,width-68,FONT_NORMAL_BLACK);
  }
  if(side_tab!=1 && city_notice_log_count>CITY_NOTICE_LOG_ROWS){
   snprintf(label,sizeof(label),"%d-%d / %d · 휠로 이동",city_notice_log_offset+1,city_notice_log_offset+CITY_NOTICE_LOG_ROWS>city_notice_log_count?city_notice_log_count:city_notice_log_offset+CITY_NOTICE_LOG_ROWS,city_notice_log_count);
   draw_utf8(label,left+96,top-21,width-264,FONT_SMALL_PLAIN);
  }
  return;
 }
 for(int row=0;row<city_notice_visible();row++){
  city_notice*n=&city_notices[city_notice_count-1-city_notice_page-row];int y=top+row*64;
  if(time_get_millis()-n->resolved_at>=250){city_notice_resolve(n);n->resolved_at=time_get_millis();}int location=n->location;
  large_label_draw_custom_size(left,y,width,60);graphics_draw_rect(left,y,width,60,n->kind==6?0xffd03020:0xffffcf70);if(n->kind==6)graphics_draw_rect(left+1,y+1,width-2,58,0xffd03020);
  draw_utf8(n->text,left+8,y+8,width-16,FONT_NORMAL_BLACK);
  const char*text=location==7?"교역소 보기":location==6?"확인":location==5?"계약 확인":location==1?"위치 보기":location==2?"출발지 보기":location==3?"마지막 위치":location==4?"진입 지점":"위치 없음";
  if(location!=6 && width>=300)draw_utf8(location==7?"창고를 짓거나 보관 설정을 열어 교역소를 비워 주세요.":location==5?"상대 도시의 계약 화면을 엽니다.":location==1?"현재 도시의 대상 위치":location?"대상이 없으면 관련 지점을 표시합니다.":"현재 도시에서 대상을 찾을 수 없습니다.",left+8,y+36,width-136,FONT_SMALL_PLAIN);
  button_border_draw(left+width-120,y+29,112,26,0);gift_center(text,left+width-116,y+36,104,location?FONT_NORMAL_BLACK:FONT_SMALL_PLAIN);
 }
}
static int city_notice_input(const mouse*m){
 if(post_reminder_input(m))return 1;
 if(cash_card_input(m))return 1;
 if(!city_notice_expanded()){
 if(city_notice_preview() && m->x>=city_notice_left() && m->x<city_notice_right() && m->y>=city_notice_top() && m->y<city_notice_top()+48){if(m->left.went_up)city_notice_action(2,0);return 1;}
 if(m->x>=city_notice_fold_left() && m->x<city_notice_fold_left()+48 && m->y>=city_notice_top()-30 && m->y<city_notice_top()-4){if(m->left.went_up)city_notice_action(2,0);return 1;}return 0;
 }
 int top=city_notice_top(),width=city_notice_width(),left=city_notice_left();
 if(m->x<left || m->x>=left+width || m->y<top-30 || m->y>=top+city_notice_panel_height())return 0;
 if(side_tab!=1 && city_notice_log_mode && m->scrolled!=SCROLL_NONE){
  city_notice_log_offset+=m->scrolled==SCROLL_DOWN?3:-3;
  if(city_notice_log_offset>city_notice_log_count-CITY_NOTICE_LOG_ROWS)city_notice_log_offset=city_notice_log_count-CITY_NOTICE_LOG_ROWS;
  if(city_notice_log_offset<0)city_notice_log_offset=0;return 1;
 }
 if(side_tab!=1 && !city_notice_log_mode && m->scrolled!=SCROLL_NONE && city_notice_count>3){
  city_notice_page+=m->scrolled==SCROLL_DOWN?3:-3;if(city_notice_page>=city_notice_count)city_notice_page=0;if(city_notice_page<0)city_notice_page=0;return 1;
 }
 if(m->left.went_up){
  if(m->y<top){if(side_tab==1)return 1;if(m->x>=left+width-80)city_notice_action(0,0);else if(m->x>=left+width-160)city_notice_action(3,0);}
  else if(!city_notice_log_mode){int row=(m->y-top)/64;if(m->x>=left+width-120 && (m->y-top)%64>=29)city_notice_action(1,row);}
 }
 return 1;
}
