/* Inventory lives in building.resources; in-flight loads live in saved figures.
 * There is no off-thread inventory mutation and no invisible stock transfer. */
#include "post_logistics.h"
#include "mailbox_publish.h"
#include "transport.h"
#include "building/granary.h"
#include "building/warehouse.h"
#include "building/storage.h"
#include "figure/movement.h"
#include "figure/route.h"
#include "map/road_access.h"
#include "map/routing.h"
#include "core/calc.h"
#include "core/time.h"
typedef struct {unsigned id,generation,contract;int resource,quantity;} post_need;
static post_need post_needs[256];
static int post_need_count,post_need_valid;
static unsigned post_need_time;
static void post_blocked_reset(void);
void mp_post_logistics_reset(void){post_need_count=0;post_need_time=0;post_need_valid=0;post_blocked_reset();}
static void post_needs_read(void){
 unsigned now=time_get_millis();if(post_need_time && now-post_need_time<250)return;post_need_time=now;
 const char*dir=getenv("AUGUSTUS_MP_BRIDGE");if(!dir)return;
 char path[2048];snprintf(path,sizeof(path),"%s/post-demand.txt",dir);FILE*f=fopen(path,"rb");if(!f)return;
 post_need next[256];int count=0,ok=1;char line[256],extra;
 while(fgets(line,sizeof(line),f)){
  unsigned id,g,c=0;int r,q;
  int fields=sscanf(line,"%u %u %d %d %u %c",&id,&g,&r,&q,&c,&extra);
  if((fields!=4 && fields!=5) || count==256 || !id || r<RESOURCE_MIN || r>=RESOURCE_MAX || q<0 || q>32){ok=0;break;}
  next[count++]=(post_need){id,g,c,r,q};
 }
 if(ferror(f))ok=0;fclose(f);
 if(ok){post_need_valid=1;memcpy(post_needs,next,count*sizeof(post_need));post_need_count=count;}
}
int mp_post_demand(const building*b,int r){
 post_needs_read();int q=0;for(int i=0;i<post_need_count;i++)if(post_needs[i].id==b->id && post_needs[i].generation==b->created_sequence && post_needs[i].resource==r){
  int exported=0;
  if(post_needs[i].contract)for(unsigned j=1;j<figure_count();j++){
   const figure*f=figure_get(j);
   if(!figure_is_dead(f) && f->type==FIGURE_TRADE_CARAVAN && f->mp_source==1 &&
      f->mp_contract_id==post_needs[i].contract && f->building_id==b->id &&
      f->mp_stops[31].building_id==b->created_sequence && f->resource_id==r &&
      (f->action_state==MP_CARAVAN_DEPART || f->action_state==MP_CARAVAN_DEPARTED)){exported=1;break;}
  }
  if(!exported)q+=post_needs[i].quantity;
 }
 return q>32?32:q;
}
int mp_post_total(const building*b){int n=0;for(int r=RESOURCE_MIN;r<RESOURCE_MAX;r++)if(b->resources[r]>0)n+=b->resources[r];return n;}
int mp_post_space(const building*b){int n=32-mp_post_total(b);return n>0?n:0;}
int mp_post_add(building*b,int r,int q){
 if(b->type!=BUILDING_PLAYER_TRADE_POST || b->state!=BUILDING_STATE_IN_USE || r<RESOURCE_MIN || r>=RESOURCE_MAX || q<=0)return 0;
 int n=mp_post_space(b);if(n>q)n=q;b->resources[r]+=n;return n;
}
int mp_post_take(building*b,int r,int q){
 if(b->type!=BUILDING_PLAYER_TRADE_POST || b->state!=BUILDING_STATE_IN_USE || r<RESOURCE_MIN || r>=RESOURCE_MAX || q<=0)return 0;
 post_needs_read();if(!post_need_valid)return 0;
 int n=b->resources[r]-mp_post_demand(b,r);if(n<0)n=0;if(n>q)n=q;b->resources[r]-=n;return n;
}
int mp_post_city_stock(int r){int n=0;for(building*b=building_first_of_type(BUILDING_PLAYER_TRADE_POST);b;b=b->next_of_type)if(b->state==BUILDING_STATE_IN_USE)n+=b->resources[r];return n;}
static int post_cart(const figure*f){return f->type==FIGURE_WAREHOUSEMAN && f->mp_source==3 && !figure_is_dead(f);}
static int post_reserved(unsigned id,int r,int inbound,const figure*ignore){
 int n=0;for(unsigned i=1;i<figure_count();i++){figure*f=figure_get(i);if(f==ignore || figure_is_dead(f) || (r && f->resource_id!=r))continue;
  if(f->type==FIGURE_DEPOT_CART_PUSHER){
   if(inbound && f->destination_building_id==id && (f->action_state==FIGURE_ACTION_241_DEPOT_CART_PUSHER_HEADING_TO_DESTINATION || f->action_state==FIGURE_ACTION_242_DEPOT_CART_PUSHER_AT_DESTINATION))n+=f->loads_sold_or_carrying;
   continue;
  }
  if(!post_cart(f))continue;
  if(inbound && f->mp_stops[1].building_id==id)n+=f->loads_sold_or_carrying?f->loads_sold_or_carrying:f->mp_leg_quantity;
  if(!inbound && !f->loads_sold_or_carrying && f->mp_stops[0].building_id==id)n+=f->mp_leg_quantity;
 }return n;
}
int mp_post_inbound_need(const building*b,int r,const figure*ignore){
 int need=mp_post_demand(b,r)-b->resources[r]-post_reserved(b->id,r,1,ignore);
 int space=mp_post_space(b)-post_reserved(b->id,0,1,ignore);
 return need<0 || space<0?0:need<space?need:space;
}
static int post_access(building*b,map_point*p){
 if(b->state!=BUILDING_STATE_IN_USE || b->has_plague)return 0;
 if(b->type==BUILDING_WAREHOUSE)return map_has_road_access_warehouse(b->x,b->y,p);
 if(b->type==BUILDING_GRANARY)return map_has_road_access_granary(b->x,b->y,p);
 return b->type==BUILDING_PLAYER_TRADE_POST && map_has_road_access(b->x,b->y,b->size,p);
}
static int post_amount(building*b,int r){return b->type==BUILDING_PLAYER_TRADE_POST?b->resources[r]:building_storage_get_amount(b,r);}
static int post_capacity(building*b,int r){
 if(b->type==BUILDING_PLAYER_TRADE_POST)return mp_post_space(b);
 if(!building_storage_accepts_storage(b,r,0))return 0;
 return b->type==BUILDING_WAREHOUSE?building_warehouse_maximum_receptible_amount(b,r):
  b->type==BUILDING_GRANARY && resource_is_food(r)?building_granary_maximum_receptible_amount(b,r):0;
}
static int post_remove(building*b,int r,int q){return b->type==BUILDING_PLAYER_TRADE_POST?mp_post_take(b,r,q):b->type==BUILDING_GRANARY?building_granary_try_remove_resource(b,r,q):building_warehouse_try_remove_resource(b,r,q);}
static void post_destination(figure*f,building*b){map_point p;if(!post_access(b,&p))return;f->destination_building_id=b->id;f->destination_x=p.x;f->destination_y=p.y;figure_route_remove(f);}
static int post_start_cart(building*home,building*src,building*dst,int r,int q,unsigned*slot){
 map_point h,s,d;if(q<=0 || !post_access(home,&h) || !post_access(src,&s) || !post_access(dst,&d) ||
  !map_routing_citizen_can_travel_over_land(h.x,h.y,s.x,s.y,8,0) || !map_routing_citizen_can_travel_over_land(s.x,s.y,d.x,d.y,8,0))return 0;
 figure*f=figure_create(FIGURE_WAREHOUSEMAN,h.x,h.y,DIR_4_BOTTOM);if(!f->id)return 0;
 f->building_id=home->id;f->mp_source=3;f->resource_id=r;f->mp_leg_quantity=q>4?4:q;
 f->mp_stops[0].building_id=src->id;f->mp_stops[1].building_id=dst->id;
 f->mp_stops[2].building_id=src->created_sequence;f->mp_stops[3].building_id=dst->created_sequence;
 f->action_state=FIGURE_ACTION_50_WAREHOUSEMAN_CREATED;f->terrain_usage=TERRAIN_USAGE_ROADS;
 *slot=f->id;post_destination(f,src);return 1;
}
static int post_job(building*home,building*p,building*only,unsigned*slot){
 post_needs_read();if(!post_need_valid)return 0;
 /* Pass 0 empties: anything not reserved for an outgoing order (received,
  * cancelled or surplus goods) goes to any staffed store that accepts it, so
  * the next caravan finds room. Pass 1 fills the post for outgoing orders.
  * Emptying first keeps the 32-load post from blocking deliveries. */
 for(int pass=0;pass<2;pass++){
  for(int r=RESOURCE_MIN;r<RESOURCE_MAX;r++){
   int need=mp_post_demand(p,r)-p->resources[r]-post_reserved(p->id,r,1,0);
   int surplus=p->resources[r]-mp_post_demand(p,r)-post_reserved(p->id,r,0,0);
   if(pass==0?surplus<=0:need<=0)continue;
   building*best=0;int distance=100000,amount=0;
   for(unsigned i=1;i<building_count();i++){
    building*s=building_get(i);if(only && s!=only)continue;
    if(s->type!=BUILDING_WAREHOUSE && !(s->type==BUILDING_GRANARY && resource_is_food(r)))continue;
    map_point road;if(!s->num_workers || !post_access(s,&road))continue;
    /* Taking goods out of a store needs the trader permission; putting
     * goods in only follows the store's own accept settings. */
    if(pass==1 && !building_storage_get_permission(BUILDING_STORAGE_PERMISSION_TRADERS,s))continue;
    int q=pass==1?post_amount(s,r)-post_reserved(s->id,r,0,0):post_capacity(s,r)-post_reserved(s->id,r,1,0);
    if(pass==1){int space=mp_post_space(p)-post_reserved(p->id,0,1,0);if(q>space)q=space;if(q>need)q=need;}
    else if(q>surplus)q=surplus;
    int d=calc_maximum_distance(p->x,p->y,s->x,s->y);
    if(q>0 && d<distance){best=s;amount=q;distance=d;}
   }
   if(best && post_start_cart(home,pass==1?best:p,pass==1?p:best,r,amount,slot))return 1;
  }
 }
 return 0;
}
void mp_post_spawn(building*b){
 if(!mp_clock_active() || !b->has_road_access || b->has_plague)return;
 if(!b->storage_id)b->storage_id=building_storage_create(b->id);
 unsigned*slots[]={&b->figure_id,&b->figure_id4};
 for(int i=0;i<2;i++){figure*f=figure_get(*slots[i]);if(*slots[i] && post_cart(f) && f->building_id==b->id)continue;*slots[i]=0;post_job(b,b,0,slots[i]);}
}
int mp_post_supply_spawn(building*b){
 if(!mp_clock_active() || !b->num_workers)return 0;
 for(building*p=building_first_of_type(BUILDING_PLAYER_TRADE_POST);p;p=p->next_of_type)
  if(p->state==BUILDING_STATE_IN_USE && p->has_road_access && post_job(b,p,b,&b->figure_id))return 1;
 return 0;
}
/* A dedicated post must stay empty for trade. Report every post that holds
 * goods no outgoing order needs while no staffed store accepts them. The
 * bridge keeps a to-do notice up until the goods can leave. Unknown demand
 * (no valid instruction file) publishes nothing: never guess a reservation. */
static unsigned post_blocked_at;
/* Reported only after the condition has held for a while, and never while one
 * of the post's own carts is already carrying that resource out: emptying in
 * progress is not "no storage". */
#define POST_BLOCKED_HOLD_MS 5000
typedef struct {unsigned post;int resource;unsigned since;} post_blocked_entry;
static post_blocked_entry post_blocked_seen[64];
static int post_has_store(building*p,int r){
 for(unsigned i=1;i<building_count();i++){
  building*s=building_get(i);
  if(s->type!=BUILDING_WAREHOUSE && !(s->type==BUILDING_GRANARY && resource_is_food(r)))continue;
  map_point road;if(!s->num_workers || !post_access(s,&road))continue;
  if(post_capacity(s,r)-post_reserved(s->id,r,1,0)>0)return 1;
 }
 return 0;
}
static int post_emptying(const building*p,int r){
 for(unsigned i=1;i<figure_count();i++){
  const figure*f=figure_get(i);
  if(!post_cart(f) || f->resource_id!=r)continue;
  if(f->mp_stops[0].building_id==p->id && f->mp_stops[1].building_id!=p->id)return 1;
 }
 return 0;
}
static unsigned post_blocked_since(unsigned post,int r,unsigned now,int blocked){
 int free=-1;
 for(int i=0;i<64;i++){
  post_blocked_entry*e=&post_blocked_seen[i];
  if(e->post==post && e->resource==r){if(!blocked){e->post=0;return 0;}return e->since;}
  if(!e->post && free<0)free=i;
 }
 if(!blocked || free<0)return 0;
 post_blocked_seen[free]=(post_blocked_entry){post,r,now};return now;
}
static void post_blocked_reset(void){memset(post_blocked_seen,0,sizeof(post_blocked_seen));post_blocked_at=0;}
void mp_post_blocked_publish(const char*dir){
 unsigned now=time_get_millis();if(post_blocked_at && now-post_blocked_at<1000)return;post_blocked_at=now;
 post_needs_read();if(!post_need_valid)return;
 char text[2048];size_t used=0;
 for(building*p=building_first_of_type(BUILDING_PLAYER_TRADE_POST);p;p=p->next_of_type){
  if(p->state!=BUILDING_STATE_IN_USE)continue;
  for(int r=RESOURCE_MIN;r<RESOURCE_MAX;r++){
   int surplus=p->resources[r]-mp_post_demand(p,r)-post_reserved(p->id,r,0,0);
   int blocked=surplus>0 && !post_emptying(p,r) && !post_has_store(p,r);
   unsigned since=post_blocked_since(p->id,r,now?now:1,blocked);
   if(!blocked || now-since<POST_BLOCKED_HOLD_MS)continue;
   int n=snprintf(text+used,sizeof(text)-used,"%u %u %d %d\n",p->id,p->created_sequence,r,surplus);
   if(n<0 || (size_t)n>=sizeof(text)-used)break;used+=(size_t)n;
  }
 }
 mp_publish_text(dir,"post-blocked",text,used);
}
/* "post gen resource held inbound" for every resource a post holds or is being
 * sent. Inbound counts carts already bound for the post (going to a store or
 * carrying back), so the host waits while goods are on their way. */
void mp_post_load_publish(const char*dir){
 static unsigned last;unsigned now=time_get_millis();if(last && now-last<1000)return;last=now?now:1;
 char text[8192];size_t used=0;
 for(building*p=building_first_of_type(BUILDING_PLAYER_TRADE_POST);p;p=p->next_of_type){
  if(p->state!=BUILDING_STATE_IN_USE)continue;
  int inbound[RESOURCE_MAX]={0};
  for(unsigned i=1;i<figure_count();i++){
   const figure*f=figure_get(i);
   if(!post_cart(f) || f->mp_stops[1].building_id!=p->id || f->mp_stops[0].building_id==p->id)continue;
   if(f->resource_id>=RESOURCE_MIN && f->resource_id<RESOURCE_MAX)inbound[f->resource_id]+=f->loads_sold_or_carrying?f->loads_sold_or_carrying:f->mp_leg_quantity;
  }
  for(int r=RESOURCE_MIN;r<RESOURCE_MAX;r++){
   if(!p->resources[r] && !inbound[r])continue;
   int n=snprintf(text+used,sizeof(text)-used,"%u %u %d %d %d\n",p->id,p->created_sequence,r,p->resources[r],inbound[r]);
   if(n<0 || (size_t)n>=sizeof(text)-used)break;used+=(size_t)n;
  }
 }
 mp_publish_text(dir,"post-load",text,used);
}
int mp_post_cart_action(figure*f){
 if(f->mp_source!=3)return 0;
 if(f->action_state==FIGURE_ACTION_53_WAREHOUSEMAN_RETURNING_EMPTY){
  building*home=building_get(f->building_id);map_point h;
  if(!post_access(home,&h)){f->state=FIGURE_STATE_DEAD;return 1;}
  if(f->destination_building_id!=home->id || f->destination_x!=h.x || f->destination_y!=h.y)post_destination(f,home);
  if(f->x==h.x && f->y==h.y){f->state=FIGURE_STATE_DEAD;return 1;}
  figure_movement_move_ticks(f,1);return 1;
 }
 building*src=building_get(f->mp_stops[0].building_id),*dst=building_get(f->mp_stops[1].building_id);
 int loaded=f->loads_sold_or_carrying>0;building*target=loaded?dst:src;map_point p;
 int valid=target->created_sequence==f->mp_stops[loaded?3:2].building_id && post_access(target,&p);
 if(!valid){
  if(!loaded){f->state=FIGURE_STATE_DEAD;return 1;}
  /* Preserve cargo if a post is demolished: deliver to a remaining local store. */
  for(unsigned i=1;i<building_count();i++){building*b=building_get(i);if((b->type==BUILDING_WAREHOUSE || b->type==BUILDING_GRANARY) && post_access(b,&p) && post_capacity(b,f->resource_id)>=f->loads_sold_or_carrying){dst=target=b;f->mp_stops[1].building_id=b->id;f->mp_stops[3].building_id=b->created_sequence;valid=1;break;}}
  if(!valid)return 1;
 }
 if(f->destination_building_id!=target->id || f->destination_x!=p.x || f->destination_y!=p.y)post_destination(f,target);
 if(f->x==p.x && f->y==p.y){
  int r=f->resource_id;
  if(!loaded){
   int q=f->mp_leg_quantity,space=post_capacity(dst,r)-post_reserved(dst->id,dst->type==BUILDING_PLAYER_TRADE_POST?0:r,1,f);
   if(q>space)q=space;
   if(dst->type==BUILDING_PLAYER_TRADE_POST){int need=mp_post_demand(dst,r)-dst->resources[r]-post_reserved(dst->id,r,1,f);if(q>need)q=need;}
   f->loads_sold_or_carrying=q>0?post_remove(src,r,q):0;
   if(!f->loads_sold_or_carrying){f->state=FIGURE_STATE_DEAD;return 1;}
   post_destination(f,dst);
  }else{
   int n=building_storage_try_add_resource(dst,r,f->loads_sold_or_carrying,0);f->loads_sold_or_carrying-=n;
   if(!f->loads_sold_or_carrying){f->mp_leg_quantity=0;f->action_state=FIGURE_ACTION_53_WAREHOUSEMAN_RETURNING_EMPTY;post_destination(f,building_get(f->building_id));}
  }
 }else{
  figure_movement_move_ticks(f,1);
  if(f->direction==DIR_FIGURE_REROUTE || f->direction==DIR_FIGURE_LOST){figure_route_remove(f);if(++f->wait_ticks>120 && !loaded)f->state=FIGURE_STATE_DEAD;}
 }
 return 1;
}
