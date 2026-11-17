/* Actual empire_route_paths.inc with engine state and drawing calls replaced by fixtures.
 * This executes the fallback renderer without a window; it is not visual UI verification. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <stdint.h>
#ifdef _WIN32
#include <sys/utime.h>
#else
#include <utime.h>
#define _utimbuf utimbuf
#define _utime utime
#define _putenv_s(k,v) setenv(k,v,1)
#endif
typedef unsigned color_t;
enum { EMPIRE_OBJECT_CITY=1, EMPIRE_OBJECT_LAND_TRADE_ROUTE, EMPIRE_OBJECT_SEA_TRADE_ROUTE };
enum { EMPIRE_CITY_OURS=1, EMPIRE_CITY_TRADE, EMPIRE_CITY_PLAYER };
#define MAX_SIDEBAR_CITIES 8
#define MAX_TRADE_EDGES 8
typedef struct { int type,id,x,y,trade_route_id; } empire_object;
typedef struct { int in_use,city_name_id;empire_object obj; } full_empire_object;
typedef struct { int in_use,type,route_id,name_id,is_sea_trade; } empire_city;
static full_empire_object objects[8];static empire_city cities[8];static int object_count=4;
static struct {int x1,y1,x2,y2;} g_trade_edges[8];static int g_trade_edge_count=1;
static int trade_city_edges[8][8];
static struct {struct {int trade_year;} sidebar;int x_draw_offset,y_draw_offset;} data;
static unsigned tick=10000,selected=0;static int multiplayer=1,draws,land,sea;
static unsigned time_get_millis(void){return tick;}
static int mp_clock_active(void){return multiplayer;}
static int empire_object_count(void){return object_count;}
static const full_empire_object *empire_object_get_full(int i){return &objects[i];}
static const empire_object *empire_object_get(int i){return &objects[i].obj;}
static const empire_city *empire_city_get(int i){return &cities[i];}
static int empire_city_get_for_object(int i){return i;}
static int empire_city_get_for_trade_route(int i){(void)i;return 1;}
static int empire_city_is_trade_route_open(int i){(void)i;return 1;}
static unsigned empire_selected_object(void){return selected;}
static void graphics_draw_line(int ax,int bx,int ay,int by,color_t color){
 (void)ax;(void)bx;(void)ay;(void)by;draws++;
 if((color&0xffffff)==0xe6bc7a)land++;
 if((color&0xffffff)==0x46d2dc)sea++;
}
#include "window/empire_route_paths.inc"
#define CHECK(x,msg) do{if(!(x)){fprintf(stderr,"FAIL %s\n",msg);return 1;}printf("PASS %s\n",msg);}while(0)
static void write_text(const char *name,const char *text){FILE*f=fopen(name,"wb");if(!f)exit(2);fwrite(text,1,strlen(text),f);fclose(f);}
static void render(void){tick+=2000;draws=land=sea=0;draw_route_paths();}
int main(int argc,char **argv){
 if(argc!=2)return 2;
 _putenv_s("AUGUSTUS_MP_BRIDGE",argv[1]);
 for(int i=0;i<8;i++)for(int j=0;j<8;j++)trade_city_edges[i][j]=-1;
 for(int i=0;i<3;i++){
  objects[i]=(full_empire_object){1,i+1,{EMPIRE_OBJECT_CITY,i,100+i*100,100,0}};
  cities[i]=(empire_city){1,i==0?EMPIRE_CITY_OURS:i==1?EMPIRE_CITY_TRADE:EMPIRE_CITY_PLAYER,0,i+1,i==2};
 }
 objects[3]=(full_empire_object){1,0,{EMPIRE_OBJECT_LAND_TRADE_ROUTE,3,0,0,0}};
 g_trade_edges[0].x1=125;g_trade_edges[0].y1=125;g_trade_edges[0].x2=225;g_trade_edges[0].y2=125;
 trade_city_edges[0][0]=0;
 write_text("empire-player-slots.txt","1\tplayer1\tA\n3\tplayer2\tB\n");
 write_text("route-state.txt","1 player2 1 1\n");
 render();CHECK(land>0&&sea>0,"missing file draws known neutral route and active sea contract");int fallback=draws;
 write_text("empire-routes.txt","broken");render();CHECK(route_paths.routes==0&&draws==fallback,"damaged file rejected; same game-known fallbacks");
 write_text("empire-routes.txt","AUGROUTES2\n1\n1 0 1 2 1 -1 1 2\n116 116 216 116\n");
 render();CHECK(route_paths.routes==1&&draws==fallback,"file route replaces matching fallback without duplicate");
 multiplayer=0;render();CHECK(draws==0,"single player untouched by overlay");multiplayer=1;
 write_text("route-state.txt","1 player2 0 2\n");render();CHECK(land>0&&sea==0,"inactive player contract has no game fallback");
 write_text("route-state.txt","1 player2 1 3\n");objects[2].in_use=0;render();CHECK(land>0&&sea==0,"unknown player position not guessed");objects[2].in_use=1;
 write_text("empire-routes.txt","AUGROUTES2\n1\n0 1 1 3 1 0 1 2\n116 116 316 116\n");
 struct _utimbuf times={1700000000,1700000000};_utime("empire-routes.txt",&times);render();CHECK(route_paths.route[0].active==0,"initial inactive file loaded");
 write_text("empire-routes.txt","AUGROUTES2\n1\n0 1 1 3 1 1 1 2\n116 116 316 116\n");
 _utime("empire-routes.txt",&times);render();CHECK(route_paths.route[0].active==1,"equal-size replacement within same timestamp refreshes contract");
 puts("ALL OK");return 0;
}
