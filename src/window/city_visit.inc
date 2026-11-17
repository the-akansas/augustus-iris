/* Isolated live state viewer. Included by city.c to reuse the game's rendering. */
#include "multiplayer/visit.h"
#include "multiplayer/observe_channel.h"
#include "game/file_io.h"
#include "core/encoding.h"
#include "core/lang.h"
#include "core/time.h"
#include "game/system.h"
#include "widget/minimap.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static char visit_file[96],visit_name[512],visit_saved[512],visit_received[512];
static int visit_building;
static unsigned int visit_polled;
static void visit_show(void);
static void visit_text(const char *s,int x,int y,int width){
 uint8_t b[2048];encoding_from_utf8(s,b,sizeof(b));text_draw_ellipsized(b,x,y,width,FONT_NORMAL_WHITE,0);
}
static void visit_line(FILE *f,char *b,int size){if(!fgets(b,size,f)){b[0]=0;return;}b[strcspn(b,"\r\n")]=0;}
static obs_channel visit_state,visit_frames,visit_ui_frames;
static uint64_t visit_state_sequence;
void city_figure_view_clear_next(void);
void city_figure_view_capture_next(ULONGLONG start,ULONGLONG end);
/* Playout buffer. Snapshots arrive in bursts over a slow link (one every
 * 0.4-1.5s at a 400ms ping), so a fixed 600ms delay ran dry and the city froze
 * then jumped. Each snapshot is scheduled by its game tick at the observed tick
 * rate (constant on-screen speed), and the delay adapts to the arrival gaps. */
#define VISIT_DELAY_MS 600
#define VISIT_DELAY_MAX_MS 3500
static double visit_gap_ms=600,visit_tick_ms=40;
static ULONGLONG visit_last_arrival,visit_last_due;
static uint64_t visit_last_ticks;
static ULONGLONG visit_schedule(ULONGLONG now,uint64_t ticks){
 if(visit_last_arrival && ticks>visit_last_ticks){
  double gap=(double)(now-visit_last_arrival);
  visit_gap_ms=visit_gap_ms*0.8+gap*0.2;
  double rate=gap/(double)(ticks-visit_last_ticks);if(rate>1 && rate<2000)visit_tick_ms=visit_tick_ms*0.8+rate*0.2;
 }
 double target=visit_gap_ms*2+300;if(target<VISIT_DELAY_MS)target=VISIT_DELAY_MS;if(target>VISIT_DELAY_MAX_MS)target=VISIT_DELAY_MAX_MS;
 ULONGLONG ideal=now+(ULONGLONG)target,due;
 if(!visit_last_due || ticks<=visit_last_ticks)due=ideal;
 else{
  due=visit_last_due+(ULONGLONG)((double)(ticks-visit_last_ticks)*visit_tick_ms);
  /* Drift slowly toward the target delay; resync only when far off. */
  long long drift=(long long)ideal-(long long)due;due+=drift/8;
  if(due<now+VISIT_DELAY_MS/2 || due>now+VISIT_DELAY_MAX_MS+1000)due=ideal;
 }
 if(due<=visit_last_due)due=visit_last_due+1;
 visit_last_arrival=now;visit_last_ticks=ticks;visit_last_due=due;return due;
}
#define VISIT_QUEUE_CAP 8
struct visit_snapshot {unsigned char *data;unsigned length;uint64_t seq,ticks;ULONGLONG due;};
static struct visit_snapshot visit_queue[VISIT_QUEUE_CAP],visit_current;
static unsigned visit_queue_count;
static uint64_t visit_received_sequence,visit_prepared_current,visit_prepared_next;

int window_city_visit_load(void){
 const char *dir=getenv("AUGUSTUS_CITY_VISIT");if(!dir || !*dir)return 0;
 char path[2048];
 if(!visit_file[0]){
  snprintf(path,sizeof(path),"%s/visit-meta.txt",dir);FILE *f=fopen(path,"rb");if(!f)return 0;
  visit_line(f,visit_file,sizeof(visit_file));visit_line(f,visit_name,sizeof(visit_name));fclose(f);
  if(strcmp(visit_file,"initial.sav")){visit_file[0]=0;return 0;}
  snprintf(path,sizeof(path),"%s/initial.sav",dir);
  if(game_file_load_saved_game(path)!=FILE_LOAD_SUCCESS){visit_file[0]=0;return 0;}
  building_construction_clear_type();formation_set_selected(0);game_state_set_overlay(OVERLAY_NONE);
  if(city_view_is_sidebar_collapsed())city_view_toggle_sidebar();visit_show();
 }
 ULONGLONG now=GetTickCount64();
 if(obs_open(&visit_state,dir,"view-state",OBS_CAP)){
  uint64_t seq,ticks;unsigned length;unsigned char *packet=obs_read(&visit_state,&length,&seq,&ticks);
  if(packet){
   if(seq>visit_received_sequence){
    visit_received_sequence=seq;
    if(visit_queue_count==VISIT_QUEUE_CAP){free(visit_queue[0].data);memmove(visit_queue,visit_queue+1,(--visit_queue_count)*sizeof(*visit_queue));}
    visit_queue[visit_queue_count++]=(struct visit_snapshot){packet,length,seq,ticks,visit_schedule(now,ticks)};packet=0;
   }free(packet);
  }
 }
 while(visit_queue_count && visit_queue[0].due<=now){
  free(visit_current.data);visit_current=visit_queue[0];
  memmove(visit_queue,visit_queue+1,(--visit_queue_count)*sizeof(*visit_queue));
 }
 uint64_t next=visit_queue_count?visit_queue[0].seq:0;
 if(visit_current.data && (visit_current.seq!=visit_prepared_current || next!=visit_prepared_next)){
  int cx,cy,scale=city_view_get_scale();city_view_get_camera_absolute(&cx,&cy);
  city_figure_view_clear_next();
  if(next){
   struct visit_snapshot *future=&visit_queue[0];
   if(!game_file_io_apply_view(future->data,future->length))return 0;
   ULONGLONG start=visit_current.due;
   /* If the buffer ran dry, resume from the held position, not mid-segment. */
   if(visit_prepared_current==visit_current.seq && !visit_prepared_next && start<now)start=now;
   city_figure_view_capture_next(start,future->due);
  }
  if(!game_file_io_apply_view(visit_current.data,visit_current.length))return 0;
  city_view_restore_lookup(); /* tiles drawn follow the watched city's images, not those of initial.sav (2026-11-14) */
  city_view_set_scale(scale);city_view_set_camera_absolute(cx,cy);
  visit_prepared_current=visit_state_sequence=visit_current.seq;visit_prepared_next=next;
  widget_minimap_invalidate(); /* the watched city's minimap follows each applied state */
  snprintf(visit_saved,sizeof(visit_saved),"진행 %llu틱",(unsigned long long)visit_current.ticks);
  snprintf(visit_received,sizeof(visit_received),"관전 지연 재생 · 게임은 방장 속도 유지");
  snprintf(path,sizeof(path),"%s/view-applied.txt",dir);FILE *f=fopen(path,"wb");if(f){fprintf(f,"%llu %llu",(unsigned long long)visit_current.seq,(unsigned long long)visit_current.ticks);fclose(f);}
 }

 return 1;
}
/* Minimap box in the right column (screen_width()-152 .. -8), below the 76 px header. */
#define VISIT_MAP_X (screen_width()-149)
#define VISIT_MAP_Y 84
#define VISIT_MAP_W 146
#define VISIT_MAP_H 111
static void visit_background(void){graphics_clear_screen();}
static void visit_draw(void){
 if(time_get_millis()-visit_polled>80){visit_polled=time_get_millis();window_city_visit_load();}
 widget_city_draw();
 int vx,vy,vw,vh;city_view_get_viewport(&vx,&vy,&vw,&vh);
 int x=screen_width()-152,w=144;
 graphics_fill_rect(0,0,screen_width(),76,COLOR_BLACK);
 graphics_fill_rect(x-8,76,160,screen_height()-76,COLOR_BLACK);
 visit_text("도시 둘러보기 / 읽기 전용",12,6,screen_width()-24);
 visit_text(visit_name,12,28,screen_width()-24);
 char line[1100];snprintf(line,sizeof(line),"%s / %s",visit_saved,visit_received);visit_text(line,12,50,screen_width()-24);
 /* The watched city's minimap, like the original sidebar: shows where the view is; click to jump. */
 widget_minimap_draw_decorated(VISIT_MAP_X,VISIT_MAP_Y,VISIT_MAP_W,VISIT_MAP_H);
 int ty=VISIT_MAP_Y+VISIT_MAP_H+12;
 visit_text("내 도시는 계속",x,ty,w);visit_text("진행되고 있습니다.",x,ty+20,w);
 visit_text("미니맵 클릭: 그곳으로",x,ty+50,w);visit_text("휠: 확대 / 축소",x,ty+70,w);visit_text("우클릭/휠 클릭: 이동",x,ty+90,w);visit_text("건물 클릭: 정보",x,ty+110,w);
 if(visit_building>0 && (unsigned)visit_building<building_count()){
  building *b=building_main(building_get(visit_building));
  text_draw_ellipsized(lang_get_building_type_string(b->type),x,ty+145,w,FONT_NORMAL_WHITE,0);
  snprintf(line,sizeof(line),"고용 인원: %d",b->num_workers);visit_text(line,x,ty+170,w);
  snprintf(line,sizeof(line),"거주 인구: %d",b->house_population);visit_text(line,x,ty+190,w);
  visit_text(b->has_road_access?"도로 연결됨":"도로 연결 없음",x,ty+210,w);
 }
 char path[2048],status[1024]={0};snprintf(path,sizeof(path),"%s/visit-status.txt",getenv("AUGUSTUS_CITY_VISIT"));FILE *f=fopen(path,"rb");if(f){fread(status,1,sizeof(status)-1,f);fclose(f);}
 graphics_fill_rect(0,screen_height()-30,x-8,30,COLOR_BLACK);visit_text(status,12,screen_height()-24,x-32);
 large_label_draw_custom_size(x,screen_height()-90,w,28);visit_text("연결 상태 새로고침",x+6,screen_height()-84,w-12);
 large_label_draw_custom_size(x,screen_height()-52,w,28);visit_text("내 도시로 돌아가기",x+6,screen_height()-46,w-12);
}
static void visit_handle(const mouse *m,const hotkeys *h){
 int x=screen_width()-152;
 if(h->close_pressed){system_exit();return;}
 if(m->x>=x && m->left.went_up){
  if(m->y>=screen_height()-52 && m->y<screen_height()-24){system_exit();return;}
  if(m->y>=screen_height()-90 && m->y<screen_height()-62){
   char p[2048];snprintf(p,sizeof(p),"%s/visit-refresh.txt",getenv("AUGUSTUS_CITY_VISIT"));FILE *f=fopen(p,"wb");if(f){fputs("refresh\n",f);fclose(f);}return;
  }
 }
 if((m->y<76 || m->y>=screen_height()-30 || m->x>=x-8) && !m->middle.is_down && !m->middle.went_up)return;
 hotkeys camera={0};camera.zoom_in=h->zoom_in;camera.zoom_out=h->zoom_out;camera.reset_zoom=h->reset_zoom;int offset=widget_city_visit_input(m,&camera);
 if(offset>0){int id=map_building_at(offset);visit_building=id>0?building_main(building_get(id))->id:0;}
}
static void visit_show(void){window_type w={WINDOW_CITY,visit_background,visit_draw,visit_handle,0};window_show(&w);}
/* Headless, semantic camera requests; no window input or input injection. */
#include "platform/renderer.h"
#include "graphics/renderer.h"
static unsigned visit_worker_sequence,visit_request_sequence;
static int visit_origin_x,visit_origin_y,visit_origin_set;
int window_city_visit_worker_step(void){
 const char *dir=getenv("AUGUSTUS_CITY_VISIT");if(!dir)return 0;
 char path[2048];snprintf(path,sizeof(path),"%s/render-request.txt",dir);
 FILE *f=fopen(path,"rb");if(!f)return 1;
 unsigned seq;int w,h,px,py,zoom,clickx,clicky,mapx=-1,mapy=-1;
 int fields=fscanf(f,"%u %d %d %d %d %d %d %d %d %d",&seq,&w,&h,&px,&py,&zoom,&clickx,&clicky,&mapx,&mapy);fclose(f);
 if((fields!=8 && fields!=10) || !seq || seq==visit_worker_sequence || w<640 || h<480 || w>4096 || h>4096 || (long long)w*h>9000000 || px< -100000 || px>100000 || py< -100000 || py>100000 || zoom<50 || zoom>500)return 1;
 if(!window_city_visit_load())return 0;
 if(w!=screen_width() || h!=screen_height()){
  screen_set_resolution(w,h);if(!platform_renderer_create_render_texture(w,h))return 0;
 }
 if(!visit_origin_set){city_view_get_camera_in_pixels(&visit_origin_x,&visit_origin_y);visit_origin_set=1;}
 city_view_set_scale(zoom);city_view_set_camera_from_pixel_position(visit_origin_x+px,visit_origin_y+py);
 if(mapx>=0 && mapy>=0){
  /* Minimap click: move this view there and tell the viewer its new camera offset. */
  mouse click={0};click.x=mapx;click.y=mapy;click.left.went_down=1;
  if(widget_minimap_handle_mouse(&click)){
   int cx,cy;city_view_get_camera_in_pixels(&cx,&cy);
   char cpath[2048];snprintf(cpath,sizeof(cpath),"%s/camera-offset.txt",dir);FILE *c=fopen(cpath,"wb");
   if(c){fprintf(c,"%u %d %d\n",seq,cx-visit_origin_x,cy-visit_origin_y);fclose(c);}
  }
 }
 if(clickx>=0 && clicky>=76 && clickx<w-160 && clicky<h-30){
  view_tile tile;if(city_view_pixels_to_view_tile(clickx,clicky,&tile)){
   int offset=city_view_tile_to_grid_offset(&tile);visit_building=offset>0?map_building_at(offset):0;
  }
 }
 graphics_clear_screen();visit_draw();
 color_t *pixels=malloc((size_t)w*h*sizeof(color_t));if(!pixels)return 0;
 if(!graphics_renderer()->save_screen_buffer(pixels,0,0,w,h,w)){free(pixels);return 0;}
 if(!obs_open(&visit_frames,dir,"view-frame",OBS_FRAME_CAP)){free(pixels);return 1;}
 unsigned length=12+(unsigned)w*h*4;unsigned char *packet=malloc(length);if(!packet){free(pixels);return 0;}
 unsigned header[3]={0x33565741,(unsigned)w,(unsigned)h};memcpy(packet,header,12);memcpy(packet+12,pixels,length-12);
 obs_write(&visit_frames,packet,length,seq,visit_state_sequence);free(packet);free(pixels);
 visit_worker_sequence=seq;return 1;
}
/* Main-process presentation only. Own city memory, clock and save path stay intact. */
static struct {
 int active,px,py,zoom,clickx,clicky,mapx,mapy,dragx,dragy,dragging,dirty,w,h,has_frame;
 unsigned seq,pending,polled,requested;
 char directory[2048];
} visit_ui;
int window_city_visit_ui_active(void){return visit_ui.active;}
/* Opened from the 관전 screen (multiplayer_spectate.inc, Korean edition): there is no city of one's own, Esc goes back
 * to that screen. */
static int visit_spectator;
void window_city_visit_set_spectator(int on){visit_spectator=on;}
void window_city_visit_ui_hide(void){if(visit_ui.active){visit_ui.active=0;obs_close(&visit_ui_frames);mp_client_command("network-visit-close","");}}
static void visit_ui_close(void){
 visit_ui.active=0;obs_close(&visit_ui_frames);mp_client_command("network-visit-close","");
 if(visit_spectator && window_multiplayer_spectating())window_empire_show();   /* back to the spectator's empire map */
 else if(visit_spectator)window_multiplayer_lobby_show();else window_city_show();
}
static void visit_ui_request(void){
 if(!visit_ui.directory[0] || visit_ui.pending)return;
 unsigned now=time_get_millis();if(now-visit_ui.requested<33)return;

 char path[2300];snprintf(path,sizeof(path),"%s/render-request.txt",visit_ui.directory);
 FILE *f=fopen(path,"wb");if(!f)return;
 visit_request_sequence++;if(!visit_request_sequence)visit_request_sequence=1;
 visit_ui.seq=visit_ui.pending=visit_request_sequence;
 fprintf(f,"%u %d %d %d %d %d %d %d %d %d\n",visit_ui.seq,screen_width(),screen_height(),visit_ui.px,visit_ui.py,visit_ui.zoom,visit_ui.clickx,visit_ui.clicky,visit_ui.mapx,visit_ui.mapy);fclose(f);
 visit_ui.clickx=visit_ui.clicky=visit_ui.mapx=visit_ui.mapy=-1;visit_ui.dirty=0;visit_ui.requested=now;
}
static void visit_ui_poll(void){
 const char *bridge=getenv("AUGUSTUS_MP_BRIDGE");if(!bridge)return;
 char path[2300];
 snprintf(path,sizeof(path),"%s/visit-denied.txt",bridge);
 FILE *denied=fopen(path,"rb");
 if(denied){int revoked=fgetc(denied)=='1';fclose(denied);if(revoked){visit_ui.has_frame=0;visit_ui_close();return;}}
 if(!visit_ui.directory[0]){
  snprintf(path,sizeof(path),"%s/visit-ready.txt",bridge);FILE *f=fopen(path,"rb");if(f){visit_line(f,visit_ui.directory,sizeof(visit_ui.directory));fclose(f);}
 }
 if(visit_ui.pending && visit_ui.directory[0]){
  if(obs_open(&visit_ui_frames,visit_ui.directory,"view-frame",OBS_FRAME_CAP)){
   unsigned length;uint64_t seq,ticks;unsigned char *packet=obs_read(&visit_ui_frames,&length,&seq,&ticks);
   if(packet){
    unsigned h[3];if(length>=12)memcpy(h,packet,12);else memset(h,0,sizeof(h));
    if(seq==visit_ui.pending && h[0]==0x33565741 && h[1]>=640 && h[1]<=4096 && h[2]>=480 && h[2]<=4096 && (uint64_t)h[1]*h[2]<=9000000 && length==12+(uint64_t)h[1]*h[2]*4){
     int w=h[1],height=h[2];
     if(!visit_ui.has_frame || visit_ui.w!=w || visit_ui.h!=height)graphics_renderer()->create_custom_image(CUSTOM_IMAGE_CITY_VISIT,w,height,0);
     graphics_renderer()->update_custom_image_from(CUSTOM_IMAGE_CITY_VISIT,(color_t *)(packet+12),0,0,w,height);
     /* A minimap jump moved the worker's camera: adopt its offset so dragging continues from there. */
     char cpath[2300];snprintf(cpath,sizeof(cpath),"%s/camera-offset.txt",visit_ui.directory);FILE *c=fopen(cpath,"rb");
     if(c){unsigned cs;int cx,cy;if(fscanf(c,"%u %d %d",&cs,&cx,&cy)==3 && cs==visit_ui.pending){visit_ui.px=cx;visit_ui.py=cy;}fclose(c);}
     visit_ui.w=w;visit_ui.h=height;visit_ui.has_frame=1;visit_ui.pending=0;
    }free(packet);
   }
  }
  if(visit_ui.pending && time_get_millis()-visit_ui.requested>2000)visit_ui.pending=0;

 }
 visit_ui_request();
}
static void visit_ui_draw(void){
 visit_ui_poll();if(!visit_ui.active)return;graphics_clear_screen();
 if(visit_ui.has_frame)graphics_renderer()->draw_custom_image(CUSTOM_IMAGE_CITY_VISIT,0,0,1,1);
 else{visit_text("도시 둘러보기를 준비하고 있습니다.",20,30,screen_width()-40);visit_text(visit_spectator?"Esc: 관전 화면으로 돌아가기":"내 도시는 계속 진행됩니다. Esc: 내 도시로 돌아가기",20,55,screen_width()-40);}
 /* Error/status is drawn locally even if the renderer cannot produce a frame. */
 const char *bridge=getenv("AUGUSTUS_MP_BRIDGE");char path[2300],status[1024]={0};
 if(bridge){snprintf(path,sizeof(path),"%s/visit-status.txt",bridge);FILE *f=fopen(path,"rb");if(f){visit_line(f,status,sizeof(status));fclose(f);}}
 if(!visit_ui.has_frame || strstr(status,"종료") || strstr(status,"못했")){
  graphics_fill_rect(0,screen_height()-30,screen_width(),30,COLOR_BLACK);visit_text(status,12,screen_height()-24,screen_width()-24);
 }
 if(screen_width()!=visit_ui.w || screen_height()!=visit_ui.h)visit_ui.dirty=1;
}
static void visit_ui_handle(const mouse *m,const hotkeys *h){
 if(h->close_pressed){visit_ui_close();return;}
 int x=screen_width()-152;
 if(m->left.went_up && m->x>=x){
  if(m->y>=screen_height()-52 && m->y<screen_height()-24){visit_ui_close();return;}
  if(m->y>=screen_height()-90 && m->y<screen_height()-62 && visit_ui.directory[0]){
   char p[2300];snprintf(p,sizeof(p),"%s/visit-refresh.txt",visit_ui.directory);FILE *f=fopen(p,"wb");if(f){fputs("refresh",f);fclose(f);}visit_ui.dirty=1;return;
  }
 }
 if(m->left.went_down && m->x>=VISIT_MAP_X && m->x<VISIT_MAP_X+VISIT_MAP_W && m->y>=VISIT_MAP_Y && m->y<VISIT_MAP_Y+VISIT_MAP_H){visit_ui.mapx=m->x;visit_ui.mapy=m->y;visit_ui.dirty=1;return;}
 int inside=m->x<x-8 && m->y>=76 && m->y<screen_height()-30;
 if(inside && (h->zoom_in || h->zoom_out || m->scrolled)){
  visit_ui.zoom+=(h->zoom_in || m->scrolled==SCROLL_UP)?-10:10;
  if(visit_ui.zoom<50)visit_ui.zoom=50;if(visit_ui.zoom>500)visit_ui.zoom=500;visit_ui.dirty=1;
 }
 if(!visit_ui.dragging && inside && (m->middle.went_down || m->right.went_down)){visit_ui.dragging=m->right.went_down?2:1;visit_ui.dragx=m->x;visit_ui.dragy=m->y;}
 int held=visit_ui.dragging==2?m->right.is_down:m->middle.is_down;
 if(visit_ui.dragging && held){
  visit_ui.px+=(visit_ui.dragx-m->x)*visit_ui.zoom/100;visit_ui.py+=(visit_ui.dragy-m->y)*visit_ui.zoom/100;
  visit_ui.dragx=m->x;visit_ui.dragy=m->y;visit_ui.dirty=1;
 }
 if(!held || !m->window_has_focus)visit_ui.dragging=0;
 if(inside && m->left.went_up){visit_ui.clickx=m->x;visit_ui.clicky=m->y;visit_ui.dirty=1;}
}
void window_city_visit_show(int name_id){
 const char *bridge=getenv("AUGUSTUS_MP_BRIDGE");if(!bridge)return;
 obs_close(&visit_ui_frames);memset(&visit_ui,0,sizeof(visit_ui));visit_ui.zoom=100;visit_ui.clickx=visit_ui.clicky=visit_ui.mapx=visit_ui.mapy=-1;visit_ui.dirty=1;
 char path[2300];snprintf(path,sizeof(path),"%s/visit-ready.txt",bridge);remove(path);
 snprintf(path,sizeof(path),"%s/visit-status.txt",bridge);remove(path);
 snprintf(path,sizeof(path),"%s/visit-denied.txt",bridge);remove(path);
 char target[32];snprintf(target,sizeof(target),"%d",name_id);mp_client_command("network-visit-city",target);
 window_type w={WINDOW_CITY,visit_background,visit_ui_draw,visit_ui_handle,0};window_show(&w);visit_ui.active=1;
}
