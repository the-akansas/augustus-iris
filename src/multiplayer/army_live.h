#ifndef MP_ARMY_LIVE_H
#define MP_ARMY_LIVE_H
#include "core/buffer.h"
#define MP_ARMY_SAVE_BYTES 600000
void mp_army_reset(void);
void mp_army_save(buffer *b);
int mp_army_restore(const buffer *b);
void mp_army_poll(const char *dir);
#endif
