/* Headless reproduction only. Never loads or modifies a user's save. */
#include "building/maintenance.h"
#include "building/destruction.h"
#include "map/sprite.h"
static int plague_probe(const char *out,int size,int reload,int plagued){
 if(size<1 || size>4)return 0;
 int x=0,y=0;
 for(int yy=10;yy<map_grid_height()-10&&!x;yy++)for(int xx=10;xx<map_grid_width()-10;xx++){
  int valid=1;for(int dy=0;dy<size;dy++)for(int dx=0;dx<size;dx++){
   int g=map_grid_offset(xx+dx,yy+dy);
   if(map_building_at(g)||map_terrain_is(g,TERRAIN_NOT_CLEAR))valid=0;
  }if(valid){x=xx;y=yy;break;}
 }if(!x)return 0;
 building*b=building_create(BUILDING_HOUSE_SMALL_TENT,x,y);
 b->state=BUILDING_STATE_IN_USE;b->size=size;b->house_size=size;b->house_population=0;
 map_building_tiles_add(b->id,x,y,size,building_image_get(b),TERRAIN_BUILDING);
 if(plagued)building_destroy_by_plague(b);else building_destroy_by_fire(b);
 char path[2048];snprintf(path,sizeof(path),"%s/trace.json",out);FILE*f=fopen(path,"w");if(!f)return 0;
 fprintf(f,"{\"size\":%d,\"plague\":%d,\"reload\":%d,\"trace\":[",size,plagued,reload);
 int ended=-1,first=1;
 for(int tick=0;tick<=1800;tick++){
  if(tick%50==0){
   int active=0,rubble=0,animated=0,max_timer=0;
   for(int dy=0;dy<size;dy++)for(int dx=0;dx<size;dx++){
    int g=map_grid_offset(x+dx,y+dy),id=map_building_at(g);building*r=building_get(id);
    if(id&&r->type==BUILDING_BURNING_RUIN){active++;if(r->fire_duration>max_timer)max_timer=r->fire_duration;}
    if(map_terrain_is(g,TERRAIN_RUBBLE))rubble++;
    if(image_get(map_image_at(g))->animation)animated++;
   }
   fprintf(f,"%s{\"tick\":%d,\"burning_tiles\":%d,\"rubble_tiles\":%d,\"animated_tiles\":%d,\"timer\":%d}",first?"":",",tick,active,rubble,animated,max_timer);first=0;
   if(!active&&rubble==size*size&&!animated){ended=tick;break;}
  }
  if(reload&&tick==500){snprintf(path,sizeof(path),"%s/mid.sav",out);if(!game_file_write_saved_game(path)||game_file_load_saved_game(path)!=FILE_LOAD_SUCCESS){fclose(f);return 0;}}
  game_tick_run();
 }
 fprintf(f,"],\"ended_tick\":%d}",ended);fclose(f);return ended>=0;
}
