#include "cargo.h"
#include "building/building.h"
#include "building/state.h"
#include "building/storage.h"
#include "building/warehouse.h"
#include "building/granary.h"

int mp_cargo_valid(const mp_cargo *c)
{
    if (!c) return 0;
    if (!c->contract) return !c->resource && !c->total && !c->remaining && !c->state;
    if (c->resource < RESOURCE_MIN || c->resource >= RESOURCE_MAX || c->total < 1 || c->total > 32) return 0;
    if (c->state == MP_CARGO_LOADED) return c->remaining == c->total;
    if (c->state == MP_CARGO_RETURNING) return c->remaining > 0 && c->remaining <= c->total;
    return (c->state == MP_CARGO_RETURNED || c->state == MP_CARGO_DELIVERED) && !c->remaining;
}
static int eligible_for(building *b, int resource,int sea)
{
    return b->state == BUILDING_STATE_IN_USE && !b->has_plague &&
        (b->type == BUILDING_WAREHOUSE || (b->type == BUILDING_GRANARY && resource_is_food(resource))) &&
        building_storage_get_permission(sea?BUILDING_STORAGE_PERMISSION_DOCK:BUILDING_STORAGE_PERMISSION_TRADERS, b);
}
int mp_cargo_load(mp_cargo *c, uint64_t contract, int resource, int quantity)
{
    if (!mp_cargo_valid(c) || !contract || resource < RESOURCE_MIN || resource >= RESOURCE_MAX || quantity < 1 || quantity > 32) return 0;
    if (contract == c->contract) return c->resource == resource && c->total == quantity && c->state == MP_CARGO_LOADED;
    if (contract < c->contract || c->remaining) return 0;
    int available = 0;
    for (unsigned int i=1; i<building_count() && available<quantity; i++) {
        building *b=building_get(i); if (!eligible_for(b,resource,0)) continue;
        int n=b->type==BUILDING_WAREHOUSE ? building_warehouse_get_amount(b,resource) : building_granary_get_amount(b,resource);
        if (n>0) available += n>quantity-available ? quantity-available : n;
    }
    if (available<quantity) return 0;
    int left=quantity;
    for (unsigned int i=1; i<building_count() && left; i++) {
        building *b=building_get(i); if (!eligible_for(b,resource,0)) continue;
        int n=b->type==BUILDING_WAREHOUSE ? building_warehouse_try_remove_resource(b,resource,left) : building_granary_try_remove_resource(b,resource,left);
        if (n<0 || n>left) return 0;
        left-=n;
    }
    if (left) return 0;
    *c=(mp_cargo){contract,resource,quantity,quantity,MP_CARGO_LOADED};
    return 1;
}
static int return_cargo(mp_cargo *c,int sea)
{
    if (!mp_cargo_valid(c) || !c->contract || c->state==MP_CARGO_DELIVERED) return 0;
    if (c->state==MP_CARGO_RETURNED) return 1;
    c->state=MP_CARGO_RETURNING;
    for (unsigned int i=1; i<building_count() && c->remaining; i++) {
        building *b=building_get(i); if (!eligible_for(b,c->resource,sea)) continue;
        int n=b->type==BUILDING_WAREHOUSE ? building_warehouse_try_add_resource(b,c->resource,c->remaining,1) : building_granary_try_add_resource(b,c->resource,c->remaining,0,1);
        if (n<0 || n>c->remaining) return 0;
        c->remaining-=n;
    }
    if (!c->remaining) c->state=MP_CARGO_RETURNED;
    return 1; /* No room: retain the remainder as durable cargo, not a loss. */
}
int mp_cargo_return(mp_cargo *c){return return_cargo(c,0);}
int mp_cargo_return_by_sea(mp_cargo *c){return return_cargo(c,1);}
int mp_cargo_consume(mp_cargo *c)
{
    if (!mp_cargo_valid(c) || !c->contract) return 0;
    if (c->state==MP_CARGO_DELIVERED) return 1;
    if (c->state!=MP_CARGO_LOADED) return 0;
    c->remaining=0; c->state=MP_CARGO_DELIVERED; return 1;
}
