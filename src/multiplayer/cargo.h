#ifndef MULTIPLAYER_CARGO_H
#define MULTIPLAYER_CARGO_H
#include <stdint.h>
enum { MP_CARGO_LOADED=1, MP_CARGO_RETURNING, MP_CARGO_RETURNED, MP_CARGO_DELIVERED };
typedef struct {
    uint64_t contract;
    int resource, total, remaining, state;
} mp_cargo;
/* Disposable snapshot only. Publish cargo and matching SAV atomically; on any
   failure discard both. These functions never change money or trade ledgers. */
int mp_cargo_valid(const mp_cargo *c);
int mp_cargo_load(mp_cargo *c, uint64_t contract, int resource, int quantity);
int mp_cargo_return(mp_cargo *c);
int mp_cargo_return_by_sea(mp_cargo *c);
int mp_cargo_consume(mp_cargo *c);
#endif
