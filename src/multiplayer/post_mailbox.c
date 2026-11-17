#include <string.h>
#include "platform/windows_paths.h"
#include <stdlib.h>
#include <wchar.h>
#include "post_ipc.h"
#include <stdio.h>
#include <windows.h>
static int path(wchar_t *out,const char *directory,const char *name) {
    char utf8[4096];int n=snprintf(utf8,sizeof(utf8),"%s/%s",directory,name);
    if(n<=0 || n>=(int)sizeof(utf8))return 0;
    /* Extended Win32 paths do not normalize forward slashes. Share the same
       normalization as SAV I/O before calling wide-character file APIs. */
    wchar_t *normalized=augustus_windows_path(utf8);
    if(!normalized)return 0;
    size_t length=wcslen(normalized);
    if(length>=4096){free(normalized);return 0;}
    memcpy(out,normalized,(length+1)*sizeof(wchar_t));free(normalized);return 1;
}
int post_ipc_poll(post_ipc *s,const char *directory) {
    wchar_t request[4096],response[4096],temp[4096];
    unsigned char p[POST_IPC_REQUEST+1],out[POST_IPC_RESPONSE];
    if(!s->ready || !path(request,directory,"post-request.bin") ||
       !path(response,directory,"post-response.bin") || !path(temp,directory,"post-response.tmp"))return 0;
    FILE *f=_wfopen(request,L"rb");if(!f)return 0;
    size_t n=fread(p,1,sizeof(p),f);int error=ferror(f);fclose(f);
    if(error || !post_ipc_exchange(s,p,n,out,sizeof(out)))return 0;
    if(s->published==s->sequence)return 1;
    f=_wfopen(temp,L"wb");if(!f)return 0;
    int ok=fwrite(out,1,sizeof(out),f)==sizeof(out);
    if(fclose(f))ok=0;
    if(!ok || !MoveFileExW(temp,response,MOVEFILE_REPLACE_EXISTING))return 0;
    s->published=s->sequence;return 1;
}
