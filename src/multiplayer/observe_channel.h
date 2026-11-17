#ifndef MP_OBSERVE_CHANNEL_H
#define MP_OBSERVE_CHANNEL_H
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define OBS_CAP (16u*1024*1024)
#define OBS_FRAME_CAP (40u*1024*1024)
typedef struct { HANDLE handle; unsigned char *mem; char token[33]; unsigned capacity,request; } obs_channel;
static void obs_close(obs_channel *c){if(c->mem)UnmapViewOfFile(c->mem);if(c->handle)CloseHandle(c->handle);memset(c,0,sizeof(*c));}
static int obs_open(obs_channel *c,const char *dir,const char *base,unsigned capacity){
 char path[4096],token[34]={0},name[80];snprintf(path,sizeof(path),"%s/%s.txt",dir,base);
 FILE *f=fopen(path,"rb");if(!f){obs_close(c);return 0;}size_t n=fread(token,1,33,f);fclose(f);
 if(n!=32){obs_close(c);return 0;}for(int i=0;i<32;i++)if(!strchr("0123456789abcdef",token[i]))return 0;
 if(c->mem && !strcmp(c->token,token))return 1;
 obs_close(c);snprintf(name,sizeof(name),"Local\\AugustusState-%s",token);
 c->handle=OpenFileMappingA(FILE_MAP_ALL_ACCESS,FALSE,name);if(!c->handle)return 0;
 c->mem=MapViewOfFile(c->handle,FILE_MAP_ALL_ACCESS,0,0,capacity+64);if(!c->mem){obs_close(c);return 0;}
 strcpy(c->token,token);c->capacity=capacity;return 1;
}
static void obs_write(obs_channel *c,const void *data,unsigned len,uint64_t seq,uint64_t ticks){
 if(!c->mem || !len || len>c->capacity)return;
 volatile LONG *stamp=(volatile LONG *)(c->mem+4);LONG even=(InterlockedCompareExchange(stamp,0,0)+2)&0x7ffffffe;if(!even)even=2;
 InterlockedExchange(stamp,even-1);memcpy(c->mem+64,data,len);memcpy(c->mem+8,&len,4);memcpy(c->mem+16,&seq,8);memcpy(c->mem+24,&ticks,8);InterlockedExchange(stamp,even);
}
static unsigned char *obs_read(obs_channel *c,unsigned *len,uint64_t *seq,uint64_t *ticks){
 if(!c->mem)return 0;volatile LONG *stamp=(volatile LONG *)(c->mem+4);
 LONG a=InterlockedCompareExchange(stamp,0,0);if(!a || (a&1))return 0;
 memcpy(len,c->mem+8,4);memcpy(seq,c->mem+16,8);memcpy(ticks,c->mem+24,8);if(!*len || *len>c->capacity)return 0;
 unsigned char *p=malloc(*len);if(!p)return 0;memcpy(p,c->mem+64,*len);
 if(InterlockedCompareExchange(stamp,0,0)!=a){free(p);return 0;}return p;
}
#endif
