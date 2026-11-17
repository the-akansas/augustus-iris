#ifndef MP_POST_LOGISTICS_H
#define MP_POST_LOGISTICS_H
#include "building/building.h"
#include "figure/figure.h"
int mp_post_total(const building *b);
int mp_post_space(const building *b);
int mp_post_add(building *b,int resource,int amount);
int mp_post_take(building *b,int resource,int amount);
int mp_post_city_stock(int resource);
int mp_post_inbound_need(const building*b,int resource,const figure*ignore);
int mp_post_demand(const building *b,int resource);
void mp_post_spawn(building *b);
int mp_post_supply_spawn(building *b);
int mp_post_cart_action(figure *f);
void mp_post_logistics_reset(void);
/* Publishes posts holding goods that no store can take (post-blocked.txt). */
void mp_post_blocked_publish(const char *dir);
/* Post contents and goods already on their way, for the host's caravan loading rule. */
void mp_post_load_publish(const char *dir);
#endif
