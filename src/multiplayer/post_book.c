#include "post_book.h"
#include <string.h>
#include <stdlib.h>
#include <limits.h>

static int roster_valid(const char *s) {
    return s && strlen(s)==64 && strspn(s,"0123456789abcdef")==64;
}
int post_book_init(post_book *b,const char *roster) {
    if(!b || !roster_valid(roster))return 0;
    memset(b,0,sizeof(*b));memcpy(b->roster,roster,65);return 1;
}
int post_book_bind(post_book *b,int peer,uint32_t site,uint32_t generation) {
    if(!b || peer<0 || peer>=POST_PEERS || !site || !generation)return 0;
    for(int i=0;i<POST_PEERS;i++)if(i!=peer && b->site[i]==site)return 0;
    b->site[peer]=site;b->generation[peer]=generation;return 1;
}
void post_book_demolish(post_book *b,uint32_t site,uint32_t generation) {
    if(!b)return;
    for(int i=0;i<POST_PEERS;i++)if(b->site[i]==site && b->generation[i]==generation){
        b->site[i]=0;b->generation[i]=0;
    }
}
static int valid(const post_command *c) {
    if(!c || !memchr(c->id,0,sizeof(c->id)) || !c->id[0])return 0;
    if(strspn(c->id,"0123456789abcdefghijklmnopqrstuvwxyz:_")!=strlen(c->id))return 0;
    if(c->peer<0 || c->peer>=POST_PEERS || c->step<POST_EXPORT || c->step>POST_REFUND_MONEY)return 0;
    if(c->resource<0 || c->resource>=POST_RESOURCES || c->amount<1 || c->amount>1000000)return 0;
    if(c->resource && (c->amount>32 || c->step==POST_ESCROW || c->step==POST_PAY || c->step==POST_REFUND_MONEY))return 0;
    return 1;
}
static int same(const post_command *a,const post_command *b) {
    return !strcmp(a->id,b->id) && a->peer==b->peer && a->step==b->step &&
        a->resource==b->resource && a->amount==b->amount;
}
int post_book_apply(post_book *b,int32_t *treasury,const post_command *c) {
    if(!b || !treasury || !valid(c) || b->count>POST_RECEIPTS)return POST_INVALID;
    for(uint32_t i=0;i<b->count;i++)if(!strcmp(b->receipts[i].command.id,c->id))
        return same(&b->receipts[i].command,c)?b->receipts[i].applied:POST_INVALID;
    if(b->count==POST_RECEIPTS)return POST_RECEIPTS_FULL;
    int32_t *value=c->resource?&b->cargo[c->peer][c->resource]:treasury;
    int debit=c->step==POST_EXPORT || c->step==POST_ESCROW;
    int applied=1;
    /* Refunds remain in city custody even if the post was demolished. */
    if(c->resource && (c->step==POST_EXPORT || c->step==POST_RECEIVE) && !b->site[c->peer])applied=0;
    if(debit && *value<c->amount)applied=0;
    if(!debit && *value>INT32_MAX-c->amount)applied=0;
    if(applied)*value+=debit?-c->amount:c->amount;
    post_receipt *receipt=&b->receipts[b->count++];
    memset(receipt,0,sizeof(*receipt));strcpy(receipt->command.id,c->id);
    receipt->command.peer=c->peer;receipt->command.step=c->step;
    receipt->command.resource=c->resource;receipt->command.amount=c->amount;receipt->applied=applied;
    return applied;
}

/* Explicit little endian format; independent of C padding and pointer size. */
static void put(unsigned char **p,uint32_t v){for(int i=0;i<4;i++)*(*p)++=(unsigned char)(v>>(i*8));}
static uint32_t get(const unsigned char **p){uint32_t v=0;for(int i=0;i<4;i++)v|=(uint32_t)*(*p)++<<(i*8);return v;}
static uint32_t checksum(const unsigned char *p,size_t n){
    uint32_t c=0xffffffffu;
    for(size_t i=0;i<n;i++){c^=p[i];for(int j=0;j<8;j++)c=(c>>1)^(0xedb88320u&-(int32_t)(c&1));}
    return ~c;
}
static size_t bytes(uint32_t count){return 4+64+4+POST_PEERS*(8+4*POST_RESOURCES)+(size_t)count*(POST_COMMAND_ID+20)+4;}
size_t post_book_encode(const post_book *b,unsigned char *out,size_t cap){
    if(!b || b->count>POST_RECEIPTS || !roster_valid(b->roster))return 0;
    size_t n=bytes(b->count);if(!out || cap<n)return n;
    unsigned char *p=out;memcpy(p,"MPT1",4);p+=4;memcpy(p,b->roster,64);p+=64;put(&p,b->count);
    for(int i=0;i<POST_PEERS;i++){
        put(&p,b->site[i]);put(&p,b->generation[i]);
        for(int j=0;j<POST_RESOURCES;j++)put(&p,(uint32_t)b->cargo[i][j]);
    }
    for(uint32_t i=0;i<b->count;i++){
        const post_receipt *v=&b->receipts[i];memcpy(p,v->command.id,POST_COMMAND_ID);p+=POST_COMMAND_ID;
        put(&p,v->command.peer);put(&p,v->command.step);put(&p,v->command.resource);put(&p,v->command.amount);put(&p,v->applied);
    }
    put(&p,checksum(out,n-4));return n;
}
int post_book_decode(post_book *b,const char *roster,const unsigned char *in,size_t n){
    if(!b || !roster_valid(roster) || !in || n<bytes(0) || memcmp(in,"MPT1",4) || memcmp(in+4,roster,64))return 0;
    const unsigned char *p=in+68;uint32_t count=get(&p);
    if(count>POST_RECEIPTS || bytes(count)!=n)return 0;
    const unsigned char *end=in+n-4;if(get(&end)!=checksum(in,n-4))return 0;
    post_book *temp=calloc(1,sizeof(*temp));if(!temp)return 0;
    memcpy(temp->roster,roster,65);temp->count=count;int ok=1;
    for(int i=0;i<POST_PEERS;i++){
        temp->site[i]=get(&p);temp->generation[i]=get(&p);
        if((!temp->site[i])!=(!temp->generation[i]))ok=0;
        for(int k=0;k<i;k++)if(temp->site[i] && temp->site[i]==temp->site[k])ok=0;
        for(int j=0;j<POST_RESOURCES;j++){uint32_t value=get(&p);if(value>INT32_MAX || (j==0 && value))ok=0;temp->cargo[i][j]=(int32_t)value;}
    }
    for(uint32_t i=0;i<count;i++){
        post_receipt *v=&temp->receipts[i];memcpy(v->command.id,p,POST_COMMAND_ID);p+=POST_COMMAND_ID;
        v->command.peer=get(&p);v->command.step=get(&p);v->command.resource=get(&p);v->command.amount=get(&p);v->applied=get(&p);
        if(!valid(&v->command) || (v->applied!=0 && v->applied!=1)){ok=0;continue;}
        for(uint32_t j=0;j<i;j++)if(!strncmp(v->command.id,temp->receipts[j].command.id,POST_COMMAND_ID))ok=0;
    }
    if(ok)*b=*temp;free(temp);return ok;
}
