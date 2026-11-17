#ifndef MULTIPLAYER_POST_CITY_H
#define MULTIPLAYER_POST_CITY_H
#include "core/buffer.h"
#include "post_book.h"
/* Fixed, bounded experimental SAV piece; legacy readers reject version 0xc3. */
#define MP_POST_SAVE_BYTES 64000
unsigned mp_post_city_revision(void);
unsigned mp_post_city_epoch(void);
int mp_post_city_compact(const char*,unsigned);
void mp_post_city_reset(void);
int mp_post_city_attach(const char *roster, unsigned city_slot);
int mp_post_city_apply(const char *roster, unsigned city_slot, const post_command *command);
const post_book *mp_post_city_book(void);
int mp_post_city_bind(int peer, unsigned building, unsigned generation);
void mp_post_city_save(buffer *buf);
int mp_post_city_restore(const buffer *buf);
int mp_post_city_transport(const char *, unsigned, const post_command *, unsigned, unsigned, unsigned);
#endif
