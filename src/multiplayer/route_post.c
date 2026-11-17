#include "route_post.h"
#include "clock.h"
#include "core/time.h"
#include "building/building.h"
#include "building/state.h"
#include "assets/assets.h"
#include "graphics/image.h"
#include "core/image.h"
#include "core/image_group.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static int selected;
/* Colour tables come from the multiplayer bridge folder. A city-view renderer (observing another city) runs without
 * the bridge on purpose; it reads copies of the same tables from its own visit folder (city_visit.py). */
static const char *color_dir(void){const char*d=getenv("AUGUSTUS_MP_BRIDGE");if(d && *d)return d;d=getenv("AUGUSTUS_CITY_VISIT");return d && *d?d:0;}
static uint32_t player_color(int index){
 /* Eight pastel player colours: sky, coral, mint, apricot, lavender, aqua, rose, lemon (no white: next to the
  * grey of an unowned mark it read as a missing colour). Same table in window/multiplayer_lobby_map.inc. */
 static const uint32_t colors[8]={0xff7fb8f5,0xfff28b82,0xff7fd6a0,0xfff7b267,0xffb9a0f0,0xff6fd3cf,0xfff5a3cf,0xffe3d96b};
 return index>=0 && index<8?colors[index]:0xffcbd1d7;
}
uint32_t mp_player_color(int index){return player_color(index);}
uint32_t mp_route_empire_color(int name_id){
 static unsigned read_at;static int initialized,count,ids[8],colors[8];unsigned now=time_get_millis();
 if(!initialized || now-read_at>=250){
  initialized=1;read_at=now;count=0;const char*dir=color_dir();
  if(dir){char path[2048];snprintf(path,sizeof(path),"%s/empire-player-colors.txt",dir);FILE*f=fopen(path,"rb");
   if(f){int id,color;while(count<8 && fscanf(f,"%d %d",&id,&color)==2){
    if(id>0 && color>=-1 && color<8){ids[count]=id;colors[count++]=color;}}
    fclose(f);}}
 }
 /* A player city nobody plays (seat never taken, or its player left) flies a white flag. */
 for(int i=0;i<count;i++)if(ids[i]==name_id)return colors[i]<0?0xfff4f4f0:player_color(colors[i]);
 return 0; /* Non-player cities keep their original graphics. */
}
uint32_t mp_route_peer_color(int peer){
 static unsigned read_at;static int initialized,assigned[9];unsigned now=time_get_millis();
 if(peer<1 || peer>8)return 0xffcbd1d7;
 if(!initialized || now-read_at>=250){
  initialized=1;read_at=now;for(int i=0;i<9;i++)assigned[i]=-1;
  const char*dir=color_dir();
  if(dir){char path[2048];snprintf(path,sizeof(path),"%s/route-player-colors.txt",dir);FILE*f=fopen(path,"rb");
   if(f){int slot,value;while(fscanf(f,"%d %d",&slot,&value)==2)
    if(slot>=1 && slot<=8 && value>=-1 && value<8)assigned[slot]=value;
    fclose(f);}}
 }
 return player_color(assigned[peer]);
}
void mp_route_reset(void){selected=0;}
/* Cloth-only shading (assets MP_Flags, made from per-frame cloth masks): the original frame stays,
 * its cloth is redrawn as brightness x player colour. Frames without a mask keep the old wash. */
static int flag_shade(int image_id){
 static int built,count,ids[64],shades[64];
 if(!built){
  built=1;int missing=assets_get_image_id("MP_Flags","");char name[32];
  /* GROUP_EMPIRE_CITY: the player's own city flag (black cloth, gold eagle); its mask leaves the eagle alone. */
  const int groups[4]={GROUP_EMPIRE_CITY,GROUP_EMPIRE_CITY_TRADE,GROUP_EMPIRE_CITY_DISTANT_ROMAN,GROUP_EMPIRE_FOREIGN_CITY};
  for(int g=0;g<4;g++)for(int k=1;k<=6 && count<64;k++){snprintf(name,sizeof(name),"E%d_%d",groups[g],k);int sh=assets_get_image_id("MP_Flags",name);if(sh!=missing){ids[count]=image_group(groups[g])+k;shades[count++]=sh;}}
  for(int k=1;k<=8 && count<64;k++){char flag[32];snprintf(flag,sizeof(flag),"Warehouse_Flag_All_%d",k);snprintf(name,sizeof(name),"P_%d",k);
   int id=assets_get_image_id("UI",flag),sh=assets_get_image_id("MP_Flags",name);if(sh!=missing && id!=missing){ids[count]=id;shades[count++]=sh;}}
  for(int k=0;k<27 && count<64;k++){snprintf(name,sizeof(name),"S_%d",k);int sh=assets_get_image_id("MP_Flags",name);if(sh!=missing){ids[count]=image_group(GROUP_FIGURE_FORT_FLAGS)+k;shades[count++]=sh;}}
 }
 for(int i=0;i<count;i++)if(ids[i]==image_id)return shades[i];
 return 0;
}
void mp_draw_player_tint(int image_id,int x,int y,uint32_t player,uint32_t color_mask,float scale){
 image_draw(image_id,x,y,color_mask,scale);
 if(!player)return;
 int shade=flag_shade(image_id);
 if(shade)image_draw(shade,x,y,((player&0x00ffffffu)|0xff000000u)&color_mask,scale);
 else image_draw_silhouette(image_id,x,y,(player&0x00ffffffu)|0xcc000000u,scale);
}
/* The original warehouse permission flag: a small cloth pennant on a pole. */
int mp_player_pennant_image(void){static int id;if(!id)id=assets_get_image_id("UI","Warehouse_Flag_All_1");return id;}
/* The empire map's own waving city flag, carried as a legion standard. */
int mp_player_standard_image(void){return image_group(GROUP_EMPIRE_CITY)+1+(int)((time_get_millis()/160)%6);}
uint32_t mp_army_token_color(unsigned token){
 static unsigned read_at,tokens[32];static int initialized,count,colors[32];unsigned now=time_get_millis();
 if(!token)return 0;
 if(!initialized || now-read_at>=500){
  initialized=1;read_at=now;count=0;const char*dir=color_dir();
  if(dir){char path[2048];snprintf(path,sizeof(path),"%s/army-colors.txt",dir);FILE*f=fopen(path,"rb");
   if(f){unsigned t;int c;while(count<32 && fscanf(f,"%u %d",&t,&c)==2)if(t && c>=0 && c<8){tokens[count]=t;colors[count++]=c;}fclose(f);}}
 }
 for(int i=0;i<count;i++)if(tokens[i]==token)return player_color(colors[i]);
 return 0;
}
static int lookup(const char *city,int wanted,int *state,int *revision){
 *state=*revision=0;const char *dir=getenv("AUGUSTUS_MP_BRIDGE");if(!dir || !mp_clock_active())return 0;
 char path[2048],id[64];snprintf(path,sizeof(path),"%s/route-state.txt",dir);FILE *f=fopen(path,"rb");if(!f)return 0;
 int peer,s,r,result=0;
 while(fscanf(f,"%d %63s %d %d",&peer,id,&s,&r)==4){
  if(peer<1 || peer>8 || s<0 || s>3 || r<0)continue;
  if((city && !strcmp(id,city)) || (!city && peer==wanted)){result=peer;*state=s;*revision=r;break;}
 }fclose(f);return result;
}
int mp_route_peer(const char *city,int *state,int *revision){return lookup(city,0,state,revision);}
int mp_route_post_for(int peer){
 if(peer<1 || peer>8)return 0;
 for(unsigned i=1;i<building_count();i++){
  building *b=building_get(i);
  /* A post placed this tick is still CREATED (the clock may be waiting on another city): it counts. */
  if(b->type==BUILDING_PLAYER_TRADE_POST && (b->state==BUILDING_STATE_IN_USE || b->state==BUILDING_STATE_CREATED) && b->subtype.orientation==peer)return i;
 }return 0;
}
int mp_route_build_peer(void){int state,revision;return selected && lookup(0,selected,&state,&revision) && state==1 && !mp_route_post_for(selected)?selected:0;}
int mp_route_select(int peer){selected=peer;if(!mp_route_build_peer()){selected=0;return 0;}return 1;}
#include "post_logistics.inc"
