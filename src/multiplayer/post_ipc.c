#include "post_ipc.h"
#include <string.h>
static unsigned rd(const unsigned char *p) { return p[0]|p[1]<<8|p[2]<<16|(unsigned)p[3]<<24; }
static void wr(unsigned char *p,unsigned n) { for(int i=0;i<4;i++)p[i]=(unsigned char)(n>>(8*i)); }
static unsigned crc(const unsigned char *p,size_t n) {
    unsigned c=~0u;
    for(size_t i=0;i<n;i++){c^=p[i];for(int j=0;j<8;j++)c=(c>>1)^(0xedb88320u&-(int)(c&1));}
    return ~c;
}
int post_ipc_init(post_ipc *s,const unsigned char run[16],const char *roster,unsigned owner) {
    memset(s,0,sizeof(*s));
    unsigned nonzero=0;for(int i=0;i<16;i++)nonzero|=run[i];
    if(!nonzero || !mp_post_city_attach(roster,owner))return 0;
    memcpy(s->run,run,16);memcpy(s->roster,roster,65);s->owner=owner;s->ready=1;return 1;
}
int post_ipc_exchange(post_ipc *s,const unsigned char *p,size_t n,unsigned char *out,size_t cap) {
    if(!s->ready || n!=POST_IPC_REQUEST || cap<POST_IPC_RESPONSE ||
       memcmp(p,"MPI1",4) || memcmp(p+4,s->run,16) ||
       rd(p+256)!=crc(p,256) || memcmp(p+56,s->roster,64) || rd(p+120)!=s->owner ||
       !mp_post_city_attach(s->roster,s->owner))return 0;
    unsigned seq=rd(p+124),kind=rd(p+128);
    if(!seq || seq<s->sequence || kind>3)return 0;
    if(seq==s->sequence) {
        if(memcmp(p,s->request,n))return 0;
        memcpy(out,s->response,POST_IPC_RESPONSE);return 1;
    }
    /* One command per packet avoids partial batch effects. Reserved bytes and
       capture payload must be canonical, not ignored silently. */
    if(kind!=2)for(int i=244;i<256;i++)if(p[i])return 0;
    int result=POST_APPLIED;
    if(kind) {
        post_command c;
        memcpy(c.id,p+132,96);
        char *end=memchr(c.id,0,96);if(!end || end==c.id)return 0;
        for(char *q=end;q<c.id+96;q++)if(*q)return 0;
        c.peer=(int32_t)rd(p+228);c.step=(int32_t)rd(p+232);
        c.resource=(int32_t)rd(p+236);c.amount=(int32_t)rd(p+240);
        if(rd(p+52)!=mp_post_city_epoch())result=POST_REJECTED;
        else if(kind==3)result=mp_post_city_compact(c.id,(unsigned)c.peer);
        else result=kind==2?mp_post_city_transport(s->roster,s->owner,&c,rd(p+244),rd(p+248),rd(p+252)):mp_post_city_apply(s->roster,s->owner,&c);
        if(result==POST_INVALID)return 0;
    } else for(int i=132;i<244;i++)if(p[i])return 0;
    memcpy(s->request,p,n);s->sequence=seq;
    memcpy(s->response,p,132);memcpy(s->response,"MPR1",4);
    wr(s->response+128,(unsigned)result);
    buffer b;buffer_init(&b,s->response+132,MP_POST_SAVE_BYTES);mp_post_city_save(&b);
    wr(s->response+POST_IPC_RESPONSE-4,crc(s->response,POST_IPC_RESPONSE-4));
    memcpy(out,s->response,POST_IPC_RESPONSE);return 1;
}
