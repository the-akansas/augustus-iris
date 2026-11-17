#ifndef MP_POST_IPC_H
#define MP_POST_IPC_H
#include "multiplayer/post_city.h"
/* Game-thread endpoint. Transport must publish complete files atomically.
 * Call reset/reinitialize after every city load, reconnect, or owner change.
 * Authentication belongs to the bridge/server; CRC only detects damage. */
#define POST_IPC_REQUEST 260
#define POST_IPC_RESPONSE (132 + MP_POST_SAVE_BYTES + 4)
typedef struct {
    unsigned char run[16], request[POST_IPC_REQUEST], response[POST_IPC_RESPONSE];
    char roster[65];
    unsigned owner, sequence, published;
    int ready;
} post_ipc;
int post_ipc_init(post_ipc *, const unsigned char run[16], const char *, unsigned);
int post_ipc_exchange(post_ipc *, const unsigned char *, size_t, unsigned char *, size_t);
/* Bounded local I/O, no sleeps/retry loops/network/SAV writes. Caller polls at
 * a controlled cadence and skips explicit checkpoint/load critical sections. */
int post_ipc_poll(post_ipc *, const char *directory);
#endif
