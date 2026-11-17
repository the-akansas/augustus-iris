#include "multiplayer/city_adapter.h"
#include "building/building.h"
#include "building/state.h"
#include "building/warehouse.h"
#include "city/finance.h"
#include <limits.h>

static building *valid_warehouse(int id)
{
    if (id <= 0 || id >= building_count()) return 0;
    building *b = building_get(id);
    if (!b || b->type != BUILDING_WAREHOUSE || b->state != BUILDING_STATE_IN_USE || b->has_plague) return 0;
    return b;
}

int mp_city_trade(mp_city_receipt *s, uint64_t seq, int id, int incoming, int quantity, int money)
{
    if (!s || !seq || quantity <= 0 || quantity > 32 || (incoming != 0 && incoming != 1)
        || (incoming && money >= 0) || (!incoming && money <= 0)) return MP_INVALID;
    if (seq == s->sequence) {
        return s->warehouse == id && s->quantity == quantity && s->money_delta == money && s->incoming == incoming
            ? MP_DUPLICATE : MP_INVALID;
    }
    if (s->sequence == UINT64_MAX || seq != s->sequence + 1) return MP_INVALID;
    if (s->pending_pottery) return MP_PENDING;
    int64_t balance = (int64_t) city_finance_treasury() + money;
    if (balance < 0 || balance > INT_MAX) return MP_FUNDS;
    building *b = valid_warehouse(id);
    if (!incoming) {
        if (!b || building_warehouse_get_amount(b, RESOURCE_POTTERY) < quantity) return MP_STOCK;
        int removed = building_warehouse_try_remove_resource(b, RESOURCE_POTTERY, quantity);
        /* Caller must reload snapshot on MP_INTERNAL; never ACK partially applied state. */
        if (removed != quantity) return MP_INTERNAL;
    }
    /* Trade has been committed by the coordinator; incoming goods stay in persistent
       inbox until storage is available, without charging a second time on delivery. */
    city_finance_treasury_add(money);
    s->sequence = seq; s->warehouse = id; s->quantity = quantity;
    s->money_delta = money; s->incoming = incoming;
    s->pending_pottery = incoming ? quantity : 0;
    return MP_OK;
}
int mp_city_deliver_pending(mp_city_receipt *s, int id)
{
    if (!s || s->pending_pottery < 0 || s->pending_pottery > 32) return MP_INVALID;
    building *b = valid_warehouse(id);
    if (!b || !s->pending_pottery) return 0;
    int added = building_warehouse_try_add_resource(b, RESOURCE_POTTERY, s->pending_pottery, 1);
    if (added < 0 || added > s->pending_pottery) return MP_INTERNAL;
    s->pending_pottery -= added;
    return added;
}
