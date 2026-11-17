#include "platform/windows_paths.h"
/* Dedicated army install mailbox. Expected token comes from the current server
 * clock grant; stale files from trade, an old session or an old epoch cannot load. */
#ifndef ARMY_INSTALL_NATIVE_H
#define ARMY_INSTALL_NATIVE_H
#include <stdio.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#endif
static char army_installed_token[65];
static void army_install_reset(void){army_installed_token[0]=0;}
static int army_install_poll(const char *dir,unsigned long long completed,const char *expected,int (*load)(const char *)){
 if(!expected || strlen(expected)!=64 || strspn(expected,"0123456789abcdef")!=64)return 0;
 char path[2048],tmp[2048],token[65]={0},extra;unsigned long long tick=0;
 snprintf(path,sizeof(path),"%s/army-install.txt",dir);FILE *f=fopen(path,"rb");if(!f)return 0;
 int valid=fscanf(f,"%64s %llu",token,&tick)==2 && fscanf(f," %c",&extra)==EOF;fclose(f);
 if(!valid || tick!=completed || strcmp(token,expected))return 0;
 if(strcmp(army_installed_token,token)){
  snprintf(path,sizeof(path),"%s/army-install-%s.sav",dir,token);
  if(!load(path))return 0;
  strcpy(army_installed_token,token);
 }
 snprintf(tmp,sizeof(tmp),"%s/army-installed.tmp",dir);f=fopen(tmp,"wb");if(!f)return 0;
 fprintf(f,"%s",token);if(fclose(f))return 0;
 snprintf(path,sizeof(path),"%s/army-installed.txt",dir);
#ifdef _WIN32
 return augustus_move_file(tmp,path,MOVEFILE_REPLACE_EXISTING)!=0;
#else
 return rename(tmp,path)==0;
#endif
}
#endif
