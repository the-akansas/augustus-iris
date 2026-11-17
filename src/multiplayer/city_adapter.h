#ifndef MP_CITY_ADAPTER_H
#define MP_CITY_ADAPTER_H
#include <stdint.h>
/* Engine-thread only. Persist this receipt with the matching city snapshot before ACK.
   A failed persistence must reload the previous complete snapshot before processing more events. */
typedef struct {
    uint64_t sequence;
    int warehouse, quantity, money_delta, incoming;
    int pending_pottery;
} mp_city_receipt;
enum { MP_OK=1, MP_DUPLICATE=2, MP_INVALID=-1, MP_FUNDS=-2, MP_STOCK=-3, MP_PENDING=-4, MP_INTERNAL=-5 };
int mp_city_trade(mp_city_receipt *state, uint64_t seq, int warehouse, int incoming, int quantity, int money_delta);
int mp_city_deliver_pending(mp_city_receipt *state, int warehouse);
#endif
