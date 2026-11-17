/* Only linked into the silent snapshot worker, never the released game. */
#include "multiplayer/transport.h"
#include "figuretype/trader.h"
#include "map/building.h"
#include "map/grid.h"
#include "map/terrain.h"
#include "map/routing_terrain.h"
#include "city/map.h"
#include <assert.h>
#include "multiplayer/clock.h"
#include <SDL.h>
static void transport_reset_fixture(const char *out){
 figure *saved=0;for(unsigned int i=1;i<figure_count();i++)if(figure_get(i)->mp_contract_id==1)saved=figure_get(i);
 assert(saved && saved->action_state==MP_CARAVAN_READY);
 _putenv_s("AUGUSTUS_MP_BRIDGE",out);
 mp_clock_start();
 char path[2048];snprintf(path,sizeof(path),"%s/transport.txt",out);
 FILE *fp=fopen(path,"w");assert(fp);fputs("99 0 3 1",fp);fclose(fp);
 mp_transport_poll(); /* Cache a creation failure for this contract. */
 saved->mp_contract_id=99; /* Equivalent persisted figure after loading a SAV. */
 snprintf(path,sizeof(path),"%s/transport.txt",out);fp=fopen(path,"w");assert(fp);fputs("99 15 3 1",fp);fclose(fp);
 /* Poll released the old contract while testing 99: restore its saved state too. */
 saved->action_state=MP_CARAVAN_READY;
 for(int via_start=0;via_start<2;via_start++){
  if(via_start)mp_clock_start();else mp_transport_reset();
  mp_transport_poll();
  snprintf(path,sizeof(path),"%s/transport-state.txt",out);fp=fopen(path,"r");assert(fp);
  unsigned int id;int status,target;assert(fscanf(fp,"%u %d %d",&id,&status,&target)==3);fclose(fp);
  assert(id==99 && status==3);
  int count=0;for(unsigned int i=1;i<figure_count();i++)if(figure_get(i)->mp_contract_id==99)count++;
  assert(count==1);
 }
 mp_clock_stop();_putenv_s("AUGUSTUS_MP_BRIDGE","");
}
static int transport_depart_fixture(const char *out,int midway){
 figure *f=0;for(unsigned int i=1;i<figure_count();i++)if(figure_get(i)->mp_contract_id==1)f=figure_get(i);
 assert(f && f->mp_source && (f->action_state==MP_CARAVAN_DEPART || f->action_state==MP_CARAVAN_DEPARTED));
 int target=0,ticks=0;
 while(mp_transport_status(1,&target)!=5 && ticks++<6000){
  figure_trade_caravan_action(f);assert(mp_transport_status(1,&target)!=4);
  if(midway && ticks>=20)break;
 }
 assert(ticks<6000);
 if(midway)assert(!mp_transport_validate_departed(1,RESOURCE_POTTERY,3));
 else assert(mp_transport_validate_departed(1,RESOURCE_POTTERY,3));
 char path[2048];snprintf(path,sizeof(path),"%s/departure.json",out);FILE *fp=fopen(path,"w");assert(fp);
 fprintf(fp,"{\"x\":%d,\"y\":%d,\"status\":%d}",f->x,f->y,mp_transport_status(1,&target));fclose(fp);
 return f->destination_building_id;
}
static int transport_fixture(const char *out,int blocked){
 for(int y=32;y<=44;y++)for(int x=30;x<=44;x++){
  int o=map_grid_offset(x,y);map_terrain_set(o,TERRAIN_CLEAR);map_building_set(o,0);
 }
 for(int x=32;x<=40;x++)map_terrain_set(map_grid_offset(x,39),TERRAIN_ROAD);
 city_map_set_entry_point(32,39);city_map_set_exit_point(32,39);
 building *b=building_create(BUILDING_WAREHOUSE,40,40);int id=b->id,prev=id;
 b->state=BUILDING_STATE_IN_USE;b->has_road_access=1;b->storage_id=building_storage_create(id);
 map_building_set(map_grid_offset(40,40),id);map_terrain_set(map_grid_offset(40,40),TERRAIN_BUILDING);
 for(int i=0;i<8;i++){
  building *part=building_create(BUILDING_WAREHOUSE_SPACE,41+i%3,41+i/3);
  part->state=BUILDING_STATE_IN_USE;part->prev_part_building_id=prev;building_get(prev)->next_part_building_id=part->id;prev=part->id;
 }
 city_finance_treasury_add(1000-city_finance_treasury());map_routing_update_land();
 if(blocked==1){building_storage_toggle_permission(BUILDING_STORAGE_PERMISSION_TRADERS,b);assert(!mp_transport_begin(1,RESOURCE_POTTERY,3));return id;}
 assert(mp_transport_begin(1,RESOURCE_POTTERY,3));
 unsigned int caravan=0;for(unsigned int i=1;i<figure_count();i++)if(figure_get(i)->mp_contract_id==1)caravan=i;
 assert(caravan);figure *f=figure_get(caravan);int initial_x=f->x,moved=0,target=0,ticks=0;
 assert(!mp_transport_validate(1,id,RESOURCE_POTTERY,3));
 while(ticks++<4000 && mp_transport_status(1,&target)!=3){
  if(blocked==2 && ticks==31)break;
  figure_trade_caravan_action(f);if(f->x!=initial_x)moved=1;
  if(mp_transport_status(1,&target)==4){fprintf(stderr,"transport failed at %d,%d dir %d action %d\n",f->x,f->y,f->direction,f->action_state);return -1;}
 }
 if(blocked==2){
  assert(moved && mp_transport_status(1,&target)==1);
  char path[2048];snprintf(path,sizeof(path),"%s/position.json",out);FILE *pos=fopen(path,"w");assert(pos);
  fprintf(pos,"{\"x\":%d,\"y\":%d,\"progress\":%d,\"contract\":%u}",f->x,f->y,f->progress_on_tile,f->mp_contract_id);fclose(pos);
  return id;
 }
 assert(moved && ticks<4000 && target==id);assert(mp_transport_validate(1,id,RESOURCE_POTTERY,3));
 assert(building_warehouse_get_amount(b,RESOURCE_POTTERY)==0 && city_finance_treasury()==1000);
 assert(!mp_transport_validate(78,id,RESOURCE_POTTERY,3));
 printf("CARAVAN WALK/UNLOAD PASS: %d ticks, (%d,39) to (%d,%d), unchanged stock and money\n",ticks,initial_x,f->x,f->y);
 char p[2048];snprintf(p,sizeof(p),"%s/transport.txt",out);FILE *file=fopen(p,"wb");assert(file);fprintf(file,"1 %d",id);fclose(file);
 return id;
}

static int transport_resume_fixture(const char *out){
 figure *f=0;int count=0;
 for(unsigned int i=1;i<figure_count();i++)if(figure_get(i)->mp_contract_id==1){f=figure_get(i);count++;}
 assert(count==1 && f);
 char path[2048];snprintf(path,sizeof(path),"%s/resume-before.json",out);FILE *pos=fopen(path,"w");assert(pos);
 fprintf(pos,"{\"x\":%d,\"y\":%d,\"progress\":%d,\"contract\":%u}",f->x,f->y,f->progress_on_tile,f->mp_contract_id);fclose(pos);
 unsigned int figures=figure_count();assert(f->mp_source?mp_transport_begin_source(1,RESOURCE_POTTERY,3):mp_transport_begin(1,RESOURCE_POTTERY,3));assert(figures==figure_count());
 int building_id=0,ticks=0;
 while(ticks++<4000 && mp_transport_status(1,&building_id)!=3)figure_trade_caravan_action(f);
 assert(ticks<4000 && (f->mp_source?mp_transport_validate_source(1,building_id,RESOURCE_POTTERY,3):mp_transport_validate(1,building_id,RESOURCE_POTTERY,3)));
 snprintf(path,sizeof(path),"%s/transport.txt",out);pos=fopen(path,"w");assert(pos);fprintf(pos,"1 %d",building_id);fclose(pos);
 return building_id;
}
/* Two partially full stores: one free cartload then two free cartloads. */
static int transport_split_fixture(const char *out,int midway,int source){
 for(int y=32;y<=46;y++)for(int x=30;x<=56;x++){
  int o=map_grid_offset(x,y);map_terrain_set(o,TERRAIN_CLEAR);map_building_set(o,0);
 }
 for(int x=32;x<=50;x++)map_terrain_set(map_grid_offset(x,39),TERRAIN_ROAD);
 city_map_set_entry_point(32,39);city_map_set_exit_point(32,39);
 int ids[2];
 for(int n=0;n<2;n++){
  int x=40+10*n;building *b=building_create(BUILDING_WAREHOUSE,x,40);ids[n]=b->id;int prev=b->id;
  b->state=BUILDING_STATE_IN_USE;b->has_road_access=1;b->storage_id=building_storage_create(b->id);
  map_building_set(map_grid_offset(x,40),b->id);map_terrain_set(map_grid_offset(x,40),TERRAIN_BUILDING);
  for(int i=0;i<8;i++){
   building *part=building_create(BUILDING_WAREHOUSE_SPACE,x+1+i%3,41+i/3);part->state=BUILDING_STATE_IN_USE;
   part->prev_part_building_id=prev;building_get(prev)->next_part_building_id=part->id;prev=part->id;
  }
  assert(building_warehouse_try_add_resource(building_get(ids[n]),RESOURCE_POTTERY,source?n+1:31-n,0)==(source?n+1:31-n));
 }
 city_finance_treasury_add(1000-city_finance_treasury());map_routing_update_land();
 assert(source?mp_transport_begin_source(1,RESOURCE_POTTERY,3):mp_transport_begin(1,RESOURCE_POTTERY,3));figure *f=0;
 for(unsigned int i=1;i<figure_count();i++)if(figure_get(i)->mp_contract_id==1)f=figure_get(i);
 assert(f);int target=0,ticks=0;
 while(ticks++<6000 && mp_transport_status(1,&target)!=3){
  figure_trade_caravan_action(f);
  assert(mp_transport_status(1,&target)!=4);
  if(midway && f->mp_stop_count==1)break;
 }
 assert(ticks<6000 && f->mp_stops[0].building_id==(unsigned int)ids[0] && f->mp_stops[0].quantity==1);
 assert(building_warehouse_get_amount(building_get(ids[0]),RESOURCE_POTTERY)==(source?1:31));
 assert(building_warehouse_get_amount(building_get(ids[1]),RESOURCE_POTTERY)==(source?2:30));
 assert(city_finance_treasury()==1000);
 if(midway){assert(f->mp_stop_count==1 && f->mp_leg_quantity==2 && f->action_state==MP_CARAVAN_WALK);}
 else if(source){assert(f->mp_source && f->mp_stop_count==2 && mp_transport_validate_source(1,ids[1],RESOURCE_POTTERY,3));assert(!mp_transport_validate(1,ids[1],RESOURCE_POTTERY,3));}
 else{
  assert(f->mp_stop_count==2 && f->mp_stops[1].quantity==2 && mp_transport_validate(1,ids[1],RESOURCE_POTTERY,3));
  building *first=building_get(ids[0]);
  building_storage_toggle_permission(BUILDING_STORAGE_PERMISSION_TRADERS,first);
  assert(!mp_transport_validate(1,ids[1],RESOURCE_POTTERY,3));
  assert(!mp_transport_deliver(1,RESOURCE_POTTERY,3));
  assert(building_warehouse_get_amount(building_get(ids[1]),RESOURCE_POTTERY)==(source?2:30));
  building_storage_toggle_permission(BUILDING_STORAGE_PERMISSION_TRADERS,first);
  assert(building_warehouse_try_add_resource(first,RESOURCE_POTTERY,1,0)==1);
  assert(!mp_transport_validate(1,ids[1],RESOURCE_POTTERY,3));
  assert(!mp_transport_deliver(1,RESOURCE_POTTERY,3));
  assert(building_warehouse_get_amount(building_get(ids[1]),RESOURCE_POTTERY)==(source?2:30));
  assert(building_warehouse_try_remove_resource(first,RESOURCE_POTTERY,1)==1);
  assert(mp_transport_validate(1,ids[1],RESOURCE_POTTERY,3));
 }
 char path[2048];snprintf(path,sizeof(path),"%s/transport.txt",out);FILE *fp=fopen(path,"w");assert(fp);fprintf(fp,"1 %d",ids[1]);fclose(fp);
 snprintf(path,sizeof(path),"%s/stops.json",out);fp=fopen(path,"w");assert(fp);
 fprintf(fp,"{\"first\":%d,\"second\":%d,\"visited\":%d,\"leg\":%d}",ids[0],ids[1],f->mp_stop_count,f->mp_leg_quantity);fclose(fp);
 return ids[0];
}
