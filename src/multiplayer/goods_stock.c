#include "goods_stock.h"
#include "post_logistics.h"
#include "transport.h"
#include "post_book.h"
#include "building/building.h"
#include "building/state.h"
#include "building/storage.h"
#include "building/warehouse.h"
#include "building/granary.h"
#include "city/resource.h"

/* A complete, bounded plan is validated before any mutation. All calls are on
 * the game thread, with no save/tick/callback between planning and applying.
 * No disposable worker, partial stock API, or whole-city rollback is used. */
typedef struct { building *part; building *main; int amount; } change;
static int plan(building *b, int r, int q, int debit, change *items, int *count) {
    if (!b || b->state!=BUILDING_STATE_IN_USE || b->has_plague || q<1) return 0;
    if(b->type==BUILDING_PLAYER_TRADE_POST){
        if((debit?b->resources[r]:mp_post_space(b))<q || *count>=32)return 0;
        items[(*count)++]=(change){b,b,q};return 1;
    }
    if (b->type==BUILDING_GRANARY && resource_is_food(r)) {
        int available=debit?b->resources[r]:building_granary_maximum_receptible_amount(b,r);
        if (!debit && available>b->resources[0]) available=b->resources[0];
        if (available<q || *count>=32) return 0;
        items[(*count)++]=(change){b,b,q};return 1;
    }
    if (b->type!=BUILDING_WAREHOUSE) return 0;
    if (!debit && building_warehouse_maximum_receptible_amount(b,r)<q) return 0;
    building *part=b; int left=q;
    for (int k=0;k<8 && left;k++) {
        part=building_next(part);
        if (!part || !part->id || part->type!=BUILDING_WAREHOUSE_SPACE) return 0;
        int type=part->subtype.warehouse_resource_id;
        int available=debit?(type==r?part->resources[r]:0):
            (type==r?4-part->resources[r]:type==RESOURCE_NONE?4:0);
        if (available<0 || available>4) return 0;
        if (!available) continue;
        int n=available<left?available:left;
        if (*count>=32) return 0;
        for (int j=0;j<*count;j++) if (items[j].part==part) return 0;
        items[(*count)++]=(change){part,b,n};left-=n;
    }
    return !left;
}
int mp_goods_stock(unsigned contract,unsigned target,int r,int q,int step,int sea) {
    if (!contract || r<RESOURCE_MIN || r>=RESOURCE_MAX || q<1 || q>32 ||
        (step!=POST_EXPORT && step!=POST_RECEIVE && step!=POST_REFUND_GOODS)) return 0;
    change items[32];int count=0, debit=step==POST_EXPORT;
    if (step!=POST_REFUND_GOODS) {
        unsigned targets[32];int amounts[32];
        int n=mp_transport_plan(contract,target,r,q,debit,sea,targets,amounts);
        if (!n) return 0;
        for(int i=0;i<n;i++) if(!plan(building_get(targets[i]),r,amounts[i],debit,items,&count)) return 0;
    } else {
        int left=q;
        for(unsigned i=1;i<building_count() && left;i++) {
            building *b=building_get(i);
            if(b->state!=BUILDING_STATE_IN_USE || b->has_plague ||
                !building_storage_get_permission(sea?BUILDING_STORAGE_PERMISSION_DOCK:BUILDING_STORAGE_PERMISSION_TRADERS,b)) continue;
            int available=b->type==BUILDING_WAREHOUSE?building_warehouse_maximum_receptible_amount(b,r):
                b->type==BUILDING_GRANARY && resource_is_food(r)?building_granary_maximum_receptible_amount(b,r):0;
            int n=available<left?available:left;if(n<=0)continue;
            if(!plan(b,r,n,0,items,&count))return 0;
            left-=n;
        }
        if(left)return 0;
    }
    for(int i=0;i<count;i++) {
        change *v=&items[i];int delta=debit?-v->amount:v->amount;
        v->part->resources[r]+=delta;
        if(v->main->type==BUILDING_PLAYER_TRADE_POST) {
            /* Dedicated post stock is counted separately from ordinary stores. */
        } else if(v->main->type==BUILDING_GRANARY) {
            v->main->resources[0]-=delta;city_resource_add_to_granary(r,delta);
        } else {
            v->part->subtype.warehouse_resource_id=v->part->resources[r]?r:RESOURCE_NONE;
            city_resource_add_to_warehouse(r,delta);
        }
    }
    for(int i=0;i<count;i++) if(items[i].main->type==BUILDING_WAREHOUSE)
        building_warehouse_recount_resources(items[i].main);
    if(step==POST_EXPORT)mp_transport_depart(contract);
    else if(step==POST_RECEIVE)mp_transport_release(contract);
    return 1;
}
