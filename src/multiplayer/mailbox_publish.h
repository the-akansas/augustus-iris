#include "platform/windows_paths.h"
#ifndef MP_MAILBOX_PUBLISH_H
#define MP_MAILBOX_PUBLISH_H
#include <stdio.h>
#include <string.h>
#include <windows.h>
/* Main-thread publication of derived status. Compare the real file, not just
   a memory cache: removed, truncated or damaged mailboxes must heal on retry. */
static int mp_publish_text(const char *dir,const char *base,const char *data,size_t length){
 char path[4096],tmp[4096];
 if(snprintf(path,sizeof(path),"%s/%s.txt",dir,base)>=(int)sizeof(path) ||
    snprintf(tmp,sizeof(tmp),"%s/%s.tmp",dir,base)>=(int)sizeof(tmp))return 0;
 FILE*f=fopen(path,"rb");int same=f!=NULL;
 if(f){
  char buf[512];size_t offset=0;
  while(same && offset<length){size_t n=length-offset;if(n>sizeof(buf))n=sizeof(buf);
   if(fread(buf,1,n,f)!=n || memcmp(buf,data+offset,n))same=0;offset+=n;
  }
  if(same && (fgetc(f)!=EOF || ferror(f)))same=0;
  fclose(f);if(same)return 1;
 }
 f=fopen(tmp,"wb");if(!f)return 0;
 int ok=fwrite(data,1,length,f)==length;if(fclose(f))ok=0;
 return ok && augustus_move_file(tmp,path,MOVEFILE_REPLACE_EXISTING);
}
#endif
