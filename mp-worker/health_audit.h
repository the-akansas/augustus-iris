/* Deterministic health subsystem audit; only synthetic local test cities. */
#include "city/health.h"
#include "city/buildings.h"
#include "city/population.h"
#include "figuretype/service.h"
#include "figuretype/maintenance.h"
#include "map/routing_terrain.h"
static building *health_audit_house(void){
 for(int y=15;y<map_grid_height()-15;y++)for(int x=15;x<map_grid_width()-15;x++){
  int g=map_grid_offset(x,y);if(map_building_at(g)||map_terrain_is(g,TERRAIN_NOT_CLEAR))continue;
  building*b=building_create(BUILDING_HOUSE_SMALL_TENT,x,y);b->state=BUILDING_STATE_IN_USE;
  b->house_size=1;b->house_population=20;b->sickness_level=200;
  map_building_tiles_add(b->id,x,y,1,building_image_get(b),TERRAIN_BUILDING);return b;
 }return 0;
}
static int health_audit(const char*out,int test){
 building*b=health_audit_house();if(!b)return 0;int id=b->id;
 city_population_add(20);
 /* Keep a real census and enough other households to avoid the <200 exemption. */
 for(int n=0;n<24;n++){building*h=health_audit_house();if(!h)return 0;h->sickness_level=0;city_population_add(20);}
 b=building_get(id);city_health_set(test==1||test==6?20:80);
 char path[2048];snprintf(path,sizeof(path),"%s/health.json",out);FILE*f=fopen(path,"w");if(!f)return 0;
 fprintf(f,"{\"case\":%d,\"initial_population\":20",test);
 if(test<=3){
  city_health_update();fprintf(f,",\"after_outbreak\":{\"population\":%d,\"plague\":%d,\"type\":%d}",b->house_population,b->has_plague,b->type);
  if(test==1){for(int n=0;n<33;n++){building_update_state();building_maintenance_update_burning_ruins();}fprintf(f,",\"after_expiry\":{\"state\":%d,\"map_building\":%d,\"rubble\":%d}",b->state,map_building_at(b->grid_offset),!!map_terrain_is(b->grid_offset,TERRAIN_RUBBLE));}
  else if(test==2){
   for(int n=0;n<16;n++)city_buildings_update_plague();
   int before=b->house_population,duration=b->sickness_duration;
   snprintf(path,sizeof(path),"%s/infected.sav",out);if(!game_file_write_saved_game(path)||game_file_load_saved_game(path)!=FILE_LOAD_SUCCESS){fclose(f);return 0;}b=building_get(id);
   city_health_update();fprintf(f,",\"next_month\":{\"before_population\":%d,\"after_population\":%d,\"before_duration\":%d,\"after_duration\":%d,\"still_infected\":%d}",before,b->house_population,duration,b->sickness_duration,b->has_plague);
   for(int day=17;day<=100;day++){city_buildings_update_plague();if(day%16==0)city_health_update();}
   fprintf(f,",\"recovered\":{\"population\":%d,\"plague\":%d}",b->house_population,b->has_plague);
   b->sickness_level=200;city_health_set(80);city_health_update();
   fprintf(f,",\"reinfection\":%d",b->has_plague);
  }else{
   figure*doc=figure_create(FIGURE_DOCTOR,b->x,b->y,0);doc->destination_building_id=id;doc->action_state=FIGURE_ACTION_232_DOCTOR_AT_PLAGUE;doc->wait_ticks=50;
   figure_doctor_action(doc);int duration=b->sickness_duration,cure=b->sickness_doctor_cure;
   snprintf(path,sizeof(path),"%s/treated.sav",out);if(!game_file_write_saved_game(path)||game_file_load_saved_game(path)!=FILE_LOAD_SUCCESS){fclose(f);return 0;}b=building_get(id);
   for(int n=0;n<5;n++)city_buildings_update_plague();
   fprintf(f,",\"doctor\":{\"duration_after_action\":%d,\"cure_flag\":%d,\"plague_after_five_days\":%d,\"sickness_after\":%d}",duration,cure,b->has_plague,b->sickness_level);
  }
 }else if(test==4){
  building*a=building_create(BUILDING_WAREHOUSE,b->x+3,b->y),*d=building_create(BUILDING_WAREHOUSE,b->x+6,b->y);a->state=d->state=BUILDING_STATE_IN_USE;
  figure walker={0};walker.building_id=a->id;walker.destination_building_id=d->id;
  a->sickness_level=100;d->sickness_level=0;city_health_dispatch_sickness(&walker);int forward=d->sickness_level;
  a->sickness_level=0;d->sickness_level=100;city_health_dispatch_sickness(&walker);
  fprintf(f,",\"spread\":{\"from_origin_100_to_0\":%d,\"from_destination_100_to_0\":%d}",forward,a->sickness_level);
 }else if(test==5){
  b->sickness_level=0;b->has_plague=1;b->sickness_duration=0;
  for(int n=0;n<99;n++)city_buildings_update_plague();int before=b->has_plague;
  city_buildings_update_plague();fprintf(f,",\"natural_end\":{\"at_day_99\":%d,\"at_day_100\":%d}",before,b->has_plague);
 }else if(test==6){
  b->sickness_level=0;building*g=building_create(BUILDING_GRANARY,b->x+3,b->y);g->state=BUILDING_STATE_IN_USE;g->sickness_level=200;g->resources[RESOURCE_WHEAT]=32;g->resources[RESOURCE_NONE]=0;
  city_health_update();int first=g->resources[RESOURCE_WHEAT];city_health_update();
  fprintf(f,",\"granary\":{\"after_first\":%d,\"after_second\":%d,\"plague\":%d}",first,g->resources[RESOURCE_WHEAT],g->has_plague);
 }else if(test==7){
  int distance;b->has_plague=1;b->distance_from_entry=0;
  int unreachable=city_buildings_get_closest_plague(b->x,b->y,&distance);
  b->distance_from_entry=1;int reachable=city_buildings_get_closest_plague(b->x,b->y,&distance);
  b->has_plague=0;int cured=city_buildings_get_closest_plague(b->x,b->y,&distance);
  b->has_plague=1;b->state=BUILDING_STATE_DELETED_BY_GAME;int deleted=city_buildings_get_closest_plague(b->x,b->y,&distance);
  fprintf(f,",\"targets\":{\"unreachable\":%d,\"reachable_matches\":%d,\"cured\":%d,\"deleted\":%d}",unreachable,reachable==id,cured,deleted);
 }else if(test==8){
  building_destroy_by_fire(b);building_update_state();b->distance_from_entry=1;int distance;
  building_maintenance_update_burning_ruins();
  int normal=building_maintenance_get_closest_burning_ruin(b->x,b->y,&distance);
  b->has_plague=1;int plague=building_maintenance_get_closest_burning_ruin(b->x,b->y,&distance);b->has_plague=0;
  building*station=building_create(BUILDING_PREFECTURE,b->x+8,b->y);station->state=BUILDING_STATE_IN_USE;
  figure*prefect=figure_create(FIGURE_PREFECT,b->x,b->y,0);prefect->building_id=station->id;station->figure_id=prefect->id;
  prefect->destination_building_id=id;prefect->action_state=FIGURE_ACTION_75_PREFECT_AT_FIRE;prefect->wait_ticks=50;
  figure_prefect_action(prefect);int timer=b->fire_duration;
  snprintf(path,sizeof(path),"%s/extinguished.sav",out);if(!game_file_write_saved_game(path)||game_file_load_saved_game(path)!=FILE_LOAD_SUCCESS){fclose(f);return 0;}b=building_get(id);
  building_maintenance_update_burning_ruins();
  fprintf(f,",\"fire\":{\"normal_matches\":%d,\"plague_target\":%d,\"timer_after_prefect\":%d,\"rubble_after_reload\":%d}",normal==id,plague,timer,!!map_terrain_is(b->grid_offset,TERRAIN_RUBBLE));
 }else if(test==9 || test==10){
  int px=0,py=0;
  for(int y=20;y<map_grid_height()-20&&!px;y++)for(int x=20;x<map_grid_width()-20;x++){
   int valid=1;for(int dy=0;dy<6;dy++)for(int dx=0;dx<12;dx++){int g=map_grid_offset(x+dx,y+dy);if(map_building_at(g)||map_terrain_is(g,TERRAIN_NOT_CLEAR))valid=0;}
   if(valid){px=x;py=y;break;}
  }if(!px){fclose(f);return 0;}
  building*target=building_create(BUILDING_HOUSE_SMALL_TENT,px+8,py+2);target->state=BUILDING_STATE_IN_USE;target->house_size=1;target->house_population=20;target->has_plague=test==9;
  map_building_tiles_add(target->id,target->x,target->y,1,building_image_get(target),TERRAIN_BUILDING);
  if(test==10){building_destroy_by_fire(target);building_update_state();building_maintenance_update_burning_ruins();}
  target->distance_from_entry=1;target->road_access_x=px+8;target->road_access_y=py+3;
  for(int dx=0;dx<=8;dx++)map_terrain_add(map_grid_offset(px+dx,py+3),TERRAIN_ROAD);
  map_routing_update_land();
  building*station=building_create(test==9?BUILDING_DOCTOR:BUILDING_PREFECTURE,px,py+2);station->state=BUILDING_STATE_IN_USE;
  figure*walker=figure_create(test==9?FIGURE_DOCTOR:FIGURE_PREFECT,px,py+3,0);station->figure_id=walker->id;walker->building_id=station->id;
  walker->action_state=test==9?FIGURE_ACTION_125_ROAMING:FIGURE_ACTION_70_PREFECT_CREATED;walker->wait_ticks_missile=20;
  int step=0;for(;step<800;step++){
   if(test==9)figure_doctor_action(walker);else figure_prefect_action(walker);
   if(target->sickness_doctor_cure==99 || target->fire_duration==32 || walker->state==FIGURE_STATE_DEAD)break;
  }
  fprintf(f,",\"walk\":{\"steps\":%d,\"moved\":%d,\"treated\":%d,\"fire_timer\":%d,\"state\":%d}",step,walker->x!=px||walker->y!=py+3,target->sickness_doctor_cure==99,target->fire_duration,walker->state);
 }else {fclose(f);return 0;}
 fputs("}",f);return fclose(f)==0;
}
