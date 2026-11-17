#include "platform/windows_paths.h"
#include <stdlib.h>
#include <wchar.h>
#include "post_runtime.h"
#include "post_logistics.h"
#include "city/resource.h"
#include "multiplayer/trade_catalog.h"
#include "game/resource.h"
#include "army_live.h"
#include "post_ipc.h"
#include "visit.h"
#include <windows.h>
#include <bcrypt.h>
#include <stdio.h>
#include <string.h>
#include "game/file_io.h"
#include "clock.h"
#include "observe_channel.h"
static obs_channel observation;
static ULONGLONG observation_due;
static void observation_poll(const char *dir){
 ULONGLONG now=GetTickCount64();if(now<observation_due)return;observation_due=now+200;
 if(!obs_open(&observation,dir,"observe-channel",OBS_CAP))return;
 unsigned request;memcpy(&request,observation.mem,4);if(!request || request==observation.request)return;
 observation.request=request;unsigned length=0;unsigned char *data=game_file_io_capture_view(&length);
 if(data){obs_write(&observation,data,length,request,mp_clock_completed());free(data);}
}
static ULONGLONG stock_due;
static void stock_poll(const char *dir){
 ULONGLONG now=GetTickCount64();if(now<stock_due)return;stock_due=now+1000;
 char path[4096],temp[4096];snprintf(path,sizeof(path),"%s/trade-stock.txt",dir);snprintf(temp,sizeof(temp),"%s/trade-stock.tmp",dir);
 FILE*f=fopen(temp,"wb");if(!f)return;
 for(int i=0;i<MP_TRADE_RESOURCE_COUNT;i++){int res=trade_resource_ids[i];if(!res)continue;int n=city_resource_get_total_amount(res,0)+mp_post_city_stock(res);if(n>0)fprintf(f,"%d %d\n",res,n);}
 if(!fclose(f)){remove(path);rename(temp,path);}
 snprintf(path,sizeof(path),"%s/trade-storage-stock.txt",dir);snprintf(temp,sizeof(temp),"%s/trade-storage-stock.tmp",dir);
 f=fopen(temp,"wb");if(!f)return;
 for(int i=0;i<MP_TRADE_RESOURCE_COUNT;i++){int res=trade_resource_ids[i];if(!res)continue;int n=city_resource_get_total_amount(res,0);if(n>0)fprintf(f,"%d %d\n",res,n);}
 if(!fclose(f)){remove(path);rename(temp,path);}
}
static post_ipc endpoint;
static unsigned revision;
static int published;
static int name(wchar_t *out,const char *dir,const char *base) {
    char utf8[4096];int n=snprintf(utf8,sizeof(utf8),"%s/%s",dir,base);
    if(n<=0 || n>=(int)sizeof(utf8))return 0;
    /* Extended Win32 paths do not normalize forward slashes. Share the same
       normalization as SAV I/O before calling wide-character file APIs. */
    wchar_t *normalized=augustus_windows_path(utf8);
    if(!normalized)return 0;
    size_t length=wcslen(normalized);
    if(length>=4096){free(normalized);return 0;}
    memcpy(out,normalized,(length+1)*sizeof(wchar_t));free(normalized);return 1;
}
void mp_post_runtime_reset(void){memset(&endpoint,0,sizeof(endpoint));published=0;revision=mp_post_city_revision();}
void mp_post_runtime_poll(const char *dir) {
    if(mp_visit_active())return;
    /* Read-only observation and inventory publication do not depend on the
       authenticated transaction endpoint. Never let its retry hide a city. */
    stock_poll(dir);
    observation_poll(dir);
    wchar_t path[4096],temp[4096];
    if(revision!=mp_post_city_revision())mp_post_runtime_reset();
    if(!endpoint.ready) {
        char scope[65];unsigned owner;unsigned char run[16];
        if(!name(path,dir,"post-capability.bin"))return;DeleteFileW(path);
        if(!name(path,dir,"post-identity.txt"))return;
        FILE *f=_wfopen(path,L"rb");if(!f)return;
        int n=fscanf(f,"%64s %u",scope,&owner);fclose(f);
        if(n!=2 || BCryptGenRandom(0,run,16,BCRYPT_USE_SYSTEM_PREFERRED_RNG)!=0 || !post_ipc_init(&endpoint,run,scope,owner))return;
    }
    if(!published) {
        if(!name(path,dir,"post-capability.bin") || !name(temp,dir,"post-capability.tmp"))return;
        unsigned char bytes[84];memcpy(bytes,endpoint.run,16);memcpy(bytes+16,endpoint.roster,64);
        for(int i=0;i<4;i++)bytes[80+i]=(unsigned char)(endpoint.owner>>(8*i));
        FILE *f=_wfopen(temp,L"wb");if(!f)return;
        int ok=fwrite(bytes,1,sizeof(bytes),f)==sizeof(bytes);if(fclose(f))ok=0;
        if(!ok || !MoveFileExW(temp,path,MOVEFILE_REPLACE_EXISTING))return;published=1;
    }
    post_ipc_poll(&endpoint,dir);
    mp_army_poll(dir);
}
