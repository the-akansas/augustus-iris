#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "multiplayer/post_city.h"
#include "city/finance.h"
#include "game/file_io.h"
#include "game/resource.h"
static const char *roster="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
/* Noninteractive fixture protocol; never exposed as a game/network API. */
int post_sav_apply(const char *in,const char *out) {
    char path[2048],identity[65]; unsigned owner;
    post_command c={0};
    snprintf(path,sizeof(path),"%s/request.txt",in); FILE *f=fopen(path,"r"); assert(f);
    assert(fscanf(f,"%64s %u %95s %d %d %d %d",identity,&owner,c.id,&c.peer,&c.step,&c.resource,&c.amount)==7); fclose(f);
    snprintf(path,sizeof(path),"%s/city.sav",in);
    if(strcmp(c.id,"seed")) { assert(game_file_io_read_saved_game(path,0)==1); }
    assert(mp_post_city_attach(identity,owner));
    int result;
    if(!strcmp(c.id,"seed")) {
        city_finance_treasury_add(1000-city_finance_treasury());
        assert(mp_post_city_bind(c.peer,123,1));
        c.step=POST_REFUND_GOODS;c.resource=RESOURCE_MARBLE;c.amount=20;
        result=mp_post_city_apply(identity,owner,&c);
    } else result=mp_post_city_apply(identity,owner,&c);
    snprintf(path,sizeof(path),"%s/city.sav",out);assert(game_file_io_write_saved_game(path));
    snprintf(path,sizeof(path),"%s/result.txt",out);f=fopen(path,"w");assert(f);
    fprintf(f,"%d %d %d %u\n",result,city_finance_treasury(),mp_post_city_book()->cargo[c.peer][RESOURCE_MARBLE],mp_post_city_book()->count);
    assert(!fclose(f));return 0;
}
int post_sav_test(const char *dir) {
    char path[2048]; snprintf(path,sizeof(path),"%s/post-city.sav",dir);
    mp_post_city_reset();
    assert(mp_post_city_attach(roster,0));
    city_finance_treasury_add(1000-city_finance_treasury());
    post_command debit={"abc:export:1",1,POST_EXPORT,0,100};
    assert(mp_post_city_apply(roster,0,&debit)==POST_APPLIED);
    assert(city_finance_treasury()==900);
    assert(mp_post_city_apply(roster,1,&debit)==POST_INVALID);
    assert(!mp_post_city_attach(roster,1));
    assert(mp_post_city_bind(1,123,1));
    post_command cargo={"abc:receive:1",1,POST_RECEIVE,RESOURCE_MARBLE,3};
    assert(mp_post_city_apply(roster,0,&cargo)==POST_APPLIED);
    assert(game_file_io_write_saved_game(path));
    mp_post_city_reset(); city_finance_treasury_add(333);
    assert(game_file_io_read_saved_game(path,0)==1);
    assert(city_finance_treasury()==900);
    assert(mp_post_city_book() && mp_post_city_book()->cargo[1][RESOURCE_MARBLE]==3);
    for(int i=0;i<100;i++) {
        assert(mp_post_city_apply(roster,0,&debit)==POST_APPLIED);
        assert(mp_post_city_apply(roster,0,&cargo)==POST_APPLIED);
    }
    assert(city_finance_treasury()==900 && mp_post_city_book()->count==2);
    assert(mp_post_city_book()->cargo[1][RESOURCE_MARBLE]==3);
    FILE *f=fopen(path,"rb"); assert(f); fseek(f,0,SEEK_END); long n=ftell(f); rewind(f);
    unsigned char *bytes=malloc(n); assert(bytes && fread(bytes,1,n,f)==(size_t)n); fclose(f);
    buffer buf; buffer_init(&buf,bytes,n);
    mp_post_city_reset(); city_finance_treasury_add(77);
    assert(game_file_io_read_save_game_from_buffer(&buf)==1);
    assert(city_finance_treasury()==900 && mp_post_city_book()->count==2);
    /* Invalid/truncated receipt piece must fail BEFORE city cash is changed. */
    for(int i=0;i<4;i++) {
        unsigned char *bad=malloc(n); memcpy(bad,bytes,n);
        if(i<3) bad[n-MP_POST_SAVE_BYTES+(i==0?12:i==1?30:63999)]^=1;
        buffer_init(&buf,bad,i==3?n-1:n);
        city_finance_treasury_add(17);
        int before=city_finance_treasury();
        assert(game_file_io_read_save_game_from_buffer(&buf)!=1);
        assert(city_finance_treasury()==before && mp_post_city_book()->count==2);
        free(bad);
    }
    free(bytes);
    /* Empty, new single-player city must not inherit another city's receipts. */
    mp_post_city_reset(); assert(game_file_io_write_saved_game(path));
    assert(mp_post_city_attach(roster,2));
    assert(game_file_io_read_saved_game(path,0)==1 && !mp_post_city_book());
    assert(mp_post_city_attach(roster,2));
    snprintf(path,sizeof(path),"%s/legacy-city.sav",dir);
    assert(game_file_io_read_saved_game(path,0)==1 && !mp_post_city_book());
    puts("PASS actual SAV: cash + marble custody + receipts, file/buffer restore, 100 duplicate retries, wrong owner, 4 corrupt/truncated inputs, inactive + legacy reset");
    return 0;
}
