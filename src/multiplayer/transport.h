#ifndef MULTIPLAYER_TRANSPORT_H
#define MULTIPLAYER_TRANSPORT_H
#include "figure/figure.h"
/* Separate actions prevent NPC price/quota logic from touching player contracts. */
enum { MP_CARAVAN_WALK=240, MP_CARAVAN_UNLOAD, MP_CARAVAN_READY, MP_CARAVAN_EXIT, MP_CARAVAN_FAILED, MP_CARAVAN_DEPART, MP_CARAVAN_DEPARTED, MP_CARAVAN_HOME, MP_CARAVAN_HOME_READY, MP_CARAVAN_EXITED, MP_CARAVAN_WAIT };
void mp_transport_reset(void);
int mp_transport_begin_sea(unsigned int contract,int resource,int quantity,int source);
int mp_transport_docker_action(figure *f);
void mp_transport_on_delete(figure *f);
void mp_transport_depart(unsigned int contract);
int mp_transport_validate_departed(unsigned int contract,int resource,int quantity);
int mp_transport_action(figure *f);
void mp_transport_poll(void);
int mp_transport_begin(unsigned int contract, int resource, int quantity);
int mp_transport_begin_source(unsigned int contract, int resource, int quantity);
int mp_transport_validate_source(unsigned int contract, int building_id, int resource, int quantity);
int mp_transport_collect(unsigned int contract, int resource, int quantity);
int mp_transport_status(unsigned int contract, int *building_id);
int mp_transport_validate(unsigned int contract, int building_id, int resource, int quantity);
int mp_transport_deliver(unsigned int contract, int resource, int quantity);
void mp_transport_release(unsigned int contract);
int mp_transport_plan(unsigned, unsigned, int, int, int, int, unsigned *, int *);
#endif
