/* Test shim for building the real engine-side mailbox (post_ipc.c, post_city.c, post_book.c, core/buffer.c) into a
 * shared library without the game. Only what those files need from the rest of the game is stood in here:
 *   - the city treasury (city_finance_treasury / _add), a plain variable the test sets and reads;
 *   - mp_army_reset (army state is not part of these files' money path), mp_goods_stock (goods: not used here);
 *   - the Windows SHA-256 calls used ONLY by receipt compaction: they report failure, so a compaction request is
 *     rejected (never faked). The tests below never ask for one; if one is asked for, it shows as rejected. */
#include <stddef.h>
#include <stdint.h>
#include "multiplayer/post_ipc.h"
static int32_t treasury;
int city_finance_treasury(void){return treasury;}
void city_finance_treasury_add(int amount){treasury+=amount;}
void shim_set_treasury(int value){treasury=value;}
int shim_get_treasury(void){return treasury;}
void mp_army_reset(void){}
int mp_goods_stock(unsigned contract,unsigned target,int resource,int quantity,int step,int sea){(void)contract;(void)target;(void)resource;(void)quantity;(void)step;(void)sea;return 0;}
size_t shim_ipc_size(void){return sizeof(post_ipc);}
