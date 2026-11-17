/* Synthetic terrain, only in the muted worker. No user city is edited. */
#include "scenario/data.h"
#include "building/dock.h"
#include "map/road_access.h"
#include "map/routing.h"
#include "figuretype/docker.h"
static int sea_run_fixture(const char *out,int midway,int departing){
 figure *ship=0;for(unsigned int i=1;i<figure_count();i++)if(figure_get(i)->type==FIGURE_TRADE_SHIP && figure_get(i)->mp_contract_id==1)ship=figure_get(i);
 assert(ship);int target=0,status=0,ticks=0;
 while(ticks++<10000){
  figure_trade_ship_action(ship);
  for(unsigned int i=1;i<figure_count();i++){
   figure *f=figure_get(i);if(f->type==FIGURE_DOCKER && !figure_is_dead(f))figure_docker_action(f);
  }
  status=mp_transport_status(1,&target);
  if(status==4){fprintf(stderr,"sea failed at %d,%d state %d dir %d dock %d\n",ship->x,ship->y,ship->action_state,ship->direction,ship->building_id);assert(0);}
  if(midway==1 && ticks==12)break;
  if(midway==2){
   int walking=0;for(unsigned int i=1;i<figure_count();i++){figure *w=figure_get(i);if(w->type==FIGURE_DOCKER && w->mp_contract_id==1 && w->action_state==MP_CARAVAN_WALK && w->x>w->source_x)walking=1;}
   if(walking)break;
  }
  if(status==(departing?5:3))break;
 }
 assert(ticks<10000);
 if(!midway && !departing)assert(ship->mp_source?mp_transport_validate_source(1,target,RESOURCE_POTTERY,3):mp_transport_validate(1,target,RESOURCE_POTTERY,3));
 if(departing && !midway)assert(mp_transport_validate_departed(1,RESOURCE_POTTERY,3));
 char path[2048];snprintf(path,sizeof(path),"%s/transport.txt",out);FILE *fp=fopen(path,"w");assert(fp);fprintf(fp,"1 %d",target);fclose(fp);
 snprintf(path,sizeof(path),"%s/departure.json",out);fp=fopen(path,"w");assert(fp);fprintf(fp,"{\"x\":%d,\"y\":%d,\"status\":%d}",ship->x,ship->y,status);fclose(fp);
 return target;
}
static int sea_seed_fixture(const char *out,int source,int midway){
 for(int y=25;y<=52;y++)for(int x=25;x<=64;x++){
  int o=map_grid_offset(x,y);map_building_set(o,0);map_terrain_set(o,y<=40?TERRAIN_WATER:TERRAIN_CLEAR);
 }
 scenario.river_entry_point=(map_point){28,32};scenario.river_exit_point=(map_point){61,32};
 for(int x=40;x<=50;x++)map_terrain_set(map_grid_offset(x,43),TERRAIN_ROAD);
 city_map_set_entry_point(40,43);city_map_set_exit_point(40,43);
 building *dock=building_create(BUILDING_DOCK,40,40);int dockid=dock->id;
 dock->state=BUILDING_STATE_IN_USE;dock->num_workers=10;dock->has_water_access=1;dock->has_road_access=1;dock->data.dock.orientation=0;dock->accepted_goods[RESOURCE_POTTERY]=1;
 for(int y=40;y<43;y++)for(int x=40;x<43;x++){map_building_set(map_grid_offset(x,y),dockid);map_terrain_set(map_grid_offset(x,y),TERRAIN_BUILDING | (y==40?TERRAIN_WATER:0));}
 building *b=building_create(BUILDING_WAREHOUSE,50,44);int id=b->id,prev=id;
 b->state=BUILDING_STATE_IN_USE;b->has_road_access=1;b->storage_id=building_storage_create(id);
 map_building_set(map_grid_offset(50,44),id);map_terrain_set(map_grid_offset(50,44),TERRAIN_BUILDING);
 for(int i=0;i<8;i++){
  building *part=building_create(BUILDING_WAREHOUSE_SPACE,51+i%3,45+i/3);part->state=BUILDING_STATE_IN_USE;
  part->prev_part_building_id=prev;building_get(prev)->next_part_building_id=part->id;prev=part->id;
 }
 if(source)assert(building_warehouse_try_add_resource(building_get(id),RESOURCE_POTTERY,5,0)==5);
 building_storage_toggle_permission(BUILDING_STORAGE_PERMISSION_TRADERS,building_get(id));
 assert(!building_storage_get_permission(BUILDING_STORAGE_PERMISSION_TRADERS,building_get(id)));
 city_finance_treasury_add(1000-city_finance_treasury());map_routing_update_land();map_routing_update_water();
 /* Missing workers and blocked warehouse permission cannot create a successful shipment. */
 building_get(dockid)->num_workers=0;assert(!mp_transport_begin_sea(1,RESOURCE_POTTERY,3,source));building_get(dockid)->num_workers=10;
 /* Run the ordinary dock workers too, to catch NPC/contract interference. */
 for(int i=0;i<3;i++){
  figure *w=figure_create(FIGURE_DOCKER,43,43,DIR_4_BOTTOM);w->building_id=dockid;
  w->action_state=FIGURE_ACTION_132_DOCKER_IDLING;building_get(dockid)->data.distribution.cartpusher_ids[i]=w->id;
 }
 figure *busy=figure_get(building_get(dockid)->data.distribution.cartpusher_ids[0]);
 busy->action_state=FIGURE_ACTION_137_DOCKER_EXPORT_RETURNING;
 assert(!mp_transport_begin_sea(1,RESOURCE_POTTERY,3,source));
 busy->action_state=FIGURE_ACTION_132_DOCKER_IDLING;
 map_point r,p;building_dock_get_ship_request_tile(building_get(dockid),SHIP_DOCK_REQUEST_1_DOCKING,&p);
 map_routing_calculate_distances_water_boat(28,32);
 fprintf(stderr,"sea fixture dock=%d first=%p road=%d target=%d,%d distance=%d work=%d water=%d\n",dockid,(void*)building_first_of_type(BUILDING_DOCK),map_has_road_access(40,40,3,&r),p.x,p.y,map_routing_distance(map_grid_offset(p.x,p.y)),building_dock_is_working(dockid),building_get(dockid)->has_water_access);
 assert(mp_transport_begin_sea(1,RESOURCE_POTTERY,3,source));
 assert(mp_transport_begin_sea(1,RESOURCE_POTTERY,3,source)); /* retry is idempotent */
 assert(!mp_transport_begin_sea(1,RESOURCE_POTTERY,4,source));
 sea_run_fixture(out,midway,0);
 if(!midway){
  building_storage_toggle_permission(BUILDING_STORAGE_PERMISSION_DOCK,building_get(id));
  assert(!(source?mp_transport_validate_source(1,id,RESOURCE_POTTERY,3):mp_transport_validate(1,id,RESOURCE_POTTERY,3)));
  building_storage_toggle_permission(BUILDING_STORAGE_PERMISSION_DOCK,building_get(id));
  building_get(dockid)->num_workers=0;
  assert(!(source?mp_transport_validate_source(1,id,RESOURCE_POTTERY,3):mp_transport_validate(1,id,RESOURCE_POTTERY,3)));
  building_get(dockid)->num_workers=10;
 }
 assert(building_warehouse_get_amount(building_get(id),RESOURCE_POTTERY)==(source?5:0));
 assert(city_finance_treasury()==1000);
 return id;
}

static void sea_failure_fixture(const char *mode){
 figure *ship=0,*worker=0;
 for(unsigned int i=1;i<figure_count();i++){
  figure *f=figure_get(i);if(f->mp_contract_id!=1)continue;
  if(f->type==FIGURE_TRADE_SHIP)ship=f;else if(f->type==FIGURE_DOCKER)worker=f;
 }
 assert(ship && worker && worker->action_state==MP_CARAVAN_WALK);
 int money=city_finance_treasury();
 if(strstr(mode,"worker"))worker->state=FIGURE_STATE_DEAD;
 else if(strstr(mode,"goods"))building_get(ship->building_id)->accepted_goods[RESOURCE_POTTERY]=0;
 else building_get(ship->building_id)->num_workers=0;
 figure_trade_ship_action(ship);int id=0;
 assert(mp_transport_status(1,&id)==4);
 assert(!building_get(ship->building_id)->data.dock.trade_ship_id);
 assert(city_finance_treasury()==money);
}
