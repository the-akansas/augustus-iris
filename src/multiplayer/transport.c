#include "route_post.h"
#include "post_logistics.h"
#include "platform/windows_paths.h"
#include "mailbox_publish.h"
#include <SDL.h>
#include "map/routing_terrain.h"
#include "transport.h"
#include "clock.h"
#include "building/building.h"
#include "building/state.h"
#include "building/storage.h"
#include "building/warehouse.h"
#include "building/granary.h"
#include "city/map.h"
#include "core/calc.h"
#include "figure/movement.h"
#include "figure/route.h"
#include "figuretype/trader.h"
#include "map/routing.h"
#include "map/road_access.h"
#include "building/dock.h"
#include "building/market.h"
#include "scenario/map.h"
#include "map/grid.h"
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#ifdef _WIN32
#include <windows.h>
#endif
#define MP_TRANSPORT_LIMIT 64
typedef struct {unsigned id,post,generation;int resource,quantity,source,failed,started,homed;} transport_slot;
static transport_slot slots[MP_TRANSPORT_LIMIT];
static unsigned int seen_contract;
static int creation_failed;
/* Advisory catalog only. Native pickup/delivery still validate live roads and stock. */
typedef struct {unsigned generation,revision;int rx,ry,ex,ey,xx,xy,known,available;} post_route_cache;
static post_route_cache *post_routes;
static unsigned post_routes_count,post_route_cursor=1;
static void post_catalog_reset(void){free(post_routes);post_routes=0;post_routes_count=0;post_route_cursor=1;}

/* These are process-local hints, never authoritative after a SAV/room change. */
void mp_transport_reset(void){mp_route_reset();mp_post_logistics_reset();post_catalog_reset();seen_contract=0;creation_failed=0;memset(slots,0,sizeof(slots));}
static int tagged(const figure *f){return (f->type==FIGURE_TRADE_CARAVAN || f->type==FIGURE_TRADE_SHIP) && f->mp_contract_id!=0;}
static figure *find(unsigned int contract){
 for(unsigned int i=1;i<figure_count();i++){figure *f=figure_get(i);if(tagged(f) && f->mp_contract_id==contract)return f;}
 return 0;
}
static int capacity_for(building *b,int resource,int source,int sea){
 if(!sea && b->type==BUILDING_PLAYER_TRADE_POST)return b->state==BUILDING_STATE_IN_USE && b->has_road_access && !b->has_plague?(source?b->resources[resource]:mp_post_space(b)):0;
 if(b->state!=BUILDING_STATE_IN_USE || b->has_plague || !b->has_road_access ||
  !building_storage_get_permission(sea?BUILDING_STORAGE_PERMISSION_DOCK:BUILDING_STORAGE_PERMISSION_TRADERS,b))return 0;
 if(b->type==BUILDING_WAREHOUSE)return source?building_warehouse_get_amount(b,resource):building_warehouse_maximum_receptible_amount(b,resource);
 if(b->type==BUILDING_GRANARY && resource_is_food(resource))return source?building_granary_get_amount(b,resource):building_granary_maximum_receptible_amount(b,resource);
 return 0;
}
static int planned(const figure *f){
 int total=0;for(int i=0;i<f->mp_stop_count;i++)total+=f->mp_stops[i].quantity;return total;
}
static int next_stop(figure *f){
 int remaining=f->loads_sold_or_carrying-planned(f);
 if(remaining<=0 || f->mp_stop_count>=32)return 0;
 int best=0,distance=100000,quantity=0;map_point target={0};
 for(unsigned int i=1;i<building_count();i++){
  if(f->type==FIGURE_TRADE_CARAVAN && f->building_id && i!=f->building_id)continue;
  int visited=0;for(int n=0;n<f->mp_stop_count;n++)if(f->mp_stops[n].building_id==i)visited=1;
  if(visited)continue;
  building *b=building_get(i);int available=capacity_for(b,f->resource_id,f->mp_source,f->type==FIGURE_DOCKER);if(available<=0)continue;
  map_point road;
  if(f->type==FIGURE_TRADE_CARAVAN && f->building_id && (b->type!=BUILDING_PLAYER_TRADE_POST || b->created_sequence!=f->mp_stops[31].building_id || available<remaining))continue;
  int access=b->type==BUILDING_PLAYER_TRADE_POST?map_has_road_access(b->x,b->y,b->size,&road):b->type==BUILDING_WAREHOUSE?map_has_road_access_warehouse(b->x,b->y,&road):map_has_road_access_granary(b->x,b->y,&road);
  if(!access || !map_routing_citizen_can_travel_over_land(f->x,f->y,road.x,road.y,8,0))continue;
  int d=calc_maximum_distance(f->x,f->y,road.x,road.y);
  if(d<distance){best=i;target=road;distance=d;quantity=available<remaining?available:remaining;}
 }
 if(!best)return 0;
 f->destination_building_id=best;f->destination_x=target.x;f->destination_y=target.y;
 f->mp_leg_quantity=quantity;f->action_state=MP_CARAVAN_WALK;f->wait_ticks=0;figure_route_remove(f);
 return 1;
}
static int post_road(unsigned id,unsigned generation,map_point *road){
 if(!id || id>=building_count())return 0;
 building *b=building_get(id);
 return b->type==BUILDING_PLAYER_TRADE_POST && b->state==BUILDING_STATE_IN_USE &&
  b->created_sequence==generation && !b->has_plague &&
  map_has_road_access(b->x,b->y,b->size,road);
}
/* A terrain change anywhere re-checks every post over a few frames. Until its turn
 * comes a post keeps its last answer: reporting "no road" for those frames made the
 * room drop the post's waiting orders whenever the player built something. */
static int catalog_last(post_route_cache *c,building *b,map_point road,const map_tile *entry,const map_tile *exit){
 return c->known && c->generation==b->created_sequence &&
 c->rx==road.x && c->ry==road.y && c->ex==entry->x && c->ey==entry->y && c->xx==exit->x && c->xy==exit->y;
}
static void post_catalog(const char *dir){
 unsigned count=building_count();
 if(count>post_routes_count){
  post_route_cache *next=realloc(post_routes,count*sizeof(*next));if(!next)return;
  memset(next+post_routes_count,0,(count-post_routes_count)*sizeof(*next));post_routes=next;post_routes_count=count;
 }
 const map_tile *entry=city_map_entry_point(),*exit=city_map_exit_point();
 Uint64 start=SDL_GetPerformanceCounter(),frequency=SDL_GetPerformanceFrequency();
 /* Round-robin expensive route checks: one pair at a time, yielding after 2ms.
    A post never checked yet is unavailable; a checked one keeps its last answer until re-checked. */
 for(unsigned checked=1;checked<count;checked++){
  if(post_route_cursor>=count)post_route_cursor=1;
  unsigned i=post_route_cursor++;building *b=building_get(i);map_point road;
  if(b->type!=BUILDING_PLAYER_TRADE_POST || b->state!=BUILDING_STATE_IN_USE ||
     !post_road(i,b->created_sequence,&road))continue;
  post_route_cache *c=&post_routes[i];
  /* Refresh in rotation even without terrain changes: combat can block a route. */
  c->available=map_routing_citizen_can_travel_over_land(entry->x,entry->y,road.x,road.y,8,0) &&
   map_routing_citizen_can_travel_over_land(road.x,road.y,exit->x,exit->y,8,0);
  c->generation=b->created_sequence;c->revision=map_routing_citizen_revision();c->rx=road.x;c->ry=road.y;
  c->ex=entry->x;c->ey=entry->y;c->xx=exit->x;c->xy=exit->y;c->known=1;
  if((SDL_GetPerformanceCounter()-start)*1000>=frequency*2)break;
 }
 size_t capacity=(size_t)count*48+1,used=0;char *text=malloc(capacity);if(!text)return;
 for(unsigned i=1;i<count;i++){
  building *b=building_get(i);if(b->type!=BUILDING_PLAYER_TRADE_POST || b->state!=BUILDING_STATE_IN_USE)continue;
  map_point road;int available=post_road(i,b->created_sequence,&road) &&
   catalog_last(&post_routes[i],b,road,entry,exit) && post_routes[i].available;
  int n=snprintf(text+used,capacity-used,"%u %u %d\n",i,b->created_sequence,available);
  if(n<0 || (size_t)n>=capacity-used){free(text);return;}used+=(size_t)n;
 }
 mp_publish_text(dir,"fleet-posts",text,used);
 used=0;
 for(unsigned i=1;i<count;i++){
  building *b=building_get(i);if(b->type!=BUILDING_PLAYER_TRADE_POST || b->state!=BUILDING_STATE_IN_USE)continue;
  int n=snprintf(text+used,capacity-used,"%u %u %d\n",i,b->created_sequence,b->subtype.orientation);
  if(n<0 || (size_t)n>=capacity-used){free(text);return;}used+=(size_t)n;
 }
 mp_publish_text(dir,"route-posts",text,used);
 used=0;
 for(unsigned i=1;i<count;i++){
  building *b=building_get(i);if(b->type!=BUILDING_PLAYER_TRADE_POST || b->state!=BUILDING_STATE_IN_USE)continue;
  map_point road;int reason=b->has_plague?5:!post_road(i,b->created_sequence,&road)?2:
   !catalog_last(&post_routes[i],b,road,entry,exit)?3:!post_routes[i].available?4:0;
  int n=snprintf(text+used,capacity-used,"%u %u %d %d\n",i,b->created_sequence,b->num_workers,reason);
  if(n<0 || (size_t)n>=capacity-used){free(text);return;}used+=n;
 }
 mp_publish_text(dir,"post-readiness",text,used);free(text);
}
static unsigned source_post,source_generation;
static int begin(unsigned int contract,int resource,int quantity,int source){
 if(!contract || resource<RESOURCE_MIN || resource>=RESOURCE_MAX || quantity<1 || quantity>32)return 0;
 figure *old=find(contract);if(old)return old->type==FIGURE_TRADE_CARAVAN && !figure_is_dead(old) && old->resource_id==resource && old->loads_sold_or_carrying==quantity && old->mp_source==source;
 const map_tile *entry=city_map_entry_point();
 map_point start={entry->x,entry->y};
 if(source && source_post && (!post_road(source_post,source_generation,&start)))return 0;
 int id=figure_create_trade_caravan(start.x,start.y,0);if(!id)return 0;
 figure *f=figure_get(id);f->mp_stop_count=0;f->mp_contract_id=contract;f->mp_source=source;
 f->building_id=source_post;f->mp_stops[31].building_id=source_generation;
 f->resource_id=resource;f->loads_sold_or_carrying=quantity;
 if(next_stop(f))return 1;
 if(!source && source_post){f->action_state=MP_CARAVAN_WAIT;return 1;}
 f->state=FIGURE_STATE_DEAD;return 0;
}
int mp_transport_begin(unsigned int contract,int resource,int quantity){return begin(contract,resource,quantity,0);}
int mp_transport_begin_source(unsigned int contract,int resource,int quantity){return begin(contract,resource,quantity,1);}
#include "sea_transport.inc"
int mp_transport_status(unsigned int contract,int *building_id){
 figure *f=find(contract);*building_id=0;
 if(!f || figure_is_dead(f) || f->action_state==MP_CARAVAN_FAILED)return 4;
 *building_id=f->destination_building_id;
 if(f->action_state==MP_CARAVAN_HOME_READY)return 8;
 if(f->action_state==MP_CARAVAN_READY)return 3;
 if(f->action_state==MP_CARAVAN_DEPARTED)return 5;
 if(f->action_state==MP_CARAVAN_UNLOAD)return 2;
 return 1;
}
static int validate(unsigned int contract,int id,int resource,int quantity,int source){
 figure *f=find(contract);
 if(f && f->type==FIGURE_TRADE_SHIP && !sea_dock_valid(f))return 0;
 if(!f || f->mp_source!=source || figure_is_dead(f) || f->action_state!=MP_CARAVAN_READY ||
  f->destination_building_id!=(unsigned int)id || f->resource_id!=resource || f->loads_sold_or_carrying!=quantity ||
  f->x!=f->destination_x || f->y!=f->destination_y || !f->mp_stop_count || f->mp_stop_count>32 || planned(f)!=quantity)return 0;
 for(int i=0;i<f->mp_stop_count;i++){
  unsigned int target=f->mp_stops[i].building_id;int amount=f->mp_stops[i].quantity;
  if(!target || target>=building_count() || !amount || amount>32 || capacity_for(building_get(target),resource,f->mp_source,f->type==FIGURE_TRADE_SHIP)<amount)return 0;
  if(f->type==FIGURE_TRADE_CARAVAN && f->building_id && (target!=f->building_id || building_get(target)->created_sequence!=f->mp_stops[31].building_id))return 0;
  for(int j=0;j<i;j++)if(f->mp_stops[j].building_id==target)return 0;
 }
 return f->mp_stops[f->mp_stop_count-1].building_id==f->destination_building_id;
}
int mp_transport_validate(unsigned int c,int id,int r,int q){return validate(c,id,r,q,0);}
int mp_transport_validate_source(unsigned int c,int id,int r,int q){return validate(c,id,r,q,1);}
int mp_transport_collect(unsigned int contract,int resource,int quantity){
 figure *f=find(contract);
 if(!f || !validate(contract,f->destination_building_id,resource,quantity,1))return 0;
 for(int i=0;i<f->mp_stop_count;i++){
  building *b=building_get(f->mp_stops[i].building_id);int qty=f->mp_stops[i].quantity;
  int removed;if(b->type==BUILDING_PLAYER_TRADE_POST){removed=b->resources[resource]>=qty?qty:0;b->resources[resource]-=removed;}
  else removed=b->type==BUILDING_WAREHOUSE?building_warehouse_try_remove_resource(b,resource,qty):building_granary_try_remove_resource(b,resource,qty);
  if(removed!=qty)return 0;
 }
 return quantity;
}
int mp_transport_deliver(unsigned int contract,int resource,int quantity){
 figure *f=find(contract);
 if(!f || !mp_transport_validate(contract,f->destination_building_id,resource,quantity))return 0;
 for(int i=0;i<f->mp_stop_count;i++){
  building *b=building_get(f->mp_stops[i].building_id);int qty=f->mp_stops[i].quantity;
  int added=b->type==BUILDING_PLAYER_TRADE_POST?mp_post_add(b,resource,qty):b->type==BUILDING_WAREHOUSE?building_warehouse_try_add_resource(b,resource,qty,1):building_granary_try_add_resource(b,resource,qty,0,1);
  if(added!=qty)return 0; /* Worker output is disposable until the entire pair commits. */
 }
 return quantity;
}
void mp_transport_release(unsigned int contract){
 figure *f=find(contract);if(!f || figure_is_dead(f) || f->action_state==MP_CARAVAN_EXIT || f->action_state==MP_CARAVAN_EXITED)return;
 if(f->type==FIGURE_TRADE_SHIP){sea_leave(f,MP_CARAVAN_EXIT);return;}
 if(f->mp_source && f->action_state==MP_CARAVAN_DEPARTED){f->state=FIGURE_STATE_DEAD;return;}
 f->loads_sold_or_carrying=0;
 const map_tile *exit=city_map_exit_point();f->destination_x=exit->x;f->destination_y=exit->y;
 f->action_state=MP_CARAVAN_EXIT;f->wait_ticks=0;figure_route_remove(f);
}
void mp_transport_depart(unsigned int contract){
 figure *f=find(contract);if(!f || !f->mp_source || figure_is_dead(f) || f->action_state==MP_CARAVAN_DEPART || f->action_state==MP_CARAVAN_DEPARTED || f->action_state==MP_CARAVAN_FAILED)return;
 if(f->action_state!=MP_CARAVAN_READY && f->action_state!=MP_CARAVAN_EXIT)return;
 if(f->type==FIGURE_TRADE_SHIP){sea_leave(f,MP_CARAVAN_DEPART);return;}
 const map_tile *exit=city_map_exit_point();f->destination_x=exit->x;f->destination_y=exit->y;
 f->action_state=MP_CARAVAN_DEPART;f->wait_ticks=0;figure_route_remove(f);
}
int mp_transport_validate_departed(unsigned int contract,int resource,int quantity){
 figure *f=find(contract);const map_tile *exit=city_map_exit_point();
 if(f && f->type==FIGURE_TRADE_SHIP){map_point p=sea_exit();return f->mp_source==1 && !figure_is_dead(f) && f->action_state==MP_CARAVAN_DEPARTED && f->resource_id==resource && f->loads_sold_or_carrying==quantity && f->x==p.x && f->y==p.y;}
 return f && f->mp_source==1 && !figure_is_dead(f) && f->action_state==MP_CARAVAN_DEPARTED && f->resource_id==resource && f->loads_sold_or_carrying==quantity && f->x==exit->x && f->y==exit->y && f->destination_x==exit->x && f->destination_y==exit->y;
}
/* Orders sharing a post travel as one caravan: only the lowest contract of a
 * post's caravans (per direction) is drawn, the rest walk with it unseen. */
static int shipment_follower(const figure *f){
 if(!f->building_id || f->type!=FIGURE_TRADE_CARAVAN)return 0;
 for(unsigned int i=1;i<figure_count();i++){
  const figure *g=figure_get(i);
  if(g==f || !tagged(g) || figure_is_dead(g) || g->type!=f->type || g->action_state==MP_CARAVAN_FAILED)continue;
  if(g->building_id==f->building_id && g->mp_source==f->mp_source && g->mp_contract_id<f->mp_contract_id)return 1;
 }
 return 0;
}
static int transport_action(figure *f);
int mp_transport_action(figure *f){
 int handled=transport_action(f);
 if(handled && tagged(f) && f->type==FIGURE_TRADE_CARAVAN && f->action_state!=MP_CARAVAN_HOME && f->action_state!=MP_CARAVAN_HOME_READY &&
  f->action_state!=MP_CARAVAN_DEPARTED && f->action_state!=MP_CARAVAN_EXITED && !figure_is_dead(f))f->is_ghost=shipment_follower(f);
 else if(!handled && tagged(f))f->is_ghost=0; /* a caravan under attack is always visible */
 return handled;
}
static int transport_action(figure *f){
 if(!tagged(f))return 0;
 if(f->type==FIGURE_TRADE_SHIP)return sea_action(f);
 if(f->action_state==MP_CARAVAN_HOME || f->action_state==MP_CARAVAN_HOME_READY || f->action_state==MP_CARAVAN_DEPARTED || f->action_state==MP_CARAVAN_EXITED){
  /* Saveable exit proof stays hidden until the server acknowledges it. */
  f->is_ghost=1;f->image_offset=0;return 1;
 }
 if(f->action_state==MP_CARAVAN_WAIT){
  building*b=building_get(f->building_id);
  if(b->type!=BUILDING_PLAYER_TRADE_POST || b->state!=BUILDING_STATE_IN_USE || b->created_sequence!=f->mp_stops[31].building_id){f->action_state=MP_CARAVAN_FAILED;return 1;}
  f->image_offset=0;next_stop(f);return 1;
 }
 /* Let ordinary combat/corpse handling run. The contract reports a failed courier. */
 if(f->action_state==FIGURE_ACTION_150_ATTACK || f->action_state==FIGURE_ACTION_149_CORPSE)return 0;
 if(f->action_state==MP_CARAVAN_FAILED || f->action_state==MP_CARAVAN_READY || f->action_state==MP_CARAVAN_DEPARTED){f->image_offset=0;return 1;}
 if(f->action_state!=MP_CARAVAN_EXIT && f->action_state!=MP_CARAVAN_DEPART && capacity_for(building_get(f->destination_building_id),f->resource_id,f->mp_source,0)<f->mp_leg_quantity){
  if(!f->mp_source && building_get(f->building_id)->type==BUILDING_PLAYER_TRADE_POST){f->action_state=MP_CARAVAN_WAIT;f->mp_stop_count=0;figure_route_remove(f);}else f->action_state=MP_CARAVAN_FAILED;return 1;
 }
 if(f->action_state==MP_CARAVAN_UNLOAD){
  f->image_offset=0;if(++f->wait_ticks>=10*f->mp_leg_quantity){
   f->wait_ticks=0;
   if(f->mp_stop_count>=32 || !f->mp_leg_quantity){f->action_state=MP_CARAVAN_FAILED;return 1;}
   int index=f->mp_stop_count++;f->mp_stops[index].building_id=f->destination_building_id;f->mp_stops[index].quantity=f->mp_leg_quantity;
   if(planned(f)==f->loads_sold_or_carrying)f->action_state=MP_CARAVAN_READY;
   else if(!next_stop(f))f->action_state=MP_CARAVAN_FAILED;
  }
  return 1;
 }
 figure_movement_move_ticks(f,1);
 if(f->direction==DIR_FIGURE_AT_DESTINATION){
  if(f->action_state==MP_CARAVAN_EXIT){f->action_state=MP_CARAVAN_EXITED;f->is_ghost=1;}
  else if(f->action_state==MP_CARAVAN_DEPART){f->action_state=MP_CARAVAN_DEPARTED;f->is_ghost=1;}
  else{f->action_state=MP_CARAVAN_UNLOAD;f->wait_ticks=0;}
 }else if(f->direction==DIR_FIGURE_REROUTE){
  figure_route_remove(f);
  if(++f->wait_ticks>120){if(f->action_state==MP_CARAVAN_EXIT)f->state=FIGURE_STATE_DEAD;else f->action_state=MP_CARAVAN_FAILED;}
 }else if(f->direction==DIR_FIGURE_LOST){
  if(f->action_state==MP_CARAVAN_EXIT)f->state=FIGURE_STATE_DEAD;else f->action_state=MP_CARAVAN_FAILED;
 }
 return 1;
}
/* Called only for a terminal, financially settled manifest row. Retire an
 * empty courier before reporting recovery; never recreate it on a retry. */
static int retire_home(unsigned contract){
 for(unsigned i=1;i<figure_count();i++){
  figure *v=figure_get(i);if(tagged(v) && v->mp_contract_id==contract){
   figure_route_remove(v);v->loads_sold_or_carrying=0;v->state=FIGURE_STATE_DEAD;v->mp_contract_id=0;
  }
 }
 return 9;
}
static int caravan_home(unsigned contract,unsigned post,unsigned generation){
 /* Only rejected, financially settled orders use this legacy cleanup acknowledgement. */
 retire_home(contract);return 8;
}
static int caravan_receiver_exit(unsigned contract){
 figure*f=find(contract);
 if(!f || figure_is_dead(f))return 11; /* Settled legacy save or retired courier: no respawn. */
 if(f->mp_source || f->type!=FIGURE_TRADE_CARAVAN)return 4;
 if(f->action_state==MP_CARAVAN_EXITED){f->is_ghost=1;return 10;}
 if(f->action_state==MP_CARAVAN_FAILED || f->action_state==FIGURE_ACTION_149_CORPSE){retire_home(contract);return 11;}
 mp_transport_release(contract);return 1;
}
/* Full bounded manifest, parsed before any mutation. A malformed or partially
 * published file cannot dismiss another contract's courier. */
static int transport_many(const char *dir){
 char path[2048],tmp[2048];snprintf(path,sizeof(path),"%s/transport-list.txt",dir);
 FILE *f=fopen(path,"rb");if(!f)return 0;
 unsigned count=0;struct {unsigned id;int resource,quantity,stage,sea;unsigned post,generation;} rows[MP_TRANSPORT_LIMIT];
 if(fscanf(f,"%u",&count)!=1 || count>MP_TRANSPORT_LIMIT){fclose(f);return 1;}
 for(unsigned i=0;i<count;i++){
  if(fscanf(f,"%u %d %d %d %d %u %u",&rows[i].id,&rows[i].resource,&rows[i].quantity,&rows[i].stage,&rows[i].sea,&rows[i].post,&rows[i].generation)!=7 || !rows[i].id || rows[i].stage<1 || rows[i].stage>9 || rows[i].resource<RESOURCE_MIN || rows[i].resource>=RESOURCE_MAX || rows[i].quantity<1 || rows[i].quantity>32 || (rows[i].sea!=0 && rows[i].sea!=1)){fclose(f);return 1;}
  for(unsigned j=0;j<i;j++)if(rows[i].id==rows[j].id){fclose(f);return 1;}
 }
 int trailing;do{trailing=fgetc(f);}while(trailing==' ' || trailing=='\r' || trailing=='\n' || trailing=='\t');
 fclose(f);if(trailing!=EOF)return 1;
 for(unsigned j=0;j<MP_TRANSPORT_LIMIT;j++)if(slots[j].id){
  int keep=0;for(unsigned i=0;i<count;i++)if(rows[i].id==slots[j].id)keep=1;
  if(!keep)memset(&slots[j],0,sizeof(slots[j]));
 }
 for(unsigned j=1;j<figure_count();j++){
  figure *old=figure_get(j);if(!tagged(old))continue;
  int keep=0;for(unsigned i=0;i<count;i++)if(rows[i].id==old->mp_contract_id)keep=1;
  if(!keep){if(old->action_state==MP_CARAVAN_EXITED || old->action_state==MP_CARAVAN_DEPARTED || old->action_state==MP_CARAVAN_HOME_READY || old->action_state==MP_CARAVAN_HOME)retire_home(old->mp_contract_id);else mp_transport_release(old->mp_contract_id);}
 }
 char output[MP_TRANSPORT_LIMIT*128];size_t used=0;
 for(unsigned i=0;i<count;i++){
  unsigned id=rows[i].id;int stage=rows[i].stage,resource=rows[i].resource,quantity=rows[i].quantity,sea=rows[i].sea;
  transport_slot *slot=0;for(unsigned j=0;j<MP_TRANSPORT_LIMIT;j++)if(slots[j].id==id)slot=&slots[j];
  if(!slot)for(unsigned j=0;j<MP_TRANSPORT_LIMIT;j++)if(!slots[j].id){slot=&slots[j];break;}
  if(!slot)continue;
  if(!slot->id){
   slot->id=id;slot->resource=resource;slot->quantity=quantity;slot->source=stage==4;slot->post=rows[i].post;slot->generation=rows[i].generation;
   figure*existing=find(id);if(existing && !figure_is_dead(existing)){slot->started=1;slot->source=existing->mp_source;}
  }
  if(!slot->started && (stage==1 || stage==4)){
   slot->source=stage==4;
   building *p=building_get(rows[i].post);
   int waiting=!sea && p->type==BUILDING_PLAYER_TRADE_POST && p->state==BUILDING_STATE_IN_USE && p->created_sequence==rows[i].generation &&
    stage==4 && p->resources[resource]<quantity;
   if(!waiting){slot->started=1;
   source_post=rows[i].post;source_generation=rows[i].generation;
   slot->failed=!sea && !rows[i].post?1:!(sea?mp_transport_begin_sea(id,resource,quantity,stage==4):begin(id,resource,quantity,stage==4));
   source_post=source_generation=0;
   }
  }
  int building_id=0,status=4,departed=0;
  if(slot->resource==resource && slot->quantity==quantity && (stage==9 || (slot->post==rows[i].post && slot->generation==rows[i].generation))){
   if(stage==2){figure*v=find(id);if(v && v->mp_source && (v->action_state==MP_CARAVAN_DEPARTED || v->action_state==MP_CARAVAN_HOME || v->action_state==MP_CARAVAN_HOME_READY))retire_home(id);}
   if(stage==3)mp_transport_release(id);
   else if(stage==5)mp_transport_depart(id);
   status=(stage==6 || stage==7)?(sea_preflight(resource,quantity,stage==6,0)?6:7):!slot->started?1:slot->failed?4:mp_transport_status(id,&building_id);
   if(stage==8){status=slot->homed?slot->homed:caravan_home(id,rows[i].post,rows[i].generation);if(status==8 || status==9)slot->homed=status;}
   if(stage==9){status=slot->homed?slot->homed:caravan_receiver_exit(id);if(status==10 || status==11)slot->homed=status;}
   departed=stage==5 && status==5 && mp_transport_validate_departed(id,resource,quantity);
   if(stage==5 && status==5 && !departed)status=4;
  }
  int n=snprintf(output+used,sizeof(output)-used,"%u %d %d %d %d %d %d\n",id,status,building_id,resource,quantity,sea?3:2,departed);
  if(n<0 || (size_t)n>=sizeof(output)-used)return 1;used+=(size_t)n;
 }
 mp_publish_text(dir,"transport-states",output,used);
 return 1;
}
void mp_transport_poll(void){
 if(!mp_clock_active())return;
 const char *dir=getenv("AUGUSTUS_MP_BRIDGE");if(!dir)return;
 post_catalog(dir);
 mp_post_blocked_publish(dir);
 mp_post_load_publish(dir);
 if(transport_many(dir))return;
 char path[2048],tmp[2048];snprintf(path,sizeof(path),"%s/transport.txt",dir);
 FILE *fp=fopen(path,"rb");unsigned int id=0;int resource=0,quantity=0,stage=0,sea=0;
 if(!fp)return;int n=fscanf(fp,"%u %d %d %d %d",&id,&resource,&quantity,&stage,&sea);fclose(fp);if(n<4)return;
 for(unsigned int i=1;i<figure_count();i++){figure *old=figure_get(i);
  if(tagged(old) && old->mp_contract_id!=id)mp_transport_release(old->mp_contract_id);
 }
 if((stage==1 || stage==4 || stage==5 || stage==6 || stage==7) && id){
  if(stage==6 || stage==7){}
  else if(stage==5)mp_transport_depart(id);
  else if(id!=seen_contract){seen_contract=id;creation_failed=!(sea?mp_transport_begin_sea(id,resource,quantity,stage==4):begin(id,resource,quantity,stage==4));}
  int building_id=0;int status=(stage==6 || stage==7)?(sea_preflight(resource,quantity,stage==6,0)?6:7):stage!=5 && creation_failed?4:mp_transport_status(id,&building_id);
  /* Validate on the game thread, against the live figure. This used to
     require a whole-room SAV roundtrip just to check the same exit. */
  int departed=stage==5 && status==5 && mp_transport_validate_departed(id,resource,quantity);
  if(stage==5 && status==5 && !departed)status=4;
  snprintf(tmp,sizeof(tmp),"%s/transport-state.tmp",dir);fp=fopen(tmp,"wb");
  if(fp){fprintf(fp,"%u %d %d %d %d %d %d",id,status,building_id,resource,quantity,sea?3:2,departed);if(!fclose(fp)){
   snprintf(path,sizeof(path),"%s/transport-state.txt",dir);
#ifdef _WIN32
   augustus_move_file(tmp,path,MOVEFILE_REPLACE_EXISTING);
#else
   rename(tmp,path);
#endif
  }}
 }else if(stage==3 && id){mp_transport_release(id);}
}

int mp_transport_plan(unsigned c,unsigned target,int r,int q,int source,int sea,unsigned *targets,int *amounts) {
    figure *f=find(c);
    if(!f || (f->type==FIGURE_TRADE_SHIP)!=!!sea || !validate(c,target,r,q,source))return 0;
    for(int i=0;i<f->mp_stop_count;i++){targets[i]=f->mp_stops[i].building_id;amounts[i]=f->mp_stops[i].quantity;}
    return f->mp_stop_count;
}

