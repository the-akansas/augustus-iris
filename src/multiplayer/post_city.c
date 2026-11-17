#include "post_city.h"
#include "army_live.h"
#include "city/finance.h"
#include "game/resource.h"
#include <string.h>
#include <windows.h>
#include <bcrypt.h>

static post_book book;
static unsigned owner;
static unsigned receipt_epoch;
unsigned mp_post_city_epoch(void){return receipt_epoch;}
static int attached;
static unsigned revision;
unsigned mp_post_city_revision(void){return revision;}
static uint32_t crc(const unsigned char *p,size_t n) {
    uint32_t value=0xffffffffu;
    for(size_t i=0;i<n;i++) { value^=p[i]; for(int k=0;k<8;k++) value=(value>>1)^(0xedb88320u&-(int32_t)(value&1)); }
    return ~value;
}
void mp_post_city_reset(void) { mp_army_reset(); ++revision; memset(&book, 0, sizeof(book)); owner=0; receipt_epoch=0; attached=0; }
const post_book *mp_post_city_book(void) { return attached ? &book : 0; }
int mp_post_city_attach(const char *roster, unsigned city_slot) {
    if (city_slot >= POST_PEERS) return 0;
    if (attached) return roster && owner==city_slot && !strcmp(book.roster,roster);
    if (!post_book_init(&book,roster)) return 0;
    owner=city_slot; attached=1; return 1;
}
int mp_post_city_bind(int peer,unsigned building,unsigned generation) {
    if (!attached || peer==(int)owner) return 0;
    return post_book_bind(&book,peer,building,generation);
}
int mp_post_city_apply(const char *roster,unsigned city_slot,const post_command *c) {
    /* peer == owner: a one-sided money step of this city alone (a throne debit or its refund: nobody receives or
       pays it, 2026-11-15). Goods always name another city. */
    if (!attached || !roster || owner!=city_slot || strcmp(book.roster,roster) || !c ||
        (c->peer==(int)owner && (c->resource || (c->step!=POST_EXPORT && c->step!=POST_PAY))) || c->resource>=RESOURCE_MAX) return POST_INVALID;
    int32_t previous=city_finance_treasury(), next=previous;
    int result=post_book_apply(&book,&next,c);
    /* Core validates overflow and duplicate receipts before any effect. The game
       thread alone owns this state: no tick/save may interleave these statements.
       Never use process_export here: its Pantheon bonus creates extra money.
       Finance categorization of escrow/refunds is a separate integration step. */
    if (result==POST_APPLIED && next!=previous) city_finance_treasury_add(next-previous);
    return result;
}
void mp_post_city_save(buffer *buf) {
    memset(buf->data,0,buf->size);
    buffer_write_raw(buf,"MPCS",4);
    buffer_write_u32(buf,2);
    buffer_write_u32(buf,attached);
    buffer_write_u32(buf,owner);
    size_t n=attached ? post_book_encode(&book,0,0) : 0;
    buffer_write_u32(buf,(uint32_t)n);
    if (n && n<=buf->size-24) post_book_encode(&book,buf->data+20,buf->size-24);
    buffer_set(buf,20+n);buffer_write_u32(buf,receipt_epoch);
    buffer_set(buf,buf->size-4); buffer_write_u32(buf,crc(buf->data,buf->size-4));
}
int mp_post_city_restore(const buffer *source) {
    if (!source) { mp_post_city_reset(); return 1; }
    if (source->size!=MP_POST_SAVE_BYTES || memcmp(source->data,"MPCS",4)) return 0;
    buffer b=*source; b.index=4; b.overflow=0;
    buffer_set(&b,b.size-4);
    if(buffer_read_u32(&b)!=crc(b.data,b.size-4)) return 0;
    buffer_set(&b,4);
    unsigned version=buffer_read_u32(&b), active=buffer_read_u32(&b), slot=buffer_read_u32(&b);
    size_t n=buffer_read_u32(&b);
    if ((version!=1 && version!=2) || active>1 || slot>=POST_PEERS || n>b.size-(version==2?28:24)) return 0;
    /* Reject noncanonical inactive state and padding corruption as well. */
    if (!active && (n || slot)) return 0;
    for (size_t i=20+n+(version==2?4:0);i<b.size-4;i++) if(b.data[i]) return 0;
    if (!active) { mp_post_city_reset(); return 1; }
    if (n<68) return 0;
    char roster[65]; memcpy(roster,b.data+24,64); roster[64]=0;
    post_book temp;
    if (!post_book_decode(&temp,roster,b.data+20,n) || temp.site[slot]) return 0;
    for (unsigned i=0;i<temp.count;i++) if((temp.receipts[i].command.peer==(int)slot && (temp.receipts[i].command.resource ||
        (temp.receipts[i].command.step!=POST_EXPORT && temp.receipts[i].command.step!=POST_PAY))) ||
        temp.receipts[i].command.resource>=RESOURCE_MAX) return 0;
    /* An authenticated session must call attach before accepting commands. A
       mismatching city/roster then fails rather than rebinding old receipts. */
    buffer_set(&b,20+n);receipt_epoch=version==2?buffer_read_u32(&b):0;
    book=temp; owner=slot; attached=1; ++revision; return 1;
}

#include "goods_stock.h"
int mp_post_city_transport(const char *roster,unsigned slot,const post_command *c,unsigned contract,unsigned target,unsigned route) {
    if(!attached || !roster || owner!=slot || strcmp(book.roster,roster) || !c ||
       c->peer==(int)owner || c->peer<0 || c->peer>=POST_PEERS || c->resource<=0 ||
       c->resource>=RESOURCE_MAX || !contract || (route!=2 && route!=3))return POST_INVALID;
    /* Validate command and duplicate/capacity semantics using the same book core.
       Stock is owned by real warehouses, never by a fabricated post balance. */
    for(unsigned i=0;i<book.count;i++)if(!strcmp(book.receipts[i].command.id,c->id)) {
        int32_t cash=city_finance_treasury();return post_book_apply(&book,&cash,c);
    }
    if(book.count==POST_RECEIPTS)return POST_RECEIPTS_FULL;
    post_book trial=book;int32_t cash=city_finance_treasury();
    trial.site[c->peer]=contract;trial.generation[c->peer]=1;
    trial.cargo[c->peer][c->resource]=c->step==POST_EXPORT?c->amount:0;
    int valid=post_book_apply(&trial,&cash,c);
    if(valid!=POST_APPLIED)return valid;
    int applied=mp_goods_stock(contract,target,c->resource,c->amount,c->step,route==3);
    /* Commit only the immutable receipt. Persistent inventory lives in the same SAV. */
    book.receipts[book.count]=trial.receipts[trial.count-1];
    book.receipts[book.count++].applied=applied;
    return applied;
}

int mp_post_city_compact(const char*expected,unsigned next_epoch){
 if(!attached || receipt_epoch==0xffffffffu || next_epoch!=receipt_epoch+1 || strlen(expected)!=64)return POST_REJECTED;
 unsigned char piece[MP_POST_SAVE_BYTES],hash[32];buffer b;buffer_init(&b,piece,sizeof(piece));mp_post_city_save(&b);
 BCRYPT_ALG_HANDLE alg=0;BCRYPT_HASH_HANDLE handle=0;int ok=0;
 if(BCryptOpenAlgorithmProvider(&alg,BCRYPT_SHA256_ALGORITHM,0,0)<0)return POST_REJECTED;
 if(BCryptCreateHash(alg,&handle,0,0,0,0,0)>=0 && BCryptHashData(handle,piece,sizeof(piece),0)>=0 && BCryptFinishHash(handle,hash,sizeof(hash),0)>=0)ok=1;
 if(handle)BCryptDestroyHash(handle);BCryptCloseAlgorithmProvider(alg,0);
 if(!ok)return POST_REJECTED;
 const char*hex="0123456789abcdef";for(int i=0;i<32;i++)if(expected[2*i]!=hex[hash[i]>>4] || expected[2*i+1]!=hex[hash[i]&15])return POST_REJECTED;
 memset(book.receipts,0,sizeof(book.receipts));book.count=0;receipt_epoch=next_epoch;++revision;return POST_APPLIED;
}
