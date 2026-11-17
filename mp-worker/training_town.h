/* Authored starting settlement, only used by the silent new-scenario worker.
 * Use real construction so multipart footprints/images/formations are saved. */
#include "building/construction_building.h"
#include "building/rotation.h"
#include "building/image.h"
#include "building/house_population.h"
#include "city/population.h"
#include "city/view.h"
#include "scenario/map.h"
#include "map/tiles.h"
#include "map/building_tiles.h"
#include "figure/formation_layout.h"
#include "figuretype/soldier.h"
static int training_place(int type,int x,int y){
 building_rotation_reset_rotation();
 if(!building_construction_place_building(type,x,y,1)){fprintf(stderr,"Training placement failed: %d %d %d\n",type,x,y);return 0;}
 building *b=building_main(building_get(map_building_at(map_grid_offset(x,y))));
 return b->id;
}
static int training_town(int kind,const char *out){
 int w=map_grid_width(),h=map_grid_height(),bx=-1,by=-1,best=100000;
 map_point entry=scenario_map_entry();
 if(w<28 || h<28 || w>160 || h>160 || entry.x<0 || entry.y<0 || entry.x>=w || entry.y>=h)return 0;
 for(int y=2;y+20<h-2;y++)for(int x=2;x+22<w-2;x++){
  int valid=1;
  for(int j=0;j<20 && valid;j++)for(int i=0;i<22;i++)
   if(map_terrain_is(map_grid_offset(x+i,y+j),(TERRAIN_NOT_CLEAR & ~(TERRAIN_TREE|TERRAIN_SHRUB)))){valid=0;break;}
  int distance=abs(x-entry.x)+abs(y+4-entry.y);
  if(valid && distance<best){bx=x;by=y;best=distance;}
 }
 if(bx<0){fputs("Training settlement needs an empty 22 by 20 area\n",stderr);return 0;}
 for(int j=0;j<20;j++)for(int i=0;i<22;i++)map_terrain_remove(map_grid_offset(bx+i,by+j),TERRAIN_TREE|TERRAIN_SHRUB);
 map_tiles_update_region_empty_land(bx,by,bx+21,by+19);
 int first=building_count();
 for(int j=4;j<=14;j+=5)for(int i=0;i<22;i++)map_terrain_add(map_grid_offset(bx+i,by+j),TERRAIN_ROAD);
 for(int j=4;j<=14;j++)map_terrain_add(map_grid_offset(bx,by+j),TERRAIN_ROAD);
 for(int j=3;j<=5;j+=2)for(int i=2;i<18;i++)if(!training_place(BUILDING_HOUSE_SMALL_TENT,bx+i,by+j))return 0;
 if(!training_place(BUILDING_WELL,bx+18,by+3) || !training_place(BUILDING_PREFECTURE,bx+19,by+3) ||
    !training_place(BUILDING_ENGINEERS_POST,bx+20,by+3) || !training_place(BUILDING_MARKET,bx+19,by+5))return 0;
 int warehouse=training_place(BUILDING_WAREHOUSE,bx+2,by+10),granary=training_place(BUILDING_GRANARY,bx+6,by+10);
 if(!warehouse || !granary)return 0;
 int pottery=training_place(BUILDING_POTTERY_WORKSHOP,bx+2,by+7);
 if(!pottery || !training_place(BUILDING_SMALL_STATUE,bx+10,by+8) ||
    !training_place(BUILDING_SMALL_STATUE,bx+14,by+8))return 0;
 building_get(pottery)->resources[RESOURCE_CLAY]=2*RESOURCE_ONE_LOAD;
 int forts[2]={0},mess=0;
 if(kind==2){
  mess=training_place(BUILDING_MESS_HALL,bx+10,by+10);
  if(!mess || !training_place(BUILDING_BARRACKS,bx+15,by+10))return 0;
  building_get(mess)->resources[RESOURCE_WHEAT]=8*RESOURCE_ONE_LOAD;
  forts[0]=training_place(BUILDING_FORT_JAVELIN,bx+2,by+17);
  forts[1]=training_place(BUILDING_FORT_LEGIONARIES,bx+13,by+17);
  if(!forts[0] || !forts[1])return 0;
  /* Separate access to fort bodies; never lay a road across parade grounds. */
  for(int i=0;i<2;i++)for(int y=15;y<=16;y++)map_terrain_add(map_grid_offset(building_get(forts[i])->x,y+by),TERRAIN_ROAD);
 }
 for(int i=first;i<building_count();i++){
  building *b=building_get(i);b->state=BUILDING_STATE_IN_USE;
  if(b->house_size){b->house_population=5;city_population_add(5);map_building_tiles_add(b->id,b->x,b->y,b->size,building_image_get(b),TERRAIN_BUILDING);}
 }
 if(building_warehouse_try_add_resource(building_get(warehouse),RESOURCE_POTTERY,20,0)!=20 ||
    building_warehouse_try_add_resource(building_get(warehouse),RESOURCE_CLAY,8,0)!=8 ||
    building_granary_try_add_resource(building_get(granary),RESOURCE_WHEAT,32,0,0)!=32)return 0;
 if(kind==2)for(int i=0;i<2;i++){
  building *b=building_get(forts[i]),*ground=building_get(b->next_part_building_id);formation*m=formation_get(b->formation_id);
  m->has_military_training=1;m->morale=100;m->is_at_fort=1;
  for(int j=0;j<16;j++){
   figure*f=figure_create(m->figure_type,m->x+formation_layout_position_x(FORMATION_AT_REST,j),m->y+formation_layout_position_y(FORMATION_AT_REST,j),DIR_0_TOP);if(!f->id)return 0;
   f->formation_id=m->id;f->building_id=b->id;f->formation_at_rest=1;f->action_state=FIGURE_ACTION_80_SOLDIER_AT_REST;
   f->index_in_formation=j;
   /* Seed the real sprite now, including when a new game starts paused. */
   figure_soldier_action(f);
  }
 }
 /* Find a traversable connection to the real entry, retaining all original terrain. */
 int parent[25600],queue[25600],head=0,tail=0,target=entry.y*w+entry.x,start=(by+4)*w+bx;
 for(int i=0;i<w*h;i++)parent[i]=-1;
 queue[tail++]=start;parent[start]=start;
 const int dx[]={1,-1,0,0},dy[]={0,0,1,-1};
 while(head<tail && parent[target]<0){int n=queue[head++],x=n%w,y=n/w;
  for(int d=0;d<4;d++){int xx=x+dx[d],yy=y+dy[d],v=yy*w+xx;
   if(xx<0 || yy<0 || xx>=w || yy>=h || parent[v]>=0 || map_terrain_is(map_grid_offset(xx,yy),TERRAIN_NOT_CLEAR_EXCEPT_ROAD))continue;
   parent[v]=n;queue[tail++]=v;
  }
 }
 if(parent[target]<0){fputs("Training settlement cannot reach the entry\n",stderr);return 0;}
 for(int v=target;;v=parent[v]){map_terrain_add(map_grid_offset(v%w,v/w),TERRAIN_ROAD);if(v==start)break;}
 map_tiles_update_all_roads();map_routing_update_land();formation_calculate_figures();
 int focus_y=by+(kind==2?17:9);
 city_view_go_to_grid_offset(map_grid_offset(bx+10,focus_y));
 char path[2048];snprintf(path,sizeof(path),"%s/training-town.json",out);FILE*f=fopen(path,"w");if(!f)return 0;
 fprintf(f,"{\"kind\":%d,\"x\":%d,\"y\":%d,\"population\":%d,\"warehouse\":%d,\"granary\":%d,\"pottery\":%d,\"forts\":[%d,%d],\"focus\":[%d,%d],\"entry_connected\":true}",kind,bx,by,city_population(),warehouse,granary,pottery,forts[0],forts[1],bx+10,focus_y);return fclose(f)==0;
}
static int training_start(const char *input,const char *city,const char *out){
 char path[2048],id[32];int kind,selected=0;snprintf(path,sizeof(path),"%s/starting-setup.txt",input);FILE*f=fopen(path,"r");if(!f)return 1;
 while(fscanf(f,"%31s %d",id,&kind)==2){if(kind<1 || kind>2){fclose(f);return 0;}if(!strcmp(id,city)){if(selected){fclose(f);return 0;}selected=kind;}}
 int ok=feof(f);fclose(f);return ok && (!selected || training_town(selected,out));
}
