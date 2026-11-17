#include "platform/windows_paths.h"
#include "clock.h"
#include "post_runtime.h"
#include "chat.h"
#include "graphics/window.h"
#include "window/city.h"
#include "input/keyboard.h"
#include "transport.h"
#include "core/time.h"
#include "game/time.h"
#include "game/file.h"
#include "city/population.h"
#include "city/ratings.h"
#include "city/finance.h"
#include "window/multiplayer_lobby.h"
#include "game/settings.h"
#include "scenario/property.h"
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <SDL.h>
#ifdef _WIN32
#include <windows.h>
#endif
#include "army_install_native.h"
static char army_expected[65];
static int active, speed=80, trade_busy;
static uint64_t installed_trade;
int mp_clock_trade_busy(void){return trade_busy;}
static uint64_t completed, serial, grant, seen, report, captured, capture_id, next_tick;
/* Aggregate durations only; no city content, names or chat. One native writer. */
enum { CLOCK_RUNNING, CLOCK_NO_GRANT, CLOCK_STALE, CLOCK_PAUSED, CLOCK_BARRIER, CLOCK_PACING, CLOCK_REASONS };
static uint64_t metric_ms[CLOCK_REASONS], metric_seen, metric_published, metric_sim_us, metric_sim_start;
static int metric_reason;
#ifndef MP_RESPONSE_GRACE_MS
#define MP_RESPONSE_GRACE_MS 5000
#endif
/* Tick spacing, separate from render FPS. Reset per city; aggregate only. */
static uint64_t spacing_last, spacing_max, spacing_over100, spacing_over250;

static int metric_return(uint64_t now, int reason, int budget) {
 if(metric_seen && now>=metric_seen)metric_ms[metric_reason]+=now-metric_seen;
 metric_seen=now;metric_reason=reason;
 if(budget)metric_sim_start=SDL_GetPerformanceCounter();
 return budget;
}
static void metric_publish(const char *dir, uint64_t now) {
 if(now-metric_published<2000)return;
 metric_published=now;
 char path[2048],tmp[2048];snprintf(tmp,sizeof(tmp),"%s/clock-metrics.tmp",dir);
 FILE *f=fopen(tmp,"wb");if(!f)return;
 fprintf(f,"%llu %llu %llu %llu %llu %llu %llu %llu %llu %llu",
  (unsigned long long)now,(unsigned long long)completed,(unsigned long long)grant,
  (unsigned long long)metric_ms[CLOCK_RUNNING],(unsigned long long)metric_ms[CLOCK_NO_GRANT],
  (unsigned long long)metric_ms[CLOCK_STALE],(unsigned long long)metric_ms[CLOCK_PAUSED],
  (unsigned long long)metric_ms[CLOCK_BARRIER],(unsigned long long)metric_ms[CLOCK_PACING],
  (unsigned long long)metric_sim_us);
 fprintf(f," %llu %llu %llu",(unsigned long long)spacing_max,(unsigned long long)spacing_over100,(unsigned long long)spacing_over250);
 if(fclose(f))return;
 snprintf(path,sizeof(path),"%s/clock-metrics.txt",dir);
#ifdef _WIN32
 augustus_move_file(tmp,path,MOVEFILE_REPLACE_EXISTING);
#else
 rename(tmp,path);
#endif
}
static uint64_t objective_reported=UINT64_MAX;
static char objective_request[65];
static void report_objective(const char *dir){
 if(trade_busy || capture_id)return;
 char path[2048],tmp[2048],request[65]={0};unsigned long long requested;
 snprintf(path,sizeof(path),"%s/objective-snapshot.txt",dir);FILE *f=fopen(path,"rb");
 if(!f)return;int valid=fscanf(f,"%llu %64s",&requested,request)==2;fclose(f);
 if(strlen(request)!=64 || strspn(request,"0123456789abcdef")!=64)return;
 if(!valid || requested>=9007199254740992ULL || requested!=completed || (requested==objective_reported && !strcmp(request,objective_request)))return;
 snprintf(tmp,sizeof(tmp),"%s/objective-stats.tmp",dir);f=fopen(tmp,"wb");if(!f)return;
 fprintf(f,"{\"ticks\":%llu,\"request\":\"%s\",\"stats\":{\"population\":%d,\"culture\":%d,\"prosperity\":%d,\"peace\":%d,\"favor\":%d,\"treasury\":%d}}",requested,request,city_population(),city_rating_culture(),city_rating_prosperity(),city_rating_peace(),city_rating_favor(),city_finance_treasury());
 if(fclose(f))return;
 snprintf(path,sizeof(path),"%s/objective-stats.json",dir);
#ifdef _WIN32
 if(augustus_move_file(tmp,path,MOVEFILE_REPLACE_EXISTING)){objective_reported=requested;strcpy(objective_request,request);}
#else
 if(!rename(tmp,path)){objective_reported=requested;strcpy(objective_request,request);}
#endif
}
static int interval(void){static const int ms[]={702,502,352,242,162,112,82,57,37,22,16};return ms[speed/10];}
/* Soft edge: when the approved look-ahead runs low (a late grant over a slow
 * link), stretch the tick spacing gradually instead of stopping dead at the
 * grant. Up to twice the spacing in the last 1.5s of credit; a fresh grant
 * restores full speed. Never runs faster than the host's speed. */
#define MP_CLOCK_SOFT_EDGE_MS 1500
static int paced_interval(void){
 int base=interval();uint64_t left=grant>completed?grant-completed:0;uint64_t left_ms=left*(uint64_t)base;
 if(left_ms>=MP_CLOCK_SOFT_EDGE_MS)return base;
 return base+(int)((MP_CLOCK_SOFT_EDGE_MS-left_ms)*(uint64_t)base/MP_CLOCK_SOFT_EDGE_MS);
}
int mp_clock_active(void){return active;}
int mp_clock_speed(void){return speed;}
unsigned long long mp_clock_completed(void){return completed;}
void mp_clock_start(void){
 mp_post_runtime_reset();
 memset(metric_ms,0,sizeof(metric_ms));metric_seen=metric_published=metric_sim_us=metric_sim_start=0;metric_reason=CLOCK_NO_GRANT;spacing_last=spacing_max=spacing_over100=spacing_over250=0;
 army_install_reset();army_expected[0]=0;
 objective_reported=UINT64_MAX;objective_request[0]=0;
 mp_transport_reset();
 mp_chat_reload();trade_busy=0;installed_trade=0;active=1;completed=serial=grant=seen=report=captured=capture_id=next_tick=0;speed=80;
 const char *dir=getenv("AUGUSTUS_MP_BRIDGE");char path[2048];
 if(dir){snprintf(path,sizeof(path),"%s/origin.txt",dir);FILE *f=fopen(path,"rb");
  if(f){unsigned long long origin;if(fscanf(f,"%llu",&origin)==1 && origin<9007199254740992ULL)completed=grant=origin;fclose(f);}
 }
}
void mp_clock_stop(void){active=0;}
void mp_clock_did_tick(void){if(active){
 completed++;uint64_t now=time_get_millis();
 if(spacing_last){uint64_t gap=now-spacing_last;if(gap>spacing_max)spacing_max=gap;if(gap>100)spacing_over100++;if(gap>250)spacing_over250++;}spacing_last=now;
 uint64_t metric_end=SDL_GetPerformanceCounter(),frequency=SDL_GetPerformanceFrequency();
 if(metric_sim_start && frequency && metric_end>=metric_sim_start)metric_sim_us+=(metric_end-metric_sim_start)*1000000/frequency;
 metric_sim_start=0;
 next_tick+=paced_interval();if(next_tick<=now)next_tick=now+paced_interval();
}}
/* A save loaded during play (trade install, army) comes from the room without a player name: keep the waiting room
   name (set on entry, multiplayer_lobby.c) so the advisors' title and letters are never blank. */
static void keep_player_name(void){if(!scenario_player_name()[0] && setting_player_name()[0])scenario_set_player_name(setting_player_name());}
static int army_load_saved(const char *path){
 if(!window_is(WINDOW_CITY) && !window_is(WINDOW_CITY_MILITARY)){keyboard_stop_capture();window_city_show();}
 active=0;int loaded=game_file_load_saved_game(path);active=1;
 if(loaded==FILE_LOAD_SUCCESS){keep_player_name();mp_transport_reset();mp_chat_reload();return 1;}return 0;
}
int mp_clock_budget(void){
 const char *dir=getenv("AUGUSTUS_MP_BRIDGE");if(!active || !dir)return 0;
 uint64_t now=time_get_millis();char path[2048],tmp[2048];
 int post_poll_due=!report || now-report>=50;
 if(!report || now-report>=50){
  snprintf(path,sizeof(path),"%s/engine.txt",dir);snprintf(tmp,sizeof(tmp),"%s/engine.tmp",dir);
  FILE *f=fopen(tmp,"wb");if(f){fprintf(f,"%llu",(unsigned long long)completed);if(!fclose(f)){
#ifdef _WIN32
   augustus_move_file(tmp,path,MOVEFILE_REPLACE_EXISTING);
#else
   rename(tmp,path);
#endif
  }}
  snprintf(path,sizeof(path),"%s/calendar.txt",dir);snprintf(tmp,sizeof(tmp),"%s/calendar.tmp",dir);
  f=fopen(tmp,"wb");if(f){fprintf(f,"%d %d %d %d",game_time_year(),game_time_month(),game_time_day(),game_time_tick());if(!fclose(f)){
#ifdef _WIN32
   augustus_move_file(tmp,path,MOVEFILE_REPLACE_EXISTING);
#else
   rename(tmp,path);
#endif
  }}report=now;
 mp_transport_poll();mp_chat_poll();
 }
 snprintf(path,sizeof(path),"%s/clock.txt",dir);FILE *f=fopen(path,"rb");
 if(f){unsigned long long seq,g,id=0;int s,busy=0;char army[65]={0};
  if(fscanf(f,"%llu %llu %d %llu %d %64s",&seq,&g,&s,&id,&busy,army)>=3 && seq>serial && g>=completed && g-completed<=MP_CLOCK_CREDIT_TICKS && s>=0 && s<=100){
   if(speed!=s)next_tick=now;
   /* The city stays visible while the transactional snapshot is installed. */
   strcpy(army_expected,army);trade_busy=busy;serial=seq;grant=g;speed=s;seen=now;capture_id=id;
  }fclose(f);
 }
 if(post_poll_due && !capture_id && !trade_busy && (!army_expected[0] || !strcmp(army_expected,"-")))mp_post_runtime_poll(dir);
 if(serial && now-seen<=1000 && capture_id && completed==grant && captured!=capture_id){
  snprintf(path,sizeof(path),"%s/capture-%llu.sav",dir,(unsigned long long)capture_id);
  if(game_file_write_saved_game(path)){
   snprintf(tmp,sizeof(tmp),"%s/capture.tmp",dir);FILE *ack=fopen(tmp,"wb");
   if(ack){fprintf(ack,"%llu %llu",(unsigned long long)capture_id,(unsigned long long)completed);
    if(!fclose(ack)){
     snprintf(path,sizeof(path),"%s/capture.txt",dir);
#ifdef _WIN32
     if(augustus_move_file(tmp,path,MOVEFILE_REPLACE_EXISTING))captured=capture_id;
#else
     if(!rename(tmp,path))captured=capture_id;
#endif
    }
   }
  }
 }
 if(trade_busy && completed==grant && (!army_expected[0] || !strcmp(army_expected,"-"))){
  snprintf(path,sizeof(path),"%s/trade-install.txt",dir);FILE *request=fopen(path,"rb");
  unsigned long long id=0,tick=0;
  if(request){int count=fscanf(request,"%llu %llu",&id,&tick);fclose(request);
   if(count==2 && id>installed_trade && tick==completed){
    snprintf(path,sizeof(path),"%s/trade-install-%llu.sav",dir,id);
    if(!window_is(WINDOW_CITY) && !window_is(WINDOW_CITY_MILITARY)){keyboard_stop_capture();window_city_show();}
    active=0;int loaded=game_file_load_saved_game(path);active=1;
    if(loaded==FILE_LOAD_SUCCESS){keep_player_name();installed_trade=id;mp_transport_reset();mp_chat_reload();}
   }
   if(count==2 && id && id==installed_trade){
    snprintf(tmp,sizeof(tmp),"%s/trade-installed.tmp",dir);FILE *ack=fopen(tmp,"wb");
    if(ack){fprintf(ack,"%llu",id);if(!fclose(ack)){
     snprintf(path,sizeof(path),"%s/trade-installed.txt",dir);
#ifdef _WIN32
     augustus_move_file(tmp,path,MOVEFILE_REPLACE_EXISTING);
#else
     rename(tmp,path);
#endif
    }}
   }
  }
 }
 if(trade_busy && completed==grant)army_install_poll(dir,completed,army_expected,army_load_saved);
 report_objective(dir);
 metric_publish(dir,now);
 if(!serial || !speed || now-seen>MP_RESPONSE_GRACE_MS || completed==grant){
  next_tick=now;
  int reason=!serial?CLOCK_NO_GRANT:now-seen>MP_RESPONSE_GRACE_MS?CLOCK_STALE:
   (capture_id || trade_busy)?CLOCK_BARRIER:!speed?CLOCK_PAUSED:CLOCK_NO_GRANT;
  return metric_return(now,reason,0);
 }
 if(now<next_tick)return metric_return(now,CLOCK_PACING,0);
 /* Never turn network credit into an animation burst or catch up after a stall. */
 return metric_return(now,CLOCK_RUNNING,1);
}
