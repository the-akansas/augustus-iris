/* Data-only terrain authoring. Uses native grids and autotiling, never UI input. */
#ifndef CREATOR_TERRAIN_H
#define CREATOR_TERRAIN_H
#include "map/grid.h"
#include "map/terrain.h"
#include "map/property.h"
#include "map/building.h"
#include "map/elevation.h"
#include "map/tiles.h"
#include "map/routing_terrain.h"
#include "map/image_context.h"
#include "map/image.h"
#include "scenario/data.h"
#include "city/map.h"
#include "map/routing.h"
#include "map/bridge.h"
#include "map/water.h"
#include "building/dock.h"
#include "scenario/map.h"
#include "core/direction.h"

static int creator_near_point(int x,int y,map_point p,int radius){
 return p.x>=0 && p.y>=0 && p.x<map_grid_width() && p.y<map_grid_height() &&
  (p.x || p.y) && abs(x-p.x)<=radius && abs(y-p.y)<=radius;
}
static int creator_terrain_protected(int x,int y){
 int w=map_grid_width(),h=map_grid_height();
 if(x<2 || y<2 || x>=w-2 || y>=h-2)return 1;
 int offset=map_grid_offset(x,y);
 if(map_terrain_is(offset,TERRAIN_BUILDING|TERRAIN_ROAD|TERRAIN_AQUEDUCT|TERRAIN_WALL_OR_GATEHOUSE|TERRAIN_HIGHWAY) || map_building_at(offset))return 1;
 for(int dy=-1;dy<=1;dy++)for(int dx=-1;dx<=1;dx++){
  int p=map_grid_offset(x+dx,y+dy);
  if(map_elevation_at(p) || map_terrain_is(p,TERRAIN_ELEVATION|TERRAIN_ACCESS_RAMP))return 1;
 }
 map_point points[]={scenario.entry_point,scenario.exit_point,scenario.river_entry_point,scenario.river_exit_point,scenario.earthquake_point};
 for(unsigned int i=0;i<sizeof(points)/sizeof(points[0]);i++)if(creator_near_point(x,y,points[i],2))return 1;
 for(int i=0;i<MAX_HERD_POINTS;i++)if(creator_near_point(x,y,scenario.herd_points[i],1))return 1;
 for(int i=0;i<MAX_FISH_POINTS;i++)if(creator_near_point(x,y,scenario.fishing_points[i],1))return 1;
 for(int i=0;i<MAX_INVASION_POINTS;i++)if(creator_near_point(x,y,scenario.invasion_points[i],2))return 1;
 const map_tile *entry=city_map_entry_flag(),*exit=city_map_exit_flag();
 if(entry && abs(x-entry->x)<=1 && abs(y-entry->y)<=1)return 1;
 if(exit && abs(x-exit->x)<=1 && abs(y-exit->y)<=1)return 1;
 return 0;
}
static int creator_connected(map_point a,map_point b,int water){
 int w=map_grid_width(),h=map_grid_height();
 if(a.x<0 || a.y<0 || b.x<0 || b.y<0 || a.x>=w || b.x>=w || a.y>=h || b.y>=h)return 0;
 if(!(a.x || a.y) || !(b.x || b.y))return 0;
 int queue[25600],head=0,tail=0;unsigned char seen[25600]={0};
 queue[tail++]=a.y*w+a.x;seen[queue[0]]=1;
 while(head<tail){int n=queue[head++],x=n%w,y=n/w;if(x==b.x && y==b.y)return 1;
  const int dx[]={0,1,0,-1},dy[]={-1,0,1,0};
  for(int d=0;d<4;d++){int xx=x+dx[d],yy=y+dy[d];if(xx<0 || yy<0 || xx>=w || yy>=h)continue;int i=yy*w+xx;if(seen[i])continue;
   int t=map_terrain_get(map_grid_offset(xx,yy));int pass=water?!!(t&TERRAIN_WATER):!(t&(TERRAIN_IMPASSABLE|TERRAIN_ACCESS_RAMP));
   if(!pass)continue;seen[i]=1;queue[tail++]=i;
  }
 }
 return 0;
}
static const char *creator_terrain_kind(int offset){
 int t=map_terrain_get(offset);
 if(t&TERRAIN_BUILDING)return "building";
 if(t&(TERRAIN_ROAD|TERRAIN_HIGHWAY))return "road";
 if(t&TERRAIN_WATER)return "water";
 if(t&(TERRAIN_ROCK|TERRAIN_ELEVATION))return "rock";
 if(t&(TERRAIN_TREE|TERRAIN_SHRUB))return "trees";
 if(t&TERRAIN_MEADOW)return "meadow";
 return "land";
}
static int creator_apply_terrain(const char *path,long offset,int count){
 if(!count)return 1;
 FILE *f=fopen(path,"rb");if(!f || fseek(f,offset,SEEK_SET)){if(f)fclose(f);return 0;}
 int w=map_grid_width(),h=map_grid_height(),ok=1;
 int *edits=calloc((size_t)count*3,sizeof(int));if(!edits){fclose(f);return 0;}
 /* Validate all tiles against the unmodified template before applying any. */
 for(int i=0;i<count;i++){
  int *e=edits+3*i;
  if(fscanf(f,"%d %d %d",e,e+1,e+2)!=3 || e[0]<0 || e[1]<0 || e[0]>=w || e[1]>=h || e[2]<0 || e[2]>2 || creator_terrain_protected(e[0],e[1])){
   fprintf(stderr,"Creator terrain rejected protected or invalid tile: %d,%d\n",e[0],e[1]);ok=0;break;
  }
 }
 fclose(f);if(!ok){free(edits);return 0;}
 int land_connected=creator_connected(scenario.entry_point,scenario.exit_point,0);
 int river_connected=creator_connected(scenario.river_entry_point,scenario.river_exit_point,1);
 for(int i=0;i<count;i++){
  int *e=edits+3*i,p=map_grid_offset(e[0],e[1]);
  map_terrain_set(p,e[2]==1?TERRAIN_WATER:e[2]==2?TERRAIN_ROCK:TERRAIN_CLEAR);
  map_property_set_multi_tile_size(p,1);map_property_clear_multi_tile_xy(p);map_property_mark_draw_tile(p);
  map_property_clear_future_earthquake(p);map_property_clear_plaza_earthquake_or_overgrown_garden(p);
 }
 free(edits);
 if((land_connected && !creator_connected(scenario.entry_point,scenario.exit_point,0)) ||
    (river_connected && !creator_connected(scenario.river_entry_point,scenario.river_exit_point,1))){
  fprintf(stderr,"Creator terrain rejected: existing entry/exit route was disconnected\n");return 0;
 }
 map_image_context_reset_water();map_image_context_reset_elevation();map_tiles_update_all();map_routing_update_all();
 map_terrain_backup();map_property_backup();return 1;
}
/* Scenario checks need the engine's own answers, not a re-implementation:
 * entry_exit - can a walker go from the city entry to the exit (the points migrants and caravans use)?
 *   now      as the map stands (map_routing_citizen_can_travel_over_land, the call figure_route_add makes)
 *   cleared  after every tree and shrub is cleared (what the clear-land tool can remove)
 *   bridged  additionally with every bridge map_bridge_calculate_length_direction accepts
 * sea        river entry/exit, boat-reachable water, and tiles where the dock placement rule passes.
 * Terrain is changed only temporarily and restored before returning. */
static int creator_walk(const map_tile *a,const map_tile *b){
 if(!a || !b)return 0;
 if(a->x==b->x && a->y==b->y)return 1;
 return map_routing_citizen_can_travel_over_land(a->x,a->y,b->x,b->y,8,0)?1:0;
}
static void creator_export_checks(FILE *f){
 int w=map_grid_width(),h=map_grid_height();
 const map_tile *a=city_map_entry_point(),*b=city_map_exit_point();
 map_routing_update_land();
 int now=creator_walk(a,b),cleared=now,bridged=now;
 if(!now){
  int *saved=malloc(sizeof(int)*(size_t)w*h);unsigned char *span=calloc((size_t)w*h,1);
  if(saved && span){
   for(int y=0;y<h;y++)for(int x=0;x<w;x++){int p=map_grid_offset(x,y);saved[y*w+x]=map_terrain_get(p);map_terrain_remove(p,TERRAIN_TREE|TERRAIN_SHRUB);}
   map_routing_update_land();cleared=bridged=creator_walk(a,b);
   if(!cleared){
    static grid_slice blocking;
    for(int y=0;y<h;y++)for(int x=0;x<w;x++){
     int length=0,direction=0;blocking.size=0;
     if(!map_bridge_calculate_length_direction(x,y,&length,&direction,&blocking))continue;
     int dx=direction==DIR_2_RIGHT?1:direction==DIR_6_LEFT?-1:0,dy=direction==DIR_4_BOTTOM?1:direction==DIR_0_TOP?-1:0;
     for(int i=0;i<length;i++){int xx=x+dx*i,yy=y+dy*i;if(xx>=0 && yy>=0 && xx<w && yy<h)span[yy*w+xx]=1;}
    }
    map_bridge_reset_building_length();
    for(int y=0;y<h;y++)for(int x=0;x<w;x++)if(span[y*w+x])map_terrain_remove(map_grid_offset(x,y),TERRAIN_WATER);
    map_routing_update_land();bridged=creator_walk(a,b);
   }
   for(int y=0;y<h;y++)for(int x=0;x<w;x++)map_terrain_set(map_grid_offset(x,y),saved[y*w+x]);
   map_routing_update_land();
  }else cleared=bridged=-1;
  free(saved);free(span);
 }
 fprintf(f,",\"entry_exit\":{\"entry\":[%d,%d],\"exit\":[%d,%d],\"now\":%d,\"cleared\":%d,\"bridged\":%d}",a?a->x:-1,a?a->y:-1,b?b->x:-1,b?b->y:-1,now,cleared,bridged);
 int has_entry=scenario_map_has_river_entry(),has_exit=scenario_map_has_river_exit(),open=0,exit_reached=0,docks=0,docks_clear=0;
 if(has_entry){
  map_point in=scenario_map_river_entry(),out=scenario_map_river_exit();
  map_routing_calculate_distances_water_boat(in.x,in.y);
  for(int y=0;y<h;y++)for(int x=0;x<w;x++)if(map_routing_distance(map_grid_offset(x,y))>0)open++;
  if(has_exit && out.x>=0 && out.y>=0 && out.x<w && out.y<h)exit_reached=map_routing_distance(map_grid_offset(out.x,out.y))>0;
  if(open)for(int y=0;y<h;y++)for(int x=0;x<w;x++){
   int absolute=0,relative=0;
   if(map_water_determine_orientation(x,y,3,0,&absolute,&relative,1,0) || !building_dock_is_connected_to_open_water(x,y))continue;
   docks++;int blocked=0; /* dock_sites: the placement rule only. dock_sites_clear: also no rock, cliff or building under it. */
   for(int yy=0;yy<3;yy++)for(int xx=0;xx<3;xx++){int t=map_terrain_get(map_grid_offset(x+xx,y+yy));if(!(t&TERRAIN_WATER) && (t&(TERRAIN_ROCK|TERRAIN_ELEVATION|TERRAIN_ACCESS_RAMP|TERRAIN_BUILDING)))blocked=1;}
   if(!blocked)docks_clear++;
  }
 }
 fprintf(f,",\"sea\":{\"river_entry\":%d,\"river_exit\":%d,\"open_water\":%d,\"exit_reached\":%d,\"dock_sites\":%d,\"dock_sites_clear\":%d}",has_entry,has_exit,open,exit_reached,docks,docks_clear);
 /* Fishing is separate from sea trade: boats go from a shipyard to a wharf to the scenario's fishing points
  * (figuretype/water.c). points = fishing points set (x>0, as scenario_map_foreach_fishing_point);
  * sites = shore tiles where the wharf/shipyard placement rule passes next to water a boat can reach from a point;
  * two_sites = at least two such sites that do not overlap (one wharf and one shipyard). */
 int points=0,sites=0,two_sites=0,first_x=-1,first_y=-1;unsigned char *seen=calloc((size_t)w*h,1);
 if(seen)for(int i=0;i<MAX_FISH_POINTS;i++){
  map_point p=scenario.fishing_points[i];if(p.x<=0 || p.x>=w || p.y<0 || p.y>=h)continue;
  points++;map_routing_calculate_distances_water_boat(p.x,p.y);
  for(int y=0;y<h;y++)for(int x=0;x<w;x++){
   int absolute=0,relative=0;if(seen[y*w+x])continue;
   if(map_water_determine_orientation(x,y,2,0,&absolute,&relative,1,0) || !map_terrain_is_adjacent_to_open_water(x,y,2))continue;
   seen[y*w+x]=1;sites++;
   if(first_x<0){first_x=x;first_y=y;}else if(abs(x-first_x)>=2 || abs(y-first_y)>=2)two_sites=1;
  }
 }
 free(seen);
 fprintf(f,",\"fishing\":{\"points\":%d,\"sites\":%d,\"two_sites\":%d}",points,sites,two_sites);
}
static int creator_export_terrain(const char *out){
 char path[2048];snprintf(path,sizeof(path),"%s/terrain.json",out);FILE *f=fopen(path,"w");if(!f)return 0;
 int w=map_grid_width(),h=map_grid_height();if(w<1 || h<1 || w>160 || h>160){fclose(f);return 0;}
 fprintf(f,"{\"width\":%d,\"height\":%d,\"tiles\":[",w,h);
 for(int y=0;y<h;y++)for(int x=0;x<w;x++)fprintf(f,"%s\"%s\"",x||y?",":"",creator_terrain_kind(map_grid_offset(x,y)));
 fputs("],\"protected\":[",f);int first=1;
 for(int y=0;y<h;y++)for(int x=0;x<w;x++)if(creator_terrain_protected(x,y)){fprintf(f,"%s[%d,%d]",first?"":",",x,y);first=0;}
 fprintf(f,"],\"entry\":[%d,%d],\"exit\":[%d,%d],\"river_entry\":[%d,%d],\"river_exit\":[%d,%d],\"terrain_flags\":[",scenario.entry_point.x,scenario.entry_point.y,scenario.exit_point.x,scenario.exit_point.y,scenario.river_entry_point.x,scenario.river_entry_point.y,scenario.river_exit_point.x,scenario.river_exit_point.y);
 for(int y=0;y<h;y++)for(int x=0;x<w;x++)fprintf(f,"%s%d",x||y?",":"",map_terrain_get(map_grid_offset(x,y)));
 fputs("],\"images\":[",f);for(int y=0;y<h;y++)for(int x=0;x<w;x++)fprintf(f,"%s%d",x||y?",":"",map_image_at(map_grid_offset(x,y)));
 fputs("],\"elevation\":[",f);for(int y=0;y<h;y++)for(int x=0;x<w;x++)fprintf(f,"%s%d",x||y?",":"",map_elevation_at(map_grid_offset(x,y)));
 fputs("],\"fishing_points\":[",f);for(int i=0;i<MAX_FISH_POINTS;i++)fprintf(f,"%s[%d,%d]",i?",":"",scenario.fishing_points[i].x,scenario.fishing_points[i].y);
 fputs("],\"herd_points\":[",f);for(int i=0;i<MAX_HERD_POINTS;i++)fprintf(f,"%s[%d,%d]",i?",":"",scenario.herd_points[i].x,scenario.herd_points[i].y);
 fputs("],\"invasion_points\":[",f);for(int i=0;i<MAX_INVASION_POINTS;i++)fprintf(f,"%s[%d,%d]",i?",":"",scenario.invasion_points[i].x,scenario.invasion_points[i].y);
 fprintf(f,"],\"climate\":%d",scenario.climate);creator_export_checks(f);fputs("}",f);return fclose(f)==0;
}
#endif
