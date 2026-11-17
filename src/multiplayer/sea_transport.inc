/* Included by transport.c: reuse contract validation/paired settlement, never NPC trade prices. */
enum { MP_DOCKER_RETURN=247 };
static map_point sea_exit(void){return scenario_map_has_river_exit()?scenario_map_river_exit():scenario_map_river_entry();}
static int sea_dock_valid(const figure *ship){
 if(!ship->building_id || ship->building_id>=building_count())return 0;
 building *dock=building_get(ship->building_id);map_point road;
 return building_dock_is_working(dock->id) && dock->has_water_access && dock->has_road_access &&
  building_distribution_is_good_accepted(dock,ship->resource_id) &&
  dock->data.dock.trade_ship_id==ship->id && map_has_road_access(dock->x,dock->y,3,&road);
}
static void sea_detach(figure *ship){
 if(ship->building_id && ship->building_id<building_count()){
  building *dock=building_get(ship->building_id);
  if(dock->data.dock.trade_ship_id==ship->id)dock->data.dock.trade_ship_id=0;
 }
 for(unsigned int i=1;i<figure_count();i++){
  figure *f=figure_get(i);
  if(f->type==FIGURE_DOCKER && f->mp_contract_id==ship->mp_contract_id)f->state=FIGURE_STATE_DEAD;
 }
}
static void sea_leave(figure *ship,int action){
 sea_detach(ship);map_point p=sea_exit();ship->destination_x=p.x;ship->destination_y=p.y;
 ship->action_state=action;ship->wait_ticks=0;figure_route_remove(ship);
}
void mp_transport_on_delete(figure *f){if(f->type==FIGURE_TRADE_SHIP && f->mp_contract_id)sea_detach(f);}
/* Do not take a berth while an NPC docker still carries a previous ship's goods. */
static int sea_dock_available(const building *dock){
 if(dock->data.dock.trade_ship_id)return 0;
 for(int i=0;i<3;i++){
  figure *f=figure_get(dock->data.distribution.cartpusher_ids[i]);
  if(f->id && f->type==FIGURE_DOCKER && !figure_is_dead(f) &&
   f->action_state!=FIGURE_ACTION_132_DOCKER_IDLING)return 0;
 }
 return 1;
}
static int sea_has_stores(map_point road,int resource,int quantity,int source){
 int total=0,stops=0;
 for(unsigned int i=1;i<building_count() && total<quantity && stops<32;i++){
  building *b=building_get(i);int amount=capacity_for(b,resource,source,1);map_point tile;
  if(amount<=0)continue;
  int access=b->type==BUILDING_WAREHOUSE?map_has_road_access_warehouse(b->x,b->y,&tile):map_has_road_access_granary(b->x,b->y,&tile);
  if(access && map_routing_citizen_can_travel_over_land(road.x,road.y,tile.x,tile.y,8,0)){total+=amount;stops++;}
 }
 return total>=quantity;
}
static int sea_preflight(int resource,int quantity,int source,map_point *chosen){
 if(resource<RESOURCE_MIN || resource>=RESOURCE_MAX || quantity<1 || quantity>32 || !scenario_map_has_river_entry())return 0;
 map_point entry=scenario_map_river_entry(),target={0},road;int selected=0;
 for(building *dock=building_first_of_type(BUILDING_DOCK);dock;dock=dock->next_of_type){
  if(!building_dock_is_working(dock->id) || !dock->has_water_access || !dock->has_road_access || !sea_dock_available(dock) ||
   !building_distribution_is_good_accepted(dock,resource) || !map_has_road_access(dock->x,dock->y,3,&road))continue;
  building_dock_get_ship_request_tile(dock,SHIP_DOCK_REQUEST_1_DOCKING,&target);
  map_routing_calculate_distances_water_boat(entry.x,entry.y);
  if(map_routing_distance(map_grid_offset(target.x,target.y))<=0)continue;
  map_point exit=sea_exit();if(map_routing_distance(map_grid_offset(exit.x,exit.y))<=0)continue;
  if(!sea_has_stores(road,resource,quantity,source))continue;
  selected=dock->id;break;
 }
 if(chosen)*chosen=target;return selected;
}
int mp_transport_begin_sea(unsigned int contract,int resource,int quantity,int source){
 if(!contract)return 0;
 figure *old=find(contract);if(old)return old->type==FIGURE_TRADE_SHIP && old->resource_id==resource && old->loads_sold_or_carrying==quantity && old->mp_source==source;
 map_point entry=scenario_map_river_entry(),target={0};int selected=sea_preflight(resource,quantity,source,&target);
 if(!selected)return 0;
 int id=figure_create_trade_ship(entry.x,entry.y,0);if(!id)return 0;
 figure *ship=figure_get(id);ship->mp_contract_id=contract;ship->mp_source=source;ship->resource_id=resource;
 ship->loads_sold_or_carrying=quantity;ship->building_id=selected;ship->destination_building_id=selected;
 ship->destination_x=target.x;ship->destination_y=target.y;ship->action_state=MP_CARAVAN_WALK;ship->is_boat=1;ship->wait_ticks=0;
 building_get(selected)->data.dock.trade_ship_id=id;return 1;
}
static int sea_action(figure *ship){
 if(ship->action_state==FIGURE_ACTION_150_ATTACK || ship->action_state==FIGURE_ACTION_149_CORPSE){sea_detach(ship);return 0;}
 int leaving=ship->action_state==MP_CARAVAN_EXIT || ship->action_state==MP_CARAVAN_DEPART || ship->action_state==MP_CARAVAN_DEPARTED;
 if(!leaving && ship->action_state!=MP_CARAVAN_FAILED && !sea_dock_valid(ship)){
  sea_detach(ship);ship->action_state=MP_CARAVAN_FAILED;
 }
 if(ship->action_state==MP_CARAVAN_FAILED || ship->action_state==MP_CARAVAN_READY || ship->action_state==MP_CARAVAN_DEPARTED)return 1;
 if(ship->action_state==MP_CARAVAN_UNLOAD){
  figure *worker=0;
  for(unsigned int i=1;i<figure_count();i++){figure *f=figure_get(i);if(f->type==FIGURE_DOCKER && f->mp_contract_id==ship->mp_contract_id && !figure_is_dead(f)){worker=f;break;}}
  if(!worker || worker->action_state==MP_CARAVAN_FAILED || worker->action_state==FIGURE_ACTION_150_ATTACK || worker->action_state==FIGURE_ACTION_149_CORPSE){sea_detach(ship);ship->action_state=MP_CARAVAN_FAILED;return 1;}
  if(worker->action_state==MP_CARAVAN_READY){
   ship->mp_stop_count=worker->mp_stop_count;memcpy(ship->mp_stops,worker->mp_stops,sizeof(ship->mp_stops));
   ship->destination_building_id=worker->destination_building_id;ship->action_state=MP_CARAVAN_READY;
  }
  return 1;
 }
 figure_movement_move_ticks(ship,1);
 if(ship->direction==DIR_FIGURE_AT_DESTINATION){
  if(ship->action_state==MP_CARAVAN_EXIT)ship->state=FIGURE_STATE_DEAD;
  else if(ship->action_state==MP_CARAVAN_DEPART)ship->action_state=MP_CARAVAN_DEPARTED;
  else{
   building *dock=building_get(ship->building_id);map_point road;
   if(!map_has_road_access(dock->x,dock->y,3,&road)){sea_detach(ship);ship->action_state=MP_CARAVAN_FAILED;return 1;}
   figure *worker=figure_create(FIGURE_DOCKER,road.x,road.y,DIR_0_TOP);
   if(!worker->id){sea_detach(ship);ship->action_state=MP_CARAVAN_FAILED;return 1;}
   worker->building_id=dock->id;worker->mp_contract_id=ship->mp_contract_id;worker->mp_source=ship->mp_source;
   worker->source_x=road.x;worker->source_y=road.y;worker->resource_id=ship->resource_id;
   worker->loads_sold_or_carrying=ship->loads_sold_or_carrying;worker->terrain_usage=TERRAIN_USAGE_ROADS_HIGHWAY;
   if(!next_stop(worker)){worker->action_state=MP_CARAVAN_FAILED;}
   ship->action_state=MP_CARAVAN_UNLOAD;
  }
 }else if(ship->direction==DIR_FIGURE_LOST || (ship->direction==DIR_FIGURE_REROUTE && ++ship->wait_ticks>120)){
  sea_detach(ship);if(ship->action_state==MP_CARAVAN_EXIT)ship->state=FIGURE_STATE_DEAD;else ship->action_state=MP_CARAVAN_FAILED;
 }else if(ship->direction==DIR_FIGURE_REROUTE)figure_route_remove(ship);
 return 1;
}
int mp_transport_docker_action(figure *f){
 if(!f->mp_contract_id)return 0;
 if(f->action_state==FIGURE_ACTION_150_ATTACK || f->action_state==FIGURE_ACTION_149_CORPSE)return 0;
 figure *ship=find(f->mp_contract_id);
 if(!ship || figure_is_dead(ship) || ship->type!=FIGURE_TRADE_SHIP || !sea_dock_valid(ship)){f->state=FIGURE_STATE_DEAD;return 1;}
 if(f->action_state==MP_CARAVAN_READY || f->action_state==MP_CARAVAN_FAILED)return 1;
 if(f->action_state!=MP_DOCKER_RETURN && capacity_for(building_get(f->destination_building_id),f->resource_id,f->mp_source,1)<f->mp_leg_quantity){f->action_state=MP_CARAVAN_FAILED;return 1;}
 if(f->action_state==MP_CARAVAN_UNLOAD){
  if(++f->wait_ticks<10*f->mp_leg_quantity)return 1;
  if(f->mp_stop_count>=32){f->action_state=MP_CARAVAN_FAILED;return 1;}
  int n=f->mp_stop_count++;f->mp_stops[n].building_id=f->destination_building_id;f->mp_stops[n].quantity=f->mp_leg_quantity;
  if(planned(f)==f->loads_sold_or_carrying){f->destination_x=f->source_x;f->destination_y=f->source_y;f->action_state=MP_DOCKER_RETURN;figure_route_remove(f);f->wait_ticks=0;}
  else if(!next_stop(f))f->action_state=MP_CARAVAN_FAILED;
  return 1;
 }
 figure_movement_move_ticks(f,1);
 if(f->direction==DIR_FIGURE_AT_DESTINATION){f->action_state=f->action_state==MP_DOCKER_RETURN?MP_CARAVAN_READY:MP_CARAVAN_UNLOAD;f->wait_ticks=0;}
 else if(f->direction==DIR_FIGURE_LOST || (f->direction==DIR_FIGURE_REROUTE && ++f->wait_ticks>120))f->action_state=MP_CARAVAN_FAILED;
 else if(f->direction==DIR_FIGURE_REROUTE)figure_route_remove(f);
 return 1;
}
