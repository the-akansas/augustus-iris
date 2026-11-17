#ifndef MP_ROUTE_POST_H
#define MP_ROUTE_POST_H
#include <stdint.h>
uint32_t mp_route_peer_color(int peer);
uint32_t mp_route_empire_color(int name_id);
int mp_route_peer(const char *city,int *state,int *revision);
int mp_route_select(int peer);
int mp_route_build_peer(void);
int mp_route_post_for(int peer);
uint32_t mp_player_color(int index);
void mp_route_reset(void);
/* Player colour on original art: the sprite is drawn as is, then its own shape
 * is washed with the colour so folds and shading still show through. */
void mp_draw_player_tint(int image_id,int x,int y,uint32_t player,uint32_t color_mask,float scale);
int mp_player_pennant_image(void);
int mp_player_standard_image(void);
uint32_t mp_army_token_color(unsigned token);
#endif
