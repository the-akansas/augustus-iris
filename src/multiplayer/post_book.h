#ifndef MP_POST_BOOK_H
#define MP_POST_BOOK_H
#include <stdint.h>
#include <stddef.h>
/* Engine-side foundation, not yet linked into the playable engine. */
#define POST_PEERS 8
#define POST_RESOURCES 64
#define POST_RECEIPTS 512
#define POST_COMMAND_ID 96
enum post_step { POST_EXPORT=1, POST_ESCROW, POST_RECEIVE, POST_PAY, POST_REFUND_GOODS, POST_REFUND_MONEY };
enum post_result { POST_INVALID=-1, POST_RECEIPTS_FULL=-2, POST_REJECTED=0, POST_APPLIED=1 };
typedef struct {
    char id[POST_COMMAND_ID];
    int32_t peer, step, resource, amount;
} post_command;
typedef struct { post_command command; int32_t applied; } post_receipt;
typedef struct {
    char roster[65];
    uint32_t site[POST_PEERS], generation[POST_PEERS];
    int32_t cargo[POST_PEERS][POST_RESOURCES];
    uint32_t count;
    post_receipt receipts[POST_RECEIPTS];
} post_book;
int post_book_init(post_book *book, const char *roster);
int post_book_bind(post_book *book, int peer, uint32_t building, uint32_t generation);
void post_book_demolish(post_book *book, uint32_t building, uint32_t generation);
int post_book_apply(post_book *book, int32_t *treasury, const post_command *command);
/* Snapshot the book together with the city inventory and treasury. Copying only
 * this book is NOT a valid game save. Never evict receipts on a network ACK. */
size_t post_book_encode(const post_book *book, unsigned char *output, size_t capacity);
int post_book_decode(post_book *book, const char *roster, const unsigned char *input, size_t length);
#endif
